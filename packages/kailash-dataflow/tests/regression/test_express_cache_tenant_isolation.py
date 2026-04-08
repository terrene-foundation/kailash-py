# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for Phase 5.7 — Express cache tenant partitioning.

Before Phase 5.7, ``CacheKeyGenerator.generate_express_key`` had no
``tenant_id`` argument and produced keys of the form
``dataflow:v1:{model}:{op}:{hash}``. Two tenants hitting the same model
and operation would share the same cache slot — a cross-tenant data
leak the moment the cache was shared across replicas via Redis.

After Phase 5.7:

* Keys include the tenant segment when a ``tenant_id`` is supplied:
  ``dataflow:v1:{tenant}:{model}:{op}:{hash}``
* ``DataFlowExpress`` resolves the tenant from the
  ``dataflow.core.tenant_context`` ContextVar when the DataFlow instance
  is configured with ``multi_tenant=True``.
* ``DataFlowExpress._resolve_tenant_id`` raises
  :class:`TenantRequiredError` when multi-tenant mode is on and no
  tenant is bound — silent fallback to a shared namespace is blocked.
* ``InMemoryCache.invalidate_model`` and
  ``AsyncRedisCacheAdapter.invalidate_model`` accept an optional
  ``tenant_id`` kwarg for scoped invalidation so tenant A cannot drop
  tenant B's entries.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache
from dataflow.core.multi_tenancy import TenantRequiredError
from dataflow.core.tenant_context import _current_tenant
from dataflow.features.express import DataFlowExpress

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSecurityConfig:
    def __init__(self, multi_tenant: bool = False) -> None:
        self.multi_tenant = multi_tenant


class _FakeConfig:
    def __init__(self, multi_tenant: bool = False) -> None:
        self.security = _FakeSecurityConfig(multi_tenant=multi_tenant)


class _FakeDataFlow:
    """Minimal DataFlow stand-in for DataFlowExpress construction.

    Only sets the attributes DataFlowExpress actually reads. Avoids
    MagicMock on purpose because MagicMock returns a truthy Mock for
    any attribute access, which would mask multi-tenant detection bugs.
    """

    def __init__(self, multi_tenant: bool = False) -> None:
        self.config = _FakeConfig(multi_tenant=multi_tenant)
        self._models: Dict[str, Any] = {}
        self._node_classes: Dict[str, Any] = {}
        self._engine_ref = None


@pytest.fixture(autouse=True)
def _reset_tenant_context() -> Any:
    """Reset the tenant ContextVar between tests to avoid leakage."""
    token = _current_tenant.set(None)
    yield
    _current_tenant.reset(token)


# ---------------------------------------------------------------------------
# Key generator
# ---------------------------------------------------------------------------


def test_generate_express_key_without_tenant_matches_legacy_shape() -> None:
    """Back-compat: no tenant → legacy shape unchanged."""
    gen = CacheKeyGenerator()
    key = gen.generate_express_key("User", "list", {"active": True})
    # dataflow:v1:User:list:<8-hex-hash>
    assert key.startswith("dataflow:v1:User:list:")
    segments = key.split(":")
    assert len(segments) == 5


def test_generate_express_key_with_tenant_inserts_tenant_segment() -> None:
    """With tenant → dataflow:v1:{tenant}:{model}:{op}:{hash}."""
    gen = CacheKeyGenerator()
    key = gen.generate_express_key("User", "list", {"active": True}, tenant_id="acme")
    assert key.startswith("dataflow:v1:acme:User:list:")
    segments = key.split(":")
    assert len(segments) == 6


def test_generate_express_key_two_tenants_produce_distinct_keys() -> None:
    """Two tenants hitting the same model+op+params MUST NOT collide."""
    gen = CacheKeyGenerator()
    key_a = gen.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-a"
    )
    key_b = gen.generate_express_key(
        "User", "list", {"active": True}, tenant_id="tenant-b"
    )
    assert key_a != key_b
    assert ":tenant-a:User:" in key_a
    assert ":tenant-b:User:" in key_b


def test_tenant_id_takes_precedence_over_constructor_namespace() -> None:
    """Per-call ``tenant_id`` beats the ``namespace`` constructor arg."""
    gen = CacheKeyGenerator(namespace="legacy")
    key = gen.generate_express_key("User", "list", None, tenant_id="runtime-tenant")
    assert ":runtime-tenant:User:" in key
    assert ":legacy:" not in key


# ---------------------------------------------------------------------------
# DataFlowExpress._resolve_tenant_id
# ---------------------------------------------------------------------------


def test_resolve_tenant_id_returns_none_in_single_tenant_mode() -> None:
    """Single-tenant DataFlow → None, no ContextVar lookup required."""
    express = DataFlowExpress(_FakeDataFlow(multi_tenant=False), cache_enabled=True)
    assert express._resolve_tenant_id() is None


def test_resolve_tenant_id_raises_when_multi_tenant_and_no_context() -> None:
    """Multi-tenant + no ContextVar → TenantRequiredError (no silent fallback)."""
    express = DataFlowExpress(_FakeDataFlow(multi_tenant=True), cache_enabled=True)
    with pytest.raises(TenantRequiredError):
        express._resolve_tenant_id()


def test_resolve_tenant_id_returns_context_value_when_multi_tenant() -> None:
    """Multi-tenant + ContextVar bound → returns the bound tenant_id."""
    express = DataFlowExpress(_FakeDataFlow(multi_tenant=True), cache_enabled=True)
    _current_tenant.set("acme")
    assert express._resolve_tenant_id() == "acme"


# ---------------------------------------------------------------------------
# InMemoryCache.invalidate_model tenant scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_model_tenant_scoped_keeps_other_tenants() -> None:
    """invalidate_model(model, tenant_id=X) MUST NOT drop tenant Y."""
    cache = InMemoryCache(ttl=300, max_size=100)

    # Pre-populate two tenants under the same model
    await cache.set("dataflow:v1:tenant-a:User:list:hash1", {"rows": ["a1"]})
    await cache.set("dataflow:v1:tenant-a:User:read:hash2", {"row": "a2"})
    await cache.set("dataflow:v1:tenant-b:User:list:hash3", {"rows": ["b1"]})

    dropped = await cache.invalidate_model("User", tenant_id="tenant-a")
    assert dropped == 2

    # tenant-a's User entries are gone
    assert await cache.get("dataflow:v1:tenant-a:User:list:hash1") is None
    assert await cache.get("dataflow:v1:tenant-a:User:read:hash2") is None

    # tenant-b's User entries survive
    assert await cache.get("dataflow:v1:tenant-b:User:list:hash3") == {"rows": ["b1"]}


@pytest.mark.asyncio
async def test_invalidate_model_without_tenant_drops_every_tenant() -> None:
    """invalidate_model(model) without tenant drops every tenant's entries.

    Back-compat path: when the caller does not supply a tenant_id,
    invalidation is model-wide (every tenant's entries are dropped).
    """
    cache = InMemoryCache(ttl=300, max_size=100)

    await cache.set("dataflow:v1:tenant-a:User:list:hash1", {"rows": ["a1"]})
    await cache.set("dataflow:v1:tenant-b:User:list:hash2", {"rows": ["b1"]})

    dropped = await cache.invalidate_model("User")
    assert dropped == 2
    assert await cache.get("dataflow:v1:tenant-a:User:list:hash1") is None
    assert await cache.get("dataflow:v1:tenant-b:User:list:hash2") is None
