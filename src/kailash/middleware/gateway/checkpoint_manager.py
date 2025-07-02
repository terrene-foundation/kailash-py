"""Checkpoint management with tiered storage and compression.

This module provides:
- Checkpoint creation and restoration
- Tiered storage (memory/disk/cloud)
- Automatic compression
- Garbage collection
"""

import asyncio
import datetime as dt
import gzip
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .durable_request import Checkpoint

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Protocol for checkpoint storage backends."""

    async def save(self, key: str, data: bytes) -> None:
        """Save data to storage."""
        ...

    async def load(self, key: str) -> Optional[bytes]:
        """Load data from storage."""
        ...

    async def delete(self, key: str) -> None:
        """Delete data from storage."""
        ...

    async def list_keys(self, prefix: str) -> List[str]:
        """List keys with prefix."""
        ...


class MemoryStorage:
    """In-memory storage backend with LRU eviction."""

    def __init__(self, max_size_mb: int = 100):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.data: OrderedDict[str, bytes] = OrderedDict()
        self.current_size = 0
        self._lock = asyncio.Lock()

    async def save(self, key: str, data: bytes) -> None:
        """Save to memory with LRU eviction."""
        async with self._lock:
            # Remove if exists to update position
            if key in self.data:
                self.current_size -= len(self.data[key])
                del self.data[key]

            # Evict oldest entries if needed
            while self.current_size + len(data) > self.max_size_bytes and self.data:
                evicted_key, evicted_data = self.data.popitem(last=False)
                self.current_size -= len(evicted_data)
                logger.debug(f"Evicted {evicted_key} from memory storage")

            # Add new data
            self.data[key] = data
            self.current_size += len(data)

    async def load(self, key: str) -> Optional[bytes]:
        """Load from memory."""
        async with self._lock:
            if key in self.data:
                # Move to end (most recently used)
                self.data.move_to_end(key)
                return self.data[key]
            return None

    async def delete(self, key: str) -> None:
        """Delete from memory."""
        async with self._lock:
            if key in self.data:
                self.current_size -= len(self.data[key])
                del self.data[key]

    async def list_keys(self, prefix: str) -> List[str]:
        """List keys with prefix."""
        async with self._lock:
            return [k for k in self.data.keys() if k.startswith(prefix)]


class DiskStorage:
    """Disk-based storage backend."""

    def __init__(self, base_path: str = "/tmp/kailash_checkpoints"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_path(self, key: str) -> Path:
        """Get file path for key."""
        # Use subdirectories to avoid too many files in one directory
        parts = key.split("_")
        if len(parts) >= 2:
            subdir = self.base_path / parts[0]
            subdir.mkdir(exist_ok=True)
            return subdir / f"{key}.ckpt"
        return self.base_path / f"{key}.ckpt"

    async def save(self, key: str, data: bytes) -> None:
        """Save to disk."""
        path = self._get_path(key)

        # Write atomically
        temp_path = path.with_suffix(".tmp")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: temp_path.write_bytes(data)
            )

            # Atomic rename
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: temp_path.rename(path)
            )
        except Exception as e:
            logger.error(f"Failed to save checkpoint to disk: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise

    async def load(self, key: str) -> Optional[bytes]:
        """Load from disk."""
        path = self._get_path(key)

        if not path.exists():
            return None

        try:
            return await asyncio.get_event_loop().run_in_executor(None, path.read_bytes)
        except Exception as e:
            logger.error(f"Failed to load checkpoint from disk: {e}")
            return None

    async def delete(self, key: str) -> None:
        """Delete from disk."""
        path = self._get_path(key)

        if path.exists():
            await asyncio.get_event_loop().run_in_executor(None, path.unlink)

    async def list_keys(self, prefix: str) -> List[str]:
        """List keys with prefix."""
        keys = []

        for path in self.base_path.rglob("*.ckpt"):
            key = path.stem
            if key.startswith(prefix):
                keys.append(key)

        return keys


class CheckpointManager:
    """Manages checkpoints with tiered storage and compression."""

    def __init__(
        self,
        memory_storage: Optional[MemoryStorage] = None,
        disk_storage: Optional[DiskStorage] = None,
        cloud_storage: Optional[StorageBackend] = None,
        compression_enabled: bool = True,
        compression_threshold_bytes: int = 1024,  # 1KB
        retention_hours: int = 24,
        # Backward compatibility parameter
        storage: Optional[DiskStorage] = None,
    ):
        """Initialize checkpoint manager.

        Args:
            memory_storage: Memory storage backend (optional)
            disk_storage: Disk storage backend (optional)
            cloud_storage: Cloud storage backend (optional)
            compression_enabled: Enable compression for large checkpoints
            compression_threshold_bytes: Minimum size for compression
            retention_hours: Hours to retain checkpoints
            storage: DEPRECATED - Use disk_storage instead
        """
        # Handle backward compatibility
        if storage is not None:
            import warnings

            warnings.warn(
                "The 'storage' parameter is deprecated. Use 'disk_storage' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if disk_storage is None:
                disk_storage = storage

        self.memory_storage = memory_storage or MemoryStorage()
        self.disk_storage = disk_storage or DiskStorage()
        self.cloud_storage = cloud_storage  # Optional cloud backend
        self.compression_enabled = compression_enabled
        self.compression_threshold = compression_threshold_bytes
        self.retention_hours = retention_hours

        # Metrics
        self.save_count = 0
        self.load_count = 0
        self.compression_ratio_sum = 0.0

        # Initialize garbage collection task (will be started when first used)
        self._gc_task = None
        self._gc_started = False

    def _ensure_gc_started(self):
        """Ensure garbage collection task is started (lazy initialization)."""
        if not self._gc_started:
            try:
                self._gc_task = asyncio.create_task(self._garbage_collection_loop())
                self._gc_started = True
            except RuntimeError:
                # No event loop running, GC will be started later
                pass

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to storage."""
        self._ensure_gc_started()
        start_time = time.time()

        # Serialize checkpoint
        data = json.dumps(checkpoint.to_dict()).encode("utf-8")
        original_size = len(data)

        # Compress if enabled and beneficial
        compression_ratio = 1.0  # Default to no compression
        if self.compression_enabled and original_size > self.compression_threshold:
            compressed = gzip.compress(data, compresslevel=6)
            if len(compressed) < original_size:
                data = compressed
                compression_ratio = len(compressed) / original_size
                logger.debug(
                    f"Compressed checkpoint {checkpoint.checkpoint_id}: "
                    f"{original_size} -> {len(data)} bytes ({compression_ratio:.2f})"
                )

        # Always update compression ratio sum
        self.compression_ratio_sum += compression_ratio

        # Save to tiered storage
        key = checkpoint.checkpoint_id

        # Always save to memory for fast access
        await self.memory_storage.save(key, data)

        # Save to disk for durability
        await self.disk_storage.save(key, data)

        # Save to cloud if available (async, don't wait)
        if self.cloud_storage:
            asyncio.create_task(self._save_to_cloud(key, data))

        self.save_count += 1
        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Saved checkpoint {checkpoint.checkpoint_id} "
            f"({len(data)} bytes) in {duration_ms:.1f}ms"
        )

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Load checkpoint from storage."""
        start_time = time.time()

        # Try memory first (fastest)
        data = await self.memory_storage.load(checkpoint_id)
        source = "memory"

        # Try disk if not in memory
        if not data:
            data = await self.disk_storage.load(checkpoint_id)
            source = "disk"

            # Promote to memory if found
            if data:
                await self.memory_storage.save(checkpoint_id, data)

        # Try cloud as last resort
        if not data and self.cloud_storage:
            data = await self.cloud_storage.load(checkpoint_id)
            source = "cloud"

            # Promote to memory and disk if found
            if data:
                await self.memory_storage.save(checkpoint_id, data)
                await self.disk_storage.save(checkpoint_id, data)

        if not data:
            logger.warning(f"Checkpoint {checkpoint_id} not found")
            return None

        # Decompress if needed
        try:
            # Try to decompress first
            decompressed = gzip.decompress(data)
            data = decompressed
        except:
            # Not compressed or decompression failed
            pass

        # Deserialize
        try:
            checkpoint_dict = json.loads(data.decode("utf-8"))
            checkpoint = Checkpoint.from_dict(checkpoint_dict)

            self.load_count += 1
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Loaded checkpoint {checkpoint_id} from {source} "
                f"in {duration_ms:.1f}ms"
            )

            return checkpoint

        except Exception as e:
            logger.error(f"Failed to deserialize checkpoint {checkpoint_id}: {e}")
            return None

    async def load_latest_checkpoint(self, request_id: str) -> Optional[Checkpoint]:
        """Load the latest checkpoint for a request."""
        # List all checkpoints for request
        prefix = f"ckpt_{request_id}"

        # Check all storage tiers
        all_keys = set()
        all_keys.update(await self.memory_storage.list_keys(prefix))
        all_keys.update(await self.disk_storage.list_keys(prefix))
        if self.cloud_storage:
            all_keys.update(await self.cloud_storage.list_keys(prefix))

        if not all_keys:
            return None

        # Load all checkpoints and find latest by sequence
        checkpoints = []
        for key in all_keys:
            checkpoint = await self.load_checkpoint(key)
            if checkpoint and checkpoint.request_id == request_id:
                checkpoints.append(checkpoint)

        if not checkpoints:
            return None

        # Return checkpoint with highest sequence number
        return max(checkpoints, key=lambda c: c.sequence)

    async def delete_checkpoint(self, checkpoint_id: str) -> None:
        """Delete checkpoint from all storage tiers."""
        await self.memory_storage.delete(checkpoint_id)
        await self.disk_storage.delete(checkpoint_id)
        if self.cloud_storage:
            await self.cloud_storage.delete(checkpoint_id)

        logger.info(f"Deleted checkpoint {checkpoint_id}")

    async def _save_to_cloud(self, key: str, data: bytes) -> None:
        """Save to cloud storage asynchronously."""
        try:
            await self.cloud_storage.save(key, data)
            logger.debug(f"Saved checkpoint {key} to cloud storage")
        except Exception as e:
            logger.error(f"Failed to save checkpoint {key} to cloud: {e}")

    async def _garbage_collection_loop(self) -> None:
        """Periodically clean up old checkpoints."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self._garbage_collection()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Garbage collection error: {e}")

    async def _garbage_collection(self) -> None:
        """Clean up old checkpoints."""
        cutoff_time = datetime.now(dt.UTC) - timedelta(hours=self.retention_hours)
        deleted_count = 0

        # Get all checkpoint keys from disk (most complete list)
        all_keys = await self.disk_storage.list_keys("ckpt_")

        for key in all_keys:
            checkpoint = await self.load_checkpoint(key)
            if checkpoint:
                # Handle both timezone-aware and naive datetimes
                checkpoint_time = checkpoint.created_at
                if checkpoint_time.tzinfo is None:
                    # Assume naive datetime is UTC
                    checkpoint_time = checkpoint_time.replace(tzinfo=dt.UTC)

                if checkpoint_time < cutoff_time:
                    await self.delete_checkpoint(key)
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Garbage collection deleted {deleted_count} old checkpoints")

    def get_stats(self) -> Dict[str, Any]:
        """Get checkpoint manager statistics."""
        avg_compression_ratio = (
            self.compression_ratio_sum / self.save_count if self.save_count > 0 else 1.0
        )

        return {
            "save_count": self.save_count,
            "load_count": self.load_count,
            "avg_compression_ratio": avg_compression_ratio,
            "compression_enabled": self.compression_enabled,
            "retention_hours": self.retention_hours,
        }

    async def close(self) -> None:
        """Close checkpoint manager and cleanup."""
        if self._gc_task is not None:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
