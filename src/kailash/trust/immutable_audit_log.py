# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Immutable Audit Log with SHA-256 Hash Chain.

Provides an append-only audit log where every entry is linked to the previous
entry via a SHA-256 hash chain.  This enables tamper detection: if any entry
is modified, the chain verification will fail from that point forward.

Key design principles:
- APPEND-ONLY: No clear, delete, or update methods exist.
- HASH-CHAINED: Each entry includes the hash of the previous entry.
- BOUNDED: Configurable maximum capacity with retention policy eviction.
- THREAD-SAFE: All mutations are protected by a threading.Lock.
- CONSTANT-TIME COMPARISON: Hash comparisons use ``hmac.compare_digest``.

SPEC-08 consolidation (2026-04): ``AuditEventType`` and ``AuditOutcome`` are
re-exported from the canonical ``kailash.trust.audit_store`` module.  The
``AuditEntry`` dataclass remains local -- it is a pre-SPEC-08 internal type
specific to the ``ImmutableAuditLog`` deque, with a sequence-number-based
structure distinct from the canonical ``AuditEvent`` (which uses
parent-anchor-id based causal chains).

Cross-SDK alignment: esperie-enterprise/kailash-rs#83
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

# SPEC-08: AuditEventType and AuditOutcome live in the canonical audit store.
from kailash.trust.audit_store import AuditEventType, AuditOutcome

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ENTRIES = 10_000
"""Default bounded capacity for the audit log (CARE-010)."""

