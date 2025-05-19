"""Tests for template utilities module."""

import pytest
from typing import Dict, Any

from kailash.utils.templates import (
    NodeTemplate,
    WorkflowTemplate,
    TemplateLibrary,
    get_template_by_name,
    create_node_from_template,
    create_workflow_from_template
)
from kailash.nodes.base import Node
from kailash.workflow import Workflow
from kailash.sdk_exceptions import KailashTemplateError


class MockNode(Node):
    """Mock node for testing."""
    
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        return {"value": data.get("value", 0) * 2}


class TestNodeTemplate:
    """Test NodeTemplate class."""
    
    def test_node_template_creation(self):
        """Test creating node template."""
        template = NodeTemplate(
            name="data_reader",
            node_type="CSVReaderNode",
            description="Template for CSV reader node",
            default_config={
                "delimiter": ",",
                "has_header": True
            },
            required_fields=["file_path"],
            optional_fields=["encoding", "skip_lines"]
        )
        
        assert template.name == "data_reader"
        assert template.node_type == "CSVReaderNode"
        assert template.description == "Template for CSV reader node"
        assert template.default_config["delimiter"] == ","
        assert "file_path" in template.required_fields
        assert "encoding" in template.optional_fields
    
    def test_node_template_instantiate(self):
        """Test instantiating node from template."""
        template = NodeTemplate(
            name="processor",
            node_type="MockNode",
            default_config={
                "name": "Processor",
                "version": "1.0.0"
            }
        )
        
        # Instantiate with additional config
        node_config = {
            "node_id": "proc1",
            "description": "First processor"
        }
        
        node = template.instantiate(node_config)
        
        assert node.node_id == "proc1"
        assert node.name == "Processor"  # From template
        assert node.version == "1.0.0"   # From template
        assert node.description == "First processor"  # From config
    
    def test_node_template_validation(self):
        """Test node template validation."""
        template = NodeTemplate(
            name="validator",
            node_type="ValidationNode",
            required_fields=["rules", "error_messages"]
        )
        
        # Missing required field
        with pytest.raises(KailashTemplateError):
            template.instantiate({"node_id": "val1"})
        
        # With all required fields
        node = template.instantiate({
            "node_id": "val1",
            "rules": ["lambda x: x > 0"],
            "error_messages": ["Value must be positive"]
        })
        
        assert node is not None
    
    def test_node_template_to_dict(self):
        """Test converting node template to dict."""
        template = NodeTemplate(
            name="test_template",
            node_type="TestNode",
            description="A test template",
            default_config={"key": "value"},
            tags=["test", "example"]
        )
        
        template_dict = template.to_dict()
        
        assert template_dict["name"] == "test_template"
        assert template_dict["node_type"] == "TestNode"
        assert template_dict["description"] == "A test template"
        assert template_dict["default_config"]["key"] == "value"
        assert template_dict["tags"] == ["test", "example"]
    
    def test_node_template_from_dict(self):
        """Test creating node template from dict."""
        template_dict = {
            "name": "from_dict",
            "node_type": "DictNode",
            "description": "Created from dict",
            "default_config": {"setting": 42},
            "required_fields": ["input_data"]
        }
        
        template = NodeTemplate.from_dict(template_dict)
        
        assert template.name == "from_dict"
        assert template.node_type == "DictNode"
        assert template.default_config["setting"] == 42
        assert "input_data" in template.required_fields


