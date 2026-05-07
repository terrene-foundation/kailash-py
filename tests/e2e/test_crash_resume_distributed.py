# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E (STRETCH): SIGKILL crash-resume via SQL queue redelivery.

The W3 ``SQLTaskQueue`` provides visibility-timeout semantics: a worker
that claims a task moves it to ``processing`` status; if the worker
crashes BEFORE calling ``ack(task_id)`` AND the visibility timeout
elapses, the task becomes re-eligible for dequeue by another worker
via ``requeue_stale(...)``.

This stretch test exercises that contract end-to-end:

1. Producer enqueues a single task to ``kailash_task_queue``.
2. Worker A spawns as a child process, dequeues the task (status →
   ``processing``), starts the workflow, then is SIGKILLed before
   ``ack()`` lands.
3. Parent waits for the visibility timeout to elapse, then calls
   ``requeue_stale(...)`` to return the orphaned task to ``pending``.
4. Worker B spawns as a fresh child, dequeues the SAME task (now
   re-eligible), runs to completion, and ``ack()``s it.

The user-visible contract: a queue-driven workflow survives an
arbitrary worker crash WITHOUT operator intervention beyond the
periodic ``requeue_stale`` sweep. The test pins:

* The dequeue + SIGKILL path leaves the task in ``processing``
  (not lost from the queue).
* ``requeue_stale`` returns the task to ``pending`` after the timeout.
* A fresh worker can claim and complete the task — the workflow
  finishes exactly once on the happy path of redelivery.

Process model + SIGKILL pattern: see ``test_crash_resume_local_runtime.py``
for the canonical reference. This file uses the same ``multiprocessing``
+ marker-table observability pattern, with the addition of the queue
state machine.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable. Marked
``@pytest.mark.e2e``.
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
from kailash.infrastructure.task_queue import SQLTaskQueue

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

# Visibility timeout for the test queue. Short enough that the test
# completes quickly, long enough that worker A actually starts running
# before the timeout would fire on its own.
VISIBILITY_TIMEOUT_SEC = 3
MARKER_TABLE = "w5_distributed_markers"


# ---------------------------------------------------------------------------
# Worker child entry-point
# ---------------------------------------------------------------------------


def _worker_dequeues_and_runs(
    pg_url: str,
    queue_name: str,
    worker_id: str,
    marker_run_id: str,
    sleep_before_ack: float,
) -> None:
    """Dequeue ONE task from the queue, write a marker row, sleep
    briefly, then ack.

    Worker A is launched with a long ``sleep_before_ack`` so the
    parent has time to SIGKILL it before ack lands. Worker B is
    launched with sleep=0 so it acks immediately.
    """
    import asyncio as _aio

    from kailash.db.connection import ConnectionManager as _CM
    from kailash.infrastructure.task_queue import SQLTaskQueue as _Queue

    async def _run() -> None:
        conn = _CM(pg_url)
        await conn.initialize()
        try:
            queue = _Queue(
                conn,
                default_visibility_timeout=VISIBILITY_TIMEOUT_SEC,
            )
            await queue.initialize()

            msg = await queue.dequeue(
                queue_name=queue_name,
                worker_id=worker_id,
            )
            if msg is None:
                # No task available — exit non-zero so the parent
                # observes the no-op (queue may be empty if a sibling
                # worker raced us).
                raise RuntimeError(
                    f"worker {worker_id} found no task on queue " f"{queue_name!r}"
                )

            # Write a marker row so the parent can observe progress
            # and which worker handled the task.
            await conn.execute(
                f"INSERT INTO {MARKER_TABLE} "
                "(run_id, worker_id, task_id, ts) "
                "VALUES (?, ?, ?, ?)",
                marker_run_id,
                worker_id,
                msg.task_id,
                time.time(),
            )

            # Optional sleep so the parent can SIGKILL between
            # dequeue and ack — the redelivery scenario.
            if sleep_before_ack > 0:
                await asyncio.sleep(sleep_before_ack)

            await queue.complete(msg.task_id)
        finally:
            await conn.close()

    _aio.run(_run())


# ---------------------------------------------------------------------------
# Parent-side helpers
# ---------------------------------------------------------------------------


async def _enqueue_one_task(
    conn: ConnectionManager,
    queue_name: str,
    task_id: str,
) -> None:
    """Use the SQLTaskQueue API to insert one pending task."""
    queue = SQLTaskQueue(
        conn,
        default_visibility_timeout=VISIBILITY_TIMEOUT_SEC,
    )
    await queue.initialize()
    await queue.enqueue(
        payload={"hello": "world"},
        queue_name=queue_name,
        task_id=task_id,
    )


