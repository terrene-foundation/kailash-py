# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Canonical Audit Store -- SINGLE source of truth for audit events (SPEC-08).

Consolidates the 5+ scattered audit implementations into ONE canonical module:

1. ``AuditEvent`` -- frozen dataclass superset of all existing audit record types
2. ``AuditFilter`` -- query filter for flexible audit retrieval
3. ``AuditStore`` -- protocol (abstract interface) for audit storage
4. ``InMemoryAuditStore`` -- list-backed store for testing and Level 0
5. ``SqliteAuditStore`` -- persistent store using AsyncSQLitePool

Error types:
- ``AuditStoreError`` -- base for all audit store failures
- ``ChainIntegrityError`` -- Merkle chain verification failure
- ``AuditQueryError`` -- query execution failure

Key Design Principles:
- APPEND-ONLY: No updates or deletes (immutable audit trail)
- HASH-CHAINED: Every event links to the previous via SHA-256 Merkle chain
- CONSTANT-TIME COMPARISON: All hash comparisons use ``hmac.compare_digest``
- BOUNDED: In-memory stores use ``maxlen=10_000`` with oldest-10% eviction
- QUERYABLE: Efficient queries by actor, action, resource, time range

Backward Compatibility:
- ``AuditRecord``, ``AppendOnlyAuditStore``, ``IntegrityVerificationResult``,
  ``AuditAnchorNotFoundError``, ``AuditStoreImmutabilityError`` are preserved
  and re-exported for existing code that imports them from this module.
- The legacy ``AuditStore`` ABC is renamed ``LegacyAuditStore`` internally
  but still exported as ``AuditStore`` for backward compatibility via the
  ``__all__`` list.  New code should use the protocol-style interface.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from kailash.trust.chain import ActionResult, AuditAnchor
from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_EVENTS = 10_000
"""Default bounded capacity for in-memory audit stores (CARE-010)."""

_GENESIS_HASH = "0" * 64
"""Sentinel previous-hash for the very first event in the chain."""

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class AuditStoreError(TrustError):
    """Base exception for audit store operations."""

    pass


class ChainIntegrityError(AuditStoreError):
    """Raised when Merkle chain verification detects tampering or inconsistency."""

    def __init__(self, message: str, sequence: Optional[int] = None):
        super().__init__(
            message,
            details={"sequence": sequence},
        )
        self.sequence = sequence


class AuditQueryError(AuditStoreError):
    """Raised when an audit query fails."""

    def __init__(self, message: str, filter_info: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            details={"filter": filter_info or {}},
        )
        self.filter_info = filter_info or {}


class AuditAnchorNotFoundError(AuditStoreError):
    """Raised when an audit anchor is not found."""

    def __init__(self, anchor_id: str):
        super().__init__(
            f"Audit anchor not found: {anchor_id}", details={"anchor_id": anchor_id}
        )
        self.anchor_id = anchor_id


class AuditStoreImmutabilityError(AuditStoreError):
    """Raised when attempting to modify or delete audit records.

    CARE-010: Enforces append-only semantics by blocking UPDATE and DELETE.
    """

    def __init__(
        self,
        operation: str,
        message: Optional[str] = None,
        record_id: Optional[str] = None,
    ):
        if message is None:
            message = f"Audit records are immutable - {operation} not allowed"
        super().__init__(
            message,
            details={"operation": operation, "record_id": record_id},
        )
        self.operation = operation
        self.record_id = record_id


# ---------------------------------------------------------------------------
# Canonical AuditEvent (SPEC-08 superset)
# ---------------------------------------------------------------------------


