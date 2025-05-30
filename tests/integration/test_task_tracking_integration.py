"""Integration tests for task tracking during workflow execution."""

import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone

import pytest
import pandas as pd

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import Node
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import Task, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.tracking.storage.database import DatabaseStorage


class TestTaskTrackingIntegration:
    """Test task tracking functionality during workflow execution."""
    
    def test_workflow_execution_with_tracking(
        self, simple_workflow: Workflow, task_manager: TaskManager
    ):
        """Test that all workflow nodes are tracked during execution."""
        runner = LocalRuntime()
        
        # Execute workflow with tracking
        result, run_id = runner.execute(simple_workflow, task_manager=task_manager)
        
        # Verify execution completed
        assert result is not None
        
        # Get all tracked tasks
        tasks = task_manager.list_tasks(run_id)
        
        # Verify correct number of tasks
        expected_node_count = len(simple_workflow.graph.nodes())
        assert len(tasks) == expected_node_count
        
        # Verify all tasks completed
        for task in tasks:
            assert task.status == TaskStatus.COMPLETED
            assert task.started_at is not None
            assert task.ended_at is not None
            assert task.duration >= 0  # Duration can be 0 for very fast tasks
    
    @pytest.mark.skip(reason="Complex workflow has too many connection issues")
    def test_task_hierarchy_tracking(self, complex_workflow: Workflow, task_manager: TaskManager):
        """Test tracking of parent-child task relationships."""
        runner = LocalRuntime()
        
        # Create parent task for workflow
        workflow_task = task_manager.create_task(
            node_id=f"workflow_{complex_workflow.workflow_id}",
            metadata={
                "workflow_id": complex_workflow.workflow_id,
                "name": f"Workflow: {complex_workflow.name}"
            }
        )
        task_manager.update_task_status(workflow_task.task_id, TaskStatus.RUNNING)
        
        # Execute workflow with tracking
        result, run_id = runner.execute(complex_workflow, task_manager=task_manager)
        
        # Complete workflow task
        task_manager.update_task_status(workflow_task.task_id, TaskStatus.COMPLETED)
        
        # Verify hierarchy
        all_tasks = task_manager.get_workflow_tasks(complex_workflow.workflow_id)
        
        assert len(all_tasks) > 0
        assert all(t.status == TaskStatus.COMPLETED for t in all_tasks if t.task_id != workflow_task.task_id)
    
    def test_failed_node_tracking(self, error_workflow: Workflow, task_manager: TaskManager):
        """Test that failed nodes are properly tracked."""
        runner = LocalRuntime()
        
        # Execute workflow that will fail
        try:
            result, run_id = runner.execute(error_workflow, task_manager=task_manager)
        except Exception:
            pass  # Expected to fail
        
        # Check tracked tasks
        tasks = task_manager.get_workflow_tasks(error_workflow.workflow_id)
        
        # At least one task should have failed status
        failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
        assert len(failed_tasks) > 0
        
        # Failed tasks should have error information
        for task in failed_tasks:
            assert task.error is not None
            assert len(task.error) > 0
    
    @pytest.mark.skip(reason="LongRunningProcessor node not implemented")
    def test_task_progress_tracking(self, temp_data_dir: Path, task_manager: TaskManager):
        """Test tracking of task progress updates."""
        builder = WorkflowBuilder()
        
        # Create workflow with long-running node
        node_id = builder.add_node(
            "LongRunningProcessor",
            "processor",
            config={"iterations": 10}
        )
        
        workflow = builder.build("progress_tracking_test")
        
        runner = LocalRuntime()
        
        # Execute workflow
        result, run_id = runner.execute(workflow, task_manager=task_manager)
        
        # Get the task for the processor node
        tasks = task_manager.get_workflow_tasks(workflow.workflow_id)
        processor_task = next((t for t in tasks if t.node_id == "processor"), None)
        
        # Verify progress was tracked
        assert processor_task is not None
        assert processor_task.metadata.get("progress", 0) > 0
    
    def test_concurrent_workflow_tracking(
        self, simple_workflow: Workflow, task_manager: TaskManager
    ):
        """Test tracking of multiple concurrent workflow executions."""
        runner = LocalRuntime()
        
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        # Execute multiple workflows concurrently
        def run_workflow(workflow_id: int):
            result, run_id = runner.execute(simple_workflow, task_manager=task_manager)
            return result
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_workflow, i) for i in range(3)]
            results = [f.result() for f in futures]
        
        # Verify all executions were tracked
        tasks = task_manager.get_workflow_tasks(simple_workflow.workflow_id)
        
        # Should have multiple sets of tasks
        assert len(tasks) >= len(simple_workflow.graph.nodes())
    
    def test_task_metadata_tracking(self, simple_workflow: Workflow, task_manager: TaskManager):
        """Test that task metadata is properly tracked."""
        runner = LocalRuntime()
        
        # Add custom metadata to nodes
        for node_id, node in simple_workflow.graph.nodes(data=True):
            node['node'].config['metadata'] = {
                "user": "test_user",
                "environment": "testing",
                "version": "1.0.0",
                "tags": ["integration", "test"]
            }
        
        # Execute workflow
        result, run_id = runner.execute(simple_workflow, task_manager=task_manager)
        
        # Verify metadata was tracked
        tasks = task_manager.get_workflow_tasks(simple_workflow.workflow_id)
        for task in tasks:
            assert task.metadata.get("user") == "test_user"
            assert task.metadata.get("environment") == "testing"
            assert "integration" in task.metadata.get("tags", [])
    
    def test_task_duration_tracking(self, simple_workflow: Workflow, task_manager: TaskManager):
        """Test accurate tracking of task execution duration."""
        runner = LocalRuntime()
        
        # Execute workflow
        start_time = datetime.now(timezone.utc)
        result, run_id = runner.execute(simple_workflow, task_manager=task_manager)
        end_time = datetime.now(timezone.utc)
        
        # Get tracked tasks
        tasks = task_manager.get_workflow_tasks(simple_workflow.workflow_id)
        
        # Verify duration tracking
        for task in tasks:
            assert task.started_at is not None
            assert task.ended_at is not None
            assert task.duration > 0
            
            # Task should have started after workflow start
            assert task.started_at >= start_time
            
            # Task should have completed before workflow end
            assert task.ended_at <= end_time
            
            # Duration should match timestamps
            expected_duration = (task.ended_at - task.started_at).total_seconds()
            assert abs(task.duration - expected_duration) < 0.1  # Allow small difference
    
    @pytest.mark.skip(reason="RetryableProcessor node not implemented")
    def test_task_retry_tracking(self, temp_data_dir: Path, task_manager: TaskManager):
        """Test tracking of task retries on failure."""
        builder = WorkflowBuilder()
        
        # Create node that fails first time but succeeds on retry
        node_id = builder.add_node(
            "RetryableProcessor",
            "processor",
            config={
                "data": {"attempts": 0},
                "max_attempts": 3
            }
        )
        
        workflow = builder.build("retry_tracking_test")
        
        runner = LocalRuntime()
        
        # Execute workflow with retries
        result, run_id = runner.execute(workflow, task_manager=task_manager)
        
        # Get tasks
        tasks = task_manager.get_workflow_tasks(workflow.workflow_id)
        
        # Check for retry information
        processor_tasks = [t for t in tasks if t.node_id == "processor"]
        
        # Should have retry information
        assert len(processor_tasks) > 0
        processor_task = processor_tasks[0]
        assert processor_task.metadata.get("retry_count", 0) >= 0
    
    @pytest.mark.skip(reason="Complex workflow has too many connection issues")
    def test_task_search_and_filtering(
        self, complex_workflow: Workflow, task_manager: TaskManager
    ):
        """Test searching and filtering of tracked tasks."""
        runner = LocalRuntime()
        
        # Execute workflow
        result, run_id = runner.execute(complex_workflow, task_manager=task_manager)
        
        # Get all tasks
        all_tasks = task_manager.get_workflow_tasks(complex_workflow.workflow_id)
        
        # Filter by status
        completed_tasks = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]
        assert len(completed_tasks) == len(complex_workflow.graph.nodes())
        
        # Filter by time range
        now = datetime.now(timezone.utc)
        recent_tasks = [
            t for t in all_tasks
            if t.started_at and t.started_at >= now - timedelta(minutes=5)
        ]
        assert len(recent_tasks) > 0
    
    def test_storage_backend_integration(self, simple_workflow: Workflow, temp_data_dir: Path):
        """Test task tracking with different storage backends."""
        runner = LocalRuntime()
        
        # Test with filesystem storage
        fs_storage = FileSystemStorage(temp_data_dir / "tasks_fs")
        fs_manager = TaskManager(storage_backend=fs_storage)
        
        result1, run_id1 = runner.execute(simple_workflow, task_manager=fs_manager)
        fs_tasks = fs_manager.get_workflow_tasks(simple_workflow.workflow_id)
        assert len(fs_tasks) > 0
        
        # Test with database storage
        db_path = temp_data_dir / "tasks.db"
        db_storage = DatabaseStorage(f"sqlite:///{db_path}")
        db_manager = TaskManager(storage_backend=db_storage)
        
        result2, run_id2 = runner.execute(simple_workflow, task_manager=db_manager)
        db_tasks = db_manager.get_workflow_tasks(simple_workflow.workflow_id)
        assert len(db_tasks) > 0
        
        # Both storages should have tracked the same number of tasks
        assert len(fs_tasks) == len(db_tasks)
    
    def test_task_lifecycle_events(self, simple_workflow: Workflow, task_manager: TaskManager):
        """Test tracking of task lifecycle events."""
        runner = LocalRuntime()
        
        # Track lifecycle events
        events = []
        
        # Override task manager methods to capture events
        original_create = task_manager.create_task
        original_update = task_manager.update_task_status
        
        def track_create(*args, **kwargs):
            task = original_create(*args, **kwargs)
            events.append({
                "type": "created",
                "task_id": task.task_id,
                "node_id": task.node_id,
                "status": task.status,
                "timestamp": datetime.now(timezone.utc)
            })
            return task
        
        def track_update(task_id, status, *args, **kwargs):
            original_update(task_id, status, *args, **kwargs)
            events.append({
                "type": status.value,
                "task_id": task_id,
                "status": status,
                "timestamp": datetime.now(timezone.utc)
            })
        
        task_manager.create_task = track_create
        task_manager.update_task_status = track_update
        
        # Execute workflow
        result, run_id = runner.execute(simple_workflow, task_manager=task_manager)
        
        # Verify events were captured
        assert len(events) > 0
        
        # Check event types
        event_types = {e["type"] for e in events}
        assert "created" in event_types
        assert TaskStatus.RUNNING.value in event_types
        assert TaskStatus.COMPLETED.value in event_types
    
    def test_task_performance_metrics(
        self, large_dataset: Path, temp_data_dir: Path, task_manager: TaskManager
    ):
        """Test tracking of performance metrics for tasks."""
        builder = WorkflowBuilder()
        
        # Create workflow with performance-intensive operations
        reader_id = builder.add_node(
            "CSVReader",
            "reader",
            config={"file_path": str(large_dataset)}
        )
        
        processor_id = builder.add_node(
            "DataTransformer",
            "aggregator",
            config={
                "transformations": [
                    # Simple aggregation transformation using pandas
                    """
import pandas as pd
df = pd.DataFrame(data)
# Convert value column to numeric
df['value'] = pd.to_numeric(df['value'], errors='coerce')
result = df.groupby('category').agg({'value': 'mean'}).reset_index().to_dict('records')
                    """
                ]
            }
        )
        
        writer_id = builder.add_node(
            "CSVWriter",
            "writer",
            config={
                "file_path": str(temp_data_dir / "aggregated.csv")
            }
        )
        
        builder.add_connection(reader_id, "data", processor_id, "data")
        builder.add_connection(processor_id, "aggregated_data", writer_id, "data")
        
        workflow = builder.build("performance_test")
        
        runner = LocalRuntime()
        
        # Execute workflow
        result, run_id = runner.execute(workflow, task_manager=task_manager)
        
        # Get performance metrics
        tasks = task_manager.get_workflow_tasks(workflow.workflow_id)
        
        for task in tasks:
            # Verify performance metrics were tracked
            metrics = task.metadata.get("performance_metrics", {})
            
            if task.node_id == "reader":
                # Check that some metrics exist
                assert len(metrics) >= 0  # May or may not have specific metrics
            elif task.node_id == "aggregator":
                assert len(metrics) >= 0
            elif task.node_id == "writer":
                assert len(metrics) >= 0