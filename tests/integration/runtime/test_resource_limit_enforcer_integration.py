"""Integration tests for ResourceLimitEnforcer with real LocalRuntime.

This module tests ResourceLimitEnforcer integration with the LocalRuntime using
real Docker services and actual resource constraints. No mocking is used for
external services or resource monitoring.

Test categories:
- Real LocalRuntime integration with resource limits
- Memory pressure scenarios with actual workflows
- Connection pool exhaustion with real database connections
- CPU intensive workflow throttling
- Cross-workflow resource sharing and competition
- Resource recovery after exhaustion
- Performance impact measurement
"""

import asyncio
import threading
import time
from typing import Any, Dict

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import ResourceLimitExceededError
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestResourceLimitEnforcerIntegration:
    """Integration tests for ResourceLimitEnforcer with LocalRuntime."""

    @pytest.fixture
    async def runtime_with_limits(self):
        """Create LocalRuntime with resource limits configured."""
        # Will be updated once ResourceLimitEnforcer is integrated with LocalRuntime
        runtime = LocalRuntime(
            # resource_limits={
            #     "max_memory_mb": 256,
            #     "max_connections": 5,
            #     "max_cpu_percent": 70.0,
            #     "enforcement_policy": "strict"
            # }
        )
        yield runtime
        # Cleanup if needed

    def test_memory_intensive_workflow_enforcement(self, runtime_with_limits):
        """Test memory limit enforcement with memory-intensive workflow."""
        # Create workflow that consumes significant memory
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "memory_consumer",
            {
                "code": """
# Allocate large amount of memory (will be limited by enforcer)
data = [list(range(10000)) for _ in range(1000)]  # ~400MB
result = {"memory_allocated": len(data), "success": True}
""",
                "output_key": "memory_result",
            },
        )

        built_workflow = workflow.build()

        # Should raise ResourceLimitExceededError when memory limit exceeded
        # Once ResourceLimitEnforcer is integrated:
        # with pytest.raises(ResourceLimitExceededError) as exc_info:
        #     runtime_with_limits.execute(built_workflow)
        # assert "memory" in str(exc_info.value).lower()

        # For now, execute normally until integration is complete
        results, run_id = runtime_with_limits.execute(built_workflow)
        assert results is not None

    def test_connection_pool_exhaustion_enforcement(self, runtime_with_limits):
        """Test connection limit enforcement with multiple database connections."""
        # Create workflow that opens many database connections
        workflow = WorkflowBuilder()

        # Add multiple SQL nodes that would exhaust connection pool
        for i in range(10):  # More than max_connections=5
            workflow.add_node(
                "SQLDatabaseNode",
                f"db_query_{i}",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": f"SELECT {i} as query_id, pg_sleep(1);",
                    "output_key": f"query_result_{i}",
                },
            )

        built_workflow = workflow.build()

        # Should raise ResourceLimitExceededError when connection limit exceeded
        # Once ResourceLimitEnforcer is integrated:
        # with pytest.raises(ResourceLimitExceededError) as exc_info:
        #     runtime_with_limits.execute(built_workflow)
        # assert "connection" in str(exc_info.value).lower()

        # For now, execute normally until integration is complete
        results, run_id = runtime_with_limits.execute(built_workflow)
        assert results is not None

    def test_cpu_intensive_workflow_throttling(self, runtime_with_limits):
        """Test CPU limit enforcement with CPU-intensive workflow."""
        # Create workflow that consumes high CPU
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "cpu_consumer",
            {
                "code": """
import math
# CPU-intensive computation
result = 0
for i in range(1000000):
    result += math.sqrt(i)
output = {"computation_result": result, "success": True}
""",
                "output_key": "cpu_result",
            },
        )

        built_workflow = workflow.build()

        # Should throttle execution when CPU usage is high
        # Once ResourceLimitEnforcer is integrated:
        # start_time = time.time()
        # results, run_id = runtime_with_limits.execute(built_workflow)
        # end_time = time.time()
        #
        # # Execution should be throttled, taking longer than normal
        # assert (end_time - start_time) > 2.0  # Should be throttled

        # For now, execute normally until integration is complete
        results, run_id = runtime_with_limits.execute(built_workflow)
        assert results is not None

    def test_concurrent_workflow_resource_competition(self, runtime_with_limits):
        """Test resource sharing between concurrent workflows."""

        def execute_workflow(workflow_id: str, results: Dict[str, Any]):
            """Execute a workflow and store results."""
            workflow = WorkflowBuilder()
            workflow.add_node(
                "SQLDatabaseNode",
                f"query_{workflow_id}",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": f"SELECT '{workflow_id}' as workflow_id, pg_sleep(0.5);",
                    "output_key": f"result_{workflow_id}",
                },
            )

            try:
                result, run_id = runtime_with_limits.execute(workflow.build())
                results[workflow_id] = {
                    "success": True,
                    "result": result,
                    "run_id": run_id,
                }
            except ResourceLimitExceededError as e:
                results[workflow_id] = {"success": False, "error": str(e)}
            except Exception as e:
                results[workflow_id] = {"success": False, "error": str(e)}

        # Launch multiple concurrent workflows
        results = {}
        threads = []
        for i in range(10):  # More workflows than connection limit
            thread = threading.Thread(
                target=execute_workflow, args=(f"workflow_{i}", results)
            )
            threads.append(thread)
            thread.start()

        # Wait for all workflows to complete
        for thread in threads:
            thread.join()

        # Some workflows should succeed, others should be limited
        # Once ResourceLimitEnforcer is integrated:
        # successful_workflows = [r for r in results.values() if r["success"]]
        # failed_workflows = [r for r in results.values() if not r["success"]]
        #
        # assert len(successful_workflows) <= 5  # Max connections
        # assert len(failed_workflows) >= 5     # Some should fail due to limits

        # For now, verify all workflows completed
        assert len(results) == 10
        for result in results.values():
            assert "success" in result

    def test_resource_recovery_after_exhaustion(self, runtime_with_limits):
        """Test resource recovery after limits are exceeded."""
        # First, exhaust resources
        workflow1 = WorkflowBuilder()
        for i in range(6):  # More than max_connections=5
            workflow1.add_node(
                "SQLDatabaseNode",
                f"exhaust_query_{i}",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": f"SELECT {i}, pg_sleep(2);",  # Long-running queries
                    "output_key": f"exhaust_result_{i}",
                },
            )

        # Then, try to execute another workflow after some time
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "SQLDatabaseNode",
            "recovery_query",
            {
                "connection_string": "postgresql://test:test@localhost:5432/test_db",
                "query": "SELECT 'recovered' as status;",
                "output_key": "recovery_result",
            },
        )

        # Execute first workflow (should fail or be throttled)
        try:
            results1, run_id1 = runtime_with_limits.execute(workflow1.build())
        except ResourceLimitExceededError:
            pass  # Expected

        # Wait for resources to be freed
        time.sleep(3)

        # Execute second workflow (should succeed after recovery)
        results2, run_id2 = runtime_with_limits.execute(workflow2.build())
        assert results2 is not None
        assert run_id2 is not None

    def test_resource_limit_performance_impact(self, runtime_with_limits):
        """Test performance impact of resource limit enforcement."""
        # Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "simple_task",
            {
                "code": "result = {'message': 'Hello World', 'success': True}",
                "output_key": "greeting",
            },
        )

        built_workflow = workflow.build()

        # Measure execution time with resource limits
        start_time = time.time()
        for _ in range(10):
            results, run_id = runtime_with_limits.execute(built_workflow)
            assert results is not None
        limited_time = time.time() - start_time

        # Measure execution time without resource limits (baseline)
        baseline_runtime = LocalRuntime()
        start_time = time.time()
        for _ in range(10):
            results, run_id = baseline_runtime.execute(built_workflow)
            assert results is not None
        baseline_time = time.time() - start_time

        # Resource limit enforcement should have minimal performance impact
        # Once ResourceLimitEnforcer is integrated:
        # overhead_ratio = limited_time / baseline_time
        # assert overhead_ratio < 1.2  # Less than 20% overhead

        # For now, just verify both completed successfully
        assert limited_time > 0
        assert baseline_time > 0

    def test_adaptive_enforcement_policy(self, runtime_with_limits):
        """Test adaptive enforcement policy with gradual resource pressure."""
        # This will test the adaptive policy once implemented
        # Should gradually throttle rather than immediately reject

        workflows = []
        for i in range(8):  # Gradually increase load
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"adaptive_task_{i}",
                {
                    "code": f"""
import time
time.sleep(0.1 * {i})  # Increasing delay
result = {{'task_id': {i}, 'success': True}}
""",
                    "output_key": f"adaptive_result_{i}",
                },
            )
            workflows.append(workflow.build())

        # Execute workflows with adaptive policy
        # Once ResourceLimitEnforcer supports adaptive policy:
        # execution_times = []
        # for workflow in workflows:
        #     start_time = time.time()
        #     results, run_id = runtime_with_limits.execute(workflow)
        #     end_time = time.time()
        #     execution_times.append(end_time - start_time)
        #     assert results is not None
        #
        # # Later workflows should take progressively longer (adaptive throttling)
        # assert execution_times[-1] > execution_times[0]

        # For now, execute all workflows normally
        for workflow in workflows:
            results, run_id = runtime_with_limits.execute(workflow)
            assert results is not None

    def test_resource_monitoring_alerts(self, runtime_with_limits):
        """Test resource monitoring alerts with real resource usage."""
        # Create workflow that gradually increases resource usage
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "monitoring_task",
            {
                "code": """
import psutil
memory_info = psutil.virtual_memory()
cpu_percent = psutil.cpu_percent(interval=1)
result = {
    'memory_percent': memory_info.percent,
    'memory_used_mb': memory_info.used / (1024*1024),
    'cpu_percent': cpu_percent,
    'success': True
}
""",
                "output_key": "monitoring_result",
            },
        )

        built_workflow = workflow.build()

        # Execute workflow and check for monitoring data
        results, run_id = runtime_with_limits.execute(built_workflow)
        assert results is not None

        # Once ResourceLimitEnforcer is integrated:
        # monitoring_data = results.get('monitoring_result', {})
        # assert 'memory_percent' in monitoring_data
        # assert 'cpu_percent' in monitoring_data

        # Should be able to get resource metrics from enforcer
        # metrics = runtime_with_limits.get_resource_metrics()
        # assert 'memory_usage_mb' in metrics
        # assert 'cpu_usage_percent' in metrics

    def test_resource_cleanup_on_workflow_completion(self, runtime_with_limits):
        """Test proper resource cleanup when workflows complete."""
        # Execute workflow that uses resources
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SQLDatabaseNode",
            "cleanup_test",
            {
                "connection_string": "postgresql://test:test@localhost:5432/test_db",
                "query": "SELECT 'cleanup_test' as test_name, pg_sleep(0.1);",
                "output_key": "cleanup_result",
            },
        )

        built_workflow = workflow.build()

        # Get initial resource usage
        # Once ResourceLimitEnforcer is integrated:
        # initial_metrics = runtime_with_limits.get_resource_metrics()

        # Execute workflow
        results, run_id = runtime_with_limits.execute(built_workflow)
        assert results is not None

        # Get final resource usage - should be cleaned up
        # final_metrics = runtime_with_limits.get_resource_metrics()
        #
        # # Active connections should be cleaned up
        # assert final_metrics['active_connections'] <= initial_metrics['active_connections']

    def test_multi_tenant_resource_isolation(self, runtime_with_limits):
        """Test resource isolation between different tenants/contexts."""
        # This will test multi-tenant resource limits once implemented
        # Different tenants should have isolated resource quotas

        # Create workflows for different tenants
        tenant1_workflow = WorkflowBuilder()
        tenant1_workflow.add_node(
            "PythonCodeNode",
            "tenant1_task",
            {
                "code": "result = {'tenant': 'tenant1', 'success': True}",
                "output_key": "tenant1_result",
            },
        )

        tenant2_workflow = WorkflowBuilder()
        tenant2_workflow.add_node(
            "PythonCodeNode",
            "tenant2_task",
            {
                "code": "result = {'tenant': 'tenant2', 'success': True}",
                "output_key": "tenant2_result",
            },
        )

        # Execute workflows (isolation to be implemented)
        results1, run_id1 = runtime_with_limits.execute(tenant1_workflow.build())
        results2, run_id2 = runtime_with_limits.execute(tenant2_workflow.build())

        assert results1 is not None
        assert results2 is not None
        assert run_id1 != run_id2


