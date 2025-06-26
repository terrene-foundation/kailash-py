"""Event store for request audit trail and event sourcing.

This module provides:
- Append-only event log
- Event replay capability
- Event projections
- Audit trail for compliance
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Standard event types for request lifecycle."""

    REQUEST_CREATED = "request.created"
    REQUEST_VALIDATED = "request.validated"
    REQUEST_STARTED = "request.started"
    REQUEST_CHECKPOINTED = "request.checkpointed"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"
    REQUEST_CANCELLED = "request.cancelled"
    REQUEST_RESUMED = "request.resumed"
    REQUEST_RETRIED = "request.retried"

    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_NODE_STARTED = "workflow.node.started"
    WORKFLOW_NODE_COMPLETED = "workflow.node.completed"
    WORKFLOW_NODE_FAILED = "workflow.node.failed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    DEDUPLICATION_HIT = "deduplication.hit"
    DEDUPLICATION_MISS = "deduplication.miss"

    ERROR_OCCURRED = "error.occurred"
    ERROR_HANDLED = "error.handled"


@dataclass
class RequestEvent:
    """Immutable event in the request lifecycle."""

    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    event_type: EventType = EventType.REQUEST_CREATED
    request_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    sequence_number: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "sequence_number": self.sequence_number,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequestEvent":
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            request_id=data["request_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            sequence_number=data["sequence_number"],
            data=data["data"],
            metadata=data.get("metadata", {}),
        )


