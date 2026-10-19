# tests/test_exception_flow.py
# Tests for the exception rule engine when it runs inside the real API:
# what happens to the status, the tasks and the audit log after a failed delivery attempt.
import json

import pytest
from sqlalchemy import select

from app.models import AuditLog, ExceptionTask, Rider, UserRole, Zone
import uuid


@pytest.fixture
def client(client, make_user, auth):
    # Act as an admin, same as the older shipment tests.
    admin = make_user(role=UserRole.ADMIN)
    client.headers.update(auth(admin))
    return client


def make_zone_and_rider(db):
    zone = Zone(name=f"FlowZone-{uuid.uuid4().hex[:8]}")  # random name, never clashes with seeded zones
    db.add(zone)
    db.flush()
    rider = Rider(name="Flow Rider", zone_id=zone.id, daily_capacity=10)
    db.add(rider)
    db.flush()
    return zone, rider


def set_status(client, shipment_id, status, **extra):
    return client.post(f"/shipments/{shipment_id}/status", json={"new_status": status, **extra})


def new_out_for_delivery(client, db, is_cod=False):
    """Creates a shipment and moves it to out_for_delivery. Returns (shipment_id, zone, rider)."""
    zone, rider = make_zone_and_rider(db)
    payload = {
        "recipient_name": "Flow Person",
        "recipient_phone": "01712345678",
        "address": "House 1, Road 2",
        "zone_id": zone.id,
        "is_cod": is_cod,
        "cod_amount": "900.00" if is_cod else "0.00",
    }
    shipment_id = client.post("/shipments", json=payload).json()["id"]
    assert set_status(client, shipment_id, "assigned", rider_id=rider.id).status_code == 200
    assert set_status(client, shipment_id, "out_for_delivery").status_code == 200
    return shipment_id, zone, rider


def tasks_of(db, shipment_id):
    return db.scalars(select(ExceptionTask).where(ExceptionTask.shipment_id == shipment_id)).all()


def rule_decisions_of(db, shipment_id):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_id == shipment_id, AuditLog.action == "rule_decision")
        .order_by(AuditLog.id)
    ).all()
    return [json.loads(row.details) for row in rows]


def test_phone_off_reschedules_and_creates_sms_task(client, db):
    shipment_id, _, _ = new_out_for_delivery(client, db)
    response = set_status(client, shipment_id, "attempt_failed", failure_reason="phone_off")
    assert response.json()["status"] == "rescheduled"

    tasks = tasks_of(db, shipment_id)
    assert [(t.task_type, t.status, t.reason, t.rule_version) for t in tasks] == [
        ("sms_reminder", "open", "phone_off", "1.0.0")
    ]
    decision = rule_decisions_of(db, shipment_id)[0]
    assert decision["rule_version"] == "1.0.0"
    assert decision["matched_rule"] == "reason:phone_off"


def test_wrong_address_waits_for_human_and_creates_customer_service_task(client, db):
    shipment_id, _, _ = new_out_for_delivery(client, db)
    response = set_status(client, shipment_id, "attempt_failed", failure_reason="wrong_address")
    assert response.json()["status"] == "attempt_failed"  # no automatic next status
    assert [t.task_type for t in tasks_of(db, shipment_id)] == ["customer_service_task"]


def test_refused_by_customer_returns_to_sender_without_tasks(client, db):
    shipment_id, _, _ = new_out_for_delivery(client, db)
    response = set_status(client, shipment_id, "attempt_failed", failure_reason="refused_by_customer")
    assert response.json()["status"] == "return_to_sender"
    assert tasks_of(db, shipment_id) == []


def test_unknown_reason_uses_default_rule(client, db):
    shipment_id, _, _ = new_out_for_delivery(client, db)
    response = set_status(client, shipment_id, "attempt_failed", failure_reason="dog_bit_the_rider")
    assert response.json()["status"] == "attempt_failed"
    assert [t.task_type for t in tasks_of(db, shipment_id)] == ["customer_service_task"]
    assert rule_decisions_of(db, shipment_id)[0]["matched_rule"] == "default"


def test_third_failed_attempt_returns_to_sender_and_records_cod_block(client, db):
    shipment_id, _, rider = new_out_for_delivery(client, db, is_cod=True)
    # attempts 1 and 2: phone_off, so the engine reschedules and we assign the rider again
    for _ in range(2):
        assert set_status(client, shipment_id, "attempt_failed", failure_reason="phone_off").json()["status"] == "rescheduled"
        assert set_status(client, shipment_id, "assigned", rider_id=rider.id).status_code == 200
        assert set_status(client, shipment_id, "out_for_delivery").status_code == 200

    # attempt 3: max_attempts beats the phone_off rule
    response = set_status(client, shipment_id, "attempt_failed", failure_reason="phone_off")
    assert response.json()["status"] == "return_to_sender"
    assert response.json()["attempt_count"] == 3

    last = rule_decisions_of(db, shipment_id)[-1]
    assert last["matched_rule"] == "max_attempts"
    assert last["block_cod"] is True  # recorded only, not enforced yet