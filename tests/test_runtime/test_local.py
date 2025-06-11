"""Tests for local runtime execution module."""

import time
from typing import Any

import pytest

from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.tracking.models import TaskStatus
from kailash.workflow import Workflow


class MockNode(Node):
    """Mock node for testing."""

    def get_parameters(self):
        """Define node parameters."""
        from kailash.nodes.base import NodeParameter

        return {
            "value": NodeParameter(name="value", type=int, required=False, default=0)
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Process data."""
        value = kwargs.get("value", 0)
        multiplier = self.config.get("multiplier", 2)
        return {"value": value * multiplier, "processed": True}


class ErrorNode(Node):
    """Node that raises errors."""

    def get_parameters(self):
        """Define node parameters."""
        from kailash.nodes.base import NodeParameter

        return {
            "value": NodeParameter(name="value", type=int, required=False, default=0)
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Process data."""
        raise ValueError("Processing error")


class SlowNode(Node):
    """Node that takes time to process."""

    def get_parameters(self):
        """Define node parameters."""
        from kailash.nodes.base import NodeParameter

        return {
            "value": NodeParameter(name="value", type=int, required=False, default=0)
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Process data slowly."""
        time.sleep(0.1)  # Simulate slow processing
        value = kwargs.get("value", 0)
        return {"value": value + 1}


class TestLocalRuntime:
    """Test LocalRuntime class."""

    def test_runner_creation(self):
        """Test creating local runner."""
        runner = LocalRuntime()

        assert runner.debug is False
        assert runner.logger is not None

    def test_runner_with_debug(self):
        """Test runner with debug mode."""
        runner = LocalRuntime(debug=True)

        assert runner.debug is True

    def test_run_simple_workflow(self, task_manager):
        """Test running simple workflow."""
        runner = LocalRuntime()

        # Create simple workflow
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        # Create and add nodes
        node1 = MockNode(name="node1")
        node1.config = {"multiplier": 2}
        node2 = MockNode(name="node2")
        node2.config = {"multiplier": 2}

        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)

        # Connect nodes
        workflow.connect("node1", "node2", {"value": "value"})

        # Execute workflow with initial parameters
        parameters = {"node1": {"value": 5}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        assert "node1" in results
        assert "node2" in results
        assert results["node1"]["processed"] is True
        assert results["node2"]["value"] == 20  # 5 * 2 * 2

    def test_run_with_error_node(self, task_manager):
        """Test execution with error node."""
        runner = LocalRuntime()

        # Create workflow with error node that has a dependent
        workflow = Workflow(workflow_id="error_workflow", name="Error Workflow")
        error_node = ErrorNode(name="error")
        mock_node = MockNode(name="dependent")

        workflow.add_node("error", error_node)
        workflow.add_node("dependent", mock_node)
        workflow.connect("error", "dependent", {"value": "value"})

        # Execute workflow and expect error (error node has dependents)
        with pytest.raises(Exception) as exc_info:
            runner.execute(workflow, task_manager=task_manager)

        assert "Processing error" in str(exc_info.value)

    def test_run_with_partial_success(self, task_manager):
        """Test execution with partial success."""
        runner = LocalRuntime()

        # Create workflow with parallel branches
        workflow = Workflow(
            workflow_id="partial_success_workflow", name="Partial Success Workflow"
        )

        # Create and add nodes
        start = MockNode(name="Start")
        start.config = {"multiplier": 2}
        success_branch = MockNode(name="Success")
        success_branch.config = {"multiplier": 2}
        error_branch = ErrorNode(name="Error")

        workflow.add_node("start", start)
        workflow.add_node("success", success_branch)
        workflow.add_node("error", error_branch)

        # Connect nodes - both branches from start
        workflow.connect("start", "success", {"value": "value"})
        workflow.connect("start", "error", {"value": "value"})

        # Execute workflow - error branch fails but doesn't stop execution (no dependents)
        parameters = {"start": {"value": 10}}

        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        # Check partial success - start and success nodes should work
        assert "start" in results
        assert results["start"]["value"] == 20  # 10 * 2
        assert results["start"]["processed"] is True

        assert "success" in results
        assert results["success"]["value"] == 40  # 20 * 2
        assert results["success"]["processed"] is True

        # Error node should have failed
        assert "error" in results
        assert results["error"]["failed"] is True
        assert "Processing error" in results["error"]["error"]

    def test_execute_node_directly(self, task_manager):
        """Test executing node directly through workflow."""
        runner = LocalRuntime()

        # Create workflow with single node
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")
        node = MockNode(name="Test Node")
        node.config = {"multiplier": 2}
        workflow.add_node("test", node)

        # Execute workflow
        parameters = {"test": {"value": 7}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        assert results["test"]["value"] == 14
        assert results["test"]["processed"] is True

        # Check task was created and updated
        tasks = task_manager.get_workflow_tasks(run_id)
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        assert len(completed_tasks) > 0
        assert completed_tasks[0].node_id == "test"

    def test_execute_node_with_error_directly(self, task_manager):
        """Test executing node that raises error."""
        runner = LocalRuntime()

        # Create workflow with error node
        workflow = Workflow(workflow_id="error_workflow", name="Error Workflow")
        node = ErrorNode(name="Error Node")
        workflow.add_node("error", node)

        # Execute workflow - error node fails but doesn't raise (no dependents)
        results, run_id = runner.execute(workflow, task_manager=task_manager)

        # Check that error node failed
        assert "error" in results
        assert results["error"]["failed"] is True
        assert "Processing error" in results["error"]["error"]

    def test_node_inputs_through_connections(self, task_manager):
        """Test node inputs through workflow connections."""
        runner = LocalRuntime()

        # Create workflow
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        # Create and add nodes
        node1 = MockNode(name="Node1")
        node1.config = {"multiplier": 1}  # Pass through
        node2 = MockNode(name="Node2")
        node2.config = {"multiplier": 1}  # Pass through
        node3 = MockNode(name="Node3")
        node3.config = {"multiplier": 2}

        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)
        workflow.add_node("node3", node3)

        # Connect nodes - node3 receives from both node1 and node2
        workflow.connect("node1", "node3", {"value": "input1"})
        workflow.connect("node2", "node3", {"value": "input2"})

        # Execute workflow with initial parameters
        parameters = {
            "node1": {"value": 100},
            "node2": {"value": 200},
            "node3": {"initial": 300},
        }
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        # Node3 should receive input1 from node1 and input2 from node2
        # But MockNode only processes "value", so we check the execution worked
        assert results["node1"]["value"] == 100
        assert results["node2"]["value"] == 200
        assert results["node3"]["processed"] is True

    def test_predecessor_node_execution(self, task_manager):
        """Test execution with predecessor nodes."""
        runner = LocalRuntime()

        # Create workflow with dependencies
        workflow = Workflow(
            workflow_id="predecessor_workflow", name="Predecessor Workflow"
        )

        # Create and add nodes
        node1 = MockNode(name="Node1")
        node1.config = {"multiplier": 2}
        node2 = MockNode(name="Node2")
        node2.config = {"multiplier": 3}
        node3 = MockNode(name="Node3")
        node3.config = {"multiplier": 1}

        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)
        workflow.add_node("node3", node3)

        # Connect nodes - node3 depends on both node1 and node2
        workflow.connect("node1", "node3", {"value": "value1"})
        workflow.connect("node2", "node3", {"value": "value2"})

        # Execute workflow
        parameters = {"node1": {"value": 10}, "node2": {"value": 20}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        assert results["node1"]["value"] == 20  # 10 * 2
        assert results["node2"]["value"] == 60  # 20 * 3
        assert results["node3"]["processed"] is True

    def test_predecessor_node_with_error(self, task_manager):
        """Test execution when predecessor fails."""
        runner = LocalRuntime()

        # Create workflow with error node as predecessor
        workflow = Workflow(
            workflow_id="error_predecessor_workflow", name="Error Predecessor Workflow"
        )

        # Create and add nodes
        error_node = ErrorNode(name="ErrorPred")
        dependent_node = MockNode(name="Dependent")

        workflow.add_node("error", error_node)
        workflow.add_node("dependent", dependent_node)

        # Connect error node to dependent
        workflow.connect("error", "dependent", {"value": "value"})

        # Execute workflow - should fail due to error node
        with pytest.raises(Exception) as exc_info:
            runner.execute(workflow, task_manager=task_manager)

        assert "Processing error" in str(exc_info.value)

    def test_parallel_execution(self, task_manager):
        """Test parallel execution of independent nodes."""
        runner = LocalRuntime()

        # Create workflow with parallel nodes
        workflow = Workflow(workflow_id="parallel_workflow", name="Parallel Workflow")

        # Create and add nodes
        source = MockNode(name="Source")
        source.config = {"multiplier": 2}
        parallel1 = SlowNode(name="Parallel 1")
        parallel2 = SlowNode(name="Parallel 2")
        parallel3 = SlowNode(name="Parallel 3")
        sink = MockNode(name="Sink")
        sink.config = {"multiplier": 1}

        workflow.add_node("source", source)
        workflow.add_node("parallel1", parallel1)
        workflow.add_node("parallel2", parallel2)
        workflow.add_node("parallel3", parallel3)
        workflow.add_node("sink", sink)

        # Connect source to all parallel nodes
        workflow.connect("source", "parallel1", {"value": "value"})
        workflow.connect("source", "parallel2", {"value": "value"})
        workflow.connect("source", "parallel3", {"value": "value"})

        # Connect all parallel nodes to sink
        workflow.connect("parallel1", "sink", {"value": "input1"})
        workflow.connect("parallel2", "sink", {"value": "input2"})
        workflow.connect("parallel3", "sink", {"value": "input3"})

        # Execute workflow - should run parallel nodes concurrently
        parameters = {"source": {"value": 1}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        # Verify results
        assert results["source"]["value"] == 2
        assert results["parallel1"]["value"] == 3  # 2 + 1
        assert results["parallel2"]["value"] == 3  # 2 + 1
        assert results["parallel3"]["value"] == 3  # 2 + 1

        # Note: We can't easily test parallelism timing without access to internals
        # The LocalRuntime may or may not execute nodes in parallel

    def test_cleanup_on_error(self, task_manager):
        """Test that workflow handles errors properly."""
        runner = LocalRuntime()

        # Create workflow with error
        workflow = Workflow(workflow_id="cleanup_workflow", name="Cleanup Workflow")

        # Create and add nodes
        node1 = MockNode(name="Node 1")
        node1.config = {"multiplier": 2}
        error_node = ErrorNode(name="Error")
        node3 = MockNode(name="Node 3")  # Add dependent node

        workflow.add_node("node1", node1)
        workflow.add_node("error", error_node)
        workflow.add_node("node3", node3)

        # Connect node1 to error node, and error to node3
        workflow.connect("node1", "error", {"value": "value"})
        workflow.connect("error", "node3", {"value": "value"})

        # Execute workflow - should raise exception
        parameters = {"node1": {"value": 5}}

        with pytest.raises(Exception) as exc_info:
            runner.execute(workflow, task_manager=task_manager, parameters=parameters)

        assert "Processing error" in str(exc_info.value)

    def test_empty_workflow(self, task_manager):
        """Test execution of empty workflow."""
        runner = LocalRuntime()

        # Create empty workflow
        workflow = Workflow(workflow_id="empty_workflow", name="Empty Workflow")

        # Execute empty workflow
        results, run_id = runner.execute(workflow, task_manager=task_manager)

        assert results == {}
        assert isinstance(run_id, str)

    def test_single_node_workflow(self, task_manager):
        """Test workflow with single node."""
        runner = LocalRuntime()

        # Create single node workflow
        workflow = Workflow(
            workflow_id="single_node_workflow", name="Single Node Workflow"
        )

        # Create and add single node
        node = MockNode(name="Single Node")
        node.config = {"multiplier": 2}
        workflow.add_node("single", node)

        # Execute workflow with parameters
        parameters = {"single": {"value": 42}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        assert results["single"]["value"] == 84  # 42 * 2
        assert results["single"]["processed"] is True

    def test_complex_dependency_chain(self, task_manager):
        """Test workflow with complex dependency chain."""
        runner = LocalRuntime()

        # Create complex workflow: A -> B -> D
        #                              -> C -> D -> E
        workflow = Workflow(
            workflow_id="complex_dependency_workflow",
            name="Complex Dependency Workflow",
        )

        # Create and add all nodes
        node_a = MockNode(name="Node A")
        node_a.config = {"multiplier": 2}
        node_b = MockNode(name="Node B")
        node_b.config = {"multiplier": 2}
        node_c = MockNode(name="Node C")
        node_c.config = {"multiplier": 2}
        node_d = MockNode(name="Node D")
        node_d.config = {"multiplier": 2}
        node_e = MockNode(name="Node E")
        node_e.config = {"multiplier": 2}

        workflow.add_node("A", node_a)
        workflow.add_node("B", node_b)
        workflow.add_node("C", node_c)
        workflow.add_node("D", node_d)
        workflow.add_node("E", node_e)

        # Create connections
        workflow.connect("A", "B", {"value": "value"})
        workflow.connect("A", "C", {"value": "value"})
        workflow.connect("B", "D", {"value": "input1"})
        workflow.connect("C", "D", {"value": "input2"})
        workflow.connect("D", "E", {"value": "value"})

        # Execute workflow
        parameters = {"A": {"value": 1}}
        results, run_id = runner.execute(
            workflow, task_manager=task_manager, parameters=parameters
        )

        assert results["A"]["value"] == 2
        assert results["B"]["value"] == 4
        assert results["C"]["value"] == 4
        # D receives both inputs, but mock node only processes "value" parameter
        # The actual value depends on which input it uses
        assert results["E"]["processed"] is True
