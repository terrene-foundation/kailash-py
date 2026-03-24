# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance audit -- maps PACT actions to EATP Audit Anchors.

Records all governance-layer decisions (access grants/denials, envelope
changes, clearance modifications) into the audit chain for compliance
review and forensic analysis.

Per thesis Section 5.7 normative mapping, every governance action maps
to one of 10 PactAuditAction types, which are recorded as EATP Audit
Anchors with structured details.

AuditChain provides a tamper-evident linked chain of AuditAnchor records
with thread-safe append and integrity verification.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import threading
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from kailash.trust.pact.config import VerificationLevel

logger = logging.getLogger(__name__)

__all__ = [
    "PactAuditAction",
    "create_pact_audit_details",
    "AuditAnchor",
    "AuditChain",
]


class PactAuditAction(str, Enum):
    """PACT governance action types for EATP audit anchors.

    Per thesis Section 5.7 normative mapping. Each action type maps
    to a specific governance operation that must be recorded in the
    audit chain.
    """

    ENVELOPE_CREATED = "envelope_created"
    ENVELOPE_MODIFIED = "envelope_modified"
    CLEARANCE_GRANTED = "clearance_granted"
    CLEARANCE_REVOKED = "clearance_revoked"
    BARRIER_ENFORCED = "barrier_enforced"
    KSP_CREATED = "ksp_created"
    KSP_REVOKED = "ksp_revoked"
    BRIDGE_ESTABLISHED = "bridge_established"
    BRIDGE_REVOKED = "bridge_revoked"
    ADDRESS_COMPUTED = "address_computed"


