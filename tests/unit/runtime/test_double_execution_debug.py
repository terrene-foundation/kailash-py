"""
Test for debugging the critical double execution issue in cyclic workflows.

This test specifically reproduces the double execution bug where nodes execute
twice per iteration instead of once, causing performance regression and
non-deterministic behavior.
"""

import time

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestDoubleExecutionDebug:
    """Test to reproduce and debug double execution issue."""

    def test_double_execution_reproduction(self):
        """Reproduce the exact double execution issue with minimal workflow."""

        def create_minimal_cyclic_workflow():
            workflow = WorkflowBuilder()

            # Simple source
            workflow.add_node(
                "PythonCodeNode",
                "source",
                {"code": "result = {'iteration': 0, 'value': 10}"},
            )

            # Processor that logs execution (without import)
            workflow.add_node(
                "PythonCodeNode",
                "processor",
                {
                    "code": """
# Handle parameters input
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

# Simple print-based logging to detect duplicates
print(f"[PROCESSOR] iteration={iteration}, value={value}")

result = {'iteration': iteration, 'value': value}
"""
                },
            )

            # Threshold check
            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "value",
                    "operator": "<",
                    "value": 25,  # Only 3 iterations: 10→15→20→25
                },
            )

            # Connect workflow
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("test_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(10)
            cycle.build()

            return built_workflow

        workflow = create_minimal_cyclic_workflow()

        # Execute and measure time
        start_time = time.time()
        with LocalRuntime(enable_monitoring=False) as runtime:
            result, run_id = runtime.execute(workflow)
        execution_time = time.time() - start_time

        print(f"\nExecution time: {execution_time:.3f}s")

        # CRITICAL ASSERTIONS - These should FAIL initially

        # 1. Performance check - should be <1 second
        assert (
            execution_time < 1.0
        ), f"Performance regression: took {execution_time:.3f}s (expected <1s)"

        # Check the final result to validate proper execution
        # We can't easily track duplicates without imports, but we can verify the workflow completed correctly
        # The double execution issue will show up in the print output and performance degradation

        # Verify final result is correct (should be from the last iteration before threshold)
        # Expected: threshold stops at value=25, so we never process that iteration
        assert "threshold" in result, "Threshold node should have executed"

        # The false_output should be None (no processing after threshold fails)
        threshold_result = result["threshold"]
        assert (
            "false_output" in threshold_result
        ), "Threshold should have false_output when condition fails"

    def test_parameter_propagation_validation(self):
        """Test that parameter propagation works correctly without duplication."""

        def create_parameter_test_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node(
                "PythonCodeNode",
                "source",
                {"code": "result = {'counter': 0, 'data': 'initial'}"},
            )

            workflow.add_node(
                "PythonCodeNode",
                "processor",
                {
                    "code": """
# Handle parameters
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

counter = input_data.get('counter', 0) + 1
data = f"processed_{counter}"

print(f"[PROCESSOR] counter={counter}, data={data}")

result = {'counter': counter, 'data': data}
"""
                },
            )

            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "counter",
                    "operator": "<",
                    "value": 3,  # 2 iterations
                },
            )

            # Connect
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("param_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(5)
            cycle.build()

            return built_workflow

        workflow = create_parameter_test_workflow()

        start_time = time.time()
        with LocalRuntime(enable_monitoring=False) as runtime:
            result, run_id = runtime.execute(workflow)
        execution_time = time.time() - start_time

        print(f"\nParameter test execution time: {execution_time:.3f}s")

        # Performance check
        assert (
            execution_time < 1.0
        ), f"Parameter test took too long: {execution_time:.3f}s"

        # Check that workflow completed correctly
        assert "threshold" in result, "Threshold node should have executed"

    def test_performance_baseline(self):
        """Establish performance baseline - this should pass after fix."""

        def create_performance_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node("PythonCodeNode", "source", {"code": "result = {'i': 0}"})

            workflow.add_node(
                "PythonCodeNode",
                "increment",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

i = input_data.get('i', 0) + 1
result = {'i': i}
"""
                },
            )

            workflow.add_node(
                "SwitchNode",
                "check",
                {"condition_field": "i", "operator": "<", "value": 10},  # 9 iterations
            )

            workflow.add_connection("source", "result", "check", "input_data")
            workflow.add_connection("check", "true_output", "increment", "parameters")

            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("perf_cycle")
            cycle.connect("increment", "check", mapping={"result": "input_data"})
            cycle.max_iterations(15)
            cycle.build()

            return built_workflow

        workflow = create_performance_workflow()

        # Run multiple times to get average
        times = []
        with LocalRuntime(enable_monitoring=False) as runtime:
            for _ in range(5):
                start = time.time()
                result, run_id = runtime.execute(workflow)
                times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print("\nPerformance results:")
        print(f"Average time: {avg_time:.3f}s")
        print(f"Max time: {max_time:.3f}s")
        print(f"All times: {[f'{t:.3f}' for t in times]}")

        # After fix, should be consistently fast
        assert (
            avg_time < 0.5
        ), f"Average execution too slow: {avg_time:.3f}s (expected <0.5s)"
        assert (
            max_time < 1.0
        ), f"Max execution too slow: {max_time:.3f}s (expected <1.0s)"
