"""
Phase 0E: SQLite CARE Storage Backend Tests

Tests for the optimized SQLiteStorage implementation with:
- WAL mode and optimal pragmas
- Inlined metrics (no separate table)
- Audit events table for CARE compliance
- Batch insert via executemany()
- Context manager support
- Thread safety with locking
"""

import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kailash.runtime.trust.audit import AuditEvent, AuditEventType
from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus, WorkflowRun
from kailash.tracking.storage.database import SQLiteStorage
from kailash.tracking.storage.deferred import DeferredStorageBackend


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


@pytest.fixture
def sqlite_storage(temp_db_path):
    """Create a SQLiteStorage instance with temp database."""
    storage = SQLiteStorage(temp_db_path)
    yield storage
    storage.close()


class TestSQLiteStorageBasics:
    """Test basic SQLiteStorage operations."""

    def test_sqlite_storage_schema_creation(self, temp_db_path):
        """Verify tables, indexes, pragmas are created correctly."""
        storage = SQLiteStorage(temp_db_path)

        # Check tables exist
        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        assert "workflow_runs" in tables
        assert "tasks" in tables
        assert "audit_events" in tables
        assert "schema_version" in tables

        # Check indexes exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        assert any("idx_workflow_runs_status" in idx for idx in indexes)
        assert any("idx_tasks_status" in idx for idx in indexes)
        assert any("idx_audit_events_type" in idx for idx in indexes)

        storage.close()

    def test_sqlite_storage_wal_mode(self, temp_db_path):
        """Confirm WAL mode is active."""
        storage = SQLiteStorage(temp_db_path)

        cursor = storage.conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        assert mode.upper() == "WAL"
        storage.close()

    def test_sqlite_storage_pragmas(self, temp_db_path):
        """Verify optimal pragmas are set."""
        storage = SQLiteStorage(temp_db_path)

        cursor = storage.conn.cursor()

        # Check synchronous
        cursor.execute("PRAGMA synchronous")
        sync = cursor.fetchone()[0]
        assert sync == 1  # NORMAL

        # Check foreign keys
        cursor.execute("PRAGMA foreign_keys")
        fk = cursor.fetchone()[0]
        assert fk == 1  # ON

        storage.close()

    def test_sqlite_storage_save_and_load_run(self, sqlite_storage):
        """Round-trip WorkflowRun through storage."""
        run = WorkflowRun(
            run_id="run-1",
            workflow_name="test_workflow",
            status="running",
            metadata={"key": "value"},
        )

        sqlite_storage.save_run(run)
        loaded = sqlite_storage.load_run("run-1")

        assert loaded is not None
        assert loaded.run_id == "run-1"
        assert loaded.workflow_name == "test_workflow"
        assert loaded.status == "running"
        assert loaded.metadata == {"key": "value"}

    def test_sqlite_storage_save_and_load_task(self, sqlite_storage):
        """Round-trip TaskRun with metrics through storage."""
        # Create run first (for FK)
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        # Create task with metrics
        task = TaskRun(
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            node_type="HttpRequest",
            status=TaskStatus.COMPLETED,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC) + timedelta(seconds=0.5),
            metrics=TaskMetrics(
                duration=0.5,
                cpu_usage=25.5,
                memory_usage_mb=128.5,
                custom_metrics={"requests": 10},
            ),
        )

        sqlite_storage.save_task(task)
        loaded = sqlite_storage.load_task("task-1")

        assert loaded is not None
        assert loaded.task_id == "task-1"
        assert loaded.node_id == "node-1"
        assert loaded.status == TaskStatus.COMPLETED
        assert loaded.metrics is not None
        assert loaded.metrics.duration == 0.5
        assert loaded.metrics.cpu_usage == 25.5
        assert loaded.metrics.memory_usage_mb == 128.5
        assert loaded.metrics.custom_metrics == {"requests": 10}

    def test_sqlite_storage_batch_insert(self, sqlite_storage):
        """Test executemany() batch insert performance."""
        # Create run first
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        # Create 100 tasks
        tasks = []
        for i in range(100):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id="run-1",
                node_id=f"node-{i}",
                node_type="HttpRequest",
                status=TaskStatus.COMPLETED,
                metrics=TaskMetrics(duration=0.1, cpu_usage=10.0),
            )
            tasks.append(task)

        # Batch insert
        sqlite_storage.save_tasks_batch(tasks)

        # Verify all inserted
        cursor = sqlite_storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]

        assert count == 100

        # Verify metrics are inlined
        cursor.execute(
            "SELECT task_id, metrics_duration, metrics_cpu_usage FROM tasks LIMIT 1"
        )
        row = cursor.fetchone()
        assert row[1] == 0.1
        assert row[2] == 10.0

    def test_sqlite_storage_check_constraints(self, temp_db_path):
        """Verify CHECK constraints reject invalid status."""
        storage = SQLiteStorage(temp_db_path)

        # Create run with invalid status should fail
        cursor = storage.conn.cursor()

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO workflow_runs
                (run_id, workflow_name, status, started_at)
                VALUES (?, ?, ?, ?)
            """,
                ("run-1", "wf", "invalid_status", "2024-01-01T00:00:00"),
            )
            storage.conn.commit()

        storage.close()

    def test_sqlite_storage_foreign_key_enforcement(self, temp_db_path):
        """Verify FK constraints reject orphan tasks."""
        storage = SQLiteStorage(temp_db_path)

        cursor = storage.conn.cursor()

        # Insert task with non-existent run
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO tasks
                (task_id, run_id, node_id, node_type, status)
                VALUES (?, ?, ?, ?, ?)
            """,
                ("task-1", "nonexistent-run", "node-1", "Http", "pending"),
            )
            storage.conn.commit()

        storage.close()

    def test_sqlite_storage_concurrent_read_write(self, sqlite_storage):
        """Test WAL concurrent access with busy_timeout."""
        import threading

        results = {"success": False}

        def writer():
            try:
                run = WorkflowRun(run_id="run-2", workflow_name="wf")
                sqlite_storage.save_run(run)
                results["success"] = True
            except Exception as e:
                results["error"] = str(e)

        # Start writer thread
        thread = threading.Thread(target=writer)
        thread.start()

        # Try to read from main thread
        sqlite_storage.load_run("run-1")

        thread.join()
        assert results["success"]


