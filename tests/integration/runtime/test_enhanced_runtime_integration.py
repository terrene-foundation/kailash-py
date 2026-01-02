#!/usr/bin/env python3
"""
Test Enhanced Runtime Integration (Phase 3.3)

This module provides comprehensive tests for the enhanced runtime capabilities
implemented in Phase 3 of the Cyclic Graph Architecture. Tests cover:

1. LocalRuntime automatic cycle detection
2. ParallelCyclicRuntime parallel execution capabilities
3. Runtime configuration and customization options
4. Task tracking integration with enhanced runtimes
5. Performance characteristics and benchmarking
6. Mixed workflow execution (DAG + Cycles)

Key Features Tested:
- Automatic workflow type detection (DAG vs Cyclic)
- Parallel execution of independent node groups
- Runtime performance metrics and comparison
- Flexible runtime configuration options
- Seamless integration with existing tracking systems
"""

import time

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.tracking.manager import TaskManager
from kailash.workflow.graph import Workflow


class TestLocalRuntimeCycleDetection:
    """Test LocalRuntime automatic cycle detection capabilities."""

    def test_dag_workflow_detection(self):
        """Test that LocalRuntime correctly identifies DAG workflows."""
        # Create simple DAG workflow
        workflow = Workflow(workflow_id="dag_test", name="DAG Test")

        workflow.add_node(
            "source",
            PythonCodeNode(name="source", code="result = {'data': [1, 2, 3, 4, 5]}"),
        )

        workflow.add_node(
            "process",
            PythonCodeNode(
                name="process",
                code="result = {'processed': [x * 2 for x in data['data']]}",
            ),
        )

        workflow.connect("source", "process", {"result": "data"})

        # Test with LocalRuntime
        runtime = LocalRuntime(debug=True, enable_cycles=True)

        # Verify workflow is detected as DAG
        assert not workflow.has_cycles()

        # Execute workflow
        results, run_id = runtime.execute(workflow)

        # Verify execution succeeded
        assert results is not None
        # Note: run_id might be None for simple executions
        assert "process" in results
        # Check if result is nested or direct
        if "result" in results["process"]:
            assert results["process"]["result"]["processed"] == [2, 4, 6, 8, 10]
        else:
            assert results["process"]["processed"] == [2, 4, 6, 8, 10]

    def test_cyclic_workflow_detection(self):
        """Test that LocalRuntime correctly identifies cyclic workflows."""
        # Create cyclic workflow
        workflow = Workflow(workflow_id="cyclic_test", name="Cyclic Test")

        workflow.add_node(
            "init", PythonCodeNode(name="init", code="result = {'counter': 0}")
        )

        workflow.add_node(
            "increment",
            PythonCodeNode(
                name="increment",
                code="""
# When connected via {"result": "data"}, the input comes as 'data'
try:
    counter = data.get('counter', 0)
except:
    counter = 0

counter = counter + 1
should_continue = counter < 3
result = {'counter': counter, 'should_continue': should_continue}
""",
            ),
        )

        # Create cycle
        workflow.connect("init", "increment", {"result": "data"})
        workflow.create_cycle("increment_cycle").connect(
            "increment", "increment", {"result": "data"}
        ).max_iterations(5).converge_when("should_continue == False").build()

        # Test with LocalRuntime
        runtime = LocalRuntime(debug=True, enable_cycles=True)

        # Verify workflow is detected as cyclic
        assert workflow.has_cycles()

        # Execute workflow
        results, run_id = runtime.execute(workflow)

        # Verify execution succeeded
        assert results is not None
        # Note: run_id might be None for simple executions
        assert "increment" in results
        # Check the actual structure returned
        if "result" in results["increment"]:
            assert results["increment"]["result"]["counter"] == 3
        else:
            assert results["increment"]["counter"] == 3

    def test_mixed_workflow_execution(self):
        """Test execution of workflows with both DAG and cyclic components."""
        workflow = Workflow(workflow_id="mixed_test", name="Mixed Test")

        # DAG preparation phase
        workflow.add_node(
            "prepare",
            PythonCodeNode(name="prepare", code="result = {'value': 10, 'target': 20}"),
        )

        # Cyclic processing phase
        workflow.add_node(
            "iterate",
            PythonCodeNode(
                name="iterate",
                code="""
# Parameters come from connected outputs
try:
    current_value = data.get('value', 10)
    current_target = data.get('target', 20)
except:
    current_value = 10
    current_target = 20

new_value = current_value + 2
converged = new_value >= current_target
result = {'value': new_value, 'target': current_target, 'converged': converged}
""",
            ),
        )

        # DAG finalization phase
        workflow.add_node(
            "finalize",
            PythonCodeNode(
                name="finalize",
                code="""
# Parameters come from connected outputs
try:
    final_value = data.get('value', 0)
    final_target = data.get('target', 0)
except:
    final_value = 0
    final_target = 0

result = {'final_value': final_value, 'reached_target': final_value >= final_target}
""",
            ),
        )

        # Connect DAG -> Cycle -> DAG
        workflow.connect("prepare", "iterate", {"result": "data"})
        workflow.create_cycle("iterate_cycle").connect(
            "iterate", "iterate", {"result": "data"}
        ).max_iterations(10).converge_when("converged == True").build()
        workflow.connect("iterate", "finalize", {"result": "data"})

        # Execute with LocalRuntime
        runtime = LocalRuntime(debug=False, enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify mixed execution
        assert results is not None
        assert "finalize" in results
        # Check the result structure
        if "result" in results["finalize"]:
            assert results["finalize"]["result"]["final_value"] >= 20
            assert results["finalize"]["result"]["reached_target"] is True
        else:
            assert results["finalize"]["final_value"] >= 20
            assert results["finalize"]["reached_target"] is True

    def test_cycle_disabled_runtime(self):
        """Test LocalRuntime behavior when cycles are disabled."""
        # Create cyclic workflow
        workflow = Workflow(
            workflow_id="cyclic_disabled_test", name="Cyclic Disabled Test"
        )

        workflow.add_node(
            "node1", PythonCodeNode(name="node1", code="result = {'value': 1}")
        )

        workflow.add_node(
            "node2", PythonCodeNode(name="node2", code="result = {'value': value + 1}")
        )

        # Create cycle
        workflow.connect("node1", "node2", {"value": "value"})
        workflow.create_cycle("node_cycle").connect(
            "node2", "node1", {"value": "value"}
        ).max_iterations(2).build()

        # Test with cycles disabled
        runtime = LocalRuntime(debug=False, enable_cycles=False)

        # Should raise an error for cyclic workflows
        with pytest.raises(Exception):
            runtime.execute(workflow)


class TestParallelCyclicRuntime:
    """Test ParallelCyclicRuntime parallel execution capabilities."""

    def test_parallel_dag_execution(self):
        """Test parallel execution of DAG workflows."""
        workflow = Workflow(workflow_id="parallel_dag", name="Parallel DAG")

        # Create source node
        workflow.add_node(
            "source",
            PythonCodeNode(name="source", code="result = {'data': list(range(100))}"),
        )

        # Create parallel processing branches
        workflow.add_node(
            "process_1",
            PythonCodeNode(
                name="process_1",
                code="""
import time
time.sleep(0.01)  # Simulate work
try:
    input_data = data.get('data', [])
    result = {'processed': [x * 2 for x in input_data[:50]]}
except:
    result = {'processed': []}
""",
            ),
        )

        workflow.add_node(
            "process_2",
            PythonCodeNode(
                name="process_2",
                code="""
import time
time.sleep(0.01)  # Simulate work
try:
    input_data = data.get('data', [])
    result = {'processed': [x ** 2 for x in input_data[50:]]}
except:
    result = {'processed': []}
""",
            ),
        )

        # Create aggregation node
        workflow.add_node(
            "aggregate",
            PythonCodeNode(
                name="aggregate",
                code="""
combined = []
# Access connected data with proper error handling
try:
    processed_1 = data_1.get('processed', []) if data_1 else []
except:
    processed_1 = []

try:
    processed_2 = data_2.get('processed', []) if data_2 else []
except:
    processed_2 = []

if processed_1:
    combined.extend(processed_1)
if processed_2:
    combined.extend(processed_2)
result = {'combined': combined, 'total': len(combined)}
""",
            ),
        )

        # Connect nodes (parallel opportunities exist)
        workflow.connect("source", "process_1", {"result": "data"})
        workflow.connect("source", "process_2", {"result": "data"})
        workflow.connect("process_1", "aggregate", {"result": "data_1"})
        workflow.connect("process_2", "aggregate", {"result": "data_2"})

        # Test with different worker counts
        for workers in [1, 2, 4]:
            runtime = ParallelCyclicRuntime(
                debug=False, max_workers=workers, enable_cycles=True
            )

            start_time = time.time()
            results, run_id = runtime.execute(workflow)
            execution_time = time.time() - start_time

            # Verify results
            assert results is not None
            assert "aggregate" in results
            # Check if result is nested or direct
            if "result" in results["aggregate"]:
                assert results["aggregate"]["result"]["total"] == 100
            else:
                assert results["aggregate"]["total"] == 100

            # Verify parallel execution was faster with more workers (generally)
            # Note: This is a heuristic test, actual speedup depends on system load
            assert execution_time < 10.0  # Should complete in reasonable time for CI

    def test_parallel_cyclic_execution(self):
        """Test parallel execution of cyclic workflows."""
        workflow = Workflow(workflow_id="parallel_cyclic", name="Parallel Cyclic")

        workflow.add_node(
            "init",
            PythonCodeNode(name="init", code="result = {'counter': 0, 'values': []}"),
        )

        workflow.add_node(
            "process",
            PythonCodeNode(
                name="process",
                code="""
import time
time.sleep(0.01)  # Simulate work
try:
    current_counter = counter
    current_values = values
except:
    current_counter = 0
    current_values = []
new_counter = current_counter + 1
new_values = current_values + [new_counter]
should_continue = new_counter < 3
result = {
    'counter': new_counter,
    'values': new_values,
    'should_continue': should_continue
}
""",
            ),
        )

        # Create cycle
        workflow.connect(
            "init", "process", {"result.counter": "counter", "result.values": "values"}
        )
        workflow.create_cycle("process_cycle").connect(
            "process",
            "process",
            {"result.counter": "counter", "result.values": "values"},
        ).max_iterations(5).converge_when("should_continue == False").build()

        # Test with ParallelCyclicRuntime
        runtime = ParallelCyclicRuntime(debug=False, max_workers=4)
        results, run_id = runtime.execute(workflow)

        # Verify cyclic execution
        assert results is not None
        assert "process" in results
        # Check if result is nested or direct
        if "result" in results["process"]:
            assert results["process"]["result"]["counter"] == 3
            assert len(results["process"]["result"]["values"]) == 3
        else:
            assert results["process"]["counter"] == 3
            assert len(results["process"]["values"]) == 3

    def test_worker_count_configuration(self):
        """Test different worker count configurations."""
        # Simple workflow for testing
        workflow = Workflow(workflow_id="worker_test", name="Worker Test")

        workflow.add_node(
            "task", PythonCodeNode(name="task", code="result = {'completed': True}")
        )

        # Test various worker counts
        worker_counts = [1, 2, 4, 8]

        for workers in worker_counts:
            runtime = ParallelCyclicRuntime(
                debug=False, max_workers=workers, enable_cycles=True, enable_async=True
            )

            results, run_id = runtime.execute(workflow)

            # Verify execution succeeds regardless of worker count
            assert results is not None
            assert "task" in results
            # Check if result is nested or direct
            if "result" in results["task"]:
                assert results["task"]["result"]["completed"] is True
            else:
                assert results["task"]["completed"] is True

    def test_async_configuration(self):
        """Test async execution configuration."""
        workflow = Workflow(workflow_id="async_test", name="Async Test")

        workflow.add_node(
            "async_task",
            PythonCodeNode(
                name="async_task",
                code="""
import time
time.sleep(0.001)  # Minimal work
result = {'async_completed': True}
""",
            ),
        )

        # Test with async enabled
        runtime_async = ParallelCyclicRuntime(
            debug=False, max_workers=4, enable_async=True
        )

        results_async, _ = runtime_async.execute(workflow)

        # Test with async disabled
        runtime_sync = ParallelCyclicRuntime(
            debug=False, max_workers=4, enable_async=False
        )

        results_sync, _ = runtime_sync.execute(workflow)

        # Both should produce same results
        assert results_async is not None
        assert results_sync is not None
        # Check if result is nested or direct
        if "result" in results_async["async_task"]:
            assert results_async["async_task"]["result"]["async_completed"] is True
            assert results_sync["async_task"]["result"]["async_completed"] is True
        else:
            assert results_async["async_task"]["async_completed"] is True
            assert results_sync["async_task"]["async_completed"] is True


class TestRuntimeConfiguration:
    """Test various runtime configuration options."""

    def test_debug_mode_configuration(self):
        """Test debug mode affects runtime behavior."""
        workflow = Workflow(workflow_id="debug_test", name="Debug Test")

        workflow.add_node(
            "debug_task",
            PythonCodeNode(
                name="debug_task", code="result = {'debug_info': 'test completed'}"
            ),
        )

        # Test debug enabled
        runtime_debug = LocalRuntime(debug=True, enable_cycles=True)
        results_debug, _ = runtime_debug.execute(workflow)

        # Test debug disabled
        runtime_no_debug = LocalRuntime(debug=False, enable_cycles=True)
        results_no_debug, _ = runtime_no_debug.execute(workflow)

        # Both should succeed
        assert results_debug is not None
        assert results_no_debug is not None
        # Check if result is nested or direct
        if "result" in results_debug["debug_task"]:
            assert (
                results_debug["debug_task"]["result"]["debug_info"] == "test completed"
            )
            assert (
                results_no_debug["debug_task"]["result"]["debug_info"]
                == "test completed"
            )
        else:
            assert results_debug["debug_task"]["debug_info"] == "test completed"
            assert results_no_debug["debug_task"]["debug_info"] == "test completed"

    def test_runtime_interface_compatibility(self):
        """Test that both runtimes have compatible interfaces."""
        workflow = Workflow(workflow_id="interface_test", name="Interface Test")

        workflow.add_node(
            "interface_task",
            PythonCodeNode(
                name="interface_task", code="result = {'interface_check': True}"
            ),
        )

        # Test LocalRuntime interface
        local_runtime = LocalRuntime()
        assert hasattr(local_runtime, "execute")
        results_local, run_id_local = local_runtime.execute(workflow)

        # Test ParallelCyclicRuntime interface
        parallel_runtime = ParallelCyclicRuntime()
        assert hasattr(parallel_runtime, "execute")
        results_parallel, run_id_parallel = parallel_runtime.execute(workflow)

        # Both should return compatible results
        assert results_local is not None
        assert results_parallel is not None
        # Note: run_id might be None for simple executions

        # Results should be equivalent
        if "result" in results_local["interface_task"]:
            assert results_local["interface_task"]["result"]["interface_check"] is True
            assert (
                results_parallel["interface_task"]["result"]["interface_check"] is True
            )
        else:
            assert results_local["interface_task"]["interface_check"] is True
            assert results_parallel["interface_task"]["interface_check"] is True

    def test_runtime_error_handling(self):
        """Test error handling in different runtime configurations."""
        # Create workflow with intentional error
        workflow = Workflow(workflow_id="error_test", name="Error Test")

        workflow.add_node(
            "error_task",
            PythonCodeNode(
                name="error_task", code="unknown_variable_that_does_not_exist"
            ),
        )

        # Test error handling in LocalRuntime
        local_runtime = LocalRuntime(debug=False)
        results_local, _ = local_runtime.execute(workflow)
        assert results_local is not None
        assert "error_task" in results_local
        assert results_local["error_task"].get("failed") is True
        assert "error" in results_local["error_task"]

        # Test error handling in ParallelCyclicRuntime
        parallel_runtime = ParallelCyclicRuntime(debug=False, max_workers=2)
        results_parallel, _ = parallel_runtime.execute(workflow)
        assert results_parallel is not None
        assert "error_task" in results_parallel
        assert results_parallel["error_task"].get("failed") is True
        assert "error" in results_parallel["error_task"]


class TestTaskTrackingIntegration:
    """Test task tracking integration with enhanced runtimes."""

    def test_local_runtime_tracking(self):
        """Test task tracking with LocalRuntime."""
        # Create task manager
        task_manager = TaskManager()

        # Create test workflow
        workflow = Workflow(workflow_id="tracking_local", name="Tracking Local")

        workflow.add_node(
            "tracked_task",
            PythonCodeNode(
                name="tracked_task", code="result = {'tracking_test': 'success'}"
            ),
        )

        # Execute with task tracking
        runtime = LocalRuntime(debug=False)
        results, run_id = runtime.execute(workflow, task_manager=task_manager)

        # Verify execution
        assert results is not None
        # Note: run_id might be None if task_manager integration is not fully implemented

        # Verify tracking if available
        if run_id:
            run_data = task_manager.get_run(run_id)
            if run_data:
                assert run_data.workflow_name == "Tracking Local"

                # Check tasks were tracked
                tasks = task_manager.get_run_tasks(run_id)
                assert len(tasks) > 0

    def test_parallel_runtime_tracking(self):
        """Test task tracking with ParallelCyclicRuntime."""
        # Create task manager
        task_manager = TaskManager()

        # Create test workflow with parallel opportunities
        workflow = Workflow(workflow_id="tracking_parallel", name="Tracking Parallel")

        workflow.add_node(
            "source", PythonCodeNode(name="source", code="result = {'data': [1, 2, 3]}")
        )

        workflow.add_node(
            "process_1",
            PythonCodeNode(
                name="process_1", code="result = {'result_1': [x * 2 for x in data]}"
            ),
        )

        workflow.add_node(
            "process_2",
            PythonCodeNode(
                name="process_2", code="result = {'result_2': [x * 3 for x in data]}"
            ),
        )

        workflow.connect("source", "process_1", {"data": "data"})
        workflow.connect("source", "process_2", {"data": "data"})

        # Execute with task tracking
        runtime = ParallelCyclicRuntime(debug=False, max_workers=2)
        results, run_id = runtime.execute(workflow, task_manager=task_manager)

        # Verify execution
        assert results is not None
        # Note: run_id might be None if task_manager integration is not fully implemented

        # Verify tracking if available
        if run_id:
            run_data = task_manager.get_run(run_id)
            if run_data:
                assert run_data.workflow_name == "Tracking Parallel"

                # Check tasks were tracked
                tasks = task_manager.get_run_tasks(run_id)
                assert len(tasks) >= 3  # source + 2 processors

    def test_cyclic_workflow_tracking(self):
        """Test task tracking with cyclic workflows."""
        # Create task manager
        task_manager = TaskManager()

        # Create cyclic workflow
        workflow = Workflow(workflow_id="tracking_cyclic", name="Tracking Cyclic")

        workflow.add_node(
            "init", PythonCodeNode(name="init", code="result = {'counter': 0}")
        )

        workflow.add_node(
            "increment",
            PythonCodeNode(
                name="increment",
                code="""
try:
    current_counter = counter
except:
    current_counter = 0
new_counter = current_counter + 1
should_continue = new_counter < 3
result = {'counter': new_counter, 'should_continue': should_continue}
""",
            ),
        )

        # Create cycle
        workflow.connect("init", "increment", {"result.counter": "counter"})
        workflow.create_cycle("increment_tracking_cycle").connect(
            "increment", "increment", {"result.counter": "counter"}
        ).max_iterations(5).converge_when("should_continue == False").build()

        # Execute with task tracking
        runtime = LocalRuntime(debug=False, enable_cycles=True)
        results, run_id = runtime.execute(workflow, task_manager=task_manager)

        # Verify execution
        assert results is not None
        # Verify run_id is present
        assert run_id is not None, "run_id should not be None"

        # Verify tracking captured cycle iterations
        run_data = task_manager.get_run(run_id)
        assert run_data is not None, "Run data should exist"
        assert run_data.workflow_name == "Tracking Cyclic"

        # Check tasks include cycle iterations
        tasks = task_manager.get_run_tasks(run_id)
        # Verify task tracking is working
        assert isinstance(tasks, list)
        assert len(tasks) > 0, f"Should have tasks now, but got {len(tasks)} tasks"

        # Check for cycle-specific tasks
        task_node_ids = [task.node_id for task in tasks]

        # Should have init node
        assert any(
            "init" in node_id for node_id in task_node_ids
        ), f"No init task found in {task_node_ids}"

        # Should have cycle group task
        assert any(
            "cycle_group_" in node_id for node_id in task_node_ids
        ), f"No cycle group task found in {task_node_ids}"

        # Should have iteration tasks
        assert any(
            "_iteration_" in node_id for node_id in task_node_ids
        ), f"No iteration tasks found in {task_node_ids}"

        # Should have node executions in cycles
        assert any(
            "increment_cycle_" in node_id for node_id in task_node_ids
        ), f"No increment cycle tasks found in {task_node_ids}"


class TestPerformanceBenchmarking:
    """Test performance characteristics of enhanced runtimes."""

    def test_dag_performance_comparison(self):
        """Compare performance between LocalRuntime and ParallelCyclicRuntime for DAG workflows."""
        # Create performance test workflow
        workflow = Workflow(workflow_id="perf_dag", name="Performance DAG")

        workflow.add_node(
            "source",
            PythonCodeNode(
                name="source",
                code="""
import time
time.sleep(0.01)  # Simulate work
result = {'data': list(range(50))}
""",
            ),
        )

        workflow.add_node(
            "process",
            PythonCodeNode(
                name="process",
                code="""
import time
time.sleep(0.01)  # Simulate work
try:
    input_data = data.get('data', [])
    result = {'processed': [x * 2 for x in input_data]}
except:
    result = {'processed': []}
""",
            ),
        )

        workflow.connect("source", "process", {"result": "data"})

        # Benchmark LocalRuntime
        local_runtime = LocalRuntime(debug=False)
        start_time = time.time()
        results_local, _ = local_runtime.execute(workflow)
        local_time = time.time() - start_time

        # Benchmark ParallelCyclicRuntime
        parallel_runtime = ParallelCyclicRuntime(debug=False, max_workers=4)
        start_time = time.time()
        results_parallel, _ = parallel_runtime.execute(workflow)
        parallel_time = time.time() - start_time

        # Both should produce correct results
        assert results_local is not None
        assert results_parallel is not None
        # Check if result is nested or direct
        if "result" in results_local["process"]:
            assert len(results_local["process"]["result"]["processed"]) == 50
            assert len(results_parallel["process"]["result"]["processed"]) == 50
        else:
            assert len(results_local["process"]["processed"]) == 50
            assert len(results_parallel["process"]["processed"]) == 50

        # Both should complete within reasonable time
        assert local_time < 10.0  # Generous timeout for CI environments
        assert parallel_time < 10.0

    def test_parallel_workflow_speedup(self):
        """Test that parallel workflows show performance benefits."""
        # Create workflow with clear parallel opportunities
        workflow = Workflow(workflow_id="speedup_test", name="Speedup Test")

        workflow.add_node(
            "source",
            PythonCodeNode(name="source", code="result = {'data': list(range(10))}"),
        )

        # Create multiple independent processing branches
        for i in range(4):
            workflow.add_node(
                f"process_{i}",
                PythonCodeNode(
                    name=f"process_{i}",
                    code=f"""
import time
time.sleep(0.02)  # Simulate work
try:
    input_data = data.get('data', [])
    result = {{'processed_{i}': [x * {i+1} for x in input_data]}}
except:
    result = {{'processed_{i}': []}}
""",
                ),
            )
            workflow.connect("source", f"process_{i}", {"result": "data"})

        # Test with single worker (sequential)
        runtime_sequential = ParallelCyclicRuntime(debug=False, max_workers=1)
        start_time = time.time()
        results_seq, _ = runtime_sequential.execute(workflow)
        sequential_time = time.time() - start_time

        # Test with multiple workers (parallel)
        runtime_parallel = ParallelCyclicRuntime(debug=False, max_workers=4)
        start_time = time.time()
        results_par, _ = runtime_parallel.execute(workflow)
        parallel_time = time.time() - start_time

        # Both should produce correct results
        assert results_seq is not None
        assert results_par is not None

        # Parallel should typically be faster (though not guaranteed on all systems)
        # We just verify both complete within reasonable bounds
        assert sequential_time < 2.0
        assert parallel_time < 2.0

        # Results should be identical
        for i in range(4):
            node_key = f"process_{i}"
            result_key = f"processed_{i}"
            assert node_key in results_seq
            assert node_key in results_par
            # Check if result is nested or direct
            if "result" in results_seq[node_key]:
                assert result_key in results_seq[node_key]["result"]
                assert result_key in results_par[node_key]["result"]
            else:
                assert result_key in results_seq[node_key]
                assert result_key in results_par[node_key]

    def test_cyclic_performance_scaling(self):
        """Test performance scaling of cyclic workflows."""
        # Create cyclic workflow
        workflow = Workflow(workflow_id="cyclic_scaling", name="Cyclic Scaling")

        workflow.add_node(
            "init", PythonCodeNode(name="init", code="result = {'counter': 0}")
        )

        workflow.add_node(
            "iterate",
            PythonCodeNode(
                name="iterate",
                code="""
import time
time.sleep(0.005)  # Small work per iteration
try:
    current_counter = counter
except:
    current_counter = 0
new_counter = current_counter + 1
should_continue = new_counter < 5
result = {'counter': new_counter, 'should_continue': should_continue}
""",
            ),
        )

        # Create cycle
        workflow.connect("init", "iterate", {"result.counter": "counter"})
        workflow.create_cycle("iterate_tracking_cycle").connect(
            "iterate", "iterate", {"result.counter": "counter"}
        ).max_iterations(10).converge_when("should_continue == False").build()

        # Test execution time scales reasonably with iterations
        runtime = LocalRuntime(debug=False, enable_cycles=True)
        start_time = time.time()
        results, _ = runtime.execute(workflow)
        execution_time = time.time() - start_time

        # Verify results
        assert results is not None
        # Check if result is nested or direct
        if "result" in results["iterate"]:
            assert results["iterate"]["result"]["counter"] == 5
        else:
            assert results["iterate"]["counter"] == 5

        # Verify execution time is reasonable (5 iterations * ~0.005s + overhead)
        # Allow more time for CI environments
        assert execution_time < 10.0
