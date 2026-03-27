"""Unit tests for the distributed runtime with Redis-backed task queue.

Tier 1 tests - Fast isolated testing with mocked Redis, no external dependencies.
All tests must complete in <1 second with no sleep/delays.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Distributed runtime tests exhaust CI runner threads
pytestmark = pytest.mark.slow

from src.kailash.runtime.distributed import (
    DistributedRuntime,
    TaskMessage,
    TaskQueue,
    TaskResult,
    Worker,
    _HEARTBEAT_PREFIX,
    _PROCESSING_KEY,
    _QUEUE_KEY,
    _RESULTS_PREFIX,
    _TASK_PREFIX,
    _WORKER_SET_KEY,
)


# ============================================================
# Helpers
# ============================================================


def _mock_redis_client():
    """Create a mock Redis client with common queue operations."""
    client = MagicMock()
    client.ping.return_value = True
    client.lpush.return_value = 1
    client.blmove.return_value = None
    client.llen.return_value = 0
    client.lrange.return_value = []
    client.lrem.return_value = 1
    client.set.return_value = True
    client.get.return_value = None
    client.delete.return_value = True
    client.sadd.return_value = 1
    client.srem.return_value = 1
    client.smembers.return_value = set()
    return client


def _make_task(**overrides) -> TaskMessage:
    """Create a TaskMessage with sensible defaults."""
    defaults = {
        "task_id": "task-001",
        "workflow_data": {"nodes": {"n1": {"type": "Echo"}}},
        "parameters": {"key": "value"},
        "submitted_at": time.time(),
        "visibility_timeout": 300,
        "attempts": 0,
        "max_attempts": 3,
    }
    defaults.update(overrides)
    return TaskMessage(**defaults)


# ============================================================
# TaskMessage Tests
# ============================================================


class TestTaskMessage:
    """Tests for TaskMessage serialization and deserialization."""

    def test_to_json_roundtrip(self):
        """TaskMessage survives JSON serialization and deserialization."""
        task = _make_task(task_id="abc-123")
        serialized = task.to_json()
        restored = TaskMessage.from_json(serialized)
        assert restored.task_id == "abc-123"
        assert restored.parameters == {"key": "value"}
        assert restored.max_attempts == 3

    def test_from_json_with_unknown_fields_ignored(self):
        """from_json tolerates unknown fields without raising."""
        data = json.dumps(
            {
                "task_id": "t1",
                "workflow_data": {},
                "parameters": {},
                "submitted_at": 0.0,
                "visibility_timeout": 300,
                "attempts": 0,
                "max_attempts": 3,
            }
        )
        task = TaskMessage.from_json(data)
        assert task.task_id == "t1"


class TestTaskResult:
    """Tests for TaskResult serialization."""

    def test_to_json_roundtrip(self):
        """TaskResult survives JSON serialization and deserialization."""
        result = TaskResult(
            task_id="t-1",
            status="completed",
            result_data={"output": 42},
            worker_id="w-1",
            execution_time=1.5,
        )
        serialized = result.to_json()
        restored = TaskResult.from_json(serialized)
        assert restored.task_id == "t-1"
        assert restored.status == "completed"
        assert restored.result_data == {"output": 42}


# ============================================================
# TaskQueue Tests
# ============================================================


class TestTaskQueue:
    """Tests for the Redis-backed task queue."""

    def _make_queue(self, mock_client=None):
        """Create a TaskQueue with a mocked Redis client."""
        queue = TaskQueue(redis_url="redis://test:6379")
        queue._client = mock_client or _mock_redis_client()
        return queue

    def test_enqueue_pushes_to_redis(self):
        """enqueue pushes a task to the pending queue."""
        client = _mock_redis_client()
        queue = self._make_queue(client)
        task = _make_task()

        task_id = queue.enqueue(task)
        assert task_id == "task-001"
        client.lpush.assert_called_once()
        assert client.lpush.call_args[0][0] == _QUEUE_KEY

    def test_enqueue_generates_task_id_when_missing(self):
        """enqueue auto-generates a task_id if empty."""
        client = _mock_redis_client()
        queue = self._make_queue(client)
        task = _make_task(task_id="")

        task_id = queue.enqueue(task)
        assert task_id != ""
        assert len(task_id) > 10  # UUID length check

    def test_dequeue_returns_task_from_redis(self):
        """dequeue returns a TaskMessage from the pending queue."""
        client = _mock_redis_client()
        task = _make_task()
        client.blmove.return_value = task.to_json()
        queue = self._make_queue(client)

        result = queue.dequeue(timeout=1)
        assert result is not None
        assert result.task_id == "task-001"
        assert result.attempts == 1  # Incremented on dequeue

    def test_dequeue_returns_none_when_empty(self):
        """dequeue returns None when no tasks are available."""
        client = _mock_redis_client()
        client.blmove.return_value = None
        queue = self._make_queue(client)

        result = queue.dequeue(timeout=0)
        assert result is None

    def test_dequeue_handles_malformed_json(self):
        """dequeue removes malformed entries and returns None."""
        client = _mock_redis_client()
        client.blmove.return_value = "not-valid-json{{"
        queue = self._make_queue(client)

        result = queue.dequeue(timeout=0)
        assert result is None
        client.lrem.assert_called_once()

    def test_ack_removes_from_processing(self):
        """ack removes the task from the processing list."""
        client = _mock_redis_client()
        task = _make_task()
        # Simulate the task being in the processing list
        client.lrange.return_value = [task.to_json()]
        queue = self._make_queue(client)

        result = queue.ack(task)
        assert result is True
        client.lrem.assert_called_once()

    def test_nack_requeues_task_under_max_attempts(self):
        """nack re-queues the task when under max_attempts."""
        client = _mock_redis_client()
        client.lrange.return_value = []
        queue = self._make_queue(client)
        task = _make_task(attempts=1, max_attempts=3)

        result = queue.nack(task)
        assert result is True
        # Should re-queue via lpush
        client.lpush.assert_called_once()

    def test_nack_dead_letters_at_max_attempts(self):
        """nack dead-letters the task when max_attempts is reached."""
        client = _mock_redis_client()
        client.lrange.return_value = []
        queue = self._make_queue(client)
        task = _make_task(attempts=3, max_attempts=3)

        result = queue.nack(task)
        assert result is True
        # Should store a dead_lettered result, not re-queue
        client.lpush.assert_not_called()
        # Result should be stored
        stored_call = client.set.call_args_list[-1]
        stored_key = stored_call[0][0]
        assert stored_key.startswith(_RESULTS_PREFIX)

    def test_store_result_writes_with_ttl(self):
        """store_result saves the result in Redis with TTL."""
        client = _mock_redis_client()
        queue = self._make_queue(client)
        result = TaskResult(task_id="t-1", status="completed")

        queue.store_result(result)
        client.set.assert_called_once()
        key, value = client.set.call_args[0][:2]
        assert key == f"{_RESULTS_PREFIX}t-1"

    def test_get_result_parses_stored_result(self):
        """get_result retrieves and parses a stored TaskResult."""
        client = _mock_redis_client()
        result = TaskResult(task_id="t-1", status="completed", result_data={"x": 1})
        client.get.return_value = result.to_json()
        queue = self._make_queue(client)

        retrieved = queue.get_result("t-1")
        assert retrieved is not None
        assert retrieved.status == "completed"
        assert retrieved.result_data == {"x": 1}

    def test_get_result_returns_none_when_missing(self):
        """get_result returns None for non-existent task IDs."""
        client = _mock_redis_client()
        client.get.return_value = None
        queue = self._make_queue(client)

        assert queue.get_result("nonexistent") is None

    def test_queue_length_returns_pending_count(self):
        """queue_length returns the number of pending tasks."""
        client = _mock_redis_client()
        client.llen.return_value = 5
        queue = self._make_queue(client)

        assert queue.queue_length() == 5
        client.llen.assert_called_with(_QUEUE_KEY)

    def test_processing_length_returns_processing_count(self):
        """processing_length returns the number of in-flight tasks."""
        client = _mock_redis_client()
        client.llen.return_value = 3
        queue = self._make_queue(client)

        # Call queue_length first to set up the call count
        queue.queue_length()
        length = queue.processing_length()
        assert length == 3

    def test_recover_stale_tasks_requeues_old_tasks(self):
        """recover_stale_tasks re-queues tasks past the stale threshold."""
        client = _mock_redis_client()
        # A task submitted 1000 seconds ago (well past 600s threshold)
        old_task = _make_task(submitted_at=time.time() - 1000, attempts=1)
        client.lrange.return_value = [old_task.to_json()]
        queue = self._make_queue(client)

        recovered = queue.recover_stale_tasks(stale_threshold=600)
        assert recovered == 1

    def test_ping_returns_true_when_connected(self):
        """ping returns True when Redis responds."""
        client = _mock_redis_client()
        queue = self._make_queue(client)
        assert queue.ping() is True

    def test_ping_returns_false_when_disconnected(self):
        """ping returns False when Redis is unreachable."""
        client = _mock_redis_client()
        client.ping.side_effect = ConnectionError("refused")
        queue = self._make_queue(client)
        assert queue.ping() is False


# ============================================================
# DistributedRuntime Tests
# ============================================================


class TestDistributedRuntime:
    """Tests for the runtime that submits workflows to a task queue."""

    def _make_runtime(self, queue=None):
        """Create a DistributedRuntime with a mocked queue."""
        if queue is None:
            queue = MagicMock(spec=TaskQueue)
            queue.queue_length.return_value = 1
            queue.processing_length.return_value = 0
            queue.ping.return_value = True
        return DistributedRuntime(
            redis_url="redis://test:6379",
            queue=queue,
        )

    def test_execute_returns_queued_status(self):
        """execute returns immediately with queued status."""
        runtime = self._make_runtime()
        mock_workflow = MagicMock()
        mock_workflow.graph.nodes = {"n1": {}}
        mock_workflow.graph.edges.return_value = []

        results, run_id = runtime.execute(mock_workflow)
        assert results["status"] == "queued"
        assert results["run_id"] == run_id
        assert "queue_length" in results

    def test_execute_enqueues_to_task_queue(self):
        """execute submits a TaskMessage to the queue."""
        mock_queue = MagicMock(spec=TaskQueue)
        mock_queue.queue_length.return_value = 2
        runtime = self._make_runtime(queue=mock_queue)
        mock_workflow = MagicMock()
        mock_workflow.graph.nodes = {}
        mock_workflow.graph.edges.return_value = []

        runtime.execute(mock_workflow, parameters={"x": 1})
        mock_queue.enqueue.assert_called_once()
        enqueued_task = mock_queue.enqueue.call_args[0][0]
        assert isinstance(enqueued_task, TaskMessage)
        assert enqueued_task.parameters == {"x": 1}

    def test_get_result_delegates_to_queue(self):
        """get_result delegates to the queue's get_result."""
        mock_queue = MagicMock(spec=TaskQueue)
        expected = TaskResult(task_id="t-1", status="completed")
        mock_queue.get_result.return_value = expected
        runtime = self._make_runtime(queue=mock_queue)

        result = runtime.get_result("t-1")
        assert result.status == "completed"
        mock_queue.get_result.assert_called_once_with("t-1")

    def test_get_queue_status_returns_metrics(self):
        """get_queue_status returns pending and processing counts."""
        mock_queue = MagicMock(spec=TaskQueue)
        mock_queue.queue_length.return_value = 5
        mock_queue.processing_length.return_value = 2
        mock_queue.ping.return_value = True
        runtime = self._make_runtime(queue=mock_queue)

        status = runtime.get_queue_status()
        assert status["pending"] == 5
        assert status["processing"] == 2
        assert status["redis_available"] is True


