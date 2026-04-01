"""Unit tests for Express cache integration (TSG-104).

Tests the cache module wiring into DataFlowExpress -- key generation,
cache hit/miss, model-scoped invalidation, TTL bypass, and cache stats.
"""

import asyncio

import pytest

from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache


# ============================================================================
# CacheKeyGenerator — Express-mode key generation
# ============================================================================


class TestCacheKeyGeneratorExpress:
    """Test CacheKeyGenerator.generate_express_key()."""

    def test_basic_key_format(self):
        """Key has format prefix:version:model:operation[:hash]."""
        gen = CacheKeyGenerator()
        key = gen.generate_express_key("User", "list")
        assert key == "dataflow:v1:User:list"

    def test_params_produce_hash_suffix(self):
        """When params are provided a short hash is appended."""
        gen = CacheKeyGenerator()
        key = gen.generate_express_key("User", "list", {"filter": {"active": True}})
        parts = key.split(":")
        assert len(parts) == 5
        assert parts[-1]  # non-empty hash

    def test_different_params_produce_different_keys(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "list", {"limit": 10})
        k2 = gen.generate_express_key("User", "list", {"limit": 20})
        assert k1 != k2

    def test_same_params_produce_same_key(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "read", {"id": "u1"})
        k2 = gen.generate_express_key("User", "read", {"id": "u1"})
        assert k1 == k2

    def test_different_models_produce_different_keys(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "read", {"id": "1"})
        k2 = gen.generate_express_key("Product", "read", {"id": "1"})
        assert k1 != k2

    def test_different_operations_produce_different_keys(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "read", {"id": "1"})
        k2 = gen.generate_express_key("User", "list", {"id": "1"})
        assert k1 != k2

    def test_namespace_included(self):
        gen = CacheKeyGenerator(namespace="tenant-42")
        key = gen.generate_express_key("User", "list")
        assert "tenant-42" in key

    def test_raises_on_empty_model(self):
        gen = CacheKeyGenerator()
        with pytest.raises(ValueError, match="Model name"):
            gen.generate_express_key("", "list")

    def test_raises_on_empty_operation(self):
        gen = CacheKeyGenerator()
        with pytest.raises(ValueError, match="Operation"):
            gen.generate_express_key("User", "")

    def test_param_order_irrelevant(self):
        gen = CacheKeyGenerator()
        k1 = gen.generate_express_key("User", "list", {"a": 1, "b": 2})
        k2 = gen.generate_express_key("User", "list", {"b": 2, "a": 1})
        assert k1 == k2

    def test_sql_key_still_works(self):
        """Backward compat: generate_key (SQL-based) is unchanged."""
        gen = CacheKeyGenerator()
        key = gen.generate_key("User", "SELECT * FROM users", [])
        assert key.startswith("dataflow:")


# ============================================================================
# InMemoryCache — async model-scoped invalidation
# ============================================================================


class TestInMemoryCacheModelScoped:
    """Test InMemoryCache.clear_pattern for model-scoped invalidation."""

    @pytest.mark.asyncio
    async def test_clear_pattern_removes_matching_keys(self):
        cache = InMemoryCache()
        await cache.set("dataflow:v1:User:list:abc", [{"id": "u1"}])
        await cache.set("dataflow:v1:User:read:def", {"id": "u1"})
        await cache.set("dataflow:v1:Product:list:ghi", [{"id": "p1"}])

        removed = await cache.clear_pattern("dataflow:v1:User:")
        assert removed == 2

        # Product untouched
        product = await cache.get("dataflow:v1:Product:list:ghi")
        assert product is not None

        # User keys gone
        assert await cache.get("dataflow:v1:User:list:abc") is None
        assert await cache.get("dataflow:v1:User:read:def") is None

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_for_no_match(self):
        cache = InMemoryCache()
        await cache.set("dataflow:v1:User:list:abc", [{"id": "u1"}])
        removed = await cache.clear_pattern("dataflow:v1:Order:")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_set_and_get_roundtrip(self):
        cache = InMemoryCache()
        await cache.set("k1", {"name": "Alice"})
        assert await cache.get("k1") == {"name": "Alice"}

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        cache = InMemoryCache(ttl=1)
        await cache.set("k1", "value", ttl=1)
        assert await cache.get("k1") == "value"
        await asyncio.sleep(1.1)
        assert await cache.get("k1") is None

    @pytest.mark.asyncio
    async def test_cache_stats(self):
        cache = InMemoryCache()
        await cache.set("k1", "v1")
        await cache.get("k1")  # hit
        await cache.get("k2")  # miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
