# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression for issue #1185 — async durable resume short-circuit.

``AsyncLocalRuntime._execute_node_async`` / ``_execute_sync_node_async``
did not short-circuit already-completed nodes on a durable resume; the
sync ``LocalRuntime`` does. So resuming a durable workflow with the same
``idempotency_key`` RE-EXECUTED every node already completed and
checkpointed on the prior run — an idempotency / correctness violation:
node side effects fired twice and the documented "resume from where the
prior run left off" guarantee was silently absent for every async
consumer of ``DurableExecutionEngine`` (the only choice for FastAPI /
Nexus / async-first applications).

These tests exercise the contract end-to-end against a REAL
``DBCheckpointStore`` (SQLite tmp file, NO mocking — Tier 2 per
``rules/testing.md`` § 3-Tier Testing):

* ``test_async_runtime_skips_completed_nodes_on_resume`` — the issue's
  minimal repro. First run completes both nodes; a second run with the
  same ``idempotency_key`` MUST short-circuit both from the checkpoint
  (call counts stay at 1) AND still return the correct final result
  (node_b output present + correct), proving restored outputs flow to
  dependents.
* ``test_async_runtime_partial_resume_runs_only_remaining_node`` — first
  run stops after node_a (node_b raises mid-run); the resume runs ONLY
  node_b (node_a stays at 1, node_b goes 0 -> 1).
* ``test_sync_runtime_resume_short_circuit_unchanged`` — the sync
  ``LocalRuntime`` resume short-circuit is unchanged (the async fix
  reuses the inherited machinery and MUST NOT regress the sync path).

Call counts are observed via a REAL filesystem side effect: each node
body appends one line to a per-node counter file. ``PythonCodeNode``'s
sandbox allowlists ``pathlib`` (no DB drivers), so the marker write is
DB-pool-free; line count == invocation count. A re-executed node body
appends a second line — the exact failure mode the assertion catches.
``PythonCodeNode`` is a sync ``Node``, so under ``AsyncLocalRuntime``'s
W1 wiring it routes through ``_execute_sync_node_async`` (the synthetic
sync-only plan) — the path the fix gates alongside ``_execute_node_async``.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest

from kailash.db.connection import ConnectionManager
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Fixtures — real SQLite-backed checkpoint store + a marker directory
# ---------------------------------------------------------------------------


