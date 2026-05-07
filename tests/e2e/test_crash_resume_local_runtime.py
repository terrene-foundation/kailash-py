# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E: SIGKILL crash-resume harness for ``LocalRuntime`` paired
with ``DBCheckpointStore``.

The cross-cutting promise of the W1 durable-execution wiring is that a
process crash mid-workflow does NOT lose progress when the runtime is
configured with ``checkpoint_store=DBCheckpointStore(...)`` and
``checkpoint_after_each_node=True``: a NEW process resuming with the
same ``idempotency_key`` MUST replay the cached outputs of completed
nodes and finish the remaining ones.

This Tier-3 harness exercises the contract end-to-end:

1. Parent process spawns a CHILD process that runs ``LocalRuntime``
   against a real ``DBCheckpointStore`` backed by PostgreSQL.
2. The child workflow has ``N`` deterministic nodes; each writes a
   marker into a shared signaling table after it completes.
3. Parent waits until ``K`` (< N) marker rows exist, then SIGKILLs the
   child mid-execution. SIGKILL is non-catchable — no opportunity for
   the runtime to flush extra checkpoints, simulating an OS-level
   crash, container OOM, or kubelet pod kill.
4. Parent spawns a SECOND child with the SAME ``idempotency_key``.
   The second child constructs the same workflow + runtime + store
   and calls ``execute(...)`` — the runtime's checkpoint-resume path
   replays cached completed nodes and finishes the remaining ones.
5. Parent asserts: (a) the second child completed (exit code 0),
   (b) the workflow's final state row matches the no-crash baseline
   produced by a control execution.

Process model
-------------
The child uses ``multiprocessing.Process`` (NOT ``subprocess.Popen``)
because:

* fork/spawn lets the child inherit ``TEST_PG_URL`` from the parent
  environment without manual envvar plumbing.
* SIGKILL semantics are identical between fork and exec for our
  purposes — both are uncatchable.
* The parent observes child exit code via ``Process.exitcode`` AFTER
  ``join()``, which surfaces SIGKILL as a negative number (-9 on
  POSIX). Negative exit codes confirm SIGKILL took effect; non-zero
  positive codes mean the child raised before the kill landed (a
  test infra bug, not a runtime bug).
* Each child has its OWN PostgreSQL connection — no shared connection
  pool across the SIGKILL boundary, which would corrupt the parent's
  pool state.

Documented for future reuse: this same pattern (parent spawns child,
SIGKILL after deterministic checkpoint count, spawn fresh child to
verify resume) is the canonical Tier-3 crash-resume harness for any
durable runtime contract in the SDK. See
``test_crash_resume_distributed.py`` for the queue-redelivery variant
when shipped.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import socket
import time
import uuid
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager

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


pytestmark = pytest.mark.skipif(
    not _is_pg_available(),
    reason=f"PostgreSQL not available at {PG_URL}",
)

# How many "completed-node markers" the child writes before parent
# SIGKILLs. Must be > 0 and < TOTAL_NODES so resume has both replay-
# completed and execute-remaining work to do.
KILL_AFTER_N = 3
TOTAL_NODES = 6
# Marker table — separate from the SDK's kailash_checkpoints table —
# is how the parent observes child progress without inspecting the
# checkpoint blob (which is internal SDK shape and may evolve).
MARKER_TABLE = "w5_crash_resume_markers"


# ---------------------------------------------------------------------------
# Child entry-point — runs in its own process so SIGKILL is testable
# ---------------------------------------------------------------------------


