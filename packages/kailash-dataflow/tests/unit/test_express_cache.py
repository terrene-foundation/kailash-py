"""Unit tests for ExpressQueryCache.

Tests the cache component of ExpressDataFlow in isolation.
"""

import time

import pytest

from dataflow.features.express import CacheEntry, ExpressQueryCache


class TestExpressQueryCache:
    """Test ExpressQueryCache functionality."""

    # ========================================================================
    # Basic Operations
    # ========================================================================

    def test_cache_init_default_params(self):
        """Test cache initialization with default parameters."""
        cache = ExpressQueryCache()
        assert cache._max_size == 1000
        assert cache._default_ttl == 300

    def test_cache_init_custom_params(self):
        """Test cache initialization with custom parameters."""
        cache = ExpressQueryCache(max_size=100, default_ttl=60)
        assert cache._max_size == 100
        assert cache._default_ttl == 60

    def test_set_and_get_basic(self):
        """Test basic set and get operations."""
        cache = ExpressQueryCache()
        cache.set("key1", {"id": "user-1", "name": "Alice"})
        result = cache.get("key1")
        assert result == {"id": "user-1", "name": "Alice"}

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        cache = ExpressQueryCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_set_overwrites_existing(self):
        """Test that setting an existing key overwrites the value."""
        cache = ExpressQueryCache()
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    # ========================================================================
    # Cache Key Generation
    # ========================================================================

    def test_generate_key_unique_for_different_params(self):
        """Test that different parameters generate different keys."""
        cache = ExpressQueryCache()
        key1 = cache._generate_key("User", "read", {"id": "user-1"})
        key2 = cache._generate_key("User", "read", {"id": "user-2"})
        assert key1 != key2

    def test_generate_key_unique_for_different_models(self):
        """Test that different models generate different keys."""
        cache = ExpressQueryCache()
        key1 = cache._generate_key("User", "read", {"id": "1"})
        key2 = cache._generate_key("Order", "read", {"id": "1"})
        assert key1 != key2

    def test_generate_key_unique_for_different_operations(self):
        """Test that different operations generate different keys."""
        cache = ExpressQueryCache()
        key1 = cache._generate_key("User", "read", {"id": "1"})
        key2 = cache._generate_key("User", "list", {"id": "1"})
        assert key1 != key2

    def test_generate_key_consistent_for_same_input(self):
        """Test that same input always generates the same key."""
        cache = ExpressQueryCache()
        key1 = cache._generate_key("User", "read", {"id": "user-1"})
        key2 = cache._generate_key("User", "read", {"id": "user-1"})
        assert key1 == key2

    def test_generate_key_sorted_params(self):
        """Test that parameter order doesn't affect the key."""
        cache = ExpressQueryCache()
        key1 = cache._generate_key("User", "list", {"a": 1, "b": 2})
        key2 = cache._generate_key("User", "list", {"b": 2, "a": 1})
        assert key1 == key2

    # ========================================================================
    # LRU Eviction
    # ========================================================================

    def test_lru_eviction_at_max_size(self):
        """Test that oldest entries are evicted when max size is reached."""
        cache = ExpressQueryCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # All keys should exist
        assert cache.get("key1") is not None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None

        # Adding a 4th key should evict the oldest (key1)
        cache.set("key4", "value4")

        # key1 should be evicted
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_lru_access_updates_order(self):
        """Test that accessing a key moves it to end (most recently used)."""
        cache = ExpressQueryCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it most recently used
        cache.get("key1")

        # Adding a new key should evict key2 (oldest now)
        cache.set("key4", "value4")

        assert cache.get("key1") is not None  # Was accessed, still there
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_eviction_count_tracked(self):
        """Test that eviction count is tracked in statistics."""
        cache = ExpressQueryCache(max_size=2)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Evicts key1

        stats = cache.get_stats()
        assert stats["evictions"] == 1

    # ========================================================================
    # TTL Expiration
    # ========================================================================

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = ExpressQueryCache(default_ttl=1)  # 1 second TTL

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for TTL to expire
        time.sleep(1.1)

        # Entry should be expired
        assert cache.get("key1") is None

    def test_custom_ttl_per_entry(self):
        """Test that custom TTL can be set per entry."""
        cache = ExpressQueryCache(default_ttl=300)

        # Set entry with short TTL
        cache.set("key1", "value1", ttl=1)

        assert cache.get("key1") == "value1"

        # Wait for custom TTL to expire
        time.sleep(1.1)

        assert cache.get("key1") is None

    def test_ttl_miss_counted(self):
        """Test that expired entries count as misses."""
        cache = ExpressQueryCache(default_ttl=1)

        cache.set("key1", "value1")
        cache.get("key1")  # Hit

        time.sleep(1.1)

        cache.get("key1")  # Miss (expired)

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    # ========================================================================
    # Cache Invalidation
    # ========================================================================

    def test_invalidate_model_clears_all(self):
        """Test that invalidate_model clears all cache entries."""
        cache = ExpressQueryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        count = cache.invalidate_model("User")

        # All entries should be cleared (current implementation clears all)
        assert count == 3
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_clear_removes_all_entries(self):
        """Test that clear removes all cache entries."""
        cache = ExpressQueryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert len(cache._cache) == 0

    # ========================================================================
    # Statistics
    # ========================================================================

    def test_hit_miss_statistics(self):
        """Test that hit/miss statistics are tracked correctly."""
        cache = ExpressQueryCache()

        cache.set("key1", "value1")

        # Hits
        cache.get("key1")
        cache.get("key1")

        # Misses
        cache.get("key2")
        cache.get("key3")

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.5

    def test_hit_rate_zero_when_no_operations(self):
        """Test that hit rate is 0 when no operations have occurred."""
        cache = ExpressQueryCache()

        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_stats_include_all_fields(self):
        """Test that stats include all expected fields."""
        cache = ExpressQueryCache(max_size=100, default_ttl=60)

        cache.set("key1", "value1")
        cache.get("key1")

        stats = cache.get_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "evictions" in stats
        assert "invalidations" in stats
        assert "cached_entries" in stats
        assert "max_size" in stats
        assert "default_ttl" in stats

        assert stats["cached_entries"] == 1
        assert stats["max_size"] == 100
        assert stats["default_ttl"] == 60


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(value={"id": "user-1"}, timestamp=time.time(), ttl=300)

        assert entry.value == {"id": "user-1"}
        assert entry.ttl == 300
        assert isinstance(entry.timestamp, float)


