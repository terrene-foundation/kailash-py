"""Tests for the connection metrics FastAPI router.

Validates the /connections/metrics, /connections/pools, and
/connections/alerts endpoints as well as Prometheus line generation.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.kailash.servers.connection_metrics_router import (
    ConnectionMetricsProvider,
    create_connection_metrics_router,
)


class _FakePool:
    """Fake pool source for testing."""

    def __init__(self, stats: dict):
        self._stats = stats

    async def get_pool_statistics(self):
        return self._stats


def _make_app(provider: ConnectionMetricsProvider | None = None) -> FastAPI:
    """Create a minimal FastAPI app with the connection metrics router."""
    app = FastAPI()
    router = create_connection_metrics_router(provider)
    app.include_router(router, prefix="/connections")
    return app


class TestConnectionMetricsRouter:
    """Endpoint tests for the connection metrics router."""

    def test_metrics_endpoint_empty(self):
        """GET /connections/metrics returns empty pool data when no sources."""
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/connections/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert data["pools"] == {}

    def test_metrics_endpoint_with_pool(self):
        """GET /connections/metrics returns stats from registered pool."""
        provider = ConnectionMetricsProvider()
        provider.register_source(
            "test_pool",
            _FakePool(
                {
                    "health_score": 90,
                    "active_connections": 5,
                    "total_connections": 10,
                    "utilization": 0.5,
                    "queries_per_second": 100.0,
                    "avg_query_time_ms": 5.0,
                    "error_rate": 0.01,
                }
            ),
        )
        app = _make_app(provider)
        client = TestClient(app)

        resp = client.get("/connections/metrics")
        assert resp.status_code == 200
        pools = resp.json()["pools"]
        assert "test_pool" in pools
        assert pools["test_pool"]["utilization"] == 0.5

    def test_pools_endpoint_status_classification(self):
        """GET /connections/pools assigns correct health status."""
        provider = ConnectionMetricsProvider()
        provider.register_source(
            "healthy_pool", _FakePool({"utilization": 0.3, "error_rate": 0.0})
        )
        provider.register_source(
            "warning_pool", _FakePool({"utilization": 0.85, "error_rate": 0.0})
        )
        provider.register_source(
            "critical_pool", _FakePool({"utilization": 0.99, "error_rate": 0.0})
        )
        app = _make_app(provider)
        client = TestClient(app)

        resp = client.get("/connections/pools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy_pool"]["status"] == "healthy"
        assert data["warning_pool"]["status"] == "warning"
        assert data["critical_pool"]["status"] == "critical"

    def test_alerts_endpoint(self):
        """GET /connections/alerts returns alerts for high utilization and error rate."""
        provider = ConnectionMetricsProvider()
        provider.register_source(
            "bad_pool",
            _FakePool({"utilization": 0.96, "error_rate": 0.10}),
        )
        app = _make_app(provider)
        client = TestClient(app)

        resp = client.get("/connections/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # utilization critical + error rate
        severities = {a["severity"] for a in data["active_alerts"]}
        assert "critical" in severities
        assert "error" in severities


class TestPrometheusLines:
    """Tests for Prometheus text-format output."""

    def test_prometheus_lines_format(self):
        """get_prometheus_lines produces valid Prometheus gauge lines."""
        provider = ConnectionMetricsProvider()
        pool_data = {
            "main_pool": {
                "health_score": 85,
                "active_connections": 8,
                "total_connections": 10,
                "utilization": 0.8,
                "queries_per_second": 150.5,
                "avg_query_time_ms": 12.3,
                "error_rate": 0.002,
            }
        }
        lines = provider.get_prometheus_lines(pool_data)
        assert len(lines) == 7
        for line in lines:
            assert line.startswith("kailash_connection_")
            assert 'pool="main_pool"' in line


class TestUSECompleteness:
    """USE completeness (#1708 W1c): idle connections + pool-exhaustion events
    are collected by ConnectionMetricsCollector.update_pool_stats /
    track_pool_exhaustion but were previously dropped by the router's
    collect()/get_prometheus_lines() — never reaching the scrape."""

    async def test_collect_surfaces_idle_and_exhaustion_from_pool_source(self):
        """collect() MUST propagate idle_connections + pool_exhaustion_events
        from a registered pool source into the result dict."""
        provider = ConnectionMetricsProvider()
        provider.register_source(
            "main_pool",
            _FakePool(
                {
                    "idle_connections": 4,
                    "pool_exhaustion_events": 2,
                }
            ),
        )

        pool_data = await provider.collect()
        assert pool_data["main_pool"]["idle_connections"] == 4
        assert pool_data["main_pool"]["pool_exhaustion_events"] == 2

    def test_get_prometheus_lines_emits_idle_gauge_and_exhaustion_counter(self):
        """get_prometheus_lines MUST emit a typed gauge line for idle
        connections and a typed counter line for pool-exhaustion events."""
        provider = ConnectionMetricsProvider()
        pool_data = {
            "main_pool": {
                "idle_connections": 3,
                "pool_exhaustion_events": 5,
            }
        }
        lines = provider.get_prometheus_lines(pool_data)

        assert "# TYPE kailash_pool_connections_idle gauge" in lines
        assert 'kailash_pool_connections_idle{pool="main_pool"} 3' in lines
        assert "# TYPE kailash_pool_exhaustion_events_total counter" in lines
        assert 'kailash_pool_exhaustion_events_total{pool="main_pool"} 5' in lines

    def test_get_prometheus_lines_types_each_metric_exactly_once(self):
        """With multiple pools reporting idle/exhaustion values, the # TYPE
        header for each metric MUST appear exactly once (Prometheus requires
        one TYPE declaration per metric name, not one per label set)."""
        provider = ConnectionMetricsProvider()
        pool_data = {
            "pool_a": {"idle_connections": 1, "pool_exhaustion_events": 0},
            "pool_b": {"idle_connections": 2, "pool_exhaustion_events": 1},
        }
        lines = provider.get_prometheus_lines(pool_data)

        assert lines.count("# TYPE kailash_pool_connections_idle gauge") == 1
        assert lines.count("# TYPE kailash_pool_exhaustion_events_total counter") == 1
        assert 'kailash_pool_connections_idle{pool="pool_a"} 1' in lines
        assert 'kailash_pool_connections_idle{pool="pool_b"} 2' in lines
        assert 'kailash_pool_exhaustion_events_total{pool="pool_a"} 0' in lines
        assert 'kailash_pool_exhaustion_events_total{pool="pool_b"} 1' in lines

    async def test_connection_metrics_collector_registers_directly_as_pool_source(
        self,
    ):
        """ConnectionMetricsCollector.get_pool_statistics() gives the
        collector the same async contract ConnectionMetricsProvider expects,
        so a real collector instance (no fake/adapter) can be registered
        directly and its idle gauge + exhaustion counter reach the scrape."""
        from src.kailash.core.monitoring.connection_metrics import (
            ConnectionMetricsCollector,
        )

        collector = ConnectionMetricsCollector("real_pool")
        collector.update_pool_stats(active=6, idle=4, total=10)
        collector.track_pool_exhaustion()
        collector.track_pool_exhaustion()

        provider = ConnectionMetricsProvider()
        provider.register_source("real_pool", collector)

        pool_data = await provider.collect()
        assert pool_data["real_pool"]["idle_connections"] == 4
        assert pool_data["real_pool"]["pool_exhaustion_events"] == 2

        lines = provider.get_prometheus_lines(pool_data)
        assert 'kailash_pool_connections_idle{pool="real_pool"} 4' in lines
        assert 'kailash_pool_exhaustion_events_total{pool="real_pool"} 2' in lines
