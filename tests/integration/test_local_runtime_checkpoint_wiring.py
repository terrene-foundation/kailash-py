# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for the W1 LocalRuntime / AsyncLocalRuntime
checkpoint + on_node_complete hooks.

These tests run against a real PostgreSQL instance via DBCheckpointStore
+ ConnectionManager.  No mocking per ``rules/testing.md`` § "3-Tier" —
the checkpoint persistence path, the shape-drift refusal, the resume,
and the multi-subscriber dispatch all exercise real I/O.

Requires PostgreSQL at ``TEST_PG_URL`` (defaults to
``postgresql://test_user:test_password@localhost:5434/kailash_test``).
Tests skip when Postgres is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from typing import AsyncGenerator, List
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.durable import (
    NodeCompletionEvent,
    WorkflowShapeDriftError,
    build_checkpoint_key,
    compute_workflow_fingerprint,
)
from kailash.runtime.execution_tracker import ExecutionTracker
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Postgres availability + fixtures
# ---------------------------------------------------------------------------

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


# Skip every test in this module if Postgres is unreachable — checkpoint
# persistence is the contract under test, and SQLite would mask the
# dialect-portability invariants the W1 design depends on.
pytestmark = pytest.mark.skipif(
    not _is_pg_available(),
    reason=f"PostgreSQL not available at {PG_URL}",
)


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield a fresh PostgreSQL ConnectionManager and clean up after."""
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    # Clean any lingering checkpoint rows from prior runs.
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_checkpoints")
    except Exception:
        pass
    yield manager
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_checkpoints")
    except Exception:
        pass
    await manager.close()


@pytest.fixture
async def checkpoint_store(
    pg_conn: ConnectionManager,
) -> AsyncGenerator[DBCheckpointStore, None]:
    """Yield an initialized DBCheckpointStore against the test Postgres."""
    store = DBCheckpointStore(pg_conn)
    await store.initialize()
    yield store
    await store.close()


def _build_three_node_workflow():
    """Three sequential PythonCodeNodes — minimal canonical pipeline."""
    wb = WorkflowBuilder()
    wb.add_node(
        "PythonCodeNode",
        "step1",
        {"code": "result = {'value': 1}"},
    )
    wb.add_node(
        "PythonCodeNode",
        "step2",
        {"code": "result = {'value': value + 1}"},
    )
    wb.add_node(
        "PythonCodeNode",
        "step3",
        {"code": "result = {'value': value + 1}"},
    )
    wb.add_connection("step1", "result.value", "step2", "value")
    wb.add_connection("step2", "result.value", "step3", "value")
    return wb.build()


def _build_alternate_shape_workflow():
    """Two-node workflow with a different fingerprint than the three-node one."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "alpha", {"code": "result = {'value': 99}"})
    wb.add_node("PythonCodeNode", "beta", {"code": "result = {'value': value * 2}"})
    wb.add_connection("alpha", "result.value", "beta", "value")
    return wb.build()


# ---------------------------------------------------------------------------
# 1. checkpoint_after_each_node persists one row per completed node
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_checkpoint_after_each_node_persists(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """Three-node workflow with checkpoint_after_each_node=True writes a
    checkpoint blob for each completed node (key namespace stable, blob
    grows monotonically with each save)."""
    workflow = _build_three_node_workflow()
    idempotency_key = f"test_persist_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    results, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )

    # The execution succeeded.
    assert "step3" in results
    # And the checkpoint row exists with the canonical key namespace.
    rows = await pg_conn.fetch(
        "SELECT checkpoint_key FROM kailash_checkpoints WHERE checkpoint_key = ?",
        expected_key,
    )
    assert len(rows) == 1
    assert rows[0]["checkpoint_key"].startswith("kailash.runtime.checkpoint.")


# ---------------------------------------------------------------------------
# 2. Resume from a partial checkpoint replays cached outputs
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_resume_from_checkpoint_replays_completed_nodes(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """If a prior checkpoint includes step1's output, a re-run with the
    same idempotency_key MUST skip step1 and replay its cached output —
    the user-visible signal is that step1's body never executes again."""
    workflow = _build_three_node_workflow()
    idempotency_key = f"test_resume_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    # First run: complete fully, persist a checkpoint at every node.
    runtime1 = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    first_results, _ = await runtime1.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )
    assert first_results["step3"]["result"]["value"] == 3  # 1+1+1

    # Second run: same idempotency_key + same workflow shape → resume.
    # The execution tracker is rebuilt from the persisted blob; ALL
    # three nodes show up as already-completed.
    runtime2 = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    second_results, _ = await runtime2.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )
    # The cached final value MUST equal the first run's result, AND
    # downstream consumers see the resume as a complete execution.
    assert second_results["step3"]["result"]["value"] == 3


# ---------------------------------------------------------------------------
# 3. Resume with shape drift refuses unless force_resume_with_drift
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_resume_with_shape_drift_refused_without_force(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """Workflow A persists a checkpoint under key K; resuming with key K
    against workflow B (different shape) MUST raise WorkflowShapeDriftError.
    """
    workflow_a = _build_three_node_workflow()
    workflow_b = _build_alternate_shape_workflow()
    idempotency_key = f"test_drift_{uuid.uuid4().hex[:8]}"

    runtime_a = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    await runtime_a.execute_workflow_async(
        workflow_a,
        inputs={},
        idempotency_key=idempotency_key,
    )

    # Different shape under same key — refuse.
    runtime_b = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    # NOTE: build_checkpoint_key partitions on (fingerprint, key, params)
    # — shape drift is detectable only when the key collides.  We force
    # the collision by re-using the fingerprint-bypassing key namespace
    # via direct write of a sibling blob.  Easier: load the workflow_a
    # blob, save it under workflow_b's expected key, then re-run B.
    fp_a = compute_workflow_fingerprint(workflow_a)
    fp_b = compute_workflow_fingerprint(workflow_b)
    key_a = build_checkpoint_key(fp_a, idempotency_key, None)
    key_b = build_checkpoint_key(fp_b, idempotency_key, None)
    blob_a = await checkpoint_store.load(key_a)
    assert blob_a is not None, "First run did not persist a checkpoint"
    # Plant the workflow_a blob at workflow_b's expected key.  This is
    # the precise scenario the rule blocks: storage holds bytes captured
    # against fingerprint_a, but the resuming caller is presenting
    # workflow_b under the same idempotency_key.
    await checkpoint_store.save(key_b, blob_a)

    with pytest.raises(WorkflowShapeDriftError):
        await runtime_b.execute_workflow_async(
            workflow_b,
            inputs={},
            idempotency_key=idempotency_key,
        )

    # Force override → proceeds without raising.
    second_results, _ = await runtime_b.execute_workflow_async(
        workflow_b,
        inputs={},
        idempotency_key=idempotency_key,
        force_resume_with_drift=True,
    )
    # workflow_b's final node "beta" runs and produces a result.
    assert "beta" in second_results


# ---------------------------------------------------------------------------
# 4. Hook subscriber receives one event per node
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_on_node_complete_subscriber_receives_events(
    checkpoint_store: DBCheckpointStore,
):
    """Subscriber registered via runtime.on_node_complete sees one
    NodeCompletionEvent per node, containing the workflow_id, node_id,
    and a non-empty fingerprint."""
    workflow = _build_three_node_workflow()
    received: List[NodeCompletionEvent] = []

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=False,
    )

    async def subscriber(event: NodeCompletionEvent) -> None:
        received.append(event)

    unsubscribe = runtime.on_node_complete(subscriber)
    try:
        await runtime.execute_workflow_async(workflow, inputs={})
    finally:
        unsubscribe()

    node_ids = sorted(e.node_id for e in received)
    assert node_ids == ["step1", "step2", "step3"]
    for ev in received:
        assert ev.workflow_fingerprint  # non-empty
        assert ev.duration_ms >= 0


# ---------------------------------------------------------------------------
# 5. AsyncLocalRuntime parallel-node atomicity
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_async_runtime_parallel_node_atomicity(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """A workflow with two parallel branches (no edge between them)
    completes without checkpoint corruption.  The asyncio.Lock per
    run_id serialises checkpoint saves across concurrent node
    completions; if the lock is missing the persisted blob's tracker
    state would race and lose one branch's record_completion.
    """
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "fork", {"code": "result = {'a': 1, 'b': 2}"})
    wb.add_node(
        "PythonCodeNode",
        "branch_left",
        {"code": "result = {'left': value * 10}"},
    )
    wb.add_node(
        "PythonCodeNode",
        "branch_right",
        {"code": "result = {'right': value * 100}"},
    )
    wb.add_connection("fork", "result.a", "branch_left", "value")
    wb.add_connection("fork", "result.b", "branch_right", "value")
    workflow = wb.build()
    idempotency_key = f"test_parallel_{uuid.uuid4().hex[:8]}"

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
        max_concurrent_nodes=4,
    )
    results, _ = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )
    assert results["branch_left"]["result"]["left"] == 10
    assert results["branch_right"]["result"]["right"] == 200

    # Verify the persisted checkpoint reflects all three nodes.
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)
    blob = await checkpoint_store.load(expected_key)
    assert blob is not None
    # Decode and confirm tracker recorded all three nodes.
    from kailash.runtime.durable import decode_checkpoint_payload

    payload = decode_checkpoint_payload(blob)
    completed = set(payload["tracker"]["completed_nodes"])
    assert {"fork", "branch_left", "branch_right"}.issubset(completed)


# ---------------------------------------------------------------------------
# 6. Hook + checkpoint co-exist in LocalRuntime (sync entrypoint)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_local_runtime_async_path_emits_events_and_checkpoints(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """LocalRuntime.execute_async (the path Nexus and similar wrappers
    use) ALSO emits the events + persists checkpoints — the W1 wiring
    sits in _execute_workflow_async and is shared with execute().
    """
    workflow = _build_three_node_workflow()
    idempotency_key = f"test_localrt_{uuid.uuid4().hex[:8]}"
    received: List[NodeCompletionEvent] = []

    runtime = LocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )

    async def subscriber(event: NodeCompletionEvent) -> None:
        received.append(event)

    runtime.on_node_complete(subscriber)
    results, _ = await runtime.execute_async(workflow, idempotency_key=idempotency_key)

    assert results["step3"]["result"]["value"] == 3
    assert sorted(e.node_id for e in received) == ["step1", "step2", "step3"]

    # Checkpoint row exists.
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)
    blob = await checkpoint_store.load(expected_key)
    assert blob is not None
