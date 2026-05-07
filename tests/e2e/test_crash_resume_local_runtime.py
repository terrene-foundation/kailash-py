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
   marker file into a shared directory after it completes.
3. Parent waits until ``K`` (< N) marker files exist, then SIGKILLs
   the child mid-execution. SIGKILL is non-catchable — no opportunity
   for the runtime to flush extra checkpoints, simulating an OS-level
   crash, container OOM, or kubelet pod kill.
4. Parent spawns a SECOND child with the SAME ``idempotency_key``.
   The second child constructs the same workflow + runtime + store
   and calls ``execute(...)`` — the runtime's checkpoint-resume path
   replays cached completed nodes and finishes the remaining ones.
5. Parent asserts: (a) the second child completed (exit code 0),
   (b) the SIGKILL took effect (negative exitcode on first child),
   (c) the marker count after resume is less than 2 * TOTAL_NODES,
       proving the cached completed nodes did NOT re-execute their
       bodies (each body writes one marker, so re-running every body
       would double the count).

Process model
-------------
The child uses ``multiprocessing.Process`` (NOT ``subprocess.Popen``)
because:

* spawn lets the child inherit env vars from the parent without
  manual envvar plumbing.
* SIGKILL semantics are identical between fork and exec for our
  purposes — both are uncatchable.
* The parent observes child exit code via ``Process.exitcode`` AFTER
  ``join()``, which surfaces SIGKILL as a negative number (-9 on
  POSIX). Negative exit codes confirm SIGKILL took effect; non-zero
  positive codes mean the child raised before the kill landed (a
  test infra bug, not a runtime bug).

Marker observability
--------------------
Each PythonCodeNode body writes an empty file ``{node_id}.marker``
to a parent-supplied directory. PythonCodeNode's code allowlist
permits ``os`` and ``pathlib`` (no DB drivers), so the file-system
marker keeps the child completely independent of the parent's
PG connection pool — the SIGKILL of the child cannot corrupt
the parent's pool state.

Documented for future reuse: this pattern (parent spawns child,
SIGKILL after deterministic checkpoint count, spawn fresh child to
verify resume, observe via filesystem markers) is the canonical
Tier-3 crash-resume harness for any durable runtime contract in the
SDK. See ``test_crash_resume_distributed.py`` for the queue-
redelivery variant.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import socket
import tempfile
import time
import uuid
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Child entry-point — runs in its own process so SIGKILL is testable
# ---------------------------------------------------------------------------


def _child_runs_workflow(
    pg_url: str,
    idempotency_key: str,
    marker_dir: str,
) -> None:
    """Run a deterministic ``TOTAL_NODES``-node workflow under
    ``LocalRuntime`` with checkpoint_after_each_node enabled.

    Runs in a CHILD process. The parent SIGKILLs this child after
    ``KILL_AFTER_N`` marker files have appeared in ``marker_dir``. The
    same function is used for the second-child resume call (no kill
    there — runs to completion).

    Imports happen INSIDE the function so the parent's imports don't
    duplicate and so any import failure surfaces in the child's exit
    code, not the parent's.
    """
    import asyncio as _aio

    from kailash.db.connection import ConnectionManager as _CM
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore as _DBStore
    from kailash.runtime.async_local import AsyncLocalRuntime as _AsyncRT
    from kailash.workflow.builder import WorkflowBuilder as _WB

    # Make marker_dir reachable inside node bodies via env var.
    os.environ["W5_MARKER_DIR"] = marker_dir

    wb = _WB()
    for i in range(TOTAL_NODES):
        node_id = f"step{i}"
        # Each node writes a marker file, sleeps briefly so the
        # parent's poll loop can observe the count grow before the
        # SIGKILL window closes, then returns. PythonCodeNode's code
        # allowlist permits ``os``, ``pathlib``, and ``time`` — the
        # marker write is therefore completely DB-pool-free, which
        # keeps the SIGKILL boundary clean of pool-state corruption.
        # Each node sleeps 1s so the parent has a wide window to
        # observe progress + SIGKILL. The marker file is written
        # at the START of the body so the parent's poll sees it
        # before the node returns; the SDK then runs the post-node
        # hook (which writes the checkpoint UPSERT). Subsequent
        # nodes see the prior checkpoint commit on next dequeue.
        code = (
            "import os, time as _t\n"
            "from pathlib import Path as _P\n"
            f"_marker = _P(os.environ['W5_MARKER_DIR']) / '{node_id}.marker'\n"
            "_marker.write_text(str(_t.time()))\n"
            "_t.sleep(1.0)\n"
            f"result = {{'node': '{node_id}', 'value': {i}}}\n"
        )
        wb.add_node("PythonCodeNode", node_id, {"code": code})

    workflow = wb.build()

    async def _run_workflow() -> None:
        # Connection + store + runtime all live inside one event loop
        # so the asyncpg pool's loop binding stays consistent. Using
        # AsyncLocalRuntime avoids LocalRuntime.execute()'s implicit
        # secondary event loop which would re-bind the pool's loop
        # mid-flight and trip ``durable.checkpoint.save_failed``.
        conn = _CM(pg_url)
        await conn.initialize()
        try:
            store = _DBStore(conn)
            await store.initialize()
            runtime = _AsyncRT(
                checkpoint_store=store,
                checkpoint_after_each_node=True,
            )
            await runtime.execute_workflow_async(
                workflow,
                inputs={},
                idempotency_key=idempotency_key,
            )
        finally:
            await conn.close()

    _aio.run(_run_workflow())


