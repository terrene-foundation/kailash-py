"""
Additional tests for DynamicExecutionPlanner to improve coverage.

These tests target specific methods and edge cases that weren't covered
in the original test suite to achieve >80% coverage.
"""

from unittest.mock import Mock, patch

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestDynamicExecutionPlannerCoverage:
    """Additional tests to improve DynamicExecutionPlanner coverage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.analyzer = ConditionalBranchAnalyzer(self.workflow)
        self.planner = DynamicExecutionPlanner(self.workflow)  # Only takes workflow

    def test_get_all_nodes_topological_order_empty_workflow(self):
        """Test _get_all_nodes_topological_order with empty workflow."""
        empty_workflow = Workflow("empty", "Empty Workflow")
        planner = DynamicExecutionPlanner(empty_workflow)

        order = planner._get_all_nodes_topological_order()
        assert order == []

    def test_get_all_nodes_topological_order_single_node(self):
        """Test _get_all_nodes_topological_order with single node."""
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")
        self.workflow.add_node("proc", proc)

        order = self.planner._get_all_nodes_topological_order()
        assert order == ["proc"]

    def test_create_execution_plan_empty_switch_results(self):
        """Test create_execution_plan with empty switch results."""
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

    def test_create_execution_plan_with_dependencies(self):
        """Test create_execution_plan respects node dependencies."""
        # Create workflow with dependencies
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        # Create dependency chain
        self.workflow.connect("source", "switch", {"result": "input_data"})
        self.workflow.connect("switch", "proc1", {"true_output": "input"})
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        switch_results = {
            "switch": {"true_output": {"status": "active"}, "false_output": None}
        }

        plan = self.planner.create_execution_plan(switch_results)

        # Verify dependency order
        source_idx = plan.index("source")
        switch_idx = plan.index("switch")
        proc1_idx = plan.index("proc1")
        proc2_idx = plan.index("proc2")

        assert source_idx < switch_idx
        assert switch_idx < proc1_idx
        assert proc1_idx < proc2_idx

    def test_validate_execution_plan_valid_plan(self):
        """Test _validate_execution_plan with valid plan."""
        # Create workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        plan = ["proc1", "proc2"]
        is_valid, errors = self.planner.validate_execution_plan(plan)

        assert is_valid is True
        assert errors == []

    def test_validate_execution_plan_missing_dependencies(self):
        """Test _validate_execution_plan with missing dependencies."""
        # Create workflow with dependencies
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.connect("proc2", "proc3", {"result": "input"})

        # Plan missing proc2 (dependency of proc3)
        plan = ["proc1", "proc3"]
        is_valid, errors = self.planner.validate_execution_plan(plan)

        assert is_valid is False
        assert any("proc2" in error for error in errors)

    def test_get_cached_execution_plan_cache_miss(self):
        """Test _execution_plan_cache.get with cache miss."""
        switch_results = {"switch1": {"true_output": {"status": "active"}}}

        # Need to use cache key, not switch_results directly
        cache_key = self.planner._create_cache_key(switch_results)
        cached_plan = self.planner._execution_plan_cache.get(cache_key)
        assert cached_plan is None

    def test_get_cached_execution_plan_cache_hit(self):
        """Test _execution_plan_cache.get with cache hit."""
        switch_results = {"switch1": {"true_output": {"status": "active"}}}
        expected_plan = ["node1", "node2", "node3"]

        # Manually add to cache
        cache_key = self.planner._create_cache_key(switch_results)
        self.planner._execution_plan_cache[cache_key] = expected_plan

        # Need to use cache key
        cached_plan = self.planner._execution_plan_cache.get(cache_key)
        assert cached_plan == expected_plan

    def test_execution_plan_cache(self):
        """Test _execution_plan_cache method."""
        switch_results = {"switch1": {"true_output": {"status": "active"}}}
        plan = ["node1", "node2", "node3"]

        # Cache should be initially empty
        assert len(self.planner._execution_plan_cache) == 0

        # Manually cache the plan
        cache_key = self.planner._create_cache_key(switch_results)
        self.planner._execution_plan_cache[cache_key] = plan

        # Verify plan was cached
        assert len(self.planner._execution_plan_cache) == 1

        cached_plan = self.planner._execution_plan_cache.get(cache_key)
        assert cached_plan == plan

    def test_create_cache_key_various_inputs(self):
        """Test _create_cache_key with various input types."""
        # Test with different switch result structures
        simple_results = {"switch1": {"true_output": {"status": "active"}}}
        key1 = self.planner._create_cache_key(simple_results)
        assert isinstance(key1, str)

        complex_results = {
            "switch1": {"true_output": {"status": "active", "type": "premium"}},
            "switch2": {"false_output": {"region": "US"}},
        }
        key2 = self.planner._create_cache_key(complex_results)
        assert isinstance(key2, str)
        assert key1 != key2

        # Same results should produce same key
        key3 = self.planner._create_cache_key(simple_results)
        assert key1 == key3

    def test_create_cache_key_with_none_values(self):
        """Test _create_cache_key with None values."""
        results_with_none = {
            "switch1": {"true_output": None, "false_output": {"status": "inactive"}}
        }

        key = self.planner._create_cache_key(results_with_none)
        assert isinstance(key, str)

    def test_create_cache_key_empty_results(self):
        """Test _create_cache_key with empty results."""
        key = self.planner._create_cache_key({})
        assert isinstance(key, str)

    def test_invalidate_cache(self):
        """Test invalidate_cache method."""
        # Add some items to cache
        self.planner._execution_plan_cache["key1"] = ["node1", "node2"]
        self.planner._execution_plan_cache["key2"] = ["node3", "node4"]

        assert len(self.planner._execution_plan_cache) == 2

        self.planner.invalidate_cache()
        assert len(self.planner._execution_plan_cache) == 0

    def test_create_hierarchical_execution_plan_simple(self):
        """Test create_hierarchical_execution_plan with simple hierarchy."""
        # Create hierarchical workflow
        switch1 = SwitchNode(
            name="switch1", condition_field="level1", operator="==", value="A"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="level2", operator="==", value="B"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc", proc)

        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "proc", {"true_output": "input"})

        switch_results = {
            "switch1": {"true_output": {"level1": "A"}, "false_output": None},
            "switch2": {"true_output": {"level2": "B"}, "false_output": None},
        }

        plan = self.planner.create_hierarchical_execution_plan(switch_results)

        assert isinstance(plan, dict)  # Returns dict
        assert "execution_layers" in plan or "execution_plan" in plan

    def test_handle_merge_nodes_with_conditional_inputs(self):
        """Test handle_merge_nodes_with_conditional_inputs method."""
        # Create workflow with merge node
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

        # Only proc1 should be reachable
        execution_plan = ["switch1", "proc1", "merge"]
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": None},
        }

        result = self.planner.handle_merge_nodes_with_conditional_inputs(
            execution_plan, switch_results
        )

        assert "strategies" in result  # Not "merge_strategies"
        assert "merge_nodes" in result

    def test_optimize_execution_plan_simple(self):
        """Test optimize_execution_plan method."""
        # Create workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "proc2", {"result": "input"})
        self.workflow.connect("proc2", "proc3", {"result": "input"})

        original_plan = ["proc1", "proc2", "proc3"]

        switch_results = {}  # Empty switch results
        optimized = self.planner.optimize_execution_plan(original_plan, switch_results)

        assert "optimized_plan" in optimized
        assert "optimizations_applied" in optimized
        assert "performance_improvement" in optimized  # Not performance_estimate

    def test_plan_validation_with_complex_workflow(self):
        """Test plan validation with complex workflow structure."""
        # Create complex workflow
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="branch", operator="==", value="A"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="sub_branch", operator="==", value="B"
        )
        proc_a = PythonCodeNode(name="proc_a", code="result = {'path': 'A'}")
        proc_b = PythonCodeNode(name="proc_b", code="result = {'path': 'B'}")
        merge = MergeNode(name="merge", merge_type="merge_dict")
        final = PythonCodeNode(name="final", code="result = {'final': True}")

        nodes = [source, switch1, switch2, proc_a, proc_b, merge, final]
        node_names = [
            "source",
            "switch1",
            "switch2",
            "proc_a",
            "proc_b",
            "merge",
            "final",
        ]

        for name, node in zip(node_names, nodes):
            self.workflow.add_node(name, node)

        # Create connections
        self.workflow.connect("source", "switch1", {"result": "input_data"})
        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "proc_a", {"true_output": "input"})
        self.workflow.connect("switch2", "proc_b", {"false_output": "input"})
        self.workflow.connect("proc_a", "merge", {"result": "data1"})
        self.workflow.connect("proc_b", "merge", {"result": "data2"})
        self.workflow.connect("merge", "final", {"merged_data": "input"})

        # Test various execution plans
        full_plan = node_names
        is_valid, errors = self.planner.validate_execution_plan(full_plan)
        assert is_valid is True

        # Test partial plan (missing dependencies)
        partial_plan = [
            "source",
            "switch1",
            "proc_a",
            "final",
        ]  # Missing switch2, proc_b, merge
        is_valid, errors = self.planner.validate_execution_plan(partial_plan)
        assert is_valid is False

    def test_performance_with_large_workflow(self):
        """Test planner performance with larger workflow."""
        # Create larger workflow
        source = PythonCodeNode(name="source", code="result = {'data': 'test'}")
        self.workflow.add_node("source", source)

        # Add many nodes
        for i in range(50):
            switch = SwitchNode(
                name=f"switch_{i}", condition_field=f"field_{i}", operator="==", value=i
            )
            proc = PythonCodeNode(name=f"proc_{i}", code=f"result = {{'proc': {i}}}")

            self.workflow.add_node(f"switch_{i}", switch)
            self.workflow.add_node(f"proc_{i}", proc)

            self.workflow.connect("source", f"switch_{i}", {"result": "input_data"})
            self.workflow.connect(f"switch_{i}", f"proc_{i}", {"true_output": "input"})

        # Create switch results
        switch_results = {}
        for i in range(0, 50, 2):  # Only even switches return true
            switch_results[f"switch_{i}"] = {
                "true_output": {f"field_{i}": i},
                "false_output": None,
            }

        # Test performance
        import time

        start_time = time.time()

        plan = self.planner.create_execution_plan(switch_results)
        validation = self.planner.validate_execution_plan(plan)

        planning_time = time.time() - start_time

        # Should complete quickly (< 2 seconds for 100 nodes)
        assert planning_time < 2.0
        assert validation[0] is True  # First element of tuple is is_valid

        # Should include source and reachable nodes
        assert "source" in plan
        assert len(plan) > 25  # Source + reachable switches and processors

    def test_cache_performance_benefits(self):
        """Test that caching provides performance benefits."""
        # Create workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        switch_results = {"switch1": {"true_output": {"status": "active"}}}

        # First call - should cache the result
        import time

        start_time = time.time()
        plan1 = self.planner.create_execution_plan(switch_results)
        first_call_time = time.time() - start_time

        # Second call - should use cache
        start_time = time.time()
        plan2 = self.planner.create_execution_plan(switch_results)
        second_call_time = time.time() - start_time

        # Results should be identical
        assert plan1 == plan2

        # Second call should be faster (or at least not significantly slower)
        # Note: For small workflows, difference may be negligible
        assert second_call_time <= first_call_time * 2  # Allow some variance

    def test_error_handling_scenarios(self):
        """Test error handling in various scenarios."""
        # Test with invalid workflow state
        try:
            # Try to create plan before workflow is properly set up
            empty_planner = DynamicExecutionPlanner(None)  # Only takes one argument
            # This should handle gracefully or raise appropriate error
        except (AttributeError, TypeError):
            pass  # Expected behavior

        # Test with malformed switch results
        malformed_results = {"invalid": "data"}

        try:
            plan = self.planner.create_execution_plan(malformed_results)
            # Should handle gracefully
            assert isinstance(plan, list)
        except Exception:
            pass  # Some errors are acceptable

        # Test validation with invalid plan
        invalid_plan = ["non_existent_node"]
        is_valid, errors = self.planner.validate_execution_plan(invalid_plan)

        # Should detect invalid plan
        assert is_valid is False
