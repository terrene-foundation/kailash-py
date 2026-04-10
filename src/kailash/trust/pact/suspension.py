# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plan suspension and resumption protocol for PACT governance.

Implements the N3 Plan Re-Entry Guarantee: when a plan is blocked due to
budget exhaustion, temporal deadline expiry, posture downgrade, or envelope
revocation, the governance engine suspends the plan with explicit resume
conditions rather than permanently blocking it. This gives callers a
deterministic path to resume once conditions are met.

Four suspension triggers:
  - BUDGET: BudgetTracker signals exhaustion
  - TEMPORAL: Envelope temporal constraint expires
  - POSTURE: Agent posture drops below plan requirement
  - ENVELOPE: Parent envelope revoked

Each trigger generates one or more ResumeConditions. All conditions must be
satisfied before ``GovernanceEngine.resume_plan()`` can re-activate the plan.

frozen=True on all dataclasses: prevents post-construction mutation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "PlanSuspension",
    "ResumeCondition",
    "SuspensionTrigger",
]


class SuspensionTrigger(str, Enum):
    """Why a plan was suspended.

    Each trigger maps to a specific governance condition that caused
    the plan to be paused. The trigger determines what resume conditions
    are generated.
    """

    BUDGET = "budget"
    TEMPORAL = "temporal"
    POSTURE = "posture"
    ENVELOPE = "envelope"


@dataclass(frozen=True)
class ResumeCondition:
    """A single condition that must be satisfied before a plan can resume.

    Attributes:
        condition_type: What must happen for this condition to be met.
            One of: "budget_replenished", "deadline_extended",
            "posture_restored", "envelope_granted".
        satisfied: Whether this condition is currently met.
        details: Human-readable description of what is needed.
    """

    condition_type: str
    satisfied: bool = False
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding.

        Returns:
            A dict representation of this condition.
        """
        return {
            "condition_type": self.condition_type,
            "satisfied": self.satisfied,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeCondition:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized ResumeCondition fields.

        Returns:
            A ResumeCondition instance.
        """
        return cls(
            condition_type=data["condition_type"],
            satisfied=data.get("satisfied", False),
            details=data.get("details", ""),
        )


# Mapping from trigger to the resume condition type that resolves it.
_TRIGGER_TO_CONDITION: dict[SuspensionTrigger, str] = {
    SuspensionTrigger.BUDGET: "budget_replenished",
    SuspensionTrigger.TEMPORAL: "deadline_extended",
    SuspensionTrigger.POSTURE: "posture_restored",
    SuspensionTrigger.ENVELOPE: "envelope_granted",
}


def resume_condition_for_trigger(
    trigger: SuspensionTrigger,
    details: str = "",
) -> ResumeCondition:
    """Create the appropriate ResumeCondition for a given trigger.

    Args:
        trigger: The suspension trigger type.
        details: Optional human-readable explanation.

    Returns:
        A ResumeCondition with the correct condition_type for the trigger.
    """
    condition_type = _TRIGGER_TO_CONDITION[trigger]
    return ResumeCondition(
        condition_type=condition_type,
        satisfied=False,
        details=details or f"Waiting for {condition_type}",
    )


@dataclass(frozen=True)
class PlanSuspension:
    """A suspended plan with its resume conditions and frozen state snapshot.

    frozen=True: prevents post-construction mutation of any field, including
    the snapshot dict (shallow freeze -- the dict reference is frozen, but
    callers should not mutate its contents).

    Attributes:
        plan_id: Unique identifier for the plan that was suspended.
        trigger: Why the plan was suspended.
        suspended_at: When the suspension occurred (ISO 8601).
        resume_conditions: Tuple of conditions that must ALL be satisfied
            before the plan can resume.
        snapshot: Frozen state of the plan at suspension time. Contains
            whatever context the caller needs to reconstruct the plan
            state on resume.
        role_address: The D/T/R address of the role whose plan was suspended.
        suspension_id: Unique identifier for this suspension record.
    """

    plan_id: str
    trigger: SuspensionTrigger
    suspended_at: str
    resume_conditions: tuple[ResumeCondition, ...]
    snapshot: dict[str, Any] = field(default_factory=dict)
    role_address: str = ""
    suspension_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def all_conditions_met(self) -> bool:
        """Check whether all resume conditions are currently satisfied.

        Returns:
            True if every ResumeCondition has satisfied=True.
            Returns True vacuously if there are no conditions (defensive).
        """
        return all(c.satisfied for c in self.resume_conditions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding.

        Returns:
            A dict representation of this suspension record.
        """
        return {
            "plan_id": self.plan_id,
            "trigger": self.trigger.value,
            "suspended_at": self.suspended_at,
            "resume_conditions": [c.to_dict() for c in self.resume_conditions],
            "snapshot": self.snapshot,
            "role_address": self.role_address,
            "suspension_id": self.suspension_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanSuspension:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized PlanSuspension fields.

        Returns:
            A PlanSuspension instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If trigger value is invalid.
        """
        return cls(
            plan_id=data["plan_id"],
            trigger=SuspensionTrigger(data["trigger"]),
            suspended_at=data["suspended_at"],
            resume_conditions=tuple(
                ResumeCondition.from_dict(c) for c in data["resume_conditions"]
            ),
            snapshot=data.get("snapshot", {}),
            role_address=data.get("role_address", ""),
            suspension_id=data.get("suspension_id", uuid.uuid4().hex),
        )
