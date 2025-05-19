"""Tests for export utilities module."""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, Any

from kailash.utils.export import (
    WorkflowExporter,
    KailashExporter,
    YAMLExporter,
    JSONExporter,
    GraphMLExporter
)
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import Node
from kailash.sdk_exceptions import KailashExportError


class MockNode(Node):
    """Mock node for testing."""
    
    INPUT_SCHEMA = {"type": "object", "properties": {"value": {"type": "number"}}}
    OUTPUT_SCHEMA = {"type": "object", "properties": {"result": {"type": "number"}}}
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        return {"result": data["value"] * 2}


class TestWorkflowExporter:
    """Test WorkflowExporter base class."""
    
    def test_base_exporter_creation(self):
        """Test creating base workflow exporter."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        exporter = WorkflowExporter(workflow)
        
        assert exporter.workflow == workflow
    
    def test_base_export_not_implemented(self):
        """Test base export method is not implemented."""
        workflow = Workflow(workflow_id="test", name="Test")
        exporter = WorkflowExporter(workflow)
        
        with pytest.raises(NotImplementedError):
            exporter.export()
    
    def test_base_export_to_file_not_implemented(self):
        """Test base export to file is not implemented."""
        workflow = Workflow(workflow_id="test", name="Test")
        exporter = WorkflowExporter(workflow)
        
        with pytest.raises(NotImplementedError):
            exporter.export_to_file("/tmp/test.tmp")


class TestJSONExporter:
    """Test JSONExporter class."""
    
    def test_json_export(self):
        """Test exporting workflow to JSON."""
        workflow = Workflow(workflow_id="test", name="Test Workflow", version="1.0.0")
        
        # Add nodes using builder
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "result", node2_id, "value")
        workflow = builder.build("test", name="Test Workflow", version="1.0.0")
        
        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")
        
        exporter = JSONExporter(workflow)
        json_data = exporter.export()
        
        # Parse JSON
        data = json.loads(json_data)
        
        assert data["workflow_id"] == "test"
        assert data["name"] == "Test Workflow"
        assert data["version"] == "1.0.0"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
    
    def test_json_export_pretty(self):
        """Test exporting workflow to pretty JSON."""
        workflow = Workflow(workflow_id="test", name="Test")
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1")
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = JSONExporter(workflow, pretty=True)
        json_data = exporter.export()
        
        # Pretty JSON should have newlines and indentation
        assert "\n" in json_data
        assert "  " in json_data
    
    def test_json_export_to_file(self, temp_dir):
        """Test exporting JSON to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1")
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = JSONExporter(workflow)
        file_path = temp_dir / "workflow.json"
        
        exporter.export_to_file(str(file_path))
        
        assert file_path.exists()
        
        # Load and verify content
        with open(file_path, "r") as f:
            data = json.load(f)
            assert data["workflow_id"] == "test"
    
    def test_json_export_custom_encoder(self):
        """Test JSON export with custom encoder."""
        workflow = Workflow(workflow_id="test", name="Test")
        
        # Add node with custom metadata using builder
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1", metadata={"custom_date": "2024-01-01"})
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = JSONExporter(workflow)
        json_data = exporter.export()
        
        data = json.loads(json_data)
        assert data["nodes"][0]["metadata"]["custom_date"] == "2024-01-01"


