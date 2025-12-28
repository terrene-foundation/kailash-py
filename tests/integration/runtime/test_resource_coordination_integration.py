"""Integration tests for runtime resource coordination.

This module tests the resource coordination components that enable
connection pool sharing, resource monitoring, and enterprise management
features in the enhanced LocalRuntime.

Test Coverage:
- ResourceCoordinator for cross-runtime coordination
- ConnectionPoolManager for pool sharing and lifecycle
- ResourceMonitor for limits and health tracking
- Enterprise monitoring hooks and metrics
"""

import asyncio
import os
import threading
import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.runtime.monitoring.runtime_monitor import ResourceMonitor, RuntimeMonitor
from kailash.runtime.resource_manager import ConnectionPoolManager, ResourceCoordinator
from kailash.sdk_exceptions import ResourceLimitExceededError

# PostgreSQL test configuration
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "database": os.getenv("POSTGRES_DB", "kailash_test"),
    "user": os.getenv("POSTGRES_USER", "test_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "test_password"),
}


class TestResourceCoordinator:
    """Test ResourceCoordinator for cross-runtime coordination."""

    def test_resource_coordinator_initialization(self):
        """Test ResourceCoordinator initialization."""
        coordinator = ResourceCoordinator(
            runtime_id="test-runtime-1", enable_coordination=True
        )

        assert coordinator.runtime_id == "test-runtime-1"
        assert coordinator.enable_coordination is True
        assert hasattr(coordinator, "_shared_resources")
        assert hasattr(coordinator, "_coordination_lock")

    def test_register_runtime_instance(self):
        """Test registering runtime instances for coordination."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        # Register runtime
        coordinator.register_runtime("runtime-1", {"max_connections": 50})

        assert "runtime-1" in coordinator._registered_runtimes
        assert (
            coordinator._registered_runtimes["runtime-1"]["config"]["max_connections"]
            == 50
        )

    def test_shared_resource_allocation(self):
        """Test shared resource allocation between runtimes."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        # Allocate shared resource
        resource_id = coordinator.allocate_shared_resource(
            resource_type="connection_pool",
            resource_config={
                "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                "database_type": "postgresql",
                "pool_size": 10,
            },
        )

        assert resource_id is not None
        assert resource_id in coordinator._shared_resources

        # Should be able to get the same resource
        same_resource = coordinator.get_shared_resource(resource_id)
        assert same_resource is not None

    def test_resource_reference_counting(self):
        """Test resource reference counting for lifecycle management."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        resource_id = coordinator.allocate_shared_resource(
            "connection_pool",
            {
                "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                "database_type": "postgresql",
            },
        )

        # Initial reference count
        assert coordinator.get_resource_reference_count(resource_id) == 1

        # Add reference
        coordinator.add_resource_reference(resource_id)
        assert coordinator.get_resource_reference_count(resource_id) == 2

        # Remove reference
        coordinator.remove_resource_reference(resource_id)
        assert coordinator.get_resource_reference_count(resource_id) == 1

    def test_resource_cleanup_on_zero_references(self):
        """Test that resources are cleaned up when references reach zero."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        resource_id = coordinator.allocate_shared_resource(
            "connection_pool",
            {
                "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                "database_type": "postgresql",
            },
        )

        # Remove last reference
        coordinator.remove_resource_reference(resource_id)

        # Resource should be cleaned up
        assert resource_id not in coordinator._shared_resources

    @pytest.mark.asyncio
    async def test_async_resource_coordination(self):
        """Test async resource coordination operations."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        # Should handle async operations
        await coordinator.coordinate_async_operation("test_operation")

        assert hasattr(coordinator, "_async_operations")

    def test_thread_safety(self):
        """Test thread safety of resource coordination."""
        coordinator = ResourceCoordinator(runtime_id="runtime-1")

        # Simulate concurrent access
        results = []

        def allocate_resource(thread_id):
            resource_id = coordinator.allocate_shared_resource(
                "test_resource", {"thread_id": thread_id}
            )
            results.append(resource_id)

        threads = [
            threading.Thread(target=allocate_resource, args=(i,)) for i in range(5)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All allocations should succeed and be unique
        assert len(results) == 5
        assert len(set(results)) == 5  # All unique


class TestConnectionPoolManager:
    """Test ConnectionPoolManager for pool sharing and lifecycle."""

    def test_pool_manager_initialization(self):
        """Test ConnectionPoolManager initialization."""
        manager = ConnectionPoolManager(
            max_pools=10, default_pool_size=5, pool_timeout=30
        )

        assert manager.max_pools == 10
        assert manager.default_pool_size == 5
        assert manager.pool_timeout == 30
        assert hasattr(manager, "_pools")
        assert hasattr(manager, "_pool_configs")

    @pytest.mark.asyncio
    async def test_create_connection_pool(self):
        """Test creating connection pools."""
        manager = ConnectionPoolManager()

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 5,
            "pool_timeout": 30,
        }

        pool = await manager.create_pool("test_pool", pool_config)

        assert pool is not None
        assert "test_pool" in manager._pools
        assert manager._pool_configs["test_pool"] == pool_config

        # Cleanup
        await manager.close_pool("test_pool")

    @pytest.mark.asyncio
    async def test_pool_reuse_same_config(self):
        """Test that pools with same config are reused."""
        manager = ConnectionPoolManager()

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 5,
        }

        pool1 = await manager.create_pool("test_pool", pool_config)
        pool2 = await manager.get_or_create_pool("test_pool", pool_config)

        # Should be the same pool instance
        assert pool1 is pool2

        # Cleanup
        await manager.close_pool("test_pool")

    @pytest.mark.asyncio
    async def test_pool_sharing_across_runtimes(self):
        """Test pool sharing across multiple runtime instances."""
        manager = ConnectionPoolManager(enable_sharing=True)

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 10,
        }

        # Create pool from runtime 1
        pool1 = await manager.create_shared_pool(
            "shared_pool", pool_config, "runtime-1"
        )

        # Get same pool from runtime 2
        pool2 = await manager.get_shared_pool("shared_pool", "runtime-2")

        assert pool1 is pool2
        assert manager.get_pool_runtime_count("shared_pool") == 2

    @pytest.mark.asyncio
    async def test_pool_health_monitoring(self):
        """Test connection pool health monitoring."""
        manager = ConnectionPoolManager(enable_health_monitoring=True)

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 5,
        }

        pool = await manager.create_pool("test_pool", pool_config)

        # Should have health metrics
        health = manager.get_pool_health("test_pool")

        assert "status" in health
        assert "active_connections" in health
        assert "total_connections" in health
        assert "last_check" in health

        # Cleanup
        await manager.close_pool("test_pool")

    @pytest.mark.asyncio
    async def test_pool_lifecycle_management(self):
        """Test pool lifecycle management."""
        manager = ConnectionPoolManager()

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 3,
        }

        pool = await manager.create_pool("lifecycle_pool", pool_config)

        # Pool should be active
        assert manager.is_pool_active("lifecycle_pool")

        # Close pool
        await manager.close_pool("lifecycle_pool")

        # Pool should be closed
        assert not manager.is_pool_active("lifecycle_pool")
        assert "lifecycle_pool" not in manager._pools

    @pytest.mark.asyncio
    async def test_pool_limit_enforcement(self):
        """Test that pool limits are enforced."""
        manager = ConnectionPoolManager(max_pools=2)

        try:
            # Create max number of pools - all use the same database
            await manager.create_pool(
                "pool1",
                {
                    "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                    "database_type": "postgresql",
                },
            )
            await manager.create_pool(
                "pool2",
                {
                    "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                    "database_type": "postgresql",
                },
            )

            # Should fail to create another pool
            with pytest.raises(ResourceLimitExceededError):
                await manager.create_pool(
                    "pool3",
                    {
                        "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                        "database_type": "postgresql",
                    },
                )
        finally:
            # Cleanup
            await manager.close_pool("pool1")
            await manager.close_pool("pool2")

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)  # Increase timeout since we need to wait for TTL
    async def test_cleanup_unused_pools(self):
        """Test cleanup of unused pools."""
        manager = ConnectionPoolManager(pool_ttl=1)  # 1 second TTL

        # Create pool using the existing database
        pool = await manager.create_pool(
            "temp_pool",
            {
                "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
                "database_type": "postgresql",
            },
        )

        # Wait for TTL
        await asyncio.sleep(1.1)

        # Run cleanup
        cleaned_count = await manager.cleanup_unused_pools()

        assert cleaned_count >= 1
        assert "temp_pool" not in manager._pools


class TestResourceMonitor:
    """Test ResourceMonitor for limits and health tracking."""

    def test_resource_monitor_initialization(self):
        """Test ResourceMonitor initialization."""
        limits = {"max_memory_mb": 1024, "max_connections": 50, "max_cpu_percent": 80}

        monitor = ResourceMonitor(resource_limits=limits, monitoring_interval=1.0)

        assert monitor.resource_limits == limits
        assert monitor.monitoring_interval == 1.0
        assert hasattr(monitor, "_current_usage")
        assert hasattr(monitor, "_is_monitoring")

    def test_memory_usage_tracking(self):
        """Test memory usage tracking."""
        monitor = ResourceMonitor({"max_memory_mb": 1024})

        # Should track current memory usage
        usage = monitor.get_current_memory_usage()
        assert usage >= 0
        assert isinstance(usage, (int, float))

    def test_connection_count_tracking(self):
        """Test connection count tracking."""
        monitor = ResourceMonitor({"max_connections": 50})

        # Add connection
        monitor.add_connection("conn1")
        assert monitor.get_connection_count() == 1

        # Remove connection
        monitor.remove_connection("conn1")
        assert monitor.get_connection_count() == 0

    def test_resource_limit_checking(self):
        """Test resource limit checking."""
        monitor = ResourceMonitor(
            {"max_memory_mb": 100, "max_connections": 2}  # Low limit for testing
        )

        # Should check if within limits
        within_limits = monitor.check_resource_limits()
        assert isinstance(within_limits, bool)

        # Add connections beyond limit
        monitor.add_connection("conn1")
        monitor.add_connection("conn2")
        monitor.add_connection("conn3")  # Beyond limit

        # Should detect limit exceeded
        violations = monitor.get_limit_violations()
        assert "connections" in violations

    @pytest.mark.asyncio
    async def test_continuous_monitoring(self):
        """Test continuous resource monitoring."""
        monitor = ResourceMonitor(
            resource_limits={"max_memory_mb": 1024}, monitoring_interval=0.1
        )

        # Start monitoring
        await monitor.start_monitoring()
        assert monitor.is_monitoring

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Should have collected metrics
        metrics = monitor.get_monitoring_metrics()
        assert len(metrics) > 0

        # Stop monitoring
        await monitor.stop_monitoring()
        assert not monitor.is_monitoring

    def test_alert_threshold_configuration(self):
        """Test configurable alert thresholds."""
        monitor = ResourceMonitor(
            resource_limits={"max_memory_mb": 1024},
            alert_thresholds={"memory": 0.8, "connections": 0.9},
        )

        # Should have configured thresholds
        assert monitor.alert_thresholds["memory"] == 0.8
        assert monitor.alert_thresholds["connections"] == 0.9

    def test_resource_usage_history(self):
        """Test resource usage history tracking."""
        monitor = ResourceMonitor({"max_memory_mb": 1024}, history_size=10)

        # Add some usage data
        for i in range(15):
            monitor._record_usage_sample({"memory_mb": 100 + i, "connections": i})

        history = monitor.get_usage_history()

        # Should keep only history_size samples
        assert len(history) == 10

        # Should be most recent samples
        assert history[-1]["memory_mb"] == 114


class TestRuntimeMonitor:
    """Test RuntimeMonitor for overall runtime health."""

    def test_runtime_monitor_initialization(self):
        """Test RuntimeMonitor initialization."""
        monitor = RuntimeMonitor(
            runtime_id="test-runtime",
            enable_performance_tracking=True,
            enable_health_checks=True,
        )

        assert monitor.runtime_id == "test-runtime"
        assert monitor.enable_performance_tracking is True
        assert monitor.enable_health_checks is True

    def test_workflow_execution_tracking(self):
        """Test workflow execution performance tracking."""
        monitor = RuntimeMonitor("test-runtime")

        # Start tracking execution
        execution_id = monitor.start_execution_tracking("workflow-1")
        assert execution_id is not None

        # End tracking
        monitor.end_execution_tracking(execution_id, success=True)

        # Should have performance metrics
        metrics = monitor.get_execution_metrics()
        assert len(metrics) == 1
        assert metrics[0]["workflow_id"] == "workflow-1"
        assert metrics[0]["success"] is True

    def test_health_check_registration(self):
        """Test health check registration and execution."""
        monitor = RuntimeMonitor("test-runtime")

        # Register health check
        def check_database():
            return {"status": "healthy", "details": "All connections active"}

        monitor.register_health_check("database", check_database)

        # Run health checks
        health_status = monitor.run_health_checks()

        assert "database" in health_status
        assert health_status["database"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_async_health_checks(self):
        """Test async health check support."""
        monitor = RuntimeMonitor("test-runtime")

        # Register async health check
        async def check_async_service():
            await asyncio.sleep(0.1)
            return {"status": "healthy", "latency_ms": 100}

        monitor.register_async_health_check("async_service", check_async_service)

        # Run async health checks
        health_status = await monitor.run_async_health_checks()

        assert "async_service" in health_status
        assert health_status["async_service"]["status"] == "healthy"

    def test_metric_aggregation(self):
        """Test metric aggregation and reporting."""
        monitor = RuntimeMonitor("test-runtime")

        # Add multiple execution metrics
        for i in range(10):
            exec_id = monitor.start_execution_tracking(f"workflow-{i}")
            time.sleep(0.001)  # Small delay
            monitor.end_execution_tracking(exec_id, success=i % 2 == 0)

        # Get aggregated metrics
        aggregated = monitor.get_aggregated_metrics()

        assert "total_executions" in aggregated
        assert "success_rate" in aggregated
        assert "avg_execution_time_ms" in aggregated

        assert aggregated["total_executions"] == 10
        assert 0 <= aggregated["success_rate"] <= 1

    def test_performance_benchmark_tracking(self):
        """Test performance benchmark tracking."""
        monitor = RuntimeMonitor("test-runtime", enable_performance_tracking=True)

        # Record benchmark
        monitor.record_performance_benchmark(
            operation="database_query",
            duration_ms=50,
            metadata={"query_type": "SELECT", "rows": 100},
        )

        benchmarks = monitor.get_performance_benchmarks()
        assert len(benchmarks) == 1
        assert benchmarks[0]["operation"] == "database_query"
        assert benchmarks[0]["duration_ms"] == 50


class TestEnterpriseMonitoring:
    """Test enterprise monitoring integration."""

    def test_metrics_collection_hooks(self):
        """Test enterprise metrics collection hooks."""
        # Mock enterprise metrics collector
        metrics_collector = Mock()

        monitor = RuntimeMonitor("test-runtime", metrics_collector=metrics_collector)

        # Should integrate with enterprise metrics
        assert monitor.metrics_collector is metrics_collector

        # Operations should trigger metrics collection
        exec_id = monitor.start_execution_tracking("test-workflow")
        monitor.end_execution_tracking(exec_id, success=True)

        # Should have called metrics collector
        assert metrics_collector.record_metric.called

    def test_audit_logging_integration(self):
        """Test audit logging integration."""
        audit_logger = Mock()

        monitor = RuntimeMonitor("test-runtime", audit_logger=audit_logger)

        # Should log audit events
        monitor.log_audit_event(
            event_type="workflow_execution",
            details={"workflow_id": "test", "success": True},
        )

        assert audit_logger.log_event.called

    def test_alerting_integration(self):
        """Test alerting system integration."""
        alert_manager = Mock()

        monitor = RuntimeMonitor("test-runtime", alert_manager=alert_manager)

        # Should trigger alerts on threshold violations
        monitor.check_and_trigger_alerts(
            {
                "memory_usage_percent": 95,  # High usage
                "error_rate": 0.25,  # High error rate
            }
        )

        assert alert_manager.trigger_alert.called

    @pytest.mark.asyncio
    async def test_enterprise_dashboard_integration(self):
        """Test enterprise dashboard integration."""
        dashboard_client = AsyncMock()

        monitor = RuntimeMonitor("test-runtime", dashboard_client=dashboard_client)

        # Should push metrics to dashboard
        await monitor.push_metrics_to_dashboard(
            {
                "runtime_id": "test-runtime",
                "timestamp": time.time(),
                "metrics": {"memory_mb": 512, "connections": 10},
            }
        )

        assert dashboard_client.push_metrics.called
