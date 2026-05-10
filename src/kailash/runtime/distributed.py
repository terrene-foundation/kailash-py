"""Distributed runtime with Redis-backed task queue and multi-worker execution.

This module provides a distributed runtime architecture that enables horizontal
scaling of Kailash workflow execution across multiple worker processes or machines.
Tasks are enqueued to a Redis-backed task queue and processed by worker instances
that can run on separate machines.

Key components:
    - TaskQueue: Redis-backed queue with reliable delivery (BLMOVE pattern),
      visibility timeouts, and automatic dead-letter handling.
    - DistributedRuntime: Extends BaseRuntime to enqueue workflows to the task
      queue instead of executing them locally.
    - Worker: Dequeue loop with configurable concurrency, heartbeat monitoring,
      and dead worker detection.

Configuration:
    Set ``KAILASH_REDIS_URL`` environment variable or pass ``redis_url`` directly
    to the constructors.

Example:
    Submitting a workflow::

        >>> from kailash.runtime.distributed import DistributedRuntime
        >>> runtime = DistributedRuntime(redis_url="redis://localhost:6379/0")
        >>> workflow = WorkflowBuilder().build()
        >>> results, run_id = runtime.execute(workflow)
        >>> # results contains {"status": "queued", "run_id": run_id}

    Running a worker::

        >>> from kailash.runtime.distributed import Worker
        >>> worker = Worker(redis_url="redis://localhost:6379/0", concurrency=4)
        >>> await worker.start()  # Blocks, processing tasks until stopped
"""

from __future__ import annotations

import asyncio
import builtins
import inspect
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from kailash.runtime._queue_keys import (
    DEFAULT_QUEUE_NAME,
    make_processing_key,
    make_queue_key,
    validate_queue_name,
)
from kailash.runtime._time_limits import (
    _TimeLimitClassifier,
    _validate_limits,
    arm_time_limits,
)
from kailash.runtime.base import BaseRuntime
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.lifecycle_events import TaskEvent, TaskEventHandler
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
)
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)

# Redis key constants
_QUEUE_KEY = "kailash:tasks:pending"
_PROCESSING_KEY = "kailash:tasks:processing"
_RESULTS_PREFIX = "kailash:results:"
_TASK_PREFIX = "kailash:task:"
_HEARTBEAT_PREFIX = "kailash:worker:heartbeat:"
_WORKER_SET_KEY = "kailash:workers"


