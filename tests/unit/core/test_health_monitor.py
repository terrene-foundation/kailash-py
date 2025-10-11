"""Unit tests for health monitoring system.

Tier 1 tests - Fast isolated testing with mocks, no external dependencies.
All tests must complete in <1 second with no sleep/delays.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.kailash.core.resilience.health_monitor import (
    AlertLevel,
    DatabaseHealthCheck,
    HealthAlert,
    HealthCheck,
    HealthCheckResult,
    HealthMetrics,
    HealthMonitor,
    HealthStatus,
    HTTPHealthCheck,
    RedisHealthCheck,
    get_health_monitor,
    quick_health_check,
)


class TestHealthStatus:
    """Test health status enum."""

    def test_health_status_values(self):
        """Test health status enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestAlertLevel:
    """Test alert level enum."""

    def test_alert_level_values(self):
        """Test alert level enum values."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.CRITICAL.value == "critical"
        assert AlertLevel.FATAL.value == "fatal"


class TestHealthCheckResult:
    """Test health check result data class."""

    def test_healthy_result_creation(self):
        """Test creating healthy result."""
        result = HealthCheckResult(
            check_id="test-123",
            service_name="test-service",
            status=HealthStatus.HEALTHY,
            response_time_ms=50.0,
        )

        assert result.check_id == "test-123"
        assert result.service_name == "test-service"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms == 50.0
        assert result.is_healthy
        assert isinstance(result.timestamp, datetime)

    def test_unhealthy_result_creation(self):
        """Test creating unhealthy result."""
        result = HealthCheckResult(
            check_id="test-456",
            service_name="failing-service",
            status=HealthStatus.UNHEALTHY,
            response_time_ms=1000.0,
            error_message="Connection failed",
        )

        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy
        assert result.error_message == "Connection failed"

    def test_degraded_result_is_healthy(self):
        """Test that degraded status is considered healthy."""
        result = HealthCheckResult(
            check_id="test-789",
            service_name="degraded-service",
            status=HealthStatus.DEGRADED,
            response_time_ms=200.0,
        )

        assert result.status == HealthStatus.DEGRADED
        assert result.is_healthy  # Degraded is still considered healthy


class TestHealthMetrics:
    """Test health metrics data class."""

    def test_default_metrics(self):
        """Test default metrics initialization."""
        metrics = HealthMetrics()

        assert metrics.total_checks == 0
        assert metrics.successful_checks == 0
        assert metrics.failed_checks == 0
        assert metrics.avg_response_time_ms == 0.0
        assert metrics.max_response_time_ms == 0.0
        assert metrics.uptime_percentage == 100.0
        assert metrics.consecutive_failures == 0
        assert metrics.last_successful_check is None
        assert metrics.last_failed_check is None
        assert isinstance(metrics.created_at, datetime)


class TestHealthAlert:
    """Test health alert data class."""

    def test_alert_creation(self):
        """Test creating health alert."""
        alert = HealthAlert(
            service_name="test-service",
            level=AlertLevel.CRITICAL,
            message="Service is down",
        )

        assert alert.service_name == "test-service"
        assert alert.level == AlertLevel.CRITICAL
        assert alert.message == "Service is down"
        assert not alert.resolved
        assert alert.resolved_at is None
        assert isinstance(alert.timestamp, datetime)
        assert len(alert.alert_id) > 0


class MockHealthCheck(HealthCheck):
    """Mock health check for testing."""

    def __init__(
        self,
        name: str,
        result_status: HealthStatus = HealthStatus.HEALTHY,
        response_time: float = 10.0,
        should_raise: bool = False,
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self.result_status = result_status
        self.response_time = response_time
        self.should_raise = should_raise

    async def check_health(self) -> HealthCheckResult:
        """Mock health check implementation."""
        if self.should_raise:
            raise Exception("Mock health check failure")

        return HealthCheckResult(
            check_id="mock-check",
            service_name=self.name,
            status=self.result_status,
            response_time_ms=self.response_time,
        )


class TestHealthCheck:
    """Test health check base class."""

    def test_health_check_initialization(self):
        """Test health check initialization."""
        check = MockHealthCheck("test-service")

        assert check.name == "test-service"
        assert check.timeout == 5.0  # Default timeout
        assert check.critical  # Default critical

    def test_health_check_custom_params(self):
        """Test health check with custom parameters."""
        check = MockHealthCheck("test-service", timeout=10.0, critical=False)

        assert check.timeout == 10.0
        assert not check.critical

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        check = MockHealthCheck("test-service", HealthStatus.HEALTHY, 25.0)
        result = await check.check_health()

        assert result.service_name == "test-service"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms == 25.0
        assert result.is_healthy

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check with exception."""
        check = MockHealthCheck("test-service", should_raise=True)

        with pytest.raises(Exception, match="Mock health check failure"):
            await check.check_health()


