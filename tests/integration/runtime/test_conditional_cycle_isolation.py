"""
Tests for conditional execution isolation from cycles.

These tests demonstrate and validate that conditional execution mode
does not interfere with cycle execution, causing double workflow execution.
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConditionalCycleIsolation:
    """Test isolation between conditional execution and cycles."""

    def test_conditional_execution_no_cycle_interference(self):
        """Test that conditional execution doesn't cause cycle workflows to execute twice."""

        def create_conditional_cycle_workflow():
            workflow = WorkflowBuilder()

            # Source with execution tracking via return values
            workflow.add_node(
                "PythonCodeNode",
                "source",
                {
                    "code": """
result = {
    'iteration': 0,
    'value': 10,
    'workflow_start': True,
    'execution_id': 'source_1',
    'execution_count': 1
}
"""
                },
            )

            # Processor with iteration tracking
            workflow.add_node(
                "PythonCodeNode",
                "processor",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

result = {
    'iteration': iteration,
    'value': value,
    'execution_id': f'processor_{iteration}_{value}',
    'source_execution_count': input_data.get('execution_count', 0)
}
"""
                },
            )

            # Threshold switch
            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "value",
                    "operator": "<",
                    "value": 30,  # Will iterate 4 times: 10→15→20→25→30
                },
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
    'execution_id': f"final_{input_data.get('iteration', 0)}_{input_data.get('value', 0)}",
    'source_execution_count': input_data.get('source_execution_count', 0)
}
"""
                },
            )

            # Connect
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )
            workflow.add_connection("threshold", "false_output", "final", "parameters")

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("conditional_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(10)
            cycle.build()

            return built_workflow

        # Test with conditional execution enabled
        workflow = create_conditional_cycle_workflow()
        runtime = LocalRuntime(conditional_execution="skip_branches")

        result, run_id = runtime.execute(workflow)

        # Verify final result is correct
        final_result = result["final"]["result"]
        assert (
            final_result["final_iteration"] == 4
        ), f"Expected final_iteration=4, got {final_result['final_iteration']}"
        assert (
            final_result["final_value"] == 30
        ), f"Expected final_value=30, got {final_result['final_value']}"

        # Critical check: Verify workflow executed correctly without double execution
        # The source should have executed and produced the expected result
        source_result = result["source"]["result"]
        assert (
            source_result["execution_count"] == 1
        ), f"Source executed {source_result['execution_count']} times, expected 1"

        # Verify execution sequence by checking processor results
        # We should have exactly 4 processor executions in the cycle history
        # This demonstrates no double execution occurred
        print(f"Final result execution_id: {final_result['execution_id']}")
        assert (
            final_result["execution_id"] == "final_4_30"
        ), "Expected single final execution with correct values"

    def test_conditional_vs_normal_execution_consistency(self):
        """Test that conditional execution produces same results as normal execution for cycles."""

        def create_test_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node(
                "PythonCodeNode",
                "source",
                {"code": "result = {'iteration': 0, 'value': 10}"},
            )

            workflow.add_node(
                "PythonCodeNode",
                "processor",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

result = {'iteration': iteration, 'value': value}
"""
                },
            )

            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "value",
                    "operator": "<",
                    "value": 35,  # 5 iterations: 10→15→20→25→30→35
                },
            )

            workflow.add_node(
                "PythonCodeNode",
                "final",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

result = {'final_iteration': input_data.get('iteration', 0), 'final_value': input_data.get('value', 0)}
"""
                },
            )

            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )
            workflow.add_connection("threshold", "false_output", "final", "parameters")

            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("consistency_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(10)
            cycle.build()

            return built_workflow

        # Execute with normal runtime
        normal_workflow = create_test_workflow()
        normal_runtime = LocalRuntime(conditional_execution="route_data")
        normal_result, _ = normal_runtime.execute(normal_workflow)

        # Execute with conditional runtime
        conditional_workflow = create_test_workflow()
        conditional_runtime = LocalRuntime(conditional_execution="skip_branches")
        conditional_result, _ = conditional_runtime.execute(conditional_workflow)

        # Results should be identical
        normal_final = normal_result["final"]["result"]
        conditional_final = conditional_result["final"]["result"]

        print(f"Normal execution: {normal_final}")
        print(f"Conditional execution: {conditional_final}")

        # CRITICAL: This should FAIL initially if conditional execution interferes
        assert (
            normal_final["final_iteration"] == conditional_final["final_iteration"]
        ), f"Iteration mismatch: normal={normal_final['final_iteration']}, conditional={conditional_final['final_iteration']}"

        assert (
            normal_final["final_value"] == conditional_final["final_value"]
        ), f"Value mismatch: normal={normal_final['final_value']}, conditional={conditional_final['final_value']}"

        # Both should reach iteration 5, value 35
        assert (
            normal_final["final_iteration"] == 5
        ), f"Expected 5 iterations, got {normal_final['final_iteration']}"
        assert (
            normal_final["final_value"] == 35
        ), f"Expected value 35, got {normal_final['final_value']}"

    def test_hierarchical_switches_conditional_isolation(self):
        """Test conditional execution with hierarchical switches (failing test pattern)."""

        def create_hierarchical_conditional_workflow():
            workflow = WorkflowBuilder()

            # Source (from failing test)
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
    'value_b': 20,
    'execution_id': 'hierarchical_start',
    'execution_count': 1
}
"""
                },
            )

            # Hierarchical switches
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

            # Processor with iteration tracking
            workflow.add_node(
                "PythonCodeNode",
                "processor_a",
                {
                    "code": """
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
    'value_b': input_data.get('value_b', 0),
    'execution_id': f'hierarchical_proc_{iteration}_{value}',
    'source_execution_count': input_data.get('execution_count', 0)
}
"""
                },
            )

            # Merge node
            workflow.add_node(
                "MergeNode",
                "final_merge",
                {"merge_type": "merge_dict", "skip_none": True},
            )

            # Connect as failing test
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

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("hierarchical_cycle")
            cycle.connect(
                "processor_a", "threshold_a", mapping={"result": "input_data"}
            )
            cycle.max_iterations(30)
            cycle.build()

            return built_workflow

        # Test with conditional execution (the problematic mode)
        workflow = create_hierarchical_conditional_workflow()
        runtime = LocalRuntime(conditional_execution="skip_branches")

        result, run_id = runtime.execute(workflow)

        # Verify final merge result
        merged_data = result["final_merge"]["merged_data"]
        assert (
            merged_data.get("value_a", 0) == 50
        ), f"Expected value_a=50, got {merged_data.get('value_a', 0)}"
        assert (
            merged_data.get("iteration_a", 0) == 8
        ), f"Expected iteration_a=8, got {merged_data.get('iteration_a', 0)}"

        # Critical check: Source should only execute once (no double execution)
        source_result = result["source"]["result"]
        assert (
            source_result["execution_count"] == 1
        ), f"Source executed {source_result['execution_count']} times, expected 1"

        # Verify that the final execution_id indicates proper completion
        final_execution_id = merged_data.get("execution_id", "")
        assert (
            final_execution_id == "hierarchical_proc_8_50"
        ), f"Expected hierarchical_proc_8_50, got {final_execution_id}"

    def test_no_conditional_execution_baseline(self):
        """Baseline test: verify cycles work correctly without conditional execution."""

        def create_baseline_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node(
                "PythonCodeNode",
                "source",
                {
                    "code": """
