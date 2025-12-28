"""Tests for the PerformanceComparator class."""

import time
from unittest.mock import Mock, patch

import pytest
from kailash.migration.performance_comparator import (
    ComparisonResult,
    PerformanceBenchmark,
    PerformanceComparator,
    PerformanceMetric,
    PerformanceReport,
)
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def comparator():
    """Create a PerformanceComparator instance for testing."""
    return PerformanceComparator(sample_size=2, warmup_runs=1, timeout_seconds=30)


@pytest.fixture
def simple_workflow():
    """Create a simple test workflow."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode", "test_node", {"code": "result = 42", "output_key": "answer"}
    )
    return builder.build()


@pytest.fixture
def mock_runtime():
    """Create a mock LocalRuntime for testing."""
    mock = Mock()
    mock.execute.return_value = ({"test_node": {"answer": 42}}, "run_123")
    return mock


class TestPerformanceComparator:
    """Test cases for PerformanceComparator."""

    def test_initialization(self, comparator):
        """Test PerformanceComparator initialization."""
        assert comparator is not None
        assert comparator.sample_size == 2
        assert comparator.warmup_runs == 1
        assert comparator.timeout_seconds == 30
        assert len(comparator.standard_workflows) > 0
        assert isinstance(comparator.significance_thresholds, dict)

    def test_standard_workflows_creation(self, comparator):
        """Test creation of standard benchmark workflows."""
        workflows = comparator.standard_workflows

        assert len(workflows) > 0

        # Check workflow structure
        for name, workflow in workflows:
            assert isinstance(name, str)
            assert workflow is not None
            assert len(name) > 0

        # Should have specific standard workflows
        workflow_names = [name for name, _ in workflows]
        assert "simple_linear" in workflow_names
        assert "multi_node" in workflow_names
        assert "memory_intensive" in workflow_names

    @patch("kailash.migration.performance_comparator.LocalRuntime")
    @patch("psutil.Process")
    def test_benchmark_configuration(
        self, mock_process, mock_runtime_class, comparator, simple_workflow
    ):
        """Test benchmarking of a specific configuration."""
        # Setup mocks
        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({"test": "result"}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        mock_process_instance = Mock()
        mock_process_instance.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
        mock_process_instance.cpu_percent.return_value = 50.0
        mock_process.return_value = mock_process_instance

        config = {"debug": True, "max_concurrency": 2}
        test_workflows = [("test", simple_workflow)]

        benchmarks = comparator.benchmark_configuration(config, test_workflows)

        assert isinstance(benchmarks, list)
        assert len(benchmarks) == 1

        benchmark = benchmarks[0]
        assert isinstance(benchmark, PerformanceBenchmark)
        assert benchmark.test_name == "test"
        assert benchmark.success is True
        assert benchmark.execution_time_ms > 0

    @patch("kailash.migration.performance_comparator.LocalRuntime")
    @patch("psutil.Process")
    def test_compare_configurations(
        self, mock_process, mock_runtime_class, comparator, simple_workflow
    ):
        """Test comparison between two configurations."""
        # Setup mocks
        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({"test": "result"}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        mock_process_instance = Mock()
        # Simulate different memory usage for before/after
        mock_process_instance.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
        mock_process_instance.cpu_percent.return_value = 50.0
        mock_process.return_value = mock_process_instance

        before_config = {"debug": True, "max_concurrency": 1}
        after_config = {"debug": True, "max_concurrency": 2}
        test_workflows = [("test", simple_workflow)]

        report = comparator.compare_configurations(
            before_config, after_config, test_workflows
        )

        assert isinstance(report, PerformanceReport)
        assert len(report.before_benchmarks) == 1
        assert len(report.after_benchmarks) == 1
        assert len(report.comparisons) > 0
        assert isinstance(report.overall_improvement, bool)
        assert isinstance(report.overall_change_percentage, float)

    def test_create_comparison(self, comparator):
        """Test creation of performance comparison results."""
        comparison = comparator._create_comparison("execution_time", 100.0, 80.0, "ms")

        assert isinstance(comparison, ComparisonResult)
        assert comparison.metric_name == "execution_time"
        assert comparison.before_value == 100.0
        assert comparison.after_value == 80.0
        assert comparison.change_absolute == -20.0
        assert comparison.change_percentage == -20.0
        assert comparison.improvement is True  # Lower time is better
        assert comparison.significance in [
            "major_improvement",
            "minor_improvement",
            "negligible",
            "minor_regression",
            "major_regression",
        ]

    def test_assess_significance(self, comparator):
        """Test significance assessment for performance changes."""
        # Major improvement
        assert comparator._assess_significance(-25.0) == "major_improvement"

        # Minor improvement
        assert comparator._assess_significance(-10.0) == "minor_improvement"

        # Negligible change
        assert comparator._assess_significance(2.0) == "negligible"

        # Minor regression
        assert comparator._assess_significance(15.0) == "minor_regression"

        # Major regression
        assert comparator._assess_significance(25.0) == "major_regression"

    def test_generate_text_report(self, comparator):
        """Test text report generation."""
        # Create mock report
        report = PerformanceReport(
            before_benchmarks=[],
            after_benchmarks=[],
            overall_improvement=True,
            overall_change_percentage=-10.5,
            recommendations=["Test recommendation"],
        )

        text_report = comparator.generate_performance_report(report, "text")

        assert isinstance(text_report, str)
        assert len(text_report) > 0
        assert "Performance Comparison Report" in text_report
        assert "EXECUTIVE SUMMARY" in text_report
        assert "IMPROVEMENT" in text_report
        assert "-10.5%" in text_report

    def test_generate_json_report(self, comparator):
        """Test JSON report generation."""
        report = PerformanceReport(
            before_benchmarks=[],
            after_benchmarks=[],
            overall_improvement=False,
            overall_change_percentage=5.2,
        )

        json_report = comparator.generate_performance_report(report, "json")

        assert isinstance(json_report, str)

        # Should be valid JSON
        import json

        data = json.loads(json_report)

        assert "summary" in data
        assert data["summary"]["overall_improvement"] is False
        assert data["summary"]["overall_change_percentage"] == 5.2

    def test_generate_markdown_report(self, comparator):
        """Test markdown report generation."""
        report = PerformanceReport(
            before_benchmarks=[],
            after_benchmarks=[],
            overall_improvement=True,
            overall_change_percentage=-15.0,
        )

        markdown_report = comparator.generate_performance_report(report, "markdown")

        assert isinstance(markdown_report, str)
        assert len(markdown_report) > 0
        assert "# LocalRuntime Performance Comparison Report" in markdown_report
        assert "## Executive Summary" in markdown_report
        assert "| Metric | Value |" in markdown_report

    @patch("kailash.migration.performance_comparator.LocalRuntime")
    def test_benchmark_error_handling(
        self, mock_runtime_class, comparator, simple_workflow
    ):
        """Test error handling during benchmarking."""
        # Setup mock to raise an exception
        mock_runtime = Mock()
        mock_runtime.execute.side_effect = Exception("Test error")
        mock_runtime_class.return_value = mock_runtime

        config = {"debug": True}
        test_workflows = [("error_test", simple_workflow)]

        benchmarks = comparator.benchmark_configuration(config, test_workflows)

        assert len(benchmarks) == 1
        benchmark = benchmarks[0]
        assert benchmark.success is False
        assert benchmark.error_message == "Test error"

    def test_recommendations_generation(self, comparator):
        """Test generation of performance recommendations."""
        # Create report with regression
        report = PerformanceReport(
            before_benchmarks=[],
            after_benchmarks=[],
            overall_improvement=False,
            overall_change_percentage=15.0,
            risk_assessment="medium",
        )

        # Add mock comparison showing execution time regression
        comparison = ComparisonResult(
            metric_name="execution_time",
            before_value=100.0,
            after_value=115.0,
            change_absolute=15.0,
            change_percentage=15.0,
            improvement=False,
            significance="minor_regression",
            unit="ms",
        )
        report.comparisons = [comparison]

        comparator._generate_recommendations(report)

        assert len(report.recommendations) > 0

        # Should include regression-related recommendations
        recommendations_text = " ".join(report.recommendations)
        assert (
            "regressed" in recommendations_text.lower()
            or "performance" in recommendations_text.lower()
        )

    def test_overall_performance_assessment(self, comparator):
        """Test overall performance assessment."""
        report = PerformanceReport(before_benchmarks=[], after_benchmarks=[])

        # Add comparisons with mixed results
        comparisons = [
            ComparisonResult(
                metric_name="execution_time",
                before_value=100.0,
                after_value=90.0,
                change_absolute=-10.0,
                change_percentage=-10.0,
                improvement=True,
                significance="minor_improvement",
                unit="ms",
            ),
            ComparisonResult(
                metric_name="memory_usage",
                before_value=50.0,
                after_value=55.0,
                change_absolute=5.0,
                change_percentage=10.0,
                improvement=False,
                significance="minor_regression",
                unit="mb",
            ),
        ]
        report.comparisons = comparisons

        comparator._assess_overall_performance(report)

        # Should calculate weighted average
        assert isinstance(report.overall_change_percentage, float)
        assert isinstance(report.overall_improvement, bool)
        assert report.risk_assessment in ["low", "medium", "high"]

    def test_save_report(self, comparator, tmp_path):
        """Test saving report to file."""
        report = PerformanceReport(
            before_benchmarks=[],
            after_benchmarks=[],
            overall_improvement=True,
            overall_change_percentage=-5.0,
        )

        file_path = tmp_path / "performance_report.json"
        comparator.save_report(report, file_path, "json")

        assert file_path.exists()

        # Check file content
        import json

        with open(file_path) as f:
            data = json.load(f)

        assert "summary" in data
        assert data["summary"]["overall_improvement"] is True


class TestPerformanceMetric:
    """Test cases for PerformanceMetric dataclass."""

    def test_creation(self):
        """Test PerformanceMetric creation."""
        metric = PerformanceMetric(name="execution_time", value=123.45, unit="ms")

        assert metric.name == "execution_time"
        assert metric.value == 123.45
        assert metric.unit == "ms"
        assert metric.timestamp is not None
        assert isinstance(metric.metadata, dict)


class TestPerformanceBenchmark:
    """Test cases for PerformanceBenchmark dataclass."""

    def test_creation(self):
        """Test PerformanceBenchmark creation."""
        benchmark = PerformanceBenchmark(
            test_name="test_case", configuration={"debug": True}
        )

        assert benchmark.test_name == "test_case"
        assert benchmark.configuration == {"debug": True}
        assert benchmark.execution_time_ms == 0.0
        assert benchmark.memory_usage_mb == 0.0
        assert benchmark.cpu_usage_percent == 0.0
        assert benchmark.success is True
        assert benchmark.error_message is None
        assert benchmark.run_timestamp is not None
        assert isinstance(benchmark.metrics, list)


class TestComparisonResult:
    """Test cases for ComparisonResult dataclass."""

    def test_creation(self):
        """Test ComparisonResult creation."""
        result = ComparisonResult(
            metric_name="test_metric",
            before_value=100.0,
            after_value=90.0,
            change_absolute=-10.0,
            change_percentage=-10.0,
            improvement=True,
            significance="minor_improvement",
            unit="ms",
        )

        assert result.metric_name == "test_metric"
        assert result.before_value == 100.0
        assert result.after_value == 90.0
        assert result.change_absolute == -10.0
        assert result.change_percentage == -10.0
        assert result.improvement is True
        assert result.significance == "minor_improvement"
        assert result.unit == "ms"


class TestPerformanceReport:
    """Test cases for PerformanceReport dataclass."""

    def test_creation(self):
        """Test PerformanceReport creation."""
        before_benchmarks = [
            PerformanceBenchmark("test1", {"debug": True}),
            PerformanceBenchmark("test2", {"debug": True}),
        ]
        after_benchmarks = [
            PerformanceBenchmark("test1", {"debug": False}),
            PerformanceBenchmark("test2", {"debug": False}),
        ]

        report = PerformanceReport(
            before_benchmarks=before_benchmarks, after_benchmarks=after_benchmarks
        )

        assert len(report.before_benchmarks) == 2
        assert len(report.after_benchmarks) == 2
        assert isinstance(report.comparisons, list)
        assert report.overall_improvement is False
        assert report.overall_change_percentage == 0.0
        assert isinstance(report.recommendations, list)
        assert report.risk_assessment == "low"
        assert report.generated_at is not None


if __name__ == "__main__":
    pytest.main([__file__])
