# Task Queue Reference

The task queue enables Level 2 multi-worker deployments. Workers dequeue tasks from a shared queue and execute workflows independently. Kailash supports two queue backends: Redis and SQL.

## Queue Factory

The `create_task_queue()` function auto-detects the backend from `KAILASH_QUEUE_URL`:

```python
from kailash.infrastructure import create_task_queue

# Auto-detect from environment
queue = await create_task_queue()

# Or pass an explicit URL
queue = await create_task_queue("redis://localhost:6379/0")
queue = await create_task_queue("postgresql://user:pass@localhost:5432/kailash")
queue = await create_task_queue("sqlite:///queue.db")

# Returns None if no queue URL is configured (Level 0/1)
if queue is None:
    print("No queue configured -- single-process mode")
```

## When to Use Which Backend

| Factor                 | Redis Queue            | SQL Queue                          |
| ---------------------- | ---------------------- | ---------------------------------- |
| **Throughput**         | High (in-memory)       | Moderate (disk I/O)                |
| **Latency**            | Sub-millisecond        | 1-10ms                             |
| **New dependency**     | Yes (Redis server)     | No (uses existing DB)              |
| **Persistence**        | Optional (AOF/RDB)     | Always durable                     |
| **Best for**           | High-volume production | Dev, staging, or simple production |
| **Concurrent workers** | Unlimited              | Hundreds (SKIP LOCKED)             |

**Recommendation**: Use Redis for production workloads with high throughput requirements. Use the SQL queue when you already have a database and want to avoid adding Redis as a dependency.

## Redis Queue

The Redis-backed `TaskQueue` uses `BLMOVE` for reliable delivery with automatic dead-letter handling.

### URL Format

```
redis://localhost:6379/0
redis://user:password@redis.example.com:6379/0
rediss://user:password@redis.example.com:6379/0   # TLS
```

### Usage

```python
from kailash.infrastructure import create_task_queue

queue = await create_task_queue("redis://localhost:6379/0")
```

The Redis queue is the same `TaskQueue` from `kailash.runtime.distributed` that powers the `DistributedRuntime`. It provides:

- Reliable delivery via `BLMOVE`
- Worker heartbeat monitoring
- Dead worker detection and task recovery
- Configurable visibility timeout

## SQL Queue

The `SQLTaskQueue` uses the `ConnectionManager` abstraction to provide a database-backed queue that works across PostgreSQL, MySQL 8.0+, and SQLite.

### URL Format

Any URL that `ConnectionManager` understands:

```
postgresql://user:pass@localhost:5432/kailash
mysql://user:pass@localhost:3306/kailash
sqlite:///queue.db
```

### Table: `kailash_task_queue`

| Column               | Type    | Constraints                | Notes                                                     |
| -------------------- | ------- | -------------------------- | --------------------------------------------------------- |
| `task_id`            | TEXT    | PRIMARY KEY                | UUID                                                      |
| `queue_name`         | TEXT    | NOT NULL DEFAULT 'default' | Logical queue name                                        |
| `payload`            | TEXT    | NOT NULL                   | JSON-serialized task data                                 |
| `status`             | TEXT    | NOT NULL DEFAULT 'pending' | pending / processing / completed / failed / dead_lettered |
| `created_at`         | REAL    | NOT NULL                   | Unix timestamp                                            |
| `updated_at`         | REAL    | NOT NULL                   | Unix timestamp (last status change)                       |
| `attempts`           | INTEGER | NOT NULL DEFAULT 0         | Processing attempts so far                                |
| `max_attempts`       | INTEGER | NOT NULL DEFAULT 3         | Maximum attempts before dead-letter                       |
| `visibility_timeout` | INTEGER | NOT NULL DEFAULT 300       | Seconds before requeue                                    |
| `worker_id`          | TEXT    | NOT NULL DEFAULT ''        | Current worker                                            |
| `error`              | TEXT    | NOT NULL DEFAULT ''        | Last error message                                        |

**Indexes**:

- `idx_kailash_task_queue_dequeue` on `(status, created_at)` -- efficient pending task lookup
- `idx_kailash_task_queue_stale` on `(status, updated_at)` -- stale task detection

### Concurrency Strategy

The SQL queue uses different strategies per database to ensure safe concurrent dequeue:

| Database   | Strategy                 | How It Works                         |
| ---------- | ------------------------ | ------------------------------------ |
| PostgreSQL | `FOR UPDATE SKIP LOCKED` | Row-level locking, skips locked rows |
| MySQL 8.0+ | `FOR UPDATE SKIP LOCKED` | Row-level locking, skips locked rows |
| SQLite     | `BEGIN IMMEDIATE`        | Serialized write transactions        |

On PostgreSQL and MySQL, multiple workers can dequeue concurrently without blocking each other. Each worker locks only the row it claims and skips rows locked by other workers.

On SQLite, the `BEGIN IMMEDIATE` transaction serializes writes. This is safe for single-machine multi-process setups but limits throughput compared to PostgreSQL.

### Task Lifecycle

```
    enqueue()
       │
       ▼
   ┌─────────┐   dequeue()   ┌────────────┐
   │ pending  │──────────────▶│ processing │
   └─────────┘               └─────┬──────┘
       ▲                           │
       │                     ┌─────┴─────┐
       │                     │           │
       │               complete()    fail()
       │                     │           │
       │                     ▼           ▼
       │              ┌───────────┐ ┌────────┐
       │              │ completed │ │ failed │
       │              └───────────┘ └───┬────┘
       │                                │
       │    attempts < max_attempts     │  attempts >= max_attempts
       └────────────────────────────────┘           │
                                                    ▼
                                            ┌───────────────┐
                                            │ dead_lettered │
                                            └───────────────┘
```

### Enqueue

```python
from kailash.infrastructure import create_task_queue

queue = await create_task_queue("postgresql://user:pass@localhost:5432/kailash")

# Enqueue a task
task_id = await queue.enqueue(
    payload={"workflow_id": "my-workflow", "parameters": {"input": "data"}},
    queue_name="default",
    max_attempts=3,
    visibility_timeout=300,
)
```

### Dequeue

```python
# Dequeue the next pending task (atomic claim)
task = await queue.dequeue(queue_name="default", worker_id="worker-1")

if task is not None:
    print(f"Processing task {task.task_id}")
    print(f"Payload: {task.payload}")
    print(f"Attempt {task.attempts} of {task.max_attempts}")
```

### Complete / Fail

```python
try:
    result = execute_workflow(task.payload)
    await queue.complete(task.task_id)
except Exception as e:
    await queue.fail(task.task_id, error=str(e))
    # If attempts >= max_attempts, task moves to dead_lettered
    # Otherwise, returns to pending for retry
```

### Stale Task Recovery

Tasks stuck in `processing` past their `visibility_timeout` are considered stale (the worker likely crashed). The `requeue_stale()` method recovers them:

```python
# Requeue stale tasks (call periodically from a supervisor)
requeued = await queue.requeue_stale(queue_name="default")
print(f"Recovered {requeued} stale tasks")
```

This checks each processing task's `updated_at + visibility_timeout` against the current time. Stale tasks return to `pending` (or `dead_lettered` if max attempts reached).

### Queue Statistics

```python
stats = await queue.get_stats(queue_name="default")
# {"pending": 5, "processing": 2, "completed": 10, "failed": 0, "dead_lettered": 1}
```

### Purge Completed Tasks

```python
import time

# Purge all completed tasks
removed = await queue.purge_completed(queue_name="default")

# Purge completed tasks older than 1 hour
cutoff = time.time() - 3600
removed = await queue.purge_completed(queue_name="default", older_than=cutoff)
```

## Worker Loop Pattern

A basic worker loop using the SQL task queue:

```python
import asyncio
from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import create_task_queue

async def worker_loop(queue_url: str, worker_id: str):
    queue = await create_task_queue(queue_url)
    runtime = LocalRuntime()

    while True:
        task = await queue.dequeue(queue_name="default", worker_id=worker_id)

        if task is None:
            await asyncio.sleep(1)  # No tasks available, poll again
            continue

        try:
            # Reconstruct and execute the workflow from the task payload
            workflow_id = task.payload["workflow_id"]
            parameters = task.payload.get("parameters", {})

            wf_builder = WorkflowBuilder()
            # ... build workflow based on workflow_id ...
            wf = wf_builder.build()

            results, run_id = runtime.execute(wf, parameters=parameters)
            await queue.complete(task.task_id)
        except Exception as e:
            await queue.fail(task.task_id, error=str(e))

        # Periodically recover stale tasks
        await queue.requeue_stale()
```
