"""
Tier 2 Integration Tests - ListNodeCacheIntegration with Real InMemoryCache

Tests ListNodeCacheIntegration with REAL InMemoryCache backend.
NO MOCKING - uses actual InMemoryCache instance to verify async interface works correctly.

Test Coverage:
- Cache hit/miss scenarios with real cache
- Async interface verification (await calls work correctly)
- Cache invalidation with real data
- Concurrent cache operations
- Cache TTL expiration
- Cache metadata generation
"""

import asyncio
import time

import pytest

from dataflow.cache.auto_detection import CacheBackend
from dataflow.cache.invalidation import CacheInvalidator
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.list_node_integration import ListNodeCacheIntegration
from dataflow.cache.memory_cache import InMemoryCache


class TestListNodeCacheIntegrationWithInMemoryCache:
    """Test ListNodeCacheIntegration with real InMemoryCache."""

    @pytest.fixture
    async def in_memory_cache(self):
        """Create real InMemoryCache instance."""
        cache = InMemoryCache(max_size=100, ttl=300)
        yield cache
        # Cleanup
        await cache.clear()

    @pytest.fixture
    def key_generator(self):
        """Create CacheKeyGenerator."""
        return CacheKeyGenerator()

    @pytest.fixture
    def invalidator(self, in_memory_cache):
        """Create CacheInvalidator with real cache."""
        return CacheInvalidator(in_memory_cache)

    @pytest.fixture
    def cache_integration(self, in_memory_cache, key_generator, invalidator):
        """Create ListNodeCacheIntegration with real components."""
        return ListNodeCacheIntegration(in_memory_cache, key_generator, invalidator)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_execute_with_cache_miss_then_hit(self, cache_integration):
        """Test cache miss followed by cache hit with real cache."""
        model_name = "User"
        query = "SELECT * FROM users WHERE id = ?"
        params = ["user-123"]

        # Mock executor function
        execution_count = 0

        async def executor():
            nonlocal execution_count
            execution_count += 1
            return {"id": "user-123", "name": "Alice"}

        # First call: cache miss
        result1 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
            cache_enabled=True,
        )

        # Verify cache miss
        assert result1["_cache"]["hit"] is False
        assert result1["_cache"]["source"] == "database"
        assert result1["id"] == "user-123"
        assert result1["name"] == "Alice"
        assert execution_count == 1

        # Second call: cache hit
        result2 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
            cache_enabled=True,
        )

        # Verify cache hit
        assert result2["_cache"]["hit"] is True
        assert result2["_cache"]["source"] == "cache"
        assert result2["id"] == "user-123"
        assert result2["name"] == "Alice"
        # Executor should NOT be called again
        assert execution_count == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_disabled_always_executes(self, cache_integration):
        """Test that cache_enabled=False always executes function."""
        execution_count = 0

        async def executor():
            nonlocal execution_count
            execution_count += 1
            return {"data": f"execution_{execution_count}"}

        # First call with cache disabled
        result1 = await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=[],
            executor_func=executor,
            cache_enabled=False,
        )

        assert result1["_cache"]["source"] == "direct"
        assert execution_count == 1

        # Second call - should execute again (cache disabled)
        result2 = await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=[],
            executor_func=executor,
            cache_enabled=False,
        )

        assert result2["_cache"]["source"] == "direct"
        assert execution_count == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_with_custom_ttl(self, cache_integration, in_memory_cache):
        """Test cache respects custom TTL."""
        model_name = "Session"
        query = "SELECT * FROM sessions"
        params = []

        async def executor():
            return {"session_id": "sess-123"}

        # Cache with 1 second TTL
        result1 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
            cache_enabled=True,
            cache_ttl=1,  # 1 second TTL
        )

        # Verify cached
        assert result1["_cache"]["hit"] is False

        # Immediate second call: cache hit
        result2 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
            cache_enabled=True,
            cache_ttl=1,
        )

        assert result2["_cache"]["hit"] is True

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Third call: cache miss (expired)
        execution_count = 0

        async def executor_with_counter():
            nonlocal execution_count
            execution_count += 1
            return {"session_id": "sess-123"}

        result3 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor_with_counter,
            cache_enabled=True,
            cache_ttl=1,
        )

        # Verify cache miss due to expiration
        assert result3["_cache"]["hit"] is False
        assert execution_count == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_key_generation_consistency(self, cache_integration):
        """Test that same query generates same cache key."""
        model_name = "Product"
        query = "SELECT * FROM products WHERE category = ?"
        params = ["electronics"]

        execution_count = 0

        async def executor():
            nonlocal execution_count
            execution_count += 1
            return {"product_id": "prod-123"}

        # First call
        result1 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
        )

        cache_key_1 = result1["_cache"]["key"]
        assert execution_count == 1

        # Second call with same parameters
        result2 = await cache_integration.execute_with_cache(
            model_name=model_name,
            query=query,
            params=params,
            executor_func=executor,
        )

        cache_key_2 = result2["_cache"]["key"]

        # Verify same cache key generated
        assert cache_key_1 == cache_key_2
        # Verify cache hit
        assert result2["_cache"]["hit"] is True
        # Executor called only once
        assert execution_count == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_key_override(self, cache_integration):
        """Test custom cache key override."""
        custom_key = "custom:cache:key:123"

        async def executor():
            return {"data": "value"}

        result = await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=[],
            executor_func=executor,
            cache_key_override=custom_key,
        )

        # Verify custom key used
        assert result["_cache"]["key"] == custom_key

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_metadata_structure(self, cache_integration):
        """Test cache metadata is correctly added to results."""

        async def executor():
            return {"user_id": "123", "name": "Alice"}

        result = await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=[],
            executor_func=executor,
        )

        # Verify metadata structure
        assert "_cache" in result
        assert "key" in result["_cache"]
        assert "hit" in result["_cache"]
        assert "source" in result["_cache"]
        assert "timestamp" in result["_cache"]

        # Verify data preserved
        assert result["user_id"] == "123"
        assert result["name"] == "Alice"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, cache_integration):
        """Test concurrent cache operations with real InMemoryCache."""
        execution_counts = {}

        async def make_executor(user_id):
            async def executor():
                if user_id not in execution_counts:
                    execution_counts[user_id] = 0
                execution_counts[user_id] += 1
                return {"user_id": user_id, "name": f"User{user_id}"}

            return executor

        # Create 10 concurrent requests (5 unique, 5 duplicates)
        tasks = []
        for i in range(10):
            user_id = f"user-{i % 5}"  # 5 unique users
            executor = await make_executor(user_id)
            task = cache_integration.execute_with_cache(
                model_name="User",
                query="SELECT * FROM users WHERE id = ?",
                params=[user_id],
                executor_func=executor,
            )
            tasks.append(task)

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        # Verify all completed
        assert len(results) == 10

        # Verify each unique user was only executed once
        for user_id in [f"user-{i}" for i in range(5)]:
            # Should be executed exactly once (subsequent calls are cache hits)
            assert execution_counts[user_id] == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_stats_tracking(self, cache_integration, in_memory_cache):
        """Test cache statistics are tracked correctly."""

        async def executor():
            return {"data": "value"}

        # First call: cache miss
        await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=["user-1"],
            executor_func=executor,
        )

        # Second call: cache hit
        await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=["user-1"],
            executor_func=executor,
        )

        # Third call: different key, cache miss
        await cache_integration.execute_with_cache(
            model_name="User",
            query="SELECT *",
            params=["user-2"],
            executor_func=executor,
        )

        # Get stats
        stats = cache_integration.get_cache_stats()

        # Verify stats tracked
        assert "hits" in stats
        assert "misses" in stats
        assert stats["hits"] == 1  # One cache hit
        assert stats["misses"] == 2  # Two cache misses


