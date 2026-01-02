"""Comprehensive tests for WorkflowVisualizer methods added in TODO-111."""

from unittest.mock import MagicMock, Mock, patch

import matplotlib.pyplot as plt
import networkx as nx
import pytest
from kailash.nodes.base import Node
from kailash.nodes.code import PythonCodeNode
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


class MockNode(Node):
    """Mock node for testing."""

    def get_parameters(self):
        return {}

    def execute(self, **inputs):
        return {"success": True}


class TestWorkflowVisualizerConstructor:
    """Test WorkflowVisualizer constructor flexibility."""

    def test_constructor_without_workflow(self):
        """Test creating visualizer without workflow."""
        visualizer = WorkflowVisualizer()
        # The constructor might not set workflow to None explicitly
        # Just check that we can create it without workflow
        assert hasattr(visualizer, "workflow")
        assert visualizer.layout == "hierarchical"
        assert "data" in visualizer.node_colors
        assert "default" in visualizer.edge_colors  # Check for 'default' edge color

    def test_constructor_with_workflow(self):
        """Test creating visualizer with workflow."""
        workflow = Mock(spec=Workflow)
        visualizer = WorkflowVisualizer(workflow=workflow)
        assert visualizer.workflow is workflow

    def test_constructor_with_custom_colors(self):
        """Test creating visualizer with custom colors."""
        custom_node_colors = {"custom": "#FF0000"}
        custom_edge_colors = {"special": "#00FF00"}

        visualizer = WorkflowVisualizer(
            node_colors=custom_node_colors, edge_colors=custom_edge_colors
        )

        assert visualizer.node_colors == custom_node_colors
        assert visualizer.edge_colors == custom_edge_colors

    def test_constructor_with_custom_layout(self):
        """Test creating visualizer with custom layout."""
        visualizer = WorkflowVisualizer(layout="circular")
        assert visualizer.layout == "circular"


class TestDrawGraphMethod:
    """Test _draw_graph method functionality."""

    @patch("matplotlib.pyplot.gca")
    @patch("networkx.draw_networkx_edge_labels")
    @patch("networkx.draw_networkx_nodes")
    @patch("networkx.draw_networkx_edges")
    @patch("networkx.draw_networkx_labels")
    def test_draw_graph_with_workflow_parameter(
        self, mock_labels, mock_edges, mock_nodes, mock_edge_labels, mock_gca
    ):
        """Test _draw_graph accepts workflow parameter."""
        # Setup
        visualizer = WorkflowVisualizer()
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("node1")
        workflow.graph.add_node("node2")
        workflow.graph.add_edge("node1", "node2")

        # Mock matplotlib axis
        mock_ax = Mock()
        mock_gca.return_value = mock_ax

        # Mock helper methods
        visualizer._get_layout_positions = Mock(
            return_value={"node1": (0, 0), "node2": (1, 1)}
        )
        visualizer._get_node_colors = Mock(return_value=["red", "blue"])

        # Execute
        visualizer._draw_graph(workflow=workflow)

        # Verify
        visualizer._get_layout_positions.assert_called_once_with(workflow)
        visualizer._get_node_colors.assert_called_once_with(workflow)
        mock_nodes.assert_called_once()

    @patch("networkx.draw_networkx_nodes")
    @patch("networkx.draw_networkx_edges")
    @patch("networkx.draw_networkx_labels")
    def test_draw_graph_with_custom_parameters(
        self, mock_labels, mock_edges, mock_nodes
    ):
        """Test _draw_graph with custom position and colors."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("node1")
        visualizer = WorkflowVisualizer(workflow=workflow)

        custom_pos = {"node1": (5, 5)}
        custom_colors = ["green"]

        # Execute
        visualizer._draw_graph(
            pos=custom_pos,
            node_colors=custom_colors,
            show_labels=False,
            show_connections=False,
        )

        # Verify custom parameters used
        mock_nodes.assert_called_once()
        call_args = mock_nodes.call_args
        assert call_args[0][1] == custom_pos  # pos parameter
        assert call_args[1]["node_color"] == custom_colors

        # Labels should not be drawn, but edges are always drawn
        mock_labels.assert_not_called()
        # Edges are always drawn, just edge labels are controlled by show_connections
        mock_edges.assert_called_once()

    def test_draw_graph_without_workflow_raises_error(self):
        """Test _draw_graph raises error when no workflow provided."""
        visualizer = WorkflowVisualizer()

        with pytest.raises(ValueError, match="No workflow provided to draw"):
            visualizer._draw_graph()

    @patch("matplotlib.pyplot.gca")
    @patch("networkx.draw_networkx_nodes")
    @patch("networkx.draw_networkx_edges")
    @patch("networkx.draw_networkx_labels")
    def test_draw_graph_uses_instance_workflow(
        self, mock_labels, mock_edges, mock_nodes, mock_gca
    ):
        """Test _draw_graph uses instance workflow when no parameter given."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("test")
        visualizer = WorkflowVisualizer(workflow=workflow)

        # Mock matplotlib axis
        mock_ax = Mock()
        mock_gca.return_value = mock_ax

        # Mock helpers
        visualizer._get_layout_positions = Mock(return_value={"test": (0, 0)})
        visualizer._get_node_colors = Mock(return_value=["blue"])

        # Execute without workflow parameter
        visualizer._draw_graph()

        # Verify instance workflow was used
        visualizer._get_layout_positions.assert_called_once_with(workflow)
        mock_nodes.assert_called_once()


