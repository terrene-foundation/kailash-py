"""
Tier 1 Unit Tests - AsyncRedisCacheAdapter

Tests the async wrapper for synchronous RedisCacheManager with mocked RedisCacheManager.
Verifies async wrappers work correctly and executor pattern functions properly.

Test Coverage:
- Async method wrappers (get, set, delete, etc.)
- Executor pattern correctness
- Thread pool integration
- Error handling
- Stats and metrics methods
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter


class TestAsyncRedisCacheAdapterBasics:
    """Test basic async wrapper functionality."""

    @pytest.fixture
    def mock_redis_manager(self):
        """Create mock RedisCacheManager."""
        mock = MagicMock()
        # Configure common return values
        mock.get.return_value = {"data": "value"}
        mock.set.return_value = True
        mock.delete.return_value = 1
        mock.delete_many.return_value = 2
        mock.exists.return_value = True
        mock.clear_pattern.return_value = 5
        mock.can_cache.return_value = True
        mock.ping.return_value = True
        mock.get_stats.return_value = {
            "status": "connected",
            "hit_rate": 0.85,
            "hits": 850,
            "misses": 150,
        }
        mock.get_ttl.return_value = 300
        mock.extend_ttl.return_value = True
        mock.set_many.return_value = True
        mock.get_many.return_value = {"key1": "value1", "key2": "value2"}
        mock.warmup.return_value = True
        return mock

    @pytest.fixture
    def adapter(self, mock_redis_manager):
        """Create AsyncRedisCacheAdapter with mocked manager."""
        return AsyncRedisCacheAdapter(mock_redis_manager)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialization(self, mock_redis_manager):
        """Test adapter initialization."""
        adapter = AsyncRedisCacheAdapter(mock_redis_manager, max_workers=4)

        assert adapter.redis_manager is mock_redis_manager
        assert adapter._executor is not None
        assert adapter._executor._max_workers == 4

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_async_wrapper(self, adapter, mock_redis_manager):
        """Test async get() wraps sync manager.get()."""
        result = await adapter.get("test_key")

        # Verify async wrapper works
        assert result == {"data": "value"}

        # Verify sync method was called
        mock_redis_manager.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_set_async_wrapper(self, adapter, mock_redis_manager):
        """Test async set() wraps sync manager.set()."""
        result = await adapter.set("test_key", {"data": "value"}, ttl=600)

        # Verify async wrapper works
        assert result is True

        # Verify sync method was called with correct args
        mock_redis_manager.set.assert_called_once_with(
            "test_key", {"data": "value"}, 600
        )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_async_wrapper(self, adapter, mock_redis_manager):
        """Test async delete() wraps sync manager.delete()."""
        result = await adapter.delete("test_key")

        assert result == 1
        mock_redis_manager.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_many_async_wrapper(self, adapter, mock_redis_manager):
        """Test async delete_many() wraps sync manager.delete_many()."""
        keys = ["key1", "key2"]
        result = await adapter.delete_many(keys)

        assert result == 2
        mock_redis_manager.delete_many.assert_called_once_with(keys)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_exists_async_wrapper(self, adapter, mock_redis_manager):
        """Test async exists() wraps sync manager.exists()."""
        result = await adapter.exists("test_key")

        assert result is True
        mock_redis_manager.exists.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_clear_pattern_async_wrapper(self, adapter, mock_redis_manager):
        """Test async clear_pattern() wraps sync manager.clear_pattern()."""
        result = await adapter.clear_pattern("user:*")

        assert result == 5
        mock_redis_manager.clear_pattern.assert_called_once_with("user:*")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_can_cache_async_wrapper(self, adapter, mock_redis_manager):
        """Test async can_cache() wraps sync manager.can_cache()."""
        result = await adapter.can_cache()

        assert result is True
        # can_cache is a property/method with no args
        mock_redis_manager.can_cache.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_ping_async_wrapper(self, adapter, mock_redis_manager):
        """Test async ping() wraps sync manager.ping()."""
        result = await adapter.ping()

        assert result is True
        mock_redis_manager.ping.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_stats_async_wrapper(self, adapter, mock_redis_manager):
        """Test async get_stats() wraps sync manager.get_stats()."""
        result = await adapter.get_stats()

        assert result["status"] == "connected"
        assert result["hit_rate"] == 0.85
        mock_redis_manager.get_stats.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_ttl_async_wrapper(self, adapter, mock_redis_manager):
        """Test async get_ttl() wraps sync manager.get_ttl()."""
        result = await adapter.get_ttl("test_key")

        assert result == 300
        mock_redis_manager.get_ttl.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_extend_ttl_async_wrapper(self, adapter, mock_redis_manager):
        """Test async extend_ttl() wraps sync manager.extend_ttl()."""
        result = await adapter.extend_ttl("test_key", 600)

        assert result is True
        mock_redis_manager.extend_ttl.assert_called_once_with("test_key", 600)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_set_many_async_wrapper(self, adapter, mock_redis_manager):
        """Test async set_many() wraps sync manager.set_many()."""
        items = [("key1", "value1", 300), ("key2", "value2", None)]
        result = await adapter.set_many(items)

        assert result is True
        mock_redis_manager.set_many.assert_called_once_with(items)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_many_async_wrapper(self, adapter, mock_redis_manager):
        """Test async get_many() wraps sync manager.get_many()."""
        keys = ["key1", "key2"]
        result = await adapter.get_many(keys)

        assert result == {"key1": "value1", "key2": "value2"}
        mock_redis_manager.get_many.assert_called_once_with(keys)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_warmup_async_wrapper(self, adapter, mock_redis_manager):
        """Test async warmup() wraps sync manager.warmup()."""
        data = [("key1", "value1"), ("key2", "value2")]
        result = await adapter.warmup(data)

        assert result is True
        mock_redis_manager.warmup.assert_called_once_with(data)


class TestAsyncRedisCacheAdapterConcurrency:
    """Test concurrent async operations."""

    @pytest.fixture
    def mock_redis_manager(self):
        """Create mock with async-safe behavior."""
        mock = MagicMock()
        mock.get.return_value = {"data": "value"}
        mock.set.return_value = True
        return mock

    @pytest.fixture
    def adapter(self, mock_redis_manager):
        """Create adapter."""
        return AsyncRedisCacheAdapter(mock_redis_manager)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_concurrent_get_operations(self, adapter, mock_redis_manager):
        """Test multiple concurrent get() operations."""
        # Execute 10 concurrent get operations
        tasks = [adapter.get(f"key_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        assert all(r == {"data": "value"} for r in results)

        # Verify all calls made
        assert mock_redis_manager.get.call_count == 10

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_concurrent_mixed_operations(self, adapter, mock_redis_manager):
        """Test mix of get/set/delete operations concurrently."""
        mock_redis_manager.delete.return_value = 1
        mock_redis_manager.exists.return_value = True  # Explicit mock return

        tasks = [
            adapter.get("key1"),
            adapter.set("key2", "value2"),
            adapter.delete("key3"),
            adapter.exists("key4"),
            adapter.get("key5"),
        ]

        results = await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(results) == 5
        assert results[0] == {"data": "value"}  # get
        assert results[1] is True  # set
        assert results[2] == 1  # delete
        assert results[3] is True  # exists
        assert results[4] == {"data": "value"}  # get


class TestAsyncRedisCacheAdapterErrorHandling:
    """Test error handling in async wrappers."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_exception_propagates(self):
        """Test exceptions from sync manager.get() propagate through async wrapper."""
        mock_manager = MagicMock()
        mock_manager.get.side_effect = ValueError("Redis connection failed")

        adapter = AsyncRedisCacheAdapter(mock_manager)

        with pytest.raises(ValueError, match="Redis connection failed"):
            await adapter.get("test_key")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_set_exception_propagates(self):
        """Test exceptions from sync manager.set() propagate."""
        mock_manager = MagicMock()
        mock_manager.set.side_effect = RuntimeError("Write failed")

        adapter = AsyncRedisCacheAdapter(mock_manager)

        with pytest.raises(RuntimeError, match="Write failed"):
            await adapter.set("test_key", "value")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_exception_propagates(self):
        """Test exceptions from sync manager.delete() propagate."""
        mock_manager = MagicMock()
        mock_manager.delete.side_effect = ConnectionError("Connection lost")

        adapter = AsyncRedisCacheAdapter(mock_manager)

        with pytest.raises(ConnectionError, match="Connection lost"):
            await adapter.delete("test_key")


