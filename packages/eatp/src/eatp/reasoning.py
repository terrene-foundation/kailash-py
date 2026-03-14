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

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

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

    def content_hash(self) -> bytes:
        """Compute SHA-256 hash of this trace's signing payload.

        Uses ``to_signing_payload()`` for deterministic ordering so the
        same trace always produces the same hash regardless of field
        insertion order.

        Returns:
            Raw SHA-256 digest (32 bytes).
        """
        payload = self.to_signing_payload()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).digest()

    def content_hash_hex(self) -> str:
        """Compute hex-encoded SHA-256 hash of this trace.

        Returns:
            Hex string of the SHA-256 digest (64 characters).
        """
        return self.content_hash().hex()

    def redact(self) -> Tuple["ReasoningTrace", str]:
        """Create a redacted copy of this trace.

        Replaces sensitive content fields with the ``"[REDACTED]"`` sentinel
        while retaining timestamp and confidentiality level. Returns the
        original trace's content hash so the redacted version can be linked
        back to the original.

        Returns:
            Tuple of (redacted_trace, original_content_hash_hex).
        """
        original_hash = self.content_hash_hex()
        redacted = ReasoningTrace(
            decision="[REDACTED]",
            rationale="[REDACTED]",
            confidentiality=self.confidentiality,
            timestamp=self.timestamp,
            alternatives_considered=["[REDACTED]"],
            evidence=[{"redacted": True}],
            methodology="[REDACTED]",
            confidence=None,
        )
        return redacted, original_hash

    def is_redacted(self) -> bool:
        """Check whether this trace has been redacted.

        Returns:
            True if the decision field contains the ``"[REDACTED]"`` sentinel.
        """
        return self.decision == "[REDACTED]"


_REDACTED_SENTINEL = "[REDACTED]"
"""Sentinel value used for redacted fields (matches Rust SDK)."""


@dataclass
class EvidenceReference:
    """Structured evidence reference for reasoning traces.

    Provides a typed alternative to raw ``Dict[str, Any]`` evidence entries.
    Both ``EvidenceReference`` objects and raw dicts are accepted in
    ``ReasoningTrace.evidence`` for backward compatibility.

    Attributes:
        evidence_type: Category of evidence (e.g., "document", "metric",
            "audit_log", "external_api").
        reference: Pointer to the evidence (e.g., URL, document ID, path).
        summary: Optional human-readable summary of the evidence.
    """

    evidence_type: str
    reference: str
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        result: Dict[str, Any] = {
            "evidence_type": self.evidence_type,
            "reference": self.reference,
        }
        if self.summary is not None:
            result["summary"] = self.summary
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceReference":
        """Deserialize from dictionary.

        Args:
            data: Dict with evidence_type, reference, and optional summary.

        Returns:
            EvidenceReference instance.
        """
        return cls(
            evidence_type=data["evidence_type"],
            reference=data["reference"],
            summary=data.get("summary"),
        )


def reasoning_completeness_score(
    trace: Optional[ReasoningTrace],
    signature_verified: bool = False,
) -> int:
    """Score the completeness of a reasoning trace (0-100).

    Factors (cross-SDK aligned with Rust ``reasoning_completeness_score()``):
    - Trace present: 30 pts
    - alternatives_considered not empty: 20 pts
    - evidence not empty: 15 pts
    - methodology present: 15 pts
    - confidence between 0 and 1.0, calibrated: 10 pts
    - signature verified: 10 pts

    Args:
        trace: The reasoning trace to score. None → 0.
        signature_verified: Whether the trace's signature has been verified.

    Returns:
        Integer score 0-100.
    """
    if trace is None:
        return 0

    score = 30  # Trace is present

    if trace.alternatives_considered:
        score += 20

    if trace.evidence:
        score += 15

    if trace.methodology is not None and trace.methodology != "":
        score += 15

    if trace.confidence is not None and 0.0 <= trace.confidence <= 1.0:
        score += 10

    if signature_verified:
        score += 10

    return max(0, min(100, score))


__all__ = [
    "ConfidentialityLevel",
    "ReasoningTrace",
    "EvidenceReference",
    "reasoning_completeness_score",
]
