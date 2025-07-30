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
        workflow_execution_log = []

        def create_conditional_cycle_workflow():
            workflow = WorkflowBuilder()

            # Source with tracking
            workflow.add_node("PythonCodeNode", "source", {
                "code": f"""
# Track workflow executions
import {__name__}
{__name__}.workflow_execution_log.append("source_executed")

result = {{'iteration': 0, 'value': 10, 'workflow_start': True}}
print(f"[SOURCE] Workflow execution #{{{len({__name__}.workflow_execution_log)}}}")
"""
            })

            # Processor with tracking
            workflow.add_node("PythonCodeNode", "processor", {
                "code": f"""
try:
    input_data = parameters if isinstance(parameters, dict) else {{}}
except NameError:
    input_data = {{}}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

# Track each processor execution
import {__name__}
execution_key = f"processor_{{iteration}}_{{value}}"
{__name__}.workflow_execution_log.append(execution_key)

print(f"[PROCESSOR] iteration={{iteration}}, value={{value}}")

result = {{'iteration': iteration, 'value': value}}
"""
            })

            # Threshold
            workflow.add_node("SwitchNode", "threshold", {
                "condition_field": "value",
                "operator": "<",
                "value": 30  # Will iterate 4 times: 10→15→20→25→30
            })

            # Final processor with tracking
            workflow.add_node("PythonCodeNode", "final", {
                "code": f"""
try:
    input_data = parameters if isinstance(parameters, dict) else {{}}
except NameError:
    input_data = {{}}

# Track final execution
import {__name__}
{__name__}.workflow_execution_log.append(f"final_{{input_data.get('iteration', 0)}}_{{input_data.get('value', 0)}}")

print(f"[FINAL] Final execution with iteration={{input_data.get('iteration', 0)}}, value={{input_data.get('value', 0)}}")

result = {{'final_iteration': input_data.get('iteration', 0), 'final_value': input_data.get('value', 0)}}
"""
            })

            # Connect
            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection("threshold", "true_output", "processor", "parameters")
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

        # Reset log
        workflow_execution_log.clear()
        globals()['workflow_execution_log'] = workflow_execution_log

        result, run_id = runtime.execute(workflow)

        print(f"\nExecution log with conditional_execution='skip_branches': {workflow_execution_log}")

        # Should see single execution sequence, not double
        expected_log = [
            "source_executed",
            "processor_1_15",
            "processor_2_20",
            "processor_3_25",
            "processor_4_30",
            "final_4_30"
        ]

        # CRITICAL: This should FAIL initially due to double execution
        assert workflow_execution_log == expected_log, f"Expected {expected_log}, got {workflow_execution_log}"

        # Verify final result is correct
        final_result = result["final"]["result"]
        assert final_result["final_iteration"] == 4, f"Expected final_iteration=4, got {final_result['final_iteration']}"
        assert final_result["final_value"] == 30, f"Expected final_value=30, got {final_result['final_value']}"

        # Critical check: No duplicate executions
        source_count = workflow_execution_log.count("source_executed")
        assert source_count == 1, f"Source executed {source_count} times, expected 1"

        final_count = len([log for log in workflow_execution_log if log.startswith("final_")])
        assert final_count == 1, f"Final executed {final_count} times, expected 1"

    def test_conditional_vs_normal_execution_consistency(self):
        """Test that conditional execution produces same results as normal execution for cycles."""
        def create_test_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node("PythonCodeNode", "source", {
                "code": "result = {'iteration': 0, 'value': 10}"
            })

            workflow.add_node("PythonCodeNode", "processor", {
                "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 5

result = {'iteration': iteration, 'value': value}
"""
            })

            workflow.add_node("SwitchNode", "threshold", {
                "condition_field": "value",
                "operator": "<",
                "value": 35  # 5 iterations: 10→15→20→25→30→35
            })

            workflow.add_node("PythonCodeNode", "final", {
                "code": """
try:
    input_data = parameters if isinstance(parameters, dict) else {}
except NameError:
    input_data = {}

result = {'final_iteration': input_data.get('iteration', 0), 'final_value': input_data.get('value', 0)}
"""
            })

            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection("threshold", "true_output", "processor", "parameters")
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
        assert normal_final["final_iteration"] == conditional_final["final_iteration"], \
            f"Iteration mismatch: normal={normal_final['final_iteration']}, conditional={conditional_final['final_iteration']}"

        assert normal_final["final_value"] == conditional_final["final_value"], \
            f"Value mismatch: normal={normal_final['final_value']}, conditional={conditional_final['final_value']}"

        # Both should reach iteration 5, value 35
        assert normal_final["final_iteration"] == 5, f"Expected 5 iterations, got {normal_final['final_iteration']}"
        assert normal_final["final_value"] == 35, f"Expected value 35, got {normal_final['final_value']}"

    def test_hierarchical_switches_conditional_isolation(self):
        """Test conditional execution with hierarchical switches (failing test pattern)."""
        hierarchical_execution_log = []

        def create_hierarchical_conditional_workflow():
            workflow = WorkflowBuilder()

            # Source (from failing test)
            workflow.add_node("PythonCodeNode", "source", {
                "code": f"""
# Track hierarchical workflow start
import {__name__}
{__name__}.hierarchical_execution_log.append("hierarchical_start")

result = {{
    'process_a': True,
    'process_b': False,
    'iteration_a': 0,
    'iteration_b': 0,
    'value_a': 10,
    'value_b': 20
}}
"""
            })

            # Hierarchical switches
            workflow.add_node("SwitchNode", "enable_a", {
                "condition_field": "process_a",
                "operator": "==",
                "value": True
            })

            workflow.add_node("SwitchNode", "threshold_a", {
                "condition_field": "value_a",
                "operator": "<",
                "value": 50
            })

            # Processor with tracking
            workflow.add_node("PythonCodeNode", "processor_a", {
                "code": f"""
try:
    input_data = parameters if isinstance(parameters, dict) else {{}}
except NameError:
    input_data = {{}}

iteration = input_data.get('iteration_a', 0) + 1
value = input_data.get('value_a', 0) + 5

# Track execution
import {__name__}
{__name__}.hierarchical_execution_log.append(f"hierarchical_proc_{{iteration}}_{{value}}")

result = {{
    'process_a': True,
    'process_b': input_data.get('process_b', False),
    'iteration_a': iteration,
    'iteration_b': input_data.get('iteration_b', 0),
    'value_a': value,
    'value_b': input_data.get('value_b', 0)
}}
"""
            })

            # Merge node
            workflow.add_node("MergeNode", "final_merge", {
                "merge_type": "merge_dict",
                "skip_none": True
            })

            # Connect as failing test
            workflow.add_connection("source", "result", "enable_a", "input_data")
            workflow.add_connection("enable_a", "true_output", "threshold_a", "input_data")
            workflow.add_connection("threshold_a", "true_output", "processor_a", "parameters")
            workflow.add_connection("source", "result", "final_merge", "data1")
            workflow.add_connection("threshold_a", "false_output", "final_merge", "data2")

            # Create cycle
            built_workflow = workflow.build()
            cycle = built_workflow.create_cycle("hierarchical_cycle")
            cycle.connect("processor_a", "threshold_a", mapping={"result": "input_data"})
            cycle.max_iterations(30)
            cycle.build()

            return built_workflow

        # Test with conditional execution (the problematic mode)
        workflow = create_hierarchical_conditional_workflow()
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Reset log
        hierarchical_execution_log.clear()
        globals()['hierarchical_execution_log'] = hierarchical_execution_log

        result, run_id = runtime.execute(workflow)

        print(f"\nHierarchical execution log: {hierarchical_execution_log}")

        # Should see single start and 8 processor executions (no double execution)
        start_count = hierarchical_execution_log.count("hierarchical_start")
        processor_executions = [log for log in hierarchical_execution_log if log.startswith("hierarchical_proc_")]

        print(f"Start count: {start_count}")
        print(f"Processor executions: {processor_executions}")

        # CRITICAL: This should FAIL initially due to double workflow execution
        assert start_count == 1, f"Workflow started {start_count} times, expected 1"

        # Should have exactly 8 processor executions (iterations 1-8)
        expected_processor_executions = [
            "hierarchical_proc_1_15",
            "hierarchical_proc_2_20",
            "hierarchical_proc_3_25",
            "hierarchical_proc_4_30",
            "hierarchical_proc_5_35",
            "hierarchical_proc_6_40",
            "hierarchical_proc_7_45",
            "hierarchical_proc_8_50"
        ]

        assert processor_executions == expected_processor_executions, \
            f"Expected {expected_processor_executions}, got {processor_executions}"

        # Verify final merge result
        merged_data = result["final_merge"]["merged_data"]
        assert merged_data.get("value_a", 0) == 50, f"Expected value_a=50, got {merged_data.get('value_a', 0)}"
        assert merged_data.get("iteration_a", 0) == 8, f"Expected iteration_a=8, got {merged_data.get('iteration_a', 0)}"

    def test_no_conditional_execution_baseline(self):
        """Baseline test: verify cycles work correctly without conditional execution."""
        baseline_log = []

        def create_baseline_workflow():
            workflow = WorkflowBuilder()

            workflow.add_node("PythonCodeNode", "source", {
                "code": f"""
import {__name__}
{__name__}.baseline_log.append("baseline_start")
result = {{'iteration': 0, 'value': 10}}
"""
            })

            workflow.add_node("PythonCodeNode", "processor", {
                "code": f"""
try:
    input_data = parameters if isinstance(parameters, dict) else {{}}
except NameError:
    input_data = {{}}

iteration = input_data.get('iteration', 0) + 1
value = input_data.get('value', 0) + 10

import {__name__}
{__name__}.baseline_log.append(f"baseline_proc_{{iteration}}_{{value}}")

result = {{'iteration': iteration, 'value': value}}
"""
            })

            workflow.add_node("SwitchNode", "threshold", {
                "condition_field": "value",
                "operator": "<",
                "value": 50  # 4 iterations: 10→20→30→40→50
            })

            workflow.add_node("PythonCodeNode", "final", {
                "code": f"""
try:
    input_data = parameters if isinstance(parameters, dict) else {{}}
except NameError:
    input_data = {{}}

import {__name__}
{__name__}.baseline_log.append(f"baseline_final_{{input_data.get('iteration', 0)}}_{{input_data.get('value', 0)}}")

result = {{'final_iteration': input_data.get('iteration', 0), 'final_value': input_data.get('value', 0)}}
"""
            })

            workflow.add_connection("source", "result", "threshold", "input_data")
            workflow.add_connection("threshold", "true_output", "processor", "parameters")
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

        # Reset log
        baseline_log.clear()
        globals()['baseline_log'] = baseline_log

        result, run_id = runtime.execute(workflow)

        print(f"\nBaseline execution log: {baseline_log}")

        # Should see clean execution pattern
        expected_log = [
            "baseline_start",
            "baseline_proc_1_20",
            "baseline_proc_2_30",
            "baseline_proc_3_40",
            "baseline_proc_4_50",
            "baseline_final_4_50"
        ]

        assert baseline_log == expected_log, f"Expected {expected_log}, got {baseline_log}"

        # Verify result
        final_result = result["final"]["result"]
        assert final_result["final_iteration"] == 4, f"Expected 4 iterations, got {final_result['final_iteration']}"
        assert final_result["final_value"] == 50, f"Expected value 50, got {final_result['final_value']}"
