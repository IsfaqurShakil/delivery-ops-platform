# tests/test_shipments_api.py
# API tests against the real PostgreSQL database.
# Each test runs inside a transaction that is rolled back at the end, so nothing is left behind.
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.deps import get_db
from app.main import app
from app.models import AuditLog, DeliveryAttempt, Rider, Zone

BAD_ID = 999_999_999  # an id that does not exist
ALL_STATUSES = [
    "created",
    "assigned",
    "out_for_delivery",
    "delivered",
    "attempt_failed",
    "rescheduled",
    "return_to_sender",
]


@pytest.fixture
def db():
    connection = engine.connect()
    outer = connection.begin()
    # create_savepoint: when the app calls commit(), it only releases a savepoint.
    # The real transaction stays open and is rolled back at the end of the test.
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db  # the app now uses our test session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_zone(db: Session) -> Zone:
    zone = Zone(name=f"TestZone-{uuid.uuid4().hex[:8]}")  # random name so it never clashes with seeded zones
    db.add(zone)
    db.flush()
    return zone


def make_rider(db: Session, zone: Zone, active: bool = True) -> Rider:
    rider = Rider(name="Test Rider", zone_id=zone.id, daily_capacity=10, is_active=active)
    db.add(rider)
    db.flush()
    return rider


def new_shipment(client, zone, **overrides):
    payload = {
        "recipient_name": "Test Person",
        "recipient_phone": "01712345678",
        "address": "House 1, Road 2",
        "zone_id": zone.id,
        "is_cod": False,
        "cod_amount": "0.00",
    }
    payload.update(overrides)
    return client.post("/shipments", json=payload)


def set_status(client, shipment_id, status, **extra):
    return client.post(f"/shipments/{shipment_id}/status", json={"new_status": status, **extra})


def deliver(client, db, zone=None):
    """Helper: creates a shipment and drives it all the way to delivered. Returns (shipment_id, rider)."""
    zone = zone or make_zone(db)
    rider = make_rider(db, zone)
    shipment_id = new_shipment(client, zone).json()["id"]
    assert set_status(client, shipment_id, "assigned", rider_id=rider.id).status_code == 200
    assert set_status(client, shipment_id, "out_for_delivery").status_code == 200
    assert set_status(client, shipment_id, "delivered").status_code == 200
    return shipment_id, rider


# ---------- creating shipments ----------

def test_create_shipment(client, db):
    zone = make_zone(db)
    response = new_shipment(client, zone)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["attempt_count"] == 0
    assert body["rider_id"] is None
    assert body["tracking_code"].startswith("DEL")


def test_create_cod_shipment(client, db):
    zone = make_zone(db)
    response = new_shipment(client, zone, is_cod=True, cod_amount="1500.00")
    assert response.status_code == 201
    assert Decimal(str(response.json()["cod_amount"])) == Decimal("1500.00")


