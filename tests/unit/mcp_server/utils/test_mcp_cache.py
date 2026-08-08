"""Unit tests for MCP cache functionality.

Tests for the caching utilities in kailash_mcp.utils.cache.
This is a unit test file (Tier 1) for isolated component testing, where
mocking is permitted per rules/testing.md § 3-Tier Testing.

It previously lived under ``tests/integration/mcp_server/utils/`` while
mocking the Redis client with ``MagicMock`` — a Tier-2 tree forbids mocking
outright, so the file was in the wrong tier, not merely mislabelled: its own
docstring already said Tier 1. Moved here rather than re-pointed at a real
Redis, because every test in it exercises in-process cache logic and none of
them needs a server. A test that genuinely needs Redis belongs in
``tests/integration/`` against the real thing.
"""

import asyncio
import json
import re
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from kailash_mcp.utils.cache import (
    CacheManager,
    LRUCache,
    UnifiedCache,
    _global_cache_manager,
    aclear_all_caches,
    cached_query,
    clear_all_caches,
    get_cache_stats,
)


class _FakeRedis:
    """Deterministic in-process stand-in for ``redis.asyncio``.

    NOT a mock: it holds real state and implements SCAN/DELETE/GET/SETEX
    semantics, so a test can assert on the OBSERVABLE result (is the key gone?)
    rather than on which methods were called. A ``MagicMock`` auto-satisfies
    every attribute and returns truthy sentinels, which is exactly how the
    original Redis-clear test managed to assert nothing at all.

    Glob handling mirrors Redis: ``*`` is a wildcard and ``\\`` escapes the
    following character, so the escaping in ``_namespace_pattern`` is exercised
    for real instead of assumed.
    """

    def __init__(self, fail_on_scan: bool = False):
        self.store: dict[str, str] = {}
        self.flushdb_called = False
        self.flushall_called = False
        self._fail_on_scan = fail_on_scan

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    async def scan(self, cursor=0, match=None, count=None):
        if self._fail_on_scan:
            raise RuntimeError("scan exploded")
        return 0, [k for k in self.store if _redis_glob(match).fullmatch(k)]

    async def flushdb(self):
        self.flushdb_called = True
        self.store.clear()

    async def flushall(self):
        self.flushall_called = True
        self.store.clear()


