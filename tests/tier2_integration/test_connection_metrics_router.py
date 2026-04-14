"""Tests for the connection metrics endpoint registration.

Validates the /connections/metrics, /connections/pools, and
/connections/alerts endpoints as well as Prometheus line generation.

Post-migration note (#445 Wave 1): the module now exposes
``register_connection_metrics`` (registers handlers directly on the host
app/router via ``add_api_route``) instead of the old
``create_connection_metrics_router`` factory. These tests construct a
minimal FastAPI app *in test scope* (exempt from the framework-first
hook) and verify the handler behavior end-to-end.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.kailash.servers.connection_metrics_router import (
    ConnectionMetricsProvider,
    register_connection_metrics,
)


class _FakePool:
    """Fake pool source for testing."""

    def __init__(self, stats: dict):
        self._stats = stats

    async def get_pool_statistics(self):
        return self._stats


def _make_app(provider: ConnectionMetricsProvider | None = None) -> FastAPI:
    """Create a minimal FastAPI app with the connection metrics handlers."""
    app = FastAPI()
    register_connection_metrics(app, provider, prefix="/connections")
    return app


class TestConnectionMetricsRouter:
    """Endpoint tests for the connection metrics handlers."""

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

    def test_prometheus_lines_empty(self):
        """Empty pool data produces no lines."""
        provider = ConnectionMetricsProvider()
        assert provider.get_prometheus_lines({}) == []

    def test_prometheus_lines_skips_error_field(self):
        """String 'error' field does not produce a Prometheus line."""
        provider = ConnectionMetricsProvider()
        pool_data = {
            "bad_pool": {
                "health_score": 0,
                "error": "connection refused",
            }
        }
        lines = provider.get_prometheus_lines(pool_data)
        # Only numeric fields produce lines; string "error" is skipped
        assert all('error="' not in line for line in lines)
        assert any("health_score" in line for line in lines)