def create_pact_audit_details(
    action: PactAuditAction,
    *,
    role_address: str = "",
    target_address: str = "",
    reason: str = "",
    step_failed: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Create audit details dict for a PACT governance action.

    Produces a structured details dictionary suitable for inclusion in an
    EATP AuditAnchor's metadata field. Optional fields are only included
    when they have non-empty/non-None values to keep audit records clean.

    Args:
        action: The PactAuditAction being recorded.
        role_address: The D/T/R address of the role performing the action.
        target_address: The D/T/R address of the target (if applicable).
        reason: Human-readable reason for the action.
        step_failed: For BARRIER_ENFORCED, which access enforcement step
            (1-5) denied access.
        **extra: Additional key-value pairs to include in the details dict.

    Returns:
        A dict with structured audit details. Always includes pact_action
        and role_address. Other fields are included only when non-empty.
    """
    details: dict[str, Any] = {
        "pact_action": action.value,
        "role_address": role_address,
    }
    if target_address:
        details["target_address"] = target_address
    if reason:
        details["reason"] = reason
    if step_failed is not None:
        details["step_failed"] = step_failed
    details.update(extra)
    return details


# ---------------------------------------------------------------------------
# AuditAnchor — a single tamper-evident record
# ---------------------------------------------------------------------------


class AuditAnchor:
    """A single tamper-evident record in the governance audit chain.

    Each anchor contains a hash of its content plus the hash of the previous
    anchor, forming an integrity chain that can be verified for tampering.

    Attributes:
        anchor_id: Unique anchor identifier.
        sequence: Position in the chain (0-based).
        previous_hash: Hash of the previous anchor (None for genesis).
        agent_id: Agent that performed the action.
        action: The action that was performed.
        verification_level: PACT VerificationLevel for this action.
        envelope_id: Constraint envelope that was evaluated (if any).
        result: Action outcome.
        metadata: Additional structured details.
        timestamp: When the action occurred.
        content_hash: SHA-256 hash of this anchor's content (set by seal()).
    """

    __slots__ = (
        "anchor_id",
        "sequence",
        "previous_hash",
        "agent_id",
        "action",
        "verification_level",
        "envelope_id",
        "result",
        "metadata",
        "timestamp",
        "content_hash",
    )

    def __init__(
        self,
        *,
        anchor_id: str = "",
        sequence: int = 0,
        previous_hash: str | None = None,
        agent_id: str = "",
        action: str = "",
        verification_level: VerificationLevel = VerificationLevel.HELD,
        envelope_id: str | None = None,
        result: str = "",
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
        content_hash: str = "",
    ) -> None:
        self.anchor_id = anchor_id or f"anc-{uuid4().hex[:8]}"
        self.sequence = sequence
        self.previous_hash = previous_hash
        self.agent_id = agent_id
        self.action = action
        self.verification_level = verification_level
        self.envelope_id = envelope_id
        self.result = result
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(UTC)
        self.content_hash = content_hash

    def compute_hash(self) -> str:
        """Compute the content hash for this anchor."""
        content = (
            f"{self.anchor_id}:{self.sequence}:{self.previous_hash or 'genesis'}:"
            f"{self.agent_id}:{self.action}:{self.verification_level.value}:"
            f"{self.envelope_id or ''}:{self.result}:{self.timestamp.isoformat()}"
        )
        if self.metadata:
            meta_str = json.dumps(self.metadata, sort_keys=True, default=str)
            content += f":{meta_str}"
        return hashlib.sha256(content.encode()).hexdigest()

    def seal(self) -> None:
        """Seal this anchor by computing and storing its content hash."""
        self.content_hash = self.compute_hash()

    @property
    def is_sealed(self) -> bool:
        return bool(self.content_hash)

    def verify_integrity(self) -> bool:
        """Verify this anchor's hash matches its content."""
        if not self.is_sealed:
            return False
        return hmac_mod.compare_digest(self.content_hash, self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "anchor_id": self.anchor_id,
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "agent_id": self.agent_id,
            "action": self.action,
            "verification_level": self.verification_level.value,
            "envelope_id": self.envelope_id,
            "result": self.result,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditAnchor:
        """Deserialize from a dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            anchor_id=data.get("anchor_id", ""),
            sequence=data.get("sequence", 0),
            previous_hash=data.get("previous_hash"),
            agent_id=data.get("agent_id", ""),
            action=data.get("action", ""),
            verification_level=VerificationLevel(
                data.get("verification_level", "HELD")
            ),
            envelope_id=data.get("envelope_id"),
            result=data.get("result", ""),
            metadata=data.get("metadata", {}),
            timestamp=ts,
            content_hash=data.get("content_hash", ""),
        )


# ---------------------------------------------------------------------------
# AuditChain — an ordered chain of audit anchors
# ---------------------------------------------------------------------------


class AuditChain:
    """An ordered chain of audit anchors with integrity verification.

    Thread-safe: append() acquires an internal lock to prevent hash chain
    corruption from concurrent appends.

    Args:
        chain_id: Unique identifier for this audit chain.
    """

    _MAX_ANCHORS = 10_000

    def __init__(self, chain_id: str, *, max_anchors: int = _MAX_ANCHORS) -> None:
        self.chain_id = chain_id
        self.anchors: list[AuditAnchor] = []
        self._max_anchors = max_anchors
        self._chain_lock = threading.Lock()

    @property
    def length(self) -> int:
        return len(self.anchors)

    @property
    def latest(self) -> AuditAnchor | None:
        return self.anchors[-1] if self.anchors else None

    def append(
        self,
        agent_id: str,
        action: str,
        verification_level: VerificationLevel,
        *,
        envelope_id: str | None = None,
        result: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditAnchor:
        """Create and append a new sealed anchor.

        Thread-safe: acquires the chain lock to ensure correct sequence
        numbering and hash linkage.

        Args:
            agent_id: The agent performing the action.
            action: The action being recorded.
            verification_level: The PACT verification level.
            envelope_id: Optional constraint envelope ID.
            result: Action outcome.
            metadata: Additional details.

        Returns:
            The newly created and sealed AuditAnchor.
        """
        with self._chain_lock:
            sequence = len(self.anchors)
            previous_hash = self.anchors[-1].content_hash if self.anchors else None

            anchor = AuditAnchor(
                anchor_id=f"{self.chain_id}-{sequence}",
                sequence=sequence,
                previous_hash=previous_hash,
                agent_id=agent_id,
                action=action,
                verification_level=verification_level,
                envelope_id=envelope_id,
                result=result,
                metadata=metadata or {},
            )
            anchor.seal()
            self.anchors.append(anchor)
            # Evict oldest 10% when at capacity (bounded collection)
            if len(self.anchors) > self._max_anchors:
                evict_count = max(1, self._max_anchors // 10)
                self.anchors = self.anchors[evict_count:]
            return anchor

    def verify_chain_integrity(self) -> tuple[bool, list[str]]:
        """Walk the chain and verify every anchor's integrity.

        Returns:
            (is_valid, list of error messages). Empty list means valid.
        """
        errors: list[str] = []

        for i, anchor in enumerate(self.anchors):
            if anchor.sequence != i:
                errors.append(
                    f"Anchor {i}: sequence mismatch (expected {i}, got {anchor.sequence})"
                )

            if not anchor.verify_integrity():
                errors.append(f"Anchor {i}: content hash mismatch (tampered?)")

            if i == 0:
                if anchor.previous_hash is not None:
                    errors.append(
                        "Anchor 0: genesis anchor should have no previous_hash"
                    )
            else:
                expected_prev = self.anchors[i - 1].content_hash
                if not hmac_mod.compare_digest(anchor.previous_hash, expected_prev):
                    errors.append(
                        f"Anchor {i}: previous_hash doesn't match anchor {i - 1}"
                    )

        return len(errors) == 0, errors

    def filter_by_agent(self, agent_id: str) -> list[AuditAnchor]:
        """Get all anchors for a specific agent."""
        return [a for a in self.anchors if a.agent_id == agent_id]

    def filter_by_level(self, level: VerificationLevel) -> list[AuditAnchor]:
        """Get all anchors at a specific verification level."""
        return [a for a in self.anchors if a.verification_level == level]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire chain."""
        return {
            "chain_id": self.chain_id,
            "anchors": [a.to_dict() for a in self.anchors],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditChain:
        """Deserialize from a dictionary."""
        chain = cls(chain_id=data.get("chain_id", ""))
        for anchor_data in data.get("anchors", []):
            chain.anchors.append(AuditAnchor.from_dict(anchor_data))
        return chain
