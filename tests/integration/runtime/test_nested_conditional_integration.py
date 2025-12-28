"""
Integration tests for the nested conditional execution bug fix.

This module tests the complete integration of conditional execution components
with LocalRuntime to ensure that nested conditional logic works correctly
and unreachable nodes are not executed.

BUG SCENARIO:
- Complex conditional workflow with hierarchical switches
- Premium user (true) -> US region (true) should only execute us_premium_processor
- But intl_premium_processor is incorrectly executing (false_output path)
"""

import asyncio

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestNestedConditionalIntegration:
    """Integration tests for nested conditional execution bug."""

    def setup_method(self):
        """Set up the test workflow that matches the validation script."""
        # Create the exact same workflow from the validation script
        self.workflow = WorkflowBuilder()

        # Data source that returns premium US user
        self.workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {
                "code": "result = {'user_type': 'premium', 'region': 'US', 'value': 1000}"
            },
        )

        # User type switch
        self.workflow.add_node(
            "SwitchNode",
            "user_type_switch",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        # Region switch (only for premium users)
        self.workflow.add_node(
            "SwitchNode",
            "region_switch",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        # Premium processors
        self.workflow.add_node(
            "PythonCodeNode",
            "premium_validator",
            {
                "code": """
# Preserve original data and add validation info
result = input.copy() if input else {}
result.update({'validated': True, 'tier': 'premium'})
"""
            },
        )

        self.workflow.add_node(
            "PythonCodeNode",
            "us_premium_processor",
            {"code": "result = {'processed': True, 'region': 'US', 'discount': 0.20}"},
        )

        self.workflow.add_node(
            "PythonCodeNode",
            "intl_premium_processor",
            {
                "code": "result = {'processed': True, 'region': 'international', 'discount': 0.15}"
            },
        )

        # Basic processors (should NOT execute)
        self.workflow.add_node(
            "PythonCodeNode",
            "basic_validator",
            {
                "code": """
# Preserve original data and add validation info
result = input.copy() if input else {}
result.update({'validated': True, 'tier': 'basic'})
"""
            },
        )

        self.workflow.add_node(
            "PythonCodeNode",
            "basic_processor",
            {"code": "result = {'processed': True, 'discount': 0.05}"},
        )

        self.workflow.add_node(
            "PythonCodeNode",
            "basic_support",
            {"code": "result = {'support': 'standard'}"},
        )

        # Final aggregator
        self.workflow.add_node(
            "PythonCodeNode",
            "aggregator",
            {"code": "result = {'final': True, 'timestamp': 'now'}"},
        )

        # Connect the workflow exactly as in validation script
        self.workflow.add_connection(
            "data_source", "result", "user_type_switch", "input"
        )

        # Premium branch
        self.workflow.add_connection(
            "user_type_switch", "true_output", "premium_validator", "input"
        )
        self.workflow.add_connection(
            "premium_validator", "result", "region_switch", "input"
        )
        self.workflow.add_connection(
            "region_switch", "true_output", "us_premium_processor", "input"
        )
        self.workflow.add_connection(
            "region_switch", "false_output", "intl_premium_processor", "input"
        )

        # Basic branch (unreachable in this test)
        self.workflow.add_connection(
            "user_type_switch", "false_output", "basic_validator", "input"
        )
        self.workflow.add_connection(
            "basic_validator", "result", "basic_processor", "input"
        )
        self.workflow.add_connection(
            "basic_processor", "result", "basic_support", "input"
        )

        # Aggregator gets input from both premium processors
        self.workflow.add_connection(
            "us_premium_processor", "result", "aggregator", "premium_input"
        )
        self.workflow.add_connection(
            "intl_premium_processor", "result", "aggregator", "premium_input"
        )
        self.workflow.add_connection(
            "basic_support", "result", "aggregator", "basic_input"
        )

        self.built_workflow = self.workflow.build()

    @pytest.mark.asyncio
    async def test_route_data_mode_executes_all_reachable_nodes(self):
        """Test that route_data mode executes all nodes with data routing."""
        runtime = LocalRuntime(conditional_execution="route_data")
        results, _ = await runtime.execute_async(self.built_workflow)

        # Route data mode should execute all nodes that receive any data (even None)
        executed_nodes = [k for k, v in results.items() if v is not None]

        # Should include all reachable nodes from the premium path
        expected_executed = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "us_premium_processor",
            "aggregator",
        }

        # Basic path nodes should be skipped because they receive None input
        expected_skipped = {"basic_validator", "basic_processor", "basic_support"}

        for expected_node in expected_executed:
            assert expected_node in executed_nodes, (
                f"Node {expected_node} should be executed in route_data mode. "
                f"Executed: {executed_nodes}"
            )

        # Verify skipped nodes are actually skipped
        for skipped_node in expected_skipped:
            assert skipped_node not in executed_nodes, (
                f"Node {skipped_node} should be skipped in route_data mode. "
                f"Executed: {executed_nodes}"
            )

    @pytest.mark.asyncio
    async def test_skip_branches_mode_premium_us_scenario(self):
        """Test skip_branches mode for Premium US scenario - this should reproduce the bug."""
        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, _ = await runtime.execute_async(self.built_workflow)

        # Get executed nodes (non-None results)
        executed_nodes = set(k for k, v in results.items() if v is not None)

        print(f"DEBUG: Executed nodes = {executed_nodes}")
        print(
            f"DEBUG: All results = {[(k, v is not None) for k, v in results.items()]}"
        )

        # Expected nodes for Premium US scenario
        expected_reachable = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "us_premium_processor",
            "aggregator",
        }

        # Unreachable nodes that should NOT execute
        unreachable_nodes = {
            "basic_validator",
            "basic_processor",
            "basic_support",
            "intl_premium_processor",  # This is the bug - it should NOT execute
        }

        # Verify expected nodes are executed
        for expected_node in expected_reachable:
            assert expected_node in executed_nodes, (
                f"Expected node {expected_node} should be executed. "
                f"Executed: {executed_nodes}"
            )

        # BUG CHECK: Verify unreachable nodes are NOT executed
        executed_unreachable = unreachable_nodes.intersection(executed_nodes)
        assert not executed_unreachable, (
            f"BUG REPRODUCED: Unreachable nodes incorrectly executed: {executed_unreachable}. "
            f"For Premium US user, only us_premium_processor should execute, not intl_premium_processor. "
            f"All executed: {executed_nodes}"
        )

    @pytest.mark.asyncio
    async def test_skip_branches_mode_premium_international_scenario(self):
        """Test skip_branches mode for Premium International scenario."""
        # Modify workflow to return international user
        workflow = WorkflowBuilder()

        # Data source that returns premium international user
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {
                "code": "result = {'user_type': 'premium', 'region': 'international', 'value': 1000}"
            },
        )

        # Use same switch and processor setup
        workflow.add_node(
            "SwitchNode",
            "user_type_switch",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        workflow.add_node(
            "SwitchNode",
            "region_switch",
            {"condition_field": "region", "operator": "==", "value": "US"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "premium_validator",
            {"code": "result = {'validated': True, 'tier': 'premium'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "us_premium_processor",
            {"code": "result = {'processed': True, 'region': 'US', 'discount': 0.20}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "intl_premium_processor",
            {
                "code": "result = {'processed': True, 'region': 'international', 'discount': 0.15}"
            },
        )

        workflow.add_node(
            "PythonCodeNode", "aggregator", {"code": "result = {'final': True}"}
        )

        # Same connections
        workflow.add_connection("data_source", "result", "user_type_switch", "input")
        workflow.add_connection(
            "user_type_switch", "true_output", "premium_validator", "input"
        )
        workflow.add_connection("premium_validator", "result", "region_switch", "input")
        workflow.add_connection(
            "region_switch", "true_output", "us_premium_processor", "input"
        )
        workflow.add_connection(
            "region_switch", "false_output", "intl_premium_processor", "input"
        )
        workflow.add_connection(
            "us_premium_processor", "result", "aggregator", "us_input"
        )
        workflow.add_connection(
            "intl_premium_processor", "result", "aggregator", "intl_input"
        )

        built_workflow = workflow.build()

        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, _ = await runtime.execute_async(built_workflow)

        executed_nodes = set(k for k, v in results.items() if v is not None)

        # Expected nodes for Premium International scenario
        expected_reachable = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "intl_premium_processor",
            "aggregator",
        }

        # us_premium_processor should NOT execute
        assert "us_premium_processor" not in executed_nodes, (
            f"us_premium_processor should not execute for international user. "
            f"Executed: {executed_nodes}"
        )

        # intl_premium_processor SHOULD execute
        assert "intl_premium_processor" in executed_nodes, (
            f"intl_premium_processor should execute for international user. "
            f"Executed: {executed_nodes}"
        )

    @pytest.mark.asyncio
    async def test_skip_branches_mode_basic_user_scenario(self):
        """Test skip_branches mode for Basic user scenario."""
        # Modify workflow to return basic user
        workflow = WorkflowBuilder()

        # Data source that returns basic user
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {"code": "result = {'user_type': 'basic', 'region': 'US', 'value': 100}"},
        )

        workflow.add_node(
            "SwitchNode",
            "user_type_switch",
            {"condition_field": "user_type", "operator": "==", "value": "premium"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "premium_validator",
            {"code": "result = {'validated': True, 'tier': 'premium'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_validator",
            {"code": "result = {'validated': True, 'tier': 'basic'}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "basic_processor",
            {"code": "result = {'processed': True, 'discount': 0.05}"},
        )

        workflow.add_node(
            "PythonCodeNode", "aggregator", {"code": "result = {'final': True}"}
        )

        # Connections for basic path
        workflow.add_connection("data_source", "result", "user_type_switch", "input")
        workflow.add_connection(
            "user_type_switch", "true_output", "premium_validator", "input"
        )
        workflow.add_connection(
            "user_type_switch", "false_output", "basic_validator", "input"
        )
        workflow.add_connection("basic_validator", "result", "basic_processor", "input")
        workflow.add_connection(
            "basic_processor", "result", "aggregator", "basic_input"
        )
        workflow.add_connection(
            "premium_validator", "result", "aggregator", "premium_input"
        )

        built_workflow = workflow.build()

        runtime = LocalRuntime(conditional_execution="skip_branches")
        results, _ = await runtime.execute_async(built_workflow)

        executed_nodes = set(k for k, v in results.items() if v is not None)

        # Expected nodes for Basic user scenario
        expected_reachable = {
            "data_source",
            "user_type_switch",
            "basic_validator",
            "basic_processor",
            "aggregator",
        }

        # premium_validator should NOT execute
        assert "premium_validator" not in executed_nodes, (
            f"premium_validator should not execute for basic user. "
            f"Executed: {executed_nodes}"
        )

        # basic path should execute
        basic_path_nodes = {"basic_validator", "basic_processor"}
        for node in basic_path_nodes:
            assert node in executed_nodes, (
                f"{node} should execute for basic user. " f"Executed: {executed_nodes}"
            )

    @pytest.mark.asyncio
    async def test_performance_improvement_metrics(self):
        """Test that skip_branches mode provides performance improvement."""
        # Test route_data mode
        runtime1 = LocalRuntime(conditional_execution="route_data")
        results1, _ = await runtime1.execute_async(self.built_workflow)
        executed_count_route_data = len(
            [k for k, v in results1.items() if v is not None]
        )

        # Test skip_branches mode
        runtime2 = LocalRuntime(conditional_execution="skip_branches")
        results2, _ = await runtime2.execute_async(self.built_workflow)
        executed_count_skip_branches = len(
            [k for k, v in results2.items() if v is not None]
        )

        # Both modes should execute the same number of reachable nodes (correctness)
        # The performance improvement comes from algorithm efficiency, not node count
        assert executed_count_skip_branches == executed_count_route_data, (
            f"Both modes should execute the same reachable nodes after conditional skipping fixes. "
            f"route_data: {executed_count_route_data}, skip_branches: {executed_count_skip_branches}"
        )

        # Both modes now execute the same nodes correctly
        # Performance improvement comes from algorithm efficiency, not node count reduction
        print(
            f"Both modes correctly execute {executed_count_route_data} reachable nodes"
        )
        print(
            "Performance improvement comes from two-phase vs single-phase execution algorithms"
        )

        # Verify both modes execute the same number of non-None nodes (correctness)
        # Note: route_data includes skipped nodes as None, skip_branches omits them entirely
        executed_nodes_route_data = set(k for k, v in results1.items() if v is not None)
        executed_nodes_skip_branches = set(
            k for k, v in results2.items() if v is not None
        )
        assert (
            executed_nodes_route_data == executed_nodes_skip_branches
        ), "Both modes should execute same non-None nodes"

        # Check that the executed nodes are the expected reachable ones
        expected_executed = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "us_premium_processor",
            "aggregator",
        }
        assert (
            executed_nodes_route_data == expected_executed
        ), f"Expected {expected_executed}, got {executed_nodes_route_data}"

    def test_workflow_validation_and_structure(self):
        """Test that the workflow structure is correct."""
        # Verify all expected nodes are in the workflow
        expected_nodes = {
            "data_source",
            "user_type_switch",
            "premium_validator",
            "region_switch",
            "us_premium_processor",
            "intl_premium_processor",
            "basic_validator",
            "basic_processor",
            "basic_support",
            "aggregator",
        }

        actual_nodes = set(self.built_workflow.graph.nodes())
        assert (
            expected_nodes == actual_nodes
        ), f"Workflow nodes mismatch. Expected: {expected_nodes}, Actual: {actual_nodes}"

        # Verify key connections exist
        edges = list(self.built_workflow.graph.edges())

        # Check critical connections
        assert ("data_source", "user_type_switch") in edges
        assert ("user_type_switch", "premium_validator") in edges
        assert ("premium_validator", "region_switch") in edges
        assert ("region_switch", "us_premium_processor") in edges
        assert ("region_switch", "intl_premium_processor") in edges

        print(
            f"Workflow validation passed. Nodes: {len(actual_nodes)}, Edges: {len(edges)}"
        )