class TestDatabaseHealthCheck:
    """Test database health check implementation."""

    def test_database_health_check_initialization(self):
        """Test database health check initialization."""
        check = DatabaseHealthCheck("postgres", "sqlite:///:memory:")

        assert check.name == "postgres"
        assert check.connection_string == "sqlite:///:memory:"
        assert check.timeout == 5.0
        assert check.critical

    @pytest.mark.asyncio
    async def test_database_health_check_success(self):
        """Test successful database health check."""
        check = DatabaseHealthCheck("postgres", "sqlite:///:memory:")

        # Mock SQLDatabaseNode
        mock_sql_node = Mock()
        mock_sql_node.execute.return_value = {
            "data": [{"health_check": 1}],
            "execution_time": 0.05,
        }

        with patch(
            "src.kailash.nodes.data.sql.SQLDatabaseNode", return_value=mock_sql_node
        ):
            with patch(
                "asyncio.to_thread", return_value=mock_sql_node.execute.return_value
            ):
                result = await check.check_health()

        assert result.service_name == "postgres"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy
        assert "query_executed" in result.details
        assert result.details["rows_returned"] == 1

    @pytest.mark.asyncio
    async def test_database_health_check_timeout(self):
        """Test database health check timeout."""
        check = DatabaseHealthCheck("postgres", "sqlite:///:memory:", timeout=0.1)

        with patch("asyncio.to_thread", side_effect=asyncio.TimeoutError):
            result = await check.check_health()

        assert result.service_name == "postgres"
        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy
        assert "timed out" in result.error_message

    @pytest.mark.asyncio
    async def test_database_health_check_error(self):
        """Test database health check with error."""
        check = DatabaseHealthCheck("postgres", "sqlite:///:memory:")

        with patch(
            "src.kailash.nodes.data.sql.SQLDatabaseNode",
            side_effect=Exception("Connection failed"),
        ):
            result = await check.check_health()

        assert result.service_name == "postgres"
        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy
        assert result.error_message == "Connection failed"


class TestRedisHealthCheck:
    """Test Redis health check implementation."""

    def test_redis_health_check_initialization(self):
        """Test Redis health check initialization."""
        config = {"host": "localhost", "port": 6379}
        check = RedisHealthCheck("redis", config)

        assert check.name == "redis"
        assert check.redis_config == config

    @pytest.mark.asyncio
    async def test_redis_health_check_success(self):
        """Test successful Redis health check."""
        config = {"host": "localhost", "port": 6379}
        check = RedisHealthCheck("redis", config)

        # Mock Redis client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {
            "connected_clients": 5,
            "used_memory": 1024,
            "redis_version": "6.2.0",
        }

        with patch("redis.Redis", return_value=mock_client):
            with patch("asyncio.to_thread") as mock_to_thread:
                # Configure to_thread to return appropriate values based on function
                def to_thread_side_effect(func, *args):
                    if func == mock_client.ping:
                        return True
                    elif func == mock_client.info:
                        return mock_client.info.return_value

                mock_to_thread.side_effect = to_thread_side_effect
                result = await check.check_health()

        assert result.service_name == "redis"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy
        assert result.details["ping_successful"]
        assert result.details["connected_clients"] == 5

    @pytest.mark.asyncio
    async def test_redis_health_check_timeout(self):
        """Test Redis health check timeout."""
        config = {"host": "localhost", "port": 6379}
        check = RedisHealthCheck("redis", config, timeout=0.1)

        with patch("asyncio.to_thread", side_effect=asyncio.TimeoutError):
            result = await check.check_health()

        assert result.service_name == "redis"
        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.error_message


