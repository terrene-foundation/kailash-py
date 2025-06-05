"""Test CLI commands with real workflows."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kailash.manifest import KailashManifest
from kailash.workflow import Workflow, WorkflowBuilder


@pytest.mark.slow
@pytest.mark.integration
class TestCLIIntegration:
    """Test CLI commands with real workflow execution."""

    def test_cli_run_workflow(self, sample_csv_file: Path, temp_data_dir: Path):
        """Test running a workflow via CLI."""
        # Create workflow Python file
        workflow_file = temp_data_dir / "test_workflow.py"
        workflow_code = f"""
from kailash.workflow import WorkflowBuilder

# Create workflow
builder = WorkflowBuilder()

# Add nodes
reader_id = builder.add_node(
    "CSVReaderNode",
    "reader",
    config={{"file_path": "{sample_csv_file}"}}
)

filter_id = builder.add_node(
    "FilterNode",
    "filter",
    config={{"field": "value", "operator": ">", "value": 100}}
)

writer_id = builder.add_node(
    "CSVWriterNode",
    "writer",
    config={{"file_path": "{temp_data_dir / 'output.csv'}"}}
)

# Connect nodes
builder.add_connection(reader_id, "data", filter_id, "data")
builder.add_connection(filter_id, "filtered_data", writer_id, "data")

# Build workflow
workflow = builder.build("cli_test_workflow")
"""
        workflow_file.write_text(workflow_code)

        # Run workflow via CLI
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "run", str(workflow_file)],
            capture_output=True,
            text=True,
        )

        # Verify execution
        assert result.returncode == 0
        assert (
            "completed successfully" in result.stdout.lower()
            or "workflow completed" in result.stdout.lower()
        )

    def test_cli_validate_workflow(self, sample_csv_file: Path, temp_data_dir: Path):
        """Test validating a workflow via CLI."""
        # Create workflow Python file
        workflow_file = temp_data_dir / "validate_workflow.py"
        workflow_code = f"""
from kailash.workflow import WorkflowBuilder

builder = WorkflowBuilder()
reader_id = builder.add_node("CSVReaderNode", "reader", config={{"file_path": "{sample_csv_file}"}})
filter_id = builder.add_node("FilterNode", "filter", config={{"field": "value", "operator": ">", "value": 100}})
writer_id = builder.add_node("CSVWriterNode", "writer", config={{"file_path": "{temp_data_dir / 'output.csv'}"}})
builder.add_connection(reader_id, "data", filter_id, "data")
builder.add_connection(filter_id, "filtered_data", writer_id, "data")
workflow = builder.build("validation_test")
"""
        workflow_file.write_text(workflow_code)

        # Validate workflow via CLI
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "validate", str(workflow_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Workflow is valid" in result.stdout

    def test_cli_export_workflow(self, sample_csv_file: Path, temp_data_dir: Path):
        """Test exporting a workflow via CLI."""
        # Create workflow Python file
        workflow_file = temp_data_dir / "export_workflow.py"
        workflow_code = f"""
from kailash.workflow import WorkflowBuilder

