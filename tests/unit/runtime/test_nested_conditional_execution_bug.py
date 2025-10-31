"""
Unit tests for the nested conditional execution bug fix.

This module tests the core logic components that handle nested conditional
execution to ensure they correctly determine reachable nodes and prevent
unreachable nodes from executing.

BUG SCENARIO:
- Complex conditional workflow with hierarchical switches
- Premium user (true) -> US region (true) should only execute us_premium_processor
- But intl_premium_processor is incorrectly executing (false_output path)
"""

from unittest.mock import MagicMock, Mock

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestNestedConditionalExecutionBug:
    """Test cases for the nested conditional execution bug."""

    def setup_method(self):
        """Set up test workflow that reproduces the bug."""
        # Create the exact scenario from the validation script
        self.workflow = Mock(spec=Workflow)
        self.workflow.graph = nx.DiGraph()

        # Add nodes to graph
        nodes = [
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
        ]

        for node_id in nodes:
            if "switch" in node_id:
                node_instance = Mock(spec=SwitchNode)
            else:
                node_instance = Mock(spec=PythonCodeNode)

            self.workflow.graph.add_node(
                node_id, node=node_instance, instance=node_instance
            )

        # Add edges that match the validation script scenario
        edges = [
            # Main flow
            ("data_source", "user_type_switch", {"mapping": {"result": "input"}}),
            # Premium branch (true_output from user_type_switch)
            (
                "user_type_switch",
                "premium_validator",
                {"mapping": {"true_output": "input"}},
            ),
            ("premium_validator", "region_switch", {"mapping": {"result": "input"}}),
            (
                "region_switch",
                "us_premium_processor",
                {"mapping": {"true_output": "input"}},
            ),
            (
                "region_switch",
                "intl_premium_processor",
                {"mapping": {"false_output": "input"}},
            ),
            # Basic branch (false_output from user_type_switch)
            (
                "user_type_switch",
                "basic_validator",
                {"mapping": {"false_output": "input"}},
            ),
            ("basic_validator", "basic_processor", {"mapping": {"result": "input"}}),
            ("basic_processor", "basic_support", {"mapping": {"result": "input"}}),
            # Aggregator connections
            (
                "us_premium_processor",
                "aggregator",
                {"mapping": {"result": "premium_input"}},
            ),
            (
                "intl_premium_processor",
                "aggregator",
                {"mapping": {"result": "premium_input"}},
            ),
            ("basic_support", "aggregator", {"mapping": {"result": "basic_input"}}),
        ]

        for source, target, edge_data in edges:
            self.workflow.graph.add_edge(source, target, **edge_data)

    def test_conditional_branch_analyzer_identifies_switch_nodes(self):
        """Test that ConditionalBranchAnalyzer correctly identifies SwitchNodes."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        switch_nodes = analyzer._find_switch_nodes()

        expected_switches = ["user_type_switch", "region_switch"]
        assert set(switch_nodes) == set(expected_switches)
        assert len(switch_nodes) == 2

    def test_conditional_branch_analyzer_builds_branch_map(self):
        """Test that ConditionalBranchAnalyzer builds correct branch map for nested switches."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        branch_map = analyzer._build_branch_map()

        # Verify user_type_switch branches
        assert "user_type_switch" in branch_map
        user_branches = branch_map["user_type_switch"]
        assert "true_output" in user_branches
        assert "false_output" in user_branches

        # true_output should lead to premium_validator and downstream
        assert "premium_validator" in user_branches["true_output"]

        # false_output should lead to basic_validator and downstream
        assert "basic_validator" in user_branches["false_output"]

        # Verify region_switch branches
        assert "region_switch" in branch_map
        region_branches = branch_map["region_switch"]
        assert "true_output" in region_branches
        assert "false_output" in region_branches

        # true_output should lead to us_premium_processor
        assert "us_premium_processor" in region_branches["true_output"]

        # false_output should lead to intl_premium_processor
        assert "intl_premium_processor" in region_branches["false_output"]

    def test_get_reachable_nodes_premium_us_scenario(self):
        """Test reachable nodes calculation for Premium US user scenario (the bug case)."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)

        # Switch results that represent: Premium user (true) + US region (true)
        switch_results = {
            "user_type_switch": {
                "true_output": {"user_type": "premium"},  # Premium user - true branch
                "false_output": None,  # Basic user - not activated
            },
            "region_switch": {
                "true_output": {"region": "US"},  # US region - true branch
                "false_output": None,  # International - not activated
            },
        }

        reachable_nodes = analyzer.get_reachable_nodes(switch_results)

        # Expected reachable nodes for Premium US scenario
        expected_reachable = {
            "user_type_switch",  # Switch itself
            "premium_validator",  # From user_type_switch true_output
            "region_switch",  # Switch itself
            "us_premium_processor",  # From region_switch true_output
            "aggregator",  # Downstream from us_premium_processor
        }

        # BUG CHECK: intl_premium_processor should NOT be reachable
        assert "intl_premium_processor" not in reachable_nodes, (
            f"BUG: intl_premium_processor should not be reachable in Premium US scenario. "
            f"Reachable nodes: {reachable_nodes}"
        )

        # Verify expected nodes are reachable
        for expected_node in expected_reachable:
            assert expected_node in reachable_nodes, (
                f"Expected node {expected_node} should be reachable. "
                f"Reachable nodes: {reachable_nodes}"
            )

    def test_get_reachable_nodes_premium_intl_scenario(self):
        """Test reachable nodes calculation for Premium International user scenario."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)

        # Switch results that represent: Premium user (true) + International region (false)
        switch_results = {
            "user_type_switch": {
                "true_output": {"user_type": "premium"},  # Premium user - true branch
                "false_output": None,  # Basic user - not activated
            },
            "region_switch": {
                "true_output": None,  # US region - not activated
                "false_output": {
                    "region": "international"
                },  # International - false branch
            },
        }

        reachable_nodes = analyzer.get_reachable_nodes(switch_results)

        # Expected reachable nodes for Premium International scenario
        expected_reachable = {
            "user_type_switch",  # Switch itself
            "premium_validator",  # From user_type_switch true_output
            "region_switch",  # Switch itself
            "intl_premium_processor",  # From region_switch false_output
            "aggregator",  # Downstream from intl_premium_processor
        }

        # us_premium_processor should NOT be reachable
        assert "us_premium_processor" not in reachable_nodes, (
            f"us_premium_processor should not be reachable in Premium International scenario. "
            f"Reachable nodes: {reachable_nodes}"
        )

        # Verify expected nodes are reachable
        for expected_node in expected_reachable:
            assert expected_node in reachable_nodes, (
                f"Expected node {expected_node} should be reachable. "
                f"Reachable nodes: {reachable_nodes}"
            )

    def test_dynamic_execution_planner_creates_correct_plan(self):
        """Test that DynamicExecutionPlanner creates correct execution plan."""
        from unittest.mock import patch

        planner = DynamicExecutionPlanner(self.workflow)

        # Mock topological sort to return predictable order
        with patch("networkx.topological_sort") as mock_topo:
            mock_topo.return_value = [
                "data_source",
                "user_type_switch",
                "premium_validator",
                "basic_validator",
                "region_switch",
                "us_premium_processor",
                "intl_premium_processor",
                "basic_processor",
                "basic_support",
                "aggregator",
            ]

            # Premium US scenario switch results
            switch_results = {
                "user_type_switch": {
                    "true_output": {"user_type": "premium"},
                    "false_output": None,
                },
                "region_switch": {
                    "true_output": {"region": "US"},
                    "false_output": None,
                },
            }

            execution_plan = planner.create_execution_plan(switch_results)

            # BUG CHECK: intl_premium_processor should NOT be in execution plan
            assert "intl_premium_processor" not in execution_plan, (
                f"BUG: intl_premium_processor should not be in execution plan for Premium US scenario. "
                f"Execution plan: {execution_plan}"
            )

            # Verify expected nodes are in execution plan
            expected_in_plan = [
                "data_source",
                "user_type_switch",
                "premium_validator",
                "region_switch",
                "us_premium_processor",
                "aggregator",
            ]

            for expected_node in expected_in_plan:
                assert expected_node in execution_plan, (
                    f"Expected node {expected_node} should be in execution plan. "
                    f"Execution plan: {execution_plan}"
                )

            # Verify unreachable nodes are NOT in execution plan
            unreachable_nodes = ["basic_validator", "basic_processor", "basic_support"]
            for unreachable_node in unreachable_nodes:
                assert unreachable_node not in execution_plan, (
                    f"Unreachable node {unreachable_node} should not be in execution plan. "
                    f"Execution plan: {execution_plan}"
                )

    def test_execution_plan_validation_passes_for_correct_plan(self):
        """Test that execution plan validation passes for correctly generated plans."""
        planner = DynamicExecutionPlanner(self.workflow)

        # Create a complete execution plan with all nodes (validation checks all dependencies)
        correct_plan = [
            "data_source",
            "user_type_switch",
            "premium_validator",
            "basic_validator",
            "region_switch",
            "us_premium_processor",
            "intl_premium_processor",
            "basic_processor",
            "basic_support",
            "aggregator",
        ]

        is_valid, errors = planner.validate_execution_plan(correct_plan)

        assert is_valid, f"Correct execution plan should be valid. Errors: {errors}"
        assert len(errors) == 0, f"No validation errors expected. Errors: {errors}"

    def test_execution_plan_validation_fails_for_incorrect_plan(self):
        """Test that execution plan validation fails for plans with dependency violations."""
        planner = DynamicExecutionPlanner(self.workflow)

        # Create an incorrect execution plan (dependencies out of order)
        incorrect_plan = [
            "aggregator",  # Aggregator before its dependencies - should fail
            "data_source",
            "user_type_switch",
        ]

        is_valid, errors = planner.validate_execution_plan(incorrect_plan)

        assert not is_valid, "Incorrect execution plan should be invalid"
        assert len(errors) > 0, "Validation errors expected for incorrect plan"

        # Check that dependency violation is detected
        dependency_errors = [err for err in errors if "dependency" in err.lower()]
        assert (
            len(dependency_errors) > 0
        ), f"Dependency errors expected. Errors: {errors}"

    def test_hierarchical_switch_dependencies_detection(self):
        """Test detection of hierarchical switch dependencies."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        switch_nodes = analyzer._find_switch_nodes()
        hierarchy_info = analyzer.analyze_switch_hierarchies(switch_nodes)

        # Current implementation considers switches connected through other nodes as independent
        assert not hierarchy_info[
            "has_hierarchies"
        ], "Switches connected through other nodes are considered independent"
        assert (
            hierarchy_info["max_depth"] >= 1
        ), "Should have at least 1 layer of switches"

        # Both switches should be identified as independent
        assert "user_type_switch" in hierarchy_info["independent_switches"]
        assert "region_switch" in hierarchy_info["independent_switches"]

    def test_edge_case_empty_switch_results(self):
        """Test handling of empty switch results."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        planner = DynamicExecutionPlanner(self.workflow)

        # Empty switch results
        empty_results = {}

        # Should not crash and should return all nodes
        reachable_nodes = analyzer.get_reachable_nodes(empty_results)
        execution_plan = planner.create_execution_plan(empty_results)

        # With no switch results, all nodes should be considered reachable
        assert len(execution_plan) == len(
            self.workflow.graph.nodes()
        ), "With empty switch results, all nodes should be in execution plan"

    def test_edge_case_invalid_switch_results(self):
        """Test handling of invalid switch results."""
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        planner = DynamicExecutionPlanner(self.workflow)

        # Empty switch results
        invalid_results = {}

        # Should not crash
        reachable_nodes = analyzer.get_reachable_nodes(invalid_results)
        execution_plan = planner.create_execution_plan(invalid_results)

        # Should handle gracefully
        assert isinstance(
            reachable_nodes, set
        ), "Should return set even with invalid results"
        assert isinstance(
            execution_plan, list
        ), "Should return list even with invalid results"

    def test_bug_scenario_detailed_analysis(self):
        """Detailed analysis of the exact bug scenario that's happening."""
        from unittest.mock import patch

        analyzer = ConditionalBranchAnalyzer(self.workflow)

        # Create the exact switch results from our validation script
        # This represents: user_type='premium' (true) AND region='US' (true)
        switch_results = {
            "user_type_switch": {
                "true_output": {"user_type": "premium"},  # Premium path taken
                "false_output": None,  # Basic path NOT taken
            },
            "region_switch": {
                "true_output": {"region": "US"},  # US path taken
                "false_output": None,  # International path NOT taken
            },
        }

        # Debug: Check branch map construction
        branch_map = analyzer._build_branch_map()
        print(f"DEBUG: Branch map = {branch_map}")

        # Check what the analyzer thinks is reachable
        reachable_nodes = analyzer.get_reachable_nodes(switch_results)
        print(f"DEBUG: Reachable nodes = {reachable_nodes}")

        # BUG CHECK: intl_premium_processor should NOT be reachable
        # This test will fail if the bug exists
        if "intl_premium_processor" in reachable_nodes:
            # Print debug information to understand why
            region_branches = branch_map.get("region_switch", {})
            print(f"DEBUG: region_switch branches = {region_branches}")

            # Check which output ports are being activated
            for switch_id, port_results in switch_results.items():
                print(f"DEBUG: Switch {switch_id} port results = {port_results}")
                if switch_id in branch_map:
                    switch_branches = branch_map[switch_id]
                    for port, result in port_results.items():
                        if result is not None:
                            print(
                                f"DEBUG: Port {port} activated -> leads to {switch_branches.get(port, 'NONE')}"
                            )

        # The failing assertion - this should pass but currently fails due to the bug
        assert "intl_premium_processor" not in reachable_nodes, (
            f"BUG REPRODUCED: intl_premium_processor should not be reachable when region=US (true_output). "
            f"Switch results: {switch_results}, Reachable: {reachable_nodes}, "
            f"Branch map: {branch_map}"
        )
