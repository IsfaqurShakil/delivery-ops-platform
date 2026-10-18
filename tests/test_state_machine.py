# tests/test_state_machine.py
# Tests for the shipment state machine. The expected rules are written out by hand here,
# NOT copied from the code under test, so a mistake in the code cannot hide itself.
import itertools

import pytest

from app.models import ShipmentStatus as S
from app.state_machine import ALLOWED_TRANSITIONS, IllegalTransition, can_transition, ensure_transition

ALL_STATES = list(S)

VALID = [
    (S.CREATED, S.ASSIGNED),
    (S.ASSIGNED, S.OUT_FOR_DELIVERY),
    (S.OUT_FOR_DELIVERY, S.DELIVERED),
    (S.OUT_FOR_DELIVERY, S.ATTEMPT_FAILED),
    (S.ATTEMPT_FAILED, S.RESCHEDULED),
    (S.ATTEMPT_FAILED, S.RETURN_TO_SENDER),
    (S.RESCHEDULED, S.ASSIGNED),
]

# Every other pair of statuses (including "stay in the same status") must be rejected.
INVALID = [pair for pair in itertools.product(ALL_STATES, ALL_STATES) if pair not in VALID]


@pytest.mark.parametrize("current,target", VALID)
def test_valid_transition_is_allowed(current, target):
    assert can_transition(current, target) is True
    ensure_transition(current, target)  # must not raise


@pytest.mark.parametrize("current,target", INVALID)
def test_invalid_transition_is_rejected(current, target):
    assert can_transition(current, target) is False
    with pytest.raises(IllegalTransition):
        ensure_transition(current, target)


@pytest.mark.parametrize("final_state", [S.DELIVERED, S.RETURN_TO_SENDER])
def test_final_states_have_no_exit(final_state):
    for target in ALL_STATES:
        assert can_transition(final_state, target) is False


def test_every_status_has_a_rule():
    # Guards against adding a new status and forgetting to define its moves.
    assert set(ALLOWED_TRANSITIONS) == set(S)
