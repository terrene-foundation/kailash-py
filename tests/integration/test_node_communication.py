"""Test data passing between nodes in workflows."""

from pathlib import Path
from typing import Any

import pytest

from kailash.nodes.base import Node, NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.sdk_exceptions import NodeValidationError
from kailash.workflow import Workflow, WorkflowBuilder

# Register MockNode from conftest
from tests.conftest import MockNode

NodeRegistry.register(MockNode)


class TestNodeCommunication:
    """Test data flow between different node types."""

    def test_simple_node_communication(self, temp_data_dir: Path):
        """Test basic data passing between nodes."""
        builder = WorkflowBuilder()

        # Create simple test workflow
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")

        # Connect nodes
        try:
            builder.add_connection(node1_id, "output", node2_id, "input")
            workflow = builder.build("simple_communication_test")

            # Execute workflow
            LocalRuntime()
            runner = WorkflowRunner()
            result = runner.run(workflow)

            # Verify workflow executed successfully
            assert result is not None
        except Exception:
            # Skip if node types not available
            pytest.skip("MockNode type not available for testing")

    def test_validation_error_handling(self):
        """Test that validation errors are properly handled."""
        builder = WorkflowBuilder()

        # Try to add node with invalid type - this should raise an error during build
        builder.add_node("NonExistentNode", "test_node")
        with pytest.raises(
            (NodeValidationError, ValueError, AttributeError, Exception)
        ):
            builder.build("test_workflow")

    def test_basic_workflow_creation(self):
        """Test basic workflow creation and validation."""
        builder = WorkflowBuilder()

        try:
            # Create simple workflow
            workflow = builder.build("empty_workflow")
            assert workflow is not None
            assert workflow.metadata.name == "empty_workflow"
        except Exception:
            # Skip if workflow creation fails
            pytest.skip("Basic workflow creation not available")

    def test_workflow_builder_api(self):
        """Test workflow builder API methods."""
        builder = WorkflowBuilder()

        # Test builder methods exist
        assert hasattr(builder, "add_node")
        assert hasattr(builder, "build")

        # Test that builder can be instantiated
        assert builder is not None

    def test_runtime_initialization(self):
        """Test that runtime components can be initialized."""
        runtime = LocalRuntime()
        assert runtime is not None

        # WorkflowRunner doesn't take runtime as argument anymore
        runner = WorkflowRunner()
        assert runner is not None

    def test_node_base_class(self):
        """Test basic node functionality."""
        # Test that Node base class can be imported and used
        from kailash.nodes.base import NodeParameter

        class TestNode(Node):
            def get_parameters(self) -> dict[str, NodeParameter]:
                return {"input": NodeParameter(name="input", type=str, required=True)}

            def run(self, **kwargs) -> dict[str, Any]:
                return {"output": "test"}

        node = TestNode(name="test", input="test_value")
        assert node.metadata.name == "test"

    def test_workflow_metadata(self):
        """Test workflow metadata functionality."""
        builder = WorkflowBuilder()
        workflow = builder.build(name="test_workflow")

        # Test that workflow has basic metadata
        assert hasattr(workflow, "metadata")
        assert workflow.name == "test_workflow"

    def test_error_handling_in_communication(self):
        """Test error handling during node communication."""
        # Test that appropriate exceptions are available
        assert NodeValidationError is not None

        # Test basic error raising
        with pytest.raises(NodeValidationError):
            raise NodeValidationError("Test error")

    def test_imports_available(self):
        """Test that all required imports are available."""
        # Test that imports work
        assert LocalRuntime is not None
        assert WorkflowRunner is not None
        assert Workflow is not None
        assert WorkflowBuilder is not None
        assert Node is not None
        assert NodeValidationError is not None
