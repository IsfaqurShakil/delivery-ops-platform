# tests/test_rbac.py
# Tests for who may do what. Runs against the real PostgreSQL database (rolled back after each test).
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy import select

from app.db import settings
from app.models import AuditLog, Rider, UserRole, Zone
from app.security import ALGORITHM, create_access_token


def make_zone(db):
    zone = Zone(name=f"RbacZone-{uuid.uuid4().hex[:8]}")  # random name, never clashes with seeded zones
    db.add(zone)
    db.flush()
    return zone


def make_rider(db, zone):
    rider = Rider(name="Rbac Rider", zone_id=zone.id, daily_capacity=10, is_active=True)
    db.add(rider)
    db.flush()
    return rider


def shipment_payload(zone):
    return {
        "recipient_name": "Test Person",
        "recipient_phone": "01712345678",
        "address": "House 1, Road 2",
        "zone_id": zone.id,
    }


def create_as(client, auth, user, zone):
    response = client.post("/shipments", json=shipment_payload(zone), headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def status_as(client, auth, user, shipment_id, status, **extra):
    return client.post(
        f"/shipments/{shipment_id}/status",
        json={"new_status": status, **extra},
        headers=auth(user),
    )


@pytest.fixture
def world(db, client, make_user, auth):
    """One zone, two riders (each with a login), a dispatcher, a viewer, and one shipment assigned to rider 1."""
    zone = make_zone(db)
    rider = make_rider(db, zone)
    other_rider = make_rider(db, zone)
    dispatcher = make_user(role=UserRole.DISPATCHER)
    viewer = make_user(role=UserRole.VIEWER)
    rider_user = make_user(role=UserRole.RIDER, rider_id=rider.id)
    other_rider_user = make_user(role=UserRole.RIDER, rider_id=other_rider.id)
    shipment_id = create_as(client, auth, dispatcher, zone)
    assigned = status_as(client, auth, dispatcher, shipment_id, "assigned", rider_id=rider.id)
    assert assigned.status_code == 200, assigned.text
    return SimpleNamespace(
        zone=zone,
        rider=rider,
        other_rider=other_rider,
        dispatcher=dispatcher,
        viewer=viewer,
        rider_user=rider_user,
        other_rider_user=other_rider_user,
        shipment_id=shipment_id,
    )


# ---------- no token / bad token ----------

@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/shipments", {"recipient_name": "A", "recipient_phone": "01712345678", "address": "B", "zone_id": 1}),
        ("GET", "/shipments/1", None),
        ("POST", "/shipments/1/status", {"new_status": "assigned", "rider_id": 1}),
    ],
)
def test_endpoints_require_a_token(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401


def test_health_and_login_stay_public(client):
    assert client.get("/health").status_code == 200
    assert client.post("/login", data={"username": "x", "password": "y"}).status_code == 401  # reachable, just wrong


def test_garbage_token_is_rejected(client):
    response = client.get("/shipments/1", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_expired_token_is_rejected(client, make_user):
    user = make_user(role=UserRole.ADMIN)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode({"sub": str(user.id), "role": "admin", "exp": past}, settings.jwt_secret, algorithm=ALGORITHM)
    assert client.get("/shipments/1", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, make_user):
    user = make_user(role=UserRole.ADMIN)
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    forged = jwt.encode({"sub": str(user.id), "role": "admin", "exp": future}, "x" * 40, algorithm=ALGORITHM)
    assert client.get("/shipments/1", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_of_deactivated_user_stops_working(client, db, make_user, auth):
    user = make_user(role=UserRole.ADMIN)
    headers = auth(user)  # a perfectly valid token...
    user.is_active = False  # ...but the account is switched off afterwards
    db.flush()
    assert client.get("/shipments/1", headers=headers).status_code == 401


def test_role_in_token_is_ignored_the_database_decides(client, world):
    # The token CLAIMS admin, but the database says this user is only a viewer.
    forged = {"Authorization": f"Bearer {create_access_token(world.viewer.id, 'admin')}"}
    response = client.post("/shipments", json=shipment_payload(world.zone), headers=forged)
    assert response.status_code == 403


# ---------- viewer ----------

def test_viewer_can_read_but_not_write(client, auth, world):
    assert client.get(f"/shipments/{world.shipment_id}", headers=auth(world.viewer)).status_code == 200
    created = client.post("/shipments", json=shipment_payload(world.zone), headers=auth(world.viewer))
    assert created.status_code == 403
    assert status_as(client, auth, world.viewer, world.shipment_id, "out_for_delivery").status_code == 403


# ---------- rider ----------

def test_rider_cannot_create_shipments(client, auth, world):
    response = client.post("/shipments", json=shipment_payload(world.zone), headers=auth(world.rider_user))
    assert response.status_code == 403


def test_rider_can_work_own_shipment(client, auth, world):
    url = f"/shipments/{world.shipment_id}"
    assert client.get(url, headers=auth(world.rider_user)).status_code == 200
    assert status_as(client, auth, world.rider_user, world.shipment_id, "out_for_delivery").status_code == 200
    assert status_as(client, auth, world.rider_user, world.shipment_id, "delivered").status_code == 200


@pytest.mark.parametrize("target", ["assigned", "rescheduled", "return_to_sender"])
def test_rider_cannot_do_dispatcher_moves(client, auth, world, target):
    response = status_as(
        client, auth, world.rider_user, world.shipment_id, target, rider_id=world.other_rider.id
    )
    assert response.status_code == 403
    after = client.get(f"/shipments/{world.shipment_id}", headers=auth(world.dispatcher)).json()
    assert after["status"] == "assigned"
    assert after["rider_id"] == world.rider.id  # nothing changed


def test_rider_cannot_touch_another_riders_shipment(client, auth, world):
    url = f"/shipments/{world.shipment_id}"
    intruder = world.other_rider_user
    assert client.get(url, headers=auth(intruder)).status_code == 404
    assert status_as(client, auth, intruder, world.shipment_id, "out_for_delivery").status_code == 404
    # Trying to steal it by assigning it to himself: still "not found", ownership is checked first.
    steal = status_as(client, auth, intruder, world.shipment_id, "assigned", rider_id=world.other_rider.id)
    assert steal.status_code == 404
    after = client.get(url, headers=auth(world.dispatcher)).json()
    assert after["status"] == "assigned"
    assert after["rider_id"] == world.rider.id


def test_rider_cannot_see_unassigned_shipment(client, auth, world):
    new_id = create_as(client, auth, world.dispatcher, world.zone)  # nobody is assigned yet
    assert client.get(f"/shipments/{new_id}", headers=auth(world.rider_user)).status_code == 404


def test_rider_login_without_rider_link_sees_nothing(client, auth, make_user, world):
    orphan = make_user(role=UserRole.RIDER, rider_id=None)
    assert client.get(f"/shipments/{world.shipment_id}", headers=auth(orphan)).status_code == 404
    assert status_as(client, auth, orphan, world.shipment_id, "out_for_delivery").status_code == 404


# ---------- audit log ----------

def test_audit_log_records_who_did_it(client, db, auth, world):
    assert status_as(client, auth, world.rider_user, world.shipment_id, "out_for_delivery").status_code == 200
    rows = db.execute(
        select(AuditLog.new_value, AuditLog.actor)
        .where(AuditLog.entity_type == "shipment", AuditLog.entity_id == world.shipment_id)
        .order_by(AuditLog.id)
    ).all()
    assert [tuple(row) for row in rows] == [
        ("created", world.dispatcher.username),
        ("assigned", world.dispatcher.username),
        ("out_for_delivery", world.rider_user.username),
    ]


# ---------- rider reporting a failed attempt (closes a gap found by breaking the code on purpose) ----------

def test_rider_can_report_failed_attempt_with_reason(client, auth, world):
    assert status_as(client, auth, world.rider_user, world.shipment_id, "out_for_delivery").status_code == 200
    failed = status_as(
        client, auth, world.rider_user, world.shipment_id, "attempt_failed", failure_reason="phone_off"
    )
    assert failed.status_code == 200
    body = failed.json()
    assert body["status"] == "rescheduled"  # rule engine: phone_off -> rescheduled automatically
    assert body["attempt_count"] == 1


def test_rider_failed_attempt_needs_a_reason(client, auth, world):
    assert status_as(client, auth, world.rider_user, world.shipment_id, "out_for_delivery").status_code == 200
    assert status_as(client, auth, world.rider_user, world.shipment_id, "attempt_failed").status_code == 422


def test_rider_cannot_reschedule_after_failed_attempt(client, auth, world):
    status_as(client, auth, world.rider_user, world.shipment_id, "out_for_delivery")
    # wrong_address has no automatic next status, so the shipment stays in attempt_failed
    status_as(client, auth, world.rider_user, world.shipment_id, "attempt_failed", failure_reason="wrong_address")
    response = status_as(client, auth, world.rider_user, world.shipment_id, "rescheduled")
    assert response.status_code == 403  # rescheduling is a dispatcher job
    after = client.get(f"/shipments/{world.shipment_id}", headers=auth(world.dispatcher)).json()
    assert after["status"] == "attempt_failed"
