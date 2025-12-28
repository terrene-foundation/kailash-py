"""
Shared tests for conditional execution across sync and async runtimes.

These tests ensure that both LocalRuntime and AsyncLocalRuntime implement
conditional execution with identical behavior and features.

This test file addresses the 93% feature gap discovered between LocalRuntime
(16 test files) and AsyncLocalRuntime (0 test files) for conditional execution.
"""

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.workflow.builder import WorkflowBuilder

from .conftest import execute_runtime


class TestSharedConditionalExecutionBasics:
    """Test basic conditional execution behavior in both runtimes."""

    def test_runtime_initialization_default(self, runtime_class):
        """Test runtime initialization with default conditional_execution."""
        runtime = runtime_class()

        # Both runtimes should default to "route_data"
        assert runtime.conditional_execution == "route_data"

    def test_runtime_initialization_skip_branches(self, runtime_class):
        """Test runtime initialization with skip_branches mode."""
        runtime = runtime_class(conditional_execution="skip_branches")

        assert runtime.conditional_execution == "skip_branches"

    def test_runtime_initialization_invalid_mode(self, runtime_class):
        """Test runtime initialization with invalid conditional_execution mode."""
        with pytest.raises(ValueError) as exc_info:
            runtime_class(conditional_execution="invalid_mode")

        assert "conditional_execution" in str(exc_info.value)
        assert "invalid_mode" in str(exc_info.value)

    def test_conditional_execution_parameter_validation(self, runtime_class):
        """Test validation of conditional_execution parameter values."""
        # Valid modes should not raise exceptions
        valid_modes = ["route_data", "skip_branches"]
        for mode in valid_modes:
            runtime = runtime_class(conditional_execution=mode)
            assert runtime.conditional_execution == mode

        # Invalid modes should raise ValueError
        invalid_modes = ["", "invalid", "true", "false"]
        for mode in invalid_modes:
            with pytest.raises(ValueError):
                runtime_class(conditional_execution=mode)


class TestSharedConditionalExecutionSkipBranches:
    """Test skip_branches mode in both runtimes."""

    def test_conditional_execution_skip_branches_mode(self, runtime_class):
        """Test skip_branches mode skips inactive branches."""
        workflow = WorkflowBuilder()

        # Create conditional workflow
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "status", "operator": "==", "value": "active"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "true_branch",
            {"code": "result = {'executed': True, 'branch': 'true'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "false_branch",
            {"code": "result = {'executed': True, 'branch': 'false'}"},
        )

        workflow.add_connection("switch", "true_output", "true_branch", "input")
        workflow.add_connection("switch", "false_output", "false_branch", "input")

        # Execute with skip_branches mode
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"status": "active"}}
        )

        # True branch should execute
        assert "true_branch" in results
        assert results["true_branch"]["executed"] is True

        # False branch should NOT execute (skipped)
        assert "false_branch" not in results

    def test_conditional_execution_skip_branches_false_condition(self, runtime_class):
        """Test skip_branches with false condition skips true branch."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "status", "operator": "==", "value": "active"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "true_branch",
            {"code": "result = {'executed': True, 'branch': 'true'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "false_branch",
            {"code": "result = {'executed': True, 'branch': 'false'}"},
        )

        workflow.add_connection("switch", "true_output", "true_branch", "input")
        workflow.add_connection("switch", "false_output", "false_branch", "input")

        # Execute with skip_branches mode and inactive status
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"status": "inactive"}}
        )

        # True branch should NOT execute (skipped)
        assert "true_branch" not in results

        # False branch should execute
        assert "false_branch" in results
        assert results["false_branch"]["executed"] is True


class TestSharedConditionalExecutionRouteData:
    """Test route_data mode in both runtimes."""

    def test_conditional_execution_route_data_mode(self, runtime_class):
        """Test route_data mode executes all branches (backward compatible)."""
        workflow = WorkflowBuilder()

        # Create conditional workflow
        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "status", "operator": "==", "value": "active"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "true_branch",
            {"code": "result = {'executed': True, 'branch': 'true'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "false_branch",
            {"code": "result = {'executed': True, 'branch': 'false'}"},
        )

        workflow.add_connection("switch", "true_output", "true_branch", "input")
        workflow.add_connection("switch", "false_output", "false_branch", "input")

        # Execute with route_data mode (default)
        runtime = runtime_class(conditional_execution="route_data")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"status": "active"}}
        )

        # Both branches should execute (backward compatible)
        assert "true_branch" in results
        assert "false_branch" in results

    def test_backward_compatibility_default_behavior(self, runtime_class):
        """Test that default behavior is route_data (backward compatible)."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "value", "operator": ">", "value": 50},
        )
        workflow.add_node(
            "PythonCodeNode", "high", {"code": "result = {'category': 'high'}"}
        )
        workflow.add_node(
            "PythonCodeNode", "low", {"code": "result = {'category': 'low'}"}
        )

        workflow.add_connection("switch", "true_output", "high", "input")
        workflow.add_connection("switch", "false_output", "low", "input")

        # Execute with default (no conditional_execution specified)
        runtime = runtime_class()
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"value": 75}}
        )

        # Both branches execute in default mode
        assert "high" in results
        assert "low" in results


