"""Tests for workflow visualization module."""

import tempfile
from pathlib import Path

import pytest

from kailash.workflow import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


class TestWorkflowVisualizer:
    """Test WorkflowVisualizer class."""

    def test_visualizer_creation(self):
        """Test creating workflow visualizer."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)

        assert visualizer.workflow == workflow
        assert visualizer.direction == "TB"

    def test_visualizer_without_workflow(self):
        """Test creating visualizer without workflow."""
        visualizer = WorkflowVisualizer()
        assert visualizer.workflow is None

    def test_to_mermaid_empty_workflow(self):
        """Test generating Mermaid for empty workflow."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)

        result = visualizer.to_mermaid()
        assert result.startswith("graph TB")

    def test_to_mermaid_with_nodes(self):
        """Test generating Mermaid with nodes."""
        import networkx as nx
        from unittest.mock import Mock

        workflow = Mock()
        workflow.graph = nx.DiGraph()
        workflow.graph.add_node("node1")
        workflow.graph.add_node("node2")
        workflow.graph.add_edge(
            "node1", "node2", from_output="result", to_input="input"
        )

        ni1 = Mock()
        ni1.node_type = "PythonCodeNode"
        ni2 = Mock()
        ni2.node_type = "PythonCodeNode"
        workflow.nodes = {"node1": ni1, "node2": ni2}
        workflow.name = "Test Workflow"

        visualizer = WorkflowVisualizer(workflow)
        result = visualizer.to_mermaid()

        assert "node1" in result
        assert "node2" in result
        assert "graph TB" in result

    def test_to_dot_empty_workflow(self):
        """Test generating DOT for empty workflow."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)

        result = visualizer.to_dot()
        assert "digraph" in result

    def test_to_mermaid_no_workflow_raises(self):
        """Test to_mermaid raises when no workflow provided."""
        visualizer = WorkflowVisualizer()
        with pytest.raises(ValueError, match="No workflow provided"):
            visualizer.to_mermaid()

    def test_to_dot_no_workflow_raises(self):
        """Test to_dot raises when no workflow provided."""
        visualizer = WorkflowVisualizer()
        with pytest.raises(ValueError, match="No workflow provided"):
            visualizer.to_dot()

    def test_visualize_returns_string(self):
        """Test visualize returns a string."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)
        result = visualizer.visualize()
        assert isinstance(result, str)
        assert "graph" in result

    def test_visualize_dot_format(self):
        """Test visualize with DOT format."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)
        result = visualizer.visualize(format="dot")
        assert "digraph" in result

    def test_save_writes_file(self):
        """Test save writes visualization to file."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        visualizer = WorkflowVisualizer(workflow)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "workflow.md")
            visualizer.save(output_path, format="mermaid")
            assert Path(output_path).exists()

    def test_sanitize_id(self):
        """Test node ID sanitization."""
        visualizer = WorkflowVisualizer()
        assert visualizer._sanitize_id("my-node") == "my_node"
        assert visualizer._sanitize_id("my.node") == "my_node"
        assert visualizer._sanitize_id("my node") == "my_node"

    def test_get_node_shape_reader(self):
        """Test node shape for reader nodes."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("CSVReaderNode")
        assert open_d == "[("
        assert close_d == ")]"

    def test_get_node_shape_switch(self):
        """Test node shape for switch nodes."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("SwitchNode")
        assert open_d == "{"
        assert close_d == "}"

    def test_get_node_shape_ai(self):
        """Test node shape for AI nodes."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("LLMAgentNode")
        assert open_d == "[["
        assert close_d == "]]"

    def test_get_node_shape_code(self):
        """Test node shape for code nodes."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("PythonCodeNode")
        assert open_d == "[/"
        assert close_d == "/]"

    def test_get_node_shape_default(self):
        """Test node shape default."""
        visualizer = WorkflowVisualizer()
        open_d, close_d = visualizer._get_node_shape("UnknownNode")
        assert open_d == "["
        assert close_d == "]"

    def test_direction_parameter(self):
        """Test custom direction parameter."""
        visualizer = WorkflowVisualizer(direction="LR")
        assert visualizer.direction == "LR"
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer.workflow = workflow
        result = visualizer.to_mermaid()
        assert "graph LR" in result

    def test_visualize_saves_to_output_path(self):
        """Test visualize saves when output_path provided."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "out.md")
            result = visualizer.visualize(output_path=output_path)
            assert Path(output_path).exists()
            assert isinstance(result, str)
