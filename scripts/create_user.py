# scripts/create_user.py
# Creates a user. The password is typed hidden, hashed, and only the hash is stored.
import argparse
import getpass

from pwdlib import PasswordHash
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    parser.add_argument("--rider-id", type=int, default=None, help="only for users with the rider role")
    args = parser.parse_args()

    username = args.username.strip().lower()  # always lower case, so "Admin" and "admin" are the same user

    password = getpass.getpass("Password (hidden): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    with SessionLocal() as session:
        if session.scalar(select(User).where(User.username == username)) is not None:
            raise SystemExit(f"User '{username}' already exists.")
        user = User(
            username=username,
            password_hash=PasswordHash.recommended().hash(password),
            role=UserRole(args.role),
            rider_id=args.rider_id,
        )
        session.add(user)
        session.commit()
        print(f"Created user '{username}' with role '{args.role}' (id={user.id})")


if __name__ == "__main__":
    main()
