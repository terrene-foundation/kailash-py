"""Test export functionality with real workflows."""

import json
import yaml
from pathlib import Path
from typing import Dict, Any

import pytest
import pandas as pd

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import Node
from kailash.manifest import KailashManifest
from kailash.utils.export import (
    export_to_kailash_format,
    export_workflow_as_code,
    export_workflow_as_config,
    validate_export_format
)


class TestExportIntegration:
    """Test export functionality with real workflows."""
    
    def test_export_simple_workflow(self, simple_workflow: Workflow, temp_data_dir: Path):
        """Test exporting a simple workflow to Kailash format."""
        # Create manifest
        manifest = KailashManifest(
            metadata={
                "id": "simple-workflow-export",
                "name": "Simple Workflow Export Test",
                "version": "1.0.0",
                "author": "Test Author",
                "description": "Test exporting simple workflow"
            },
            workflow=simple_workflow
        )
        
        # Export to file
        export_path = temp_data_dir / "exported_workflow.json"
        exported_data = export_to_kailash_format(manifest, export_path)
        
        # Verify export file exists
        assert export_path.exists()
        
        # Load and verify exported data
        with open(export_path, 'r') as f:
            loaded_data = json.load(f)
        
        assert loaded_data["metadata"]["id"] == "simple-workflow-export"
        assert "nodes" in loaded_data["workflow"]
        assert "connections" in loaded_data["workflow"]
        assert len(loaded_data["workflow"]["nodes"]) == len(simple_workflow.graph.nodes())
    
    def test_export_complex_workflow(self, complex_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test exporting a complex workflow with multiple branches."""
        manifest = KailashManifest(
            metadata={
                "id": "complex-workflow-export",
                "name": "Complex Workflow Export",
                "version": "2.0.0",
                "author": "Test Author",
                "description": "Complex workflow with multiple branches",
                "tags": ["complex", "multi-branch", "test"]
            },
            workflow=complex_workflow
        )
        
        # Export to different formats
        json_path = temp_data_dir / "complex_workflow.json"
        yaml_path = temp_data_dir / "complex_workflow.yaml"
        
        # Export as JSON
        json_export = export_to_kailash_format(manifest, json_path)
        
        # Export as YAML
        yaml_export = export_workflow_as_config(manifest, yaml_path, format="yaml")
        
        # Verify both exports
        assert json_path.exists()
        assert yaml_path.exists()
        
        # Verify JSON export
        with open(json_path, 'r') as f:
            json_data = json.load(f)
        
        assert json_data["metadata"]["id"] == "complex-workflow-export"
        assert len(json_data["workflow"]["nodes"]) == len(complex_workflow.graph.nodes())
        
        # Verify YAML export
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        assert yaml_data["metadata"]["id"] == "complex-workflow-export"
        assert len(yaml_data["workflow"]["nodes"]) == len(complex_workflow.graph.nodes())
    
    def test_export_workflow_as_python_code(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test exporting workflow as executable Python code."""
        manifest = KailashManifest(
            metadata={
                "id": "python-export-test",
                "name": "Python Code Export",
                "version": "1.0.0"
            },
            workflow=simple_workflow
        )
        
        # Export as Python code
        python_file = temp_data_dir / "workflow_code.py"
        code_export = export_workflow_as_code(manifest, python_file)
        
        # Verify file exists
        assert python_file.exists()
        
        # Verify code structure
        code_content = python_file.read_text()
        assert "from kailash.workflow.graph import WorkflowBuilder" in code_content
        assert "builder = WorkflowBuilder()" in code_content
        assert "builder.add_node" in code_content
        assert "builder.add_connection" in code_content
        assert "builder.build" in code_content
        
        # Test that the code is valid Python
        compile(code_content, str(python_file), 'exec')
    
    def test_export_with_node_templates(self, temp_data_dir: Path):
        """Test exporting workflow with custom node templates."""
        builder = WorkflowBuilder()
        
        # Create workflow with templated nodes
        template_reader_id = builder.add_node(
            "TemplatedReader",
            "template_reader",
            inputs={"path": InputType(value="${INPUT_PATH}")},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)},
            metadata={"template": True, "template_vars": ["INPUT_PATH"]}
        )
        
        template_processor_id = builder.add_node(
            "TemplatedProcessor",
            "template_processor",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "threshold": InputType(value="${THRESHOLD_VALUE}")
            },
            outputs={"processed": OutputType(format=DataFormat.DATAFRAME)},
            metadata={"template": True, "template_vars": ["THRESHOLD_VALUE"]}
        )
        
        builder.add_connection(template_reader_id, "data", template_processor_id, "data")
        workflow = builder.build("templated_workflow")
        
        manifest = KailashManifest(
            metadata={
                "id": "template-export",
                "name": "Template Export Test",
                "template_variables": {
                    "INPUT_PATH": "path/to/input.csv",
                    "THRESHOLD_VALUE": "100"
                }
            },
            workflow=workflow
        )
        
        # Export with templates
        export_path = temp_data_dir / "templated_workflow.json"
        exported = export_to_kailash_format(manifest, export_path)
        
        # Verify templates in export
        with open(export_path, 'r') as f:
            data = json.load(f)
        
        assert "template_variables" in data["metadata"]
        assert data["metadata"]["template_variables"]["INPUT_PATH"] == "path/to/input.csv"
        
        # Check that template vars are preserved in nodes
        nodes = data["workflow"]["nodes"]
        template_reader = next(n for n in nodes if n["id"] == "template_reader")
        assert template_reader["metadata"]["template"] is True
        assert "template_vars" in template_reader["metadata"]
    
    def test_export_validation(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test export format validation."""
        manifest = KailashManifest(
            metadata={
                "id": "validation-test",
                "name": "Export Validation Test",
                "version": "1.0.0"
            },
            workflow=simple_workflow
        )
        
        # Export workflow
        export_path = temp_data_dir / "validation_test.json"
        exported = export_to_kailash_format(manifest, export_path)
        
        # Validate export format
        is_valid, errors = validate_export_format(export_path)
        
        assert is_valid is True
        assert len(errors) == 0
        
        # Corrupt the export and test validation
        with open(export_path, 'r') as f:
            data = json.load(f)
        
        # Remove required field
        del data["metadata"]["id"]
        
        corrupted_path = temp_data_dir / "corrupted.json"
        with open(corrupted_path, 'w') as f:
            json.dump(data, f)
        
        # Validate corrupted export
        is_valid, errors = validate_export_format(corrupted_path)
        
        assert is_valid is False
        assert len(errors) > 0
        assert any("id" in error for error in errors)
    
    def test_export_with_execution_results(
        self, simple_workflow: WorkflowGraph, temp_data_dir: Path
    ):
        """Test exporting workflow with execution results included."""
        # Execute workflow first
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(simple_workflow)
        
        # Create manifest with execution results
        manifest = KailashManifest(
            metadata={
                "id": "results-export",
                "name": "Export with Results",
                "version": "1.0.0",
                "execution_result": {
                    "status": result.status.value,
                    "outputs": result.outputs,
                    "execution_time": result.execution_time
                }
            },
            workflow=simple_workflow
        )
        
        # Export with results
        export_path = temp_data_dir / "workflow_with_results.json"
        exported = export_to_kailash_format(manifest, export_path)
        
        # Verify results are included
        with open(export_path, 'r') as f:
            data = json.load(f)
        
        assert "execution_result" in data["metadata"]
        assert data["metadata"]["execution_result"]["status"] == "completed"
        assert "outputs" in data["metadata"]["execution_result"]
    
    def test_export_workflow_bundle(self, complex_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test exporting workflow as a complete bundle with dependencies."""
        manifest = KailashManifest(
            metadata={
                "id": "bundle-export",
                "name": "Workflow Bundle Export",
                "version": "1.0.0",
                "dependencies": {
                    "python": "3.8+",
                    "packages": ["pandas>=1.0", "numpy", "scikit-learn"]
                }
            },
            workflow=complex_workflow
        )
        
        # Create bundle directory
        bundle_dir = temp_data_dir / "workflow_bundle"
        bundle_dir.mkdir(exist_ok=True)
        
        # Export workflow
        workflow_file = bundle_dir / "workflow.json"
        export_to_kailash_format(manifest, workflow_file)
        
        # Create requirements file
        requirements_file = bundle_dir / "requirements.txt"
        requirements = manifest.metadata["dependencies"]["packages"]
        requirements_file.write_text("\n".join(requirements))
        
        # Create README
        readme_file = bundle_dir / "README.md"
        readme_content = f"""# {manifest.metadata['name']}

## Description
{manifest.metadata.get('description', 'Workflow bundle')}

## Requirements
- Python {manifest.metadata['dependencies']['python']}
- See requirements.txt for package dependencies

## Usage
```python
from kailash.manifest import KailashManifest

manifest = KailashManifest.load('workflow.json')
# Execute workflow...
```
"""
        readme_file.write_text(readme_content)
        
        # Create metadata file
        metadata_file = bundle_dir / "metadata.json"
        metadata = {
            "bundle_version": "1.0",
            "created_at": "2023-01-01T00:00:00",
            "files": ["workflow.json", "requirements.txt", "README.md"],
            "workflow_id": manifest.metadata["id"]
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Verify bundle structure
        assert workflow_file.exists()
        assert requirements_file.exists()
        assert readme_file.exists()
        assert metadata_file.exists()
        
        # Verify bundle can be loaded
        bundle_manifest = KailashManifest.load(workflow_file)
        assert bundle_manifest.metadata["id"] == "bundle-export"
    
    def test_incremental_export(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test incremental/versioned exports."""
        # Create base export
        base_manifest = KailashManifest(
            metadata={
                "id": "incremental-export",
                "name": "Incremental Export Test",
                "version": "1.0.0"
            },
            workflow=simple_workflow
        )
        
        base_path = temp_data_dir / "v1.0.0" / "workflow.json"
        base_path.parent.mkdir(exist_ok=True)
        export_to_kailash_format(base_manifest, base_path)
        
        # Create modified workflow
        builder = WorkflowBuilder.from_workflow(simple_workflow)
        
        # Add new node
        new_node_id = builder.add_node(
            "DataValidator",
            "validator",
            inputs={"data": InputType(format=DataFormat.DATAFRAME)},
            outputs={"validated": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        modified_workflow = builder.build("modified_workflow")
        
        # Create incremental export
        incremental_manifest = KailashManifest(
            metadata={
                "id": "incremental-export",
                "name": "Incremental Export Test",
                "version": "1.1.0",
                "previous_version": "1.0.0",
                "changes": [
                    "Added DataValidator node",
                    "Updated workflow structure"
                ]
            },
            workflow=modified_workflow
        )
        
        incremental_path = temp_data_dir / "v1.1.0" / "workflow.json"
        incremental_path.parent.mkdir(exist_ok=True)
        export_to_kailash_format(incremental_manifest, incremental_path)
        
        # Create version manifest
        version_manifest = {
            "versions": [
                {"version": "1.0.0", "path": "v1.0.0/workflow.json"},
                {"version": "1.1.0", "path": "v1.1.0/workflow.json", "base": "1.0.0"}
            ],
            "current": "1.1.0"
        }
        
        version_file = temp_data_dir / "versions.json"
        with open(version_file, 'w') as f:
            json.dump(version_manifest, f, indent=2)
        
        # Verify version structure
        assert base_path.exists()
        assert incremental_path.exists()
        assert version_file.exists()
        
        # Verify incremental changes
        with open(incremental_path, 'r') as f:
            incremental_data = json.load(f)
        
        assert incremental_data["metadata"]["version"] == "1.1.0"
        assert "changes" in incremental_data["metadata"]
        assert len(incremental_data["workflow"]["nodes"]) > len(simple_workflow.graph.nodes())
    
    def test_export_with_custom_serializers(self, temp_data_dir: Path):
        """Test export with custom node serializers."""
        class CustomNode(Node):
            """Custom node with special serialization needs."""
            
            def __init__(self, custom_data):
                super().__init__()
                self.custom_data = custom_data
            
            def to_dict(self):
                """Custom serialization method."""
                base_dict = super().to_dict()
                base_dict["custom_data"] = {
                    "type": type(self.custom_data).__name__,
                    "value": str(self.custom_data)
                }
                return base_dict
        
        # Create workflow with custom node
        builder = WorkflowBuilder()
        
        # Register custom node type
        builder.register_node_type("CustomNode", CustomNode)
        
        custom_node_id = builder.add_node(
            "CustomNode",
            "custom_processor",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"result": OutputType(format=DataFormat.JSON)},
            custom_data={"complex": "object", "nested": [1, 2, 3]}
        )
        
        workflow = builder.build("custom_node_workflow")
        
        manifest = KailashManifest(
            metadata={
                "id": "custom-serializer-test",
                "name": "Custom Serializer Test"
            },
            workflow=workflow
        )
        
        # Export with custom serializers
        export_path = temp_data_dir / "custom_export.json"
        exported = export_to_kailash_format(
            manifest, 
            export_path,
            custom_serializers={"CustomNode": lambda n: n.to_dict()}
        )
        
        # Verify custom serialization
        with open(export_path, 'r') as f:
            data = json.load(f)
        
        custom_node = next(
            n for n in data["workflow"]["nodes"] 
            if n["id"] == "custom_processor"
        )
        assert "custom_data" in custom_node
        assert custom_node["custom_data"]["type"] == "dict"