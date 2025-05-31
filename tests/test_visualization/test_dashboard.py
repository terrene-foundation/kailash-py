"""Tests for dashboard visualization components."""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskMetrics, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.dashboard import (
    DashboardConfig,
    DashboardExporter,
    LiveMetrics,
    RealTimeDashboard,
)


class TestDashboardConfig:
    """Test dashboard configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DashboardConfig()

        assert config.update_interval == 1.0
        assert config.max_history_points == 100
        assert config.auto_refresh is True
        assert config.show_completed is True
        assert config.show_failed is True
        assert config.theme == "light"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DashboardConfig(
            update_interval=0.5, max_history_points=50, auto_refresh=False, theme="dark"
        )

        assert config.update_interval == 0.5
        assert config.max_history_points == 50
        assert config.auto_refresh is False
        assert config.theme == "dark"


class TestLiveMetrics:
    """Test live metrics data structure."""

    def test_default_metrics(self):
        """Test default metrics initialization."""
        metrics = LiveMetrics()

        assert isinstance(metrics.timestamp, datetime)
        assert metrics.active_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.total_cpu_usage == 0.0
        assert metrics.total_memory_usage == 0.0
        assert metrics.throughput == 0.0
        assert metrics.avg_task_duration == 0.0

    def test_custom_metrics(self):
        """Test custom metrics values."""
        timestamp = datetime.now()
        metrics = LiveMetrics(
            timestamp=timestamp,
            active_tasks=3,
            completed_tasks=5,
            failed_tasks=1,
            total_cpu_usage=45.2,
            total_memory_usage=128.7,
            throughput=1.5,
            avg_task_duration=2.3,
        )

        assert metrics.timestamp == timestamp
        assert metrics.active_tasks == 3
        assert metrics.completed_tasks == 5
        assert metrics.failed_tasks == 1
        assert metrics.total_cpu_usage == 45.2
        assert metrics.total_memory_usage == 128.7
        assert metrics.throughput == 1.5
        assert metrics.avg_task_duration == 2.3


class TestRealTimeDashboard:
    """Test real-time dashboard functionality."""

    @pytest.fixture
    def task_manager(self, tmp_path):
        """Create a test task manager."""
        storage = FileSystemStorage(tmp_path / "test_storage")
        return TaskManager(storage)

    @pytest.fixture
    def dashboard_config(self):
        """Create test dashboard configuration."""
        return DashboardConfig(
            update_interval=0.1,  # Fast updates for testing
            max_history_points=10,
            auto_refresh=True,
            theme="light",
        )

    @pytest.fixture
    def dashboard(self, task_manager, dashboard_config):
        """Create test dashboard."""
        return RealTimeDashboard(task_manager, dashboard_config)

    def test_dashboard_initialization(self, task_manager, dashboard_config):
        """Test dashboard initialization."""
        dashboard = RealTimeDashboard(task_manager, dashboard_config)

        assert dashboard.task_manager == task_manager
        assert dashboard.config == dashboard_config
        assert dashboard._monitoring is False
        assert dashboard._current_run_id is None
        assert len(dashboard._metrics_history) == 0
        assert len(dashboard._status_callbacks) == 0
        assert len(dashboard._metrics_callbacks) == 0

    def test_start_stop_monitoring(self, dashboard):
        """Test starting and stopping monitoring."""
        # Test starting monitoring
        dashboard.start_monitoring("test-run-id")

        assert dashboard._monitoring is True
        assert dashboard._current_run_id == "test-run-id"
        assert dashboard._monitor_thread is not None
        assert dashboard._monitor_thread.is_alive()

        # Test stopping monitoring
        dashboard.stop_monitoring()

        assert dashboard._monitoring is False

        # Wait for thread to stop
        time.sleep(0.2)
        assert not dashboard._monitor_thread.is_alive()

    def test_monitoring_without_run_id(self, dashboard):
        """Test monitoring without specific run ID."""
        dashboard.start_monitoring()

        assert dashboard._monitoring is True
        assert dashboard._current_run_id is None

        dashboard.stop_monitoring()
        assert dashboard._monitoring is False

    def test_callbacks(self, dashboard):
        """Test callback registration and execution."""
        metrics_called = []
        status_called = []

        def metrics_callback(metrics):
            metrics_called.append(metrics)

        def status_callback(event_type, count):
            status_called.append((event_type, count))

        # Register callbacks
        dashboard.add_metrics_callback(metrics_callback)
        dashboard.add_status_callback(status_callback)

        assert len(dashboard._metrics_callbacks) == 1
        assert len(dashboard._status_callbacks) == 1

        # Test callback execution (manual trigger)
        test_metrics = LiveMetrics(completed_tasks=1)
        dashboard._metrics_history = [test_metrics]

        # Manually trigger callbacks
        for callback in dashboard._metrics_callbacks:
            callback(test_metrics)

        for callback in dashboard._status_callbacks:
            callback("task_completed", 1)

        assert len(metrics_called) == 1
        assert len(status_called) == 1
        assert status_called[0] == ("task_completed", 1)

    def test_metrics_history_management(self, dashboard):
        """Test metrics history management."""
        # Add metrics to exceed max_history_points
        for i in range(15):
            metrics = LiveMetrics(completed_tasks=i)
            dashboard._metrics_history.append(metrics)

        # Simulate history trimming
        while len(dashboard._metrics_history) > dashboard.config.max_history_points:
            dashboard._metrics_history.pop(0)

        assert len(dashboard._metrics_history) == dashboard.config.max_history_points
        assert (
            dashboard._metrics_history[0].completed_tasks == 5
        )  # First 5 were removed

    def test_get_current_metrics(self, dashboard):
        """Test getting current metrics."""
        # No metrics yet
        assert dashboard.get_current_metrics() is None

        # Add metrics
        test_metrics = LiveMetrics(completed_tasks=5)
        dashboard._metrics_history.append(test_metrics)

        current = dashboard.get_current_metrics()
        assert current is not None
        assert current.completed_tasks == 5

    def test_get_metrics_history(self, dashboard):
        """Test getting metrics history."""
        # Add test metrics with different timestamps
        base_time = datetime.now()
        for i in range(5):
            metrics = LiveMetrics(
                timestamp=base_time - timedelta(minutes=i), completed_tasks=i
            )
            dashboard._metrics_history.append(metrics)

        # Get all history
        all_history = dashboard.get_metrics_history()
        assert len(all_history) == 5

        # Get limited history
        recent_history = dashboard.get_metrics_history(minutes=2)
        assert len(recent_history) <= 3  # Only recent metrics

    def test_collect_live_metrics_no_data(self, dashboard):
        """Test collecting metrics with no data."""
        metrics = dashboard._collect_live_metrics()

        assert isinstance(metrics, LiveMetrics)
        assert metrics.active_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0

    @patch.object(TaskManager, "get_run_tasks")
    @patch.object(TaskManager, "list_runs")
    def test_collect_live_metrics_with_data(
        self, mock_list_runs, mock_get_tasks, dashboard
    ):
        """Test collecting metrics with actual task data."""
        # Mock run data
        mock_run = Mock()
        mock_run.run_id = "test-run"
        mock_list_runs.return_value = [mock_run]

        # Mock task data
        completed_task = Mock()
        completed_task.status = TaskStatus.COMPLETED
        completed_task.metrics = TaskMetrics(
            duration=2.5, cpu_usage=45.0, memory_usage_mb=128.0
        )

        running_task = Mock()
        running_task.status = TaskStatus.RUNNING
        running_task.metrics = None

        failed_task = Mock()
        failed_task.status = TaskStatus.FAILED
        failed_task.metrics = None

        mock_get_tasks.return_value = [completed_task, running_task, failed_task]

        # Test metrics collection
        metrics = dashboard._collect_live_metrics()

        assert metrics.completed_tasks == 1
        assert metrics.active_tasks == 1
        assert metrics.failed_tasks == 1
        assert metrics.total_cpu_usage == 45.0
        assert metrics.total_memory_usage == 128.0
        assert metrics.avg_task_duration == 2.5

    def test_generate_live_report(self, dashboard, tmp_path):
        """Test live report generation."""
        # Add some test metrics
        test_metrics = LiveMetrics(
            completed_tasks=3, total_cpu_usage=30.0, total_memory_usage=256.0
        )
        dashboard._metrics_history.append(test_metrics)

        # Generate report
        output_path = tmp_path / "test_dashboard.html"
        result_path = dashboard.generate_live_report(output_path, include_charts=False)

        assert result_path == output_path
        assert output_path.exists()

        # Check content
        content = output_path.read_text()
        assert "Real-time Workflow Dashboard" in content
        assert "3" in content  # Completed tasks
        assert "30.0%" in content  # CPU usage

    def test_generate_status_section(self, dashboard):
        """Test status section generation."""
        # Test with no metrics
        section = dashboard._generate_status_section(None)
        assert "No Data Available" in section

        # Test with metrics
        metrics = LiveMetrics(
            active_tasks=2,
            completed_tasks=5,
            failed_tasks=1,
            throughput=1.5,
            total_cpu_usage=45.0,
            total_memory_usage=200.0,
        )

        section = dashboard._generate_status_section(metrics)
        assert "2" in section  # Active tasks
        assert "5" in section  # Completed tasks
        assert "1" in section  # Failed tasks
        assert "1.5" in section  # Throughput
        assert "45.0%" in section  # CPU
        assert "200MB" in section  # Memory


class TestDashboardExporter:
    """Test dashboard exporter functionality."""

    @pytest.fixture
    def dashboard(self, tmp_path):
        """Create test dashboard with data."""
        storage = FileSystemStorage(tmp_path / "test_storage")
        task_manager = TaskManager(storage)
        dashboard = RealTimeDashboard(task_manager)

        # Add test metrics
        test_metrics = LiveMetrics(
            completed_tasks=5,
            total_cpu_usage=35.0,
            total_memory_usage=180.0,
            throughput=2.0,
        )
        dashboard._metrics_history = [test_metrics]

        return dashboard

    @pytest.fixture
    def exporter(self, dashboard):
        """Create test exporter."""
        return DashboardExporter(dashboard)

    def test_export_metrics_json(self, exporter, tmp_path):
        """Test JSON metrics export."""
        output_path = tmp_path / "test_metrics.json"
        result_path = exporter.export_metrics_json(output_path)

        assert result_path == output_path
        assert output_path.exists()

        # Check JSON content
        with open(output_path) as f:
            data = json.load(f)

        assert "timestamp" in data
        assert "current_metrics" in data
        assert "history" in data
        assert "config" in data

        assert len(data["history"]) == 1
        assert data["history"][0]["completed_tasks"] == 5

    def test_metrics_to_dict(self, exporter):
        """Test metrics to dictionary conversion."""
        metrics = LiveMetrics(active_tasks=3, completed_tasks=7, total_cpu_usage=40.0)

        result = exporter._metrics_to_dict(metrics)

        assert result["active_tasks"] == 3
        assert result["completed_tasks"] == 7
        assert result["total_cpu_usage"] == 40.0
        assert "timestamp" in result

    def test_create_dashboard_snapshot(self, exporter, tmp_path):
        """Test dashboard snapshot creation."""
        output_dir = tmp_path / "snapshot"

        assets = exporter.create_dashboard_snapshot(
            output_dir=output_dir,
            include_static_charts=False,  # Skip charts for testing
        )

        assert "dashboard" in assets
        assert "metrics" in assets

        # Check files exist
        assert assets["dashboard"].exists()
        assert assets["metrics"].exists()

        # Check dashboard HTML
        dashboard_content = assets["dashboard"].read_text()
        assert "Real-time Workflow Dashboard" in dashboard_content


class TestDashboardIntegration:
    """Integration tests for dashboard components."""

    @pytest.fixture
    def setup_integration_test(self, tmp_path):
        """Set up integration test environment."""
        # Create task manager with real data
        storage = FileSystemStorage(tmp_path / "integration_storage")
        task_manager = TaskManager(storage)

        # Create and start a workflow run
        run_id = task_manager.create_run("test_workflow", {})

        # Add some test tasks
        task_ids = []
        for i in range(3):
            task = task_manager.create_task(
                node_id=f"test_node_{i}", run_id=run_id, node_type="TestNode"
            )
            task_id = task.task_id
            task_ids.append(task_id)

        # Complete tasks with metrics
        for i, task_id in enumerate(task_ids):
            metrics = TaskMetrics(
                duration=float(i + 1),
                cpu_usage=30.0 + i * 10,
                memory_usage_mb=100.0 + i * 50,
            )

            if i < 2:  # Complete first two tasks
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.complete_task(task_id, {"result": f"result_{i}"})
            else:  # Fail the last task
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.fail_task(task_id, "Test error")

        return task_manager, run_id

    def test_full_dashboard_workflow(self, setup_integration_test, tmp_path):
        """Test complete dashboard workflow."""
        task_manager, run_id = setup_integration_test

        # Create dashboard
        config = DashboardConfig(update_interval=0.1, max_history_points=20)
        dashboard = RealTimeDashboard(task_manager, config)

        # Start monitoring
        dashboard.start_monitoring(run_id)

        # Allow monitoring to collect data
        time.sleep(0.3)

        # Check metrics collection
        current_metrics = dashboard.get_current_metrics()
        assert current_metrics is not None
        assert current_metrics.completed_tasks == 2
        assert current_metrics.failed_tasks == 1

        # Generate dashboard
        dashboard_path = tmp_path / "integration_dashboard.html"
        dashboard.generate_live_report(dashboard_path)

        assert dashboard_path.exists()
        content = dashboard_path.read_text()
        assert "2" in content  # Completed tasks
        assert "1" in content  # Failed tasks

        # Stop monitoring
        dashboard.stop_monitoring()

        # Test exporter
        exporter = DashboardExporter(dashboard)
        snapshot_assets = exporter.create_dashboard_snapshot(
            tmp_path / "snapshot", include_static_charts=False
        )

        assert len(snapshot_assets) >= 2  # At least dashboard and metrics

        # Check JSON export
        metrics_data = json.loads(snapshot_assets["metrics"].read_text())
        assert metrics_data["current_metrics"]["completed_tasks"] == 2
        assert metrics_data["current_metrics"]["failed_tasks"] == 1

    def test_monitoring_lifecycle(self, setup_integration_test):
        """Test complete monitoring lifecycle."""
        task_manager, run_id = setup_integration_test

        dashboard = RealTimeDashboard(task_manager)

        # Test monitoring states
        assert not dashboard._monitoring

        dashboard.start_monitoring(run_id)
        assert dashboard._monitoring
        assert dashboard._current_run_id == run_id

        # Collect some metrics
        time.sleep(0.2)

        # Check metrics history
        history = dashboard.get_metrics_history()
        assert len(history) > 0

        # Test double start (should warn but not crash)
        dashboard.start_monitoring(run_id)  # Should log warning
        assert dashboard._monitoring  # Still monitoring

        # Stop monitoring
        dashboard.stop_monitoring()
        assert not dashboard._monitoring

        # Test double stop (should not crash)
        dashboard.stop_monitoring()  # Should handle gracefully
        assert not dashboard._monitoring

    def test_callback_integration(self, setup_integration_test):
        """Test callback integration with real data."""
        task_manager, run_id = setup_integration_test

        dashboard = RealTimeDashboard(task_manager)

        # Track callback calls
        metrics_updates = []
        status_events = []

        def metrics_callback(metrics):
            metrics_updates.append(metrics)

        def status_callback(event_type, count):
            status_events.append((event_type, count))

        dashboard.add_metrics_callback(metrics_callback)
        dashboard.add_status_callback(status_callback)

        # Start monitoring
        dashboard.start_monitoring(run_id)

        # Let it collect some data
        time.sleep(0.3)

        dashboard.stop_monitoring()

        # Check callbacks were called
        assert len(metrics_updates) > 0

        # Verify metrics data
        latest_metrics = metrics_updates[-1]
        assert latest_metrics.completed_tasks >= 0
        assert latest_metrics.failed_tasks >= 0