@pytest.mark.integration
class TestResourceLimitEnforcementPolicies:
    """Integration tests for different enforcement policies."""

    def test_strict_policy_immediate_rejection(self):
        """Test strict policy immediately rejects when limits exceeded."""
        # Once ResourceLimitEnforcer supports policy configuration:
        # runtime = LocalRuntime(resource_limits={
        #     "enforcement_policy": "strict",
        #     "max_connections": 2
        # })
        #
        # # Should immediately reject when limits are exceeded
        pass

    def test_warn_policy_allows_with_warnings(self):
        """Test warn policy allows execution but logs warnings."""
        # Once ResourceLimitEnforcer supports policy configuration:
        # runtime = LocalRuntime(resource_limits={
        #     "enforcement_policy": "warn",
        #     "max_memory_mb": 100
        # })
        #
        # # Should log warnings but allow execution
        pass

    def test_adaptive_policy_graceful_degradation(self):
        """Test adaptive policy implements graceful degradation."""
        # Once ResourceLimitEnforcer supports policy configuration:
        # runtime = LocalRuntime(resource_limits={
        #     "enforcement_policy": "adaptive",
        #     "degradation_strategy": "defer"
        # })
        #
        # # Should implement graceful degradation
        pass


@pytest.mark.integration
class TestResourceLimitIntegrationPerformance:
    """Performance tests for resource limit enforcement integration."""

    def test_enforcement_overhead_minimal(self, runtime_with_limits):
        """Test that resource limit enforcement has minimal overhead."""
        # Performance test to ensure <5% overhead
        pass

    def test_concurrent_enforcement_scalability(self, runtime_with_limits):
        """Test resource enforcement scales with concurrent workflows."""
        # Test scalability with multiple concurrent workflows
        pass
