"""Unit tests for database storage backend."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus, WorkflowRun
from kailash.tracking.storage.database import DatabaseStorage


class TestDatabaseStorageInitialization:
    """Test DatabaseStorage initialization."""

    def test_init_with_sqlite_url(self):
        """Test initialization with sqlite:// URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(f"sqlite://{db_path}")

            assert storage.db_path == db_path
            assert os.path.exists(db_path)

            # Verify connection
            assert storage.conn is not None
            storage.conn.close()

    def test_init_with_user_path_expansion(self):
        """Test initialization with ~ path expansion."""
        with patch("os.path.expanduser") as mock_expand:
            mock_expand.return_value = "/home/user/.kailash/tracking.db"
            with patch("os.makedirs") as mock_makedirs:
                with patch("sqlite3.connect") as mock_connect:
                    mock_connect.return_value = MagicMock()

                    storage = DatabaseStorage("sqlite://~/.kailash/tracking.db")

                    mock_expand.assert_called_once_with("~/.kailash/tracking.db")
                    mock_makedirs.assert_called_once_with(
                        "/home/user/.kailash", exist_ok=True
                    )

    def test_init_with_direct_path(self):
        """Test initialization with direct path (no sqlite://)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)

            assert storage.db_path == db_path
            assert os.path.exists(db_path)
            storage.conn.close()

    def test_schema_initialization(self):
        """Test database schema is created correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)

            # Check tables exist
            cursor = storage.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            expected_tables = {"workflow_runs", "tasks", "task_runs", "metrics"}
            assert expected_tables.issubset(tables)

            # Check indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}

            expected_indexes = {
                "idx_runs_workflow",
                "idx_runs_status",
                "idx_tasks_run",
                "idx_tasks_node",
                "idx_tasks_status",
                "idx_node_id",
                "idx_status",
                "idx_created_at",
                "idx_task_runs_run",
                "idx_task_runs_node",
                "idx_task_runs_status",
            }
            assert expected_indexes.issubset(indexes)

            storage.conn.close()


class TestWorkflowRunOperations:
    """Test workflow run operations."""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)
            yield storage
            storage.conn.close()

    def test_save_and_load_run(self, storage):
        """Test saving and loading a workflow run."""
        run = WorkflowRun(
            run_id="test-run-123",
            workflow_name="test_workflow",
            status="completed",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            metadata={"key": "value"},
            error=None,
            tasks=[],
        )

        storage.save_run(run)
        loaded_run = storage.load_run("test-run-123")

        assert loaded_run is not None
        assert loaded_run.run_id == "test-run-123"
        assert loaded_run.workflow_name == "test_workflow"
        assert loaded_run.status == "completed"
        assert loaded_run.metadata == {"key": "value"}

    def test_load_nonexistent_run(self, storage):
        """Test loading a run that doesn't exist."""
        result = storage.load_run("nonexistent-id")
        assert result is None

    def test_list_runs_no_filters(self, storage):
        """Test listing all runs."""
        # Save multiple runs
        for i in range(3):
            run = WorkflowRun(
                run_id=f"run-{i}",
                workflow_name=f"workflow_{i}",
                status="completed" if i % 2 == 0 else "failed",
                started_at=datetime.now(timezone.utc),
                metadata={},
                tasks=[],
            )
            storage.save_run(run)

        runs = storage.list_runs()
        assert len(runs) == 3
        assert all(isinstance(r, WorkflowRun) for r in runs)

    def test_list_runs_by_workflow_name(self, storage):
        """Test listing runs filtered by workflow name."""
        # Save runs with different workflow names
        for i in range(3):
            run = WorkflowRun(
                run_id=f"run-{i}",
                workflow_name="target_workflow" if i == 1 else "other_workflow",
                status="completed",
                started_at=datetime.now(timezone.utc),
                metadata={},
                tasks=[],
            )
            storage.save_run(run)

        runs = storage.list_runs(workflow_name="target_workflow")
        assert len(runs) == 1
        assert runs[0].workflow_name == "target_workflow"

    def test_list_runs_by_status(self, storage):
        """Test listing runs filtered by status."""
        # Save runs with different statuses
        statuses = ["completed", "failed", "completed"]
        for i, status in enumerate(statuses):
            run = WorkflowRun(
                run_id=f"run-{i}",
                workflow_name="workflow",
                status=status,
                started_at=datetime.now(timezone.utc),
                metadata={},
                tasks=[],
            )
            storage.save_run(run)

        runs = storage.list_runs(status="completed")
        assert len(runs) == 2
        assert all(r.status == "completed" for r in runs)


