# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PY-EI-018: Multi-worker integration tests.

Tests SQL task queue with multiple concurrent dequeue operations
to verify no duplicate delivery under contention.

Requires: PostgreSQL at localhost:5434 (or TEST_PG_URL env var)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueue

PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _pg_available() -> bool:
    try:
        import asyncpg  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture
async def pg_queue():
    if not _pg_available():
        pytest.skip("asyncpg not installed")
    conn = ConnectionManager(PG_URL)
    try:
        await conn.initialize()
    except Exception:
        pytest.skip("PostgreSQL not available")
    queue = SQLTaskQueue(conn=conn, table_name="test_multi_worker_queue")
    await queue.initialize()
    yield queue
    # Clean up
    await conn.execute("DROP TABLE IF EXISTS test_multi_worker_queue")
    await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiWorkerSQLQueue:
    async def test_concurrent_dequeue_no_duplicates(self, pg_queue):
        """Multiple concurrent dequeue calls get unique tasks."""
        n_tasks = 20
        for i in range(n_tasks):
            await pg_queue.enqueue(
                {"task_num": i}, task_id=f"task-{i:03d}", queue_name="default"
            )

        # Simulate 5 workers dequeuing concurrently
        async def worker_dequeue(worker_id: str):
            claimed = []
            while True:
                msg = await pg_queue.dequeue(queue_name="default", worker_id=worker_id)
                if msg is None:
                    break
                claimed.append(msg.task_id)
                await pg_queue.complete(msg.task_id)
            return claimed

        results = await asyncio.gather(
            *[worker_dequeue(f"worker-{i}") for i in range(5)]
        )

        all_claimed = []
        for r in results:
            all_claimed.extend(r)

        # Every task claimed exactly once
        assert (
            len(all_claimed) == n_tasks
        ), f"Expected {n_tasks} tasks, got {len(all_claimed)}"
        assert len(set(all_claimed)) == n_tasks, "Duplicate task delivery detected!"

    async def test_stale_recovery_after_worker_death(self, pg_queue):
        """Tasks stuck in 'processing' are recovered after timeout."""
        import time

        await pg_queue.enqueue(
            {"data": "important"},
            task_id="stuck-task",
            queue_name="default",
            visibility_timeout=1,  # 1 second timeout
        )

        # Worker claims but "dies" (never completes)
        msg = await pg_queue.dequeue(queue_name="default", worker_id="dead-worker")
        assert msg is not None
        assert msg.task_id == "stuck-task"

        # Simulate time passing
        past = time.time() - 600
        await pg_queue._conn.execute(
            f"UPDATE {pg_queue._table} SET updated_at = ? WHERE task_id = ?",
            past,
            "stuck-task",
        )

        # Recovery should requeue
        count = await pg_queue.requeue_stale(queue_name="default")
        assert count == 1

        # Another worker can now pick it up
        msg2 = await pg_queue.dequeue(queue_name="default", worker_id="rescue-worker")
        assert msg2 is not None
        assert msg2.task_id == "stuck-task"
        assert msg2.worker_id == "rescue-worker"