def _redis_glob(pattern: str) -> "re.Pattern[str]":
    """Compile a Redis MATCH glob (``*`` wildcard, ``\\`` escape) to a regex."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "*" else "." if ch == "?" else re.escape(ch))
        i += 1
    return re.compile("".join(out))


class TestLRUCache:
    """Test LRU cache implementation."""

    def test_init_default_values(self):
        """Test cache initialization with default values."""
        cache = LRUCache()

        assert cache.max_size == 128
        assert cache.ttl == 300
        assert len(cache._cache) == 0
        assert len(cache._access_order) == 0
        assert cache._hits == 0
        assert cache._misses == 0
        assert cache._evictions == 0

    def test_init_custom_values(self):
        """Test cache initialization with custom values."""
        cache = LRUCache(max_size=64, ttl=600)

        assert cache.max_size == 64
        assert cache.ttl == 600

    def test_set_and_get_basic(self):
        """Test basic set and get operations."""
        cache = LRUCache()

        # Test setting and getting a value
        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"
        assert cache._hits == 1
        assert cache._misses == 0

    def test_get_nonexistent_key(self):
        """Test getting a non-existent key."""
        cache = LRUCache()

        result = cache.get("nonexistent")

        assert result is None
        assert cache._hits == 0
        assert cache._misses == 1

    def test_set_existing_key_updates_value(self):
        """Test that setting an existing key updates the value."""
        cache = LRUCache()

        cache.set("key1", "value1")
        cache.set("key1", "value2")
        result = cache.get("key1")

        assert result == "value2"
        assert len(cache._cache) == 1

    def test_ttl_expiration(self):
        """Test TTL expiration functionality."""
        cache = LRUCache(ttl=0.1)  # 0.1 second TTL for faster testing

        cache.set("key1", "value1")

        # Should get value immediately
        result = cache.get("key1")
        assert result == "value1"

        # Wait for TTL to expire using polling
        from datetime import datetime

        start_time = datetime.now()
        expired = False

        while (datetime.now() - start_time).total_seconds() < 0.5:
            result = cache.get("key1")
            if result is None:
                expired = True
                break
            time.sleep(0.02)

        # Should have expired
        assert expired, "Cache key did not expire within expected time"
        assert cache._misses == 1

    def test_ttl_disabled(self):
        """Test cache with TTL disabled (ttl=0)."""
        cache = LRUCache(ttl=0)

        cache.set("key1", "value1")

        # Wait to ensure no expiration
        time.sleep(0.1)

        result = cache.get("key1")
        assert result == "value1"

    def test_lru_eviction(self):
        """Test LRU eviction when max_size is reached."""
        cache = LRUCache(max_size=2)

        # Fill cache to capacity
        cache.set("key1", "value1")
        time.sleep(0.001)  # Ensure distinct timestamps
        cache.set("key2", "value2")
        time.sleep(0.001)  # Ensure distinct timestamps

        # Access key1 to make it recently used
        cache.get("key1")
        time.sleep(0.001)  # Ensure distinct timestamps

        # Add third key, should evict key2 (least recently used)
        cache.set("key3", "value3")

        assert cache.get("key1") == "value1"  # Should still exist
        assert cache.get("key2") is None  # Should be evicted
        assert cache.get("key3") == "value3"  # Should exist
        assert cache._evictions == 1

    def test_lru_access_order_update(self):
        """Test that accessing items updates their position in LRU order."""
        cache = LRUCache(max_size=3)

        cache.set("key1", "value1")
        time.sleep(0.001)  # Ensure distinct timestamps
        cache.set("key2", "value2")
        time.sleep(0.001)  # Ensure distinct timestamps
        cache.set("key3", "value3")
        time.sleep(0.001)  # Ensure distinct timestamps

        # Access key1 to make it recently used
        cache.get("key1")
        time.sleep(0.001)  # Ensure distinct timestamps

        # Add fourth key, should evict key2 (oldest unaccessed)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Should still exist
        assert cache.get("key2") is None  # Should be evicted
        assert cache.get("key3") == "value3"  # Should still exist
        assert cache.get("key4") == "value4"  # Should exist

    def test_clear_cache(self):
        """Test clearing all cache entries."""
        cache = LRUCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        assert len(cache._cache) == 2

        cache.clear()

        assert len(cache._cache) == 0
        assert len(cache._access_order) == 0

    def test_stats_empty_cache(self):
        """Test statistics for empty cache."""
        cache = LRUCache()

        stats = cache.stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["evictions"] == 0
        assert stats["hit_rate"] == 0
        assert stats["size"] == 0
        assert stats["max_size"] == 128
        assert stats["ttl"] == 300

    def test_stats_with_operations(self):
        """Test statistics after various operations."""
        cache = LRUCache(max_size=2)

        # Perform various operations
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # Hit
        cache.get("key3")  # Miss
        cache.set("key3", "value3")  # Eviction

        stats = cache.stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["evictions"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 2

    def test_thread_safety(self):
        """Test thread safety of cache operations."""
        cache = LRUCache(max_size=100)
        results = []

        def worker(thread_id):
            for i in range(10):
                key = f"key_{thread_id}_{i}"
                value = f"value_{thread_id}_{i}"
                cache.set(key, value)
                retrieved = cache.get(key)
                results.append(retrieved == value)

        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All operations should have succeeded
        assert all(results)

    def test_custom_ttl_per_key(self):
        """Test setting custom TTL per key (functionality not implemented)."""
        cache = LRUCache(ttl=300)

        # The current implementation doesn't support per-key TTL
        # This test documents the current behavior
        cache.set("key1", "value1", ttl=1)  # ttl parameter is accepted but not used

        # Value should still be accessible after 1 second since global TTL is 300
        time.sleep(0.1)
        result = cache.get("key1")
        assert result == "value1"

    def test_large_cache_operations(self):
        """Test cache operations with larger datasets."""
        cache = LRUCache(max_size=1000)

        # Set many values
        for i in range(500):
            cache.set(f"key_{i}", f"value_{i}")

        # Verify all values are accessible
        for i in range(500):
            result = cache.get(f"key_{i}")
            assert result == f"value_{i}"

        stats = cache.stats()
        assert stats["size"] == 500
        assert stats["hits"] == 500

    def test_eviction_empty_cache(self):
        """Test eviction behavior on empty cache."""
        cache = LRUCache(max_size=1)

        # This should not raise an exception
        cache._evict_lru()

        assert cache._evictions == 0


class TestUnifiedCache:
    """Test unified cache interface."""

    def test_init_memory_backend(self):
        """Test initialization with memory backend."""
        lru_cache = LRUCache(max_size=64, ttl=120)
        cache = UnifiedCache(name="test_cache", ttl=300, lru_cache=lru_cache)

        assert cache.name == "test_cache"
        assert cache.ttl == 300
        assert cache.lru_cache is lru_cache
        assert cache.redis_client is None
        assert cache.is_redis is False

    def test_init_redis_backend(self):
        """Test initialization with Redis backend."""
        mock_redis = MagicMock()
        cache = UnifiedCache(
            name="test_cache", ttl=300, redis_client=mock_redis, redis_prefix="test:"
        )

        assert cache.name == "test_cache"
        assert cache.ttl == 300
        assert cache.redis_client is mock_redis
        assert cache.redis_prefix == "test:"
        assert cache.is_redis is True

    def test_make_key_memory_backend(self):
        """Test key creation for memory backend."""
        cache = UnifiedCache(name="test_cache", lru_cache=LRUCache())

        key = cache._make_key("test_key")
        assert key == "test_key"

    def test_make_key_redis_backend(self):
        """Test key creation for Redis backend."""
        mock_redis = MagicMock()
        cache = UnifiedCache(
            name="test_cache", redis_client=mock_redis, redis_prefix="mcp:"
        )

        key = cache._make_key("test_key")
        assert key == "mcp:test_cache:test_key"

    def test_get_set_memory_backend(self):
        """Test get/set operations with memory backend."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

    def test_get_set_redis_backend_sync(self):
        """Test sync get/set operations with Redis backend (returns None/pass)."""
        mock_redis = MagicMock()
        cache = UnifiedCache(name="test_cache", redis_client=mock_redis)

        # Sync operations should return None/pass for Redis
        result = cache.get("key1")
        assert result is None

        # Set should pass without error
        cache.set("key1", "value1")

    @pytest.mark.asyncio
    async def test_aget_aset_memory_backend(self):
        """Test async get/set operations with memory backend."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        success = await cache.aset("key1", "value1")
        assert success is True

        result = await cache.aget("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_aget_aset_redis_backend(self):
        """Test async get/set operations with Redis backend."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = asyncio.Future()
        mock_redis.get.return_value.set_result(json.dumps("value1"))
        mock_redis.setex.return_value = asyncio.Future()
        mock_redis.setex.return_value.set_result(True)

        cache = UnifiedCache(name="test_cache", redis_client=mock_redis, ttl=300)

        # Test set
        success = await cache.aset("key1", "value1")
        assert success is True
        mock_redis.setex.assert_called_with("mcp:test_cache:key1", 300, '"value1"')

        # Test get
        result = await cache.aget("key1")
        assert result == "value1"
        mock_redis.get.assert_called_with("mcp:test_cache:key1")

    @pytest.mark.asyncio
    async def test_aget_redis_error(self):
        """Test Redis get operation with error."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")

        cache = UnifiedCache(name="test_cache", redis_client=mock_redis)

        result = await cache.aget("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_aset_redis_error(self):
        """Test Redis set operation with error."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis error")

        cache = UnifiedCache(name="test_cache", redis_client=mock_redis)

        success = await cache.aset("key1", "value1")
        assert success is False

    @pytest.mark.asyncio
    async def test_get_or_compute_cache_hit(self):
        """Test get_or_compute with cache hit."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        # Pre-populate cache
        await cache.aset("key1", "cached_value")

        # Mock compute function
        async def compute_func():
            return "computed_value"

        result = await cache.get_or_compute("key1", compute_func)
        assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_get_or_compute_cache_miss(self):
        """Test get_or_compute with cache miss."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        # Mock compute function
        async def compute_func():
            return "computed_value"

        result = await cache.get_or_compute("key1", compute_func)
        assert result == "computed_value"

        # Verify value is now cached
        cached_result = await cache.aget("key1")
        assert cached_result == "computed_value"

    @pytest.mark.asyncio
    async def test_get_or_compute_stampede_prevention(self):
        """Test cache stampede prevention with concurrent requests."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        compute_count = 0

        async def compute_func():
            nonlocal compute_count
            compute_count += 1
            await asyncio.sleep(0.1)  # Simulate slow computation
            return f"computed_value_{compute_count}"

        # Start multiple concurrent requests
        tasks = [
            cache.get_or_compute("key1", compute_func),
            cache.get_or_compute("key1", compute_func),
            cache.get_or_compute("key1", compute_func),
        ]

        results = await asyncio.gather(*tasks)

        # All should return the same value
        assert len(set(results)) == 1
        # Compute function should only be called once
        assert compute_count == 1

    @pytest.mark.asyncio
    async def test_get_or_compute_with_exception(self):
        """Test get_or_compute when compute function raises exception."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        async def compute_func():
            raise ValueError("Computation failed")

        with pytest.raises(ValueError, match="Computation failed"):
            await cache.get_or_compute("key1", compute_func)

    @pytest.mark.asyncio
    async def test_get_or_compute_custom_ttl(self):
        """Test get_or_compute with custom TTL."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache, ttl=300)

        async def compute_func():
            return "computed_value"

        result = await cache.get_or_compute("key1", compute_func, ttl=600)
        assert result == "computed_value"

    def test_clear_memory_backend(self):
        """Test clear operation with memory backend."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        cache.set("key1", "value1")
        cache.clear()

        result = cache.get("key1")
        assert result is None

    def test_sync_clear_refuses_on_redis_instead_of_silently_no_opping(self):
        """Sync ``clear()`` MUST refuse on Redis, not pretend to succeed.

        The defect this replaces: ``clear()`` executed ``pass`` on the Redis
        branch, so the cache reported a successful invalidation and went on
        serving every stale entry. A cache that lies about invalidating is
        worse than one that refuses, so the sync surface now raises and names
        the async replacement.

        The previous xfail-STRICT marker is REMOVED rather than left to
        self-clear: it asserted that SYNC ``clear()`` issues a Redis command,
        and the fix moves that contract to ``aclear()``, so the sync-shaped
        assertion can never XPASS. Its contract lives on in the aclear tests
        below.
        """
        cache = UnifiedCache(name="test_cache", redis_client=_FakeRedis())

        with pytest.raises(RuntimeError) as exc_info:
            cache.clear()

        message = str(exc_info.value)
        assert "aclear()" in message, (
            "the refusal must name the working replacement, or the caller has "
            f"no way forward: {message!r}"
        )
        assert "test_cache" in message, f"refusal does not name the cache: {message!r}"

    @pytest.mark.asyncio
    async def test_aclear_deletes_the_keys_it_wrote(self):
        """The real contract: after ``aclear()`` the entry is GONE.

        Read-back through the public ``aget`` surface, not the fake's internals
        — a deletion that does not change what a caller reads is not a
        deletion.
        """
        redis = _FakeRedis()
        cache = UnifiedCache(name="tools", redis_client=redis)

        await cache.aset("k1", {"v": 1})
        assert await cache.aget("k1") == {"v": 1}, "precondition: the key is cached"

        deleted = await cache.aclear()

        assert deleted == 1, f"aclear() reported {deleted} keys deleted, expected 1"
        assert await cache.aget("k1") is None, "the entry survived aclear()"

    @pytest.mark.asyncio
    async def test_aclear_never_flushes_the_shared_database(self):
        """FLUSHDB would destroy every other consumer's keys.

        This is the destructive-fix guard: the cheap way to make the test above
        pass is ``FLUSHDB``, which also wipes every sibling cache and every
        non-MCP consumer sharing the database.
        """
        redis = _FakeRedis()
        cache = UnifiedCache(name="tools", redis_client=redis)
        await cache.aset("k1", {"v": 1})

        await cache.aclear()

        assert not redis.flushdb_called, "aclear() issued FLUSHDB on a shared database"
        assert not redis.flushall_called, "aclear() issued FLUSHALL"

    @pytest.mark.asyncio
    async def test_aclear_leaves_a_sibling_caches_keys_intact(self):
        """Scoping is the whole safety property, so it is asserted directly."""
        redis = _FakeRedis()
        tools = UnifiedCache(name="tools", redis_client=redis)
        prompts = UnifiedCache(name="prompts", redis_client=redis)

        await tools.aset("k", {"owner": "tools"})
        await prompts.aset("k", {"owner": "prompts"})

        await tools.aclear()

        assert await tools.aget("k") is None, "the target cache was not cleared"
        assert await prompts.aget("k") == {
            "owner": "prompts"
        }, "aclear() deleted a SIBLING cache's keys — the namespace scope leaked"

    @pytest.mark.asyncio
    async def test_aclear_escapes_glob_metacharacters_in_the_cache_name(self):
        """A cache named ``tools*`` must not match ``tools-internal:``.

        Without escaping, the SCAN pattern ``mcp:tools*:*`` matches the sibling
        namespace and deletes its keys — the same destructive class as FLUSHDB,
        reached through the name instead of the command.
        """
        redis = _FakeRedis()
        globby = UnifiedCache(name="tools*", redis_client=redis)
        sibling = UnifiedCache(name="tools-internal", redis_client=redis)

        await globby.aset("k", {"owner": "globby"})
        await sibling.aset("k", {"owner": "sibling"})

        await globby.aclear()

        assert await sibling.aget("k") == {
            "owner": "sibling"
        }, "an unescaped glob in the cache name reached a sibling namespace"

    @pytest.mark.asyncio
    async def test_aclear_on_memory_backend_clears_and_reports_zero(self):
        """``aclear()`` works on both backends so callers need no branch."""
        cache = UnifiedCache(name="test_cache", lru_cache=LRUCache())
        cache.set("key1", "value1")

        deleted = await cache.aclear()

        assert deleted == 0, "memory backend deletes no REDIS keys"
        assert cache.get("key1") is None, "memory backend was not cleared"

    @pytest.mark.asyncio
    async def test_aclear_reraises_rather_than_swallowing_a_redis_failure(self):
        """A silently-failed clear is the defect class this method closes."""
        redis = _FakeRedis(fail_on_scan=True)
        cache = UnifiedCache(name="tools", redis_client=redis)

        with pytest.raises(RuntimeError, match="scan exploded"):
            await cache.aclear()

    def test_stats_memory_backend(self):
        """Test stats operation with memory backend."""
        lru_cache = LRUCache()
        cache = UnifiedCache(name="test_cache", lru_cache=lru_cache)

        stats = cache.stats()
        assert "hits" in stats
        assert "misses" in stats

    def test_stats_redis_backend(self):
        """Test stats operation with Redis backend."""
        mock_redis = MagicMock()
        cache = UnifiedCache(name="test_cache", redis_client=mock_redis)

        stats = cache.stats()
        assert stats["backend"] == "redis"
        assert stats["name"] == "test_cache"