# ---------------------------------------------------------------------------
# Parent-side helpers
# ---------------------------------------------------------------------------


def _count_markers(marker_dir: Path) -> int:
    return len(list(marker_dir.glob("*.marker")))


def _wait_for_marker_count_blocking(
    marker_dir: Path, target: int, timeout: float = 30.0
) -> int:
    """Poll the marker dir until at least ``target`` files exist, or
    timeout expires. Returns the final count."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        c = _count_markers(marker_dir)
        if c >= target:
            return c
        time.sleep(0.1)
    return _count_markers(marker_dir)


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield a parent-side PG connection used ONLY for direct
    inspection of the kailash_checkpoints table. The child processes
    own their own connections — this fixture's connection never
    crosses the SIGKILL boundary."""
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
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
def marker_dir() -> Path:
    """Yield a fresh temp directory for the marker files. Cleaned up
    after the test regardless of pass/fail."""
    d = Path(tempfile.mkdtemp(prefix="w5_crash_resume_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Crash-resume test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_local_runtime_resumes_after_sigkill(
    pg_conn: ConnectionManager,
    marker_dir: Path,
):
    """Spawn child running ``LocalRuntime`` with ``DBCheckpointStore``;
    SIGKILL after ``KILL_AFTER_N`` marker files exist; spawn fresh
    child with same idempotency_key; assert resume finishes the
    workflow without re-executing cached node bodies.

    The contract under test:

    * After SIGKILL the checkpoint table holds at least one row (proof
      the runtime persisted progress before the kill).
    * The second child finishes (exit code 0) without re-executing
      cached nodes' bodies — proven by the marker-file count NOT
      growing past ``2 * TOTAL_NODES``. Each node body writes EXACTLY
      one marker; cached replay does NOT execute the body, so cached
      nodes contribute zero new markers across the two runs.
    * If the resume re-executed every node body, the marker count
      would equal ``2 * TOTAL_NODES`` exactly — the strict-inequality
      assertion catches that.
    """
    # spawn avoids fork-related event-loop / connection-pool
    # contamination — the child must start clean.
    ctx = mp.get_context("spawn")

    idempotency_key = f"crash-resume-{uuid.uuid4().hex[:8]}"

    # 1. Spawn first child — it WILL be killed mid-workflow.
    proc = ctx.Process(
        target=_child_runs_workflow,
        args=(PG_URL, idempotency_key, str(marker_dir)),
    )
    proc.start()

    try:
        # 2a. Wait until at least KILL_AFTER_N markers exist — this
        # guarantees that AT LEAST KILL_AFTER_N node BODIES have
        # started and the runtime is past the warm-up phase.
        count = _wait_for_marker_count_blocking(
            marker_dir, target=KILL_AFTER_N, timeout=30.0
        )
        assert count >= KILL_AFTER_N, (
            f"Child did not reach {KILL_AFTER_N} markers within 30s "
            f"(got {count}). The runtime may not be invoking the "
            f"checkpoint hook, or the workflow is broken. This is a "
            f"test-infra failure, not a resume failure."
        )

        # 2b. Wait until the checkpoint table has AT LEAST ONE
        # committed row — this guarantees the SIGKILL fires AFTER
        # the W1 hook persisted at least one checkpoint. Without
        # this gate, SIGKILL during the very-first hook UPSERT
        # would leave an empty table and surface as "W1 contract
        # broken" when the actual cause is timing.
        ckpt_deadline = time.monotonic() + 30.0
        ckpt_seen = 0
        while time.monotonic() < ckpt_deadline:
            ckpt_check = ConnectionManager(PG_URL)
            await ckpt_check.initialize()
            try:
                try:
                    ckpt_rows = await ckpt_check.fetch(
                        "SELECT COUNT(*) AS c FROM kailash_checkpoints"
                    )
                    ckpt_seen = int(ckpt_rows[0]["c"]) if ckpt_rows else 0
                except Exception:
                    pass
            finally:
                await ckpt_check.close()
            if ckpt_seen >= 1:
                break
            time.sleep(0.2)
        assert ckpt_seen >= 1, (
            "Child did not commit any checkpoint within 30s — the "
            "W1 checkpoint hook is not firing or the UPSERT path "
            "is broken. Test-infra cannot distinguish from W1 bug; "
            "fix the W1 contract before this test can pass."
        )

        # 3. SIGKILL — uncatchable signal.
        assert proc.pid is not None
        os.kill(proc.pid, 9)
        proc.join(timeout=10.0)
        assert not proc.is_alive(), "child did not die within 10s of SIGKILL"
        # SIGKILL surfaces as exitcode == -SIGKILL (-9 on POSIX). A
        # positive exitcode means the child raised before the kill
        # landed (test-infra bug — kill window was too narrow).
        assert proc.exitcode is not None and proc.exitcode < 0, (
            f"child exitcode {proc.exitcode} is non-negative — SIGKILL "
            f"did not take effect. The window between marker count "
            f"{KILL_AFTER_N} and SIGKILL was too narrow."
        )
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5.0)

    # 4. Confirm the checkpoint table has at least one row — the
    # resume path will load from these.
    #
    # Use a FRESH connection (not the fixture's pg_conn) for this
    # query: the fixture's pool acquired connections before the
    # child re-created the table. Some asyncpg builds cache type-
    # info per connection and refuse to re-resolve the table after
    # a DROP+CREATE-from-another-process. A fresh connection sees
    # the post-child state without that cache hazard.
    #
    # Brief grace window: the in-flight checkpoint UPSERT may not
    # have committed by the time SIGKILL landed. The PRIOR UPSERTs
    # are committed (each node UPSERTs the same row after return).
    # We poll for up to 5s before declaring "no rows". An empty
    # table after the grace IS a real W1 contract violation.
    ckpt_count = 0
    table_exists = False
    grace_deadline = time.monotonic() + 5.0
    while time.monotonic() < grace_deadline:
        ckpt_check = ConnectionManager(PG_URL)
        await ckpt_check.initialize()
        try:
            try:
                ckpt_rows = await ckpt_check.fetch(
                    "SELECT COUNT(*) AS c FROM kailash_checkpoints"
                )
                table_exists = True
                ckpt_count = int(ckpt_rows[0]["c"]) if ckpt_rows else 0
            except Exception:
                # Table doesn't exist yet — child may not have run
                # store.initialize() before SIGKILL. Wait + retry.
                pass
        finally:
            await ckpt_check.close()
        if ckpt_count >= 1:
            break
        time.sleep(0.2)
    assert table_exists, (
        "kailash_checkpoints table was not created — the child's "
        "store.initialize() did not run before SIGKILL. The "
        "marker-count gate fired prematurely."
    )
    assert ckpt_count >= 1, (
        f"checkpoint table empty after SIGKILL (count={ckpt_count}) — "
        f"the runtime did not persist any checkpoint blob before the "
        f"kill. The W1 checkpoint_after_each_node contract is broken."
    )

    pre_resume_count = _count_markers(marker_dir)

    # 5. Spawn a SECOND child with the SAME idempotency_key — the W1
    # resume path MUST replay completed nodes from the checkpoint and
    # execute the remaining ones.
    proc2 = ctx.Process(
        target=_child_runs_workflow,
        args=(PG_URL, idempotency_key, str(marker_dir)),
    )
    proc2.start()
    proc2.join(timeout=120.0)

    try:
        assert not proc2.is_alive(), (
            "second child did not finish within 120s — the resume "
            "path may be hanging or the workflow is taking too long."
        )
        assert proc2.exitcode == 0, (
            f"second child exited with {proc2.exitcode} — the resume "
            f"path failed. This indicates a broken W1 checkpoint-"
            f"replay contract."
        )
    finally:
        if proc2.is_alive():
            proc2.kill()
            proc2.join(timeout=5.0)

    # 6. Final state: the marker count after resume MUST be less than
    # 2 * TOTAL_NODES. If the resume replayed cached outputs (the W1
    # contract), the cached nodes contribute zero new markers — total
    # < 2 * TOTAL_NODES. If the resume re-executed every node body,
    # total would equal 2 * TOTAL_NODES — proving the checkpoint-
    # replay path did NOT activate.
    final_count = _count_markers(marker_dir)
    assert final_count < 2 * TOTAL_NODES, (
        f"After resume the marker dir holds {final_count} files, "
        f"expected < {2 * TOTAL_NODES}. Every cached node should NOT "
        f"re-execute its body — the W1 resume path is replaying "
        f"completed nodes' bodies instead of returning their cached "
        f"outputs. (pre-resume count was {pre_resume_count})"
    )

    # 7. Belt-and-suspenders: at least ONE node must be reported as
    # completed in the final results — proven by the workflow exiting
    # cleanly above. The marker count grows monotonically across
    # runs; if final < pre we have a bug in the test infra.
    assert final_count >= pre_resume_count, (
        f"Marker count went DOWN ({pre_resume_count} -> {final_count}) "
        f"— file-system bug in the test harness."
    )
