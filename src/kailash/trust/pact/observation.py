# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structured observation emission protocol for PACT governance monitoring.

Distinct from PactEatpEmitter (which emits EATP chain records for compliance
and lineage), ObservationSink emits structured monitoring events -- real-time
signals for dashboards, alerts, and external monitoring systems.

GovernanceEngine calls ObservationSink.emit() at 4 key decision points:
1. After every verify_action() verdict
2. After every envelope mutation (set_role_envelope / set_task_envelope)
3. After every clearance change (grant / revoke)
4. After every bridge event (approve / create / reject)

Emission is non-blocking: exceptions are logged but never re-raised.

See: PACT conformance N5 (GH #384).
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "InMemoryObservationSink",
    "Observation",
    "ObservationSink",
]


@dataclass(frozen=True)
class Observation:
    """A structured governance observation event.

    Immutable record of a governance event emitted by GovernanceEngine
    for external monitoring, dashboards, and alerting.

    Attributes:
        event_type: Category of the event. One of:
            "verdict" -- result of verify_action()
            "envelope_change" -- role or task envelope mutation
            "clearance_change" -- clearance grant, revoke, or transition
            "bridge_event" -- bridge approval, creation, or rejection
        role_address: The D/T/R address of the primary role involved.
        timestamp: ISO 8601 timestamp of when the event occurred.
        level: Severity level for monitoring. One of:
            "info" -- normal operation (auto_approved, grants)
            "warn" -- near-boundary (flagged, held verdicts)
            "critical" -- blocked actions, revocations
        payload: Structured event-specific data. Contents vary by event_type.
        correlation_id: Optional cross-event tracing identifier. Allows
            correlating related events (e.g., a clearance change that
            triggers envelope re-evaluation).
        observation_id: Unique identifier for this observation. Auto-generated
            as a hex UUID if not provided.
    """

    event_type: str
    role_address: str
    timestamp: str
    level: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    observation_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary.

        Returns:
            Dict with all fields. Suitable for JSON serialization.
        """
        return {
            "event_type": self.event_type,
            "role_address": self.role_address,
            "timestamp": self.timestamp,
            "level": self.level,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "observation_id": self.observation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized Observation fields.

        Returns:
            An Observation instance.
        """
        return cls(
            event_type=data["event_type"],
            role_address=data["role_address"],
            timestamp=data["timestamp"],
            level=data["level"],
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id"),
            observation_id=data.get("observation_id", uuid.uuid4().hex),
        )


@runtime_checkable
class ObservationSink(Protocol):
    """Protocol for receiving structured governance observations.

    Implementations may forward to monitoring systems, buffer for batch
    processing, or collect for testing/inspection.

    GovernanceEngine calls emit() OUTSIDE its lock (same pattern as
    _emit_audit), so implementations must be independently thread-safe
    if shared across threads.
    """

    def emit(self, observation: Observation) -> None:
        """Emit a governance observation.

        Must be non-blocking: implementations should handle errors
        internally and never propagate exceptions to the caller.

        Args:
            observation: The observation to emit.
        """
        ...


class InMemoryObservationSink:
    """Default implementation that collects observations in a bounded deque.

    Thread-safe: deque with maxlen is atomic for append on CPython (GIL).
    For non-CPython runtimes, wrap in a threading.Lock.

    Args:
        maxlen: Maximum number of observations to retain. Oldest are
            evicted when the limit is reached (FIFO). Default: 10,000
            per trust-plane-security bounded-collection rule.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._observations: deque[Observation] = deque(maxlen=maxlen)

    def emit(self, observation: Observation) -> None:
        """Append an observation to the bounded deque.

        Args:
            observation: The observation to store.
        """
        self._observations.append(observation)

    @property
    def observations(self) -> list[Observation]:
        """Return a snapshot of all stored observations.

        Returns:
            List of observations in chronological order.
        """
        return list(self._observations)

    def clear(self) -> None:
        """Remove all stored observations."""
        self._observations.clear()

    def __len__(self) -> int:
        """Return the number of stored observations."""
        return len(self._observations)
