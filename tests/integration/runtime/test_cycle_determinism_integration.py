"""
Integration tests for deterministic cycle execution behavior.

These tests demonstrate and validate that cycles execute deterministically -
same input should always produce same output with same iteration count.

IMPORTANT: These are Tier 2 INTEGRATION tests that:
- Test full execution pipeline including LocalRuntime + CyclicWorkflowExecutor
- Run in <5 seconds per test
- Use real infrastructure from tests/utils (if needed)
- Test component interactions, not just algorithmic behavior

NO MOCKING is allowed - these tests use real execution components.
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestCycleDeterminismIntegration:
    """Test deterministic behavior of cycle execution through full integration pipeline.

    These are INTEGRATION tests that verify the deterministic behavior of the complete
    cycle execution system including LocalRuntime and CyclicWorkflowExecutor.
    """

    @pytest.mark.integration
    @pytest.mark.timeout(5)  # 5-second timeout for integration tests
    def test_simple_cycle_deterministic_execution(self):
        """Test that a simple cycle executes deterministically."""

        def create_test_workflow():
            workflow = WorkflowBuilder()

            # Source data
            workflow.add_node(
                "PythonCodeNode",
                "source",
                {
                    "code": """
result = {
    'iteration': 0,
    'value': 10
}
"""
                },
            )

            # Increment processor
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

result = {
    'iteration': iteration,
    'value': value
}
"""
                },
            )

            # Threshold check
            workflow.add_node(
                "SwitchNode",
                "threshold",
                {"condition_field": "value", "operator": "<", "value": 50},
            )

            # Final processor
            workflow.add_node(
                "PythonCodeNode",
                "final",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

result = {
    'final_iteration': input_data.get('iteration', 0),
    'final_value': input_data.get('value', 0),
    'status': 'completed'
}
"""
                },
            )

            # Connect workflow
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )
            workflow.add_connection("threshold", "false_output", "final", "parameters")

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("increment_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(20)
            cycle.build()

            return built_workflow

        # Execute the same workflow multiple times
        workflow = create_test_workflow()
        # Disable monitoring to avoid I/O overhead in unit tests
        runtime = LocalRuntime(
            enable_monitoring=False, enable_cycles=True, enable_async=False
        )

        results = []
        iterations = []
        values = []

        for run in range(3):  # Reduce to 3 runs for faster testing
            # No print statements during test execution - they might cause I/O delays
            # Pass None for task_manager to ensure no tracking
            result, run_id = runtime.execute(workflow, task_manager=None)

            final_result = result["final"]["result"]
            final_iteration = final_result["final_iteration"]
            final_value = final_result["final_value"]

            results.append(final_result)
            iterations.append(final_iteration)
            values.append(final_value)

        # All results should be identical (deterministic)
        unique_iterations = set(iterations)
        unique_values = set(values)

        # CRITICAL: This test should FAIL initially, demonstrating non-deterministic behavior
        assert (
            len(unique_iterations) == 1
        ), f"Non-deterministic iteration counts: {iterations}"
        assert len(unique_values) == 1, f"Non-deterministic values: {values}"

        # Verify the expected deterministic behavior
        expected_iteration = 8  # 10→15→20→25→30→35→40→45→50 (8 iterations)
        expected_value = 50  # Final value after 8 iterations

        assert (
            iterations[0] == expected_iteration
        ), f"Expected {expected_iteration} iterations, got {iterations[0]}"
        assert (
            values[0] == expected_value
        ), f"Expected value {expected_value}, got {values[0]}"

    @pytest.mark.integration
    @pytest.mark.timeout(5)  # 5-second timeout for integration tests
    def test_cycle_execution_count_determinism(self):
        """Test that cycle nodes execute exactly once per iteration."""

        def create_counting_workflow():
            workflow = WorkflowBuilder()

            # Source
            workflow.add_node(
                "PythonCodeNode",
                "source",
                {"code": "result = {'iteration': 0, 'value': 10}"},
            )

            # Counting processor - using print statements to track execution
            workflow.add_node(
                "PythonCodeNode",
                "counter",
                {
                    "code": """
# Handle parameters input
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

# Track execution by printing unique execution markers
print(f"EXECUTION_MARKER:counter_{iteration}")

result = {'iteration': iteration, 'value': value}
"""
                },
            )

            # Threshold
            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "value",
                    "operator": "<",
                    "value": 30,  # Will iterate 4 times: 10→15→20→25→30
                },
            )

            # Connect
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection("threshold", "true_output", "counter", "parameters")

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("count_cycle")
            cycle.connect("counter", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(10)
            cycle.build()

            return built_workflow

        workflow = create_counting_workflow()
        # Disable monitoring to avoid I/O overhead in integration tests
        runtime = LocalRuntime(
            enable_monitoring=False, enable_cycles=True, enable_async=False
        )

        # Capture stdout to check execution markers
        import sys
        from io import StringIO

        captured_output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured_output

        try:
            result, run_id = runtime.execute(workflow, task_manager=None)
        finally:
            sys.stdout = old_stdout

        # Parse execution markers from output
        output_lines = captured_output.getvalue().split("\n")
        execution_markers = [
            line for line in output_lines if line.startswith("EXECUTION_MARKER")
        ]

        # Count executions per iteration
        execution_counts = {}
        for marker in execution_markers:
            key = marker.split(":")[
                1
            ]  # Extract "counter_N" from "EXECUTION_MARKER:counter_N"
            execution_counts[key] = execution_counts.get(key, 0) + 1

        print(f"Execution markers found: {execution_markers}")
        print(f"Execution counts: {execution_counts}")

        # Each iteration should execute exactly once
        for key, count in execution_counts.items():
            assert count == 1, f"Node {key} executed {count} times, expected 1"

        # Should have 4 iterations: counter_1, counter_2, counter_3, counter_4
        expected_keys = {"counter_1", "counter_2", "counter_3", "counter_4"}
        actual_keys = set(execution_counts.keys())

        assert (
            actual_keys == expected_keys
        ), f"Expected {expected_keys}, got {actual_keys}"

    @pytest.mark.integration
    @pytest.mark.timeout(5)  # 5-second timeout for integration tests
    def test_hierarchical_switch_cycle_determinism(self):
        """Test deterministic behavior with the actual failing test pattern."""

        def create_hierarchical_workflow():
            workflow = WorkflowBuilder()

            # Data source with multiple parameters (exact pattern from failing test)
            workflow.add_node(
                "PythonCodeNode",
                "source",
                {
                    "code": """
result = {
    'process_a': True,
    'process_b': False,
    'iteration_a': 0,
    'iteration_b': 0,
    'value_a': 10,
    'value_b': 20
}
"""
                },
            )

            # Hierarchical switches for process A
            workflow.add_node(
                "SwitchNode",
                "enable_a",
                {"condition_field": "process_a", "operator": "==", "value": True},
            )

            workflow.add_node(
                "SwitchNode",
                "threshold_a",
                {"condition_field": "value_a", "operator": "<", "value": 50},
            )

            # Processor A with iteration (exact pattern from failing test)
            workflow.add_node(
                "PythonCodeNode",
                "processor_a",
                {
                    "code": """
# Handle parameters input (can be None, dict, or other)
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration_a', 0) + 1
value = input_data.get('value_a', 0) + 5

result = {
    'process_a': True,
    'process_b': input_data.get('process_b', False),
    'iteration_a': iteration,
    'iteration_b': input_data.get('iteration_b', 0),
    'value_a': value,
    'value_b': input_data.get('value_b', 0)
}
"""
                },
            )

            # Final merge
            workflow.add_node(
                "MergeNode",
                "final_merge",
                {"merge_type": "merge_dict", "skip_none": True},
            )

            # Connect exactly as in failing test
            workflow.add_connection("source", "result", "enable_a", "input_data")
            workflow.add_connection(
                "enable_a", "true_output", "threshold_a", "input_data"
            )
            workflow.add_connection(
                "threshold_a", "true_output", "processor_a", "parameters"
            )
            workflow.add_connection("source", "result", "final_merge", "data1")
            workflow.add_connection(
                "threshold_a", "false_output", "final_merge", "data2"
            )

            # Build and create cycle
            built_workflow = workflow.build()
            cycle_a = built_workflow.create_cycle("process_a_cycle")
            cycle_a.connect(
                "processor_a", "threshold_a", mapping={"result": "input_data"}
            )
            cycle_a.max_iterations(30)
            cycle_a.build()

            return built_workflow

        # Execute multiple times to test determinism
        workflow = create_hierarchical_workflow()
        # Disable monitoring to avoid I/O overhead in unit tests
        runtime = LocalRuntime(
            enable_monitoring=False, enable_cycles=True, enable_async=False
        )

        results = []
        for run in range(3):  # Reduce to 3 runs for faster testing
            result, run_id = runtime.execute(workflow, task_manager=None)

            merged_data = result["final_merge"]["merged_data"]
            value_a = merged_data.get("value_a", 0)
            iteration_a = merged_data.get("iteration_a", 0)

            results.append((value_a, iteration_a))

        # Extract values and iterations
        values = [r[0] for r in results]
        iterations = [r[1] for r in results]

        # CRITICAL: This should FAIL initially, showing non-deterministic behavior
        unique_values = set(values)
        unique_iterations = set(iterations)

        assert len(unique_values) == 1, f"Non-deterministic values: {values}"
        assert (
            len(unique_iterations) == 1
        ), f"Non-deterministic iterations: {iterations}"

        # Verify expected behavior (this will establish what the fix should achieve)
        expected_value = 50  # 10→15→20→25→30→35→40→45→50
        expected_iteration = 8  # 8 iterations to reach 50

        assert (
            values[0] == expected_value
        ), f"Expected value_a={expected_value}, got {values[0]}"
        assert (
            iterations[0] == expected_iteration
        ), f"Expected iteration_a={expected_iteration}, got {iterations[0]}"