# ============================================================
# Worker Tests
# ============================================================


class TestWorker:
    """Tests for the task queue worker."""

    def _make_worker(self, queue=None, redis_client=None):
        """Create a Worker with mocked dependencies."""
        mock_queue = queue or MagicMock(spec=TaskQueue)
        mock_queue.ping.return_value = True
        mock_queue.recover_stale_tasks.return_value = 0
        mock_queue.queue_length.return_value = 0
        mock_queue.processing_length.return_value = 0

        worker = Worker(
            redis_url="redis://test:6379",
            queue=mock_queue,
            concurrency=2,
            worker_id="test-worker-1",
        )
        worker._redis_client = redis_client or _mock_redis_client()
        return worker, mock_queue

    def test_worker_initializes_with_defaults(self):
        """Worker initializes with sensible default values."""
        worker = Worker(redis_url="redis://test:6379")
        assert worker._concurrency >= 1
        assert worker._heartbeat_interval == 30
        assert worker._dead_worker_timeout == 90
        assert worker._running is False

    def test_worker_id_auto_generated(self):
        """Worker auto-generates a unique ID when not provided."""
        worker = Worker(redis_url="redis://test:6379")
        assert worker._worker_id.startswith("worker-")
        assert len(worker._worker_id) > 10

    def test_worker_custom_id(self):
        """Worker uses provided worker_id."""
        worker = Worker(redis_url="redis://test:6379", worker_id="my-worker")
        assert worker._worker_id == "my-worker"

    def test_register_worker_adds_to_set(self):
        """_register_worker adds worker ID to Redis worker set."""
        worker, _ = self._make_worker()
        worker._register_worker()
        worker._redis_client.sadd.assert_called_with(_WORKER_SET_KEY, "test-worker-1")

    def test_deregister_worker_removes_from_set(self):
        """_deregister_worker removes worker ID from Redis set."""
        worker, _ = self._make_worker()
        worker._deregister_worker()
        worker._redis_client.srem.assert_called_with(_WORKER_SET_KEY, "test-worker-1")
        worker._redis_client.delete.assert_called_with(
            f"{_HEARTBEAT_PREFIX}test-worker-1"
        )

    def test_send_heartbeat_writes_to_redis(self):
        """_send_heartbeat writes heartbeat data with TTL."""
        worker, _ = self._make_worker()
        worker._send_heartbeat()
        worker._redis_client.set.assert_called_once()
        key = worker._redis_client.set.call_args[0][0]
        assert key == f"{_HEARTBEAT_PREFIX}test-worker-1"

    def test_detect_dead_workers_removes_expired(self):
        """_detect_dead_workers removes workers with expired heartbeats."""
        worker, queue = self._make_worker()
        # Simulate another worker that has no heartbeat (expired)
        worker._redis_client.smembers.return_value = {"dead-worker-99"}
        worker._redis_client.get.return_value = None  # Heartbeat expired

        worker._detect_dead_workers()
        worker._redis_client.srem.assert_called_with(_WORKER_SET_KEY, "dead-worker-99")
        queue.recover_stale_tasks.assert_called_once()

    def test_get_status_returns_worker_metadata(self):
        """get_status returns current worker state."""
        worker, _ = self._make_worker()
        status = worker.get_status()
        assert status["worker_id"] == "test-worker-1"
        assert status["running"] is False
        assert status["concurrency"] == 2
        assert status["active_tasks"] == 0

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        """stop() sets the running flag to False."""
        worker, _ = self._make_worker()
        worker._running = True
        await worker.stop()
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_execute_task_stores_result_on_success(self):
        """_execute_task stores a failed result when workflow deserialization fails."""
        worker, queue = self._make_worker()
        task = _make_task()

        await worker._execute_task(task)
        queue.store_result.assert_called_once()
        stored_result = queue.store_result.call_args[0][0]
        # _execute_workflow_sync fails because "Echo" node is not in the registry
        assert stored_result.status == "failed"
        assert stored_result.worker_id == "test-worker-1"
        assert stored_result.error != ""
        queue.nack.assert_called_once_with(task)

    @pytest.mark.asyncio
    async def test_execute_task_nacks_on_failure(self):
        """_execute_task stores a failed result and nacks the task on error."""
        worker, queue = self._make_worker()
        # Make the sync execution raise
        worker._execute_workflow_sync = MagicMock(side_effect=RuntimeError("boom"))
        task = _make_task()

        await worker._execute_task(task)
        queue.store_result.assert_called_once()
        stored_result = queue.store_result.call_args[0][0]
        assert stored_result.status == "failed"
        assert "boom" in stored_result.error
        queue.nack.assert_called_once_with(task)

    def test_concurrency_minimum_is_one(self):
        """Worker enforces a minimum concurrency of 1."""
        worker = Worker(redis_url="redis://test:6379", concurrency=0)
        assert worker._concurrency == 1

        worker_neg = Worker(redis_url="redis://test:6379", concurrency=-5)
        assert worker_neg._concurrency == 1
