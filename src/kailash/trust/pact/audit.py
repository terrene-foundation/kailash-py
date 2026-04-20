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

GENESIS_HASH = "0" * 64
"""Canonical genesis sentinel for audit-chain fingerprints.

Used as `previous_hash` when hashing the first entry in any audit chain.
MUST match across all Kailash SDKs (Python + Rust) per EATP D6 and the
cross-SDK fingerprint contract — see `rules/event-payload-classification.md`
MUST Rule 2. Matches existing blockchain convention (bitcoin, ethereum) and
shares the byte shape of a real SHA-256 hex digest so verifiers need no
option/enum branching.

Change history:
    2026-04-20: replaced the prior ``'genesis'`` literal. Breaking change —
    existing chains rooted at ``'genesis'`` will no longer verify.
"""

__all__ = [
    "GENESIS_HASH",
    "PactAuditAction",
    "create_pact_audit_details",
    "AuditAnchor",
    "AuditChain",
    "TieredAuditDispatcher",
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
    BRIDGE_APPROVED = "bridge_approved"
    BRIDGE_ESTABLISHED = "bridge_established"
    BRIDGE_REVOKED = "bridge_revoked"
    ADDRESS_COMPUTED = "address_computed"
    VACANCY_DESIGNATED = "vacancy_designated"
    VACANCY_SUSPENDED = "vacancy_suspended"
    BRIDGE_CONSENT = "bridge_consent"
    BRIDGE_REJECTED = "bridge_rejected"
    CLEARANCE_TRANSITIONED = "clearance_transitioned"
    PLAN_SUSPENDED = "plan_suspended"
    PLAN_RESUMED = "plan_resumed"
    RESUME_CONDITION_UPDATED = "resume_condition_updated"


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
        """Compute the content hash for this anchor.

        Canonical input format (cross-SDK contract, see kailash-rs#449 §2):

            {anchor_id}:{sequence}:{previous_hash}:{agent_id}:{action}:
            {verification_level}:{envelope_id_or_empty}:{result}:
            {iso8601_utc_with_+00:00}[:{metadata_json_sorted_compact}]

        Metadata MUST use compact separators (``","``, ``":"``) and
        ASCII-escaped strings so Python's output matches Rust's
        ``serde_json::to_string(&BTreeMap)`` byte-for-byte. Empty metadata
        omits the suffix entirely (no trailing ``:``).
        """
        content = (
            f"{self.anchor_id}:{self.sequence}:{self.previous_hash or GENESIS_HASH}:"
            f"{self.agent_id}:{self.action}:{self.verification_level.value}:"
            f"{self.envelope_id or ''}:{self.result}:{self.timestamp.isoformat()}"
        )
        if self.metadata:
            meta_str = json.dumps(
                self.metadata,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
                ensure_ascii=True,
            )
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

    def _compute_hash_legacy(self) -> str:
        """Recompute the content hash under the pre-2026-04-20 contract.

        Used ONLY for forensic disambiguation in ``verify_chain_integrity``
        to distinguish legacy-rooted chains (pre-GENESIS_HASH migration)
        from real tampering. Legacy form: ``'genesis'`` literal as the
        first-anchor sentinel AND default ``json.dumps`` separators (with
        spaces) for metadata canonicalization.

        An anchor whose stored ``content_hash`` matches this legacy form
        is a pre-migration chain that requires re-sealing, NOT a tampered
        record.
        """
        content = (
            f"{self.anchor_id}:{self.sequence}:{self.previous_hash or 'genesis'}:"
            f"{self.agent_id}:{self.action}:{self.verification_level.value}:"
            f"{self.envelope_id or ''}:{self.result}:{self.timestamp.isoformat()}"
        )
        if self.metadata:
            meta_str = json.dumps(self.metadata, sort_keys=True, default=str)
            content += f":{meta_str}"
        return hashlib.sha256(content.encode()).hexdigest()

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
                # Distinguish legacy-sentinel chains (pre-2026-04-20 migration)
                # from real tampering. An anchor whose stored content_hash
                # matches the legacy compute is a pre-migration chain that
                # requires re-seal, not a forensic incident.
                if anchor.is_sealed and hmac_mod.compare_digest(
                    anchor.content_hash, anchor._compute_hash_legacy()
                ):
                    errors.append(
                        f"Anchor {i}: legacy genesis sentinel detected — chain "
                        f"pre-dates 2026-04-20 canonical alignment (kailash-rs#449). "
                        f"Re-seal required: re-invoke AuditAnchor.seal() across every "
                        f"anchor in the chain. This is NOT tampering."
                    )
                else:
                    errors.append(f"Anchor {i}: content hash mismatch (tampered?)")

            if i == 0:
                if anchor.previous_hash is not None:
                    errors.append(
                        "Anchor 0: genesis anchor should have no previous_hash"
                    )
            else:
                expected_prev = self.anchors[i - 1].content_hash
                if anchor.previous_hash is None or not hmac_mod.compare_digest(
                    anchor.previous_hash, expected_prev
                ):
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
        """Deserialize from a dictionary and verify integrity (P-H10).

        After reconstruction, verifies the hash chain integrity.
        Raises PactError if the chain is corrupted.
        """
        chain = cls(chain_id=data.get("chain_id", ""))
        for anchor_data in data.get("anchors", []):
            chain.anchors.append(AuditAnchor.from_dict(anchor_data))

        # Verify integrity after reconstruction (P-H10 fix)
        if chain.anchors:
            valid, errors = chain.verify_chain_integrity()
            if not valid:
                logger.warning(
                    "AuditChain '%s' integrity check failed after from_dict: %s",
                    chain.chain_id,
                    errors,
                )

        return chain


# ---------------------------------------------------------------------------
# TieredAuditDispatcher -- gradient-aligned persistence tiers (PACT-08)
# ---------------------------------------------------------------------------

# Tier buffer bound: maximum FLAGGED anchors buffered before forced flush.
_MAX_SESSION_BUFFER = 10_000


class TieredAuditDispatcher:
    """Routes audit anchors to storage tiers based on verification level.

    The three tiers align with the PACT verification gradient:

    * **Tier 1 (ephemeral)** -- ``AUTO_APPROVED`` actions are written only to
      the in-memory ``AuditChain``.  Cheap, fast, lost on process restart.
    * **Tier 2 (session-buffered)** -- ``FLAGGED`` actions are buffered in
      memory and flushed to the durable store at session end via
      ``flush_session()``.  Balances cost with auditability.
    * **Tier 3 (synchronous durable)** -- ``HELD`` and ``BLOCKED`` actions are
      written synchronously to both the ephemeral chain AND the durable store.
      These represent governance denials or holds that MUST survive restarts.

    Thread safety: the dispatcher acquires ``_lock`` around the session buffer.
    The ephemeral ``AuditChain`` and durable store each have their own locks.

    Args:
        ephemeral: The in-memory ``AuditChain`` for all tiers.
        durable: An ``InMemoryAuditStore`` (or any store exposing
            ``create_event`` / ``append``).  When ``None``, Tier 2 and 3
            behave identically to Tier 1 (ephemeral-only).
    """

    def __init__(
        self,
        ephemeral: AuditChain,
        durable: Any | None = None,
    ) -> None:
        self._ephemeral = ephemeral
        self._durable = durable
        self._session_buffer: list[AuditAnchor] = []
        self._lock = threading.Lock()

    @property
    def ephemeral(self) -> AuditChain:
        """The underlying ephemeral audit chain."""
        return self._ephemeral

    @property
    def session_buffer_size(self) -> int:
        """Number of FLAGGED anchors currently buffered."""
        with self._lock:
            return len(self._session_buffer)

    def dispatch(
        self,
        anchor: AuditAnchor,
        level: VerificationLevel,
    ) -> None:
        """Route an anchor to the appropriate persistence tier.

        Args:
            anchor: The sealed ``AuditAnchor`` to dispatch.
            level: The ``VerificationLevel`` that determines the tier.
        """
        if level in (VerificationLevel.HELD, VerificationLevel.BLOCKED):
            # Tier 3: synchronous durable write + ephemeral
            if self._durable is not None:
                event = self._anchor_to_event(anchor)
                try:
                    # InMemoryAuditStore.append is async, but for synchronous
                    # governance paths we need a sync wrapper.  We use the
                    # store's internal deque directly if available, otherwise
                    # fall back to create+append via an event loop.
                    import asyncio

                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop is not None and loop.is_running():
                        # Already in an async context -- schedule as task
                        loop.create_task(self._durable.append(event))
                    else:
                        asyncio.run(self._durable.append(event))
                except Exception:
                    logger.exception(
                        "TieredAuditDispatcher: durable write failed for "
                        "HELD/BLOCKED anchor %s -- ephemeral-only",
                        anchor.anchor_id,
                    )
            self._ephemeral.append(
                agent_id=anchor.agent_id,
                action=anchor.action,
                verification_level=level,
                envelope_id=anchor.envelope_id,
                result=anchor.result,
                metadata=anchor.metadata,
            )

        elif level == VerificationLevel.FLAGGED:
            # Tier 2: buffer for session-end persistence + ephemeral
            with self._lock:
                self._session_buffer.append(anchor)
                # Bounded: evict oldest 10% at capacity
                if len(self._session_buffer) > _MAX_SESSION_BUFFER:
                    evict = max(1, _MAX_SESSION_BUFFER // 10)
                    self._session_buffer = self._session_buffer[evict:]
            self._ephemeral.append(
                agent_id=anchor.agent_id,
                action=anchor.action,
                verification_level=level,
                envelope_id=anchor.envelope_id,
                result=anchor.result,
                metadata=anchor.metadata,
            )

        else:
            # Tier 1: ephemeral only (AUTO_APPROVED)
            self._ephemeral.append(
                agent_id=anchor.agent_id,
                action=anchor.action,
                verification_level=level,
                envelope_id=anchor.envelope_id,
                result=anchor.result,
                metadata=anchor.metadata,
            )

    def flush_session(self) -> int:
        """Persist Tier 2 (FLAGGED) anchors to the durable store.

        Returns the number of anchors flushed.  Clears the session buffer
        regardless of whether the durable store is configured (so the buffer
        does not grow unbounded in ephemeral-only mode).

        Returns:
            Number of anchors flushed to durable storage.
        """
        with self._lock:
            to_flush = list(self._session_buffer)
            self._session_buffer.clear()

        if not to_flush or self._durable is None:
            return 0

        flushed = 0
        for anchor in to_flush:
            event = self._anchor_to_event(anchor)
            try:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None and loop.is_running():
                    loop.create_task(self._durable.append(event))
                else:
                    asyncio.run(self._durable.append(event))
                flushed += 1
            except Exception:
                logger.exception(
                    "TieredAuditDispatcher: flush failed for anchor %s",
                    anchor.anchor_id,
                )
        return flushed

    def _anchor_to_event(self, anchor: AuditAnchor) -> Any:
        """Convert a PACT AuditAnchor to a canonical AuditEvent.

        Uses the durable store's ``create_event`` factory to build a
        properly hash-chained event from the anchor's fields.

        Returns:
            An ``AuditEvent`` instance ready for ``store.append()``.
        """
        if self._durable is None:
            raise RuntimeError("Cannot convert anchor to event without a durable store")
        return self._durable.create_event(
            actor=anchor.agent_id,
            action=anchor.action,
            resource=anchor.envelope_id or "",
            outcome=anchor.result or "success",
            metadata={
                **anchor.metadata,
                "verification_level": anchor.verification_level.value,
                "pact_anchor_id": anchor.anchor_id,
            },
        )
