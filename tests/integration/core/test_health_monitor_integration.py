"""Integration tests for health monitoring system with real Docker services.

Tier 2 tests - Integration testing with real PostgreSQL and Redis services.
All tests use REAL Docker services via docker_config.py - NO MOCKING.
"""

import asyncio
import time

import pytest
from src.kailash.core.resilience.health_monitor import (
    AlertLevel,
    DatabaseHealthCheck,
    HealthMonitor,
    HealthStatus,
    HTTPHealthCheck,
    RedisHealthCheck,
    get_health_monitor,
    quick_health_check,
)

from tests.utils.docker_config import (
    get_mock_api_url,
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.integration
class TestHealthMonitorPostgreSQLIntegration:
    """Test health monitor integration with real PostgreSQL database."""

    # NOTE: postgres_connection_string and health_monitor fixtures
    # are now consolidated in tests/conftest.py to eliminate duplication

    @pytest.mark.asyncio
    async def test_database_health_check_real_postgres(
        self, postgres_connection_string, health_monitor
    ):
        """Test database health check with real PostgreSQL."""
        # Create database health check
        db_check = DatabaseHealthCheck(
            name="postgres_test",
            database_node_or_connection_string=postgres_connection_string,
            timeout=10.0,
        )

        # Register with monitor
        health_monitor.register_check("postgres_test", db_check)

        # Perform health check
        result = await health_monitor.check_service_health("postgres_test")

        # Verify results
        assert result.service_name == "postgres_test"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy
        assert result.response_time_ms > 0
        assert "query_executed" in result.details
        assert result.details["rows_returned"] == 1

    @pytest.mark.asyncio
    async def test_database_health_check_invalid_connection(self, health_monitor):
        """Test database health check with invalid connection string."""
        # Create health check with invalid connection
        db_check = DatabaseHealthCheck(
            name="invalid_postgres",
            database_node_or_connection_string="postgresql://invalid:invalid@nonexistent:5432/invalid",
            timeout=2.0,
        )

        health_monitor.register_check("invalid_postgres", db_check)

        # Perform health check - should fail
        result = await health_monitor.check_service_health("invalid_postgres")

        assert result.service_name == "invalid_postgres"
        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_multiple_database_health_checks(
        self, postgres_connection_string, health_monitor
    ):
        """Test multiple database health checks concurrently."""
        # Create multiple database checks
        db_check1 = DatabaseHealthCheck(
            name="postgres_1",
            database_node_or_connection_string=postgres_connection_string,
        )
        db_check2 = DatabaseHealthCheck(
            name="postgres_2",
            database_node_or_connection_string=postgres_connection_string,
        )

        health_monitor.register_check("postgres_1", db_check1)
        health_monitor.register_check("postgres_2", db_check2)

        # Check all health statuses
        all_status = await health_monitor.get_all_health_status()

        assert len(all_status) == 2
        assert "postgres_1" in all_status
        assert "postgres_2" in all_status
        assert all_status["postgres_1"].is_healthy
        assert all_status["postgres_2"].is_healthy

    @pytest.mark.asyncio
    async def test_database_health_metrics_collection(
        self, postgres_connection_string, health_monitor
    ):
        """Test health metrics collection with real database."""
        db_check = DatabaseHealthCheck(
            name="postgres_metrics",
            database_node_or_connection_string=postgres_connection_string,
        )
        health_monitor.register_check("postgres_metrics", db_check)

        # Perform multiple health checks
        for i in range(5):
            await health_monitor.check_service_health("postgres_metrics")

        # Check metrics
        metrics = await health_monitor.get_metrics("postgres_metrics")

        assert metrics.total_checks == 5
        assert metrics.successful_checks == 5
        assert metrics.failed_checks == 0
        assert metrics.uptime_percentage == 100.0
        assert metrics.avg_response_time_ms > 0
        assert metrics.consecutive_failures == 0


@pytest.mark.integration
class TestHealthMonitorRedisIntegration:
    """Test health monitor integration with real Redis."""

    @pytest.fixture
    def redis_config(self):
        """Get Redis connection config from Docker config."""
        return get_redis_connection_params()

    @pytest.fixture
    def health_monitor(self):
        """Create fresh health monitor for testing."""
        return HealthMonitor(check_interval=3.0, alert_threshold=2)

    @pytest.mark.asyncio
    async def test_redis_health_check_real_redis(self, redis_config, health_monitor):
        """Test Redis health check with real Redis instance."""
        # Create Redis health check
        redis_check = RedisHealthCheck(
            name="redis_test", redis_config=redis_config, timeout=5.0
        )

        health_monitor.register_check("redis_test", redis_check)

        # Perform health check
        result = await health_monitor.check_service_health("redis_test")

        # Verify results
        assert result.service_name == "redis_test"
        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy
        assert result.response_time_ms > 0
        assert "ping_successful" in result.details
        assert result.details["ping_successful"]
        assert "redis_version" in result.details

    @pytest.mark.asyncio
    async def test_redis_health_check_invalid_config(self, health_monitor):
        """Test Redis health check with invalid configuration."""
        # Invalid Redis config
        invalid_config = {"host": "nonexistent", "port": 9999}

        redis_check = RedisHealthCheck(
            name="invalid_redis", redis_config=invalid_config, timeout=2.0
        )

        health_monitor.register_check("invalid_redis", redis_check)

        # Should fail
        result = await health_monitor.check_service_health("invalid_redis")

        assert result.service_name == "invalid_redis"
        assert result.status == HealthStatus.UNHEALTHY
        assert not result.is_healthy
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_redis_health_metrics_real_service(
        self, redis_config, health_monitor
    ):
        """Test Redis health metrics with real service."""
        redis_check = RedisHealthCheck(name="redis_metrics", redis_config=redis_config)
        health_monitor.register_check("redis_metrics", redis_check)

        # Perform multiple checks
        for i in range(3):
            await health_monitor.check_service_health("redis_metrics")
            await asyncio.sleep(0.1)  # Small delay between checks

        # Verify metrics
        metrics = await health_monitor.get_metrics("redis_metrics")

        assert metrics.total_checks == 3
        assert metrics.successful_checks == 3
        assert metrics.uptime_percentage == 100.0


@pytest.mark.integration
class TestHealthMonitorMixedServicesIntegration:
    """Test health monitor with multiple real services."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string."""
        return get_postgres_connection_string("kailash_test")

    @pytest.fixture
    def redis_config(self):
        """Get Redis connection config."""
        return get_redis_connection_params()

    @pytest.fixture
    def health_monitor(self):
        """Create health monitor."""
        return HealthMonitor(check_interval=10.0, alert_threshold=2)

    @pytest.mark.asyncio
    async def test_mixed_services_health_monitoring(
        self, postgres_connection_string, redis_config, health_monitor
    ):
        """Test health monitoring with multiple real services."""
        # Register multiple service checks
        db_check = DatabaseHealthCheck(
            name="postgres_mixed",
            database_node_or_connection_string=postgres_connection_string,
        )
        redis_check = RedisHealthCheck(name="redis_mixed", redis_config=redis_config)

        health_monitor.register_check("postgres_mixed", db_check)
        health_monitor.register_check("redis_mixed", redis_check)

        # Check overall health
        overall_health = await health_monitor.get_overall_health()
        assert overall_health == HealthStatus.HEALTHY

        # Check individual services
        all_status = await health_monitor.get_all_health_status()

        assert len(all_status) == 2
        assert all_status["postgres_mixed"].is_healthy
        assert all_status["redis_mixed"].is_healthy

    @pytest.mark.asyncio
    async def test_health_monitoring_with_partial_failures(
        self, postgres_connection_string, health_monitor
    ):
        """Test health monitoring with some services failing."""
        # Register working and failing services
        working_db = DatabaseHealthCheck(
            name="working_db",
            database_node_or_connection_string=postgres_connection_string,
        )
        failing_db = DatabaseHealthCheck(
            name="failing_db",
            database_node_or_connection_string="postgresql://invalid:invalid@nonexistent:5432/invalid",
            timeout=1.0,
        )

        health_monitor.register_check("working_db", working_db)
        health_monitor.register_check("failing_db", failing_db)

        # Check all services
        all_status = await health_monitor.get_all_health_status()

        assert len(all_status) == 2
        assert all_status["working_db"].is_healthy
        assert not all_status["failing_db"].is_healthy

        # Overall health should be degraded or unhealthy
        overall_health = await health_monitor.get_overall_health()
        assert overall_health in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]

    @pytest.mark.asyncio
    async def test_alert_generation_real_failures(
        self, postgres_connection_string, health_monitor
    ):
        """Test alert generation with real service failures."""
        # Create callback to capture alerts
        captured_alerts = []

        def alert_callback(alert):
            captured_alerts.append(alert)

        health_monitor.register_alert_callback(alert_callback)

        # Register failing service
        failing_check = DatabaseHealthCheck(
            name="failing_service",
            database_node_or_connection_string="postgresql://invalid:invalid@nonexistent:5432/invalid",
            timeout=1.0,
        )
        health_monitor.register_check("failing_service", failing_check)

        # Trigger enough failures to generate alerts
        for i in range(3):  # Above alert threshold
            await health_monitor.check_service_health("failing_service")

        # Check alerts were generated
        alerts = await health_monitor.get_alerts(resolved=False)
        assert len(alerts) >= 1

        # Check callback was called
        assert len(captured_alerts) >= 1

    @pytest.mark.asyncio
    async def test_performance_under_load_real_services(
        self, postgres_connection_string, redis_config, health_monitor
    ):
        """Test health monitor performance under load with real services."""
        # Register multiple services
        services = []
        for i in range(5):
            db_check = DatabaseHealthCheck(f"db_{i}", postgres_connection_string)
            redis_check = RedisHealthCheck(f"redis_{i}", redis_config)
            health_monitor.register_check(f"db_{i}", db_check)
            health_monitor.register_check(f"redis_{i}", redis_check)
            services.extend([f"db_{i}", f"redis_{i}"])

        # Perform concurrent health checks
        start_time = time.time()
        all_status = await health_monitor.get_all_health_status()
        execution_time = time.time() - start_time

        # Verify all services were checked
        assert len(all_status) == 10
        assert all(status.is_healthy for status in all_status.values())

        # Performance should be reasonable
        assert execution_time < 10.0  # Should complete within 10 seconds


