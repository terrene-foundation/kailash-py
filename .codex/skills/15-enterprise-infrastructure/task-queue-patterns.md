# Task Queue Patterns

You are an expert in Kailash task queue patterns for multi-worker deployments. Guide users through the SQL task queue, Redis queue, worker registry, and the decision framework for choosing between them.

> For full implementation details, see `docs/enterprise-infrastructure/03-task-queue.md` and the source at `kailash/infrastructure/task_queue.py`.

## SQL Task Queue with SKIP LOCKED

The `SQLTaskQueue` provides database-backed task distribution using `FOR UPDATE SKIP LOCKED` on PostgreSQL/MySQL for concurrent dequeue without contention, and `BEGIN IMMEDIATE` on SQLite for single-writer safety.

### Setup

```python
from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueue

conn = ConnectionManager("postgresql://user:pass@localhost/kailash")
await conn.initialize()

queue = SQLTaskQueue(conn, table_name="kailash_task_queue")
await queue.initialize()  # CREATE TABLE IF NOT EXISTS
```

### Enqueue

```python
task_id = await queue.enqueue(
    payload={"workflow_id": "etl-pipeline", "params": {"source": "s3://bucket"}},
    queue_name="default",
    max_attempts=3,
    visibility_timeout=300,  # seconds before requeue if worker dies
)
# Returns: task_id (str, auto-generated UUID if not provided)
```

### Atomic Dequeue

The dequeue operation is atomic -- SELECT + UPDATE happens within a single transaction:

```python
task = await queue.dequeue(queue_name="default", worker_id="worker-1")
if task is None:
    # Queue is empty
    pass
else:
    # task is a SQLTaskMessage dataclass
    print(task.task_id, task.payload, task.attempts)
```

**How it works** (from `kailash/infrastructure/task_queue.py`):

```python
async with self._conn.transaction() as tx:
    # 1. Find oldest pending task (with row lock on PG/MySQL)
    select_sql = (
        f"SELECT task_id FROM {self._table} "
        f"WHERE queue_name = ? AND status = 'pending' "
        f"ORDER BY created_at ASC LIMIT 1"
    )
    if lock_clause:
        select_sql += f" {lock_clause}"
    row = await tx.fetchone(select_sql, queue_name)

    # 2. Claim it atomically
    await tx.execute(
        f"UPDATE {self._table} SET status = 'processing', "
        "worker_id = ?, updated_at = ?, attempts = attempts + 1 "
        "WHERE task_id = ? AND status = 'pending'",
        worker_id, now, tid,
    )
```

### Complete / Fail

```python
# On success:
await queue.complete(task.task_id)

# On failure (auto-retries up to max_attempts, then dead-letters):
await queue.fail(task.task_id, error="Connection timeout to external API")
```

### Stale Task Requeue

Workers that die without completing tasks leave them stuck in `processing`. The requeue method finds and recovers them:

```python
requeued_count = await queue.requeue_stale(queue_name="default")
# Requeues tasks stuck in 'processing' past their visibility_timeout
# Tasks exceeding max_attempts are moved to 'dead_lettered'
```

### Queue Statistics

```python
stats = await queue.get_stats(queue_name="default")
# {"pending": 5, "processing": 2, "completed": 10, "dead_lettered": 1}
```

### Purge Completed

```python
import time
# Remove completed tasks older than 24 hours
removed = await queue.purge_completed(
    queue_name="default",
    older_than=time.time() - 86400,
)
```

## SQLTaskMessage Dataclass

```python
from kailash.infrastructure.task_queue import SQLTaskMessage

@dataclass
class SQLTaskMessage:
    task_id: str = ""
    queue_name: str = "default"
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"           # pending, processing, completed, failed, dead_lettered
    created_at: float = 0.0           # Unix timestamp
    updated_at: float = 0.0
    attempts: int = 0
    max_attempts: int = 3
    visibility_timeout: int = 300     # seconds
    worker_id: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SQLTaskMessage: ...
```

## Worker Registry

The `SQLWorkerRegistry` tracks worker processes with heartbeat monitoring and dead worker reaping.

### Setup

```python
from kailash.infrastructure.worker_registry import SQLWorkerRegistry

registry = SQLWorkerRegistry(
    conn=conn,
    task_queue=queue,  # Needed to requeue tasks from dead workers
    table_name="kailash_worker_registry",
)
await registry.initialize()
```

### Worker Lifecycle

