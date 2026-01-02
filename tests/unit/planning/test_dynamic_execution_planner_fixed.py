"""
Fixed tests for DynamicExecutionPlanner to improve coverage.

These tests use the actual available methods and test realistic scenarios
to achieve >80% coverage.
"""

from unittest.mock import Mock, patch

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestDynamicExecutionPlannerFixed:
    """Fixed tests to improve DynamicExecutionPlanner coverage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.analyzer = ConditionalBranchAnalyzer(self.workflow)
        self.planner = DynamicExecutionPlanner(self.workflow)

    def test_create_execution_plan_empty_workflow(self):
        """Test create_execution_plan with empty workflow."""
        empty_workflow = Workflow("empty", "Empty Workflow")
        planner = DynamicExecutionPlanner(empty_workflow)

        plan = planner.create_execution_plan({})
        assert plan == []

    def test_create_execution_plan_no_switches(self):
        """Test create_execution_plan with workflow without switches."""
        # Add some nodes
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        # Empty switch results should return all nodes
        plan = self.planner.create_execution_plan({})
        assert len(plan) == 2
        assert "proc1" in plan
        assert "proc2" in plan
        assert plan.index("proc1") < plan.index("proc2")  # Dependency order

    def test_create_execution_plan_with_switches(self):
        """Test create_execution_plan with switch nodes."""
        # Create workflow with switch
        source = PythonCodeNode(name="source", code="result = {'status': 'active'}")
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc_true = PythonCodeNode(name="proc_true", code="result = {'branch': 'true'}")
        proc_false = PythonCodeNode(
            name="proc_false", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc_true", proc_true)
        self.workflow.add_node("proc_false", proc_false)

        self.workflow.connect("source", "switch", {"result": "input_data"})
        self.workflow.connect("switch", "proc_true", {"true_output": "input"})
        self.workflow.connect("switch", "proc_false", {"false_output": "input"})

        # Test with switch taking true path
        switch_results = {
            "switch": {"true_output": {"status": "active"}, "false_output": None}
        }

        plan = self.planner.create_execution_plan(switch_results)

        # Should include source, switch, and true processor
        assert "source" in plan
        assert "switch" in plan
        assert "proc_true" in plan
        # False processor should not be in plan
        assert "proc_false" not in plan

    def test_validate_execution_plan(self):
        """Test validate_execution_plan method."""
        # Create workflow with dependencies
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.connect("proc2", "proc3", {"result": "input"})

        # Valid plan
        valid_plan = ["proc1", "proc2", "proc3"]
        is_valid, issues = self.planner.validate_execution_plan(valid_plan)
        assert is_valid is True
        assert len(issues) == 0

        # Invalid plan (missing dependency)
        invalid_plan = ["proc1", "proc3"]  # Missing proc2
        is_valid, issues = self.planner.validate_execution_plan(invalid_plan)
        assert is_valid is False
        assert len(issues) > 0

    def test_analyze_dependencies(self):
        """Test _analyze_dependencies method."""
        # Create workflow with complex dependencies
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.connect("proc1", "proc3", {"result": "input"})
        self.workflow.connect("proc2", "proc3", {"result": "input2"})

        dependencies = self.planner._analyze_dependencies()

        assert "proc1" in dependencies
        assert dependencies["proc1"] == []  # No dependencies
        assert "proc2" in dependencies
        assert "proc1" in dependencies["proc2"]
        assert "proc3" in dependencies
        assert set(dependencies["proc3"]) == {"proc1", "proc2"}

    def test_create_cache_key(self):
        """Test _create_cache_key method."""
        # Test with various switch results
        switch_results1 = {"switch1": {"true_output": {"status": "active"}}}
        key1 = self.planner._create_cache_key(switch_results1)
        assert isinstance(key1, str)

        # Same results should produce same key
        key2 = self.planner._create_cache_key(switch_results1)
        assert key1 == key2

        # Different results should produce different key
        switch_results2 = {"switch1": {"false_output": {"status": "inactive"}}}
        key3 = self.planner._create_cache_key(switch_results2)
        assert key3 != key1

        # Test with None values
        switch_results3 = {
            "switch1": {"true_output": None, "false_output": {"data": "test"}}
        }
        key4 = self.planner._create_cache_key(switch_results3)
        assert isinstance(key4, str)

    def test_invalidate_cache(self):
        """Test invalidate_cache method."""
        # Add something to cache first (use proper attribute name)
        self.planner._execution_plan_cache = {"test_key": ["node1", "node2"]}

        assert len(self.planner._execution_plan_cache) == 1

        self.planner.invalidate_cache()

        assert len(self.planner._execution_plan_cache) == 0

    def test_create_hierarchical_plan(self):
        """Test create_hierarchical_plan method."""
        # Create workflow with parallel branches
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("source", source)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("source", "proc1", {"result": "input"})
        self.workflow.connect("source", "proc2", {"result": "input"})
        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})

        hierarchical_plan = self.planner.create_hierarchical_plan(self.workflow)

        assert isinstance(hierarchical_plan, list)
        assert len(hierarchical_plan) > 0
        # First layer should have source
        assert "source" in hierarchical_plan[0]
        # Parallel processors should be in same layer
        for layer in hierarchical_plan:
            if "proc1" in layer:
                assert "proc2" in layer
        # Merge should be in last layer
        assert "merge" in hierarchical_plan[-1]

    def test_create_hierarchical_execution_plan(self):
        """Test create_hierarchical_execution_plan method."""
        # Create workflow with switches
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc", proc)

        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "proc", {"true_output": "input"})

        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": {"b": 2}, "false_output": None},
        }

        plan = self.planner.create_hierarchical_execution_plan(switch_results)

        assert isinstance(plan, dict)
        assert "execution_layers" in plan
        assert "performance_estimate" in plan
        assert "reachable_nodes" in plan

    def test_handle_merge_nodes_with_conditional_inputs(self):
        """Test handle_merge_nodes_with_conditional_inputs method."""
        # Create workflow with conditional merge
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'data_a': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data_b': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("switch1", "proc1", {"true_output": "input"})
        self.workflow.connect("switch2", "proc2", {"true_output": "input"})
        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})

        # Only proc1 is reachable
        reachable_nodes = {"switch1", "proc1", "merge"}
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": None},
        }

        # handle_merge_nodes_with_conditional_inputs expects execution_plan as first arg
        execution_plan = ["switch1", "proc1", "merge"]
        result = self.planner.handle_merge_nodes_with_conditional_inputs(
            execution_plan, switch_results
        )

        assert isinstance(result, dict)
        assert "strategies" in result  # Not "merge_strategies"
        assert "merge_nodes" in result

    def test_optimize_execution_plan(self):
        """Test optimize_execution_plan method."""
        # Create simple workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.connect("proc2", "proc3", {"result": "input"})

        execution_plan = ["proc1", "proc2", "proc3"]
        switch_results = {}

        optimized = self.planner.optimize_execution_plan(execution_plan, switch_results)

        assert isinstance(optimized, dict)
        assert "optimized_plan" in optimized
        assert "optimizations_applied" in optimized
        assert "performance_improvement" in optimized  # Not "performance_estimate"

    def test_prune_unreachable_branches(self):
        """Test _prune_unreachable_branches method."""
        all_nodes = ["node1", "node2", "node3", "node4"]
        reachable_nodes = {"node1", "node3"}

        pruned = self.planner._prune_unreachable_branches(all_nodes, reachable_nodes)

        assert len(pruned) == 2
        assert "node1" in pruned
        assert "node3" in pruned
        assert "node2" not in pruned
        assert "node4" not in pruned

    def test_get_always_reachable_nodes(self):
        """Test _get_always_reachable_nodes method."""
        # Create workflow with mixed nodes
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
        always_reachable = self.planner._get_always_reachable_nodes(switch_node_ids)

        # Source should be always reachable (no switch dependencies)
        assert "source" in always_reachable
        # Switch itself is always reachable
        assert "switch" in always_reachable
        # Proc depends on switch output, not always reachable
        assert "proc" not in always_reachable

    def test_handle_merge_with_conditional_inputs(self):
        """Test _handle_merge_with_conditional_inputs method."""
        # Create workflow with merge
        merge = MergeNode(name="merge", merge_type="merge_dict")
        self.workflow.add_node("merge", merge)

        switch_results = {}

        # This method checks if merge should be included
        result = self.planner._handle_merge_with_conditional_inputs(
            "merge", self.workflow, switch_results
        )

        assert isinstance(result, bool)

    def test_identify_parallel_execution_groups(self):
        """Test _identify_parallel_execution_groups method."""
        # Create workflow with parallel branches
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        self.workflow.connect("source", "proc1", {"result": "input"})
        self.workflow.connect("source", "proc2", {"result": "input"})

        execution_plan = ["source", "proc1", "proc2"]

        groups = self.planner._identify_parallel_execution_groups(execution_plan)

        assert isinstance(groups, list)
        # proc1 and proc2 should be in same group (parallel)
        parallel_group = None
        for group in groups:
            if "proc1" in group and "proc2" in group:
                parallel_group = group
                break
        assert parallel_group is not None

    def test_large_workflow_performance(self):
        """Test performance with larger workflow."""
        # Create larger workflow
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        self.workflow.add_node("source", source)

        # Add many nodes
        for i in range(50):
            if i % 5 == 0:  # Every 5th node is a switch
                switch = SwitchNode(
                    name=f"switch_{i}",
                    condition_field=f"field_{i}",
                    operator="==",
                    value=i,
                )
                self.workflow.add_node(f"node_{i}", switch)
            else:
                proc = PythonCodeNode(
                    name=f"proc_{i}", code=f"result = {{'proc': {i}}}"
                )
                self.workflow.add_node(f"node_{i}", proc)

            if i > 0:
                self.workflow.connect("source", f"node_{i}", {"result": "input"})

        # Create switch results
        switch_results = {}
        for i in range(0, 50, 5):
            switch_results[f"node_{i}"] = {
                "true_output": {f"field_{i}": i},
                "false_output": None,
            }

        # Test performance
        import time

        start_time = time.time()

        plan = self.planner.create_execution_plan(switch_results)

        execution_time = time.time() - start_time

        # Should complete quickly
        assert execution_time < 2.0
        assert len(plan) > 0

    def test_edge_cases(self):
        """Test edge cases and error conditions."""
        # Test with empty switch results
        plan = self.planner.create_execution_plan({})
        assert isinstance(plan, list)

        # Test validation with empty plan
        is_valid, issues = self.planner.validate_execution_plan([])
        assert isinstance(is_valid, bool)

        # Test cache key with empty results
        key = self.planner._create_cache_key({})
        assert isinstance(key, str)

        # Test optimize with empty plan
        optimized = self.planner.optimize_execution_plan([], {})
        assert isinstance(optimized, dict)
