# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for the W6 SQLTaskQueue visibility-timeout
contract.

Pre-W6 the timestamp columns ``created_at`` and ``updated_at`` were
declared ``REAL NOT NULL`` in :meth:`SQLTaskQueue.initialize`.  On
PostgreSQL ``REAL`` is single-precision (4 bytes), and ``time.time()``
returns a double-precision (8-byte) Unix epoch; coercion to single
precision truncates current epoch values by ~50 seconds.  The
downstream effect: :meth:`SQLTaskQueue.requeue_stale` computes
``now - row["updated_at"]`` and gets a NEGATIVE number on every fresh
row, so no row is ever detected as stale and the visibility-timeout
contract is structurally broken on PostgreSQL.

The W6 fix routes timestamp DDL through
``dialect.double_precision_type()``: PostgreSQL/MySQL get
``DOUBLE PRECISION`` / ``DOUBLE`` (8 bytes); SQLite gets ``REAL``
(which IS 8 bytes per the SQLite type-affinity rules).

These Tier-2 tests pin the contract on real Postgres:

  1. **Round-trip test** — a stored ``time.time()`` value comes back
     bit-for-bit (positive ``now - updated_at`` delta on a fresh row).
  2. **End-to-end requeue test** — claim a task, advance updated_at past
     the visibility window, call ``requeue_stale``, observe the task
     transitions back to ``pending`` (or ``dead_lettered`` if attempts
     exhausted).