class TestSharedNestedConditionalExecution:
    """Test nested conditional execution in both runtimes."""

    def test_nested_conditional_execution(self, runtime_class):
        """Test nested conditionals with skip_branches mode."""
        workflow = WorkflowBuilder()

        # Source node provides the customer data
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'tier': 'premium', 'region': 'US'}"},
        )

        # Level 1 switch
        workflow.add_node(
            "SwitchNode",
            "level1",
            {"condition_field": "tier", "operator": "==", "value": "premium"},
        )

        # Level 2 switches (nested in true branch)
        workflow.add_node(
            "SwitchNode",
            "level2_premium",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # Final processors
        workflow.add_node(
            "PythonCodeNode", "premium_us", {"code": "result = {'path': 'premium_us'}"}
        )
        workflow.add_node(
            "PythonCodeNode", "premium_eu", {"code": "result = {'path': 'premium_eu'}"}
        )
        workflow.add_node(
            "PythonCodeNode", "basic", {"code": "result = {'path': 'basic'}"}
        )

        # Connections
        workflow.add_connection("source", "result", "level1", "input_data")
        workflow.add_connection("level1", "true_output", "level2_premium", "input_data")
        workflow.add_connection("level1", "false_output", "basic", "input")
        workflow.add_connection("level2_premium", "true_output", "premium_us", "input")
        workflow.add_connection("level2_premium", "false_output", "premium_eu", "input")

        # Execute: premium US customer
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={},  # No parameters needed - source provides data
        )

        # Only premium_us path should execute
        assert "premium_us" in results
        assert results["premium_us"]["path"] == "premium_us"

        # Other paths should NOT execute
        assert "premium_eu" not in results
        assert "basic" not in results

    def test_nested_conditional_multiple_levels(self, runtime_class):
        """Test deeply nested conditionals (3 levels)."""
        workflow = WorkflowBuilder()

        # Source node provides the classification data
        workflow.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'type': 'A', 'subtype': 'X', 'variant': '1'}"},
        )

        # Level 1
        workflow.add_node(
            "SwitchNode",
            "level1",
            {"condition_field": "type", "operator": "==", "value": "A"},
        )

        # Level 2
        workflow.add_node(
            "SwitchNode",
            "level2",
            {"condition_field": "subtype", "operator": "==", "value": "X"},
        )

        # Level 3
        workflow.add_node(
            "SwitchNode",
            "level3",
            {"condition_field": "variant", "operator": "==", "value": "1"},
        )

        # Final nodes
        workflow.add_node(
            "PythonCodeNode", "final1", {"code": "result = {'result': 'A-X-1'}"}
        )
        workflow.add_node(
            "PythonCodeNode", "final2", {"code": "result = {'result': 'A-X-2'}"}
        )

        # Connections - data flows through all levels
        workflow.add_connection("source", "result", "level1", "input_data")
        workflow.add_connection("level1", "true_output", "level2", "input_data")
        workflow.add_connection("level2", "true_output", "level3", "input_data")
        workflow.add_connection("level3", "true_output", "final1", "input")
        workflow.add_connection("level3", "false_output", "final2", "input")

        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={},  # No parameters needed - source provides data
        )

        # Only final1 should execute
        assert "final1" in results
        assert results["final1"]["result"] == "A-X-1"
        assert "final2" not in results


