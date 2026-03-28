"""Tests for WorkflowVisualizer methods — updated for v1.0.0 Mermaid/DOT API."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


class TestWorkflowVisualizerConstructor:
    """Test WorkflowVisualizer constructor flexibility."""

    def test_constructor_without_workflow(self):
        """Test creating visualizer without workflow."""
        visualizer = WorkflowVisualizer()
        assert hasattr(visualizer, "workflow")
        assert visualizer.workflow is None
        assert visualizer.direction == "TB"

    def test_constructor_with_workflow(self):
        """Test creating visualizer with workflow."""
        workflow = Mock(spec=Workflow)
        visualizer = WorkflowVisualizer(workflow=workflow)
        assert visualizer.workflow is workflow

    def test_constructor_with_custom_direction(self):
        """Test creating visualizer with custom direction."""
        visualizer = WorkflowVisualizer(direction="LR")
        assert visualizer.direction == "LR"

    def test_constructor_default_direction(self):
        """Test default direction is TB."""
        visualizer = WorkflowVisualizer()
        assert visualizer.direction == "TB"


class TestToMermaidMethod:
    """Test to_mermaid method."""

    def test_to_mermaid_empty_workflow(self):
        """Test to_mermaid with empty workflow."""
        import networkx as nx

        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.nodes = {}
        workflow.name = "Test"

        visualizer = WorkflowVisualizer(workflow=workflow)
        result = visualizer.to_mermaid()

        assert result.startswith("graph TB")

    def test_to_mermaid_uses_workflow_parameter(self):
        """Test to_mermaid accepts workflow parameter."""
        import networkx as nx

        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("node1")
        workflow.nodes = {}
        workflow.name = "Test"

        visualizer = WorkflowVisualizer()
        result = visualizer.to_mermaid(workflow=workflow)

        assert "node1" in result

    def test_to_mermaid_no_workflow_raises(self):
        """Test to_mermaid raises when no workflow."""
        visualizer = WorkflowVisualizer()
        with pytest.raises(ValueError, match="No workflow provided"):
            visualizer.to_mermaid()

    def test_to_mermaid_with_edges(self):
        """Test to_mermaid with edges."""
        import networkx as nx

        from kailash.workflow import NodeInstance

        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("node1")
        workflow.graph.add_node("node2")
        workflow.graph.add_edge(
            "node1", "node2", from_output="result", to_input="input"
        )

        ni1 = Mock()
        ni1.node_type = "PythonCodeNode"
        ni2 = Mock()
        ni2.node_type = "CSVWriterNode"
        workflow.nodes = {"node1": ni1, "node2": ni2}
        workflow.name = "Test"

        visualizer = WorkflowVisualizer(workflow=workflow)
        result = visualizer.to_mermaid()

        assert "node1" in result
        assert "node2" in result
        assert "-->" in result


class TestToDotMethod:
    """Test to_dot method."""

    def test_to_dot_empty_workflow(self):
        """Test to_dot with empty workflow."""
        import networkx as nx

        workflow = Mock(spec=Workflow)
        workflow.graph = nx.DiGraph()
        workflow.nodes = {}
        workflow.name = "Test"

        visualizer = WorkflowVisualizer(workflow=workflow)
        result = visualizer.to_dot()

        assert "digraph" in result

    def test_to_dot_no_workflow_raises(self):
        """Test to_dot raises when no workflow."""
        visualizer = WorkflowVisualizer()
        with pytest.raises(ValueError, match="No workflow provided"):
            visualizer.to_dot()


class TestHelperMethods:
    """Test helper methods."""

    def test_sanitize_id(self):
        """Test _sanitize_id."""
        visualizer = WorkflowVisualizer()
        assert visualizer._sanitize_id("my-node") == "my_node"
        assert visualizer._sanitize_id("my.node") == "my_node"
        assert visualizer._sanitize_id("my node") == "my_node"

    def test_get_node_shape_reader(self):
        """Test _get_node_shape for reader."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("CSVReaderNode")
        assert open_d == "[("

    def test_get_node_shape_ai(self):
        """Test _get_node_shape for AI."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("LLMAgentNode")
        assert open_d == "[["

    def test_get_node_shape_code(self):
        """Test _get_node_shape for code."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("PythonCodeNode")
        assert open_d == "[/"

    def test_get_node_shape_default(self):
        """Test _get_node_shape default."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("UnknownNode")
        assert open_d == "["


class TestVisualizationIntegration:
    """Test integration with real workflow objects."""

    def test_visualize_returns_mermaid_string(self):
        """Test visualize method returns mermaid string."""
        workflow = Workflow("test", "Test Workflow")
        visualizer = WorkflowVisualizer(workflow=workflow)

        result = visualizer.visualize()
        assert isinstance(result, str)
        assert "graph TB" in result

    def test_visualize_no_workflow_raises(self):
        """Test visualize raises when no workflow set."""
        visualizer = WorkflowVisualizer()
        with pytest.raises(ValueError, match="No workflow provided"):
            visualizer.visualize()

    def test_visualize_saves_to_file(self):
        """Test visualize saves output when output_path provided."""
        workflow = Workflow("test", "Test Workflow")
        visualizer = WorkflowVisualizer(workflow=workflow)

        with tempfile.TemporaryDirectory() as tmpdir:
            # No suffix — visualize wraps in ```mermaid fencing
            output_path = str(Path(tmpdir) / "workflow")
            result = visualizer.visualize(output_path=output_path)
            saved_path = Path(output_path + ".md")
            assert saved_path.exists()
            content = saved_path.read_text()
            assert "mermaid" in content

    def test_save_method(self):
        """Test save method."""
        workflow = Workflow("test", "Test Workflow")
        visualizer = WorkflowVisualizer(workflow=workflow)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "out.md")
            visualizer.save(output_path)
            assert Path(output_path).exists()

    def test_direction_appears_in_output(self):
        """Test direction appears in mermaid output."""
        workflow = Workflow("test", "Test")
        visualizer = WorkflowVisualizer(workflow=workflow, direction="LR")
        result = visualizer.to_mermaid()
        assert "graph LR" in result
