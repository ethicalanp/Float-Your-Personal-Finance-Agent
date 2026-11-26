import argparse
import asyncio
import getpass
import sys
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import get_async_engine, get_async_session_factory
from app.models.admin import AdminUser


async def create_or_update_admin(
    username: str,
    password: str,
    is_superuser: bool = False,
    session: AsyncSession | None = None,
) -> AdminUser:
    """Create or update an administrative user account."""
    if not username or not username.strip():
        raise ValueError("Username cannot be blank.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    username = username.strip()
    hashed = hash_password(password)

    if session is not None:
        stmt = select(AdminUser).where(AdminUser.username == username)
        res = await session.execute(stmt)
        admin = res.scalars().first()

        if admin:
            admin.hashed_password = hashed
            admin.is_active = True
            admin.is_superuser = is_superuser
        else:
            admin = AdminUser(
                username=username,
                hashed_password=hashed,
                is_active=True,
                is_superuser=is_superuser,
            )
            session.add(admin)

        await session.commit()
        await session.refresh(admin)
        return admin

    session_factory = get_async_session_factory()
    async with session_factory() as s:
        stmt = select(AdminUser).where(AdminUser.username == username)
        res = await s.execute(stmt)
        admin = res.scalars().first()

        if admin:
            admin.hashed_password = hashed
            admin.is_active = True
            admin.is_superuser = is_superuser
            print(f"Updated existing admin user '{username}'.")
        else:
            admin = AdminUser(
                username=username,
                hashed_password=hashed,
                is_active=True,
                is_superuser=is_superuser,
            )
            s.add(admin)
            print(f"Created new admin user '{username}'.")

        await s.commit()
        await s.refresh(admin)
        return admin


async def main_async(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update an internal Float admin user.")
    parser.add_argument("--username", "-u", help="Admin username")
    parser.add_argument("--password", "-p", help="Admin password (insecure via CLI history; prompt preferred)")
    parser.add_argument("--superuser", "-s", action="store_true", help="Grant superuser privileges")

    args = parser.parse_args(argv)

    username = args.username
    if not username:
        username = input("Enter admin username: ").strip()

    password = args.password
    if not password:
        password = getpass.getpass("Enter admin password (min 8 chars): ")
        password_confirm = getpass.getpass("Confirm admin password: ")
        if password != password_confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            return 1

    try:
        await create_or_update_admin(
            username=username,
            password=password,
            is_superuser=args.superuser,
        )
    finally:
        await get_async_engine().dispose()

    return 0


def cli_main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    code = asyncio.run(main_async(sys.argv[1:]))
    sys.exit(code)


if __name__ == "__main__":
    cli_main()
