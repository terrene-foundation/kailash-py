# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance verdict -- the result of GovernanceEngine.verify_action().

GovernanceVerdict is the primary decision output from the GovernanceEngine.
It encapsulates the verification gradient level, the effective envelope snapshot,
any access decision, and full audit details for compliance review.

frozen=True: verdicts are immutable records of governance decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pact.governance.access import AccessDecision

logger = logging.getLogger(__name__)

__all__ = ["GovernanceVerdict"]


@dataclass(frozen=True)
class GovernanceVerdict:
    """Result of GovernanceEngine.verify_action() -- the primary decision API.

    Attributes:
        level: Verification gradient level. One of:
            "auto_approved" -- action falls within all constraint dimensions
            "flagged" -- action is near a boundary
            "held" -- action exceeds a soft limit, queued for human approval
            "blocked" -- action violates a hard constraint
        reason: Human-readable explanation of the decision.
        role_address: The D/T/R address of the role that requested the action.
        action: The action that was evaluated.
        effective_envelope_snapshot: Serialized ConstraintEnvelopeConfig at
            the time of the decision, or None if no envelope was available.
        audit_details: Structured details for EATP audit anchoring.
        access_decision: If a knowledge resource was checked, the AccessDecision
            from the 5-step algorithm. None if no resource was involved.
        timestamp: When the verdict was issued (UTC).
    """

    level: str
    reason: str
    role_address: str
    action: str
    effective_envelope_snapshot: dict[str, Any] | None = None
    audit_details: dict[str, Any] = field(default_factory=dict)
    access_decision: AccessDecision | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    envelope_version: str = ""

    @property
    def allowed(self) -> bool:
        """True if the action is permitted (auto_approved or flagged).

        FLAGGED actions are allowed but should be logged for review.
        HELD and BLOCKED actions are not allowed.
        """
        return self.level in ("auto_approved", "flagged")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding or audit storage.

        Returns:
            A dict representation of the verdict with all fields.
        """
        result: dict[str, Any] = {
            "level": self.level,
            "reason": self.reason,
            "role_address": self.role_address,
            "action": self.action,
            "allowed": self.allowed,
            "effective_envelope_snapshot": self.effective_envelope_snapshot,
            "audit_details": self.audit_details,
            "timestamp": self.timestamp.isoformat(),
            "envelope_version": self.envelope_version,
        }
        if self.access_decision is not None:
            result["access_decision"] = {
                "allowed": self.access_decision.allowed,
                "reason": self.access_decision.reason,
                "step_failed": self.access_decision.step_failed,
                "audit_details": self.access_decision.audit_details,
            }
        else:
            result["access_decision"] = None
        return result
