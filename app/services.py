# app/services.py
# The business logic. Routes call these functions; the rules live here, not in the routes.
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, DeliveryAttempt, Rider, Shipment, ShipmentStatus, UserRole, Zone
from app.schemas import ShipmentCreate, StatusChange
from app.state_machine import ensure_transition

# The only moves a rider may report. Assigning, rescheduling and returning are dispatcher jobs.
RIDER_ALLOWED_TARGETS = {
    ShipmentStatus.OUT_FOR_DELIVERY,
    ShipmentStatus.DELIVERED,
    ShipmentStatus.ATTEMPT_FAILED,
}


class NotFound(Exception):
    """The thing the caller asked for does not exist (or the caller may not know that it exists)."""


class RuleViolation(Exception):
    """The request is understood, but breaks a business rule."""


class Forbidden(Exception):
    """The caller is known, but their role does not allow this action."""


def _audit(db: Session, shipment_id: int, action: str, old: str | None, new: str | None, actor: str) -> None:
    db.add(
        AuditLog(
            entity_type="shipment",
            entity_id=shipment_id,
            action=action,
            old_value=old,
            new_value=new,
            actor=actor,
        )
    )


def create_shipment(db: Session, data: ShipmentCreate, actor: str = "api") -> Shipment:
    if db.get(Zone, data.zone_id) is None:
        raise NotFound("Zone not found")
    shipment = Shipment(tracking_code=f"DEL{uuid.uuid4().hex[:10].upper()}", **data.model_dump())
    db.add(shipment)
    db.flush()  # sends the INSERT now so the shipment gets its id
    _audit(db, shipment.id, "created", None, ShipmentStatus.CREATED.value, actor)
    db.commit()
    db.refresh(shipment)
    return shipment


def change_status(
    db: Session,
    shipment_id: int,
    change: StatusChange,
    actor: str = "api",
    actor_role: UserRole | None = None,
    actor_rider_id: int | None = None,
) -> Shipment:
    # FOR UPDATE locks this row until we commit, so two requests cannot change the same shipment at once.
    shipment = db.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
    if shipment is None:
        raise NotFound("Shipment not found")

    if actor_role == UserRole.RIDER:
        # Ownership is checked first and answers "not found", so a rider cannot learn
        # that another rider's shipment exists. We check it AFTER the lock, so it cannot go stale.
        if actor_rider_id is None or shipment.rider_id != actor_rider_id:
            raise NotFound("Shipment not found")
        if change.new_status not in RIDER_ALLOWED_TARGETS:
            raise Forbidden("Riders can only report out_for_delivery, delivered or attempt_failed")

    old_status = shipment.status
    target = change.new_status
    ensure_transition(old_status, target)  # raises IllegalTransition if the move is not allowed

    if target == ShipmentStatus.ASSIGNED:
        if change.rider_id is None:
            raise RuleViolation("rider_id is required when assigning a shipment")
        rider = db.get(Rider, change.rider_id)
        if rider is None or not rider.is_active:
            raise RuleViolation("Rider not found or not active")
        if rider.zone_id != shipment.zone_id:
            raise RuleViolation("Rider belongs to a different zone")
        shipment.rider_id = rider.id

    if target == ShipmentStatus.ATTEMPT_FAILED:
        if not change.failure_reason:
            raise RuleViolation("failure_reason is required when an attempt fails")
        shipment.attempt_count += 1
        db.add(
            DeliveryAttempt(
                shipment_id=shipment.id,
                rider_id=shipment.rider_id,
                attempt_no=shipment.attempt_count,
                outcome="failed",
                failure_reason=change.failure_reason,
            )
        )

    if target == ShipmentStatus.DELIVERED:
        shipment.attempt_count += 1
        db.add(
            DeliveryAttempt(
                shipment_id=shipment.id,
                rider_id=shipment.rider_id,
                attempt_no=shipment.attempt_count,
                outcome="delivered",
            )
        )

    shipment.status = target
    _audit(db, shipment.id, "status_change", old_status.value, target.value, actor)
    db.commit()
    db.refresh(shipment)
    return shipment
