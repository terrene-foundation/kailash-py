"""Tests for workflow visualization module."""

import pytest
from unittest.mock import Mock, patch, call
import tempfile
from pathlib import Path

from kailash.workflow.visualization import WorkflowVisualizer
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import Node


class MockNode(Node):
    """Mock node for testing."""
    
    def process(self, data):
        """Process data."""
        return data


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
            workflow,
            node_colors=node_colors,
            edge_colors=edge_colors
        )
        
        assert visualizer.node_colors["data"] == "blue"
        assert visualizer.edge_colors["error"] == "red"
    
    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.figure')
    def test_visualize(self, mock_figure, mock_show, mock_savefig):
        """Test workflow visualization."""
        # Create a workflow with nodes
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "output", node2_id, "input")
        
        workflow = builder.build("test", name="Test Workflow")
        
        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")
        
        visualizer = WorkflowVisualizer(workflow)
        
        # Call visualize
        visualizer.visualize()
        
        # Check that matplotlib methods were called
        mock_figure.assert_called_once()
        mock_show.assert_called_once()
    
    @patch('matplotlib.pyplot.savefig')
    def test_save_visualization(self, mock_savefig):
        """Test saving visualization to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)
        
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            visualizer.save(tmp.name)
            mock_savefig.assert_called_once_with(tmp.name, dpi=300, bbox_inches='tight')
    
    def test_get_node_color(self):
        """Test getting node color based on type."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)
        
        # Test default colors
        assert visualizer._get_node_color("DataReader") == visualizer.node_colors["data"]
        assert visualizer._get_node_color("Transformer") == visualizer.node_colors["transform"]
        assert visualizer._get_node_color("AINode") == visualizer.node_colors["ai"]
        assert visualizer._get_node_color("Unknown") == visualizer.node_colors["default"]
    
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
    
    @patch('matplotlib.pyplot.figure')
    def test_complex_workflow_visualization(self, mock_figure):
        """Test visualizing complex workflow."""
        # Create a complex workflow
        builder = WorkflowBuilder()
        
        # Add nodes of different types
        reader_id = builder.add_node("DataReader", "reader")
        filter_id = builder.add_node("DataFilter", "filter")
        ai_id = builder.add_node("AIProcessor", "ai")
        writer_id = builder.add_node("DataWriter", "writer")
        
        # Add connections
        builder.add_connection(reader_id, "data", filter_id, "input")
        builder.add_connection(filter_id, "output", ai_id, "input")
        builder.add_connection(ai_id, "result", writer_id, "data")
        
        workflow = builder.build("complex", name="Complex Workflow")
        
        # Mock the nodes
        workflow.graph.nodes["reader"]["node"] = MockNode(node_id="reader", name="Reader")
        workflow.graph.nodes["filter"]["node"] = MockNode(node_id="filter", name="Filter")
        workflow.graph.nodes["ai"]["node"] = MockNode(node_id="ai", name="AI")
        workflow.graph.nodes["writer"]["node"] = MockNode(node_id="writer", name="Writer")
        
        visualizer = WorkflowVisualizer(workflow)
        
        # Mock the actual drawing to avoid matplotlib backend issues
        with patch.object(visualizer, '_draw_graph'):
            visualizer.visualize()
        
        mock_figure.assert_called_once()
    
    def test_visualizer_with_empty_workflow(self):
        """Test visualizing empty workflow."""
        workflow = Workflow(workflow_id="empty", name="Empty Workflow")
        visualizer = WorkflowVisualizer(workflow)
        
        # Should not raise exception
        with patch('matplotlib.pyplot.figure'):
            with patch('matplotlib.pyplot.show'):
                visualizer.visualize()
    
    @patch('matplotlib.pyplot.figure')
    def test_visualize_with_labels(self, mock_figure):
        """Test visualization with custom labels."""
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "test_node")
        workflow = builder.build("test")
        
        # Mock the node
        workflow.graph.nodes["test_node"]["node"] = MockNode(
            node_id="test_node", 
            name="Test Node"
        )
        
        visualizer = WorkflowVisualizer(workflow)
        
        # Test that the node labels are properly extracted
        with patch.object(visualizer, '_draw_graph') as mock_draw:
            visualizer.visualize()
            
            # Check that labels were created
            assert visualizer._get_node_labels() == {"test_node": "Test Node"}
    
    def test_get_node_labels(self):
        """Test getting node labels from workflow."""
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2") 
        workflow = builder.build("test")
        
        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="First Node")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Second Node")
        
        visualizer = WorkflowVisualizer(workflow)
        labels = visualizer._get_node_labels()
        
        assert labels == {
            "node1": "First Node",
            "node2": "Second Node"
        }
    
    def test_visualizer_with_custom_layout(self):
        """Test visualizer with custom layout algorithm."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow, layout="circular")
        
        assert visualizer.layout == "circular"
    
    @patch('matplotlib.pyplot.figure')
    def test_save_high_dpi(self, mock_figure):
        """Test saving visualization with high DPI."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)
        
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            with patch('matplotlib.pyplot.savefig') as mock_savefig:
                visualizer.save(tmp.name, dpi=600)
                mock_savefig.assert_called_once_with(
                    tmp.name, 
                    dpi=600, 
                    bbox_inches='tight'
                )
    
    def test_visualizer_error_handling(self):
        """Test error handling in visualizer."""
        workflow = Workflow(workflow_id="test", name="Test")
        visualizer = WorkflowVisualizer(workflow)
        
        # Test with invalid layout
        with patch('networkx.spring_layout', side_effect=ValueError):
            with pytest.raises(ValueError):
                with patch('matplotlib.pyplot.figure'):
                    visualizer.visualize()