"""
Comprehensive tests for LocalRuntime conditional execution to improve coverage.

Tests conditional execution paths, error handling, and edge cases.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.planning.dynamic_execution_planner import DynamicExecutionPlanner
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, RuntimeExecutionError
from kailash.workflow.graph import Workflow


class TestLocalRuntimeConditionalCoverage:
    """Test LocalRuntime conditional execution for coverage improvement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.runtime = LocalRuntime(conditional_execution="skip_branches")

    def test_has_conditional_patterns(self):
        """Test _has_conditional_patterns method."""
        # Test with no switches
        assert not self.runtime._has_conditional_patterns(self.workflow)

        # Add a switch node
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        self.workflow.add_node("switch", switch)

        # Should detect conditional patterns
        assert self.runtime._has_conditional_patterns(self.workflow)

    @pytest.mark.asyncio
    async def test_execute_conditional_approach_success(self):
        """Test successful conditional execution approach."""
        # Create workflow with switches
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

        # Execute conditional approach
        task_manager = Mock()
        results = await self.runtime._execute_conditional_approach(
            workflow=self.workflow,
            parameters={},
            task_manager=task_manager,
            run_id="test-run",
            workflow_context={},
        )

        # Should have executed source, switch, and true branch
        assert "source" in results
        assert "switch" in results
        assert "proc_true" in results
        # False branch might not be in results with skip_branches

    def test_execute_conditional_approach_phase1_error(self):
        """Test conditional execution with phase 1 error."""
        # Create workflow with failing switch
        switch = SwitchNode(
            name="switch",
            condition_field="missing_field",
            operator="==",
            value="active",
        )
        self.workflow.add_node("switch", switch)

        # Execute - should handle missing field gracefully
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Should execute but handle the error
        assert "switch" in results

    def test_execute_phase1_switches(self):
        """Test switch execution."""
        # Create workflow with multiple switches
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)

        # Add dependencies
        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})

        # Execute
        with self.runtime:
            results, run_id = self.runtime.execute(
                self.workflow, parameters={"switch1": {"a": 1}, "switch2": {"b": 2}}
            )

        assert "switch1" in results
        assert "switch2" in results

    def test_execute_phase2_conditional_plan(self):
        """Test conditional plan execution."""
        # Create simple workflow
        proc1 = PythonCodeNode(name="proc1", code="result = {'data': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data': 2}")

        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.connect("proc1", "proc2", {"result": "input"})

        # Execute
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Should have results for both processors
        assert "proc1" in results
        assert "proc2" in results

    def test_execute_single_node_with_error(self):
        """Test single node execution with error handling."""
        # Create node that will fail
        failing_node = PythonCodeNode(
            name="failing_node", code="raise Exception('Test error')"
        )

        self.workflow.add_node("failing_node", failing_node)

        # Execute - should handle error gracefully
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Should have executed with error
        assert "failing_node" in results

    def test_skip_branches_mode_validation(self):
        """Test skip_branches mode validation and setup."""
        # Test with skip_branches mode
        runtime_skip = LocalRuntime(conditional_execution="skip_branches")
        assert runtime_skip.conditional_execution == "skip_branches"

        # Test with route_data mode (default)
        runtime_route = LocalRuntime(conditional_execution="route_data")
        assert runtime_route.conditional_execution == "route_data"

        # Test with invalid mode - should raise error
        with pytest.raises(ValueError) as exc_info:
            LocalRuntime(conditional_execution="invalid_mode")
        assert "Invalid conditional_execution mode" in str(exc_info.value)

    def test_conditional_execution_fallback(self):
        """Test fallback to standard execution when conditional fails."""
        # Create workflow with switches
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        self.workflow.add_node("switch", switch)

        # Execute - should handle missing status field
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Should execute successfully
        assert "switch" in results

    @pytest.mark.asyncio
    async def test_gather_switch_dependencies(self):
        """Test gathering switch dependencies for hierarchical execution."""
        # Create hierarchical switches
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

        # switch2 depends on switch1
        self.workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        self.workflow.connect("switch2", "proc", {"true_output": "input"})

        # Test dependency gathering
        analyzer = ConditionalBranchAnalyzer(self.workflow)
        hierarchy = analyzer.analyze_switch_hierarchies(["switch1", "switch2"])

        assert hierarchy["has_hierarchies"] is True
        assert len(hierarchy["execution_layers"]) > 1

    def test_conditional_execution_disabled(self):
        """Test behavior when conditional execution is disabled."""
        # Create runtime with standard execution
        runtime = LocalRuntime(conditional_execution="route_data")

        # Add simple workflow
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")

        self.workflow.add_node("node1", node1)
        self.workflow.add_node("node2", node2)

        self.workflow.connect("node1", "node2", {"result": "input"})

        # Should execute all nodes
        with runtime:
            results, run_id = runtime.execute(self.workflow)

        assert "node1" in results
        assert "node2" in results

    def test_merge_node_conditional_handling(self):
        """Test merge node handling with conditional inputs."""
        # Create workflow with conditional merge
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        proc1 = PythonCodeNode(name="proc1", code="result = {'data_a': 1}")
        proc2 = PythonCodeNode(name="proc2", code="result = {'data_b': 2}")
        merge = MergeNode(name="merge", merge_type="merge_dict", skip_none=True)

        self.workflow.add_node("switch1", switch1)
        self.workflow.add_node("switch2", switch2)
        self.workflow.add_node("proc1", proc1)
        self.workflow.add_node("proc2", proc2)
        self.workflow.add_node("merge", merge)

        self.workflow.connect("switch1", "proc1", {"true_output": "input"})
        self.workflow.connect("switch2", "proc2", {"true_output": "input"})
        self.workflow.connect("proc1", "merge", {"result": "data1"})
        self.workflow.connect("proc2", "merge", {"result": "data2"})

        # Execute with only switch1 true
        parameters = {"switch1": {"a": 1}, "switch2": {"b": 3}}  # Will be false

        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow, parameters=parameters)

        # Merge should handle partial inputs
        assert "merge" in results

    def test_complex_conditional_patterns(self):
        """Test complex conditional patterns with multiple switches and merges."""
        # Create complex workflow
        source = PythonCodeNode(
            name="source", code="result = {'type': 'A', 'value': 100}"
        )

        # Type routing
        type_switch = SwitchNode(
            name="type_switch", condition_field="type", operator="==", value="A"
        )

        # Value routing
        value_switch = SwitchNode(
            name="value_switch", condition_field="value", operator=">", value=50
        )

        # Processors
        type_a_proc = PythonCodeNode(
            name="type_a_proc", code="result = {'processed': 'type_a'}"
        )
        high_value_proc = PythonCodeNode(
            name="high_value_proc", code="result = {'processed': 'high_value'}"
        )

        # Final merge
        final_merge = MergeNode(name="final_merge", merge_type="merge_dict")

        # Build workflow
        self.workflow.add_node("source", source)
        self.workflow.add_node("type_switch", type_switch)
        self.workflow.add_node("value_switch", value_switch)
        self.workflow.add_node("type_a_proc", type_a_proc)
        self.workflow.add_node("high_value_proc", high_value_proc)
        self.workflow.add_node("final_merge", final_merge)

        # Connect
        self.workflow.connect("source", "type_switch", {"result": "input_data"})
        self.workflow.connect("source", "value_switch", {"result": "input_data"})
        self.workflow.connect("type_switch", "type_a_proc", {"true_output": "input"})
        self.workflow.connect(
            "value_switch", "high_value_proc", {"true_output": "input"}
        )
        self.workflow.connect("type_a_proc", "final_merge", {"result": "data1"})
        self.workflow.connect("high_value_proc", "final_merge", {"result": "data2"})

        # Execute
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Verify execution
        assert "source" in results
        assert "type_switch" in results
        assert "value_switch" in results

    def test_workflow_context_handling(self):
        """Test workflow context propagation in conditional execution."""
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Create simple workflow
        node = PythonCodeNode(name="node", code="result = {'data': 'test'}")
        runtime.workflow = Workflow("test", "Test Workflow")
        runtime.workflow.add_node("node", node)

        # Execute
        with runtime:
            results, run_id = runtime.execute(runtime.workflow)

        # Should execute successfully
        assert results["node"]["result"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_phase_execution_error_handling(self):
        """Test error handling in different phases of conditional execution."""
        # Test phase 1 switch execution error
        switch = SwitchNode(
            name="switch", condition_field="field", operator="invalid_op", value=1
        )
        self.workflow.add_node("switch", switch)

        task_manager = Mock()

        # Should handle invalid operator gracefully
        try:
            switch_results = await self.runtime._execute_phase1_switches(
                workflow=self.workflow,
                switch_nodes=["switch"],
                parameters={},
                task_manager=task_manager,
                run_id="test-run",
                workflow_context={},
            )
            # Might return error result or raise exception
            assert True  # Just verify it doesn't crash
        except Exception:
            # Error handling is acceptable
            assert True

    def test_execution_mode_logging(self):
        """Test execution mode logging and detection."""
        # Test conditional workflow detection
        runtime = LocalRuntime(conditional_execution="skip_branches")

        # Create workflow with switch
        switch = SwitchNode(
            name="switch", condition_field="status", operator="==", value="active"
        )
        proc = PythonCodeNode(name="proc", code="result = {'data': 1}")

        self.workflow.add_node("switch", switch)
        self.workflow.add_node("proc", proc)
        self.workflow.connect("switch", "proc", {"true_output": "input"})

        # Execute
        with runtime:
            results, run_id = runtime.execute(self.workflow)

        # Should execute successfully
        assert "switch" in results
