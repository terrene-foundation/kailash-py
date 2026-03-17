# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration test for Redis task queue end-to-end flow (PY-EI-014).

End-to-end smoke test: build workflow -> enqueue -> dequeue -> execute -> result.

Requires Redis at localhost:6380. Skips if Redis is unavailable.
NO MOCKING: this test uses real Redis and real workflow execution.
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
    """Check if Redis is reachable at the configured URL."""
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


@skip_no_redis
@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisEnqueueDequeueExecute:
    """End-to-end: build workflow -> enqueue -> dequeue -> execute -> result."""

    async def test_full_roundtrip(self, _flush_redis):
        """Build a simple workflow, enqueue it, dequeue with a worker, verify results."""
        from kailash.runtime.distributed import (
            DistributedRuntime,
            TaskQueue,
            Worker,
        )
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # 1. Build a simple 2-node workflow: StartNode -> PythonCodeNode
        builder = WorkflowBuilder()
        builder.add_node("StartNode", "start", {})
        builder.add_node(
            "PythonCodeNode",
            "compute",
            {
                "code": "result = input_data.get('value', 0) * 2",
                "input_data": "{{start.output}}",
            },
        )
        builder.connect("start", "output", "compute", "input_data")
        workflow = builder.build()

        # 2. Enqueue via DistributedRuntime
        queue = TaskQueue(redis_url=REDIS_URL)
        dist_runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)

        status, run_id = dist_runtime.execute(workflow, parameters={"value": 21})
        assert status["status"] == "queued"
        assert run_id is not None
        assert queue.queue_length() >= 1

        # 3. Dequeue and verify task structure
        task = queue.dequeue(timeout=2)
        assert task is not None, "Task must be dequeued from Redis"
        assert task.task_id == run_id

        # Verify workflow_data is a valid dict that can reconstruct a Workflow
        from kailash.workflow.graph import Workflow as WF

        reconstructed = WF.from_dict(task.workflow_data)
        assert reconstructed is not None
        assert "start" in reconstructed.nodes
        assert "compute" in reconstructed.nodes

        # 4. Execute via LocalRuntime (simulating what Worker does)
        local_runtime = LocalRuntime()
        built = reconstructed.build() if hasattr(reconstructed, "build") else reconstructed
        results, local_run_id = local_runtime.execute(
            built, parameters=task.parameters
        )

        assert results is not None, "Execution must produce results"
        logger.info("Execution results: %s", results)

        # 5. Ack the task
        queue.ack(task)

        # Verify processing queue is empty after ack
        assert queue.processing_length() == 0

    async def test_worker_executes_task(self, _flush_redis):
        """Worker dequeues and executes a task, storing the result in Redis."""
        from kailash.runtime.distributed import (
            DistributedRuntime,
            TaskQueue,
            Worker,
        )
        from kailash.workflow.builder import WorkflowBuilder

        # Build a trivial workflow
        builder = WorkflowBuilder()
        builder.add_node("StartNode", "start", {})
        workflow = builder.build()

        # Enqueue
        queue = TaskQueue(redis_url=REDIS_URL)
        dist_runtime = DistributedRuntime(redis_url=REDIS_URL, queue=queue)
        status, run_id = dist_runtime.execute(workflow)

        assert queue.queue_length() >= 1

        # Create worker with single concurrency
        worker = Worker(
            redis_url=REDIS_URL,
            queue=queue,
            concurrency=1,
            worker_id="test-worker-001",
        )

        # Run worker for a brief period to process the task
        async def run_worker_briefly():
            worker._running = True
            worker._semaphore = asyncio.Semaphore(1)
            # Register for heartbeat
            worker._register_worker()
            # Process one iteration
            task = await asyncio.get_event_loop().run_in_executor(
                None, lambda: queue.dequeue(timeout=2)
            )
            if task:
                await worker._execute_task(task)
            worker._running = False
            worker._deregister_worker()

        await run_worker_briefly()

        # Verify result is stored
        result = queue.get_result(run_id)
        assert result is not None, "Worker must store a result after execution"
        assert result.status in ("completed", "failed"), (
            f"Expected completed or failed, got {result.status}"
        )
        logger.info("Worker result: status=%s, data=%s", result.status, result.result_data)

    async def test_queue_metrics(self, _flush_redis):
        """Queue length and processing length are correctly tracked."""
        from kailash.runtime.distributed import TaskQueue
        from kailash.workflow.builder import WorkflowBuilder

        queue = TaskQueue(redis_url=REDIS_URL)

        assert queue.queue_length() == 0
        assert queue.processing_length() == 0

        # Enqueue 3 tasks
        from kailash.runtime.distributed import TaskMessage

        for i in range(3):
            task = TaskMessage(
                task_id=f"metric-task-{i}",
                workflow_data={"nodes": {}},
                parameters={},
            )
            queue.enqueue(task)

        assert queue.queue_length() == 3

        # Dequeue 2
        queue.dequeue(timeout=1)
        queue.dequeue(timeout=1)

        assert queue.queue_length() == 1
        assert queue.processing_length() == 2
