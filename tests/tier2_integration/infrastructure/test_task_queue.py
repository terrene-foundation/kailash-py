# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SQLTaskQueue.

Tests run against in-memory SQLite via ConnectionManager.
"""

from __future__ import annotations

import json
import time

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueue


@pytest.fixture
async def conn_manager():
    mgr = ConnectionManager("sqlite:///:memory:")
    await mgr.initialize()
    yield mgr
    await mgr.close()


@pytest.fixture
async def task_queue(conn_manager):
    queue = SQLTaskQueue(conn=conn_manager)
    await queue.initialize()
    yield queue


@pytest.mark.asyncio
class TestEnqueueDequeue:
    async def test_enqueue_dequeue_round_trip(self, task_queue):
        payload = {"workflow_id": "wf-1", "nodes": {"start": {"type": "StartNode"}}}
        tid = await task_queue.enqueue(payload, task_id="task-001")
        assert tid == "task-001"

        msg = await task_queue.dequeue(worker_id="worker-1")
        assert msg is not None
        assert msg.task_id == "task-001"
        assert msg.payload == payload
        assert msg.status == "processing"
        assert msg.worker_id == "worker-1"
        assert msg.attempts == 1

    async def test_enqueue_auto_generates_id(self, task_queue):
        tid = await task_queue.enqueue({"data": "test"})
        assert tid  # non-empty UUID

    async def test_dequeue_returns_none_when_empty(self, task_queue):
        result = await task_queue.dequeue(worker_id="w")
        assert result is None

    async def test_dequeue_respects_fifo(self, task_queue):
        await task_queue.enqueue({"order": 1}, task_id="first")
        await task_queue.enqueue({"order": 2}, task_id="second")

        msg = await task_queue.dequeue(worker_id="w")
        assert msg.task_id == "first"

    async def test_no_duplicate_delivery(self, task_queue):
        await task_queue.enqueue({"a": 1}, task_id="task-A")
        await task_queue.enqueue({"b": 2}, task_id="task-B")

        first = await task_queue.dequeue(worker_id="w1")
        second = await task_queue.dequeue(worker_id="w2")
        assert first is not None
        assert second is not None
        assert first.task_id != second.task_id
        assert {first.task_id, second.task_id} == {"task-A", "task-B"}

    async def test_dequeue_after_all_consumed(self, task_queue):
        await task_queue.enqueue({"x": 1}, task_id="only")
        await task_queue.dequeue(worker_id="w")
        result = await task_queue.dequeue(worker_id="w")
        assert result is None


@pytest.mark.asyncio
class TestCompleteAndFail:
    async def test_complete_marks_task(self, task_queue):
        await task_queue.enqueue({"d": 1}, task_id="t1")
        await task_queue.dequeue(worker_id="w")
        await task_queue.complete("t1")

        stats = await task_queue.get_stats()
        assert stats.get("completed", 0) == 1

    async def test_fail_requeues_for_retry(self, task_queue):
        await task_queue.enqueue({"d": 1}, task_id="t1", max_attempts=3)
        await task_queue.dequeue(worker_id="w")  # attempts=1
        await task_queue.fail("t1", error="oops")

        stats = await task_queue.get_stats()
        assert stats.get("pending", 0) == 1  # back in queue

    async def test_fail_dead_letters_at_max_attempts(self, task_queue):
        await task_queue.enqueue({"d": 1}, task_id="t1", max_attempts=1)
        await task_queue.dequeue(worker_id="w")  # attempts=1, max=1
        await task_queue.fail("t1", error="fatal")

        stats = await task_queue.get_stats()
        assert stats.get("dead_lettered", 0) == 1


@pytest.mark.asyncio
class TestStaleRecovery:
    async def test_requeue_stale_tasks(self, task_queue):
        # Enqueue and dequeue a task
        await task_queue.enqueue({"d": 1}, task_id="stale-1", visibility_timeout=1)
        await task_queue.dequeue(worker_id="dead-worker")

        # Simulate time passing (update updated_at to past)
        past = time.time() - 600
        await task_queue._conn.execute(
            f"UPDATE {task_queue._table} SET updated_at = ? WHERE task_id = ?",
            past,
            "stale-1",
        )

        count = await task_queue.requeue_stale()
        assert count == 1

        # Should be dequeueable again
        msg = await task_queue.dequeue(worker_id="new-worker")
        assert msg is not None
        assert msg.task_id == "stale-1"


@pytest.mark.asyncio
class TestGetStats:
    async def test_stats_by_status(self, task_queue):
        await task_queue.enqueue({"a": 1}, task_id="p1")
        await task_queue.enqueue({"b": 2}, task_id="p2")
        await task_queue.dequeue(worker_id="w")  # 1 processing

        stats = await task_queue.get_stats()
        assert stats.get("pending", 0) == 1
        assert stats.get("processing", 0) == 1


@pytest.mark.asyncio
class TestInitialization:
    async def test_double_initialize_is_safe(self, task_queue):
        await task_queue.initialize()  # second call
        await task_queue.enqueue({"test": True}, task_id="ok")
        msg = await task_queue.dequeue(worker_id="w")
        assert msg is not None


@pytest.mark.asyncio
class TestQueueNames:
    async def test_separate_queues(self, task_queue):
        await task_queue.enqueue({"q": "alpha"}, task_id="a1", queue_name="alpha")
        await task_queue.enqueue({"q": "beta"}, task_id="b1", queue_name="beta")

        msg = await task_queue.dequeue(queue_name="beta", worker_id="w")
        assert msg is not None
        assert msg.task_id == "b1"

        msg2 = await task_queue.dequeue(queue_name="beta", worker_id="w")
        assert msg2 is None  # beta is empty

        msg3 = await task_queue.dequeue(queue_name="alpha", worker_id="w")
        assert msg3 is not None
        assert msg3.task_id == "a1"


@pytest.mark.asyncio
class TestPurgeCompleted:
    async def test_purge_completed_removes_completed_tasks(self, task_queue):
        """purge_completed removes all tasks with status 'completed'."""
        # Enqueue, dequeue, and complete two tasks
        await task_queue.enqueue({"d": 1}, task_id="c1")
        await task_queue.enqueue({"d": 2}, task_id="c2")
        await task_queue.dequeue(worker_id="w")
        await task_queue.dequeue(worker_id="w")
        await task_queue.complete("c1")
        await task_queue.complete("c2")

        stats_before = await task_queue.get_stats()
        assert stats_before.get("completed", 0) == 2

        count = await task_queue.purge_completed()
        assert count == 2

        stats_after = await task_queue.get_stats()
        assert stats_after.get("completed", 0) == 0

    async def test_purge_completed_with_older_than(self, task_queue):
        """purge_completed with older_than only removes tasks completed before that timestamp."""
        # Enqueue, dequeue, and complete two tasks
        await task_queue.enqueue({"d": 1}, task_id="old-1")
        await task_queue.enqueue({"d": 2}, task_id="new-1")
        await task_queue.dequeue(worker_id="w")
        await task_queue.complete("old-1")
        await task_queue.dequeue(worker_id="w")
        await task_queue.complete("new-1")

        # Force old-1 to have an updated_at far in the past
        past = time.time() - 3600  # 1 hour ago
        await task_queue._conn.execute(
            f"UPDATE {task_queue._table} SET updated_at = ? WHERE task_id = ?",
            past,
            "old-1",
        )

        # Use a cutoff between old-1 (1 hour ago) and new-1 (just now)
        cutoff = time.time() - 60  # 1 minute ago

        # Purge only tasks older than cutoff
        count = await task_queue.purge_completed(older_than=cutoff)
        assert count == 1  # only old-1

        stats = await task_queue.get_stats()
        assert stats.get("completed", 0) == 1  # new-1 remains

    async def test_purge_completed_on_empty_table_is_safe(self, task_queue):
        """purge_completed on an empty queue returns 0 without errors."""
        count = await task_queue.purge_completed()
        assert count == 0

    async def test_purge_completed_does_not_remove_pending_tasks(self, task_queue):
        """purge_completed only removes 'completed' tasks, not pending/processing/failed."""
        # Enqueue three tasks
        await task_queue.enqueue({"d": 1}, task_id="stay-pending")
        await task_queue.enqueue({"d": 2}, task_id="stay-processing")
        await task_queue.enqueue({"d": 3}, task_id="to-complete")

        # Dequeue all three in FIFO order
        msg1 = await task_queue.dequeue(worker_id="w")  # stay-pending
        assert msg1 is not None
        assert msg1.task_id == "stay-pending"

        msg2 = await task_queue.dequeue(worker_id="w")  # stay-processing
        assert msg2 is not None
        assert msg2.task_id == "stay-processing"

        msg3 = await task_queue.dequeue(worker_id="w")  # to-complete
        assert msg3 is not None
        assert msg3.task_id == "to-complete"

        # Put stay-pending back to pending via fail (under max_attempts)
        await task_queue.fail("stay-pending", error="retry")
        # Leave stay-processing in processing state
        # Complete to-complete
        await task_queue.complete("to-complete")

        stats_before = await task_queue.get_stats()
        assert stats_before.get("completed", 0) == 1
        assert stats_before.get("pending", 0) == 1
        assert stats_before.get("processing", 0) == 1

        # Purge completed
        count = await task_queue.purge_completed()
        assert count == 1

        # Verify non-completed tasks still exist
        stats_after = await task_queue.get_stats()
        assert stats_after.get("completed", 0) == 0
        assert stats_after.get("pending", 0) == 1
        assert stats_after.get("processing", 0) == 1
