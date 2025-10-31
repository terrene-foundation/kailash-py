"""
Edge case tests for DynamicExecutionPlanner to achieve >80% coverage.

Tests specific edge cases and error conditions to improve test coverage.
"""

from unittest.mock import Mock, patch

import networkx as nx
import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestDynamicExecutionPlannerEdgeCases:
    """Edge case tests for DynamicExecutionPlanner."""

    def test_analyze_dependencies_no_graph(self):
        """Test _analyze_dependencies when workflow has no graph."""
        workflow = Workflow("test", "Test")
        workflow.graph = None  # Explicitly set to None

        planner = DynamicExecutionPlanner(workflow)
        dependencies = planner._analyze_dependencies()

        assert dependencies == {}

    def test_get_always_reachable_nodes_no_graph(self):
        """Test _get_always_reachable_nodes when workflow has no graph."""
        workflow = Workflow("test", "Test")
        workflow.graph = None

        planner = DynamicExecutionPlanner(workflow)
        reachable = planner._get_always_reachable_nodes({"switch1"})

        assert reachable == set()

    def test_validate_execution_plan_no_graph(self):
        """Test validate_execution_plan when workflow has no graph."""
        workflow = Workflow("test", "Test")
        workflow.graph = None

        planner = DynamicExecutionPlanner(workflow)
        is_valid, errors = planner.validate_execution_plan(["node1"])

        assert is_valid is False
        assert "Workflow has no graph to validate against" in errors

    def test_create_hierarchical_plan_error_handling(self):
        """Test create_hierarchical_plan error handling."""
        workflow = Workflow("test", "Test")

        # Add switches with circular dependency
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)

        # Create circular dependency
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        workflow.connect("switch2", "switch1", {"true_output": "input_data"})

        planner = DynamicExecutionPlanner(workflow)

        # Should handle circular dependencies gracefully
        layers = planner.create_hierarchical_plan(workflow)
        assert isinstance(layers, list)
        assert len(layers) > 0

    def test_create_hierarchical_execution_plan_error(self):
        """Test create_hierarchical_execution_plan error handling."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Mock analyzer method to raise error
        with patch.object(
            planner.analyzer,
            "create_hierarchical_execution_plan",
            side_effect=Exception("Test error"),
        ):
            result = planner.create_hierarchical_execution_plan({})

            # Should fallback to basic execution plan
            assert "execution_plan" in result
            assert isinstance(result["execution_plan"], list)

    def test_handle_merge_with_conditional_inputs_no_graph(self):
        """Test _handle_merge_with_conditional_inputs when workflow has no graph."""
        workflow = Workflow("test", "Test")
        workflow.graph = None

        planner = DynamicExecutionPlanner(workflow)
        result = planner._handle_merge_with_conditional_inputs("merge", workflow, {})

        assert result is True  # Default behavior when no graph

    def test_find_merge_nodes_fallback_error(self):
        """Test _find_merge_nodes_fallback error handling."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Mock graph nodes to raise error
        with patch.object(workflow.graph, "nodes", side_effect=Exception("Test error")):
            merge_nodes = planner._find_merge_nodes_fallback()
            assert merge_nodes == []

    def test_create_merge_strategy_error(self):
        """Test _create_merge_strategy error handling."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Mock graph predecessors to raise error
        with patch.object(
            workflow.graph, "predecessors", side_effect=Exception("Test error")
        ):
            strategy = planner._create_merge_strategy("merge", set(), {})

            assert strategy["strategy_type"] == "error"
            assert len(strategy["recommendations"]) > 0

    def test_optimize_execution_plan_with_merge_modifications(self):
        """Test optimize_execution_plan with merge node modifications."""
        workflow = Workflow("test", "Test")

        # Create workflow with merge node
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        workflow.add_node("proc1", proc1)
        workflow.add_node("proc2", proc2)
        workflow.add_node("merge", merge)

        workflow.connect("proc1", "merge", {"result": "data1"})
        workflow.connect("proc2", "merge", {"result": "data2"})

        planner = DynamicExecutionPlanner(workflow)

        execution_plan = ["proc1", "merge"]
        switch_results = {}

        # Test optimization with merge node that should be skipped
        result = planner.optimize_execution_plan(execution_plan, switch_results)

        assert "optimized_plan" in result
        assert "analysis" in result

    def test_identify_parallel_execution_groups_error(self):
        """Test _identify_parallel_execution_groups error handling."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Test with None execution plan
        with patch.object(
            planner, "_analyze_dependencies", side_effect=Exception("Test error")
        ):
            groups = planner._identify_parallel_execution_groups(["node1", "node2"])

            # Should return default grouping
            assert isinstance(groups, list)

    def test_create_execution_plan_with_none_switch_results(self):
        """Test create_execution_plan with None switch_results."""
        workflow = Workflow("test", "Test")

        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")
        workflow.add_node("proc", proc)

        planner = DynamicExecutionPlanner(workflow)

        # Test with None switch_results
        plan = planner.create_execution_plan(None)
        assert plan == ["proc"]

    def test_get_all_nodes_topological_order_with_cycle(self):
        """Test _get_all_nodes_topological_order with cyclic graph."""
        workflow = Workflow("test", "Test")

        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")

        workflow.add_node("proc1", proc1)
        workflow.add_node("proc2", proc2)

        # Create cycle
        workflow.connect("proc1", "proc2", {"result": "input"})
        workflow.connect("proc2", "proc1", {"result": "input"})

        planner = DynamicExecutionPlanner(workflow)

        # Should handle cycles gracefully
        nodes = planner._get_all_nodes_topological_order()
        assert set(nodes) == {"proc1", "proc2"}

    def test_is_reachable_without_switches_edge_cases(self):
        """Test _is_reachable_without_switches edge cases."""
        workflow = Workflow("test", "Test")

        # Create complex graph
        source = PythonCodeNode(name="source", code="result = {'data': 1}")
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 2}")

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("proc", proc)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("switch1", "proc", {"true_output": "input"})

        planner = DynamicExecutionPlanner(workflow)

        # Test node behind switch
        is_reachable = planner._is_reachable_without_switches("proc", {"switch1"})
        assert is_reachable is False

        # Test source node
        is_reachable = planner._is_reachable_without_switches("source", {"switch1"})
        assert is_reachable is True

    def test_create_cache_key_edge_cases(self):
        """Test _create_cache_key with edge cases."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Test with None ports
        results1 = {"switch1": None}
        key1 = planner._create_cache_key(results1)
        assert isinstance(key1, str)

        # Test with non-dict ports
        results2 = {"switch1": "invalid"}
        key2 = planner._create_cache_key(results2)
        assert isinstance(key2, str)

        # Test with complex nested structure
        results3 = {
            "switch1": {
                "true_output": {"nested": {"data": [1, 2, 3]}},
                "false_output": None,
            }
        }
        key3 = planner._create_cache_key(results3)
        assert isinstance(key3, str)

    def test_handle_merge_nodes_without_analyzer_method(self):
        """Test handle_merge_nodes_with_conditional_inputs without analyzer method."""
        workflow = Workflow("test", "Test")

        merge = MergeNode(name="merge", merge_type="merge_dict")
        workflow.add_node("merge", merge)

        planner = DynamicExecutionPlanner(workflow)

        # Mock analyzer to not have _find_merge_nodes method
        with patch.object(
            planner.analyzer, "_find_merge_nodes", side_effect=AttributeError
        ):
            result = planner.handle_merge_nodes_with_conditional_inputs(["merge"], {})

            # Should use fallback method
            assert "merge_nodes" in result
            assert "strategies" in result

    def test_performance_metrics_division_by_zero(self):
        """Test performance metrics when total_nodes is 0."""
        workflow = Workflow("test", "Test")
        workflow.graph = nx.DiGraph()  # Empty graph

        planner = DynamicExecutionPlanner(workflow)

        result = planner.create_hierarchical_execution_plan({})

        # Should handle division by zero
        assert result["performance_metrics"]["performance_improvement"] == 0
