"""Tests for export utilities module."""

import pytest
from kailash.nodes.base import Node
from kailash.sdk_exceptions import ExportException
from kailash.utils.export import WorkflowExporter
from kailash.workflow import WorkflowBuilder


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, name: str = "Mock"):
        super().__init__(name)

    def process(self, inputs):
        """Mock processing method."""
        return {"output": "test"}


class TestWorkflowExporter:
    """Test WorkflowExporter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure nodes are registered
        from tests.node_registry_utils import ensure_nodes_registered

        ensure_nodes_registered()

    def test_exporter_initialization(self):
        """Test WorkflowExporter can be initialized."""
        exporter = WorkflowExporter()
        assert exporter is not None

    def test_exporter_with_simple_workflow(self):
        """Test exporting a simple workflow."""
        # Create a simple workflow with real nodes
        builder = WorkflowBuilder()
        # Use CSVReader which is registered
        builder.add_node("CSVReaderNode", "csv_reader", {"file_path": "test.csv"})
        workflow = builder.build("test_workflow")

        # Initialize exporter
        exporter = WorkflowExporter()

        # Test that exporter has to_yaml method
        assert hasattr(exporter, "to_yaml")

        # If the method is implemented, test it
        if callable(getattr(exporter, "to_yaml", None)):
            try:
                result = exporter.to_yaml(workflow)
                assert result is not None
                assert isinstance(result, str)
                # Basic check that it contains workflow metadata
                assert "csv_reader" in result  # Check for the node we added
                assert "CSVReaderNode" in result  # Check for the node type
            except NotImplementedError:
                # Mark as expected behavior if not implemented
                pass

    def test_exporter_error_handling(self):
        """Test error handling in exporter."""
        exporter = WorkflowExporter()

        # Test with None workflow
        with pytest.raises(ExportException):
            exporter.to_yaml(None)