class TestListNodeCacheIntegrationInvalidation:
    """
    Test cache invalidation with real InMemoryCache.

    NOTE: CacheInvalidator currently expects RedisCacheManager (sync interface),
    not async InMemoryCache. These tests verify manual invalidation patterns work correctly.
    Full CacheInvalidator integration will require async invalidator implementation.
    """

    @pytest.fixture
    async def in_memory_cache(self):
        """Create real InMemoryCache instance."""
        cache = InMemoryCache(max_size=100, ttl=300)
        yield cache
        await cache.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manual_cache_invalidation_with_clear_pattern(self, in_memory_cache):
        """Test manual cache invalidation using clear_pattern()."""
        model_name = "User"

        # Cache multiple entries
        await in_memory_cache.set(f"dataflow:{model_name}:list:all", [{"id": "1"}])
        await in_memory_cache.set(f"dataflow:{model_name}:list:active", [{"id": "2"}])
        await in_memory_cache.set(f"dataflow:{model_name}:record:1", {"id": "1"})

        # Verify caches exist
        assert await in_memory_cache.get(f"dataflow:{model_name}:list:all") is not None
        assert await in_memory_cache.get(f"dataflow:{model_name}:record:1") is not None

        # Manually invalidate all list caches
        deleted = await in_memory_cache.clear_pattern(f"dataflow:{model_name}:list:")

        # Verify list caches invalidated
        assert deleted == 2
        assert await in_memory_cache.get(f"dataflow:{model_name}:list:all") is None
        assert await in_memory_cache.get(f"dataflow:{model_name}:list:active") is None

        # Verify record cache still exists
        assert await in_memory_cache.get(f"dataflow:{model_name}:record:1") is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manual_record_invalidation(self, in_memory_cache):
        """Test manual invalidation of specific record cache."""
        model_name = "User"
        user_id = "user-123"

        # Cache a specific record
        await in_memory_cache.set(
            f"dataflow:{model_name}:record:{user_id}",
            {"id": user_id, "name": "Alice"},
        )

        # Verify cache exists
        cached = await in_memory_cache.get(f"dataflow:{model_name}:record:{user_id}")
        assert cached is not None

        # Manually invalidate
        deleted = await in_memory_cache.delete(
            f"dataflow:{model_name}:record:{user_id}"
        )

        # Verify invalidated
        assert deleted == 1
        cached_after = await in_memory_cache.get(
            f"dataflow:{model_name}:record:{user_id}"
        )
        assert cached_after is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_bulk_invalidation_with_delete_many(self, in_memory_cache):
        """Test bulk invalidation using delete_many()."""
        model_name = "User"

        # Cache multiple records
        keys = [f"dataflow:{model_name}:record:{i}" for i in range(5)]
        for i, key in enumerate(keys):
            await in_memory_cache.set(key, {"id": i})

        # Verify all cached
        for key in keys:
            assert await in_memory_cache.get(key) is not None

        # Bulk delete
        deleted = await in_memory_cache.delete_many(keys)

        # Verify all invalidated
        assert deleted == 5
        for key in keys:
            assert await in_memory_cache.get(key) is None


