# Migration Guide

This guide covers upgrading between infrastructure levels. Each migration is additive and reversible.

## Level 0 to Level 1: Add Database Persistence

### What Changes

| Before (Level 0)                | After (Level 1)                       |
| ------------------------------- | ------------------------------------- |
| Events in local SQLite file     | Events in shared database             |
| Checkpoints on local disk       | Checkpoints in shared database        |
| DLQ in local SQLite file        | DLQ in shared database                |
| Execution metadata in memory    | Execution metadata in shared database |
| No idempotency                  | Persistent idempotency store          |
| State lost on process restart\* | State persists across restarts        |

\*Level 0 EventStore and DLQ persist to local SQLite files, but these are not shared across processes.

### Pre-Migration Checklist

- [ ] Database server is running and accessible (PostgreSQL, MySQL, or SQLite on a shared path)
- [ ] Database and user are created with appropriate permissions
- [ ] Network connectivity from application to database is confirmed
- [ ] Required driver is installed:
  - PostgreSQL: `pip install kailash[postgres]` (installs asyncpg)
  - MySQL: `pip install kailash[mysql]` (installs aiomysql)
  - SQLite (shared): `pip install kailash[database]` (installs aiosqlite)

### Step 1: Set the Environment Variable

```bash
# PostgreSQL (recommended for production)
export KAILASH_DATABASE_URL=postgresql://user:password@localhost:5432/kailash

# MySQL
export KAILASH_DATABASE_URL=mysql://user:password@localhost:3306/kailash

# SQLite on shared filesystem (dev/staging only)
export KAILASH_DATABASE_URL=sqlite:///shared/path/kailash.db
```

The `KAILASH_DATABASE_URL` variable takes priority. If your environment already uses `DATABASE_URL` (common with Heroku, Railway, Render), that works too -- Kailash checks `KAILASH_DATABASE_URL` first, then `DATABASE_URL`.

### Step 2: Run Your Application

No code changes needed. The `StoreFactory` auto-detects the database URL and creates DB-backed stores. All infrastructure tables (`kailash_events`, `kailash_checkpoints`, `kailash_dlq`, `kailash_executions`, `kailash_idempotency`, `kailash_meta`) are created automatically on first use.

```python
# This code is unchanged from Level 0
from kailash import WorkflowBuilder, LocalRuntime

builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "greet", {
    "code": "output = f'Hello, {name}!'",
    "inputs": {"name": "str"},
    "output_type": "str",
})
wf = builder.build()

with LocalRuntime() as runtime:
    results, run_id = runtime.execute(wf, parameters={"greet": {"name": "World"}})
```

### Step 3: Verify

Check that tables were created:

```sql
-- PostgreSQL
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name LIKE 'kailash_%';

-- MySQL
SHOW TABLES LIKE 'kailash_%';

-- SQLite
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kailash_%';
```

Expected tables:

- `kailash_meta`
- `kailash_events`
- `kailash_checkpoints`
- `kailash_dlq`
- `kailash_executions`
- `kailash_idempotency`

### Rollback

Remove the environment variable. The application falls back to Level 0 defaults:

```bash
unset KAILASH_DATABASE_URL
unset DATABASE_URL
```

Data in the database is retained and available if you re-enable the variable later.

---

## Level 1 to Level 2: Add Task Queue

### What Changes

| Before (Level 1)         | After (Level 2)                      |
| ------------------------ | ------------------------------------ |
| Single-process execution | Multi-worker task distribution       |
| No task queue            | Redis or SQL-backed task queue       |
| Local runtime only       | Workers can run on separate machines |

### Pre-Migration Checklist

- [ ] Level 1 is working (database URL configured and stores functional)
- [ ] Queue backend is running:
  - Redis: `redis-server` or managed Redis instance
  - SQL: Same database as Level 1 (no extra setup)
- [ ] Network connectivity from all workers to the queue backend
- [ ] For Redis: `pip install redis` (or `pip install kailash[redis]` if available)

### Step 1: Set the Queue URL

```bash
# Redis (recommended for production)
export KAILASH_QUEUE_URL=redis://localhost:6379/0

# PostgreSQL (uses same database as stores -- no new dependency)
export KAILASH_QUEUE_URL=postgresql://user:password@localhost:5432/kailash

# SQLite (dev only -- limited concurrency)
export KAILASH_QUEUE_URL=sqlite:///queue.db
```

### Step 2: Create Workers

Workers are separate processes that dequeue and execute tasks:

```python
import asyncio
from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import create_task_queue

async def run_worker(worker_id: str):
    queue = await create_task_queue()  # auto-detects from KAILASH_QUEUE_URL
    runtime = LocalRuntime()  # Don't forget to call runtime.close() when done

    print(f"Worker {worker_id} started, polling for tasks...")

    while True:
        task = await queue.dequeue(queue_name="default", worker_id=worker_id)

        if task is None:
            await asyncio.sleep(1)
            continue

        try:
            # Build and execute the workflow from task payload
            builder = WorkflowBuilder()
            builder.add_node("PythonCodeNode", "process", {
                "code": task.payload.get("code", "output = 'no-op'"),
                "inputs": task.payload.get("inputs", {}),
                "output_type": task.payload.get("output_type", "str"),
            })
            wf = builder.build()

            results, run_id = runtime.execute(
                wf, parameters=task.payload.get("parameters", {})
            )
            await queue.complete(task.task_id)
            print(f"Task {task.task_id} completed: {results}")
        except Exception as e:
            await queue.fail(task.task_id, error=str(e))
            print(f"Task {task.task_id} failed: {e}")

        # Recover stale tasks periodically
        await queue.requeue_stale()

asyncio.run(run_worker("worker-1"))
```

### Step 3: Enqueue Tasks

From your application or API, enqueue tasks instead of executing directly:

```python
import asyncio
from kailash.infrastructure import create_task_queue

async def submit_task():
    queue = await create_task_queue()  # auto-detects from KAILASH_QUEUE_URL

    task_id = await queue.enqueue(
        payload={
            "code": "output = data.upper()",
            "inputs": {"data": "str"},
            "output_type": "str",
            "parameters": {"process": {"data": "hello"}},
        },
        queue_name="default",
        max_attempts=3,
    )
    print(f"Task submitted: {task_id}")

asyncio.run(submit_task())
```

### Step 4: Verify

Check queue statistics:

```python
stats = await queue.get_stats()
print(stats)  # {"pending": 0, "processing": 1, "completed": 5, ...}
```

### Rollback

Remove the queue URL. Workers will stop receiving tasks, and the application falls back to local single-process execution:

```bash
unset KAILASH_QUEUE_URL
```

The `create_task_queue()` call returns `None`, and your application should handle this by executing locally:

```python
queue = await create_task_queue()
if queue is None:
    # No queue -- execute locally
    results, run_id = runtime.execute(wf, parameters=params)
else:
    # Queue available -- enqueue for distributed processing
    await queue.enqueue(payload=task_data)
```

---

## Common Pitfalls

### 1. Forgetting the Driver Package

**Symptom**: `ImportError: asyncpg is required for PostgreSQL connections`

**Fix**: Install the appropriate extra:

```bash
pip install kailash[postgres]   # PostgreSQL
pip install kailash[mysql]      # MySQL
pip install kailash[database]   # SQLite (aiosqlite)
```

### 2. Using SQLite for Multi-Process Production

**Symptom**: `database is locked` errors under load.

**Why**: SQLite uses file-level locking. Concurrent writers across processes cause contention.

**Fix**: Use PostgreSQL or MySQL for multi-process deployments. SQLite is suitable for single-process or development use.

### 3. Queue URL Matching Database URL

**Symptom**: Queue creates a second connection pool to the same database.

**Why**: `KAILASH_QUEUE_URL` and `KAILASH_DATABASE_URL` create independent `ConnectionManager` instances, even if they point to the same database.

**Impact**: This is intentional and correct -- the queue operates independently from the stores. The overhead of a second connection pool is minimal.

### 4. Missing Table Auto-Creation

**Symptom**: `relation "kailash_events" does not exist`

**Why**: Tables are created lazily by `StoreFactory.initialize()`. If you use stores directly without going through the factory, you must call `await store.initialize()` on each store.

**Fix**: Either use `StoreFactory` (recommended) or initialize stores manually:

```python
from kailash.db.connection import ConnectionManager
from kailash.infrastructure import DBEventStoreBackend

conn = ConnectionManager("postgresql://...")
await conn.initialize()

store = DBEventStoreBackend(conn)
await store.initialize()  # Creates the table
```

### 5. Schema Version Mismatch

**Symptom**: `RuntimeError: Database schema version 2 is newer than code version 1`

**Why**: The database was initialized by a newer version of Kailash than you are running.

**Fix**: Upgrade to the latest version of Kailash:

```bash
pip install --upgrade kailash
```

### 6. Forgetting to Close the Factory

**Symptom**: Resource warnings about unclosed connections on shutdown.

**Fix**: Always close the factory when done:

```python
factory = StoreFactory()
try:
    # ... use stores ...
finally:
    await factory.close()
```