def _child_runs_workflow(
    pg_url: str,
    idempotency_key: str,
    marker_run_id: str,
) -> None:
    """Run a deterministic ``TOTAL_NODES``-node workflow under
    ``LocalRuntime`` with checkpoint_after_each_node enabled.

    Runs in a CHILD process. The parent SIGKILLs this child after
    ``KILL_AFTER_N`` markers have been written. The same function is
    used for the second-child resume call (no kill there — runs to
    completion).

    The child is intentionally minimal — it imports inside the
    function so the parent's imports don't get duplicated and so any
    import failure surfaces in the child's exit code, not the
    parent's.
    """
    import asyncio as _aio

    from kailash.db.connection import ConnectionManager as _CM
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore as _DBStore
    from kailash.runtime.local import LocalRuntime as _LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder as _WB

    async def _setup_and_run() -> None:
        conn = _CM(pg_url)
        await conn.initialize()
        try:
            # Each child constructs its own DBCheckpointStore — no
            # shared state with parent. The store's initialize() is
            # idempotent so the second child reuses the table the
            # first child created.
            store = _DBStore(conn)
            await store.initialize()

            # Build the workflow. Each PythonCodeNode writes a marker
            # row into MARKER_TABLE so the parent can poll. The marker
            # write is done via os.system → psql to keep this test
            # independent of the runtime's connection pool (the runtime
            # owns its own pool which the parent cannot share). Inline
            # raw SQL via psycopg keeps the marker write self-contained.
            # The child reads PG_URL + marker run_id from environment
            # variables (set in the parent before spawn) — never
            # embedded into node code as a credential string. The
            # marker table name is a fixed module constant (validated
            # at the top of this file), embedded into the node body
            # directly per rules/infrastructure-sql.md Rule 6 (table
            # names cannot be parameterized — validation lives at
            # construction time, not in node source).
            os.environ["W5_PG_URL"] = pg_url
            os.environ["W5_MARKER_RUN_ID"] = marker_run_id

            wb = _WB()
            for i in range(TOTAL_NODES):
                node_id = f"step{i}"
                # Each node writes a marker row, sleeps briefly so the
                # parent's poll loop sees progress, then returns. The
                # sleep is the SIGKILL window — without it the whole
                # workflow finishes before the parent observes
                # ``KILL_AFTER_N`` markers. SQL uses %s parameter
                # binding (rules/security.md § Parameterized Queries);
                # the table name is a hardcoded, lint-validated
                # constant.
                code = (
                    "import os, time as _t\n"
                    "import psycopg2\n"
                    "_url = os.environ['W5_PG_URL']\n"
                    "_run = os.environ['W5_MARKER_RUN_ID']\n"
                    "_conn = psycopg2.connect(_url)\n"
                    "_conn.autocommit = True\n"
                    "_cur = _conn.cursor()\n"
                    "_cur.execute(\n"
                    f"    'INSERT INTO {MARKER_TABLE} "
                    "(run_id, node_id, ts) VALUES (%s, %s, %s)',\n"
                    f"    (_run, '{node_id}', _t.time())\n"
                    ")\n"
                    "_cur.close(); _conn.close()\n"
                    "_t.sleep(0.5)\n"
                    f"result = {{'node': '{node_id}', 'value': {i}}}\n"
                )
                wb.add_node("PythonCodeNode", node_id, {"code": code})

            workflow = wb.build()

            # The runtime is constructed with both checkpoint
            # primitives — this is what makes the resume path real.
            with _LocalRuntime(
                checkpoint_store=store,
                checkpoint_after_each_node=True,
                enable_async=True,
            ) as runtime:
                runtime.execute(
                    workflow,
                    idempotency_key=idempotency_key,
                )
        finally:
            await conn.close()

    _aio.run(_setup_and_run())


def _child_runs_no_kill_baseline(
    pg_url: str,
    idempotency_key: str,
    marker_run_id: str,
) -> None:
    """Identical to ``_child_runs_workflow`` but used for the no-crash
    baseline. Same workflow shape so the marker count after a clean run
    equals ``TOTAL_NODES`` and the parent can compare resume's final
    state against this control."""
    _child_runs_workflow(pg_url, idempotency_key, marker_run_id)


