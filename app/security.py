# app/security.py
# Password checking and JWT (login token) creation/reading.
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.db import settings

ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32

password_hasher = PasswordHash.recommended()

# A hash of a throwaway password. Login compares against it when the username does not exist,
# so "unknown user" takes about as long as "wrong password" and timing does not leak which users exist.
DUMMY_HASH = password_hasher.hash("this-is-not-a-real-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hasher.verify(plain, hashed)


def _secret() -> str:
    if len(settings.jwt_secret) < MIN_SECRET_LENGTH:
        raise RuntimeError("JWT_SECRET is missing or too short (at least 32 characters). Check your .env file.")
    return settings.jwt_secret


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # "subject": who this token belongs to
        "role": role,
        "iat": now,  # issued at
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),  # expires at
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    # algorithms=[...] pins the one allowed signing method. "require" makes exp and sub mandatory.
    return jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