class TestAsyncRedisCacheAdapterCleanup:
    """Test executor cleanup."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_executor_shutdown_on_delete(self):
        """Test executor is shut down when adapter is deleted."""
        mock_manager = MagicMock()
        adapter = AsyncRedisCacheAdapter(mock_manager)

        # Get reference to executor
        executor = adapter._executor

        # Delete adapter
        del adapter

        # Executor should be shut down (verify it's closed)
        # Note: ThreadPoolExecutor doesn't have a simple "is_shutdown" flag
        # We verify by ensuring we can't submit new tasks
        with pytest.raises(RuntimeError):
            executor.submit(lambda: None)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_adapters_independent_executors(self):
        """Test multiple adapters have independent executors."""
        mock_manager1 = MagicMock()
        mock_manager2 = MagicMock()

        adapter1 = AsyncRedisCacheAdapter(mock_manager1, max_workers=2)
        adapter2 = AsyncRedisCacheAdapter(mock_manager2, max_workers=4)

        # Executors should be independent
        assert adapter1._executor is not adapter2._executor
        assert adapter1._executor._max_workers == 2
        assert adapter2._executor._max_workers == 4

        # Cleanup
        del adapter1
        del adapter2


class TestAsyncRedisCacheAdapterEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_returns_none(self):
        """Test get() correctly handles None return from manager."""
        mock_manager = MagicMock()
        mock_manager.get.return_value = None

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.get("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_set_with_none_ttl(self):
        """Test set() with None TTL (use default)."""
        mock_manager = MagicMock()
        mock_manager.set.return_value = True

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.set("key", "value", ttl=None)

        assert result is True
        mock_manager.set.assert_called_once_with("key", "value", None)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_nonexistent_key(self):
        """Test delete() returns 0 for nonexistent key."""
        mock_manager = MagicMock()
        mock_manager.delete.return_value = 0

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.delete("nonexistent")

        assert result == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_many_empty_list(self):
        """Test delete_many() with empty list."""
        mock_manager = MagicMock()
        mock_manager.delete_many.return_value = 0

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.delete_many([])

        assert result == 0
        mock_manager.delete_many.assert_called_once_with([])

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_ttl_key_not_exist(self):
        """Test get_ttl() returns -2 for nonexistent key."""
        mock_manager = MagicMock()
        mock_manager.get_ttl.return_value = -2

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.get_ttl("nonexistent")

        assert result == -2

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_ttl_no_expiration(self):
        """Test get_ttl() returns -1 for key with no TTL."""
        mock_manager = MagicMock()
        mock_manager.get_ttl.return_value = -1

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.get_ttl("persistent_key")

        assert result == -1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_many_partial_results(self):
        """Test get_many() with some missing keys."""
        mock_manager = MagicMock()
        mock_manager.get_many.return_value = {"key1": "value1"}  # key2 missing

        adapter = AsyncRedisCacheAdapter(mock_manager)
        result = await adapter.get_many(["key1", "key2"])

        assert "key1" in result
        assert "key2" not in result


class TestAsyncRedisCacheAdapterIntegration:
    """Integration-style tests with more realistic scenarios (still mocked)."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cache_hit_miss_workflow(self):
        """Test realistic cache hit/miss workflow."""
        mock_manager = MagicMock()

        # First call: cache miss (returns None)
        # Second call: cache hit (returns value)
        mock_manager.get.side_effect = [None, {"data": "cached_value"}]
        mock_manager.set.return_value = True

        adapter = AsyncRedisCacheAdapter(mock_manager)

        # Cache miss
        result1 = await adapter.get("user:123")
        assert result1 is None

        # Store in cache
        await adapter.set("user:123", {"data": "cached_value"})

        # Cache hit
        result2 = await adapter.get("user:123")
        assert result2 == {"data": "cached_value"}

        # Verify call sequence
        assert mock_manager.get.call_count == 2
        assert mock_manager.set.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cache_invalidation_workflow(self):
        """Test cache invalidation workflow."""
        mock_manager = MagicMock()
        mock_manager.clear_pattern.return_value = 3

        adapter = AsyncRedisCacheAdapter(mock_manager)

        # Invalidate all user cache entries
        deleted_count = await adapter.clear_pattern("user:*")

        assert deleted_count == 3
        mock_manager.clear_pattern.assert_called_once_with("user:*")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_bulk_operations_workflow(self):
        """Test bulk set/get operations."""
        mock_manager = MagicMock()
        mock_manager.set_many.return_value = True
        mock_manager.get_many.return_value = {
            "user:1": {"name": "Alice"},
            "user:2": {"name": "Bob"},
        }

        adapter = AsyncRedisCacheAdapter(mock_manager)

        # Bulk set
        items = [
            ("user:1", {"name": "Alice"}, 300),
            ("user:2", {"name": "Bob"}, 300),
        ]
        set_result = await adapter.set_many(items)
        assert set_result is True

        # Bulk get
        get_result = await adapter.get_many(["user:1", "user:2"])
        assert get_result["user:1"]["name"] == "Alice"
        assert get_result["user:2"]["name"] == "Bob"
