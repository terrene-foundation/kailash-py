# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""WebSocket event types for governance decisions.

Defines the platform event infrastructure (EventType, PlatformEvent, EventBus)
locally and extends it with governance-specific event types:

- ACCESS_CHECKED -- result of a check-access evaluation
- ACTION_VERIFIED -- result of a verify-action evaluation
- CLEARANCE_GRANTED -- clearance granted to a role
- CLEARANCE_REVOKED -- clearance revoked from a role
- BRIDGE_CREATED -- Cross-Functional Bridge established
- KSP_CREATED -- Knowledge Share Policy created
- ENVELOPE_SET -- role or task envelope configured

These events are emitted by the governance API endpoints when mutations
occur, enabling real-time dashboard updates via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any
from uuid import uuid4

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone

    UTC = timezone.utc

from datetime import datetime

logger = logging.getLogger(__name__)

__all__ = [
    "EventType",
    "PlatformEvent",
    "EventBus",
    "event_bus",
    "GovernanceEventType",
    "emit_governance_event",
]


# ---------------------------------------------------------------------------
# Platform event types (local definitions, no pact.use dependency)
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Types of real-time events the platform can emit."""

    AUDIT_ANCHOR = "audit_anchor"
    HELD_ACTION = "held_action"
    POSTURE_CHANGE = "posture_change"
    BRIDGE_STATUS = "bridge_status"
    VERIFICATION_RESULT = "verification_result"
    WORKSPACE_TRANSITION = "workspace_transition"


class PlatformEvent:
    """A single event emitted by the platform.

    Args:
        event_type: The category of event.
        data: JSON-serializable payload.
        source_agent_id: Optional originating agent identifier.
        source_team_id: Optional originating team identifier.
    """

    def __init__(
        self,
        event_type: EventType,
        data: dict[str, Any],
        *,
        source_agent_id: str = "",
        source_team_id: str = "",
    ) -> None:
        self.event_id: str = f"evt-{uuid4().hex[:8]}"
        self.event_type: EventType = event_type
        self.data: dict[str, Any] = data
        self.timestamp: str = datetime.now(UTC).isoformat()
        self.source_agent_id: str = source_agent_id
        self.source_team_id: str = source_team_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a plain dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source_agent_id": self.source_agent_id,
            "source_team_id": self.source_team_id,
        }

    def to_json(self) -> str:
        """Serialize the event to a JSON string."""
        return json.dumps(self.to_dict())


class EventBus:
    """Async event bus with bounded subscriber list.

    Args:
        max_subscribers: Upper limit on concurrent subscribers (default 100).
    """

    _QUEUE_MAXSIZE = 1000

    def __init__(self, max_subscribers: int = 100) -> None:
        self._max_subscribers: int = max_subscribers
        self._subscribers: list[asyncio.Queue[PlatformEvent]] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[PlatformEvent]:
        """Create a new subscriber queue.

        Returns:
            An asyncio.Queue that will receive published events.

        Raises:
            RuntimeError: If the maximum subscriber count is reached.
        """
        async with self._lock:
            if len(self._subscribers) >= self._max_subscribers:
                raise RuntimeError(
                    f"EventBus subscriber limit reached ({self._max_subscribers})"
                )
            queue: asyncio.Queue[PlatformEvent] = asyncio.Queue(
                maxsize=self._QUEUE_MAXSIZE,
            )
            self._subscribers.append(queue)
            return queue

    async def unsubscribe(self, queue: asyncio.Queue[PlatformEvent]) -> None:
        """Remove a subscriber queue.

        Args:
            queue: The queue previously returned by :meth:`subscribe`.
        """
        async with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass  # Already removed — idempotent

    async def publish(self, event: PlatformEvent) -> int:
        """Publish an event to all subscribers.

        Events are delivered on a best-effort basis: if a subscriber queue
        is full the event is dropped for that subscriber (back-pressure).

        Args:
            event: The event to broadcast.

        Returns:
            The number of subscribers that received the event.
        """
        notified = 0
        async with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                    notified += 1
                except asyncio.QueueFull:
                    logger.warning(
                        "Dropping event %s for a subscriber (queue full)",
                        event.event_id,
                    )
        return notified

    @property
    def subscriber_count(self) -> int:
        """Return the current number of subscribers."""
        return len(self._subscribers)

    # -- Convenience emitters ------------------------------------------------

    async def emit_audit_anchor(self, data: dict[str, Any]) -> int:
        """Emit an AUDIT_ANCHOR event."""
        return await self.publish(PlatformEvent(EventType.AUDIT_ANCHOR, data))

    async def emit_held_action(self, data: dict[str, Any]) -> int:
        """Emit a HELD_ACTION event."""
        return await self.publish(PlatformEvent(EventType.HELD_ACTION, data))

    async def emit_posture_change(self, data: dict[str, Any]) -> int:
        """Emit a POSTURE_CHANGE event."""
        return await self.publish(PlatformEvent(EventType.POSTURE_CHANGE, data))


# Module-level singleton
event_bus = EventBus()


# ---------------------------------------------------------------------------
# Governance-specific event types
# ---------------------------------------------------------------------------


class GovernanceEventType(str, Enum):
    """Event types specific to governance operations."""

    ACCESS_CHECKED = "governance.access_checked"
    ACTION_VERIFIED = "governance.action_verified"
    CLEARANCE_GRANTED = "governance.clearance_granted"
    CLEARANCE_REVOKED = "governance.clearance_revoked"
    BRIDGE_CREATED = "governance.bridge_created"
    KSP_CREATED = "governance.ksp_created"
    ENVELOPE_SET = "governance.envelope_set"


async def emit_governance_event(
    event_type: GovernanceEventType,
    data: dict[str, Any],
    *,
    source_role_address: str = "",
) -> PlatformEvent | None:
    """Emit a governance event to the platform EventBus.

    Creates a PlatformEvent with EventType.VERIFICATION_RESULT (the closest
    existing platform event type for governance decisions) and attaches
    the governance-specific event type in the data payload.

    Args:
        event_type: The governance-specific event type.
        data: Event payload (must be JSON-serializable).
        source_role_address: Optional role that triggered the event.

    Returns:
        The emitted PlatformEvent, or None if emission failed.
    """
    try:
        enriched_data = {
            "governance_event_type": event_type.value,
            **data,
        }
        event = PlatformEvent(
            EventType.VERIFICATION_RESULT,
            enriched_data,
            source_agent_id=source_role_address,
        )
        await event_bus.publish(event)
        logger.debug(
            "Emitted governance event: type=%s role=%s",
            event_type.value,
            source_role_address,
        )
        return event
    except Exception:
        logger.exception(
            "Failed to emit governance event: type=%s -- continuing without event",
            event_type.value,
        )
        return None
