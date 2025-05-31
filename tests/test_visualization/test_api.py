"""Tests for dashboard API components."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.api import SimpleDashboardAPI
from kailash.visualization.dashboard import DashboardConfig

# Test FastAPI components only if available
try:
    from kailash.visualization.api import DashboardAPIServer

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TestSimpleDashboardAPI:
    """Test simple dashboard API functionality."""

    @pytest.fixture
    def task_manager_with_data(self, tmp_path):
        """Create task manager with test data."""
        storage = FileSystemStorage(tmp_path / "api_test_storage")
        task_manager = TaskManager(storage)

        # Create test runs
        run_ids = []
        for run_idx in range(3):
            run_id = task_manager.create_run(f"test_workflow_{run_idx}", {})
            run_ids.append(run_id)

            # Add tasks to each run
            for task_idx in range(2 + run_idx):
                task = task_manager.create_task(
                    node_id=f"node_{task_idx}", run_id=run_id, node_type="TestNode"
                )
                task_id = task.task_id

                metrics = TaskMetrics(
                    duration=1.0 + task_idx * 0.5,
                    cpu_usage=20.0 + task_idx * 10,
                    memory_usage_mb=100.0 + task_idx * 50,
                )

                if task_idx == 0 or run_idx < 2:  # Complete most tasks
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.complete_task(
                        task_id, {"result": f"result_{task_idx}"}
                    )
                else:  # Fail some tasks
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.fail_task(task_id, "Test error")

        return task_manager, run_ids

    @pytest.fixture
    def api(self, task_manager_with_data):
        """Create simple dashboard API."""
        task_manager, run_ids = task_manager_with_data
        config = DashboardConfig(update_interval=0.1)  # Fast updates for testing
        return SimpleDashboardAPI(task_manager, config), run_ids

    def test_api_initialization(self, task_manager_with_data):
        """Test API initialization."""
        task_manager, _ = task_manager_with_data

        # Test with default config
        api = SimpleDashboardAPI(task_manager)
        assert api.task_manager == task_manager
        assert isinstance(api.dashboard_config, DashboardConfig)
        assert api.dashboard.task_manager == task_manager

        # Test with custom config
        custom_config = DashboardConfig(theme="dark", update_interval=0.5)
        api = SimpleDashboardAPI(task_manager, custom_config)
        assert api.dashboard_config == custom_config
        assert api.dashboard.config == custom_config

    def test_get_runs(self, api):
        """Test getting list of runs."""
        api_instance, run_ids = api

        # Get all runs
        runs = api_instance.get_runs()
        assert len(runs) == 3

        # Check run data structure
        for run in runs:
            assert "run_id" in run
            assert "workflow_name" in run
            assert "status" in run
            assert "started_at" in run
            assert "total_tasks" in run
            assert "completed_tasks" in run
            assert "failed_tasks" in run

        # Test with limit
        limited_runs = api_instance.get_runs(limit=2)
        assert len(limited_runs) == 2

        # Test with offset
        offset_runs = api_instance.get_runs(limit=2, offset=1)
        assert len(offset_runs) == 2
        assert offset_runs[0]["run_id"] != runs[0]["run_id"]

    def test_get_run_details(self, api):
        """Test getting run details."""
        api_instance, run_ids = api

        # Get details for existing run
        run_details = api_instance.get_run_details(run_ids[0])
        assert run_details is not None

        # Check detailed structure
        assert "run_id" in run_details
        assert "workflow_name" in run_details
        assert "tasks" in run_details
        assert isinstance(run_details["tasks"], list)

        # Check task details
        if run_details["tasks"]:
            task = run_details["tasks"][0]
            assert "node_id" in task
            assert "node_type" in task
            assert "status" in task
            assert "duration" in task
            assert "cpu_usage" in task
            assert "memory_usage_mb" in task

        # Test with nonexistent run
        nonexistent_details = api_instance.get_run_details("nonexistent-run-id")
        assert nonexistent_details is None

    def test_monitoring_control(self, api):
        """Test monitoring start/stop functionality."""
        api_instance, run_ids = api

        # Test start monitoring
        start_result = api_instance.start_monitoring(run_ids[0])
        assert start_result["status"] == "started"
        assert start_result["run_id"] == run_ids[0]
        assert api_instance.dashboard._monitoring is True

        # Test stop monitoring
        stop_result = api_instance.stop_monitoring()
        assert stop_result["status"] == "stopped"
        assert api_instance.dashboard._monitoring is False

        # Test start without run_id
        start_result = api_instance.start_monitoring()
        assert start_result["status"] == "started"
        assert start_result["run_id"] is None

        api_instance.stop_monitoring()

    def test_current_metrics(self, api):
        """Test getting current metrics."""
        api_instance, run_ids = api

        # No metrics initially
        metrics = api_instance.get_current_metrics()
        assert metrics is None

        # Start monitoring and get metrics
        api_instance.start_monitoring(run_ids[0])

        # Allow some time for metrics collection
        import time

        time.sleep(0.2)

        metrics = api_instance.get_current_metrics()
        if metrics:  # Metrics might be None if no data collected yet
            assert "timestamp" in metrics
            assert "active_tasks" in metrics
            assert "completed_tasks" in metrics
            assert "failed_tasks" in metrics
            assert "total_cpu_usage" in metrics
            assert "total_memory_usage" in metrics
            assert "throughput" in metrics
            assert "avg_task_duration" in metrics

        api_instance.stop_monitoring()

    def test_metrics_history(self, api):
        """Test getting metrics history."""
        api_instance, run_ids = api

        # Start monitoring to collect history
        api_instance.start_monitoring(run_ids[0])

        import time

        time.sleep(0.3)  # Allow time for multiple samples

        # Get history
        history = api_instance.get_metrics_history()
        assert isinstance(history, list)

        # Get limited history
        limited_history = api_instance.get_metrics_history(minutes=1)
        assert isinstance(limited_history, list)
        assert len(limited_history) <= len(history)

        # Check history structure
        for metrics in history:
            assert "timestamp" in metrics
            assert "completed_tasks" in metrics

        api_instance.stop_monitoring()

    def test_report_generation(self, api, tmp_path):
        """Test report generation via API."""
        api_instance, run_ids = api

        # Test HTML report
        html_path = api_instance.generate_report(
            run_id=run_ids[0], format="html", output_path=tmp_path / "api_test.html"
        )
        assert html_path.exists()
        assert html_path.suffix == ".html"

        # Test Markdown report
        md_path = api_instance.generate_report(
            run_id=run_ids[0], format="markdown", output_path=tmp_path / "api_test.md"
        )
        assert md_path.exists()
        assert md_path.suffix == ".md"

        # Test JSON report
        json_path = api_instance.generate_report(
            run_id=run_ids[0], format="json", output_path=tmp_path / "api_test.json"
        )
        assert json_path.exists()
        assert json_path.suffix == ".json"

        # Verify JSON content
        with open(json_path) as f:
            data = json.load(f)
        assert "metadata" in data
        assert "summary" in data

        # Test invalid format
        with pytest.raises(ValueError, match="Invalid format"):
            api_instance.generate_report(run_ids[0], format="invalid")

    def test_dashboard_generation(self, api, tmp_path):
        """Test dashboard generation via API."""
        api_instance, run_ids = api

        # Test default path generation
        dashboard_path = api_instance.generate_dashboard()
        assert dashboard_path.exists()
        assert dashboard_path.suffix == ".html"

        # Test custom path
        custom_path = tmp_path / "custom_dashboard.html"
        result_path = api_instance.generate_dashboard(custom_path)
        assert result_path == custom_path
        assert custom_path.exists()

        # Check content
        content = custom_path.read_text()
        assert "Real-time Workflow Dashboard" in content

    def test_metrics_export(self, api, tmp_path):
        """Test metrics export functionality."""
        api_instance, run_ids = api

        # Start monitoring to generate some metrics
        api_instance.start_monitoring(run_ids[0])

        import time

        time.sleep(0.2)

        # Export metrics
        metrics_path = api_instance.export_metrics_json()
        assert metrics_path.exists()
        assert metrics_path.suffix == ".json"

        # Test custom path
        custom_path = tmp_path / "custom_metrics.json"
        result_path = api_instance.export_metrics_json(custom_path)
        assert result_path == custom_path
        assert custom_path.exists()

        # Verify JSON structure
        with open(custom_path) as f:
            data = json.load(f)
        assert "timestamp" in data
        assert "current_metrics" in data
        assert "history" in data
        assert "config" in data

        api_instance.stop_monitoring()


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestDashboardAPIServer:
    """Test FastAPI dashboard server."""

    @pytest.fixture
    def task_manager_with_data(self, tmp_path):
        """Create task manager with test data."""
        storage = FileSystemStorage(tmp_path / "fastapi_test_storage")
        task_manager = TaskManager(storage)

        # Create a test run
        run_id = task_manager.create_run("fastapi_test_workflow", {})

        # Add test tasks
        for i in range(3):
            task = task_manager.create_task(
                node_id=f"api_node_{i}", run_id=run_id, node_type="APITestNode"
            )
            task_id = task.task_id

            metrics = TaskMetrics(
                duration=1.0 + i * 0.5,
                cpu_usage=25.0 + i * 15,
                memory_usage_mb=80.0 + i * 40,
            )

            if i < 2:
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.complete_task(task_id, {"result": f"api_result_{i}"})
            else:
                task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                task_manager.update_task_metrics(task_id, metrics)
                task_manager.fail_task(task_id, "API test error")

        return task_manager, run_id

    @pytest.fixture
    def api_server(self, task_manager_with_data):
        """Create FastAPI server instance."""
        task_manager, run_id = task_manager_with_data
        config = DashboardConfig(update_interval=0.1)
        return DashboardAPIServer(task_manager, config), run_id

    def test_server_initialization(self, task_manager_with_data):
        """Test API server initialization."""
        task_manager, _ = task_manager_with_data

        server = DashboardAPIServer(task_manager)
        assert server.task_manager == task_manager
        assert isinstance(server.dashboard_config, DashboardConfig)
        assert server.app is not None
        assert len(server._websocket_connections) == 0

    @pytest.mark.asyncio
    async def test_health_endpoint(self, api_server):
        """Test health check endpoint."""
        server, _ = api_server

        # Import test client
        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_list_runs_endpoint(self, api_server):
        """Test list runs endpoint."""
        server, _ = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        response = client.get("/api/v1/runs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Check run structure
        run = data[0]
        assert "run_id" in run
        assert "workflow_name" in run
        assert "status" in run
        assert "total_tasks" in run
        assert "completed_tasks" in run
        assert "failed_tasks" in run

    @pytest.mark.asyncio
    async def test_get_run_endpoint(self, api_server):
        """Test get specific run endpoint."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Test existing run
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == run_id
        assert data["workflow_name"] == "fastapi_test_workflow"

        # Test nonexistent run
        response = client.get("/api/v1/runs/nonexistent-run-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_run_tasks_endpoint(self, api_server):
        """Test get run tasks endpoint."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        response = client.get(f"/api/v1/runs/{run_id}/tasks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3  # We created 3 tasks

        # Check task structure
        task = data[0]
        assert "node_id" in task
        assert "node_type" in task
        assert "status" in task
        assert "duration" in task
        assert "cpu_usage" in task
        assert "memory_usage_mb" in task

    @pytest.mark.asyncio
    async def test_monitoring_endpoints(self, api_server):
        """Test monitoring control endpoints."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Test start monitoring
        response = client.post("/api/v1/monitoring/start", json={"run_id": run_id})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["run_id"] == run_id

        # Test monitoring status
        response = client.get("/api/v1/monitoring/status")
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["monitoring"] is True
        assert status_data["run_id"] == run_id

        # Test stop monitoring
        response = client.post("/api/v1/monitoring/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

        # Verify monitoring stopped
        response = client.get("/api/v1/monitoring/status")
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["monitoring"] is False

    @pytest.mark.asyncio
    async def test_metrics_endpoints(self, api_server):
        """Test metrics endpoints."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Start monitoring first
        client.post("/api/v1/monitoring/start", json={"run_id": run_id})

        # Allow time for metrics collection
        import time

        time.sleep(0.2)

        # Test current metrics
        response = client.get("/api/v1/metrics/current")
        assert response.status_code == 200
        # Data might be None if no metrics collected yet

        # Test metrics history
        response = client.get("/api/v1/metrics/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Test with time parameter
        response = client.get("/api/v1/metrics/history?minutes=5")
        assert response.status_code == 200

        # Stop monitoring
        client.post("/api/v1/monitoring/stop")

    @pytest.mark.asyncio
    async def test_report_generation_endpoint(self, api_server, tmp_path):
        """Test report generation endpoint."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Test report generation
        request_data = {"run_id": run_id, "format": "json", "include_charts": False}

        response = client.post("/api/v1/reports/generate", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "generating"
        assert "filename" in data
        assert "download_url" in data

        # Test invalid format
        invalid_request = {"run_id": run_id, "format": "invalid_format"}

        response = client.post("/api/v1/reports/generate", json=invalid_request)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_live_dashboard_endpoint(self, api_server):
        """Test live dashboard endpoint."""
        server, _ = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        response = client.get("/api/v1/dashboard/live")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    @pytest.mark.asyncio
    async def test_websocket_endpoint(self, api_server):
        """Test WebSocket metrics streaming endpoint."""
        server, run_id = api_server

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Start monitoring
        client.post("/api/v1/monitoring/start", json={"run_id": run_id})

        # Test WebSocket connection
        with client.websocket_connect("/api/v1/metrics/stream") as websocket:
            # Connection should be established
            assert websocket is not None

            # Should be able to send a message (keep-alive)
            websocket.send_text("ping")

            # In a real scenario, we'd receive metrics data
            # For testing, we'll just verify the connection works

        # Stop monitoring
        client.post("/api/v1/monitoring/stop")

    def test_server_startup_without_dependencies(self):
        """Test server behavior when dependencies are missing."""
        # This would be tested in an environment without FastAPI/uvicorn
        # For now, we just test the import error handling

        with patch("kailash.visualization.api.FASTAPI_AVAILABLE", False):
            from kailash.tracking.manager import TaskManager
            from kailash.tracking.storage.filesystem import FileSystemStorage

            storage = FileSystemStorage(Path(tempfile.mkdtemp()))
            task_manager = TaskManager(storage)

            with pytest.raises(ImportError, match="FastAPI is required"):
                from kailash.visualization.api import DashboardAPIServer

                DashboardAPIServer(task_manager)


class TestAPIIntegration:
    """Integration tests for API components."""

    @pytest.fixture
    def full_api_setup(self, tmp_path):
        """Set up complete API testing environment."""
        # Create task manager with comprehensive data
        storage = FileSystemStorage(tmp_path / "integration_storage")
        task_manager = TaskManager(storage)

        # Create multiple workflows
        workflow_data = []
        for workflow_idx in range(2):
            run_id = task_manager.create_run(f"integration_workflow_{workflow_idx}", {})

            # Add tasks with different patterns
            for task_idx in range(4):
                task = task_manager.create_task(
                    node_id=f"task_{task_idx}",
                    run_id=run_id,
                    node_type=f"Type_{task_idx % 2}",
                )
                task_id = task.task_id

                metrics = TaskMetrics(
                    duration=0.5 + task_idx * 0.3,
                    cpu_usage=15.0 + task_idx * 8,
                    memory_usage_mb=60.0 + task_idx * 25,
                    custom_metrics={
                        "io_read_bytes": 1000 * (task_idx + 1),
                        "io_write_bytes": 500 * (task_idx + 1),
                    },
                )

                if task_idx < 3:  # Complete most tasks
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.complete_task(
                        task_id, {"result": f"result_{task_idx}"}
                    )
                else:  # Fail last task
                    task_manager.update_task_status(task_id, TaskStatus.RUNNING)
                    task_manager.update_task_metrics(task_id, metrics)
                    task_manager.fail_task(task_id, "Integration test error")

            workflow_data.append(run_id)

        return task_manager, workflow_data

    def test_simple_api_full_workflow(self, full_api_setup, tmp_path):
        """Test complete workflow using SimpleDashboardAPI."""
        task_manager, run_ids = full_api_setup

        api = SimpleDashboardAPI(task_manager)

        # Test complete workflow
        # 1. Get runs
        runs = api.get_runs()
        assert len(runs) >= 2

        # 2. Get run details
        run_details = api.get_run_details(run_ids[0])
        assert run_details is not None
        assert len(run_details["tasks"]) == 4

        # 3. Start monitoring
        api.start_monitoring(run_ids[0])

        # 4. Collect metrics
        import time

        time.sleep(0.3)

        current_metrics = api.get_current_metrics()
        history = api.get_metrics_history()

        # 5. Generate reports
        html_report = api.generate_report(
            run_ids[0], format="html", output_path=tmp_path / "integration_report.html"
        )

        json_report = api.generate_report(
            run_ids[0],
            format="json",
            output_path=tmp_path / "integration_report.json",
            compare_runs=[run_ids[1]],
        )

        # 6. Generate dashboard
        dashboard_path = api.generate_dashboard(tmp_path / "integration_dashboard.html")

        # 7. Export metrics
        metrics_path = api.export_metrics_json(tmp_path / "integration_metrics.json")

        # 8. Stop monitoring
        api.stop_monitoring()

        # Verify all outputs
        assert html_report.exists()
        assert json_report.exists()
        assert dashboard_path.exists()
        assert metrics_path.exists()

        # Verify JSON report has comparison data
        with open(json_report) as f:
            report_data = json.load(f)

        assert "comparison" in report_data
        assert len(report_data["comparison"]["runs"]) == 2

        # Verify metrics export
        with open(metrics_path) as f:
            metrics_data = json.load(f)

        assert "current_metrics" in metrics_data
        assert "history" in metrics_data
        assert len(metrics_data["history"]) > 0

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
    def test_fastapi_server_integration(self, full_api_setup):
        """Test FastAPI server integration."""
        task_manager, run_ids = full_api_setup

        server = DashboardAPIServer(task_manager)

        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Test complete API workflow
        # 1. Health check
        health_response = client.get("/health")
        assert health_response.status_code == 200

        # 2. List runs
        runs_response = client.get("/api/v1/runs")
        assert runs_response.status_code == 200
        runs_data = runs_response.json()
        assert len(runs_data) >= 2

        # 3. Get specific run
        run_response = client.get(f"/api/v1/runs/{run_ids[0]}")
        assert run_response.status_code == 200

        # 4. Get run tasks
        tasks_response = client.get(f"/api/v1/runs/{run_ids[0]}/tasks")
        assert tasks_response.status_code == 200
        tasks_data = tasks_response.json()
        assert len(tasks_data) == 4

        # 5. Start monitoring
        start_response = client.post(
            "/api/v1/monitoring/start", json={"run_id": run_ids[0]}
        )
        assert start_response.status_code == 200

        # 6. Check monitoring status
        status_response = client.get("/api/v1/monitoring/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["monitoring"] is True

        # 7. Get current metrics
        metrics_response = client.get("/api/v1/metrics/current")
        assert metrics_response.status_code == 200

        # 8. Get metrics history
        history_response = client.get("/api/v1/metrics/history")
        assert history_response.status_code == 200

        # 9. Generate report
        report_request = {
            "run_id": run_ids[0],
            "format": "json",
            "include_charts": False,
            "compare_runs": [run_ids[1]],
        }
        report_response = client.post("/api/v1/reports/generate", json=report_request)
        assert report_response.status_code == 200

        # 10. Get live dashboard
        dashboard_response = client.get("/api/v1/dashboard/live")
        assert dashboard_response.status_code == 200

        # 11. Stop monitoring
        stop_response = client.post("/api/v1/monitoring/stop")
        assert stop_response.status_code == 200

        # Verify monitoring stopped
        final_status_response = client.get("/api/v1/monitoring/status")
        assert final_status_response.status_code == 200
        final_status_data = final_status_response.json()
        assert final_status_data["monitoring"] is False

    def test_api_error_handling(self, full_api_setup):
        """Test API error handling scenarios."""
        task_manager, run_ids = full_api_setup

        api = SimpleDashboardAPI(task_manager)

        # Test nonexistent run
        assert api.get_run_details("nonexistent-id") is None

        # Test invalid report format
        with pytest.raises(ValueError):
            api.generate_report(run_ids[0], format="invalid_format")

        # Test monitoring operations without errors
        # Start monitoring
        result = api.start_monitoring("nonexistent-run")
        assert result["status"] == "started"

        # Stop monitoring (should work even if nothing was monitoring)
        result = api.stop_monitoring()
        assert result["status"] == "stopped"

        # Multiple stops should work
        result = api.stop_monitoring()
        assert result["status"] == "stopped"

    def test_concurrent_api_operations(self, full_api_setup, tmp_path):
        """Test concurrent API operations."""
        task_manager, run_ids = full_api_setup

        api = SimpleDashboardAPI(task_manager)

        import threading
        import time

        results = []
        errors = []

        def api_worker(worker_id):
            try:
                # Each worker performs different operations
                if worker_id % 3 == 0:
                    # Worker 0, 3, 6... - Get runs and details
                    runs = api.get_runs(limit=2)
                    for run in runs[:1]:  # Just first run
                        details = api.get_run_details(run["run_id"])
                        results.append(f"worker_{worker_id}_details")

                elif worker_id % 3 == 1:
                    # Worker 1, 4, 7... - Generate reports
                    report_path = api.generate_report(
                        run_ids[0],
                        format="json",
                        output_path=tmp_path / f"concurrent_report_{worker_id}.json",
                    )
                    results.append(f"worker_{worker_id}_report")

                else:
                    # Worker 2, 5, 8... - Dashboard operations
                    dashboard_path = api.generate_dashboard(
                        tmp_path / f"concurrent_dashboard_{worker_id}.html"
                    )
                    results.append(f"worker_{worker_id}_dashboard")

            except Exception as e:
                errors.append(f"worker_{worker_id}_error: {e}")

        # Start multiple worker threads
        threads = []
        for i in range(6):
            thread = threading.Thread(target=api_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=10.0)

        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 6, f"Not all workers completed successfully: {results}"

        # Verify generated files exist
        report_files = list(tmp_path.glob("concurrent_report_*.json"))
        dashboard_files = list(tmp_path.glob("concurrent_dashboard_*.html"))

        assert len(report_files) >= 1  # At least one report generated
        assert len(dashboard_files) >= 1  # At least one dashboard generated
