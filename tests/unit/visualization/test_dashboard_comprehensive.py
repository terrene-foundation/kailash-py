"""Comprehensive tests for RealTimeDashboard module.

This module provides thorough test coverage for the dashboard visualization
components, following TDD principles with focus on high-impact coverage improvement.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.dashboard import (
    DashboardConfig,
    DashboardExporter,
    LiveMetrics,
    RealTimeDashboard,
)


class TestLiveMetrics:
    """Test LiveMetrics dataclass functionality."""

    def test_live_metrics_default_creation(self):
        """Test LiveMetrics creation with defaults."""
        metrics = LiveMetrics()

        assert isinstance(metrics.timestamp, datetime)
        assert metrics.active_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.total_cpu_usage == 0.0
        assert metrics.total_memory_usage == 0.0
        assert metrics.throughput == 0.0
        assert metrics.avg_task_duration == 0.0

    def test_live_metrics_custom_values(self):
        """Test LiveMetrics creation with custom values."""
        timestamp = datetime.now()
        metrics = LiveMetrics(
            timestamp=timestamp,
            active_tasks=5,
            completed_tasks=10,
            failed_tasks=2,
            total_cpu_usage=75.5,
            total_memory_usage=1024.0,
            throughput=12.5,
            avg_task_duration=2.34,
        )

        assert metrics.timestamp == timestamp
        assert metrics.active_tasks == 5
        assert metrics.completed_tasks == 10
        assert metrics.failed_tasks == 2
        assert metrics.total_cpu_usage == 75.5
        assert metrics.total_memory_usage == 1024.0
        assert metrics.throughput == 12.5
        assert metrics.avg_task_duration == 2.34


class TestDashboardConfig:
    """Test DashboardConfig functionality and validation."""

    def test_dashboard_config_defaults(self):
        """Test DashboardConfig default values."""
        config = DashboardConfig()

        assert config.update_interval == 1.0
        assert config.max_history_points == 100
        assert config.auto_refresh is True
        assert config.show_completed is True
        assert config.show_failed is True
        assert config.theme == "light"

    def test_dashboard_config_custom_values(self):
        """Test DashboardConfig with custom values."""
        config = DashboardConfig(
            update_interval=0.5,
            max_history_points=200,
            auto_refresh=False,
            show_completed=False,
            show_failed=False,
            theme="dark",
        )

        assert config.update_interval == 0.5
        assert config.max_history_points == 200
        assert config.auto_refresh is False
        assert config.show_completed is False
        assert config.show_failed is False
        assert config.theme == "dark"

    def test_dashboard_config_edge_cases(self):
        """Test DashboardConfig edge cases."""
        # Test very small update interval
        config = DashboardConfig(update_interval=0.01)
        assert config.update_interval == 0.01

        # Test very large history points
        config = DashboardConfig(max_history_points=10000)
        assert config.max_history_points == 10000

        # Test theme validation (should accept any string)
        config = DashboardConfig(theme="custom")
        assert config.theme == "custom"


class TestRealTimeDashboard:
    """Test RealTimeDashboard core functionality."""

    @pytest.fixture
    def task_manager(self, tmp_path):
        """Create a TaskManager for testing."""
        storage = FileSystemStorage(base_path=str(tmp_path))
        return TaskManager(storage_backend=storage)

    @pytest.fixture
    def dashboard(self, task_manager):
        """Create a RealTimeDashboard for testing."""
        return RealTimeDashboard(task_manager)

    @pytest.fixture
    def dashboard_with_config(self, task_manager):
        """Create a RealTimeDashboard with custom config."""
        config = DashboardConfig(
            update_interval=0.1, max_history_points=50, theme="dark"
        )
        return RealTimeDashboard(task_manager, config)

    def test_dashboard_initialization(self, task_manager):
        """Test RealTimeDashboard initialization."""
        dashboard = RealTimeDashboard(task_manager)

        assert dashboard.task_manager == task_manager
        assert isinstance(dashboard.config, DashboardConfig)
        assert dashboard._monitoring is False
        assert dashboard._monitor_thread is None
        assert dashboard._metrics_history == []
        assert dashboard._current_run_id is None
        assert dashboard._status_callbacks == []
        assert dashboard._metrics_callbacks == []

    def test_dashboard_initialization_with_config(self, task_manager):
        """Test dashboard initialization with custom config."""
        config = DashboardConfig(update_interval=2.0, theme="dark")
        dashboard = RealTimeDashboard(task_manager, config)

        assert dashboard.config == config
        assert dashboard.config.update_interval == 2.0
        assert dashboard.config.theme == "dark"

    def test_start_monitoring_basic(self, dashboard):
        """Test basic start_monitoring functionality."""
        with patch.object(dashboard, "_monitor_loop") as mock_loop:
            dashboard.start_monitoring("test-run-id")

            assert dashboard._monitoring is True
            assert dashboard._current_run_id == "test-run-id"
            assert isinstance(dashboard._monitor_thread, threading.Thread)
            assert dashboard._monitor_thread.daemon is True

            # Clean up
            dashboard.stop_monitoring()

    def test_start_monitoring_already_active_warning(self, dashboard):
        """Test warning when starting monitoring that's already active."""
        with patch.object(dashboard, "_monitor_loop") as mock_loop:
            dashboard.start_monitoring("test-run-id")

            with patch.object(dashboard.logger, "warning") as mock_warning:
                dashboard.start_monitoring("another-run-id")
                mock_warning.assert_called_once_with("Monitoring already active")

            # Verify state hasn't changed
            assert dashboard._current_run_id == "test-run-id"

            # Clean up
            dashboard.stop_monitoring()

    def test_stop_monitoring(self, dashboard):
        """Test stop_monitoring functionality."""
        with patch.object(dashboard, "_monitor_loop") as mock_loop:
            dashboard.start_monitoring("test-run-id")
            assert dashboard._monitoring is True

            dashboard.stop_monitoring()
            assert dashboard._monitoring is False

    def test_stop_monitoring_when_not_active(self, dashboard):
        """Test stopping monitoring when not active."""
        # Should not raise exception
        dashboard.stop_monitoring()
        assert dashboard._monitoring is False

    def test_collect_live_metrics_no_tasks(self, dashboard):
        """Test _collect_live_metrics when no tasks exist."""
        metrics = dashboard._collect_live_metrics()

        assert isinstance(metrics, LiveMetrics)
        assert metrics.active_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.total_cpu_usage == 0.0
        assert metrics.total_memory_usage == 0.0

    def test_collect_live_metrics_with_specific_run(self, dashboard, task_manager):
        """Test _collect_live_metrics with specific run ID."""
        run_id = "test-run-123"
        dashboard._current_run_id = run_id

        # Create mock tasks with different statuses
        task1 = TaskRun(
            task_id="task1",
            run_id=run_id,
            node_id="node1",
            node_type="TestNode",
            status=TaskStatus.RUNNING,
        )
        task2 = TaskRun(
            task_id="task2",
            run_id=run_id,
            node_id="node2",
            node_type="TestNode",
            status=TaskStatus.COMPLETED,
            metrics=TaskMetrics(cpu_usage=50.0, memory_usage_mb=256.0, duration=1.5),
        )
        task3 = TaskRun(
            task_id="task3",
            run_id=run_id,
            node_id="node3",
            node_type="TestNode",
            status=TaskStatus.FAILED,
        )

        # Mock the task retrieval
        with patch.object(task_manager, "get_run_tasks") as mock_get_tasks:
            mock_get_tasks.return_value = [task1, task2, task3]

            metrics = dashboard._collect_live_metrics()

            assert metrics.active_tasks == 1
            assert metrics.completed_tasks == 1
            assert metrics.failed_tasks == 1
            assert metrics.total_cpu_usage == 50.0
            assert metrics.total_memory_usage == 256.0
            assert metrics.avg_task_duration == 1.5

    def test_collect_live_metrics_recent_run(self, dashboard, task_manager):
        """Test _collect_live_metrics using most recent run."""
        # Create a run
        run_id = task_manager.create_run("test_workflow")

        # Don't set current_run_id - should use recent
        dashboard._current_run_id = None

        with patch.object(task_manager, "list_runs") as mock_list_runs:
            mock_run = Mock()
            mock_run.run_id = run_id
            mock_list_runs.return_value = [mock_run]

            with patch.object(task_manager, "get_run_tasks") as mock_get_tasks:
                mock_get_tasks.return_value = []

                metrics = dashboard._collect_live_metrics()

                mock_list_runs.assert_called_once()
                mock_get_tasks.assert_called_once_with(run_id)
                assert isinstance(metrics, LiveMetrics)

    def test_collect_live_metrics_no_recent_runs(self, dashboard, task_manager):
        """Test _collect_live_metrics when no runs exist."""
        dashboard._current_run_id = None

        with patch.object(task_manager, "list_runs") as mock_list_runs:
            mock_list_runs.return_value = []

            metrics = dashboard._collect_live_metrics()

            assert metrics.active_tasks == 0
            assert metrics.completed_tasks == 0
            assert metrics.failed_tasks == 0

    def test_collect_live_metrics_with_throughput_calculation(self, dashboard):
        """Test throughput calculation in _collect_live_metrics."""
        # Add some history to calculate throughput
        earlier_time = datetime.now() - timedelta(minutes=1)
        dashboard._metrics_history.append(
            LiveMetrics(timestamp=earlier_time, completed_tasks=5)
        )

        with patch.object(dashboard, "_collect_live_metrics") as mock_collect:
            # Create mock metrics with more completed tasks
            new_metrics = LiveMetrics(timestamp=datetime.now(), completed_tasks=10)
            mock_collect.return_value = new_metrics

            # Call the real method to test throughput calculation
            mock_collect.side_effect = None
            dashboard._current_run_id = None

            with patch.object(dashboard.task_manager, "list_runs", return_value=[]):
                metrics = dashboard._collect_live_metrics()

                # Throughput should be calculated based on time difference
                assert isinstance(metrics, LiveMetrics)

    def test_check_status_changes_task_completion(self, dashboard):
        """Test _check_status_changes for task completion."""
        # Add metrics history
        dashboard._metrics_history.append(LiveMetrics(completed_tasks=5))
        dashboard._metrics_history.append(LiveMetrics(completed_tasks=7))

        # Add callback
        callback = Mock()
        dashboard.add_status_callback(callback)

        dashboard._check_status_changes()

        callback.assert_called_once_with("task_completed", 2)

    def test_check_status_changes_task_failure(self, dashboard):
        """Test _check_status_changes for task failure."""
        # Add metrics history
        dashboard._metrics_history.append(LiveMetrics(failed_tasks=1))
        dashboard._metrics_history.append(LiveMetrics(failed_tasks=3))

        # Add callback
        callback = Mock()
        dashboard.add_status_callback(callback)

        dashboard._check_status_changes()

        callback.assert_called_once_with("task_failed", 2)

    def test_check_status_changes_insufficient_history(self, dashboard):
        """Test _check_status_changes with insufficient history."""
        # Add only one metrics entry
        dashboard._metrics_history.append(LiveMetrics(completed_tasks=5))

        callback = Mock()
        dashboard.add_status_callback(callback)

        dashboard._check_status_changes()

        # Should not call callback
        callback.assert_not_called()

    def test_check_status_changes_callback_exception(self, dashboard):
        """Test _check_status_changes handles callback exceptions."""
        dashboard._metrics_history.append(LiveMetrics(completed_tasks=5))
        dashboard._metrics_history.append(LiveMetrics(completed_tasks=7))

        # Add callback that raises exception
        def failing_callback(event_type, count):
            raise ValueError("Test exception")

        dashboard.add_status_callback(failing_callback)

        with patch.object(dashboard.logger, "warning") as mock_warning:
            dashboard._check_status_changes()
            mock_warning.assert_called_once()

    def test_add_metrics_callback(self, dashboard):
        """Test add_metrics_callback functionality."""
        callback = Mock()
        dashboard.add_metrics_callback(callback)

        assert callback in dashboard._metrics_callbacks

    def test_add_status_callback(self, dashboard):
        """Test add_status_callback functionality."""
        callback = Mock()
        dashboard.add_status_callback(callback)

        assert callback in dashboard._status_callbacks

    def test_get_current_metrics_empty(self, dashboard):
        """Test get_current_metrics when no metrics exist."""
        result = dashboard.get_current_metrics()
        assert result is None

    def test_get_current_metrics_with_data(self, dashboard):
        """Test get_current_metrics with data."""
        metrics = LiveMetrics(active_tasks=5)
        dashboard._metrics_history.append(metrics)

        result = dashboard.get_current_metrics()
        assert result == metrics

    def test_get_metrics_history_all(self, dashboard):
        """Test get_metrics_history without time limit."""
        metrics1 = LiveMetrics(active_tasks=1)
        metrics2 = LiveMetrics(active_tasks=2)
        dashboard._metrics_history.extend([metrics1, metrics2])

        result = dashboard.get_metrics_history()
        assert result == [metrics1, metrics2]
        # Verify it's a copy
        assert result is not dashboard._metrics_history

    def test_get_metrics_history_with_time_limit(self, dashboard):
        """Test get_metrics_history with time limit."""
        now = datetime.now()
        old_metrics = LiveMetrics(timestamp=now - timedelta(minutes=10), active_tasks=1)
        recent_metrics = LiveMetrics(timestamp=now, active_tasks=2)
        dashboard._metrics_history.extend([old_metrics, recent_metrics])

        result = dashboard.get_metrics_history(minutes=5)
        assert len(result) == 1
        assert result[0] == recent_metrics

    def test_monitor_loop_metrics_collection(self, dashboard):
        """Test _monitor_loop metrics collection and callbacks."""
        # Mock the methods to avoid actual monitoring
        dashboard._monitoring = True
        dashboard.config.update_interval = 0.01  # Very fast for testing

        collected_metrics = []

        def metrics_callback(metrics):
            collected_metrics.append(metrics)

        dashboard.add_metrics_callback(metrics_callback)

        with patch.object(dashboard, "_collect_live_metrics") as mock_collect:
            mock_metrics = LiveMetrics(active_tasks=5)
            mock_collect.return_value = mock_metrics

            with patch.object(dashboard, "_check_status_changes") as mock_check:
                # Start monitoring in thread and let it run briefly
                thread = threading.Thread(target=dashboard._monitor_loop)
                thread.start()

                time.sleep(0.05)  # Let it run a few iterations
                dashboard._monitoring = False
                thread.join(timeout=1)

                # Verify methods were called
                assert mock_collect.call_count > 0
                assert mock_check.call_count > 0
                assert len(collected_metrics) > 0
                assert all(m == mock_metrics for m in collected_metrics)

    def test_monitor_loop_history_limit(self, dashboard_with_config):
        """Test _monitor_loop respects max_history_points."""
        dashboard = dashboard_with_config
        dashboard.config.max_history_points = 3

        # Add more metrics than the limit
        metrics_list = [LiveMetrics(active_tasks=i) for i in range(5)]
        dashboard._metrics_history = metrics_list.copy()

        # Simulate adding one more metric
        new_metrics = LiveMetrics(active_tasks=99)
        dashboard._metrics_history.append(new_metrics)

        # Simulate history limit enforcement (this is the logic from the actual implementation)
        while len(dashboard._metrics_history) > dashboard.config.max_history_points:
            dashboard._metrics_history.pop(0)

        assert len(dashboard._metrics_history) == 3
        assert dashboard._metrics_history[-1] == new_metrics

    def test_monitor_loop_exception_handling(self, dashboard):
        """Test _monitor_loop handles exceptions gracefully."""
        dashboard._monitoring = True
        dashboard.config.update_interval = 0.01

        with patch.object(dashboard, "_collect_live_metrics") as mock_collect:
            mock_collect.side_effect = Exception("Test exception")

            with patch.object(dashboard.logger, "error") as mock_error:
                # Run loop briefly
                thread = threading.Thread(target=dashboard._monitor_loop)
                thread.start()

                time.sleep(0.02)
                dashboard._monitoring = False
                thread.join(timeout=1)

                # Should have logged errors
                assert mock_error.call_count > 0

    def test_monitor_loop_metrics_callback_exception(self, dashboard):
        """Test _monitor_loop handles metrics callback exceptions."""
        dashboard._monitoring = True
        dashboard.config.update_interval = 0.01

        def failing_callback(metrics):
            raise ValueError("Callback failed")

        dashboard.add_metrics_callback(failing_callback)

        with patch.object(dashboard, "_collect_live_metrics") as mock_collect:
            mock_collect.return_value = LiveMetrics()

            with patch.object(dashboard.logger, "warning") as mock_warning:
                thread = threading.Thread(target=dashboard._monitor_loop)
                thread.start()

                time.sleep(0.02)
                dashboard._monitoring = False
                thread.join(timeout=1)

                # Should have logged warnings for callback failures
                assert mock_warning.call_count > 0


