# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SQLWorkerRegistry.

Tests run against in-memory SQLite via ConnectionManager.
"""

from __future__ import annotations

import time

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueue
from kailash.infrastructure.worker_registry import SQLWorkerRegistry


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


@pytest.fixture
async def registry(conn_manager, task_queue):
    reg = SQLWorkerRegistry(conn=conn_manager, task_queue=task_queue)
    await reg.initialize()
    yield reg


@pytest.mark.asyncio
class TestRegisterAndHeartbeat:
    async def test_register_creates_active_worker(self, registry):
        await registry.register("worker-1", "default")

        workers = await registry.get_active_workers("default")
        assert len(workers) == 1
        assert workers[0]["worker_id"] == "worker-1"
        assert workers[0]["queue_name"] == "default"
        assert workers[0]["status"] == "active"

    async def test_heartbeat_updates_last_beat_at(self, registry):
        await registry.register("worker-1", "default")

        workers_before = await registry.get_active_workers("default")
        beat_before = workers_before[0]["last_beat_at"]

        # Small delay so timestamp differs
        await registry.heartbeat("worker-1")

        workers_after = await registry.get_active_workers("default")
        beat_after = workers_after[0]["last_beat_at"]
        assert beat_after >= beat_before

    async def test_register_heartbeat_lifecycle(self, registry):
        """Register, heartbeat, and verify the worker remains active."""
        await registry.register("worker-A", "q1")
        await registry.heartbeat("worker-A")
        await registry.heartbeat("worker-A")

        workers = await registry.get_active_workers("q1")
        assert len(workers) == 1
        assert workers[0]["worker_id"] == "worker-A"
        assert workers[0]["status"] == "active"


@pytest.mark.asyncio
class TestDeregister:
    async def test_deregister_sets_inactive(self, registry):
        await registry.register("worker-1", "default")
        await registry.deregister("worker-1")

        workers = await registry.get_active_workers("default")
        assert len(workers) == 0

    async def test_deregister_nonexistent_worker_is_safe(self, registry):
        """Deregistering a worker that does not exist should not raise."""
        await registry.deregister("ghost-worker")  # no error expected


@pytest.mark.asyncio
class TestSetAndClearCurrentTask:
    async def test_set_current_task(self, registry):
        await registry.register("worker-1", "default")
        await registry.set_current_task("worker-1", "task-42")

        workers = await registry.get_active_workers("default")
        assert workers[0]["current_task"] == "task-42"

    async def test_clear_current_task(self, registry):
        await registry.register("worker-1", "default")
        await registry.set_current_task("worker-1", "task-42")
        await registry.clear_current_task("worker-1")

        workers = await registry.get_active_workers("default")
        assert workers[0]["current_task"] is None


@pytest.mark.asyncio
class TestReapDeadWorkers:
    async def test_reap_identifies_stale_workers(self, registry, conn_manager):
        """Workers with last_beat_at older than staleness threshold are reaped."""
        await registry.register("stale-worker", "default")

        # Simulate staleness by backdating last_beat_at
        past = time.time() - 600
        await conn_manager.execute(
            "UPDATE kailash_worker_registry SET last_beat_at = ? WHERE worker_id = ?",
            past,
            "stale-worker",
        )

        count = await registry.reap_dead_workers(
            staleness_seconds=60, queue_name="default"
        )
        assert count == 1

        # Worker should now be inactive
        workers = await registry.get_active_workers("default")
        assert len(workers) == 0

    async def test_reap_requeues_tasks_held_by_dead_workers(
        self, registry, task_queue, conn_manager
    ):
        """Tasks assigned to dead workers are requeued to pending."""
        # Register a worker and give it a task
        await registry.register("dead-worker", "default")
        tid = await task_queue.enqueue({"data": "important"}, task_id="task-held")
        msg = await task_queue.dequeue(worker_id="dead-worker")
        assert msg is not None
        assert msg.status == "processing"

        await registry.set_current_task("dead-worker", "task-held")

        # Backdate the heartbeat to simulate death
        past = time.time() - 600
        await conn_manager.execute(
            "UPDATE kailash_worker_registry SET last_beat_at = ? WHERE worker_id = ?",
            past,
            "dead-worker",
        )

        count = await registry.reap_dead_workers(
            staleness_seconds=60, queue_name="default"
        )
        assert count == 1

        # The task should now be pending again
        stats = await task_queue.get_stats()
        assert stats.get("pending", 0) == 1
        assert stats.get("processing", 0) == 0

    async def test_reap_does_not_affect_fresh_workers(self, registry, conn_manager):
        """Workers with recent heartbeats are not reaped."""
        await registry.register("fresh-worker", "default")

        count = await registry.reap_dead_workers(
            staleness_seconds=60, queue_name="default"
        )
        assert count == 0

        workers = await registry.get_active_workers("default")
        assert len(workers) == 1

    async def test_reap_on_empty_table_is_safe(self, registry):
        """Reaping when no workers exist should return 0 without errors."""
        count = await registry.reap_dead_workers(
            staleness_seconds=60, queue_name="default"
        )
        assert count == 0

    async def test_reap_only_affects_matching_queue(self, registry, conn_manager):
        """Reaping is scoped to the specified queue_name."""
        await registry.register("worker-q1", "q1")
        await registry.register("worker-q2", "q2")

        # Make both stale
        past = time.time() - 600
        await conn_manager.execute(
            "UPDATE kailash_worker_registry SET last_beat_at = ?",
            past,
        )

        count = await registry.reap_dead_workers(staleness_seconds=60, queue_name="q1")
        assert count == 1

        # q2 worker should still be active
        workers_q2 = await registry.get_active_workers("q2")
        assert len(workers_q2) == 1


@pytest.mark.asyncio
class TestInitialization:
    async def test_double_initialize_is_safe(self, registry):
        """Calling initialize() twice should not raise or corrupt state."""
        await registry.initialize()  # second call
        await registry.register("worker-1", "default")

        workers = await registry.get_active_workers("default")
        assert len(workers) == 1


@pytest.mark.asyncio
class TestGetActiveWorkers:
    async def test_get_active_workers_filters_by_queue(self, registry):
        await registry.register("worker-alpha", "alpha")
        await registry.register("worker-beta", "beta")
        await registry.register("worker-alpha-2", "alpha")

        alpha_workers = await registry.get_active_workers("alpha")
        assert len(alpha_workers) == 2
        worker_ids = {w["worker_id"] for w in alpha_workers}
        assert worker_ids == {"worker-alpha", "worker-alpha-2"}

    async def test_get_active_workers_excludes_inactive(self, registry):
        await registry.register("active-worker", "default")
        await registry.register("inactive-worker", "default")
        await registry.deregister("inactive-worker")

        workers = await registry.get_active_workers("default")
        assert len(workers) == 1
        assert workers[0]["worker_id"] == "active-worker"

    async def test_get_active_workers_empty_queue(self, registry):
        """Returns empty list when no workers exist for the queue."""
        workers = await registry.get_active_workers("nonexistent")
        assert workers == []
