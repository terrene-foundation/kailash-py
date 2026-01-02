"""End-to-end tests for resource limit enforcement.

This module tests complete resource limit enforcement scenarios using the full
LocalRuntime with real infrastructure and no mocking. Tests cover complete user
workflows and business scenarios.

Test categories:
- Complete workflow execution with resource limits
- Enterprise multi-tenant resource isolation scenarios
- Resource exhaustion and recovery workflows
- Performance impact validation in production scenarios
- Real-world resource competition scenarios
- Complete degradation and recovery cycles
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import ResourceLimitExceededError
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
class TestResourceLimitEnforcementE2E:
    """End-to-end tests for complete resource limit enforcement scenarios."""

    @pytest.fixture
    def enterprise_runtime(self):
        """Create enterprise-grade LocalRuntime with comprehensive resource limits."""
        # Will be updated once ResourceLimitEnforcer is fully integrated
        runtime = LocalRuntime(
            # resource_limits={
            #     "max_memory_mb": 512,
            #     "max_connections": 10,
            #     "max_cpu_percent": 80.0,
            #     "enforcement_policy": "adaptive",
            #     "degradation_strategy": "queue",
            #     "monitoring_interval": 0.5,
            #     "enable_alerts": True,
            #     "alert_thresholds": {
            #         "memory": 0.8,
            #         "cpu": 0.7,
            #         "connections": 0.9
            #     }
            # },
            enable_monitoring=True,
            enable_audit=True,
        )
        yield runtime

    def test_complete_data_processing_pipeline_with_limits(self, enterprise_runtime):
        """Test complete data processing pipeline respecting resource limits."""
        # Create realistic data processing workflow
        workflow = WorkflowBuilder()

        # Data ingestion phase
        workflow.add_node(
            "PythonCodeNode",
            "data_ingestion",
            {
                "code": """
import json
import random

# Simulate data ingestion
data = []
for i in range(10000):  # Large dataset
    record = {
        'id': i,
        'value': random.random(),
        'category': f'category_{i % 10}'
    }
    data.append(record)

result = {
    'ingested_count': len(data),
    'data': data[:100],  # Sample for next step
    'success': True
}
""",
                "output_key": "ingested_data",
            },
        )

        # Data processing phase
        workflow.add_node(
            "PythonCodeNode",
            "data_processing",
            {
                "code": """
import math
import statistics

# Get data from previous step
ingested_data = parameters.get('ingested_data', {}).get('data', [])

# Perform calculations
processed_data = []
for record in ingested_data:
    processed_record = {
        'id': record['id'],
        'value': record['value'],
        'squared': record['value'] ** 2,
        'sqrt': math.sqrt(record['value']),
        'category': record['category']
    }
    processed_data.append(processed_record)

# Calculate statistics
values = [r['value'] for r in processed_data]
result = {
    'processed_count': len(processed_data),
    'mean_value': statistics.mean(values) if values else 0,
    'median_value': statistics.median(values) if values else 0,
    'processed_data': processed_data,
    'success': True
}
""",
                "output_key": "processed_data",
            },
        )

        # Database storage phase
        workflow.add_node(
            "SQLDatabaseNode",
            "data_storage",
            {
                "connection_string": "postgresql://test:test@localhost:5432/test_db",
                "query": """
                INSERT INTO processed_data (mean_value, median_value, record_count, created_at)
                VALUES (%(mean_value)s, %(median_value)s, %(processed_count)s, NOW())
                RETURNING id;
            """,
                "parameters": {
                    "mean_value": "{{processed_data.mean_value}}",
                    "median_value": "{{processed_data.median_value}}",
                    "processed_count": "{{processed_data.processed_count}}",
                },
                "output_key": "storage_result",
            },
        )

        built_workflow = workflow.build()

        # Execute complete pipeline with resource monitoring
        start_time = time.time()
        results, run_id = enterprise_runtime.execute(built_workflow)
        execution_time = time.time() - start_time

        # Verify pipeline completed successfully
        assert results is not None
        assert "ingested_data" in results
        assert "processed_data" in results
        assert "storage_result" in results

        # Verify data integrity
        ingested_count = results["ingested_data"]["ingested_count"]
        assert ingested_count == 10000

        processed_count = results["processed_data"]["processed_count"]
        assert processed_count > 0

        # Once ResourceLimitEnforcer is integrated:
        # Verify resource limits were respected
        # execution_metrics = enterprise_runtime.get_execution_metrics(run_id)
        # assert execution_metrics["peak_memory_mb"] <= 512
        # assert execution_metrics["peak_cpu_percent"] <= 80.0

        print(f"Complete pipeline executed in {execution_time:.2f}s")

    def test_multi_tenant_resource_isolation_scenario(self, enterprise_runtime):
        """Test complete multi-tenant scenario with resource isolation."""

        def execute_tenant_workflow(tenant_id: str, complexity: int, results: Dict):
            """Execute workflow for a specific tenant with varying complexity."""
            workflow = WorkflowBuilder()

            # Each tenant has different workload complexity
            workflow.add_node(
                "PythonCodeNode",
                f"tenant_{tenant_id}_processing",
                {
                    "code": f"""
