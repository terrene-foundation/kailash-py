# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for fabric critical bug fixes: #245, #248, #253.

- #245: Virtual products return data (not None) via single and batch handlers
- #248: dev_mode pre-warming with prewarm parameter
- #253: ChangeDetector receives adapter objects, not dicts

These are Tier 2 integration tests using real infrastructure
(MockSource, real PipelineExecutor, real ChangeDetector).
NO unittest.mock, NO @patch, NO MagicMock.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import pytest

from dataflow import DataFlow
from dataflow.adapters.source_adapter import SourceState
from dataflow.fabric.change_detector import ChangeDetector
from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.context import FabricContext, PipelineContext
from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.runtime import FabricRuntime
from dataflow.fabric.serving import FabricServingLayer
from dataflow.fabric.testing import MockSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product_registration(
    name: str,
    fn: Any,
    mode: str = "materialized",
    depends_on: List[str] | None = None,
) -> ProductRegistration:
    """Build a ProductRegistration for testing."""
    return ProductRegistration(
        name=name,
        fn=fn,
        mode=ProductMode(mode),
        depends_on=depends_on or [],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
    )


# ===========================================================================
# #245 — Virtual products execute inline (single handler)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_virtual_product_returns_data_single_handler():
    """Virtual product returns real data (not None) via GET /fabric/{name}.

    Regression: #245 — virtual products returned data: None because the
    serving layer only checked cache and returned None on miss. Virtual
    products should always execute inline.
    """
    source = MockSource("api", data={"users": [{"id": 1, "name": "Alice"}]})
    await source.connect()

    async def user_count(ctx: FabricContext) -> Dict[str, Any]:
        users = await ctx.source("api").fetch("users")
        return {"count": len(users), "source": "live"}

    product_reg = _make_product_registration(
        "user_count", user_count, mode="virtual", depends_on=["api"]
    )
    products = {"user_count": product_reg}

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    sources_dict = {"api": {"adapter": source, "config": None, "name": "api"}}

    serving = FabricServingLayer(
        products=products,
        pipeline_executor=pipeline,
        express=None,
        sources=sources_dict,
    )

    routes = serving.get_routes()
    get_route = next(r for r in routes if r["path"] == "/fabric/user_count")
    handler = get_route["handler"]

    # Call the handler — virtual product should execute inline
    response = await handler()

    assert response["_status"] == 200, f"Expected 200, got {response['_status']}"
    assert response["data"] is not None, "Virtual product returned data: None"
    assert response["data"]["count"] == 1
    assert response["data"]["source"] == "live"
    assert response["_headers"]["X-Fabric-Freshness"] == "fresh"
    assert response["_headers"]["X-Fabric-Mode"] == "virtual"


