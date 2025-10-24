"""E2E tests for health monitoring in enterprise scenarios.

Tier 3 tests - End-to-end testing with complete real infrastructure.
Tests enterprise health monitoring scenarios with PostgreSQL, Redis, and HTTP services.
NO MOCKING - uses real Docker services for enterprise validation.
"""

import asyncio
import time

import pytest
from src.kailash.core.resilience.bulkhead import (
    execute_with_bulkhead,
    get_bulkhead_manager,
)
from src.kailash.core.resilience.health_monitor import (
    AlertLevel,
    DatabaseHealthCheck,
    HealthMonitor,
    HealthStatus,
    HTTPHealthCheck,
    RedisHealthCheck,
    get_health_monitor,
)

from tests.utils.docker_config import (
    get_postgres_connection_string,
    get_redis_connection_params,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestEnterpriseHealthMonitoringE2E:
    """Test enterprise health monitoring scenarios end-to-end."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.fixture
    def redis_config(self):
        """Get Redis connection config from Docker config."""
        return get_redis_connection_params()

    @pytest.fixture
    def enterprise_health_monitor(self):
        """Create enterprise-configured health monitor."""
        return HealthMonitor(
            check_interval=5.0,  # 5 second intervals for enterprise monitoring
            alert_threshold=2,  # Alert after 2 consecutive failures
        )

    @pytest.mark.asyncio
    async def test_enterprise_infrastructure_health_monitoring_e2e(
        self, postgres_connection_string, redis_config, enterprise_health_monitor
    ):
        """Test complete enterprise infrastructure health monitoring."""

        # Register enterprise infrastructure services

        # Critical database services
        primary_db_check = DatabaseHealthCheck(
            name="primary_database",
            connection_string=postgres_connection_string,
            timeout=5.0,
            critical=True,
        )

        secondary_db_check = DatabaseHealthCheck(
            name="secondary_database",
            connection_string=postgres_connection_string,
            timeout=10.0,
            critical=False,
        )

        # Cache services
        primary_cache_check = RedisHealthCheck(
            name="primary_cache", redis_config=redis_config, timeout=3.0, critical=True
        )

        secondary_cache_check = RedisHealthCheck(
            name="secondary_cache",
            redis_config=redis_config,
            timeout=5.0,
            critical=False,
        )

        # Register all services
        enterprise_health_monitor.register_check("primary_database", primary_db_check)
        enterprise_health_monitor.register_check(
            "secondary_database", secondary_db_check
        )
        enterprise_health_monitor.register_check("primary_cache", primary_cache_check)
        enterprise_health_monitor.register_check(
            "secondary_cache", secondary_cache_check
        )

        # Enterprise health assessment
        start_time = time.time()

        # Check all infrastructure health
        all_health = await enterprise_health_monitor.get_all_health_status()
        overall_health = await enterprise_health_monitor.get_overall_health()

        health_check_time = time.time() - start_time

        # Enterprise validation requirements
        assert len(all_health) == 4
        assert overall_health == HealthStatus.HEALTHY

        # All critical services must be healthy
        assert all_health["primary_database"].is_healthy
        assert all_health["primary_cache"].is_healthy

        # Non-critical services should also be healthy in this test
        assert all_health["secondary_database"].is_healthy
        assert all_health["secondary_cache"].is_healthy

        # Enterprise SLA: Health checks must complete within 15 seconds
        assert health_check_time < 15.0

        # Verify enterprise metrics
        all_metrics = await enterprise_health_monitor.get_all_metrics()
        for service_name, metrics in all_metrics.items():
            assert metrics.total_checks >= 1
            assert metrics.uptime_percentage >= 99.0  # 99% uptime requirement

    @pytest.mark.asyncio
    async def test_enterprise_health_monitoring_with_bulkhead_integration_e2e(
        self, postgres_connection_string, redis_config
    ):
        """Test health monitoring integration with bulkhead pattern for enterprise resilience."""

        # Create enterprise health monitor
        health_monitor = HealthMonitor(check_interval=3.0, alert_threshold=2)

        # Register infrastructure health checks
        db_check = DatabaseHealthCheck(
            "enterprise_db", postgres_connection_string, critical=True
        )
        cache_check = RedisHealthCheck("enterprise_cache", redis_config, critical=True)

        health_monitor.register_check("enterprise_db", db_check)
        health_monitor.register_check("enterprise_cache", cache_check)

        # Get bulkhead manager for service isolation
        bulkhead_manager = get_bulkhead_manager()

        # Enterprise workflow: Health-aware operations with bulkhead isolation
        async def health_aware_database_operation():
            # Check health before proceeding
            db_healthy = await health_monitor.get_health_status("enterprise_db")
            if not db_healthy.is_healthy:
                raise Exception("Database unhealthy - operation aborted")

            # Execute through bulkhead for isolation
            from src.kailash.nodes.data.sql import SQLDatabaseNode

            sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)

            def db_operation():
                return sql_node.execute(query="SELECT 'enterprise_operation' as status")

            return await execute_with_bulkhead("database", db_operation)

        async def health_aware_cache_operation():
            # Check cache health
            cache_healthy = await health_monitor.get_health_status("enterprise_cache")
            if not cache_healthy.is_healthy:
                raise Exception("Cache unhealthy - using fallback")

            # Simulate cache operation through bulkhead
            def cache_operation():
                import redis

                client = redis.Redis(**redis_config)
                client.set("enterprise_key", "enterprise_value", ex=60)
                return {"cached": True, "key": "enterprise_key"}

            return await execute_with_bulkhead("background", cache_operation)

        # Execute enterprise operations with health monitoring and bulkhead isolation
        enterprise_operations = [
            health_aware_database_operation(),
            health_aware_cache_operation(),
            health_aware_database_operation(),  # Multiple DB operations
            health_aware_cache_operation(),  # Multiple cache operations
        ]

        start_time = time.time()
        results = await asyncio.gather(*enterprise_operations)
        execution_time = time.time() - start_time

        # Enterprise validation
        assert len(results) == 4

        # Verify database operations succeeded
        db_results = [results[0], results[2]]
        for result in db_results:
            assert "data" in result
            assert result["data"][0]["status"] == "enterprise_operation"

        # Verify cache operations succeeded
        cache_results = [results[1], results[3]]
        for result in cache_results:
            assert result["cached"]

        # Enterprise performance requirement
        assert execution_time < 10.0  # All operations within 10 seconds

        # Verify bulkhead partitions handled the load
        bulkhead_status = bulkhead_manager.get_all_status()
        assert "database" in bulkhead_status
        assert "background" in bulkhead_status

        # Database partition should show activity
        db_partition_metrics = bulkhead_status["database"]["metrics"]
        assert db_partition_metrics["total_operations"] >= 2

        # Background partition should show cache activity
        bg_partition_metrics = bulkhead_status["background"]["metrics"]
        assert bg_partition_metrics["total_operations"] >= 2

    @pytest.mark.asyncio
    async def test_enterprise_disaster_recovery_health_monitoring_e2e(
        self, postgres_connection_string, redis_config
    ):
        """Test enterprise disaster recovery scenarios with health monitoring."""

        # Enterprise disaster recovery health monitor
        dr_health_monitor = HealthMonitor(
            check_interval=2.0,  # Faster checks during DR
            alert_threshold=1,  # Immediate alerting during DR
        )

        # Alert collection for disaster recovery
        dr_alerts = []

        def dr_alert_handler(alert):
            dr_alerts.append(alert)
            print(f"DR Alert: {alert.level.value} - {alert.message}")

        dr_health_monitor.register_alert_callback(dr_alert_handler)

        # Register production services
        production_db = DatabaseHealthCheck(
            "production_db", postgres_connection_string, timeout=3.0, critical=True
        )

        production_cache = RedisHealthCheck(
            "production_cache", redis_config, timeout=2.0, critical=True
        )

        # Register failing "disaster" services
        disaster_db = DatabaseHealthCheck(
            "disaster_db",
            "postgresql://invalid:invalid@failed-server:5432/disaster",
            timeout=1.0,
            critical=True,
        )

        dr_health_monitor.register_check("production_db", production_db)
        dr_health_monitor.register_check("production_cache", production_cache)
        dr_health_monitor.register_check("disaster_db", disaster_db)

        # Simulate disaster recovery scenario

        # Phase 1: Normal operations - all services healthy
        initial_health = await dr_health_monitor.get_overall_health()

        # Phase 2: Disaster simulation - check failing service
        disaster_result = await dr_health_monitor.check_service_health("disaster_db")
        assert not disaster_result.is_healthy

        # Phase 3: Verify healthy services remain operational during disaster
        production_db_result = await dr_health_monitor.check_service_health(
            "production_db"
        )
        production_cache_result = await dr_health_monitor.check_service_health(
            "production_cache"
        )

        assert production_db_result.is_healthy
        assert production_cache_result.is_healthy

        # Phase 4: Enterprise failover validation
        # Check that critical services (production) can handle load during disaster
        failover_operations = []

        for i in range(5):  # Simulate increased load during failover

            async def failover_db_operation():
                from src.kailash.nodes.data.sql import SQLDatabaseNode

                sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
                return sql_node.execute(
                    query=f"SELECT 'failover_operation_{i}' as status, NOW() as timestamp"
                )

            failover_operations.append(failover_db_operation())

        # Execute failover operations
        start_time = time.time()
        failover_results = await asyncio.gather(*failover_operations)
        failover_time = time.time() - start_time

        # Disaster recovery validation
        assert len(failover_results) == 5
        assert all("data" in result for result in failover_results)

        # Failover should complete quickly (< 5 seconds)
        assert failover_time < 5.0

        # Verify DR alerts were generated for failed service
        dr_unresolved_alerts = await dr_health_monitor.get_alerts(resolved=False)
        disaster_alerts = [
            alert
            for alert in dr_unresolved_alerts
            if alert.service_name == "disaster_db"
        ]
        assert len(disaster_alerts) >= 1

        # Verify alert callback was triggered
        assert len(dr_alerts) >= 1

    @pytest.mark.asyncio
    async def test_enterprise_health_monitoring_performance_e2e(
        self, postgres_connection_string, redis_config
    ):
        """Test health monitoring performance under enterprise load."""

        # High-frequency enterprise health monitor
        perf_monitor = HealthMonitor(
            check_interval=1.0, alert_threshold=3  # High frequency monitoring
        )

        # Register multiple enterprise services
        services = []
        for i in range(10):  # 10 database connections
            db_check = DatabaseHealthCheck(
                f"enterprise_db_{i}", postgres_connection_string, timeout=5.0
            )
            perf_monitor.register_check(f"enterprise_db_{i}", db_check)
            services.append(f"enterprise_db_{i}")

        for i in range(5):  # 5 cache connections
            cache_check = RedisHealthCheck(
                f"enterprise_cache_{i}", redis_config, timeout=3.0
            )
            perf_monitor.register_check(f"enterprise_cache_{i}", cache_check)
            services.append(f"enterprise_cache_{i}")

        # Enterprise load test: Multiple concurrent health checks
        concurrent_checks = []

        # Simulate enterprise monitoring load
        for round_num in range(3):  # 3 rounds of checks
            for service in services:
                concurrent_checks.append(perf_monitor.check_service_health(service))

        # Execute enterprise load test
        start_time = time.time()
        check_results = await asyncio.gather(*concurrent_checks)
        total_execution_time = time.time() - start_time

        # Enterprise performance validation
        total_checks = len(check_results)
        successful_checks = len([r for r in check_results if r.is_healthy])

        assert total_checks == 45  # 15 services × 3 rounds
        assert successful_checks >= 40  # At least 90% success rate

        # Enterprise SLA: All health checks within 30 seconds
        assert total_execution_time < 30.0

        # Verify metrics collection under load
        all_metrics = await perf_monitor.get_all_metrics()

        for service_name, metrics in all_metrics.items():
            assert metrics.total_checks >= 3  # Each service checked 3 times
            assert metrics.avg_response_time_ms > 0

        # Overall health should remain stable under load
        overall_health = await perf_monitor.get_overall_health()
        assert overall_health in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

    @pytest.mark.asyncio
    async def test_global_enterprise_health_monitoring_e2e(
        self, postgres_connection_string, redis_config
    ):
        """Test global enterprise health monitoring deployment."""

        # Clear global monitor for clean test
        import src.kailash.core.resilience.health_monitor as monitor_module

        monitor_module._health_monitor = None

        # Configure global enterprise health monitor
        global_monitor = get_health_monitor()

        # Register enterprise infrastructure
        enterprise_services = {
            "customer_database": DatabaseHealthCheck(
                "customer_database", postgres_connection_string, critical=True
            ),
            "session_cache": RedisHealthCheck(
                "session_cache", redis_config, critical=True
            ),
            "analytics_database": DatabaseHealthCheck(
                "analytics_database", postgres_connection_string, critical=False
            ),
            "feature_cache": RedisHealthCheck(
                "feature_cache", redis_config, critical=False
            ),
        }

        for service_name, health_check in enterprise_services.items():
            global_monitor.register_check(service_name, health_check)

        # Enterprise application simulation using global health monitoring
        async def enterprise_customer_operation():
            """Simulate customer-facing operation with health checks."""
            # Check critical services health
            customer_db_health = await global_monitor.get_health_status(
                "customer_database"
            )
            session_cache_health = await global_monitor.get_health_status(
                "session_cache"
            )

            if not customer_db_health.is_healthy:
                raise Exception("Customer database unavailable")
            if not session_cache_health.is_healthy:
                print("Warning: Session cache degraded, using fallback")

            # Simulate customer operation
            return {
                "customer_operation": "success",
                "db_response_time": customer_db_health.response_time_ms,
                "cache_available": session_cache_health.is_healthy,
            }

        async def enterprise_analytics_operation():
            """Simulate analytics operation with health checks."""
            analytics_db_health = await global_monitor.get_health_status(
                "analytics_database"
            )

            if not analytics_db_health.is_healthy:
                return {
                    "analytics_operation": "deferred",
                    "reason": "database_unavailable",
                }

            return {
                "analytics_operation": "success",
                "db_response_time": analytics_db_health.response_time_ms,
            }

        # Execute enterprise operations
        enterprise_operations = [
            enterprise_customer_operation(),
            enterprise_analytics_operation(),
            enterprise_customer_operation(),  # Multiple customer ops
        ]

        start_time = time.time()
        operation_results = await asyncio.gather(*enterprise_operations)
        operations_time = time.time() - start_time

        # Enterprise deployment validation
        assert len(operation_results) == 3

        # Customer operations should succeed (critical services healthy)
        customer_results = [operation_results[0], operation_results[2]]
        for result in customer_results:
            assert result["customer_operation"] == "success"
            assert result["db_response_time"] > 0

        # Analytics should succeed (non-critical but healthy)
        analytics_result = operation_results[1]
        assert analytics_result["analytics_operation"] == "success"

        # Enterprise performance: Operations complete quickly
        assert operations_time < 5.0

        # Verify global monitoring tracked all services
        final_overall_health = await global_monitor.get_overall_health()
        assert final_overall_health == HealthStatus.HEALTHY

        # Enterprise reporting: All services should have metrics
        final_metrics = await global_monitor.get_all_metrics()
        assert len(final_metrics) == 4

        for service_name in enterprise_services.keys():
            assert service_name in final_metrics
            assert final_metrics[service_name].total_checks >= 1