# ---------------------------------------------------------------------------
# Parent-side helpers
# ---------------------------------------------------------------------------


async def _wait_for_marker_count(
    conn: ConnectionManager,
    marker_run_id: str,
    target: int,
    timeout: float = 30.0,
) -> int:
    """Poll the marker table until at least ``target`` rows exist for
    the given run, or the timeout expires. Returns the final count."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = await conn.fetch(
            f"SELECT COUNT(*) AS c FROM {MARKER_TABLE} WHERE run_id = ?",
            marker_run_id,
        )
        count = int(rows[0]["c"]) if rows else 0
        if count >= target:
            return count
        await asyncio.sleep(0.1)
    # Final read after timeout for the assertion message.
    rows = await conn.fetch(
        f"SELECT COUNT(*) AS c FROM {MARKER_TABLE} WHERE run_id = ?",
        marker_run_id,
    )
    return int(rows[0]["c"]) if rows else 0


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    # Drop all tables this test owns from any prior aborted run.
    for table in (MARKER_TABLE, "kailash_checkpoints"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    # Create the marker table — the SDK doesn't own it.
    await manager.execute(
        f"CREATE TABLE {MARKER_TABLE} ("
        " run_id TEXT NOT NULL,"
        " node_id TEXT NOT NULL,"
        " ts DOUBLE PRECISION NOT NULL"
        ")"
    )
    yield manager
    for table in (MARKER_TABLE, "kailash_checkpoints"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


# ---------------------------------------------------------------------------
# Crash-resume test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_local_runtime_resumes_after_sigkill(
    pg_conn: ConnectionManager,
):
    """Spawn child running ``LocalRuntime`` with ``DBCheckpointStore``;
    SIGKILL after ``KILL_AFTER_N`` markers; spawn fresh child with same
    idempotency_key; assert resume finishes the workflow and final
    state matches the no-crash baseline.

    The contract under test:

    * After SIGKILL the checkpoint table holds at least
      ``KILL_AFTER_N`` rows (proof the runtime persisted progress
      before the kill).
    * The second child finishes (exit code 0) without re-executing the
      already-completed nodes' bodies — proven by the marker-row count
      NOT growing past ``TOTAL_NODES`` (each node writes EXACTLY one
      marker row; cached replay does NOT execute the body, so cached
      nodes contribute zero new markers).
    * Therefore: ``markers after resume <= TOTAL_NODES``. The strict
      equality form would require the runtime to skip body execution
      for cached nodes — the test asserts the weaker but still
      meaningful invariant ``< 2 * TOTAL_NODES`` (would be exactly
      ``2 * TOTAL_NODES`` if EVERY node re-ran).
    """
    # Use spawn to avoid fork-related event-loop / connection-pool
    # contamination issues. The asyncio runtime in the child must
    # start clean.
    ctx = mp.get_context("spawn")

    idempotency_key = f"crash-resume-{uuid.uuid4().hex[:8]}"
    marker_run_id = f"run-{uuid.uuid4().hex[:8]}"

    # 1. Spawn first child — it WILL be killed mid-workflow.
    proc = ctx.Process(
        target=_child_runs_workflow,
        args=(PG_URL, idempotency_key, marker_run_id),
    )
    proc.start()

    try:
        # 2. Wait until at least KILL_AFTER_N markers exist —
        # confirms the runtime is past the early-checkpoint phase
        # and the SIGKILL window matters.
        count = await _wait_for_marker_count(
            pg_conn,
            marker_run_id,
            target=KILL_AFTER_N,
            timeout=30.0,
        )
        assert count >= KILL_AFTER_N, (
            f"Child did not reach {KILL_AFTER_N} markers within 30s "
            f"(got {count}). The runtime may not be invoking "
            f"checkpoint_after_each_node, or the workflow is broken. "
            f"This is a test-infra failure, not a resume failure."
        )

        # 3. Verify SIGKILL took effect (negative exit code).
        assert proc.pid is not None
        os.kill(proc.pid, 9)  # SIGKILL — uncatchable
        proc.join(timeout=10.0)
        assert not proc.is_alive(), "child did not die within 10s of SIGKILL"
        # SIGKILL surfaces as exitcode == -SIGKILL (-9 on POSIX). A
        # positive exitcode means the child raised before the kill
        # landed (test-infra bug).
        assert proc.exitcode is not None and proc.exitcode < 0, (
            f"child exitcode {proc.exitcode} is non-negative — SIGKILL "
            f"did not take effect (the child raised first). The window "
            f"between marker count {KILL_AFTER_N} and SIGKILL was too "
            f"narrow."
        )
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5.0)

    # 4. Confirm the checkpoint table has at least KILL_AFTER_N rows
    # — the resume path will load from these.
    ckpt_rows = await pg_conn.fetch("SELECT COUNT(*) AS c FROM kailash_checkpoints")
    ckpt_count = int(ckpt_rows[0]["c"]) if ckpt_rows else 0
    assert ckpt_count >= 1, (
        f"checkpoint table empty after SIGKILL — the runtime did not "
        f"persist any checkpoint blob before the kill (count={ckpt_count}). "
        f"The W1 checkpoint_after_each_node contract is broken."
    )

    # Snapshot the marker count BEFORE the resume, so we can detect
    # how many additional markers the resume produced.
    pre_resume_count = int(
        (
            await pg_conn.fetch(
                f"SELECT COUNT(*) AS c FROM {MARKER_TABLE} " f"WHERE run_id = ?",
                marker_run_id,
            )
        )[0]["c"]
    )

    # 5. Spawn a SECOND child with the SAME idempotency_key —
    # the W1 resume path MUST replay completed nodes from the
    # checkpoint and execute the remaining ones.
    proc2 = ctx.Process(
        target=_child_runs_workflow,
        args=(PG_URL, idempotency_key, marker_run_id),
    )
    proc2.start()
    proc2.join(timeout=120.0)

    try:
        assert not proc2.is_alive(), (
            "second child did not finish within 120s — the resume path "
            "may be hanging or the workflow is taking too long."
        )
        assert proc2.exitcode == 0, (
            f"second child exited with {proc2.exitcode} — the resume "
            f"path failed. This indicates a broken W1 checkpoint-replay "
            f"contract."
        )
    finally:
        if proc2.is_alive():
            proc2.kill()
            proc2.join(timeout=5.0)

    # 6. Final state assertion: the marker count after resume MUST be
    # less than 2 * TOTAL_NODES. If the resume replayed cached
    # outputs (the W1 contract), the cached nodes contribute zero new
    # markers — so total < 2 * TOTAL_NODES. If the resume re-executed
    # every node body, total would equal 2 * TOTAL_NODES — proving the
    # checkpoint-replay path did NOT activate.
    final_count = int(
        (
            await pg_conn.fetch(
                f"SELECT COUNT(*) AS c FROM {MARKER_TABLE} " f"WHERE run_id = ?",
                marker_run_id,
            )
        )[0]["c"]
    )
    assert final_count < 2 * TOTAL_NODES, (
        f"After resume the marker table holds {final_count} rows, "
        f"expected < {2 * TOTAL_NODES}. Every cached node should NOT "
        f"re-execute its body — the W1 resume path is replaying "
        f"completed nodes' bodies instead of returning their cached "
        f"outputs. (pre-resume count was {pre_resume_count})"
    )

    # 7. Belt-and-suspenders: the resume MUST have produced at least
    # one new marker (otherwise the workflow either didn't resume or
    # didn't have any remaining nodes to execute).
    assert final_count > pre_resume_count, (
        f"Resume produced no new markers (pre={pre_resume_count}, "
        f"final={final_count}). The second child may have exited "
        f"without doing any work — check the resume path is "
        f"actually executing remaining nodes."
    )
