# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: CacheNode CAS + tenant key enforcement.

GH-419: CacheBackend CAS (compare-and-swap) semantics and
tenant-scoped key isolation. Cross-SDK alignment with kailash-rs #292.
"""
from __future__ import annotations

import pytest

from kailash.nodes.cache.cache import CacheNode


@pytest.mark.regression
class TestCacheCAS:
    """Compare-and-swap semantics for CacheNode."""

    @pytest.fixture
    def cache(self) -> CacheNode:
        node = CacheNode(id="test-cache")
        return node

    @pytest.mark.asyncio
    async def test_set_returns_version(self, cache: CacheNode) -> None:
        """Every set should return a version tag."""
        result = await cache.async_run(
            operation="set", key="k1", value="v1", backend="memory"
        )
        assert result["success"] is True
        assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_get_returns_version(self, cache: CacheNode) -> None:
        """Get should return the current version tag."""
        await cache.async_run(operation="set", key="k1", value="v1", backend="memory")
        result = await cache.async_run(operation="get", key="k1", backend="memory")
        assert result["hit"] is True
        assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_cas_success(self, cache: CacheNode) -> None:
        """CAS with matching version should succeed."""
        await cache.async_run(operation="set", key="k1", value="v1", backend="memory")
        result = await cache.async_run(
            operation="set",
            key="k1",
            value="v2",
            expected_version=1,
            backend="memory",
        )
        assert result["success"] is True
        assert result["version"] == 2

    @pytest.mark.asyncio
    async def test_cas_failure(self, cache: CacheNode) -> None:
        """CAS with stale version should fail."""
        await cache.async_run(operation="set", key="k1", value="v1", backend="memory")
        result = await cache.async_run(
            operation="set",
            key="k1",
            value="v2",
            expected_version=99,
            backend="memory",
        )
        assert result["success"] is False
        assert result["cas_failed"] is True
        assert result["expected_version"] == 99
        assert result["actual_version"] == 1

    @pytest.mark.asyncio
    async def test_cas_on_new_key(self, cache: CacheNode) -> None:
        """CAS on a key that doesn't exist yet (version=None)."""
        # expected_version=None means "key must not exist"
        result = await cache.async_run(
            operation="set",
            key="new",
            value="v1",
            expected_version=None,
            backend="memory",
        )
        assert result["success"] is True
        assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_cas_on_new_key_conflict(self, cache: CacheNode) -> None:
        """CAS expecting version 5 on a key that doesn't exist -> fail."""
        result = await cache.async_run(
            operation="set",
            key="new",
            value="v1",
            expected_version=5,
            backend="memory",
        )
        assert result["success"] is False
        assert result["cas_failed"] is True

    @pytest.mark.asyncio
    async def test_delete_clears_version(self, cache: CacheNode) -> None:
        """After delete, the version tag should be cleared."""
        await cache.async_run(operation="set", key="k1", value="v1", backend="memory")
        await cache.async_run(operation="delete", key="k1", backend="memory")
        result = await cache.async_run(operation="get", key="k1", backend="memory")
        assert result["version"] is None


@pytest.mark.regression
class TestCacheTenantKeyEnforcement:
    """Tenant-scoped key isolation for CacheNode."""

    @pytest.fixture
    def cache(self) -> CacheNode:
        node = CacheNode(id="test-cache-tenant")
        return node

    @pytest.mark.asyncio
    async def test_tenant_key_prefix(self, cache: CacheNode) -> None:
        """Keys should include tenant_id when provided."""
        result = await cache.async_run(
            operation="set",
            key="doc:1",
            value="data",
            tenant_id="tenant-a",
            backend="memory",
        )
        assert result["key"] == "tenant-a:doc:1"

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, cache: CacheNode) -> None:
        """Two tenants with the same key should not see each other's data."""
        await cache.async_run(
            operation="set",
            key="doc:1",
            value="tenant-a-data",
            tenant_id="tenant-a",
            backend="memory",
        )
        await cache.async_run(
            operation="set",
            key="doc:1",
            value="tenant-b-data",
            tenant_id="tenant-b",
            backend="memory",
        )

        result_a = await cache.async_run(
            operation="get",
            key="doc:1",
            tenant_id="tenant-a",
            backend="memory",
        )
        result_b = await cache.async_run(
            operation="get",
            key="doc:1",
            tenant_id="tenant-b",
            backend="memory",
        )

        assert result_a["value"] == "tenant-a-data"
        assert result_b["value"] == "tenant-b-data"

    @pytest.mark.asyncio
    async def test_tenant_plus_namespace(self, cache: CacheNode) -> None:
        """Tenant + namespace should both prefix the key."""
        result = await cache.async_run(
            operation="set",
            key="doc:1",
            value="data",
            tenant_id="t1",
            namespace="ns",
            backend="memory",
        )
        assert result["key"] == "t1:ns:doc:1"

    @pytest.mark.asyncio
    async def test_no_tenant_no_prefix(self, cache: CacheNode) -> None:
        """Without tenant_id, key should not have a tenant prefix."""
        result = await cache.async_run(
            operation="set",
            key="doc:1",
            value="data",
            backend="memory",
        )
        assert result["key"] == "doc:1"