class TestAuditEvents:
    """Test audit event persistence."""

    def test_sqlite_storage_audit_events(self, sqlite_storage):
        """Persist and query AuditEvent (SPEC-08 canonical shape)."""
        now_iso = datetime.now(UTC).isoformat()
        events = [
            AuditEvent(
                event_id="evt-1",
                timestamp=now_iso,
                actor="agent-1",
                action="workflow_started",
                resource="",
                outcome="success",
                prev_hash="0" * 64,
                hash="a" * 64,
                event_type=AuditEventType.WORKFLOW_START.value,
                trace_id="trace-1",
                workflow_id="run-1",
            ),
            AuditEvent(
                event_id="evt-2",
                timestamp=now_iso,
                actor="agent-1",
                action="node_executed",
                resource="",
                outcome="success",
                prev_hash="0" * 64,
                hash="b" * 64,
                event_type=AuditEventType.NODE_END.value,
                trace_id="trace-1",
                workflow_id="run-1",
                node_id="node-1",
            ),
        ]

        sqlite_storage.save_audit_events(events)

        # Query by trace_id
        found = sqlite_storage.query_audit_events(trace_id="trace-1")
        assert len(found) == 2

        # Query by event_type
        found = sqlite_storage.query_audit_events(
            event_type=AuditEventType.WORKFLOW_START.value
        )
        assert len(found) == 1
        assert found[0]["event_id"] == "evt-1"

        # Query by canonical outcome (legacy "result" kwarg still works)
        found = sqlite_storage.query_audit_events(outcome="success")
        assert len(found) == 2

    def test_sqlite_storage_audit_events_dict_format(self, sqlite_storage):
        """Handle audit events in dict format."""
        events_dict = [
            {
                "event_id": "evt-3",
                "event_type": "workflow_error",
                "timestamp": datetime.now(UTC).isoformat(),
                "trace_id": "trace-2",
                "result": "failure",
                "context": {"error": "test error"},
            }
        ]

        sqlite_storage.save_audit_events(events_dict)

        found = sqlite_storage.query_audit_events(trace_id="trace-2")
        assert len(found) == 1
        assert found[0]["event_type"] == "workflow_error"
        assert found[0]["context"]["error"] == "test error"


