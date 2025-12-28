"""
Unit tests for DynamicExecutionPlanner.

Tests execution plan generation functionality including:
- Pruned execution plan creation based on SwitchNode results
- Dependency analysis for SwitchNode execution ordering
- Branch pruning algorithms
- Plan validation and optimization
- Complex workflow pattern handling
"""

from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.workflow.graph import Workflow


class TestDynamicExecutionPlanner:
    """Test DynamicExecutionPlanner functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test_workflow", "Test Execution Planning")
        self.planner = DynamicExecutionPlanner(self.workflow)

    def test_planner_initialization(self):
        """Test DynamicExecutionPlanner initialization."""
        assert self.planner.workflow == self.workflow
        assert isinstance(self.planner.analyzer, ConditionalBranchAnalyzer)
        assert self.planner._execution_plan_cache is not None

    def test_create_execution_plan_empty_workflow(self):
        """Test create_execution_plan with empty workflow."""
        switch_results = {}

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert execution_plan == []

    def test_create_execution_plan_no_switches(self):
        """Test create_execution_plan with workflow containing no switches."""
        # Add regular nodes only
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        switch_results = {}

        execution_plan = self.planner.create_execution_plan(switch_results)

        # Should include all nodes since no conditional routing
        assert "proc1" in execution_plan
        assert "proc2" in execution_plan
        assert len(execution_plan) == 2

    def test_create_execution_plan_simple_true_branch(self):
        """Test create_execution_plan with simple true branch execution."""
        # Create simple conditional workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")
        false_proc = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.add_node("false_proc", false_proc)

        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        # Switch results indicating true branch execution
        switch_results = {
            "switch1": {"true_output": {"data": "processed"}, "false_output": None}
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "switch1" in execution_plan
        assert "true_proc" in execution_plan
        assert "false_proc" not in execution_plan

    def test_create_execution_plan_simple_false_branch(self):
        """Test create_execution_plan with simple false branch execution."""
        # Create simple conditional workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")
        false_proc = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.add_node("false_proc", false_proc)

        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        # Switch results indicating false branch execution
        switch_results = {
            "switch1": {"true_output": None, "false_output": {"data": "processed"}}
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "switch1" in execution_plan
        assert "true_proc" not in execution_plan
        assert "false_proc" in execution_plan

    def test_create_execution_plan_cascading_switches(self):
        """Test create_execution_plan with cascading switches."""
        # Create cascading workflow: switch1 -> switch2 -> processor
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="status", operator="equals", value="active"
        )
        final_proc = PythonCodeNode(name="final_proc", code="result = {'final': True}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("final_proc", final_proc)

        self.workflow.connect("switch1", "switch2", {"true_output": "input"})
        self.workflow.connect("switch2", "final_proc", {"true_output": "input"})

        # Both switches execute true branch
        switch_results = {
            "switch1": {"true_output": {"type": "premium"}, "false_output": None},
            "switch2": {"true_output": {"status": "active"}, "false_output": None},
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "switch1" in execution_plan
        assert "switch2" in execution_plan
        assert "final_proc" in execution_plan

    def test_create_execution_plan_blocked_cascade(self):
        """Test create_execution_plan with blocked cascade."""
        # Create cascading workflow
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="status", operator="equals", value="active"
        )
        final_proc = PythonCodeNode(name="final_proc", code="result = {'final': True}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("final_proc", final_proc)

        self.workflow.connect("switch1", "switch2", {"true_output": "input"})
        self.workflow.connect("switch2", "final_proc", {"true_output": "input"})

        # Switch1 false blocks switch2 execution
        switch_results = {
            "switch1": {"true_output": None, "false_output": {"type": "basic"}}
            # switch2 never executed due to blocked path
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "switch1" in execution_plan
        assert "switch2" not in execution_plan
        assert "final_proc" not in execution_plan

    def test_create_execution_plan_parallel_switches(self):
        """Test create_execution_plan with parallel switches."""
        # Create parallel conditional branches
        source = PythonCodeNode(name="source", code="result = {'data': 'input'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="region", operator="equals", value="US"
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'proc': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'proc': 2}")

        self.workflow.add_node("source", source)
        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        # Create parallel branches
        self.workflow.connect("source", "switch1", {"result": "input"})
        self.workflow.connect("source", "switch2", {"result": "input"})
        self.workflow.connect("switch1", "proc1", {"true_output": "input"})
        self.workflow.connect("switch2", "proc2", {"true_output": "input"})

        # Both switches execute true branch
        switch_results = {
            "switch1": {"true_output": {"type": "premium"}, "false_output": None},
            "switch2": {"true_output": {"region": "US"}, "false_output": None},
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "source" in execution_plan
        assert "switch1" in execution_plan
        assert "switch2" in execution_plan
        assert "proc1" in execution_plan
        assert "proc2" in execution_plan

    def test_analyze_dependencies_simple(self):
        """Test _analyze_dependencies with simple switch dependency."""
        # Create simple dependency: switch1 -> switch2
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="status", operator="equals", value="active"
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.connect("switch1", "switch2", {"true_output": "input"})

        dependencies = self.planner._analyze_dependencies()

        # switch2 should depend on switch1
        assert "switch1" in dependencies
        assert "switch2" in dependencies
        assert dependencies["switch2"] == ["switch1"]
        assert dependencies["switch1"] == []

    def test_analyze_dependencies_parallel(self):
        """Test _analyze_dependencies with parallel switches."""
        # Create parallel switches (no dependencies)
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="region", operator="equals", value="US"
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)

        dependencies = self.planner._analyze_dependencies()

        # Both switches should be independent
        assert "switch1" in dependencies
        assert "switch2" in dependencies
        assert dependencies["switch1"] == []
        assert dependencies["switch2"] == []

    def test_analyze_dependencies_complex(self):
        """Test _analyze_dependencies with complex dependency graph."""
        # Create complex dependency: switch1 -> switch2, switch3 -> switch2
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="equals", value=3
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("switch3", switch3)

        self.workflow.connect("switch1", "switch2", {"true_output": "input1"})
        self.workflow.connect("switch3", "switch2", {"true_output": "input2"})

        dependencies = self.planner._analyze_dependencies()

        # switch2 should depend on both switch1 and switch3
        assert "switch2" in dependencies
        assert "switch1" in dependencies["switch2"]
        assert "switch3" in dependencies["switch2"]
        assert dependencies["switch1"] == []
        assert dependencies["switch3"] == []

    def test_prune_unreachable_branches_simple(self):
        """Test _prune_unreachable_branches with simple pruning."""
        # Create workflow with reachable and unreachable branches
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        true_proc = PythonCodeNode(name="true_proc", code="result = {'branch': 'true'}")
        false_proc = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_proc)
        self.workflow.add_node("false_proc", false_proc)

        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        # Define reachable nodes (true branch only)
        reachable_nodes = {"switch1", "true_proc"}
        all_nodes = ["switch1", "true_proc", "false_proc"]

        pruned_plan = self.planner._prune_unreachable_branches(
            all_nodes, reachable_nodes
        )

        assert "switch1" in pruned_plan
        assert "true_proc" in pruned_plan
        assert "false_proc" not in pruned_plan

    def test_prune_unreachable_branches_preserves_order(self):
        """Test _prune_unreachable_branches preserves topological order."""
        # Create ordered workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")
        proc3 = PythonCodeNode(name="proc3", code="result = {'step': 3}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("proc3", proc3)

        self.workflow.connect("proc1", "switch1", {"result": "input"})
        self.workflow.connect("switch1", "proc2", {"true_output": "input"})
        self.workflow.connect("switch1", "proc3", {"false_output": "input"})

        # All nodes are reachable
        reachable_nodes = {"proc1", "switch1", "proc2", "proc3"}
        all_nodes = ["proc1", "switch1", "proc2", "proc3"]

        pruned_plan = self.planner._prune_unreachable_branches(
            all_nodes, reachable_nodes
        )

        # Order should be preserved
        assert pruned_plan.index("proc1") < pruned_plan.index("switch1")
        assert pruned_plan.index("switch1") < pruned_plan.index("proc2")
        assert pruned_plan.index("switch1") < pruned_plan.index("proc3")

    def test_validate_execution_plan_valid(self):
        """Test validate_execution_plan with valid plan."""
        # Create simple workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        execution_plan = ["proc1", "proc2"]

        is_valid, errors = self.planner.validate_execution_plan(execution_plan)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_execution_plan_missing_dependency(self):
        """Test validate_execution_plan with missing dependency."""
        # Create workflow with dependency
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'step': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        # Invalid plan - proc2 without proc1
        execution_plan = ["proc2"]

        is_valid, errors = self.planner.validate_execution_plan(execution_plan)

        assert is_valid is False
        assert len(errors) > 0
        assert any("dependency" in error.lower() for error in errors)

    def test_validate_execution_plan_invalid_node(self):
        """Test validate_execution_plan with invalid node reference."""
        # Create simple workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'step': 1}")
        self.workflow.add_node("proc1", proc1)

        # Plan with non-existent node
        execution_plan = ["proc1", "nonexistent_node"]

        is_valid, errors = self.planner.validate_execution_plan(execution_plan)

        assert is_valid is False
        assert len(errors) > 0
        assert any("nonexistent_node" in error for error in errors)

    def test_execution_plan_caching(self):
        """Test execution plan caching for performance."""
        # Create workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 'processed'}")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("proc", proc)
        self.workflow.connect("switch1", "proc", {"true_output": "input"})

        switch_results = {
            "switch1": {"true_output": {"data": "processed"}, "false_output": None}
        }

        # First call should cache result
        plan1 = self.planner.create_execution_plan(switch_results)

        # Second call with same results should use cache
        plan2 = self.planner.create_execution_plan(switch_results)

        assert plan1 == plan2
        # Verify cache was used (specific implementation dependent)

    def test_execution_plan_cache_invalidation(self):
        """Test execution plan cache invalidation."""
        # Create initial workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 'processed'}")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("proc", proc)
        self.workflow.connect("switch1", "proc", {"true_output": "input"})

        switch_results = {
            "switch1": {"true_output": {"data": "processed"}, "false_output": None}
        }

        # Create initial plan
        plan1 = self.planner.create_execution_plan(switch_results)

        # Modify workflow (should invalidate cache)
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 'processed2'}")
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("switch1", "proc2", {"false_output": "input"})

        # Force cache invalidation
        self.planner.invalidate_cache()

        # Create new plan with different results
        switch_results_2 = {
            "switch1": {"true_output": None, "false_output": {"data": "processed"}}
        }

        plan2 = self.planner.create_execution_plan(switch_results_2)

        assert "proc2" in plan2
        assert plan1 != plan2

    def test_multi_case_switch_planning(self):
        """Test execution planning with multi-case switches."""
        # Create multi-case switch workflow
        switch_node = SwitchNode(
            name="multi_switch",
            condition_field="type",
            operator="switch",
            cases={
                "premium": "premium_proc",
                "basic": "basic_proc",
                "trial": "trial_proc",
            },
        )

        proc1 = PythonCodeNode(name="premium_proc", code="result = {'type': 'premium'}")
        proc2 = PythonCodeNode(name="basic_proc", code="result = {'type': 'basic'}")
        proc3 = PythonCodeNode(name="trial_proc", code="result = {'type': 'trial'}")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("premium_proc", proc1)
        self.workflow.add_node("basic_proc", proc2)
        self.workflow.add_node("trial_proc", proc3)

        self.workflow.connect("switch1", "premium_proc", {"case_premium": "input"})
        self.workflow.connect("switch1", "basic_proc", {"case_basic": "input"})
        self.workflow.connect("switch1", "trial_proc", {"case_trial": "input"})

        # Test premium case execution
        switch_results = {
            "switch1": {
                "case_premium": {"type": "premium"},
                "case_basic": None,
                "case_trial": None,
            }
        }

        execution_plan = self.planner.create_execution_plan(switch_results)

        assert "switch1" in execution_plan
        assert "premium_proc" in execution_plan
        assert "basic_proc" not in execution_plan
        assert "trial_proc" not in execution_plan


class TestDynamicExecutionPlannerComplexScenarios:
    """Test complex scenarios for DynamicExecutionPlanner."""

    def test_merge_node_handling(self):
        """Test execution planning with merge nodes."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create conditional branches that merge
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 'a'}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 'b'}")
        merge = MergeNode(name="merge", merge_type="merge_dict")
        final = PythonCodeNode(name="final", code="result = {'final': True}")

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("proc1", proc1)
        workflow.add_node("proc2", proc2)
        workflow.add_node("merge", merge)
        workflow.add_node("final", final)

        workflow.connect("switch1", "proc1", {"true_output": "input"})
        workflow.connect("switch2", "proc2", {"true_output": "input"})
        workflow.connect("proc1", "merge", {"result": "data1"})
        workflow.connect("proc2", "merge", {"result": "data2"})
        workflow.connect("merge", "final", {"merged_data": "input"})

        # Both switches execute true branch
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": {"b": 2}, "false_output": None},
        }

        execution_plan = planner.create_execution_plan(switch_results)

        # All nodes should be included
        assert all(
            node in execution_plan
            for node in ["switch1", "switch2", "proc1", "proc2", "merge", "final"]
        )

    def test_partial_merge_node_handling(self):
        """Test execution planning with partial merge inputs."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create conditional branches that partially merge
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 'a'}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 'b'}")
        merge = MergeNode(name="merge", merge_type="merge_dict")

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("proc1", proc1)
        workflow.add_node("proc2", proc2)
        workflow.add_node("merge", merge)

        workflow.connect("switch1", "proc1", {"true_output": "input"})
        workflow.connect("switch2", "proc2", {"true_output": "input"})
        workflow.connect("proc1", "merge", {"result": "data1"})
        workflow.connect("proc2", "merge", {"result": "data2"})

        # Only switch1 executes true branch, switch2 false
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": {"b": 0}},
        }

        execution_plan = planner.create_execution_plan(switch_results)

        # Only proc1 branch should be included, but merge should still execute
        assert "switch1" in execution_plan
        assert "switch2" in execution_plan
        assert "proc1" in execution_plan
        assert "proc2" not in execution_plan
        assert "merge" in execution_plan  # Merge can handle partial inputs

    def test_cyclic_conditional_execution(self):
        """Test execution planning with cycles containing switches."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create cycle with internal switch
        counter = PythonCodeNode(name="counter", code="result = {'count': count + 1}")
        switch = SwitchNode(
            name="continue_switch",
            condition_field="count",
            operator="less_than",
            value=5,
        )

        workflow.add_node("counter", counter)
        workflow.add_node("continue_switch", switch)

        # Create cycle
        workflow.connect("counter", "continue_switch", {"result": "input"})
        workflow.create_cycle("count_cycle").connect(
            "continue_switch", "counter", {"true_output": "input"}
        ).max_iterations(10).build()

        # Switch indicates continuation
        switch_results = {
            "continue_switch": {"true_output": {"count": 3}, "false_output": None}
        }

        execution_plan = planner.create_execution_plan(switch_results)

        # For cycles, both nodes should be included (cycles execute fully)
        assert "counter" in execution_plan
        assert "continue_switch" in execution_plan

    def test_hierarchical_switch_dependencies(self):
        """Test execution planning with hierarchical switch dependencies."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create hierarchy: source -> switch1 -> switch2 -> switch3 -> final
        source = PythonCodeNode(name="source", code="result = {'data': 'input'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="c", operator="equals", value=3
        )
        final = PythonCodeNode(name="final", code="result = {'final': True}")

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("switch3", switch3)
        workflow.add_node("final", final)

        workflow.connect("source", "switch1", {"result": "input"})
        workflow.connect("switch1", "switch2", {"true_output": "input"})
        workflow.connect("switch2", "switch3", {"true_output": "input"})
        workflow.connect("switch3", "final", {"true_output": "input"})

        # All switches execute true branch
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": {"b": 2}, "false_output": None},
            "switch3": {"true_output": {"c": 3}, "false_output": None},
        }

        execution_plan = planner.create_execution_plan(switch_results)

        # All nodes should be included
        expected_nodes = ["source", "switch1", "switch2", "switch3", "final"]
        assert all(node in execution_plan for node in expected_nodes)

        # Order should be preserved
        for i in range(len(expected_nodes) - 1):
            assert execution_plan.index(expected_nodes[i]) < execution_plan.index(
                expected_nodes[i + 1]
            )

    def test_performance_optimization_large_workflow(self):
        """Test performance optimization with large workflow."""
        workflow = Workflow("large_test", "Large Performance Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create large workflow with complex conditional structure
        source = PythonCodeNode(name="source", code="result = {'data': 'input'}")
        workflow.add_node("source", source)

        # Create 20 switches each with 5 processing nodes
        for i in range(20):
            switch = SwitchNode(
                name=f"switch_{i}",
                condition_field=f"field_{i}",
                operator="equals",
                value=i,
            )
            workflow.add_node(f"switch_{i}", switch)
            workflow.connect("source", f"switch_{i}", {"result": "input"})

            for j in range(5):
                proc = PythonCodeNode(
                    name=f"proc_{i}_{j}", code=f"result = {{'proc': {i}, 'sub': {j}}}"
                )
                workflow.add_node(f"proc_{i}_{j}", proc)
                workflow.connect(
                    f"switch_{i}", f"proc_{i}_{j}", {"true_output": "input"}
                )

        # Only execute switches 0, 5, 10, 15 (25% execution)
        switch_results = {}
        for i in range(20):
            if i % 5 == 0:
                switch_results[f"switch_{i}"] = {
                    "true_output": {f"field_{i}": i},
                    "false_output": None,
                }
            else:
                switch_results[f"switch_{i}"] = {
                    "true_output": None,
                    "false_output": {f"field_{i}": -1},
                }

        # Performance test - should complete quickly
        import time

        start_time = time.time()

        execution_plan = planner.create_execution_plan(switch_results)

        execution_time = time.time() - start_time

        # Should include source + 4 switches + 20 processors (4 * 5)
        expected_count = 1 + 20 + 20  # source + all switches + 20 processors
        assert len(execution_plan) == expected_count

        # Performance should be reasonable
        assert execution_time < 2.0  # Should complete in under 2 seconds

        # Verify only correct processors are included
        executed_processors = [node for node in execution_plan if "proc_" in node]
        assert len(executed_processors) == 20  # 4 switches * 5 processors each

    def test_error_handling_invalid_switch_results(self):
        """Test error handling with invalid switch results."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create simple workflow
        switch = SwitchNode(
            name="switch", condition_field="a", operator="equals", value=1
        )
        workflow.add_node("switch1", switch)

        # Test with invalid switch results format
        invalid_results = [
            None,
            {"switch1": None},
            {"switch1": "invalid"},
            {"nonexistent_switch": {"true_output": {}}},
            {"switch1": {"invalid_output": {}}},
        ]

        for invalid_result in invalid_results:
            try:
                execution_plan = planner.create_execution_plan(invalid_result)
                # Should handle gracefully, possibly returning empty plan or default behavior
                assert isinstance(execution_plan, list)
            except Exception as e:
                # Exceptions should be meaningful
                assert isinstance(e, (ValueError, KeyError, TypeError))

    def test_plan_optimization_duplicate_removal(self):
        """Test execution plan optimization removes duplicates."""
        workflow = Workflow("test", "Test")
        planner = DynamicExecutionPlanner(workflow)

        # Create workflow where same node could be reached via multiple paths
        source = PythonCodeNode(name="source", code="result = {'data': 'input'}")
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        shared_proc = PythonCodeNode(name="shared", code="result = {'shared': True}")

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("shared", shared_proc)

        # Both switches can reach shared processor
        workflow.connect("source", "switch1", {"result": "input"})
        workflow.connect("source", "switch2", {"result": "input"})
        workflow.connect("switch1", "shared", {"true_output": "input"})
        workflow.connect("switch2", "shared", {"true_output": "input"})

        # Both switches execute true branch
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": {"b": 2}, "false_output": None},
        }

        execution_plan = planner.create_execution_plan(switch_results)

        # shared_proc should appear only once despite multiple paths
        shared_count = execution_plan.count("shared")
        assert shared_count == 1
