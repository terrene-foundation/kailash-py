"""Integration test for ResourceLimitEnforcer with LocalRuntime."""

import time

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.resource_manager import EnforcementPolicy, MemoryLimitExceededError
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestResourceLimitRuntimeIntegration:
    """Integration tests for ResourceLimitEnforcer with LocalRuntime."""

    def test_runtime_resource_limit_initialization(self):
        """Test that LocalRuntime correctly initializes ResourceLimitEnforcer."""
        runtime = LocalRuntime(
            resource_limits={
                "max_memory_mb": 512,
                "max_connections": 5,
                "max_cpu_percent": 80.0,
                "enforcement_policy": "adaptive",
            }
        )

        # Verify resource enforcer was created
        assert runtime._resource_enforcer is not None
        assert runtime._resource_enforcer.max_memory_mb == 512
        assert runtime._resource_enforcer.max_connections == 5
        assert runtime._resource_enforcer.max_cpu_percent == 80.0
        assert (
            runtime._resource_enforcer.enforcement_policy == EnforcementPolicy.ADAPTIVE
        )

    def test_workflow_execution_with_resource_limits(self):
        """Test workflow execution with resource limits enabled."""
        runtime = LocalRuntime(
            resource_limits={
                "max_memory_mb": 2048,
                "max_connections": 10,
                "enforcement_policy": "adaptive",
            }
        )

        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "test_task",
            {
                "code": """
import time
result = {
    'message': 'Resource limit test completed',
    'timestamp': time.time(),
    'success': True
}
""",
                "output_key": "test_result",
            },
        )

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify execution succeeded
        assert results is not None
        assert run_id is not None
        assert "test_task" in results

        # Verify resource metrics are available
        metrics = runtime.get_resource_metrics()
        assert metrics is not None
        assert "memory_usage_mb" in metrics
        assert "cpu_usage_percent" in metrics
        assert "active_connections" in metrics

    def test_adaptive_enforcement_with_workflow(self):
        """Test adaptive enforcement policy with actual workflow."""
        runtime = LocalRuntime(
            resource_limits={
                "max_memory_mb": 1024,
                "enforcement_policy": "adaptive",
                "degradation_strategy": "defer",
            }
        )

        # Create workflow that will trigger resource monitoring
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "memory_test",
            {
                "code": """
# This will trigger resource monitoring
import gc
import time

# Force garbage collection and check memory
gc.collect()
time.sleep(0.1)  # Small delay for monitoring

result = {
    'message': 'Memory monitoring test',
    'gc_collected': True,
    'success': True
}
""",
                "output_key": "memory_test_result",
            },
        )

        # Execute workflow - should succeed with adaptive policy
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Verify execution completed
        assert results is not None
        assert "memory_test" in results

        # Get execution metrics
        metrics = runtime.get_execution_metrics(run_id)
        assert metrics is not None
        assert metrics["run_id"] == run_id

    def test_warn_enforcement_policy(self):
        """Test warn enforcement policy allows execution with warnings."""
        runtime = LocalRuntime(
            resource_limits={
                "max_memory_mb": 1,  # Very low limit to trigger warnings
                "enforcement_policy": "warn",
            }
        )

        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "warn_test",
            {
                "code": "result = {'message': 'Warn policy test', 'success': True}",
                "output_key": "warn_result",
            },
        )

        # Execute workflow - should succeed with warnings
        results, run_id = runtime.execute(workflow.build())

        # Verify execution succeeded despite warnings
        assert results is not None
        assert "warn_test" in results

    def test_resource_metrics_collection(self):
        """Test that resource metrics are properly collected."""
        runtime = LocalRuntime(
            resource_limits={
                "max_memory_mb": 1024,
                "max_connections": 5,
                "enable_metrics_history": True,
            }
        )

        # Get initial metrics
        initial_metrics = runtime.get_resource_metrics()
        assert initial_metrics is not None

        # Execute a workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "metrics_test",
            {
                "code": "result = {'message': 'Metrics test', 'success': True}",
                "output_key": "metrics_result",
            },
        )

        results, run_id = runtime.execute(workflow.build())
        assert results is not None

        # Get metrics after execution
        final_metrics = runtime.get_resource_metrics()
        assert final_metrics is not None

        # Verify metrics structure
        required_keys = [
            "timestamp",
            "memory_usage_mb",
            "memory_usage_percent",
            "cpu_usage_percent",
            "active_connections",
            "peak_memory_mb",
            "peak_cpu_percent",
            "enforcement_policy",
            "uptime_seconds",
        ]

        for key in required_keys:
            assert key in final_metrics, f"Missing required metric: {key}"

        # Verify metrics are reasonable
        assert final_metrics["memory_usage_mb"] > 0
        assert final_metrics["cpu_usage_percent"] >= 0
        assert final_metrics["active_connections"] >= 0
        assert final_metrics["uptime_seconds"] >= 0

    def test_no_resource_limits_configured(self):
        """Test runtime behavior when no resource limits are configured."""
        runtime = LocalRuntime()  # No resource_limits parameter

        # Verify no resource enforcer was created
        assert runtime._resource_enforcer is None

        # Verify metrics methods return None
        assert runtime.get_resource_metrics() is None
        assert runtime.get_execution_metrics("test_run") is None

        # Verify workflow execution still works
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "no_limits_test",
            {
                "code": "result = {'message': 'No limits test', 'success': True}",
                "output_key": "no_limits_result",
            },
        )

        results, run_id = runtime.execute(workflow.build())
        assert results is not None
        assert "no_limits_test" in results
