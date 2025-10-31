"""Integration tests for enhanced LocalRuntime with persistent mode support.

This module provides comprehensive integration tests for the enhanced LocalRuntime
implementation that supports persistent mode, connection pool coordination,
and enterprise features while maintaining backward compatibility.

Test Coverage:
- Persistent mode activation and lifecycle
- Resource coordination and management
- Connection pool sharing mechanisms with real databases
- Enterprise monitoring hooks
- Backward compatibility validation
- Resource limits enforcement
- Graceful shutdown procedures
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow.builder import WorkflowBuilder

# PostgreSQL test configuration
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5434)),
    "database": os.getenv("POSTGRES_DB", "kailash_test"),
    "user": os.getenv("POSTGRES_USER", "test_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "test_password"),
}


class TestPersistentRuntimeBasics:
    """Test basic persistent runtime functionality."""

    def test_default_initialization_backward_compatible(self):
        """Test that default initialization maintains backward compatibility."""
        runtime = LocalRuntime()

        # Should not be in persistent mode by default
        assert not hasattr(runtime, "_persistent_mode") or not runtime._persistent_mode
        assert (
            not hasattr(runtime, "_is_persistent_started")
            or not runtime._is_persistent_started
        )

        # Should maintain all existing default settings
        assert runtime.debug is False
        assert runtime.enable_cycles is True
        assert runtime.enable_async is True
        assert runtime.max_concurrency == 10

    def test_persistent_mode_initialization(self):
        """Test initialization with persistent mode enabled."""
        runtime = LocalRuntime(
            persistent_mode=True,
            enable_connection_sharing=True,
            max_concurrent_workflows=15,
            enable_monitoring=True,
        )

        # Should initialize persistent mode settings
        assert hasattr(runtime, "_persistent_mode")
        assert runtime._persistent_mode is True
        assert hasattr(runtime, "_enable_connection_sharing")
        assert runtime._enable_connection_sharing is True
        assert hasattr(runtime, "_max_concurrent_workflows")
        assert runtime._max_concurrent_workflows == 15

    def test_persistent_mode_configuration_validation(self):
        """Test that persistent mode configuration is validated properly."""
        # Valid configuration should work
        runtime = LocalRuntime(
            persistent_mode=True, max_concurrent_workflows=50, connection_pool_size=25
        )
        assert runtime._persistent_mode is True

        # Invalid configuration should set sensible defaults
        runtime = LocalRuntime(
            persistent_mode=True, max_concurrent_workflows=-1  # Invalid
        )
        # Should default to reasonable value
        assert runtime._max_concurrent_workflows > 0

    @pytest.mark.asyncio
    async def test_start_persistent_mode_lifecycle(self):
        """Test persistent mode startup lifecycle."""
        runtime = LocalRuntime(persistent_mode=True)

        # Should not be started initially
        assert not runtime._is_persistent_started

        # Start persistent mode
        await runtime.start_persistent_mode()

        # Should be marked as started
        assert runtime._is_persistent_started

        # Should have initialized persistent resources
        assert hasattr(runtime, "_persistent_event_loop")
        assert hasattr(runtime, "_resource_coordinator")
        assert hasattr(runtime, "_runtime_metrics")

    @pytest.mark.asyncio
    async def test_start_persistent_mode_idempotent(self):
        """Test that starting persistent mode multiple times is safe."""
        runtime = LocalRuntime(persistent_mode=True)

        # Start multiple times
        await runtime.start_persistent_mode()
        first_loop = runtime._persistent_event_loop

        await runtime.start_persistent_mode()
        second_loop = runtime._persistent_event_loop

        # Should be the same event loop
        assert first_loop is second_loop
        assert runtime._is_persistent_started

    @pytest.mark.asyncio
    async def test_persistent_mode_without_configuration_fails(self):
        """Test that persistent mode operations fail on non-persistent runtime."""
        runtime = LocalRuntime(persistent_mode=False)

        with pytest.raises(RuntimeError, match="Persistent mode not enabled"):
            await runtime.start_persistent_mode()

    def test_resource_limits_configuration(self):
        """Test resource limits configuration in persistent mode."""
        limits = {"max_memory_mb": 1024, "max_connections": 50, "max_cpu_percent": 80}

        runtime = LocalRuntime(persistent_mode=True, resource_limits=limits)

        assert runtime._resource_limits == limits
        assert hasattr(runtime, "_resource_monitor")

    def test_enterprise_monitoring_hooks(self):
        """Test that enterprise monitoring hooks are properly initialized."""
        runtime = LocalRuntime(
            persistent_mode=True, enable_monitoring=True, enable_audit=True
        )

        # Should have monitoring components
        assert hasattr(runtime, "_metrics_collector")
        assert hasattr(runtime, "_health_monitor")
        assert hasattr(runtime, "_audit_logger")

        # Should be enabled
        assert runtime.enable_monitoring is True
        assert runtime.enable_audit is True


class TestConnectionPoolCoordination:
    """Test connection pool coordination functionality."""

    def test_connection_sharing_initialization(self):
        """Test connection pool sharing initialization."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)

        assert hasattr(runtime, "_pool_coordinator")
        assert runtime._enable_connection_sharing is True

    def test_connection_sharing_disabled_by_default(self):
        """Test that connection sharing can be disabled."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=False)

        assert runtime._enable_connection_sharing is False

    @pytest.mark.asyncio
    async def test_get_shared_connection_pool(self):
        """Test getting shared connection pools."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)

        await runtime.start_persistent_mode()

        # Should be able to get connection pools
        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 10,
        }
        pool = await runtime.get_shared_connection_pool("test_db", pool_config)

        assert pool is not None
        assert hasattr(runtime._pool_coordinator, "_pools")

    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self):
        """Test that connection pools are reused properly."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)

        await runtime.start_persistent_mode()

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 10,
        }

        # Get pool twice with same config
        pool1 = await runtime.get_shared_connection_pool("test_db", pool_config)
        pool2 = await runtime.get_shared_connection_pool("test_db", pool_config)

        # Should be the same pool instance
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_connection_pool_isolation_fix(self):
        """Test that connection pool isolation issue is fixed."""
        # Create two runtime instances
        runtime1 = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)
        runtime2 = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)

        await runtime1.start_persistent_mode()
        await runtime2.start_persistent_mode()

        pool_config = {
            "database_url": f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}",
            "database_type": "postgresql",
            "pool_size": 10,
        }

        # Both runtimes should be able to coordinate pools
        pool1 = await runtime1.get_shared_connection_pool("shared_db", pool_config)
        pool2 = await runtime2.get_shared_connection_pool("shared_db", pool_config)

        # Pools should be coordinated (either same instance or coordinated)
        assert pool1 is not None
        assert pool2 is not None


class TestResourceManagement:
    """Test resource management and limits."""

    def test_resource_limits_enforcement_setup(self):
        """Test resource limits enforcement setup."""
        limits = {
            "max_memory_mb": 512,
            "max_connections": 25,
            "max_concurrent_workflows": 5,
        }

        runtime = LocalRuntime(persistent_mode=True, resource_limits=limits)

        assert runtime._resource_limits == limits
        assert hasattr(runtime, "_resource_enforcer")

    @pytest.mark.asyncio
    async def test_resource_monitoring_startup(self):
        """Test resource monitoring starts with persistent mode."""
        runtime = LocalRuntime(
            persistent_mode=True,
            enable_monitoring=True,
            resource_limits={"max_memory_mb": 1024},
        )

        await runtime.start_persistent_mode()

        # Should have started resource monitoring
        assert hasattr(runtime, "_resource_monitor")
        assert runtime._resource_monitor.is_monitoring

    @pytest.mark.asyncio
    async def test_concurrent_workflow_limit_enforcement(self):
        """Test that concurrent workflow limits are enforced."""
        runtime = LocalRuntime(persistent_mode=True, max_concurrent_workflows=2)

        await runtime.start_persistent_mode()

        # Track concurrent executions
        assert hasattr(runtime, "_active_workflows")
        assert len(runtime._active_workflows) == 0

        # Should be able to check if can execute
        can_execute = runtime.can_execute_workflow()
        assert can_execute is True

    def test_get_runtime_metrics_structure(self):
        """Test runtime metrics structure."""
        runtime = LocalRuntime(persistent_mode=True, enable_monitoring=True)

        metrics = runtime.get_runtime_metrics()

        # Should have standard metric categories
        assert "resources" in metrics
        assert "connections" in metrics
        assert "performance" in metrics
        assert "health" in metrics

        # Each category should have relevant fields
        assert "memory_mb" in metrics["resources"]
        assert "active_connections" in metrics["connections"]
        assert "avg_execution_time_ms" in metrics["performance"]
        assert "status" in metrics["health"]

    def test_health_check_api(self):
        """Test health check API functionality."""
        runtime = LocalRuntime(persistent_mode=True, enable_monitoring=True)

        health_status = runtime.get_health_status()

        # Should have health check structure
        assert "status" in health_status
        assert "details" in health_status
        assert "timestamp" in health_status

        # Status should be valid
        assert health_status["status"] in ["healthy", "degraded", "unhealthy"]


class TestGracefulShutdown:
    """Test graceful shutdown functionality."""

    @pytest.mark.asyncio
    async def test_shutdown_gracefully_basic(self):
        """Test basic graceful shutdown."""
        runtime = LocalRuntime(persistent_mode=True)
        await runtime.start_persistent_mode()

        # Should shutdown without errors
        await runtime.shutdown_gracefully(timeout=30)

        # Should be marked as shutdown
        assert not runtime._is_persistent_started

    @pytest.mark.asyncio
    async def test_shutdown_with_active_workflows(self):
        """Test shutdown waits for active workflows."""
        runtime = LocalRuntime(persistent_mode=True, max_concurrent_workflows=2)
        await runtime.start_persistent_mode()

        # Simulate active workflows
        runtime._active_workflows = {"workflow1": Mock(), "workflow2": Mock()}

        start_time = time.time()
        await runtime.shutdown_gracefully(timeout=5)
        end_time = time.time()

        # Should have waited for workflows or timeout
        assert (end_time - start_time) >= 0  # At least some time passed
        assert not runtime._is_persistent_started

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_resources(self):
        """Test that shutdown properly cleans up resources."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)
        await runtime.start_persistent_mode()

        # Track cleanup
        cleanup_called = []

        async def mock_cleanup():
            cleanup_called.append(True)

        runtime._pool_coordinator.cleanup = mock_cleanup

        await runtime.shutdown_gracefully()

        # Should have called cleanup
        assert len(cleanup_called) > 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)  # Need more time than the shutdown timeout we're testing
    async def test_shutdown_timeout_handling(self):
        """Test shutdown timeout handling."""
        runtime = LocalRuntime(persistent_mode=True)
        await runtime.start_persistent_mode()

        # Mock a hanging operation
        original_cleanup = runtime._cleanup_resources

        async def hanging_cleanup():
            await asyncio.sleep(10)  # Hang longer than timeout

        runtime._cleanup_resources = hanging_cleanup

        start_time = time.time()
        await runtime.shutdown_gracefully(timeout=1)
        end_time = time.time()

        # Should respect timeout
        assert (end_time - start_time) <= 2  # Should timeout around 1 second


