"""Tests for task tracking manager module."""

import pytest
from datetime import datetime, timedelta
from typing import Optional, List

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus, TaskMetrics, WorkflowRun
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.tracking.storage.base import StorageBackend
from kailash.sdk_exceptions import KailashValidationError


class MockStorage(StorageBackend):
    """Mock storage backend for testing."""
    
    def __init__(self):
        """Initialize mock storage."""
        self.tasks = {}
        self.runs = {}
    
    def save_task(self, task: TaskRun) -> None:
        """Save task to storage."""
        self.tasks[task.task_id] = task
    
    def get_task(self, task_id: str) -> TaskRun:
        """Get task from storage."""
        return self.tasks.get(task_id)
    
    def load_task(self, task_id: str) -> TaskRun:
        """Load task from storage."""
        return self.get_task(task_id)
    
    def get_all_tasks(self) -> list[TaskRun]:
        """Get all tasks."""
        return list(self.tasks.values())
    
    def update_task(self, task: TaskRun) -> None:
        """Update task in storage."""
        if task.task_id not in self.tasks:
            raise ValueError(f"Task {task.task_id} not found")
        self.tasks[task.task_id] = task
    
    def delete_task(self, task_id: str) -> None:
        """Delete task from storage."""
        if task_id in self.tasks:
            del self.tasks[task_id]
    
    def query_tasks(self, **kwargs) -> list[TaskRun]:
        """Query tasks by criteria."""
        results = []
        for task in self.tasks.values():
            if self._matches_criteria(task, **kwargs):
                results.append(task)
        return results
    
    def _matches_criteria(self, task: TaskRun, **kwargs) -> bool:
        """Check if task matches criteria."""
        for key, value in kwargs.items():
            # Handle special time range parameters
            if key == 'started_after':
                if not task.created_at or task.created_at < value:
                    return False
            elif key == 'completed_before':
                if not task.created_at or task.created_at > value:
                    return False
            else:
                # Handle regular attribute matching
                if not hasattr(task, key):
                    return False
                if getattr(task, key) != value:
                    return False
        return True
    
    # Required by StorageBackend abstract class
    def save_run(self, run: WorkflowRun) -> None:
        """Save workflow run."""
        self.runs[run.run_id] = run
    
    def load_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Load workflow run."""
        return self.runs.get(run_id)
    
    def list_runs(self, workflow_name: Optional[str] = None, status: Optional[str] = None) -> List[WorkflowRun]:
        """List workflow runs."""
        results = []
        for run in self.runs.values():
            if workflow_name and run.workflow_name != workflow_name:
                continue
            if status and run.status != status:
                continue
            results.append(run)
        return results
    
    def list_tasks(self, run_id: str, node_id: Optional[str] = None, status: Optional[TaskStatus] = None) -> List[TaskRun]:
        """List tasks for a run."""
        results = []
        for task in self.tasks.values():
            if task.run_id != run_id:
                continue
            if node_id and task.node_id != node_id:
                continue
            if status and task.status != status:
                continue
            results.append(task)
        return results
    
    def clear(self) -> None:
        """Clear all stored data."""
        self.tasks.clear()
        self.runs.clear()
    
    def export_run(self, run_id: str, output_path: str) -> None:
        """Export a run and its tasks."""
        pass
    
    def import_run(self, input_path: str) -> str:
        """Import a run and its tasks."""
        return "imported-run-id"


class TestTaskManager:
    """Test TaskManager class."""
    
    def test_manager_creation(self):
        """Test creating task manager."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        assert manager.storage == storage
    
    def test_create_task(self):
        """Test creating a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        task = manager.create_task(
            node_id="test-node",
            input_data={"value": 42},
            metadata={"user": "test"}
        )
        
        assert task.node_id == "test-node"
        assert task.status == TaskStatus.PENDING
        assert task.input_data["value"] == 42
        assert task.metadata["user"] == "test"
        assert task.task_id in storage.tasks
    
    def test_get_task(self):
        """Test getting a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create task
        created_task = manager.create_task(node_id="test")
        
        # Get task
        retrieved_task = manager.get_task(created_task.task_id)
        
        assert retrieved_task.task_id == created_task.task_id
        assert retrieved_task.node_id == "test"
    
    def test_get_nonexistent_task(self):
        """Test getting non-existent task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        task = manager.get_task("nonexistent")
        assert task is None
    
    def test_update_task_status(self):
        """Test updating task status."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create task
        task = manager.create_task(node_id="test")
        original_id = task.task_id
        
        # Update status
        manager.update_task_status(
            task_id=original_id,
            status=TaskStatus.RUNNING
        )
        
        # Verify update
        updated_task = manager.get_task(original_id)
        assert updated_task.status == TaskStatus.RUNNING
        assert updated_task.started_at is not None
    
    def test_complete_task(self):
        """Test completing a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create and start task
        task = manager.create_task(node_id="test")
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        
        # Complete task
        output_data = {"result": 100}
        manager.complete_task(task.task_id, output_data)
        
        # Verify completion
        completed_task = manager.get_task(task.task_id)
        assert completed_task.status == TaskStatus.COMPLETED
        assert completed_task.output_data == output_data
        assert completed_task.completed_at is not None
        assert completed_task.metrics is not None
        assert completed_task.metrics.duration > 0
    
    def test_fail_task(self):
        """Test failing a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create and start task
        task = manager.create_task(node_id="test")
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        
        # Fail task
        error_msg = "Processing failed"
        manager.fail_task(task.task_id, error_msg)
        
        # Verify failure
        failed_task = manager.get_task(task.task_id)
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.error == error_msg
        assert failed_task.completed_at is not None
    
    def test_retry_task(self):
        """Test retrying a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create, start, and fail task
        task = manager.create_task(node_id="test", input_data={"value": 1})
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        manager.fail_task(task.task_id, "First attempt failed")
        
        # Retry task
        new_task = manager.retry_task(task.task_id)
        
        assert new_task.task_id != task.task_id
        assert new_task.node_id == task.node_id
        assert new_task.input_data == task.input_data
        assert new_task.retry_count == 1
        assert new_task.parent_task_id == task.task_id
    
    def test_get_tasks_by_status(self):
        """Test getting tasks by status."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks with different statuses
        task1 = manager.create_task(node_id="test1")
        task2 = manager.create_task(node_id="test2")
        task3 = manager.create_task(node_id="test3")
        
        manager.update_task_status(task2.task_id, TaskStatus.RUNNING)
        # Must transition to RUNNING before COMPLETED
        manager.update_task_status(task3.task_id, TaskStatus.RUNNING)
        manager.complete_task(task3.task_id, {"result": 1})
        
        # Query by status
        pending_tasks = manager.get_tasks_by_status(TaskStatus.PENDING)
        running_tasks = manager.get_tasks_by_status(TaskStatus.RUNNING)
        completed_tasks = manager.get_tasks_by_status(TaskStatus.COMPLETED)
        
        assert len(pending_tasks) == 1
        assert len(running_tasks) == 1
        assert len(completed_tasks) == 1
        
        assert pending_tasks[0].task_id == task1.task_id
        assert running_tasks[0].task_id == task2.task_id
        assert completed_tasks[0].task_id == task3.task_id
    
    def test_get_tasks_by_node(self):
        """Test getting tasks by node ID."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks for different nodes
        task1 = manager.create_task(node_id="node1")
        task2 = manager.create_task(node_id="node1")
        task3 = manager.create_task(node_id="node2")
        
        # Query by node
        node1_tasks = manager.get_tasks_by_node("node1")
        node2_tasks = manager.get_tasks_by_node("node2")
        
        assert len(node1_tasks) == 2
        assert len(node2_tasks) == 1
        
        assert all(task.node_id == "node1" for task in node1_tasks)
        assert node2_tasks[0].node_id == "node2"
    
    def test_get_task_history(self):
        """Test getting task history."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create initial task
        original_task = manager.create_task(node_id="test", input_data={"v": 1})
        manager.update_task_status(original_task.task_id, TaskStatus.RUNNING)
        manager.fail_task(original_task.task_id, "Failed")
        
        # Create retries
        retry1 = manager.retry_task(original_task.task_id)
        manager.update_task_status(retry1.task_id, TaskStatus.RUNNING)
        manager.fail_task(retry1.task_id, "Failed again")
        
        retry2 = manager.retry_task(retry1.task_id)
        manager.update_task_status(retry2.task_id, TaskStatus.RUNNING)
        manager.complete_task(retry2.task_id, {"result": "success"})
        
        # Get history
        history = manager.get_task_history(retry2.task_id)
        
        assert len(history) == 3
        assert history[0].task_id == original_task.task_id
        assert history[1].task_id == retry1.task_id
        assert history[2].task_id == retry2.task_id
    
    def test_cancel_task(self):
        """Test canceling a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create and start task
        task = manager.create_task(node_id="test")
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        
        # Cancel task
        manager.cancel_task(task.task_id, "User requested cancellation")
        
        # Verify cancellation
        cancelled_task = manager.get_task(task.task_id)
        assert cancelled_task.status == TaskStatus.CANCELLED
        assert cancelled_task.error == "User requested cancellation"
    
    def test_delete_task(self):
        """Test deleting a task."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create task
        task = manager.create_task(node_id="test")
        task_id = task.task_id
        
        # Delete task
        manager.delete_task(task_id)
        
        # Verify deletion
        assert manager.get_task(task_id) is None
        assert task_id not in storage.tasks
    
    def test_get_tasks_by_timerange(self):
        """Test getting tasks by time range."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks at different times using naive datetime to match model
        now = datetime.now()
        
        task1 = manager.create_task(node_id="test1")
        task1.created_at = now - timedelta(hours=3)
        storage.save_task(task1)  # Use save_task instead of update_task
        
        task2 = manager.create_task(node_id="test2")
        task2.created_at = now - timedelta(hours=1)
        storage.save_task(task2)
        
        task3 = manager.create_task(node_id="test3")
        task3.created_at = now - timedelta(minutes=30)
        storage.save_task(task3)
        
        # Query by time range
        start_time = now - timedelta(hours=2)
        end_time = now + timedelta(minutes=1)  # Add some buffer
        
        tasks = manager.get_tasks_by_timerange(start_time, end_time)
        
        assert len(tasks) == 2
        assert task2.task_id in [t.task_id for t in tasks]
        assert task3.task_id in [t.task_id for t in tasks]
    
    def test_get_task_statistics(self):
        """Test getting task statistics."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks with different statuses
        for i in range(10):
            task = manager.create_task(node_id=f"node{i % 3}")
            
            if i < 3:
                manager.update_task_status(task.task_id, TaskStatus.RUNNING)
            elif i < 7:
                manager.update_task_status(task.task_id, TaskStatus.RUNNING)
                manager.complete_task(task.task_id, {"result": i})
            else:
                manager.update_task_status(task.task_id, TaskStatus.RUNNING)
                manager.fail_task(task.task_id, "Error")
        
        # Get statistics
        stats = manager.get_task_statistics()
        
        assert stats["total_tasks"] == 10
        assert stats["by_status"][TaskStatus.RUNNING] == 3
        assert stats["by_status"][TaskStatus.COMPLETED] == 4
        assert stats["by_status"][TaskStatus.FAILED] == 3
        assert stats["by_node"]["node0"] == 4
        assert stats["by_node"]["node1"] == 3
        assert stats["by_node"]["node2"] == 3
    
    def test_cleanup_old_tasks(self):
        """Test cleaning up old tasks."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        now = datetime.now()
        
        # Create tasks with different ages
        old_task = manager.create_task(node_id="old")
        old_task.created_at = now - timedelta(days=35)
        old_task.status = TaskStatus.COMPLETED
        storage.update_task(old_task)
        
        recent_task = manager.create_task(node_id="recent")
        
        # Cleanup tasks older than 30 days
        manager.cleanup_old_tasks(days=30)
        
        # Verify cleanup
        assert manager.get_task(old_task.task_id) is None
        assert manager.get_task(recent_task.task_id) is not None
    
    def test_update_metrics(self):
        """Test updating task metrics."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create and start task
        task = manager.create_task(node_id="test")
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        
        # Update metrics
        metrics = TaskMetrics(
            cpu_usage=75.5,
            memory_usage_mb=1024,
            duration=10.5,
            custom_metrics={"throughput": 1000}
        )
        
        manager.update_task_metrics(task.task_id, metrics)
        
        # Verify metrics
        updated_task = manager.get_task(task.task_id)
        assert updated_task.metrics == metrics
        assert updated_task.metrics.cpu_usage == 75.5
        assert updated_task.metrics.custom_metrics["throughput"] == 1000
    
    def test_get_running_tasks(self):
        """Test getting currently running tasks."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks
        task1 = manager.create_task(node_id="test1")
        task2 = manager.create_task(node_id="test2")
        task3 = manager.create_task(node_id="test3")
        
        # Start some tasks
        manager.update_task_status(task1.task_id, TaskStatus.RUNNING)
        manager.update_task_status(task2.task_id, TaskStatus.RUNNING)
        
        # Get running tasks
        running = manager.get_running_tasks()
        
        assert len(running) == 2
        assert all(task.status == TaskStatus.RUNNING for task in running)
    
    def test_task_with_dependencies(self):
        """Test task with dependencies."""
        storage = MockStorage()
        manager = TaskManager(storage)
        
        # Create tasks with dependencies
        task1 = manager.create_task(node_id="task1")
        task2 = manager.create_task(
            node_id="task2",
            dependencies=[task1.task_id]
        )
        task3 = manager.create_task(
            node_id="task3",
            dependencies=[task1.task_id, task2.task_id]
        )
        
        # Verify dependencies
        assert task2.dependencies == [task1.task_id]
        assert task3.dependencies == [task1.task_id, task2.task_id]
        
        # Get dependencies
        deps = manager.get_task_dependencies(task3.task_id)
        assert len(deps) == 2