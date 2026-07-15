"""Create an administrator account using the application's normal auth flow."""

from __future__ import annotations

import argparse
import asyncio
import getpass

from app.db.session import AsyncSessionFactory
from app.services.auth_service import AuthService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Pixpress1 administrator account.")
    parser.add_argument("username", help="Admin login username")
    parser.add_argument("password", nargs="?", help="Admin password; omit to enter it securely")
    return parser.parse_args()


async def create_admin(username: str, password: str) -> bool:
    async with AsyncSessionFactory() as session:
        user = await AuthService(session).create_admin_user(username, password)
        return user is not None


def main() -> int:
    args = parse_args()
    password = args.password or getpass.getpass("Admin password: ")
    if not password:
        print("Error: password cannot be empty.")
        return 2
    if not asyncio.run(create_admin(args.username, password)):
        print(f"Error: username already exists: {args.username}")
        return 1
    print(f"Admin created successfully: {args.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