class TestHelperMethods:
    """Test helper methods for layout and colors."""

    def test_get_layout_positions(self):
        """Test _get_layout_positions method."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_nodes_from(["A", "B", "C"])
        workflow.graph.add_edges_from([("A", "B"), ("B", "C")])

        original_workflow = Mock(spec=Workflow)
        visualizer = WorkflowVisualizer(workflow=original_workflow)

        # Mock _calculate_layout
        expected_pos = {"A": (0, 0), "B": (1, 0), "C": (2, 0)}
        with patch.object(
            visualizer, "_calculate_layout", return_value=expected_pos
        ) as mock_calc:
            # Execute
            positions = visualizer._get_layout_positions(workflow)

            # Verify
            assert positions == expected_pos
            mock_calc.assert_called_once()
            # Original workflow should be restored
            assert visualizer.workflow is original_workflow

    def test_get_node_colors_by_type(self):
        """Test _get_node_colors maps node types to colors."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_nodes_from(["csv_node", "transform_node", "ai_node"])

        # Create mock nodes with different types
        csv_node = Mock()
        csv_node.__class__.__name__ = "CSVReaderNode"

        transform_node = Mock()
        transform_node.__class__.__name__ = "PythonCodeNode"

        ai_node = Mock()
        ai_node.__class__.__name__ = "LLMAgentNode"

        def get_node_side_effect(node_id):
            return {
                "csv_node": csv_node,
                "transform_node": transform_node,
                "ai_node": ai_node,
            }.get(node_id)

        workflow.get_node.side_effect = get_node_side_effect

        visualizer = WorkflowVisualizer()

        # Execute
        colors = visualizer._get_node_colors(workflow)

        # Verify correct color mapping
        assert len(colors) == 3
        assert colors[0] == visualizer.node_colors["data"]  # CSV -> data
        assert colors[1] == visualizer.node_colors["transform"]  # Python -> transform
        assert colors[2] == visualizer.node_colors["ai"]  # LLM -> ai

    def test_get_node_colors_default_fallback(self):
        """Test _get_node_colors uses default for unknown types."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("unknown")

        unknown_node = Mock()
        unknown_node.__class__.__name__ = "UnknownNodeType"
        workflow.get_node.return_value = unknown_node

        visualizer = WorkflowVisualizer()

        # Execute
        colors = visualizer._get_node_colors(workflow)

        # Verify default color used
        assert len(colors) == 1
        assert colors[0] == visualizer.node_colors["default"]

    def test_get_node_colors_missing_node(self):
        """Test _get_node_colors handles missing nodes."""
        # Setup
        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("missing")
        workflow.get_node.return_value = None

        visualizer = WorkflowVisualizer()

        # Execute
        colors = visualizer._get_node_colors(workflow)

        # Verify default color used for missing node
        assert len(colors) == 1
        assert colors[0] == visualizer.node_colors["default"]


class TestVisualizationIntegration:
    """Test integration with real workflow objects."""

    @patch("matplotlib.pyplot.savefig")
    @patch("matplotlib.pyplot.figure")
    def test_visualize_with_optional_workflow(self, mock_figure, mock_savefig):
        """Test visualize method works with optional workflow parameter."""
        # Setup
        visualizer = WorkflowVisualizer()  # No workflow in constructor

        # Create test workflow using correct API
        workflow = Workflow("test", "Test Workflow")
        workflow.add_node("node1", MockNode())
        workflow.add_node("node2", MockNode())
        workflow.connect("node1", "node2", mapping={"output": "input"})

        # Mock the drawing process
        with patch.object(visualizer, "_draw_graph") as mock_draw:
            # Execute - visualize without workflow should raise error
            with pytest.raises(ValueError, match="No workflow to visualize"):
                visualizer.visualize(output_path="test.png")

            # Drawing should not have been attempted
            mock_draw.assert_not_called()

        # Now set workflow and try again
        visualizer.workflow = workflow
        with patch.object(visualizer, "_draw_graph") as mock_draw:
            visualizer.visualize(output_path="test.png")

            # Should work now
            mock_draw.assert_called_once()
            # Check that savefig was called with the expected filename
            mock_savefig.assert_called_once()
            call_args = mock_savefig.call_args
            assert call_args[0][0] == "test.png"  # First positional argument

    def test_default_colors_comprehensive(self):
        """Test all default color mappings."""
        visualizer = WorkflowVisualizer()

        # Test node color defaults
        assert visualizer.node_colors["data"] == "lightblue"
        assert visualizer.node_colors["transform"] == "lightyellow"
        assert visualizer.node_colors["logic"] == "lightcoral"
        assert visualizer.node_colors["ai"] == "lightpink"
        assert visualizer.node_colors["default"] == "lightgray"

        # Test edge color defaults
        assert "default" in visualizer.edge_colors
        assert visualizer.edge_colors["default"] == "gray"