async def _count_markers(conn: ConnectionManager, marker_run_id: str) -> int:
    rows = await conn.fetch(
        f"SELECT COUNT(*) AS c FROM {MARKER_TABLE} WHERE run_id = ?",
        marker_run_id,
    )
    return int(rows[0]["c"]) if rows else 0


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    for table in (MARKER_TABLE, "kailash_task_queue"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.execute(
        f"CREATE TABLE {MARKER_TABLE} ("
        " run_id TEXT NOT NULL,"
        " worker_id TEXT NOT NULL,"
        " task_id TEXT NOT NULL,"
        " ts DOUBLE PRECISION NOT NULL"
        ")"
    )
    yield manager
    for table in (MARKER_TABLE, "kailash_task_queue"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


# ---------------------------------------------------------------------------
# Distributed crash-resume test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_sql_task_queue_redelivers_after_worker_sigkill(
    pg_conn: ConnectionManager,
):
    """Worker A dequeues, gets SIGKILLed; visibility timeout elapses;
    worker B re-claims the SAME task and completes it.

    The contract under test:

    * After SIGKILL the task row sits in ``processing`` status (not
      lost, not yet acked).
    * After ``requeue_stale(...)`` AND the visibility timeout, the
      task returns to ``pending``.
    * Worker B can dequeue the same task_id and complete it.
    * Two markers exist (one per worker that observed the task);
      worker A wrote a row but did NOT ack, worker B wrote a row AND
      acked. The redelivery happened exactly once.
    """
    ctx = mp.get_context("spawn")

    queue_name = f"q-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    marker_run_id = f"run-{uuid.uuid4().hex[:8]}"

    # 1. Producer enqueues one task.
    await _enqueue_one_task(pg_conn, queue_name, task_id)

    # 2. Worker A: long sleep before ack so SIGKILL has a window.
    worker_a = ctx.Process(
        target=_worker_dequeues_and_runs,
        args=(PG_URL, queue_name, "worker-A", marker_run_id, 30.0),
    )
    worker_a.start()
    try:
        # Wait until worker A has written a marker — proof it
        # dequeued the task and started running.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if await _count_markers(pg_conn, marker_run_id) >= 1:
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail(
                "worker A did not dequeue the task within 15s — "
                "test infra failure, queue not reachable from child"
            )

        # SIGKILL worker A before ack lands.
        assert worker_a.pid is not None
        os.kill(worker_a.pid, 9)
        worker_a.join(timeout=10.0)
        assert not worker_a.is_alive(), "worker A did not die within 10s of SIGKILL"
        assert worker_a.exitcode is not None and worker_a.exitcode < 0, (
            f"worker A exitcode {worker_a.exitcode} is non-negative "
            f"— SIGKILL did not take effect (worker raised first)."
        )
    finally:
        if worker_a.is_alive():
            worker_a.kill()
            worker_a.join(timeout=5.0)

    # 3. Confirm the queue row sits in 'processing' status (not lost).
    rows = await pg_conn.fetch(
        "SELECT status FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1, "task row disappeared after worker A SIGKILL"
    assert rows[0]["status"] == "processing", (
        f"task row status after SIGKILL is {rows[0]['status']!r}; "
        f"expected 'processing'. The queue lost the task or completed "
        f"it without an ack."
    )

    # 4. Wait past the visibility timeout, then sweep stale.
    await asyncio.sleep(VISIBILITY_TIMEOUT_SEC + 1.0)
    queue = SQLTaskQueue(pg_conn, default_visibility_timeout=VISIBILITY_TIMEOUT_SEC)
    await queue.initialize()
    requeued = await queue.requeue_stale(queue_name=queue_name)
    assert requeued >= 1, (
        f"requeue_stale returned {requeued} — the orphaned task was "
        f"not detected as stale. The queue's visibility-timeout "
        f"contract is broken."
    )

    # Confirm row returned to 'pending'.
    rows = await pg_conn.fetch(
        "SELECT status FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert rows[0]["status"] == "pending", (
        f"task status after requeue_stale is {rows[0]['status']!r}; "
        f"expected 'pending'."
    )

    # 5. Worker B: dequeues the redelivered task and acks immediately.
    worker_b = ctx.Process(
        target=_worker_dequeues_and_runs,
        args=(PG_URL, queue_name, "worker-B", marker_run_id, 0.0),
    )
    worker_b.start()
    worker_b.join(timeout=30.0)
    try:
        assert not worker_b.is_alive(), "worker B did not finish within 30s"
        assert worker_b.exitcode == 0, (
            f"worker B exited with {worker_b.exitcode} — "
            f"redelivered task could not be claimed/completed."
        )
    finally:
        if worker_b.is_alive():
            worker_b.kill()
            worker_b.join(timeout=5.0)

    # 6. Final state: queue row is now 'completed' (worker B acked),
    # AND the marker table has TWO rows (one from each worker that
    # observed the task).
    rows = await pg_conn.fetch(
        "SELECT status FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert rows[0]["status"] == "completed", (
        f"task status after worker B is {rows[0]['status']!r}; "
        f"expected 'completed'."
    )
    final_markers = await _count_markers(pg_conn, marker_run_id)
    assert final_markers == 2, (
        f"marker count is {final_markers}; expected exactly 2 "
        f"(one from worker A's pre-SIGKILL write, one from worker "
        f"B's post-redelivery write). The queue may have re-fired "
        f"the task more than once."
    )

    # And worker B was the redeliverer — confirm by worker_id.
    workers = await pg_conn.fetch(
        f"SELECT DISTINCT worker_id FROM {MARKER_TABLE} "
        "WHERE run_id = ? ORDER BY worker_id",
        marker_run_id,
    )
    worker_ids = {row["worker_id"] for row in workers}
    assert worker_ids == {"worker-A", "worker-B"}, (
        f"marker workers were {worker_ids}; expected exactly "
        f"{{'worker-A', 'worker-B'}}."
    )