class TestWorkflowTemplate:
    """Test WorkflowTemplate class."""
    
    def test_workflow_template_creation(self):
        """Test creating workflow template."""
        template = WorkflowTemplate(
            name="etl_pipeline",
            description="ETL pipeline template",
            nodes=[
                {
                    "node_id": "reader",
                    "template": "csv_reader",
                    "config": {"delimiter": ","}
                },
                {
                    "node_id": "transformer",
                    "template": "data_transformer",
                    "config": {"operation": "normalize"}
                },
                {
                    "node_id": "writer",
                    "template": "json_writer",
                    "config": {"pretty": True}
                }
            ],
            edges=[
                {"source": "reader", "target": "transformer"},
                {"source": "transformer", "target": "writer"}
            ],
            metadata={"author": "test", "version": "1.0.0"}
        )
        
        assert template.name == "etl_pipeline"
        assert len(template.nodes) == 3
        assert len(template.edges) == 2
        assert template.metadata["author"] == "test"
    
    def test_workflow_template_instantiate(self):
        """Test instantiating workflow from template."""
        template = WorkflowTemplate(
            name="simple_flow",
            description="Simple workflow",
            nodes=[
                {
                    "node_id": "input",
                    "node_type": "MockNode",
                    "config": {"name": "Input Node"}
                },
                {
                    "node_id": "output",
                    "node_type": "MockNode", 
                    "config": {"name": "Output Node"}
                }
            ],
            edges=[
                {"source": "input", "target": "output"}
            ]
        )
        
        workflow = template.instantiate(
            workflow_id="flow1",
            name="My Flow"
        )
        
        assert workflow.workflow_id == "flow1"
        assert workflow.name == "My Flow"
        assert len(workflow.nodes) == 2
        assert workflow.graph.has_edge("input", "output")
    
    def test_workflow_template_with_field_mapping(self):
        """Test workflow template with field mapping."""
        template = WorkflowTemplate(
            name="mapped_flow",
            nodes=[
                {"node_id": "n1", "node_type": "MockNode"},
                {"node_id": "n2", "node_type": "MockNode"}
            ],
            edges=[
                {
                    "source": "n1",
                    "target": "n2",
                    "field_mapping": {"output": "input"}
                }
            ]
        )
        
        workflow = template.instantiate("test", "Test")
        
        edge_data = workflow.graph.edges["n1", "n2"]
        assert edge_data["field_mapping"]["output"] == "input"
    
    def test_workflow_template_validation(self):
        """Test workflow template validation."""
        # Template with invalid edge (missing node)
        template = WorkflowTemplate(
            name="invalid",
            nodes=[
                {"node_id": "n1", "node_type": "MockNode"}
            ],
            edges=[
                {"source": "n1", "target": "nonexistent"}
            ]
        )
        
        with pytest.raises(KailashTemplateError):
            template.instantiate("test", "Test")
    
    def test_workflow_template_to_from_dict(self):
        """Test converting workflow template to/from dict."""
        template = WorkflowTemplate(
            name="serializable",
            description="Can be serialized",
            nodes=[
                {"node_id": "n1", "node_type": "TypeA"},
                {"node_id": "n2", "node_type": "TypeB"}
            ],
            edges=[
                {"source": "n1", "target": "n2"}
            ],
            tags=["example", "test"]
        )
        
        # To dict
        template_dict = template.to_dict()
        assert template_dict["name"] == "serializable"
        assert len(template_dict["nodes"]) == 2
        assert template_dict["tags"] == ["example", "test"]
        
        # From dict
        restored = WorkflowTemplate.from_dict(template_dict)
        assert restored.name == template.name
        assert len(restored.nodes) == len(template.nodes)
        assert restored.tags == template.tags


