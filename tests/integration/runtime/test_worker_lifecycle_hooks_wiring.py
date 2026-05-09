# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``Worker.on_task_*`` lifecycle hooks (issue #914).

Per ``rules/testing.md`` Tier 2 contract: NO mocking, real Redis, real workflow
execution. Per ``rules/orphan-detection.md`` Rule 2 + ``rules/facade-manager-
detection.md`` Rule 1: hooks are wired into the framework's hot path
(``Worker._execute_task``), so the wiring contract MUST be exercised end-to-end.

Requires Redis at ``localhost:6380``. Skips if Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)

REDIS_URL = "redis://localhost:6380"


def _redis_available() -> bool:
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        client.close()
        return True
    except Exception:
        return False


skip_no_redis = pytest.mark.skipif(
    not _redis_available(),
    reason=f"Redis not available at {REDIS_URL}",
)


@pytest.fixture
def _flush_redis():
    """Flush the test Redis database before and after each test."""
    import redis as redis_lib

    client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    yield
    client.flushdb()
    client.close()


def _build_workflow(*, raises: bool = False):
    """Build a 1-node Python workflow; ``raises=True`` raises ZeroDivisionError."""
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    code = "raise ZeroDivisionError('intentional')" if raises else "result = 42"
    builder.add_node("PythonCodeNode", "start", {"code": code})
    return builder.build()


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
class TestWorkerLifecycleHooksWiring:
    """Verify Worker dispatches lifecycle events to registered handlers."""

    async def test_success_path_fires_prerun_success_postrun(self, _flush_redis):
        """A successful task fires prerun → success → postrun in order."""
        from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker
        from kailash.runtime.lifecycle_events import TaskEvent

        queue = TaskQueue(redis_url=REDIS_URL)
        runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)
        _, run_id = runtime.execute(_build_workflow())

        events: list[tuple[str, TaskEvent]] = []
        worker = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="hooks-success-worker",
        )
        worker.on_task_prerun(lambda e: events.append(("prerun", e)))
        worker.on_task_success(lambda e: events.append(("success", e)))
        worker.on_task_postrun(lambda e: events.append(("postrun", e)))
        worker.on_task_failure(lambda e: events.append(("failure", e)))
        worker.on_task_retry(lambda e: events.append(("retry", e)))

        worker._semaphore = asyncio.Semaphore(1)
        task = await asyncio.get_event_loop().run_in_executor(
            None, lambda: queue.dequeue(timeout=2)
        )
        assert task is not None, "task must be dequeued from Redis"
        await worker._execute_task(task)

        # ORDER: prerun → success → postrun. failure / retry MUST NOT fire.
        kinds = [k for k, _ in events]
        assert kinds == [
            "prerun",
            "success",
            "postrun",
        ], f"expected [prerun, success, postrun], got {kinds}"

        # PAYLOAD shape: every event is a TaskEvent with our run_id.
        assert all(isinstance(e, TaskEvent) for _, e in events)
        assert {e.task_id for _, e in events} == {run_id}

        # prerun has elapsed_ms=None; success/postrun have elapsed_ms populated.
        prerun = events[0][1]
        success = events[1][1]
        postrun = events[2][1]
        assert prerun.elapsed_ms is None
        assert prerun.exception is None
        assert success.elapsed_ms is not None and success.elapsed_ms >= 0
        assert success.exception is None
        assert postrun.elapsed_ms is not None
        assert postrun.exception is None

    async def test_failure_path_classifies_retry_vs_final(self, _flush_redis):
        """A failing task fires retry while attempts<max, failure on the final attempt."""
        from kailash.runtime.distributed import TaskQueue, Worker

        queue = TaskQueue(redis_url=REDIS_URL)

        # First attempt: max_attempts=2, attempts=1 → retry handler MUST fire.
        # Second attempt: attempts=2 == max_attempts → failure handler MUST fire.
        events_attempt1: list[tuple[str, object]] = []
        events_attempt2: list[tuple[str, object]] = []

        worker = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="hooks-retry-worker",
        )

        # Build a single task that raises and execute it twice through _execute_task,
        # incrementing the attempt counter each time. We bypass DistributedRuntime
        # so we can control task.attempts precisely without round-tripping through
        # nack's re-queue path (which adds Redis-timing noise to this assertion).
        from kailash.runtime.distributed import TaskMessage

        wf = _build_workflow(raises=True)
        task = TaskMessage(
            task_id="failing-task-001",
            workflow_data=wf.to_dict(),
            parameters={},
            attempts=1,
            max_attempts=2,
        )
        # Enqueue + dequeue to get the task into the processing list (so ack/nack
        # round-trips don't error). Real Redis path; no mocking.
        queue.enqueue(task)
        task = await asyncio.get_event_loop().run_in_executor(
            None, lambda: queue.dequeue(timeout=2)
        )
        assert task is not None
        # Pin attempts to 1/2 so retry-classifier fires retry, not failure.
        task.attempts = 1
        worker._hooks_retry.append(lambda e: events_attempt1.append(("retry", e)))
        worker._hooks_failure.append(lambda e: events_attempt1.append(("failure", e)))
        worker._semaphore = asyncio.Semaphore(1)
        await worker._execute_task(task)

        kinds_a1 = [k for k, _ in events_attempt1]
        assert (
            "retry" in kinds_a1
        ), f"attempt 1/2 (failing) MUST fire retry; got {kinds_a1}"
        assert (
            "failure" not in kinds_a1
        ), f"attempt 1/2 MUST NOT fire failure; got {kinds_a1}"

        # Final-failure case: attempts == max_attempts.
        # Use a fresh worker with separate hook registries to keep assertions clean.
        worker2 = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="hooks-final-failure-worker",
        )
        task2 = TaskMessage(
            task_id="failing-task-002",
            workflow_data=wf.to_dict(),
            parameters={},
            attempts=2,
            max_attempts=2,
        )
        queue.enqueue(task2)
        task2 = await asyncio.get_event_loop().run_in_executor(
            None, lambda: queue.dequeue(timeout=2)
        )
        assert task2 is not None
        task2.attempts = 2
        worker2._hooks_retry.append(lambda e: events_attempt2.append(("retry", e)))
        worker2._hooks_failure.append(lambda e: events_attempt2.append(("failure", e)))
        worker2._semaphore = asyncio.Semaphore(1)
        await worker2._execute_task(task2)

        kinds_a2 = [k for k, _ in events_attempt2]
        assert "failure" in kinds_a2, f"final attempt MUST fire failure; got {kinds_a2}"
        assert (
            "retry" not in kinds_a2
        ), f"final attempt MUST NOT fire retry; got {kinds_a2}"

        # Failure event payload carries the originating exception.
        failure_event = next(e for k, e in events_attempt2 if k == "failure")
        assert isinstance(failure_event.exception, ZeroDivisionError)

    async def test_handler_exception_does_not_block_lifecycle(self, _flush_redis):
        """A raising handler MUST NOT prevent later handlers / nack / ack."""
        from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker

        queue = TaskQueue(redis_url=REDIS_URL)
        runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)
        _, run_id = runtime.execute(_build_workflow())

        observed: list[str] = []

        def bad_handler(_event):
            raise RuntimeError("handler exploded")

        worker = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="hooks-resilient-worker",
        )
        worker.on_task_success(bad_handler)  # raises
        worker.on_task_success(lambda e: observed.append("second-success-fired"))
        worker.on_task_postrun(lambda e: observed.append("postrun-fired"))

        worker._semaphore = asyncio.Semaphore(1)
        task = await asyncio.get_event_loop().run_in_executor(
            None, lambda: queue.dequeue(timeout=2)
        )
        await worker._execute_task(task)

        assert (
            "second-success-fired" in observed
        ), "later handlers MUST run even after an earlier handler raised"
        assert (
            "postrun-fired" in observed
        ), "postrun MUST fire after a handler in an earlier phase raised"

        # Result was still stored — the handler exception did not abort lifecycle.
        result = queue.get_result(run_id)
        assert result is not None
        assert result.status == "completed"

    async def test_async_handler_is_awaited(self, _flush_redis):
        """A coroutine-returning handler MUST be awaited inline."""
        from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker

        queue = TaskQueue(redis_url=REDIS_URL)
        runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)
        runtime.execute(_build_workflow())

        seen: list[str] = []

        async def async_handler(event):
            await asyncio.sleep(0)  # actually awaitable
            seen.append(f"async:{event.task_id}")

        worker = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="hooks-async-worker",
        )
        worker.on_task_success(async_handler)

        worker._semaphore = asyncio.Semaphore(1)
        task = await asyncio.get_event_loop().run_in_executor(
            None, lambda: queue.dequeue(timeout=2)
        )
        await worker._execute_task(task)

        assert len(seen) == 1
        assert seen[0].startswith("async:")