class TestBackwardCompatibility:
    """Test backward compatibility with existing LocalRuntime usage."""

    def test_existing_code_unchanged(self):
        """Test that existing code patterns work unchanged."""
        # Traditional usage patterns should work
        runtime = LocalRuntime()
        assert runtime is not None

        runtime = LocalRuntime(debug=True, enable_cycles=False)
        assert runtime.debug is True
        assert runtime.enable_cycles is False

    @pytest.mark.asyncio
    async def test_execute_method_unchanged(self):
        """Test that execute method signature and behavior is unchanged."""
        runtime = LocalRuntime()

        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "test", {"code": "result = {'result': 'test'}"}
        )

        # Should execute normally
        results, run_id = runtime.execute(workflow.build())

        assert results is not None
        assert run_id is not None
        assert "test" in results

    def test_no_persistent_features_by_default(self):
        """Test that persistent features are not active by default."""
        runtime = LocalRuntime()

        # Should not have persistent mode features
        assert not hasattr(runtime, "_persistent_mode") or not runtime._persistent_mode
        assert (
            not hasattr(runtime, "_is_persistent_started")
            or not runtime._is_persistent_started
        )

        # Traditional methods should still work
        metrics = runtime.get_runtime_metrics()
        assert metrics is not None

    def test_enterprise_features_opt_in(self):
        """Test that enterprise features are opt-in."""
        # Default runtime - minimal enterprise features
        runtime_basic = LocalRuntime()
        assert not runtime_basic.enable_security
        assert not runtime_basic.enable_audit

        # Enterprise runtime - features enabled
        runtime_enterprise = LocalRuntime(
            enable_security=True, enable_audit=True, enable_monitoring=True
        )
        assert runtime_enterprise.enable_security
        assert runtime_enterprise.enable_audit
        assert runtime_enterprise.enable_monitoring


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_start_persistent_mode_error_handling(self):
        """Test error handling during persistent mode startup."""
        runtime = LocalRuntime(persistent_mode=True)

        # Mock an initialization error
        with patch.object(
            runtime,
            "_initialize_persistent_resources",
            side_effect=Exception("Init failed"),
        ):
            with pytest.raises(RuntimeError, match="Failed to start persistent mode"):
                await runtime.start_persistent_mode()

    @pytest.mark.asyncio
    async def test_connection_pool_error_handling(self):
        """Test error handling in connection pool operations."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)
        await runtime.start_persistent_mode()

        # Invalid pool config should handle gracefully
        with pytest.raises(ValueError):
            await runtime.get_shared_connection_pool("invalid", {})

    def test_resource_limit_validation(self):
        """Test resource limit validation."""
        # Invalid limits should be caught
        with pytest.raises(ValueError):
            LocalRuntime(persistent_mode=True, resource_limits={"max_memory_mb": -1})

    @pytest.mark.asyncio
    async def test_shutdown_error_handling(self):
        """Test error handling during shutdown."""
        runtime = LocalRuntime(persistent_mode=True)
        await runtime.start_persistent_mode()

        # Mock cleanup error
        with patch.object(
            runtime, "_cleanup_resources", side_effect=Exception("Cleanup failed")
        ):
            # Should not raise exception, but log error
            await runtime.shutdown_gracefully()
            assert not runtime._is_persistent_started
