# tests/test_rules.py
# Tests for the exception rule engine. Pure Python, no database.
# The expected answers are written by hand from the business policy, not copied from the code.
import pytest
from pydantic import ValidationError

from app.models import ShipmentStatus as S
from app.rules import RuleSet, decide, load_rules


def base_data() -> dict:
    return {
        "version": "test-1",
        "max_attempts": 3,
        "on_max_attempts": {"next_status": "return_to_sender", "tasks": [], "block_cod": True},
        "default": {"next_status": None, "tasks": ["customer_service_task"]},
        "reasons": {
            "phone_off": {"next_status": "rescheduled", "tasks": ["sms_reminder"]},
            "wrong_address": {"next_status": None, "tasks": ["customer_service_task"]},
        },
    }


RULES = RuleSet.model_validate(base_data())


# ---------- engine logic, with a small test config ----------

def test_known_reason_applies_its_rule():
    decision = decide(RULES, "phone_off", attempt_count=1, is_cod=False)
    assert decision.next_status == S.RESCHEDULED
    assert decision.tasks == ["sms_reminder"]
    assert decision.block_cod is False
    assert decision.matched_rule == "reason:phone_off"
    assert decision.rule_version == "test-1"


def test_wrong_address_waits_for_a_human():
    decision = decide(RULES, "wrong_address", attempt_count=1, is_cod=False)
    assert decision.next_status is None
    assert decision.tasks == ["customer_service_task"]


def test_unknown_reason_falls_back_to_default():
    decision = decide(RULES, "aliens_took_the_parcel", attempt_count=1, is_cod=False)
    assert decision.matched_rule == "default"
    assert decision.next_status is None
    assert decision.tasks == ["customer_service_task"]


def test_reason_is_trimmed_and_case_insensitive():
    decision = decide(RULES, "  Phone_OFF ", attempt_count=1, is_cod=False)
    assert decision.matched_rule == "reason:phone_off"


@pytest.mark.parametrize(
    "attempts,expected_rule",
    [(1, "reason:phone_off"), (2, "reason:phone_off"), (3, "max_attempts"), (4, "max_attempts")],
)
def test_max_attempts_boundary(attempts, expected_rule):
    assert decide(RULES, "phone_off", attempt_count=attempts, is_cod=False).matched_rule == expected_rule


@pytest.mark.parametrize("is_cod", [True, False])
def test_max_attempts_returns_parcel_and_blocks_cod_only_for_cod(is_cod):
    decision = decide(RULES, "phone_off", attempt_count=3, is_cod=is_cod)
    assert decision.next_status == S.RETURN_TO_SENDER
    assert decision.tasks == []
    assert decision.block_cod is is_cod


# ---------- a broken config must be refused when loaded ----------

@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["reasons"]["phone_off"].update(tasks=["send_pigeon"]),  # unknown task
        lambda d: d["reasons"]["phone_off"].update(next_status="delivered"),  # status not allowed after a failure
        lambda d: d.update(max_attempts=0),  # must be at least 1
        lambda d: d.pop("version"),  # version is mandatory
        lambda d: d.update(version=""),  # and must not be empty
        lambda d: d.update(max_attemps=3),  # typo in a top-level key
        lambda d: d["reasons"]["phone_off"].update(nxt_status="rescheduled"),  # typo in an inner key
    ],
)
def test_invalid_config_is_rejected(mutate):
    data = base_data()
    mutate(data)
    with pytest.raises(ValidationError):
        RuleSet.model_validate(data)


# ---------- the real config file in the repo must follow our policy ----------

def test_real_config_file_loads():
    rules = load_rules()
    assert rules.version
    assert rules.max_attempts == 3


@pytest.mark.parametrize(
    "reason,attempts,is_cod,status,tasks,blocked",
    [
        ("phone_off", 1, False, S.RESCHEDULED, ["sms_reminder"], False),
        ("customer_not_available", 1, True, S.RESCHEDULED, [], False),
        ("wrong_address", 1, False, None, ["customer_service_task"], False),
        ("refused_by_customer", 1, False, S.RETURN_TO_SENDER, [], False),
        ("phone_off", 3, True, S.RETURN_TO_SENDER, [], True),
        ("phone_off", 3, False, S.RETURN_TO_SENDER, [], False),
    ],
)
def test_real_policy(reason, attempts, is_cod, status, tasks, blocked):
    decision = decide(load_rules(), reason, attempt_count=attempts, is_cod=is_cod)
    assert decision.next_status == status
    assert decision.tasks == tasks
    assert decision.block_cod is blocked