class EventStore:
    """Append-only event store with replay capability."""

    def __init__(
        self,
        storage_backend: Optional[Any] = None,
        batch_size: int = 100,
        flush_interval_seconds: float = 1.0,
    ):
        """Initialize event store."""
        self.storage_backend = storage_backend
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds

        # In-memory buffer
        self._buffer: List[RequestEvent] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_in_progress = False

        # Event stream
        self._event_stream: List[RequestEvent] = []
        self._stream_lock = asyncio.Lock()

        # Projections
        self._projections: Dict[str, Any] = {}
        self._projection_handlers: Dict[str, Callable] = {}

        # Sequence tracking
        self._sequences: Dict[str, int] = {}

        # Metrics
        self.event_count = 0
        self.flush_count = 0

        # Start flush task
        try:
            self._flush_task = asyncio.create_task(self._flush_loop())
        except RuntimeError:
            # If no event loop is running, defer task creation
            self._flush_task = None

    async def _ensure_flush_task(self):
        """Ensure the flush task is running."""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def append(
        self,
        event_type: EventType,
        request_id: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RequestEvent:
        """Append an event to the store."""
        # Ensure flush task is running
        await self._ensure_flush_task()

        async with self._buffer_lock:
            # Get next sequence number
            sequence = self._sequences.get(request_id, 0)
            self._sequences[request_id] = sequence + 1

            # Create event
            event = RequestEvent(
                event_type=event_type,
                request_id=request_id,
                sequence_number=sequence,
                data=data,
                metadata=metadata or {},
            )

            # Add to buffer
            self._buffer.append(event)
            self.event_count += 1

            # Check if we need to flush (but don't flush inside the lock)
            needs_flush = len(self._buffer) >= self.batch_size

        # Apply projections outside the lock
        await self._apply_projections(event)

        # Flush if needed (outside the lock to avoid deadlock)
        if needs_flush and not self._flush_in_progress:
            # Set flag to prevent concurrent flushes
            self._flush_in_progress = True
            try:
                await self._flush_buffer()
            finally:
                self._flush_in_progress = False

        logger.debug(
            f"Appended event {event.event_type.value} for request {request_id} "
            f"(seq: {sequence})"
        )

        return event

    async def get_events(
        self,
        request_id: str,
        start_sequence: int = 0,
        end_sequence: Optional[int] = None,
        event_types: Optional[List[EventType]] = None,
    ) -> List[RequestEvent]:
        """Get events for a request."""
        # Ensure buffer is flushed
        await self._flush_buffer()

        events = []

        # Get from in-memory stream
        async with self._stream_lock:
            for event in self._event_stream:
                if event.request_id != request_id:
                    continue

                if event.sequence_number < start_sequence:
                    continue

                if end_sequence is not None and event.sequence_number > end_sequence:
                    continue

                if event_types and event.event_type not in event_types:
                    continue

                events.append(event)

        # Get from storage if available
        if self.storage_backend and not events:
            stored_events = await self._load_from_storage(
                request_id,
                start_sequence,
                end_sequence,
            )
            events.extend(stored_events)

        # Sort by sequence
        events.sort(key=lambda e: e.sequence_number)

        return events

    async def replay(
        self,
        request_id: str,
        handler: Callable[[RequestEvent], Any],
        start_sequence: int = 0,
        end_sequence: Optional[int] = None,
    ) -> None:
        """Replay events for a request."""
        events = await self.get_events(
            request_id,
            start_sequence,
            end_sequence,
        )

        for event in events:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

    async def stream_events(
        self,
        request_id: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        follow: bool = False,
    ) -> AsyncIterator[RequestEvent]:
        """Stream events as they occur."""
        # Ensure buffer is flushed before streaming
        await self._flush_buffer()

        last_index = 0

        while True:
            # Get new events
            async with self._stream_lock:
                events = self._event_stream[last_index:]
                last_index = len(self._event_stream)

            # Filter and yield
            for event in events:
                if request_id and event.request_id != request_id:
                    continue

                if event_types and event.event_type not in event_types:
                    continue

                yield event

            if not follow:
                break

            # Wait for new events
            await asyncio.sleep(0.1)

    def register_projection(
        self,
        name: str,
        handler: Callable[[RequestEvent, Dict[str, Any]], Any],
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a projection handler."""
        self._projection_handlers[name] = handler
        self._projections[name] = initial_state or {}

        logger.info(f"Registered projection: {name}")

    def get_projection(self, name: str) -> Optional[Dict[str, Any]]:
        """Get current projection state."""
        return self._projections.get(name)

    async def _apply_projections(self, event: RequestEvent) -> None:
        """Apply registered projections to an event."""
        for name, handler in self._projection_handlers.items():
            try:
                state = self._projections[name]

                if asyncio.iscoroutinefunction(handler):
                    new_state = await handler(event, state)
                else:
                    new_state = handler(event, state)

                if new_state is not None:
                    self._projections[name] = new_state

            except Exception as e:
                logger.error(
                    f"Projection {name} failed for event {event.event_id}: {e}"
                )

    async def _flush_buffer(self) -> None:
        """Flush event buffer to storage."""
        # Acquire lock with timeout to prevent deadlock
        try:
            # Use wait_for to add timeout on lock acquisition
            async with asyncio.timeout(1.0):  # 1 second timeout
                async with self._buffer_lock:
                    if not self._buffer:
                        return

                    events_to_flush = self._buffer.copy()
                    self._buffer.clear()
        except asyncio.TimeoutError:
            logger.warning("Timeout acquiring buffer lock during flush")
            return

        # Add to in-memory stream
        async with self._stream_lock:
            self._event_stream.extend(events_to_flush)

        # Store if backend available
        if self.storage_backend:
            await self._store_events(events_to_flush)

        self.flush_count += 1
        logger.debug(f"Flushed {len(events_to_flush)} events")

    async def _flush_loop(self) -> None:
        """Periodically flush the buffer."""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                if not self._flush_in_progress:
                    self._flush_in_progress = True
                    try:
                        await self._flush_buffer()
                    finally:
                        self._flush_in_progress = False
            except asyncio.CancelledError:
                # Final flush before shutdown
                if not self._flush_in_progress:
                    await self._flush_buffer()
                break
            except Exception as e:
                logger.error(f"Flush error: {e}")

    async def _store_events(self, events: List[RequestEvent]) -> None:
        """Store events in backend."""
        try:
            # Group by request ID for efficient storage
            by_request = {}
            for event in events:
                if event.request_id not in by_request:
                    by_request[event.request_id] = []
                by_request[event.request_id].append(event.to_dict())

            # Store each request's events
            for request_id, request_events in by_request.items():
                key = f"events:{request_id}"
                await self.storage_backend.append(key, request_events)

        except Exception as e:
            logger.error(f"Failed to store events: {e}")

    async def _load_from_storage(
        self,
        request_id: str,
        start_sequence: int,
        end_sequence: Optional[int],
    ) -> List[RequestEvent]:
        """Load events from storage."""
        try:
            key = f"events:{request_id}"
            stored = await self.storage_backend.get(key)

            if not stored:
                return []

            events = []
            for event_dict in stored:
                event = RequestEvent.from_dict(event_dict)

                if event.sequence_number < start_sequence:
                    continue

                if end_sequence is not None and event.sequence_number > end_sequence:
                    continue

                events.append(event)

            return events

        except Exception as e:
            logger.error(f"Failed to load events for {request_id}: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get event store statistics."""
        return {
            "event_count": self.event_count,
            "flush_count": self.flush_count,
            "buffer_size": len(self._buffer),
            "stream_size": len(self._event_stream),
            "active_projections": list(self._projection_handlers.keys()),
            "request_count": len(self._sequences),
        }

    async def close(self) -> None:
        """Close event store and flush remaining events."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_buffer()


# Example projection handlers
def request_state_projection(
    event: RequestEvent, state: Dict[str, Any]
) -> Dict[str, Any]:
    """Track current state of all requests."""
    request_id = event.request_id

    if request_id not in state:
        state[request_id] = {
            "current_state": "initialized",
            "created_at": event.timestamp,
            "updated_at": event.timestamp,
            "event_count": 0,
        }

    request_state = state[request_id]
    request_state["event_count"] += 1
    request_state["updated_at"] = event.timestamp

    # Update state based on event type
    if event.event_type == EventType.REQUEST_STARTED:
        request_state["current_state"] = "executing"
    elif event.event_type == EventType.REQUEST_COMPLETED:
        request_state["current_state"] = "completed"
    elif event.event_type == EventType.REQUEST_FAILED:
        request_state["current_state"] = "failed"
    elif event.event_type == EventType.REQUEST_CANCELLED:
        request_state["current_state"] = "cancelled"

    return state


def performance_metrics_projection(
    event: RequestEvent, state: Dict[str, Any]
) -> Dict[str, Any]:
    """Track performance metrics across all requests."""
    if "total_requests" not in state:
        state.update(
            {
                "total_requests": 0,
                "completed_requests": 0,
                "failed_requests": 0,
                "cancelled_requests": 0,
                "total_duration_ms": 0,
                "checkpoint_count": 0,
            }
        )

    state["total_requests"] += 1

    if event.event_type == EventType.REQUEST_COMPLETED:
        state["completed_requests"] += 1
        if "duration_ms" in event.data:
            state["total_duration_ms"] += event.data["duration_ms"]
    elif event.event_type == EventType.REQUEST_FAILED:
        state["failed_requests"] += 1
    elif event.event_type == EventType.REQUEST_CANCELLED:
        state["cancelled_requests"] += 1
    elif event.event_type == EventType.REQUEST_CHECKPOINTED:
        state["checkpoint_count"] += 1

    return state
