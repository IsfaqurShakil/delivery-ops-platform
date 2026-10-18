# app/state_machine.py
# The rules for how a shipment may move from one status to the next.
# Pure Python: no database here, so it is fast and easy to test.
from app.models import ShipmentStatus as S

# For every status: the set of statuses it is allowed to move to.
ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.CREATED: {S.ASSIGNED},
    S.ASSIGNED: {S.OUT_FOR_DELIVERY},
    S.OUT_FOR_DELIVERY: {S.DELIVERED, S.ATTEMPT_FAILED},
    S.ATTEMPT_FAILED: {S.RESCHEDULED, S.RETURN_TO_SENDER},
    S.RESCHEDULED: {S.ASSIGNED},  # a rescheduled shipment gets a rider again
    S.DELIVERED: set(),           # final state, no way out
    S.RETURN_TO_SENDER: set(),    # final state, no way out
}


class IllegalTransition(Exception):
    """Raised when someone tries a status change that the rules do not allow."""


def can_transition(current: S, target: S) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: S, target: S) -> None:
    if not can_transition(current, target):
        raise IllegalTransition(f"Cannot move shipment from {current.value} to {target.value}")