class TestFindOneCacheKeyGeneration:
    """Test cache key generation for find_one operation."""

    def test_find_one_generates_unique_key(self):
        """Test that find_one generates unique cache keys."""
        cache = ExpressQueryCache()

        # Keys should be different for different filters
        key1 = cache._generate_key("User", "find_one", {"email": "alice@example.com"})
        key2 = cache._generate_key("User", "find_one", {"email": "bob@example.com"})
        assert key1 != key2

    def test_find_one_key_differs_from_read_key(self):
        """Test that find_one generates different keys than read."""
        cache = ExpressQueryCache()

        # Same ID but different operations should have different keys
        key_find_one = cache._generate_key(
            "User", "find_one", {"filter": {"id": "user-1"}, "limit": 1, "offset": 0}
        )
        key_read = cache._generate_key("User", "read", {"id": "user-1"})
        assert key_find_one != key_read

    def test_find_one_key_consistent_for_same_filter(self):
        """Test that find_one generates consistent keys for same filter."""
        cache = ExpressQueryCache()

        key1 = cache._generate_key(
            "User",
            "find_one",
            {"filter": {"status": "active"}, "limit": 1, "offset": 0},
        )
        key2 = cache._generate_key(
            "User",
            "find_one",
            {"filter": {"status": "active"}, "limit": 1, "offset": 0},
        )
        assert key1 == key2
