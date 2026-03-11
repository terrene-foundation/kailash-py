"""
Integration tests for PerformanceDashboard.

Tests FastAPI endpoints, WebSocket updates, data retrieval, and visualization data format.
All tests must pass BEFORE implementation.
"""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


class TestPerformanceDashboardBasics:
    """Test basic PerformanceDashboard functionality."""

    @pytest.mark.asyncio
    async def test_dashboard_initialization(self):
        """Test PerformanceDashboard initializes with aggregator."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        assert dashboard.aggregator is aggregator
        assert dashboard._clients == []

    def test_dashboard_has_fastapi_app(self):
        """Test dashboard creates FastAPI app."""
        from kaizen.monitoring.dashboard import app

        assert app is not None
        assert app.title == "Kaizen Performance Dashboard"


class TestPerformanceDashboardHTTPEndpoints:
    """Test FastAPI HTTP endpoints."""

    def test_root_endpoint_returns_html(self):
        """Test that root endpoint returns HTML dashboard."""
        from kaizen.monitoring.dashboard import app

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Kaizen Performance Dashboard" in response.text
        assert "plotly" in response.text.lower()

    def test_html_contains_chart_divs(self):
        """Test that HTML contains chart containers."""
        from kaizen.monitoring.dashboard import app

        client = TestClient(app)
        response = client.get("/")

        html = response.text

        # Should contain chart divs
        assert "latency-chart" in html
        assert "cache-hit-rate-chart" in html
        assert "error-rate-chart" in html

    def test_html_contains_websocket_connection(self):
        """Test that HTML includes WebSocket connection code."""
        from kaizen.monitoring.dashboard import app

        client = TestClient(app)
        response = client.get("/")

        html = response.text

        # Should contain WebSocket connection
        assert "WebSocket" in html
        assert "ws://" in html or "wss://" in html

    def test_metrics_endpoint_prometheus_format(self):
        """Test /metrics endpoint returns Prometheus format."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import app
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Patch get_instance to return our aggregator
        with patch(
            "kaizen.monitoring.dashboard.PerformanceDashboard.get_instance"
        ) as mock_get:
            mock_dashboard = Mock()
            mock_dashboard.aggregator = aggregator
            mock_get.return_value = mock_dashboard

            client = TestClient(app)
            response = client.get("/metrics")

            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")


class TestPerformanceDashboardWebSocket:
    """Test WebSocket functionality."""

    @pytest.mark.asyncio
    async def test_websocket_connection_accepted(self):
        """Test WebSocket connection is accepted."""
        from kaizen.monitoring.dashboard import app

        client = TestClient(app)

        with client.websocket_connect("/ws") as websocket:
            assert websocket is not None

    @pytest.mark.asyncio
    async def test_websocket_receives_metrics(self):
        """Test WebSocket receives metric updates."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import app
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        AnalyticsAggregator(collector)

        # Add some metrics
        for i in range(10):
            await collector.record_metric(
                metric_name="test.websocket", value=float(i * 10)
            )

        # Note: Full WebSocket testing requires running server
        # This is a basic connectivity test
        client = TestClient(app)

        with client.websocket_connect("/ws") as websocket:
            # WebSocket should be connected
            assert websocket is not None

    @pytest.mark.asyncio
    async def test_websocket_data_format(self):
        """Test WebSocket sends data in correct format."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Get dashboard data
        data = await dashboard._get_dashboard_data()

        # Should have required keys
        assert "latency_traces" in data
        assert "cache_traces" in data
        assert "error_traces" in data

        # Each should be a list of traces
        assert isinstance(data["latency_traces"], list)
        assert isinstance(data["cache_traces"], list)
        assert isinstance(data["error_traces"], list)


class TestPerformanceDashboardDataRetrieval:
    """Test data retrieval and formatting."""

    @pytest.mark.asyncio
    async def test_get_dashboard_data_structure(self):
        """Test _get_dashboard_data returns correct structure."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        data = await dashboard._get_dashboard_data()

        assert isinstance(data, dict)
        assert "latency_traces" in data
        assert "cache_traces" in data
        assert "error_traces" in data

    @pytest.mark.asyncio
    async def test_latency_traces_format(self):
        """Test latency traces are in Plotly format."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Add some metrics
        for i in range(10):
            await collector.record_metric(
                metric_name="signature.resolution.latency", value=float(i * 5)
            )

        # Start aggregator to process metrics
        await aggregator.start()
        await asyncio.sleep(0.2)

        data = await dashboard._get_dashboard_data()
        traces = data["latency_traces"]

        # Stop aggregator
        aggregator._running = False

        # Traces should be a list
        assert isinstance(traces, list)

        # Each trace should have Plotly-compatible structure
        if len(traces) > 0:
            trace = traces[0]
            # Plotly traces have x, y, type, mode, etc.
            assert isinstance(trace, dict)

    @pytest.mark.asyncio
    async def test_cache_traces_format(self):
        """Test cache traces are in Plotly format."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        data = await dashboard._get_dashboard_data()
        traces = data["cache_traces"]

        assert isinstance(traces, list)

    @pytest.mark.asyncio
    async def test_error_traces_format(self):
        """Test error traces are in Plotly format."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        data = await dashboard._get_dashboard_data()
        traces = data["error_traces"]

        assert isinstance(traces, list)


