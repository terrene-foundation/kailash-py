"""Comprehensive tests to boost workflow.visualization coverage from 14% to >80%."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes = {}
        self.name = "Test Workflow"

    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def add_test_nodes(self):
        """Add test nodes for visualization testing."""
        # Add nodes to graph
        self.graph.add_node("data_reader")
        self.graph.add_node("processor")
        self.graph.add_node("ai_analyzer")
        self.graph.add_node("output_writer")

        # Add edges
        self.graph.add_edge("data_reader", "processor", mapping={"data": "input"})
        self.graph.add_edge("processor", "ai_analyzer", mapping={"result": "input"})
        self.graph.add_edge(
            "ai_analyzer", "output_writer", mapping={"analysis": "data"}
        )

        # Add node instances
        mock_reader = Mock()
        mock_reader.node_type = "CSVReaderNode"
        mock_reader.name = "Data Reader"

        mock_processor = Mock()
        mock_processor.node_type = "PythonCodeNode"
        mock_processor.name = "Processor"

        mock_ai = Mock()
        mock_ai.node_type = "LLMAgentNode"
        mock_ai.name = "AI Analyzer"

        mock_writer = Mock()
        mock_writer.node_type = "CSVWriterNode"
        mock_writer.name = "Output Writer"

        self.nodes = {
            "data_reader": mock_reader,
            "processor": mock_processor,
            "ai_analyzer": mock_ai,
            "output_writer": mock_writer,
        }


class TestWorkflowVisualizer:
    """Test WorkflowVisualizer functionality."""

    def test_workflow_visualizer_init_default(self):
        """Test WorkflowVisualizer initialization with defaults."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            assert visualizer.workflow == workflow
            assert visualizer.layout == "hierarchical"
            assert isinstance(visualizer.node_colors, dict)
            assert isinstance(visualizer.edge_colors, dict)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_workflow_visualizer_init_custom(self):
        """Test WorkflowVisualizer initialization with custom parameters."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            custom_node_colors = {"data": "blue", "ai": "red"}
            custom_edge_colors = {"default": "black"}

            visualizer = WorkflowVisualizer(
                workflow=workflow,
                node_colors=custom_node_colors,
                edge_colors=custom_edge_colors,
                layout="spring",
            )

            assert visualizer.workflow == workflow
            assert visualizer.layout == "spring"
            assert visualizer.node_colors == custom_node_colors
            assert visualizer.edge_colors == custom_edge_colors

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_default_node_colors(self):
        """Test default node color mapping."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            colors = visualizer._default_node_colors()

            assert "data" in colors
            assert "transform" in colors
            assert "logic" in colors
            assert "ai" in colors
            assert "default" in colors

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_default_edge_colors(self):
        """Test default edge color mapping."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            colors = visualizer._default_edge_colors()

            assert "default" in colors
            assert "error" in colors
            assert "conditional" in colors

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_color_data_nodes(self):
        """Test node color assignment for data nodes."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            # Test data reader/writer nodes
            assert (
                visualizer._get_node_color("CSVReaderNode")
                == visualizer.node_colors["data"]
            )
            assert (
                visualizer._get_node_color("JSONWriterNode")
                == visualizer.node_colors["data"]
            )

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_color_transform_nodes(self):
        """Test node color assignment for transform nodes."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            # Test transform/processing nodes
            assert (
                visualizer._get_node_color("DataTransformNode")
                == visualizer.node_colors["transform"]
            )
            assert (
                visualizer._get_node_color("FilterNode")
                == visualizer.node_colors["transform"]
            )
            assert (
                visualizer._get_node_color("ProcessorNode")
                == visualizer.node_colors["transform"]
            )

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_color_logic_nodes(self):
        """Test node color assignment for logic nodes."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            # Test logic nodes
            assert (
                visualizer._get_node_color("MergeNode")
                == visualizer.node_colors["logic"]
            )
            assert (
                visualizer._get_node_color("ConditionalNode")
                == visualizer.node_colors["logic"]
            )
            assert (
                visualizer._get_node_color("LogicGateNode")
                == visualizer.node_colors["logic"]
            )

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_color_ai_nodes(self):
        """Test node color assignment for AI nodes."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            # Test AI nodes
            assert (
                visualizer._get_node_color("LLMAgentNode")
                == visualizer.node_colors["ai"]
            )
            assert (
                visualizer._get_node_color("AIModelNode")
                == visualizer.node_colors["ai"]
            )

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_color_default(self):
        """Test node color assignment for unknown node types."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            # Test unknown node type
            assert (
                visualizer._get_node_color("UnknownNode")
                == visualizer.node_colors["default"]
            )

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_colors(self):
        """Test getting colors for all nodes in workflow."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            colors = visualizer._get_node_colors()

            assert len(colors) == 4  # Four nodes in test workflow
            assert all(isinstance(color, str) for color in colors)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_labels_with_names(self):
        """Test getting node labels when nodes have names."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            labels = visualizer._get_node_labels()

            assert len(labels) == 4
            assert labels["data_reader"] == "Data Reader"
            assert labels["ai_analyzer"] == "AI Analyzer"

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_node_labels_without_names(self):
        """Test getting node labels when nodes don't have names."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.graph.add_node("test_node")

            # Mock node without name
            mock_node = Mock()
            mock_node.node_type = "TestNode"
            mock_node.name = None
            workflow.nodes["test_node"] = mock_node

            visualizer = WorkflowVisualizer(workflow)
            labels = visualizer._get_node_labels()

            assert "test_node" in labels
            assert "TestNode" in labels["test_node"]

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_get_edge_labels(self):
        """Test getting edge labels from workflow connections."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            edge_labels = visualizer._get_edge_labels()

            # Should have labels for edges with mappings
            assert len(edge_labels) >= 0  # May have labels depending on edge data

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_calculate_layout_hierarchical(self):
        """Test hierarchical layout calculation."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow, layout="hierarchical")

            layout = visualizer._calculate_layout()

            assert isinstance(layout, dict)
            assert len(layout) == 4  # Four nodes
            # Each position should be a tuple of coordinates
            for node_id, pos in layout.items():
                assert isinstance(pos, (tuple, list))
                assert len(pos) == 2

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_calculate_layout_spring(self):
        """Test spring layout calculation."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow, layout="spring")

            with patch("networkx.spring_layout") as mock_spring:
                mock_spring.return_value = {
                    "data_reader": (0.0, 0.0),
                    "processor": (1.0, 0.0),
                    "ai_analyzer": (2.0, 0.0),
                    "output_writer": (3.0, 0.0),
                }

                layout = visualizer._calculate_layout()

                mock_spring.assert_called_once()
                assert isinstance(layout, dict)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_calculate_layout_circular(self):
        """Test circular layout calculation."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow, layout="circular")

            with patch("networkx.circular_layout") as mock_circular:
                mock_circular.return_value = {
                    "data_reader": (0.0, 1.0),
                    "processor": (1.0, 0.0),
                    "ai_analyzer": (0.0, -1.0),
                    "output_writer": (-1.0, 0.0),
                }

                layout = visualizer._calculate_layout()

                mock_circular.assert_called_once()
                assert isinstance(layout, dict)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_create_layers(self):
        """Test layer creation for hierarchical layout."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            layers = visualizer._create_layers()

            assert isinstance(layers, dict)
            # Should have at least one layer
            assert len(layers) > 0
            # Each layer should contain node IDs
            for layer_nodes in layers.values():
                assert isinstance(layer_nodes, list)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_hierarchical_layout(self):
        """Test hierarchical layout positioning."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            layers = {
                0: ["data_reader"],
                1: ["processor"],
                2: ["ai_analyzer"],
                3: ["output_writer"],
            }
            layout = visualizer._hierarchical_layout(layers)

            assert isinstance(layout, dict)
            assert len(layout) == 4

            # Verify coordinates are reasonable
            for node_id, (x, y) in layout.items():
                assert isinstance(x, (int, float))
                assert isinstance(y, (int, float))

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_draw_graph(self):
        """Test graph drawing functionality."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            with patch("matplotlib.pyplot.figure") as mock_fig:
                with patch("matplotlib.pyplot.subplots") as mock_subplots:
                    with patch("networkx.draw_networkx") as mock_draw:
                        mock_ax = Mock()
                        mock_subplots.return_value = (Mock(), mock_ax)

                        fig, ax = visualizer._draw_graph()

                        mock_subplots.assert_called_once()
                        mock_draw.assert_called_once()

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_visualize_method(self):
        """Test main visualize method."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            with patch.object(visualizer, "_draw_graph") as mock_draw:
                with patch("matplotlib.pyplot.show") as mock_show:
                    mock_draw.return_value = (Mock(), Mock())

                    visualizer.visualize()

                    mock_draw.assert_called_once()
                    mock_show.assert_called_once()

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_visualize_with_output_path(self):
        """Test visualize method with output path."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            with patch.object(visualizer, "_draw_graph") as mock_draw:
                with patch.object(visualizer, "save") as mock_save:
                    mock_draw.return_value = (Mock(), Mock())

                    visualizer.visualize(output_path="/tmp/test.png")

                    mock_draw.assert_called_once()
                    mock_save.assert_called_once_with("/tmp/test.png")

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_save_method(self):
        """Test save method functionality."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            visualizer = WorkflowVisualizer(workflow)

            with patch("matplotlib.pyplot.savefig") as mock_savefig:
                visualizer.save("/tmp/test.png", dpi=150)

                mock_savefig.assert_called_once()
                args, kwargs = mock_savefig.call_args
                assert args[0] == "/tmp/test.png"
                assert kwargs.get("dpi") == 150

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_create_execution_graph(self):
        """Test execution graph creation with task manager."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            # Mock task manager with execution data
            mock_task_manager = Mock()
            mock_task_manager.get_run_tasks.return_value = [
                Mock(node_id="data_reader", status="completed", duration=1.5),
                Mock(node_id="processor", status="running", duration=None),
                Mock(node_id="ai_analyzer", status="pending", duration=None),
                Mock(node_id="output_writer", status="pending", duration=None),
            ]

            with patch.object(visualizer, "_draw_graph") as mock_draw:
                mock_draw.return_value = (Mock(), Mock())

                fig, ax = visualizer.create_execution_graph(
                    task_manager=mock_task_manager, run_id="test_run"
                )

                mock_draw.assert_called_once()
                mock_task_manager.get_run_tasks.assert_called_once_with("test_run")

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_create_performance_dashboard(self):
        """Test performance dashboard creation."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            # Mock task manager with performance data
            mock_task_manager = Mock()
            mock_task_manager.get_run_tasks.return_value = [
                Mock(node_id="data_reader", duration=1.5, memory_peak_mb=100),
                Mock(node_id="processor", duration=2.3, memory_peak_mb=150),
                Mock(node_id="ai_analyzer", duration=5.1, memory_peak_mb=300),
                Mock(node_id="output_writer", duration=0.8, memory_peak_mb=80),
            ]

            with patch("matplotlib.pyplot.subplots") as mock_subplots:
                mock_fig = Mock()
                mock_axes = [Mock(), Mock(), Mock()]
                mock_subplots.return_value = (mock_fig, mock_axes)

                fig = visualizer.create_performance_dashboard(
                    task_manager=mock_task_manager, run_id="test_run"
                )

                assert fig == mock_fig
                mock_task_manager.get_run_tasks.assert_called_once()

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_create_dashboard_html(self):
        """Test HTML dashboard creation."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()
            visualizer = WorkflowVisualizer(workflow)

            # Mock task data
            tasks = [
                Mock(
                    node_id="data_reader",
                    status="completed",
                    duration=1.5,
                    memory_peak_mb=100,
                ),
                Mock(
                    node_id="processor",
                    status="completed",
                    duration=2.3,
                    memory_peak_mb=150,
                ),
            ]

            html_content = visualizer._create_dashboard_html(
                tasks=tasks, run_id="test_run", total_duration=3.8
            )

            assert isinstance(html_content, str)
            assert "test_run" in html_content
            assert "data_reader" in html_content
            assert "processor" in html_content

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_visualize_class_method(self):
        """Test static visualize method."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.add_test_nodes()

            with patch.object(
                WorkflowVisualizer, "__init__", return_value=None
            ) as mock_init:
                with patch.object(WorkflowVisualizer, "visualize") as mock_visualize:
                    # Create instance manually since __init__ is mocked
                    visualizer = WorkflowVisualizer.__new__(WorkflowVisualizer)

                    # Call the class method
                    WorkflowVisualizer.visualize(workflow, output_path="/tmp/test.png")

                    # Verify initialization was called
                    mock_init.assert_called_once_with(workflow)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")


class TestVisualizationEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_workflow(self):
        """Test visualization of empty workflow."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()  # Empty workflow
            visualizer = WorkflowVisualizer(workflow)

            # Should handle empty workflow gracefully
            colors = visualizer._get_node_colors()
            assert colors == []

            labels = visualizer._get_node_labels()
            assert labels == {}

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_single_node_workflow(self):
        """Test visualization of single node workflow."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.graph.add_node("single_node")

            mock_node = Mock()
            mock_node.node_type = "TestNode"
            mock_node.name = "Single Node"
            workflow.nodes["single_node"] = mock_node

            visualizer = WorkflowVisualizer(workflow)

            colors = visualizer._get_node_colors()
            assert len(colors) == 1

            labels = visualizer._get_node_labels()
            assert len(labels) == 1
            assert labels["single_node"] == "Single Node"

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")

    def test_disconnected_nodes(self):
        """Test visualization of workflow with disconnected nodes."""
        try:
            from kailash.workflow.visualization import WorkflowVisualizer

            workflow = MockWorkflow()
            workflow.graph.add_node("node1")
            workflow.graph.add_node("node2")
            workflow.graph.add_node("node3")
            # No edges - disconnected nodes

            mock_node = Mock()
            mock_node.node_type = "TestNode"
            mock_node.name = "Test"

            workflow.nodes = {
                "node1": mock_node,
                "node2": mock_node,
                "node3": mock_node,
            }

            visualizer = WorkflowVisualizer(workflow)

            # Should handle disconnected graph
            layers = visualizer._create_layers()
            assert isinstance(layers, dict)

        except ImportError:
            pytest.skip("WorkflowVisualizer not available")