@dataclass
class TaskMessage:
    """Represents a task submitted to the distributed queue.

    Attributes:
        task_id: Unique task identifier (also used as run_id).
        workflow_data: Serialized workflow definition.
        parameters: Execution parameters.
        submitted_at: Unix timestamp when the task was submitted.
        visibility_timeout: Seconds before a processing task becomes
            eligible for re-delivery.
        attempts: Number of times this task has been attempted.
        max_attempts: Maximum delivery attempts before dead-lettering.
        execution_limits: Optional per-task time-limit dict produced by
            ``DistributedRuntime.execute(soft_time_limit=, time_limit=)``
            (issue #912 Shard 4). Shape:
            ``{"soft": <float seconds>, "hard": <float seconds>}``;
            either key may be omitted when the corresponding limit is
            ``None`` (so an old worker or a producer that only set the
            hard limit serializes a partial dict). The wire format is
            ONE optional field so older workers running pre-Shard-4 SDK
            silently ignore it (forward-compat). The worker arms the
            timers at dequeue (NOT enqueue) so queue wait time does
            NOT consume the task's budget. Default ``None`` (no limit).
        queue_name: Logical queue this task targets. Defaults to
            ``"default"`` so legacy single-queue producers and workers
            interoperate byte-for-byte (the default queue resolves to
            the legacy Redis list key ``kailash:tasks:pending``).
            Older-SDK ``TaskMessage`` JSON without ``queue_name``
            deserializes as ``"default"``. Issue #911 Shard 1.
    """

    task_id: str = ""
    workflow_data: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    submitted_at: float = 0.0
    visibility_timeout: int = 300  # 5 minutes default
    attempts: int = 0
    max_attempts: int = 3
    execution_limits: Optional[Dict[str, float]] = None
    queue_name: str = DEFAULT_QUEUE_NAME

    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage.

        ``execution_limits`` is included only when set so the wire format
        stays compact for the common no-limit case AND so older workers
        running a pre-Shard-4 SDK do not have to pattern-match a new
        field name on every dequeue. Workers running this SDK or newer
        read the field; workers running an older SDK ignore it.
        """
        payload: Dict[str, Any] = {
            "task_id": self.task_id,
            "workflow_data": self.workflow_data,
            "parameters": self.parameters,
            "submitted_at": self.submitted_at,
            "visibility_timeout": self.visibility_timeout,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }
        if self.execution_limits is not None:
            payload["execution_limits"] = self.execution_limits
        # #911 Shard 1: emit queue_name only when non-default so the
        # default-queue wire format stays byte-identical to pre-#911
        # JSON. Older workers that don't know the field continue to
        # parse default-queue messages unchanged.
        if self.queue_name != DEFAULT_QUEUE_NAME:
            payload["queue_name"] = self.queue_name
        return json.dumps(payload)

    @classmethod
    def from_json(cls, data: str) -> "TaskMessage":
        """Deserialize from JSON string.

        Older-SDK ``TaskMessage`` JSON without ``execution_limits``
        deserializes as ``execution_limits=None`` (the dataclass
        default), preserving the forward-compat invariant.
        """
        parsed = json.loads(data)
        known = {k: v for k, v in parsed.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class TaskResult:
    """Result of a completed task.

    Attributes:
        task_id: The task that produced this result.
        status: One of "completed", "failed", "dead_lettered".
        result_data: The workflow execution results (if completed).
        error: Error message (if failed).
        completed_at: Unix timestamp of completion.
        worker_id: ID of the worker that processed this task.
        execution_time: Duration in seconds.
    """

    task_id: str = ""
    status: str = "completed"
    result_data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    completed_at: float = 0.0
    worker_id: str = ""
    execution_time: float = 0.0

    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage."""
        return json.dumps(
            {
                "task_id": self.task_id,
                "status": self.status,
                "result_data": self.result_data,
                "error": self.error,
                "completed_at": self.completed_at,
                "worker_id": self.worker_id,
                "execution_time": self.execution_time,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "TaskResult":
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        known = {k: v for k, v in parsed.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class TaskQueue:
    """Redis-backed task queue with reliable delivery.

    Uses the BLMOVE pattern for reliable delivery: tasks are atomically
    moved from the pending queue to a processing list when dequeued. If a
    worker crashes, visibility timeout expiry makes the task eligible for
    re-delivery.

    Args:
        redis_url: Redis connection URL.
        queue_key: Redis key for the pending queue.
        processing_key: Redis key for the processing list.
        default_visibility_timeout: Default seconds before re-delivery.
        result_ttl: TTL in seconds for completed task results.

    Example:
        >>> queue = TaskQueue(redis_url="redis://localhost:6379/0")
        >>> task = TaskMessage(task_id="abc", workflow_data={...})
        >>> queue.enqueue(task)
        >>> dequeued = queue.dequeue(timeout=5)
    """

    def __init__(
        self,
        redis_url: str = "",
        queue_key: str = _QUEUE_KEY,
        processing_key: str = _PROCESSING_KEY,
        default_visibility_timeout: int = 300,
        result_ttl: int = 3600,
    ):
        self._redis_url = redis_url or os.environ.get("KAILASH_REDIS_URL", "")
        self._queue_key = queue_key
        self._processing_key = processing_key
        self._default_visibility_timeout = default_visibility_timeout
        self._result_ttl = result_ttl
        self._client = None

    def _get_client(self):
        """Lazily create and return a Redis client."""
        if self._client is None:
            import redis as redis_lib

            from kailash.utils.validation import validate_redis_url

            validate_redis_url(self._redis_url)
            self._client = redis_lib.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._client

    def enqueue(self, task: TaskMessage) -> str:
        """Add a task to the pending queue.

        Args:
            task: The task message to enqueue.

        Returns:
            The task_id for tracking.

        Raises:
            ConnectionError: If Redis is unreachable.
        """
        if not task.task_id:
            task.task_id = str(uuid.uuid4())
        if task.submitted_at == 0.0:
            task.submitted_at = time.time()
        if task.visibility_timeout == 0:
            task.visibility_timeout = self._default_visibility_timeout

        client = self._get_client()
        # Store the full task data separately for inspection
        client.set(
            f"{_TASK_PREFIX}{task.task_id}",
            task.to_json(),
            ex=self._result_ttl * 2,  # Keep task data longer than results
        )
        # Push task_id to the queue (lightweight reference)
        client.lpush(self._queue_key, task.to_json())

        logger.info("Enqueued task %s to queue '%s'", task.task_id, self._queue_key)
        return task.task_id

    def dequeue(self, timeout: int = 5) -> Optional[TaskMessage]:
        """Dequeue a task using BLMOVE for reliable delivery.

        Atomically moves the task from the pending queue to the processing
        list. If the worker crashes, the task remains in the processing list
        and can be recovered.

        Args:
            timeout: Seconds to block waiting for a task. 0 means non-blocking.

        Returns:
            A TaskMessage if one was available, None otherwise.
        """
        client = self._get_client()
        raw = client.blmove(
            self._queue_key, self._processing_key, timeout, "RIGHT", "LEFT"
        )
        if raw is None:
            return None

        try:
            task = TaskMessage.from_json(cast(str, raw))
            task.attempts += 1
            # Update the task in the processing list with incremented attempts
            return task
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Failed to parse task from queue: %s", exc)
            # Remove malformed message from processing list
            client.lrem(self._processing_key, 1, cast(str, raw))
            return None

    def ack(self, task: TaskMessage) -> bool:
        """Acknowledge successful task completion.

        Removes the task from the processing list and stores the result.

        Args:
            task: The completed task.

        Returns:
            True if acknowledgment succeeded.
        """
        client = self._get_client()
        # Remove from processing list (the original JSON before attempts increment)
        # We search by task_id in the processing list
        removed = self._remove_from_processing(task.task_id)
        logger.debug("Acknowledged task %s (removed=%s)", task.task_id, removed)
        return removed

    def nack(self, task: TaskMessage) -> bool:
        """Negatively acknowledge a task (re-queue or dead-letter).

        If the task has exceeded max_attempts, it is dead-lettered.
        Otherwise, it is re-queued for another attempt.

        Args:
            task: The failed task.

        Returns:
            True if the nack was processed.
        """
        client = self._get_client()
        self._remove_from_processing(task.task_id)

        if task.attempts >= task.max_attempts:
            # Dead-letter: store as failed result
            result = TaskResult(
                task_id=task.task_id,
                status="dead_lettered",
                error=f"Exceeded max attempts ({task.max_attempts})",
                completed_at=time.time(),
            )
            self.store_result(result)
            logger.warning(
                "Task %s dead-lettered after %d attempts",
                task.task_id,
                task.attempts,
            )
            return True

        # Re-queue with incremented attempts
        client.lpush(self._queue_key, task.to_json())
        logger.info(
            "Task %s re-queued (attempt %d/%d)",
            task.task_id,
            task.attempts,
            task.max_attempts,
        )
        return True

    def store_result(self, result: TaskResult) -> bool:
        """Store a task result in Redis with configured TTL.

        Args:
            result: The task result to store.

        Returns:
            True if storage succeeded.
        """
        client = self._get_client()
        key = f"{_RESULTS_PREFIX}{result.task_id}"
        client.set(key, result.to_json(), ex=self._result_ttl)
        return True

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Retrieve a task result by task_id.

        Args:
            task_id: The task identifier.

        Returns:
            The task result, or None if not found or expired.
        """
        client = self._get_client()
        raw = client.get(f"{_RESULTS_PREFIX}{task_id}")
        if raw is None:
            return None
        try:
            return TaskResult.from_json(cast(str, raw))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to parse result for task %s: %s", task_id, exc)
            return None

    def queue_length(self) -> int:
        """Get the number of pending tasks in the queue.

        Returns:
            Number of pending tasks.
        """
        client = self._get_client()
        return cast(int, client.llen(self._queue_key))

    def processing_length(self) -> int:
        """Get the number of tasks currently being processed.

        Returns:
            Number of tasks in the processing list.
        """
        client = self._get_client()
        return cast(int, client.llen(self._processing_key))

    def _remove_from_processing(self, task_id: str) -> bool:
        """Remove a task from the processing list by scanning for its task_id.

        Since BLMOVE stores the full JSON, we need to scan and match.

        Args:
            task_id: Task identifier to remove.

        Returns:
            True if found and removed.
        """
        client = self._get_client()
        # Scan the processing list for a matching task_id
        items = cast(list, client.lrange(self._processing_key, 0, -1))
        for item in items:
            try:
                parsed = json.loads(item)
                if parsed.get("task_id") == task_id:
                    client.lrem(self._processing_key, 1, item)
                    return True
            except (json.JSONDecodeError, TypeError):
                continue
        return False

    def recover_stale_tasks(self, stale_threshold: int = 600) -> int:
        """Recover tasks stuck in the processing list beyond the threshold.

        Checks each task in the processing list. If a task has been processing
        for longer than ``stale_threshold`` seconds, it is re-queued (nack'd).

        Args:
            stale_threshold: Seconds after which a processing task is
                considered stale.

        Returns:
            Number of tasks recovered.
        """
        client = self._get_client()
        items = cast(list, client.lrange(self._processing_key, 0, -1))
        recovered = 0
        now = time.time()

        for item in items:
            try:
                parsed = json.loads(item)
                submitted = parsed.get("submitted_at", 0)
                if now - submitted > stale_threshold:
                    task = TaskMessage.from_json(item)
                    self.nack(task)
                    recovered += 1
            except (json.JSONDecodeError, TypeError):
                # Remove malformed entries
                client.lrem(self._processing_key, 1, item)
                recovered += 1

        if recovered > 0:
            logger.info("Recovered %d stale tasks from processing list", recovered)
        return recovered

    def ping(self) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis responds to PING.
        """
        try:
            return cast(bool, self._get_client().ping())
        except Exception:
            return False

    def close(self) -> None:
        """Release the lazily-created Redis client.

        ``_get_client`` constructs a ``redis.Redis`` connection pool on
        first use; multi-queue runtimes that route through ``_queue_for``
        accumulate one client per named queue. ``DistributedRuntime.close``
        iterates ``self._queues`` and calls this method on each cached
        TaskQueue so shutdown does not leak per-queue Redis clients.

        Idempotent — calling ``close()`` twice is a no-op.

        Issue #911 Shard 2 followup — R1-005 redteam finding.
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "TaskQueue.close: ignoring error from Redis client close: %s",
                    exc,
                )
            finally:
                self._client = None


class DistributedRuntime(BaseRuntime):
    """Runtime that enqueues workflows to a distributed task queue.

    Instead of executing workflows locally, this runtime submits them to a
    Redis-backed task queue for processing by remote :class:`Worker` instances.
    The ``execute()`` method returns immediately with a queued status and a
    ``run_id`` that can be used to poll for results.

    Args:
        redis_url: Redis connection URL. Defaults to ``KAILASH_REDIS_URL`` env var.
        queue: Optional pre-configured :class:`TaskQueue` instance.
        visibility_timeout: Default visibility timeout for tasks.
        result_ttl: TTL for task results in seconds.
        **kwargs: Additional arguments passed to :class:`BaseRuntime`.

    Example:
        >>> runtime = DistributedRuntime(redis_url="redis://localhost:6379/0")
        >>> results, run_id = runtime.execute(workflow, parameters={"key": "value"})
        >>> print(results)  # {"status": "queued", "run_id": "..."}
        >>> # Later, poll for results:
        >>> result = runtime.get_result(run_id)
    """

    def __init__(
        self,
        redis_url: str = "",
        queue: Optional[TaskQueue] = None,
        visibility_timeout: int = 300,
        result_ttl: int = 3600,
        default_queue: str = DEFAULT_QUEUE_NAME,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._redis_url = redis_url or os.environ.get("KAILASH_REDIS_URL", "")
        # Producer-side default queue. Validated at construction so an
        # invalid name fails loud instead of silently stranding tasks
        # at first execute() call. Issue #911 Shard 1.
        validate_queue_name(default_queue)
        self._default_queue = default_queue
        self._queue = queue or TaskQueue(
            redis_url=self._redis_url,
            queue_key=make_queue_key(default_queue),
            processing_key=make_processing_key(default_queue),
            default_visibility_timeout=visibility_timeout,
            result_ttl=result_ttl,
        )
        self._visibility_timeout = visibility_timeout
        self._result_ttl = result_ttl
        # Per-queue TaskQueue cache so every `execute(queue=...)` call
        # routes through ONE TaskQueue instance per queue name (sharing
        # the same Redis client, with the canonical Redis-list-key from
        # ``make_queue_key``). The default-queue entry mirrors
        # ``self._queue`` so legacy callers see no behavior change.
        self._queues: Dict[str, TaskQueue] = {default_queue: self._queue}

    def close(self) -> None:
        """Release distributed runtime resources.

        Cleans up the task queue connection and any execution metadata.
        Closes every per-queue TaskQueue instance the runtime created
        through ``execute(queue=...)`` (#911 Shard 1) so multi-queue
        runtimes do not leak Redis clients on shutdown.
        """
        self._execution_metadata.clear()
        # Close every cached per-queue TaskQueue. ``self._queue`` is
        # always present in ``self._queues`` under the default-queue
        # name (seeded at __init__) so closing the cache covers both
        # the legacy single-queue path and any new per-queue routes.
        for tq in list(self._queues.values()):
            _close = getattr(tq, "close", None)
            if _close is not None:
                _close()
        self._queues.clear()

    def execute(
        self,
        workflow: Workflow,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        soft_time_limit: float | None = None,
        time_limit: float | None = None,
        queue: Optional[str] = None,
        **kwargs,
    ) -> Tuple[Dict[str, Any], str]:
        """Submit a workflow to the distributed task queue.

        Instead of executing locally, the workflow is serialized and enqueued.
        Returns immediately with a queued status.

        Args:
            workflow: The workflow to execute.
            parameters: Optional execution parameters.
            soft_time_limit: Optional advisory deadline in seconds. Per
                #912 Shard 4, this serializes onto
                ``TaskMessage.execution_limits["soft"]`` and the worker
                arms the timer at dequeue (NOT enqueue) so queue wait
                does NOT burn the task's budget.
            time_limit: Optional unconditional kill deadline in seconds.
                Per #912 Shard 4, this serializes onto
                ``TaskMessage.execution_limits["hard"]`` and the worker
                arms the hard-deadline timer at dequeue. When the hard
                deadline fires, the task is requeued (NOT dead-lettered)
                if ``attempts < max_attempts``; dead-lettered only after
                exhaustion.
            queue: Optional logical queue name for routing. Defaults to
                this runtime's ``default_queue`` (constructor kwarg,
                itself defaulting to ``"default"``). The
                ``"default"`` queue resolves to the legacy Redis list
                key ``kailash:tasks:pending`` for byte-identical
                back-compat with single-queue deployments. Non-default
                names get the suffix ``:<name>`` (issue #911 Shard 1).

        Returns:
            Tuple of (status_dict, run_id) where status_dict contains
            ``{"status": "queued", "run_id": run_id, "queue_length": N}``.

        Time-Limit Example (per-task limits travel through the queue)::

            from kailash.runtime.distributed import DistributedRuntime

            runtime = DistributedRuntime(redis_url="redis://localhost:6379/0")
            status, run_id = runtime.execute(
                workflow,
                soft_time_limit=2.0,   # advisory; raises SoftTimeLimitExceeded
                time_limit=5.0,         # hard kill (after grace); requeue path
            )
            # The Worker arms the timers at DEQUEUE (not enqueue) so queue
            # wait time does NOT consume the task's budget. Per-task limits
            # ALWAYS win over Worker(default_*_time_limit) defaults.
        """
        # #912 Shard 1: validate typed time-limit kwargs at the entry point.
        _validate_limits(soft_time_limit, time_limit)

        # #911 Shard 1: resolve and validate the queue name BEFORE
        # building any task or run-id metadata so an invalid queue
        # raises ValueError from the public API surface, not from a
        # half-constructed task.
        queue_name = queue if queue is not None else self._default_queue
        validate_queue_name(queue_name)
        target_queue = self._queue_for(queue_name)

        run_id = self._generate_run_id()
        metadata = self._initialize_execution_metadata(workflow, run_id)
        self._execution_metadata[run_id] = metadata

        # Serialize the workflow for queue transport
        workflow_data = self._serialize_workflow(workflow)

        # #912 Shard 4: build the optional execution_limits dict from the
        # validated kwargs. Shape is ONE optional dict (NOT two separate
        # fields) so older workers silently ignore the new field. Keys
        # are omitted when their corresponding limit is None so the wire
        # form stays compact.
        execution_limits: Optional[Dict[str, float]] = None
        if soft_time_limit is not None or time_limit is not None:
            execution_limits = {}
            if soft_time_limit is not None:
                execution_limits["soft"] = float(soft_time_limit)
            if time_limit is not None:
                execution_limits["hard"] = float(time_limit)

        task = TaskMessage(
            task_id=run_id,
            workflow_data=workflow_data,
            parameters=parameters or {},
            visibility_timeout=self._visibility_timeout,
            execution_limits=execution_limits,
            queue_name=queue_name,
        )

        target_queue.enqueue(task)

        self._update_execution_metadata(run_id, {"status": "queued"})

        return {
            "status": "queued",
            "run_id": run_id,
            "queue_length": target_queue.queue_length(),
            "queue_name": queue_name,
        }, run_id

    def _queue_for(self, queue_name: str) -> TaskQueue:
        """Return (memoized) the TaskQueue routing to ``queue_name``.

        Each named queue gets its own TaskQueue instance with a queue_key
        derived through ``make_queue_key`` — guaranteeing producer +
        worker share the canonical key. The default-queue entry is
        seeded in ``__init__`` to alias ``self._queue`` so legacy
        callers see no behavior change. Issue #911 Shard 1.
        """
        cached = self._queues.get(queue_name)
        if cached is not None:
            return cached
        new_queue = TaskQueue(
            redis_url=self._redis_url,
            queue_key=make_queue_key(queue_name),
            processing_key=make_processing_key(queue_name),
            default_visibility_timeout=self._visibility_timeout,
            result_ttl=self._result_ttl,
        )
        self._queues[queue_name] = new_queue
        return new_queue

    def get_result(self, run_id: str) -> Optional[TaskResult]:
        """Poll for a task result by run_id.

        Args:
            run_id: The run_id returned by ``execute()``.

        Returns:
            A :class:`TaskResult` if available, None if still processing.
        """
        return self._queue.get_result(run_id)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status metrics.

        Returns the default queue's pending / processing counts at the
        top level for back-compat with single-queue dashboards, plus a
        ``queues`` map with per-queue counts for every cached named
        queue (#911 Shard 2 followup — R1-003 redteam finding). The
        default queue always appears in ``queues`` under the
        configured ``default_queue`` name (typically ``"default"``).

        Returns:
            Dictionary with the shape::

                {
                    "pending": <int>,
                    "processing": <int>,
                    "redis_available": <bool>,
                    "queues": {
                        "<name>": {"pending": <int>, "processing": <int>},
                        ...
                    },
                }
        """
        per_queue: Dict[str, Dict[str, int]] = {}
        for name, tq in self._queues.items():
            try:
                per_queue[name] = {
                    "pending": tq.queue_length(),
                    "processing": tq.processing_length(),
                }
            except Exception as exc:
                logger.warning(
                    "get_queue_status: failed to read queue %r: %s", name, exc
                )
                per_queue[name] = {"pending": -1, "processing": -1}
        return {
            "pending": self._queue.queue_length(),
            "processing": self._queue.processing_length(),
            "redis_available": self._queue.ping(),
            "queues": per_queue,
        }

    def _serialize_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        """Serialize a workflow for queue transport.

        Uses Workflow.to_dict() for round-trip compatible serialization.
        The Worker deserializes with Workflow.from_dict().

        Args:
            workflow: The workflow to serialize.

        Returns:
            JSON-serializable workflow representation.
        """
        return workflow.to_dict()


@dataclass
class _QueueSpec:
    """Per-queue runtime config inside a multi-queue ``Worker``.

    Holds the queue's TaskQueue (already configured with
    ``make_queue_key(name)``) plus the per-queue concurrency and
    visibility-timeout. Issue #911 Shard 2.
    """

    name: str
    concurrency: int
    visibility_timeout: int
    queue: TaskQueue
    semaphore: Optional[asyncio.Semaphore] = None


def _parse_queue_spec(raw: Any) -> Tuple[int, int]:
    """Parse a single ``Worker(queues=)`` value into (concurrency, vt).

    Accepts EITHER a bare ``int`` (concurrency only; visibility_timeout
    defaults to 300) OR a dict with ``concurrency`` (required) and
    optional ``visibility_timeout`` overrides:

        queues={"fast": 8}                                     # bare int
        queues={"slow": {"concurrency": 2, "visibility_timeout": 1800}}

    Issue #911 Shard 2 failure-point #4.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, dict)):
        raise ValueError(
            "queues entry must be int or dict with 'concurrency' key, "
            f"got {type(raw).__name__}"
        )
    if isinstance(raw, int):
        if raw < 1:
            raise ValueError(f"queue concurrency must be >= 1, got {raw}")
        return raw, 300
    # dict path
    if "concurrency" not in raw:
        raise ValueError("queues entry dict must include 'concurrency' key")
    concurrency_raw = raw["concurrency"]
    if isinstance(concurrency_raw, bool) or not isinstance(concurrency_raw, int):
        raise ValueError(
            "queues entry concurrency must be int, got "
            f"{type(concurrency_raw).__name__}"
        )
    if concurrency_raw < 1:
        raise ValueError(
            f"queues entry concurrency must be >= 1, got {concurrency_raw}"
        )
    vt_raw = raw.get("visibility_timeout", 300)
    if isinstance(vt_raw, bool) or not isinstance(vt_raw, int):
        raise ValueError(
            "queues entry visibility_timeout must be int, got "
            f"{type(vt_raw).__name__}"
        )
    if vt_raw < 1:
        raise ValueError(
            "queues entry visibility_timeout must be >= 1, " f"got {vt_raw}"
        )
    return concurrency_raw, vt_raw


# Wrappers the SDK adds around user / node errors. When recovering the
# user-meaningful root cause from a recorded node failure we walk past these
# so retry-classification consumers see ZeroDivisionError, ValueError, etc.
# instead of the SDK's bookkeeping exception.
_SDK_WRAPPER_EXC_NAMES = frozenset({"NodeExecutionError", "WorkflowExecutionError"})


def _unwrap_node_failure(payload: Dict[str, Any], node_id: str) -> BaseException:
    """Return the user-meaningful exception for a recorded node failure.

    LocalRuntime stores the actual exception object under ``_exception`` when
    a leaf node fails (see ``runtime.local`` issue #941 fix). This helper
    walks ``__cause__`` then ``__context__`` past SDK wrapper exceptions to
    surface the user's original error type. Falls back to reconstructing
    by name if ``_exception`` is missing (defensive — older callers, JSON
    round-trip, etc.) and finally to ``RuntimeError`` if nothing else fits.
    """

    exc = payload.get("_exception")
    if isinstance(exc, BaseException):
        seen: set[int] = set()
        current: Optional[BaseException] = exc
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if type(current).__name__ not in _SDK_WRAPPER_EXC_NAMES:
                return current
            current = current.__cause__ or current.__context__
        return exc

    error_type_name = payload.get("error_type") or "RuntimeError"
    error_msg = payload.get("error") or f"node '{node_id}' failed"
    exc_cls = getattr(builtins, error_type_name, None)
    if not (isinstance(exc_cls, type) and issubclass(exc_cls, BaseException)):
        exc_cls = RuntimeError
    return exc_cls(error_msg)


class Worker:
    """Task queue worker that dequeues and executes workflows.

    Runs a continuous loop that dequeues tasks from the Redis queue, executes
    them using a local runtime, and stores results back in Redis.

    Features:
        - Configurable concurrency (number of parallel tasks).
        - Heartbeat monitoring for dead worker detection.
        - Graceful shutdown via signals (SIGINT, SIGTERM).
        - Automatic stale task recovery on startup.

    Args:
        redis_url: Redis connection URL.
        queue: Optional pre-configured TaskQueue.
        concurrency: Number of tasks to process in parallel.
        heartbeat_interval: Seconds between heartbeat updates.
        dead_worker_timeout: Seconds before a worker is considered dead.
        worker_id: Unique worker identifier. Auto-generated if not provided.
        runtime_factory: Optional callable that returns a runtime instance for
            executing tasks. Defaults to creating a LocalRuntime.
        default_soft_time_limit: Default advisory deadline in seconds applied to
            tasks whose ``TaskMessage.execution_limits`` does NOT specify a soft
            limit (#912 Shard 4). Per-task limits ALWAYS win over this default.
            ``None`` (default) = no soft deadline applied when the task has none.
        default_time_limit: Default unconditional kill deadline in seconds applied
            to tasks whose ``TaskMessage.execution_limits`` does NOT specify a
            hard limit (#912 Shard 4). Per-task limits ALWAYS win over this
            default. ``None`` (default) = no hard deadline applied when the task
            has none.
        hard_time_limit_grace_seconds: Wind-down window between the hard deadline
            firing and the unconditional kill (#912 Shard 2). Default 1.0s; MUST
            be >= 0.

    Example:
        >>> worker = Worker(
        ...     redis_url="redis://localhost:6379/0",
        ...     concurrency=4,
        ... )
        >>> await worker.start()  # Runs until stopped

        # With operator-set defaults (#912 Shard 4) — per-task
        # ``DistributedRuntime.execute(soft_time_limit=, time_limit=)``
        # ALWAYS wins over these defaults; defaults apply only when the
        # task did not set its own:
        >>> worker = Worker(
        ...     redis_url="redis://localhost:6379/0",
        ...     concurrency=4,
        ...     default_soft_time_limit=30.0,
        ...     default_time_limit=60.0,
        ...     hard_time_limit_grace_seconds=2.0,
        ... )
    """

    def __init__(
        self,
        redis_url: str = "",
        queue: Optional[TaskQueue] = None,
        concurrency: int = 1,
        heartbeat_interval: int = 30,
        dead_worker_timeout: int = 90,
        worker_id: Optional[str] = None,
        runtime_factory: Optional[Callable] = None,
        *,
        default_soft_time_limit: float | None = None,
        default_time_limit: float | None = None,
        hard_time_limit_grace_seconds: float = 1.0,
        queues: Optional[Dict[str, Any]] = None,
    ):
        # #912 Shard 4 + Shard 6: validate Worker-default time limits AND
        # the grace_seconds at construction so bad configuration surfaces
        # here, NOT later from a timer thread on the first dequeue.
        # Reuses the Shard 1 validator so the contract stays single-
        # sourced (per security.md § Multi-Site Kwarg Plumbing).
        _validate_limits(
            default_soft_time_limit,
            default_time_limit,
            grace_seconds=hard_time_limit_grace_seconds,
        )

        # #911 Shard 2: ``queue`` (legacy single-queue path) and
        # ``queues`` (multi-queue map) are mutually exclusive — passing
        # both is a configuration error (the agent has no canonical way
        # to merge them) so we raise at construction, not silently
        # prefer one. Per zero-tolerance.md Rule 3 (no silent fallback).
        if queue is not None and queues is not None:
            raise ValueError(
                "Worker(queue=, queues=) are mutually exclusive — "
                "pass ONE or the other"
            )

        self._redis_url = redis_url or os.environ.get("KAILASH_REDIS_URL", "")
        self._heartbeat_interval = heartbeat_interval
        self._dead_worker_timeout = dead_worker_timeout
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        self._runtime_factory = runtime_factory
        self._default_soft_time_limit = default_soft_time_limit
        self._default_time_limit = default_time_limit
        self._hard_time_limit_grace_seconds = hard_time_limit_grace_seconds
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._redis_client = None

        # Resolve the multi-queue map. Three input shapes resolve to the
        # same internal ``self._queue_specs`` table (one entry per
        # logical queue) so the rest of the worker is queue-agnostic:
        #   1. Legacy ``Worker(concurrency=N)`` → single ``"default"``
        #      queue with N concurrency. Byte-identical wire format
        #      to pre-#911.
        #   2. Legacy ``Worker(queue=tq)`` (pre-built TaskQueue) →
        #      single ``"default"`` queue using the passed instance.
        #   3. New ``Worker(queues={"fast": 8, "slow": {"concurrency":
        #      2, "visibility_timeout": 1800}})`` → one entry per
        #      named queue, with optional per-queue visibility-timeout
        #      override (failure-point #4).
        self._queue_specs: Dict[str, "_QueueSpec"] = {}
        if queues is not None:
            if not queues:
                raise ValueError("Worker(queues={}) must declare at least one queue")
            for name, raw_spec in queues.items():
                validate_queue_name(name)
                queue_concurrency, vt = _parse_queue_spec(raw_spec)
                tq = TaskQueue(
                    redis_url=self._redis_url,
                    queue_key=make_queue_key(name),
                    processing_key=make_processing_key(name),
                    default_visibility_timeout=vt,
                )
                self._queue_specs[name] = _QueueSpec(
                    name=name,
                    concurrency=queue_concurrency,
                    visibility_timeout=vt,
                    queue=tq,
                )
        else:
            tq = queue or TaskQueue(redis_url=self._redis_url)
            self._queue_specs[DEFAULT_QUEUE_NAME] = _QueueSpec(
                name=DEFAULT_QUEUE_NAME,
                concurrency=max(1, concurrency),
                visibility_timeout=tq._default_visibility_timeout,
                queue=tq,
            )

        # Legacy attributes preserved for back-compat with code that
        # reads them (get_status, _heartbeat_loop, etc.). When multi-
        # queue, ``self._queue`` aliases the default queue (or the
        # first declared queue if no default was declared) so legacy
        # callers see SOMETHING; ``self._concurrency`` reports the
        # AGGREGATE concurrency across declared queues.
        primary = self._queue_specs.get(
            DEFAULT_QUEUE_NAME,
            next(iter(self._queue_specs.values())),
        )
        self._queue = primary.queue
        self._concurrency = sum(spec.concurrency for spec in self._queue_specs.values())

        # Lifecycle hook registries (issue #914). Each list holds zero or more
        # handlers, dispatched in registration order. Handler exceptions are
        # caught + logged at WARN per `observability.md` Rule 3a — handler
        # failure MUST NOT block task lifecycle.
        self._hooks_prerun: List[TaskEventHandler] = []
        self._hooks_postrun: List[TaskEventHandler] = []
        self._hooks_success: List[TaskEventHandler] = []
        self._hooks_retry: List[TaskEventHandler] = []
        self._hooks_failure: List[TaskEventHandler] = []

    def _get_redis_client(self):
        """Get the Redis client for heartbeat operations."""
        if self._redis_client is None:
            import redis as redis_lib

            from kailash.utils.validation import validate_redis_url

            validate_redis_url(self._redis_url)
            self._redis_client = redis_lib.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._redis_client

    def _get_runtime(self):
        """Create a runtime instance for task execution.

        Returns:
            A runtime instance (LocalRuntime by default).
        """
        if self._runtime_factory:
            return self._runtime_factory()

        from kailash.runtime.local import LocalRuntime

        return LocalRuntime()

    # ------------------------------------------------------------------
    # Lifecycle hook registration (issue #914)
    # ------------------------------------------------------------------

    def on_task_prerun(self, handler: TaskEventHandler) -> TaskEventHandler:
        """Register a handler invoked BEFORE each task executes.

        The handler receives a :class:`TaskEvent` with ``elapsed_ms=None``
        and ``exception=None``. Sync and async handlers are both supported;
        async handlers are awaited inline.

        Returns the handler unchanged so it can be used as a decorator.
        """
        self._hooks_prerun.append(handler)
        return handler

    def on_task_postrun(self, handler: TaskEventHandler) -> TaskEventHandler:
        """Register a handler invoked AFTER each task, regardless of outcome.

        The handler receives a :class:`TaskEvent` with ``elapsed_ms`` populated
        and ``exception`` set iff the task raised.
        """
        self._hooks_postrun.append(handler)
        return handler

    def on_task_success(self, handler: TaskEventHandler) -> TaskEventHandler:
        """Register a handler invoked AFTER successful task completion."""
        self._hooks_success.append(handler)
        return handler

    def on_task_retry(self, handler: TaskEventHandler) -> TaskEventHandler:
        """Register a handler invoked when a failed task will be retried.

        Fires when ``task.attempts < task.max_attempts`` after a failure;
        the next ``nack`` re-queues the task. NOT invoked when the failure
        will dead-letter (use ``on_task_failure`` for that).
        """
        self._hooks_retry.append(handler)
        return handler

    def on_task_failure(self, handler: TaskEventHandler) -> TaskEventHandler:
        """Register a handler invoked on FINAL task failure (will dead-letter).

        Fires when ``task.attempts >= task.max_attempts`` after a failure;
        ``nack`` will dead-letter the task. NOT invoked on retryable failures
        (use ``on_task_retry`` for those).
        """
        self._hooks_failure.append(handler)
        return handler

    async def _dispatch_task_event(
        self,
        handlers: List[TaskEventHandler],
        event: TaskEvent,
    ) -> None:
        """Dispatch ``event`` to every handler in ``handlers``.

        Per ``observability.md`` Rule 3a: handler exceptions are caught and
        logged at WARN — handler failure MUST NOT block task lifecycle.
        Async handlers are awaited; sync handlers run inline.
        """
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning(
                    "Worker '%s' lifecycle handler %r raised %s for task %s; continuing",
                    self._worker_id,
                    getattr(handler, "__name__", repr(handler)),
                    type(exc).__name__,
                    event.task_id,
                    exc_info=True,
                )

    @staticmethod
    def _workflow_name_from_task(task: TaskMessage) -> Optional[str]:
        """Extract ``workflow.name`` from the task's serialized workflow blob."""
        wf_data = task.workflow_data or {}
        name = wf_data.get("name")
        return name if isinstance(name, str) and name else None

    @staticmethod
    def _validate_execution_limits_dict(
        d: Optional[Any],
    ) -> Optional[Dict[str, float]]:
        """Validate the shape + content of ``TaskMessage.execution_limits``.

        Per #912 Shard 6 security finding F2: a malicious producer can
        send arbitrary shapes (``{"soft": "DROP TABLE"}`` /
        ``{"hard": -1}`` / ``{"soft": [1, 2, 3]}``) on the wire. Without
        validation at dequeue, the bad value flows to ``arm_time_limits``
        and surfaces as a TypeError / ValueError from a daemon timer
        thread — far from the entry point, with no actionable traceback.

        Validation rules (all enforced):

        * ``None`` → return ``None`` (no per-task override; worker
          defaults will apply).
        * Non-dict → raise ``ValueError`` with the actual type so the
          operator can grep the dead-letter for the offending shape.
        * Unknown keys outside ``{"soft", "hard"}`` → silently ignored
          (forward-compat with future fields). Keys are NOT raised on
          to keep the wire format additive.
        * ``"soft"`` / ``"hard"`` values: MUST be ``int`` or ``float``
          (NOT ``bool`` — Python's ``bool`` is a subclass of ``int``
          but a True/False time limit is nonsense). Non-numeric values
          (``str``, ``list``, ``dict``) raise ``ValueError``.
        * Numeric values: forwarded to ``_validate_limits`` so the
          finite-check + ``> 0`` + ``soft < hard`` invariants apply
          identically to the in-process path.

        Returns:
            The validated dict (with only ``soft`` / ``hard`` keys), or
            ``None`` when the input was ``None``.

        Raises:
            ValueError: If the dict shape, key types, or numeric values
                violate the contract. Message names the offending field
                so dead-letter triage can grep the wire payload.
        """
        if d is None:
            return None
        if not isinstance(d, dict):
            raise ValueError(
                f"TaskMessage.execution_limits MUST be dict or None, "
                f"got {type(d).__name__!r}: {d!r}"
            )
        validated: Dict[str, float] = {}
        for key in ("soft", "hard"):
            if key not in d:
                continue
            value = d[key]
            # bool is a subclass of int; explicitly reject because
            # `True` would round-trip through validation as 1.0 second
            # which is nonsense for a time-limit semantics.
            if isinstance(value, bool):
                raise ValueError(
                    f"TaskMessage.execution_limits[{key!r}] MUST be "
                    f"numeric (int / float), got bool: {value!r}"
                )
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"TaskMessage.execution_limits[{key!r}] MUST be "
                    f"numeric (int / float), got {type(value).__name__!r}: "
                    f"{value!r}"
                )
            validated[key] = float(value)
        # Run through the canonical validator so finite-check +
        # `> 0` + `soft < hard` apply identically to in-process path.
        _validate_limits(
            validated.get("soft"),
            validated.get("hard"),
        )
        return validated

    def _effective_time_limits(
        self, task: TaskMessage
    ) -> Tuple[Optional[float], Optional[float]]:
        """Compute the (soft, hard) effective time limits for a task.

        Per #912 Shard 4 invariant 3: per-task value (from
        ``TaskMessage.execution_limits``) wins over ``Worker(default_*)``;
        falls through to ``None`` (no limit) when neither is set.

        Per #912 Shard 6 security finding F2: validate the per-task
        dict at dequeue so a malicious producer cannot smuggle bad
        shapes into the timer-arm code path.

        Returns:
            ``(effective_soft, effective_hard)`` — either may be ``None``
            when neither the per-task dict nor the Worker default sets it.

        Raises:
            ValueError: If the per-task ``execution_limits`` dict has a
                bad shape or non-finite / non-positive values.
        """
        validated = self._validate_execution_limits_dict(task.execution_limits)
        per_task = validated or {}
        soft = per_task.get("soft", self._default_soft_time_limit)
        hard = per_task.get("hard", self._default_time_limit)
        return soft, hard

    async def start(self):
        """Start the worker loop.

        Registers the worker, starts the heartbeat, recovers stale tasks,
        and begins processing. Blocks until ``stop()`` is called or a
        termination signal is received.

        Multi-queue (#911 Shard 2): spawns one independent asyncio
        dequeue-loop task per declared queue, each with its own
        concurrency semaphore. Per-queue tasks are independent so a
        slow-queue task does NOT block fast-queue dequeue.
        """
        self._running = True

        # Per-queue semaphores: each declared queue enforces its own
        # concurrency cap independently. The aggregate self._semaphore
        # alias points at the default queue's semaphore for back-compat
        # with code that reads self._semaphore directly.
        for spec in self._queue_specs.values():
            spec.semaphore = asyncio.Semaphore(spec.concurrency)
        self._semaphore = self._queue_specs[
            (
                DEFAULT_QUEUE_NAME
                if DEFAULT_QUEUE_NAME in self._queue_specs
                else next(iter(self._queue_specs))
            )
        ].semaphore

        logger.info(
            "Worker '%s' starting with queues=%s (aggregate concurrency=%d)",
            self._worker_id,
            {n: s.concurrency for n, s in self._queue_specs.items()},
            self._concurrency,
        )

        # Register worker
        self._register_worker()

        # Recover stale tasks from previous crashes — once per queue.
        for spec in self._queue_specs.values():
            recovered = spec.queue.recover_stale_tasks()
            if recovered:
                logger.info(
                    "Recovered %d stale tasks on startup (queue=%s)",
                    recovered,
                    spec.name,
                )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start dead worker detection task
        detection_task = asyncio.create_task(self._dead_worker_detection_loop())

        # Start one dequeue loop per declared queue (#911 Shard 2). Each
        # loop runs independently, so a BLMOVE block on the slow queue
        # cannot stall fast-queue pickup (failure-point #3).
        per_queue_loops = [
            asyncio.create_task(self._dequeue_loop(spec))
            for spec in self._queue_specs.values()
        ]

        try:
            # Block until any of the dequeue loops exits (typically via
            # self._running going False on stop()).
            await asyncio.gather(*per_queue_loops, return_exceptions=True)
        finally:
            self._running = False
            for loop_task in per_queue_loops:
                loop_task.cancel()
            heartbeat_task.cancel()
            detection_task.cancel()
            self._deregister_worker()
            # Wait for in-flight tasks
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            logger.info("Worker '%s' stopped", self._worker_id)

    async def stop(self):
        """Signal the worker to stop processing new tasks.

        In-flight tasks are allowed to complete before the worker fully stops.
        """
        logger.info("Worker '%s' stop requested", self._worker_id)
        self._running = False

    async def _dequeue_loop(self, spec: "_QueueSpec"):
        """Per-queue dequeue loop (#911 Shard 2).

        One asyncio task per declared queue. Each loop dequeues from
        its OWN Redis list with its OWN semaphore — so a slow-queue
        task that takes the semaphore does NOT block fast-queue
        pickup (failure-point #3, acceptance criterion 3).
        """
        assert spec.semaphore is not None
        while self._running:
            try:
                # Non-blocking dequeue with short timeout — bounded so
                # self._running becomes False within ~2s of stop().
                task = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: spec.queue.dequeue(timeout=2)
                )
                if task is None:
                    continue

                # Acquire THIS queue's semaphore (per-queue concurrency
                # cap, NOT aggregate). A saturated slow queue does not
                # block fast-queue dequeue because the fast queue has
                # its own loop + semaphore.
                await spec.semaphore.acquire()
                async_task = asyncio.create_task(self._execute_task(task, spec=spec))
                self._tasks.add(async_task)
                async_task.add_done_callback(lambda t, s=spec: self._task_done(t, s))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in dequeue loop (queue=%s): %s", spec.name, exc)
                await asyncio.sleep(1)

    def _task_done(self, task: asyncio.Task, spec: Optional["_QueueSpec"] = None):
        """Callback when a task completes. Releases the per-queue semaphore."""
        if spec is not None and spec.semaphore is not None:
            spec.semaphore.release()
        elif self._semaphore is not None:
            # Legacy-callback path (no spec) — fall back to default.
            self._semaphore.release()
        if task in self._tasks:
            self._tasks.discard(task)

    async def _execute_task(
        self,
        task: TaskMessage,
        *,
        spec: Optional["_QueueSpec"] = None,
    ):
        """Execute a single task and store the result.

        Args:
            task: The task to execute.
            spec: The :class:`_QueueSpec` of the queue this task was
                dequeued from (#911 Shard 2). Used to route ack/store/
                nack back to the originating queue. Falls back to the
                worker's primary queue (legacy single-queue behavior)
                when ``None`` so legacy code paths keep working.
        """
        # Resolve the queue this task belongs to. spec is the canonical
        # signal; in the rare legacy single-queue path we fall back to
        # the primary queue (which IS the only queue in that path).
        active_queue = spec.queue if spec is not None else self._queue
        active_queue_name = spec.name if spec is not None else task.queue_name

        start_time = time.time()
        logger.info(
            "Worker '%s' executing task %s (queue=%s, attempt %d/%d)",
            self._worker_id,
            task.task_id,
            active_queue_name,
            task.attempts,
            task.max_attempts,
        )

        workflow_name = self._workflow_name_from_task(task)

        # Issue #914 + #911 Shard 2: prerun lifecycle hook — handler sees
        # the task BEFORE the runtime executes. queue_name is populated
        # so per-queue alerting (e.g. slow_queue_failure_rate dashboards)
        # can route on it.
        if self._hooks_prerun:
            await self._dispatch_task_event(
                self._hooks_prerun,
                TaskEvent(
                    task_id=task.task_id,
                    workflow_name=workflow_name,
                    attempt=task.attempts,
                    max_attempts=task.max_attempts,
                    worker_id=self._worker_id,
                    queue_name=active_queue_name,
                ),
            )

        execution_time: float = 0.0
        outcome_exc: Optional[BaseException] = None
        try:
            runtime = self._get_runtime()
            # #912 Shard 4: compute effective time limits (per-task wins over
            # Worker defaults; both default to None = no limit). Arm timers
            # AT DEQUEUE (here), NOT at enqueue, so queue wait time does NOT
            # consume the task's budget (Shard 4 invariant 1).
            soft_limit, hard_limit = self._effective_time_limits(task)
            cancellation_token = (
                CancellationToken()
                if (soft_limit is not None or hard_limit is not None)
                else None
            )
            cancellable = arm_time_limits(
                cancellation_token or CancellationToken(),
                soft_time_limit=soft_limit,
                time_limit=hard_limit,
                grace_seconds=self._hard_time_limit_grace_seconds,
            )

            try:
                # Reconstruct and execute the workflow inside the time-limit
                # window. WorkflowCancelledError raised by the runtime when it
                # observes the cancelled token gets classified into the typed
                # SoftTimeLimitExceeded / HardTimeLimitExceeded subclass below.
                try:
                    result_data = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._execute_workflow_sync(
                            runtime, task, cancellation_token=cancellation_token
                        ),
                    )
                except WorkflowCancelledError as cancel_exc:
                    # Convert to the typed deadline exception. The classifier
                    # inspects which deadline was reached on the _Cancellable
                    # handle and returns the matching subclass.
                    classified = _TimeLimitClassifier(cancellable).classify(cancel_exc)
                    raise classified from cancel_exc
            finally:
                # Always disarm the timers AND check the hard-deadline flag.
                # The hard timer may have fired AFTER the workflow returned
                # successfully (race between executor completion and timer
                # callback). Per Shard 2 contract: HardTimeLimitExceeded is
                # raised UNCONDITIONALLY when the flag is set.
                cancellable.disarm()
                if cancellable.hard_deadline_reached:
                    raise HardTimeLimitExceeded(
                        f"workflow exceeded hard time limit "
                        f"(time_limit={cancellable.time_limit}s + "
                        f"grace_seconds={cancellable.grace_seconds}s)"
                    )

            execution_time = time.time() - start_time
            result = TaskResult(
                task_id=task.task_id,
                status="completed",
                result_data=result_data,
                completed_at=time.time(),
                worker_id=self._worker_id,
                execution_time=execution_time,
            )
            active_queue.store_result(result)
            active_queue.ack(task)

            logger.info(
                "Task %s completed in %.2fs by worker '%s' (queue=%s)",
                task.task_id,
                execution_time,
                self._worker_id,
                active_queue_name,
            )

            # Issue #914 + #911 Shard 2: success lifecycle hook — fire
            # AFTER ack so the handler observes committed-success state.
            # queue_name routes per-queue success metrics.
            if self._hooks_success:
                await self._dispatch_task_event(
                    self._hooks_success,
                    TaskEvent(
                        task_id=task.task_id,
                        workflow_name=workflow_name,
                        attempt=task.attempts,
                        max_attempts=task.max_attempts,
                        worker_id=self._worker_id,
                        elapsed_ms=execution_time * 1000.0,
                        queue_name=active_queue_name,
                    ),
                )

        except Exception as exc:
            execution_time = time.time() - start_time
            outcome_exc = exc
            logger.error(
                "Task %s failed after %.2fs (queue=%s): %s",
                task.task_id,
                execution_time,
                active_queue_name,
                exc,
            )

            # Store failure result
            result = TaskResult(
                task_id=task.task_id,
                status="failed",
                error=str(exc),
                completed_at=time.time(),
                worker_id=self._worker_id,
                execution_time=execution_time,
            )
            active_queue.store_result(result)

            # Issue #914: classify retry vs final failure BEFORE nack so the
            # handler sees the disposition that nack will apply. TaskQueue.nack
            # re-queues when ``task.attempts < task.max_attempts`` and
            # dead-letters otherwise (see TaskQueue.nack:300).
            failure_event = TaskEvent(
                task_id=task.task_id,
                workflow_name=workflow_name,
                attempt=task.attempts,
                max_attempts=task.max_attempts,
                worker_id=self._worker_id,
                elapsed_ms=execution_time * 1000.0,
                exception=exc,
                queue_name=active_queue_name,
            )
            if task.attempts < task.max_attempts:
                if self._hooks_retry:
                    await self._dispatch_task_event(self._hooks_retry, failure_event)
            else:
                if self._hooks_failure:
                    await self._dispatch_task_event(self._hooks_failure, failure_event)

            active_queue.nack(task)

        finally:
            # Issue #914 + #911 Shard 2: postrun lifecycle hook — fires
            # for both success and failure paths. Equivalent to Celery's
            # `task_postrun` signal.
            if self._hooks_postrun:
                await self._dispatch_task_event(
                    self._hooks_postrun,
                    TaskEvent(
                        task_id=task.task_id,
                        workflow_name=workflow_name,
                        attempt=task.attempts,
                        max_attempts=task.max_attempts,
                        worker_id=self._worker_id,
                        elapsed_ms=execution_time * 1000.0,
                        exception=outcome_exc,
                        queue_name=active_queue_name,
                    ),
                )

    def _execute_workflow_sync(
        self,
        runtime,
        task: TaskMessage,
        *,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Synchronously execute a workflow from task data.

        Deserializes the workflow from the task's JSON payload using
        Workflow.from_dict(), then executes it with the provided runtime.

        Args:
            runtime: The local runtime to use for execution.
            task: The task containing workflow data and parameters.
            cancellation_token: Optional token forwarded to the runtime so the
                Shard 4 timer-arming pipeline can cancel a long-running
                workflow at the soft / hard deadline. ``None`` when the task
                has no effective time limits (the no-limits path stays
                allocation-free).

        Returns:
            The workflow execution results.
        """
        from kailash.workflow.graph import Workflow

        workflow = Workflow.from_dict(task.workflow_data)
        _build = getattr(workflow, "build", None)
        built = _build() if _build is not None else workflow
        # Forward cancellation_token to the runtime ONLY when one is set —
        # runtimes accept the kwarg but the no-limit path stays opt-in.
        kwargs: Dict[str, Any] = {"parameters": task.parameters}
        if cancellation_token is not None:
            kwargs["cancellation_token"] = cancellation_token
        results, run_id = runtime.execute(built, **kwargs)

        # Issue #941: LocalRuntime._should_stop_on_error returns False when a
        # failed node has no downstream dependents, so the node-level failure
        # is recorded in results (`failed: True, error_type, error, _exception`)
        # and the runtime returns NORMALLY. The worker's retry/final
        # classification at _execute_task only fires on raised exceptions; a
        # silently-recorded failure looks like success and the lifecycle-hooks
        # contract breaks (retry/failure events never fire). Re-raise the
        # user-meaningful root exception so the classifier sees the disposition
        # the user sees in the runtime logs.
        for node_id, payload in results.items():
            if not (isinstance(payload, dict) and payload.get("failed") is True):
                continue
            raise _unwrap_node_failure(payload, node_id)

        return results

    # -- Heartbeat --

    def _register_worker(self):
        """Register this worker in the Redis worker set."""
        try:
            client = self._get_redis_client()
            client.sadd(_WORKER_SET_KEY, self._worker_id)
            self._send_heartbeat()
            logger.debug("Registered worker '%s'", self._worker_id)
        except Exception as exc:
            logger.warning("Failed to register worker: %s", exc)

    def _deregister_worker(self):
        """Remove this worker from the Redis worker set."""
        try:
            client = self._get_redis_client()
            client.srem(_WORKER_SET_KEY, self._worker_id)
            client.delete(f"{_HEARTBEAT_PREFIX}{self._worker_id}")
            logger.debug("Deregistered worker '%s'", self._worker_id)
        except Exception as exc:
            logger.warning("Failed to deregister worker: %s", exc)

    def _send_heartbeat(self):
        """Send a heartbeat to Redis with worker metadata."""
        try:
            client = self._get_redis_client()
            heartbeat_data = json.dumps(
                {
                    "worker_id": self._worker_id,
                    "timestamp": time.time(),
                    "active_tasks": len(self._tasks),
                    "concurrency": self._concurrency,
                    # #911 Shard 2: per-queue concurrency map. Operators
                    # observing the heartbeat see exactly which queues
                    # this worker is consuming from + their per-queue
                    # caps (failure-point #7).
                    "queues": {
                        spec.name: spec.concurrency
                        for spec in self._queue_specs.values()
                    },
                }
            )
            client.set(
                f"{_HEARTBEAT_PREFIX}{self._worker_id}",
                heartbeat_data,
                ex=self._dead_worker_timeout,
            )
        except Exception as exc:
            logger.warning("Failed to send heartbeat: %s", exc)

    async def _heartbeat_loop(self):
        """Periodically send heartbeats while the worker is running."""
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat loop error: %s", exc)

    async def _dead_worker_detection_loop(self):
        """Periodically check for dead workers and recover their tasks.

        A worker is considered dead if its heartbeat has expired (controlled
        by ``dead_worker_timeout``). Dead workers are removed from the worker
        set.
        """
        while self._running:
            try:
                await asyncio.sleep(self._dead_worker_timeout)
                self._detect_dead_workers()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Dead worker detection error: %s", exc)

    def _detect_dead_workers(self):
        """Check for dead workers and clean up."""
        try:
            client = self._get_redis_client()
            workers = cast(set, client.smembers(_WORKER_SET_KEY))

            for worker_id in workers:
                if worker_id == self._worker_id:
                    continue

                heartbeat = client.get(f"{_HEARTBEAT_PREFIX}{worker_id}")
                if heartbeat is None:
                    # Heartbeat expired -- worker is dead
                    logger.warning(
                        "Detected dead worker '%s', removing from worker set",
                        worker_id,
                    )
                    client.srem(_WORKER_SET_KEY, worker_id)
                    # #911 Shard 2: stale task recovery sweeps every
                    # queue this worker consumes from, not just the
                    # primary. A dead worker may have orphaned tasks
                    # on multiple queues.
                    for spec in self._queue_specs.values():
                        spec.queue.recover_stale_tasks()

        except Exception as exc:
            logger.warning("Dead worker detection failed: %s", exc)

    def get_status(self) -> Dict[str, Any]:
        """Get current worker status.

        Returns:
            Dictionary with worker metadata and task counts. The
            ``queues`` field (#911 Shard 2) reports per-queue pending
            and processing counts for every queue this worker consumes
            from. Legacy fields ``queue_pending`` / ``queue_processing``
            report the PRIMARY queue's counts so existing dashboards
            keep working.
        """
        primary = self._queue
        per_queue: Dict[str, Dict[str, int]] = {}
        for spec in self._queue_specs.values():
            try:
                if spec.queue.ping():
                    per_queue[spec.name] = {
                        "pending": spec.queue.queue_length(),
                        "processing": spec.queue.processing_length(),
                        "concurrency": spec.concurrency,
                    }
                else:
                    per_queue[spec.name] = {
                        "pending": -1,
                        "processing": -1,
                        "concurrency": spec.concurrency,
                    }
            except Exception:
                per_queue[spec.name] = {
                    "pending": -1,
                    "processing": -1,
                    "concurrency": spec.concurrency,
                }
        return {
            "worker_id": self._worker_id,
            "running": self._running,
            "active_tasks": len(self._tasks),
            "concurrency": self._concurrency,
            "queue_pending": primary.queue_length() if primary.ping() else -1,
            "queue_processing": (primary.processing_length() if primary.ping() else -1),
            "queues": per_queue,
        }
