"""
Unit tests for CLI analyze command.

Tests the dataflow-analyze command for workflow metrics,
complexity analysis, and verbosity levels.
"""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


class TestAnalyzeCommand:
    """Test suite for analyze command."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def workflow_metrics(self):
        """Create sample workflow metrics."""
        return {
            "node_count": 10,
            "connection_count": 15,
            "avg_params_per_node": 3.5,
            "max_depth": 5,
            "cycles": 0,
            "branches": 2,
        }

    def test_analyze_command_workflow_metrics(self, runner, workflow_metrics):
        """
        Test analyze command extracts workflow metrics.

        Expected behavior:
        - Displays node count, connection count
        - Shows graph depth and complexity
        - Exit code 0
        """
        from dataflow.cli.commands import analyze

        with patch("dataflow.cli.analyze.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock()},
                connections=[{"source": "node1", "target": "node2"}],
                name="test_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.get_metrics.return_value = workflow_metrics

                result = runner.invoke(analyze, ["workflow.py"])

                assert result.exit_code == 0
                assert "10" in result.output  # node_count
                assert "15" in result.output  # connection_count
                assert (
                    "metrics" in result.output.lower()
                    or "node" in result.output.lower()
                )

    def test_analyze_command_complexity_analysis(self, runner):
        """
        Test analyze command performs complexity analysis.

        Expected behavior:
        - Calculates cyclomatic complexity
        - Identifies bottlenecks
        - Reports complexity score
        """
        from dataflow.cli.commands import analyze

        with patch("dataflow.cli.analyze.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock()},
                connections=[],
                name="complex_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                # Mock get_metrics() which is called first
                mock_inspector.return_value.get_metrics.return_value = {
                    "node_count": 2,
                    "connection_count": 0,
                }

                complexity_data = {
                    "cyclomatic_complexity": 12,
                    "cognitive_complexity": 15,
                    "bottlenecks": [{"node": "node1", "impact": "high"}],
                    "complexity_score": "medium",
                }
                mock_inspector.return_value.analyze_complexity.return_value = (
                    complexity_data
                )

                result = runner.invoke(analyze, ["workflow.py", "--complexity"])

                assert result.exit_code == 0
                assert "complexity" in result.output.lower()
                assert "12" in result.output or "15" in result.output

    def test_analyze_command_verbosity_levels(self, runner, workflow_metrics):
        """
        Test analyze command supports verbosity levels.

        Expected behavior:
        - -q: Quiet mode (minimal output)
        - Default: Standard output
        - -v: Verbose (detailed metrics)
        - -vv: Very verbose (all data)
        """
        from dataflow.cli.commands import analyze

        with patch("dataflow.cli.analyze.load_workflow") as mock_load:
            mock_load.return_value = Mock(nodes={}, connections=[], name="test")

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.get_metrics.return_value = workflow_metrics

                # Test quiet mode
                result_quiet = runner.invoke(analyze, ["workflow.py", "-q"])
                assert result_quiet.exit_code == 0
                quiet_lines = len(result_quiet.output.strip().split("\n"))

                # Test verbose mode
                result_verbose = runner.invoke(analyze, ["workflow.py", "-v"])
                assert result_verbose.exit_code == 0
                verbose_lines = len(result_verbose.output.strip().split("\n"))

                # Verbose should have more output than quiet
                assert verbose_lines >= quiet_lines

                # Test very verbose mode
                result_vv = runner.invoke(analyze, ["workflow.py", "-vv"])
                assert result_vv.exit_code == 0
                vv_lines = len(result_vv.output.strip().split("\n"))

                # Very verbose should have most output
                assert vv_lines >= verbose_lines

    def test_analyze_command_json_output(self, runner, workflow_metrics):
        """
        Test analyze command with JSON output format.

        Expected behavior:
        - Valid JSON output
        - Contains all metrics
        - Machine-readable format
        """
        from dataflow.cli.commands import analyze

        with patch("dataflow.cli.analyze.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()}, connections=[], name="test_workflow"
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.get_metrics.return_value = workflow_metrics

                result = runner.invoke(analyze, ["workflow.py", "--format", "json"])

                assert result.exit_code == 0

                # Parse JSON output
                output_data = json.loads(result.output)
                assert "node_count" in output_data
                assert output_data["node_count"] == 10
                assert "connection_count" in output_data
                assert output_data["connection_count"] == 15
