# tests/conftest.py
# Shared test fixtures. pytest loads this file automatically for every test file in this folder.
# Every test runs inside a database transaction that is rolled back at the end, so no rows are left behind.
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.deps import get_db
from app.main import app


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