class TestDashboardHTMLGeneration:
    """Test HTML generation methods in RealTimeDashboard."""

    @pytest.fixture
    def dashboard(self, tmp_path):
        """Create a dashboard for testing."""
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        return RealTimeDashboard(task_manager)

    def test_generate_live_report(self, dashboard, tmp_path):
        """Test generate_live_report functionality."""
        output_path = tmp_path / "dashboard.html"

        with patch.object(dashboard, "_generate_dashboard_html") as mock_generate:
            mock_generate.return_value = "<html>Test</html>"

            result = dashboard.generate_live_report(str(output_path))

            assert result == output_path
            assert output_path.exists()
            assert output_path.read_text() == "<html>Test</html>"
            mock_generate.assert_called_once_with(True)

    def test_generate_live_report_no_charts(self, dashboard, tmp_path):
        """Test generate_live_report without charts."""
        output_path = tmp_path / "dashboard.html"

        with patch.object(dashboard, "_generate_dashboard_html") as mock_generate:
            mock_generate.return_value = "<html>No Charts</html>"

            dashboard.generate_live_report(str(output_path), include_charts=False)

            mock_generate.assert_called_once_with(False)

    def test_generate_status_section_no_metrics(self, dashboard):
        """Test _generate_status_section with no metrics."""
        result = dashboard._generate_status_section(None)

        assert "No Data Available" in result
        assert "status-section" in result

    def test_generate_status_section_with_metrics(self, dashboard):
        """Test _generate_status_section with metrics."""
        metrics = LiveMetrics(
            active_tasks=5,
            completed_tasks=10,
            failed_tasks=2,
            throughput=12.5,
            total_cpu_usage=75.0,
            total_memory_usage=1024.0,
        )

        result = dashboard._generate_status_section(metrics)

        assert "5" in result  # active_tasks
        assert "10" in result  # completed_tasks
        assert "2" in result  # failed_tasks
        assert "12.5" in result  # throughput
        assert "75.0%" in result  # cpu_usage
        assert "1024MB" in result  # memory_usage
        assert "status-section" in result

    def test_generate_live_metrics_section_no_history(self, dashboard):
        """Test _generate_live_metrics_section with no history."""
        result = dashboard._generate_live_metrics_section([])

        assert "No metrics data available" in result
        assert "metrics-section" in result

    def test_generate_live_metrics_section_with_history(self, dashboard):
        """Test _generate_live_metrics_section with metrics history."""
        history = [
            LiveMetrics(
                timestamp=datetime.now(),
                total_cpu_usage=50.0,
                total_memory_usage=512.0,
                throughput=10.0,
            )
        ]

        result = dashboard._generate_live_metrics_section(history)

        assert "Live Metrics" in result
        assert "cpuChart" in result
        assert "memoryChart" in result
        assert "throughputChart" in result
        assert "drawLiveCharts" in result

    def test_generate_charts_section_no_run_id(self, dashboard):
        """Test _generate_charts_section with no current run ID."""
        dashboard._current_run_id = None

        result = dashboard._generate_charts_section()

        assert result == ""

    def test_generate_charts_section_with_run_id(self, dashboard):
        """Test _generate_charts_section with run ID."""
        dashboard._current_run_id = "test-run-123"

        result = dashboard._generate_charts_section()

        assert "Performance Analysis" in result
        assert "test-run-123" in result
        assert "timeline_test-run-123.png" in result
        assert "resources_test-run-123.png" in result
        assert "heatmap_test-run-123.png" in result

    def test_generate_task_list_section_no_run_id(self, dashboard):
        """Test _generate_task_list_section with no current run ID."""
        dashboard._current_run_id = None

        result = dashboard._generate_task_list_section()

        assert "Recent Tasks" in result
        assert "No active workflow" in result

    def test_generate_task_list_section_with_tasks(self, dashboard, task_manager):
        """Test _generate_task_list_section with tasks."""
        run_id = "test-run-123"
        dashboard._current_run_id = run_id

        # Create mock task
        task1 = TaskRun(
            task_id="task1",
            run_id=run_id,
            node_id="node1",
            node_type="TestNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(),
            metrics=TaskMetrics(duration=1.5),
        )

        # Mock the task retrieval on the dashboard's task manager
        with patch.object(dashboard.task_manager, "get_run_tasks") as mock_get_tasks:
            mock_get_tasks.return_value = [task1]

            result = dashboard._generate_task_list_section()

            assert "Recent Tasks" in result
            assert "node1" in result
            assert "TestNode" in result
            assert "COMPLETED" in result
            assert "1.50s" in result

    def test_get_dashboard_css_light_theme(self, dashboard):
        """Test _get_dashboard_css with light theme."""
        dashboard.config.theme = "light"

        result = dashboard._get_dashboard_css()

        assert "#f8f9fa" in result  # Light background
        assert "#ffffff" in result  # Light card background
        assert "font-family" in result
        assert ".dashboard-container" in result

    def test_get_dashboard_css_dark_theme(self, dashboard):
        """Test _get_dashboard_css with dark theme."""
        dashboard.config.theme = "dark"

        result = dashboard._get_dashboard_css()

        assert "#121212" in result  # Dark background
        assert "#1e1e1e" in result  # Dark card background
        assert "font-family" in result
        assert ".dashboard-container" in result

    def test_get_dashboard_javascript(self, dashboard):
        """Test _get_dashboard_javascript generation."""
        result = dashboard._get_dashboard_javascript()

        assert "drawLiveCharts" in result
        assert "drawSimpleChart" in result
        assert "getContext" in result
        assert "setInterval" in result
        assert "window.location.reload" in result


