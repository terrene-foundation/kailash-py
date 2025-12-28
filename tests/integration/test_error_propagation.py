"""Test error handling and propagation across workflows."""

from pathlib import Path
from typing import Any

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import (
    NodeExecutionError,
    RuntimeExecutionError,
    WorkflowValidationError,
)
from kailash.tracking.manager import TaskManager
from kailash.workflow.graph import Workflow


class ErrorNode(Node):
    """Node that always fails for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "error_message": NodeParameter(
                name="error_message",
                type=str,
                required=False,
                default="Test error",
                description="Error message to raise",
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        error_message = kwargs.get("error_message", "Test error")
        raise NodeExecutionError(error_message)


class ConditionalErrorNode(Node):
    """Node that fails based on input condition."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "should_fail": NodeParameter(
                name="should_fail",
                type=bool,
                required=False,
                default=False,
                description="Whether the node should fail",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                default=None,
                description="Data to process",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        should_fail = kwargs.get("should_fail", False)
        data = kwargs.get("data")

        if should_fail:
            raise NodeExecutionError("Conditional failure triggered")

        return {"processed_data": data, "status": "success"}


@pytest.mark.critical
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

        # With unified runtime, errors for nodes without dependents are captured in results
        results, run_id = runtime.execute(workflow)

        # Check error is captured in results
        assert "error" in results, f"Expected error result, got: {results}"
        error_result = results["error"]
        assert error_result["failed"] is True
        assert error_result["error_type"] == "NodeExecutionError"
        assert (
            error_result["error"] == "Expected failure"
        )  # Config param now properly passed

    def test_error_in_chain(self, temp_data_dir: Path):
        """Test error propagation in a chain of nodes."""
        # Create test data
        test_csv = temp_data_dir / "test.csv"
        test_csv.write_text("id,value\n1,100\n2,200")

        workflow = Workflow(workflow_id="chain_error", name="Chain Error Test")

        # Add nodes
        from kailash.nodes.data.readers import CSVReaderNode

        reader = CSVReaderNode(name="reader", file_path=str(test_csv))
        workflow.add_node("reader", reader)

        error_node = ErrorNode(name="error", error_message="Processing failed")
        workflow.add_node("error", error_node)

        # Connect nodes
        workflow.connect("reader", "error", {"data": "unused"})

        # Add a dependent node so error propagates
        from kailash.nodes.data.writers import CSVWriterNode

        writer = CSVWriterNode(
            name="writer", file_path=str(temp_data_dir / "output.csv")
        )
        workflow.add_node("writer", writer)
        workflow.connect("error", "writer", {"data": "data"})

        # Execute
        runtime = LocalRuntime()

        with pytest.raises(RuntimeExecutionError) as exc_info:
            runtime.execute(workflow)

        # Error message should now include the configured message
        assert "Processing failed" in str(exc_info.value)

    def test_conditional_error_handling(self):
        """Test conditional error handling in workflows."""
        workflow = Workflow(workflow_id="conditional_error", name="Conditional Error")

        # Add conditional error node
        node = ConditionalErrorNode(name="conditional", should_fail=True, data="test")
        workflow.add_node("conditional", node)

        runtime = LocalRuntime()

        # Should fail but since node has no dependents, error is captured in results
        results, run_id = runtime.execute(workflow)
        assert "conditional" in results
        assert results["conditional"]["error"] == "Conditional failure triggered"
        assert results["conditional"]["failed"] is True

        # Now test without failure
        workflow2 = Workflow(
            workflow_id="conditional_success", name="Conditional Success"
        )
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
            name="success_branch", should_fail=False, data="success"
        )
        error_node = ErrorNode(name="error_branch", error_message="Branch failed")

        workflow.add_node("success", success_node)
        workflow.add_node("error", error_node)

        # Both nodes run independently (no connections)
        runtime = LocalRuntime()

        # Since nodes have no dependents, errors are captured in results
        results, run_id = runtime.execute(workflow)
        assert "error" in results
        assert results["error"]["error"] == "Branch failed"
        assert results["error"]["failed"] is True
        assert results["success"]["processed_data"] == "success"

    def test_error_with_task_tracking(self, temp_data_dir: Path):
        """Test that errors are properly tracked in task manager."""
        # Set up task tracking
        from kailash.tracking.storage.filesystem import FileSystemStorage

        storage = FileSystemStorage(base_path=str(temp_data_dir / "tasks"))
        task_manager = TaskManager(storage_backend=storage)

        workflow = Workflow(workflow_id="tracked_error", name="Tracked Error")
        error_node = ErrorNode(name="error", error_message="Tracked failure")
        workflow.add_node("error", error_node)

        runtime = LocalRuntime()

        # Execute and expect failure captured in results
        results, run_id = runtime.execute(workflow, task_manager=task_manager)

        # Check that the run was tracked
        run = task_manager.get_run(run_id)
        assert run is not None
        # Run completes even with node failures since error is captured
        assert run.status == "completed"

        # Check the individual task failed
        tasks = task_manager.list_tasks(run_id)
        error_task = next((t for t in tasks if t.node_id == "error"), None)
        assert error_task is not None
        assert error_task.status == "failed"
        assert "Tracked failure" in str(error_task.error)

    def test_validation_error_before_execution(self):
        """Test that validation errors occur during workflow validation (Session 061 behavior)."""

        class ValidationNode(Node):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "required_param": NodeParameter(
                        name="required_param",
                        type=str,
                        required=True,
                        description="Required parameter",
                    )
                }

            def run(self, **kwargs) -> dict[str, Any]:
                return {"result": kwargs.get("required_param")}

        workflow = Workflow(workflow_id="validation_error", name="Validation Error")

        # NEW BEHAVIOR: Node creation succeeds without required parameter
        node = ValidationNode(name="validation")  # Missing required_param - OK now
        workflow.add_node("validation", node)

        # NEW BEHAVIOR: Validation error occurs during workflow validation, before execution
        runtime = LocalRuntime()
        with pytest.raises(WorkflowValidationError) as exc_info:
            runtime.execute(workflow)

        assert "required_param" in str(exc_info.value)

    def test_error_message_context(self):
        """Test that error messages include helpful context."""
        workflow = Workflow(
            workflow_id="context_error",
            name="Context Error Test",
            description="Test workflow for error context",
        )

        error_node = ErrorNode(
            name="contextual_error", error_message="Something went wrong"
        )
        workflow.add_node("error_node", error_node)

        runtime = LocalRuntime()

        # Since node has no dependents, error is captured in results
        results, run_id = runtime.execute(workflow)

        assert "error_node" in results
        assert results["error_node"]["error"] == "Something went wrong"
        assert results["error_node"]["failed"] is True

    def test_nested_error_handling(self):
        """Test error handling with nested exceptions."""

        class NestedErrorNode(Node):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {}

            def run(self, **kwargs) -> dict[str, Any]:
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

        # Since node has no dependents, error is captured in results
        results, run_id = runtime.execute(workflow)

        assert "nested" in results
        assert "Failed to process" in results["nested"]["error"]
        assert results["nested"]["failed"] is True

    def test_workflow_recovery_after_error(self):
        """Test that workflows can be re-executed after fixing errors."""
        workflow = Workflow(workflow_id="recovery_test", name="Recovery Test")

        # First, add a node that will fail
        node1 = ConditionalErrorNode(name="maybe_fail", should_fail=True)
        workflow.add_node("node1", node1)

        runtime = LocalRuntime()

        # First execution should fail but error is captured
        results, run_id = runtime.execute(workflow)
        assert results["node1"]["failed"] is True

        # Now fix the issue by creating a new workflow
        workflow2 = Workflow(workflow_id="recovery_test2", name="Recovery Test 2")
        node2 = ConditionalErrorNode(
            name="maybe_fail", should_fail=False, data="recovered"
        )
        workflow2.add_node("node1", node2)

        # Second execution should succeed
        results2, run_id2 = runtime.execute(workflow2)
        assert results2["node1"]["status"] == "success"
        assert results2["node1"]["processed_data"] == "recovered"
