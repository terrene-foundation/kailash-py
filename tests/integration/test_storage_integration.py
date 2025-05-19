"""Test storage backends in real scenarios."""

import json
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pytest

from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.tracking.storage.database import DatabaseStorage
from kailash.tracking.storage.base import StorageBackend
from kailash.tracking.models import Task, TaskStatus
from kailash.tracking.manager import TaskTracker
from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow


class TestStorageIntegration:
    """Test storage backends with real task tracking scenarios."""
    
    def test_filesystem_storage_persistence(self, temp_data_dir: Path):
        """Test filesystem storage persistence across sessions."""
        storage_path = temp_data_dir / "fs_storage"
        
        # Create first storage instance and save tasks
        storage1 = FileSystemStorage(storage_path)
        tracker1 = TaskTracker(storage=storage1)
        
        # Create and track tasks
        task1 = tracker1.create_task("Task 1", "First task")
        task1.update_status(TaskStatus.COMPLETED)
        
        task2 = tracker1.create_task("Task 2", "Second task")
        task2.update_status(TaskStatus.IN_PROGRESS)
        
        # Get task IDs for verification
        task1_id = task1.id
        task2_id = task2.id
        
        # Create new storage instance pointing to same location
        storage2 = FileSystemStorage(storage_path)
        tracker2 = TaskTracker(storage=storage2)
        
        # Verify tasks are persisted
        loaded_tasks = tracker2.get_tasks()
        assert len(loaded_tasks) == 2
        
        # Verify task data integrity
        loaded_task1 = tracker2.get_task(task1_id)
        assert loaded_task1.name == "Task 1"
        assert loaded_task1.status == TaskStatus.COMPLETED
        
        loaded_task2 = tracker2.get_task(task2_id)
        assert loaded_task2.name == "Task 2"
        assert loaded_task2.status == TaskStatus.IN_PROGRESS
    
    def test_database_storage_persistence(self, temp_data_dir: Path):
        """Test database storage persistence and querying."""
        db_path = temp_data_dir / "tasks.db"
        db_url = f"sqlite:///{db_path}"
        
        # Create first storage instance
        storage1 = DatabaseStorage(db_url)
        tracker1 = TaskTracker(storage=storage1)
        
        # Create tasks with metadata
        task1 = tracker1.create_task(
            "DB Task 1",
            "Database storage test",
            metadata={"priority": "high", "category": "test"}
        )
        task1.update_status(TaskStatus.COMPLETED)
        
        task2 = tracker1.create_task(
            "DB Task 2",
            "Another database test",
            metadata={"priority": "low", "category": "test"}
        )
        task2.update_status(TaskStatus.FAILED, error="Test error")
        
        # Create new storage instance
        storage2 = DatabaseStorage(db_url)
        tracker2 = TaskTracker(storage=storage2)
        
        # Query tasks
        all_tasks = tracker2.get_tasks()
        assert len(all_tasks) == 2
        
        # Query by status
        completed_tasks = tracker2.search_tasks(status=TaskStatus.COMPLETED)
        assert len(completed_tasks) == 1
        assert completed_tasks[0].name == "DB Task 1"
        
        failed_tasks = tracker2.search_tasks(status=TaskStatus.FAILED)
        assert len(failed_tasks) == 1
        assert failed_tasks[0].error == "Test error"
    
    def test_concurrent_storage_access(self, temp_data_dir: Path):
        """Test concurrent access to storage backends."""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        
        storage_path = temp_data_dir / "concurrent_storage"
        storage = FileSystemStorage(storage_path)
        
        # Function to create and update tasks
        def create_and_update_task(task_id: int):
            tracker = TaskTracker(storage=storage)
            task = tracker.create_task(f"Concurrent Task {task_id}", f"Task {task_id}")
            time.sleep(0.01)  # Simulate some work
            task.update_status(TaskStatus.IN_PROGRESS)
            time.sleep(0.01)  # More work
            task.update_status(TaskStatus.COMPLETED)
            return task.id
        
        # Create tasks concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_and_update_task, i) for i in range(10)]
            task_ids = [f.result() for f in futures]
        
        # Verify all tasks were created
        tracker = TaskTracker(storage=storage)
        all_tasks = tracker.get_tasks()
        assert len(all_tasks) == 10
        
        # Verify all tasks completed
        completed_tasks = tracker.search_tasks(status=TaskStatus.COMPLETED)
        assert len(completed_tasks) == 10
    
    def test_storage_migration(self, temp_data_dir: Path):
        """Test migrating data between storage backends."""
        # Create filesystem storage with tasks
        fs_storage_path = temp_data_dir / "fs_storage"
        fs_storage = FileSystemStorage(fs_storage_path)
        fs_tracker = TaskTracker(storage=fs_storage)
        
        # Create test tasks
        tasks_data = []
        for i in range(5):
            task = fs_tracker.create_task(
                f"Migration Task {i}",
                f"Task to migrate {i}",
                metadata={"index": i, "source": "filesystem"}
            )
            task.update_status(TaskStatus.COMPLETED)
            tasks_data.append({
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "metadata": task.metadata
            })
        
        # Create database storage
        db_path = temp_data_dir / "migrated.db"
        db_storage = DatabaseStorage(f"sqlite:///{db_path}")
        
        # Migrate tasks
        for task_data in fs_tracker.get_tasks():
            db_storage.create_task(
                task_data.name,
                task_data.description,
                task_data.metadata,
                task_data.parent_id
            )
            
            # Update status to match
            db_tasks = db_storage.get_tasks()
            latest_task = db_tasks[-1]
            latest_task.status = task_data.status
            latest_task.started_at = task_data.started_at
            latest_task.completed_at = task_data.completed_at
            db_storage.update_task(latest_task)
        
        # Verify migration
        db_tracker = TaskTracker(storage=db_storage)
        migrated_tasks = db_tracker.get_tasks()
        assert len(migrated_tasks) == 5
        
        for i, task in enumerate(migrated_tasks):
            assert task.name == f"Migration Task {i}"
            assert task.metadata["source"] == "filesystem"
            assert task.status == TaskStatus.COMPLETED
    
    def test_storage_with_workflow_execution(
        self, simple_workflow: WorkflowGraph, temp_data_dir: Path
    ):
        """Test storage backends during actual workflow execution."""
        # Test with filesystem storage
        fs_storage = FileSystemStorage(temp_data_dir / "workflow_fs_storage")
        fs_tracker = TaskTracker(storage=fs_storage)
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow with filesystem tracking
        fs_result = runner.run(simple_workflow, tracker=fs_tracker)
        
        # Verify tasks were stored
        fs_tasks = fs_tracker.get_tasks()
        assert len(fs_tasks) == len(simple_workflow.graph.nodes())
        
        # Test with database storage
        db_storage = DatabaseStorage(f"sqlite:///{temp_data_dir}/workflow_tasks.db")
        db_tracker = TaskTracker(storage=db_storage)
        
        # Execute same workflow with database tracking
        db_result = runner.run(simple_workflow, tracker=db_tracker)
        
        # Verify tasks were stored
        db_tasks = db_tracker.get_tasks()
        assert len(db_tasks) == len(simple_workflow.graph.nodes())
        
        # Compare storage results
        assert len(fs_tasks) == len(db_tasks)
    
    def test_storage_search_capabilities(self, temp_data_dir: Path):
        """Test advanced search capabilities of storage backends."""
        # Use database storage for advanced queries
        db_storage = DatabaseStorage(f"sqlite:///{temp_data_dir}/search_test.db")
        tracker = TaskTracker(storage=db_storage)
        
        # Create tasks with various attributes
        now = datetime.now()
        
        # Create completed tasks
        for i in range(3):
            task = tracker.create_task(
                f"Completed Task {i}",
                f"Completed task {i}",
                metadata={"priority": "high", "category": "processing"}
            )
            task.update_status(TaskStatus.IN_PROGRESS)
            time.sleep(0.01)
            task.update_status(TaskStatus.COMPLETED)
        
        # Create failed tasks
        for i in range(2):
            task = tracker.create_task(
                f"Failed Task {i}",
                f"Failed task {i}",
                metadata={"priority": "low", "category": "validation"}
            )
            task.update_status(TaskStatus.IN_PROGRESS)
            task.update_status(TaskStatus.FAILED, error=f"Error {i}")
        
        # Create pending tasks
        for i in range(2):
            task = tracker.create_task(
                f"Pending Task {i}",
                f"Pending task {i}",
                metadata={"priority": "medium", "category": "processing"}
            )
        
        # Test various search queries
        
        # By status
        completed = tracker.search_tasks(status=TaskStatus.COMPLETED)
        assert len(completed) == 3
        
        failed = tracker.search_tasks(status=TaskStatus.FAILED)
        assert len(failed) == 2
        
        # By metadata
        high_priority = tracker.search_tasks(
            metadata_filter={"priority": "high"}
        )
        assert len(high_priority) == 3
        
        processing_tasks = tracker.search_tasks(
            metadata_filter={"category": "processing"}
        )
        assert len(processing_tasks) == 5
        
        # By time range
        recent_tasks = tracker.search_tasks(
            started_after=now - timedelta(minutes=1)
        )
        assert len(recent_tasks) >= 5  # At least the completed and failed tasks
        
        # Combined filters
        failed_validation = tracker.search_tasks(
            status=TaskStatus.FAILED,
            metadata_filter={"category": "validation"}
        )
        assert len(failed_validation) == 2
    
    def test_storage_performance(self, temp_data_dir: Path, large_dataset: Path):
        """Test storage performance with large numbers of tasks."""
        import time
        
        # Test filesystem storage performance
        fs_storage = FileSystemStorage(temp_data_dir / "perf_fs")
        fs_tracker = TaskTracker(storage=fs_storage)
        
        fs_start = time.time()
        
        # Create many tasks
        for i in range(1000):
            task = fs_tracker.create_task(
                f"Perf Task {i}",
                f"Performance test task {i}",
                metadata={"batch": i // 100, "index": i}
            )
            if i % 3 == 0:
                task.update_status(TaskStatus.COMPLETED)
            elif i % 3 == 1:
                task.update_status(TaskStatus.IN_PROGRESS)
        
        fs_create_time = time.time() - fs_start
        
        # Test retrieval performance
        fs_start = time.time()
        all_fs_tasks = fs_tracker.get_tasks()
        fs_retrieve_time = time.time() - fs_start
        
        # Test database storage performance
        db_storage = DatabaseStorage(f"sqlite:///{temp_data_dir}/perf_test.db")
        db_tracker = TaskTracker(storage=db_storage)
        
        db_start = time.time()
        
        # Create same tasks in database
        for i in range(1000):
            task = db_tracker.create_task(
                f"Perf Task {i}",
                f"Performance test task {i}",
                metadata={"batch": i // 100, "index": i}
            )
            if i % 3 == 0:
                task.update_status(TaskStatus.COMPLETED)
            elif i % 3 == 1:
                task.update_status(TaskStatus.IN_PROGRESS)
        
        db_create_time = time.time() - db_start
        
        # Test retrieval performance
        db_start = time.time()
        all_db_tasks = db_tracker.get_tasks()
        db_retrieve_time = time.time() - db_start
        
        # Verify both storages have same data
        assert len(all_fs_tasks) == 1000
        assert len(all_db_tasks) == 1000
        
        # Log performance metrics
        print(f"Filesystem - Create: {fs_create_time:.3f}s, Retrieve: {fs_retrieve_time:.3f}s")
        print(f"Database - Create: {db_create_time:.3f}s, Retrieve: {db_retrieve_time:.3f}s")
        
        # Database should generally be faster for retrieval with large datasets
        assert db_retrieve_time < fs_retrieve_time * 2  # Allow some variance
    
    def test_storage_backup_and_restore(self, temp_data_dir: Path):
        """Test backup and restore functionality."""
        # Create original storage with tasks
        original_path = temp_data_dir / "original_storage"
        original_storage = FileSystemStorage(original_path)
        tracker = TaskTracker(storage=original_storage)
        
        # Create test tasks
        task_ids = []
        for i in range(5):
            task = tracker.create_task(
                f"Backup Task {i}",
                f"Task for backup test {i}",
                metadata={"important": True, "backup_test": True}
            )
            task.update_status(TaskStatus.COMPLETED)
            task_ids.append(task.id)
        
        # Create backup
        backup_path = temp_data_dir / "backup"
        backup_path.mkdir(exist_ok=True)
        
        # Simple file-based backup
        import shutil
        shutil.copytree(original_path, backup_path / "storage_backup")
        
        # Simulate data loss - delete some tasks
        for task_file in list(original_path.glob("*.json"))[:2]:
            task_file.unlink()
        
        # Verify some tasks are missing
        remaining_tasks = tracker.get_tasks()
        assert len(remaining_tasks) < 5
        
        # Restore from backup
        restored_path = temp_data_dir / "restored_storage"
        shutil.copytree(backup_path / "storage_backup", restored_path)
        
        # Use restored storage
        restored_storage = FileSystemStorage(restored_path)
        restored_tracker = TaskTracker(storage=restored_storage)
        
        # Verify all tasks are restored
        restored_tasks = restored_tracker.get_tasks()
        assert len(restored_tasks) == 5
        
        for task_id in task_ids:
            task = restored_tracker.get_task(task_id)
            assert task is not None
            assert task.metadata["backup_test"] is True
    
    def test_storage_data_integrity(self, temp_data_dir: Path):
        """Test data integrity features of storage backends."""
        # Test with database storage (better integrity features)
        db_storage = DatabaseStorage(f"sqlite:///{temp_data_dir}/integrity_test.db")
        tracker = TaskTracker(storage=db_storage)
        
        # Create task with all fields
        task = tracker.create_task(
            name="Integrity Test Task",
            description="Testing data integrity",
            metadata={
                "test_string": "value",
                "test_number": 42,
                "test_bool": True,
                "test_list": [1, 2, 3],
                "test_dict": {"nested": "data"}
            },
            parent_id="parent-123"
        )
        
        # Update task multiple times
        task.update_status(TaskStatus.IN_PROGRESS)
        task.update_progress(50)
        task.add_metadata("additional_field", "additional_value")
        task.update_status(TaskStatus.COMPLETED)
        
        task_id = task.id
        
        # Retrieve task and verify all data is intact
        retrieved_task = tracker.get_task(task_id)
        
        assert retrieved_task.name == "Integrity Test Task"
        assert retrieved_task.description == "Testing data integrity"
        assert retrieved_task.parent_id == "parent-123"
        assert retrieved_task.status == TaskStatus.COMPLETED
        assert retrieved_task.progress == 50
        
        # Verify metadata integrity
        assert retrieved_task.metadata["test_string"] == "value"
        assert retrieved_task.metadata["test_number"] == 42
        assert retrieved_task.metadata["test_bool"] is True
        assert retrieved_task.metadata["test_list"] == [1, 2, 3]
        assert retrieved_task.metadata["test_dict"]["nested"] == "data"
        assert retrieved_task.metadata["additional_field"] == "additional_value"
        
        # Verify timestamps
        assert retrieved_task.created_at is not None
        assert retrieved_task.started_at is not None
        assert retrieved_task.completed_at is not None
        assert retrieved_task.updated_at is not None
        
        # Verify data types are preserved
        assert isinstance(retrieved_task.metadata["test_number"], int)
        assert isinstance(retrieved_task.metadata["test_bool"], bool)
        assert isinstance(retrieved_task.metadata["test_list"], list)
        assert isinstance(retrieved_task.metadata["test_dict"], dict)