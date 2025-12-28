"""Consolidated tests for tracking functionality."""

import pytest
from kailash.tracking.manager import TaskManager
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus


class TestTrackingSuite:
    """Consolidated tests for tracking components."""

    def test_task_models(self):
        """Test task and metrics model functionality."""
        # Test TaskRun model with required fields
        task_run = TaskRun(
            node_id="test_node", run_id="test_workflow", status=TaskStatus.PENDING
        )

        assert task_run.node_id == "test_node"
        assert task_run.status == TaskStatus.PENDING
        assert task_run.task_id is not None  # Should be auto-generated

        # Test model serialization
        task_dict = task_run.model_dump()
        assert "task_id" in task_dict
        assert "node_id" in task_dict
        assert "status" in task_dict

    def test_task_manager_basic(self):
        """Test basic TaskManager functionality."""
        # Test with default storage backend
        manager = TaskManager()
        assert manager is not None

        # Test with None storage backend (should use default)
        manager = TaskManager(storage_backend=None)
        assert manager is not None

    def test_metrics_collector_basic(self):
        """Test basic MetricsCollector functionality."""
        collector = MetricsCollector()

        # Test collector initialization
        assert collector is not None

        # Test that collector has expected methods
        assert hasattr(collector, "collect")

    def test_task_status_enum(self):
        """Test TaskStatus enum values."""
        # Test all status values are accessible
        assert TaskStatus.PENDING is not None
        assert TaskStatus.RUNNING is not None
        assert TaskStatus.COMPLETED is not None
        assert TaskStatus.FAILED is not None

        # Test status string conversion
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"

    def test_task_metrics_model(self):
        """Test TaskMetrics model."""
        metrics = TaskMetrics(duration=1.5, memory_usage_mb=100.0, cpu_usage=50.0)

        assert metrics.duration == 1.5
        assert metrics.memory_usage_mb == 100.0
        assert metrics.cpu_usage == 50.0

        # Test serialization
        metrics_dict = metrics.model_dump()
        assert "duration" in metrics_dict
        assert "memory_usage_mb" in metrics_dict
        assert "cpu_usage" in metrics_dict

    def test_task_run_with_all_fields(self):
        """Test TaskRun with all available fields."""
        task = TaskRun(
            node_id="test_node",
            run_id="test_workflow",
            status=TaskStatus.COMPLETED,
            input_data={"test": True},
            output_data={"result": "success"},
        )

        # Test task can be created and accessed
        assert task.node_id == "test_node"
        assert task.status == TaskStatus.COMPLETED

        # Test dictionary conversion
        task_data = task.model_dump()
        assert isinstance(task_data, dict)
        assert task_data["node_id"] == "test_node"

    def test_model_validation(self):
        """Test model validation and error handling."""
        # Test that required fields are enforced
        with pytest.raises(Exception):  # ValidationError or similar
            TaskRun()  # Missing required node_id

        # Test that node_id is required
        with pytest.raises(Exception):
            TaskRun(
                run_id="test",
                status=TaskStatus.PENDING,
                # Missing node_id
            )

    def test_task_run_defaults(self):
        """Test TaskRun default values."""
        task = TaskRun(node_id="test_node")

        # Should have auto-generated task_id
        assert task.task_id is not None
        assert len(task.task_id) > 0

        # Should have default run_id
        assert task.run_id == "test-run-id"

        # Should have default node_type
        assert task.node_type == "default-node-type"

    def test_multiple_task_instances(self):
        """Test creating multiple task instances."""
        tasks = []
        for i in range(3):
            task = TaskRun(node_id=f"node_{i}", run_id="multi_test")
            tasks.append(task)

        # All tasks should have unique IDs
        task_ids = [task.task_id for task in tasks]
        assert len(set(task_ids)) == 3  # All unique

        # All should have same run_id
        run_ids = [task.run_id for task in tasks]
        assert all(rid == "multi_test" for rid in run_ids)
