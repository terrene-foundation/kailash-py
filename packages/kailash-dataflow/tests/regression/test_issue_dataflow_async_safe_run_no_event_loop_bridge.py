"""
Regression test for the asyncio-thread-pool event-loop bridge bug class
closed in kailash-dataflow v0.10.11
(``packages/kailash-dataflow/src/dataflow/migrations/auto_migration_system.py``
lines 40-114 — ARCHITECTURE FIX). Originating issue predates the
v0.10.11 fix; this file preserves the regression assertion per
``rules/testing.md`` § Regression.

Carved out of
``tests/integration/migrations/test_async_safe_run_integration.py::TestRegressionScenarios::test_original_bug_scenario``
during issue #992 (Workstream B-1.5 Shard 1) so the regression
assertion lives in the regression-tier directory where it is
permanent and never deleted.

The dead ``"thread" in error_str`` except arm has been dropped per
``rules/zero-tolerance.md`` Rule 6 (Implement Fully — every branch
must serve a purpose). The architecture fix at
auto_migration_system.py:40-114 makes the live-path branch
(``assert "bug_repro" in results``) the contract this test pins;
the SQLite-threading error arm was an artefact of the pre-fix
behaviour and is no longer the right assertion.
"""

import asyncio

import pytest


@pytest.mark.regression
@pytest.mark.asyncio
async def test_original_bug_scenario():
    """
    Reproduce the original event-loop bridge bug:

    Before the v0.10.11 fix, ``LocalRuntime.execute()`` invoked from
    inside a running event loop (e.g. FastAPI lifespan) raised
    "Task got Future attached to a different loop". The fix routes
    workflow execution through ``_execute_workflow_safe`` so the
    workflow runs on the SAME loop the caller is on. This test
    pins the live-path success contract.
    """
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow.migrations.auto_migration_system import _execute_workflow_safe

    # Simulate being in FastAPI context (event loop running).
    loop = asyncio.get_running_loop()
    assert loop.is_running(), "Test requires running event loop"

    # Pre-fix this would have raised "Task got Future attached to a
    # different loop" because LocalRuntime created a fresh loop
    # inside the already-running outer loop.
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SQLDatabaseNode",
        "bug_repro",
        {
            "connection_string": "sqlite:///:memory:",
            "database_type": "sqlite",
            "query": "SELECT 'no_hang' as result",
        },
    )

    # Live-path success: _execute_workflow_safe returns a results
    # dict containing the bug_repro node's output.
    results, run_id = _execute_workflow_safe(workflow)
    assert "bug_repro" in results