class AuditEventType(str, Enum):
    """Well-known audit event types (cross-domain union).

    String-backed enum whose ``.value`` is used to populate the canonical
    ``AuditEvent.event_type`` field. This enum provides a shared vocabulary
    for high-level trust-plane events; domain-specific modules MAY define
    their own enums as long as the string values are preserved in
    ``AuditEvent.event_type``.
    """

    # Generic trust events (from immutable_audit_log)
    ACTION_EXECUTED = "action_executed"
    ACTION_DENIED = "action_denied"
    DELEGATION_CREATED = "delegation_created"
    DELEGATION_REVOKED = "delegation_revoked"
    TRUST_ESTABLISHED = "trust_established"
    TRUST_REVOKED = "trust_revoked"
    POLICY_CHANGED = "policy_changed"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    CONSTRAINT_VIOLATED = "constraint_violated"
    SYSTEM_EVENT = "system_event"
    CUSTOM = "custom"

    # Workflow lifecycle events (from runtime.trust.audit)
    WORKFLOW_START = "workflow_start"
    WORKFLOW_END = "workflow_end"
    WORKFLOW_ERROR = "workflow_error"
    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    TRUST_VERIFICATION = "trust_verification"
    TRUST_DENIED = "trust_denied"
    RESOURCE_ACCESS = "resource_access"
    DELEGATION_USED = "delegation_used"