@pytest.mark.regression
class TestCacheCASRace:
    """Concurrent CAS race semantics — exactly one of N contenders wins."""

    @pytest.mark.asyncio
    async def test_concurrent_cas_exactly_one_wins(self) -> None:
        """Two coroutines racing with same expected_version: 1 wins, 1 loses."""
        import asyncio

        cache = CacheNode(id="test-cache-race")
        await cache.async_run(operation="set", key="counter", value=0, backend="memory")

        async def try_cas(new_value: int) -> dict:
            return await cache.async_run(
                operation="set",
                key="counter",
                value=new_value,
                expected_version=1,
                backend="memory",
            )

        r1, r2 = await asyncio.gather(try_cas(100), try_cas(200))
        successes = [r for r in (r1, r2) if r["success"]]
        failures = [r for r in (r1, r2) if not r["success"]]
        assert len(successes) == 1, f"expected 1 success, got {len(successes)}"
        assert len(failures) == 1, f"expected 1 failure, got {len(failures)}"
        assert failures[0]["cas_failed"] is True

    @pytest.mark.asyncio
    async def test_cas_rejected_on_redis_backend(self) -> None:
        """CAS with Redis backend must fail-closed (not silently succeed)."""
        cache = CacheNode(id="test-cache-redis-cas")
        result = await cache.async_run(
            operation="set",
            key="k1",
            value="v1",
            expected_version=1,
            backend="redis",
        )
        assert result["success"] is False
        assert result["cas_failed"] is True
        assert "memory" in result["error"].lower()


@pytest.mark.regression
class TestCacheTenantScopedClear:
    """_clear must scope by tenant_id so one tenant cannot nuke others."""

    @pytest.mark.asyncio
    async def test_clear_with_tenant_only_clears_that_tenant(self) -> None:
        """Clearing tenant-a must not affect tenant-b's keys."""
        cache = CacheNode(id="test-cache-tscope")
        await cache.async_run(
            operation="set", key="k", value="a", tenant_id="tenant-a", backend="memory"
        )
        await cache.async_run(
            operation="set", key="k", value="b", tenant_id="tenant-b", backend="memory"
        )

        await cache.async_run(operation="clear", tenant_id="tenant-a", backend="memory")

        r_a = await cache.async_run(
            operation="get", key="k", tenant_id="tenant-a", backend="memory"
        )
        r_b = await cache.async_run(
            operation="get", key="k", tenant_id="tenant-b", backend="memory"
        )
        assert r_a["hit"] is False  # tenant-a cleared
        assert r_b["hit"] is True  # tenant-b untouched
        assert r_b["value"] == "b"


@pytest.mark.regression
class TestCacheVersionTagEvictionCleanup:
    """_version_tags must not leak when _memory_cache evicts (M1)."""

    @pytest.mark.asyncio
    async def test_version_tags_cleaned_on_lru_eviction(self) -> None:
        """After LRU eviction, evicted keys must not have stale version tags."""
        cache = CacheNode(id="test-cache-evict")
        # Fill beyond max_items to trigger eviction
        for i in range(20):
            await cache.async_run(
                operation="set",
                key=f"k{i}",
                value=f"v{i}",
                backend="memory",
                max_memory_items=10,
                eviction_policy="lru",
            )
        # At least some early keys should have been evicted; their
        # version tags must be gone (not leaking in _version_tags).
        assert len(cache._version_tags) <= len(cache._memory_cache)


@pytest.mark.regression
class TestClassificationEngineFailClosed:
    """DataFlowEngine.classify_field without a policy must fail-closed (L6)."""

    def test_no_policy_returns_highly_confidential(self) -> None:
        """Without a configured policy, classify_field returns the most
        restrictive level — not 'public'."""
        from dataflow.classification.types import DataClassification
        from dataflow.engine import DataFlowEngine

        engine = object.__new__(DataFlowEngine)
        engine._classification = None
        result = engine.classify_field("UnknownModel", "unknown_field")
        assert result == DataClassification.HIGHLY_CONFIDENTIAL.value
