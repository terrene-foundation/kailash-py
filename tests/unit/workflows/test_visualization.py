"""Tests for workflow visualization module."""

import tempfile
from unittest.mock import patch

import pytest
from kailash.nodes.base import Node
from kailash.workflow import NodeInstance, Workflow
from kailash.workflow.visualization import WorkflowVisualizer


@pytest.fixture(autouse=True)
def setup_matplotlib_backend():
    """Ensure matplotlib backend is properly set for visualization tests."""
    import matplotlib

    matplotlib.use("Agg")  # Ensure non-interactive backend
    yield


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, node_id=None, name=None, **kwargs):
        """Initialize mock node."""
        self.node_id = node_id
        self.name = name or node_id
        self.config = kwargs

    def process(self, data):
        """Process data."""
        return data

    def run(self, **kwargs):
        """Execute the node."""
        return self.process(kwargs)

    def get_parameters(self):
        """Get node parameters."""
        return {}


@pytest.mark.requires_isolation
class TestWorkflowVisualizer:
    """Test WorkflowVisualizer class."""

    def test_visualizer_creation(self):
        """Test creating workflow visualizer."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)

        assert visualizer.workflow == workflow
        assert visualizer.node_colors == visualizer._default_node_colors()
        assert visualizer.edge_colors == visualizer._default_edge_colors()

    def test_visualizer_with_custom_colors(self):
        """Test visualizer with custom colors."""
        workflow = Workflow(workflow_id="test", name="Test")

        node_colors = {"data": "blue", "transform": "green"}
        edge_colors = {"default": "black", "error": "red"}

        visualizer = WorkflowVisualizer(
            workflow, node_colors=node_colors, edge_colors=edge_colors
        )

        assert visualizer.node_colors["data"] == "blue"
        assert visualizer.edge_colors["error"] == "red"

    @patch("matplotlib.pyplot.savefig")
    @patch("matplotlib.pyplot.show")
    @patch("matplotlib.pyplot.figure")
    def test_visualize(self, mock_figure, mock_show, mock_savefig):
        """Test workflow visualization."""
        # Create a workflow directly
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        # Create mock nodes
        node1 = MockNode(node_id="node1", name="Node 1")
        node2 = MockNode(node_id="node2", name="Node 2")

        # Add nodes to workflow manually
        workflow.graph.add_node("node1", node=node1, type="MockNode")
        workflow.graph.add_node("node2", node=node2, type="MockNode")

        # Create nodes dict manually
        workflow.nodes["node1"] = NodeInstance(node_id="node1", node_type="MockNode")
        workflow.nodes["node2"] = NodeInstance(node_id="node2", node_type="MockNode")

        # Add to node instances
        workflow._node_instances["node1"] = node1
        workflow._node_instances["node2"] = node2

        visualizer = WorkflowVisualizer(workflow)

        # Skip the actual drawing which has matplotlib compatibility issues in testing
        with patch.object(visualizer, "_draw_graph"):
            # Call visualize
            visualizer.visualize()

            # Check that matplotlib methods were called
            assert mock_figure.called
            assert mock_show.called

    @patch("matplotlib.pyplot.savefig")
    def test_save_visualization(self, mock_savefig):
        """Test saving visualization to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            visualizer.save(tmp.name)
            mock_savefig.assert_called_once_with(tmp.name, dpi=300, bbox_inches="tight")

    def test_get_node_color(self):
        """Test getting node color based on type."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        # Test default colors
        assert (
            visualizer._get_node_color("DataReader") == visualizer.node_colors["data"]
        )
        assert (
            visualizer._get_node_color("Transformer")
            == visualizer.node_colors["transform"]
        )
        assert visualizer._get_node_color("AINode") == visualizer.node_colors["ai"]
        assert (
            visualizer._get_node_color("Unknown") == visualizer.node_colors["default"]
        )

    def test_default_node_colors(self):
        """Test default node color scheme."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        default_colors = visualizer._default_node_colors()

        assert "data" in default_colors
        assert "transform" in default_colors
        assert "logic" in default_colors
        assert "ai" in default_colors
        assert "default" in default_colors

    def test_default_edge_colors(self):
        """Test default edge color scheme."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        default_colors = visualizer._default_edge_colors()

        assert "default" in default_colors
        assert "error" in default_colors
        assert "conditional" in default_colors

    @patch("matplotlib.pyplot.figure")
    def test_complex_workflow_visualization(self, mock_figure):
        """Test visualizing complex workflow."""
        # Create a workflow directly
        workflow = Workflow(workflow_id="complex", name="Complex Workflow")

        # Create mock nodes
        reader_node = MockNode(node_id="reader", name="Reader")
        filter_node = MockNode(node_id="filter", name="Filter")
        ai_node = MockNode(node_id="ai", name="AI")
        writer_node = MockNode(node_id="writer", name="Writer")

        # Add nodes to workflow manually
        workflow.graph.add_node("reader", node=reader_node, type="DataReader")
        workflow.graph.add_node("filter", node=filter_node, type="DataFilter")
        workflow.graph.add_node("ai", node=ai_node, type="AIProcessor")
        workflow.graph.add_node("writer", node=writer_node, type="DataWriter")

        # Create nodes dict manually
        workflow.nodes["reader"] = NodeInstance(
            node_id="reader", node_type="DataReader"
        )
        workflow.nodes["filter"] = NodeInstance(
            node_id="filter", node_type="DataFilter"
        )
        workflow.nodes["ai"] = NodeInstance(node_id="ai", node_type="AIProcessor")
        workflow.nodes["writer"] = NodeInstance(
            node_id="writer", node_type="DataWriter"
        )

        # Add to node instances
        workflow._node_instances["reader"] = reader_node
        workflow._node_instances["filter"] = filter_node
        workflow._node_instances["ai"] = ai_node
        workflow._node_instances["writer"] = writer_node

        visualizer = WorkflowVisualizer(workflow)

        # Reset mock to clear previous calls
        mock_figure.reset_mock()

        # Mock the actual drawing to avoid matplotlib backend issues
        with patch.object(visualizer, "_draw_graph"):
            visualizer.visualize()

        # Just check that figure was called, don't be strict about number of calls
        assert mock_figure.called

    def test_visualizer_with_empty_workflow(self):
        """Test visualizing empty workflow."""
        workflow = Workflow(workflow_id="empty", name="Empty Workflow")
        visualizer = WorkflowVisualizer(workflow)

        # Should not raise exception
        with patch("matplotlib.pyplot.figure"):
            with patch("matplotlib.pyplot.show"):
                visualizer.visualize()

    @patch("matplotlib.pyplot.figure")
    def test_visualize_with_labels(self, mock_figure):
        """Test visualization with custom labels."""
        # Create workflow directly
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        # Create and add mock node
        node = MockNode(node_id="test_node", name="Test Node")
        workflow.graph.add_node("test_node", node=node, type="MockNode")

        # Add to nodes dict
        workflow.nodes["test_node"] = NodeInstance(
            node_id="test_node", node_type="MockNode"
        )

        # Add to node instances
        workflow._node_instances["test_node"] = node

        visualizer = WorkflowVisualizer(workflow)

        # Test that the node labels are properly extracted
        with patch.object(visualizer, "_draw_graph"):
            visualizer.visualize()

            # Check that labels were created
            assert visualizer._get_node_labels() == {"test_node": "Test Node"}

    def test_get_node_labels(self):
        """Test getting node labels from workflow."""
        # Create workflow directly
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        # Create and add mock nodes
        node1 = MockNode(node_id="node1", name="First Node")
        node2 = MockNode(node_id="node2", name="Second Node")

        # Add nodes to workflow
        workflow.graph.add_node("node1", node=node1, type="MockNode")
        workflow.graph.add_node("node2", node=node2, type="MockNode")

        # Add to nodes dict
        workflow.nodes["node1"] = NodeInstance(node_id="node1", node_type="MockNode")
        workflow.nodes["node2"] = NodeInstance(node_id="node2", node_type="MockNode")

        # Add to node instances
        workflow._node_instances["node1"] = node1
        workflow._node_instances["node2"] = node2

        visualizer = WorkflowVisualizer(workflow)
        labels = visualizer._get_node_labels()

        assert labels == {"node1": "First Node", "node2": "Second Node"}

    def test_visualizer_with_custom_layout(self):
        """Test visualizer with custom layout algorithm."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow, layout="circular")

        assert visualizer.layout == "circular"

    @patch("matplotlib.pyplot.figure")
    def test_save_high_dpi(self, mock_figure):
        """Test saving visualization with high DPI."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            with patch("matplotlib.pyplot.savefig") as mock_savefig:
                visualizer.save(tmp.name, dpi=600)
                mock_savefig.assert_called_once_with(
                    tmp.name, dpi=600, bbox_inches="tight"
                )

    def test_visualizer_error_handling(self):
        """Test error handling in visualizer."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        # Create a mock node that raises an error when accessed
        node = MockNode(node_id="error_node", name="Error Node")
        workflow.graph.add_node("error_node", node=node, type="MockNode")
        workflow.nodes["error_node"] = NodeInstance(
            node_id="error_node", node_type="MockNode"
        )
        workflow._node_instances["error_node"] = node

        # Test with failing draw graph
        with patch.object(
            visualizer, "_draw_graph", side_effect=ValueError("Test error")
        ):
            with pytest.raises(ValueError):
                with patch("matplotlib.pyplot.figure"):
                    with patch("matplotlib.pyplot.close"):
                        visualizer.visualize()
