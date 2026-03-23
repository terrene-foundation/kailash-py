# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EATP Audit Trail -- records governance events for the orchestration layer.

Every governance-relevant action (spawn, terminate, tool call, budget check,
state transition, held event, modification) creates an audit record with
timestamp, agent identity, action details, and hash chain linkage.

Storage: In-memory with bounded collection (maxlen=10000 per trust-plane rules).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["AuditRecord", "AuditTrail"]


@dataclass(frozen=True)
class AuditRecord:
    """A single audit record in the trail.

    Frozen to prevent accidental mutation after creation. Hash chain
    integrity depends on records being immutable once appended.
    """

    record_id: str
    record_type: str
    timestamp: datetime
    agent_id: str
    parent_id: str | None
    action: str
    details: dict[str, Any]
    prev_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for export and storage."""
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "parent_id": self.parent_id,
            "action": self.action,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


class AuditTrail:
    """Append-only audit trail with hash chain integrity.

    Bounded to 10000 records (maxlen per trust-plane-security.md Rule 4).
    Each record's hash is computed as:
        sha256(prev_hash + record_type + agent_id + action + timestamp_iso)
    """

    def __init__(self, maxlen: int = 10000) -> None:
        if maxlen <= 0:
            raise ValueError(f"maxlen must be positive, got {maxlen}")
        self._lock = threading.Lock()
        self._records: deque[AuditRecord] = deque(maxlen=maxlen)
        self._prev_hash: str = "genesis"

    def _compute_hash(
        self,
        prev_hash: str,
        record_type: str,
        agent_id: str,
        action: str,
        timestamp: datetime,
    ) -> str:
        """Compute SHA-256 hash for a record.

        Hash = sha256(prev_hash + record_type + agent_id + action + timestamp_iso).
        """
        payload = prev_hash + record_type + agent_id + action + timestamp.isoformat()
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _append_record(
        self,
        record_type: str,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        parent_id: str | None = None,
    ) -> AuditRecord:
        """Create, hash, and append a new record to the trail. Thread-safe."""
        with self._lock:
            return self._append_record_locked(record_type, agent_id, action, details, parent_id)

    def _append_record_locked(
        self,
        record_type: str,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        parent_id: str | None = None,
    ) -> AuditRecord:
        """Create, hash, and append. Caller must hold lock."""
        timestamp = datetime.now(timezone.utc)
        record_hash = self._compute_hash(
            prev_hash=self._prev_hash,
            record_type=record_type,
            agent_id=agent_id,
            action=action,
            timestamp=timestamp,
        )

        record = AuditRecord(
            record_id=str(uuid.uuid4()),
            record_type=record_type,
            timestamp=timestamp,
            agent_id=agent_id,
            parent_id=parent_id,
            action=action,
            details=details,
            prev_hash=self._prev_hash,
            record_hash=record_hash,
        )

        self._records.append(record)
        self._prev_hash = record_hash

        logger.debug(
            "Audit record appended: type=%s agent=%s action=%s hash=%s",
            record_type,
            agent_id,
            action,
            record_hash[:12],
        )

        return record

    def record_genesis(self, agent_id: str, envelope: dict[str, Any]) -> AuditRecord:
        """Record root agent creation.

        Args:
            agent_id: Instance ID of the root agent.
            envelope: The constraint envelope assigned to the root agent.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="genesis",
            agent_id=agent_id,
            action="genesis",
            details={"envelope": envelope},
            parent_id=None,
        )

    def record_delegation(
        self,
        parent_id: str,
        child_id: str,
        envelope: dict[str, Any],
    ) -> AuditRecord:
        """Record parent delegating to child with envelope.

        Args:
            parent_id: Instance ID of the delegating parent.
            child_id: Instance ID of the new child agent.
            envelope: The constraint envelope assigned to the child.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="delegation",
            agent_id=child_id,
            action="delegation",
            details={"envelope": envelope},
            parent_id=parent_id,
        )

    def record_termination(
        self,
        agent_id: str,
        reason: str,
        budget_consumed: dict[str, Any],
    ) -> AuditRecord:
        """Record agent termination.

        Args:
            agent_id: Instance ID of the terminated agent.
            reason: Why the agent was terminated.
            budget_consumed: Resource consumption at termination time.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="termination",
            agent_id=agent_id,
            action="termination",
            details={"reason": reason, "budget_consumed": budget_consumed},
        )

    def record_action(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
    ) -> AuditRecord:
        """Record a governance-relevant action (tool call, budget check).

        Args:
            agent_id: Instance ID of the acting agent.
            action: Human-readable action description.
            details: Structured details about the action.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="action",
            agent_id=agent_id,
            action=action,
            details=details,
        )

    def record_held(
        self,
        agent_id: str,
        node_id: str,
        reason: str,
    ) -> AuditRecord:
        """Record a held event.

        Args:
            agent_id: Instance ID of the agent that triggered the hold.
            node_id: Plan node ID that was held.
            reason: Why the node was held.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="held",
            agent_id=agent_id,
            action="held",
            details={"node_id": node_id, "reason": reason},
        )

    def record_modification(
        self,
        agent_id: str,
        modification: dict[str, Any],
    ) -> AuditRecord:
        """Record a plan modification.

        Args:
            agent_id: Instance ID of the agent performing the modification.
            modification: Structured modification details.

        Returns:
            The created AuditRecord.
        """
        return self._append_record(
            record_type="modification",
            agent_id=agent_id,
            action="modification",
            details={"modification": modification},
        )

    def verify_chain(self) -> bool:
        """Verify hash chain integrity across surviving records. Thread-safe.

        Recomputes each record's hash from its fields and checks:
        1. The computed hash matches the stored record_hash.
        2. Each record's prev_hash matches the previous record's record_hash.

        Note: After bounded eviction (deque maxlen reached), the oldest records
        are dropped. The first surviving record's prev_hash will reference the
        evicted record — we accept this and start verification from the first
        surviving record's stored prev_hash (not "genesis").

        Returns:
            True if the chain is intact, False if any record has been tampered with.
        """
        with self._lock:
            return self._verify_chain_locked()

    def _verify_chain_locked(self) -> bool:
        """Verify chain. Caller must hold lock."""
        if not self._records:
            return True

        # Start from first surviving record's prev_hash (handles eviction)
        prev_hash = self._records[0].prev_hash
        for record in self._records:
            # Verify prev_hash linkage
            if not hmac_mod.compare_digest(record.prev_hash, prev_hash):
                logger.warning(
                    "Hash chain broken: record %s prev_hash mismatch " "(expected=%s, got=%s)",
                    record.record_id,
                    prev_hash,
                    record.prev_hash,
                )
                return False

            # Recompute hash and verify
            expected_hash = self._compute_hash(
                prev_hash=record.prev_hash,
                record_type=record.record_type,
                agent_id=record.agent_id,
                action=record.action,
                timestamp=record.timestamp,
            )
            if not hmac_mod.compare_digest(record.record_hash, expected_hash):
                logger.warning(
                    "Hash chain tampered: record %s hash mismatch " "(expected=%s, got=%s)",
                    record.record_id,
                    expected_hash,
                    record.record_hash,
                )
                return False

            prev_hash = record.record_hash

        return True

    def query_by_agent(self, agent_id: str) -> list[AuditRecord]:
        """Return all records for a specific agent. Thread-safe.

        Args:
            agent_id: The agent instance ID to filter by.

        Returns:
            List of AuditRecords where agent_id matches, in chronological order.
        """
        with self._lock:
            return [r for r in self._records if r.agent_id == agent_id]

    def to_list(self) -> list[dict[str, Any]]:
        """Export all records as dicts. Thread-safe.

        Returns:
            List of dict representations of all records, in chronological order.
        """
        with self._lock:
            return [r.to_dict() for r in self._records]
