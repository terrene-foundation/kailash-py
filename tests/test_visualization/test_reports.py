"""Tests for performance report generation."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.reports import (
    PerformanceInsight,
    ReportConfig,
    ReportFormat,
    WorkflowPerformanceReporter,
    WorkflowSummary,
)


class TestReportConfig:
    """Test report configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ReportConfig()

        assert config.include_charts is True
        assert config.include_recommendations is True
        assert config.chart_format == "png"
        assert config.detail_level == "detailed"
        assert config.compare_historical is True
        assert config.theme == "corporate"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ReportConfig(
            include_charts=False,
            include_recommendations=False,
            chart_format="svg",
            detail_level="summary",
            compare_historical=False,
            theme="dark",
        )

        assert config.include_charts is False
        assert config.include_recommendations is False
        assert config.chart_format == "svg"
        assert config.detail_level == "summary"
        assert config.compare_historical is False
        assert config.theme == "dark"


class TestPerformanceInsight:
    """Test performance insight data structure."""

    def test_insight_creation(self):
        """Test creating performance insights."""
        insight = PerformanceInsight(
            category="bottleneck",
            severity="high",
            title="Slow Task Execution",
            description="Task X is taking too long",
            recommendation="Optimize task X algorithm",
            metrics={"duration": 10.5, "threshold": 5.0},
        )

        assert insight.category == "bottleneck"
        assert insight.severity == "high"
        assert insight.title == "Slow Task Execution"
        assert insight.description == "Task X is taking too long"
        assert insight.recommendation == "Optimize task X algorithm"
        assert insight.metrics["duration"] == 10.5
        assert insight.metrics["threshold"] == 5.0


class TestWorkflowSummary:
    """Test workflow summary data structure."""

    def test_summary_creation(self):
        """Test creating workflow summary."""
        summary = WorkflowSummary(
            run_id="test-run-123",
            workflow_name="test_workflow",
            total_tasks=10,
            completed_tasks=8,
            failed_tasks=2,
            total_duration=45.5,
            avg_cpu_usage=35.2,
            peak_memory_usage=256.0,
            throughput=12.5,
            efficiency_score=75.0,
        )

        assert summary.run_id == "test-run-123"
        assert summary.workflow_name == "test_workflow"
        assert summary.total_tasks == 10
        assert summary.completed_tasks == 8
        assert summary.failed_tasks == 2
        assert summary.total_duration == 45.5
        assert summary.avg_cpu_usage == 35.2
        assert summary.peak_memory_usage == 256.0
        assert summary.throughput == 12.5
        assert summary.efficiency_score == 75.0


