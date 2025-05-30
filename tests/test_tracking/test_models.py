"""Tests for tracking models module."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from kailash.sdk_exceptions import KailashValidationError
from kailash.tracking.models import Task, TaskMetrics, TaskStatus


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_task_status_values(self):
        """Test task status values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_task_status_comparison(self):
        """Test task status comparison."""
        assert TaskStatus.PENDING == TaskStatus.PENDING
        assert TaskStatus.RUNNING != TaskStatus.COMPLETED

    def test_task_status_string_conversion(self):
        """Test converting status to string."""
        assert str(TaskStatus.PENDING) == "TaskStatus.PENDING"
        assert TaskStatus.PENDING.value == "pending"


class TestTaskMetrics:
    """Test TaskMetrics class."""

    def test_metrics_creation(self):
        """Test creating task metrics."""
        metrics = TaskMetrics(
            cpu_usage=75.5,
            memory_usage_mb=1024,
            duration=10.5,
            custom_metrics={"throughput": 1000, "latency": 50},
        )

        assert metrics.cpu_usage == 75.5
        assert metrics.memory_usage_mb == 1024
        assert metrics.duration == 10.5
        assert metrics.custom_metrics["throughput"] == 1000
        assert metrics.custom_metrics["latency"] == 50

    def test_metrics_defaults(self):
        """Test default metric values."""
        metrics = TaskMetrics()

        assert metrics.cpu_usage == 0.0
        assert metrics.memory_usage_mb == 0.0
        assert metrics.duration == 0.0
        assert metrics.custom_metrics == {}

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = TaskMetrics(
            cpu_usage=50.0,
            memory_usage_mb=512,
            duration=5.0,
            custom_metrics={"requests": 100},
        )

        metrics_dict = metrics.to_dict()

        assert metrics_dict["cpu_usage"] == 50.0
        assert metrics_dict["memory_usage_mb"] == 512
        assert metrics_dict["duration"] == 5.0
        assert metrics_dict["custom_metrics"]["requests"] == 100

    def test_metrics_from_dict(self):
        """Test creating metrics from dictionary."""
        metrics_dict = {
            "cpu_usage": 80.0,
            "memory_usage_mb": 2048,
            "duration": 15.0,
            "custom_metrics": {"cache_hits": 500},
        }

        metrics = TaskMetrics.from_dict(metrics_dict)

        assert metrics.cpu_usage == 80.0
        assert metrics.memory_usage_mb == 2048
        assert metrics.duration == 15.0
        assert metrics.custom_metrics["cache_hits"] == 500

    def test_metrics_equality(self):
        """Test metrics equality comparison."""
        metrics1 = TaskMetrics(cpu_usage=50.0, memory_usage_mb=1024)
        metrics2 = TaskMetrics(cpu_usage=50.0, memory_usage_mb=1024)
        metrics3 = TaskMetrics(cpu_usage=60.0, memory_usage_mb=1024)

        assert metrics1 == metrics2
        assert metrics1 != metrics3

    def test_metrics_validation(self):
        """Test metrics validation."""
        # Negative CPU usage should be invalid
        with pytest.raises(ValueError):
            TaskMetrics(cpu_usage=-10.0)

        # Negative memory usage should be invalid
        with pytest.raises(ValueError):
            TaskMetrics(memory_usage_mb=-100)

        # Negative duration should be invalid
        with pytest.raises(ValueError):
            TaskMetrics(duration=-1.0)