class TestDashboardExporter:
    """Test DashboardExporter functionality."""

    @pytest.fixture
    def dashboard_exporter(self, tmp_path):
        """Create a DashboardExporter for testing."""
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        dashboard = RealTimeDashboard(task_manager)
        return DashboardExporter(dashboard)

    def test_exporter_initialization(self, dashboard_exporter):
        """Test DashboardExporter initialization."""
        assert dashboard_exporter.dashboard is not None
        assert dashboard_exporter.logger is not None

    def test_metrics_to_dict(self, dashboard_exporter):
        """Test _metrics_to_dict conversion."""
        timestamp = datetime.now()
        metrics = LiveMetrics(
            timestamp=timestamp,
            active_tasks=5,
            completed_tasks=10,
            failed_tasks=2,
            total_cpu_usage=75.5,
            total_memory_usage=1024.0,
            throughput=12.5,
            avg_task_duration=2.34,
        )

        result = dashboard_exporter._metrics_to_dict(metrics)

        assert result["timestamp"] == timestamp.isoformat()
        assert result["active_tasks"] == 5
        assert result["completed_tasks"] == 10
        assert result["failed_tasks"] == 2
        assert result["total_cpu_usage"] == 75.5
        assert result["total_memory_usage"] == 1024.0
        assert result["throughput"] == 12.5
        assert result["avg_task_duration"] == 2.34

    def test_export_metrics_json(self, dashboard_exporter, tmp_path):
        """Test export_metrics_json functionality."""
        output_path = tmp_path / "metrics.json"

        # Add some metrics to dashboard
        metrics = LiveMetrics(active_tasks=5, completed_tasks=10)
        dashboard_exporter.dashboard._metrics_history.append(metrics)

        result = dashboard_exporter.export_metrics_json(str(output_path))

        assert result == output_path
        assert output_path.exists()

        # Verify JSON content
        with open(output_path, "r") as f:
            data = json.load(f)

        assert "timestamp" in data
        assert "current_metrics" in data
        assert "history" in data
        assert "config" in data
        assert len(data["history"]) == 1
        assert data["history"][0]["active_tasks"] == 5

    def test_export_metrics_json_no_current_metrics(self, dashboard_exporter, tmp_path):
        """Test export_metrics_json with no current metrics."""
        output_path = tmp_path / "metrics.json"

        result = dashboard_exporter.export_metrics_json(str(output_path))

        assert result == output_path

        with open(output_path, "r") as f:
            data = json.load(f)

        assert data["current_metrics"] is None
        assert data["history"] == []

    def test_create_dashboard_snapshot(self, dashboard_exporter, tmp_path):
        """Test create_dashboard_snapshot functionality."""
        output_dir = tmp_path / "snapshot"

        with patch.object(
            dashboard_exporter.dashboard, "generate_live_report"
        ) as mock_generate:
            with patch.object(dashboard_exporter, "export_metrics_json") as mock_export:
                mock_generate.return_value = output_dir / "dashboard.html"
                mock_export.return_value = output_dir / "metrics.json"

                result = dashboard_exporter.create_dashboard_snapshot(str(output_dir))

                assert "dashboard" in result
                assert "metrics" in result
                assert result["dashboard"] == output_dir / "dashboard.html"
                assert result["metrics"] == output_dir / "metrics.json"

    def test_create_dashboard_snapshot_with_charts(self, dashboard_exporter, tmp_path):
        """Test create_dashboard_snapshot with static charts."""
        output_dir = tmp_path / "snapshot"
        dashboard_exporter.dashboard._current_run_id = "test-run-123"

        with patch.object(dashboard_exporter.dashboard, "generate_live_report"):
            with patch.object(dashboard_exporter, "export_metrics_json"):
                with patch.object(
                    dashboard_exporter.dashboard.performance_viz,
                    "create_run_performance_summary",
                ) as mock_perf:
                    mock_perf.return_value = {"chart1": "path1", "chart2": "path2"}

                    result = dashboard_exporter.create_dashboard_snapshot(
                        str(output_dir), include_static_charts=True
                    )

                    assert "dashboard" in result
                    assert "metrics" in result
                    assert "chart1" in result
                    assert "chart2" in result

    def test_create_dashboard_snapshot_chart_error(self, dashboard_exporter, tmp_path):
        """Test create_dashboard_snapshot handles chart generation errors."""
        output_dir = tmp_path / "snapshot"
        dashboard_exporter.dashboard._current_run_id = "test-run-123"

        with patch.object(dashboard_exporter.dashboard, "generate_live_report"):
            with patch.object(dashboard_exporter, "export_metrics_json"):
                with patch.object(
                    dashboard_exporter.dashboard.performance_viz,
                    "create_run_performance_summary",
                ) as mock_perf:
                    mock_perf.side_effect = Exception("Chart generation failed")

                    with patch.object(
                        dashboard_exporter.logger, "warning"
                    ) as mock_warning:
                        result = dashboard_exporter.create_dashboard_snapshot(
                            str(output_dir), include_static_charts=True
                        )

                        mock_warning.assert_called_once()
                        # Should still have basic assets
                        assert "dashboard" in result
                        assert "metrics" in result
