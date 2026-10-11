#!/usr/bin/env python3
"""Buat/update akun administrator, operator, atau viewer pada instance Pantau Server.

Cara pakai (dari folder server, pakai venv instance):
    # Buat/Update Master Admin:
    env/bin/python seed_admin.py --username masteradmin --password 'Katasandi@2026!' --role master_admin

    # Ganti nama akun admin bawaan (misal dari 'admin' ke 'sysops-bos'):
    env/bin/python seed_admin.py --rename-from admin --username sysops-bos

    # Buat Operator dengan izin kustom:
    env/bin/python seed_admin.py --username budi --password 'Katasandi@2026!' --role operator --permissions terminal,services,firewall

    # Reset 2FA darurat untuk user tertentu:
    env/bin/python seed_admin.py --username masteradmin --reset-2fa

Baca kredensial DB dari .env di folder yang sama (lihat config.py).
"""

import argparse
import json
import re
import sys
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base, User

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALL_OPERATOR_PERMS = [
    "can_terminal", "can_file_manager", "can_services", "can_processes",
    "can_firewall", "can_users_sys", "can_cron", "can_ssl",
    "can_server_control", "can_apt", "can_ota", "can_manage_servers", "can_manage_viewers"
]


def validate_password_strength(password: str) -> tuple[bool, str]:
    if not password:
        return False, "Password tidak boleh kosong."
    if len(password) < 12:
        return False, "Password minimal 12 karakter."
    if not re.search(r"[A-Z]", password):
        return False, "Password harus mengandung minimal 1 huruf besar (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password harus mengandung minimal 1 huruf kecil (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password harus mengandung minimal 1 angka (0-9)."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]", password):
        return False, "Password harus mengandung minimal 1 simbol khusus (!@#$%^&*...)."
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", help="Nama user target")
    ap.add_argument("--password", help="Password baru")
    ap.add_argument("--role", default="master_admin", choices=["master_admin", "admin", "operator", "viewer"],
                    help="Peran akun (default: master_admin)")
    ap.add_argument("--rename-from", help="Ganti nama user dari username lama ke --username baru")
    ap.add_argument("--permissions", help="Izin operator (koma dipisah, misal: terminal,services,firewall atau 'all')")
    ap.add_argument("--reset-2fa", action="store_true", help="Nonaktifkan 2FA dan hapus kode cadangan untuk user target")
    ap.add_argument("--force", action="store_true", help="Lewati validasi kompleksitas password")
    args = ap.parse_args()

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()

    try:
        # Aksi 1: Rename username lama
        if args.rename_from:
            if not args.username:
                print("[ERROR] Gunakan --username untuk menentukan nama baru!")
                sys.exit(1)
            u = db.query(User).filter(User.username == args.rename_from).first()
            if not u:
                print(f"[ERROR] User lama '{args.rename_from}' tidak ditemukan.")
                sys.exit(1)
            exist = db.query(User).filter(User.username == args.username).first()
            if exist and exist.id != u.id:
                print(f"[ERROR] Username baru '{args.username}' sudah dipakai akun lain.")
                sys.exit(1)
            u.username = args.username
            db.commit()
            print(f"[OK] Berhasil mengubah nama user '{args.rename_from}' menjadi '{args.username}'.")
            return

        target_username = args.username or "admin"

        # Aksi 2: Reset 2FA
        if args.reset_2fa:
            u = db.query(User).filter(User.username == target_username).first()
            if not u:
                print(f"[ERROR] User '{target_username}' tidak ditemukan.")
                sys.exit(1)
            u.totp_enabled = 0
            u.totp_secret = None
            u.recovery_codes = None
            db.commit()
            print(f"[OK] 2FA untuk user '{target_username}' telah di-reset (dinonaktifkan).")
            return

        # Aksi 3: Buat atau update password & role
        if not args.password:
            print("[ERROR] Parameter --password wajib diisi untuk membuat atau memperbarui akun.")
            sys.exit(1)

        if not args.force:
            valid, msg = validate_password_strength(args.password)
            if not valid:
                print(f"[ERROR] Password ditolak: {msg}")
                print("Tip: Gunakan password minimal 12 karakter dengan huruf besar, huruf kecil, angka, dan simbol.")
                print("Atau gunakan flag --force jika ingin memaksa.")
                sys.exit(1)

        role = "master_admin" if args.role in ("master_admin", "admin") else args.role

        # Parsing permission untuk operator
        perms_json = None
        if role == "operator":
            perms_dict = {p: False for p in ALL_OPERATOR_PERMS}
            if args.permissions:
                if args.permissions.strip().lower() == "all":
                    perms_dict = {p: True for p in ALL_OPERATOR_PERMS}
                else:
                    req_perms = [p.strip().lower() for p in args.permissions.split(",")]
                    for rp in req_perms:
                        key = f"can_{rp}" if not rp.startswith("can_") else rp
                        if key in perms_dict:
                            perms_dict[key] = True
            perms_json = json.dumps(perms_dict)

        user = db.query(User).filter(User.username == target_username).first()
        if user:
            user.password_hash = pwd_ctx.hash(args.password)
            user.role = role
            user.password_changed_at = datetime.utcnow()
            user.is_active = 1
            if role == "operator" and perms_json is not None:
                user.permissions = perms_json
            print(f"[OK] User '{target_username}' berhasil diperbarui (role={role})")
        else:
            db.add(User(
                username=target_username,
                password_hash=pwd_ctx.hash(args.password),
                role=role,
                is_active=1,
                password_changed_at=datetime.utcnow(),
                permissions=perms_json,
            ))
            print(f"[OK] User '{target_username}' berhasil dibuat (role={role})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()