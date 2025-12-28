"""Unit tests for connection dashboard node."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from aiohttp import web
from kailash.nodes.monitoring.connection_dashboard import (
    Alert,
    AlertRule,
    ConnectionDashboardNode,
    MetricsCache,
)


class TestMetricsCache:
    """Test metrics cache functionality."""

    @pytest.fixture
    def cache(self):
        """Create test cache."""
        return MetricsCache(retention_hours=1)

    def test_add_and_get_recent(self, cache):
        """Test adding and retrieving metrics."""
        # Add metrics
        cache.add("cpu_usage", {"value": 50.0})
        cache.add("cpu_usage", {"value": 60.0})
        cache.add("memory_usage", {"value": 1024})

        # Get recent metrics
        cpu_metrics = cache.get_recent("cpu_usage", minutes=5)
        assert len(cpu_metrics) == 2
        assert cpu_metrics[0]["value"] == 50.0
        assert cpu_metrics[1]["value"] == 60.0

        memory_metrics = cache.get_recent("memory_usage", minutes=5)
        assert len(memory_metrics) == 1
        assert memory_metrics[0]["value"] == 1024

    def test_time_based_filtering(self, cache):
        """Test time-based metric filtering."""
        import time

        # Add old metric
        old_metric = {"value": 10.0}
        cache.add("test_metric", old_metric)
        old_metric["timestamp"] = time.time() - 120  # 2 minutes ago

        # Add recent metric
        cache.add("test_metric", {"value": 20.0})

        # Get only last minute
        recent = cache.get_recent("test_metric", minutes=1)
        assert len(recent) == 1
        assert recent[0]["value"] == 20.0

    def test_cleanup(self, cache):
        """Test automatic cleanup of old data."""
        import time

        # Add metrics
        cache.add("test_metric", {"value": 1.0})

        # Manually set old timestamp
        cache._data["test_metric"][0]["timestamp"] = time.time() - 7200  # 2 hours ago

        # Force cleanup
        cache._cleanup()

        # Old data should be removed
        assert "test_metric" not in cache._data


class TestAlertSystem:
    """Test alert functionality."""

    def test_alert_rule_creation(self):
        """Test alert rule configuration."""
        rule = AlertRule(
            id="test_rule",
            name="High CPU",
            condition="cpu > 0.9",
            threshold=0.9,
            duration_seconds=60,
            severity="warning",
        )

        assert rule.id == "test_rule"
        assert rule.threshold == 0.9
        assert not rule.is_in_cooldown()

    def test_alert_cooldown(self):
        """Test alert cooldown period."""
        import time

        rule = AlertRule(
            id="test",
            name="Test",
            condition="test > 1",
            threshold=1.0,
            cooldown_seconds=5,
        )

        # Not in cooldown initially
        assert not rule.is_in_cooldown()

        # Trigger alert
        rule.last_triggered = time.time()
        assert rule.is_in_cooldown()

        # After cooldown period
        rule.last_triggered = time.time() - 10
        assert not rule.is_in_cooldown()

    def test_alert_creation(self):
        """Test alert instance creation."""
        alert = Alert(
            rule_id="high_cpu",
            triggered_at=1234567890.0,
            severity="warning",
            message="CPU usage above 90%",
            metric_value=0.92,
        )

        assert alert.rule_id == "high_cpu"
        assert not alert.resolved
        assert alert.duration() > 0


class TestConnectionDashboardNode:
    """Test dashboard node functionality."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime."""
        runtime = Mock()
        runtime.resource_registry = Mock()
        runtime.resource_registry.list_resources.return_value = {}
        return runtime

    @pytest.fixture
    def dashboard(self, mock_runtime):
        """Create test dashboard node."""
        dashboard = ConnectionDashboardNode(
            name="test_dashboard",
            port=8888,
            host="localhost",
            update_interval=10.0,  # Longer interval for tests
            enable_alerts=True,
        )

        dashboard.runtime = mock_runtime

        return dashboard

    def test_get_parameters(self):
        """Test parameter definitions."""
        dashboard = ConnectionDashboardNode(name="test")
        params = dashboard.get_parameters()

        assert "port" in params
        assert "host" in params
        assert "update_interval" in params
        assert "retention_hours" in params
        assert "enable_alerts" in params
        assert "action" in params

    @pytest.mark.asyncio
    async def test_start_stop(self, dashboard):
        """Test starting and stopping dashboard."""
        # Start dashboard
        result = await dashboard.execute({"action": "start"})
        assert result["status"] == "started"
        assert result["url"] == "http://localhost:8888"
        assert dashboard.app is not None

        # Get status
        status = dashboard.get_status()
        assert status["running"]
        assert status["url"] == "http://localhost:8888"

        # Stop dashboard
        result = await dashboard.execute({"action": "stop"})
        assert result["status"] == "stopped"
        assert dashboard.app is None

    @pytest.mark.asyncio
    async def test_default_alerts(self, dashboard):
        """Test default alert rules are created."""
        assert len(dashboard._alert_rules) == 3
        assert "high_utilization" in dashboard._alert_rules
        assert "high_error_rate" in dashboard._alert_rules
        assert "pool_exhausted" in dashboard._alert_rules

    @pytest.mark.asyncio
    async def test_get_pool_info(self, dashboard):
        """Test pool information retrieval."""
        # Mock pool with statistics
        mock_pool = Mock()
        mock_pool.get_pool_statistics = AsyncMock(
            return_value={
                "health_score": 95,
                "active_connections": 5,
                "total_connections": 10,
                "utilization": 0.5,
                "queries_per_second": 100.0,
                "avg_query_time_ms": 15.0,
                "error_rate": 0.01,
            }
        )

        dashboard.runtime.resource_registry.list_resources.return_value = {
            "test_pool": mock_pool
        }

        pools = await dashboard._get_pool_info()

        assert "test_pool" in pools
        assert pools["test_pool"]["health_score"] == 95
        assert pools["test_pool"]["active_connections"] == 5

    @pytest.mark.asyncio
    async def test_check_alerts(self, dashboard):
        """Test alert checking logic."""
        # Create test data
        pools = {
            "test_pool": {"utilization": 0.95, "error_rate": 0.01}
        }  # Above threshold

        # Check alerts
        await dashboard._check_alerts(pools)

        # Should have triggered high utilization alert
        active_alerts = [a for a in dashboard._active_alerts.values() if not a.resolved]
        assert len(active_alerts) > 0
        assert any("High Pool Utilization" in a.message for a in active_alerts)

    @pytest.mark.asyncio
    async def test_metrics_collection(self, dashboard):
        """Test metrics collection and caching."""
        # Add test pool data
        pools = {"pool1": {"utilization": 0.7, "error_rate": 0.02}}

        # Mock get_pool_info
        dashboard._get_pool_info = AsyncMock(return_value=pools)

        # Collect metrics
        metrics = await dashboard._collect_metrics()

        assert "timestamp" in metrics
        assert "pools" in metrics
        assert metrics["pools"] == pools

    @pytest.mark.asyncio
    async def test_websocket_broadcast(self, dashboard):
        """Test WebSocket broadcasting."""
        # Create mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        dashboard._websockets.add(mock_ws)

        # Broadcast data
        test_data = {"type": "test", "value": 123}
        await dashboard._broadcast(test_data)

        # Check WebSocket received data
        mock_ws.send_json.assert_called_once_with(test_data)

    @pytest.mark.asyncio
    async def test_handle_index(self, dashboard):
        """Test index page generation."""
        # Mock dashboard start to avoid port conflicts
        dashboard.app = Mock()
        dashboard.runner = Mock()
        dashboard.site = Mock()
        dashboard._update_task = None

        # Create mock request
        request = Mock()

        # Get index page
        response = await dashboard._handle_index(request)

        assert response.status == 200
        assert response.content_type == "text/html"

        # Check HTML content
        html = response.text
        assert "<title>Connection Pool Dashboard</title>" in html
        assert "WebSocket" in html
        assert "updateChart" in html  # Chart function exists

    @pytest.mark.asyncio
    async def test_handle_metrics_api(self, dashboard):
        """Test metrics API endpoint."""
        # Mock collect_metrics
        dashboard._collect_metrics = AsyncMock(
            return_value={
                "timestamp": 1234567890,
                "pools": {"test": {"utilization": 0.5}},
            }
        )

        # Mock dashboard start to avoid port conflicts
        dashboard.app = Mock()
        dashboard.runner = Mock()
        dashboard.site = Mock()
        dashboard._update_task = None

        # Create mock request
        request = Mock()

        # Get metrics
        response = await dashboard._handle_metrics(request)

        assert response.status == 200
        data = json.loads(response.text)
        assert data["timestamp"] == 1234567890
        assert "pools" in data

    @pytest.mark.asyncio
    async def test_handle_alerts_api(self, dashboard):
        """Test alerts API endpoint."""
        # Add test alert
        dashboard._active_alerts["test"] = Alert(
            rule_id="high_cpu",
            triggered_at=1234567890,
            severity="warning",
            message="High CPU usage",
            metric_value=0.95,
        )

        # Mock dashboard start to avoid port conflicts
        dashboard.app = Mock()
        dashboard.runner = Mock()
        dashboard.site = Mock()
        dashboard._update_task = None

        # Create mock request
        request = Mock()

        # Get alerts
        response = await dashboard._handle_alerts(request)

        assert response.status == 200
        data = json.loads(response.text)
        assert len(data["active"]) == 1
        assert data["active"][0]["severity"] == "warning"
        assert len(data["rules"]) == 3  # Default rules

    @pytest.mark.asyncio
    async def test_update_pool_metrics(self, dashboard):
        """Test pool metrics updates."""
        # Mock pool info
        pools = {
            "test_pool": {
                "name": "test_pool",
                "utilization": 0.75,
                "error_rate": 0.02,
                "active_connections": 15,
                "max_connections": 20,
            }
        }

        # Get pool info should work
        dashboard.runtime.resource_registry.list_resources.return_value = {
            "ConnectionPool": {"test_pool": Mock()}
        }
        result = await dashboard._get_pool_info()
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_dashboard_integration():
    """Test dashboard integration with real web server."""
    dashboard = ConnectionDashboardNode(
        name="integration_test",
        port=0,  # Random port
        update_interval=60.0,  # Don't update during test
    )

    try:
        # Start dashboard
        await dashboard.start()

        # Verify it's running
        assert dashboard.app is not None
        assert dashboard.site is not None

        # Could add HTTP client tests here

    finally:
        # Cleanup
        await dashboard.stop()