class TestWorkflowPerformanceReporter:
    """Test workflow performance reporter."""

    @pytest.fixture
    def task_manager(self, tmp_path):
        """Create test task manager with data."""
        storage = FileSystemStorage(tmp_path / "test_storage")
        task_manager = TaskManager(storage)

        # Create a test run
        run_id = task_manager.create_run("test_workflow", {"param1": "value1"})

        # Add test tasks
        task_metrics = [
            TaskMetrics(duration=2.0, cpu_usage=30.0, memory_usage_mb=100.0),
            TaskMetrics(duration=3.5, cpu_usage=45.0, memory_usage_mb=150.0),
            TaskMetrics(duration=1.8, cpu_usage=25.0, memory_usage_mb=80.0),
        ]

        for i, metrics in enumerate(task_metrics):
            task = task_manager.create_task(
                node_id=f"test_node_{i}", run_id=run_id, node_type="TestNode"
            )
            task_id = task.task_id

            if i < 2:  # Complete first two tasks
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.complete_task(task_id, {"result": f"result_{i}"})
            else:  # Fail the last task
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.fail_task(task_id, "Test error")

        return task_manager, run_id

    @pytest.fixture
    def reporter(self, task_manager):
        """Create test reporter."""
        task_manager_instance, run_id = task_manager
        config = ReportConfig(include_charts=False)  # Disable charts for testing
        return WorkflowPerformanceReporter(task_manager_instance, config), run_id

    def test_reporter_initialization(self, task_manager):
        """Test reporter initialization."""
        task_manager_instance, run_id = task_manager

        # Test with default config
        reporter = WorkflowPerformanceReporter(task_manager_instance)
        assert reporter.task_manager == task_manager_instance
        assert isinstance(reporter.config, ReportConfig)
        assert reporter.config.include_charts is True

        # Test with custom config
        custom_config = ReportConfig(include_charts=False, theme="dark")
        reporter = WorkflowPerformanceReporter(task_manager_instance, custom_config)
        assert reporter.config == custom_config
        assert reporter.config.include_charts is False
        assert reporter.config.theme == "dark"

    def test_calculate_workflow_summary(self, reporter):
        """Test workflow summary calculation."""
        reporter_instance, run_id = reporter

        # Get run and tasks
        run = reporter_instance.task_manager.get_run(run_id)
        tasks = reporter_instance.task_manager.get_run_tasks(run_id)

        # Calculate summary
        summary = reporter_instance._calculate_workflow_summary(run, tasks)

        assert summary.run_id == run_id
        assert summary.workflow_name == "test_workflow"
        assert summary.total_tasks == 3
        assert summary.completed_tasks == 2
        assert summary.failed_tasks == 1
        assert summary.total_duration > 0  # Should have some duration
        assert summary.avg_cpu_usage > 0  # Should have CPU usage
        assert summary.peak_memory_usage > 0  # Should have memory usage

    def test_analyze_task_performance(self, reporter):
        """Test task performance analysis."""
        reporter_instance, run_id = reporter

        tasks = reporter_instance.task_manager.get_run_tasks(run_id)
        analysis = reporter_instance._analyze_task_performance(tasks)

        assert "by_node_type" in analysis
        assert "duration_distribution" in analysis
        assert "resource_patterns" in analysis
        assert "execution_order" in analysis

        # Check node type analysis
        assert "TestNode" in analysis["by_node_type"]
        node_stats = analysis["by_node_type"]["TestNode"]
        assert node_stats["count"] == 3
        assert node_stats["completed"] == 2
        assert node_stats["avg_duration"] > 0
        assert node_stats["success_rate"] < 100  # One task failed

    def test_identify_bottlenecks(self, reporter):
        """Test bottleneck identification."""
        reporter_instance, run_id = reporter

        tasks = reporter_instance.task_manager.get_run_tasks(run_id)
        bottlenecks = reporter_instance._identify_bottlenecks(tasks)

        # Should identify bottlenecks based on duration, CPU, memory
        assert isinstance(bottlenecks, list)

        # Check bottleneck structure
        for bottleneck in bottlenecks:
            assert "type" in bottleneck
            assert "node_id" in bottleneck
            assert "node_type" in bottleneck
            assert "value" in bottleneck
            assert "threshold" in bottleneck
            assert "severity" in bottleneck
            assert bottleneck["type"] in ["duration", "memory", "cpu"]

    def test_analyze_resource_utilization(self, reporter):
        """Test resource utilization analysis."""
        reporter_instance, run_id = reporter

        tasks = reporter_instance.task_manager.get_run_tasks(run_id)
        analysis = reporter_instance._analyze_resource_utilization(tasks)

        assert "cpu_distribution" in analysis
        assert "memory_distribution" in analysis
        assert "io_patterns" in analysis
        assert "resource_efficiency" in analysis

        # Check CPU distribution
        if analysis["cpu_distribution"]:
            cpu_dist = analysis["cpu_distribution"]
            assert "mean" in cpu_dist
            assert "median" in cpu_dist
            assert "std" in cpu_dist
            assert "min" in cpu_dist
            assert "max" in cpu_dist
            assert "percentiles" in cpu_dist

    def test_analyze_errors(self, reporter):
        """Test error analysis."""
        reporter_instance, run_id = reporter

        tasks = reporter_instance.task_manager.get_run_tasks(run_id)
        analysis = reporter_instance._analyze_errors(tasks)

        assert "error_summary" in analysis
        assert "error_by_type" in analysis
        assert "error_timeline" in analysis
        assert "recovery_suggestions" in analysis

        # Check error summary
        error_summary = analysis["error_summary"]
        assert error_summary["total_errors"] == 1  # One failed task
        assert error_summary["error_rate"] > 0
        assert error_summary["critical_failures"] >= 0

    def test_generate_insights(self, reporter):
        """Test insight generation."""
        reporter_instance, run_id = reporter

        # Create mock analysis data
        analysis = {
            "summary": WorkflowSummary(
                run_id=run_id,
                workflow_name="test",
                efficiency_score=60.0,  # Low efficiency
                completed_tasks=2,
                total_tasks=3,
                throughput=0.5,  # Low throughput
            ),
            "bottlenecks": [
                {
                    "type": "duration",
                    "node_id": "slow_node",
                    "node_type": "SlowNode",
                    "value": 10.0,
                    "threshold": 5.0,
                    "severity": "high",
                }
            ],
            "resource_analysis": {},
            "error_analysis": {"error_summary": {"error_rate": 15.0}},
        }

        insights = reporter_instance._generate_insights(analysis)

        assert isinstance(insights, list)
        assert len(insights) > 0

        # Check insight structure
        for insight in insights:
            assert isinstance(insight, PerformanceInsight)
            assert insight.category in ["optimization", "bottleneck", "warning"]
            assert insight.severity in ["low", "medium", "high", "critical"]
            assert len(insight.title) > 0
            assert len(insight.description) > 0
            assert len(insight.recommendation) > 0

    def test_generate_html_report(self, reporter, tmp_path):
        """Test HTML report generation."""
        reporter_instance, run_id = reporter

        output_path = tmp_path / "test_report.html"
        result_path = reporter_instance.generate_report(
            run_id=run_id, output_path=output_path, format=ReportFormat.HTML
        )

        assert result_path == output_path
        assert output_path.exists()

        # Check HTML content
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Workflow Performance Report" in content
        assert "test_workflow" in content
        assert "Executive Summary" in content

        # Check for metrics
        assert "Total Tasks" in content
        assert "Completed" in content
        assert "Failed" in content

    def test_generate_markdown_report(self, reporter, tmp_path):
        """Test Markdown report generation."""
        reporter_instance, run_id = reporter

        output_path = tmp_path / "test_report.md"
        result_path = reporter_instance.generate_report(
            run_id=run_id, output_path=output_path, format=ReportFormat.MARKDOWN
        )

        assert result_path == output_path
        assert output_path.exists()

        # Check Markdown content
        content = output_path.read_text()
        assert "# 🚀 Workflow Performance Report" in content
        assert "## 📊 Executive Summary" in content
        assert "test_workflow" in content
        assert "| Metric | Value |" in content

    def test_generate_json_report(self, reporter, tmp_path):
        """Test JSON report generation."""
        reporter_instance, run_id = reporter

        output_path = tmp_path / "test_report.json"
        result_path = reporter_instance.generate_report(
            run_id=run_id, output_path=output_path, format=ReportFormat.JSON
        )

        assert result_path == output_path
        assert output_path.exists()

        # Check JSON content
        with open(output_path) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "run_info" in data
        assert "summary" in data
        assert "insights" in data
        assert "detailed_analysis" in data

        # Check summary data
        summary = data["summary"]
        assert summary["total_tasks"] == 3
        assert summary["completed_tasks"] == 2
        assert summary["failed_tasks"] == 1

    def test_invalid_report_format(self, reporter, tmp_path):
        """Test handling of invalid report format."""
        reporter_instance, run_id = reporter

        with pytest.raises(ValueError, match="Unsupported report format"):
            reporter_instance.generate_report(
                run_id=run_id,
                output_path=tmp_path / "test.txt",
                format="invalid_format",
            )

    def test_nonexistent_run(self, reporter):
        """Test handling of nonexistent run ID."""
        reporter_instance, _ = reporter

        with pytest.raises(ValueError, match="Run .* not found"):
            reporter_instance._analyze_workflow_run("nonexistent-run-id")

    def test_compare_runs(self, reporter):
        """Test run comparison functionality."""
        reporter_instance, run_id = reporter

        # Create another run for comparison
        run_id_2 = reporter_instance.task_manager.create_run("test_workflow_2", {})

        for i in range(2):
            task = reporter_instance.task_manager.create_task(
                node_id=f"node_{i}", run_id=run_id_2, node_type="TestNode"
            )
            task_id = task.task_id

            metrics = TaskMetrics(duration=1.5, cpu_usage=20.0, memory_usage_mb=90.0)
            reporter_instance.task_manager.update_task_status(
                task_id, TaskStatus.RUNNING
            )
            reporter_instance.task_manager.update_task_metrics(task_id, metrics)
            reporter_instance.task_manager.complete_task(
                task_id, {"result": f"result_{i}"}
            )

        # Test comparison
        comparison = reporter_instance._compare_runs([run_id, run_id_2])

        assert "runs" in comparison
        assert "trends" in comparison
        assert "relative_performance" in comparison

        assert len(comparison["runs"]) == 2

        # Check trends calculation
        trends = comparison["trends"]
        assert "duration_change" in trends
        assert "efficiency_change" in trends
        assert "throughput_change" in trends

    def test_default_output_path(self, reporter, tmp_path):
        """Test default output path generation."""
        reporter_instance, run_id = reporter

        # Change to temp directory for test
        import os

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            result_path = reporter_instance.generate_report(
                run_id=run_id, format=ReportFormat.HTML
            )

            # Check that a file was created with expected naming pattern
            assert result_path.exists()
            assert result_path.suffix == ".html"
            assert run_id[:8] in result_path.name

        finally:
            os.chdir(original_cwd)