class TestHTTPHealthCheck:
    """Test HTTP health check implementation."""

    def test_http_health_check_initialization(self):
        """Test HTTP health check initialization."""
        check = HTTPHealthCheck("api", "http://localhost:8080/health")

        assert check.name == "api"
        assert check.url == "http://localhost:8080/health"
        assert check.expected_status == 200

    @pytest.mark.asyncio
    async def test_http_health_check_success(self):
        """Test successful HTTP health check."""
        check = HTTPHealthCheck("api", "http://localhost:8080/health")

        # Mock httpx response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"OK"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            result = await check.check_health()

        assert result.service_name == "api"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy
        assert result.details["status_code"] == 200

    @pytest.mark.asyncio
    async def test_http_health_check_degraded(self):
        """Test HTTP health check with unexpected but OK status."""
        check = HTTPHealthCheck(
            "api", "http://localhost:8080/health", expected_status=200
        )

        # Mock response with different but acceptable status
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.content = b"Created"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            result = await check.check_health()

        assert result.service_name == "api"
        assert result.status == HealthStatus.DEGRADED
        assert result.is_healthy

    @pytest.mark.asyncio
    async def test_http_health_check_unhealthy(self):
        """Test HTTP health check with error status."""
        check = HTTPHealthCheck("api", "http://localhost:8080/health")

        # Mock response with error status
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.content = b"Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            result = await check.check_health()

        assert result.service_name == "api"
        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy


class TestHealthMonitor:
    """Test health monitor functionality."""

    def test_health_monitor_initialization(self):
        """Test health monitor initialization."""
        monitor = HealthMonitor(check_interval=60.0, alert_threshold=5)

        assert monitor.check_interval == 60.0
        assert monitor.alert_threshold == 5
        assert len(monitor.health_checks) == 0
        assert len(monitor.metrics) == 0
        assert len(monitor.alerts) == 0

    def test_register_health_check(self):
        """Test registering health check."""
        monitor = HealthMonitor()
        check = MockHealthCheck("test-service")

        monitor.register_check("test-service", check)

        assert "test-service" in monitor.health_checks
        assert "test-service" in monitor.metrics
        assert monitor.health_checks["test-service"] == check

    def test_register_alert_callback(self):
        """Test registering alert callback."""
        monitor = HealthMonitor()
        callback = Mock()

        monitor.register_alert_callback(callback)

        assert callback in monitor.alert_callbacks

    @pytest.mark.asyncio
    async def test_check_service_health_success(self):
        """Test checking service health successfully."""
        monitor = HealthMonitor()
        check = MockHealthCheck("test-service", HealthStatus.HEALTHY, 30.0)
        monitor.register_check("test-service", check)

        result = await monitor.check_service_health("test-service")

        assert result.service_name == "test-service"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms == 30.0

    @pytest.mark.asyncio
    async def test_check_service_health_not_registered(self):
        """Test checking health for unregistered service."""
        monitor = HealthMonitor()

        with pytest.raises(ValueError, match="No health check registered"):
            await monitor.check_service_health("unknown-service")

    @pytest.mark.asyncio
    async def test_get_all_health_status(self):
        """Test getting all health statuses."""
        monitor = HealthMonitor()

        check1 = MockHealthCheck("service1", HealthStatus.HEALTHY)
        check2 = MockHealthCheck("service2", HealthStatus.DEGRADED)

        monitor.register_check("service1", check1)
        monitor.register_check("service2", check2)

        results = await monitor.get_all_health_status()

        assert len(results) == 2
        assert "service1" in results
        assert "service2" in results
        assert results["service1"].status == HealthStatus.HEALTHY
        assert results["service2"].status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_get_overall_health_all_healthy(self):
        """Test overall health when all services are healthy."""
        monitor = HealthMonitor()

        check1 = MockHealthCheck("service1", HealthStatus.HEALTHY)
        check2 = MockHealthCheck("service2", HealthStatus.HEALTHY)

        monitor.register_check("service1", check1)
        monitor.register_check("service2", check2)

        overall = await monitor.get_overall_health()

        assert overall == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_overall_health_with_degraded(self):
        """Test overall health with degraded service."""
        monitor = HealthMonitor()

        check1 = MockHealthCheck("service1", HealthStatus.HEALTHY)
        check2 = MockHealthCheck("service2", HealthStatus.DEGRADED)

        monitor.register_check("service1", check1)
        monitor.register_check("service2", check2)

        overall = await monitor.get_overall_health()

        assert overall == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_get_overall_health_critical_unhealthy(self):
        """Test overall health with critical service unhealthy."""
        monitor = HealthMonitor()

        check1 = MockHealthCheck("service1", HealthStatus.HEALTHY)
        check2 = MockHealthCheck("critical-service", HealthStatus.UNHEALTHY)
        check2.critical = True

        monitor.register_check("service1", check1)
        monitor.register_check("critical-service", check2)

        overall = await monitor.get_overall_health()

        assert overall == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_metrics_update_success(self):
        """Test metrics update for successful check."""
        monitor = HealthMonitor()
        check = MockHealthCheck("test-service", HealthStatus.HEALTHY, 50.0)
        monitor.register_check("test-service", check)

        # Perform multiple checks
        await monitor.check_service_health("test-service")
        await monitor.check_service_health("test-service")

        metrics = await monitor.get_metrics("test-service")

        assert metrics.total_checks == 2
        assert metrics.successful_checks == 2
        assert metrics.failed_checks == 0
        assert metrics.consecutive_failures == 0
        assert metrics.uptime_percentage == 100.0
        assert metrics.avg_response_time_ms == 50.0

    @pytest.mark.asyncio
    async def test_metrics_update_failure(self):
        """Test metrics update for failed check."""
        monitor = HealthMonitor()
        check = MockHealthCheck("test-service", HealthStatus.UNHEALTHY, 100.0)
        monitor.register_check("test-service", check)

        await monitor.check_service_health("test-service")

        metrics = await monitor.get_metrics("test-service")

        assert metrics.total_checks == 1
        assert metrics.successful_checks == 0
        assert metrics.failed_checks == 1
        assert metrics.consecutive_failures == 1
        assert metrics.uptime_percentage == 0.0

    @pytest.mark.asyncio
    async def test_alert_generation(self):
        """Test alert generation for consecutive failures."""
        monitor = HealthMonitor(alert_threshold=2)
        check = MockHealthCheck("test-service", HealthStatus.UNHEALTHY)
        monitor.register_check("test-service", check)

        # Trigger failures to reach threshold
        await monitor.check_service_health("test-service")
        await monitor.check_service_health("test-service")

        alerts = await monitor.get_alerts()

        assert len(alerts) >= 1
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        assert len(critical_alerts) >= 1

    @pytest.mark.asyncio
    async def test_alert_callback(self):
        """Test alert callback execution."""
        monitor = HealthMonitor(alert_threshold=1)
        callback = Mock()
        monitor.register_alert_callback(callback)

        check = MockHealthCheck("test-service", HealthStatus.UNHEALTHY)
        monitor.register_check("test-service", check)

        await monitor.check_service_health("test-service")

        # Callback should have been called
        callback.assert_called()

    @pytest.mark.asyncio
    async def test_get_alerts_filtered(self):
        """Test getting filtered alerts."""
        monitor = HealthMonitor()

        # Add mock alerts
        resolved_alert = HealthAlert(
            service_name="service1",
            level=AlertLevel.WARNING,
            message="Resolved issue",
            resolved=True,
        )
        unresolved_alert = HealthAlert(
            service_name="service2",
            level=AlertLevel.CRITICAL,
            message="Active issue",
            resolved=False,
        )

        monitor.alerts.extend([resolved_alert, unresolved_alert])

        resolved_alerts = await monitor.get_alerts(resolved=True)
        unresolved_alerts = await monitor.get_alerts(resolved=False)
        all_alerts = await monitor.get_alerts()

        assert len(resolved_alerts) == 1
        assert len(unresolved_alerts) == 1
        assert len(all_alerts) == 2


class TestGlobalHealthMonitor:
    """Test global health monitor functions."""

    def test_get_global_health_monitor(self):
        """Test getting global health monitor."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        monitor1 = get_health_monitor()
        monitor2 = get_health_monitor()

        assert monitor1 is monitor2
        assert isinstance(monitor1, HealthMonitor)

    @pytest.mark.asyncio
    async def test_quick_health_check_success(self):
        """Test quick health check function."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        monitor = get_health_monitor()
        check = MockHealthCheck("test-service", HealthStatus.HEALTHY)
        monitor.register_check("test-service", check)

        is_healthy = await quick_health_check("test-service")

        assert is_healthy

    @pytest.mark.asyncio
    async def test_quick_health_check_failure(self):
        """Test quick health check with failure."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        monitor = get_health_monitor()
        check = MockHealthCheck("test-service", HealthStatus.UNHEALTHY)
        monitor.register_check("test-service", check)

        is_healthy = await quick_health_check("test-service")

        assert not is_healthy

    @pytest.mark.asyncio
    async def test_quick_health_check_unregistered(self):
        """Test quick health check for unregistered service."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        is_healthy = await quick_health_check("unknown-service")

        assert not is_healthy