@pytest.fixture
def marker_dir() -> Path:
    """Fresh temp dir for per-node counter files; cleaned up after."""
    import shutil

    d = Path(tempfile.mkdtemp(prefix="issue_1185_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
async def ckpt_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Real SQLite ConnectionManager (tmp file) for the checkpoint store.

    SQLite tmp file (not ``:memory:``) so the single shared connection
    persists checkpoint rows across the two ``execute(...)`` calls within
    one test — the resume path reads what the first run wrote.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    manager = ConnectionManager(f"sqlite:///{db_path}")
    await manager.initialize()
    try:
        yield manager
    finally:
        await manager.close()
        Path(db_path).unlink(missing_ok=True)


def _count_invocations(marker_dir: Path, node_id: str) -> int:
    """Return how many times *node_id*'s body executed (== line count)."""
    f = marker_dir / f"{node_id}.count"
    if not f.exists():
        return 0
    return len([ln for ln in f.read_text().splitlines() if ln])


def _node_code(node_id: str, marker_dir: Path, *, fail: bool = False) -> str:
    """PythonCodeNode body: append one line to the node's counter file
    (the observable side effect), then either raise or return the node's
    output. node_b consumes ``value`` from node_a and concatenates.

    Uses ``pathlib`` only (allowlisted in PythonCodeNode's sandbox) so
    the side effect never touches a DB driver — line count == call count.
    """
    counter = (marker_dir / f"{node_id}.count").as_posix()
    body = [
        "from pathlib import Path as _P",
        f"_c = _P({counter!r})",
        "with _c.open('a') as _fh:",
        "    _fh.write('x\\n')",
    ]
    if fail:
        body.append("raise RuntimeError('forced stop after node_a (issue #1185)')")
    elif node_id == "node_a":
        body.append("result = {'value': 'a-output'}")
    else:  # node_b — consume predecessor's value, concatenate
        # ``value`` is wired from node_a's result.value; always present
        # when node_b's body runs (node_a is its only predecessor).
        body.append("result = {'value': value + '+b-output'}")
    return "\n".join(body)


def _build_two_node_workflow(marker_dir: Path, *, node_b_fails: bool = False):
    """Two-node DAG: node_a -> node_b. Mirrors the issue's repro shape."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "node_a", {"code": _node_code("node_a", marker_dir)})
    wb.add_node(
        "PythonCodeNode",
        "node_b",
        {"code": _node_code("node_b", marker_dir, fail=node_b_fails)},
    )
    # node_a's result.value -> node_b's `value` input
    wb.add_connection("node_a", "result.value", "node_b", "value")
    return wb.build()


async def _make_engine(ckpt_conn: ConnectionManager):
    """Construct a DurableExecutionEngine wrapping AsyncLocalRuntime with a
    real SQLite-backed DBCheckpointStore (checkpoint_after_each_node=True
    is set by the builder when a checkpoint_store is configured)."""
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore
    from kailash.runtime.durable import DurableExecutionEngine

    store = DBCheckpointStore(ckpt_conn)
    await store.initialize()
    engine = DurableExecutionEngine.builder().checkpoint_store(store).build()
    return engine


def _node_b_value(results: dict) -> str:
    """Extract node_b's ``value`` output from the runtime results dict.

    PythonCodeNode wraps the body's ``result`` under a ``result`` key, so
    the shape is ``results['node_b']['result']['value']``. The restored
    (checkpointed) shape is the serialized tracker output, which for a
    dict output round-trips unchanged.
    """
    out = results["node_b"]
    # Fresh-execution shape: {'result': {'value': ...}}.
    if isinstance(out, dict) and "result" in out and isinstance(out["result"], dict):
        return out["result"]["value"]
    # Restored-from-checkpoint shape: the serialized dict as recorded.
    if isinstance(out, dict) and "value" in out:
        return out["value"]
    raise AssertionError(f"unexpected node_b output shape: {out!r}")


# ---------------------------------------------------------------------------
# Test 1 — the issue's minimal repro
# ---------------------------------------------------------------------------


async def test_async_runtime_skips_completed_nodes_on_resume(
    ckpt_conn: ConnectionManager, marker_dir: Path
):
    """First run completes both nodes; a second run with the same
    idempotency_key MUST short-circuit both from the saved checkpoint.

    Pre-fix: both nodes re-executed (call counts {a:2, b:2}).
    Post-fix: call counts stay {a:1, b:1} AND the resumed run still
    returns the correct final result, proving restored outputs reach
    dependents.
    """
    engine = await _make_engine(ckpt_conn)
    workflow = _build_two_node_workflow(marker_dir)
    key = f"run-{uuid.uuid4().hex[:8]}"

    # First run — completes normally, saves per-node checkpoints.
    results1, _ = await engine.execute(workflow, idempotency_key=key, inputs={})
    assert _node_b_value(results1) == "a-output+b-output"
    assert _count_invocations(marker_dir, "node_a") == 1
    assert _count_invocations(marker_dir, "node_b") == 1

    # Second run — SAME idempotency_key. Checkpoints exist for both nodes.
    # The resume MUST replay cached outputs, NOT re-execute the bodies.
    results2, _ = await engine.execute(workflow, idempotency_key=key, inputs={})

    assert _count_invocations(marker_dir, "node_a") == 1, (
        f"node_a re-executed on resume: "
        f"{_count_invocations(marker_dir, 'node_a')} invocations "
        f"(expected 1) — the async resume short-circuit is not firing."
    )
    assert _count_invocations(marker_dir, "node_b") == 1, (
        f"node_b re-executed on resume: "
        f"{_count_invocations(marker_dir, 'node_b')} invocations "
        f"(expected 1) — the async resume short-circuit is not firing."
    )
    # Restored result still flows to the caller (and to dependents): the
    # final node's output is present and correct after a full short-circuit.
    assert _node_b_value(results2) == "a-output+b-output", (
        "Resumed run did not return node_b's restored output — the "
        "short-circuit dropped the cached result instead of feeding it "
        "to the per-run tracker."
    )


# ---------------------------------------------------------------------------
# Test 2 — partial resume runs only the remaining node
# ---------------------------------------------------------------------------


async def test_async_runtime_partial_resume_runs_only_remaining_node(
    ckpt_conn: ConnectionManager, marker_dir: Path
):
    """First run completes node_a then node_b raises (process "stops"
    after node_a checkpointed). The resume MUST replay node_a from the
    checkpoint (count stays 1) and execute ONLY node_b (0 -> 1).

    This proves the short-circuit is per-node, not all-or-nothing, and
    that node_a's restored output flows to node_b on the resume so node_b
    can complete with the correct concatenated value.
    """
    engine = await _make_engine(ckpt_conn)
    key = f"run-{uuid.uuid4().hex[:8]}"

    # First run — node_b raises after node_a completes + checkpoints.
    failing = _build_two_node_workflow(marker_dir, node_b_fails=True)
    with pytest.raises(Exception):
        await engine.execute(failing, idempotency_key=key, inputs={})

    # node_a completed (1) and checkpointed; node_b ran its body once and
    # raised (its counter incremented before the raise; it was NOT
    # checkpoint-recorded as complete because it errored).
    assert _count_invocations(marker_dir, "node_a") == 1
    node_b_before = _count_invocations(marker_dir, "node_b")

    # Resume with the SAME key, now with a node_b that succeeds.
    good = _build_two_node_workflow(marker_dir, node_b_fails=False)
    results, _ = await engine.execute(good, idempotency_key=key, inputs={})

    # node_a is restored from the checkpoint — its body MUST NOT run again.
    assert _count_invocations(marker_dir, "node_a") == 1, (
        f"node_a re-executed on partial resume: "
        f"{_count_invocations(marker_dir, 'node_a')} (expected 1)."
    )
    # node_b was NOT completed on the prior run, so it executes exactly
    # once more on the resume.
    assert _count_invocations(marker_dir, "node_b") == node_b_before + 1, (
        f"node_b invocation count {_count_invocations(marker_dir, 'node_b')} "
        f"!= {node_b_before + 1} — the resume did not run the one remaining "
        f"node exactly once."
    )
    # node_a's restored output reached node_b on the resume.
    assert _node_b_value(results) == "a-output+b-output"


# ---------------------------------------------------------------------------
# Test 3 — sync LocalRuntime resume short-circuit is unchanged
# ---------------------------------------------------------------------------


async def test_sync_runtime_resume_short_circuit_unchanged(
    ckpt_conn: ConnectionManager, marker_dir: Path
):
    """The async fix reuses the inherited LocalRuntime checkpoint machinery
    and MUST NOT regress the sync path. Run the same two-node workflow
    twice through the sync ``LocalRuntime`` with the same idempotency_key;
    the second run MUST short-circuit both nodes (call counts stay 1).

    ``LocalRuntime.execute(...)`` runs the async pipeline on its own event
    loop, so this test drives the durable-resume context the same way the
    async engine does but through the SYNC runtime entry point.
    """
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore
    from kailash.runtime.local import LocalRuntime

    store = DBCheckpointStore(ckpt_conn)
    await store.initialize()

    workflow = _build_two_node_workflow(marker_dir)
    key = f"run-{uuid.uuid4().hex[:8]}"

    # Context-manager form for deterministic resource cleanup (the bare
    # ``LocalRuntime().execute()`` form emits a DeprecationWarning).
    with LocalRuntime(
        checkpoint_store=store,
        checkpoint_after_each_node=True,
    ) as runtime:
        # First run.
        results1, _ = runtime.execute(workflow, idempotency_key=key)
        assert _node_b_value(results1) == "a-output+b-output"
        assert _count_invocations(marker_dir, "node_a") == 1
        assert _count_invocations(marker_dir, "node_b") == 1

        # Second run — same key. Sync resume short-circuit MUST replay both.
        results2, _ = runtime.execute(workflow, idempotency_key=key)

    assert (
        _count_invocations(marker_dir, "node_a") == 1
    ), "sync LocalRuntime resume short-circuit regressed for node_a"
    assert (
        _count_invocations(marker_dir, "node_b") == 1
    ), "sync LocalRuntime resume short-circuit regressed for node_b"
    assert _node_b_value(results2) == "a-output+b-output"
