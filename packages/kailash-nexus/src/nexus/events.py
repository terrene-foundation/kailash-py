# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import enum
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

import janus

logger = logging.getLogger(__name__)

__all__ = ["EventBus", "NexusEvent", "NexusEventType"]


class NexusEventType(str, enum.Enum):
    """Types of events in the Nexus event system."""

    HANDLER_REGISTERED = "handler.registered"
    HANDLER_CALLED = "handler.called"
    HANDLER_COMPLETED = "handler.completed"
    HANDLER_ERROR = "handler.error"
    HEALTH_CHECK = "health.check"
    CUSTOM = "custom"


@dataclass
class NexusEvent:
    """A single event in the Nexus event system.

    Mirrors kailash-rs NexusEvent (events/mod.rs).
    """

    event_type: NexusEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: Dict[str, Any] = field(default_factory=dict)
    handler_name: Optional[str] = None
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "handler_name": self.handler_name,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> NexusEvent:
        return cls(
            event_type=NexusEventType(d["event_type"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            data=d.get("data", {}),
            handler_name=d.get("handler_name"),
            request_id=d.get("request_id"),
        )


class EventBus:
    """In-process event bus with cross-thread safety.

    Uses janus.Queue to bridge sync publishers (MCP thread) and async
    consumers (main event loop). Bounded buffer (capacity=256) prevents
    memory exhaustion in long-running processes.

    Lifecycle:
        bus = EventBus(capacity=256)
        # publish() works immediately (no running loop needed)
        bus.publish(event)
        # start() begins the async dispatch loop
        await bus.start()
        # subscribe() returns queue for consumers
        queue = bus.subscribe()
        # stop() shuts down cleanly
        await bus.stop()
    """

    def __init__(self, capacity: int = 256):
        self._capacity = capacity
        self._janus_queue: Optional[janus.Queue] = None
        self._subscribers: List[asyncio.Queue] = []
        self._filtered_subscribers: List[
            tuple[Callable[[NexusEvent], bool], asyncio.Queue]
        ] = []
        self._history: deque[NexusEvent] = deque(maxlen=capacity)
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None

    def _ensure_queue(self) -> janus.Queue:
        """Lazily create the janus.Queue.

        janus.Queue requires a running event loop at creation time (janus>=1.0).
        We defer creation until first publish() or start() call.
        """
        if self._janus_queue is None:
            try:
                self._janus_queue = janus.Queue(maxsize=self._capacity)
            except RuntimeError:
                # No running event loop — queue will be created in start()
                return None
        return self._janus_queue

    def publish(self, event: NexusEvent) -> None:
        """Publish an event (non-blocking, thread-safe).

        Can be called from any thread. Uses the janus sync queue.
        If the queue is full, drops the oldest event.
        If no event loop is running yet, events are stored directly in history.
        """
        q = self._ensure_queue()
        if q is None:
            # No event loop yet — store directly in history
            self._history.append(event)
            return

        sync_q = q.sync_q
        if sync_q.full():
            try:
                sync_q.get_nowait()  # Drop oldest to make room
            except Exception:
                pass
        try:
            sync_q.put_nowait(event)
        except Exception:
            # Fallback: store in history directly
            self._history.append(event)
            logger.debug("EventBus: failed to enqueue event (queue issue)")

    def publish_handler_registered(self, name: str, handler_def=None) -> None:
        """Convenience: publish a HANDLER_REGISTERED event."""
        self.publish(
            NexusEvent(
                event_type=NexusEventType.HANDLER_REGISTERED,
                handler_name=name,
                data={"handler_name": name},
            )
        )

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to all events. Returns an asyncio.Queue.

        Events are delivered to subscribers during the dispatch loop
        (after start() is called). Subscribing before start() is fine;
        events will begin flowing once the loop starts.
        """
        q: asyncio.Queue[NexusEvent] = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def subscribe_filtered(
        self, predicate: Callable[[NexusEvent], bool]
    ) -> asyncio.Queue:
        """Subscribe to events matching a predicate.

        Args:
            predicate: Function that returns True for events to receive.

        Returns:
            asyncio.Queue that receives only matching events.
        """
        q: asyncio.Queue[NexusEvent] = asyncio.Queue(maxsize=256)
        self._filtered_subscribers.append((predicate, q))
        return q

    @property
    def subscriber_count(self) -> int:
        """Total number of active subscribers."""
        return len(self._subscribers) + len(self._filtered_subscribers)

    @staticmethod
    def sse_url() -> str:
        """Return the SSE streaming endpoint path.

        Matches the kailash-rs ``EventBus::sse_url()`` interface.
        """
        return "/events/stream"

    def get_history(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read event history from the internal bounded deque.

        Backward-compatible with the old get_events() signature.
        Returns dicts in the same format as the old _event_log entries.
        """
        events = list(self._history)

        if session_id:
            events = [e for e in events if e.data.get("session_id") == session_id]

        if event_type:
            events = [
                e
                for e in events
                if e.event_type.value == event_type or e.data.get("type") == event_type
            ]

        if limit:
            events = list(reversed(events))[:limit]
            events = list(reversed(events))

        # Convert to legacy dict format for backward compat
        return [self._event_to_legacy_dict(e) for e in events]

    async def start(self) -> None:
        """Start the async dispatch loop."""
        if self._running:
            return
        # Ensure queue exists now that we have an event loop
        if self._janus_queue is None:
            self._janus_queue = janus.Queue(maxsize=self._capacity)
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.debug("EventBus started")

    async def stop(self) -> None:
        """Stop the dispatch loop and close the janus queue."""
        self._running = False
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None
        if self._janus_queue is not None:
            self._janus_queue.close()
            await self._janus_queue.wait_closed()
            self._janus_queue = None
        logger.debug("EventBus stopped")

    async def _dispatch_loop(self) -> None:
        """Read from janus async queue and fan out to subscribers."""
        async_q = self._janus_queue.async_q
        while self._running:
            try:
                event = await asyncio.wait_for(async_q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Store in history deque
            self._history.append(event)

            # Fan out to all subscribers
            for sub_q in self._subscribers:
                try:
                    sub_q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Lagging subscriber — drop oldest semantics

            # Fan out to filtered subscribers
            for predicate, sub_q in self._filtered_subscribers:
                try:
                    if predicate(event):
                        sub_q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
                except Exception:
                    pass  # Predicate failure — skip

    @staticmethod
    def _event_to_legacy_dict(event: NexusEvent) -> Dict[str, Any]:
        """Convert NexusEvent to legacy _event_log dict format."""
        return {
            "id": f"evt_{int(event.timestamp.timestamp() * 1000)}",
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "session_id": event.data.get("session_id"),
        }