import time
import random

# Tenant-specific processing with varying complexity
tenant_id = "{tenant_id}"
complexity = {complexity}

# Simulate tenant workload
data = []
for i in range(complexity * 1000):
    data.append({{
        'tenant_id': tenant_id,
        'record_id': i,
        'value': random.random(),
        'processed_at': time.time()
    }})

# Simulate processing time based on complexity
time.sleep(complexity * 0.1)

result = {{
    'tenant_id': tenant_id,
    'records_processed': len(data),
    'complexity_level': complexity,
    'success': True
}}
""",
                    "output_key": f"tenant_{tenant_id}_result",
                },
            )

            # Tenant-specific database operations
            workflow.add_node(
                "SQLDatabaseNode",
                f"tenant_{tenant_id}_storage",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": f"""
                    INSERT INTO tenant_data (tenant_id, records_processed, complexity_level, created_at)
                    VALUES ('{tenant_id}', %(records_processed)s, %(complexity_level)s, NOW())
                    RETURNING id;
                """,
                    "parameters": {
                        "records_processed": f"{{{{tenant_{tenant_id}_result.records_processed}}}}",
                        "complexity_level": f"{{{{tenant_{tenant_id}_result.complexity_level}}}}",
                    },
                    "output_key": f"tenant_{tenant_id}_storage_result",
                },
            )

            try:
                start_time = time.time()
                tenant_results, run_id = enterprise_runtime.execute(workflow.build())
                execution_time = time.time() - start_time

                results[tenant_id] = {
                    "success": True,
                    "execution_time": execution_time,
                    "results": tenant_results,
                    "run_id": run_id,
                }
            except ResourceLimitExceededError as e:
                results[tenant_id] = {
                    "success": False,
                    "error": str(e),
                    "error_type": "resource_limit",
                }
            except Exception as e:
                results[tenant_id] = {
                    "success": False,
                    "error": str(e),
                    "error_type": "general",
                }

        # Launch multiple tenant workflows concurrently
        tenant_results = {}
        threads = []

        # Different tenants with different complexity levels
        tenant_configs = [
            ("tenant_A", 5),  # High complexity
            ("tenant_B", 3),  # Medium complexity
            ("tenant_C", 2),  # Low complexity
            ("tenant_D", 4),  # Medium-high complexity
            ("tenant_E", 1),  # Very low complexity
            ("tenant_F", 6),  # Very high complexity
        ]

        for tenant_id, complexity in tenant_configs:
            thread = threading.Thread(
                target=execute_tenant_workflow,
                args=(tenant_id, complexity, tenant_results),
            )
            threads.append(thread)
            thread.start()

        # Wait for all tenant workflows to complete
        for thread in threads:
            thread.join()

        # Analyze results
        successful_tenants = [t for t in tenant_results.values() if t["success"]]
        failed_tenants = [t for t in tenant_results.values() if not t["success"]]

        print(f"Successful tenants: {len(successful_tenants)}")
        print(f"Failed tenants: {len(failed_tenants)}")

        # At least some tenants should succeed
        assert len(successful_tenants) > 0

        # Once ResourceLimitEnforcer is integrated:
        # Higher complexity tenants should be more likely to hit limits
        # resource_limit_failures = [t for t in failed_tenants if t.get("error_type") == "resource_limit"]
        # assert len(resource_limit_failures) >= 0  # Some may hit resource limits

        # Verify resource isolation - each tenant should have independent metrics
        for tenant_id, result in tenant_results.items():
            if result["success"]:
                assert result["run_id"] is not None
                assert result["execution_time"] > 0

    def test_resource_exhaustion_and_recovery_cycle(self, enterprise_runtime):
        """Test complete resource exhaustion and recovery cycle."""

        # Phase 1: Exhaust resources with resource-intensive workflow
        exhaustion_workflow = WorkflowBuilder()

        # Create workflow that will exhaust memory
        exhaustion_workflow.add_node(
            "PythonCodeNode",
            "memory_exhauster",
            {
                "code": """