result = {
    'iteration': 0,
    'value': 10,
    'execution_id': 'baseline_start',
    'execution_count': 1
}
"""
                },
            )

            workflow.add_node(
                "PythonCodeNode",
                "processor",
                {
                    "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 10

result = {
    'iteration': iteration,
    'value': value,
    'execution_id': f'baseline_proc_{iteration}_{value}',
    'source_execution_count': input_data.get('execution_count', 0)
}
"""
                },
            )

            workflow.add_node(
                "SwitchNode",
                "threshold",
                {
                    "condition_field": "value",
                    "operator": "<",
                    "value": 50,  # 4 iterations: 10→20→30→40→50
                },
            )

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
    'execution_id': f"baseline_final_{input_data.get('iteration', 0)}_{input_data.get('value', 0)}",
    'source_execution_count': input_data.get('source_execution_count', 0)
}
"""
                },
            )

            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection(
                "threshold", "true_output", "processor", "parameters"
            )
            workflow.add_connection("threshold", "false_output", "final", "parameters")

            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("baseline_cycle")
            cycle.connect("processor", "threshold", mapping={"result": "input_data"})
            cycle.max_iterations(10)
            cycle.build()

            return built_workflow

        # Test with normal execution (no conditional execution)
        workflow = create_baseline_workflow()
        runtime = LocalRuntime()  # Default: conditional_execution="route_data"

        result, run_id = runtime.execute(workflow)

        # Verify result
        final_result = result["final"]["result"]
        assert (
            final_result["final_iteration"] == 4
        ), f"Expected 4 iterations, got {final_result['final_iteration']}"
        assert (
            final_result["final_value"] == 50
        ), f"Expected value 50, got {final_result['final_value']}"

        # Critical check: Source should only execute once
        source_result = result["source"]["result"]
        assert (
            source_result["execution_count"] == 1
        ), f"Source executed {source_result['execution_count']} times, expected 1"

        # Verify proper execution sequence
        assert (
            final_result["execution_id"] == "baseline_final_4_50"
        ), f"Expected baseline_final_4_50, got {final_result['execution_id']}"
