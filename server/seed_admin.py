#!/usr/bin/env python3
"""Buat/update akun admin (atau akun lain) pada instance Pantau Server.

Cara pakai (dari folder server, pakai venv instance):
    env/bin/python seed_admin.py --username admin --password 'rahasia'
    env/bin/python seed_admin.py --username diyah --role viewer --password 'rahasia2'

Baca kredensial DB dari .env di folder yang sama (lihat config.py).
"""

import argparse

from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base, User

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--username", default="admin", help="nama user (default: admin)")
    ap.add_argument("--password", required=True, help="password baru")
    ap.add_argument("--role", default="admin", choices=["admin", "viewer"])
    args = ap.parse_args()

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user:
            user.password_hash = pwd_ctx.hash(args.password)
            user.role = args.role
            print(f"[OK] user '{args.username}' diperbarui (role={args.role})")
        else:
            db.add(User(
                username=args.username,
                password_hash=pwd_ctx.hash(args.password),
                role=args.role,
            ))
            print(f"[OK] user '{args.username}' dibuat (role={args.role})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()