class TestTemplateLibrary:
    """Test TemplateLibrary class."""
    
    def test_library_creation(self):
        """Test creating template library."""
        library = TemplateLibrary()
        
        assert library.node_templates == {}
        assert library.workflow_templates == {}
    
    def test_add_node_template(self):
        """Test adding node template to library."""
        library = TemplateLibrary()
        
        template = NodeTemplate(
            name="reader",
            node_type="ReaderNode",
            description="A reader node"
        )
        
        library.add_node_template(template)
        
        assert "reader" in library.node_templates
        assert library.node_templates["reader"] == template
    
    def test_add_workflow_template(self):
        """Test adding workflow template to library."""
        library = TemplateLibrary()
        
        template = WorkflowTemplate(
            name="pipeline",
            description="A pipeline",
            nodes=[],
            edges=[]
        )
        
        library.add_workflow_template(template)
        
        assert "pipeline" in library.workflow_templates
        assert library.workflow_templates["pipeline"] == template
    
    def test_get_templates(self):
        """Test getting templates from library."""
        library = TemplateLibrary()
        
        # Add templates
        node_template = NodeTemplate("node1", "Type1")
        workflow_template = WorkflowTemplate("flow1", nodes=[], edges=[])
        
        library.add_node_template(node_template)
        library.add_workflow_template(workflow_template)
        
        # Get templates
        assert library.get_node_template("node1") == node_template
        assert library.get_workflow_template("flow1") == workflow_template
        
        # Get non-existent
        assert library.get_node_template("nonexistent") is None
        assert library.get_workflow_template("nonexistent") is None
    
    def test_list_templates(self):
        """Test listing templates in library."""
        library = TemplateLibrary()
        
        # Add multiple templates
        for i in range(3):
            library.add_node_template(
                NodeTemplate(f"node{i}", f"Type{i}")
            )
            library.add_workflow_template(
                WorkflowTemplate(f"flow{i}", nodes=[], edges=[])
            )
        
        node_list = library.list_node_templates()
        workflow_list = library.list_workflow_templates()
        
        assert len(node_list) == 3
        assert len(workflow_list) == 3
        assert all(name.startswith("node") for name in node_list)
        assert all(name.startswith("flow") for name in workflow_list)
    
    def test_remove_templates(self):
        """Test removing templates from library."""
        library = TemplateLibrary()
        
        # Add templates
        template = NodeTemplate("removable", "Type")
        library.add_node_template(template)
        
        # Remove template
        library.remove_node_template("removable")
        
        assert "removable" not in library.node_templates
        assert library.get_node_template("removable") is None
    
    def test_library_search(self):
        """Test searching templates in library."""
        library = TemplateLibrary()
        
        # Add templates with tags
        library.add_node_template(
            NodeTemplate("csv_reader", "CSVReader", tags=["io", "csv"])
        )
        library.add_node_template(
            NodeTemplate("json_reader", "JSONReader", tags=["io", "json"])
        )
        library.add_node_template(
            NodeTemplate("processor", "Processor", tags=["transform"])
        )
        
        # Search by tag
        io_templates = library.search_node_templates(tags=["io"])
        assert len(io_templates) == 2
        assert all(t.name.endswith("reader") for t in io_templates)
        
        # Search by type
        csv_templates = library.search_node_templates(node_type="CSVReader")
        assert len(csv_templates) == 1
        assert csv_templates[0].name == "csv_reader"
    
    def test_library_import_export(self, temp_dir):
        """Test importing/exporting library."""
        library = TemplateLibrary()
        
        # Add templates
        library.add_node_template(
            NodeTemplate("template1", "Type1", description="First")
        )
        library.add_workflow_template(
            WorkflowTemplate("workflow1", nodes=[], edges=[])
        )
        
        # Export to file
        export_file = temp_dir / "templates.json"
        library.export_to_file(str(export_file))
        
        assert export_file.exists()
        
        # Import to new library
        new_library = TemplateLibrary()
        new_library.import_from_file(str(export_file))
        
        assert len(new_library.node_templates) == 1
        assert len(new_library.workflow_templates) == 1
        assert new_library.get_node_template("template1").description == "First"


def test_template_functions():
    """Test module-level template functions."""
    # Create and register templates
    library = TemplateLibrary()
    
    node_template = NodeTemplate(
        name="test_node",
        node_type="MockNode",
        default_config={"name": "Test"}
    )
    
    workflow_template = WorkflowTemplate(
        name="test_workflow",
        nodes=[
            {"node_id": "n1", "node_type": "MockNode"}
        ],
        edges=[]
    )
    
    library.add_node_template(node_template)
    library.add_workflow_template(workflow_template)
    
    # Test get_template_by_name
    retrieved_node = get_template_by_name("test_node", "node", library)
    assert retrieved_node == node_template
    
    retrieved_workflow = get_template_by_name("test_workflow", "workflow", library)
    assert retrieved_workflow == workflow_template
    
    # Test create_node_from_template
    node = create_node_from_template(
        "test_node",
        {"node_id": "created_node"},
        library
    )
    assert node.node_id == "created_node"
    assert node.name == "Test"  # From template
    
    # Test create_workflow_from_template
    workflow = create_workflow_from_template(
        "test_workflow",
        "created_workflow",
        "Created Workflow",
        library
    )
    assert workflow.workflow_id == "created_workflow"
    assert len(workflow.nodes) == 1