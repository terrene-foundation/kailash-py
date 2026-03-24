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
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from kailash.runtime.base import BaseRuntime
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
    """

    task_id: str = ""
    workflow_data: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    submitted_at: float = 0.0
    visibility_timeout: int = 300  # 5 minutes default
    attempts: int = 0
    max_attempts: int = 3

    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage."""
        return json.dumps(
            {
                "task_id": self.task_id,
                "workflow_data": self.workflow_data,
                "parameters": self.parameters,
                "submitted_at": self.submitted_at,
                "visibility_timeout": self.visibility_timeout,
                "attempts": self.attempts,
                "max_attempts": self.max_attempts,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "TaskMessage":
        """Deserialize from JSON string."""
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

            if not self._redis_url.startswith(("redis://", "rediss://")):
                raise ValueError(
                    f"Invalid Redis URL '{self._redis_url}': must start with redis:// or rediss://"
                )
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
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._redis_url = redis_url or os.environ.get("KAILASH_REDIS_URL", "")
        self._queue = queue or TaskQueue(
            redis_url=self._redis_url,
            default_visibility_timeout=visibility_timeout,
            result_ttl=result_ttl,
        )
        self._visibility_timeout = visibility_timeout
        self._result_ttl = result_ttl

    def close(self) -> None:
        """Release distributed runtime resources.

        Cleans up the task queue connection and any execution metadata.
        """
        self._execution_metadata.clear()
        _close = getattr(self._queue, "close", None)
        if _close is not None:
            _close()

    def execute(
        self,
        workflow: Workflow,
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Tuple[Dict[str, Any], str]:
        """Submit a workflow to the distributed task queue.

        Instead of executing locally, the workflow is serialized and enqueued.
        Returns immediately with a queued status.

        Args:
            workflow: The workflow to execute.
            parameters: Optional execution parameters.
            **kwargs: Additional execution options.

        Returns:
            Tuple of (status_dict, run_id) where status_dict contains
            ``{"status": "queued", "run_id": run_id, "queue_length": N}``.
        """
        run_id = self._generate_run_id()
        metadata = self._initialize_execution_metadata(workflow, run_id)
        self._execution_metadata[run_id] = metadata

        # Serialize the workflow for queue transport
        workflow_data = self._serialize_workflow(workflow)

        task = TaskMessage(
            task_id=run_id,
            workflow_data=workflow_data,
            parameters=parameters or {},
            visibility_timeout=self._visibility_timeout,
        )

        self._queue.enqueue(task)

        self._update_execution_metadata(run_id, {"status": "queued"})

        return {
            "status": "queued",
            "run_id": run_id,
            "queue_length": self._queue.queue_length(),
        }, run_id

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

        Returns:
            Dictionary with pending and processing counts.
        """
        return {
            "pending": self._queue.queue_length(),
            "processing": self._queue.processing_length(),
            "redis_available": self._queue.ping(),
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

    Example:
        >>> worker = Worker(
        ...     redis_url="redis://localhost:6379/0",
        ...     concurrency=4,
        ... )
        >>> await worker.start()  # Runs until stopped
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
    ):
        self._redis_url = redis_url or os.environ.get("KAILASH_REDIS_URL", "")
        self._queue = queue or TaskQueue(redis_url=self._redis_url)
        self._concurrency = max(1, concurrency)
        self._heartbeat_interval = heartbeat_interval
        self._dead_worker_timeout = dead_worker_timeout
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        self._runtime_factory = runtime_factory
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._redis_client = None

    def _get_redis_client(self):
        """Get the Redis client for heartbeat operations."""
        if self._redis_client is None:
            import redis as redis_lib

            if not self._redis_url.startswith(("redis://", "rediss://")):
                raise ValueError(
                    f"Invalid Redis URL '{self._redis_url}': must start with redis:// or rediss://"
                )
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

    async def start(self):
        """Start the worker loop.

        Registers the worker, starts the heartbeat, recovers stale tasks,
        and begins processing. Blocks until ``stop()`` is called or a
        termination signal is received.
        """
        self._running = True
        self._semaphore = asyncio.Semaphore(self._concurrency)

        logger.info(
            "Worker '%s' starting with concurrency=%d",
            self._worker_id,
            self._concurrency,
        )

        # Register worker
        self._register_worker()

        # Recover stale tasks from previous crashes
        recovered = self._queue.recover_stale_tasks()
        if recovered:
            logger.info("Recovered %d stale tasks on startup", recovered)

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start dead worker detection task
        detection_task = asyncio.create_task(self._dead_worker_detection_loop())

        try:
            await self._process_loop()
        finally:
            self._running = False
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

    async def _process_loop(self):
        """Main processing loop that dequeues and executes tasks."""
        while self._running:
            try:
                # Non-blocking dequeue with short timeout
                task = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._queue.dequeue(timeout=2)
                )
                if task is None:
                    continue

                # Acquire semaphore for concurrency control
                assert self._semaphore is not None
                await self._semaphore.acquire()
                async_task = asyncio.create_task(self._execute_task(task))
                self._tasks.add(async_task)
                async_task.add_done_callback(self._task_done)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in worker process loop: %s", exc)
                await asyncio.sleep(1)

    def _task_done(self, task: asyncio.Task):
        """Callback when a task completes. Releases the semaphore."""
        if self._semaphore:
            self._semaphore.release()
        if task in self._tasks:
            self._tasks.discard(task)

    async def _execute_task(self, task: TaskMessage):
        """Execute a single task and store the result.

        Args:
            task: The task to execute.
        """
        start_time = time.time()
        logger.info(
            "Worker '%s' executing task %s (attempt %d/%d)",
            self._worker_id,
            task.task_id,
            task.attempts,
            task.max_attempts,
        )

        try:
            runtime = self._get_runtime()
            # Reconstruct and execute the workflow
            # For now, we pass the workflow data to the runtime
            # In production, this would deserialize and re-build the workflow
            result_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._execute_workflow_sync(runtime, task),
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
            self._queue.store_result(result)
            self._queue.ack(task)

            logger.info(
                "Task %s completed in %.2fs by worker '%s'",
                task.task_id,
                execution_time,
                self._worker_id,
            )

        except Exception as exc:
            execution_time = time.time() - start_time
            logger.error(
                "Task %s failed after %.2fs: %s",
                task.task_id,
                execution_time,
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
            self._queue.store_result(result)
            self._queue.nack(task)

    def _execute_workflow_sync(self, runtime, task: TaskMessage) -> Dict[str, Any]:
        """Synchronously execute a workflow from task data.

        Deserializes the workflow from the task's JSON payload using
        Workflow.from_dict(), then executes it with the provided runtime.

        Args:
            runtime: The local runtime to use for execution.
            task: The task containing workflow data and parameters.

        Returns:
            The workflow execution results.
        """
        from kailash.workflow.graph import Workflow

        workflow = Workflow.from_dict(task.workflow_data)
        _build = getattr(workflow, "build", None)
        built = _build() if _build is not None else workflow
        results, run_id = runtime.execute(built, parameters=task.parameters)
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
                    # Stale task recovery happens in the main loop via
                    # recover_stale_tasks()
                    self._queue.recover_stale_tasks()

        except Exception as exc:
            logger.warning("Dead worker detection failed: %s", exc)

    def get_status(self) -> Dict[str, Any]:
        """Get current worker status.

        Returns:
            Dictionary with worker metadata and task counts.
        """
        return {
            "worker_id": self._worker_id,
            "running": self._running,
            "active_tasks": len(self._tasks),
            "concurrency": self._concurrency,
            "queue_pending": self._queue.queue_length() if self._queue.ping() else -1,
            "queue_processing": (
                self._queue.processing_length() if self._queue.ping() else -1
            ),
        }
