"""Integration tests for CheckpointManager with real Docker services."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from kailash.middleware.gateway.checkpoint_manager import (
    CheckpointManager,
    DiskStorage,
    MemoryStorage,
)
from kailash.middleware.gateway.durable_request import Checkpoint, RequestState
from kailash.middleware.gateway.storage_backends import RedisStorage

from tests.config_unified import REDIS_CONFIG


@pytest.fixture
def redis_storage():
    """Create Redis storage backend using unified config."""
    return RedisStorage(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=0,
        password=None,
    )


@pytest.fixture
def checkpoint():
    """Create test checkpoint."""
    return Checkpoint(
        checkpoint_id="ckpt_123",
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
class TestCheckpointManagerRedisIntegration:
    """Test CheckpointManager with real Redis backend."""

    @pytest.mark.asyncio
    async def test_redis_save_and_load(self, redis_storage, checkpoint):
        """Test saving and loading checkpoint with Redis."""
        manager = CheckpointManager(
            memory_storage=MemoryStorage(),
            disk_storage=None,
            cloud_storage=redis_storage,
        )

        await manager.save_checkpoint(checkpoint)
        loaded = await manager.load_checkpoint("ckpt_123")

        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.name == checkpoint.name
        assert loaded.data == checkpoint.data

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_compression(self, redis_storage):
        """Test checkpoint compression with Redis."""
        large_data = {"data": "x" * 10000}
        checkpoint = Checkpoint(
            checkpoint_id="ckpt_compress",
            request_id="req_compress",
            sequence=0,
            name="compress_test",
            state=RequestState.EXECUTING,
            data=large_data,
            workflow_state=None,
            created_at=datetime.now(UTC),
            size_bytes=len(json.dumps(large_data)),
        )

        manager = CheckpointManager(
            memory_storage=MemoryStorage(),
            disk_storage=None,
            cloud_storage=redis_storage,
            compression_enabled=True,
            compression_threshold_bytes=1024,
        )

        await manager.save_checkpoint(checkpoint)

        # Verify compression was applied
        assert manager.compression_ratio_sum > 0
        assert manager.compression_ratio_sum < 1.0

        # Verify data can be loaded back correctly
        loaded = await manager.load_checkpoint("ckpt_compress")
        assert loaded.data == large_data

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_tiered_storage(self, redis_storage, checkpoint):
        """Test saving to Redis as cloud tier."""
        manager = CheckpointManager(
            memory_storage=MemoryStorage(),
            disk_storage=DiskStorage("/tmp/test_checkpoints"),
            cloud_storage=redis_storage,
        )

        await manager.save_checkpoint(checkpoint)

        # Give time for async cloud save
        await asyncio.sleep(0.2)

        # Verify saved to all tiers
        memory_data = await manager.memory_storage.load("ckpt_123")
        assert memory_data is not None

        disk_data = await manager.disk_storage.load("ckpt_123")
        assert disk_data is not None

        cloud_data = await manager.cloud_storage.load("ckpt_123")
        assert cloud_data is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_failover(self, redis_storage, checkpoint):
        """Test failover from Redis to local storage."""
        manager = CheckpointManager(
            memory_storage=MemoryStorage(),
            disk_storage=DiskStorage("/tmp/test_checkpoints"),
            cloud_storage=redis_storage,
        )

        # Save checkpoint
        await manager.save_checkpoint(checkpoint)

        # Simulate Redis failure by closing connection
        await redis_storage.close()

        # Should still be able to load from memory/disk
        loaded = await manager.load_checkpoint("ckpt_123")
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_list_keys(self, redis_storage):
        """Test listing checkpoint keys with Redis."""
        manager = CheckpointManager(cloud_storage=redis_storage)

        # Save multiple checkpoints
        for i in range(3):
            ckpt = Checkpoint(
                checkpoint_id=f"ckpt_req_456_{i}",
                request_id="req_456",
                sequence=i,
                name=f"checkpoint_{i}",
                state=RequestState.EXECUTING,
                data={},
                workflow_state=None,
                created_at=datetime.now(UTC),
                size_bytes=100,
            )
            await manager.save_checkpoint(ckpt)

        # Give time for async saves
        await asyncio.sleep(0.2)

        # List keys with prefix
        keys = await redis_storage.list_keys("ckpt_req_456_")
        assert len(keys) == 3
        assert all(key.startswith("ckpt_req_456_") for key in keys)

        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_garbage_collection(self, redis_storage):
        """Test garbage collection with Redis storage."""
        manager = CheckpointManager(
            cloud_storage=redis_storage,
            retention_hours=1,
        )

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

        # Give time for async saves
        await asyncio.sleep(0.2)

        # Run garbage collection
        await manager._garbage_collection()

        # Old checkpoint should be deleted
        assert await manager.load_checkpoint("ckpt_old") is None
        assert await manager.load_checkpoint("ckpt_new") is not None

        await manager.close()


@pytest.mark.integration
class TestCheckpointManagerDockerCompose:
    """Test CheckpointManager with Docker services (requires manual setup)."""

    @pytest.mark.asyncio
    async def test_multi_storage_integration(self, checkpoint):
        """Test CheckpointManager with multiple storage backends."""
        # Create storage backends
        memory_storage = MemoryStorage()
        disk_storage = DiskStorage("/tmp/test_checkpoints")

        # Redis storage using unified config
        redis_storage = RedisStorage(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            db=0,
            password=None,
        )

        manager = CheckpointManager(
            memory_storage=memory_storage,
            disk_storage=disk_storage,
            cloud_storage=redis_storage,
        )

        try:
            # Save checkpoint
            await manager.save_checkpoint(checkpoint)

            # Give time for async cloud save
            await asyncio.sleep(0.5)

            # Verify saved to all storage tiers
            memory_data = await memory_storage.load("ckpt_123")
            assert memory_data is not None

            disk_data = await disk_storage.load("ckpt_123")
            assert disk_data is not None

            # Load from manager (should use memory tier first)
            loaded = await manager.load_checkpoint("ckpt_123")
            assert loaded is not None
            assert loaded.checkpoint_id == checkpoint.checkpoint_id

        finally:
            await manager.close()
            await redis_storage.close()
