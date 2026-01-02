"""
Enhanced tests for DynamicExecutionPlanner to achieve 80%+ coverage.

These tests target advanced Phase 4 methods and edge cases that are likely
under-covered in the existing test suite.
"""

from collections import defaultdict, deque
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestDynamicExecutionPlannerAdvancedMethods:
    """Test advanced Phase 4 methods in DynamicExecutionPlanner."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.planner = DynamicExecutionPlanner(self.workflow)

    def test_get_always_reachable_nodes_empty_workflow(self):
        """Test _get_always_reachable_nodes with empty workflow."""
        switch_node_ids = {"switch1", "switch2"}
        reachable = self.planner._get_always_reachable_nodes(switch_node_ids)
        assert reachable == set()

    def test_get_always_reachable_nodes_no_switches(self):
        """Test _get_always_reachable_nodes with no switches."""
        # Add regular nodes
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        switch_node_ids = set()
        reachable = self.planner._get_always_reachable_nodes(switch_node_ids)

        # All nodes should be always reachable when there are no switches
        assert "proc1" in reachable
        assert "proc2" in reachable

    def test_get_always_reachable_nodes_with_switches(self):
        """Test _get_always_reachable_nodes with switches present."""
        # Create workflow with source -> switch -> processor
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'step': 1}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc", proc)

        self.workflow.connect("source", "switch", {"result": "input_data"})
        self.workflow.connect("switch", "proc", {"true_output": "input"})

        switch_node_ids = {"switch"}
        reachable = self.planner._get_always_reachable_nodes(switch_node_ids)

        # Source and switch should be always reachable, proc depends on switch
        assert "source" in reachable
        assert "switch" in reachable
        assert "proc" not in reachable

    def test_is_reachable_without_switches_source_node(self):
        """Test _is_reachable_without_switches with source node."""
        # Create source node (no predecessors)
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        self.workflow.add_node("source", source)

        switch_node_ids = {"switch1"}
        is_reachable = self.planner._is_reachable_without_switches(
            "source", switch_node_ids
        )

        # Source nodes are always reachable without switches
        assert is_reachable is True

    def test_is_reachable_without_switches_switch_node(self):
        """Test _is_reachable_without_switches with switch node itself."""
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        self.workflow.add_node("switch", switch)

        switch_node_ids = {"switch"}
        is_reachable = self.planner._is_reachable_without_switches(
            "switch", switch_node_ids
        )

        # Switches themselves are always reachable
        assert is_reachable is True

    def test_is_reachable_without_switches_through_switch(self):
        """Test _is_reachable_without_switches when path goes through switch."""
        # Create workflow: source -> switch -> proc
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'step': 1}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc", proc)

        self.workflow.connect("source", "switch", {"result": "input_data"})
        self.workflow.connect("switch", "proc", {"true_output": "input"})

        switch_node_ids = {"switch"}
        is_reachable = self.planner._is_reachable_without_switches(
            "proc", switch_node_ids
        )

        # proc can only be reached through switch, so not always reachable
        assert is_reachable is False

    def test_is_reachable_without_switches_complex_path(self):
        """Test _is_reachable_without_switches with complex path."""
        # Create workflow: source -> proc1 -> proc2 (no switches)
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        self.workflow.connect("source", "proc1", {"result": "input"})
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        switch_node_ids = {"switch1"}  # No actual switches in this workflow
        is_reachable = self.planner._is_reachable_without_switches(
            "proc2", switch_node_ids
        )

        # proc2 can be reached without going through any switches
        assert is_reachable is True

    def test_create_cache_key_complex_scenarios(self):
        """Test _create_cache_key with complex switch result structures."""
        # Test with None ports
        results_with_none_ports = {"switch1": None}
        key1 = self.planner._create_cache_key(results_with_none_ports)
        assert isinstance(key1, str)
        assert "None" in key1

        # Test with invalid port format
        results_with_invalid_ports = {"switch1": "invalid_format"}
        key2 = self.planner._create_cache_key(results_with_invalid_ports)
        assert isinstance(key2, str)
        assert "invalid" in key2

        # Test with multiple switches and mixed result types
        complex_results = {
            "switch1": {"true_output": {"data": "active"}, "false_output": None},
            "switch2": None,
            "switch3": {"case_A": {"type": "premium"}, "case_B": None, "case_C": None},
        }
        key3 = self.planner._create_cache_key(complex_results)
        assert isinstance(key3, str)
        # Should contain all switch IDs
        assert "switch1" in key3
        assert "switch2" in key3
        assert "switch3" in key3

    def test_create_hierarchical_plan_no_switches(self):
        """Test create_hierarchical_plan with workflow containing no switches."""
        # Create workflow without switches
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        layers = self.planner.create_hierarchical_plan(self.workflow)

        # Should return single layer with all nodes
        assert len(layers) == 1
        assert "proc1" in layers[0]
        assert "proc2" in layers[0]

    def test_create_hierarchical_plan_linear_switches(self):
        """Test create_hierarchical_plan with linear switch dependencies."""
        # Create linear switch chain: switch1 -> switch2 -> switch3
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="==", value=3
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "switch3", {"true_output": "input_data"})

        layers = self.planner.create_hierarchical_plan(self.workflow)

        # Should create multiple layers based on dependencies
        assert len(layers) == 3
        assert "switch1" in layers[0]
        assert "switch2" in layers[1]
        assert "switch3" in layers[2]

    def test_create_hierarchical_plan_parallel_switches(self):
        """Test create_hierarchical_plan with parallel switches."""
        # Create parallel switches (no dependencies between them)
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="==", value=3
        )

        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        # All switches depend on source but not on each other
        self.workflow.connect("source", "switch1", {"result": "input_data"})
        self.workflow.connect("source", "switch2", {"result": "input_data"})
        self.workflow.connect("source", "switch3", {"result": "input_data"})

        layers = self.planner.create_hierarchical_plan(self.workflow)

        # All switches should be in the same layer (can execute in parallel)
        assert len(layers) == 1
        assert "switch1" in layers[0]
        assert "switch2" in layers[0]
        assert "switch3" in layers[0]

    def test_create_hierarchical_plan_circular_dependencies(self):
        """Test create_hierarchical_plan with circular dependencies."""
        # Create circular dependency: switch1 -> switch2 -> switch3 -> switch1
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="==", value=3
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        # Create circular connections
        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "switch3", {"true_output": "input_data"})
        self.workflow.connect("switch3", "switch1", {"true_output": "input_data"})

        layers = self.planner.create_hierarchical_plan(self.workflow)

        # Should handle circular dependencies by putting all in one layer
        assert len(layers) == 1
        assert set(layers[0]) == {"switch1", "switch2", "switch3"}

    def test_handle_merge_with_conditional_inputs_no_graph(self):
        """Test _handle_merge_with_conditional_inputs with no graph."""
        # Create workflow without graph
        empty_workflow = Workflow("empty", "Empty")
        empty_workflow.graph = None

        result = self.planner._handle_merge_with_conditional_inputs(
            "merge1", empty_workflow, {}
        )

        # Should return True (default behavior when no graph)
        assert result is True

    def test_handle_merge_with_conditional_inputs_with_available_inputs(self):
        """Test _handle_merge_with_conditional_inputs with available inputs."""
        # Create workflow with merge node
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc", proc)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("switch", "proc", {"true_output": "input"})
        self.workflow.connect("proc", "merge", {"result": "data"})

        switch_results = {
            "switch": {"true_output": {"status": "active"}, "false_output": None}
        }

        result = self.planner._handle_merge_with_conditional_inputs(
            "merge", self.workflow, switch_results
        )

        # Should return True since proc is reachable and feeds into merge
        assert result is True

    def test_handle_merge_with_conditional_inputs_no_available_inputs(self):
        """Test _handle_merge_with_conditional_inputs with no available inputs."""
        # Create workflow with merge node but no reachable inputs
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc", proc)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("switch", "proc", {"true_output": "input"})
        self.workflow.connect("proc", "merge", {"result": "data"})

        # Switch takes false path, so proc is not reachable
        switch_results = {
            "switch": {"true_output": None, "false_output": {"status": "inactive"}}
        }

        result = self.planner._handle_merge_with_conditional_inputs(
            "merge", self.workflow, switch_results
        )

        # Should return False since no inputs are available to merge
        assert result is False


class TestAdvancedExecutionPlanOptimization:
    """Test advanced execution plan optimization methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.planner = DynamicExecutionPlanner(self.workflow)

    def test_find_merge_nodes_fallback(self):
        """Test _find_merge_nodes_fallback method."""
        # Create workflow with merge nodes
        merge1 = MergeNode(name="merge1", merge_type="merge_dict")
        merge2 = MergeNode(name="merge2", merge_type="merge_list")
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")

        self.workflow.add_node("merge1", merge1)
        self.workflow.add_node("merge2", merge2)
        self.workflow.add_node("proc", proc)

        merge_nodes = self.planner._find_merge_nodes_fallback()

        assert "merge1" in merge_nodes
        assert "merge2" in merge_nodes
        assert "proc" not in merge_nodes
        assert len(merge_nodes) == 2

    def test_find_merge_nodes_fallback_no_merges(self):
        """Test _find_merge_nodes_fallback with no merge nodes."""
        # Create workflow with only regular nodes
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        merge_nodes = self.planner._find_merge_nodes_fallback()

        assert merge_nodes == []

    def test_create_merge_strategy_all_inputs_available(self):
        """Test _create_merge_strategy with all inputs available."""
        # Create workflow with merge node
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})

        reachable_nodes = {"proc1", "proc2", "merge"}
        switch_results = {}

        strategy = self.planner._create_merge_strategy(
            "merge", reachable_nodes, switch_results
        )

        assert strategy["merge_id"] == "merge"
        assert strategy["strategy_type"] == "full"
        assert strategy["confidence"] == 1.0
        assert set(strategy["available_inputs"]) == {"proc1", "proc2"}
        assert strategy["missing_inputs"] == []

    def test_create_merge_strategy_no_inputs_available(self):
        """Test _create_merge_strategy with no inputs available."""
        # Create workflow with merge node
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})

        # Only merge is reachable, not its inputs
        reachable_nodes = {"merge"}
        switch_results = {}

        strategy = self.planner._create_merge_strategy(
            "merge", reachable_nodes, switch_results
        )

        assert strategy["strategy_type"] == "skip"
        assert strategy["confidence"] == 1.0
        assert strategy["available_inputs"] == []
        assert set(strategy["missing_inputs"]) == {"proc1", "proc2"}

    def test_create_merge_strategy_partial_inputs(self):
        """Test _create_merge_strategy with partial inputs available."""
        # Create workflow with merge node
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'data': 3}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})
        self.workflow.connect("proc3", "merge", {"result": "data3"})

        # Only proc1 and proc3 are reachable
        reachable_nodes = {"proc1", "proc3", "merge"}
        switch_results = {}

        strategy = self.planner._create_merge_strategy(
            "merge", reachable_nodes, switch_results
        )

        assert strategy["strategy_type"] == "partial"
        assert strategy["confidence"] == 2 / 3  # 2 out of 3 inputs available
        assert set(strategy["available_inputs"]) == {"proc1", "proc3"}
        assert strategy["missing_inputs"] == ["proc2"]

    def test_identify_parallel_execution_groups(self):
        """Test _identify_parallel_execution_groups method."""
        # Create workflow with parallel execution opportunities
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("source", source)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)
        self.workflow.add_node("merge", merge)

        # Create parallel branches
        self.workflow.connect("source", "proc1", {"result": "input"})
        self.workflow.connect("source", "proc2", {"result": "input"})
        self.workflow.connect("source", "proc3", {"result": "input"})
        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})
        self.workflow.connect("proc3", "merge", {"result": "data3"})

        execution_plan = ["source", "proc1", "proc2", "proc3", "merge"]
        parallel_groups = self.planner._identify_parallel_execution_groups(
            execution_plan
        )

        # proc1, proc2, proc3 should be identified as a parallel group
        assert len(parallel_groups) >= 1
        found_parallel_group = False
        for group in parallel_groups:
            if "proc1" in group and "proc2" in group and "proc3" in group:
                found_parallel_group = True
                break
        assert found_parallel_group

    def test_group_by_dependency_depth(self):
        """Test _group_by_dependency_depth method."""
        execution_plan = ["source", "proc1", "proc2", "proc3", "merge"]
        dependencies = {
            "source": [],
            "proc1": ["source"],
            "proc2": ["source"],
            "proc3": ["source"],
            "merge": ["proc1", "proc2", "proc3"],
        }

        depth_groups = self.planner._group_by_dependency_depth(
            execution_plan, dependencies
        )

        # Should group by dependency depth
        assert 0 in depth_groups  # source at depth 0
        assert 1 in depth_groups  # proc1, proc2, proc3 at depth 1
        assert 2 in depth_groups  # merge at depth 2

        assert "source" in depth_groups[0]
        assert all(proc in depth_groups[1] for proc in ["proc1", "proc2", "proc3"])
        assert "merge" in depth_groups[2]

    def test_calculate_node_depth(self):
        """Test _calculate_node_depth method."""
        dependencies = {
            "source": [],
            "proc1": ["source"],
            "proc2": ["proc1"],
            "proc3": ["proc2"],
        }
        node_depths = {}

        # Test depth calculation for nodes at different levels
        depth0 = self.planner._calculate_node_depth("source", dependencies, node_depths)
        assert depth0 == 0

        depth1 = self.planner._calculate_node_depth("proc1", dependencies, node_depths)
        assert depth1 == 1

        depth2 = self.planner._calculate_node_depth("proc2", dependencies, node_depths)
        assert depth2 == 2

        depth3 = self.planner._calculate_node_depth("proc3", dependencies, node_depths)
        assert depth3 == 3

    def test_calculate_node_depth_with_cache(self):
        """Test _calculate_node_depth uses cache correctly."""
        dependencies = {"proc1": ["source"], "proc2": ["proc1"]}
        node_depths = {"source": 0, "proc1": 1}  # Pre-populate cache

        # Should use cached value for proc1
        depth = self.planner._calculate_node_depth("proc2", dependencies, node_depths)
        assert depth == 2

    def test_error_handling_in_create_hierarchical_execution_plan(self):
        """Test error handling in create_hierarchical_execution_plan."""
        # Test with workflow that might cause errors
        switch_results = {"nonexistent_switch": {"true_output": {"data": 1}}}

        # Mock the analyzer to raise an exception
        with patch.object(self.planner, "analyzer") as mock_analyzer:
            mock_analyzer.create_hierarchical_execution_plan.side_effect = Exception(
                "Test error"
            )

            plan = self.planner.create_hierarchical_execution_plan(switch_results)

            # Should handle error gracefully and return basic structure
            assert isinstance(plan, dict)
            assert "execution_plan" in plan

    def test_error_handling_in_handle_merge_nodes(self):
        """Test error handling in handle_merge_nodes_with_conditional_inputs."""
        execution_plan = ["node1", "node2"]
        switch_results = {}

        # Mock analyzer to raise exception
        with patch.object(
            self.planner.analyzer,
            "_find_merge_nodes",
            side_effect=Exception("Test error"),
        ):
            result = self.planner.handle_merge_nodes_with_conditional_inputs(
                execution_plan, switch_results
            )

            # Should handle error gracefully
            assert "warnings" in result
            assert len(result["warnings"]) > 0

    def test_error_handling_in_optimize_execution_plan(self):
        """Test error handling in optimize_execution_plan."""
        execution_plan = ["node1", "node2"]
        switch_results = {}

        # Mock a method to raise exception
        with patch.object(
            self.planner,
            "_identify_parallel_execution_groups",
            side_effect=Exception("Test error"),
        ):
            result = self.planner.optimize_execution_plan(
                execution_plan, switch_results
            )

            # Should handle error gracefully
            assert "analysis" in result
            assert "error" in result["analysis"]


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.planner = DynamicExecutionPlanner(self.workflow)

    def test_create_execution_plan_none_switch_results(self):
        """Test create_execution_plan with None switch_results."""
        # Add some nodes to test with
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        # Test with None
        plan = self.planner.create_execution_plan(None)

        # Should return all nodes in topological order
        assert len(plan) == 2
        assert "proc1" in plan
        assert "proc2" in plan

    def test_validate_execution_plan_no_graph(self):
        """Test validate_execution_plan with workflow having no graph."""
        # Create workflow without graph
        empty_workflow = Workflow("empty", "Empty")
        empty_planner = DynamicExecutionPlanner(empty_workflow)
        empty_planner.workflow.graph = None

        is_valid, errors = empty_planner.validate_execution_plan(["node1"])

        assert is_valid is False
        assert len(errors) > 0
        assert any("no graph" in error.lower() for error in errors)

    def test_get_all_nodes_topological_order_with_cycles(self):
        """Test _get_all_nodes_topological_order with workflow containing cycles."""
        # Create workflow with cycle
        proc1 = PythonCodeNode(name="proc1", code="result = {'count': count + 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': data}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        # Create cycle
        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.create_cycle("test_cycle").connect(
            "proc2", "proc1", {"result": "input"}
        ).max_iterations(5).build()

        # Should handle cycles gracefully (fallback to node list)
        order = self.planner._get_all_nodes_topological_order()
        assert isinstance(order, list)
        assert len(order) == 2

    def test_analyze_dependencies_caching(self):
        """Test _analyze_dependencies caching behavior."""
        # Add nodes to workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        # First call should populate cache
        deps1 = self.planner._analyze_dependencies()

        # Second call should use cache
        deps2 = self.planner._analyze_dependencies()

        assert deps1 == deps2
        assert self.planner._dependency_cache is not None

    def test_create_execution_plan_error_handling(self):
        """Test create_execution_plan error handling."""
        # Mock analyzer to raise exception
        with patch.object(
            self.planner.analyzer,
            "get_reachable_nodes",
            side_effect=Exception("Test error"),
        ):
            switch_results = {"switch1": {"true_output": {"data": 1}}}

            # Should fall back to all nodes despite error
            plan = self.planner.create_execution_plan(switch_results)
            assert isinstance(plan, list)

    def test_prune_unreachable_branches_edge_cases(self):
        """Test _prune_unreachable_branches edge cases."""
        # Test with empty inputs
        pruned = self.planner._prune_unreachable_branches([], set())
        assert pruned == []

        # Test with all nodes unreachable
        all_nodes = ["node1", "node2", "node3"]
        reachable_nodes = set()
        pruned = self.planner._prune_unreachable_branches(all_nodes, reachable_nodes)
        assert pruned == []

        # Test with all nodes reachable
        reachable_nodes = set(all_nodes)
        pruned = self.planner._prune_unreachable_branches(all_nodes, reachable_nodes)
        assert pruned == all_nodes

    def test_dependency_analysis_edge_cases(self):
        """Test dependency analysis edge cases."""
        # Test with workflow having no graph
        empty_workflow = Workflow("empty", "Empty")
        empty_planner = DynamicExecutionPlanner(empty_workflow)
        empty_planner.workflow.graph = None

        deps = empty_planner._analyze_dependencies()
        assert deps == {}

    def test_invalidate_cache_with_analyzer(self):
        """Test invalidate_cache also invalidates analyzer cache."""
        # Mock analyzer with invalidate_cache method
        mock_analyzer = Mock()
        mock_analyzer.invalidate_cache = Mock()
        self.planner.analyzer = mock_analyzer

        self.planner.invalidate_cache()

        # Should call analyzer's invalidate_cache
        mock_analyzer.invalidate_cache.assert_called_once()

    def test_invalidate_cache_without_analyzer_method(self):
        """Test invalidate_cache when analyzer doesn't have invalidate_cache method."""
        # Mock analyzer without invalidate_cache method
        mock_analyzer = Mock()
        del mock_analyzer.invalidate_cache  # Remove the method
        self.planner.analyzer = mock_analyzer

        # Should not raise error
        self.planner.invalidate_cache()
        assert len(self.planner._execution_plan_cache) == 0
