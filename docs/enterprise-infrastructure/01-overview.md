# Progressive Infrastructure Model

Kailash Python SDK uses a **progressive infrastructure** model: start with zero configuration on a single machine, scale to a multi-worker PostgreSQL-backed deployment by changing environment variables. Your workflow code never changes.

## The Three Levels

```
Level 0    pip install kailash
           In-process, SQLite, single worker
           Zero configuration required

Level 1    KAILASH_DATABASE_URL=postgresql://...
           Shared state across restarts and processes
           All stores persist to PostgreSQL (or MySQL)

Level 2    KAILASH_QUEUE_URL=redis://...
           Multi-worker task distribution
           Redis or SQL-backed task queue
```

Each level is **additive**. Code written at Level 0 runs unchanged at Level 2.

## What Changes at Each Level

### Level 0: Zero Config

No environment variables needed. All state lives in local SQLite databases and in-memory stores.

| Store             | Backend                            |
| ----------------- | ---------------------------------- |
| EventStore        | SQLite (file: `kailash_events.db`) |
| CheckpointStore   | Disk (file-based)                  |
| Dead Letter Queue | SQLite (file: `kailash_dlq.db`)    |
| ExecutionStore    | In-memory (dict)                   |
| IdempotencyStore  | Not available                      |
| Task Queue        | Not available (single-process)     |

```python
from kailash import WorkflowBuilder, LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "greet", {
    "code": "output = f'Hello, {name}!'",
    "inputs": {"name": "str"},
    "output_type": "str",
})
wf = workflow.build()

runtime = LocalRuntime()
results, run_id = runtime.execute(wf, parameters={"greet": {"name": "World"}})
print(results["greet"])  # Hello, World!
```

### Level 1: Add a Database URL

Set **one environment variable** and all stores switch to database-backed persistence. No code changes.

```bash
export KAILASH_DATABASE_URL=postgresql://user:pass@localhost:5432/kailash
```

| Store             | Backend                        |
| ----------------- | ------------------------------ |
| EventStore        | `kailash_events` table         |
| CheckpointStore   | `kailash_checkpoints` table    |
| Dead Letter Queue | `kailash_dlq` table            |
| ExecutionStore    | `kailash_executions` table     |
| IdempotencyStore  | `kailash_idempotency` table    |
| Task Queue        | Not available (single-process) |

The workflow code from Level 0 runs identically. The `StoreFactory` auto-detects `KAILASH_DATABASE_URL` and creates database-backed stores instead of local defaults.

### Level 2: Add a Task Queue

Set a second environment variable to enable multi-worker task distribution.

```bash
export KAILASH_DATABASE_URL=postgresql://user:pass@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
```

| Store             | Backend                                       |
| ----------------- | --------------------------------------------- |
| EventStore        | `kailash_events` table                        |
| CheckpointStore   | `kailash_checkpoints` table                   |
| Dead Letter Queue | `kailash_dlq` table                           |
| ExecutionStore    | `kailash_executions` table                    |
| IdempotencyStore  | `kailash_idempotency` table                   |
| Task Queue        | Redis (or SQL via `kailash_task_queue` table) |

Workers dequeue tasks and execute workflows. The same `WorkflowBuilder` code from Level 0 is used.

## Environment Variables

| Variable               | Required | Fallback       | Purpose                             |
| ---------------------- | -------- | -------------- | ----------------------------------- |
| `KAILASH_DATABASE_URL` | No       | `DATABASE_URL` | Shared persistence for all stores   |
| `KAILASH_QUEUE_URL`    | No       | (none)         | Task queue backend for multi-worker |

### Supported URL Schemes

**Database URLs** (`KAILASH_DATABASE_URL`):

| Scheme              | Database   | Driver    | Install extra                   |
| ------------------- | ---------- | --------- | ------------------------------- |
| `postgresql://`     | PostgreSQL | asyncpg   | `pip install kailash[postgres]` |
| `postgres://`       | PostgreSQL | asyncpg   | `pip install kailash[postgres]` |
| `mysql://`          | MySQL      | aiomysql  | `pip install kailash[mysql]`    |
| `sqlite:///path.db` | SQLite     | aiosqlite | `pip install kailash[database]` |

**Queue URLs** (`KAILASH_QUEUE_URL`):

| Scheme              | Backend   | Notes                         |
| ------------------- | --------- | ----------------------------- |
| `redis://`          | Redis     | Recommended for production    |
| `rediss://`         | Redis+TLS | Redis with TLS encryption     |
| `postgresql://`     | SQL queue | Uses `FOR UPDATE SKIP LOCKED` |
| `mysql://`          | SQL queue | Uses `FOR UPDATE SKIP LOCKED` |
| `sqlite:///path.db` | SQL queue | Uses `BEGIN IMMEDIATE` (dev)  |

## Key Principle: Identical Workflow Code

The workflow definition, node configuration, and execution call are the same at every level. Only the environment variables and runtime choice change.

```python
# This code is level-agnostic -- it works at Level 0, 1, and 2.
from kailash import WorkflowBuilder, LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "output = data.upper()",
    "inputs": {"data": "str"},
    "output_type": "str",
})
wf = workflow.build()

runtime = LocalRuntime()
results, run_id = runtime.execute(wf, parameters={"process": {"data": "hello"}})
```

At Level 0, this stores events in local SQLite. At Level 1 with `KAILASH_DATABASE_URL` set, the same call persists events to PostgreSQL. The `StoreFactory` handles the detection and wiring transparently.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Your Workflow Code                     │
│    WorkflowBuilder → .build() → runtime.execute()        │
└─────────────────────┬───────────────────────────────────┘
                      │
              ┌───────┴───────┐
              │  StoreFactory  │  ← auto-detects from env vars
              └───────┬───────┘
                      │
        ┌─────────────┼─────────────┐
        │ Level 0     │ Level 1+    │
        │ SQLite/     │ Database    │
        │ In-memory   │ backends    │
        └─────────────┴─────────────┘
                      │
              ┌───────┴───────┐
              │  Queue Factory │  ← auto-detects from KAILASH_QUEUE_URL
              └───────┬───────┘
                      │
        ┌─────────────┼─────────────┐
        │ None        │ Level 2     │
        │ (single     │ Redis or    │
        │  process)   │ SQL queue   │
        └─────────────┴─────────────┘
```

## Next Steps

- [Store Backends Reference](02-store-backends.md) -- table schemas and backend details
- [Task Queue Reference](03-task-queue.md) -- Redis vs SQL queue
- [Idempotency Reference](04-idempotency.md) -- exactly-once execution
- [Migration Guide](05-migration-guide.md) -- moving between levels
