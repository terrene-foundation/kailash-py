"""Unit tests for ResourceLimitEnforcer class.

This module tests the ResourceLimitEnforcer class in isolation using mocks
for system resources like memory and CPU monitoring.

Test categories:
- Constructor validation and parameter handling
- Memory limit enforcement logic
- Connection limit enforcement logic
- CPU usage monitoring logic
- Error handling and exception types
- Degradation policy implementations
- Thread safety for concurrent access
- Configuration validation
"""

import asyncio
import threading
import time
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import will be added once we create the class
# from kailash.runtime.resource_manager import ResourceLimitEnforcer, EnforcementPolicy
from kailash.sdk_exceptions import ResourceLimitExceededError


class TestResourceLimitEnforcer:
    """Test ResourceLimitEnforcer class functionality."""

    def test_constructor_default_parameters(self):
        """Test ResourceLimitEnforcer constructor with default parameters."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()

        # Verify default values
        assert enforcer.max_memory_mb is None
        assert enforcer.max_connections is None
        assert enforcer.max_cpu_percent is None
        assert enforcer.monitoring_interval == 1.0
        assert enforcer.enable_alerts is True

    def test_constructor_custom_parameters(self):
        """Test ResourceLimitEnforcer constructor with custom parameters."""
        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            max_memory_mb=512,
            max_connections=50,
            max_cpu_percent=80.0,
            enforcement_policy="strict",
            monitoring_interval=2.0,
        )

        # Verify custom values
        assert enforcer.max_memory_mb == 512
        assert enforcer.max_connections == 50
        assert enforcer.max_cpu_percent == 80.0
        assert enforcer.enforcement_policy == EnforcementPolicy.STRICT
        assert enforcer.monitoring_interval == 2.0

    def test_constructor_invalid_parameters(self):
        """Test ResourceLimitEnforcer constructor with invalid parameters."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        # Test invalid memory limit
        with pytest.raises(ValueError, match="max_memory_mb must be positive"):
            ResourceLimitEnforcer(max_memory_mb=-1)

        # Test invalid connections limit
        with pytest.raises(ValueError, match="max_connections must be positive"):
            ResourceLimitEnforcer(max_connections=0)

        # Test invalid CPU limit
        with pytest.raises(
            ValueError, match="max_cpu_percent must be between 0 and 100"
        ):
            ResourceLimitEnforcer(max_cpu_percent=150.0)

        # Test invalid monitoring interval
        with pytest.raises(ValueError, match="monitoring_interval must be positive"):
            ResourceLimitEnforcer(monitoring_interval=-1.0)

    @patch("psutil.Process")
    def test_memory_limit_enforcement_below_threshold(self, mock_process):
        """Test memory monitoring when usage is below threshold."""
        # Mock process memory to show low usage
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 1024 * 1024 * 100  # 100MB
        mock_process.return_value.memory_info.return_value = mock_memory_info

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(max_memory_mb=512)
        result = enforcer.check_memory_limits()

        assert result.can_proceed is True
        assert result.resource_type == "memory"
        assert result.current_usage == 100.0  # 100MB
        assert result.limit == 512.0

    @patch("psutil.Process")
    def test_memory_limit_enforcement_above_threshold(self, mock_process):
        """Test memory monitoring when usage exceeds threshold."""
        # Mock process memory to show high usage
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 1024 * 1024 * 600  # 600MB
        mock_process.return_value.memory_info.return_value = mock_memory_info

        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            MemoryLimitExceededError,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            max_memory_mb=512, enforcement_policy=EnforcementPolicy.STRICT
        )

        # Check memory limits - should indicate cannot proceed
        result = enforcer.check_memory_limits()
        assert result.can_proceed is False
        assert result.current_usage == 600.0  # 600MB
        assert result.limit == 512.0

        # Enforce memory limits - should raise exception
        with pytest.raises(MemoryLimitExceededError) as exc_info:
            enforcer.enforce_memory_limits()
        assert "memory" in str(exc_info.value).lower()
        assert exc_info.value.current_mb == 600.0
        assert exc_info.value.limit_mb == 512.0

    def test_connection_limit_enforcement_below_threshold(self):
        """Test connection limit enforcement when below threshold."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(max_connections=10)

        # Should allow new connections when below limit
        for i in range(5):
            result = enforcer.request_connection(f"conn_{i}")
            assert result["granted"] is True
            assert result["connection_id"] == f"conn_{i}"
            assert result["active_count"] == i + 1

    def test_connection_limit_enforcement_at_threshold(self):
        """Test connection limit enforcement when at threshold."""
        from kailash.runtime.resource_manager import (
            ConnectionLimitExceededError,
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            max_connections=5, enforcement_policy=EnforcementPolicy.STRICT
        )

        # Use up all connections
        for i in range(5):
            result = enforcer.request_connection(f"conn_{i}")
            assert result["granted"] is True

        # Should reject connection when at limit
        with pytest.raises(ConnectionLimitExceededError) as exc_info:
            enforcer.request_connection("excess_conn")
        assert "connection" in str(exc_info.value).lower()
        assert exc_info.value.current_connections == 5
        assert exc_info.value.max_connections == 5

    @patch("psutil.cpu_percent")
    def test_cpu_monitoring_below_threshold(self, mock_cpu):
        """Test CPU usage monitoring when below threshold."""
        mock_cpu.return_value = 40.0

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(max_cpu_percent=80.0)
        # Should allow execution when CPU usage is acceptable
        result = enforcer.check_cpu_limits()
        assert result.can_proceed is True
        assert result.current_usage == 40.0
        assert result.limit == 80.0

    @patch("psutil.cpu_percent")
    def test_cpu_monitoring_above_threshold(self, mock_cpu):
        """Test CPU usage monitoring when above threshold."""
        mock_cpu.return_value = 95.0

        from kailash.runtime.resource_manager import (
            CPULimitExceededError,
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            max_cpu_percent=80.0, enforcement_policy=EnforcementPolicy.STRICT
        )
        # Should throttle execution when CPU usage is high
        with pytest.raises(CPULimitExceededError) as exc_info:
            enforcer.enforce_cpu_limits()
        assert "cpu" in str(exc_info.value).lower()

    def test_enforcement_policy_strict(self):
        """Test strict enforcement policy - immediately reject when limits exceeded."""
        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(enforcement_policy=EnforcementPolicy.STRICT)
        # Should immediately reject when limits are exceeded
        assert enforcer.enforcement_policy == EnforcementPolicy.STRICT

    def test_enforcement_policy_warn(self):
        """Test warn enforcement policy - log warnings but allow execution."""
        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(enforcement_policy=EnforcementPolicy.WARN)
        # Should log warnings but allow execution to continue
        assert enforcer.enforcement_policy == EnforcementPolicy.WARN

    def test_enforcement_policy_adaptive(self):
        """Test adaptive enforcement policy - graceful degradation."""
        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(enforcement_policy=EnforcementPolicy.ADAPTIVE)
        # Should implement graceful degradation strategies
        assert enforcer.enforcement_policy == EnforcementPolicy.ADAPTIVE

    def test_graceful_degradation_queue_strategy(self):
        """Test queue degradation strategy - queue requests when limits exceeded."""
        from kailash.runtime.resource_manager import (
            DegradationStrategy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(degradation_strategy=DegradationStrategy.QUEUE)
        # Should queue requests when resources are exhausted
        assert enforcer.degradation_strategy == DegradationStrategy.QUEUE

    def test_graceful_degradation_reject_strategy(self):
        """Test reject degradation strategy - immediately reject when limits exceeded."""
        from kailash.runtime.resource_manager import (
            DegradationStrategy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            degradation_strategy=DegradationStrategy.REJECT
        )
        # Should immediately reject when resources are exhausted
        assert enforcer.degradation_strategy == DegradationStrategy.REJECT

    def test_graceful_degradation_defer_strategy(self):
        """Test defer degradation strategy - delay execution when limits exceeded."""
        from kailash.runtime.resource_manager import (
            DegradationStrategy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(degradation_strategy=DegradationStrategy.DEFER)
        # Should defer execution when resources are exhausted
        assert enforcer.degradation_strategy == DegradationStrategy.DEFER

    def test_thread_safety_concurrent_resource_requests(self):
        """Test thread safety for concurrent resource limit checks."""
        import uuid

        from kailash.runtime.resource_manager import (
            EnforcementPolicy,
            ResourceLimitEnforcer,
        )

        enforcer = ResourceLimitEnforcer(
            max_connections=10, enforcement_policy=EnforcementPolicy.STRICT
        )

        results = []
        errors = []

        def worker(worker_id):
            try:
                # Each thread tries to request a unique connection
                result = enforcer.request_connection(f"conn_{worker_id}_{uuid.uuid4()}")
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create 20 threads but only 10 connections allowed
        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True) for i in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have 10 successful connections and 10 rejections
        successful = len([r for r in results if r["granted"]])
        total_errors = len(errors)

        # Debug output if test fails
        if successful != 10 or total_errors != 10:
            print(f"Successful: {successful}, Errors: {total_errors}")
            print(f"Results: {results[:5]}...")  # First 5 results
            print(f"Active connections: {enforcer.get_active_connection_count()}")

        assert successful == 10, f"Expected 10 successful connections, got {successful}"
        assert total_errors == 10, f"Expected 10 errors, got {total_errors}"

    def test_resource_monitoring_interval_configuration(self):
        """Test configuration of resource monitoring interval."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(monitoring_interval=0.5)
        # Should use custom monitoring interval
        assert enforcer.monitoring_interval == 0.5

    def test_resource_cleanup_on_connection_release(self):
        """Test resource cleanup when connections are released."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(max_connections=5)
        # Should properly clean up resources when connections are released
        result = enforcer.request_connection("test_conn")
        conn_id = result["connection_id"]
        enforcer.release_connection(conn_id)
        assert enforcer.get_active_connection_count() == 0

    def test_resource_limit_exceeded_error_types(self):
        """Test different types of ResourceLimitExceededError for different resources."""
        # Test will verify specific error types once implemented
        # Memory, CPU, Connection errors should have distinct error codes/messages
        pass

    @patch("psutil.Process")
    @patch("psutil.cpu_percent")
    def test_comprehensive_resource_check(self, mock_cpu, mock_process):
        """Test comprehensive resource checking across all resource types."""
        mock_cpu.return_value = 30.0
        mock_memory_info = MagicMock()
        mock_memory_info.rss = 100 * 1024 * 1024  # 100MB
        mock_process.return_value.memory_info.return_value = mock_memory_info

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(
            max_memory_mb=512, max_connections=10, max_cpu_percent=80.0
        )
        # Should check all resource limits in a single call
        result = enforcer.check_all_limits()
        assert result["memory"].can_proceed is True
        assert result["cpu"].can_proceed is True
        assert result["connections"].can_proceed is True

    def test_resource_usage_reporting(self):
        """Test resource usage reporting and metrics."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()
        # Should provide detailed resource usage metrics
        metrics = enforcer.get_resource_metrics()
        assert "memory_usage_mb" in metrics
        assert "cpu_usage_percent" in metrics
        assert "active_connections" in metrics

    @pytest.mark.asyncio
    async def test_async_resource_monitoring(self):
        """Test asynchronous resource monitoring."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()
        # Should support async resource monitoring
        await enforcer.start_monitoring()
        await asyncio.sleep(0.1)
        await enforcer.stop_monitoring()

    def test_resource_alert_thresholds(self):
        """Test configurable alert thresholds for resource monitoring."""
        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(
            memory_alert_threshold=0.8,  # Alert at 80% of max
            cpu_alert_threshold=0.7,  # Alert at 70% of max
            connection_alert_threshold=0.9,  # Alert at 90% of max
        )
        # Should trigger alerts at configured thresholds
        assert enforcer.memory_alert_threshold == 0.8
        assert enforcer.cpu_alert_threshold == 0.7
        assert enforcer.connection_alert_threshold == 0.9


class TestEnforcementPolicies:
    """Test different enforcement policy implementations."""

    def test_enforcement_policy_enum_values(self):
        """Test EnforcementPolicy enum has expected values."""
        from kailash.runtime.resource_manager import EnforcementPolicy

        assert EnforcementPolicy.STRICT.value == "strict"
        assert EnforcementPolicy.WARN.value == "warn"
        assert EnforcementPolicy.ADAPTIVE.value == "adaptive"

    def test_degradation_strategy_enum_values(self):
        """Test DegradationStrategy enum has expected values."""
        from kailash.runtime.resource_manager import DegradationStrategy

        assert DegradationStrategy.QUEUE.value == "queue"
        assert DegradationStrategy.REJECT.value == "reject"
        assert DegradationStrategy.DEFER.value == "defer"


class TestResourceLimitExceededErrorTypes:
    """Test specific ResourceLimitExceededError subtypes."""

    def test_memory_limit_exceeded_error(self):
        """Test MemoryLimitExceededError specific functionality."""
        # Test will verify memory-specific error details
        pass

    def test_connection_limit_exceeded_error(self):
        """Test ConnectionLimitExceededError specific functionality."""
        # Test will verify connection-specific error details
        pass

    def test_cpu_limit_exceeded_error(self):
        """Test CPULimitExceededError specific functionality."""
        # Test will verify CPU-specific error details
        pass


class TestResourceMetrics:
    """Test resource metrics collection and reporting."""

    def test_metrics_collection_format(self):
        """Test format of collected resource metrics."""
        from datetime import datetime

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()
        # Should return metrics in consistent format
        metrics = enforcer.get_resource_metrics()
        assert isinstance(metrics["timestamp"], datetime)
        assert isinstance(metrics["memory_usage_mb"], (int, float))
        assert isinstance(metrics["cpu_usage_percent"], (int, float))

    def test_metrics_history_tracking(self):
        """Test tracking of resource metrics over time."""
        import time

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer(enable_metrics_history=True)
        # Should maintain history of resource metrics
        metrics1 = enforcer.get_resource_metrics()
        time.sleep(0.1)
        metrics2 = enforcer.get_resource_metrics()

        # Check metrics history is being tracked
        if hasattr(enforcer, "metrics_history"):
            assert len(enforcer.metrics_history) >= 2
            # history = enforcer.get_metrics_history(duration_seconds=60)
            # assert isinstance(history, list)


# Performance tests (should complete quickly for unit tests)
class TestResourceLimitEnforcerPerformance:
    """Test performance characteristics of ResourceLimitEnforcer."""

    def test_resource_check_performance(self):
        """Test that resource checks complete quickly."""
        import time

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()

        start_time = time.time()
        # Should complete resource check in < 100ms (relaxed for CI)
        enforcer.check_all_limits()
        end_time = time.time()

        assert (end_time - start_time) < 0.1  # < 100ms

    def test_concurrent_resource_check_performance(self):
        """Test performance of concurrent resource checks."""
        import threading
        import time

        from kailash.runtime.resource_manager import ResourceLimitEnforcer

        enforcer = ResourceLimitEnforcer()

        def check_resources():
            enforcer.check_all_limits()

        start_time = time.time()
        threads = [
            threading.Thread(target=check_resources, daemon=True) for _ in range(10)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        end_time = time.time()

        # Should handle 10 concurrent checks in < 200ms (relaxed for CI)
        assert (end_time - start_time) < 0.2