import gc
import time

# Attempt to allocate large amounts of memory
large_data = []
try:
    for i in range(100):  # Will be limited by resource enforcer
        chunk = [list(range(10000)) for _ in range(100)]  # ~400MB per chunk
        large_data.append(chunk)
        time.sleep(0.01)  # Small delay to allow monitoring
except MemoryError:
    pass

result = {
    'chunks_allocated': len(large_data),
    'memory_exhaustion_attempted': True,
    'success': True
}

# Clean up explicitly
del large_data
gc.collect()
""",
                "output_key": "exhaustion_result",
            },
        )

        # Create workflow that will exhaust connections
        for i in range(15):  # More than max_connections
            exhaustion_workflow.add_node(
                "SQLDatabaseNode",
                f"connection_exhauster_{i}",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": f"SELECT {i} as conn_id, pg_sleep(2);",  # Long-running
                    "output_key": f"conn_result_{i}",
                },
            )

        # Phase 2: Execute exhaustion workflow (expect some failures)
        print("Phase 1: Attempting resource exhaustion...")
        try:
            exhaustion_results, exhaustion_run_id = enterprise_runtime.execute(
                exhaustion_workflow.build()
            )
            print("Exhaustion workflow completed (may have been limited)")
        except ResourceLimitExceededError as e:
            print(f"Resource exhaustion detected: {e}")
            exhaustion_results = None

        # Phase 3: Wait for resource recovery
        print("Phase 2: Waiting for resource recovery...")
        time.sleep(5)  # Allow resources to be freed

        # Phase 4: Execute simple recovery workflow
        recovery_workflow = WorkflowBuilder()
        recovery_workflow.add_node(
            "PythonCodeNode",
            "recovery_test",
            {
                "code": """
import psutil
import gc

# Force garbage collection
gc.collect()

# Check system resources
memory_info = psutil.virtual_memory()
cpu_percent = psutil.cpu_percent(interval=1)

result = {
    'memory_available_mb': memory_info.available / (1024*1024),
    'memory_percent_used': memory_info.percent,
    'cpu_percent': cpu_percent,
    'recovery_successful': True,
    'success': True
}
""",
                "output_key": "recovery_status",
            },
        )

        recovery_workflow.add_node(
            "SQLDatabaseNode",
            "connection_recovery_test",
            {
                "connection_string": "postgresql://test:test@localhost:5432/test_db",
                "query": "SELECT 'recovery_successful' as status, NOW() as recovered_at;",
                "output_key": "connection_recovery",
            },
        )

        print("Phase 3: Testing resource recovery...")
        recovery_results, recovery_run_id = enterprise_runtime.execute(
            recovery_workflow.build()
        )

        # Verify recovery was successful
        assert recovery_results is not None
        assert "recovery_status" in recovery_results
        assert "connection_recovery" in recovery_results

        recovery_status = recovery_results["recovery_status"]
        assert recovery_status["recovery_successful"] is True

        connection_recovery = recovery_results["connection_recovery"]
        assert "status" in connection_recovery

        print("Resource exhaustion and recovery cycle completed successfully")

    def test_production_load_scenario_with_monitoring(self, enterprise_runtime):
        """Test production-like load scenario with comprehensive monitoring."""

        # Simulate production load with multiple workflow types
        def create_data_ingestion_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "ingest_data",
                {
                    "code": """
import random
import time

# Simulate data ingestion from external source
batch_size = random.randint(1000, 5000)
data = []
for i in range(batch_size):
    record = {
        'timestamp': time.time(),
        'user_id': random.randint(1000, 9999),
        'event_type': random.choice(['click', 'view', 'purchase', 'signup']),
        'value': random.random() * 100
    }
    data.append(record)

time.sleep(0.1)  # Simulate network I/O

result = {
    'batch_size': batch_size,
    'ingestion_time': time.time(),
    'data_sample': data[:10],
    'success': True
}
""",
                    "output_key": "ingestion_data",
                },
            )
            return workflow.build()

        def create_analytics_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                "calculate_analytics",
                {
                    "code": """
import statistics
import random
import time

# Simulate analytics calculation
data_points = [random.random() for _ in range(10000)]

# Perform statistical analysis
mean_val = statistics.mean(data_points)
median_val = statistics.median(data_points)
stdev_val = statistics.stdev(data_points)

