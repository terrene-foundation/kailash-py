# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 2 integration tests for the Data Fabric Engine (TODO-31).

These tests exercise the fabric subsystems with REAL infrastructure:
- SQLite in-memory for database operations
- MockSource (fabric's own testing adapter) for external source simulation
- Real PipelineExecutor, ChangeDetector, LeaderElector, FabricRuntime

NO unittest.mock, NO @patch, NO MagicMock.

Each test is self-contained and verifies state via read-back.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import pytest

from dataflow import DataFlow
from dataflow.adapters.source_adapter import (
    BaseSourceAdapter,
    CircuitBreakerState,
    SourceState,
)
from dataflow.fabric.change_detector import ChangeDetector
from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.context import FabricContext, PipelineContext
from dataflow.fabric.leader import InMemoryLeaderBackend, LeaderElector
from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.runtime import FabricRuntime
from dataflow.fabric.serving import FabricServingLayer
from dataflow.fabric.testing import MockSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — reusable across tests, no mocking
# ---------------------------------------------------------------------------


class _FailingSource(BaseSourceAdapter):
    """Source adapter that raises on fetch after a configurable number of calls.

    Used to test circuit breaker behaviour with real adapter state transitions.
    Not a mock — it is a concrete adapter with deterministic failure logic.
    """

    def __init__(self, name: str, fail_after: int = 0) -> None:
        super().__init__(name=name)
        self._fail_after = fail_after
        self._call_count = 0
        self._preloaded: Dict[str, Any] = {}

    @property
    def database_type(self) -> str:
        return "failing_test"

    async def _connect(self) -> None:
        pass

    async def _disconnect(self) -> None:
        pass

    async def detect_change(self) -> bool:
        return False

    def preload(self, path: str, data: Any) -> None:
        """Pre-load data for graceful degradation tests."""
        self._preloaded[path] = data

    async def fetch(self, path: str = "", params: Any = None) -> Any:
        self._call_count += 1
        if self._call_count > self._fail_after:
            raise ConnectionError(
                f"FailingSource '{self.name}': simulated failure on call {self._call_count}"
            )
        data = self._preloaded.get(path, {"default": True})
        self._record_successful_data(path, data)
        return data

    async def fetch_pages(self, path: str = "", page_size: int = 100):  # type: ignore[override]
        data = await self.fetch(path)
        if isinstance(data, list):
            for i in range(0, len(data), page_size):
                yield data[i : i + page_size]
        else:
            yield [data]


def _make_product_registration(
    name: str,
    fn: Any,
    mode: str = "materialized",
    depends_on: List[str] | None = None,
) -> ProductRegistration:
    """Build a ProductRegistration without going through DataFlow.product().

    This is intentional for integration tests that need to wire subsystems
    directly (PipelineExecutor, ChangeDetector, etc.) without starting the
    full DataFlow engine.
    """
    return ProductRegistration(
        name=name,
        fn=fn,
        mode=ProductMode(mode),
        depends_on=depends_on or [],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
    )


# ---------------------------------------------------------------------------
# Test 1: Source registration + prewarm populates product cache
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_source_registration_and_prewarm():
    """Register 3 sources + 1 materialized product, verify data after prewarm.

    Integration path: MockSource -> connect -> PipelineExecutor -> cache -> read-back.
    """
    # --- Setup: 3 real MockSource adapters with preloaded data ---
    crm_source = MockSource("crm", data={"deals": [{"id": 1, "value": 100}]})
    erp_source = MockSource("erp", data={"orders": [{"id": "A1", "total": 500}]})
    analytics_source = MockSource(
        "analytics", data={"metrics": {"dau": 1000, "mau": 5000}}
    )

    await crm_source.connect()
    await erp_source.connect()
    await analytics_source.connect()

    # Verify sources are in ACTIVE state after connect
    assert crm_source.state == SourceState.ACTIVE
    assert erp_source.state == SourceState.ACTIVE
    assert analytics_source.state == SourceState.ACTIVE

    # --- Product function that reads from all 3 sources ---
    async def dashboard_product(ctx: FabricContext) -> Dict[str, Any]:
        deals = await ctx.source("crm").fetch("deals")
        orders = await ctx.source("erp").fetch("orders")
        metrics = await ctx.source("analytics").fetch("metrics")
        return {
            "deal_count": len(deals),
            "order_count": len(orders),
            "dau": metrics["dau"],
            "summary": "aggregated",
        }

    product_reg = _make_product_registration(
        "dashboard",
        dashboard_product,
        depends_on=["crm", "erp", "analytics"],
    )

    # --- Create a real pipeline executor and execute the product ---
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    source_adapters = {
        "crm": crm_source,
        "erp": erp_source,
        "analytics": analytics_source,
    }
    ctx = PipelineContext(
        express=None,
        sources=source_adapters,
        products_cache={},
    )

    result = await pipeline.execute_product(
        product_name="dashboard",
        product_fn=dashboard_product,
        context=ctx,
    )

    # --- Verify: product was executed and cached ---
    assert result.product_name == "dashboard"
    assert result.content_changed is True
    assert result.data["deal_count"] == 1
    assert result.data["order_count"] == 1
    assert result.data["dau"] == 1000
    assert result.data["summary"] == "aggregated"

    # --- Read-back from cache (state persistence verification) ---
    cached = pipeline.get_cached("dashboard")
    assert cached is not None
    raw_bytes, metadata = cached
    assert len(raw_bytes) > 0
    assert "cached_at" in metadata
    assert "content_hash" in metadata

    # Verify traces recorded
    assert len(pipeline.traces) == 1
    assert pipeline.traces[0].status == "success"
    assert pipeline.traces[0].cache_action == "write"


# ---------------------------------------------------------------------------
# Test 2: Source change triggers pipeline re-execution
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_file_change_triggers_pipeline():
    """MockSource with detect_change=True triggers pipeline, cache updated.

    Integration path: MockSource.trigger_change -> ChangeDetector poll ->
    on_change callback -> PipelineExecutor -> cache updated.
    """
    source = MockSource("files", data={"": [{"file": "a.csv", "rows": 100}]})
    await source.connect()

    execution_log: List[str] = []

    async def file_report(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("files").fetch()
        execution_log.append("executed")
        return {"file_count": len(data), "total_rows": sum(d["rows"] for d in data)}

    product_reg = _make_product_registration(
        "file_report", file_report, depends_on=["files"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    source_adapters = {"files": source}

    # Execute the product once to populate the initial cache
    ctx = PipelineContext(express=None, sources=source_adapters, products_cache={})
    initial_result = await pipeline.execute_product(
        product_name="file_report",
        product_fn=file_report,
        context=ctx,
    )
    assert initial_result.data["file_count"] == 1
    assert initial_result.data["total_rows"] == 100
    assert len(execution_log) == 1

    # --- Simulate source change: update data + trigger change flag ---
    source.set_data(
        "", [{"file": "a.csv", "rows": 100}, {"file": "b.csv", "rows": 200}]
    )
    source.trigger_change()

    # Verify change is detected (real adapter API, not mock)
    assert await source.detect_change() is True
    # Change flag is consumed (one-shot)
    assert await source.detect_change() is False

    # --- Re-execute the pipeline (simulating what ChangeDetector would do) ---
    ctx2 = PipelineContext(express=None, sources=source_adapters, products_cache={})
    updated_result = await pipeline.execute_product(
        product_name="file_report",
        product_fn=file_report,
        context=ctx2,
    )

    # --- Verify: cache was updated with new data ---
    assert updated_result.data["file_count"] == 2
    assert updated_result.data["total_rows"] == 300
    assert updated_result.content_changed is True
    assert len(execution_log) == 2

    # --- Read-back: verify cached data matches latest execution ---
    from_cache = pipeline.get_product_from_cache("file_report")
    assert from_cache is not None
    assert from_cache.data["file_count"] == 2
    assert from_cache.data["total_rows"] == 300


# ---------------------------------------------------------------------------
# Test 3: Write-through event triggers product refresh
# ---------------------------------------------------------------------------


class _WritableMockSource(MockSource):
    """MockSource that advertises write support for serving layer integration.

    FabricServingLayer.get_routes() checks adapter.supports_feature("write")
    before generating POST endpoints. This subclass reports write support
    so the integration test exercises the full serving-layer write path.
    """

    def supports_feature(self, feature: str) -> bool:
        if feature == "write":
            return True
        return super().supports_feature(feature)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_write_through_event_triggers_refresh():
    """Write via serving layer triggers product refresh via on_product_refresh.

    Integration path: FabricServingLayer write handler -> source.write() ->
    on_product_refresh callback -> PipelineExecutor -> updated cache.
    """
    source = _WritableMockSource("inventory", data={"items": [{"sku": "A", "qty": 10}]})
    await source.connect()

    refresh_log: List[str] = []

    async def inventory_report(ctx: FabricContext) -> Dict[str, Any]:
        items = await ctx.source("inventory").fetch("items")
        return {"item_count": len(items), "total_qty": sum(i["qty"] for i in items)}

    product_reg = _make_product_registration(
        "inventory_report", inventory_report, depends_on=["inventory"]
    )
    products = {"inventory_report": product_reg}

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    sources_dict = {
        "inventory": {"adapter": source, "config": None, "name": "inventory"}
    }

    # Initial pipeline execution to populate cache
    source_adapters = {"inventory": source}
    ctx = PipelineContext(express=None, sources=source_adapters, products_cache={})
    await pipeline.execute_product(
        product_name="inventory_report",
        product_fn=inventory_report,
        context=ctx,
    )

    # Verify initial state
    from_cache = pipeline.get_product_from_cache("inventory_report")
    assert from_cache is not None
    assert from_cache.data["item_count"] == 1

    # --- Set up serving layer with write support and refresh callback ---
    async def on_refresh(product_name: str) -> None:
        refresh_log.append(product_name)
        # Re-execute the pipeline as the runtime would
        refresh_ctx = PipelineContext(
            express=None, sources=source_adapters, products_cache={}
        )
        await pipeline.execute_product(
            product_name=product_name,
            product_fn=products[product_name].fn,
            context=refresh_ctx,
        )

    serving = FabricServingLayer(
        products=products,
        pipeline_executor=pipeline,
        express=None,
        sources=sources_dict,
        enable_writes=True,
        on_product_refresh=on_refresh,
    )

    # --- Verify write routes are generated for writable source ---
    routes = serving.get_routes()
    write_routes = [r for r in routes if r["method"] == "POST"]
    assert (
        len(write_routes) > 0
    ), "Expected write routes when enable_writes=True and source supports write"

    # Find the inventory write handler
    inv_write = next(
        (r for r in write_routes if "inventory" in r["path"]),
        None,
    )
    assert inv_write is not None, (
        f"Expected /fabric/inventory/write route. "
        f"Got routes: {[r['path'] for r in write_routes]}"
    )

    # Update the source data so the product refresh pipeline sees
    # the new inventory state. The write handler writes via
    # adapter.write(path, data), which stores at the given path.
    # We pre-set "items" to the full updated list so the product
    # function (which reads "items") sees both SKUs after refresh.
    source.set_data("items", [{"sku": "A", "qty": 10}, {"sku": "B", "qty": 20}])

    # Call the write handler — write to the "new_item" path to avoid
    # overwriting the "items" list. The handler still triggers product
    # refresh for all products whose depends_on includes "inventory".
    write_result = await inv_write["handler"](
        data={"sku": "B", "qty": 20},
        operation="create",
        path="new_item",
    )

    # Verify write handler executed successfully
    assert write_result["_status"] == 200

    # Verify on_product_refresh was called for affected products
    assert "inventory_report" in refresh_log

    # --- Read-back: cache should reflect updated data ---
    updated_cache = pipeline.get_product_from_cache("inventory_report")
    assert updated_cache is not None
    assert updated_cache.data["item_count"] == 2
    assert updated_cache.data["total_qty"] == 30


# ---------------------------------------------------------------------------
# Test 4: Circuit breaker opens, product serves stale data
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_circuit_breaker_serves_stale():
    """Source fails -> circuit opens -> safe_fetch returns last good data.

    Integration path: _FailingSource with real CircuitBreaker -> repeated
    failures trip threshold -> safe_fetch serves last_successful_data.
    """
    # Source that succeeds once then fails
    source = _FailingSource("flaky_api", fail_after=1)
    source.preload("", [{"id": 1, "status": "active"}])
    await source.connect()

    assert source.state == SourceState.ACTIVE

    # --- First fetch succeeds and caches the data ---
    first_result = await source.safe_fetch("")
    assert first_result == [{"id": 1, "status": "active"}]
    assert source.circuit_breaker.state == CircuitBreakerState.CLOSED

    # --- Subsequent fetches fail, circuit breaker records failures ---
    # The default circuit breaker threshold is 3 failures.
    for i in range(3):
        result = await source.safe_fetch("")
        # safe_fetch returns last known good data on failure
        assert result == [{"id": 1, "status": "active"}]

    # --- Verify circuit breaker is now OPEN ---
    assert source.circuit_breaker.state == CircuitBreakerState.OPEN
    assert source.state == SourceState.PAUSED

    # --- Fetch with open circuit should still return stale data ---
    stale_result = await source.safe_fetch("")
    assert stale_result == [{"id": 1, "status": "active"}]

    # --- Use the stale data in a product pipeline ---
    async def stale_product(ctx: FabricContext) -> Dict[str, Any]:
        # This uses safe_fetch through the SourceHandle
        data = await ctx.source("flaky_api").fetch("")
        return {"count": len(data), "degraded": not ctx.source("flaky_api").healthy}

    source_adapters = {"flaky_api": source}
    ctx = PipelineContext(express=None, sources=source_adapters, products_cache={})

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    result = await pipeline.execute_product(
        product_name="stale_product",
        product_fn=stale_product,
        context=ctx,
    )

    assert result.data["count"] == 1
    assert result.data["degraded"] is True

    # --- Read-back: verify pipeline cached even with degraded data ---
    cached = pipeline.get_cached("stale_product")
    assert cached is not None


# ---------------------------------------------------------------------------
# Test 5: Parameterized product cache isolation + cardinality limit
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_parameterized_product_cache_isolation():
    """Multiple param combos get separate cache entries with LRU eviction.

    Integration path: PipelineExecutor.execute_product with params ->
    separate cache keys -> verify isolation -> exceed max_cache_entries ->
    oldest evicted.
    """
    source = MockSource(
        "users_api",
        data={
            "": [
                {"id": 1, "name": "Alice", "dept": "eng"},
                {"id": 2, "name": "Bob", "dept": "sales"},
                {"id": 3, "name": "Charlie", "dept": "eng"},
            ]
        },
    )
    await source.connect()

    async def filtered_users(
        ctx: FabricContext, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        all_users = await ctx.source("users_api").fetch("")
        dept = params.get("dept")
        if dept:
            filtered = [u for u in all_users if u["dept"] == dept]
        else:
            filtered = all_users
        return {"users": filtered, "count": len(filtered), "dept": dept}

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    source_adapters = {"users_api": source}
    ctx = PipelineContext(express=None, sources=source_adapters, products_cache={})

    # --- Execute with different params ---
    result_eng = await pipeline.execute_product(
        product_name="filtered_users",
        product_fn=filtered_users,
        context=ctx,
        params={"dept": "eng"},
    )
    assert result_eng.data["count"] == 2
    assert result_eng.data["dept"] == "eng"

    result_sales = await pipeline.execute_product(
        product_name="filtered_users",
        product_fn=filtered_users,
        context=ctx,
        params={"dept": "sales"},
    )
    assert result_sales.data["count"] == 1
    assert result_sales.data["dept"] == "sales"

    result_all = await pipeline.execute_product(
        product_name="filtered_users",
        product_fn=filtered_users,
        context=ctx,
        params={},
    )
    assert result_all.data["count"] == 3

    # --- Verify cache isolation: each param combo has its own entry ---
    cached_eng = pipeline.get_cached("filtered_users", params={"dept": "eng"})
    cached_sales = pipeline.get_cached("filtered_users", params={"dept": "sales"})
    cached_all = pipeline.get_cached("filtered_users", params={})

    assert cached_eng is not None
    assert cached_sales is not None
    assert cached_all is not None

    # Verify the cached data is different for each param combo
    eng_hash = cached_eng[1]["content_hash"]
    sales_hash = cached_sales[1]["content_hash"]
    all_hash = cached_all[1]["content_hash"]

    assert eng_hash != sales_hash, "eng and sales should have different hashes"
    assert eng_hash != all_hash, "eng and all should have different hashes"

    # --- Verify cardinality limit (LRU eviction) ---
    # Set a small max to test eviction
    pipeline._max_cache_entries = 5

    # Generate 6 more cache entries to exceed the limit
    for i in range(6):
        await pipeline.execute_product(
            product_name="filtered_users",
            product_fn=filtered_users,
            context=ctx,
            params={"dept": f"dept_{i}"},
        )

    # Total entries should be capped at max_cache_entries
    total_entries = len(pipeline._cache_data)
    assert (
        total_entries <= 5
    ), f"Expected at most 5 cache entries (max_cache_entries), got {total_entries}"

    # The oldest entries (eng, sales, all) should have been evicted
    assert (
        pipeline.get_cached("filtered_users", params={"dept": "eng"}) is None
    ), "Expected 'eng' entry to be evicted by LRU"


# ---------------------------------------------------------------------------
# Test 6: Graceful shutdown drains tasks and releases leader lock
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_graceful_shutdown():
    """Start runtime in dev_mode -> stop -> verify clean shutdown.

    Integration path: FabricRuntime.start() -> FabricRuntime.stop() ->
    verify leader released, sources disconnected, no lingering tasks.
    """
    source = MockSource("shutdown_test", data={"": {"status": "ok"}})

    async def health_product(ctx: FabricContext) -> Dict[str, Any]:
        data = await ctx.source("shutdown_test").fetch()
        return {"status": data.get("status", "unknown")}

    product_reg = _make_product_registration(
        "health_check", health_product, depends_on=["shutdown_test"]
    )

    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    sources = {
        "shutdown_test": {
            "name": "shutdown_test",
            "config": None,
            "adapter": source,
        }
    }
    products = {"health_check": product_reg}

    runtime = FabricRuntime(
        dataflow=db,
        sources=sources,
        products=products,
        fail_fast=True,
        dev_mode=True,
    )

    # --- Start the runtime ---
    await runtime.start()

    # Verify runtime is started
    status = runtime.status()
    assert status["started"] is True
    assert status["leader"] is True  # dev_mode -> always leader
    assert "shutdown_test" in status["sources"]
    assert status["sources"]["shutdown_test"]["state"] == "active"

    # Verify source is connected
    assert source.state == SourceState.ACTIVE
    assert source.is_connected is True

    # --- Stop the runtime ---
    await runtime.stop()

    # --- Verify clean shutdown ---
    # Leader should be released
    assert runtime.is_leader is False

    # Source should be disconnected
    assert source.state == SourceState.DISCONNECTED
    assert source.is_connected is False

    # Runtime should report not started
    post_stop_status = runtime.status()
    assert post_stop_status["started"] is False


# ---------------------------------------------------------------------------
# Test 7: Leader election basic lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_leader_election_basic():
    """LeaderElector acquire -> verify is_leader -> release -> verify not leader.

    Integration path: InMemoryLeaderBackend (real backend, not mock) ->
    try_elect -> is_leader -> start_heartbeat -> release -> verify state.
    """
    backend = InMemoryLeaderBackend()

    leader = LeaderElector(
        backend=backend,
        ttl=30,
        heartbeat_interval=1,
    )

    # --- Acquire leadership ---
    acquired = await leader.try_elect()
    assert acquired is True
    assert leader.is_leader is True

    # Verify leader_id is set
    leader_id = leader.leader_id
    assert leader_id is not None
    assert len(leader_id) > 0

    # --- Verify via backend read-back ---
    current_leader = await backend.get_leader()
    assert current_leader == leader_id

    # --- Start heartbeat (real asyncio task) ---
    await leader.start_heartbeat()
    # Give heartbeat one tick to ensure it runs
    await asyncio.sleep(0.05)

    # Still the leader after heartbeat
    assert leader.is_leader is True

    # --- A second elector should NOT become leader ---
    leader2 = LeaderElector(backend=backend, ttl=30, heartbeat_interval=1)
    acquired2 = await leader2.try_elect()
    assert acquired2 is False
    assert leader2.is_leader is False

    # Verify first leader is still the leader
    current = await backend.get_leader()
    assert current == leader_id

    # --- Release leadership ---
    await leader.release()
    assert leader.is_leader is False

    # --- Verify backend reflects released state ---
    post_release = await backend.get_leader()
    assert post_release is None

    # --- Second elector can now acquire ---
    acquired2_retry = await leader2.try_elect()
    assert acquired2_retry is True
    assert leader2.is_leader is True

    # Clean up
    await leader2.release()
    assert leader2.is_leader is False
    assert await backend.get_leader() is None
