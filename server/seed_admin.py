#!/usr/bin/env python3
import sys
import argparse
from datetime import datetime
from core.database import SessionLocal
from core.security import get_password_hash
from models.user import User

def main():
    parser = argparse.ArgumentParser(description="Kelola akun pengguna Pantau Server")
    parser.add_argument("--username", required=True, help="Username target")
    parser.add_argument("--password", required=True, help="Password baru")
    parser.add_argument("--role", default="master_admin", choices=["master_admin", "operator", "viewer"])
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        hashed = get_password_hash(args.password)
        now = datetime.utcnow()
        if user:
            user.password_hash = hashed
            user.role = args.role
            user.is_active = 1
            user.password_changed_at = now
            print(f"[OK] Akun '{args.username}' berhasil diperbarui dengan password baru.")
        else:
            new_user = User(
                username=args.username,
                password_hash=hashed,
                role=args.role,
                is_active=1,
                password_changed_at=now,
            )
            db.add(new_user)
            print(f"[OK] Akun baru '{args.username}' (role={args.role}) berhasil dibuat.")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    main()