class TestYAMLExporter:
    """Test YAMLExporter class."""
    
    def test_yaml_export(self):
        """Test exporting workflow to YAML."""
        workflow = Workflow(workflow_id="test", name="Test Workflow", description="A test workflow")
        
        # Add nodes using builder
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "result", node2_id, "value")
        workflow = builder.build("test", name="Test Workflow", description="A test workflow")
        
        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")
        
        exporter = YAMLExporter(workflow)
        yaml_data = exporter.export()
        
        # Parse YAML
        data = yaml.safe_load(yaml_data)
        
        assert data["workflow_id"] == "test"
        assert data["name"] == "Test Workflow"
        assert data["description"] == "A test workflow"
        assert len(data["nodes"]) == 2
        assert data["edges"][0]["from_output"] == "result"
    
    def test_yaml_export_to_file(self, temp_dir):
        """Test exporting YAML to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1")
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = YAMLExporter(workflow)
        file_path = temp_dir / "workflow.yaml"
        
        exporter.export_to_file(str(file_path))
        
        assert file_path.exists()
        
        # Load and verify content
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
            assert data["workflow_id"] == "test"
    
    def test_yaml_export_complex_workflow(self):
        """Test exporting complex workflow to YAML."""
        workflow = Workflow(workflow_id="complex", name="Complex Workflow")
        
        # Create a more complex workflow
        builder = WorkflowBuilder()
        node_ids = []
        for i in range(5):
            node_id = builder.add_node("MockNode", f"node{i}")
            node_ids.append(node_id)
        
        # Add edges creating a diamond shape
        builder.add_connection(node_ids[0], "result", node_ids[1], "value")
        builder.add_connection(node_ids[0], "result", node_ids[2], "value")
        builder.add_connection(node_ids[1], "result", node_ids[3], "value")
        builder.add_connection(node_ids[2], "result", node_ids[3], "value")
        builder.add_connection(node_ids[3], "result", node_ids[4], "value")
        
        workflow = builder.build("complex", name="Complex Workflow")
        
        # Mock the nodes
        for i in range(5):
            workflow.graph.nodes[f"node{i}"]["node"] = MockNode(node_id=f"node{i}", name=f"Node {i}")
        
        exporter = YAMLExporter(workflow)
        yaml_data = exporter.export()
        
        data = yaml.safe_load(yaml_data)
        assert len(data["nodes"]) == 5
        assert len(data["edges"]) == 5


class TestKailashExporter:
    """Test KailashExporter class."""
    
    def test_kailash_export(self):
        """Test exporting to Kailash-compatible format."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        
        # Add nodes using builder
        builder = WorkflowBuilder()
        input_id = builder.add_node("MockNode", "input")
        process_id = builder.add_node("MockNode", "process")
        output_id = builder.add_node("MockNode", "output")
        
        builder.add_connection(input_id, "result", process_id, "value")
        builder.add_connection(process_id, "result", output_id, "value")
        
        workflow = builder.build("test", name="Test Workflow")
        
        # Mock the nodes
        workflow.graph.nodes["input"]["node"] = MockNode(node_id="input", name="Input Node")
        workflow.graph.nodes["process"]["node"] = MockNode(node_id="process", name="Process Node")
        workflow.graph.nodes["output"]["node"] = MockNode(node_id="output", name="Output Node")
        
        exporter = KailashExporter(workflow)
        kailash_data = exporter.export()
        
        data = json.loads(kailash_data)
        
        # Verify Kailash-specific format
        assert data["version"] == "1.0"
        assert data["type"] == "workflow"
        assert "metadata" in data
        assert "containers" in data
        assert len(data["containers"]) == 3
        
        # Check container format
        container = data["containers"][0]
        assert "id" in container
        assert "name" in container
        assert "type" in container
        assert "config" in container
        assert "connections" in container
    
    def test_kailash_export_with_resources(self):
        """Test Kailash export with resource requirements."""
        workflow = Workflow(workflow_id="test", name="Test")
        
        # Add node with resource requirements
        builder = WorkflowBuilder()
        node_id = builder.add_node(
            "MockNode", 
            "compute",
            metadata={
                "resources": {
                    "cpu": "2.0",
                    "memory": "4Gi",
                    "gpu": "1"
                }
            }
        )
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["compute"]["node"] = MockNode(node_id="compute", name="Compute Node")
        
        exporter = KailashExporter(workflow)
        kailash_data = exporter.export()
        
        data = json.loads(kailash_data)
        container = data["containers"][0]
        
        assert "resources" in container
        assert container["resources"]["cpu"] == "2.0"
        assert container["resources"]["memory"] == "4Gi"
        assert container["resources"]["gpu"] == "1"
    
    def test_kailash_export_to_file(self, temp_dir):
        """Test exporting Kailash format to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1")
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = KailashExporter(workflow)
        file_path = temp_dir / "workflow.kailash.json"
        
        exporter.export_to_file(str(file_path))
        
        assert file_path.exists()
        
        # Verify file content
        with open(file_path, "r") as f:
            data = json.load(f)
            assert data["version"] == "1.0"
            assert data["type"] == "workflow"
    
    def test_kailash_export_validation(self):
        """Test Kailash export validation."""
        workflow = Workflow(workflow_id="test", name="Test")
        
        # Create workflow with cycle (invalid for Kailash)
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        
        builder.add_connection(node1_id, "result", node2_id, "value")
        builder.add_connection(node2_id, "result", node1_id, "value")  # Creates cycle
        
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")
        
        exporter = KailashExporter(workflow)
        
        with pytest.raises(KailashExportError):
            exporter.export()


class TestGraphMLExporter:
    """Test GraphMLExporter class."""
    
    def test_graphml_export(self):
        """Test exporting workflow to GraphML."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")
        
        # Add nodes using builder
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "result", node2_id, "value")
        workflow = builder.build("test", name="Test Workflow")
        
        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")
        
        exporter = GraphMLExporter(workflow)
        graphml_data = exporter.export()
        
        # Verify GraphML structure
        assert '<?xml version="1.0"' in graphml_data
        assert '<graphml' in graphml_data
        assert '<graph' in graphml_data
        assert '<node id="node1"' in graphml_data
        assert '<node id="node2"' in graphml_data
        assert '<edge' in graphml_data
        assert 'source="node1"' in graphml_data
        assert 'target="node2"' in graphml_data
    
    def test_graphml_with_attributes(self):
        """Test GraphML export with node attributes."""
        workflow = Workflow(workflow_id="test", name="Test")
        
        builder = WorkflowBuilder()
        node_id = builder.add_node(
            "MockNode", 
            "node1",
            metadata={
                "color": "blue",
                "shape": "circle",
                "size": 10
            }
        )
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = GraphMLExporter(workflow)
        graphml_data = exporter.export()
        
        # Check attributes are included
        assert 'key="color"' in graphml_data
        assert 'key="shape"' in graphml_data
        assert '>blue<' in graphml_data
        assert '>circle<' in graphml_data
    
    def test_graphml_export_to_file(self, temp_dir):
        """Test exporting GraphML to file."""
        workflow = Workflow(workflow_id="test", name="Test")
        builder = WorkflowBuilder()
        node_id = builder.add_node("MockNode", "node1")
        workflow = builder.build("test", name="Test")
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        
        exporter = GraphMLExporter(workflow)
        file_path = temp_dir / "workflow.graphml"
        
        exporter.export_to_file(str(file_path))
        
        assert file_path.exists()
        
        # Verify it's valid XML
        content = file_path.read_text()
        assert content.startswith('<?xml version="1.0"')
        assert '</graphml>' in content
    
    def test_graphml_complex_workflow(self):
        """Test GraphML export with complex workflow."""
        workflow = Workflow(workflow_id="complex", name="Complex Workflow")
        
        # Create multiple nodes with different types
        builder = WorkflowBuilder()
        node_ids = []
        for i in range(10):
            node_id = builder.add_node("MockNode", f"node{i}")
            node_ids.append(node_id)
        
        # Create various edge patterns
        for i in range(9):
            builder.add_connection(node_ids[i], "result", node_ids[i+1], "value")
        
        # Add some cross connections
        builder.add_connection(node_ids[0], "result", node_ids[5], "value")
        builder.add_connection(node_ids[3], "result", node_ids[7], "value")
        
        workflow = builder.build("complex", name="Complex Workflow")
        
        # Mock all nodes
        for i in range(10):
            workflow.graph.nodes[f"node{i}"]["node"] = MockNode(node_id=f"node{i}", name=f"Node {i}")
        
        exporter = GraphMLExporter(workflow)
        graphml_data = exporter.export()
        
        # Count nodes and edges in output
        node_count = graphml_data.count('<node')
        edge_count = graphml_data.count('<edge')
        
        assert node_count == 10
        assert edge_count == 11


def test_exporter_factory():
    """Test exporter factory function."""
    from kailash.utils.export import get_exporter
    
    workflow = Workflow(workflow_id="test", name="Test")
    
    # Test getting different exporters
    json_exporter = get_exporter(workflow, "json")
    assert isinstance(json_exporter, JSONExporter)
    
    yaml_exporter = get_exporter(workflow, "yaml")
    assert isinstance(yaml_exporter, YAMLExporter)
    
    kailash_exporter = get_exporter(workflow, "kailash")
    assert isinstance(kailash_exporter, KailashExporter)
    
    graphml_exporter = get_exporter(workflow, "graphml")
    assert isinstance(graphml_exporter, GraphMLExporter)
    
    # Test invalid format
    with pytest.raises(ValueError):
        get_exporter(workflow, "invalid_format")