# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EATP audit record translator for L3 governance events.

Converts L3Event instances into EATP-compatible audit record dicts.
Subscribe the translator's ``handle_event`` method to the L3EventBus
to automatically generate audit trail entries for all governance events.

Translation mapping:
    L3Event.event_type  ->  EATP record ``action_type``
    L3Event.agent_id    ->  EATP record ``subject_id``
    L3Event.timestamp   ->  EATP record ``recorded_at``
    L3Event.details     ->  EATP record ``context``

Security:
    - Bounded deque (maxlen=10000) per production-readiness-patterns
    - threading.Lock on all mutable state
    - NaN/Inf sanitized at the L3Event level (see events.py)
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from typing import Any

from kaizen.l3.events import L3Event, L3EventType

__all__ = [
    "EatpTranslator",
]

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RECORDS = 10_000

# Classification of event types for EATP severity mapping.
# Events that indicate policy violations or failures map to higher
# severity levels in the audit record.

_SEVERITY_MAP: dict[str, str] = {
    L3EventType.ENVELOPE_VIOLATION.value: "high",
    L3EventType.AGENT_TERMINATED.value: "medium",
    L3EventType.MESSAGE_DEAD_LETTERED.value: "medium",
    L3EventType.PLAN_NODE_FAILED.value: "medium",
    L3EventType.PLAN_NODE_HELD.value: "medium",
    L3EventType.CONTEXT_ACCESS_DENIED.value: "high",
}

_DEFAULT_SEVERITY = "low"


class EatpTranslator:
    """Translates L3 events into EATP-compatible audit records.

    Subscribe this to the L3EventBus to automatically generate
    audit trail entries for all governance events.

    Usage::

        translator = EatpTranslator()
        bus = L3EventBus()
        bus.subscribe_all(translator.handle_event)

        # Events are now automatically translated and stored:
        bus.emit(L3Event.create(L3EventType.AGENT_SPAWNED, "agent-1"))

        records = translator.get_records()
    """

    def __init__(self, max_records: int = _DEFAULT_MAX_RECORDS) -> None:
        """Initialize the translator.

        Args:
            max_records: Maximum number of audit records to retain.
                Oldest records are evicted when this limit is reached.
                Defaults to 10,000.
        """
        if max_records < 1:
            raise ValueError(f"max_records must be >= 1, got {max_records}")
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._max_records = max_records

    def translate(self, event: L3Event) -> dict[str, Any]:
        """Convert an L3Event to an EATP audit record dict.

        The returned dict follows the EATP audit record schema:
            - record_id: Unique identifier for the audit record
            - action_type: Maps from event_type
            - subject_id: Maps from agent_id
            - recorded_at: Maps from timestamp
            - context: Maps from details
            - severity: Derived from event type classification
            - source: Always "l3_event_bus"

        Args:
            event: The L3Event to translate.

        Returns:
            An EATP-compatible audit record dict.
        """
        return {
            "record_id": str(uuid.uuid4()),
            "action_type": event.event_type,
            "subject_id": event.agent_id,
            "recorded_at": event.timestamp,
            "context": dict(event.details),
            "severity": _SEVERITY_MAP.get(event.event_type, _DEFAULT_SEVERITY),
            "source": "l3_event_bus",
        }

    def handle_event(self, event: L3Event) -> None:
        """Event handler -- translates and stores the audit record.

        This method is designed to be passed directly to
        ``L3EventBus.subscribe()`` or ``L3EventBus.subscribe_all()``.

        Args:
            event: The L3Event to handle.
        """
        record = self.translate(event)
        with self._lock:
            self._records.append(record)
        logger.debug(
            "Translated L3 event %s from agent %s -> audit record %s",
            event.event_type,
            event.agent_id,
            record["record_id"],
        )

    def get_records(self) -> list[dict[str, Any]]:
        """Return all audit records as a list (newest last).

        Returns:
            A copy of all stored audit records.
        """
        with self._lock:
            return list(self._records)

    def get_records_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Return audit records for a specific agent.

        Args:
            agent_id: The agent instance ID to filter by.

        Returns:
            Records matching the agent_id, ordered oldest to newest.
        """
        with self._lock:
            return [r for r in self._records if r["subject_id"] == agent_id]

    def get_records_by_type(
        self, event_type: str | L3EventType
    ) -> list[dict[str, Any]]:
        """Return audit records for a specific event type.

        Args:
            event_type: The event type string or L3EventType to filter by.

        Returns:
            Records matching the event type, ordered oldest to newest.
        """
        key = event_type.value if isinstance(event_type, L3EventType) else event_type
        with self._lock:
            return [r for r in self._records if r["action_type"] == key]

    @property
    def record_count(self) -> int:
        """Number of audit records currently stored."""
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        """Remove all stored records. Useful for test teardown."""
        with self._lock:
            self._records.clear()
