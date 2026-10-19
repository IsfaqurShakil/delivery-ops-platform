# app/rules.py
# The exception rule engine: given a failed delivery, decide what happens next.
# The rules live in config/exception_rules.json (versioned), not in this code.
# Pure Python: no database, so it is fast and easy to test.
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ShipmentStatus

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "exception_rules.json"

# After a failed attempt the state machine only allows these two moves.
# None means "stay in attempt_failed and wait for a human".
ALLOWED_NEXT_STATUSES = {ShipmentStatus.RESCHEDULED, ShipmentStatus.RETURN_TO_SENDER}
KNOWN_TASKS = {"sms_reminder", "customer_service_task"}


class Outcome(BaseModel):
    """What to do for one situation."""

    model_config = ConfigDict(extra="forbid")  # a typo in a key name is an error, not silently ignored

    next_status: ShipmentStatus | None = None
    tasks: list[str] = []
    block_cod: bool = False

    @model_validator(mode="after")
    def check_values(self):
        if self.next_status is not None and self.next_status not in ALLOWED_NEXT_STATUSES:
            raise ValueError(f"next_status '{self.next_status.value}' is not allowed after a failed attempt")
        unknown = set(self.tasks) - KNOWN_TASKS
        if unknown:
            raise ValueError(f"unknown task(s): {sorted(unknown)}")
        return self


class RuleSet(BaseModel):
    """The whole config file. If anything in it is wrong, loading fails right away."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    max_attempts: int = Field(ge=1)
    on_max_attempts: Outcome
    default: Outcome
    reasons: dict[str, Outcome]


class Decision(BaseModel):
    next_status: ShipmentStatus | None
    tasks: list[str]
    block_cod: bool
    rule_version: str  # which version of the rules made this decision
    matched_rule: str  # "max_attempts", "reason:<name>" or "default"


def decide(rules: RuleSet, failure_reason: str, attempt_count: int, is_cod: bool) -> Decision:
    """attempt_count = how many attempts have failed so far, including the one that just failed."""
    reason = failure_reason.strip().lower()
    if attempt_count >= rules.max_attempts:  # this rule beats every reason-specific rule
        outcome, matched = rules.on_max_attempts, "max_attempts"
    elif reason in rules.reasons:
        outcome, matched = rules.reasons[reason], f"reason:{reason}"
    else:
        outcome, matched = rules.default, "default"
    return Decision(
        next_status=outcome.next_status,
        tasks=list(outcome.tasks),
        block_cod=outcome.block_cod and is_cod,  # COD blocking only makes sense for COD shipments
        rule_version=rules.version,
        matched_rule=matched,
    )


def load_rules(path: Path = CONFIG_PATH) -> RuleSet:
    with open(path, encoding="utf-8") as file:
        return RuleSet.model_validate(json.load(file))


@lru_cache
def get_rules() -> RuleSet:
    # Loaded once and remembered, so we do not re-read the file on every request.
    return load_rules()