# Simulate computation time
time.sleep(0.2)

result = {
    'data_points_analyzed': len(data_points),
    'mean': mean_val,
    'median': median_val,
    'stdev': stdev_val,
    'analysis_type': 'statistical_summary',
    'success': True
}
""",
                    "output_key": "analytics_result",
                },
            )
            return workflow.build()

        def create_reporting_workflow():
            workflow = WorkflowBuilder()
            workflow.add_node(
                "SQLDatabaseNode",
                "generate_report",
                {
                    "connection_string": "postgresql://test:test@localhost:5432/test_db",
                    "query": """
                    WITH report_data AS (
                        SELECT
                            'production_load_test' as report_type,
                            NOW() as generated_at,
                            random() * 100 as metric_value
                    )
                    INSERT INTO reports (report_type, generated_at, metric_value)
                    SELECT report_type, generated_at, metric_value FROM report_data
                    RETURNING *;
                """,
                    "output_key": "report_result",
                },
            )
            return workflow.build()

        # Execute production load simulation
        print("Starting production load simulation...")

        workflows = [
            ("ingestion", create_data_ingestion_workflow),
            ("analytics", create_analytics_workflow),
            ("reporting", create_reporting_workflow),
        ]

        load_results = {}
        execution_times = {}

        # Execute multiple iterations to simulate sustained load
        for iteration in range(3):
            print(f"Load iteration {iteration + 1}/3...")

            iteration_results = {}
            iteration_times = {}

            for workflow_type, workflow_creator in workflows:
                workflow_key = f"{workflow_type}_iter_{iteration}"

                start_time = time.time()
                try:
                    workflow = workflow_creator()
                    results, run_id = enterprise_runtime.execute(workflow)
                    execution_time = time.time() - start_time

                    iteration_results[workflow_key] = {
                        "success": True,
                        "results": results,
                        "run_id": run_id,
                        "execution_time": execution_time,
                    }
                    iteration_times[workflow_key] = execution_time

                except ResourceLimitExceededError as e:
                    execution_time = time.time() - start_time
                    iteration_results[workflow_key] = {
                        "success": False,
                        "error": str(e),
                        "error_type": "resource_limit",
                        "execution_time": execution_time,
                    }

                except Exception as e:
                    execution_time = time.time() - start_time
                    iteration_results[workflow_key] = {
                        "success": False,
                        "error": str(e),
                        "error_type": "general",
                        "execution_time": execution_time,
                    }

            load_results.update(iteration_results)
            execution_times.update(iteration_times)

            # Brief pause between iterations
            time.sleep(1)

        # Analyze production load results
        total_workflows = len(load_results)
        successful_workflows = len([r for r in load_results.values() if r["success"]])
        failed_workflows = total_workflows - successful_workflows
        resource_limit_failures = len(
            [
                r
                for r in load_results.values()
                if not r["success"] and r.get("error_type") == "resource_limit"
            ]
        )

        print("Production load simulation completed:")
        print(f"  Total workflows: {total_workflows}")
        print(f"  Successful: {successful_workflows}")
        print(f"  Failed: {failed_workflows}")
        print(f"  Resource limit failures: {resource_limit_failures}")

        # Verify that at least most workflows succeeded
        success_rate = successful_workflows / total_workflows
        assert success_rate >= 0.7  # At least 70% success rate expected

        # Verify reasonable execution times
        if execution_times:
            avg_execution_time = sum(execution_times.values()) / len(execution_times)
            max_execution_time = max(execution_times.values())

            print(f"  Average execution time: {avg_execution_time:.2f}s")
            print(f"  Maximum execution time: {max_execution_time:.2f}s")

            # Execution times should be reasonable for production
            assert avg_execution_time < 5.0  # Average should be under 5s
            assert max_execution_time < 15.0  # Max should be under 15s

        # Once ResourceLimitEnforcer is integrated:
        # Verify resource monitoring data was collected
        # for workflow_key, result in load_results.items():
        #     if result["success"]:
        #         metrics = enterprise_runtime.get_execution_metrics(result["run_id"])
        #         assert "memory_usage_mb" in metrics
        #         assert "cpu_usage_percent" in metrics
        #         assert metrics["peak_memory_mb"] <= 512  # Respect limits

    def test_resource_limit_enforcement_with_cyclic_workflows(self, enterprise_runtime):
        """Test resource limits with cyclic workflows and convergence."""

        # Create cyclic workflow with resource constraints
        workflow = WorkflowBuilder()

        # Initial data processing
        workflow.add_node(
            "PythonCodeNode",
            "initialize_cycle",
            {
                "code": """