class TestCacheManager:
    """Test cache manager functionality."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        manager = CacheManager()

        assert manager.enabled is True
        assert manager.default_ttl == 300
        assert manager.backend == "memory"
        assert manager.config == {}
        assert len(manager._caches) == 0

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        config = {"prefix": "test:", "max_connections": 10}
        manager = CacheManager(
            enabled=False, default_ttl=600, backend="redis", config=config
        )

        assert manager.enabled is False
        assert manager.default_ttl == 600
        assert manager.backend == "redis"
        assert manager.config == config

    def test_get_cache_memory_backend(self):
        """Test getting cache with memory backend."""
        manager = CacheManager()

        cache = manager.get_cache("test_cache", max_size=64, ttl=120)

        assert isinstance(cache, UnifiedCache)
        assert cache.name == "test_cache"
        assert cache.ttl == 120
        assert cache.lru_cache is not None
        assert cache.is_redis is False

    def test_get_cache_redis_backend_no_redis(self):
        """Test getting cache with Redis backend when Redis is not available."""
        # Force Redis to be unavailable by setting _redis to None
        manager = CacheManager(backend="redis")
        manager._redis = None  # Simulate Redis not being available

        cache = manager.get_cache("test_cache")

        # When Redis is not available, should fallback to memory backend
        assert cache.lru_cache is not None
        assert cache.is_redis is False

    def test_get_cache_same_name_returns_same_instance(self):
        """Test that getting cache with same name returns same instance."""
        manager = CacheManager()

        cache1 = manager.get_cache("test_cache")
        cache2 = manager.get_cache("test_cache")

        assert cache1 is cache2

    def test_get_cache_default_ttl(self):
        """Test getting cache with default TTL."""
        manager = CacheManager(default_ttl=600)

        cache = manager.get_cache("test_cache")

        assert cache.ttl == 600

    def test_cached_decorator_disabled(self):
        """Test cached decorator when caching is disabled."""
        manager = CacheManager(enabled=False)

        @manager.cached("test_cache")
        def test_func(x):
            return x * 2

        result = test_func(5)
        assert result == 10

    def test_cached_decorator_sync_function(self):
        """Test cached decorator with synchronous function."""
        manager = CacheManager()

        call_count = 0

        @manager.cached("test_cache")
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call should execute function
        result1 = test_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call should use cache
        result2 = test_func(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment

    @pytest.mark.asyncio
    async def test_cached_decorator_async_function(self):
        """Test cached decorator with async function."""
        manager = CacheManager()

        call_count = 0

        @manager.cached("test_cache")
        async def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call should execute function
        result1 = await test_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call should use cache
        result2 = await test_func(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment

    def test_cached_decorator_with_args_and_kwargs(self):
        """Test cached decorator with various argument combinations."""
        manager = CacheManager()

        call_count = 0

        @manager.cached("test_cache")
        def test_func(x, y, z=None):
            nonlocal call_count
            call_count += 1
            return f"{x}-{y}-{z}"

        # Different argument combinations should create different cache entries
        result1 = test_func(1, 2)
        result2 = test_func(1, 2, z=3)
        result3 = test_func(1, 2)  # Should hit cache

        assert result1 == "1-2-None"
        assert result2 == "1-2-3"
        assert result3 == "1-2-None"
        assert call_count == 2  # Only two unique calls

    def test_create_cache_key(self):
        """Cache keys are ``<func_name>:<sha256>`` and discriminate their inputs.

        This test previously pinned the four literal plaintext keys
        (``"func::"``, ``"func:(1, 2, 3):"``, ...). That shape was retired
        because the composed key was interpolated verbatim into DEBUG log lines
        and used as a Redis key NAME, so any credential-shaped argument that the
        7-name strip list does not cover landed in ``KEYS``/``MONITOR``/the
        slowlog/RDB. The key is now hashed.

        Asserting the digest literals would re-pin a value with no meaning and
        would break again on the next composition change. The load-bearing
        properties are asserted instead: readable prefix (invalidation and
        debugging still work), opacity (no argument survives into the key), and
        DISCRIMINATION -- distinct inputs must not collide, which is the
        property a hash could actually get wrong.
        """
        manager = CacheManager()

        cases = {
            "no args": manager._create_cache_key("func", (), {}),
            "positional": manager._create_cache_key("func", (1, 2, 3), {}),
            "keyword": manager._create_cache_key("func", (), {"a": 1, "b": 2}),
            "both": manager._create_cache_key("func", (1, 2), {"a": 1}),
        }

        for label, key in cases.items():
            prefix, _, digest = key.partition(":")
            assert prefix == "func", f"{label}: lost the readable prefix: {key!r}"
            assert re.fullmatch(
                r"[0-9a-f]{64}", digest
            ), f"{label}: expected a sha256 digest, got {digest!r}"
            # Opacity: no argument value may survive into the key.
            for leaked in ("(1, 2", "'a'", "[('a'"):
                assert leaked not in key, f"{label}: argument leaked into key: {key!r}"

        # Discrimination: four distinct inputs -> four distinct keys.
        assert len(set(cases.values())) == len(cases), f"key collision: {cases}"

        # Determinism: the same input must reproduce the same key.
        assert manager._create_cache_key("func", (1, 2), {"a": 1}) == cases["both"]

    def test_make_redis_key(self):
        """Test Redis key creation."""
        manager = CacheManager(config={"prefix": "test:"})

        key = manager._make_redis_key("cache_key")
        assert key == "test:cache_key"

    def test_make_redis_key_default_prefix(self):
        """Test Redis key creation with default prefix."""
        manager = CacheManager()

        key = manager._make_redis_key("cache_key")
        assert key == "mcp:cache_key"

    def test_clear_all_caches(self):
        """Test clearing all caches."""
        manager = CacheManager()

        # Create some caches and add data
        cache1 = manager.get_cache("cache1")
        cache2 = manager.get_cache("cache2")

        cache1.set("key1", "value1")
        cache2.set("key2", "value2")

        # Clear all
        manager.clear_all()

        # Verify all caches are cleared
        assert cache1.get("key1") is None
        assert cache2.get("key2") is None

    def test_stats_all_caches(self):
        """Test getting stats for all caches."""
        manager = CacheManager()

        cache1 = manager.get_cache("cache1")
        cache2 = manager.get_cache("cache2")

        cache1.set("key1", "value1")
        cache2.set("key2", "value2")

        stats = manager.stats()

        assert "cache1" in stats
        assert "cache2" in stats
        assert isinstance(stats["cache1"], dict)
        assert isinstance(stats["cache2"], dict)

    def test_init_redis_import_error(self):
        """Test Redis initialization with import error."""
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'redis'")
        ):
            manager = CacheManager(backend="redis")

            # Should fallback to disabled
            assert manager.enabled is False

    def test_init_redis_connection_error(self):
        """Test Redis initialization with connection error."""
        with patch(
            "redis.asyncio.from_url", side_effect=Exception("Connection failed")
        ):
            manager = CacheManager(backend="redis")

            # Should fallback to disabled
            assert manager.enabled is False

    @pytest.mark.asyncio
    async def test_get_redis_no_client(self):
        """Test Redis get operation when no Redis client."""
        manager = CacheManager()

        result = await manager.get_redis("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_redis_no_client(self):
        """Test Redis set operation when no Redis client."""
        manager = CacheManager()

        success = await manager.set_redis("key1", "value1")
        assert success is False

    @pytest.mark.asyncio
    async def test_get_redis_with_client(self):
        """Test Redis get operation with client."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = asyncio.Future()
        mock_redis.get.return_value.set_result(json.dumps("value1"))

        manager = CacheManager()
        manager._redis = mock_redis

        result = await manager.get_redis("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_set_redis_with_client(self):
        """Test Redis set operation with client."""
        mock_redis = MagicMock()
        mock_redis.setex.return_value = asyncio.Future()
        mock_redis.setex.return_value.set_result(True)

        manager = CacheManager()
        manager._redis = mock_redis

        success = await manager.set_redis("key1", "value1", ttl=300)
        assert success is True
        mock_redis.setex.assert_called_with("mcp:key1", 300, '"value1"')

    @pytest.mark.asyncio
    async def test_set_redis_no_ttl(self):
        """Test Redis set operation without TTL."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = asyncio.Future()
        mock_redis.set.return_value.set_result(True)

        manager = CacheManager()
        manager._redis = mock_redis

        success = await manager.set_redis("key1", "value1")
        assert success is True
        mock_redis.set.assert_called_with("mcp:key1", '"value1"')


class TestGlobalCacheManager:
    """Test global cache manager functionality."""

    def test_cached_query_decorator_enabled(self):
        """Test cached_query decorator when enabled."""
        call_count = 0

        @cached_query("test_cache", ttl=300, enabled=True)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = test_func(5)
        result2 = test_func(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # Should only call once due to caching

    def test_cached_query_decorator_disabled(self):
        """Test cached_query decorator when disabled."""
        call_count = 0

        @cached_query("test_cache", ttl=300, enabled=False)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = test_func(5)
        result2 = test_func(5)

        assert result1 == 10
        assert result2 == 10
        assert call_count == 2  # Should call twice, no caching

    @pytest.mark.asyncio
    async def test_cached_query_decorator_async(self):
        """Test cached_query decorator with async function."""
        call_count = 0

        @cached_query("test_cache_async", ttl=300, enabled=True)
        async def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await test_func(5)
        result2 = await test_func(5)

        assert result1 == 10
        assert result2 == 10
        # The decorator should work for async functions
        assert call_count == 1  # Should only call once due to caching

    def test_get_cache_stats_global(self):
        """Test getting global cache statistics."""
        # Clear any existing caches
        clear_all_caches()

        # Create and use a cache
        @cached_query("test_stats", ttl=300, enabled=True)
        def test_func(x):
            return x * 2

        test_func(5)

        stats = get_cache_stats()
        assert isinstance(stats, dict)
        # Should have at least one cache
        assert len(stats) >= 1

    def test_clear_all_caches_global(self):
        """clear_all_caches() MUST drop the entries, forcing recomputation.

        The previous version called ``clear_all_caches()`` under "# Should work
        without errors" and closed with ``assert True`` — which passes whether
        the caches were cleared, partially cleared, or not touched at all.
        """
        calls = []

        @cached_query("test_clear", ttl=300, enabled=True)
        def test_func(x):
            calls.append(x)
            return x * 2

        assert test_func(5) == 10
        assert test_func(5) == 10
        # CONTROL: the decorator really is caching. Without this, the
        # post-clear recomputation below is equally consistent with "the clear
        # worked" and "nothing was ever cached".
        assert len(calls) == 1, (
            "the cached_query decorator did not cache; the clear assertion "
            f"below would hold vacuously. calls={calls!r}"
        )

        clear_all_caches()

        assert test_func(5) == 10
        assert len(calls) == 2, (
            "clear_all_caches() returned but the entry was still served from "
            f"cache — the function was not recomputed. calls={calls!r}"
        )

    def test_global_cache_manager_singleton(self):
        """Test that global cache manager is a singleton."""
        # This tests that the global instance is used consistently
        stats1 = get_cache_stats()
        stats2 = get_cache_stats()

        # Should return the same type of data
        assert type(stats1) == type(stats2)


class TestCacheIntegration:
    """Integration tests for cache components."""

    def test_lru_cache_with_unified_cache(self):
        """Test LRU cache working with UnifiedCache."""
        lru = LRUCache(max_size=3, ttl=300)
        unified = UnifiedCache(name="test", lru_cache=lru)

        # Add data through unified cache
        unified.set("key1", "value1")
        unified.set("key2", "value2")

        # Verify through LRU cache
        assert lru.get("key1") == "value1"
        assert lru.get("key2") == "value2"

        # Verify through unified cache
        assert unified.get("key1") == "value1"
        assert unified.get("key2") == "value2"

    def test_cache_manager_with_unified_cache(self):
        """Test CacheManager working with UnifiedCache."""
        manager = CacheManager()

        cache = manager.get_cache("integration_test")

        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

        # Verify stats
        stats = manager.stats()
        assert "integration_test" in stats

    def test_end_to_end_caching_workflow(self):
        """Test complete caching workflow from decorator to storage."""
        manager = CacheManager()

        execution_count = 0

        @manager.cached("workflow_test", ttl=300)
        def expensive_computation(x, y):
            nonlocal execution_count
            execution_count += 1
            return x * y + execution_count

        # First call should execute
        result1 = expensive_computation(3, 4)
        assert result1 == 13  # 3*4 + 1
        assert execution_count == 1

        # Second call should use cache
        result2 = expensive_computation(3, 4)
        assert result2 == 13  # Same result from cache
        assert execution_count == 1  # Should not increment

        # Different arguments should execute again
        result3 = expensive_computation(5, 6)
        assert result3 == 32  # 5*6 + 2
        assert execution_count == 2

        # Original arguments should still use cache
        result4 = expensive_computation(3, 4)
        assert result4 == 13  # Still from cache
        assert execution_count == 2  # Should not increment

    @pytest.mark.asyncio
    async def test_async_end_to_end_caching_workflow(self):
        """Test complete async caching workflow."""
        manager = CacheManager()

        execution_count = 0

        @manager.cached("async_workflow_test", ttl=300)
        async def expensive_async_computation(x, y):
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.01)  # Simulate async work
            return x * y + execution_count

        # First call should execute
        result1 = await expensive_async_computation(3, 4)
        assert result1 == 13  # 3*4 + 1
        assert execution_count == 1

        # Second call should use cache
        result2 = await expensive_async_computation(3, 4)
        assert result2 == 13  # Same result from cache
        assert execution_count == 1  # Should not increment

    def test_cache_with_complex_data_types(self):
        """Test caching with complex data types."""
        cache = LRUCache()

        # Test with dictionary
        dict_data = {"key": "value", "nested": {"inner": "data"}}
        cache.set("dict_key", dict_data)
        result = cache.get("dict_key")
        assert result == dict_data

        # Test with list
        list_data = [1, 2, 3, {"nested": "list"}]
        cache.set("list_key", list_data)
        result = cache.get("list_key")
        assert result == list_data

        # Test with custom object
        class CustomObject:
            def __init__(self, value):
                self.value = value

            def __eq__(self, other):
                return isinstance(other, CustomObject) and self.value == other.value

        obj = CustomObject("test")
        cache.set("obj_key", obj)
        result = cache.get("obj_key")
        assert result == obj

    def test_cache_performance_under_load(self):
        """Test cache performance under load."""
        cache = LRUCache(max_size=100)

        # Add many items
        start_time = time.time()
        for i in range(1000):
            cache.set(f"key_{i}", f"value_{i}")
        set_time = time.time() - start_time

        # Get many items
        start_time = time.time()
        for i in range(1000):
            cache.get(f"key_{i}")
        get_time = time.time() - start_time

        # Should complete reasonably quickly (less than 1 second each)
        assert set_time < 1.0
        assert get_time < 1.0

        # Verify cache size limit is enforced
        assert len(cache._cache) <= 100

    def test_cache_memory_management(self):
        """Test that cache properly manages memory."""
        cache = LRUCache(max_size=10)

        # Fill cache beyond capacity
        for i in range(50):
            cache.set(f"key_{i}", f"value_{i}")

        # Cache should never exceed max_size
        assert len(cache._cache) <= 10

        # Verify evictions occurred
        stats = cache.stats()
        assert stats["evictions"] > 0
        assert stats["size"] <= 10