@pytest.mark.integration
class TestGlobalHealthMonitorIntegration:
    """Test global health monitor with real services."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string."""
        return get_postgres_connection_string("kailash_test")

    @pytest.mark.asyncio
    async def test_global_health_monitor_real_service(self, postgres_connection_string):
        """Test global health monitor with real database service."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        # Get global monitor and register service
        monitor = get_health_monitor()
        db_check = DatabaseHealthCheck("global_postgres", postgres_connection_string)
        monitor.register_check("global_postgres", db_check)

        # Use quick health check function
        is_healthy = await quick_health_check("global_postgres")
        assert is_healthy

        # Verify through direct check
        result = await monitor.get_health_status("global_postgres")
        assert result.is_healthy

    @pytest.mark.asyncio
    async def test_global_health_monitor_service_isolation(
        self, postgres_connection_string
    ):
        """Test that global health monitor properly isolates service checks."""
        # Clear any existing global monitor
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        monitor = get_health_monitor()

        # Register working and failing services
        working_check = DatabaseHealthCheck(
            "global_working", postgres_connection_string
        )
        failing_check = DatabaseHealthCheck(
            "global_failing",
            "postgresql://invalid:invalid@nonexistent:5432/invalid",
            timeout=1.0,
        )

        monitor.register_check("global_working", working_check)
        monitor.register_check("global_failing", failing_check)

        # Quick checks should return different results
        working_healthy = await quick_health_check("global_working")
        failing_healthy = await quick_health_check("global_failing")

        assert working_healthy
        assert not failing_healthy