def test_create_with_unknown_zone_returns_404(client):
    response = client.post(
        "/shipments",
        json={
            "recipient_name": "Test Person",
            "recipient_phone": "01712345678",
            "address": "House 1",
            "zone_id": BAD_ID,
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize("phone", ["12345", "01712", "abcdefghijk", "0171234567890"])
def test_create_rejects_bad_phone(client, db, phone):
    zone = make_zone(db)
    assert new_shipment(client, zone, recipient_phone=phone).status_code == 422


@pytest.mark.parametrize("is_cod,amount", [(False, "100.00"), (True, "0.00"), (True, "-5.00")])
def test_create_rejects_bad_cod_combination(client, db, is_cod, amount):
    zone = make_zone(db)
    assert new_shipment(client, zone, is_cod=is_cod, cod_amount=amount).status_code == 422


# ---------- reading shipments ----------

def test_get_shipment(client, db):
    zone = make_zone(db)
    shipment_id = new_shipment(client, zone).json()["id"]
    response = client.get(f"/shipments/{shipment_id}")
    assert response.status_code == 200
    assert response.json()["id"] == shipment_id


def test_get_unknown_shipment_returns_404(client):
    assert client.get(f"/shipments/{BAD_ID}").status_code == 404


# ---------- changing status ----------

def test_happy_path_and_audit_trail(client, db):
    zone = make_zone(db)
    rider = make_rider(db, zone)
    shipment_id = new_shipment(client, zone, is_cod=True, cod_amount="800.00").json()["id"]
    assert set_status(client, shipment_id, "assigned", rider_id=rider.id).status_code == 200
    assert set_status(client, shipment_id, "out_for_delivery").status_code == 200
    response = set_status(client, shipment_id, "delivered")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "delivered"
    assert body["attempt_count"] == 1
    assert body["rider_id"] == rider.id

    history = db.scalars(
        select(AuditLog.new_value)
        .where(AuditLog.entity_type == "shipment", AuditLog.entity_id == shipment_id)
        .order_by(AuditLog.id)
    ).all()
    assert history == ["created", "assigned", "out_for_delivery", "delivered"]


@pytest.mark.parametrize("target", ["delivered", "out_for_delivery", "attempt_failed"])
def test_illegal_transition_returns_409_and_changes_nothing(client, db, target):
    zone = make_zone(db)
    shipment_id = new_shipment(client, zone).json()["id"]
    assert set_status(client, shipment_id, target).status_code == 409
    assert client.get(f"/shipments/{shipment_id}").json()["status"] == "created"


def test_assign_requires_rider(client, db):
    zone = make_zone(db)
    shipment_id = new_shipment(client, zone).json()["id"]
    assert set_status(client, shipment_id, "assigned").status_code == 422


@pytest.mark.parametrize("case", ["unknown", "inactive", "other_zone"])
def test_assign_rejects_bad_rider(client, db, case):
    zone = make_zone(db)
    other_zone = make_zone(db)
    if case == "unknown":
        rider_id = BAD_ID
    elif case == "inactive":
        rider_id = make_rider(db, zone, active=False).id
    else:
        rider_id = make_rider(db, other_zone).id
    shipment_id = new_shipment(client, zone).json()["id"]
    assert set_status(client, shipment_id, "assigned", rider_id=rider_id).status_code == 422
    assert client.get(f"/shipments/{shipment_id}").json()["status"] == "created"


def test_failed_attempt_requires_reason(client, db):
    zone = make_zone(db)
    rider = make_rider(db, zone)
    shipment_id = new_shipment(client, zone).json()["id"]
    set_status(client, shipment_id, "assigned", rider_id=rider.id)
    set_status(client, shipment_id, "out_for_delivery")
    assert set_status(client, shipment_id, "attempt_failed").status_code == 422
    assert client.get(f"/shipments/{shipment_id}").json()["status"] == "out_for_delivery"


def test_failed_attempt_then_reschedule_then_deliver(client, db):
    zone = make_zone(db)
    rider = make_rider(db, zone)
    shipment_id = new_shipment(client, zone).json()["id"]
    set_status(client, shipment_id, "assigned", rider_id=rider.id)
    set_status(client, shipment_id, "out_for_delivery")

    failed = set_status(client, shipment_id, "attempt_failed", failure_reason="phone_off")
    assert failed.status_code == 200
    assert failed.json()["attempt_count"] == 1

    assert set_status(client, shipment_id, "rescheduled").status_code == 200
    assert set_status(client, shipment_id, "assigned", rider_id=rider.id).status_code == 200
    assert set_status(client, shipment_id, "out_for_delivery").status_code == 200
    assert set_status(client, shipment_id, "delivered").status_code == 200

    assert client.get(f"/shipments/{shipment_id}").json()["attempt_count"] == 2
    attempts = db.scalars(
        select(DeliveryAttempt).where(DeliveryAttempt.shipment_id == shipment_id).order_by(DeliveryAttempt.attempt_no)
    ).all()
    assert [(a.attempt_no, a.outcome, a.failure_reason) for a in attempts] == [
        (1, "failed", "phone_off"),
        (2, "delivered", None),
    ]


def test_delivered_shipment_cannot_change(client, db):
    shipment_id, rider = deliver(client, db)
    for status in ALL_STATUSES:
        response = set_status(client, shipment_id, status, rider_id=rider.id, failure_reason="x")
        assert response.status_code == 409, status


def test_unknown_status_value_returns_422(client, db):
    zone = make_zone(db)
    shipment_id = new_shipment(client, zone).json()["id"]
    assert set_status(client, shipment_id, "flying").status_code == 422


def test_status_change_on_unknown_shipment_returns_404(client):
    assert set_status(client, BAD_ID, "assigned", rider_id=1).status_code == 404
