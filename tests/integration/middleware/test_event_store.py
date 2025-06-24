"""Integration tests for EventStore with async components."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.middleware.gateway.event_store import (
    EventStore,
    EventType,
    RequestEvent,
    performance_metrics_projection,
    request_state_projection,
)


class TestRequestEvent:
    """Test RequestEvent dataclass."""

    def test_event_creation(self):
        """Test creating request event."""
        event = RequestEvent(
            event_type=EventType.REQUEST_STARTED,
            request_id="req_123",
            data={"test": "data"},
            metadata={"user": "test_user"},
        )

        assert event.event_id.startswith("evt_")
        assert event.event_type == EventType.REQUEST_STARTED
        assert event.request_id == "req_123"
        assert event.sequence_number == 0
        assert event.data == {"test": "data"}
        assert event.metadata == {"user": "test_user"}

    def test_event_serialization(self):
        """Test event to/from dict."""
        event = RequestEvent(
            event_id="evt_test",
            event_type=EventType.REQUEST_COMPLETED,
            request_id="req_456",
            timestamp=datetime.now(UTC),
            sequence_number=5,
            data={"duration_ms": 123},
            metadata={"source": "test"},
        )

        # Convert to dict
        event_dict = event.to_dict()
        assert event_dict["event_id"] == "evt_test"
        assert event_dict["event_type"] == "request.completed"
        assert event_dict["sequence_number"] == 5

        # Convert back
        restored = RequestEvent.from_dict(event_dict)
        assert restored.event_id == event.event_id
        assert restored.event_type == event.event_type
        assert restored.sequence_number == event.sequence_number


@pytest.mark.integration
@pytest.mark.slow  # Has hanging async tasks
class TestEventStore:
    """Test EventStore class."""

    @pytest.mark.asyncio
    async def test_append_event(self):
        """Test appending events."""
        store = EventStore()

        event = await store.append(
            EventType.REQUEST_STARTED,
            "req_123",
            {"started_at": "2024-01-01"},
            {"user_id": "user_456"},
        )

        assert event.event_type == EventType.REQUEST_STARTED
        assert event.request_id == "req_123"
        assert event.data == {"started_at": "2024-01-01"}
        assert event.metadata == {"user_id": "user_456"}
        assert event.sequence_number == 0
        assert store.event_count == 1

    @pytest.mark.asyncio
    async def test_sequence_numbers(self):
        """Test sequence number increments per request."""
        store = EventStore()

        # Request 1
        event1 = await store.append(EventType.REQUEST_STARTED, "req_1", {})
        event2 = await store.append(EventType.REQUEST_COMPLETED, "req_1", {})

        # Request 2
        event3 = await store.append(EventType.REQUEST_STARTED, "req_2", {})

        assert event1.sequence_number == 0
        assert event2.sequence_number == 1
        assert event3.sequence_number == 0  # New request starts at 0

    @pytest.mark.asyncio
    async def test_buffer_flush_on_size(self):
        """Test buffer flushes when reaching batch size."""
        store = EventStore(batch_size=2, flush_interval_seconds=60)

        # Add 2 events (should trigger flush)
        await store.append(EventType.REQUEST_STARTED, "req_1", {})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {})

        # Buffer should be empty after flush
        assert len(store._buffer) == 0
        assert len(store._event_stream) == 2
        assert store.flush_count == 1

    @pytest.mark.asyncio
    async def test_get_events(self):
        """Test retrieving events for a request."""
        store = EventStore()

        # Add events for multiple requests
        await store.append(EventType.REQUEST_STARTED, "req_1", {"data": 1})
        await store.append(EventType.REQUEST_STARTED, "req_2", {"data": 2})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {"data": 3})

        # Get events for req_1
        events = await store.get_events("req_1")

        assert len(events) == 2
        assert all(e.request_id == "req_1" for e in events)
        assert events[0].event_type == EventType.REQUEST_STARTED
        assert events[1].event_type == EventType.REQUEST_COMPLETED

    @pytest.mark.asyncio
    async def test_get_events_with_filters(self):
        """Test retrieving events with sequence and type filters."""
        store = EventStore()

        # Add multiple events
        for i in range(5):
            await store.append(
                (
                    EventType.REQUEST_CHECKPOINTED
                    if i % 2 == 0
                    else EventType.REQUEST_STARTED
                ),
                "req_1",
                {"seq": i},
            )

        # Get events with sequence range
        events = await store.get_events("req_1", start_sequence=1, end_sequence=3)
        assert len(events) == 3
        assert events[0].sequence_number == 1
        assert events[-1].sequence_number == 3

        # Get events by type
        checkpoint_events = await store.get_events(
            "req_1", event_types=[EventType.REQUEST_CHECKPOINTED]
        )
        assert len(checkpoint_events) == 3
        assert all(
            e.event_type == EventType.REQUEST_CHECKPOINTED for e in checkpoint_events
        )

    @pytest.mark.asyncio
    async def test_replay_events(self):
        """Test replaying events with handler."""
        store = EventStore()

        # Add events
        await store.append(EventType.REQUEST_STARTED, "req_1", {"step": 1})
        await store.append(EventType.REQUEST_CHECKPOINTED, "req_1", {"step": 2})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {"step": 3})

        # Track replayed events
        replayed = []

        async def handler(event: RequestEvent):
            replayed.append(event.data["step"])

        await store.replay("req_1", handler)

        assert replayed == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_stream_events(self):
        """Test streaming events."""
        store = EventStore()

        # Add initial events
        await store.append(EventType.REQUEST_STARTED, "req_1", {"seq": 1})
        await store.append(EventType.REQUEST_STARTED, "req_2", {"seq": 2})

        # Stream events (non-follow mode)
        events = []
        async for event in store.stream_events():
            events.append(event)

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_stream_events_with_filter(self):
        """Test streaming events with filters."""
        store = EventStore()

        # Add events
        await store.append(EventType.REQUEST_STARTED, "req_1", {})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {})
        await store.append(EventType.REQUEST_STARTED, "req_2", {})

        # Stream only req_1 events
        events = []
        async for event in store.stream_events(request_id="req_1"):
            events.append(event)

        assert len(events) == 2
        assert all(e.request_id == "req_1" for e in events)

    @pytest.mark.asyncio
    async def test_projections(self):
        """Test event projections."""
        store = EventStore()

        # Register projection
        def count_projection(event: RequestEvent, state: dict) -> dict:
            state["count"] = state.get("count", 0) + 1
            return state

        store.register_projection("event_count", count_projection, {"count": 0})

        # Add events
        await store.append(EventType.REQUEST_STARTED, "req_1", {})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {})

        # Check projection
        projection = store.get_projection("event_count")
        assert projection["count"] == 2

    @pytest.mark.asyncio
    async def test_async_projection(self):
        """Test async projection handler."""
        store = EventStore()

        # Async projection
        async def async_projection(event: RequestEvent, state: dict) -> dict:
            await asyncio.sleep(0.01)  # Simulate async work
            state["processed"] = state.get("processed", 0) + 1
            return state

        store.register_projection("async_proj", async_projection)

        await store.append(EventType.REQUEST_STARTED, "req_1", {})

        projection = store.get_projection("async_proj")
        assert projection["processed"] == 1

    @pytest.mark.asyncio
    async def test_storage_backend(self):
        """Test integration with storage backend."""
        mock_storage = AsyncMock()
        store = EventStore(storage_backend=mock_storage)

        # Add events to trigger flush
        await store.append(EventType.REQUEST_STARTED, "req_1", {"data": 1})
        await store.append(EventType.REQUEST_COMPLETED, "req_1", {"data": 2})

        # Force flush
        await store._flush_buffer()

        # Check storage was called
        mock_storage.append.assert_called_once()
        call_args = mock_storage.append.call_args
        assert call_args[0][0] == "events:req_1"
        assert len(call_args[0][1]) == 2

    @pytest.mark.asyncio
    async def test_load_from_storage(self):
        """Test loading events from storage."""
        mock_storage = AsyncMock()
        mock_storage.get.return_value = [
            {
                "event_id": "evt_1",
                "event_type": "request.started",
                "request_id": "req_1",
                "timestamp": datetime.now(UTC).isoformat(),
                "sequence_number": 0,
                "data": {"stored": True},
                "metadata": {},
            }
        ]

        store = EventStore(storage_backend=mock_storage)

        # Get events (should load from storage)
        events = await store.get_events("req_1")

        assert len(events) == 1
        assert events[0].data == {"stored": True}
        mock_storage.get.assert_called_with("events:req_1")

    def test_get_stats(self):
        """Test getting event store statistics."""
        store = EventStore()
        store.event_count = 100
        store.flush_count = 10
        store._buffer = [None, None]  # Mock buffer
        store._event_stream = [None] * 50  # Mock stream
        store._projection_handlers = {"proj1": None, "proj2": None}
        store._sequences = {"req_1": 5, "req_2": 3}

        stats = store.get_stats()

        assert stats["event_count"] == 100
        assert stats["flush_count"] == 10
        assert stats["buffer_size"] == 2
        assert stats["stream_size"] == 50
        assert stats["active_projections"] == ["proj1", "proj2"]
        assert stats["request_count"] == 2

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing event store."""
        store = EventStore()

        # Add event to buffer
        await store.append(EventType.REQUEST_STARTED, "req_1", {})
        assert len(store._buffer) == 1

        # Close should flush
        await store.close()

        assert store._flush_task.cancelled()
        assert len(store._buffer) == 0  # Buffer flushed


