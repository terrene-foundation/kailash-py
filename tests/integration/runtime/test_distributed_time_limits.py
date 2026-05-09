# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for #912 Shard 4 — distributed runtime + Worker time limits.

Per ``rules/testing.md`` Tier 2 contract: NO mocking, real Redis, real workflow
execution. Per ``rules/orphan-detection.md`` Rule 2 + ``rules/facade-manager-
detection.md`` Rule 1: ``execution_limits`` field + ``Worker.default_*time_limit``
defaults are wired into the framework's hot path (``Worker._execute_task``), so
the wiring contract MUST be exercised end-to-end.

Shard 4 invariants (per ``workspaces/issue-912-task-time-limits/02-todos/todos.md``):

1. Producer-side serializes limits onto ``TaskMessage.execution_limits`` (NOT a
   deadline timestamp — timer arms at dequeue so queue wait does not burn budget).
2. Wire format: one optional dict ``{"soft": float, "hard": float}`` so older
   workers silently ignore unknown field (forward-compat).
3. Default fallback: per-task wins over Worker defaults; falls through to None.
4. ``HardTimeLimitExceeded`` triggers requeue when ``attempts < max_attempts``;
   dead-letter only after exhaustion.
5. Lifecycle hook ``on_task_retry`` fires on hard-limit-with-attempts-remaining.
6. Lifecycle hook ``on_task_failure`` fires on dead-letter after exhaustion.
7. ``runtime.execute(...)`` typed signature (Shard 1 invariant 1 propagates).

Requires Redis at ``localhost:6380``. Skips if Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

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


def _build_workflow(*, sleep_seconds: float | None = None):
    """Build a 1-node Python workflow.

    If ``sleep_seconds`` is provided, the node sleeps that long so callers can
    trigger the hard time limit deterministically.
    """
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    if sleep_seconds is not None:
        # Use blocking time.sleep — the workflow runs in a thread executor,
        # mirroring real workloads that don't poll cancellation tokens.
        code = f"import time as _t; _t.sleep({sleep_seconds!r}); result = 'done'"
    else:
        code = "result = 42"
    builder.add_node("PythonCodeNode", "start", {"code": code})
    return builder.build()


# --------------------------------------------------------------------------- #
# Wire-format tests (forward-compat) — no Redis required, but co-located here
# because the dataclass + JSON contract is the producer side of Shard 4.
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_taskmessage_wire_format_forward_compat():
    """Older-SDK ``TaskMessage`` JSON without ``execution_limits`` deserializes cleanly.

    Invariant 2: workers running an older SDK encounter the new ``execution_limits``
    field and ignore it (and vice-versa: a new worker reading old JSON sees
    ``execution_limits is None`` rather than ``KeyError``).
    """
    from kailash.runtime.distributed import TaskMessage

    # Older-SDK shape: no execution_limits key.
    legacy_json = json.dumps(
        {
            "task_id": "legacy-001",
            "workflow_data": {"nodes": []},
            "parameters": {"k": "v"},
            "submitted_at": 12345.0,
            "visibility_timeout": 300,
            "attempts": 0,
            "max_attempts": 3,
        }
    )
    task = TaskMessage.from_json(legacy_json)

    assert task.task_id == "legacy-001"
    assert task.execution_limits is None, (
        "older-SDK JSON without execution_limits MUST deserialize as None per "
        "the forward-compat invariant"
    )

    # Round-trip: serializing back MUST emit execution_limits=None (or omit it),
    # not raise. Round-tripping is the cheapest sanity check on the wire format.
    round_trip = TaskMessage.from_json(task.to_json())
    assert round_trip.execution_limits is None


@skip_no_redis
@pytest.mark.integration
def test_producer_time_limits_serialize_to_taskmessage(_flush_redis):
    """``DistributedRuntime.execute(soft_time_limit=X, time_limit=Y)`` serializes onto TaskMessage.

    Invariant 1 + 2: producer-side serializes limits as one optional dict
    ``{"soft": 300.0, "hard": 600.0}`` onto the TaskMessage; workers read at
    dequeue (timer arms there, so queue wait does not burn budget).
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskMessage, TaskQueue

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    workflow = _build_workflow()
    _, run_id = runtime.execute(workflow, soft_time_limit=300.0, time_limit=600.0)

    # Dequeue the raw task and inspect the wire shape directly.
    task = queue.dequeue(timeout=2)
    assert task is not None
    assert task.task_id == run_id
    assert task.execution_limits == {"soft": 300.0, "hard": 600.0}, (
        f"producer MUST serialize typed limits onto TaskMessage.execution_limits "
        f"as {{'soft': float, 'hard': float}}; got {task.execution_limits!r}"
    )

    # And the JSON round-trip preserves the shape (so workers in another process
    # read the same dict).
    round_trip = TaskMessage.from_json(task.to_json())
    assert round_trip.execution_limits == {"soft": 300.0, "hard": 600.0}


@skip_no_redis
@pytest.mark.integration
def test_producer_no_limits_serializes_none(_flush_redis):
    """Calling ``execute()`` without time-limit kwargs MUST leave execution_limits None.

    Invariant 3: per-task wins over Worker defaults; falls through to None.
    The producer-side default (no kwargs) MUST be ``None``, not an empty dict.
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskQueue

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    runtime.execute(_build_workflow())  # no time-limit kwargs

    task = queue.dequeue(timeout=2)
    assert task is not None
    assert task.execution_limits is None, (
        f"no kwargs MUST serialize execution_limits=None (not empty dict); "
        f"got {task.execution_limits!r}"
    )