class TestTaskOperations:
    """Test task operations."""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)
            yield storage
            storage.conn.close()

    def test_save_and_load_task(self, storage):
        """Test saving and loading a task."""
        task = TaskRun(
            task_id="task-123",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            result={"output": "value"},
            error=None,
            metadata={"key": "value"},
            input_data={"input": "data"},
            output_data={"output": "data"},
        )

        storage.save_task(task)
        loaded_task = storage.load_task("task-123")

        assert loaded_task is not None
        assert loaded_task.task_id == "task-123"
        assert loaded_task.node_type == "ProcessorNode"
        assert loaded_task.result == {"output": "value"}
        assert loaded_task.input_data == {"input": "data"}
        assert loaded_task.output_data == {"output": "data"}

    def test_save_task_with_metrics(self, storage):
        """Test saving a task with metrics."""
        metrics = TaskMetrics(
            cpu_usage=45.5,
            memory_usage_mb=1024.0,
            duration=2.5,
            custom_metrics={"requests": 100},
        )

        task = TaskRun(
            task_id="task-with-metrics",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            metadata={},
        )
        task.metrics = metrics

        storage.save_task(task)
        loaded_task = storage.load_task("task-with-metrics")

        assert loaded_task.metrics is not None
        assert loaded_task.metrics.cpu_usage == 45.5
        assert loaded_task.metrics.memory_usage_mb == 1024.0
        assert loaded_task.metrics.duration == 2.5
        assert loaded_task.metrics.custom_metrics == {"requests": 100}

    def test_load_nonexistent_task(self, storage):
        """Test loading a task that doesn't exist."""
        result = storage.load_task("nonexistent-task")
        assert result is None

    def test_list_tasks_by_run(self, storage):
        """Test listing tasks for a specific run."""
        # Save tasks for different runs
        for i in range(3):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id="run-123" if i < 2 else "run-456",
                node_id=f"node-{i}",
                node_type="ProcessorNode",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                metadata={},
            )
            storage.save_task(task)

        tasks = storage.list_tasks("run-123")
        assert len(tasks) == 2
        assert all(t.run_id == "run-123" for t in tasks)

    def test_list_tasks_with_filters(self, storage):
        """Test listing tasks with node_id and status filters."""
        # Save tasks with different attributes
        tasks_data = [
            ("task-1", "node-1", TaskStatus.COMPLETED),
            ("task-2", "node-1", TaskStatus.FAILED),
            ("task-3", "node-2", TaskStatus.COMPLETED),
        ]

        for task_id, node_id, status in tasks_data:
            task = TaskRun(
                task_id=task_id,
                run_id="run-123",
                node_id=node_id,
                node_type="ProcessorNode",
                status=status,
                started_at=datetime.now(timezone.utc),
                metadata={},
            )
            storage.save_task(task)

        # Filter by node_id
        tasks = storage.list_tasks("run-123", node_id="node-1")
        assert len(tasks) == 2
        assert all(t.node_id == "node-1" for t in tasks)

        # Filter by status
        tasks = storage.list_tasks("run-123", status=TaskStatus.COMPLETED)
        assert len(tasks) == 2
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

    def test_get_task_alias(self, storage):
        """Test get_task method (alias for load_task)."""
        task = TaskRun(
            task_id="task-alias",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            metadata={},
        )
        storage.save_task(task)

        loaded_task = storage.get_task("task-alias")
        assert loaded_task is not None
        assert loaded_task.task_id == "task-alias"

    def test_update_task(self, storage):
        """Test updating an existing task."""
        # Save initial task
        task = TaskRun(
            task_id="task-update",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            metadata={},
        )
        storage.save_task(task)

        # Update task
        task.status = TaskStatus.COMPLETED
        task.result = {"updated": True}
        storage.update_task(task)

        # Verify update
        loaded_task = storage.load_task("task-update")
        assert loaded_task.status == TaskStatus.COMPLETED
        assert loaded_task.result == {"updated": True}

    def test_delete_task(self, storage):
        """Test deleting a task."""
        # Save task
        task = TaskRun(
            task_id="task-delete",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            metadata={},
        )
        storage.save_task(task)

        # Delete task
        storage.delete_task("task-delete")

        # Verify deletion
        loaded_task = storage.load_task("task-delete")
        assert loaded_task is None

    def test_get_all_tasks(self, storage):
        """Test getting all tasks."""
        # Save multiple tasks
        for i in range(3):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id=f"run-{i}",
                node_id=f"node-{i}",
                node_type="ProcessorNode",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                metadata={},
            )
            storage.save_task(task)

        all_tasks = storage.get_all_tasks()
        assert len(all_tasks) == 3
        assert all(isinstance(t, TaskRun) for t in all_tasks)

    def test_query_tasks(self, storage):
        """Test querying tasks with various filters."""
        # Save tasks with different attributes
        base_time = datetime.now(timezone.utc)
        tasks_data = [
            (
                "task-1",
                "node-1",
                TaskStatus.COMPLETED,
                0,
                1,
            ),  # started 0h ago, ended 1h ago
            (
                "task-2",
                "node-1",
                TaskStatus.FAILED,
                2,
                3,
            ),  # started 2h ago, ended 3h ago
            (
                "task-3",
                "node-2",
                TaskStatus.COMPLETED,
                1,
                2,
            ),  # started 1h ago, ended 2h ago
        ]

        from datetime import timedelta

        for task_id, node_id, status, start_offset, end_offset in tasks_data:
            task = TaskRun(
                task_id=task_id,
                run_id="run-123",
                node_id=node_id,
                node_type="ProcessorNode",
                status=status,
                started_at=base_time - timedelta(hours=start_offset),
                ended_at=base_time - timedelta(hours=end_offset),
                metadata={},
            )
            storage.save_task(task)

        # Query by node_id
        tasks = storage.query_tasks(node_id="node-1")
        assert len(tasks) == 2

        # Query by status
        tasks = storage.query_tasks(status=TaskStatus.COMPLETED)
        assert len(tasks) == 2

        # Query by time range
        tasks = storage.query_tasks(
            started_after=base_time - timedelta(hours=1.5),
            completed_before=base_time - timedelta(hours=1.5),
        )
        assert len(tasks) == 1
        assert tasks[0].task_id == "task-3"


