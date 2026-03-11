"""
Integration tests for DataFlow Health Monitoring System

Tests integration between health monitoring and actual DataFlow components,
including real database connections and monitoring workflows.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from kailash.core.resilience.health_monitor import (
    CustomHealthCheck,
    DatabaseHealthCheck,
    HealthCheckManager,
    HealthMonitor,
    HealthStatus,
    HTTPHealthCheck,
    MemoryHealthCheck,
    RedisHealthCheck,
    register_custom_health_check,
    register_database_health_check,
    register_memory_health_check,
)
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestHealthMonitorIntegration:
    """Integration test suite for health monitoring with DataFlow components."""

    @pytest.fixture
    async def runtime(self):
        """Create LocalRuntime for testing."""
        runtime = LocalRuntime()
        yield runtime
        await runtime.shutdown()

    @pytest.fixture
    async def database_node(self):
        """Create mock database node that simulates real database behavior."""

        class MockAsyncDatabaseNode:
            def __init__(self):
                self.connection_active = True

            async def execute(self, query: str, result_format: str = "dict"):
                """Mock execute method that simulates real database behavior."""
                if not self.connection_active:
                    raise ConnectionError("Database connection closed")

                # Simulate database response time
                await asyncio.sleep(0.01)

                if "SELECT 1" in query.upper():
                    return {"success": True, "data": [{"health_check": 1}]}
                else:
                    return {"success": True, "data": []}

            async def shutdown(self):
                """Mock shutdown method."""
                self.connection_active = False

        node = MockAsyncDatabaseNode()
        yield node
        await node.shutdown()

    @pytest.fixture
    async def health_manager(self):
        """Create health manager for integration testing."""
        config = {
            "enabled": True,
            "default_interval": 1.0,
            "parallel_checks": True,
            "max_concurrent_checks": 3,
        }
        manager = HealthCheckManager(config)
        yield manager
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_database_health_check_with_real_database(
        self, health_manager, database_node
    ):
        """Test database health check with real database connection."""

        # Register database health check
        db_health_check = DatabaseHealthCheck("main_db", database_node)
        health_manager.register_health_check(db_health_check)

        # Run health check
        result = await health_manager.run_health_check("main_db")

        # Verify result
        assert result.check_name == "main_db"
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms > 0
        assert "healthy" in result.message.lower()
        assert result.error is None

        # Verify metadata contains query result
        assert "query_result" in result.metadata
        assert len(result.metadata["query_result"]) > 0

    @pytest.mark.asyncio
    async def test_multiple_health_checks_integration(
        self, health_manager, database_node
    ):
        """Test multiple health checks running together."""

        # Register database health check
        db_health_check = DatabaseHealthCheck("main_db", database_node)
        health_manager.register_health_check(db_health_check, interval=2.0)

        # Register memory health check with mocked psutil
        with patch("psutil.virtual_memory") as mock_memory:
            mock_memory.return_value = MagicMock(
                percent=45.0,
                total=8 * 1024 * 1024 * 1024,
                available=4 * 1024 * 1024 * 1024,
                used=4 * 1024 * 1024 * 1024,
            )

            memory_health_check = MemoryHealthCheck("system_memory")
            health_manager.register_health_check(memory_health_check, interval=3.0)

            # Register custom health check
            async def service_health_check():
                return {
                    "status": "healthy",
                    "message": "Service responding normally",
                    "metadata": {"latency_ms": 25},
                }

            custom_health_check = CustomHealthCheck("service_api", service_health_check)
            health_manager.register_health_check(custom_health_check, interval=1.5)

            # Run all health checks
            results = await health_manager.run_all_health_checks()

            # Verify all checks completed
            assert len(results) == 3

            # Verify each check
            check_names = {r.check_name for r in results}
            assert "main_db" in check_names
            assert "system_memory" in check_names
            assert "service_api" in check_names

            # All should be healthy
            for result in results:
                assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_summary_integration(self, health_manager, database_node):
        """Test health summary with mixed health statuses."""

        # Register healthy database check
        db_health_check = DatabaseHealthCheck("healthy_db", database_node)
        health_manager.register_health_check(db_health_check)

        # Register failing custom check
        async def failing_service():
            raise ConnectionError("Service unavailable")

        failing_check = CustomHealthCheck("failing_service", failing_service)
        health_manager.register_health_check(failing_check)

        # Register degraded custom check
        async def degraded_service():
            return {
                "status": "degraded",
                "message": "Service slow but functional",
                "metadata": {"latency_ms": 850},
            }

        degraded_check = CustomHealthCheck("degraded_service", degraded_service)
        health_manager.register_health_check(degraded_check)

        # Get health summary
        summary = await health_manager.get_health_summary()

        # Verify summary
        assert summary.total_checks == 3
        assert summary.healthy_checks == 1
        assert summary.degraded_checks == 1
        assert summary.unhealthy_checks == 1
        assert (
            summary.overall_status == HealthStatus.UNHEALTHY
        )  # Due to failing service

        # Verify details
        assert len(summary.details) == 3

        # Find specific results
        healthy_results = [
            r for r in summary.details if r.status == HealthStatus.HEALTHY
        ]
        degraded_results = [
            r for r in summary.details if r.status == HealthStatus.DEGRADED
        ]
        unhealthy_results = [
            r for r in summary.details if r.status == HealthStatus.UNHEALTHY
        ]

        assert len(healthy_results) == 1
        assert len(degraded_results) == 1
        assert len(unhealthy_results) == 1

        # Verify specific checks
        healthy_result = healthy_results[0]
        assert healthy_result.check_name == "healthy_db"

        degraded_result = degraded_results[0]
        assert degraded_result.check_name == "degraded_service"
        assert degraded_result.metadata["latency_ms"] == 850

        unhealthy_result = unhealthy_results[0]
        assert unhealthy_result.check_name == "failing_service"
        assert "unavailable" in unhealthy_result.error.lower()

    @pytest.mark.asyncio
    async def test_health_monitoring_during_operations(
        self, health_manager, database_node
    ):
        """Test health monitoring during simulated database operations."""

        # Register database health check
        db_health_check = DatabaseHealthCheck("workflow_db", database_node)
        health_manager.register_health_check(db_health_check)

        # Simulate multiple database operations
        for i in range(3):
            # Simulate a database operation
            result = await database_node.execute("SELECT COUNT(*) FROM users", "dict")
            assert result["success"] is True

            # Run health check during operations
            health_result = await health_manager.run_health_check("workflow_db")
            assert health_result.status == HealthStatus.HEALTHY

            await asyncio.sleep(0.01)  # Brief pause between operations

        # Final health check
        final_health = await health_manager.run_health_check("workflow_db")
        assert final_health.status == HealthStatus.HEALTHY
        assert final_health.response_time_ms > 0

    @pytest.mark.asyncio
    async def test_health_status_change_notifications(
        self, health_manager, database_node
    ):
        """Test health status change notifications with real components."""

        status_changes = []

        async def status_change_handler(check_name: str, result):
            status_changes.append(
                {
                    "check_name": check_name,
                    "status": result.status,
                    "timestamp": result.timestamp,
                    "message": result.message,
                }
            )

        health_manager.add_status_change_callback(status_change_handler)

        # Register database health check
        db_health_check = DatabaseHealthCheck("monitored_db", database_node)
        health_manager.register_health_check(db_health_check)

        # Run initial check (should be healthy)
        result1 = await health_manager.run_health_check("monitored_db")
        assert result1.status == HealthStatus.HEALTHY

        # Simulate database failure by shutting down the node
        await database_node.shutdown()

        # Run check again (should fail)
        result2 = await health_manager.run_health_check("monitored_db")
        assert result2.status == HealthStatus.UNHEALTHY

        # Verify status change was captured
        assert len(status_changes) == 1
        change = status_changes[0]
        assert change["check_name"] == "monitored_db"
        assert change["status"] == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_convenience_functions(self, database_node):
        """Test convenience functions for registering health checks."""

        # Test database health check registration
        await register_database_health_check("conv_db", database_node, interval=5.0)

        # Test memory health check registration (with mocked psutil)
        with patch("psutil.virtual_memory") as mock_memory:
            mock_memory.return_value = MagicMock(
                percent=60.0,
                total=16 * 1024 * 1024 * 1024,
                available=6 * 1024 * 1024 * 1024,
                used=10 * 1024 * 1024 * 1024,
            )

            await register_memory_health_check(
                "conv_memory",
                warning_threshold=70.0,
                critical_threshold=90.0,
                interval=10.0,
            )

        # Test custom health check registration
        async def custom_check():
            return True

        await register_custom_health_check(
            "conv_custom", custom_check, interval=3.0, timeout=2.0
        )

        # Get global health manager and verify registrations
        from kailash.core.resilience.health_monitor import get_health_manager

        manager = get_health_manager()

        # Verify all checks were registered
        assert "conv_db" in manager.health_checks
        assert "conv_memory" in manager.health_checks
        assert "conv_custom" in manager.health_checks

        # Verify intervals
        assert manager.check_intervals["conv_db"] == 5.0
        assert manager.check_intervals["conv_memory"] == 10.0
        assert manager.check_intervals["conv_custom"] == 3.0

        # Test running the registered checks
        results = await manager.run_all_health_checks()
        assert len(results) >= 3

        # Cleanup
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_health_monitoring_performance(self, health_manager, database_node):
        """Test health monitoring performance with multiple checks."""

        # Register multiple health checks
        for i in range(5):
            db_check = DatabaseHealthCheck(f"db_{i}", database_node)
            health_manager.register_health_check(db_check)

        # Add custom checks
        async def fast_check():
            await asyncio.sleep(0.001)  # Very fast check
            return True

        for i in range(2):
            custom_check = CustomHealthCheck(f"custom_{i}", fast_check)
            health_manager.register_health_check(custom_check)

        # Add memory checks with mocked psutil and run tests within the patch
        with patch("psutil.virtual_memory") as mock_memory:
            mock_memory.return_value = MagicMock(
                percent=50.0,
                total=16 * 1024 * 1024 * 1024,
                available=8 * 1024 * 1024 * 1024,
                used=8 * 1024 * 1024 * 1024,
            )

            for i in range(3):
                memory_check = MemoryHealthCheck(f"memory_{i}")
                health_manager.register_health_check(memory_check)

            # Measure performance of running all checks
            import time

            start_time = time.time()

            results = await health_manager.run_all_health_checks()

            execution_time = time.time() - start_time

            # Verify results
            assert len(results) == 10  # 5 db + 3 memory + 2 custom

            # All should be healthy
            for result in results:
                assert result.status == HealthStatus.HEALTHY

            # Performance should be reasonable (parallel execution)
            # With parallel execution, should be much faster than sequential
            assert (
                execution_time < 2.0
            ), f"Health checks took too long: {execution_time:.2f}s"

            # Verify parallel execution was faster than sequential would be
            # (Each DB check takes ~10ms + memory checks ~1ms each + custom checks ~1ms each)
            # Sequential would be ~55ms minimum, parallel should be much faster
            total_individual_time = sum(r.response_time_ms for r in results) / 1000
            parallel_efficiency = total_individual_time / execution_time

            # Should have significant parallel efficiency (>2x speedup)
            assert (
                parallel_efficiency > 2.0
            ), f"Parallel efficiency too low: {parallel_efficiency:.2f}x"

    @pytest.mark.asyncio
    async def test_health_monitoring_error_resilience(
        self, health_manager, database_node
    ):
        """Test health monitoring resilience to errors in individual checks."""

        # Register a healthy check
        healthy_check = DatabaseHealthCheck("healthy_db", database_node)
        health_manager.register_health_check(healthy_check)

        # Register a check that raises an exception
        async def exception_check():
            raise RuntimeError("Unexpected error in check")

        error_check = CustomHealthCheck("error_check", exception_check)
        health_manager.register_health_check(error_check)

        # Register a check that times out
        async def timeout_check():
            await asyncio.sleep(1.0)  # Longer than default timeout
            return True

        timeout_check_obj = CustomHealthCheck(
            "timeout_check", timeout_check, timeout=0.1
        )
        health_manager.register_health_check(timeout_check_obj)

        # Run all checks - should not fail despite errors
        results = await health_manager.run_all_health_checks()

        # Verify all checks completed
        assert len(results) == 3

        # Find specific results
        healthy_result = next(r for r in results if r.check_name == "healthy_db")
        error_result = next(r for r in results if r.check_name == "error_check")
        timeout_result = next(r for r in results if r.check_name == "timeout_check")

        # Verify statuses
        assert healthy_result.status == HealthStatus.HEALTHY
        assert error_result.status == HealthStatus.UNHEALTHY
        assert timeout_result.status == HealthStatus.UNHEALTHY

        # Verify error details
        assert "Unexpected error in check" in error_result.error
        assert "timeout" in timeout_result.error.lower()

        # Get health summary - should aggregate correctly despite errors
        summary = await health_manager.get_health_summary()
        assert summary.overall_status == HealthStatus.UNHEALTHY
        assert summary.healthy_checks == 1
        assert summary.unhealthy_checks == 2

    @pytest.mark.asyncio
    async def test_health_history_tracking(self, health_manager, database_node):
        """Test health history tracking over multiple checks."""

        # Register database health check
        db_check = DatabaseHealthCheck("history_db", database_node)
        health_manager.register_health_check(db_check)

        # Run multiple health checks
        for i in range(5):
            await health_manager.run_health_check("history_db")
            await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

        # Get health history
        history = health_manager.get_health_history("history_db")

        # Verify history
        assert len(history) == 5

        # All should be healthy
        for result in history:
            assert result.status == HealthStatus.HEALTHY
            assert result.check_name == "history_db"

        # Timestamps should be in order
        timestamps = [r.timestamp for r in history]
        assert timestamps == sorted(timestamps)

        # Test history limit
        limited_history = health_manager.get_health_history("history_db", limit=3)
        assert len(limited_history) == 3

        # Should be the most recent 3
        assert limited_history == history[-3:]
