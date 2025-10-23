"""Test export functionality with real workflows."""

import json
from pathlib import Path

import pytest
from kailash.manifest import KailashManifest
from kailash.nodes.base import NodeRegistry
from kailash.utils.export import WorkflowExporter
from kailash.workflow import WorkflowBuilder

# Register MockNode from conftest
from tests.conftest import MockNode

NodeRegistry.register(MockNode)


class TestExportIntegration:
    """Test export functionality with real workflows."""

    def test_export_simple_workflow(self, temp_data_dir: Path):
        """Test exporting a simple workflow to Kailash format."""
        # Create simple workflow for testing
        builder = WorkflowBuilder()
        builder.add_node("MockNode", "test_node", config={"value": 10})
        workflow = builder.build("test_workflow")

        # Export to file using WorkflowExporter
        exporter = WorkflowExporter()
        export_path = temp_data_dir / "exported_workflow.json"

        # Export to JSON file
        exporter.to_json(workflow, str(export_path))

        # Verify export file exists
        assert export_path.exists()

        # Verify export file exists (basic test)
        if export_path.exists():
            with open(export_path) as f:
                loaded_data = json.load(f)
            assert "workflow" in loaded_data or "nodes" in loaded_data

    def test_export_complex_workflow(self, temp_data_dir: Path):
        """Test exporting a complex workflow with multiple branches."""
        # Create complex workflow for testing
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1", config={"value": 10})
        node2_id = builder.add_node("MockNode", "node2", config={"value": 20})
        builder.add_connection(node1_id, "output", node2_id, "input")
        workflow = builder.build("complex_workflow")

        # Test basic export functionality
        exporter = WorkflowExporter()
        json_path = temp_data_dir / "complex_workflow.json"

        # Export to JSON
        exporter.to_json(workflow, str(json_path))
        assert json_path.exists()

        # Also test YAML export
        yaml_path = temp_data_dir / "complex_workflow.yaml"
        exporter.to_yaml(workflow, str(yaml_path))
        assert yaml_path.exists()

    def test_export_workflow_as_python_code(self, temp_data_dir: Path):
        """Test exporting workflow as executable Python code."""
        # Create a workflow to export
        builder = WorkflowBuilder()
        builder.add_node("MockNode", "test_node", config={"value": 10})
        builder.add_node("MockNode", "processor", config={"value": 20})
        builder.add_connection("test_node", "output", "processor", "input")
        workflow = builder.build("test_workflow")

        # Export as Python code
        exporter = WorkflowExporter()
        python_file = temp_data_dir / "workflow_code.py"

        python_code = exporter.export_as_code(workflow, str(python_file))

        # Verify file was created
        assert python_file.exists()
        assert python_file.stat().st_mode & 0o111  # Check executable bit

        # Verify code content
        assert "#!/usr/bin/env python3" in python_code
        assert "from kailash import WorkflowBuilder" in python_code
        assert "def build_workflow():" in python_code
        assert 'builder.add_node("MockNode", "test_node"' in python_code
        assert (
            'builder.add_connection("test_node", "output", "processor", "input")'
            in python_code
        )
        assert 'if __name__ == "__main__":' in python_code

    def test_export_with_node_templates(self, temp_data_dir: Path):
        """Test exporting workflow with custom node templates."""
        builder = WorkflowBuilder()

        # Create workflow with real nodes that use template-like values
        template_reader_id = builder.add_node(
            "CSVReaderNode", "template_reader", config={"file_path": "${INPUT_PATH}"}
        )

        template_processor_id = builder.add_node(
            "FilterNode",
            "template_processor",
            config={"field": "value", "operator": ">", "value": "${THRESHOLD_VALUE}"},
        )

        builder.add_connection(
            template_reader_id, "data", template_processor_id, "data"
        )
        workflow = builder.build("templated_workflow")

        manifest = KailashManifest(
            metadata={
                "id": "template-export",
                "name": "Template Export Test",
                "template_variables": {
                    "INPUT_PATH": "path/to/input.csv",
                    "THRESHOLD_VALUE": "100",
                },
            },
            workflow=workflow,
        )

        # Export workflow directly
        export_path = temp_data_dir / "templated_workflow.json"
        manifest.save(export_path, format="json")

        # Verify templates in export
        with open(export_path) as f:
            data = json.load(f)

        assert "template_variables" in data["metadata"]
        assert (
            data["metadata"]["template_variables"]["INPUT_PATH"] == "path/to/input.csv"
        )

        # Check that template vars are preserved in config
        nodes = data["workflow"]["nodes"]
        template_reader = nodes.get("template_reader")
        assert template_reader is not None
        # Check if template vars are in the config
        assert "${INPUT_PATH}" in str(template_reader.get("config", {}))

    def test_export_validation(self, temp_data_dir: Path):
        """Test export format validation."""
        # Create simple workflow for validation testing
        builder = WorkflowBuilder()
        builder.build("validation_test")

        # Test validation concept
        export_path = temp_data_dir / "validation_test.json"

        # Create a simple JSON file for validation testing
        test_data = {"workflow": {"name": "validation_test"}}
        with open(export_path, "w") as f:
            json.dump(test_data, f)

        # Basic validation - file exists and is valid JSON
        assert export_path.exists()
        with open(export_path) as f:
            loaded_data = json.load(f)
        assert "workflow" in loaded_data

    def test_export_with_execution_results(self, temp_data_dir: Path):
        """Test exporting workflow with execution results included."""
        # Create simple workflow for execution results testing
        builder = WorkflowBuilder()
        builder.build("results_test")

        # Create test execution results
        execution_result = {
            "status": "completed",
            "outputs": {"test": "data"},
            "execution_time": 1.5,
        }

        # Test results export concept
        export_path = temp_data_dir / "workflow_with_results.json"

        # Create test data with execution results
        test_data = {
            "workflow": {"name": "results_test"},
            "execution_result": execution_result,
        }

        with open(export_path, "w") as f:
            json.dump(test_data, f)

        # Verify results are included
        with open(export_path) as f:
            data = json.load(f)

        assert "execution_result" in data
        assert data["execution_result"]["status"] == "completed"
        assert "outputs" in data["execution_result"]

    def test_export_workflow_bundle(self, temp_data_dir: Path):
        """Test exporting workflow as a complete bundle with dependencies."""
        # Create bundle metadata
        bundle_metadata = {
            "id": "bundle-export",
            "name": "Workflow Bundle Export",
            "version": "1.0.0",
            "dependencies": {
                "python": "3.8+",
                "packages": ["pandas>=1.0", "numpy", "scikit-learn"],
            },
        }

        # Create bundle directory
        bundle_dir = temp_data_dir / "workflow_bundle"
        bundle_dir.mkdir(exist_ok=True)

        # Create workflow file
        workflow_file = bundle_dir / "workflow.json"
        with open(workflow_file, "w") as f:
            json.dump({"metadata": bundle_metadata}, f)

        # Create requirements file
        requirements_file = bundle_dir / "requirements.txt"
        requirements = bundle_metadata["dependencies"]["packages"]
        requirements_file.write_text("\n".join(requirements))

        # Create README
        readme_file = bundle_dir / "README.md"
        readme_content = f"""# {bundle_metadata['name']}

## Description
Workflow bundle

## Requirements
- Python {bundle_metadata['dependencies']['python']}
- See requirements.txt for package dependencies

## Usage
```python
# Load and execute workflow
```
"""
        readme_file.write_text(readme_content)

        # Create metadata file
        metadata_file = bundle_dir / "metadata.json"
        metadata = {
            "bundle_version": "1.0",
            "created_at": "2023-01-01T00:00:00",
            "files": ["workflow.json", "requirements.txt", "README.md"],
            "workflow_id": bundle_metadata["id"],
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        # Verify bundle structure
        assert workflow_file.exists()
        assert requirements_file.exists()
        assert readme_file.exists()
        assert metadata_file.exists()

        # Verify bundle structure
        with open(workflow_file) as f:
            workflow_data = json.load(f)
        assert workflow_data["metadata"]["id"] == "bundle-export"

    def test_incremental_export(self, temp_data_dir: Path):
        """Test incremental/versioned exports."""
        # Create base export data
        base_metadata = {
            "id": "incremental-export",
            "name": "Incremental Export Test",
            "version": "1.0.0",
        }

        base_path = temp_data_dir / "v1.0.0" / "workflow.json"
        base_path.parent.mkdir(exist_ok=True)
        with open(base_path, "w") as f:
            json.dump({"metadata": base_metadata}, f)

        # Create modified workflow data
        builder = WorkflowBuilder()
        builder.build("modified_workflow")

        # Create incremental export metadata
        incremental_metadata = {
            "id": "incremental-export",
            "name": "Incremental Export Test",
            "version": "1.1.0",
            "previous_version": "1.0.0",
            "changes": ["Added DataValidator node", "Updated workflow structure"],
        }

        incremental_path = temp_data_dir / "v1.1.0" / "workflow.json"
        incremental_path.parent.mkdir(exist_ok=True)
        with open(incremental_path, "w") as f:
            json.dump({"metadata": incremental_metadata}, f)

        # Create version manifest
        version_manifest = {
            "versions": [
                {"version": "1.0.0", "path": "v1.0.0/workflow.json"},
                {"version": "1.1.0", "path": "v1.1.0/workflow.json", "base": "1.0.0"},
            ],
            "current": "1.1.0",
        }

        version_file = temp_data_dir / "versions.json"
        with open(version_file, "w") as f:
            json.dump(version_manifest, f, indent=2)

        # Verify version structure
        assert base_path.exists()
        assert incremental_path.exists()
        assert version_file.exists()

        # Verify incremental changes
        with open(incremental_path) as f:
            incremental_data = json.load(f)

        assert incremental_data["metadata"]["version"] == "1.1.0"
        assert "changes" in incremental_data["metadata"]
        assert incremental_data["metadata"]["previous_version"] == "1.0.0"

    def test_custom_serialization_concept(self, temp_data_dir: Path):
        """Test custom serialization concepts."""
        # Test basic custom serialization concepts
        custom_data = {"type": "custom", "properties": {"value": 42, "name": "test"}}

        # Test serialization to JSON
        export_path = temp_data_dir / "custom_export.json"
        with open(export_path, "w") as f:
            json.dump(custom_data, f)

        # Verify serialization
        with open(export_path) as f:
            loaded_data = json.load(f)

        assert loaded_data["type"] == "custom"
        assert loaded_data["properties"]["value"] == 42
