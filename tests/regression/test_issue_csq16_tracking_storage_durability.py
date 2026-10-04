"""Real SQLite parent updates preserve persisted tracking state."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus, WorkflowRun
from kailash.tracking.storage.database import SQLiteStorage

pytestmark = pytest.mark.regression


def _seed_related_rows(store):
    run = WorkflowRun(workflow_name="durable-tracking", metadata={"revision": 1})
    store.save_run(run)
    task = TaskRun(run_id=run.run_id, node_id="child", node_type="processor")
    store.save_task(task)
    store.save_audit_events(
        [
            {
                "event_id": "parent-update-audit",
                "event_type": "workflow_started",
                "timestamp": run.started_at.isoformat(),
                "trace_id": run.run_id,
                "outcome": "success",
                "metadata": {"revision": 1},
            }
        ]
    )
    store.upsert_search_attributes(run.run_id, {"region": "sg", "attempt": 1})
    # A fixed historical creation time distinguishes update from replacement
    # without sleeping or relying on SQLite's timestamp precision.
    store.conn.execute(
        "UPDATE workflow_runs SET created_at = ? WHERE run_id = ?",
        ("2001-02-03 04:05:06", run.run_id),
    )
    store.conn.commit()
    return run, task


def _related_snapshot(store, run_id):
    return {
        "tasks": store.conn.execute(
            "SELECT * FROM tasks WHERE run_id = ? ORDER BY task_id", (run_id,)
        ).fetchall(),
        "audit": store.query_audit_events(trace_id=run_id),
        "search": store.conn.execute(
            "SELECT * FROM workflow_search_attributes WHERE run_id = ? ORDER BY attr_name",
            (run_id,),
        ).fetchall(),
    }


def test_manager_run_updates_keep_tasks_after_cache_clear_and_reopen(tmp_path):
    path = str(tmp_path / "tracking.db")
    with SQLiteStorage(path) as store:
        manager = TaskManager(store)
        run_id = manager.create_run("durable-lifecycle")
        task = manager.create_task("child", run_id=run_id)
        manager.clear_cache()
        assert manager.get_task(task.task_id) is not None
        manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        manager.complete_task(task.task_id, {"value": 7})
        manager.update_run_status(run_id, "completed")
        manager.clear_cache()
        assert manager.get_task(task.task_id).output_data == {"value": 7}
        assert manager.get_run(run_id).tasks == [task.task_id]

    with SQLiteStorage(path) as reopened:
        manager = TaskManager(reopened)
        assert manager.get_run(run_id).status == "completed"
        assert manager.get_task(task.task_id).status == TaskStatus.COMPLETED
        assert manager.get_task(task.task_id).output_data == {"value": 7}
        assert manager.get_run_summary(run_id).completed_tasks == 1
        assert reopened.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)


@pytest.mark.parametrize("clear_optional", [False, True])
def test_parent_upsert_preserves_related_rows_and_creation_time(
    tmp_path, clear_optional
):
    path = str(tmp_path / "tracking.db")
    with SQLiteStorage(path) as store:
        run, task = _seed_related_rows(store)
        before = _related_snapshot(store, run.run_id)
        changed = run.model_copy(
            update={
                "workflow_name": "renamed-workflow",
                "status": "failed",
                "started_at": run.started_at + timedelta(seconds=1),
                "ended_at": datetime.now(UTC),
                "metadata": {"revision": 2},
                "error": "ordinary workflow failure",
            }
        )
        store.save_run(changed)
        if clear_optional:
            changed = changed.model_copy(
                update={"ended_at": None, "metadata": {}, "error": None}
            )
            store.save_run(changed)
        assert store.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert store.load_task(task.task_id) is not None
        assert _related_snapshot(store, run.run_id) == before
        assert store.conn.execute(
            "SELECT created_at FROM workflow_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone() == ("2001-02-03 04:05:06",)
        expected = changed.model_dump(exclude={"tasks"})
        assert store.load_run(run.run_id).model_dump(exclude={"tasks"}) == expected

    with SQLiteStorage(path) as reopened:
        assert _related_snapshot(reopened, run.run_id) == before
        assert reopened.load_run(run.run_id).model_dump(exclude={"tasks"}) == expected
        assert reopened.load_run(run.run_id).tasks == [task.task_id]
        assert reopened.search_runs({"region": "sg"})[0]["run_id"] == run.run_id
        assert reopened.conn.execute(
            "SELECT created_at FROM workflow_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone() == ("2001-02-03 04:05:06",)


def test_failed_parent_update_is_atomic_and_next_valid_update_is_durable(tmp_path):
    path = str(tmp_path / "tracking.db")
    with SQLiteStorage(path) as store:
        run, task = _seed_related_rows(store)
        before = _related_snapshot(store, run.run_id)
        parent_before = store.conn.execute(
            "SELECT * FROM workflow_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()
        # Bypass model validation only to reach SQLite's real CHECK constraint.
        invalid = run.model_copy(
            update={"status": "invalid", "workflow_name": "changed"}
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            store.save_run(invalid)
        assert (
            store.conn.execute(
                "SELECT * FROM workflow_runs WHERE run_id = ?", (run.run_id,)
            ).fetchone()
            == parent_before
        )
        assert _related_snapshot(store, run.run_id) == before
        assert store.load_task(task.task_id) is not None
        valid = run.model_copy(update={"metadata": {"revision": 3}})
        store.save_run(valid)

    with SQLiteStorage(path) as reopened:
        assert _related_snapshot(reopened, run.run_id) == before
        assert reopened.load_run(run.run_id).metadata == {"revision": 3}
        assert reopened.load_run(run.run_id).workflow_name == run.workflow_name


def test_parent_upsert_keeps_foreign_key_enforcement_enabled(tmp_path):
    with SQLiteStorage(str(tmp_path / "tracking.db")) as store:
        run, existing = _seed_related_rows(store)
        store.save_run(run)
        orphan = TaskRun(run_id="absent-run", node_id="orphan", node_type="processor")
        with pytest.raises(
            sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"
        ):
            store.save_task(orphan)
        assert store.load_task(orphan.task_id) is None
        assert store.load_task(existing.task_id) is not None
        assert store.conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
