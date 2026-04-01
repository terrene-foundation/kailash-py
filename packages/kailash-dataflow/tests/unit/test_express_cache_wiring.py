"""Unit tests for Express ↔ cache module wiring (TSG-104).

Tests the full integration between DataFlowExpress and the cache/ module:
cache hits, cache misses, model-scoped invalidation, TTL bypass, cache_stats,
and CacheBackendProtocol compliance.
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow.cache.auto_detection import CacheBackend
from dataflow.cache.invalidation import CacheBackendProtocol
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache
from dataflow.features.express import DataFlowExpress


# ============================================================================
# Helpers — lightweight DataFlow stub for unit tests
# ============================================================================


class _StubDataFlow:
    """Minimal DataFlow-like object so DataFlowExpress can be instantiated."""

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._nodes: Dict[str, Any] = {}
        self._validate_on_write = False

    def get_model_fields(self, model: str) -> Dict[str, Any]:
        return {}


class _StubNode:
    """Stub node whose async_run returns configurable data."""

    def __init__(self, return_value: Any = None):
        self._return_value = return_value
        self.call_count = 0

    async def async_run(self, **kwargs) -> Any:
        self.call_count += 1
        return self._return_value


def _make_express(
    cache_ttl: int = 300,
    cache_enabled: bool = True,
    redis_url: Optional[str] = None,
) -> DataFlowExpress:
    """Create a DataFlowExpress with InMemoryCache (no real DB)."""
    db = _StubDataFlow()
    return DataFlowExpress(
        db,
        cache_enabled=cache_enabled,
        cache_ttl=cache_ttl,
        redis_url=redis_url,
    )


# ============================================================================
# Tests
# ============================================================================


class TestCacheHitMiss:
    """Verify that cached reads return without DB call and misses query DB."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        """Second read of the same key returns the cached value."""
        exp = _make_express()
        # Pre-populate cache directly
        key = exp._key_gen.generate_express_key("User", "read", {"id": "u1"})
        await exp._cache_manager.set(key, {"id": "u1", "name": "Alice"}, ttl=300)
        exp._cache_hits = 0

        # Pretend read() encounters cache hit
        result = await exp._cache_get("User", "read", {"id": "u1"}, 300)
        assert result == {"id": "u1", "name": "Alice"}
        assert exp._cache_hits == 1

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """Uncached read returns None from _cache_get."""
        exp = _make_express()
        result = await exp._cache_get("User", "read", {"id": "u99"}, 300)
        assert result is None
        assert exp._cache_misses == 1

    @pytest.mark.asyncio
    async def test_cache_set_then_get(self):
        """_cache_set stores value, _cache_get retrieves it."""
        exp = _make_express()
        await exp._cache_set("User", "list", {"limit": 10}, [{"id": "u1"}], 300)
        result = await exp._cache_get("User", "list", {"limit": 10}, 300)
        assert result == [{"id": "u1"}]


class TestCacheTTLBypass:
    """cache_ttl=0 should bypass the cache entirely."""

    @pytest.mark.asyncio
    async def test_ttl_zero_skips_cache_get(self):
        exp = _make_express()
        # Pre-populate
        key = exp._key_gen.generate_express_key("User", "read", {"id": "u1"})
        await exp._cache_manager.set(key, {"id": "u1", "name": "Alice"}, ttl=300)

        result = await exp._cache_get("User", "read", {"id": "u1"}, 0)
        assert result is None  # Bypassed

    @pytest.mark.asyncio
    async def test_ttl_zero_skips_cache_set(self):
        exp = _make_express()
        await exp._cache_set("User", "read", {"id": "u1"}, {"id": "u1"}, 0)
        # Nothing stored
        key = exp._key_gen.generate_express_key("User", "read", {"id": "u1"})
        assert await exp._cache_manager.get(key) is None

    def test_global_ttl_zero_disables_cache(self):
        """DataFlowExpress(cache_ttl=0) disables caching entirely."""
        exp = _make_express(cache_ttl=0)
        assert exp._cache_enabled is False
        assert exp._cache_manager is None


class TestModelScopedInvalidation:
    """Writes to model X clear only model X cache, not model Y."""

    @pytest.mark.asyncio
    async def test_invalidate_clears_only_target_model(self):
        exp = _make_express()
        # Populate cache for User and Product
        await exp._cache_set("User", "list", {}, [{"id": "u1"}], 300)
        await exp._cache_set("Product", "list", {}, [{"id": "p1"}], 300)

        # Invalidate User
        await exp._invalidate_model_cache("User")

        # User cache gone
        assert await exp._cache_get("User", "list", {}, 300) is None
        # Product cache untouched
        result = await exp._cache_get("Product", "list", {}, 300)
        assert result == [{"id": "p1"}]

    @pytest.mark.asyncio
    async def test_invalidate_handles_no_cache(self):
        """Invalidation is a no-op when caching is disabled."""
        exp = _make_express(cache_ttl=0)
        # Should not raise
        await exp._invalidate_model_cache("User")


class TestCacheStats:
    """cache_stats() returns hits, misses, size, backend."""

    @pytest.mark.asyncio
    async def test_cache_stats_structure(self):
        exp = _make_express()
        await exp._cache_set("User", "list", {}, [{"id": "u1"}], 300)
        await exp._cache_get("User", "list", {}, 300)  # hit
        await exp._cache_get("User", "read", {"id": "x"}, 300)  # miss

        stats = await exp.cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["backend"] == "in_memory"

    @pytest.mark.asyncio
    async def test_cache_stats_disabled(self):
        exp = _make_express(cache_ttl=0)
        stats = await exp.cache_stats()
        assert stats["backend"] == "disabled"
        assert stats["size"] == 0

    def test_get_cache_stats_sync(self):
        exp = _make_express()
        stats = exp.get_cache_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "backend" in stats


class TestCacheBackendProtocolCompliance:
    """InMemoryCache and CacheBackendProtocol."""

    def test_in_memory_cache_satisfies_protocol(self):
        cache = InMemoryCache()
        assert isinstance(cache, CacheBackendProtocol)


class TestCacheBackendAutoDetection:
    """Verify auto-detection picks InMemoryCache when Redis is unavailable."""

    def test_auto_detect_falls_back_to_in_memory(self):
        """Without Redis, auto_detect returns InMemoryCache."""
        backend = CacheBackend.auto_detect(redis_url=None)
        assert isinstance(backend, InMemoryCache)


class TestExpressKeyGeneration:
    """Test Express-specific cache key generation."""

    def test_express_key_deterministic(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "list", {"filter": {"active": True}})
        k2 = gen.generate_express_key("User", "list", {"filter": {"active": True}})
        assert k1 == k2

    def test_express_key_different_params(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "list", {"filter": {"active": True}})
        k2 = gen.generate_express_key("User", "list", {"filter": {"active": False}})
        assert k1 != k2


class TestClearCache:
    """Test clear_cache for model-scoped and global clearing."""

    @pytest.mark.asyncio
    async def test_clear_cache_model_scoped(self):
        exp = _make_express()
        await exp._cache_set("User", "list", {}, [{"id": "u1"}], 300)
        await exp._cache_set("Product", "list", {}, [{"id": "p1"}], 300)

        cleared = await exp.clear_cache("User")
        assert cleared >= 1

        # Product still cached
        result = await exp._cache_get("Product", "list", {}, 300)
        assert result == [{"id": "p1"}]

    @pytest.mark.asyncio
    async def test_clear_cache_global(self):
        exp = _make_express()
        await exp._cache_set("User", "list", {}, [{"id": "u1"}], 300)
        await exp._cache_set("Product", "list", {}, [{"id": "p1"}], 300)

        cleared = await exp.clear_cache()
        assert cleared == 2

        assert await exp._cache_get("User", "list", {}, 300) is None
        assert await exp._cache_get("Product", "list", {}, 300) is None


class TestResetStats:
    """Test reset_stats clears hit/miss counters."""

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        exp = _make_express()
        await exp._cache_get("User", "read", {"id": "u1"}, 300)  # miss
        assert exp._cache_misses == 1

        exp.reset_stats()
        assert exp._cache_hits == 0
        assert exp._cache_misses == 0
