"""EATP-Compliant Audit Generation for Kailash Runtime (CARE-018).

This module provides audit trail generation for workflow execution, bridging
to Kaizen's AuditStore when available. It enables compliance with the
Enterprise Agent Trust Protocol (EATP) audit requirements.

Design Principles:
    - Audit failures MUST NOT break workflow execution (all wrapped in try/except)
    - No hard dependency on Kaizen (use TYPE_CHECKING for type annotations)
    - Default disabled for backward compatibility
    - All methods async for consistency with trust verification flow
    - Events stored in-memory with optional persistence to Kaizen AuditStore

SPEC-08 consolidation (2026-04): ``AuditEvent`` and ``AuditEventType`` are
re-exported from the canonical single source of truth at
``kailash.trust.audit_store``.  This module owns only the workflow-lifecycle
audit GENERATOR; the event types themselves live in the trust plane.

Usage:
    from kailash.runtime.trust.audit import (
        AuditEventType,
        AuditEvent,
        RuntimeAuditGenerator,
    )

    # Create generator (optionally with Kaizen store)
    generator = RuntimeAuditGenerator(
        audit_store=kaizen_audit_store,  # Optional
        enabled=True,
        log_to_stdout=False,
    )

    # Record events during workflow execution
    trust_ctx = RuntimeTrustContext(trace_id="trace-123")
    await generator.workflow_started("run-1", "my-workflow", trust_ctx)
    await generator.node_executed("run-1", "node-1", "HttpRequest", 150, trust_ctx)
    await generator.workflow_completed("run-1", 500, trust_ctx)

    # Query events
    events = generator.get_events()
    events_by_type = generator.get_events_by_type(AuditEventType.NODE_END)

Version:
    Added in: v0.11.0
    Part of: CARE trust implementation (Phase 2)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

# SPEC-08: canonical AuditEvent lives in kailash.trust.audit_store.
# We re-export AuditEvent and AuditEventType here for backward compatibility
# with existing imports from ``kailash.runtime.trust.audit``.
from kailash.trust.audit_store import AuditEvent, AuditEventType

if TYPE_CHECKING:
    from kailash.runtime.trust.context import RuntimeTrustContext

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64
"""Sentinel previous-hash for generator-built events that are not part of a chain."""


def _generate_event_id() -> str:
    """Generate a unique event ID.

    Format: evt-{12 hex characters from UUID}

    Returns:
        Unique event identifier
    """
    return f"evt-{uuid4().hex[:12]}"


def _get_utc_now_iso() -> str:
    """Get current UTC datetime as ISO-8601 string.

    The canonical ``AuditEvent.timestamp`` is a string for deterministic
    hashing across platforms.
    """
    return datetime.now(UTC).isoformat()


def _build_runtime_event(
    *,
    event_id: str,
    event_type: AuditEventType,
    timestamp: str,
    trace_id: str,
    result: str,
    workflow_id: Optional[str] = None,
    node_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    human_origin_id: Optional[str] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """Build a canonical ``AuditEvent`` for runtime workflow audit.

    Generator-built events are standalone observation records, NOT part
    of a Merkle chain — ``prev_hash`` is the genesis sentinel and ``hash``
    is a deterministic digest of the non-chain fields.  The trust-plane
    ``InMemoryAuditStore`` / ``SqliteAuditStore`` maintain the real chain
    when these events are persisted.
    """
    meta = dict(context) if context else {}
    # The canonical AuditEvent expects ``actor`` and ``action`` as strings
    # and ``outcome`` to distinguish success/failure/denied.  We map
    # workflow-runtime semantics onto those fields.
    actor = agent_id or human_origin_id or "runtime"
    action_str = action or event_type.value
    resource_str = resource or ""

    payload = {
        "event_id": event_id,
        "timestamp": timestamp,
        "actor": actor,
        "action": action_str,
        "resource": resource_str,
        "outcome": result,
        "prev_hash": _GENESIS_HASH,
        "parent_anchor_id": None,
        "duration_ms": None,
        "metadata": meta,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return AuditEvent(
        event_id=event_id,
        timestamp=timestamp,
        actor=actor,
        action=action_str,
        resource=resource_str,
        outcome=result,
        prev_hash=_GENESIS_HASH,
        hash=event_hash,
        metadata=meta,
        event_type=event_type.value,
        trace_id=trace_id,
        workflow_id=workflow_id,
        node_id=node_id,
        agent_id=agent_id,
        human_origin_id=human_origin_id,
    )


class RuntimeAuditGenerator:
    """Audit trail generator for runtime workflow execution.

    Generates EATP-compliant audit events for workflow and node execution,
    with optional persistence to Kaizen AuditStore.

    Features:
        - In-memory event storage for queries
        - Optional Kaizen AuditStore integration
        - Optional stdout logging
        - Extraction of trust context fields

    Example:
        >>> generator = RuntimeAuditGenerator(enabled=True)
        >>> trust_ctx = RuntimeTrustContext(trace_id="trace-123")
        >>> await generator.workflow_started("run-1", "wf-1", trust_ctx)
        >>> events = generator.get_events()
    """

    def __init__(
        self,
        audit_store: Optional[Any] = None,
        enabled: bool = True,
        log_to_stdout: bool = False,
    ) -> None:
        """Initialize the RuntimeAuditGenerator.

        Args:
            audit_store: Optional Kaizen AuditStore for persistence
            enabled: Whether audit generation is enabled (default True)
            log_to_stdout: Whether to log events to stdout (default False)
        """
        self._audit_store = audit_store
        self._enabled = enabled
        self._log_to_stdout = log_to_stdout
        self._events: List[AuditEvent] = []
        # ROUND7-002: Thread-safe access to _events list
        self._lock = threading.Lock()

    def _extract_agent_id(
        self, trust_context: Optional["RuntimeTrustContext"]
    ) -> Optional[str]:
        """Extract agent ID from trust context (last in delegation chain).

        Args:
            trust_context: RuntimeTrustContext to extract from

        Returns:
            Agent ID or None if not available
        """
        if trust_context is None:
            return None
        if not trust_context.delegation_chain:
            return None
        return trust_context.delegation_chain[-1]

    def _extract_human_origin_id(
        self, trust_context: Optional["RuntimeTrustContext"]
    ) -> Optional[str]:
        """Extract human origin ID from trust context.

        Args:
            trust_context: RuntimeTrustContext to extract from

        Returns:
            Human origin ID or None if not available
        """
        if trust_context is None:
            return None
        if trust_context.human_origin is None:
            return None

        # Try to get 'id' attribute or key
        if hasattr(trust_context.human_origin, "id"):
            return trust_context.human_origin.id
        if isinstance(trust_context.human_origin, dict):
            return trust_context.human_origin.get("id")

        return None

    async def _record_event(self, event: AuditEvent) -> None:
        """Record an event internally and optionally persist.

        Args:
            event: The AuditEvent to record

        Note:
            This method NEVER raises exceptions. All errors are caught
            and logged to prevent audit failures from breaking workflow execution.
        """
        try:
            # ROUND7-002: Thread-safe event recording
            with self._lock:
                self._events.append(event)

            # Log to stdout if enabled
            if self._log_to_stdout:
                logger.info(
                    "AUDIT: %s trace=%s result=%s",
                    event.event_type or "unknown",
                    event.trace_id,
                    event.outcome,
                )

            # Persist to Kaizen store if available
            if self._audit_store is not None:
                await self._persist_to_kaizen(event)

        except Exception as e:
            # Never let audit failures break workflow
            logger.warning("Failed to record audit event: %s", e)

    async def _persist_to_kaizen(self, event: AuditEvent) -> None:
        """Persist event to Kaizen AuditStore.

        Converts AuditEvent to a dict format compatible with Kaizen's
        AuditAnchor structure and calls store.append().

        Args:
            event: The AuditEvent to persist

        Note:
            This method NEVER raises exceptions. All errors are caught
            and logged.
        """
        if self._audit_store is None:
            return

        try:
            # Create anchor-like dict for Kaizen store
            anchor_dict = {
                "id": event.event_id,
                "agent_id": event.agent_id or "unknown",
                "action": event.action or event.event_type or "unknown",
                "timestamp": event.timestamp,
                "result": event.outcome,
                "resource": event.resource,
                "context": dict(event.metadata),
                "trace_id": event.trace_id,
                "human_origin_id": event.human_origin_id,
            }

            await self._audit_store.append(anchor_dict)

        except Exception as e:
            # Never let persistence failures break workflow
            logger.warning("Failed to persist audit event to Kaizen store: %s", e)

    async def workflow_started(
        self,
        run_id: str,
        workflow_name: str,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record workflow start event.

        Args:
            run_id: Unique run identifier
            workflow_name: Name of the workflow
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="workflow_started",
            result="success",
            context={"workflow_name": workflow_name},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def workflow_completed(
        self,
        run_id: str,
        duration_ms: int,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record workflow completion event.

        Args:
            run_id: Unique run identifier
            duration_ms: Execution duration in milliseconds
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.WORKFLOW_END,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="workflow_completed",
            result="success",
            context={"duration_ms": duration_ms},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def workflow_failed(
        self,
        run_id: str,
        error: str,
        duration_ms: int,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record workflow failure event.

        Args:
            run_id: Unique run identifier
            error: Error message or description
            duration_ms: Execution duration in milliseconds
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.WORKFLOW_ERROR,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="workflow_failed",
            result="failure",
            context={"error": error, "duration_ms": duration_ms},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def node_executed(
        self,
        run_id: str,
        node_id: str,
        node_type: str,
        duration_ms: int,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record successful node execution event.

        Args:
            run_id: Unique run identifier
            node_id: Node instance ID
            node_type: Type of node executed
            duration_ms: Execution duration in milliseconds
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.NODE_END,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            node_id=node_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="node_executed",
            result="success",
            context={"node_type": node_type, "duration_ms": duration_ms},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def node_failed(
        self,
        run_id: str,
        node_id: str,
        node_type: str,
        error: str,
        duration_ms: int,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record node failure event.

        Args:
            run_id: Unique run identifier
            node_id: Node instance ID
            node_type: Type of node that failed
            error: Error message or description
            duration_ms: Execution duration in milliseconds
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.NODE_ERROR,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            node_id=node_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="node_failed",
            result="failure",
            context={
                "node_type": node_type,
                "error": error,
                "duration_ms": duration_ms,
            },
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def trust_verification_performed(
        self,
        run_id: str,
        target: str,
        allowed: bool,
        reason: str,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record trust verification event.

        Args:
            run_id: Unique run identifier
            target: What was verified (e.g., "workflow:name" or "node:type:id")
            allowed: Whether the verification allowed the operation
            reason: Reason for the verification result
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event_type = (
            AuditEventType.TRUST_VERIFICATION
            if allowed
            else AuditEventType.TRUST_DENIED
        )
        result = "success" if allowed else "denied"

        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=event_type,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action="trust_verification",
            result=result,
            context={"target": target, "allowed": allowed, "reason": reason},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    async def resource_accessed(
        self,
        run_id: str,
        resource: str,
        action: str,
        result: str,
        trust_context: Optional["RuntimeTrustContext"],
    ) -> AuditEvent:
        """Record resource access event.

        Args:
            run_id: Unique run identifier
            resource: Resource path or identifier
            action: Action performed (e.g., "read", "write")
            result: Result of access ("success", "failure", "denied")
            trust_context: RuntimeTrustContext for trust information

        Returns:
            The created AuditEvent
        """
        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.RESOURCE_ACCESS,
            timestamp=_get_utc_now_iso(),
            trace_id=trust_context.trace_id if trust_context else run_id,
            workflow_id=run_id,
            agent_id=self._extract_agent_id(trust_context),
            human_origin_id=self._extract_human_origin_id(trust_context),
            action=action,
            resource=resource,
            result=result,
            context={},
        )

        if self._enabled:
            await self._record_event(event)

        return event

    def get_events(self) -> List[AuditEvent]:
        """Get all recorded events.

        Returns:
            List of all AuditEvents in chronological order
        """
        # ROUND7-002: Thread-safe event access
        with self._lock:
            return list(self._events)

    def get_events_by_type(self, event_type: AuditEventType) -> List[AuditEvent]:
        """Get events filtered by type.

        Args:
            event_type: Type of events to retrieve

        Returns:
            List of matching AuditEvents
        """
        # ROUND7-002: Thread-safe event access
        # Canonical AuditEvent stores event_type as a string (.value),
        # so compare against the enum's string value.
        type_value = event_type.value
        with self._lock:
            return [e for e in self._events if e.event_type == type_value]

    def get_events_by_trace(self, trace_id: str) -> List[AuditEvent]:
        """Get events filtered by trace ID.

        Args:
            trace_id: Trace ID to filter by

        Returns:
            List of matching AuditEvents
        """
        # ROUND7-002: Thread-safe event access
        with self._lock:
            return [e for e in self._events if e.trace_id == trace_id]

    def clear_events(self) -> None:
        """Clear all recorded events.

        Removes all events from in-memory storage. Does not affect
        events already persisted to Kaizen store.
        """
        # ROUND7-002: Thread-safe event clear
        with self._lock:
            self._events.clear()
