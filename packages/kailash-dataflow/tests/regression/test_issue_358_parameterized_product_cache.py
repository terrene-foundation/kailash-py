# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for kailash-py#358 — parameterized product cache lookup
missing params in serving layer and health manager.

Before the fix:

- ``fabric/serving.py`` called ``self._pipeline.get_cached(name)`` without
  passing ``params``, so parameterized products always looked up the
  bare-name cache slot and missed the per-param entry. HTTP GET returned
  ``{"data": null}`` with HTTP 200.

- ``fabric/health.py`` called ``self._pipeline.get_metadata(name)``
  without aggregating per-param entries, so parameterized products
  always reported ``freshness="cold"`` regardless of cache state.

After the fix:

- Serving GET passes ``params=params`` to ``get_cached`` so the lookup
  hits the parameterized cache slot.
- Batch serving returns an explicit error for parameterized products
  (the batch contract has no place to carry per-product params).
- Health uses the new ``scan_product_metadata`` wrapper (backed by the
  cache backend's ``scan_prefix`` primitive) to aggregate freshness
  across every cached param combination and report
  ``freshness="fresh"`` + ``param_combinations_cached=N``.

All assertions in this file target the in-memory cache backend because
Redis assertions live in ``tests/fabric/test_fabric_cache_redis.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from dataflow.fabric.cache import InMemoryFabricCacheBackend, _FabricCacheEntry
from dataflow.fabric.config import ProductMode, StalenessPolicy
from dataflow.fabric.health import FabricHealthManager
from dataflow.fabric.pipeline import PipelineExecutor

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeDataFlow:
    """Minimal DataFlow stand-in for PipelineExecutor construction."""

    class _Database:
        def get_pool_size(self, _env: str) -> int:
            return 5

    class _Config:
        database = None
        environment = "development"

        def __init__(self) -> None:
            self.database = _FakeDataFlow._Database()

    def __init__(self) -> None:
        self.config = _FakeDataFlow._Config()


class _FakeProduct:
    """Stand-in for ProductRegistration with only the fields health reads."""

    def __init__(
        self,
        name: str,
        mode: ProductMode,
        max_age_seconds: int = 60,
        multi_tenant: bool = False,
    ) -> None:
        self.name = name
        self.mode = mode
        self.multi_tenant = multi_tenant
        self.staleness = StalenessPolicy(max_age=timedelta(seconds=max_age_seconds))


def _build_entry(
    product_name: str,
    params_json: str,
    cached_at: datetime,
    run_started_at: Optional[datetime] = None,
    content_hash: str = "deadbeef",
) -> _FabricCacheEntry:
    return _FabricCacheEntry(
        product_name=product_name,
        tenant_id=None,
        data_bytes=b"{}",
        content_hash=content_hash,
        metadata={"pipeline_ms": 42},
        cached_at=cached_at,
        run_started_at=run_started_at or cached_at,
        schema_version=2,
        size_bytes=2,
    )


# ---------------------------------------------------------------------------
# scan_prefix primitive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_prefix_returns_matching_parameterized_entries() -> None:
    """scan_prefix MUST return every entry under the product_name: prefix."""
    backend = InMemoryFabricCacheBackend()
    now = datetime.now(timezone.utc)

    # Insert two param combinations for "members" + one bare-name entry
    # for a DIFFERENT product called "members_summary". The bare entry
    # for members_summary MUST NOT match the members: prefix.
    await backend.set(
        'members:{"ecosystem_id": "eco-a"}',
        _build_entry("members", '{"ecosystem_id": "eco-a"}', now),
    )
    await backend.set(
        'members:{"ecosystem_id": "eco-b"}',
        _build_entry("members", '{"ecosystem_id": "eco-b"}', now),
    )
    await backend.set(
        "members_summary",
        _build_entry("members_summary", "", now),
    )

    results = await backend.scan_prefix("members:")
    keys = sorted(key for key, _meta in results)
    assert keys == [
        'members:{"ecosystem_id": "eco-a"}',
        'members:{"ecosystem_id": "eco-b"}',
    ]
    for _key, metadata in results:
        assert "cached_at" in metadata
        assert "content_hash" in metadata
        assert metadata["size_bytes"] == 2


@pytest.mark.asyncio
async def test_scan_prefix_excludes_tenant_prefixed_entries() -> None:
    """scan_prefix on ``members:`` must not match ``tenant-a:members:...``."""
    backend = InMemoryFabricCacheBackend()
    now = datetime.now(timezone.utc)

    await backend.set(
        'members:{"ecosystem_id": "eco-a"}',
        _build_entry("members", '{"ecosystem_id": "eco-a"}', now),
    )
    await backend.set(
        'tenant-a:members:{"ecosystem_id": "eco-a"}',
        _build_entry("members", '{"ecosystem_id": "eco-a"}', now),
    )

    results = await backend.scan_prefix("members:")
    keys = [key for key, _meta in results]
    assert keys == ['members:{"ecosystem_id": "eco-a"}']


# ---------------------------------------------------------------------------
# PipelineExecutor.scan_product_metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_product_metadata_returns_all_param_entries() -> None:
    """PipelineExecutor.scan_product_metadata MUST surface every param entry."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(
        _FakeDataFlow(),
        cache_backend=backend,
    )
    now = datetime.now(timezone.utc)

    # Register data through set_cached so the cache key construction
    # matches the real code path, not a hand-rolled key.
    await executor.set_cached(
        "members",
        data_bytes=b"{}",
        content_hash="aaa",
        metadata={"pipeline_ms": 10},
        params={"ecosystem_id": "eco-a"},
        run_started_at=now,
    )
    await executor.set_cached(
        "members",
        data_bytes=b"{}",
        content_hash="bbb",
        metadata={"pipeline_ms": 20},
        params={"ecosystem_id": "eco-b"},
        run_started_at=now,
    )

    result = await executor.scan_product_metadata("members")
    assert len(result) == 2
    hashes = sorted(entry["content_hash"] for entry in result)
    assert hashes == ["aaa", "bbb"]


# ---------------------------------------------------------------------------
# Health endpoint — parameterized product regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_reports_parameterized_product_as_fresh_when_entries_exist() -> (
    None
):
    """gh#358 core regression: health for parameterized products.

    Prior behaviour: ``freshness="cold"`` because ``get_metadata(name)``
    used the bare-name key and always missed. Fixed behaviour:
    ``freshness="fresh"`` when at least one param combination has a
    non-stale entry, with ``param_combinations_cached`` reporting breadth.
    """
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(_FakeDataFlow(), cache_backend=backend)

    now = datetime.now(timezone.utc)
    await executor.set_cached(
        "members",
        data_bytes=b"{}",
        content_hash="aaa",
        metadata={"pipeline_ms": 10},
        params={"ecosystem_id": "eco-a"},
        run_started_at=now,
    )
    await executor.set_cached(
        "members",
        data_bytes=b"{}",
        content_hash="bbb",
        metadata={"pipeline_ms": 20},
        params={"ecosystem_id": "eco-b"},
        run_started_at=now - timedelta(seconds=5),
    )

    products = {
        "members": _FakeProduct(
            "members",
            ProductMode.PARAMETERIZED,
            max_age_seconds=60,
        )
    }
    manager = FabricHealthManager(
        sources={},
        products=products,
        pipeline=executor,
        started_at=now - timedelta(seconds=120),
    )

    health = await manager.get_health()
    product_health = health["products"]["members"]

    assert product_health["freshness"] == "fresh"
    assert product_health["param_combinations_cached"] == 2
    assert product_health["age_seconds"] is not None
    assert product_health["age_seconds"] <= 5


@pytest.mark.asyncio
async def test_health_reports_parameterized_product_as_cold_when_empty() -> None:
    """An unknown parameterized product with no entries still reports cold."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(_FakeDataFlow(), cache_backend=backend)

    products = {
        "members": _FakeProduct(
            "members",
            ProductMode.PARAMETERIZED,
            max_age_seconds=60,
        )
    }
    manager = FabricHealthManager(
        sources={},
        products=products,
        pipeline=executor,
    )

    health = await manager.get_health()
    product_health = health["products"]["members"]
    assert product_health["freshness"] == "cold"
    assert product_health["param_combinations_cached"] == 0


@pytest.mark.asyncio
async def test_health_reports_parameterized_product_as_stale_when_past_max_age() -> (
    None
):
    """Stale aggregation: all entries past max_age → freshness=stale."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(_FakeDataFlow(), cache_backend=backend)

    now = datetime.now(timezone.utc)
    cached_at = now - timedelta(seconds=600)  # 10 minutes ago
    # ``set_cached`` reads ``cached_at`` from the metadata dict, falling
    # back to ``now`` when absent. Pass it through metadata so the entry
    # is genuinely 10 minutes old for the staleness assertion.
    await executor.set_cached(
        "members",
        data_bytes=b"{}",
        content_hash="aaa",
        metadata={"pipeline_ms": 10, "cached_at": cached_at.isoformat()},
        params={"ecosystem_id": "eco-a"},
        run_started_at=cached_at,
    )

    products = {
        "members": _FakeProduct(
            "members",
            ProductMode.PARAMETERIZED,
            max_age_seconds=60,
        )
    }
    manager = FabricHealthManager(
        sources={},
        products=products,
        pipeline=executor,
    )

    health = await manager.get_health()
    product_health = health["products"]["members"]
    assert product_health["freshness"] == "stale"
    assert product_health["param_combinations_cached"] == 1
    assert product_health["age_seconds"] is not None
    assert product_health["age_seconds"] >= 600


# ---------------------------------------------------------------------------
# Serving path — params propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_get_cached_with_params_hits_parameterized_slot() -> None:
    """get_cached MUST look up the per-param slot, not the bare name."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(_FakeDataFlow(), cache_backend=backend)

    now = datetime.now(timezone.utc)
    await executor.set_cached(
        "members",
        data_bytes=b"payload-eco-a",
        content_hash="aaa",
        metadata={"pipeline_ms": 10},
        params={"ecosystem_id": "eco-a"},
        run_started_at=now,
    )

    # Without params → bare-name lookup, MUST miss
    assert await executor.get_cached("members") is None

    # With params → per-param lookup, MUST hit
    cached = await executor.get_cached("members", params={"ecosystem_id": "eco-a"})
    assert cached is not None
    data_bytes, _metadata = cached
    assert data_bytes == b"payload-eco-a"