class TestSharedConditionalExecutionWithMerge:
    """Test conditional branches with merge points."""

    def test_conditional_execution_with_merge(self, runtime_class):
        """Test conditional branches merging back together."""
        workflow = WorkflowBuilder()

        # Split
        workflow.add_node(
            "SwitchNode",
            "split",
            {"condition_field": "priority", "operator": "==", "value": "high"},
        )

        # Process branches
        workflow.add_node(
            "PythonCodeNode",
            "high_priority",
            {"code": "result = {'processed': True, 'priority': 'high'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "normal_priority",
            {"code": "result = {'processed': True, 'priority': 'normal'}"},
        )

        # Merge
        workflow.add_node("MergeNode", "merge", {})

        # Final step
        workflow.add_node(
            "PythonCodeNode", "finalize", {"code": "result = {'finalized': True}"}
        )

        # Connections
        workflow.add_connection("split", "true_output", "high_priority", "input")
        workflow.add_connection("split", "false_output", "normal_priority", "input")
        workflow.add_connection("high_priority", "result", "merge", "input_high")
        workflow.add_connection("normal_priority", "result", "merge", "input_normal")
        workflow.add_connection("merge", "merged", "finalize", "input")

        # Execute with skip_branches
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"split": {"priority": "high"}}
        )

        # High priority branch should execute
        assert "high_priority" in results

        # Normal priority should NOT execute
        assert "normal_priority" not in results

        # Merge and finalize should execute
        assert "merge" in results
        assert "finalize" in results


class TestSharedConditionalExecutionEdgeCases:
    """Test edge cases for conditional execution."""

    def test_conditional_with_no_connections(self, runtime_class):
        """Test switch node with no downstream connections."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "status", "operator": "==", "value": "active"},
        )

        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"status": "active"}}
        )

        # Switch should execute successfully even without connections
        assert "switch" in results

    def test_conditional_with_multiple_switches(self, runtime_class):
        """Test workflow with multiple independent switches."""
        workflow = WorkflowBuilder()

        # Switch 1
        workflow.add_node(
            "SwitchNode",
            "switch1",
            {"condition_field": "a", "operator": "==", "value": True},
        )
        workflow.add_node(
            "PythonCodeNode", "process1", {"code": "result = {'switch': 1}"}
        )

        # Switch 2
        workflow.add_node(
            "SwitchNode",
            "switch2",
            {"condition_field": "b", "operator": "==", "value": True},
        )
        workflow.add_node(
            "PythonCodeNode", "process2", {"code": "result = {'switch': 2}"}
        )

        workflow.add_connection("switch1", "true_output", "process1", "input")
        workflow.add_connection("switch2", "true_output", "process2", "input")

        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"switch1": {"a": True}, "switch2": {"b": False}},
        )

        # Process1 should execute (switch1 true)
        assert "process1" in results

        # Process2 should NOT execute (switch2 false)
        assert "process2" not in results


@pytest.mark.integration
class TestSharedConditionalExecutionPerformance:
    """Test performance characteristics of conditional execution."""

    def test_skip_branches_performance_benefit(self, runtime_class):
        """
        Test that skip_branches mode provides performance benefit.

        Note: This is a basic test. Actual performance gains depend on
        workflow complexity and node execution time.
        """
        workflow = WorkflowBuilder()

        workflow.add_node(
            "SwitchNode",
            "switch",
            {"condition_field": "path", "operator": "==", "value": "fast"},
        )

        # Fast path
        workflow.add_node(
            "PythonCodeNode", "fast", {"code": "result = {'path': 'fast'}"}
        )

        # Slow path (would be expensive if executed)
        workflow.add_node(
            "PythonCodeNode",
            "slow",
            {
                "code": """
import time
# This would be slow if executed
result = {'path': 'slow'}
"""
            },
        )

        workflow.add_connection("switch", "true_output", "fast", "input")
        workflow.add_connection("switch", "false_output", "slow", "input")

        # With skip_branches, slow path should not execute
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime, workflow.build(), parameters={"switch": {"path": "fast"}}
        )

        # Verify slow path was skipped
        assert "fast" in results
        assert "slow" not in results