# ===========================================================================
# #245 — Virtual products execute inline (batch handler)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_virtual_product_returns_data_batch_handler():
    """Virtual product returns real data via GET /fabric/_batch.

    Regression: #245 — batch handler returned {data: None, status: cold}
    for virtual products instead of executing them inline.
    """
    source = MockSource("metrics", data={"": {"dau": 500, "mau": 2000}})
    await source.connect()

    async def live_metrics(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("metrics").fetch()
        return {"dau": data["dau"], "mau": data["mau"]}

    product_reg = _make_product_registration(
        "live_metrics", live_metrics, mode="virtual", depends_on=["metrics"]
    )
    products = {"live_metrics": product_reg}

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    sources_dict = {"metrics": {"adapter": source, "config": None, "name": "metrics"}}

    serving = FabricServingLayer(
        products=products,
        pipeline_executor=pipeline,
        express=None,
        sources=sources_dict,
    )

    routes = serving.get_routes()
    batch_route = next(r for r in routes if r["path"] == "/fabric/_batch")
    handler = batch_route["handler"]

    response = await handler(products="live_metrics")

    assert response["_status"] == 200
    batch_data = response["data"]
    assert "live_metrics" in batch_data
    result = batch_data["live_metrics"]
    assert result["data"] is not None, "Batch virtual product returned data: None"
    assert result["data"]["dau"] == 500
    assert result["data"]["mau"] == 2000


# ===========================================================================
# #245 — Materialized product still returns 202 when cold (no regression)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_materialized_product_returns_202_when_cold():
    """Materialized product with no cache returns 202 (warming), not data.

    Regression guard: ensures the virtual product fix doesn't break
    the existing materialized product cold-start behavior.
    """
    source = MockSource("db", data={"": [{"id": 1}]})
    await source.connect()

    async def report(ctx: FabricContext) -> Dict[str, Any]:
        return {"total": 42}

    product_reg = _make_product_registration(
        "report", report, mode="materialized", depends_on=["db"]
    )
    products = {"report": product_reg}

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    sources_dict = {"db": {"adapter": source, "config": None, "name": "db"}}

    serving = FabricServingLayer(
        products=products,
        pipeline_executor=pipeline,
        express=None,
        sources=sources_dict,
    )

    routes = serving.get_routes()
    get_route = next(r for r in routes if r["path"] == "/fabric/report")
    handler = get_route["handler"]

    # No cache exists — materialized should return 202
    response = await handler()

    assert response["_status"] == 202
    assert response["data"]["status"] == "warming"
    assert response["_headers"]["X-Fabric-Freshness"] == "cold"


# ===========================================================================
# #248 — dev_mode pre-warming with prewarm=True
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_dev_mode_prewarm_true_warms_products():
    """dev_mode=True with prewarm=True pre-warms products on start.

    Regression: #248 — dev_mode skipped pre-warming entirely, so the
    first request always got a 202 instead of cached data.
    """
    source = MockSource("src", data={"": {"value": 42}})

    async def my_product(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("src").fetch()
        return {"result": data["value"]}

    product_reg = _make_product_registration(
        "my_product", my_product, mode="materialized", depends_on=["src"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    sources = {"src": {"name": "src", "config": None, "adapter": source}}
    products = {"my_product": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    # Start with prewarm=True (default)
    await runtime.start(prewarm=True)

    # Product should be cached from pre-warming
    assert runtime.pipeline is not None
    cached = await runtime.pipeline.get_cached("my_product")
    assert (
        cached is not None
    ), "Product was not pre-warmed despite dev_mode=True, prewarm=True"

    await runtime.stop()


# ===========================================================================
# #248 — dev_mode pre-warming with prewarm=False
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_dev_mode_prewarm_false_skips_warming():
    """dev_mode=True with prewarm=False does NOT pre-warm products.

    When prewarm=False is explicitly passed, products should not be
    warmed on startup — the first request gets a 202 (cold).
    """
    source = MockSource("src", data={"": {"value": 99}})

    async def my_product(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("src").fetch()
        return {"result": data["value"]}

    product_reg = _make_product_registration(
        "my_product", my_product, mode="materialized", depends_on=["src"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    sources = {"src": {"name": "src", "config": None, "adapter": source}}
    products = {"my_product": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    # Start with prewarm=False
    await runtime.start(prewarm=False)

    # Product should NOT be cached
    assert runtime.pipeline is not None
    cached = await runtime.pipeline.get_cached("my_product")
    assert cached is None, "Product was pre-warmed despite prewarm=False"

    await runtime.stop()


# ===========================================================================
# #253 — ChangeDetector receives adapter objects, not dicts
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_change_detector_receives_adapters_not_dicts():
    """ChangeDetector receives adapter objects — no AttributeError.

    Regression: #253 — ChangeDetector received self._sources (dicts) and
    every poll cycle failed with AttributeError: 'dict' object has no
    attribute 'safe_detect_change'.
    """
    source = MockSource("files", data={"": [{"file": "a.csv"}]})
    await source.connect()

    async def file_report(ctx: FabricContext) -> Dict[str, Any]:
        return {"count": 1}

    product_reg = _make_product_registration(
        "file_report", file_report, depends_on=["files"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    # Pass adapter objects directly — this is what the runtime fix now does
    adapter_sources = {"files": source}

    detector = ChangeDetector(
        sources=adapter_sources,
        products={"file_report": product_reg},
        pipeline_executor=pipeline,
        dev_mode=True,
    )

    # Start the detector — if it receives dicts, this crashes with
    # AttributeError: 'dict' has no attribute 'safe_detect_change'
    await detector.start()

    # Let at least one poll cycle run
    await asyncio.sleep(0.1)

    # Should have tasks running without errors
    assert detector.running is True
    assert detector.task_count == 1

    await detector.stop()


# ===========================================================================
# #253 — Change detection fires when source changes
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_change_detection_fires_on_source_change():
    """Change detection triggers product refresh when source data changes.

    Verifies the full change detection path: MockSource.trigger_change ->
    ChangeDetector poll -> on_change callback fires with product name.
    """
    source = MockSource("api", data={"": {"version": 1}})
    await source.connect()

    async def api_report(ctx: FabricContext) -> Dict[str, Any]:
        return {"version": 1}

    product_reg = _make_product_registration(
        "api_report", api_report, depends_on=["api"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    adapter_sources = {"api": source}
    triggered: List[str] = []

    async def on_change(product_name: str, triggered_by: str) -> None:
        triggered.append(f"{product_name}:{triggered_by}")

    detector = ChangeDetector(
        sources=adapter_sources,
        products={"api_report": product_reg},
        pipeline_executor=pipeline,
        dev_mode=True,
    )
    detector.set_on_change(on_change)

    # Override poll interval to be fast for testing.
    # Access via __dict__ to get the actual staticmethod descriptor
    # (not the unwrapped function), so we can restore it properly.
    original_descriptor = ChangeDetector.__dict__["_get_poll_interval"]
    ChangeDetector._get_poll_interval = staticmethod(lambda adapter: 0.05)

    try:
        await detector.start()

        # Let the fingerprint seed complete before triggering a change.
        # The seed calls safe_detect_change() once to prime internal
        # change-tracking state; triggering too early races with it. (#1492)
        # Poll until at least one poll cycle has elapsed, then trigger.
        await asyncio.sleep(0.1)

        # Trigger a source change
        source.trigger_change()

        # Wait for the poll loop to detect the change
        for _ in range(20):
            if triggered:
                break
            await asyncio.sleep(0.05)

        assert len(triggered) > 0, "Change detection callback was never fired"
        assert triggered[0] == "api_report:api"
    finally:
        ChangeDetector._get_poll_interval = original_descriptor
        await detector.stop()


# ===========================================================================
# #253 — Runtime integration: full start/stop with change detection
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_runtime_start_stop_with_change_detection():
    """FabricRuntime start/stop with change detection does not crash.

    Regression: #253 — runtime passed self._sources (dicts) to
    ChangeDetector, causing AttributeError on every poll cycle.
    This test verifies the full runtime lifecycle works cleanly.
    """
    source = MockSource("events", data={"": {"count": 10}})

    async def event_summary(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("events").fetch()
        return {"total": data["count"]}

    product_reg = _make_product_registration(
        "event_summary", event_summary, mode="materialized", depends_on=["events"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    sources = {"events": {"name": "events", "config": None, "adapter": source}}
    products = {"event_summary": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    # Start runtime — this now extracts adapters before passing to
    # ChangeDetector. Previously this would create ChangeDetector
    # with dicts, and every poll cycle would crash.
    await runtime.start()

    status = runtime.status()
    assert status["started"] is True
    assert status["leader"] is True

    # Verify product was pre-warmed (dev_mode + prewarm=True default)
    cached = await runtime.pipeline.get_cached("event_summary")
    assert cached is not None, "Product not pre-warmed after runtime.start()"

    # Let change detection run at least one poll cycle without crashing
    await asyncio.sleep(0.2)

    await runtime.stop()
    assert runtime.status()["started"] is False


# ===========================================================================
# #1492 — Fingerprint seed prevents startup poll storm
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_change_detector_no_startup_storm_with_fresh_adapter():
    """First poll seeds fingerprint; no product dispatch before poll_interval.

    Regression: #1492 — a fresh adapter whose ``detect_change`` returns
    ``True`` on the first call (because it has no prior fingerprint state)
    would storm-materialize every dependent product at t=0, concurrent
    with the startup pre-warm pass. The fix seeds the adapter's fingerprint
    state before entering the main poll loop so the first real poll after
    ``poll_interval`` only reports changes that occurred AFTER startup.
    """
    # Simulate a fresh adapter that reports "changed" on its first poll
    # (a real adapter with empty change-state would do this).
    source = MockSource("db", data={"": {"rows": 100}}, change_detected=True)
    await source.connect()

    async def report(ctx: FabricContext) -> Dict[str, Any]:
        return {"count": 1}

    product_reg = _make_product_registration("report", report, depends_on=["db"])

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    adapter_sources = {"db": source}
    triggered: List[str] = []

    async def on_change(product_name: str, triggered_by: str) -> None:
        triggered.append(f"{product_name}:{triggered_by}")

    detector = ChangeDetector(
        sources=adapter_sources,
        products={"report": product_reg},
        pipeline_executor=pipeline,
        dev_mode=True,
    )
    detector.set_on_change(on_change)

    # Override poll interval to 0.05s for fast test.
    original_descriptor = ChangeDetector.__dict__["_get_poll_interval"]
    ChangeDetector._get_poll_interval = staticmethod(lambda adapter: 0.05)

    try:
        await detector.start()

        # Wait for 3+ poll cycles — if the seed didn't work, the first
        # real poll would have dispatched the product by now.
        await asyncio.sleep(0.2)

        assert len(triggered) == 0, (
            f"Startup poll storm: {len(triggered)} product(s) dispatched "
            f"before poll_interval elapsed — fingerprint seed did not "
            f"prevent the storm: {triggered}"
        )
        assert detector.running is True
        assert detector.task_count == 1
    finally:
        ChangeDetector._get_poll_interval = original_descriptor
        await detector.stop()


# ===========================================================================
# #1492 — max_concurrent threaded through FabricRuntime.start()
# ===========================================================================


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_fabric_runtime_respects_max_concurrent():
    """FabricRuntime.start() threads max_concurrent to PipelineExecutor.

    Regression: #1492 — ``PipelineExecutor(max_concurrent=…)`` existed but
    ``FabricRuntime`` constructed it without passing ``max_concurrent``,
    and ``FabricRuntime.start()`` / ``DataFlow.start()`` did not expose it.
    Callers could not bound startup materialization concurrency.
    """
    source = MockSource("csv", data={"": {"rows": 42}})

    async def summary(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("csv").fetch()
        return {"total": data["rows"]}

    product_reg = _make_product_registration(
        "summary", summary, mode="materialized", depends_on=["csv"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    sources = {"csv": {"name": "csv", "config": None, "adapter": source}}
    products = {"summary": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
        max_concurrent=7,
    )
    await runtime.start()

    assert runtime.pipeline is not None
    # The semaphore bound reflects the passed max_concurrent.
    assert (
        runtime.pipeline._max_concurrent == 7
    ), f"Expected max_concurrent=7, got {runtime.pipeline._max_concurrent}"

    await runtime.stop()
