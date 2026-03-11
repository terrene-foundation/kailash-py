"""
Integration Tests for Query Cache System

Tests the complete query caching system with real PostgreSQL database,
including auto-detection, cache operations, and invalidation.

Tier: 2 (Integration - Real PostgreSQL, NO MOCKING)
"""

import asyncio
import os
import time

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def test_db_url():
    """Provide test database URL."""
    return os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.mark.integration
@pytest.mark.asyncio
class TestQueryCacheBasics:
    """Test basic query caching functionality."""

    async def test_cache_initialization_with_redis_unavailable(self, test_db_url):
        """Test that cache initializes with async backend (InMemoryCache or AsyncRedisCacheAdapter)."""
        from dataflow import DataFlow

        db = DataFlow(
            test_db_url,
            enable_query_cache=True,  # Enable caching
            cache_ttl=300,
        )

        # Cache should initialize with async backend (InMemoryCache if Redis unavailable, AsyncRedisCacheAdapter if available)
        assert db._cache_integration is not None
        backend_name = db._cache_integration.cache_manager.__class__.__name__
        assert backend_name in ["InMemoryCache", "AsyncRedisCacheAdapter"]

    async def test_cache_disabled_by_default(self, test_db_url):
        """Test that cache is disabled by default."""
        from dataflow import DataFlow

        db = DataFlow(test_db_url)

        # Cache should not be initialized
        assert db._cache_integration is None

    async def test_cache_explicit_enable(self, test_db_url):
        """Test explicit cache enablement."""
        from dataflow import DataFlow

        db = DataFlow(
            test_db_url,
            enable_query_cache=True,
            cache_ttl=600,
            cache_max_size=5000,
        )

        # Cache should be initialized
        assert db._cache_integration is not None

        # Verify configuration
        cache_manager = db._cache_integration.cache_manager
        if cache_manager.__class__.__name__ == "InMemoryCache":
            assert cache_manager.ttl == 600
            assert cache_manager.max_size == 5000


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheBackendAutoDetection:
    """Test cache backend auto-detection in real scenarios."""

    async def test_auto_detection_with_no_redis(self, test_db_url):
        """Test that system initializes cache backend (either InMemoryCache or AsyncRedisCacheAdapter)."""
        from dataflow import DataFlow

        # Enable caching (backend auto-detection)
        db = DataFlow(
            test_db_url,
            enable_query_cache=True,
            cache_redis_url="redis://nonexistent-server:6379/0",
        )

        # Should initialize with async backend (InMemoryCache if Redis unavailable, AsyncRedisCacheAdapter if available)
        assert db._cache_integration is not None
        backend_name = db._cache_integration.cache_manager.__class__.__name__
        assert backend_name in ["InMemoryCache", "AsyncRedisCacheAdapter"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheMetrics:
    """Test cache metrics tracking."""

    async def test_cache_hit_miss_metrics(self, test_db_url):
        """Test that cache hits and misses are tracked correctly."""
        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        # Perform cache operations
        await cache_manager.set("test_key_1", {"data": "value1"})
        await cache_manager.set("test_key_2", {"data": "value2"})

        # Cache hits
        await cache_manager.get("test_key_1")
        await cache_manager.get("test_key_2")

        # Cache misses
        await cache_manager.get("nonexistent_key")

        # Check metrics
        metrics = await cache_manager.get_metrics()
        assert metrics["hits"] == 2
        assert metrics["misses"] == 1
        assert metrics["hit_rate"] == 2 / 3  # 2 hits out of 3 total

    async def test_cache_eviction_metrics(self, test_db_url):
        """Test that cache evictions are tracked."""
        from dataflow import DataFlow

        db = DataFlow(
            test_db_url,
            enable_query_cache=True,
            cache_max_size=3,  # Small size to trigger evictions
        )

        cache_manager = db._cache_integration.cache_manager

        # Fill cache beyond capacity
        await cache_manager.set("key1", {"data": "value1"})
        await cache_manager.set("key2", {"data": "value2"})
        await cache_manager.set("key3", {"data": "value3"})
        await cache_manager.set("key4", {"data": "value4"})  # Triggers eviction

        # Check metrics
        metrics = await cache_manager.get_metrics()
        assert metrics["evictions"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheInvalidation:
    """Test cache invalidation patterns."""

    async def test_invalidate_model_cache(self, test_db_url):
        """Test invalidating all cache entries for a model."""
        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        # Add cache entries for multiple models
        await cache_manager.set("dataflow:User:list:abc123", {"users": []})
        await cache_manager.set("dataflow:User:list:def456", {"users": []})
        await cache_manager.set("dataflow:Product:list:xyz789", {"products": []})

        # Invalidate User model
        count = await cache_manager.invalidate_model("User")

        # User entries should be removed
        assert await cache_manager.get("dataflow:User:list:abc123") is None
        assert await cache_manager.get("dataflow:User:list:def456") is None

        # Product entry should remain
        assert await cache_manager.get("dataflow:Product:list:xyz789") == {
            "products": []
        }

        # Count should match
        assert count == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheTTL:
    """Test cache TTL expiration."""

    async def test_cache_entry_expires_after_ttl(self, test_db_url):
        """Test that cache entries expire after TTL."""
        from dataflow import DataFlow

        db = DataFlow(
            test_db_url,
            enable_query_cache=True,
            cache_ttl=1,  # 1 second TTL
        )

        cache_manager = db._cache_integration.cache_manager

        # Set cache entry
        await cache_manager.set("test_key", {"data": "value"})

        # Should be available immediately
        result = await cache_manager.get("test_key")
        assert result == {"data": "value"}

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache_manager.get("test_key")
        assert result is None

    async def test_custom_ttl_per_entry(self, test_db_url):
        """Test custom TTL per cache entry."""
        from dataflow import DataFlow

        db = DataFlow(
            test_db_url,
            enable_query_cache=True,
            cache_ttl=10,  # Default 10 seconds
        )

        cache_manager = db._cache_integration.cache_manager

        # Set entry with custom TTL
        await cache_manager.set("short_ttl_key", {"data": "value"}, ttl=1)

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache_manager.get("short_ttl_key")
        assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheConcurrency:
    """Test cache behavior under concurrent operations."""

    async def test_concurrent_cache_writes(self, test_db_url):
        """Test concurrent write operations to cache."""
        import asyncio

        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        async def write_values(start: int, count: int):
            for i in range(start, start + count):
                await cache_manager.set(f"key{i}", {"value": i})

        # Run concurrent writes
        await asyncio.gather(
            write_values(0, 50),
            write_values(50, 50),
            write_values(100, 50),
        )

        # Verify all writes succeeded
        result = await cache_manager.get("key25")
        assert result == {"value": 25}

        result = await cache_manager.get("key75")
        assert result == {"value": 75}

        result = await cache_manager.get("key125")
        assert result == {"value": 125}

    async def test_concurrent_cache_reads_and_writes(self, test_db_url):
        """Test concurrent read and write operations."""
        import asyncio

        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        # Prepopulate cache
        for i in range(50):
            await cache_manager.set(f"key{i}", {"value": i})

        async def reader():
            results = []
            for i in range(50):
                result = await cache_manager.get(f"key{i}")
                results.append(result)
            return results

        async def writer():
            for i in range(50, 100):
                await cache_manager.set(f"key{i}", {"value": i})

        # Run concurrent operations
        read_results, _ = await asyncio.gather(reader(), writer())

        # All reads should succeed
        assert len(read_results) == 50
        assert all(r is not None for r in read_results)


@pytest.mark.integration
@pytest.mark.asyncio
class TestCachePerformance:
    """Test cache performance characteristics."""

    async def test_cache_improves_query_performance(self, test_db_url):
        """Test that caching provides performance improvement."""
        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        # First access (cache miss)
        key = "perf_test_key"
        start = time.perf_counter()
        await cache_manager.set(key, {"large_data": "x" * 1000})
        await cache_manager.get(key)  # Cache miss (but now cached)
        miss_time = time.perf_counter() - start

        # Second access (cache hit)
        start = time.perf_counter()
        result = await cache_manager.get(key)
        hit_time = time.perf_counter() - start

        # Cache hit should be faster (significantly so)
        # Note: This is a basic check; actual speedup depends on data size
        assert result is not None
        assert hit_time < miss_time

    async def test_cache_operations_are_fast(self, test_db_url):
        """Test that cache operations complete quickly."""
        from dataflow import DataFlow

        db = DataFlow(test_db_url, enable_query_cache=True)

        cache_manager = db._cache_integration.cache_manager

        # Measure set operation
        start = time.perf_counter()
        for i in range(100):
            await cache_manager.set(f"speed_key_{i}", {"data": i})
        set_time = time.perf_counter() - start

        # Measure get operation
        start = time.perf_counter()
        for i in range(100):
            await cache_manager.get(f"speed_key_{i}")
        get_time = time.perf_counter() - start

        # Operations should be fast (<100ms for 100 operations)
        assert set_time < 0.1, f"Set operations too slow: {set_time:.3f}s"
        assert get_time < 0.1, f"Get operations too slow: {get_time:.3f}s"
