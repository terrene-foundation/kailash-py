# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 governance event types for EATP audit trail integration.

Defines the canonical event types emitted by L3 autonomy primitives
(envelope enforcement, agent lifecycle, messaging, plan execution,
context scoping). These events are consumed by translators that convert
them into EATP audit records.

All event types are frozen dataclasses per AD-L3-15 (value types).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "L3Event",
    "L3EventType",
]

logger = logging.getLogger(__name__)


class L3EventType(str, Enum):
    """Canonical L3 governance event types.

    These map to the five L3 primitive categories:

    Envelope (Spec 01):
        ENVELOPE_VIOLATION, ENVELOPE_REGISTERED, ENVELOPE_SPLIT

    Factory (Spec 04):
        AGENT_SPAWNED, AGENT_TERMINATED, AGENT_STATE_CHANGED

    Messaging (Spec 03):
        MESSAGE_ROUTED, MESSAGE_DEAD_LETTERED

    Plan (Spec 05):
        PLAN_VALIDATED, PLAN_EXECUTED, PLAN_NODE_COMPLETED,
        PLAN_NODE_FAILED, PLAN_NODE_HELD

    Context (Spec 02):
        CONTEXT_SCOPE_CREATED, CONTEXT_ACCESS_DENIED
    """

    # Envelope events (Spec 01)
    ENVELOPE_VIOLATION = "envelope_violation"
    ENVELOPE_REGISTERED = "envelope_registered"
    ENVELOPE_SPLIT = "envelope_split"

    # Factory events (Spec 04)
    AGENT_SPAWNED = "agent_spawned"
    AGENT_TERMINATED = "agent_terminated"
    AGENT_STATE_CHANGED = "agent_state_changed"

    # Messaging events (Spec 03)
    MESSAGE_ROUTED = "message_routed"
    MESSAGE_DEAD_LETTERED = "message_dead_lettered"

    # Plan events (Spec 05)
    PLAN_VALIDATED = "plan_validated"
    PLAN_EXECUTED = "plan_executed"
    PLAN_NODE_COMPLETED = "plan_node_completed"
    PLAN_NODE_FAILED = "plan_node_failed"
    PLAN_NODE_HELD = "plan_node_held"

    # Context events (Spec 02)
    CONTEXT_SCOPE_CREATED = "context_scope_created"
    CONTEXT_ACCESS_DENIED = "context_access_denied"


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Sanitize event detail values to prevent NaN/Inf corruption.

    Replaces non-finite float values with a string sentinel and logs a
    warning. This ensures audit records never contain values that would
    poison downstream numeric comparisons.

    Args:
        details: Raw event details dict.

    Returns:
        Sanitized copy with non-finite floats replaced.
    """
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        if isinstance(value, float) and not math.isfinite(value):
            logger.warning(
                "Non-finite value in event details: key=%r value=%r — replaced with sentinel",
                key,
                value,
            )
            sanitized[key] = f"<non-finite:{value!r}>"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_details(value)
        else:
            sanitized[key] = value
    return sanitized


@dataclass(frozen=True)
class L3Event:
    """Base L3 governance event.

    All L3 primitives emit events through this type. The event bus
    dispatches these to registered listeners (including the EATP
    translator for audit trail integration).

    Attributes:
        event_type: Canonical event type from L3EventType.
        agent_id: The agent instance ID that caused the event.
        timestamp: ISO 8601 timestamp of when the event occurred.
        details: Structured event-specific data (sanitized on creation).
    """

    event_type: str
    agent_id: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate fields and sanitize details."""
        if not self.event_type:
            raise ValueError("event_type must not be empty")
        if not self.agent_id:
            raise ValueError("agent_id must not be empty")
        if not self.timestamp:
            raise ValueError("timestamp must not be empty")
        # Sanitize details to prevent NaN/Inf propagation.
        # We use object.__setattr__ because the dataclass is frozen.
        sanitized = _sanitize_details(self.details)
        object.__setattr__(self, "details", sanitized)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for transport/storage."""
        return {
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> L3Event:
        """Deserialize from dict."""
        return cls(
            event_type=data["event_type"],
            agent_id=data["agent_id"],
            timestamp=data["timestamp"],
            details=data.get("details", {}),
        )

    @classmethod
    def create(
        cls,
        event_type: L3EventType,
        agent_id: str,
        details: dict[str, Any] | None = None,
    ) -> L3Event:
        """Factory method with auto-generated ISO 8601 timestamp.

        Args:
            event_type: The L3EventType enum member.
            agent_id: Agent instance ID.
            details: Optional event-specific data.

        Returns:
            A new L3Event with the current UTC timestamp.
        """
        return cls(
            event_type=event_type.value,
            agent_id=agent_id,
            timestamp=datetime.now(UTC).isoformat(),
            details=details or {},
        )
