"""
Unit tests for CLI generate command.

Tests the dataflow-generate command for report generation,
diagram creation, and documentation generation.

Mock-construction discipline (origin: 2026-05-06 docs/Mock leak):
``Mock(name="X")`` does NOT set ``Mock.name`` — the ``name=`` kwarg
configures the Mock's repr-name (used in str/repr), and ``.name``
remains a child Mock. Code that f-strings the workflow's ``.name``
into a filename leaks ``"<Mock name='test_workflow.name' id='...'>.md"``
to disk. ALWAYS construct via ``mock = Mock(...); mock.name = "X"``
post-construction.

Filesystem-isolation discipline (per ``tests/unit/CLAUDE.md`` Tier 1):
the ``docs`` subcommand calls ``Path.write_text`` which is NOT
intercepted by ``patch("builtins.open", ...)``. Any test exercising
that path MUST point ``--output-dir`` at ``tmp_path`` so writes are
bounded and auto-cleaned by pytest.
"""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


def _make_workflow_mock(*, nodes, connections, name="test_workflow"):
    """Build a Mock workflow with `.name` set CORRECTLY.

    See module docstring on why ``Mock(name=...)`` is wrong here.
    """
    mock_workflow = Mock(nodes=nodes, connections=connections)
    mock_workflow.name = name  # post-construction assignment, NOT Mock(name=)
    return mock_workflow


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
            mock_load.return_value = _make_workflow_mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
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
            mock_load.return_value = _make_workflow_mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
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

    def test_generate_documentation_command(self, runner, workflow_data, tmp_path):
        """
        Test generate command creates workflow documentation.

        Expected behavior:
        - Generates markdown documentation
        - Includes node descriptions, parameters
        - Saves to output directory
        - Filename derives from validated `workflow.name` via
          `safe_workflow_filename` (rejects path-traversal,
          filesystem-unsafe chars, Mock-repr leaks).
        """
        from dataflow.cli.commands import generate

        with patch("dataflow.cli.generate.load_workflow") as mock_load:
            mock_load.return_value = _make_workflow_mock(
                nodes=workflow_data["nodes"],
                connections=workflow_data["connections"],
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

                # tmp_path bounds the filesystem write so it auto-cleans.
                # `Path.write_text` (used by generate.py:159) is NOT caught
                # by `patch("builtins.open", mock_open())`, so we point the
                # real write at pytest's tmp dir.
                output_dir = tmp_path / "docs"
                result = runner.invoke(
                    generate,
                    ["docs", "workflow.py", "--output-dir", str(output_dir)],
                )

                assert result.exit_code == 0
                assert (
                    "documentation" in result.output.lower()
                    or "generated" in result.output.lower()
                )
                # Verify the file landed under tmp_path with the validated name.
                doc_file = output_dir / "test_workflow.md"
                assert doc_file.exists(), (
                    f"expected {doc_file} to exist, got "
                    f"{list(output_dir.glob('*.md')) if output_dir.exists() else 'no dir'}"
                )
                assert "test_workflow" in doc_file.read_text()

    def test_generate_documentation_rejects_unsafe_workflow_name(
        self, runner, workflow_data, tmp_path
    ):
        """
        Regression for 2026-05-06 docs/Mock leak.

        When `workflow.name` is not a string (e.g. a Mock object whose
        `.name` returned a child Mock), the docs command MUST raise
        rather than write `<Mock name='...' id='...'>.md` to disk.
        """
        from dataflow.cli.commands import generate

        # Reproduce the historical bug: Mock(name="X") sets repr-name,
        # NOT .name — so .name returns a child Mock that f-strings to
        # `<Mock name='X.name' id='...'>` if the helper doesn't validate.
        bad_mock = Mock(
            nodes=workflow_data["nodes"],
            connections=workflow_data["connections"],
            name="test_workflow",  # WRONG — does not set .name to "test_workflow"
        )

        with patch("dataflow.cli.generate.load_workflow") as mock_load:
            mock_load.return_value = bad_mock

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.generate_documentation.return_value = "x"

                output_dir = tmp_path / "docs"
                result = runner.invoke(
                    generate,
                    ["docs", "workflow.py", "--output-dir", str(output_dir)],
                )

                # Click runner returns exit_code 2 when the command's
                # except-Exception branch fires after WorkflowNameError.
                assert result.exit_code == 2, result.output
                # And — the critical assertion — NO Mock-repr file was written.
                if output_dir.exists():
                    leaked = [
                        p.name
                        for p in output_dir.iterdir()
                        if p.name.startswith("<Mock")
                    ]
                    assert leaked == [], (
                        f"safe_workflow_filename failed to reject Mock-repr "
                        f"input — leaked files: {leaked}"
                    )
