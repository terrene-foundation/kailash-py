# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for gh#368: source change must not crash parameterized products.

Before the fix, ``_on_source_change()`` attempted to re-execute the product
function for parameterized products without any params context. The product
function either crashed (missing required param argument) or produced a
nonsensical result cached under the bare product name instead of the
parameterized cache slot.

After the fix, ``_on_source_change()`` detects ``ProductMode.PARAMETERIZED``
and invalidates all cached parameter combinations via
``cache.invalidate_all(prefix=...)``, then returns. The lazy re-population
on next request ensures correct params are always supplied by the serving
layer.

Tier 2 integration test: real FabricRuntime, real InMemoryFabricCacheBackend,
real PipelineExecutor. NO mocking.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from dataflow import DataFlow
from dataflow.fabric.cache import InMemoryFabricCacheBackend
from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.context import FabricContext, PipelineContext
from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.runtime import FabricRuntime
from dataflow.fabric.testing import MockSource

pytestmark = [pytest.mark.regression, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product_registration(
    name: str,
    fn: Any,
    mode: str = "materialized",
    depends_on: List[str] | None = None,
    multi_tenant: bool = False,
) -> ProductRegistration:
    """Build a ProductRegistration for testing."""
    return ProductRegistration(
        name=name,
        fn=fn,
        mode=ProductMode(mode),
        depends_on=depends_on or [],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
        multi_tenant=multi_tenant,
    )


# ---------------------------------------------------------------------------
# Test: source change does not crash for parameterized products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_parameterized_product_source_change_does_not_crash() -> None:
    """_on_source_change MUST NOT crash when the product is parameterized.

    Regression: gh#368 -- _on_source_change called product_fn(context) for
    parameterized products, which expect (context, params). This caused
    TypeError or produced wrong results.
    """
    source = MockSource("api", data={"": {"items": [1, 2, 3]}})
    await source.connect()

    async def filtered_items(
        ctx: FabricContext, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        # This function REQUIRES params -- calling it without params crashes
        data = await ctx.source("api").fetch()
        category = params["category"]
        return {"category": category, "count": len(data["items"])}

    product_reg = _make_product_registration(
        "filtered_items",
        filtered_items,
        mode="parameterized",
        depends_on=["api"],
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    sources = {"api": {"name": "api", "config": None, "adapter": source}}
    products = {"filtered_items": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    # Start the runtime (prewarm=False to avoid executing parameterized
    # products during pre-warming, which also lacks params context)
    await runtime.start(prewarm=False)

    # Calling _on_source_change should NOT crash -- it should gracefully
    # invalidate cached entries instead of trying to re-execute
    await runtime._on_source_change("filtered_items")

    # If we got here without an exception, the fix works
    await runtime.stop()


# ---------------------------------------------------------------------------
# Test: source change invalidates all cached param combinations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_parameterized_product_source_change_invalidates_cache() -> None:
    """When source changes, parameterized products should invalidate all cached entries.

    Strategy: pre-populate the cache with two parameter combinations, then
    trigger _on_source_change. Both cache entries should be invalidated.
    """
    source = MockSource("api", data={"": {"items": [1, 2, 3]}})
    await source.connect()

    async def filtered_items(
        ctx: FabricContext, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        data = await ctx.source("api").fetch()
        return {"category": params["category"], "count": len(data["items"])}

    product_reg = _make_product_registration(
        "filtered_items",
        filtered_items,
        mode="parameterized",
        depends_on=["api"],
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    sources = {"api": {"name": "api", "config": None, "adapter": source}}
    products = {"filtered_items": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    await runtime.start(prewarm=False)

    pipeline = runtime.pipeline
    assert pipeline is not None

    # Pre-populate the cache with two param combinations
    ctx = PipelineContext(express=None, sources={"api": source}, products_cache={})

    await pipeline.execute_product(
        product_name="filtered_items",
        product_fn=filtered_items,
        context=ctx,
        params={"category": "electronics"},
    )
    await pipeline.execute_product(
        product_name="filtered_items",
        product_fn=filtered_items,
        context=ctx,
        params={"category": "books"},
    )

    # Verify both entries are cached
    cached_electronics = await pipeline.get_cached(
        "filtered_items", params={"category": "electronics"}
    )
    cached_books = await pipeline.get_cached(
        "filtered_items", params={"category": "books"}
    )
    assert cached_electronics is not None, "electronics entry should be cached"
    assert cached_books is not None, "books entry should be cached"

    # Trigger source change -- should invalidate all param combinations
    await runtime._on_source_change("filtered_items")

    # Both cache entries should now be invalidated
    cached_electronics_after = await pipeline.get_cached(
        "filtered_items", params={"category": "electronics"}
    )
    cached_books_after = await pipeline.get_cached(
        "filtered_items", params={"category": "books"}
    )
    assert (
        cached_electronics_after is None
    ), "electronics entry should be invalidated after source change"
    assert (
        cached_books_after is None
    ), "books entry should be invalidated after source change"

    await runtime.stop()


# ---------------------------------------------------------------------------
# Test: materialized products still re-execute on source change (no regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_materialized_product_still_refreshes_on_source_change() -> None:
    """Materialized products should still re-execute on source change.

    Regression guard: the parameterized product fix must not break
    the existing materialized product refresh path.
    """
    source = MockSource("api", data={"": {"version": 1}})
    await source.connect()

    call_count = 0

    async def report(ctx: FabricContext) -> Dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"version": call_count}

    product_reg = _make_product_registration(
        "report",
        report,
        mode="materialized",
        depends_on=["api"],
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    sources = {"api": {"name": "api", "config": None, "adapter": source}}
    products = {"report": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    await runtime.start(prewarm=True)

    # Pre-warm should have executed once
    assert call_count == 1

    # Trigger source change -- materialized product should re-execute
    await runtime._on_source_change("report")
    assert call_count == 2, "Materialized product should re-execute on source change"

    # Cache should contain the updated result
    cached = await runtime.pipeline.get_cached("report")
    assert cached is not None

    await runtime.stop()


# ---------------------------------------------------------------------------
# Test: unknown product name in source change is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_source_change_with_unknown_product_is_noop() -> None:
    """_on_source_change with an unknown product name should be a no-op."""
    source = MockSource("api", data={"": {}})
    await source.connect()

    async def noop_product(ctx: FabricContext) -> Dict[str, Any]:
        return {}

    product_reg = _make_product_registration(
        "real_product",
        noop_product,
        mode="materialized",
        depends_on=["api"],
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    sources = {"api": {"name": "api", "config": None, "adapter": source}}
    products = {"real_product": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    await runtime.start(prewarm=False)

    # Should not crash with unknown product name
    await runtime._on_source_change("nonexistent_product")

    await runtime.stop()