class TestTask:
    """Test Task class."""

    def test_task_creation(self):
        """Test creating a task."""
        task = Task(
            node_id="test-node",
            status=TaskStatus.PENDING,
            input_data={"value": 42},
            metadata={"user": "test", "priority": "high"},
        )

        assert task.task_id is not None
        assert task.node_id == "test-node"
        assert task.status == TaskStatus.PENDING
        assert task.input_data["value"] == 42
        assert task.metadata["user"] == "test"
        assert task.created_at is not None
        assert task.started_at is None
        assert task.completed_at is None

    def test_task_with_custom_id(self):
        """Test creating task with custom ID."""
        custom_id = "custom-task-123"
        task = Task(task_id=custom_id, node_id="test", status=TaskStatus.PENDING)

        assert task.task_id == custom_id

    def test_task_start(self):
        """Test starting a task."""
        task = Task(node_id="test", status=TaskStatus.PENDING)

        task.start()

        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None
        assert task.started_at <= datetime.now(timezone.utc)

    def test_task_complete(self):
        """Test completing a task."""
        task = Task(node_id="test", status=TaskStatus.PENDING)

        task.start()
        output_data = {"result": 100}
        task.complete(output_data)

        assert task.status == TaskStatus.COMPLETED
        assert task.output_data == output_data
        assert task.completed_at is not None
        assert task.error is None

    def test_task_fail(self):
        """Test failing a task."""
        task = Task(node_id="test", status=TaskStatus.PENDING)

        task.start()
        error_msg = "Processing failed due to invalid input"
        task.fail(error_msg)

        assert task.status == TaskStatus.FAILED
        assert task.error == error_msg
        assert task.completed_at is not None
        assert task.output_data is None

    def test_task_cancel(self):
        """Test canceling a task."""
        task = Task(node_id="test", status=TaskStatus.RUNNING)

        reason = "User requested cancellation"
        task.cancel(reason)

        assert task.status == TaskStatus.CANCELLED
        assert task.error == reason
        assert task.completed_at is not None

    def test_task_duration(self):
        """Test calculating task duration."""
        task = Task(node_id="test", status=TaskStatus.PENDING)

        # Task not started yet
        assert task.duration is None

        # Start task
        task.start()
        start_time = task.started_at

        # Task still running
        assert task.duration is None

        # Complete task
        task.completed_at = start_time + timedelta(seconds=5.5)
        duration = task.duration

        assert duration is not None
        assert abs(duration - 5.5) < 0.01

    def test_task_retry(self):
        """Test creating retry task."""
        original_task = Task(
            node_id="test",
            status=TaskStatus.FAILED,
            input_data={"value": 42},
            metadata={"priority": "high"},
        )

        retry_task = original_task.create_retry()

        assert retry_task.task_id != original_task.task_id
        assert retry_task.node_id == original_task.node_id
        assert retry_task.input_data == original_task.input_data
        assert retry_task.parent_task_id == original_task.task_id
        assert retry_task.retry_count == 1
        assert retry_task.status == TaskStatus.PENDING

    def test_task_multiple_retries(self):
        """Test multiple retry attempts."""
        task1 = Task(node_id="test", status=TaskStatus.FAILED)

        task2 = task1.create_retry()
        assert task2.retry_count == 1

        task3 = task2.create_retry()
        assert task3.retry_count == 2
        assert task3.parent_task_id == task2.task_id

    def test_task_to_dict(self):
        """Test converting task to dictionary."""
        task = Task(
            task_id="test-123",
            node_id="test-node",
            status=TaskStatus.RUNNING,
            input_data={"value": 42},
            output_data={"result": 84},
            metadata={"user": "test"},
            error="Some error",
            dependencies=["dep1", "dep2"],
        )

        task.started_at = datetime.now()
        task.metrics = TaskMetrics(cpu_usage=50.0)

        task_dict = task.to_dict()

        assert task_dict["task_id"] == "test-123"
        assert task_dict["node_id"] == "test-node"
        assert task_dict["status"] == "running"
        assert task_dict["input_data"]["value"] == 42
        assert task_dict["output_data"]["result"] == 84
        assert task_dict["metadata"]["user"] == "test"
        assert task_dict["error"] == "Some error"
        assert task_dict["dependencies"] == ["dep1", "dep2"]
        assert "started_at" in task_dict
        assert task_dict["metrics"]["cpu_usage"] == 50.0

    def test_task_from_dict(self):
        """Test creating task from dictionary."""
        now = datetime.now()
        task_dict = {
            "task_id": "test-456",
            "node_id": "test-node",
            "status": "completed",
            "input_data": {"x": 10},
            "output_data": {"y": 20},
            "metadata": {"tag": "production"},
            "created_at": now.isoformat(),
            "started_at": now.isoformat(),
            "completed_at": (now + timedelta(seconds=5)).isoformat(),
            "error": None,
            "dependencies": ["dep1"],
            "parent_task_id": "parent-123",
            "retry_count": 2,
            "metrics": {"cpu_usage": 75.0, "memory_usage_mb": 512, "duration": 5.0},
        }

        task = Task.from_dict(task_dict)

        assert task.task_id == "test-456"
        assert task.node_id == "test-node"
        assert task.status == TaskStatus.COMPLETED
        assert task.input_data["x"] == 10
        assert task.output_data["y"] == 20
        assert task.metadata["tag"] == "production"
        assert task.dependencies == ["dep1"]
        assert task.parent_task_id == "parent-123"
        assert task.retry_count == 2
        assert task.metrics.cpu_usage == 75.0

    def test_task_json_serialization(self):
        """Test JSON serialization of task."""
        task = Task(node_id="test", status=TaskStatus.PENDING, input_data={"value": 42})

        # Convert to JSON string
        json_str = json.dumps(task.to_dict(), default=str)

        # Parse back from JSON
        task_dict = json.loads(json_str)
        restored_task = Task.from_dict(task_dict)

        assert restored_task.node_id == task.node_id
        assert restored_task.status == task.status
        assert restored_task.input_data == task.input_data

    def test_task_validation(self):
        """Test task validation."""
        # Valid task
        task = Task(node_id="test", status=TaskStatus.PENDING)
        task.validate()  # Should not raise

        # Task with invalid state transition
        task.status = TaskStatus.COMPLETED
        task.started_at = None  # Completed but never started

        with pytest.raises(KailashValidationError):
            task.validate()

    def test_task_state_transitions(self):
        """Test valid task state transitions."""
        task = Task(node_id="test", status=TaskStatus.PENDING)

        # Valid transitions
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()  # Set started_at for validation to pass
        task.validate()  # Should not raise

        task.status = TaskStatus.COMPLETED
        task.validate()  # Should not raise

        # Invalid transition - can't go from completed to running
        completed_task = Task(node_id="test", status=TaskStatus.COMPLETED)
        completed_task.started_at = (
            datetime.now()
        )  # Set started_at to avoid validation error

        # Set special attributes for transition validation
        completed_task._from_status = TaskStatus.COMPLETED
        completed_task._to_status = TaskStatus.RUNNING

        with pytest.raises(KailashValidationError):
            completed_task.validate()

    def test_task_equality(self):
        """Test task equality comparison."""
        task1 = Task(task_id="test-1", node_id="test", status=TaskStatus.PENDING)
        task2 = Task(task_id="test-1", node_id="test", status=TaskStatus.PENDING)
        task3 = Task(task_id="test-2", node_id="test", status=TaskStatus.PENDING)

        assert task1 == task2  # Same task ID
        assert task1 != task3  # Different task ID

    def test_task_hash(self):
        """Test task hashing."""
        task1 = Task(task_id="test-1", node_id="test", status=TaskStatus.PENDING)
        task2 = Task(task_id="test-1", node_id="test", status=TaskStatus.PENDING)

        # Tasks with same ID should have same hash
        assert hash(task1) == hash(task2)

        # Can be used in sets/dicts
        task_set = {task1, task2}
        assert len(task_set) == 1
