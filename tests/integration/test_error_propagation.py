"""Test error handling and propagation across workflows."""

import json
from pathlib import Path
from typing import Dict, Any

import pytest
import pandas as pd

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow.graph import Workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import Node, NodeParameter, NodeMetadata
from kailash.sdk_exceptions import (
    KailashException, NodeException, WorkflowException,
    NodeValidationError, NodeExecutionError, 
    ConnectionError as KailashConnectionError
)
from kailash.tracking.manager import TaskManager


class ErrorNode(Node):
    """Node that always fails for testing."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "error_message": NodeParameter(
                name="error_message",
                type=str,
                required=False,
                default="Test error",
                description="Error message to raise"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        error_message = kwargs.get("error_message", "Test error")
        raise NodeExecutionError(error_message)


class ConditionalErrorNode(Node):
    """Node that fails based on input condition."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "should_fail": NodeParameter(
                name="should_fail",
                type=bool,
                required=False,
                default=False,
                description="Whether the node should fail"
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                default=None,
                description="Data to process"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        should_fail = kwargs.get("should_fail", False)
        data = kwargs.get("data")
        
        if should_fail:
            raise NodeExecutionError("Conditional failure triggered")
        
        return {"processed_data": data, "status": "success"}


class TestErrorPropagation:
    """Test error handling and propagation in workflows."""
    
    def test_simple_node_error(self):
        """Test that a simple node error is properly caught."""
        workflow = Workflow(workflow_id="error_test", name="Error Test")
        
        # Add error node
        error_node = ErrorNode(name="error_node", error_message="Expected failure")
        workflow.add_node("error", error_node)
        
        # Execute workflow
        runtime = LocalRuntime()
        
        # Check what actually happens
        try:
            results, run_id = runtime.execute(workflow)
            # If we get here, check if the error is in the results
            assert "error" in results, f"Expected error result, got: {results}"
            assert "Expected failure" in str(results.get("error", results))
        except NodeExecutionError as e:
            # This is the expected behavior
            assert "Expected failure" in str(e)
    
    def test_error_in_chain(self, temp_data_dir: Path):
        """Test error propagation in a chain of nodes."""
        # Create test data
        test_csv = temp_data_dir / "test.csv"
        test_csv.write_text("id,value\n1,100\n2,200")
        
        workflow = Workflow(workflow_id="chain_error", name="Chain Error Test")
        
        # Add nodes
        from kailash.nodes.data.readers import CSVReader
        reader = CSVReader(name="reader", file_path=str(test_csv))
        workflow.add_node("reader", reader)
        
        error_node = ErrorNode(name="error", error_message="Processing failed")
        workflow.add_node("error", error_node)
        
        # Connect nodes
        workflow.connect("reader", "error", {"data": "unused"})
        
        # Execute
        runtime = LocalRuntime()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow)
        
        assert "Processing failed" in str(exc_info.value)
    
    def test_conditional_error_handling(self):
        """Test conditional error handling in workflows."""
        workflow = Workflow(workflow_id="conditional_error", name="Conditional Error")
        
        # Add conditional error node
        node = ConditionalErrorNode(name="conditional", should_fail=True, data="test")
        workflow.add_node("conditional", node)
        
        runtime = LocalRuntime()
        
        # Should fail
        with pytest.raises(NodeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow)
        
        assert "Conditional failure triggered" in str(exc_info.value)
        
        # Now test without failure
        workflow2 = Workflow(workflow_id="conditional_success", name="Conditional Success")
        node2 = ConditionalErrorNode(name="conditional", should_fail=False, data="test")
        workflow2.add_node("conditional", node2)
        
        results, run_id = runtime.execute(workflow2)
        assert results["conditional"]["processed_data"] == "test"
        assert results["conditional"]["status"] == "success"
    
    def test_parallel_error_handling(self):
        """Test error handling in parallel branches."""
        workflow = Workflow(workflow_id="parallel_error", name="Parallel Error Test")
        
        # Add nodes - one succeeds, one fails
        success_node = ConditionalErrorNode(
            name="success_branch",
            should_fail=False,
            data="success"
        )
        error_node = ErrorNode(
            name="error_branch",
            error_message="Branch failed"
        )
        
        workflow.add_node("success", success_node)
        workflow.add_node("error", error_node)
        
        # Both nodes run independently (no connections)
        runtime = LocalRuntime()
        
        # The workflow should fail because one node fails
        with pytest.raises(NodeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow)
        
        assert "Branch failed" in str(exc_info.value)
    
    def test_error_with_task_tracking(self, temp_data_dir: Path):
        """Test that errors are properly tracked in task manager."""
        # Set up task tracking
        from kailash.tracking.storage.filesystem import FileSystemStorage
        storage = FileSystemStorage(base_path=str(temp_data_dir / "tasks"))
        task_manager = TaskManager(storage_backend=storage)
        
        workflow = Workflow(workflow_id="tracked_error", name="Tracked Error")
        error_node = ErrorNode(name="error", error_message="Tracked failure")
        workflow.add_node("error", error_node)
        
        runtime = LocalRuntime(task_manager=task_manager)
        
        # Execute and expect failure
        with pytest.raises(NodeExecutionError):
            results, run_id = runtime.execute(workflow)
        
        # Check that the run was tracked
        run = task_manager.get_run(run_id)
        assert run is not None
        assert run.status == "failed"
        assert "Tracked failure" in str(run.error) if run.error else False
    
    def test_validation_error_before_execution(self):
        """Test that validation errors prevent execution."""
        class ValidationNode(Node):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {
                    "required_param": NodeParameter(
                        name="required_param",
                        type=str,
                        required=True,
                        description="Required parameter"
                    )
                }
            
            def run(self, **kwargs) -> Dict[str, Any]:
                return {"result": kwargs.get("required_param")}
        
        workflow = Workflow(workflow_id="validation_error", name="Validation Error")
        
        # Add node without required parameter
        with pytest.raises(NodeValidationError) as exc_info:
            node = ValidationNode(name="validation")  # Missing required_param
        
        assert "Required parameter 'required_param' not provided" in str(exc_info.value)
    
    def test_error_message_context(self):
        """Test that error messages include helpful context."""
        workflow = Workflow(
            workflow_id="context_error",
            name="Context Error Test",
            description="Test workflow for error context"
        )
        
        error_node = ErrorNode(name="contextual_error", error_message="Something went wrong")
        workflow.add_node("error_node", error_node)
        
        runtime = LocalRuntime()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow)
        
        error_str = str(exc_info.value)
        # Should include node information in the error
        assert "contextual_error" in error_str or "error_node" in error_str
        assert "Something went wrong" in error_str
    
    def test_nested_error_handling(self):
        """Test error handling with nested exceptions."""
        class NestedErrorNode(Node):
            def get_parameters(self) -> Dict[str, NodeParameter]:
                return {}
            
            def run(self, **kwargs) -> Dict[str, Any]:
                try:
                    # Simulate nested operation that fails
                    raise ValueError("Inner error")
                except ValueError as e:
                    # Re-raise as node error
                    raise NodeExecutionError(f"Failed to process: {e}") from e
        
        workflow = Workflow(workflow_id="nested_error", name="Nested Error")
        node = NestedErrorNode(name="nested")
        workflow.add_node("nested", node)
        
        runtime = LocalRuntime()
        
        with pytest.raises(NodeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow)
        
        assert "Failed to process" in str(exc_info.value)
        assert "Inner error" in str(exc_info.value)
    
    def test_workflow_recovery_after_error(self):
        """Test that workflows can be re-executed after fixing errors."""
        workflow = Workflow(workflow_id="recovery_test", name="Recovery Test")
        
        # First, add a node that will fail
        node1 = ConditionalErrorNode(name="maybe_fail", should_fail=True)
        workflow.add_node("node1", node1)
        
        runtime = LocalRuntime()
        
        # First execution should fail
        with pytest.raises(NodeExecutionError):
            results, run_id = runtime.execute(workflow)
        
        # Now fix the issue by updating the node
        workflow.remove_node("node1")
        node2 = ConditionalErrorNode(name="maybe_fail", should_fail=False, data="recovered")
        workflow.add_node("node1", node2)
        
        # Second execution should succeed
        results, run_id = runtime.execute(workflow)
        assert results["node1"]["status"] == "success"
        assert results["node1"]["processed_data"] == "recovered"