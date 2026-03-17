# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Level 2: Multi-worker task queue with distributed execution.

Combines database-backed stores (Level 1) with a task queue for
distributing work across multiple worker processes.

This file provides both a producer (enqueue tasks) and a worker
(dequeue and execute tasks) in a single script.

Usage:
    # Start infrastructure (see docker-compose.yml in this directory)
    docker compose up -d

    # Set environment variables
    export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
    export KAILASH_QUEUE_URL=redis://localhost:6379/0

    # Run the producer to enqueue tasks
    python level2_app.py produce

    # Run a worker to process tasks (in a separate terminal)
    python level2_app.py work --worker-id worker-1

    # Run the idempotent execution demo
    python level2_app.py idempotent
"""

import argparse
import asyncio
import sys

from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import (
    IdempotentExecutor,
    StoreFactory,
    create_task_queue,
)


def build_workflow(code: str, inputs: dict, output_type: str = "str"):
    """Build a single-node PythonCodeNode workflow."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "process",
        {
            "code": code,
            "inputs": inputs,
            "output_type": output_type,
        },
    )
    return builder.build()


async def produce(count: int = 5) -> None:
    """Enqueue tasks to the distributed queue."""
    queue = await create_task_queue()

    if queue is None:
        print("Error: KAILASH_QUEUE_URL is not set. Cannot enqueue tasks.")
        print("Set it to redis://localhost:6379/0 or a database URL.")
        sys.exit(1)

    print(f"Enqueuing {count} tasks...")

    for i in range(count):
        task_id = await queue.enqueue(
            payload={
                "code": "output = text.upper().replace(' ', '_')",
                "inputs": {"text": "str"},
                "output_type": "str",
                "parameters": {"process": {"text": f"message number {i}"}},
            },
            queue_name="default",
            max_attempts=3,
        )
        print(f"  Enqueued task {task_id}")

    stats = await queue.get_stats()
    print(f"\nQueue stats: {stats}")


async def work(worker_id: str) -> None:
    """Run a worker loop that dequeues and executes tasks."""
    queue = await create_task_queue()

    if queue is None:
        print("Error: KAILASH_QUEUE_URL is not set. Cannot start worker.")
        sys.exit(1)

    runtime = LocalRuntime()
    print(f"[{worker_id}] Worker started, polling for tasks...")

    tasks_processed = 0

    while True:
        task = await queue.dequeue(queue_name="default", worker_id=worker_id)

        if task is None:
            await asyncio.sleep(1)
            continue

        print(
            f"[{worker_id}] Processing task {task.task_id} "
            f"(attempt {task.attempts}/{task.max_attempts})"
        )

        try:
            wf = build_workflow(
                code=task.payload["code"],
                inputs=task.payload["inputs"],
                output_type=task.payload.get("output_type", "str"),
            )

            results, run_id = runtime.execute(
                wf, parameters=task.payload.get("parameters", {})
            )
            await queue.complete(task.task_id)
            tasks_processed += 1
            print(
                f"[{worker_id}] Task {task.task_id} completed "
                f"(total: {tasks_processed}): {results}"
            )
        except Exception as e:
            await queue.fail(task.task_id, error=str(e))
            print(f"[{worker_id}] Task {task.task_id} failed: {e}")

        # Recover stale tasks periodically
        requeued = await queue.requeue_stale()
        if requeued > 0:
            print(f"[{worker_id}] Recovered {requeued} stale task(s)")


async def idempotent_demo() -> None:
    """Demonstrate idempotent execution with cached results."""
    factory = StoreFactory()
    idempotency_store = await factory.create_idempotency_store()

    if idempotency_store is None:
        print(
            "Error: KAILASH_DATABASE_URL is not set. Idempotency requires a database."
        )
        sys.exit(1)

    executor = IdempotentExecutor(idempotency_store, ttl_seconds=3600)

    wf = build_workflow(
        code="output = text.upper()",
        inputs={"text": "str"},
    )

    runtime = LocalRuntime()

    # First call -- executes the workflow
    print("Call 1 (fresh execution):")
    results, run_id = await executor.execute(
        runtime,
        wf,
        parameters={"process": {"text": "hello world"}},
        idempotency_key="demo-key-001",
    )
    print(f"  Results: {results}")
    print(f"  Run ID:  {run_id}")

    # Second call with same key -- returns cached result instantly
    print("\nCall 2 (cached, no re-execution):")
    results2, run_id2 = await executor.execute(
        runtime,
        wf,
        parameters={"process": {"text": "hello world"}},
        idempotency_key="demo-key-001",
    )
    print(f"  Results: {results2}")
    print(f"  Run ID:  {run_id2}")

    # Third call with different key -- executes again
    print("\nCall 3 (different key, fresh execution):")
    results3, run_id3 = await executor.execute(
        runtime,
        wf,
        parameters={"process": {"text": "different input"}},
        idempotency_key="demo-key-002",
    )
    print(f"  Results: {results3}")
    print(f"  Run ID:  {run_id3}")

    print(f"\nCall 1 == Call 2? {results == results2}")
    print(f"Call 1 == Call 3? {results == results3}")

    await factory.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kailash Level 2: Multi-worker task queue demo"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # produce command
    produce_parser = subparsers.add_parser("produce", help="Enqueue tasks")
    produce_parser.add_argument(
        "--count", type=int, default=5, help="Number of tasks to enqueue"
    )

    # work command
    work_parser = subparsers.add_parser("work", help="Run a worker")
    work_parser.add_argument(
        "--worker-id", default="worker-1", help="Worker identifier"
    )

    # idempotent command
    subparsers.add_parser("idempotent", help="Idempotent execution demo")

    args = parser.parse_args()

    if args.command == "produce":
        asyncio.run(produce(count=args.count))
    elif args.command == "work":
        asyncio.run(work(worker_id=args.worker_id))
    elif args.command == "idempotent":
        asyncio.run(idempotent_demo())


if __name__ == "__main__":
    main()
