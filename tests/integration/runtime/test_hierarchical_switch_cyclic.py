"""
Integration tests for hierarchical switch execution with cyclic workflows.
"""

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestHierarchicalSwitchWithCycles:
    """Test hierarchical switch execution with cyclic workflows."""

    def test_hierarchical_switches_with_cycle(self):
        """Test that hierarchical switches work with cyclic workflows."""
        workflow = WorkflowBuilder()

        # Initial data source
        workflow.add_node(
            "PythonCodeNode",
            "initializer",
            {
                "code": """
result = {
    'iteration': 0,
    'quality': 0.5,
    'type': 'premium',
    'region': 'US'
}
"""
            },
        )

        # Layer 1: Type check
        workflow.add_node(
            "SwitchNode",
            "type_check",
            {"condition_field": "type", "operator": "==", "value": "premium"},
        )

        # Layer 2: Region check (depends on type)
        workflow.add_node(
            "SwitchNode",
            "region_check",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # Quality improvement processor
        workflow.add_node(
            "PythonCodeNode",
            "quality_improver",
            {
                "code": """
# Handle parameters input (can be None, dict, or other)
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
current_quality = input_data.get('quality', 0.5)
improvement = 0.1

new_quality = min(current_quality + improvement, 1.0)

result = {
    'iteration': iteration,
    'quality': new_quality,
    'type': 'premium',
    'region': 'US',
    'improved': True
}
"""
            },
        )

        # Convergence check
        workflow.add_node(
            "SwitchNode",
            "convergence_check",
            {"condition_field": "quality", "operator": ">=", "value": 0.9},
        )

        # Final processor
        workflow.add_node(
            "PythonCodeNode",
            "final_processor",
            {
                "code": """
# Handle parameters input (can be None, dict, or other)
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

result = {
    'status': 'completed',
    'final_quality': input_data.get('quality', 0),
    'iterations': input_data.get('iteration', 0)
}
"""
            },
        )

        # Connect hierarchical switches
        workflow.add_connection("initializer", "result", "type_check", "input_data")
        workflow.add_connection(
            "type_check", "true_output", "region_check", "input_data"
        )
        workflow.add_connection(
            "region_check", "true_output", "quality_improver", "parameters"
        )
        workflow.add_connection(
            "quality_improver", "result", "convergence_check", "input_data"
        )
        workflow.add_connection(
            "convergence_check", "true_output", "final_processor", "parameters"
        )

        # Create cycle for quality improvement
        built_workflow = workflow.build()
        cycle = built_workflow.create_cycle("quality_improvement_cycle")
        cycle.connect(
            "convergence_check",
            "quality_improver",
            mapping={"false_output": "parameters"},
        )
        cycle.max_iterations(10)
        cycle.build()

        # Execute with hierarchical switch execution
        runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)
        results, run_id = runtime.execute(built_workflow)

        # Verify execution
        assert "final_processor" in results
        assert results["final_processor"]["result"]["status"] == "completed"
        assert results["final_processor"]["result"]["final_quality"] >= 0.9
        assert (
            results["final_processor"]["result"]["iterations"] >= 4
        )  # Should take ~4 iterations to reach 0.9

    def test_multiple_cycles_with_hierarchical_switches(self):
        """Test multiple cycles with hierarchical switch patterns."""
        workflow = WorkflowBuilder()

        # Data source with multiple parameters
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

        # Processor A with iteration
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
            "MergeNode", "final_merge", {"merge_type": "merge_dict", "skip_none": True}
        )

        # Connect initial workflow path
        workflow.add_connection("source", "result", "enable_a", "input_data")
        workflow.add_connection("enable_a", "true_output", "threshold_a", "input_data")

        # Forward connections for conditional routing (outside cycle)
        workflow.add_connection(
            "threshold_a", "true_output", "processor_a", "parameters"
        )  # Initial input
        workflow.add_connection("source", "result", "final_merge", "data1")  # Base data
        workflow.add_connection(
            "threshold_a", "false_output", "final_merge", "data2"
        )  # Cycle output (priority)

        # Build and create cycle (backward flow only, like working example)
        built_workflow = workflow.build()
        cycle_a = built_workflow.create_cycle("process_a_cycle")
        cycle_a.connect(
            "processor_a", "threshold_a", mapping={"result": "input_data"}
        ).max_iterations(
            30
        ).build()  # Sufficient iterations to reach value_a >= 50

        # Execute
        runtime = LocalRuntime()  # No conditional execution needed for this test
        results, run_id = runtime.execute(built_workflow)

        # Verify
        assert "final_merge" in results
        merged_data = results["final_merge"]["merged_data"]

        # Process A should have iterated exactly 8 times to reach value_a=50
        # Starting at 10, incrementing by 5 each iteration: 10→15→20→25→30→35→40→45→50
        # ORIGINAL EXPECTATIONS (DO NOT RELAX THESE!)
        assert (
            merged_data.get("value_a", 0) >= 50
        ), f"Expected value_a >= 50, got {merged_data.get('value_a', 0)}"
        assert (
            merged_data.get("iteration_a", 0) >= 8
        ), f"Expected iteration_a >= 8, got {merged_data.get('iteration_a', 0)}"

        # Process B should not have been processed
        assert merged_data.get("process_b") is False
        assert merged_data.get("iteration_b", 0) == 0

    def test_nested_workflow_with_hierarchical_switches(self):
        """Test hierarchical switches in nested workflows."""
        # Create inner workflow with hierarchical switches
        inner_workflow = WorkflowBuilder()

        inner_workflow.add_node(
            "PythonCodeNode",
            "inner_source",
            {
                "code": "result = {'level': parameters.get('level', 1), 'type': 'nested'}"
            },
        )

        inner_workflow.add_node(
            "SwitchNode",
            "level_check",
            {"condition_field": "level", "operator": ">", "value": 0},
        )

        inner_workflow.add_node(
            "SwitchNode",
            "type_check",
            {"condition_field": "type", "operator": "==", "value": "nested"},
        )

        inner_workflow.add_node(
            "PythonCodeNode",
            "inner_processor",
            {
                "code": "try: input_data = parameters if isinstance(parameters, dict) else {}\nexcept NameError: input_data = {}\nresult = {'processed': True, 'level': input_data.get('level', 1)}"
            },
        )

        inner_workflow.add_connection(
            "inner_source", "result", "level_check", "input_data"
        )
        inner_workflow.add_connection(
            "level_check", "true_output", "type_check", "input_data"
        )
        inner_workflow.add_connection(
            "type_check", "true_output", "inner_processor", "parameters"
        )

        # Create outer workflow
        outer_workflow = WorkflowBuilder()

        outer_workflow.add_node(
            "PythonCodeNode", "outer_source", {"code": "result = {'levels': [1, 2, 3]}"}
        )

        # Add inner workflow as WorkflowNode
        outer_workflow.add_node(
            "WorkflowNode", "nested_processor", {"workflow": inner_workflow.build()}
        )

        outer_workflow.add_connection(
            "outer_source", "result.levels[0]", "nested_processor", "level"
        )

        # Execute
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, run_id = runtime.execute(outer_workflow.build())

        # Verify nested execution worked
        assert "nested_processor" in results
        # The exact structure depends on WorkflowNode implementation

    def test_error_recovery_in_cyclic_hierarchical_workflow(self):
        """Test error recovery when switches fail in cyclic workflows."""
        workflow = WorkflowBuilder()

        # Source that will cause an error after some iterations
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {
                "code": """
# Handle parameters input (can be None, dict, or other)
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0)
if iteration == 3:
    # This will cause the value check to fail
    result = {'iteration': iteration, 'value': 'not_a_number', 'continue': True}
else:
    result = {'iteration': iteration, 'value': iteration * 10, 'continue': True}
"""
            },
        )

        # Hierarchical switches
        workflow.add_node(
            "SwitchNode",
            "continue_check",
            {"condition_field": "continue", "operator": "==", "value": True},
        )

        workflow.add_node(
            "SwitchNode",
            "value_check",
            {
                "condition_field": "value",
                "operator": "<",
                "value": 50,  # This will fail when value is not a number
            },
        )

        # Iterator
        workflow.add_node(
            "PythonCodeNode",
            "iterator",
            {
                "code": """
# Handle parameters input (can be None, dict, or other)
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
result = {'iteration': iteration, 'value': iteration * 10, 'continue': iteration < 5}
"""
            },
        )

        # Connect
        workflow.add_connection("source", "result", "continue_check", "input_data")
        workflow.add_connection(
            "continue_check", "true_output", "value_check", "input_data"
        )
        workflow.add_connection("value_check", "true_output", "iterator", "parameters")

        # Create cycle
        built_workflow = workflow.build()
        cycle = built_workflow.create_cycle("iteration_cycle")
        cycle.connect("iterator", "source", mapping={"result": "parameters"})
        cycle.max_iterations(10)
        cycle.build()

        # Execute - should handle the error gracefully
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, run_id = runtime.execute(built_workflow)

        # The workflow should complete despite the error
        assert len(results) > 0
        # The exact behavior depends on error handling in conditional execution