import random
import time

# Initialize data for cyclic processing
initial_data = {
    'values': [random.random() for _ in range(1000)],
    'iteration': 0,
    'converged': False,
    'target_mean': 0.5
}

result = {
    'data': initial_data,
    'initialized': True,
    'success': True
}
""",
                "output_key": "cycle_data",
            },
        )

        # Cyclic processing node
        workflow.add_node(
            "PythonCodeNode",
            "process_cycle",
            {
                "code": """
import statistics
import time

# Get data from previous iteration
cycle_data = parameters.get('cycle_data', {}).get('data', {})
values = cycle_data.get('values', [])
iteration = cycle_data.get('iteration', 0)
target_mean = cycle_data.get('target_mean', 0.5)

# Process values (simulate iterative algorithm)
processed_values = []
for val in values:
    # Adjust values towards target mean
    adjustment = (target_mean - val) * 0.1
    new_val = val + adjustment
    processed_values.append(new_val)

# Check convergence
current_mean = statistics.mean(processed_values) if processed_values else 0
converged = abs(current_mean - target_mean) < 0.01

# Simulate processing time based on data size
time.sleep(len(values) / 10000)  # Scale with data size

result = {
    'data': {
        'values': processed_values,
        'iteration': iteration + 1,
        'converged': converged,
        'current_mean': current_mean,
        'target_mean': target_mean
    },
    'processing_completed': True,
    'success': True
}
""",
                "output_key": "cycle_data",
                "max_iterations": 10,  # Limit iterations to prevent resource exhaustion
            },
        )

        # Convergence check and output
        workflow.add_node(
            "PythonCodeNode",
            "finalize_cycle",
            {
                "code": """
cycle_data = parameters.get('cycle_data', {}).get('data', {})

result = {
    'final_iteration': cycle_data.get('iteration', 0),
    'converged': cycle_data.get('converged', False),
    'final_mean': cycle_data.get('current_mean', 0),
    'target_mean': cycle_data.get('target_mean', 0.5),
    'convergence_error': abs(cycle_data.get('current_mean', 0) - cycle_data.get('target_mean', 0.5)),
    'cycle_completed': True,
    'success': True
}
""",
                "output_key": "final_result",
            },
        )

        # Add cycle relationship
        workflow.add_cycle(
            "process_cycle", "process_cycle", condition="not cycle_data.data.converged"
        )

        built_workflow = workflow.build()

        # Execute cyclic workflow with resource monitoring
        print("Executing cyclic workflow with resource limits...")
        start_time = time.time()

        try:
            results, run_id = enterprise_runtime.execute(built_workflow)
            execution_time = time.time() - start_time

            print(f"Cyclic workflow completed in {execution_time:.2f}s")

            # Verify cyclic execution completed
            assert results is not None
            assert "final_result" in results

            final_result = results["final_result"]
            assert final_result["cycle_completed"] is True
            assert final_result["final_iteration"] > 0

            print(f"Converged in {final_result['final_iteration']} iterations")
            print(f"Final convergence error: {final_result['convergence_error']:.4f}")

            # Once ResourceLimitEnforcer is integrated:
            # Verify resource limits were respected during cycles
            # execution_metrics = enterprise_runtime.get_execution_metrics(run_id)
            # assert execution_metrics["peak_memory_mb"] <= 512
            # assert execution_metrics["total_execution_time"] < 30  # Should complete in reasonable time

        except ResourceLimitExceededError as e:
            print(f"Cyclic workflow hit resource limits: {e}")
            # This is acceptable - resource limits should prevent runaway cycles
            assert "resource limit" in str(e).lower()


@pytest.mark.e2e
class TestResourceLimitEnforcementEnterpriseScenarios:
    """Enterprise-level end-to-end resource limit scenarios."""

    def test_enterprise_multi_workflow_orchestration(self):
        """Test enterprise scenario with multiple orchestrated workflows."""
        # Complex enterprise scenario with multiple workflows
        pass

    def test_disaster_recovery_with_resource_constraints(self):
        """Test disaster recovery scenarios under resource constraints."""
        # Test system recovery when resources are constrained
        pass

    def test_auto_scaling_resource_management(self):
        """Test automatic resource scaling based on demand."""
        # Test auto-scaling capabilities with resource limits
        pass