class TestDeferredFlush:
    """Test DeferredStorageBackend flush to SQLite."""

    def test_deferred_flush_to_sqlite(self, temp_db_path):
        """DeferredStorageBackend → SQLite round-trip."""
        deferred = DeferredStorageBackend()

        # Create run and tasks in memory
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        deferred.save_run(run)

        for i in range(10):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id="run-1",
                node_id=f"node-{i}",
                node_type="Http",
                status=TaskStatus.COMPLETED,
                metrics=TaskMetrics(duration=0.1),
            )
            deferred.save_task(task)

        # Flush to SQLite
        deferred.flush_to_sqlite(temp_db_path)

        # Verify in database
        storage = SQLiteStorage(temp_db_path)
        loaded_run = storage.load_run("run-1")
        assert loaded_run is not None

        cursor = storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]
        assert count == 10

        storage.close()

    def test_deferred_flush_to_sqlite_empty(self, temp_db_path):
        """No-op when no data."""
        deferred = DeferredStorageBackend()
        deferred.flush_to_sqlite(temp_db_path)  # Should not fail

        # Database should be created but empty
        storage = SQLiteStorage(temp_db_path)
        cursor = storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM workflow_runs")
        count = cursor.fetchone()[0]
        assert count == 0
        storage.close()

    def test_deferred_flush_clears_buffers(self, temp_db_path):
        """Buffers cleared after flush."""
        deferred = DeferredStorageBackend()

        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        deferred.save_run(run)

        assert len(deferred._runs) == 1

        deferred.flush_to_sqlite(temp_db_path)

        assert len(deferred._runs) == 0


class TestStatisticsAndMaintenance:
    """Test statistics and maintenance operations."""

    def test_sqlite_storage_statistics(self, sqlite_storage):
        """Aggregate statistics for CARE reporting."""
        # Create runs
        for i in range(3):
            run = WorkflowRun(
                run_id=f"run-{i}",
                workflow_name="wf",
                status="completed" if i < 2 else "failed",
            )
            sqlite_storage.save_run(run)

        # Create tasks with various statuses
        for i in range(5):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id="run-0",
                node_id=f"node-{i}",
                node_type="Http",
                status=TaskStatus.COMPLETED,
                metrics=TaskMetrics(duration=0.1 * (i + 1)),
            )
            sqlite_storage.save_task(task)

        stats = sqlite_storage.get_statistics()

        assert stats["total_runs"] == 3
        assert stats["total_tasks"] == 5
        assert "tasks_by_status" in stats
        assert stats["tasks_by_status"]["completed"] == 5
        assert stats["avg_task_duration"] is not None
        assert stats["max_task_duration"] is not None

    def test_sqlite_storage_maintenance(self, sqlite_storage):
        """Run ANALYZE and incremental VACUUM."""
        # Create some data
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        # Should not fail
        sqlite_storage.maintenance()

        # Verify data still intact
        loaded = sqlite_storage.load_run("run-1")
        assert loaded is not None


class TestContextManager:
    """Test context manager support."""

    def test_sqlite_storage_context_manager(self, temp_db_path):
        """Proper cleanup on exit."""
        with SQLiteStorage(temp_db_path) as storage:
            run = WorkflowRun(run_id="run-1", workflow_name="wf")
            storage.save_run(run)

        # Verify data persists after close
        storage2 = SQLiteStorage(temp_db_path)
        loaded = storage2.load_run("run-1")
        assert loaded is not None
        storage2.close()


class TestSchemaVersioning:
    """Test schema version tracking."""

    def test_sqlite_storage_migration(self, temp_db_path):
        """Schema versioning."""
        storage = SQLiteStorage(temp_db_path)

        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        version = cursor.fetchone()[0]

        assert version == SQLiteStorage.SCHEMA_VERSION
        storage.close()

    def test_sqlite_storage_schema_idempotent(self, temp_db_path):
        """Multiple instances use same schema."""
        storage1 = SQLiteStorage(temp_db_path)
        storage1.close()

        storage2 = SQLiteStorage(temp_db_path)
        storage2.close()

        # Should not fail or create duplicate schema entries
        storage3 = SQLiteStorage(temp_db_path)
        cursor = storage3.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schema_version")
        count = cursor.fetchone()[0]

        assert count == 1
        storage3.close()


class TestBackwardCompatibility:
    """Test backward compatibility aliases."""

    def test_database_storage_alias(self, temp_db_path):
        """DatabaseStorage alias for SQLiteStorage."""
        from kailash.tracking.storage.database import DatabaseStorage

        # Should be the same class
        assert DatabaseStorage is SQLiteStorage

    def test_backward_compat_apis(self, sqlite_storage):
        """Backward compatibility method aliases."""
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        # Test get_task alias
        task = TaskRun(
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            node_type="Http",
            status=TaskStatus.PENDING,
        )
        sqlite_storage.save_task(task)

        loaded = sqlite_storage.get_task("task-1")  # Alias for load_task
        assert loaded is not None

        # Test get_all_tasks
        all_tasks = sqlite_storage.get_all_tasks()
        assert len(all_tasks) == 1