_GENESIS_HASH = "0" * 64
"""Sentinel previous-hash for the very first entry in the chain."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEntry:
    """A single, immutable audit log entry.

    All fields participate in the SHA-256 hash computation.  The ``hash``
    field is the hash of the canonical JSON representation of every other
    field (including ``prev_hash`` which links to the previous entry).

    Attributes:
        seq: Monotonically increasing sequence number (1-based).
        prev_hash: SHA-256 hex digest of the previous entry (or genesis sentinel).
        timestamp: UTC timestamp of when the entry was created.
        event_type: Category of the audited event.
        actor: Identifier of the entity that performed the action.
        action: Short description of what was done.
        resource: Identifier of the resource acted upon.
        outcome: Result of the action.
        metadata: Arbitrary additional context.
        hash: SHA-256 hex digest covering all fields above.
    """

    seq: int
    prev_hash: str
    timestamp: str  # ISO-8601 UTC string for deterministic hashing
    event_type: str
    actor: str
    action: str
    resource: str
    outcome: str
    metadata: Dict[str, Any]
    hash: str

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "seq": self.seq,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "metadata": dict(self.metadata),
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuditEntry:
        """Deserialize from a plain dictionary."""
        return cls(
            seq=int(data["seq"]),
            prev_hash=str(data["prev_hash"]),
            timestamp=str(data["timestamp"]),
            event_type=str(data["event_type"]),
            actor=str(data["actor"]),
            action=str(data["action"]),
            resource=str(data["resource"]),
            outcome=str(data["outcome"]),
            metadata=dict(data.get("metadata") or {}),
            hash=str(data["hash"]),
        )


@dataclass
class RetentionPolicy:
    """Retention policy for bounded audit log eviction.

    When the log reaches ``max_entries``, the oldest entries that do
    **not** have a legal hold are evicted first.

    Attributes:
        max_entries: Maximum number of entries to retain.
        legal_hold_event_types: Event types exempt from eviction.
    """

    max_entries: int = _DEFAULT_MAX_ENTRIES
    legal_hold_event_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_entries": self.max_entries,
            "legal_hold_event_types": list(self.legal_hold_event_types),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RetentionPolicy:
        return cls(
            max_entries=int(data.get("max_entries", _DEFAULT_MAX_ENTRIES)),
            legal_hold_event_types=list(data.get("legal_hold_event_types") or []),
        )


@dataclass
class ChainVerificationResult:
    """Result of a hash-chain verification.

    Attributes:
        valid: ``True`` if the verified range is intact.
        entries_checked: Number of entries that were verified.
        first_invalid_seq: Sequence number of the first tampered entry, or ``None``.
        errors: Human-readable descriptions of detected issues.
    """

    valid: bool
    entries_checked: int
    first_invalid_seq: Optional[int] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "entries_checked": self.entries_checked,
            "first_invalid_seq": self.first_invalid_seq,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChainVerificationResult:
        return cls(
            valid=bool(data["valid"]),
            entries_checked=int(data["entries_checked"]),
            first_invalid_seq=data.get("first_invalid_seq"),
            errors=list(data.get("errors") or []),
        )


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def _compute_entry_hash(
    seq: int,
    prev_hash: str,
    timestamp: str,
    event_type: str,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    metadata: Dict[str, Any],
) -> str:
    """Compute the SHA-256 hash covering ALL entry fields.

    The canonical form is a JSON string with sorted keys and minimal
    separators so that the hash is deterministic across platforms.
    """
    payload = {
        "seq": seq,
        "prev_hash": prev_hash,
        "timestamp": timestamp,
        "event_type": event_type,
        "actor": actor,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "metadata": metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ImmutableAuditLog
# ---------------------------------------------------------------------------


class ImmutableAuditLog:
    """Append-only, hash-chained audit log.

    This class intentionally provides **no** ``clear``, ``delete``, or
    ``update`` methods.  The only way to add data is via :meth:`append`.

    Thread safety is guaranteed by a :class:`threading.Lock` that
    protects all mutations and reads of the internal deque.

    Example::

        log = ImmutableAuditLog()
        entry = log.append(
            event_type="action_executed",
            actor="agent-007",
            action="analyse_data",
            resource="dataset-42",
            outcome="success",
        )
        assert log.verify_chain().valid

    Args:
        retention_policy: Controls max capacity and legal-hold exemptions.
    """

    def __init__(
        self,
        retention_policy: Optional[RetentionPolicy] = None,
    ) -> None:
        self._policy = retention_policy or RetentionPolicy()
        self._entries: Deque[AuditEntry] = deque(maxlen=self._policy.max_entries)
        self._lock = threading.Lock()
        self._seq: int = 0

    # -- public API (write) --------------------------------------------------

    def append(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Append a new entry to the audit log.

        This is the **only** mutation method.  The entry's hash is
        computed from all supplied fields plus the hash of the previous
        entry, forming a chain.

        Args:
            event_type: Category of the event (see :class:`AuditEventType`).
            actor: Who performed the action.
            action: What was done.
            resource: What was acted upon.
            outcome: Result (see :class:`AuditOutcome`).
            metadata: Optional additional context.

        Returns:
            The newly created :class:`AuditEntry` (frozen dataclass).
        """
        meta = dict(metadata) if metadata else {}
        ts = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._seq += 1
            prev_hash = self._entries[-1].hash if self._entries else _GENESIS_HASH

            entry_hash = _compute_entry_hash(
                seq=self._seq,
                prev_hash=prev_hash,
                timestamp=ts,
                event_type=event_type,
                actor=actor,
                action=action,
                resource=resource,
                outcome=outcome,
                metadata=meta,
            )

            entry = AuditEntry(
                seq=self._seq,
                prev_hash=prev_hash,
                timestamp=ts,
                event_type=event_type,
                actor=actor,
                action=action,
                resource=resource,
                outcome=outcome,
                metadata=meta,
                hash=entry_hash,
            )

            # Enforce retention: evict oldest non-held entries if at capacity.
            # deque(maxlen=...) auto-evicts from the left, but we need to
            # respect legal holds, so we handle eviction manually when holds
            # are configured.
            if (
                self._policy.legal_hold_event_types
                and len(self._entries) >= self._policy.max_entries
            ):
                self._evict_respecting_holds()

            self._entries.append(entry)

        logger.debug(
            "Audit entry appended: seq=%d actor=%s action=%s",
            entry.seq,
            actor,
            action,
        )
        return entry

    # -- public API (read / query) -------------------------------------------

    def verify_chain(
        self,
        start: int = 0,
        end: Optional[int] = None,
    ) -> ChainVerificationResult:
        """Verify the integrity of the hash chain.

        For each entry in the range ``[start, end)`` (indices into the
        internal deque, **not** sequence numbers), the method checks:

        1. The entry's ``hash`` matches the recomputed hash of its fields.
        2. The entry's ``prev_hash`` matches the hash of the preceding entry
           (or the genesis sentinel for the first entry in the deque).

        Hash comparisons use :func:`hmac.compare_digest` to avoid timing
        side-channels.

        Args:
            start: Start index (inclusive, 0-based into current deque).
            end: End index (exclusive).  ``None`` means through the last entry.

        Returns:
            :class:`ChainVerificationResult` describing the outcome.
        """
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return ChainVerificationResult(valid=True, entries_checked=0)

        actual_end = len(entries) if end is None else min(end, len(entries))
        actual_start = max(0, start)

        errors: List[str] = []
        first_invalid: Optional[int] = None
        checked = 0

        for i in range(actual_start, actual_end):
            entry = entries[i]

            # Determine expected prev_hash
            if i == 0:
                expected_prev = _GENESIS_HASH
            else:
                expected_prev = entries[i - 1].hash

            # Check prev_hash linkage
            if not hmac_mod.compare_digest(entry.prev_hash, expected_prev):
                msg = (
                    f"Broken chain at seq {entry.seq}: prev_hash mismatch "
                    f"(expected {expected_prev[:16]}..., "
                    f"got {entry.prev_hash[:16]}...)"
                )
                errors.append(msg)
                if first_invalid is None:
                    first_invalid = entry.seq

            # Recompute hash and compare
            recomputed = _compute_entry_hash(
                seq=entry.seq,
                prev_hash=entry.prev_hash,
                timestamp=entry.timestamp,
                event_type=entry.event_type,
                actor=entry.actor,
                action=entry.action,
                resource=entry.resource,
                outcome=entry.outcome,
                metadata=entry.metadata,
            )
            if not hmac_mod.compare_digest(entry.hash, recomputed):
                msg = (
                    f"Hash mismatch at seq {entry.seq}: entry may have been "
                    f"tampered with"
                )
                errors.append(msg)
                if first_invalid is None:
                    first_invalid = entry.seq

            checked += 1

        return ChainVerificationResult(
            valid=len(errors) == 0,
            entries_checked=checked,
            first_invalid_seq=first_invalid,
            errors=errors,
        )

    def query(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[AuditEntry]:
        """Query entries by optional filters.

        All filters are combined with AND logic.  Passing no filters
        returns all entries currently in the log.

        Args:
            event_type: Filter by event type string.
            actor: Filter by actor identifier.
            start_time: Include entries at or after this time (UTC).
            end_time: Include entries at or before this time (UTC).

        Returns:
            List of matching :class:`AuditEntry` objects (newest last).
        """
        with self._lock:
            entries = list(self._entries)

        results: List[AuditEntry] = []
        for entry in entries:
            if event_type is not None and entry.event_type != event_type:
                continue
            if actor is not None and entry.actor != actor:
                continue
            if start_time is not None:
                entry_dt = datetime.fromisoformat(entry.timestamp)
                if entry_dt < start_time:
                    continue
            if end_time is not None:
                entry_dt = datetime.fromisoformat(entry.timestamp)
                if entry_dt > end_time:
                    continue
            results.append(entry)

        return results

    def get_entry(self, seq: int) -> Optional[AuditEntry]:
        """Retrieve a single entry by sequence number.

        Args:
            seq: The 1-based sequence number.

        Returns:
            The :class:`AuditEntry` if found, ``None`` otherwise.
        """
        with self._lock:
            for entry in self._entries:
                if entry.seq == seq:
                    return entry
        return None

    @property
    def count(self) -> int:
        """Number of entries currently stored."""
        with self._lock:
            return len(self._entries)

    @property
    def last_seq(self) -> int:
        """Last sequence number assigned (0 if empty)."""
        with self._lock:
            return self._seq

    @property
    def last_hash(self) -> str:
        """Hash of the most recent entry, or the genesis sentinel."""
        with self._lock:
            if self._entries:
                return self._entries[-1].hash
            return _GENESIS_HASH

    # -- internal helpers ----------------------------------------------------

    def _evict_respecting_holds(self) -> None:
        """Remove the oldest non-held entry to make room.

        Called under ``self._lock``.  If every entry is under legal hold
        the oldest entry is evicted anyway to prevent unbounded growth
        (safety net).
        """
        hold_types = set(self._policy.legal_hold_event_types)
        for i, entry in enumerate(self._entries):
            if entry.event_type not in hold_types:
                del self._entries[i]
                return
        # All entries held: evict oldest as safety net.
        if self._entries:
            self._entries.popleft()


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "AuditEventType",
    "AuditOutcome",
    "AuditEntry",
    "RetentionPolicy",
    "ChainVerificationResult",
    "ImmutableAuditLog",
]
