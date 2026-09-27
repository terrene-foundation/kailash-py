"""Cancellation must terminate real workflow-run tracking without masking its cause."""

import asyncio
import json
import logging

import pytest

from kailash.nodes.base_async import AsyncNode
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.local import LocalRuntime
from kailash.runtime.progress import ProgressRegistry, _current_progress_registry
from kailash.sdk_exceptions import WorkflowCancelledError
from kailash.tracking import TaskManager
from kailash.tracking.storage.database import SQLiteStorage
from kailash.tracking.storage.deferred import DeferredStorageBackend
from kailash.workflow.graph import Workflow


def cancellation_workflow(kind):
    error = asyncio.CancelledError("private-cancel-state-9732")
    cancellation_token = CancellationToken() if kind == "sdk" else None
    if cancellation_token is not None:
        cancellation_token.cancel("private-cancel-state-9732")

    class CancelNode(AsyncNode):
        def get_parameters(self):
            return {}

        async def async_run(self, **kwargs):
            raise error

    workflow = Workflow("tracking-cancellation", name="tracking-cancellation")
    workflow.add_node("cancel", CancelNode())
    return workflow, error, cancellation_token


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["asyncio", "sdk"])
@pytest.mark.parametrize("tracking", ["provided", "deferred"])
async def test_cancellation_persists_terminal_run(
    tmp_path, monkeypatch, caplog, kind, tracking
):
    workflow, error, cancellation_token = cancellation_workflow(kind)
    storage = SQLiteStorage(str(tmp_path / "provided.db"))
    manager = TaskManager(storage_backend=storage)
    deferred_path = tmp_path / "deferred.db"
    flushed_ids = []
    original_flush = DeferredStorageBackend.flush_to_sqlite

    def flush_to_test_database(self, db_path=None):
        flushed_ids.extend(self._runs)
        return original_flush(self, str(deferred_path))

    monkeypatch.setattr(
        DeferredStorageBackend, "flush_to_sqlite", flush_to_test_database
    )
    previous = ProgressRegistry()
    token = _current_progress_registry.set(previous)
    try:
        with LocalRuntime(enable_audit=True, enable_monitoring=True) as runtime:
            with caplog.at_level(logging.INFO):
                with pytest.raises(
                    asyncio.CancelledError
                    if kind == "asyncio"
                    else WorkflowCancelledError
                ) as caught:
                    await runtime.execute_async(
                        workflow,
                        task_manager=manager if tracking == "provided" else None,
                        cancellation_token=cancellation_token,
                    )
            if kind == "asyncio":
                assert caught.value is error
            else:
                assert "private-cancel-state-9732" in str(caught.value)
            assert _current_progress_registry.get() is previous
            assert runtime._workflow_signals == {}
        if tracking == "provided":
            runs = storage.list_runs()
        else:
            assert len(flushed_ids) == 1
            persisted = SQLiteStorage(str(deferred_path))
            try:
                runs = persisted.list_runs()
            finally:
                persisted.close()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.ended_at >= run.started_at
        assert run.error == str(caught.value)
    finally:
        _current_progress_registry.reset(token)
        storage.close()
    entries = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "audit.runtime_audit"
    ]
    assert [e["event_type"] for e in entries] == [
        "workflow_execution_start",
        "workflow_execution_cancelled",
    ]
    if kind == "sdk":
        assert entries[-1]["data"]["cancelled_at_node"] == "cancel"
        assert entries[-1]["data"]["completed_nodes"] == []
    assert all(
        "private-cancel-state-9732" not in r.getMessage() for r in caplog.records
    )
    assert not any(
        "Failed to persist cancelled workflow status" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["asyncio", "sdk"])
async def test_tracking_failure_preserves_original_cancellation(caplog, kind):
    # Unit fault injection at the public TaskManager seam; no database is mocked.
    secret = "opaque-tracking-storage-error-3917"

    class FailingManager(TaskManager):
        def update_run_status(self, run_id, status, error=None):
            if status == "failed":
                raise RuntimeError(secret)
            return super().update_run_status(run_id, status, error)

    manager = FailingManager(storage_backend=DeferredStorageBackend())
    workflow, error, cancellation_token = cancellation_workflow(kind)
    with LocalRuntime(enable_audit=True, enable_monitoring=False) as runtime:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(
                asyncio.CancelledError if kind == "asyncio" else WorkflowCancelledError
            ) as caught:
                await runtime.execute_async(
                    workflow,
                    task_manager=manager,
                    cancellation_token=cancellation_token,
                )
        if kind == "asyncio":
            assert caught.value is error
        else:
            assert "private-cancel-state-9732" in str(caught.value)
        assert runtime._workflow_signals == {}
    diagnostic = [
        r
        for r in caplog.records
        if "Failed to persist cancelled workflow status" in r.getMessage()
    ]
    assert len(diagnostic) == 1
    assert diagnostic[0].levelno == logging.WARNING
    assert "RuntimeError@" in diagnostic[0].getMessage()
    assert diagnostic[0].exc_info is None
    assert all(secret not in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["asyncio", "sdk", "validation", "denial", "execution"]
)
async def test_error_paths_report_real_deferred_storage_failure(
    tmp_path, monkeypatch, caplog, outcome
):
    from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowValidationError

    invalid_database = tmp_path / "private-database-path-8642"
    invalid_database.mkdir()
    original_flush = DeferredStorageBackend.flush_to_sqlite
    attempts = []
    failures = []

    def real_failed_flush(self, db_path=None):
        attempts.append(len(self._runs))
        try:
            return original_flush(self, str(invalid_database))
        except Exception as failure:
            failures.append(failure)
            raise

    monkeypatch.setattr(DeferredStorageBackend, "flush_to_sqlite", real_failed_flush)
    workflow, cancellation, token = cancellation_workflow(outcome)
    errors = {
        "validation": WorkflowValidationError("private-validation-8642"),
        "denial": PermissionError("private-denial-8642"),
        "execution": RuntimeError("private-execution-8642"),
    }
    error = errors.get(outcome, cancellation)

    class ErrorPathRuntime(LocalRuntime):
        async def _execute_workflow_async(self, *args, **kwargs):
            # Unit fault injection after tracking initialization; persistence
            # below uses the actual SQLite driver and actual failing file path.
            raise error

    runtime_type = LocalRuntime if outcome in ("asyncio", "sdk") else ErrorPathRuntime
    expected_type = (
        WorkflowCancelledError
        if outcome == "sdk"
        else RuntimeExecutionError if outcome == "execution" else type(error)
    )
    with caplog.at_level(logging.WARNING):
        with runtime_type(enable_monitoring=True, enable_audit=True) as runtime:
            with pytest.raises(expected_type) as caught:
                await runtime.execute_async(workflow, cancellation_token=token)
    if outcome == "execution":
        assert caught.value.__cause__ is error
    elif outcome == "sdk":
        assert "private-cancel-state-9732" in str(caught.value)
    else:
        assert caught.value is error
    assert attempts == [1]
    assert len(failures) == 1
    assert type(failures[0]).__name__ == "OperationalError"
    records = [
        r
        for r in caplog.records
        if "Failed to persist deferred tracking data" in r.getMessage()
    ]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "OperationalError@" in records[0].getMessage()
    assert records[0].exc_info is None
    for private in (
        "private-database-path-8642",
        "private-validation-8642",
        "private-denial-8642",
        "private-execution-8642",
        "private-cancel-state-9732",
    ):
        assert all(private not in record.getMessage() for record in records)
