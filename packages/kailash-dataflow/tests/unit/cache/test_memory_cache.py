"""
Unit Tests for In-Memory Cache

Tests the InMemoryCache implementation including LRU eviction,
TTL expiration, thread safety, and performance characteristics.

Tier: 1 (Unit - No external dependencies)
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import pytest


class TestInMemoryCacheBasics:
    """Test basic cache operations."""

    def test_cache_initialization(self):
        """Test cache initialization with default parameters."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()
        assert cache.max_size == 1000
        assert cache.ttl == 300
        assert len(cache.cache) == 0

    def test_cache_initialization_custom_params(self):
        """Test cache initialization with custom parameters."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=500, ttl=600)
        assert cache.max_size == 500
        assert cache.ttl == 600

    @pytest.mark.asyncio
    async def test_get_set_basic(self):
        """Test basic get/set operations."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        # Set value
        await cache.set("key1", {"data": "value1"})

        # Get value
        result = await cache.get("key1")
        assert result == {"data": "value1"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Test getting a non-existent key returns None."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self):
        """Test that set overwrites existing values."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        await cache.set("key1", {"data": "original"})
        await cache.set("key1", {"data": "updated"})

        result = await cache.get("key1")
        assert result == {"data": "updated"}


class TestInMemoryCacheTTL:
    """Test TTL expiration functionality."""

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(ttl=1)  # 1 second TTL

        await cache.set("key1", {"data": "value1"})

        # Should be available immediately
        result = await cache.get("key1")
        assert result == {"data": "value1"}

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_ttl_per_key(self):
        """Test custom TTL per key."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(ttl=10)  # Default 10 seconds

        # Set with custom TTL
        await cache.set("key1", {"data": "value1"}, ttl=1)

        # Should expire after 1 second
        await asyncio.sleep(1.1)

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entries_removed_on_access(self):
        """Test that expired entries are removed on access."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(ttl=1)

        await cache.set("key1", {"data": "value1"})
        await asyncio.sleep(1.1)

        # Access expired key
        await cache.get("key1")

        # Key should be removed from cache
        assert "key1" not in cache.cache


class TestInMemoryCacheLRU:
    """Test LRU eviction functionality."""

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test that oldest entries are evicted when cache is full."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=3, ttl=60)

        # Fill cache to capacity
        await cache.set("key1", {"data": "value1"})
        await cache.set("key2", {"data": "value2"})
        await cache.set("key3", {"data": "value3"})

        # Add one more - should evict key1 (oldest)
        await cache.set("key4", {"data": "value4"})

        # key1 should be evicted
        assert await cache.get("key1") is None

        # Others should still exist
        assert await cache.get("key2") == {"data": "value2"}
        assert await cache.get("key3") == {"data": "value3"}
        assert await cache.get("key4") == {"data": "value4"}

    @pytest.mark.asyncio
    async def test_lru_access_updates_order(self):
        """Test that accessing a key moves it to the end (most recent)."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=3, ttl=60)

        # Fill cache
        await cache.set("key1", {"data": "value1"})
        await cache.set("key2", {"data": "value2"})
        await cache.set("key3", {"data": "value3"})

        # Access key1 (moves to end)
        await cache.get("key1")

        # Add new key - should evict key2 (now oldest)
        await cache.set("key4", {"data": "value4"})

        # key2 should be evicted (not key1)
        assert await cache.get("key2") is None
        assert await cache.get("key1") == {"data": "value1"}


class TestInMemoryCacheInvalidation:
    """Test cache invalidation functionality."""

    @pytest.mark.asyncio
    async def test_invalidate_model(self):
        """Test invalidating all entries for a model."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        # Add entries for multiple models
        await cache.set("dataflow:User:list:abc123", {"users": []})
        await cache.set("dataflow:User:list:def456", {"users": []})
        await cache.set("dataflow:Product:list:xyz789", {"products": []})

        # Invalidate User model
        await cache.invalidate_model("User")

        # User entries should be removed
        assert await cache.get("dataflow:User:list:abc123") is None
        assert await cache.get("dataflow:User:list:def456") is None

        # Product entry should remain
        assert await cache.get("dataflow:Product:list:xyz789") == {"products": []}

    @pytest.mark.asyncio
    async def test_clear_all(self):
        """Test clearing all cache entries."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        await cache.set("key1", {"data": "value1"})
        await cache.set("key2", {"data": "value2"})
        await cache.set("key3", {"data": "value3"})

        # Clear all
        await cache.clear()

        # All entries should be removed
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None
        assert len(cache.cache) == 0


class TestInMemoryCacheMetrics:
    """Test cache metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_hits_and_misses(self):
        """Test that hits and misses are tracked."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        await cache.set("key1", {"data": "value1"})

        # Cache hit
        await cache.get("key1")

        # Cache miss
        await cache.get("key2")

        metrics = await cache.get_metrics()
        assert metrics["hits"] == 1
        assert metrics["misses"] == 1
        assert metrics["hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_metrics_evictions(self):
        """Test that evictions are tracked."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=2, ttl=60)

        await cache.set("key1", {"data": "value1"})
        await cache.set("key2", {"data": "value2"})
        await cache.set("key3", {"data": "value3"})  # Triggers eviction

        metrics = await cache.get_metrics()
        assert metrics["evictions"] == 1

    @pytest.mark.asyncio
    async def test_metrics_invalidations(self):
        """Test that invalidations are tracked."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        await cache.set("dataflow:User:list:abc", {"users": []})
        await cache.invalidate_model("User")

        metrics = await cache.get_metrics()
        assert metrics["invalidations"] >= 1


class TestInMemoryCacheThreadSafety:
    """Test thread safety of cache operations."""

    @pytest.mark.asyncio
    async def test_concurrent_writes(self):
        """Test concurrent write operations."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        async def write_values(start: int, count: int):
            for i in range(start, start + count):
                await cache.set(f"key{i}", {"value": i})

        # Run concurrent writes
        await asyncio.gather(
            write_values(0, 100),
            write_values(100, 100),
            write_values(200, 100),
        )

        # All writes should succeed
        result = await cache.get("key50")
        assert result == {"value": 50}

        result = await cache.get("key150")
        assert result == {"value": 150}

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self):
        """Test concurrent read and write operations."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()

        # Prepopulate cache
        for i in range(50):
            await cache.set(f"key{i}", {"value": i})

        async def reader():
            results = []
            for i in range(50):
                result = await cache.get(f"key{i}")
                results.append(result)
            return results

        async def writer():
            for i in range(50, 100):
                await cache.set(f"key{i}", {"value": i})

        # Run concurrent reads and writes
        read_results, _ = await asyncio.gather(reader(), writer())

        # All reads should succeed (may be None if not written yet)
        assert len(read_results) == 50


class TestInMemoryCachePerformance:
    """Test cache performance characteristics."""

    @pytest.mark.asyncio
    async def test_performance_get_operation(self):
        """Test that get operations are fast (<1ms)."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache()
        await cache.set("key1", {"data": "value1"})

        # Measure get performance
        start = time.perf_counter()
        for _ in range(1000):
            await cache.get("key1")
        elapsed = time.perf_counter() - start

        # Should average <1ms per operation (1000 ops in <1 second)
        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Average get time: {avg_time_ms:.3f}ms"

    @pytest.mark.asyncio
    async def test_performance_set_operation(self):
        """Test that set operations are fast (<1ms)."""
        from dataflow.cache.memory_cache import InMemoryCache

        cache = InMemoryCache(max_size=5000)

        # Measure set performance
        start = time.perf_counter()
        for i in range(1000):
            await cache.set(f"key{i}", {"data": f"value{i}"})
        elapsed = time.perf_counter() - start

        # Should average <1ms per operation
        avg_time_ms = (elapsed / 1000) * 1000
        assert avg_time_ms < 1.0, f"Average set time: {avg_time_ms:.3f}ms"
