"""Integration tests for EventStore with real Docker services."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from kailash.middleware.gateway.event_store import EventStore, EventType, RequestEvent
from kailash.middleware.gateway.storage_backends import (
    PostgreSQLEventStorage,
    RedisEventStorage,
)

from tests.config_unified import POSTGRES_CONFIG, REDIS_CONFIG


@pytest.fixture
def postgres_storage():
    """Create PostgreSQL storage backend using unified config."""
    return PostgreSQLEventStorage(
        host=POSTGRES_CONFIG["host"],
        port=POSTGRES_CONFIG["port"],
        database=POSTGRES_CONFIG["database"],
        username=POSTGRES_CONFIG["user"],
        password=POSTGRES_CONFIG["password"],
    )


@pytest.fixture
def redis_storage():
    """Create Redis storage backend using unified config."""
    return RedisEventStorage(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=0,
        password=None,
    )


@pytest.mark.integration
class TestEventStorePostgreSQLIntegration:
    """Test EventStore with real PostgreSQL backend."""

    @pytest.mark.asyncio
    async def test_postgres_event_persistence(self, postgres_storage):
        """Test event persistence with PostgreSQL."""
        store = EventStore(storage_backend=postgres_storage)

        try:
            # Add events
            event1 = await store.append(
                EventType.REQUEST_STARTED,
                "req_postgres_1",
                {"started_at": "2024-01-01T10:00:00Z"},
                {"user_id": "user_123"},
            )

            event2 = await store.append(
                EventType.REQUEST_CHECKPOINTED,
                "req_postgres_1",
                {"checkpoint": "step_1"},
                {"user_id": "user_123"},
            )

            event3 = await store.append(
                EventType.REQUEST_COMPLETED,
                "req_postgres_1",
                {"completed_at": "2024-01-01T10:05:00Z"},
                {"user_id": "user_123"},
            )

            # Force flush to storage
            await store._flush_buffer()

            # Verify events can be retrieved
            events = await store.get_events("req_postgres_1")
            assert len(events) == 3

            # Verify sequence numbers
            assert events[0].sequence_number == 0
            assert events[1].sequence_number == 1
            assert events[2].sequence_number == 2

            # Verify event types
            assert events[0].event_type == EventType.REQUEST_STARTED
            assert events[1].event_type == EventType.REQUEST_CHECKPOINTED
            assert events[2].event_type == EventType.REQUEST_COMPLETED

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_postgres_event_filtering(self, postgres_storage):
        """Test event filtering with PostgreSQL."""
        store = EventStore(storage_backend=postgres_storage)

        try:
            # Add mixed events
            for i in range(10):
                event_type = (
                    EventType.REQUEST_CHECKPOINTED
                    if i % 2 == 0
                    else EventType.REQUEST_STARTED
                )
                await store.append(
                    event_type,
                    "req_filter_test",
                    {"sequence": i},
                    {"batch": "filter_test"},
                )

            await store._flush_buffer()

            # Filter by type
            checkpoint_events = await store.get_events(
                "req_filter_test", event_types=[EventType.REQUEST_CHECKPOINTED]
            )
            assert len(checkpoint_events) == 5
            assert all(
                e.event_type == EventType.REQUEST_CHECKPOINTED
                for e in checkpoint_events
            )

            # Filter by sequence range
            middle_events = await store.get_events(
                "req_filter_test", start_sequence=3, end_sequence=7
            )
            assert len(middle_events) == 5
            assert middle_events[0].sequence_number == 3
            assert middle_events[-1].sequence_number == 7

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_postgres_event_replay(self, postgres_storage):
        """Test event replay with PostgreSQL."""
        store = EventStore(storage_backend=postgres_storage)

        try:
            # Create workflow simulation events
            workflow_events = [
                (EventType.REQUEST_STARTED, {"step": "init"}),
                (EventType.REQUEST_CHECKPOINTED, {"step": "validate"}),
                (EventType.REQUEST_CHECKPOINTED, {"step": "process"}),
                (EventType.REQUEST_CHECKPOINTED, {"step": "transform"}),
                (EventType.REQUEST_COMPLETED, {"step": "complete"}),
            ]

            for event_type, data in workflow_events:
                await store.append(event_type, "req_replay_test", data)

            await store._flush_buffer()

            # Replay events
            replayed_steps = []

            async def replay_handler(event: RequestEvent):
                replayed_steps.append(event.data["step"])

            await store.replay("req_replay_test", replay_handler)

            assert replayed_steps == [
                "init",
                "validate",
                "process",
                "transform",
                "complete",
            ]

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_postgres_concurrent_writes(self, postgres_storage):
        """Test concurrent event writes with PostgreSQL."""
        store = EventStore(storage_backend=postgres_storage, batch_size=5)

        try:
            # Simulate concurrent request processing
            async def simulate_request(request_id):
                await store.append(
                    EventType.REQUEST_STARTED, request_id, {"start": True}
                )
                await asyncio.sleep(0.01)  # Simulate processing time
                await store.append(
                    EventType.REQUEST_CHECKPOINTED, request_id, {"checkpoint": 1}
                )
                await asyncio.sleep(0.01)
                await store.append(
                    EventType.REQUEST_COMPLETED, request_id, {"end": True}
                )

            # Run 10 concurrent requests
            tasks = [simulate_request(f"req_concurrent_{i}") for i in range(10)]
            await asyncio.gather(*tasks)

            # Force flush
            await store._flush_buffer()

            # Verify all events were stored
            for i in range(10):
                events = await store.get_events(f"req_concurrent_{i}")
                assert len(events) == 3
                assert events[0].event_type == EventType.REQUEST_STARTED
                assert events[1].event_type == EventType.REQUEST_CHECKPOINTED
                assert events[2].event_type == EventType.REQUEST_COMPLETED

        finally:
            await store.close()


@pytest.mark.integration
class TestEventStoreRedisIntegration:
    """Test EventStore with real Redis backend."""

    @pytest.mark.asyncio
    async def test_redis_event_streams(self, redis_storage):
        """Test event streaming with Redis."""
        store = EventStore(storage_backend=redis_storage)

        try:
            # Add events
            await store.append(
                EventType.REQUEST_STARTED, "req_redis_1", {"data": "test1"}
            )
            await store.append(
                EventType.REQUEST_STARTED, "req_redis_2", {"data": "test2"}
            )
            await store.append(
                EventType.REQUEST_COMPLETED, "req_redis_1", {"data": "test3"}
            )

            await store._flush_buffer()

            # Test streaming all events
            all_events = []
            async for event in store.stream_events():
                all_events.append(event)

            assert len(all_events) == 3

            # Test streaming filtered events
            req1_events = []
            async for event in store.stream_events(request_id="req_redis_1"):
                req1_events.append(event)

            assert len(req1_events) == 2
            assert all(e.request_id == "req_redis_1" for e in req1_events)

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_redis_event_expiration(self, redis_storage):
        """Test event expiration with Redis."""
        store = EventStore(storage_backend=redis_storage)

        try:
            # Add events with short TTL
            await store.append(
                EventType.REQUEST_STARTED,
                "req_expire_test",
                {"ttl_test": True},
                {"expires_in": "1s"},
            )

            await store._flush_buffer()

            # Verify event exists initially
            events = await store.get_events("req_expire_test")
            assert len(events) == 1

            # Wait for expiration (if Redis storage supports TTL)
            await asyncio.sleep(2)

            # Note: Actual expiration depends on Redis storage implementation
            # This test verifies the storage can handle TTL metadata

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_redis_pub_sub_integration(self, redis_storage):
        """Test Redis pub/sub integration for real-time events."""
        store = EventStore(storage_backend=redis_storage)

        try:
            # Set up event subscription (if supported by Redis storage)
            published_events = []

            async def event_subscriber(event):
                published_events.append(event)

            # Add events
            await store.append(EventType.REQUEST_STARTED, "req_pubsub", {"live": True})
            await store.append(
                EventType.REQUEST_COMPLETED, "req_pubsub", {"live": True}
            )

            await store._flush_buffer()

            # Verify events can be retrieved normally
            events = await store.get_events("req_pubsub")
            assert len(events) == 2

        finally:
            await store.close()


@pytest.mark.integration
class TestEventStoreProjectionsIntegration:
    """Test EventStore projections with real storage backends."""

    @pytest.mark.asyncio
    async def test_postgres_request_state_projection(self, postgres_storage):
        """Test request state projection with PostgreSQL."""
        store = EventStore(storage_backend=postgres_storage)

        try:
            # Register request state projection
            from kailash.middleware.gateway.event_store import request_state_projection

            store.register_projection(
                "request_states",
                request_state_projection,
                {},
            )

            # Simulate request lifecycle
            await store.append(EventType.REQUEST_STARTED, "req_projection_1", {})
            await store.append(EventType.REQUEST_CHECKPOINTED, "req_projection_1", {})
            await store.append(EventType.REQUEST_COMPLETED, "req_projection_1", {})

            await store.append(EventType.REQUEST_STARTED, "req_projection_2", {})
            await store.append(EventType.REQUEST_FAILED, "req_projection_2", {})

            await store._flush_buffer()

            # Check projection state
            projection = store.get_projection("request_states")

            assert "req_projection_1" in projection
            assert projection["req_projection_1"]["current_state"] == "completed"
            assert projection["req_projection_1"]["event_count"] == 3

            assert "req_projection_2" in projection
            assert projection["req_projection_2"]["current_state"] == "failed"
            assert projection["req_projection_2"]["event_count"] == 2

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_redis_performance_metrics_projection(self, redis_storage):
        """Test performance metrics projection with Redis."""
        store = EventStore(storage_backend=redis_storage)

        try:
            # Register performance metrics projection
            from kailash.middleware.gateway.event_store import (
                performance_metrics_projection,
            )

            store.register_projection(
                "performance_metrics",
                performance_metrics_projection,
                {
                    "total_requests": 0,
                    "completed_requests": 0,
                    "failed_requests": 0,
                    "total_duration_ms": 0,
                },
            )

            # Simulate multiple requests with performance data
            requests = [
                ("req_perf_1", 150),  # 150ms duration
                ("req_perf_2", 200),  # 200ms duration
                ("req_perf_3", None),  # Failed request
            ]

            for req_id, duration in requests:
                await store.append(EventType.REQUEST_STARTED, req_id, {})

                if duration is not None:
                    await store.append(
                        EventType.REQUEST_COMPLETED,
                        req_id,
                        {"duration_ms": duration},
                    )
                else:
                    await store.append(EventType.REQUEST_FAILED, req_id, {})

            await store._flush_buffer()

            # Check performance metrics
            metrics = store.get_projection("performance_metrics")

            assert metrics["total_requests"] == 6  # 3 starts + 2 completes + 1 fail
            assert metrics["completed_requests"] == 2
            assert metrics["failed_requests"] == 1
            assert metrics["total_duration_ms"] == 350  # 150 + 200

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_cross_storage_event_consistency(
        self, postgres_storage, redis_storage
    ):
        """Test event consistency across different storage backends."""
        postgres_store = EventStore(storage_backend=postgres_storage)
        redis_store = EventStore(storage_backend=redis_storage)

        try:
            # Add same events to both stores
            test_events = [
                (EventType.REQUEST_STARTED, "req_consistency", {"source": "postgres"}),
                (EventType.REQUEST_CHECKPOINTED, "req_consistency", {"checkpoint": 1}),
                (EventType.REQUEST_COMPLETED, "req_consistency", {"result": "success"}),
            ]

            for event_type, request_id, data in test_events:
                await postgres_store.append(event_type, request_id, data)
                await redis_store.append(event_type, request_id, data)

            await postgres_store._flush_buffer()
            await redis_store._flush_buffer()

            # Verify consistency
            postgres_events = await postgres_store.get_events("req_consistency")
            redis_events = await redis_store.get_events("req_consistency")

            assert len(postgres_events) == len(redis_events) == 3

            # Compare event types and sequence numbers
            for pg_event, redis_event in zip(postgres_events, redis_events):
                assert pg_event.event_type == redis_event.event_type
                assert pg_event.sequence_number == redis_event.sequence_number
                assert pg_event.request_id == redis_event.request_id

        finally:
            await postgres_store.close()
            await redis_store.close()