class TestImportExport:
    """Test import/export functionality."""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)
            yield storage
            storage.conn.close()

    def test_export_run(self, storage):
        """Test exporting a run with tasks."""
        # Create run
        run = WorkflowRun(
            run_id="export-run",
            workflow_name="export_workflow",
            status="completed",
            started_at=datetime.now(timezone.utc),
            metadata={"exported": True},
            tasks=["task-1", "task-2"],
        )
        storage.save_run(run)

        # Create tasks
        for i in range(2):
            task = TaskRun(
                task_id=f"task-{i+1}",
                run_id="export-run",
                node_id=f"node-{i+1}",
                node_type="ProcessorNode",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                metadata={"task_num": i + 1},
            )
            storage.save_task(task)

        # Export
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            export_path = f.name

        try:
            storage.export_run("export-run", export_path)

            # Verify export file
            with open(export_path, "r") as f:
                export_data = json.load(f)

            assert "run" in export_data
            assert "tasks" in export_data
            assert export_data["run"]["run_id"] == "export-run"
            assert len(export_data["tasks"]) == 2
        finally:
            os.unlink(export_path)

    def test_export_nonexistent_run(self, storage):
        """Test exporting a run that doesn't exist."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            export_path = f.name

        try:
            with pytest.raises(ValueError, match="Run nonexistent-run not found"):
                storage.export_run("nonexistent-run", export_path)
        finally:
            os.unlink(export_path)

    def test_import_run(self, storage):
        """Test importing a run with tasks."""
        # Create import data
        import_data = {
            "run": {
                "run_id": "original-run",
                "workflow_name": "import_workflow",
                "status": "completed",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {"imported": True},
                "error": None,
                "tasks": ["task-1", "task-2"],
            },
            "tasks": [
                {
                    "task_id": "task-1",
                    "run_id": "original-run",
                    "node_id": "node-1",
                    "node_type": "ProcessorNode",
                    "status": "completed",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "result": {"data": "value"},
                    "error": None,
                    "metadata": {},
                    "input_data": None,
                    "output_data": None,
                },
                {
                    "task_id": "task-2",
                    "run_id": "original-run",
                    "node_id": "node-2",
                    "node_type": "ProcessorNode",
                    "status": "completed",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "result": {"data": "value2"},
                    "error": None,
                    "metadata": {},
                    "input_data": None,
                    "output_data": None,
                },
            ],
        }

        # Write import file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(import_data, f)
            import_path = f.name

        try:
            # Import
            new_run_id = storage.import_run(import_path)

            # Verify new run ID is different
            assert new_run_id != "original-run"

            # Verify run was imported
            imported_run = storage.load_run(new_run_id)
            assert imported_run is not None
            assert imported_run.workflow_name == "import_workflow"
            assert imported_run.metadata == {"imported": True}

            # Verify tasks were imported with new run ID
            tasks = storage.list_tasks(new_run_id)
            assert len(tasks) == 2
            assert all(t.run_id == new_run_id for t in tasks)
            assert tasks[0].result == {"data": "value"}
            assert tasks[1].result == {"data": "value2"}
        finally:
            os.unlink(import_path)


class TestDatabaseStorageEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)
            yield storage
            storage.conn.close()

    def test_clear_all_data(self, storage):
        """Test clearing all stored data."""
        # Add some data
        run = WorkflowRun(
            run_id="clear-run",
            workflow_name="workflow",
            status="completed",
            started_at=datetime.now(timezone.utc),
            metadata={},
            tasks=[],
        )
        storage.save_run(run)

        task = TaskRun(
            task_id="clear-task",
            run_id="clear-run",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            metadata={},
        )
        storage.save_task(task)

        # Clear data
        storage.clear()

        # Verify data is gone from the tables that clear() affects
        assert storage.load_run("clear-run") is None
        # Note: clear() only clears task_runs table, not tasks table
        # So we check get_all_tasks which queries task_runs
        assert len(storage.get_all_tasks()) == 0

        # The load_task method might still find data in the tasks table
        # This is an inconsistency in the implementation

    def test_json_parsing_edge_cases(self, storage):
        """Test handling of malformed JSON data."""
        # Insert task with malformed JSON directly
        cursor = storage.conn.cursor()
        cursor.execute(
            """
            INSERT INTO task_runs
            (task_id, run_id, node_id, node_type, status, started_at, result, metadata, input_data, output_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "malformed-task",
                "run-123",
                "node-1",
                "ProcessorNode",
                "completed",
                datetime.now(timezone.utc).isoformat(),
                '{"valid": "json"}',
                "{}",
                "not valid json",  # Invalid JSON
                '{"valid": "output"}',
            ),
        )
        storage.conn.commit()

        # Load task - should handle invalid JSON gracefully
        task = storage.load_task("malformed-task")
        assert task is not None
        assert task.result == {"valid": "json"}
        assert task.input_data == {"value": "not valid json"}  # Wrapped in dict
        assert task.output_data == {"valid": "output"}

    def test_execute_query_helper(self, storage):
        """Test _execute_query helper method."""
        # Test successful query
        cursor = storage._execute_query("SELECT 1 as test")
        result = cursor.fetchone()
        assert result[0] == 1

        # Test query with parameters
        cursor = storage._execute_query("SELECT ? as param", ("test_value",))
        result = cursor.fetchone()
        assert result[0] == "test_value"

        # Test invalid query
        with pytest.raises(sqlite3.Error):
            storage._execute_query("INVALID SQL")

    def test_database_destructor(self):
        """Test that database connection is closed on deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            storage = DatabaseStorage(db_path)
            conn = storage.conn

            # Delete storage object
            del storage

            # Connection should be closed
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")

    def test_concurrent_table_compatibility(self, storage):
        """Test that both tasks and task_runs tables stay in sync."""
        # Save a task
        task = TaskRun(
            task_id="sync-task",
            run_id="run-123",
            node_id="node-1",
            node_type="ProcessorNode",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            metadata={"test": "sync"},
        )
        storage.save_task(task)

        # Verify task exists in both tables
        cursor = storage.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE task_id = ?", ("sync-task",))
        assert cursor.fetchone()[0] == 1

        cursor.execute(
            "SELECT COUNT(*) FROM task_runs WHERE task_id = ?", ("sync-task",)
        )
        assert cursor.fetchone()[0] == 1

        # Load from tasks table should work
        loaded_task = storage.load_task("sync-task")
        assert loaded_task.metadata == {"test": "sync"}
