"""
Tests for hierarchical switch execution in LocalRuntime.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.analysis import ConditionalBranchAnalyzer
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.hierarchical_switch_executor import HierarchicalSwitchExecutor
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class TestHierarchicalSwitchExecution:
    """Test hierarchical switch execution functionality."""

    def test_simple_switch_hierarchy(self):
        """Test simple hierarchical switch pattern."""
        workflow = Workflow("test", "Test Workflow")

        # Create workflow: source -> switch1 -> switch2 -> processor
        source = PythonCodeNode(
            name="source", code="result = {'level': 1, 'type': 'A'}"
        )
        switch1 = SwitchNode(
            name="switch1", condition_field="level", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="type", operator="==", value="A"
        )
        processor = PythonCodeNode(
            name="processor", code="result = {'processed': True}"
        )

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("processor", processor)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        workflow.connect("switch2", "processor", {"true_output": "input"})

        # Execute workflow
        with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
            results, run_id = runtime.execute(workflow)

            # Verify all nodes executed
            assert "source" in results
            assert "switch1" in results
            assert "switch2" in results
            assert "processor" in results

            # Verify correct execution
            assert results["processor"]["result"]["processed"] is True

    def test_parallel_switch_layers(self):
        """Test switches that can execute in parallel."""
        workflow = Workflow("test", "Test Workflow")

        # Create workflow with parallel switches
        # source -> [switch1, switch2] -> merge
        source = PythonCodeNode(name="source", code="result = {'a': 1, 'b': 2}")
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )
        merge = PythonCodeNode(name="merge", code="result = {'merged': True}")

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("merge", merge)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("source", "switch2", {"result": "input_data"})
        workflow.connect("switch1", "merge", {"true_output": "input1"})
        workflow.connect("switch2", "merge", {"true_output": "input2"})

        # Execute workflow
        with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
            results, run_id = runtime.execute(workflow)

            # Verify all nodes executed
            assert "source" in results
            assert "switch1" in results
            assert "switch2" in results
            assert "merge" in results

    def test_complex_switch_hierarchy(self):
        """Test complex multi-layer switch hierarchy."""
        workflow = Workflow("test", "Test Workflow")

        # Create complex hierarchy:
        # source -> switch1 -> [switch2, switch3] -> switch4 -> final
        source = PythonCodeNode(
            name="source",
            code="result = {'level1': True, 'level2a': True, 'level2b': False, 'level3': True}",
        )
        switch1 = SwitchNode(
            name="switch1", condition_field="level1", operator="==", value=True
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="level2a", operator="==", value=True
        )
        switch3 = SwitchNode(
            name="switch3", condition_field="level2b", operator="==", value=True
        )
        switch4 = SwitchNode(
            name="switch4", condition_field="level3", operator="==", value=True
        )
        final = PythonCodeNode(name="final", code="result = {'complete': True}")

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.add_node("switch3", switch3)
        workflow.add_node("switch4", switch4)
        workflow.add_node("final", final)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})
        workflow.connect("switch1", "switch3", {"true_output": "input_data"})
        workflow.connect("switch2", "switch4", {"true_output": "input_data"})
        workflow.connect("switch3", "switch4", {"false_output": "input_data"})
        workflow.connect("switch4", "final", {"true_output": "input"})

        # Execute workflow
        with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
            results, run_id = runtime.execute(workflow)

            # Verify execution
            assert "source" in results
            assert "switch1" in results
            assert "switch2" in results
            assert "switch3" in results
            assert "switch4" in results
            assert "final" in results

            # Check that final node was reached
            assert results["final"]["result"]["complete"] is True

    def test_should_use_hierarchical_execution(self):
        """Test the decision logic for using hierarchical execution."""
        workflow = Workflow("test", "Test Workflow")

        # Single switch - should not use hierarchical
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        workflow.add_node("switch1", switch1)

        with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
            assert not runtime._should_use_hierarchical_execution(workflow, ["switch1"])

            # Multiple independent switches - should not use hierarchical
            switch2 = SwitchNode(
                name="switch2", condition_field="b", operator="==", value=2
            )
            workflow.add_node("switch2", switch2)

            assert not runtime._should_use_hierarchical_execution(
                workflow, ["switch1", "switch2"]
            )

            # Dependent switches - should use hierarchical
            workflow.connect("switch1", "switch2", {"true_output": "input_data"})

            assert runtime._should_use_hierarchical_execution(
                workflow, ["switch1", "switch2"]
            )

    @pytest.mark.asyncio
    async def test_hierarchical_executor_directly(self):
        """Test HierarchicalSwitchExecutor directly."""
        workflow = Workflow("test", "Test Workflow")

        # Create simple hierarchy
        source = PythonCodeNode(name="source", code="result = {'value': 10}")
        switch1 = SwitchNode(
            name="switch1", condition_field="value", operator=">", value=5
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="value", operator="<", value=20
        )

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})

        # Create executor
        executor = HierarchicalSwitchExecutor(workflow, debug=True)

        # Mock node executor
        async def mock_executor(
            node_id,
            node_instance,
            all_results,
            parameters,
            task_manager,
            workflow,
            workflow_context,
        ):
            # Simple execution
            if node_id == "source":
                return {"result": {"value": 10}}
            elif node_id == "switch1":
                return {"true_output": {"value": 10}, "false_output": None}
            elif node_id == "switch2":
                return {"true_output": {"value": 10}, "false_output": None}
            return {}

        # Execute
        all_results, switch_results = await executor.execute_switches_hierarchically(
            parameters={}, node_executor=mock_executor
        )

        # Verify results
        assert "switch1" in switch_results
        assert "switch2" in switch_results
        assert switch_results["switch1"]["true_output"] is not None
        assert switch_results["switch2"]["true_output"] is not None

        # Get summary
        summary = executor.get_execution_summary(switch_results)
        assert summary["total_switches"] == 2
        assert summary["successful_switches"] == 2
        assert len(summary["execution_layers"]) > 0

    def test_hierarchical_with_errors(self):
        """Test hierarchical execution with switch errors."""
        workflow = Workflow("test", "Test Workflow")

        # Create workflow with a failing switch
        source = PythonCodeNode(
            name="source", code="result = {'value': 'not_a_number'}"
        )
        switch1 = SwitchNode(
            name="switch1", condition_field="value", operator=">", value=5
        )  # Will fail with string
        switch2 = SwitchNode(
            name="switch2", condition_field="other", operator="==", value=1
        )

        workflow.add_node("source", source)
        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)

        workflow.connect("source", "switch1", {"result": "input_data"})
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})

        # Execute workflow - should handle error gracefully
        with LocalRuntime(conditional_execution="skip_branches", debug=True) as runtime:
            results, run_id = runtime.execute(workflow)

            # Source should execute
            assert "source" in results
            # Switches might have errors but workflow should complete
            assert len(results) > 0

    def test_get_layer_dependencies(self):
        """Test dependency collection for switch layers."""
        workflow = Workflow("test", "Test Workflow")

        # Create workflow with dependencies
        prep1 = PythonCodeNode(name="prep1", code="result = {'data': 1}")
        prep2 = PythonCodeNode(name="prep2", code="result = {'data': 2}")
        switch1 = SwitchNode(
            name="switch1", condition_field="data", operator="==", value=1
        )

        workflow.add_node("prep1", prep1)
        workflow.add_node("prep2", prep2)
        workflow.add_node("switch1", switch1)

        workflow.connect("prep1", "switch1", {"result": "input_data"})
        workflow.connect("prep2", "switch1", {"result": "extra_data"})

        # Create executor and test dependency collection
        executor = HierarchicalSwitchExecutor(workflow)
        deps = executor._get_layer_dependencies(["switch1"], set())

        # Should include both prep nodes
        assert "prep1" in deps
        assert "prep2" in deps

    def test_execution_summary(self):
        """Test execution summary generation."""
        workflow = Workflow("test", "Test Workflow")

        # Create workflow
        switch1 = SwitchNode(
            name="switch1", condition_field="a", operator="==", value=1
        )
        switch2 = SwitchNode(
            name="switch2", condition_field="b", operator="==", value=2
        )

        workflow.add_node("switch1", switch1)
        workflow.add_node("switch2", switch2)
        workflow.connect("switch1", "switch2", {"true_output": "input_data"})

        # Create executor
        executor = HierarchicalSwitchExecutor(workflow)

        # Mock switch results
        switch_results = {
            "switch1": {"true_output": {"a": 1}, "false_output": None},
            "switch2": {"true_output": None, "false_output": {"b": 3}},
        }

        # Get summary
        summary = executor.get_execution_summary(switch_results)

        assert summary["total_switches"] == 2
        assert summary["successful_switches"] == 2
        assert summary["failed_switches"] == 0
        assert summary["branch_decisions"]["true_branches"] == 1
        assert summary["branch_decisions"]["false_branches"] == 1
        assert "execution_layers" in summary
        assert "dependency_chains" in summary
