"""
Unit tests for CLI generate command.

Tests the dataflow-generate command for report generation,
diagram creation, and documentation generation.
"""

from unittest.mock import Mock, mock_open, patch

import pytest
from click.testing import CliRunner


class TestGenerateCommand:
    """Test suite for generate command."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def workflow_data(self):
        """Create sample workflow data."""
        return {
            "name": "test_workflow",
            "nodes": {
                "node1": {"type": "InputNode", "params": {}},
                "node2": {"type": "ProcessNode", "params": {"key": "value"}},
            },
            "connections": [
                {
                    "source": "node1",
                    "source_output": "output",
                    "target": "node2",
                    "target_param": "input",
                }
            ],
        }

    def test_generate_report_command(self, runner, workflow_data):
        """
        Test generate command creates workflow report.

        Expected behavior:
        - Generates comprehensive report
        - Includes nodes, connections, metrics
        - Saves to file or stdout
        """
        from dataflow.cli.commands import generate

        with patch("dataflow.cli.generate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
                name="test_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.generate_report.return_value = {
                    "title": "Workflow Report",
                    "summary": "2 nodes, 1 connection",
                    "sections": [
                        {"title": "Nodes", "content": "node1, node2"},
                        {"title": "Connections", "content": "1 connection"},
                    ],
                }

                result = runner.invoke(generate, ["report", "workflow.py"])

                assert result.exit_code == 0
                assert (
                    "report" in result.output.lower()
                    or "workflow" in result.output.lower()
                )
                assert "node" in result.output.lower()

    def test_generate_diagram_command(self, runner, workflow_data):
        """
        Test generate command creates text-based workflow diagram.

        Expected behavior:
        - Generates ASCII/Unicode diagram
        - Shows nodes and connections
        - Readable in terminal
        """
        from dataflow.cli.commands import generate

        with patch("dataflow.cli.generate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
                name="test_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                # Mock diagram generation
                diagram_text = """
                ┌──────────┐
                │  node1   │
                └────┬─────┘
                     │
                ┌────▼─────┐
                │  node2   │
                └──────────┘
                """
                mock_inspector.return_value.generate_diagram.return_value = diagram_text

                result = runner.invoke(generate, ["diagram", "workflow.py"])

                assert result.exit_code == 0
                assert "node1" in result.output
                assert "node2" in result.output

    def test_generate_documentation_command(self, runner, workflow_data):
        """
        Test generate command creates workflow documentation.

        Expected behavior:
        - Generates markdown documentation
        - Includes node descriptions, parameters
        - Saves to output directory
        """
        from dataflow.cli.commands import generate

        with patch("dataflow.cli.generate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
                name="test_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                docs_content = """
# Workflow: test_workflow

## Nodes

### node1 (InputNode)
- **Type**: InputNode
- **Parameters**: None

### node2 (ProcessNode)
- **Type**: ProcessNode
- **Parameters**: key=value

## Connections
- node1.output → node2.input
"""
                mock_inspector.return_value.generate_documentation.return_value = (
                    docs_content
                )

                with patch("builtins.open", mock_open()) as mock_file:
                    result = runner.invoke(
                        generate, ["docs", "workflow.py", "--output-dir", "./docs"]
                    )

                    assert result.exit_code == 0
                    assert (
                        "documentation" in result.output.lower()
                        or "generated" in result.output.lower()
                    )