Per ``rules/testing.md`` § Tier 2 — NO mocking; per
``rules/orphan-detection.md`` MUST Rule 2 — exercises the real
PostgreSQL surface that the bug class manifests on.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.
"""

from __future__ import annotations

import os
import socket
import time
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


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:
        # Best-effort cleanup — table may not exist on first run.
        pass
    yield manager
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:
        pass
    await manager.close()


# ---------------------------------------------------------------------------
# Round-trip baseline: time.time() survives the column round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_timestamp_columns_preserve_time_dot_time_precision(
    pg_conn: ConnectionManager,
):
    """A ``time.time()`` value MUST round-trip through ``updated_at``
    with ZERO truncation — pre-W6 PostgreSQL REAL truncated to ~50s of
    drift, making ``now - updated_at`` go negative on every fresh row.

    This test is the structural baseline: if it ever flips to non-zero
    delta, the column type has regressed back to single-precision and
    every downstream visibility-timeout contract is broken again.
    """
    queue = SQLTaskQueue(pg_conn)
    await queue.initialize()

    task_id = await queue.enqueue(
        payload={"hello": "world"},
        queue_name="precision_test",
    )

    # Direct DB observation: read the raw updated_at column AS A FLOAT
    # and confirm `time.time() - updated_at >= 0` (i.e., not in the
    # future due to truncation).  Pre-W6 this would have been a
    # negative number on PostgreSQL.
    row = await pg_conn.fetchone(
        "SELECT created_at, updated_at FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert row is not None, "task did not land in queue"
    now = time.time()

    # The fresh row was inserted moments ago.  `now` is strictly >=
    # both timestamps (or at most a few microseconds before, depending
    # on clock resolution).  The pre-W6 bug produced deltas ~ -50s.
    delta_created = now - row["created_at"]
    delta_updated = now - row["updated_at"]
    assert delta_created >= -0.001, (
        f"created_at appears to be in the future by {-delta_created:.6f}s — "
        f"timestamp column truncation regressed; PostgreSQL REAL is back. "
        f"now={now!r}, created_at={row['created_at']!r}"
    )
    assert delta_updated >= -0.001, (
        f"updated_at appears to be in the future by {-delta_updated:.6f}s — "
        f"timestamp column truncation regressed; PostgreSQL REAL is back. "
        f"now={now!r}, updated_at={row['updated_at']!r}"
    )

    # Fresh-row deltas should be small (sub-second), not the ~50s gap
    # that a single-precision REAL would produce.  Allow generous
    # margin (10s) for slow CI runners.
    assert delta_created < 10.0, (
        f"created_at delta {delta_created:.6f}s is suspiciously large — "
        f"may indicate single-precision truncation is back."
    )
    assert delta_updated < 10.0, (
        f"updated_at delta {delta_updated:.6f}s is suspiciously large — "
        f"may indicate single-precision truncation is back."
    )


# ---------------------------------------------------------------------------
# End-to-end: requeue_stale detects a genuinely-stale task
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_requeue_stale_detects_task_past_visibility_timeout(
    pg_conn: ConnectionManager,
):
    """End-to-end: enqueue → dequeue (claim) → fast-forward updated_at
    past the visibility window → ``requeue_stale`` MUST detect and
    re-pend the task.

    Pre-W6 the column truncation produced a negative ``elapsed`` value
    on every fresh row, so requeue_stale silently returned 0 even
    when the task was demonstrably past its visibility window.  The
    test pins the structural contract: a task whose updated_at is
    older than its visibility_timeout MUST be detected.
    """
    queue = SQLTaskQueue(pg_conn, default_visibility_timeout=1)
    await queue.initialize()

    # Enqueue and claim a task with a 1-second visibility timeout.
    task_id = await queue.enqueue(
        payload={"work": "stale_test"},
        queue_name="vis_timeout_test",
        visibility_timeout=1,
    )
    msg = await queue.dequeue(queue_name="vis_timeout_test", worker_id="w1")
    assert msg is not None, "fresh task should be claimable"
    assert msg.task_id == task_id

    # Manually fast-forward the row's updated_at so we don't have to
    # actually wait for the visibility window to elapse — the WHOLE
    # POINT of this test is to verify the timestamp comparison works,
    # which requires writing a deliberately-stale value.
    stale_ts = time.time() - 60.0  # 60 seconds in the past
    await pg_conn.execute(
        "UPDATE kailash_task_queue SET updated_at = ? WHERE task_id = ?",
        stale_ts,
        task_id,
    )

    # Confirm the row's updated_at survived the round-trip — same
    # invariant as the baseline test, this time on a known-stale value.
    row = await pg_conn.fetchone(
        "SELECT updated_at FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert row is not None
    delta = time.time() - row["updated_at"]
    assert delta >= 50.0, (
        f"Stale-fixture updated_at lost precision: round-trip delta is "
        f"{delta:.6f}s, expected >= 50s (we wrote 60s ago).  Column "
        f"type may have regressed."
    )

    # Now requeue_stale MUST see the staleness and transition the task
    # back to pending.  Pre-W6 this returned 0 because the timestamp
    # truncation made every elapsed comparison negative.
    requeued = await queue.requeue_stale(queue_name="vis_timeout_test")
    assert requeued == 1, (
        f"requeue_stale should have detected exactly one stale task; "
        f"got {requeued}.  The visibility-timeout contract is broken — "
        f"either the column type regressed or requeue_stale's elapsed "
        f"math is wrong."
    )

    # The task is now back in 'pending' (or dead-lettered if attempts
    # exhausted; here we used max_attempts=3 default and attempts=1).
    final_row = await pg_conn.fetchone(
        "SELECT status FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert final_row is not None
    assert (
        final_row["status"] == "pending"
    ), f"requeued task should be 'pending'; got {final_row['status']!r}"


# ---------------------------------------------------------------------------
# Idempotency: re-claim after requeue works
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_requeued_task_can_be_redequeued(
    pg_conn: ConnectionManager,
):
    """After ``requeue_stale`` re-pends a task, a worker MUST be able
    to dequeue it again — proving the full visibility-timeout cycle
    works end-to-end, not just the detection half.
    """
    queue = SQLTaskQueue(pg_conn, default_visibility_timeout=1)
    await queue.initialize()

    task_id = await queue.enqueue(
        payload={"work": "redeliver_test"},
        queue_name="redeliver",
        visibility_timeout=1,
    )
    msg1 = await queue.dequeue(queue_name="redeliver", worker_id="worker1")
    assert msg1 is not None and msg1.task_id == task_id

    # Fast-forward and requeue.
    stale_ts = time.time() - 60.0
    await pg_conn.execute(
        "UPDATE kailash_task_queue SET updated_at = ? WHERE task_id = ?",
        stale_ts,
        task_id,
    )
    requeued = await queue.requeue_stale(queue_name="redeliver")
    assert requeued == 1

    # A second worker MUST be able to claim the now-pending task.
    msg2 = await queue.dequeue(queue_name="redeliver", worker_id="worker2")
    assert msg2 is not None, (
        "task should be re-claimable after requeue_stale; got None.  "
        "The visibility-timeout cycle is incomplete."
    )
    assert msg2.task_id == task_id
    assert msg2.attempts == 2, (
        f"attempts should increment to 2 on the redelivery; got " f"{msg2.attempts}."
    )
