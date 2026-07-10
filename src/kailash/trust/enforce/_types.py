# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared enforcement value types — the cycle-free base for ``strict`` + ``held``.

``Verdict`` and ``EnforcementRecord`` are consumed at RUNTIME by BOTH
``kailash.trust.enforce.strict`` (the enforcer) and
``kailash.trust.enforce.held`` (the HITL hold store). Defining them here — a
leaf module that imports neither — breaks the ``strict`` <-> ``held``
module-level import cycle (CodeQL ``py/unsafe-cyclic-import``): both modules
import these types from here, and neither imports the other at module scope
for them. ``strict`` re-exports both (module-level import + ``__all__``), so
every existing ``from kailash.trust.enforce.strict import Verdict`` /
``EnforcementRecord`` path still resolves unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

from kailash.trust.chain import VerificationResult

__all__ = ["EnforcementRecord", "Verdict"]


class Verdict(Enum):
    """Enforcement verdict for a verification result."""

    AUTO_APPROVED = "auto_approved"  # Valid, no issues
    FLAGGED = "flagged"  # Valid but has warnings (constraint near limits)
    HELD = "held"  # Requires human review before proceeding
    BLOCKED = "blocked"  # Denied, action must not proceed


@dataclass(frozen=True)
class EnforcementRecord:
    """Record of an enforcement decision.

    Frozen to prevent post-creation tampering of audit records.
    """

    agent_id: str
    action: str
    verdict: Verdict
    verification_result: VerificationResult
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