builder = WorkflowBuilder()
reader_id = builder.add_node("CSVReaderNode", "reader", config={{"file_path": "{sample_csv_file}"}})
filter_id = builder.add_node("FilterNode", "filter", config={{"field": "value", "operator": ">", "value": 100}})
writer_id = builder.add_node("CSVWriterNode", "writer", config={{"file_path": "{temp_data_dir / 'output.csv'}"}})
builder.add_connection(reader_id, "data", filter_id, "data")
builder.add_connection(filter_id, "filtered_data", writer_id, "data")
workflow = builder.build("export_test")
"""
        workflow_file.write_text(workflow_code)

        export_file = temp_data_dir / "exported.json"

        # Export workflow via CLI
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "export",
                str(workflow_file),
                str(export_file),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert export_file.exists()
        assert "Exported workflow to" in result.stdout

    def test_cli_list_nodes(self):
        """Test listing available nodes via CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "nodes", "list"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Available nodes:" in result.stdout
        assert "CSVReaderNode" in result.stdout
        assert "FilterNode" in result.stdout

    def test_cli_describe_node(self):
        """Test describing a specific node via CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "nodes", "info", "CSVReaderNode"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "CSVReaderNode" in result.stdout
        assert "Parameters:" in result.stdout or "Inputs:" in result.stdout
        assert "file_path" in result.stdout

    @pytest.mark.skip(reason="CLI doesn't have a create workflow command")
    def test_cli_create_workflow(self, temp_data_dir: Path):
        """Test creating a new workflow via CLI."""
        workflow_file = temp_data_dir / "new_workflow.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "create",
                "--name",
                "New Workflow",
                "--id",
                "new-workflow",
                "--output",
                str(workflow_file),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert workflow_file.exists()
        assert "Workflow created" in result.stdout

        # Verify created workflow
        with open(workflow_file, "r") as f:
            data = json.load(f)

        assert data["metadata"]["id"] == "new-workflow"
        assert data["metadata"]["name"] == "New Workflow"

    @pytest.mark.skip(reason="CLI doesn't have a visualize command")
    def test_cli_visualize_workflow(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test visualizing a workflow via CLI."""
        # Create manifest file
        manifest = KailashManifest(
            metadata={"id": "viz-test", "name": "Visualization Test"},
            workflow=simple_workflow,
        )

        manifest_file = temp_data_dir / "workflow.json"
        manifest.save(manifest_file)

        output_image = temp_data_dir / "workflow.png"

        # Visualize workflow via CLI
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "visualize",
                str(manifest_file),
                "--output",
                str(output_image),
            ],
            capture_output=True,
            text=True,
        )

        # Visualization might fail if graphviz is not installed
        if result.returncode == 0:
            assert output_image.exists()
            assert "Visualization saved" in result.stdout
        else:
            assert "graphviz" in result.stderr.lower()

    def test_cli_with_params_file(self, sample_csv_file: Path, temp_data_dir: Path):
        """Test CLI with parameters file."""
        # Create params file
        params = {
            "reader": {"file_path": str(sample_csv_file)},
            "filter": {"field": "value", "operator": ">", "value": 50},
        }

        params_file = temp_data_dir / "params.json"
        with open(params_file, "w") as f:
            json.dump(params, f)

        # Create workflow Python file
        workflow_file = temp_data_dir / "params_workflow.py"
        workflow_code = f"""
from kailash.workflow import WorkflowBuilder

builder = WorkflowBuilder()
reader_id = builder.add_node("CSVReaderNode", "reader", config={{"file_path": "{sample_csv_file}"}})
filter_id = builder.add_node("FilterNode", "filter", config={{"field": "value", "operator": ">", "value": 100}})
writer_id = builder.add_node("CSVWriterNode", "writer", config={{"file_path": "{temp_data_dir / 'filtered.csv'}"}})
builder.add_connection(reader_id, "data", filter_id, "data")
builder.add_connection(filter_id, "filtered_data", writer_id, "data")
workflow = builder.build("params_test")
"""
        workflow_file.write_text(workflow_code)

        # Run with params
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "run",
                str(workflow_file),
                "--params",
                str(params_file),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify output was created
        output_file = temp_data_dir / "filtered.csv"
        assert output_file.exists()

    @pytest.mark.skip(reason="CLI doesn't have a batch command")
    def test_cli_batch_processing(self, temp_data_dir: Path):
        """Test batch processing multiple workflows via CLI."""
        # Create multiple workflow files
        workflow_files = []

        for i in range(3):
            builder = WorkflowBuilder()
            builder.add_node(f"Processor{i}", f"processor_{i}")
            workflow = builder.build(f"batch_workflow_{i}")

            manifest = KailashManifest(
                metadata={"id": f"batch-{i}", "name": f"Batch Workflow {i}"},
                workflow=workflow,
            )

            manifest_file = temp_data_dir / f"workflow_{i}.json"
            manifest.save(manifest_file)
            workflow_files.append(str(manifest_file))

        # Create batch file
        batch_file = temp_data_dir / "batch.txt"
        batch_file.write_text("\n".join(workflow_files))

        # Run batch processing
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "batch",
                str(batch_file),
                "--parallel",
                "2",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Batch processing completed" in result.stdout
        assert "3 workflows processed" in result.stdout

    @pytest.mark.skip(reason="CLI doesn't have an interactive mode")
    def test_cli_interactive_mode(self, temp_data_dir: Path):
        """Test interactive CLI mode."""
        # Create a simple script to test interactive mode
        script = """
from kailash.cli.commands import interactive_mode
interactive_mode()
"""

        script_file = temp_data_dir / "interactive_test.py"
        script_file.write_text(script)

        # This test is simplified as full interactive testing is complex
        # In real implementation, you might use pexpect or similar
        result = subprocess.run(
            [sys.executable, str(script_file)],
            input="help\nexit\n",
            capture_output=True,
            text=True,
        )

        # Verify basic interactive functionality
        if "Interactive mode" in result.stdout:
            assert "Available commands:" in result.stdout

    def test_cli_error_handling(self, temp_data_dir: Path):
        """Test CLI error handling."""
        # Test with non-existent file
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "run", "nonexistent.json"],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Error" in result.stderr or "not found" in result.stderr

        # Test with invalid workflow
        invalid_workflow = {"invalid": "data"}
        invalid_file = temp_data_dir / "invalid.json"
        with open(invalid_file, "w") as f:
            json.dump(invalid_workflow, f)

        result = subprocess.run(
            [sys.executable, "-m", "kailash", "validate", str(invalid_file)],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Invalid" in result.stderr or "Error" in result.stderr

    @pytest.mark.skip(reason="CLI doesn't have a plugins command")
    def test_cli_plugin_support(self, temp_data_dir: Path):
        """Test CLI plugin loading and execution."""
        # Create a simple plugin
        plugin_code = """
from kailash.nodes.base import Node

class CustomPlugin(Node):
    '''Custom plugin node for testing.'''

    def execute(self, inputs):
        return {"message": "Plugin executed!"}

    @classmethod
    def get_info(cls):
        return {
            "name": "CustomPlugin",
            "description": "Test plugin",
            "inputs": {},
            "outputs": {"message": "TEXT"}
        }
"""

        plugin_file = temp_data_dir / "custom_plugin.py"
        plugin_file.write_text(plugin_code)

        # Test loading plugin
        result = subprocess.run(
            [sys.executable, "-m", "kailash", "plugins", "load", str(plugin_file)],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            assert "Plugin loaded" in result.stdout

            # List plugins
            result = subprocess.run(
                [sys.executable, "-m", "kailash", "plugins", "list"],
                capture_output=True,
                text=True,
            )

            assert "CustomPlugin" in result.stdout

    @pytest.mark.skip(reason="CLI doesn't have debugging features")
    def test_cli_workflow_debugging(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test workflow debugging features via CLI."""
        # Create manifest
        manifest = KailashManifest(
            metadata={"id": "debug-test", "name": "Debug Test"},
            workflow=simple_workflow,
        )

        manifest_file = temp_data_dir / "workflow.json"
        manifest.save(manifest_file)

        # Run with debug mode
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "run",
                str(manifest_file),
                "--debug",
                "--breakpoint",
                "filter",
            ],
            capture_output=True,
            text=True,
        )

        # Debug mode might require interactive input
        # This is a simplified test
        if "--debug" in result.stdout or "Debug mode" in result.stdout:
            assert "Breakpoint" in result.stdout or "Debug" in result.stdout

    @pytest.mark.skip(reason="CLI doesn't have profiling features")
    def test_cli_performance_profiling(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test performance profiling via CLI."""
        # Create manifest
        manifest = KailashManifest(
            metadata={"id": "profile-test", "name": "Profile Test"},
            workflow=simple_workflow,
        )

        manifest_file = temp_data_dir / "workflow.json"
        manifest.save(manifest_file)

        profile_output = temp_data_dir / "profile.json"

        # Run with profiling
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "kailash",
                "run",
                str(manifest_file),
                "--profile",
                "--profile-output",
                str(profile_output),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and profile_output.exists():
            # Verify profile data
            with open(profile_output, "r") as f:
                profile_data = json.load(f)

            assert "execution_time" in profile_data
            assert "node_timings" in profile_data
