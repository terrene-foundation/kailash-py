"""Regression: model-registry worker-thread runtime re-resolution (#1498).

Root cause: ``ModelRegistry._execute_workflow_sync_safe`` decided the runtime
was async (``_is_async`` -> ``isinstance(self.runtime, AsyncLocalRuntime)``,
resolved in the caller's event-loop context), then, inside the worker-thread
offload branch, re-read ``self.runtime`` to build the coroutine
``self.runtime.execute_workflow_async(...)``. ``self.runtime`` is the parent
DataFlow's per-event-loop lazy property: it returns the cached
``AsyncLocalRuntime`` only while a loop is running, and the sync
``LocalRuntime`` singleton otherwise. The worker-thread expression is
evaluated BEFORE ``run_until_complete`` starts the worker loop — a loop-less
context — so ``self.runtime`` re-resolved to the sync ``LocalRuntime``
singleton, which has no ``execute_workflow_async``:

    AttributeError: 'LocalRuntime' object has no attribute 'execute_workflow_async'

Fix: resolve the runtime ONCE in the caller's frame and use that captured
object everywhere (the async check AND the worker-thread coroutine).

Tier-2 — NO MOCKING. Real DataFlow, real file-backed SQLite, real
AsyncLocalRuntime resolution under a running (pytest-asyncio) event loop,
real worker-thread offload.
"""

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1498_sync_safe_executor_offloads_async_runtime(sqlite_file_url):
    """Under a running loop with an async runtime, the registry's sync-safe
    executor offloads to a worker thread WITHOUT re-resolving self.runtime to
    the sync LocalRuntime singleton (the #1498 AttributeError)."""
    db = DataFlow(sqlite_file_url)
    try:
        registry = db._model_registry

        # We are inside pytest-asyncio's running loop, so the parent DataFlow
        # runtime property resolves to an AsyncLocalRuntime — the exact
        # precondition that drove the worker-thread offload branch.
        assert isinstance(
            db.runtime, AsyncLocalRuntime
        ), "precondition: a running loop must resolve an AsyncLocalRuntime"

        # A trivial workflow that reaches runtime.execute_workflow_async.
        wf = WorkflowBuilder()
        wf.add_node(
            "SQLDatabaseNode",
            "probe",
            {
                "connection_string": db.config.database.get_connection_url(
                    db.config.environment
                ),
                "database_type": "sqlite",
                "query": "SELECT 1 AS one",
                "parameters": [],
            },
        )

        # Before the fix this raised AttributeError: 'LocalRuntime' object has
        # no attribute 'execute_workflow_async' from inside the worker thread.
        results, _run_id = registry._execute_workflow_sync_safe(wf)
        assert results is not None
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1498_captured_runtime_survives_loopless_reresolution(
    sqlite_file_url, monkeypatch
):
    """Pin the fix structurally: even if the parent runtime property would
    re-resolve to a sync LocalRuntime in a loop-less context, the sync-safe
    executor must use the async runtime it captured in the caller's frame.

    We force the failure mode by making ``registry.runtime`` return the async
    runtime on the FIRST read (the caller-frame capture) and a sync
    LocalRuntime on any later read (simulating the worker-thread loop-less
    re-resolution). The fix reads it once, so the later sync value is never
    consulted and no AttributeError fires.
    """
    from kailash.runtime import LocalRuntime

    db = DataFlow(sqlite_file_url)
    try:
        registry = db._model_registry
        async_rt = AsyncLocalRuntime()
        sync_rt = LocalRuntime()

        calls = {"n": 0}

        def _flaky_runtime(_self):
            calls["n"] += 1
            # First read (caller-frame capture) -> async; later reads -> sync.
            return async_rt if calls["n"] == 1 else sync_rt

        monkeypatch.setattr(
            type(registry), "runtime", property(_flaky_runtime), raising=True
        )

        wf = WorkflowBuilder()
        wf.add_node(
            "SQLDatabaseNode",
            "probe",
            {
                "connection_string": db.config.database.get_connection_url(
                    db.config.environment
                ),
                "database_type": "sqlite",
                "query": "SELECT 1 AS one",
                "parameters": [],
            },
        )

        # If the executor re-read `self.runtime` in the worker thread it would
        # get sync_rt and AttributeError. The fix captures once -> async_rt.
        results, _run_id = registry._execute_workflow_sync_safe(wf)
        assert results is not None
    finally:
        db.close()