class TestThreadSafety:
    """Test thread safety with locking."""

    def test_thread_safe_concurrent_saves(self, sqlite_storage):
        """Concurrent saves with locking."""
        import threading

        errors = []

        # Create run once before threads
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        def save_task(task_id):
            try:
                task = TaskRun(
                    task_id=task_id,
                    run_id="run-1",
                    node_id=f"node-{task_id}",
                    node_type="Http",
                    status=TaskStatus.PENDING,
                )
                sqlite_storage.save_task(task)
            except Exception as e:
                errors.append(str(e))

        # Create 10 threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=save_task, args=(f"task-{i}",))
            threads.append(thread)
            thread.start()

        # Wait for all
        for thread in threads:
            thread.join()

        assert len(errors) == 0

        # Verify all tasks saved
        cursor = sqlite_storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        count = cursor.fetchone()[0]
        assert count == 10


class TestQueryFiltering:
    """Test query filtering capabilities."""

    def test_sqlite_storage_query_by_status(self, sqlite_storage):
        """Filter tasks by status."""
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        # Create tasks with different statuses
        for i, status in enumerate(
            [TaskStatus.COMPLETED, TaskStatus.COMPLETED, TaskStatus.FAILED]
        ):
            task = TaskRun(
                task_id=f"task-{i}",
                run_id="run-1",
                node_id=f"node-{i}",
                node_type="Http",
                status=status,
            )
            sqlite_storage.save_task(task)

        # Query by status
        completed = sqlite_storage.query_tasks(status=TaskStatus.COMPLETED)
        assert len(completed) == 2

        failed = sqlite_storage.query_tasks(status=TaskStatus.FAILED)
        assert len(failed) == 1

    def test_sqlite_storage_query_by_time_range(self, sqlite_storage):
        """Filter by timestamp range."""
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        now = datetime.now(UTC)

        # Create task with timestamp
        task = TaskRun(
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            node_type="Http",
            status=TaskStatus.COMPLETED,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        sqlite_storage.save_task(task)

        # Query by time range
        future = now + timedelta(seconds=10)
        found = sqlite_storage.query_tasks(started_after=now)
        assert len(found) == 1

        found = sqlite_storage.query_tasks(started_after=future)
        assert len(found) == 0


class TestDataIntegrity:
    """Test data integrity and ACID properties."""

    def test_sqlite_storage_metrics_roundtrip(self, sqlite_storage):
        """Metrics preserved accurately through storage."""
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        original = TaskRun(
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            node_type="Http",
            status=TaskStatus.COMPLETED,
            metrics=TaskMetrics(
                duration=1.23456,
                cpu_usage=45.67,
                memory_usage_mb=256.789,
                custom_metrics={"value": 42, "nested": {"key": "value"}},
            ),
        )

        sqlite_storage.save_task(original)
        loaded = sqlite_storage.load_task("task-1")

        assert loaded.metrics.duration == original.metrics.duration
        assert loaded.metrics.cpu_usage == original.metrics.cpu_usage
        assert loaded.metrics.memory_usage_mb == original.metrics.memory_usage_mb
        assert loaded.metrics.custom_metrics == original.metrics.custom_metrics

    def test_sqlite_storage_json_fields_roundtrip(self, sqlite_storage):
        """JSON fields preserved accurately."""
        run = WorkflowRun(run_id="run-1", workflow_name="wf")
        sqlite_storage.save_run(run)

        original = TaskRun(
            task_id="task-1",
            run_id="run-1",
            node_id="node-1",
            node_type="Http",
            status=TaskStatus.COMPLETED,
            result={"status": 200, "headers": {"content-type": "application/json"}},
            input_data={"url": "https://example.com", "timeout": 30},
            output_data={"response": "OK", "latency_ms": 123},
            metadata={"retry_count": 2, "custom": "value"},
        )

        sqlite_storage.save_task(original)
        loaded = sqlite_storage.load_task("task-1")

        assert loaded.result == original.result
        assert loaded.input_data == original.input_data
        assert loaded.output_data == original.output_data
        assert loaded.metadata == original.metadata