```python
import uuid

worker_id = f"worker-{uuid.uuid4().hex[:8]}"

# Register
await registry.register(worker_id, queue_name="default")

# Periodic heartbeat (run in background loop)
await registry.heartbeat(worker_id)

# Track current task
await registry.set_current_task(worker_id, task.task_id)
# ... process task ...
await registry.clear_current_task(worker_id)

# Graceful shutdown
await registry.deregister(worker_id)
```

### Dead Worker Reaping

```python
# Reap workers with no heartbeat in the last 60 seconds
reaped = await registry.reap_dead_workers(
    staleness_seconds=60.0,
    queue_name="default",
)
# For each dead worker:
#   1. Requeues their processing tasks back to 'pending'
#   2. Marks the worker as 'inactive'
```

The reap operation is transactional per worker -- task requeue and worker deactivation happen atomically.

## Queue Factory

The `create_task_queue()` factory auto-detects the queue backend from `KAILASH_QUEUE_URL`:

```python
from kailash.infrastructure.queue_factory import create_task_queue

# Auto-detect from environment
queue = await create_task_queue()

# Explicit URL
queue = await create_task_queue("redis://localhost:6379/0")
queue = await create_task_queue("postgresql://user:pass@localhost/kailash")
queue = await create_task_queue("sqlite:///queue.db")

if queue is None:
    # Level 0/1: no queue configured, single-process only
    pass
```

### URL Scheme Mapping

| URL Scheme                     | Backend              | Class                                    |
| ------------------------------ | -------------------- | ---------------------------------------- |
| `redis://`, `rediss://`        | Redis                | `TaskQueue` (from `runtime.distributed`) |
| `postgresql://`, `postgres://` | PostgreSQL SQL queue | `SQLTaskQueue`                           |
| `mysql://`                     | MySQL SQL queue      | `SQLTaskQueue`                           |
| `sqlite:///`                   | SQLite SQL queue     | `SQLTaskQueue`                           |
| Plain file path                | SQLite SQL queue     | `SQLTaskQueue`                           |

## Redis vs SQL Decision Matrix

| Factor                 | Redis Queue                     | SQL Queue                          |
| ---------------------- | ------------------------------- | ---------------------------------- |
| **Latency**            | Sub-millisecond dequeue         | 1-5ms dequeue                      |
| **Throughput**         | 100K+ ops/sec                   | 10K+ ops/sec                       |
| **Dependencies**       | Requires Redis server           | Uses existing database             |
| **Reliability**        | BRPOPLPUSH reliable delivery    | FOR UPDATE SKIP LOCKED             |
| **Visibility timeout** | Built into Redis list ops       | Column-based with requeue_stale()  |
| **Dead letter**        | Redis-native DLQ                | Status column + max_attempts       |
| **Monitoring**         | Redis CLI, RedisInsight         | Standard SQL queries               |
| **Best for**           | High-throughput, existing Redis | Simpler infra, PG-only deployments |
| **Avoid when**         | No Redis in stack               | Ultra-high throughput needed       |

### Recommendation

- **Already have Redis?** Use `redis://` -- battle-tested, higher throughput
- **PostgreSQL-only stack?** Use `postgresql://` SQL queue -- zero new dependencies
- **Development/testing?** Use `sqlite:///` -- no server required

## Table Schema

```sql
-- kailash_task_queue
CREATE TABLE IF NOT EXISTS kailash_task_queue (
    task_id TEXT PRIMARY KEY,
    queue_name TEXT NOT NULL DEFAULT 'default',
    payload TEXT NOT NULL,                       -- JSON
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,                    -- Unix timestamp
    updated_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    visibility_timeout INTEGER NOT NULL DEFAULT 300,
    worker_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);

-- Indices for efficient dequeue and stale detection
CREATE INDEX IF NOT EXISTS idx_kailash_task_queue_dequeue
    ON kailash_task_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_kailash_task_queue_stale
    ON kailash_task_queue (status, updated_at);

-- kailash_worker_registry
CREATE TABLE IF NOT EXISTS kailash_worker_registry (
    worker_id TEXT PRIMARY KEY,
    queue_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_beat_at REAL NOT NULL,
    started_at REAL NOT NULL,
    current_task TEXT,
    metadata_json TEXT DEFAULT '{}'
);
```

## When to Engage

- User asks about "task queue", "SKIP LOCKED", "multi-worker", "distributed"
- User asks about "Redis vs SQL queue", "KAILASH_QUEUE_URL"
- User asks about "worker registry", "heartbeat", "dead worker reaping"
- User needs to set up Level 2 multi-worker processing
- User asks about "visibility timeout", "dead letter", "retry", "requeue"