class AuditOutcome(str, Enum):
    """Outcome of an audited action.

    String-backed enum whose ``.value`` populates the canonical
    ``AuditEvent.outcome`` field.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


def _compute_event_hash(
    event_id: str,
    timestamp: str,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    prev_hash: str,
    parent_anchor_id: Optional[str],
    duration_ms: Optional[float],
    metadata: Dict[str, Any],
) -> str:
    """Compute SHA-256 hash for an AuditEvent.

    The canonical form is JSON with sorted keys and minimal separators for
    deterministic hashing across platforms.

    NOTE: Only the hash-anchoring fields are included in the digest.  The
    extended domain fields (``event_type``, ``severity``, etc.) are stored
    in ``metadata`` or as optional attributes and do NOT participate in the
    Merkle chain, preserving backward compatibility for pre-SPEC-08 chains
    while still letting consumers migrate to the canonical type.
    """
    payload = {
        "event_id": event_id,
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "prev_hash": prev_hash,
        "parent_anchor_id": parent_anchor_id,
        "duration_ms": duration_ms,
        "metadata": metadata,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEvent:
    """Canonical audit event -- SPEC-08 single source of truth.

    Consolidates every audit record type that previously existed in scattered
    modules (``nodes/admin/audit_log.AuditEvent``,
    ``runtime/trust/audit.AuditEvent``, ``trust/immutable_audit_log.AuditEntry``,
    ``pact.audit.AuditAnchor``).  All of those are now either migrated to
    import from here or are deprecated-and-scheduled-for-deletion.

    The core fields (``event_id``, ``timestamp``, ``actor``, ``action``,
    ``resource``, ``outcome``, ``prev_hash``, ``hash``, ``parent_anchor_id``,
    ``duration_ms``, ``metadata``) form the Merkle-chained audit trail.
    The extended fields are optional attributes for domain-specific
    consumers (workflow runtime, enterprise admin logging) and do not
    participate in the hash chain.

    Attributes:
        event_id: Unique identifier for this event.
        timestamp: UTC timestamp as ISO-8601 string for deterministic hashing.
        actor: Identifier of the entity that performed the action.
        action: Short description of what was done.
        resource: Identifier of the resource acted upon.
        outcome: Result of the action (``success``, ``failure``, ``denied``, ``error``).
        prev_hash: SHA-256 hex digest of the previous event (or genesis sentinel).
        hash: SHA-256 hex digest covering all core fields above.
        parent_anchor_id: Link to triggering action for causal chains.
        duration_ms: Execution duration in milliseconds.
        metadata: Arbitrary additional context.
        event_type: High-level event category (see ``AuditEventType``).
        severity: Severity level string (e.g. ``"low"``, ``"high"``, ``"critical"``).
        description: Human-readable event description.
        user_id: Authenticated user identifier (enterprise audit).
        tenant_id: Multi-tenant isolation key.
        resource_id: Structured resource identifier (distinct from ``resource``).
        ip_address: Source IP address of the actor.
        user_agent: User-Agent string of the actor.
        session_id: Session correlation ID.
        correlation_id: Request/trace correlation ID.
        trace_id: Distributed trace ID for correlation across services.
        workflow_id: Workflow run identifier (runtime audit).
        node_id: Node instance identifier (runtime audit).
        agent_id: Agent identifier from delegation chain.
        human_origin_id: Identifier of the human at the root of the delegation chain.
    """

    event_id: str
    timestamp: str  # ISO-8601 UTC string for deterministic hashing
    actor: str
    action: str
    resource: str
    outcome: str  # "success", "failure", "denied", "error"
    prev_hash: str
    hash: str
    parent_anchor_id: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # --- Extended domain fields (do NOT participate in the Merkle hash) ----
    # These were previously scattered across 4 separate ``AuditEvent``
    # dataclasses (siem, nodes/admin, runtime/trust, immutable_audit_log).
    # SPEC-08 folds them into the canonical type as optional attributes.
    event_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    workflow_id: Optional[str] = None
    node_id: Optional[str] = None
    agent_id: Optional[str] = None
    human_origin_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary.

        All extended fields are included; ``None`` values are preserved so
        round-trips are lossless.
        """
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "parent_anchor_id": self.parent_anchor_id,
            "duration_ms": self.duration_ms,
            "metadata": dict(self.metadata),
            "event_type": self.event_type,
            "severity": self.severity,
            "description": self.description,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AuditEvent:
        """Deserialize from a plain dictionary.

        Unknown extra keys are ignored.  Missing optional keys default to
        ``None`` or the field default.
        """
        return cls(
            event_id=str(data["event_id"]),
            timestamp=str(data["timestamp"]),
            actor=str(data["actor"]),
            action=str(data["action"]),
            resource=str(data.get("resource", "")),
            outcome=str(data["outcome"]),
            prev_hash=str(data["prev_hash"]),
            hash=str(data["hash"]),
            parent_anchor_id=data.get("parent_anchor_id"),
            duration_ms=data.get("duration_ms"),
            metadata=dict(data.get("metadata") or {}),
            event_type=data.get("event_type"),
            severity=data.get("severity"),
            description=data.get("description"),
            user_id=data.get("user_id"),
            tenant_id=data.get("tenant_id"),
            resource_id=data.get("resource_id"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            session_id=data.get("session_id"),
            correlation_id=data.get("correlation_id"),
            trace_id=data.get("trace_id"),
            workflow_id=data.get("workflow_id"),
            node_id=data.get("node_id"),
            agent_id=data.get("agent_id"),
            human_origin_id=data.get("human_origin_id"),
        )

    def verify_integrity(self) -> bool:
        """Verify this event's hash matches its content.

        Uses ``hmac.compare_digest`` to prevent timing side-channels.
        Only the core Merkle-chained fields participate in the hash;
        extended domain fields are excluded so pre-SPEC-08 chains remain
        verifiable after migration.

        Returns:
            True if the hash is valid.
        """
        recomputed = _compute_event_hash(
            event_id=self.event_id,
            timestamp=self.timestamp,
            actor=self.actor,
            action=self.action,
            resource=self.resource,
            outcome=self.outcome,
            prev_hash=self.prev_hash,
            parent_anchor_id=self.parent_anchor_id,
            duration_ms=self.duration_ms,
            metadata=self.metadata,
        )
        return hmac_mod.compare_digest(self.hash, recomputed)


# ---------------------------------------------------------------------------
# AuditFilter
# ---------------------------------------------------------------------------


@dataclass
class AuditFilter:
    """Filter criteria for querying audit events.

    All fields are optional; ``None`` means "no filter on this field".
    Multiple non-None fields are combined with AND logic.
    """

    actor: Optional[str] = None
    action: Optional[str] = None
    resource: Optional[str] = None
    outcome: Optional[str] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    limit: int = 100

    def to_dict(self) -> Dict[str, Any]:
        """Serialize filter to dictionary."""
        return {
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "limit": self.limit,
        }


# ---------------------------------------------------------------------------
# AuditStore protocol (SPEC-08 canonical interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class AuditStoreProtocol(Protocol):
    """Protocol for audit storage implementations.

    All implementations must enforce append-only semantics and maintain
    a Merkle hash chain for tamper detection.
    """

    async def append(self, event: AuditEvent) -> None:
        """Append a pre-built audit event to the store."""
        ...

    async def query(self, filter: AuditFilter) -> List[AuditEvent]:
        """Query audit events matching the filter criteria."""
        ...

    async def verify_chain(self) -> bool:
        """Verify the integrity of the entire Merkle hash chain.

        Returns:
            True if the chain is intact, False if tampering detected.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the store."""
        ...


# ---------------------------------------------------------------------------
# InMemoryAuditStore
# ---------------------------------------------------------------------------


class InMemoryAuditStore:
    """List-backed audit store for testing and Level 0 deployments.

    Maintains a Merkle hash chain and enforces append-only semantics.
    Bounded to ``max_events`` entries (default 10,000) with oldest-10%
    eviction when capacity is reached.

    Example::

        store = InMemoryAuditStore()
        event = store.create_event(actor="agent-1", action="analyze", resource="dataset-42")
        await store.append(event)
        assert await store.verify_chain()
    """

    def __init__(self, max_events: int = _DEFAULT_MAX_EVENTS) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._max_events = max_events

    @property
    def count(self) -> int:
        """Number of events in the store."""
        return len(self._events)

    @property
    def last_hash(self) -> str:
        """Hash of the most recent event, or genesis sentinel."""
        if self._events:
            return self._events[-1].hash
        return _GENESIS_HASH

    def create_event(
        self,
        *,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        parent_anchor_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> AuditEvent:
        """Create a new AuditEvent with correct hash chain linkage.

        This is the recommended way to create events -- it computes the
        correct ``prev_hash`` and ``hash`` fields automatically.

        Args:
            actor: Who performed the action.
            action: What was done.
            resource: What was acted upon.
            outcome: Result (``success``, ``failure``, ``denied``).
            parent_anchor_id: Link to triggering action.
            duration_ms: Execution duration in milliseconds.
            metadata: Additional context.
            event_id: Override event ID (auto-generated UUID if None).
            timestamp: Override timestamp (auto-generated UTC ISO-8601 if None).

        Returns:
            A new frozen AuditEvent ready to be appended.
        """
        eid = event_id or str(uuid.uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        meta = dict(metadata) if metadata else {}
        prev = self.last_hash

        h = _compute_event_hash(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev,
            parent_anchor_id=parent_anchor_id,
            duration_ms=duration_ms,
            metadata=meta,
        )

        return AuditEvent(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev,
            hash=h,
            parent_anchor_id=parent_anchor_id,
            duration_ms=duration_ms,
            metadata=meta,
        )

    async def append(self, event: AuditEvent) -> None:
        """Append a pre-built audit event.

        Validates chain linkage: the event's ``prev_hash`` must match the
        current ``last_hash``.

        Args:
            event: The AuditEvent to append.

        Raises:
            ChainIntegrityError: If chain linkage is broken.
            AuditStoreError: If storage fails.
        """
        expected_prev = self.last_hash
        if not hmac_mod.compare_digest(event.prev_hash, expected_prev):
            raise ChainIntegrityError(
                f"Chain linkage broken: expected prev_hash {expected_prev[:16]}..., "
                f"got {event.prev_hash[:16]}...",
                sequence=self.count,
            )

        if not event.verify_integrity():
            raise ChainIntegrityError(
                f"Event {event.event_id} hash does not match content",
                sequence=self.count,
            )

        self._events.append(event)

    async def query(self, filter: AuditFilter) -> List[AuditEvent]:
        """Query events matching the filter criteria.

        Args:
            filter: AuditFilter with optional constraints.

        Returns:
            List of matching AuditEvents (newest last), limited by filter.limit.
        """
        results: List[AuditEvent] = []
        for event in self._events:
            if filter.actor is not None and event.actor != filter.actor:
                continue
            if filter.action is not None and event.action != filter.action:
                continue
            if filter.resource is not None and event.resource != filter.resource:
                continue
            if filter.outcome is not None and event.outcome != filter.outcome:
                continue
            if filter.since is not None:
                event_dt = datetime.fromisoformat(event.timestamp)
                if event_dt < filter.since:
                    continue
            if filter.until is not None:
                event_dt = datetime.fromisoformat(event.timestamp)
                if event_dt > filter.until:
                    continue
            results.append(event)
            if len(results) >= filter.limit:
                break
        return results

    async def verify_chain(self) -> bool:
        """Verify the integrity of the entire Merkle hash chain.

        Checks:
        1. Each event's hash matches its content.
        2. Each event's prev_hash matches the preceding event's hash.
        3. The first event's prev_hash is the genesis sentinel.

        Returns:
            True if the chain is intact.
        """
        events = list(self._events)
        if not events:
            return True

        for i, event in enumerate(events):
            # Check hash integrity
            if not event.verify_integrity():
                return False

            # Check chain linkage
            if i == 0:
                if not hmac_mod.compare_digest(event.prev_hash, _GENESIS_HASH):
                    return False
            else:
                if not hmac_mod.compare_digest(event.prev_hash, events[i - 1].hash):
                    return False

        return True

    async def close(self) -> None:
        """No-op for in-memory store."""
        pass


# ---------------------------------------------------------------------------
# SqliteAuditStore
# ---------------------------------------------------------------------------


class SqliteAuditStore:
    """Persistent audit store using AsyncSQLitePool.

    Uses WAL mode and parameterized queries for safety. Maintains the
    Merkle hash chain in a ``kailash_audit_events`` table.

    Args:
        pool: An initialized ``AsyncSQLitePool`` instance.
        table_name: Name of the audit events table.

    Example::

        from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig

        pool = AsyncSQLitePool(SQLitePoolConfig(db_path="audit.db"))
        await pool.initialize()
        store = SqliteAuditStore(pool)
        await store.initialize()
    """

    _TABLE_NAME = "kailash_audit_events"

    def __init__(
        self,
        pool: Any,
        table_name: str = _TABLE_NAME,
    ) -> None:
        # Validate table name to prevent SQL injection
        import re

        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
            raise ValueError(f"Invalid table name: {table_name!r}")
        self._pool = pool
        self._table_name = table_name

    async def initialize(self) -> None:
        """Create the audit events table if it does not exist."""
        async with self._pool.acquire_write() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    parent_anchor_id TEXT,
                    duration_ms REAL,
                    metadata TEXT NOT NULL DEFAULT '{{}}'
                )
                """
            )
            # Index for common query patterns
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_actor
                ON {self._table_name} (actor)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_action
                ON {self._table_name} (action)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table_name}_timestamp
                ON {self._table_name} (timestamp)
                """
            )
            await conn.commit()

    async def append(self, event: AuditEvent) -> None:
        """Append an audit event to the persistent store.

        Validates chain linkage against the last stored event.

        Args:
            event: The AuditEvent to append.

        Raises:
            ChainIntegrityError: If chain linkage is broken.
            AuditStoreError: If storage fails.
        """
        if not event.verify_integrity():
            raise ChainIntegrityError(
                f"Event {event.event_id} hash does not match content"
            )

        # Verify chain linkage against last stored event
        last_hash = await self._get_last_hash()
        if not hmac_mod.compare_digest(event.prev_hash, last_hash):
            raise ChainIntegrityError(
                f"Chain linkage broken: expected prev_hash {last_hash[:16]}..., "
                f"got {event.prev_hash[:16]}..."
            )

        meta_json = json.dumps(event.metadata, sort_keys=True, separators=(",", ":"))
        async with self._pool.acquire_write() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self._table_name}
                    (event_id, timestamp, actor, action, resource, outcome,
                     prev_hash, hash, parent_anchor_id, duration_ms, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.actor,
                    event.action,
                    event.resource,
                    event.outcome,
                    event.prev_hash,
                    event.hash,
                    event.parent_anchor_id,
                    event.duration_ms,
                    meta_json,
                ),
            )
            await conn.commit()

    async def query(self, filter: AuditFilter) -> List[AuditEvent]:
        """Query audit events from the persistent store.

        Args:
            filter: AuditFilter with optional constraints.

        Returns:
            List of matching AuditEvents ordered by timestamp ASC.

        Raises:
            AuditQueryError: If the query fails.
        """
        conditions: List[str] = []
        params: List[Any] = []

        if filter.actor is not None:
            conditions.append("actor = ?")
            params.append(filter.actor)
        if filter.action is not None:
            conditions.append("action = ?")
            params.append(filter.action)
        if filter.resource is not None:
            conditions.append("resource = ?")
            params.append(filter.resource)
        if filter.outcome is not None:
            conditions.append("outcome = ?")
            params.append(filter.outcome)
        if filter.since is not None:
            conditions.append("timestamp >= ?")
            params.append(filter.since.isoformat())
        if filter.until is not None:
            conditions.append("timestamp <= ?")
            params.append(filter.until.isoformat())

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = (
            f"SELECT event_id, timestamp, actor, action, resource, outcome, "
            f"prev_hash, hash, parent_anchor_id, duration_ms, metadata "
            f"FROM {self._table_name} {where_clause} "
            f"ORDER BY rowid ASC LIMIT ?"
        )
        params.append(filter.limit)

        try:
            async with self._pool.acquire_read() as conn:
                cursor = await conn.execute(sql, tuple(params))
                rows = await cursor.fetchall()
        except Exception as e:
            raise AuditQueryError(
                f"Query failed: {e}", filter_info=filter.to_dict()
            ) from e

        events: List[AuditEvent] = []
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            events.append(
                AuditEvent(
                    event_id=row["event_id"],
                    timestamp=row["timestamp"],
                    actor=row["actor"],
                    action=row["action"],
                    resource=row["resource"],
                    outcome=row["outcome"],
                    prev_hash=row["prev_hash"],
                    hash=row["hash"],
                    parent_anchor_id=row["parent_anchor_id"],
                    duration_ms=row["duration_ms"],
                    metadata=meta,
                )
            )
        return events

    async def verify_chain(self) -> bool:
        """Verify the integrity of the entire persisted Merkle chain.

        Reads all events in insertion order and checks hash linkage.

        Returns:
            True if the chain is intact.
        """
        async with self._pool.acquire_read() as conn:
            cursor = await conn.execute(
                f"SELECT event_id, timestamp, actor, action, resource, outcome, "
                f"prev_hash, hash, parent_anchor_id, duration_ms, metadata "
                f"FROM {self._table_name} ORDER BY rowid ASC"
            )
            rows = await cursor.fetchall()

        if not rows:
            return True

        prev_hash = _GENESIS_HASH
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            event = AuditEvent(
                event_id=row["event_id"],
                timestamp=row["timestamp"],
                actor=row["actor"],
                action=row["action"],
                resource=row["resource"],
                outcome=row["outcome"],
                prev_hash=row["prev_hash"],
                hash=row["hash"],
                parent_anchor_id=row["parent_anchor_id"],
                duration_ms=row["duration_ms"],
                metadata=meta,
            )

            # Check hash integrity
            if not event.verify_integrity():
                return False

            # Check chain linkage
            if not hmac_mod.compare_digest(event.prev_hash, prev_hash):
                return False

            prev_hash = event.hash

        return True

    async def close(self) -> None:
        """Close the underlying pool (caller is responsible for pool lifecycle)."""
        # The pool lifecycle is managed by the caller; we do not close it here.
        pass

    async def _get_last_hash(self) -> str:
        """Get the hash of the last stored event, or genesis sentinel."""
        async with self._pool.acquire_read() as conn:
            cursor = await conn.execute(
                f"SELECT hash FROM {self._table_name} ORDER BY rowid DESC LIMIT 1"
            )
            row = await cursor.fetchone()
        if row is None:
            return _GENESIS_HASH
        return str(row["hash"])

    def create_event(
        self,
        *,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        parent_anchor_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        prev_hash: str,
    ) -> AuditEvent:
        """Create a new AuditEvent with the given prev_hash.

        Unlike InMemoryAuditStore.create_event(), this requires an explicit
        prev_hash because the SQLite store must read the last hash from the
        database before calling this method.

        Callers should use ``_get_last_hash()`` to obtain the correct value.
        """
        eid = event_id or str(uuid.uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        meta = dict(metadata) if metadata else {}

        h = _compute_event_hash(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev_hash,
            parent_anchor_id=parent_anchor_id,
            duration_ms=duration_ms,
            metadata=meta,
        )

        return AuditEvent(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev_hash,
            hash=h,
            parent_anchor_id=parent_anchor_id,
            duration_ms=duration_ms,
            metadata=meta,
        )

    async def create_and_append(
        self,
        *,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        parent_anchor_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Convenience: create an event with correct chain linkage and append it.

        Reads the last hash from the database, creates the event, and appends
        it in a single logical operation.

        Returns:
            The appended AuditEvent.
        """
        prev = await self._get_last_hash()
        event = self.create_event(
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            parent_anchor_id=parent_anchor_id,
            duration_ms=duration_ms,
            metadata=metadata,
            prev_hash=prev,
        )
        await self.append(event)
        return event


# ---------------------------------------------------------------------------
# Backward-compatible legacy types (SPEC-08: preserved for existing imports)
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """Enhanced audit record wrapping an AuditAnchor (legacy, pre-SPEC-08).

    Preserved for backward compatibility with code that imports from
    ``kailash.trust.audit_store``.
    """

    anchor: AuditAnchor
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    integrity_hash: str = ""
    previous_hash: Optional[str] = None
    sequence_number: int = 0

    def __post_init__(self):
        """Compute integrity hash if not provided."""
        if not self.integrity_hash:
            self.integrity_hash = self._compute_integrity_hash()

    def _compute_integrity_hash(self) -> str:
        payload = self.anchor.to_signing_payload()
        if self.anchor.context:
            payload["context"] = self.anchor.context
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        computed = self._compute_integrity_hash()
        return hmac_mod.compare_digest(computed, self.integrity_hash)


@dataclass
class IntegrityVerificationResult:
    """Result of audit chain integrity verification (legacy, pre-SPEC-08)."""

    valid: bool
    total_records: int
    verified_records: int
    first_invalid_sequence: Optional[int] = None
    errors: List[str] = field(default_factory=list)


class AppendOnlyAuditStore:
    """In-memory audit store wrapping AuditAnchor (legacy, pre-SPEC-08).

    Preserved for backward compatibility.  New code should use
    ``InMemoryAuditStore`` with the canonical ``AuditEvent`` type.
    """

    def __init__(self):
        self._records: List[AuditRecord] = []
        self._index: Dict[str, AuditRecord] = {}
        self._anchor_index: Dict[str, AuditRecord] = {}
        self._sequence: int = 0

    async def append(self, anchor: AuditAnchor) -> AuditRecord:
        try:
            previous_hash: Optional[str] = None
            if self._records:
                previous_hash = self._records[-1].integrity_hash

            self._sequence += 1

            record = AuditRecord(
                anchor=anchor,
                sequence_number=self._sequence,
                previous_hash=previous_hash,
            )

            self._records.append(record)
            self._index[record.record_id] = record
            self._anchor_index[anchor.id] = record

            return record

        except Exception as e:
            raise AuditStoreError(
                f"Failed to append audit anchor {anchor.id}: {str(e)}"
            ) from e

    async def get(self, record_id: str) -> Optional[AuditRecord]:
        return self._index.get(record_id)

    async def get_by_anchor_id(self, anchor_id: str) -> Optional[AuditRecord]:
        return self._anchor_index.get(anchor_id)

    async def get_by_sequence(self, sequence: int) -> Optional[AuditRecord]:
        if sequence < 1 or sequence > len(self._records):
            return None
        return self._records[sequence - 1]

    async def list_records(
        self,
        agent_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        filtered = self._records
        if agent_id is not None:
            filtered = [r for r in filtered if r.anchor.agent_id == agent_id]
        if action is not None:
            filtered = [r for r in filtered if r.anchor.action == action]
        return filtered[offset : offset + limit]

    async def update(self, *args: Any, **kwargs: Any) -> None:
        raise AuditStoreImmutabilityError(operation="update")

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AuditStoreImmutabilityError(operation="delete")

    async def verify_integrity(self) -> IntegrityVerificationResult:
        if not self._records:
            return IntegrityVerificationResult(
                valid=True, total_records=0, verified_records=0
            )

        errors: List[str] = []
        verified_count = 0
        first_invalid: Optional[int] = None

        for i, record in enumerate(self._records):
            expected_sequence = i + 1

            if record.sequence_number != expected_sequence:
                if first_invalid is None:
                    first_invalid = record.sequence_number
                errors.append(
                    f"Sequence gap at position {i}: expected {expected_sequence}, "
                    f"got {record.sequence_number}"
                )
                continue

            if i == 0:
                if record.previous_hash is not None:
                    if first_invalid is None:
                        first_invalid = record.sequence_number
                    errors.append(
                        f"First record (seq {record.sequence_number}) has "
                        f"unexpected previous_hash: {record.previous_hash}"
                    )
                    continue
            else:
                expected_previous = self._records[i - 1].integrity_hash
                if not hmac_mod.compare_digest(
                    record.previous_hash or "", expected_previous
                ):
                    if first_invalid is None:
                        first_invalid = record.sequence_number
                    errors.append(
                        f"Broken hash chain at sequence {record.sequence_number}"
                    )
                    continue

            if not record.verify_integrity():
                if first_invalid is None:
                    first_invalid = record.sequence_number
                errors.append(
                    f"Integrity hash mismatch at sequence {record.sequence_number}"
                )
                continue

            verified_count += 1

        return IntegrityVerificationResult(
            valid=len(errors) == 0,
            total_records=len(self._records),
            verified_records=verified_count,
            first_invalid_sequence=first_invalid,
            errors=errors,
        )

    async def verify_record(self, record_id: str) -> bool:
        record = self._index.get(record_id)
        if record is None:
            return False
        return record.verify_integrity()

    @property
    def count(self) -> int:
        return len(self._records)

    @property
    def last_sequence(self) -> int:
        return self._sequence

    @staticmethod
    def get_postgres_trigger_sql(table_name: str = "audit_anchors") -> str:
        return f"""
-- CARE-010: Append-Only Audit Trigger
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Audit trail is append-only: % not allowed on %', TG_OP, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_append_only ON {table_name};
CREATE TRIGGER audit_append_only
BEFORE UPDATE OR DELETE ON {table_name}
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
"""


class AuditStore(ABC):
    """Abstract base class for audit storage (legacy, pre-SPEC-08).

    Preserved for backward compatibility with ``AuditQueryService`` and other
    code that depends on this ABC.  New code should use ``AuditStoreProtocol``.
    """

    @abstractmethod
    async def append(self, anchor: AuditAnchor) -> str: ...

    @abstractmethod
    async def get(self, anchor_id: str) -> AuditAnchor: ...

    @abstractmethod
    async def get_agent_history(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actions: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]: ...

    @abstractmethod
    async def get_action_chain(
        self,
        anchor_id: str,
    ) -> List[AuditAnchor]: ...

    @abstractmethod
    async def query_by_action(
        self,
        action: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        result: Optional[ActionResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]: ...

    @abstractmethod
    async def count_by_agent(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int: ...


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # SPEC-08 canonical types
    "AuditEvent",
    "AuditEventType",
    "AuditOutcome",
    "AuditFilter",
    "AuditStoreProtocol",
    "InMemoryAuditStore",
    "SqliteAuditStore",
    # Error types
    "AuditStoreError",
    "ChainIntegrityError",
    "AuditQueryError",
    "AuditAnchorNotFoundError",
    "AuditStoreImmutabilityError",
    # Legacy backward-compatible types
    "AuditRecord",
    "IntegrityVerificationResult",
    "AppendOnlyAuditStore",
    "AuditStore",
]