class TestReportIntegration:
    """Integration tests for report generation."""

    @pytest.fixture
    def complex_workflow_data(self, tmp_path):
        """Create complex workflow data for testing."""
        storage = FileSystemStorage(tmp_path / "complex_storage")
        task_manager = TaskManager(storage)

        # Create multiple runs with different characteristics
        runs_data = []

        for run_idx in range(3):
            run_id = task_manager.create_run(f"workflow_{run_idx}", {})

            # Create tasks with varying performance characteristics
            task_count = 5 + run_idx * 2
            for task_idx in range(task_count):
                task = task_manager.create_task(
                    node_id=f"node_{task_idx}",
                    run_id=run_id,
                    node_type=f"NodeType_{task_idx % 3}",
                )
                task_id = task.task_id

                # Vary performance metrics
                base_duration = 1.0 + task_idx * 0.5
                base_cpu = 20.0 + task_idx * 5
                base_memory = 100.0 + task_idx * 20

                metrics = TaskMetrics(
                    duration=base_duration * (1 + run_idx * 0.2),
                    cpu_usage=base_cpu * (1 + run_idx * 0.1),
                    memory_usage_mb=base_memory * (1 + run_idx * 0.15),
                    custom_metrics={
                        "io_read_bytes": 1024 * (task_idx + 1),
                        "io_write_bytes": 512 * (task_idx + 1),
                        "io_read_count": task_idx + 1,
                        "io_write_count": task_idx,
                    },
                )

                # Complete most tasks, fail some occasionally
                if task_idx < task_count - 1 or run_idx == 0:
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.complete_task(
                        task_id, {"result": f"result_{task_idx}"}
                    )
                else:
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.fail_task(task_id, f"Error in run {run_idx}")

            runs_data.append(run_id)

        return task_manager, runs_data

    def test_comprehensive_report_generation(self, complex_workflow_data, tmp_path):
        """Test comprehensive report generation with complex data."""
        task_manager, run_ids = complex_workflow_data

        reporter = WorkflowPerformanceReporter(task_manager)

        # Generate report for the most complex run
        run_id = run_ids[2]  # Last run has most tasks

        # Test all formats
        formats = [
            (ReportFormat.HTML, "comprehensive.html"),
            (ReportFormat.MARKDOWN, "comprehensive.md"),
            (ReportFormat.JSON, "comprehensive.json"),
        ]

        for report_format, filename in formats:
            output_path = tmp_path / filename
            result_path = reporter.generate_report(
                run_id=run_id,
                output_path=output_path,
                format=report_format,
                compare_runs=run_ids[:2],  # Compare with first two runs
            )

            assert result_path.exists()
            assert result_path.stat().st_size > 0

            # Format-specific checks
            if report_format == ReportFormat.JSON:
                with open(result_path) as f:
                    data = json.load(f)

                assert "comparison" in data  # Should have comparison data
                assert len(data["comparison"]["runs"]) == 3  # Should compare all 3 runs

                # Check detailed analysis
                detailed = data["detailed_analysis"]
                assert "task_analysis" in detailed
                assert "bottlenecks" in detailed
                assert "resource_analysis" in detailed
                assert "error_analysis" in detailed

    def test_report_with_recommendations(self, complex_workflow_data, tmp_path):
        """Test report generation with performance recommendations."""
        task_manager, run_ids = complex_workflow_data

        # Configure for detailed recommendations
        config = ReportConfig(
            include_recommendations=True, detail_level="comprehensive"
        )

        reporter = WorkflowPerformanceReporter(task_manager, config)

        output_path = tmp_path / "recommendations_report.html"
        reporter.generate_report(
            run_id=run_ids[2], output_path=output_path, format=ReportFormat.HTML
        )

        content = output_path.read_text()

        # Check for recommendations section
        assert "Performance Insights" in content
        assert "Recommendation" in content

        # Should contain insight indicators
        assert any(indicator in content for indicator in ["🔍", "⚡", "⚠️"])

    def test_report_performance_with_large_dataset(self, tmp_path):
        """Test report generation performance with larger dataset."""
        storage = FileSystemStorage(tmp_path / "large_storage")
        task_manager = TaskManager(storage)

        # Create a run with many tasks
        run_id = task_manager.create_run("large_workflow", {})

        import time

        start_time = time.time()

        # Create 50 tasks (simulating larger workflow)
        for i in range(50):
            task = task_manager.create_task(
                node_id=f"task_{i:03d}", run_id=run_id, node_type=f"Type_{i % 5}"
            )
            task_id = task.task_id

            metrics = TaskMetrics(
                duration=0.1 + (i % 10) * 0.1,
                cpu_usage=10.0 + (i % 20) * 2,
                memory_usage_mb=50.0 + (i % 30) * 5,
            )

            if i % 10 != 9:  # 90% success rate
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.complete_task(task_id, {"result": f"result_{i}"})
            else:
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.fail_task(task_id, f"Error {i}")

        setup_time = time.time() - start_time

        # Generate report and measure time
        reporter = WorkflowPerformanceReporter(task_manager)

        report_start = time.time()
        output_path = tmp_path / "large_report.json"
        reporter.generate_report(
            run_id=run_id, output_path=output_path, format=ReportFormat.JSON
        )
        report_time = time.time() - report_start

        # Verify report was generated
        assert output_path.exists()

        with open(output_path) as f:
            data = json.load(f)

        assert data["summary"]["total_tasks"] == 50
        assert len(data["detailed_analysis"]["task_analysis"]["by_node_type"]) == 5

        # Performance should be reasonable (less than 5 seconds for 50 tasks)
        assert (
            report_time < 5.0
        ), f"Report generation took {report_time:.2f}s, expected < 5s"

        print(f"Setup: {setup_time:.2f}s, Report generation: {report_time:.2f}s")

    def test_error_handling_in_report_generation(self, tmp_path):
        """Test error handling during report generation."""
        storage = FileSystemStorage(tmp_path / "error_storage")
        task_manager = TaskManager(storage)

        reporter = WorkflowPerformanceReporter(task_manager)

        # Test with empty run (no tasks)
        empty_run_id = task_manager.create_run("empty_workflow", {})

        output_path = tmp_path / "empty_report.html"
        result_path = reporter.generate_report(
            run_id=empty_run_id, output_path=output_path, format=ReportFormat.HTML
        )

        # Should handle empty run gracefully
        assert result_path.exists()
        content = result_path.read_text()
        assert "empty_workflow" in content

        # Test with run containing only failed tasks
        failed_run_id = task_manager.create_run("failed_workflow", {})

        for i in range(3):
            task = task_manager.create_task(
                node_id=f"failed_task_{i}", run_id=failed_run_id, node_type="FailedNode"
            )
            task_id = task.task_id
            task_manager.update_task_status(task_id, TaskStatus.RUNNING)
            task_manager.fail_task(task_id, f"Intentional failure {i}")

        failed_output_path = tmp_path / "failed_report.json"
        failed_result_path = reporter.generate_report(
            run_id=failed_run_id,
            output_path=failed_output_path,
            format=ReportFormat.JSON,
        )

        assert failed_result_path.exists()

        with open(failed_result_path) as f:
            failed_data = json.load(f)

        assert failed_data["summary"]["total_tasks"] == 3
        assert failed_data["summary"]["completed_tasks"] == 0
        assert failed_data["summary"]["failed_tasks"] == 3
        assert (
            failed_data["detailed_analysis"]["error_analysis"]["error_summary"][
                "error_rate"
            ]
            == 100.0
        )
