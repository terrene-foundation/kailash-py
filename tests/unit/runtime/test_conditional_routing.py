"""Test conditional routing functionality in LocalRuntime."""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConditionalRouting:
    """Test that conditional routing works correctly with SwitchNode."""

    def test_switch_node_true_path_only_executes(self):
        """Test that only the true path executes when condition is true."""
        workflow = WorkflowBuilder()

        # Initial data node
        workflow.add_node(
            "PythonCodeNode",
            "check_stage",
            {"code": "result = {'is_initial_stage': True, 'message': 'test'}"},
        )

        # Switch node for conditional routing
        workflow.add_node(
            "SwitchNode",
            "stage_router",
            {"condition_field": "is_initial_stage", "operator": "==", "value": True},
        )

        # TRUE path - should execute
        workflow.add_node(
            "PythonCodeNode",
            "handle_confirmation",
            {"code": "result = {'status': 'confirmation_handled'}"},
        )

        # FALSE path - should NOT execute
        workflow.add_node(
            "PythonCodeNode", "parse_dob", {"code": "result = {'status': 'dob_parsed'}"}
        )

        # Connect the workflow
        workflow.add_connection("check_stage", "result", "stage_router", "input_data")
        workflow.add_connection(
            "stage_router", "true_output", "handle_confirmation", "input"
        )
        workflow.add_connection("stage_router", "false_output", "parse_dob", "input")

        # Execute workflow
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())

        # Verify SwitchNode outputs
        switch_result = results["stage_router"]
        assert switch_result["true_output"] is not None
        assert switch_result["false_output"] is None
        assert switch_result["condition_result"] is True

        # Verify only true path executed
        assert results["handle_confirmation"] is not None
        assert results["parse_dob"] is None  # Should be skipped

        # Verify the correct node ran
        assert (
            results["handle_confirmation"]["result"]["status"] == "confirmation_handled"
        )

    def test_switch_node_false_path_only_executes(self):
        """Test that only the false path executes when condition is false."""
        workflow = WorkflowBuilder()

        # Initial data node
        workflow.add_node(
            "PythonCodeNode",
            "check_stage",
            {"code": "result = {'is_initial_stage': False, 'message': 'test'}"},
        )

        # Switch node for conditional routing
        workflow.add_node(
            "SwitchNode",
            "stage_router",
            {"condition_field": "is_initial_stage", "operator": "==", "value": True},
        )

        # TRUE path - should NOT execute
        workflow.add_node(
            "PythonCodeNode",
            "handle_confirmation",
            {"code": "result = {'status': 'confirmation_handled'}"},
        )

        # FALSE path - should execute
        workflow.add_node(
            "PythonCodeNode", "parse_dob", {"code": "result = {'status': 'dob_parsed'}"}
        )

        # Connect the workflow
        workflow.add_connection("check_stage", "result", "stage_router", "input_data")
        workflow.add_connection(
            "stage_router", "true_output", "handle_confirmation", "input"
        )
        workflow.add_connection("stage_router", "false_output", "parse_dob", "input")

        # Execute workflow
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())

        # Verify SwitchNode outputs
        switch_result = results["stage_router"]
        assert switch_result["true_output"] is None
        assert switch_result["false_output"] is not None
        assert switch_result["condition_result"] is False

        # Verify only false path executed
        assert results["handle_confirmation"] is None  # Should be skipped
        assert results["parse_dob"] is not None

        # Verify the correct node ran
        assert results["parse_dob"]["result"]["status"] == "dob_parsed"

    def test_multi_case_switch_routing(self):
        """Test multi-case conditional routing."""
        workflow = WorkflowBuilder()

        # Initial data node
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {"code": "result = {'priority': 'high', 'task': 'urgent_task'}"},
        )

        # Multi-case switch node
        workflow.add_node(
            "SwitchNode",
            "priority_router",
            {"condition_field": "priority", "cases": ["high", "medium", "low"]},
        )

        # High priority handler
        workflow.add_node(
            "PythonCodeNode",
            "handle_high",
            {"code": "result = {'handled': 'high_priority'}"},
        )

        # Medium priority handler
        workflow.add_node(
            "PythonCodeNode",
            "handle_medium",
            {"code": "result = {'handled': 'medium_priority'}"},
        )

        # Low priority handler
        workflow.add_node(
            "PythonCodeNode",
            "handle_low",
            {"code": "result = {'handled': 'low_priority'}"},
        )

        # Connect the workflow
        workflow.add_connection(
            "data_source", "result", "priority_router", "input_data"
        )
        workflow.add_connection("priority_router", "case_high", "handle_high", "input")
        workflow.add_connection(
            "priority_router", "case_medium", "handle_medium", "input"
        )
        workflow.add_connection("priority_router", "case_low", "handle_low", "input")

        # Execute workflow
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())

        # Verify switch node outputs
        switch_result = results["priority_router"]
        assert switch_result["case_high"] is not None
        assert switch_result["case_medium"] is None
        assert switch_result["case_low"] is None
        assert switch_result["condition_result"] == "high"

        # Verify only high priority handler executed
        assert results["handle_high"] is not None
        assert results["handle_medium"] is None  # Should be skipped
        assert results["handle_low"] is None  # Should be skipped

        # Verify correct handler ran
        assert results["handle_high"]["result"]["handled"] == "high_priority"

    def test_non_conditional_nodes_still_execute(self):
        """Test that nodes not connected to conditional routing still execute normally."""
        workflow = WorkflowBuilder()

        # Source node
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'data': 'test'}"}
        )

        # Normal processing node (not conditional)
        workflow.add_node(
            "PythonCodeNode", "processor", {"code": "result = {'processed': True}"}
        )

        # Conditional routing
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "data", "operator": "==", "value": "test"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "conditional_true",
            {"code": "result = {'conditional': True}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "conditional_false",
            {"code": "result = {'conditional': False}"},
        )

        # Connect workflow
        workflow.add_connection("source", "result", "processor", "input")
        workflow.add_connection("source", "result", "switch", "input_data")
        workflow.add_connection("switch", "true_output", "conditional_true", "input")
        workflow.add_connection("switch", "false_output", "conditional_false", "input")

        # Execute workflow
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())

        # Verify all non-conditional nodes executed
        assert results["source"] is not None
        assert results["processor"] is not None
        assert results["switch"] is not None

        # Verify conditional routing worked
        assert results["conditional_true"] is not None
        assert results["conditional_false"] is None

        # Verify non-conditional processing happened
        assert results["processor"]["result"]["processed"] is True