class TestProjections:
    """Test built-in projections."""

    def test_request_state_projection(self):
        """Test request state tracking projection."""
        state = {}

        # Initial event
        event1 = RequestEvent(
            event_type=EventType.REQUEST_STARTED,
            request_id="req_1",
            timestamp=datetime.now(UTC),
        )
        state = request_state_projection(event1, state)

        assert "req_1" in state
        assert state["req_1"]["current_state"] == "executing"
        assert state["req_1"]["event_count"] == 1

        # Completion event
        event2 = RequestEvent(
            event_type=EventType.REQUEST_COMPLETED,
            request_id="req_1",
            timestamp=datetime.now(UTC),
        )
        state = request_state_projection(event2, state)

        assert state["req_1"]["current_state"] == "completed"
        assert state["req_1"]["event_count"] == 2

    def test_performance_metrics_projection(self):
        """Test performance metrics projection."""
        state = {}

        # Start event
        event1 = RequestEvent(
            event_type=EventType.REQUEST_STARTED,
            request_id="req_1",
        )
        state = performance_metrics_projection(event1, state)

        assert state["total_requests"] == 1
        assert state["completed_requests"] == 0

        # Completion event with duration
        event2 = RequestEvent(
            event_type=EventType.REQUEST_COMPLETED,
            request_id="req_1",
            data={"duration_ms": 123},
        )
        state = performance_metrics_projection(event2, state)

        assert state["total_requests"] == 2
        assert state["completed_requests"] == 1
        assert state["total_duration_ms"] == 123

        # Failed event
        event3 = RequestEvent(
            event_type=EventType.REQUEST_FAILED,
            request_id="req_2",
        )
        state = performance_metrics_projection(event3, state)

        assert state["failed_requests"] == 1
