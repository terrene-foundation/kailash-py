"""Unit tests for CheckpointManager."""

import asyncio
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.middleware.gateway.checkpoint_manager import (
    CheckpointManager,
    DiskStorage,
    MemoryStorage,
)
from kailash.middleware.gateway.durable_request import Checkpoint, RequestState


class TestMemoryStorage:
    """Test MemoryStorage backend."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test saving and loading from memory."""
        storage = MemoryStorage(max_size_mb=1)

        data = b"test data"
        await storage.save("key1", data)

        loaded = await storage.load("key1")
        assert loaded == data

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when size limit reached."""
        storage = MemoryStorage(max_size_mb=1)  # 1MB limit

        # Create data that's about 300KB each
        large_data = b"x" * (300 * 1024)

        # Save 4 items (should evict first one)
        await storage.save("key1", large_data)
        await storage.save("key2", large_data)
        await storage.save("key3", large_data)
        await storage.save("key4", large_data)

        # First key should be evicted
        assert await storage.load("key1") is None
        assert await storage.load("key2") is not None
        assert await storage.load("key3") is not None
        assert await storage.load("key4") is not None

    @pytest.mark.asyncio
    async def test_lru_access_order(self):
        """Test LRU updates access order."""
        storage = MemoryStorage(max_size_mb=1)

        await storage.save("key1", b"data1")
        await storage.save("key2", b"data2")

        # Access key1 to make it most recently used
        await storage.load("key1")

        # Add large data to trigger eviction
        # Need to ensure total size exceeds 1MB to trigger eviction
        # Current size is 10 bytes (key1 + key2), so we need more than 1MB - 10
        large_data = b"x" * (1024 * 1024 - 5)  # This will force eviction

        await storage.save("key3", large_data)

        # key2 should be evicted (least recently used)
        assert await storage.load("key1") is not None
        assert await storage.load("key2") is None
        assert await storage.load("key3") is not None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting from memory."""
        storage = MemoryStorage()

        await storage.save("key1", b"data1")
        await storage.delete("key1")

        assert await storage.load("key1") is None

    @pytest.mark.asyncio
    async def test_list_keys(self):
        """Test listing keys with prefix."""
        storage = MemoryStorage()

        await storage.save("prefix_1", b"data1")
        await storage.save("prefix_2", b"data2")
        await storage.save("other_1", b"data3")

        keys = await storage.list_keys("prefix_")
        assert set(keys) == {"prefix_1", "prefix_2"}