class TestListNodeCacheIntegrationWithAsyncRedis:
    """Test ListNodeCacheIntegration works with AsyncRedisCacheAdapter."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_can_cache_returns_true_for_inmemory(self):
        """Test can_cache() returns True for InMemoryCache."""
        cache = InMemoryCache()
        result = await cache.can_cache()
        assert result is True
        await cache.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_async_interface_compatibility(self):
        """Test InMemoryCache has async interface compatible with AsyncRedisCacheAdapter."""
        cache = InMemoryCache()

        # Verify all required async methods exist
        assert hasattr(cache, "get")
        assert hasattr(cache, "set")
        assert hasattr(cache, "delete")
        assert hasattr(cache, "delete_many")
        assert hasattr(cache, "exists")
        assert hasattr(cache, "clear_pattern")
        assert hasattr(cache, "can_cache")
        assert hasattr(cache, "ping")

        # Verify they are coroutines (async)
        import inspect

        assert inspect.iscoroutinefunction(cache.get)
        assert inspect.iscoroutinefunction(cache.set)
        assert inspect.iscoroutinefunction(cache.delete)
        assert inspect.iscoroutinefunction(cache.can_cache)

        await cache.clear()


class TestCacheBackendAutoDetection:
    """Test CacheBackend.auto_detect() with InMemoryCache fallback."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_auto_detect_returns_inmemory_when_redis_unavailable(self):
        """Test auto_detect() returns InMemoryCache when Redis is unavailable."""
        # Force Redis failure by using invalid connection URL
        cache = CacheBackend.auto_detect(redis_url="redis://invalid_host_12345:9999/0")

        # Should fall back to InMemoryCache
        assert isinstance(cache, InMemoryCache)

        # Verify it works
        result = await cache.set("test_key", "test_value")
        assert result is True

        value = await cache.get("test_key")
        assert value == "test_value"

        await cache.clear()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_inmemory_cache_fallback_functional(self):
        """Test InMemoryCache fallback is fully functional."""
        cache = InMemoryCache(max_size=10, ttl=300)

        # Test basic operations
        await cache.set("key1", {"data": "value1"})
        await cache.set("key2", {"data": "value2"})

        value1 = await cache.get("key1")
        assert value1 == {"data": "value1"}

        # Test delete
        deleted = await cache.delete("key1")
        assert deleted == 1

        value1_after = await cache.get("key1")
        assert value1_after is None

        # Test clear_pattern
        await cache.set("user:1", {"id": 1})
        await cache.set("user:2", {"id": 2})
        await cache.set("product:1", {"id": 1})

        deleted_count = await cache.clear_pattern("user:*")
        assert deleted_count == 2

        # Verify only user keys deleted
        assert await cache.get("user:1") is None
        assert await cache.get("user:2") is None
        assert await cache.get("product:1") is not None

        await cache.clear()
