# tests/test_audit_log.py
# Tests that run against the real PostgreSQL database.
# They prove the audit log really is append-only (the database itself refuses changes).
import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError

from app.db import SessionLocal
from app.models import AuditLog


@pytest.fixture
def db():
    # Every test runs inside a transaction that is rolled back at the end,
    # so tests leave no rows behind (audit_log rows cannot be deleted by design).
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _new_entry() -> AuditLog:
    return AuditLog(
        entity_type="shipment",
        entity_id=1,
        action="status_change",
        old_value="created",
        new_value="assigned",
        actor="test",
    )


def test_insert_is_allowed(db):
    entry = _new_entry()
    db.add(entry)
    db.flush()  # sends the INSERT to the database inside our transaction
    assert entry.id is not None


def test_update_is_blocked(db):
    entry = _new_entry()
    db.add(entry)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(update(AuditLog).where(AuditLog.id == entry.id).values(actor="hacker"))


def test_delete_is_blocked(db):
    entry = _new_entry()
    db.add(entry)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(delete(AuditLog).where(AuditLog.id == entry.id))


def test_truncate_is_blocked(db):
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("TRUNCATE TABLE audit_log"))