class TestDiskStorage:
    """Test DiskStorage backend."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        """Test saving and loading from disk."""
        storage = DiskStorage(str(tmp_path))

        data = b"test data"
        await storage.save("test_key", data)

        loaded = await storage.load("test_key")
        assert loaded == data

        # Check file exists - test_key splits to test/test_key.ckpt
        assert (tmp_path / "test" / "test_key.ckpt").exists()

    @pytest.mark.asyncio
    async def test_subdirectory_creation(self, tmp_path):
        """Test subdirectory creation for keys."""
        storage = DiskStorage(str(tmp_path))

        await storage.save("type_123_abc", b"data")

        # Should create subdirectory
        assert (tmp_path / "type" / "type_123_abc.ckpt").exists()

    @pytest.mark.asyncio
    async def test_atomic_write(self, tmp_path):
        """Test atomic file writing."""
        storage = DiskStorage(str(tmp_path))

        # Write data
        await storage.save("test_key", b"data")

        # Temp file should not exist
        assert not list(tmp_path.glob("*.tmp"))

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        """Test deleting from disk."""
        storage = DiskStorage(str(tmp_path))

        await storage.save("test_key", b"data")
        await storage.delete("test_key")

        assert not (tmp_path / "test" / "test_key.ckpt").exists()
        assert await storage.load("test_key") is None

    @pytest.mark.asyncio
    async def test_list_keys(self, tmp_path):
        """Test listing keys with prefix."""
        storage = DiskStorage(str(tmp_path))

        await storage.save("ckpt_123", b"data1")
        await storage.save("ckpt_456", b"data2")
        await storage.save("other_789", b"data3")

        keys = await storage.list_keys("ckpt_")
        assert set(keys) == {"ckpt_123", "ckpt_456"}


class TestCheckpointManager:
    """Test CheckpointManager."""

    @pytest.fixture
    def checkpoint(self):
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

    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self, checkpoint):
        """Test saving and loading checkpoint."""
        manager = CheckpointManager()

        await manager.save_checkpoint(checkpoint)

        loaded = await manager.load_checkpoint("ckpt_123")
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.name == checkpoint.name
        assert loaded.data == checkpoint.data

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_compression(self, checkpoint):
        """Test checkpoint compression."""
        # Create checkpoint with large data
        large_data = {"data": "x" * 10000}
        checkpoint.data = large_data

        manager = CheckpointManager(
            compression_enabled=True, compression_threshold_bytes=1024
        )

        await manager.save_checkpoint(checkpoint)

        # Check compression was applied
        assert manager.save_count == 1
        assert manager.compression_ratio_sum > 0
        assert manager.compression_ratio_sum < 1.0  # Should be compressed

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_no_compression_small_data(self, checkpoint):
        """Test no compression for small data."""
        manager = CheckpointManager(
            compression_enabled=True, compression_threshold_bytes=1024
        )

        # Small checkpoint
        checkpoint.data = {"small": "data"}

        await manager.save_checkpoint(checkpoint)

        # No compression for small data (ratio is 1.0)
        assert manager.compression_ratio_sum == 1.0

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_tiered_storage(self, checkpoint):
        """Test saving to multiple storage tiers."""
        memory_storage = AsyncMock()
        disk_storage = AsyncMock()
        cloud_storage = AsyncMock()

        manager = CheckpointManager(
            memory_storage=memory_storage,
            disk_storage=disk_storage,
            cloud_storage=cloud_storage,
        )

        await manager.save_checkpoint(checkpoint)

        # Should save to memory and disk immediately
        memory_storage.save.assert_called_once()
        disk_storage.save.assert_called_once()

        # Cloud save is async (not awaited)
        await asyncio.sleep(0.1)
        cloud_storage.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_from_tiers(self):
        """Test loading from storage tiers."""
        # Setup storage mocks
        memory_storage = AsyncMock()
        disk_storage = AsyncMock()
        cloud_storage = AsyncMock()

        # Memory miss, disk hit
        memory_storage.load.return_value = None

        checkpoint_data = {
            "checkpoint_id": "ckpt_123",
            "request_id": "req_456",
            "sequence": 0,
            "name": "test",
            "state": "executing",
            "data": {},
            "workflow_state": None,
            "created_at": datetime.now(UTC).isoformat(),
            "size_bytes": 100,
        }
        disk_storage.load.return_value = json.dumps(checkpoint_data).encode()

        manager = CheckpointManager(
            memory_storage=memory_storage,
            disk_storage=disk_storage,
            cloud_storage=cloud_storage,
        )

        loaded = await manager.load_checkpoint("ckpt_123")

        assert loaded is not None
        assert loaded.checkpoint_id == "ckpt_123"

        # Should promote to memory
        memory_storage.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_latest_checkpoint(self, checkpoint):
        """Test loading latest checkpoint for request."""
        manager = CheckpointManager()

        # Save multiple checkpoints
        checkpoints = []
        for i in range(3):
            ckpt = Checkpoint(
                checkpoint_id=f"ckpt_req_456_{i}",  # Include request_id in checkpoint_id
                request_id="req_456",
                sequence=i,
                name=f"checkpoint_{i}",
                state=RequestState.EXECUTING,
                data={},
                workflow_state=None,
                created_at=datetime.now(UTC),
                size_bytes=100,
            )
            checkpoints.append(ckpt)
            await manager.save_checkpoint(ckpt)

        # Load latest
        latest = await manager.load_latest_checkpoint("req_456")

        assert latest is not None
        assert latest.sequence == 2  # Highest sequence number

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_garbage_collection(self):
        """Test garbage collection of old checkpoints."""
        manager = CheckpointManager(retention_hours=1)

        # Create old checkpoint
        old_checkpoint = Checkpoint(
            checkpoint_id="ckpt_req_old_0",
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
            checkpoint_id="ckpt_req_new_0",
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
        assert await manager.load_checkpoint("ckpt_req_old_0") is None
        assert await manager.load_checkpoint("ckpt_req_new_0") is not None

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_stats(self, checkpoint):
        """Test getting manager statistics."""
        manager = CheckpointManager()

        await manager.save_checkpoint(checkpoint)
        await manager.load_checkpoint("ckpt_123")

        stats = manager.get_stats()

        assert stats["save_count"] == 1
        assert stats["load_count"] == 1
        assert stats["compression_enabled"] is True
        assert stats["avg_compression_ratio"] == 1.0  # No compression

        # Clean up
        await manager.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing checkpoint manager."""
        manager = CheckpointManager()

        # Close should cancel GC task
        await manager.close()

        assert manager._gc_task.cancelled()
