# tests/conftest.py
# Shared test fixtures. pytest loads this file automatically for every test file in this folder.
# Every test runs inside a database transaction that is rolled back at the end, so no rows are left behind.
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.deps import get_db
from app.main import app
from app.models import User, UserRole
from app.security import create_access_token, hash_password


@pytest.fixture
def db():
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db):
    # Returns a function that creates a user with a random name inside the test transaction.
    def _make(role=UserRole.DISPATCHER, rider_id=None, active=True, password="test-password-123"):
        user = User(
            username=f"user_{uuid.uuid4().hex[:10]}",
            password_hash=hash_password(password),
            role=role,
            rider_id=rider_id,
            is_active=active,
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def auth():
    # Returns a function: user -> {"Authorization": "Bearer <token>"} header.
    def _auth(user):
        token = create_access_token(user.id, user.role.value)
        return {"Authorization": f"Bearer {token}"}

    return _auth
