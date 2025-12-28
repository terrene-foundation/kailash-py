"""
Unit tests for ConditionalBranchAnalyzer.

Tests conditional branch analysis functionality including:
- SwitchNode detection and classification
- Branch mapping and dependency analysis
- Reachable node identification
- Complex pattern recognition
- Edge case handling (cycles, multiple switches, merge nodes)
"""

from unittest.mock import Mock, patch

import networkx as nx
import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.workflow.graph import Workflow


class TestConditionalBranchAnalyzer:
    """Test ConditionalBranchAnalyzer functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test_workflow", "Test Conditional Analysis")
        self.analyzer = ConditionalBranchAnalyzer(self.workflow)

    def test_analyzer_initialization(self):
        """Test ConditionalBranchAnalyzer initialization."""
        assert self.analyzer.workflow == self.workflow
        assert self.analyzer._branch_map is None
        assert self.analyzer._switch_nodes is None

    def test_find_switch_nodes_empty_workflow(self):
        """Test _find_switch_nodes with empty workflow."""
        switch_nodes = self.analyzer._find_switch_nodes()
        assert switch_nodes == []

    def test_find_switch_nodes_single_switch(self):
        """Test _find_switch_nodes with single SwitchNode."""
        # Add SwitchNode to workflow
        switch_node = SwitchNode(
            name="test_switch",
            condition_field="status",
            operator="equals",
            value="active",
        )
        self.workflow.add_node("switch1", switch_node)

        switch_nodes = self.analyzer._find_switch_nodes()
        assert len(switch_nodes) == 1
        assert "switch1" in switch_nodes

    def test_find_switch_nodes_multiple_switches(self):
        """Test _find_switch_nodes with multiple SwitchNodes."""
        # Add multiple SwitchNodes
        switch1 = SwitchNode(
            name="switch1", condition_field="status", operator="equals", value="active"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="type", operator="equals", value="premium"
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)

        switch_nodes = self.analyzer._find_switch_nodes()
        assert len(switch_nodes) == 2
        assert "switch1" in switch_nodes
        assert "switch2" in switch_nodes

    def test_find_switch_nodes_mixed_nodes(self):
        """Test _find_switch_nodes with mixed node types."""
        # Add SwitchNode and regular nodes
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        python_node = PythonCodeNode(
            name="processor", code="result = {'processed': True}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("processor", python_node)

        switch_nodes = self.analyzer._find_switch_nodes()
        assert len(switch_nodes) == 1
        assert "switch1" in switch_nodes
        assert "processor" not in switch_nodes

    def test_build_branch_map_single_switch(self):
        """Test _build_branch_map with single SwitchNode."""
        # Create simple conditional workflow
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        true_processor = PythonCodeNode(
            name="true_proc", code="result = {'branch': 'true'}"
        )
        false_processor = PythonCodeNode(
            name="false_proc", code="result = {'branch': 'false'}"
        )

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("true_proc", true_processor)
        self.workflow.add_node("false_proc", false_processor)

        # Connect switch to processors
        self.workflow.connect("switch1", "true_proc", {"true_output": "input"})
        self.workflow.connect("switch1", "false_proc", {"false_output": "input"})

        branch_map = self.analyzer._build_branch_map()

        assert "switch1" in branch_map
        switch_branches = branch_map["switch1"]
        assert "true_output" in switch_branches
        assert "false_output" in switch_branches
        assert "true_proc" in switch_branches["true_output"]
        assert "false_proc" in switch_branches["false_output"]

    def test_build_branch_map_cascading_switches(self):
        """Test _build_branch_map with cascading SwitchNodes."""
        # Create cascading conditional workflow: Switch1 -> Switch2 -> Processors
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="status", operator="equals", value="active"
        )
        processor = PythonCodeNode(name="final_proc", code="result = {'final': True}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("final_proc", processor)

        # Connect: switch1 -> switch2 -> processor
        self.workflow.connect("switch1", "switch2", {"true_output": "input"})
        self.workflow.connect("switch2", "final_proc", {"true_output": "input"})

        branch_map = self.analyzer._build_branch_map()

        assert "switch1" in branch_map
        assert "switch2" in branch_map
        assert "switch2" in branch_map["switch1"]["true_output"]
        assert "final_proc" in branch_map["switch2"]["true_output"]

    def test_build_branch_map_parallel_switches(self):
        """Test _build_branch_map with parallel SwitchNodes."""
        # Create parallel conditional branches
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="region", operator="equals", value="US"
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'proc': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'proc': 2}")

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)

        # Create parallel branches
        self.workflow.connect("switch1", "proc1", {"true_output": "input"})
        self.workflow.connect("switch2", "proc2", {"true_output": "input"})

        branch_map = self.analyzer._build_branch_map()

        assert len(branch_map) == 2
        assert "switch1" in branch_map
        assert "switch2" in branch_map
        assert "proc1" in branch_map["switch1"]["true_output"]
        assert "proc2" in branch_map["switch2"]["true_output"]

    def test_get_reachable_nodes_simple_case(self):
        """Test get_reachable_nodes with simple switch results."""
        # Setup simple conditional workflow
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

        # Test true branch reachability
        switch_results = {
            "switch1": {"true_output": {"data": "processed"}, "false_output": None}
        }

        reachable = self.analyzer.get_reachable_nodes(switch_results)

        assert "switch1" in reachable
        assert "true_proc" in reachable
        assert "false_proc" not in reachable

    def test_get_reachable_nodes_false_branch(self):
        """Test get_reachable_nodes with false branch execution."""
        # Setup simple conditional workflow
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

        # Test false branch reachability
        switch_results = {
            "switch1": {"true_output": None, "false_output": {"data": "processed"}}
        }

        reachable = self.analyzer.get_reachable_nodes(switch_results)

        assert "switch1" in reachable
        assert "true_proc" not in reachable
        assert "false_proc" in reachable

    def test_get_reachable_nodes_cascading(self):
        """Test get_reachable_nodes with cascading conditions."""
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

        # Test cascading true path
        switch_results = {
            "switch1": {"true_output": {"type": "premium"}, "false_output": None},
            "switch2": {"true_output": {"status": "active"}, "false_output": None},
        }

        reachable = self.analyzer.get_reachable_nodes(switch_results)

        assert "switch1" in reachable
        assert "switch2" in reachable
        assert "final_proc" in reachable

    def test_get_reachable_nodes_blocked_cascade(self):
        """Test get_reachable_nodes with blocked cascade (first switch false)."""
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

        # Test blocked cascade (switch1 false blocks switch2)
        switch_results = {
            "switch1": {"true_output": None, "false_output": {"type": "basic"}}
            # switch2 not executed because switch1 blocked it
        }

        reachable = self.analyzer.get_reachable_nodes(switch_results)

        assert "switch1" in reachable
        assert "switch2" not in reachable
        assert "final_proc" not in reachable

    def test_detect_conditional_patterns_simple(self):
        """Test detect_conditional_patterns with simple pattern."""
        # Create simple conditional pattern
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        self.workflow.add_node("switch1", switch_node)

        patterns = self.analyzer.detect_conditional_patterns()

        assert "single_switch" in patterns
        assert patterns["single_switch"] == ["switch1"]
        assert patterns["total_switches"] == 1
        assert not patterns["has_cycles"]

    def test_detect_conditional_patterns_multiple(self):
        """Test detect_conditional_patterns with multiple switches."""
        # Create multiple switches
        switch1 = SwitchNode(
            name="switch1", condition_field="type", operator="equals", value="premium"
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="status", operator="equals", value="active"
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.connect("switch1", "switch2", {"true_output": "input"})

        patterns = self.analyzer.detect_conditional_patterns()

        assert patterns["total_switches"] == 2
        assert "cascading_switches" in patterns
        assert len(patterns["cascading_switches"]) > 0

    def test_detect_conditional_patterns_with_cycles(self):
        """Test detect_conditional_patterns with cycles."""
        # Create conditional pattern with cycle
        switch_node = SwitchNode(
            name="switch", condition_field="continue", operator="equals", value=True
        )
        self.workflow.add_node("switch1", switch_node)

        # Create cycle by connecting switch back to itself
        self.workflow.create_cycle("test_cycle").connect(
            "switch1", "switch1", {"true_output": "input"}
        ).max_iterations(5).build()

        patterns = self.analyzer.detect_conditional_patterns()

        assert patterns["has_cycles"]
        assert "cyclic_conditional" in patterns

    def test_detect_conditional_patterns_with_merge(self):
        """Test detect_conditional_patterns with merge nodes."""
        # Create conditional pattern with merge
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        merge_node = MergeNode(name="merge", merge_type="merge_dict")

        self.workflow.add_node("switch1", switch_node)
        self.workflow.add_node("merge1", merge_node)

        patterns = self.analyzer.detect_conditional_patterns()

        assert "merge_nodes" in patterns
        assert "merge1" in patterns["merge_nodes"]

    def test_error_handling_invalid_workflow(self):
        """Test error handling with invalid workflow structure."""
        # Test with corrupted workflow graph
        self.workflow.graph = None

        # Should handle gracefully and return empty list
        switch_nodes = self.analyzer._find_switch_nodes()
        assert switch_nodes == []

    def test_error_handling_missing_node_data(self):
        """Test error handling with missing node data."""
        # Add node without proper instance
        self.workflow.graph.add_node("invalid_node")

        switch_nodes = self.analyzer._find_switch_nodes()
        assert "invalid_node" not in switch_nodes

    def test_caching_behavior(self):
        """Test that results are cached for performance."""
        # Add switch node
        switch_node = SwitchNode(
            name="switch", condition_field="status", operator="equals", value="active"
        )
        self.workflow.add_node("switch1", switch_node)

        # First call should compute and cache
        switch_nodes1 = self.analyzer._find_switch_nodes()
        branch_map1 = self.analyzer._build_branch_map()

        # Second call should use cache
        switch_nodes2 = self.analyzer._find_switch_nodes()
        branch_map2 = self.analyzer._build_branch_map()

        assert switch_nodes1 == switch_nodes2
        assert branch_map1 == branch_map2
        assert self.analyzer._switch_nodes is not None
        assert self.analyzer._branch_map is not None

    def test_cache_invalidation(self):
        """Test cache invalidation when workflow changes."""
        # Add initial switch
        switch1 = SwitchNode(
            name="switch1", condition_field="status", operator="equals", value="active"
        )
        self.workflow.add_node("switch1", switch1)

        # Cache initial state
        switch_nodes1 = self.analyzer._find_switch_nodes()
        assert len(switch_nodes1) == 1

        # Add another switch (should invalidate cache)
        switch2 = SwitchNode(
            name="switch2", condition_field="type", operator="equals", value="premium"
        )
        self.workflow.add_node("switch2", switch2)

        # Force cache invalidation
        self.analyzer._switch_nodes = None
        self.analyzer._branch_map = None

        # Re-analyze should find both switches
        switch_nodes2 = self.analyzer._find_switch_nodes()
        assert len(switch_nodes2) == 2


class TestConditionalBranchAnalyzerEdgeCases:
    """Test edge cases for ConditionalBranchAnalyzer."""

    def test_empty_switch_outputs(self):
        """Test handling of SwitchNode with no outputs."""
        workflow = Workflow("test", "Test")
        analyzer = ConditionalBranchAnalyzer(workflow)

        # SwitchNode with no connections
        switch_node = SwitchNode(
            name="isolated_switch",
            condition_field="status",
            operator="equals",
            value="active",
        )
        workflow.add_node("switch1", switch_node)

        branch_map = analyzer._build_branch_map()

        assert "switch1" in branch_map
        assert len(branch_map["switch1"]) == 0

    def test_circular_switch_dependencies(self):
        """Test detection of circular switch dependencies."""
        workflow = Workflow("test", "Test")
        analyzer = ConditionalBranchAnalyzer(workflow)

        # Create circular dependency: switch1 -> switch2 -> switch1
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.connect("switch1", "switch2", {"true_output": "input"})
        workflow.connect("switch2", "switch1", {"true_output": "input"})

        patterns = analyzer.detect_conditional_patterns()

        assert patterns["has_cycles"]
        assert "circular_switches" in patterns

    def test_complex_merge_scenarios(self):
        """Test complex merge node scenarios."""
        workflow = Workflow("test", "Test")
        analyzer = ConditionalBranchAnalyzer(workflow)

        # Create complex merge scenario
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="equals", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="equals", value=2
        )
        merge1 = MergeNode(name="merge1", merge_type="merge_dict")
        merge2 = MergeNode(name="merge2", merge_type="concat")

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("merge1", merge1)
        workflow.add_node("merge2", merge2)

        # Complex connections
        workflow.connect("switch1", "merge1", {"true_output": "data1"})
        workflow.connect("switch2", "merge1", {"true_output": "data2"})
        workflow.connect("merge1", "merge2", {"merged_data": "data1"})

        patterns = analyzer.detect_conditional_patterns()

        assert len(patterns["merge_nodes"]) == 2
        assert "complex_merge_patterns" in patterns

    def test_performance_large_workflow(self):
        """Test performance with large workflow (100+ nodes)."""
        workflow = Workflow("large_test", "Large Test")
        analyzer = ConditionalBranchAnalyzer(workflow)

        # Create large workflow with 10 switches and 90 processing nodes
        for i in range(10):
            switch = SwitchNode(
                name=f"switch_{i}",
                condition_field=f"field_{i}",
                operator="equals",
                value=i,
            )
            workflow.add_node(f"switch_{i}", switch)

            # Add 9 processing nodes per switch
            for j in range(9):
                proc = PythonCodeNode(
                    name=f"proc_{i}_{j}", code=f"result = {{'proc': {i}, 'sub': {j}}}"
                )
                workflow.add_node(f"proc_{i}_{j}", proc)
                workflow.connect(
                    f"switch_{i}", f"proc_{i}_{j}", {"true_output": "input"}
                )

        # Performance test - should complete quickly
        import time

        start_time = time.time()

        switch_nodes = analyzer._find_switch_nodes()
        branch_map = analyzer._build_branch_map()
        patterns = analyzer.detect_conditional_patterns()

        execution_time = time.time() - start_time

        assert len(switch_nodes) == 10
        assert len(branch_map) == 10
        assert patterns["total_switches"] == 10
        assert execution_time < 1.0  # Should complete in under 1 second

    def test_multi_case_switch_analysis(self):
        """Test analysis of multi-case SwitchNode patterns."""
        workflow = Workflow("test", "Test")
        analyzer = ConditionalBranchAnalyzer(workflow)

        # Create multi-case switch
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

        workflow.add_node("switch1", switch_node)
        workflow.add_node("premium_proc", proc1)
        workflow.add_node("basic_proc", proc2)
        workflow.add_node("trial_proc", proc3)

        # Connect multi-case outputs
        workflow.connect("switch1", "premium_proc", {"case_premium": "input"})
        workflow.connect("switch1", "basic_proc", {"case_basic": "input"})
        workflow.connect("switch1", "trial_proc", {"case_trial": "input"})

        branch_map = analyzer._build_branch_map()
        patterns = analyzer.detect_conditional_patterns()

        assert "switch1" in branch_map
        assert len(branch_map["switch1"]) == 3  # Three case outputs
        assert "multi_case_switches" in patterns
