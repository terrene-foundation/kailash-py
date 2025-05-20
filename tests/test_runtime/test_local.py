"""Tests for local runtime execution module."""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any
import time
from concurrent.futures import Future

from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import Node
from kailash.tracking.models import Task, TaskStatus
from kailash.sdk_exceptions import KailashRuntimeError, KailashValidationError


class MockNode(Node):
    """Mock node for testing."""
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        value = data.get("value", 0)
        return {"value": value * 2, "processed": True}


class ErrorNode(Node):
    """Node that raises errors."""
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        raise ValueError("Processing error")


class SlowNode(Node):
    """Node that takes time to process."""
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data slowly."""
        time.sleep(0.1)  # Simulate slow processing
        return {"value": data.get("value", 0) + 1}


class TestLocalRuntime:
    """Test LocalRuntime class."""
    
    def test_runner_creation(self, task_manager):
        """Test creating local runner."""
        runner = LocalRuntime(task_manager=task_manager)
        
        assert runner.task_manager == task_manager
        assert runner.executor is not None
        assert runner.max_workers == 4  # Default value
    
    def test_runner_with_custom_workers(self, task_manager):
        """Test runner with custom worker count."""
        runner = LocalRuntime(task_manager=task_manager, max_workers=8)
        
        assert runner.max_workers == 8
    
    def test_run_simple_workflow(self, task_manager):
        """Test running simple workflow."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create simple workflow using builder
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1", config={"multiplier": 2})
        node2_id = builder.add_node("MockNode", "node2", config={"multiplier": 2})
        builder.add_connection(node1_id, "value", node2_id, "value")
        
        workflow = builder.build("test_workflow")
        
        # Mock nodes
        node1 = MockNode(node_id="node1", name="Node 1")
        node2 = MockNode(node_id="node2", name="Node 2")
        workflow.graph.nodes["node1"]["node"] = node1
        workflow.graph.nodes["node2"]["node"] = node2
        
        # Set initial data
        initial_data = {"node1": {"value": 5}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        result = runner.run(workflow)
        
        assert result.success is True
        assert result.errors == []
        assert "node1" in result.node_results
        assert "node2" in result.node_results
        assert result.node_results["node1"]["processed"] is True
        assert result.node_results["node2"]["value"] == 20  # 5 * 2 * 2
    
    def test_run_with_error_node(self, task_manager):
        """Test execution with error node."""
        runner = LocalRuntime(task_manager=task_manager)
        
        builder = WorkflowBuilder()
        error_id = builder.add_node("ErrorNode", "error")
        workflow = builder.build("error_workflow")
        
        # Mock error node
        error_node = ErrorNode(node_id="error", name="Error Node")
        workflow.graph.nodes["error"]["node"] = error_node
        
        result = runner.run(workflow)
        
        assert result.success is False
        assert len(result.errors) == 1
        assert "error" in result.errors[0]
        assert result.node_results["error"] is None
    
    def test_run_with_partial_success(self, task_manager):
        """Test execution with partial success."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create workflow with parallel branches
        builder = WorkflowBuilder()
        start_id = builder.add_node("MockNode", "start")
        success_id = builder.add_node("MockNode", "success")
        error_id = builder.add_node("ErrorNode", "error")
        
        builder.add_connection(start_id, "value", success_id, "value")
        builder.add_connection(start_id, "value", error_id, "value")
        
        workflow = builder.build("partial_success_workflow")
        
        # Mock nodes
        start = MockNode(node_id="start", name="Start")
        success_branch = MockNode(node_id="success", name="Success")
        error_branch = ErrorNode(node_id="error", name="Error")
        
        workflow.graph.nodes["start"]["node"] = start
        workflow.graph.nodes["success"]["node"] = success_branch
        workflow.graph.nodes["error"]["node"] = error_branch
        
        # Set initial data
        initial_data = {"start": {"value": 10}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        result = runner.run(workflow)
        
        assert result.success is False  # Overall failed due to error node
        assert len(result.errors) == 1
        assert result.node_results["start"]["value"] == 20
        assert result.node_results["success"]["value"] == 40
        assert result.node_results["error"] is None
    
    def test_execute_node(self, task_manager):
        """Test executing single node."""
        runner = LocalRuntime(task_manager=task_manager)
        
        node = MockNode(node_id="test", name="Test Node")
        input_data = {"value": 7}
        
        result = runner._execute_node(node, input_data, "workflow123")
        
        assert result["value"] == 14
        assert result["processed"] is True
        
        # Check task was created and updated
        tasks = task_manager.get_workflow_tasks("workflow123")
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        assert len(completed_tasks) > 0
        assert completed_tasks[0].node_id == "test"
    
    def test_execute_node_with_error(self, task_manager):
        """Test executing node that raises error."""
        runner = LocalRuntime(task_manager=task_manager)
        
        node = ErrorNode(node_id="error", name="Error Node")
        
        with pytest.raises(ValueError):
            runner._execute_node(node, {}, "workflow123")
        
        # Check task was marked as failed
        tasks = task_manager.get_workflow_tasks("workflow123")
        failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
        assert len(failed_tasks) > 0
        assert failed_tasks[0].node_id == "error"
    
    def test_get_node_inputs(self, task_manager):
        """Test getting node inputs."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create workflow
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        node3_id = builder.add_node("MockNode", "node3")
        
        builder.add_connection(node1_id, "output1", node3_id, "input1")
        builder.add_connection(node2_id, "output2", node3_id, "input2")
        
        workflow = builder.build("test_workflow")
        
        # Set up predecessor results
        predecessor_results = {
            "node1": {"output1": 100},
            "node2": {"output2": 200}
        }
        
        # Set up initial data
        initial_data = {"node3": {"initial": 300}}
        
        inputs = runner._get_node_inputs(
            "node3", 
            workflow, 
            predecessor_results,
            initial_data
        )
        
        assert inputs["input1"] == 100
        assert inputs["input2"] == 200
        assert inputs["initial"] == 300
    
    def test_wait_for_predecessors(self, task_manager):
        """Test waiting for predecessor nodes."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create futures for predecessor nodes
        future1 = Future()
        future2 = Future()
        
        node_futures = {
            "node1": future1,
            "node2": future2
        }
        
        # Set results
        future1.set_result({"value": 10})
        future2.set_result({"value": 20})
        
        results = runner._wait_for_predecessors(["node1", "node2"], node_futures)
        
        assert results["node1"]["value"] == 10
        assert results["node2"]["value"] == 20
    
    def test_wait_for_predecessors_with_error(self, task_manager):
        """Test waiting for predecessors when one fails."""
        runner = LocalRuntime(task_manager=task_manager)
        
        future1 = Future()
        future2 = Future()
        
        node_futures = {
            "node1": future1,
            "node2": future2
        }
        
        # Set result for first, exception for second
        future1.set_result({"value": 10})
        future2.set_exception(ValueError("Node failed"))
        
        with pytest.raises(ValueError):
            runner._wait_for_predecessors(["node1", "node2"], node_futures)
    
    def test_parallel_execution(self, task_manager):
        """Test parallel execution of independent nodes."""
        runner = LocalRuntime(task_manager=task_manager, max_workers=3)
        
        # Create workflow with parallel nodes
        builder = WorkflowBuilder()
        source_id = builder.add_node("MockNode", "source")
        parallel1_id = builder.add_node("SlowNode", "parallel1")
        parallel2_id = builder.add_node("SlowNode", "parallel2")
        parallel3_id = builder.add_node("SlowNode", "parallel3")
        sink_id = builder.add_node("MockNode", "sink")
        
        # Connect source to all parallel nodes
        builder.add_connection(source_id, "value", parallel1_id, "value")
        builder.add_connection(source_id, "value", parallel2_id, "value")
        builder.add_connection(source_id, "value", parallel3_id, "value")
        
        # Connect all parallel nodes to sink
        builder.add_connection(parallel1_id, "value", sink_id, "input1")
        builder.add_connection(parallel2_id, "value", sink_id, "input2")
        builder.add_connection(parallel3_id, "value", sink_id, "input3")
        
        workflow = builder.build("parallel_workflow")
        
        # Mock nodes
        source = MockNode(node_id="source", name="Source")
        parallel1 = SlowNode(node_id="parallel1", name="Parallel 1")
        parallel2 = SlowNode(node_id="parallel2", name="Parallel 2")
        parallel3 = SlowNode(node_id="parallel3", name="Parallel 3")
        sink = MockNode(node_id="sink", name="Sink")
        
        workflow.graph.nodes["source"]["node"] = source
        workflow.graph.nodes["parallel1"]["node"] = parallel1
        workflow.graph.nodes["parallel2"]["node"] = parallel2
        workflow.graph.nodes["parallel3"]["node"] = parallel3
        workflow.graph.nodes["sink"]["node"] = sink
        
        # Set initial data
        initial_data = {"source": {"value": 1}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        # Execute workflow - should run parallel nodes concurrently
        start_time = time.time()
        result = runner.run(workflow)
        execution_time = time.time() - start_time
        
        assert result.success is True
        
        # Execution time should be less than sequential execution
        # 3 slow nodes at 0.1s each = 0.3s sequential
        # With parallelism, should be around 0.1s + overhead
        assert execution_time < 0.25  # Allow some overhead
        
        # Verify results
        assert result.node_results["source"]["value"] == 2
        assert result.node_results["parallel1"]["value"] == 3  # 2 + 1
        assert result.node_results["parallel2"]["value"] == 3  # 2 + 1
        assert result.node_results["parallel3"]["value"] == 3  # 2 + 1
    
    def test_cleanup_on_error(self, task_manager):
        """Test that resources are cleaned up on error."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create workflow with error
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        error_id = builder.add_node("ErrorNode", "error")
        builder.add_connection(node1_id, "value", error_id, "value")
        
        workflow = builder.build("cleanup_workflow")
        
        # Mock nodes
        node1 = MockNode(node_id="node1", name="Node 1")
        error_node = ErrorNode(node_id="error", name="Error")
        
        workflow.graph.nodes["node1"]["node"] = node1
        workflow.graph.nodes["error"]["node"] = error_node
        
        # Set initial data
        initial_data = {"node1": {"value": 5}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        # Execute workflow
        result = runner.run(workflow)
        
        assert result.success is False
        
        # Executor should be shutdown
        assert runner.executor._shutdown
    
    def test_empty_workflow(self, task_manager):
        """Test execution of empty workflow."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create empty workflow
        builder = WorkflowBuilder()
        workflow = builder.build("empty_workflow")
        
        result = runner.run(workflow)
        
        assert result.success is True
        assert result.errors == []
        assert result.node_results == {}
    
    def test_single_node_workflow(self, task_manager):
        """Test workflow with single node."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create single node workflow
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "single")
        workflow = builder.build("single_node_workflow")
        
        # Mock node
        node = MockNode(node_id="single", name="Single Node")
        workflow.graph.nodes["single"]["node"] = node
        
        # Set initial data
        initial_data = {"single": {"value": 42}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        result = runner.run(workflow)
        
        assert result.success is True
        assert result.node_results["single"]["value"] == 84  # 42 * 2
    
    def test_complex_dependency_chain(self, task_manager):
        """Test workflow with complex dependency chain."""
        runner = LocalRuntime(task_manager=task_manager)
        
        # Create complex workflow: A -> B -> D
        #                              -> C -> D -> E
        builder = WorkflowBuilder()
        a_id = builder.add_node("MockNode", "A")
        b_id = builder.add_node("MockNode", "B")
        c_id = builder.add_node("MockNode", "C")
        d_id = builder.add_node("MockNode", "D")
        e_id = builder.add_node("MockNode", "E")
        
        builder.add_connection(a_id, "value", b_id, "value")
        builder.add_connection(a_id, "value", c_id, "value")
        builder.add_connection(b_id, "value", d_id, "input1")
        builder.add_connection(c_id, "value", d_id, "input2")
        builder.add_connection(d_id, "value", e_id, "value")
        
        workflow = builder.build("complex_dependency_workflow")
        
        # Mock all nodes
        for node_id in ["A", "B", "C", "D", "E"]:
            workflow.graph.nodes[node_id]["node"] = MockNode(
                node_id=node_id, 
                name=f"Node {node_id}"
            )
        
        # Set initial data
        initial_data = {"A": {"value": 1}}
        runner.set_initial_data(workflow.workflow_id, initial_data)
        
        result = runner.run(workflow)
        
        assert result.success is True
        assert result.node_results["A"]["value"] == 2
        assert result.node_results["B"]["value"] == 4
        assert result.node_results["C"]["value"] == 4
        # D receives both inputs, but mock node just doubles the "value"
        assert result.node_results["E"]["value"] == 8