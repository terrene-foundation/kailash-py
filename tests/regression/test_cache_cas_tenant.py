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
