# Multi-Worker Quickstart (15 Minutes)

Go from a single-process workflow to a multi-worker distributed system in four steps. Each step adds one capability by setting an environment variable -- your workflow code never changes.

## Prerequisites

- Python 3.10+
- Docker (for PostgreSQL and Redis in Steps 2-4)
- `pip install kailash`

## Step 1: Level 0 -- Zero Config

Run a workflow with no configuration at all. Kailash uses SQLite and in-memory stores by default.

Create `app.py`:

```python
from kailash import WorkflowBuilder, LocalRuntime

# Build a workflow that processes text
builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "transform", {
    "code": "output = text.upper().replace(' ', '_')",
    "inputs": {"text": "str"},
    "output_type": "str",
})
wf = builder.build()

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(wf, parameters={
    "transform": {"text": "hello world"}
})

print(f"Result: {results['transform']}")
print(f"Run ID: {run_id}")
```

Run it:

```bash
python app.py
# Result: {'output': 'HELLO_WORLD'}
# Run ID: abc123...
```

No environment variables, no databases, no configuration files. Everything works.

## Step 2: Level 1 -- Durable Database Storage

Start a PostgreSQL instance and set one environment variable. Your workflow code is unchanged -- stores automatically switch to database-backed persistence.

### Start PostgreSQL

```bash
docker run -d \
  --name kailash-pg \
  -e POSTGRES_USER=kailash \
  -e POSTGRES_PASSWORD=kailash \
  -e POSTGRES_DB=kailash \
  -p 5432:5432 \
  postgres:16
```

### Install the PostgreSQL Driver

```bash
pip install kailash[postgres]
```

### Set the Database URL

```bash
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
```

### Run the Same App

```bash
python app.py
# Result: {'output': 'HELLO_WORLD'}
# Run ID: def456...
```

The output is identical. Behind the scenes, events, checkpoints, execution metadata, and the dead letter queue now persist to PostgreSQL. Restart the process and the data survives.

### Verify

Connect to PostgreSQL and check:

```bash
docker exec -it kailash-pg psql -U kailash -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'kailash_%';"
```

You should see: `kailash_meta`, `kailash_events`, `kailash_checkpoints`, `kailash_dlq`, `kailash_executions`, `kailash_idempotency`.

## Step 3: Level 2 -- Distributed Task Queue

Add a Redis instance and set a second environment variable. Tasks are now distributed across workers.

### Start Redis

```bash
docker run -d \
  --name kailash-redis \
  -p 6379:6379 \
  redis:7
```

### Set the Queue URL

```bash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
```

### Create a Task Producer

Create `producer.py`:

```python
import asyncio
from kailash.infrastructure import create_task_queue

async def main():
    queue = await create_task_queue()  # auto-detects from KAILASH_QUEUE_URL

    for i in range(5):
        task_id = await queue.enqueue(
            payload={
                "workflow_id": "text-transform",
                "code": "output = text.upper().replace(' ', '_')",
                "inputs": {"text": "str"},
                "output_type": "str",
                "parameters": {"transform": {"text": f"message number {i}"}},
            },
            queue_name="default",
            max_attempts=3,
        )
        print(f"Enqueued task {task_id}")

    stats = await queue.get_stats()
    print(f"Queue stats: {stats}")

asyncio.run(main())
```

### Create a Worker

Create `worker.py`:

```python
import asyncio
from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import create_task_queue

async def run_worker(worker_id: str):
    queue = await create_task_queue()
    runtime = LocalRuntime()

    print(f"[{worker_id}] Worker started, polling for tasks...")

    while True:
        task = await queue.dequeue(queue_name="default", worker_id=worker_id)

        if task is None:
            await asyncio.sleep(1)
            continue

        print(f"[{worker_id}] Processing task {task.task_id}")

        try:
            builder = WorkflowBuilder()
            builder.add_node("PythonCodeNode", "transform", {
                "code": task.payload["code"],
                "inputs": task.payload["inputs"],
                "output_type": task.payload["output_type"],
            })
            wf = builder.build()

            results, run_id = runtime.execute(
                wf, parameters=task.payload.get("parameters", {})
            )
            await queue.complete(task.task_id)
            print(f"[{worker_id}] Task {task.task_id} completed: {results}")
        except Exception as e:
            await queue.fail(task.task_id, error=str(e))
            print(f"[{worker_id}] Task {task.task_id} failed: {e}")

        await queue.requeue_stale()

asyncio.run(run_worker("worker-1"))
```

### Run It

Terminal 1 -- start the worker:

```bash
python worker.py
# [worker-1] Worker started, polling for tasks...
```

Terminal 2 -- submit tasks:

```bash
python producer.py
# Enqueued task abc-123
# Enqueued task def-456
# ...
```

The worker picks up tasks and processes them:

```
[worker-1] Processing task abc-123
[worker-1] Task abc-123 completed: {'transform': {'output': 'MESSAGE_NUMBER_0'}}
[worker-1] Processing task def-456
[worker-1] Task def-456 completed: {'transform': {'output': 'MESSAGE_NUMBER_1'}}
```

Start more workers in additional terminals to process tasks in parallel.

## Step 4: Add Idempotency

Wrap your runtime with `IdempotentExecutor` to ensure exactly-once execution. Duplicate requests with the same idempotency key return cached results.

Create `idempotent_app.py`:

```python
import asyncio
from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import StoreFactory, IdempotentExecutor

async def main():
    # Create the idempotency store
    factory = StoreFactory()  # auto-detects from KAILASH_DATABASE_URL
    idempotency_store = await factory.create_idempotency_store()

    if idempotency_store is None:
        print("Idempotency requires KAILASH_DATABASE_URL to be set")
        return

    executor = IdempotentExecutor(idempotency_store, ttl_seconds=3600)

    # Build a workflow
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "transform", {
        "code": "output = text.upper()",
        "inputs": {"text": "str"},
        "output_type": "str",
    })
    wf = builder.build()

    runtime = LocalRuntime()

    # First call -- executes the workflow
    print("Call 1 (fresh execution):")
    results, run_id = await executor.execute(
        runtime, wf,
        parameters={"transform": {"text": "hello"}},
        idempotency_key="unique-request-001",
    )
    print(f"  Results: {results}")
    print(f"  Run ID:  {run_id}")

    # Second call with same key -- returns cached result
    print("\nCall 2 (cached, no re-execution):")
    results2, run_id2 = await executor.execute(
        runtime, wf,
        parameters={"transform": {"text": "hello"}},
        idempotency_key="unique-request-001",
    )
    print(f"  Results: {results2}")
    print(f"  Run ID:  {run_id2}")

    print(f"\nSame result? {results == results2}")

    await factory.close()

asyncio.run(main())
```

Run it (with `KAILASH_DATABASE_URL` still set):

```bash
python idempotent_app.py
# Call 1 (fresh execution):
#   Results: {'transform': {'output': 'HELLO'}}
#   Run ID:  abc123...
#
# Call 2 (cached, no re-execution):
#   Results: {'transform': {'output': 'HELLO'}}
#   Run ID:  abc123...
#
# Same result? True
```

The second call returns instantly from cache. No workflow re-execution.

## Production Checklist

Before deploying to production:

- [ ] **PostgreSQL**: Use a managed instance (AWS RDS, Cloud SQL, etc.) with connection pooling
- [ ] **Redis**: Use a managed instance (ElastiCache, Memorystore, etc.) with TLS (`rediss://`)
- [ ] **Credentials**: Store `KAILASH_DATABASE_URL` and `KAILASH_QUEUE_URL` in your secret manager (not in code or `.env` files committed to git)
- [ ] **Workers**: Run multiple worker processes behind a process manager (systemd, supervisord, Kubernetes)
- [ ] **Stale task recovery**: Run `queue.requeue_stale()` periodically (every 60s) from each worker or a dedicated supervisor
- [ ] **Idempotency cleanup**: Run `idempotency_store.cleanup()` periodically to purge expired entries
- [ ] **Monitoring**: Track queue depth (`queue.get_stats()`) and DLQ growth (`dlq.get_stats()`) with your metrics system
- [ ] **Backups**: Standard PostgreSQL backup strategy for the `kailash_*` tables

## Cleanup

Stop the Docker containers:

```bash
docker rm -f kailash-pg kailash-redis
```

Unset environment variables:

```bash
unset KAILASH_DATABASE_URL
unset KAILASH_QUEUE_URL
```

## Next Steps

- [Progressive Infrastructure Overview](../enterprise-infrastructure/01-overview.md) -- architecture and design principles
- [Store Backends Reference](../enterprise-infrastructure/02-store-backends.md) -- table schemas and API details
- [Task Queue Reference](../enterprise-infrastructure/03-task-queue.md) -- Redis vs SQL queue comparison
- [Idempotency Reference](../enterprise-infrastructure/04-idempotency.md) -- exactly-once execution details
- [Migration Guide](../enterprise-infrastructure/05-migration-guide.md) -- upgrading between levels
