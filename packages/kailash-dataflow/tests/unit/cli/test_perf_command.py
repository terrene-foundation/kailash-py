"""
Unit tests for CLI perf command.

Tests the dataflow-perf command for performance profiling,
bottleneck detection, and optimization recommendations.
"""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner


class TestPerfCommand:
    """Test suite for perf command."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def performance_data(self):
        """Create sample performance profiling data."""
        return {
            "total_time": 1.234,
            "node_timings": {
                "node1": {"time": 0.100, "calls": 1, "percentage": 8.1},
                "node2": {"time": 0.500, "calls": 1, "percentage": 40.5},
                "node3": {"time": 0.634, "calls": 1, "percentage": 51.4},
            },
            "bottlenecks": [{"node": "node3", "time": 0.634, "impact": "high"}],
            "memory_usage": {"peak": "45.2 MB", "average": "32.1 MB"},
        }

    def test_perf_command_execution_profiling(self, runner, performance_data):
        """
        Test perf command profiles workflow execution.

        Expected behavior:
        - Executes workflow with profiling enabled
        - Measures time per node
        - Reports total execution time
        """
        from dataflow.cli.commands import perf

        with patch("dataflow.cli.perf.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock(), "node3": Mock()},
                connections=[],
                name="perf_workflow",
            )

            with patch("dataflow.cli.perf.ProfilingRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.execute.return_value = ({"result": "data"}, "run123")
                mock_instance.get_profile.return_value = performance_data

                result = runner.invoke(perf, ["workflow.py"])

                assert result.exit_code == 0
                # Should show timing information
                assert "1.234" in result.output or "time" in result.output.lower()
                assert "node" in result.output.lower()

    def test_perf_command_bottleneck_detection(self, runner, performance_data):
        """
        Test perf command identifies performance bottlenecks.

        Expected behavior:
        - Identifies slowest nodes
        - Calculates percentage of total time
        - Ranks by impact
        """
        from dataflow.cli.commands import perf

        with patch("dataflow.cli.perf.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock(), "node3": Mock()},
                connections=[],
                name="bottleneck_workflow",
            )

            with patch("dataflow.cli.perf.ProfilingRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.execute.return_value = ({}, "run123")
                mock_instance.get_profile.return_value = performance_data

                result = runner.invoke(perf, ["workflow.py", "--bottlenecks"])

                assert result.exit_code == 0
                # Should identify node3 as bottleneck
                assert "node3" in result.output
                assert "bottleneck" in result.output.lower() or "51.4" in result.output

    def test_perf_command_output_formats(self, runner, performance_data):
        """
        Test perf command supports multiple output formats.

        Expected behavior:
        - Text format (default): Human-readable
        - JSON format: Machine-readable
        - YAML format: Structured data
        """
        from dataflow.cli.commands import perf

        with patch("dataflow.cli.perf.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()}, connections=[], name="format_workflow"
            )

            with patch("dataflow.cli.perf.ProfilingRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.execute.return_value = ({}, "run123")
                mock_instance.get_profile.return_value = performance_data

                # Test JSON format
                result_json = runner.invoke(perf, ["workflow.py", "--format", "json"])
                assert result_json.exit_code == 0

                output_data = json.loads(result_json.output)
                assert "total_time" in output_data
                assert output_data["total_time"] == 1.234

                # Test text format (default)
                result_text = runner.invoke(perf, ["workflow.py"])
                assert result_text.exit_code == 0
                assert len(result_text.output) > 0

    def test_perf_command_with_recommendations(self, runner, performance_data):
        """
        Test perf command provides optimization recommendations.

        Expected behavior:
        - Analyzes performance data
        - Suggests optimizations
        - Prioritizes by impact
        """
        from dataflow.cli.commands import perf

        with patch("dataflow.cli.perf.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock(), "node2": Mock(), "node3": Mock()},
                connections=[],
                name="optimize_workflow",
            )

            with patch("dataflow.cli.perf.ProfilingRuntime") as mock_runtime:
                mock_instance = mock_runtime.return_value
                mock_instance.execute.return_value = ({}, "run123")

                # Add recommendations to performance data
                perf_with_recommendations = performance_data.copy()
                perf_with_recommendations["recommendations"] = [
                    {
                        "node": "node3",
                        "issue": "Slow execution",
                        "suggestion": "Consider caching or parallelization",
                        "impact": "high",
                    }
                ]
                mock_instance.get_profile.return_value = perf_with_recommendations

                result = runner.invoke(perf, ["workflow.py", "--recommend"])

                assert result.exit_code == 0
                assert (
                    "recommendation" in result.output.lower()
                    or "optimization" in result.output.lower()
                )
                assert "node3" in result.output