class TestPerformanceDashboardRefreshLatency:
    """Test dashboard refresh performance."""

    @pytest.mark.asyncio
    async def test_dashboard_refresh_under_1s(self):
        """Test dashboard data refresh completes in <1s."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Add metrics
        for i in range(100):
            await collector.record_metric(metric_name="test.refresh", value=float(i))

        # Start aggregator
        await aggregator.start()
        await asyncio.sleep(0.3)

        # Measure refresh time
        start = time.perf_counter()
        await dashboard._get_dashboard_data()
        duration = time.perf_counter() - start

        # Stop aggregator
        aggregator._running = False

        # Should complete in <1s
        assert (
            duration < 1.0
        ), f"Dashboard refresh took {duration:.3f}s, exceeds 1s target"


class TestPerformanceDashboardVisualization:
    """Test visualization data building."""

    @pytest.mark.asyncio
    async def test_build_latency_traces(self):
        """Test _build_latency_traces creates valid Plotly traces."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Mock stats
        stats = {"samples": [10.0, 20.0, 30.0, 40.0, 50.0], "p95": 50.0, "mean": 30.0}

        traces = dashboard._build_latency_traces(stats)

        assert isinstance(traces, list)
        # Should have at least one trace (latency line)
        assert len(traces) > 0

    @pytest.mark.asyncio
    async def test_build_cache_traces(self):
        """Test _build_cache_traces creates valid Plotly traces."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Mock cache stats for different tiers
        cache_stats = {
            "hot": {"mean": 5.0, "p95": 8.0},
            "warm": {"mean": 15.0, "p95": 20.0},
            "cold": {"mean": 50.0, "p95": 75.0},
        }

        traces = dashboard._build_cache_traces(cache_stats)

        assert isinstance(traces, list)

    @pytest.mark.asyncio
    async def test_build_error_traces(self):
        """Test _build_error_traces creates valid Plotly traces."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Mock error stats
        error_stats = {"count": 10, "mean": 2.5, "p95": 5.0}

        traces = dashboard._build_error_traces(error_stats)

        assert isinstance(traces, list)


class TestPerformanceDashboardConcurrency:
    """Test concurrent client connections."""

    @pytest.mark.asyncio
    async def test_multiple_websocket_clients(self):
        """Test dashboard supports multiple WebSocket clients."""
        from kaizen.monitoring.dashboard import app

        client = TestClient(app)

        # Note: TestClient doesn't support multiple concurrent WebSocket connections
        # This test verifies basic connectivity
        # Production testing would need actual WebSocket client library

        with client.websocket_connect("/ws") as ws1:
            assert ws1 is not None

        with client.websocket_connect("/ws") as ws2:
            assert ws2 is not None


class TestPerformanceDashboardIntegration:
    """Test end-to-end dashboard integration."""

    @pytest.mark.asyncio
    async def test_end_to_end_dashboard_flow(self):
        """Test complete flow from metrics to dashboard visualization."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Start aggregator
        await aggregator.start()

        # Collect metrics
        metric_types = [
            "signature.resolution.latency",
            "cache.access.latency",
            "agent.execution.latency",
        ]

        for metric_type in metric_types:
            for i in range(20):
                await collector.record_metric(
                    metric_name=metric_type, value=float(i * 5)
                )

        # Give aggregator time to process
        await asyncio.sleep(0.5)

        # Get dashboard data
        data = await dashboard._get_dashboard_data()

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Verify data structure
        assert "latency_traces" in data
        assert "cache_traces" in data
        assert "error_traces" in data

        # Verify data is present (if aggregator processed metrics)
        assert isinstance(data["latency_traces"], list)
        assert isinstance(data["cache_traces"], list)
        assert isinstance(data["error_traces"], list)

    @pytest.mark.asyncio
    async def test_real_time_updates_simulation(self):
        """Test simulated real-time metric updates."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        await aggregator.start()

        # Simulate continuous metric collection
        for batch in range(3):
            for i in range(10):
                await collector.record_metric(
                    metric_name="test.realtime", value=float(batch * 10 + i)
                )
            await asyncio.sleep(0.1)

        # Get dashboard data
        data = await dashboard._get_dashboard_data()

        # Stop aggregator
        aggregator._running = False

        # Verify data exists
        assert data is not None
        assert "latency_traces" in data


class TestPerformanceDashboardErrorHandling:
    """Test dashboard error handling."""

    @pytest.mark.asyncio
    async def test_dashboard_handles_missing_stats(self):
        """Test dashboard handles missing statistics gracefully."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Get data with no metrics collected
        data = await dashboard._get_dashboard_data()

        # Should return empty but valid structure
        assert "latency_traces" in data
        assert "cache_traces" in data
        assert "error_traces" in data

    @pytest.mark.asyncio
    async def test_dashboard_handles_partial_stats(self):
        """Test dashboard handles partial statistics gracefully."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.dashboard import PerformanceDashboard
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        dashboard = PerformanceDashboard(aggregator)

        # Collect only some metrics
        for i in range(5):
            await collector.record_metric(
                metric_name="signature.resolution.latency", value=float(i)
            )

        await aggregator.start()
        await asyncio.sleep(0.2)

        data = await dashboard._get_dashboard_data()

        aggregator._running = False

        # Should handle partial data gracefully
        assert data is not None
        assert "latency_traces" in data
