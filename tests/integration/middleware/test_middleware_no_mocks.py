"""Integration tests for middleware components without mocks."""

import asyncio
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.middleware.communication.api_gateway import APIGateway
from kailash.middleware.gateway.checkpoint_manager import (
    CheckpointManager,
    DiskStorage,
    MemoryStorage,
)
from kailash.middleware.gateway.durable_request import Checkpoint, RequestState
from kailash.middleware.gateway.event_store import EventStore, EventType, RequestEvent
from kailash.nodes.transform import DataTransformer


@pytest.fixture
def checkpoint():
    """Create test checkpoint."""
    return Checkpoint(
        checkpoint_id="ckpt_req_456_0",  # Format: ckpt_{request_id}_{sequence}
        request_id="req_456",
        sequence=0,
        name="test_checkpoint",
        state=RequestState.EXECUTING,
        data={"key": "value"},
        workflow_state=None,
        created_at=datetime.now(UTC),
        size_bytes=100,
    )


@pytest.mark.integration
class TestCheckpointManagerIntegration:
    """Test CheckpointManager integration without mocks."""

    @pytest.mark.asyncio
    async def test_memory_disk_integration(self, checkpoint):
        """Test CheckpointManager with memory and disk storage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory_storage = MemoryStorage()
            disk_storage = DiskStorage(tmp_dir)

            manager = CheckpointManager(
                memory_storage=memory_storage,
                disk_storage=disk_storage,
                compression_enabled=True,
                compression_threshold_bytes=100,
            )

            try:
                # Save checkpoint
                await manager.save_checkpoint(checkpoint)

                # Verify saved to memory
                memory_data = await memory_storage.load("ckpt_req_456_0")
                assert memory_data is not None

                # Verify saved to disk
                disk_data = await disk_storage.load("ckpt_req_456_0")
                assert disk_data is not None

                # Load from manager
                loaded = await manager.load_checkpoint("ckpt_req_456_0")
                assert loaded is not None
                assert loaded.checkpoint_id == checkpoint.checkpoint_id
                assert loaded.data == checkpoint.data

                # Test latest checkpoint loading
                latest = await manager.load_latest_checkpoint("req_456")
                assert latest is not None
                assert latest.checkpoint_id == checkpoint.checkpoint_id

            finally:
                await manager.close()

    @pytest.mark.asyncio
    async def test_checkpoint_compression(self, checkpoint):
        """Test checkpoint compression without mocks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Large data for compression
            large_data = {"data": "x" * 10000}
            checkpoint.data = large_data

            manager = CheckpointManager(
                memory_storage=MemoryStorage(),
                disk_storage=DiskStorage(tmp_dir),
                compression_enabled=True,
                compression_threshold_bytes=1000,
            )

            try:
                await manager.save_checkpoint(checkpoint)

                # Verify compression was applied
                assert manager.compression_ratio_sum > 0
                assert manager.compression_ratio_sum < 1.0

                # Verify data can be loaded back correctly
                loaded = await manager.load_checkpoint("ckpt_req_456_0")
                assert loaded.data == large_data

            finally:
                await manager.close()

    @pytest.mark.asyncio
    async def test_garbage_collection(self):
        """Test garbage collection without mocks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = CheckpointManager(
                memory_storage=MemoryStorage(),
                disk_storage=DiskStorage(tmp_dir),
                retention_hours=1,
            )

            try:
                # Create old checkpoint
                old_checkpoint = Checkpoint(
                    checkpoint_id="ckpt_old",
                    request_id="req_old",
                    sequence=0,
                    name="old",
                    state=RequestState.COMPLETED,
                    data={},
                    workflow_state=None,
                    created_at=datetime.now(UTC) - timedelta(hours=2),
                    size_bytes=100,
                )

                # Create recent checkpoint
                new_checkpoint = Checkpoint(
                    checkpoint_id="ckpt_new",
                    request_id="req_new",
                    sequence=0,
                    name="new",
                    state=RequestState.COMPLETED,
                    data={},
                    workflow_state=None,
                    created_at=datetime.now(UTC),
                    size_bytes=100,
                )

                await manager.save_checkpoint(old_checkpoint)
                await manager.save_checkpoint(new_checkpoint)

                # Run garbage collection
                await manager._garbage_collection()

                # Old checkpoint should be deleted
                assert await manager.load_checkpoint("ckpt_old") is None
                assert await manager.load_checkpoint("ckpt_new") is not None

            finally:
                await manager.close()


@pytest.mark.integration
class TestEventStoreIntegration:
    """Test EventStore integration without mocks."""

    @pytest.mark.asyncio
    async def test_event_store_basic_operations(self):
        """Test EventStore basic operations without mocks."""
        store = EventStore(batch_size=2)

        try:
            # Add events
            event1 = await store.append(
                EventType.REQUEST_STARTED,
                "req_integration_1",
                {"started_at": "2024-01-01T10:00:00Z"},
                {"user_id": "user_123"},
            )

            event2 = await store.append(
                EventType.REQUEST_CHECKPOINTED,
                "req_integration_1",
                {"checkpoint": "step_1"},
                {"user_id": "user_123"},
            )

            event3 = await store.append(
                EventType.REQUEST_COMPLETED,
                "req_integration_1",
                {"completed_at": "2024-01-01T10:05:00Z"},
                {"user_id": "user_123"},
            )

            # Force flush
            await store._flush_buffer()

            # Verify events can be retrieved
            events = await store.get_events("req_integration_1")
            assert len(events) == 3

            # Verify sequence numbers
            assert events[0].sequence_number == 0
            assert events[1].sequence_number == 1
            assert events[2].sequence_number == 2

            # Verify event types
            assert events[0].event_type == EventType.REQUEST_STARTED
            assert events[1].event_type == EventType.REQUEST_CHECKPOINTED
            assert events[2].event_type == EventType.REQUEST_COMPLETED

            # Test event filtering
            checkpoint_events = await store.get_events(
                "req_integration_1", event_types=[EventType.REQUEST_CHECKPOINTED]
            )
            assert len(checkpoint_events) == 1
            assert checkpoint_events[0].event_type == EventType.REQUEST_CHECKPOINTED

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_projections(self):
        """Test event projections without mocks."""
        store = EventStore()

        try:
            # Register request state projection
            from kailash.middleware.gateway.event_store import request_state_projection

            store.register_projection(
                "request_states",
                request_state_projection,
                {},
            )

            # Add events
            await store.append(EventType.REQUEST_STARTED, "req_proj_1", {})
            await store.append(EventType.REQUEST_CHECKPOINTED, "req_proj_1", {})
            await store.append(EventType.REQUEST_COMPLETED, "req_proj_1", {})

            await store.append(EventType.REQUEST_STARTED, "req_proj_2", {})
            await store.append(EventType.REQUEST_FAILED, "req_proj_2", {})

            await store._flush_buffer()

            # Check projection state
            projection = store.get_projection("request_states")

            assert "req_proj_1" in projection
            assert projection["req_proj_1"]["current_state"] == "completed"
            assert projection["req_proj_1"]["event_count"] == 3

            assert "req_proj_2" in projection
            assert projection["req_proj_2"]["current_state"] == "failed"
            assert projection["req_proj_2"]["event_count"] == 2

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_event_replay(self):
        """Test event replay without mocks."""
        store = EventStore()

        try:
            # Add events
            await store.append(EventType.REQUEST_STARTED, "req_replay", {"step": 1})
            await store.append(
                EventType.REQUEST_CHECKPOINTED, "req_replay", {"step": 2}
            )
            await store.append(EventType.REQUEST_COMPLETED, "req_replay", {"step": 3})

            await store._flush_buffer()

            # Replay events
            replayed = []

            async def handler(event: RequestEvent):
                replayed.append(event.data["step"])

            await store.replay("req_replay", handler)

            assert replayed == [1, 2, 3]

        finally:
            await store.close()


@pytest.mark.integration
class TestAPIGatewayIntegration:
    """Test API Gateway integration without mocks."""

    def test_data_transformer_integration(self):
        """Test DataTransformer integration without mocks."""
        transformer = DataTransformer(name="test_transformer")

        # Test basic transformation
        result = transformer.execute(
            data={"input": "test", "value": 42},
            transformations=[
                "{'transformed': True, **data}",
                "{'doubled_value': data['value'] * 2, **data}",
            ],
        )

        # Check result format
        assert "result" in result
        assert result["result"]["input"] == "test"
        assert result["result"]["value"] == 42
        assert result["result"]["doubled_value"] == 84

        # Test single transformation to ensure 'transformed' key exists
        single_result = transformer.execute(
            data={"input": "test", "value": 42},
            transformations=["{'transformed': True, **data}"],
        )

        assert single_result["result"]["transformed"] is True
        assert single_result["result"]["input"] == "test"

    def test_api_gateway_components(self):
        """Test API Gateway component integration without mocks."""
        # Create minimal gateway for testing
        gateway = APIGateway(
            enable_auth=False,
            enable_docs=False,
        )

        # Test that data transformer is properly initialized
        assert hasattr(gateway, "data_transformer")
        assert isinstance(gateway.data_transformer, DataTransformer)
        assert hasattr(gateway.data_transformer, "execute")
        assert not hasattr(gateway.data_transformer, "process")

    def test_middleware_pipeline_integration(self):
        """Test middleware pipeline integration without mocks."""
        # Create components
        checkpoint_manager = CheckpointManager(
            memory_storage=MemoryStorage(),
            disk_storage=DiskStorage("/tmp/test_pipeline"),
        )

        event_store = EventStore()

        # Create gateway
        gateway = APIGateway(
            enable_auth=False,
            enable_docs=False,
        )

        # Test that gateway has the expected components
        assert hasattr(gateway, "data_transformer")
        assert hasattr(gateway.data_transformer, "execute")

        # Test data transformation
        result = gateway.data_transformer.execute(
            data={"test": "pipeline"},
            transformations=["{'processed': True, **data}"],
        )

        assert result["result"]["test"] == "pipeline"
        assert result["result"]["processed"] is True

    @pytest.mark.asyncio
    async def test_async_middleware_operations(self):
        """Test async middleware operations without mocks."""
        # Create async-friendly components
        checkpoint_manager = CheckpointManager(memory_storage=MemoryStorage())
        event_store = EventStore()

        try:
            # Test checkpoint operations
            checkpoint = Checkpoint(
                checkpoint_id="ckpt_req_async_0",
                request_id="req_async",
                sequence=0,
                name="async_checkpoint",
                state=RequestState.EXECUTING,
                data={"async": True},
                workflow_state=None,
                created_at=datetime.now(UTC),
                size_bytes=100,
            )

            await checkpoint_manager.save_checkpoint(checkpoint)
            loaded = await checkpoint_manager.load_checkpoint("ckpt_req_async_0")
            assert loaded is not None
            assert loaded.data["async"] is True

            # Test event operations
            event = await event_store.append(
                EventType.REQUEST_STARTED,
                "req_async",
                {"async_test": True},
            )
            assert event.data["async_test"] is True

            await event_store._flush_buffer()
            events = await event_store.get_events("req_async")
            assert len(events) == 1
            assert events[0].data["async_test"] is True

        finally:
            await checkpoint_manager.close()
            await event_store.close()


@pytest.mark.integration
class TestMiddlewareErrorHandling:
    """Test middleware error handling without mocks."""

    @pytest.mark.asyncio
    async def test_checkpoint_manager_error_handling(self):
        """Test CheckpointManager error handling."""
        manager = CheckpointManager(memory_storage=MemoryStorage())

        try:
            # Test loading non-existent checkpoint
            result = await manager.load_checkpoint("non_existent")
            assert result is None

            # Test loading latest for non-existent request
            result = await manager.load_latest_checkpoint("non_existent_req")
            assert result is None

            # Test stats with no operations
            stats = manager.get_stats()
            assert stats["save_count"] == 0
            assert stats["load_count"] == 0

        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_event_store_error_handling(self):
        """Test EventStore error handling."""
        store = EventStore()

        try:
            # Test getting events for non-existent request
            events = await store.get_events("non_existent_req")
            assert len(events) == 0

            # Test replay with no events
            replayed = []

            async def handler(event):
                replayed.append(event)

            await store.replay("non_existent_req", handler)
            assert len(replayed) == 0

            # Test projection with no events
            projection = store.get_projection("non_existent_projection")
            assert projection is None

        finally:
            await store.close()

    def test_data_transformer_error_handling(self):
        """Test DataTransformer error handling."""
        transformer = DataTransformer(name="error_test")

        # Test with invalid transformation
        with pytest.raises(Exception):
            transformer.execute(
                data={"test": "data"},
                transformations=["invalid python code {{"],
            )

        # Test with empty transformations
        result = transformer.execute(
            data={"test": "data"},
            transformations=[],
        )
        assert result["result"]["test"] == "data"
