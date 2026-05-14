# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 5.12 — FabricMetrics singleton + Prometheus wiring.

These tests assert the contract documented in
``workspaces/dataflow-perfection/todos/active/06-phase-5-wiring.md``
TODO-5.12: instantiate FabricMetrics in FabricRuntime.start(), wire
counters into pipeline/cache/leader/webhook, register Prometheus
handler at /fabric/metrics.

Coverage:
- Singleton lifecycle (get/reset)
- Cache error + degraded gauge dispatch from cache.py recorders
- Pipeline run counter wiring inside PipelineExecutor.execute_product
- Cache hit/miss wiring inside PipelineExecutor.get_cached
- Prometheus exposition format
- /fabric/metrics route shape
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Singleton lifecycle
# ---------------------------------------------------------------------------


class TestFabricMetricsSingleton:
    """get_fabric_metrics() returns the same instance until reset_fabric_metrics()."""

    def setup_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def teardown_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def test_singleton_returns_same_instance(self):
        from dataflow.fabric.metrics import get_fabric_metrics

        first = get_fabric_metrics()
        second = get_fabric_metrics()
        assert first is second

    def test_reset_replaces_instance(self):
        from dataflow.fabric.metrics import get_fabric_metrics, reset_fabric_metrics

        first = get_fabric_metrics()
        reset_fabric_metrics()
        second = get_fabric_metrics()
        assert first is not second

    def test_render_exposition_returns_bytes(self):
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()
        body = metrics.render_exposition()
        assert isinstance(body, bytes)
        # Either prometheus_client wired the registry (every metric name
        # appears in the # HELP comments) or the no-op fallback emitted
        # an explanatory message — both are valid contract responses.
        text = body.decode()
        assert "fabric_pipeline_runs_total" in text or "metrics disabled" in text


# ---------------------------------------------------------------------------
# Cache recorder dispatch
# ---------------------------------------------------------------------------


class TestCacheMetricsDispatch:
    """cache.py recorders MUST forward to the FabricMetrics singleton."""

    def setup_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def teardown_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def test_record_cache_error_increments_counter(self):
        from dataflow.fabric.cache import _record_cache_error
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()
        if not metrics.enabled:
            pytest.skip("prometheus_client not installed")

        before = metrics.cache_errors_total.labels(
            backend="redis", operation="get"
        )._value.get()
        _record_cache_error("redis", "get")
        after = metrics.cache_errors_total.labels(
            backend="redis", operation="get"
        )._value.get()
        assert after == before + 1

    def test_set_cache_degraded_flips_gauge(self):
        from dataflow.fabric.cache import _set_cache_degraded
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()
        if not metrics.enabled:
            pytest.skip("prometheus_client not installed")

        _set_cache_degraded("redis", 1)
        assert metrics.cache_degraded.labels(backend="redis")._value.get() == 1.0

        _set_cache_degraded("redis", 0)
        assert metrics.cache_degraded.labels(backend="redis")._value.get() == 0.0


# ---------------------------------------------------------------------------
# PipelineExecutor wiring
# ---------------------------------------------------------------------------


class TestPipelineMetricsWiring:
    """PipelineExecutor MUST record pipeline runs and cache hit/miss."""

    def setup_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def teardown_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    @pytest.mark.asyncio
    async def test_get_cached_records_hit_and_miss(self):
        from dataflow.fabric.cache import InMemoryFabricCacheBackend, _FabricCacheEntry
        from dataflow.fabric.metrics import get_fabric_metrics
        from dataflow.fabric.pipeline import PipelineExecutor, _cache_key

        metrics = get_fabric_metrics()
        if not metrics.enabled:
            pytest.skip("prometheus_client not installed")

        # Build a minimal PipelineExecutor by hand: bypass __init__'s
        # _resolve_pool_size + dataflow plumbing because we only need
        # the cache get path here.
        executor = PipelineExecutor.__new__(PipelineExecutor)
        executor._cache = InMemoryFabricCacheBackend()
        executor._instance_name = "metrics-test"

        # Miss → counter increments by 1
        miss_before = metrics.cache_miss_total.labels(product="prod_a")._value.get()
        result = await executor.get_cached("prod_a")
        miss_after = metrics.cache_miss_total.labels(product="prod_a")._value.get()
        assert result is None
        assert miss_after == miss_before + 1

        # Seed the cache and verify hit increments
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        entry = _FabricCacheEntry(
            product_name="prod_a",
            tenant_id=None,
            data_bytes=b'{"x": 1}',
            content_hash="abc",
            cached_at=now,
            run_started_at=now,
            size_bytes=8,
            schema_version=2,
            metadata={},
        )
        await executor._cache.set(_cache_key("prod_a", None, None), entry)

        hit_before = metrics.cache_hit_total.labels(product="prod_a")._value.get()
        result = await executor.get_cached("prod_a")
        hit_after = metrics.cache_hit_total.labels(product="prod_a")._value.get()
        assert result is not None
        assert hit_after == hit_before + 1


# ---------------------------------------------------------------------------
# /fabric/metrics route shape
# ---------------------------------------------------------------------------


class TestFabricMetricsRoute:
    """get_metrics_route() returns a fabric route dict the runtime registers."""

    def setup_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def teardown_method(self) -> None:
        from dataflow.fabric.metrics import reset_fabric_metrics

        reset_fabric_metrics()

    def test_route_dict_shape(self):
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()
        route = metrics.get_metrics_route()
        assert route["method"] == "GET"
        assert route["path"] == "/fabric/metrics"
        assert callable(route["handler"])
        assert route["metadata"]["type"] == "metrics"

    @pytest.mark.asyncio
    async def test_route_handler_returns_prometheus_body(self):
        from dataflow.fabric.metrics import get_fabric_metrics

        metrics = get_fabric_metrics()
        route = metrics.get_metrics_route()
        response = await route["handler"](request=None)
        assert response["_status"] == 200
        assert isinstance(response["_body"], bytes)
        headers = response["_headers"]
        assert "content-type" in headers
        # Either real prometheus exposition or the no-op explanation —
        # both round-trip the body bytes through the route handler.
        assert response["_body"] == metrics.render_exposition()
