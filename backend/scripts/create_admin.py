"""Cấp quyền admin cho tài khoản (không có đường đăng ký admin qua web).

Usage:
    cd backend
    venv\\Scripts\\python.exe scripts\\create_admin.py admin@example.com           # nâng quyền tài khoản đã đăng ký
    venv\\Scripts\\python.exe scripts\\create_admin.py admin@example.com --create  # tạo mới, hỏi mật khẩu
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.repositories.user_repository import UserRepository  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.auth_service import hash_password  # noqa: E402

MIN_PASSWORD_LENGTH = 8


async def main(email: str, create: bool) -> int:
    email = email.strip().lower()
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        if user is None:
            if not create:
                print(f"Không có tài khoản {email}. Đăng ký trước, hoặc chạy lại với --create.")
                return 1
            password = getpass.getpass("Mật khẩu cho admin mới: ")
            if len(password) < MIN_PASSWORD_LENGTH or password != getpass.getpass("Nhập lại mật khẩu: "):
                print(f"Mật khẩu phải từ {MIN_PASSWORD_LENGTH} ký tự và nhập lại khớp.")
                return 1
            user = await repo.create_user(email=email, password_hash=hash_password(password), full_name="Admin")
        user.role = "admin"
        user.is_active = True
        await session.commit()
    print(f"Đã cấp quyền admin cho {email}.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--create", action="store_true", help="tạo tài khoản nếu chưa có")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.email, args.create)))
