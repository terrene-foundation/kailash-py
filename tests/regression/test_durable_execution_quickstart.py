# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2+ regression: README quickstart for the durable-execution trio.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression": every
canonical pipeline the docs teach MUST have a Tier-2+ regression test
executing DOCS-EXACT code against real infrastructure and asserting the
final user-visible outcome.

The canonical W4 quickstart (see
``workspaces/runtime-integration-trio/todos/active/W4-*``) composes the
full durable-execution trio in three lines plus the engine builder:

    from kailash.runtime.durable import DurableExecutionEngine
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore
    from kailash.infrastructure.history_store import PostgresHistoryStore

    engine = (
        DurableExecutionEngine.builder()
            .checkpoint_store(DBCheckpointStore(conn))
            .history_store(PostgresHistoryStore(conn))
            .build()
    )
    results, run_id = await engine.execute(
        workflow.build(), idempotency_key="user-42-prewarm",
    )
    history = await engine.history.get_run_events(run_id)

The kailash-ml W33b "Fake integration via missing handoff field"
incident (see ``rules/zero-tolerance.md`` Rule 2) showed why this test
matters: per-primitive unit tests construct fixtures with exactly the
fields THAT primitive needs and cannot observe a field MISSING from the
A→B handoff. Only the docs-exact composition exercises the handoff
contract end-to-end.

The W4 ``DurableExecutionEngine`` is being implemented in parallel
(branch ``feat/w4-durable-execution-engine``). When W4 has not yet
merged to main, this test skips with an explicit reason — the skip is
the canonical signal per ``rules/testing.md`` § "Tier-1 Conftest Stub"
+ ``rules/test-skip-discipline.md`` (when present) for an
infrastructure-not-yet-shipped gate. Once W4 lands the import succeeds
and the test runs unconditionally; no test-side amendment is needed.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable OR when
W4 has not yet shipped.
"""

from __future__ import annotations

import os
import socket
import uuid
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager
from kailash.workflow.builder import WorkflowBuilder

PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _is_pg_available() -> bool:
    parsed = urlparse(PG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


def _w4_engine_available() -> bool:
    """Return True iff the W4 ``DurableExecutionEngine`` is importable.

    W4 is being implemented in parallel; until the engine lands on
    ``main`` this test skips cleanly. The skip reason is grep-able so
    a post-W4 sweep can confirm coverage flipped from skipped to
    passing.
    """
    try:
        from kailash.runtime.durable import DurableExecutionEngine  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.skipif(
        not _is_pg_available(),
        reason=f"PostgreSQL not available at {PG_URL}",
    ),
    pytest.mark.skipif(
        not _w4_engine_available(),
        reason=(
            "DurableExecutionEngine (W4) not yet on main — "
            "this regression unblocks once "
            "feat/w4-durable-execution-engine merges. "
            "Test SHOULD pass without amendment when W4 lands."
        ),
    ),
]


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    for table in (
        "kailash_checkpoints",
        "workflow_run_events",
        "workflow_runs",
    ):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    yield manager
    for table in (
        "kailash_checkpoints",
        "workflow_run_events",
        "workflow_runs",
    ):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


def _build_quickstart_workflow():
    """Two-node workflow with a connection — minimum shape that
    exercises both per-node checkpoint AND a node-completion event
    in the history store. Mirrors the README's "hello world" durable
    workflow."""
    wb = WorkflowBuilder()
    wb.add_node(
        "PythonCodeNode",
        "compute",
        {"code": "result = {'value': 42}"},
    )
    wb.add_node(
        "PythonCodeNode",
        "double",
        {"code": "result = {'value': value * 2}"},
    )
    wb.add_connection("compute", "result.value", "double", "value")
    return wb.build()


@pytest.mark.regression
async def test_durable_execution_quickstart_executes_end_to_end(
    pg_conn: ConnectionManager,
):
    """Execute the docs-exact quickstart against real Postgres; assert
    the final user-visible outcome (results dict + history rows).

    Per ``rules/testing.md`` § "End-to-End Pipeline Regression": the
    test MUST execute the same code a user would copy from the README
    and assert the outcome a user would see. Anything narrower is a
    primitive test, not a pipeline regression.

    Pinned acceptance:

    1. ``engine.execute(...)`` returns ``(results, run_id)``.
    2. ``results`` contains the final node's output (``double`` -> 84).
    3. ``engine.history.get_run_events(run_id)`` returns at least one row
       per node (the user-visible audit trail).
    """
    # Imports are repeated INSIDE the test body to mirror the README
    # exactly — the test should be a near-verbatim copy of the docs.
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore
    from kailash.infrastructure.history_store import PostgresHistoryStore
    from kailash.runtime.durable import DurableExecutionEngine

    checkpoint_store = DBCheckpointStore(pg_conn)
    await checkpoint_store.initialize()

    history_store = PostgresHistoryStore(pg_conn)
    await history_store.initialize()

    # tenant_id is mandatory at the history-store read surface (cross-tenant
    # reads blocked at store layer per W2 defense-in-depth).  Pass via
    # runtime_kwargs so the runtime carries it through resolve_tenant_id().
    tenant_id = f"quickstart-tenant-{uuid.uuid4().hex[:6]}"

    class _TenantContext:
        def __init__(self, tid: str) -> None:
            self.tenant_id = tid

    engine = (
        DurableExecutionEngine.builder()
        .checkpoint_store(checkpoint_store)
        .history_store(history_store)
        .runtime_kwargs({"user_context": _TenantContext(tenant_id)})
        .build()
    )

    workflow = _build_quickstart_workflow()
    idempotency_key = f"quickstart-{uuid.uuid4().hex[:8]}"

    results, run_id = await engine.execute(
        workflow,
        idempotency_key=idempotency_key,
    )

    # User-visible outcome 1: the final node's output is what the
    # workflow contract promises.
    assert "double" in results, (
        "Quickstart pipeline did not produce the final node's output — "
        "the docs-exact 3-line API silently dropped a node from the "
        "results dict. This is the W33b 'fake integration via missing "
        "handoff field' failure mode."
    )
    assert results["double"]["result"]["value"] == 84

    # User-visible outcome 2: the history store has at least one row
    # per executed node — the audit trail the user expects.
    history = await engine.history.get_run_events(run_id, tenant_id=tenant_id)
    assert len(history) >= 2, (
        f"History store has {len(history)} rows for run_id={run_id}; "
        f"expected at least one row per executed node. The engine's "
        f"on_node_complete wiring may not be reaching history_store."
    )
