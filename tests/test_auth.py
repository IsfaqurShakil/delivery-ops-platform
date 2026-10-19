# tests/test_auth.py
# Tests for login and for token handling. Runs against the real PostgreSQL database (rolled back after each test).
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.db import settings
from app.models import User, UserRole
from app.security import ALGORITHM, create_access_token, decode_token, hash_password

PASSWORD = "test-password-123"
WRONG_MESSAGE = "Incorrect username or password"


def make_user(db, *, role=UserRole.DISPATCHER, active=True, password=PASSWORD) -> User:
    user = User(
        username=f"user_{uuid.uuid4().hex[:10]}",  # random name, never clashes with real users
        password_hash=hash_password(password),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.flush()
    return user


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


def test_login_success(client, db):
    user = make_user(db, role=UserRole.DISPATCHER)
    response = login(client, user.username, PASSWORD)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    claims = decode_token(body["access_token"])
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "dispatcher"
    assert claims["exp"] - claims["iat"] == settings.jwt_expire_minutes * 60


def test_login_wrong_password(client, db):
    user = make_user(db)
    response = login(client, user.username, "wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"] == WRONG_MESSAGE


def test_login_unknown_user_gives_same_message(client):
    response = login(client, "no_such_user_" + uuid.uuid4().hex[:8], PASSWORD)
    assert response.status_code == 401
    # Same text as a wrong password, so an attacker cannot find out which usernames exist.
    assert response.json()["detail"] == WRONG_MESSAGE


def test_login_inactive_user(client, db):
    user = make_user(db, active=False)
    assert login(client, user.username, PASSWORD).status_code == 401


def test_login_username_is_case_insensitive_and_trimmed(client, db):
    user = make_user(db)
    assert login(client, f"  {user.username.upper()}  ", PASSWORD).status_code == 200


@pytest.mark.parametrize("form", [{}, {"username": "someone"}, {"password": "secret"}])
def test_login_missing_fields(client, form):
    assert client.post("/login", data=form).status_code == 422


def test_response_contains_only_token_fields(client, db):
    user = make_user(db)
    body = login(client, user.username, PASSWORD).json()
    assert set(body) == {"access_token", "token_type"}  # no password hash, no extra user data


def test_stored_password_is_hashed(db):
    user = make_user(db)
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$argon2")


def test_token_with_wrong_signature_is_rejected():
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": expires}, "x" * 40, algorithm=ALGORITHM)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(forged)


def test_expired_token_is_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"sub": "1", "role": "admin", "exp": past}, settings.jwt_secret, algorithm=ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired)


def test_token_with_none_algorithm_is_rejected():
    # Classic attack: an unsigned token that says "no signature needed". We must refuse it.
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    unsigned = jwt.encode({"sub": "1", "role": "admin", "exp": expires}, "", algorithm="none")
    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_token(unsigned)


def test_short_secret_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "short")  # temporary, undone after the test
    with pytest.raises(RuntimeError):
        create_access_token(1, "admin")
