# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Reasoning Trace Extension.

Provides structured reasoning traces that capture WHY a decision was made
during trust delegation and audit operations. This extension enables:

- **Decision transparency**: Every delegation/audit can explain its rationale
- **Confidentiality classification**: Reasoning traces carry enterprise
  classification levels (PUBLIC through TOP_SECRET)
- **Dual-binding**: Reasoning trace hash is included in the parent record's
  signing payload, cryptographically binding the trace to the delegation
- **Evidence linking**: Traces can reference evidence and methodology

Key design decisions:
- ConfidentialityLevel supports ordering for access control comparisons
- ReasoningTrace is fully optional on DelegationRecord/AuditAnchor
- Confidence is validated in __post_init__ (0.0 to 1.0 inclusive)
- to_signing_payload() returns deterministic sorted dict for signing
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ordering weights for ConfidentialityLevel comparison
# ---------------------------------------------------------------------------

_CONFIDENTIALITY_ORDER = {
    "public": 0,
    "restricted": 1,
    "confidential": 2,
    "secret": 3,
    "top_secret": 4,
}


class ConfidentialityLevel(Enum):
    """
    Enterprise confidentiality classification for reasoning traces.

    Supports ordering comparisons so that access control logic can
    evaluate whether an agent's clearance meets the trace's classification.

    Ordering: PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET

    Attributes:
        PUBLIC: Unrestricted reasoning traces
        RESTRICTED: Default classification — limited distribution
        CONFIDENTIAL: Sensitive business reasoning
        SECRET: Highly sensitive reasoning (e.g., security decisions)
        TOP_SECRET: Maximum classification (e.g., critical infrastructure)
    """

    PUBLIC = "public"
    RESTRICTED = "restricted"  # Default
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"

    def _order(self) -> int:
        """Return the numeric ordering weight for this level."""
        return _CONFIDENTIALITY_ORDER[self.value]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ConfidentialityLevel):
            return NotImplemented
        return self._order() < other._order()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, ConfidentialityLevel):
            return NotImplemented
        return self._order() <= other._order()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, ConfidentialityLevel):
            return NotImplemented
        return self._order() > other._order()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, ConfidentialityLevel):
            return NotImplemented
        return self._order() >= other._order()


@dataclass
class ReasoningTrace:
    """
    Structured reasoning trace capturing WHY a decision was made.

    Designed to be attached (optionally) to DelegationRecord and AuditAnchor
    records, providing full transparency into agent decision-making while
    maintaining backward compatibility with existing trust chain signatures.

    Attributes:
        decision: What was decided (human-readable summary)
        rationale: Why the decision was made (human-readable explanation)
        confidentiality: Enterprise classification level for this trace
        timestamp: When the reasoning occurred (UTC recommended)
        alternatives_considered: Other options that were evaluated
        evidence: Supporting evidence as list of dicts (flexible schema)
        methodology: Reasoning methodology used (e.g., "risk_assessment",
            "cost_benefit", "capability_matching")
        confidence: Confidence score from 0.0 to 1.0 (None if not assessed)
    """

    decision: str
    rationale: str
    confidentiality: ConfidentialityLevel
    timestamp: datetime
    alternatives_considered: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    methodology: Optional[str] = None
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate fields after dataclass initialization."""
        # Size limits to prevent DoS via oversized reasoning traces
        _MAX_DECISION_LEN = 10_000
        _MAX_RATIONALE_LEN = 50_000
        _MAX_ALTERNATIVES = 100
        _MAX_ALTERNATIVE_LEN = 5_000
        _MAX_EVIDENCE_ITEMS = 100
        _MAX_METHODOLOGY_LEN = 1_000

        if len(self.decision) > _MAX_DECISION_LEN:
            raise ValueError(
                f"decision exceeds maximum length of {_MAX_DECISION_LEN} characters, "
                f"got {len(self.decision)}"
            )
        if len(self.rationale) > _MAX_RATIONALE_LEN:
            raise ValueError(
                f"rationale exceeds maximum length of {_MAX_RATIONALE_LEN} characters, "
                f"got {len(self.rationale)}"
            )
        if len(self.alternatives_considered) > _MAX_ALTERNATIVES:
            raise ValueError(
                f"alternatives_considered exceeds maximum of {_MAX_ALTERNATIVES} items, "
                f"got {len(self.alternatives_considered)}"
            )
        for i, alt in enumerate(self.alternatives_considered):
            if len(alt) > _MAX_ALTERNATIVE_LEN:
                raise ValueError(
                    f"alternatives_considered[{i}] exceeds maximum length of "
                    f"{_MAX_ALTERNATIVE_LEN} characters, got {len(alt)}"
                )
        if len(self.evidence) > _MAX_EVIDENCE_ITEMS:
            raise ValueError(
                f"evidence exceeds maximum of {_MAX_EVIDENCE_ITEMS} items, "
                f"got {len(self.evidence)}"
            )
        if (
            self.methodology is not None
            and len(self.methodology) > _MAX_METHODOLOGY_LEN
        ):
            raise ValueError(
                f"methodology exceeds maximum length of {_MAX_METHODOLOGY_LEN} characters, "
                f"got {len(self.methodology)}"
            )
        if self.confidence is not None:
            if not (0.0 <= self.confidence <= 1.0):
                raise ValueError(
                    f"confidence must be between 0.0 and 1.0 inclusive, "
                    f"got {self.confidence}"
                )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary.

        ConfidentialityLevel is serialized as its string value.
        Timestamp is serialized as ISO 8601 string.

        Returns:
            Dictionary representation with all fields
        """
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "confidentiality": self.confidentiality.value,
            "timestamp": self.timestamp.isoformat(),
            "alternatives_considered": self.alternatives_considered,
            "evidence": self.evidence,
            "methodology": self.methodology,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningTrace":
        """
        Deserialize from dictionary with backward-compatible defaults.

        Handles missing optional fields gracefully, using sensible defaults
        for fields that may not be present in older serialized forms.

        Args:
            data: Dictionary with ReasoningTrace fields

        Returns:
            ReasoningTrace instance
        """
        # Parse alternatives_considered: default to empty list if missing or None
        alternatives = data.get("alternatives_considered")
        if alternatives is None:
            alternatives = []

        # Parse evidence: default to empty list if missing or None
        evidence = data.get("evidence")
        if evidence is None:
            evidence = []

        return cls(
            decision=data["decision"],
            rationale=data["rationale"],
            confidentiality=ConfidentialityLevel(data["confidentiality"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            alternatives_considered=alternatives,
            evidence=evidence,
            methodology=data.get("methodology"),
            confidence=data.get("confidence"),
        )

    def to_signing_payload(self) -> Dict[str, Any]:
        """
        Get deterministic dict for separate reasoning signature.

        All fields are included with sorted keys to ensure deterministic
        serialization. ConfidentialityLevel is serialized as its string
        value. Timestamp is serialized as ISO 8601.

        This payload is used for computing a reasoning-specific signature
        that is independent of the parent record's signature, enabling
        reasoning traces to be verified separately.

        Returns:
            Dictionary with sorted keys, suitable for signing
        """
        return dict(
            sorted(
                {
                    "alternatives_considered": self.alternatives_considered,
                    "confidence": self.confidence,
                    "confidentiality": self.confidentiality.value,
                    "decision": self.decision,
                    "evidence": self.evidence,
                    "methodology": self.methodology,
                    "rationale": self.rationale,
                    "timestamp": self.timestamp.isoformat(),
                }.items()
            )
        )