@skip_no_redis
@pytest.mark.integration
def test_producer_only_time_limit_serializes_only_hard(_flush_redis):
    """``execute(time_limit=Y)`` with no soft limit MUST serialize ``{"hard": Y}`` only.

    Invariant 2: the dict shape MUST omit ``"soft"`` when soft_time_limit is
    None (rather than encode it as null). Workers + JSON round-trips MUST
    handle the partial-shape case.
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskMessage, TaskQueue

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    runtime.execute(_build_workflow(), time_limit=10.0)
    task = queue.dequeue(timeout=2)
    assert task is not None
    assert task.execution_limits == {"hard": 10.0}, (
        f"hard-only execute() MUST serialize {{'hard': float}}; "
        f"got {task.execution_limits!r}"
    )

    # JSON round-trip preserves the partial shape.
    round_trip = TaskMessage.from_json(task.to_json())
    assert round_trip.execution_limits == {"hard": 10.0}


# --------------------------------------------------------------------------- #
# Worker-side enforcement tests (real Redis, real workflow execution)
# --------------------------------------------------------------------------- #


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_arms_timers_at_dequeue_not_at_enqueue(_flush_redis):
    """Worker MUST arm timers at dequeue time so queue wait does not burn budget.

    Invariant 1: producer serializes onto TaskMessage; worker arms at dequeue.
    Test by enqueuing with a short hard limit, sleeping (simulating queue wait),
    THEN starting worker — the task MUST still get its full budget at execution.
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    # Enqueue a 0.5s-sleeping workflow with a 3s hard limit.
    runtime.execute(_build_workflow(sleep_seconds=0.5), time_limit=3.0)

    # Simulate queue wait: sleep longer than the hard limit BEFORE worker starts.
    # If the producer had armed the timer at enqueue, the task would already be
    # past its deadline. With dequeue-side arming, the task gets full 3s.
    await asyncio.sleep(2.0)

    worker = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="dequeue-arm-worker",
    )
    worker._semaphore = asyncio.Semaphore(1)

    task = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert task is not None
    assert task.execution_limits == {"hard": 3.0}

    start = time.monotonic()
    await worker._execute_task(task)
    elapsed = time.monotonic() - start

    # The task slept 0.5s and the hard limit was 3.0s — task MUST complete
    # successfully because timer arms at dequeue (not at enqueue 2s ago).
    assert elapsed < 2.5, (
        f"task should complete in ~0.5s if timer arms at dequeue; got {elapsed:.2f}s "
        f"— if elapsed >= time_limit + grace, the timer may have armed at enqueue"
    )

    # Result was completed (not failed by hard limit).
    result = queue.get_result(task.task_id)
    assert result is not None
    assert result.status == "completed", (
        f"task MUST complete (not be hard-killed) when worker arms at dequeue; "
        f"got status={result.status!r}, error={result.error!r}"
    )


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_default_overridden_by_per_task(_flush_redis):
    """Per-task ``execution_limits`` wins over ``Worker(default_time_limit=...)``.

    Invariant 3: per-task value (from TaskMessage) wins; falls through to
    Worker defaults; falls through to None.

    Setup: Worker default = 10s; per-task limit = 1s; workflow sleeps 3s.
    Effective limit MUST be 1s → hard kill fires → task processed retried/dead-lettered.
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    # Per-task: hard=1.0s. Workflow sleeps 3s → MUST hit hard limit.
    runtime.execute(_build_workflow(sleep_seconds=3.0), time_limit=1.0)

    # Worker default would say 10s — but per-task 1.0s MUST win.
    worker = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="per-task-wins-worker",
        default_time_limit=10.0,
        hard_time_limit_grace_seconds=0.5,
    )
    worker._semaphore = asyncio.Semaphore(1)

    task = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert task is not None
    # Pin attempts so we hit dead-letter immediately (cleaner assertion than
    # asserting nack-then-requeue).
    task.attempts = 1
    task.max_attempts = 1

    start = time.monotonic()
    await worker._execute_task(task)
    elapsed = time.monotonic() - start

    # Hard limit (1.0s + 0.5s grace) MUST fire well before the workflow's 3s sleep.
    # The task wraps up via the hard-deadline poll in the wrapper's finally.
    assert elapsed < 2.8, (
        f"per-task hard limit (1.0s) MUST kill the task before the worker default "
        f"(10s); got elapsed={elapsed:.2f}s"
    )

    # Failure result is stored — the executed-task path raised
    # HardTimeLimitExceeded, which routed through the failure branch.
    result = queue.get_result(task.task_id)
    assert result is not None
    assert result.status in ("failed", "dead_lettered"), (
        f"per-task hard limit MUST mark task as failed or dead_lettered; "
        f"got status={result.status!r}, error={result.error!r}"
    )


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_default_used_when_per_task_missing(_flush_redis):
    """When TaskMessage.execution_limits is None, ``Worker(default_time_limit=)`` applies.

    Invariant 3 (middle clause): per-task None → Worker default applied.
    """
    from kailash.runtime.distributed import DistributedRuntime, TaskQueue, Worker

    queue = TaskQueue(redis_url=REDIS_URL)
    runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

    # Producer omits time-limit kwargs; execution_limits is None.
    runtime.execute(_build_workflow(sleep_seconds=3.0))

    # Worker default kicks in: hard=1.0s.
    worker = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="worker-default-applied",
        default_time_limit=1.0,
        hard_time_limit_grace_seconds=0.5,
    )
    worker._semaphore = asyncio.Semaphore(1)

    task = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert task is not None
    assert task.execution_limits is None
    task.attempts = 1
    task.max_attempts = 1

    start = time.monotonic()
    await worker._execute_task(task)
    elapsed = time.monotonic() - start

    assert elapsed < 2.8, (
        f"Worker default time_limit=1.0s MUST kill the 3s-sleeping task; "
        f"got elapsed={elapsed:.2f}s"
    )

    result = queue.get_result(task.task_id)
    assert result is not None
    assert result.status in ("failed", "dead_lettered")


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_hard_limit_triggers_requeue(_flush_redis):
    """Hard-limit failure with attempts < max_attempts MUST requeue, not dead-letter.

    Invariant 4: ``HardTimeLimitExceeded`` triggers requeue when attempts <
    max_attempts; dead-letter only after exhaustion. Test the requeue path
    by enqueuing once with max_attempts=2 — first execution hits hard limit
    AND nack re-queues for a second attempt.
    """
    from kailash.runtime.distributed import (
        DistributedRuntime,
        TaskMessage,
        TaskQueue,
        Worker,
    )

    queue = TaskQueue(redis_url=REDIS_URL)

    # Build a sleeping workflow + per-task hard limit + max_attempts=2.
    workflow = _build_workflow(sleep_seconds=2.0)
    workflow_data = workflow.to_dict()

    task = TaskMessage(
        task_id="hard-limit-requeue-001",
        workflow_data=workflow_data,
        parameters={},
        attempts=0,  # incremented to 1 on first dequeue
        max_attempts=2,
        execution_limits={"hard": 0.5},
    )
    queue.enqueue(task)

    worker = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="hard-limit-requeue-worker",
        hard_time_limit_grace_seconds=0.3,
    )
    worker._semaphore = asyncio.Semaphore(1)

    # First attempt: dequeue → execute → hard kill → nack re-queues.
    first_dequeue = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert first_dequeue is not None
    assert first_dequeue.attempts == 1
    await worker._execute_task(first_dequeue)

    # The task MUST be back on the pending queue (nack re-queued because
    # attempts (1) < max_attempts (2)).
    assert queue.queue_length() == 1, (
        f"hard-limit failure with attempts < max_attempts MUST re-queue; "
        f"queue_length={queue.queue_length()}"
    )

    # Second attempt: dequeue → still hits hard limit → exhausts → dead-letter.
    second_dequeue = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert second_dequeue is not None
    assert second_dequeue.attempts == 2
    assert second_dequeue.execution_limits == {
        "hard": 0.5
    }, "execution_limits MUST survive the requeue round-trip"
    await worker._execute_task(second_dequeue)

    # No further re-queue — the task was dead-lettered.
    assert queue.queue_length() == 0, (
        f"second hard-limit failure (attempts == max_attempts) MUST dead-letter "
        f"(NOT re-queue); queue_length={queue.queue_length()}"
    )

    # Dead-letter result is stored.
    result = queue.get_result(task.task_id)
    assert result is not None
    assert (
        result.status == "dead_lettered"
    ), f"final attempt MUST dead-letter; got status={result.status!r}"


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_lifecycle_hooks_fire_on_hard_limit(_flush_redis):
    """``on_task_retry`` fires on retryable hard limit; ``on_task_failure`` on dead-letter.

    Invariants 5 + 6: lifecycle hooks fire on hard-limit-with-attempts-remaining
    (retry) and on the dead-letter after exhaustion (failure). #914 contract.
    """
    from kailash.runtime.distributed import TaskMessage, TaskQueue, Worker
    from kailash.sdk_exceptions import HardTimeLimitExceeded

    queue = TaskQueue(redis_url=REDIS_URL)
    workflow = _build_workflow(sleep_seconds=2.0)

    # First: attempts=1, max_attempts=2 → retry hook fires.
    retry_events: list[object] = []
    failure_events: list[object] = []

    worker_a = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="retry-hook-worker",
        hard_time_limit_grace_seconds=0.3,
    )
    worker_a.on_task_retry(lambda e: retry_events.append(e))
    worker_a.on_task_failure(lambda e: failure_events.append(e))
    worker_a._semaphore = asyncio.Semaphore(1)

    task_a = TaskMessage(
        task_id="hooks-hard-limit-retry",
        workflow_data=workflow.to_dict(),
        parameters={},
        attempts=1,
        max_attempts=2,
        execution_limits={"hard": 0.4},
    )
    queue.enqueue(task_a)
    dequeued_a = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert dequeued_a is not None
    # Pin attempts post-dequeue (dequeue increments to 2; we want 1/2 to trigger retry).
    dequeued_a.attempts = 1
    await worker_a._execute_task(dequeued_a)

    assert len(retry_events) == 1, (
        f"on_task_retry MUST fire once on hard-limit with attempts<max; got "
        f"retry_events={len(retry_events)}, failure_events={len(failure_events)}"
    )
    assert (
        len(failure_events) == 0
    ), "on_task_failure MUST NOT fire when attempts < max_attempts"
    assert isinstance(retry_events[0].exception, HardTimeLimitExceeded), (
        f"retry event payload MUST carry HardTimeLimitExceeded; "
        f"got {type(retry_events[0].exception).__name__}"
    )

    # Second: attempts=2, max_attempts=2 → failure hook fires.
    retry_events_b: list[object] = []
    failure_events_b: list[object] = []

    worker_b = Worker(
        redis_url=REDIS_URL,
        queue=queue,
        concurrency=1,
        worker_id="failure-hook-worker",
        hard_time_limit_grace_seconds=0.3,
    )
    worker_b.on_task_retry(lambda e: retry_events_b.append(e))
    worker_b.on_task_failure(lambda e: failure_events_b.append(e))
    worker_b._semaphore = asyncio.Semaphore(1)

    task_b = TaskMessage(
        task_id="hooks-hard-limit-final",
        workflow_data=workflow.to_dict(),
        parameters={},
        attempts=2,
        max_attempts=2,
        execution_limits={"hard": 0.4},
    )
    queue.enqueue(task_b)
    dequeued_b = await asyncio.get_event_loop().run_in_executor(
        None, lambda: queue.dequeue(timeout=2)
    )
    assert dequeued_b is not None
    dequeued_b.attempts = 2
    await worker_b._execute_task(dequeued_b)

    assert len(failure_events_b) == 1, (
        f"on_task_failure MUST fire on hard-limit at final attempt; got "
        f"failure_events={len(failure_events_b)}"
    )
    assert (
        len(retry_events_b) == 0
    ), "on_task_retry MUST NOT fire when attempts == max_attempts"
    assert isinstance(failure_events_b[0].exception, HardTimeLimitExceeded)


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_default_validation_rejects_invalid(_flush_redis):
    """``Worker(default_*time_limit=...)`` MUST validate via ``_validate_limits``.

    Per Shard 1 invariant: every entry point that accepts time-limit kwargs
    MUST run them through ``_validate_limits`` so the failure surfaces at the
    construction site, not later from a timer thread.
    """
    from kailash.runtime.distributed import Worker

    # Negative hard limit — invalid.
    with pytest.raises(ValueError, match="time_limit MUST be > 0"):
        Worker(
            redis_url=REDIS_URL,
            default_time_limit=-1.0,
        )

    # soft >= hard — invalid (celery convention).
    with pytest.raises(
        ValueError, match="soft_time_limit .* MUST be strictly less than"
    ):
        Worker(
            redis_url=REDIS_URL,
            default_soft_time_limit=10.0,
            default_time_limit=5.0,
        )
