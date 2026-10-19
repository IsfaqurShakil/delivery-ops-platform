# app/services.py
# The business logic. Routes call these functions; the rules live here, not in the routes.
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    DeliveryAttempt,
    ExceptionTask,
    Rider,
    Shipment,
    ShipmentStatus,
    UserRole,
    Zone,
)
from app.rules import decide, get_rules
from app.schemas import ShipmentCreate, StatusChange
from app.state_machine import ensure_transition

# The only moves a rider may report. Assigning, rescheduling and returning are dispatcher jobs.
RIDER_ALLOWED_TARGETS = {
    ShipmentStatus.OUT_FOR_DELIVERY,
    ShipmentStatus.DELIVERED,
    ShipmentStatus.ATTEMPT_FAILED,
}

# Name written in the audit log when the rule engine (not a person) makes a change.
RULE_ENGINE_ACTOR = "rule_engine"


class NotFound(Exception):
    """The thing the caller asked for does not exist (or the caller may not know that it exists)."""


class RuleViolation(Exception):
    """The request is understood, but breaks a business rule."""


class Forbidden(Exception):
    """The caller is known, but their role does not allow this action."""


def _audit(
    db: Session,
    shipment_id: int,
    action: str,
    old: str | None,
    new: str | None,
    actor: str,
    details: dict | None = None,  # extra context, stored as JSON text
) -> None:
    db.add(
        AuditLog(
            entity_type="shipment",
            entity_id=shipment_id,
            action=action,
            old_value=old,
            new_value=new,
            actor=actor,
            details=json.dumps(details) if details else None,
        )
    )


def _apply_exception_rules(db: Session, shipment: Shipment, failure_reason: str) -> None:
    """Called right after an attempt failed. Asks the rule engine what to do and does it.
    It only adds rows to the session; the caller commits, so everything is one transaction."""
    decision = decide(get_rules(), failure_reason, shipment.attempt_count, shipment.is_cod)
    reason = failure_reason.strip().lower()

    # 1) Always record WHAT the engine decided and WHICH rule version decided it.
    _audit(
        db,
        shipment.id,
        "rule_decision",
        None,
        decision.next_status.value if decision.next_status else None,
        RULE_ENGINE_ACTOR,
        details={
            "rule_version": decision.rule_version,
            "matched_rule": decision.matched_rule,
            "failure_reason": reason,
            "attempt_count": shipment.attempt_count,
            "tasks": decision.tasks,
            "block_cod": decision.block_cod,
        },
    )

    # 2) Create the follow-up tasks (SMS reminder, customer service call, ...).
    for task_type in decision.tasks:
        db.add(
            ExceptionTask(
                shipment_id=shipment.id,
                task_type=task_type,
                reason=reason,
                rule_version=decision.rule_version,
            )
        )

    # 3) Move the shipment on automatically (rescheduled or return_to_sender).
    #    next_status None means: stay in attempt_failed and wait for a human.
    if decision.next_status is not None:
        ensure_transition(shipment.status, decision.next_status)  # safety net: the state machine still has the final say
        _audit(
            db,
            shipment.id,
            "status_change",
            shipment.status.value,
            decision.next_status.value,
            RULE_ENGINE_ACTOR,
        )
        shipment.status = decision.next_status


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

    # NEW: after a failed attempt the rule engine decides what happens next (same transaction).
    if target == ShipmentStatus.ATTEMPT_FAILED:
        _apply_exception_rules(db, shipment, change.failure_reason)

    db.commit()
    db.refresh(shipment)
    return shipment