# Progressive Infrastructure

## Overview

Kailash SDK supports four infrastructure levels. Start with zero config, scale to multi-worker by changing environment variables. Never rewrite application code.

Your workflow code stays the same at every level. The SDK detects which environment variables are set and automatically provisions the right backends. This means you can develop locally with SQLite, test against PostgreSQL in CI, and run multi-worker in production — all with the same `runtime.execute(workflow.build())` call.

---

## Levels

### Level 0: Zero Config (Default)

- `pip install kailash` — nothing else required
- SQLite stores, in-memory execution, single process
- No environment variables needed
- Perfect for: development, prototyping, small workloads

At Level 0, the SDK uses file-based SQLite for durable stores (EventStore, DLQ) and in-memory dictionaries for ephemeral state (ExecutionStore). This is fully functional — workflows execute, events are recorded, checkpoints are persisted. The only limitation is single-process execution.

### Level 1: Database-Backed Persistence

- Set `KAILASH_DATABASE_URL=postgresql://...` (or `mysql://` or `sqlite:///path`)
- All stores auto-switch to the configured database
- Survives restarts, queryable execution history
- Perfect for: production single-server deployments

At Level 1, every store writes to the same database. You get transactional consistency across event logs, checkpoints, dead letter queue entries, and execution metadata. The database becomes your single source of truth, and you can query execution history with standard SQL tooling.

### Level 2: Multi-Worker

- Set `KAILASH_QUEUE_URL=redis://...` (or `postgresql://` for SQL-backed queue)
- Multiple workers dequeue and execute workflows in parallel
- Perfect for: horizontal scaling, high-throughput workloads

At Level 2, workflow submissions go into a task queue. Worker processes claim tasks using `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL/MySQL) or Redis `BRPOP` and execute them independently. Each worker is stateless — all shared state lives in the database from Level 1.

### Level 3: Cluster Coordination (v1.1+)

- Leader election, distributed locks, global ordering
- Coming in a future release
- Will add: fencing tokens, partition-aware scheduling, exactly-once delivery guarantees across restarts

---

## Environment Variables

| Variable               | Purpose                                                    | Default                         | Example                                    |
| ---------------------- | ---------------------------------------------------------- | ------------------------------- | ------------------------------------------ |
| `KAILASH_DATABASE_URL` | Infrastructure store backend                               | None (Level 0: SQLite files)    | `postgresql://user:pass@localhost/kailash` |
| `DATABASE_URL`         | Fallback for `KAILASH_DATABASE_URL`; also used by DataFlow | None (Level 0: SQLite files)    | `mysql://user:pass@localhost/kailash`      |
| `KAILASH_QUEUE_URL`    | Task queue backend                                         | None (no queue, single-process) | `redis://localhost:6379/0`                 |

**Resolution order**: The SDK checks `KAILASH_DATABASE_URL` first, then falls back to `DATABASE_URL`. This means DataFlow and Core SDK can share one database URL, or you can point them at different databases by setting both variables.

---

## Database Compatibility

| Feature                  | PostgreSQL   | MySQL 8.0+      | SQLite                            |
| ------------------------ | ------------ | --------------- | --------------------------------- |
| Infrastructure stores    | Yes          | Yes             | Yes                               |
| SKIP LOCKED (task queue) | Yes          | Yes             | No (FIFO fallback)                |
| Advisory locks           | Planned      | Planned         | N/A                               |
| JSONB columns            | Yes (native) | Yes (JSON type) | No (TEXT with JSON serialization) |
| Concurrent writers       | Unlimited    | Unlimited       | Single writer (WAL mode)          |
| Recommended for          | Production   | Production      | Development                       |

**SQLite is not a toy**: SQLite in WAL mode handles thousands of reads per second and is the correct choice for single-process deployments, development, and testing. Do not switch to PostgreSQL unless you need concurrent writers or multi-worker execution.

---

## Store Backends

| Store            | Purpose                  | Level 0 Default       | Level 1+                |
| ---------------- | ------------------------ | --------------------- | ----------------------- |
| EventStore       | Append-only event log    | SQLite file           | Database table          |
| CheckpointStore  | Workflow state snapshots | Disk files            | Database table          |
| DLQ              | Failed workflow retry    | SQLite file           | Database table          |
| ExecutionStore   | Run metadata tracking    | In-memory dict        | Database table          |
| IdempotencyStore | Exactly-once keys        | None                  | Database table          |
| TaskQueue        | Multi-worker dispatch    | None (single-process) | Redis or database table |

All stores implement the same Python protocol regardless of backend. Application code never interacts with store internals directly — the runtime handles backend selection transparently.

---

## Code Examples

### Level 0 (default — zero config)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("TransformNode", "process", {"operation": "uppercase"})
built = workflow.build()

with LocalRuntime() as runtime:
    results, run_id = runtime.execute(built, parameters={"input": "hello"})
    print(results["process"])
```

No environment variables. No database. No queue. Works immediately after `pip install kailash`.

### Level 1 (add one environment variable)

```bash
export KAILASH_DATABASE_URL=postgresql://user:pass@localhost:5432/kailash
python my_workflow.py  # Same code, now persists to PostgreSQL
```

The application code is identical to Level 0. The only change is the environment variable. Tables are created automatically on first use — no migration step required.

### Level 2 (add queue for multi-worker)

```bash
export KAILASH_DATABASE_URL=postgresql://user:pass@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0

# Terminal 1: Submit workflows
python submit_workflow.py

# Terminal 2+: Start workers
python -m kailash.worker
```

Workers are stateless processes that pull tasks from the queue. Start as many as you need. Each worker connects to the shared database for state and to Redis (or PostgreSQL) for task dispatch.

---

## Docker Compose (Development)

A minimal Docker Compose file for Level 2 local development:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: kailash
      POSTGRES_USER: kailash
      POSTGRES_PASSWORD: kailash
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

Then set your environment:

```bash
export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
```

---

## QueryDialect

The SDK automatically detects your database from the URL scheme and generates correct SQL for each backend:

- **PostgreSQL**: `$1` positional placeholders, `JSONB` column type, `FOR UPDATE SKIP LOCKED`
- **MySQL**: `%s` placeholders, `JSON` column type, `FOR UPDATE SKIP LOCKED`
- **SQLite**: `?` placeholders, `TEXT` column type, single-writer FIFO (no row-level locking)

You never write SQL directly. The store backends use QueryDialect internally to produce backend-appropriate queries. This is why the same application code runs on all three databases without changes.

---

## Migration Guide

### Level 0 to Level 1

1. Start your database (PostgreSQL or MySQL recommended for production)
2. Set `KAILASH_DATABASE_URL` to the connection string
3. Run your application — tables are created automatically on first use
4. No code changes needed

**What happens to existing data**: Level 0 SQLite files and in-memory state are independent of the database. If you need to migrate historical data, export from SQLite and import into the new database. For most users, starting fresh at Level 1 is the right choice.

### Level 1 to Level 2

1. Start Redis, or use your existing database as the queue backend (`KAILASH_QUEUE_URL=postgresql://...`)
2. Set `KAILASH_QUEUE_URL`
3. Start one or more worker processes: `python -m kailash.worker`
4. Submit workflows via `DistributedRuntime` instead of `LocalRuntime`

**Redis vs database queue**: Redis provides lower latency for task dispatch. PostgreSQL with `SKIP LOCKED` works well for moderate throughput and avoids adding another infrastructure dependency. Choose based on your latency requirements and operational preferences.

### Level 2 to Level 3

Level 3 is planned for v1.1+. The migration path will be documented when the feature ships. No application code changes will be required — consistent with the progressive infrastructure principle.

---

## Troubleshooting

| Symptom                      | Cause                                | Fix                                                                 |
| ---------------------------- | ------------------------------------ | ------------------------------------------------------------------- |
| `No module named asyncpg`    | Kailash not installed or corrupted   | `pip install kailash` (drivers are included in base install)        |
| `No module named aiomysql`   | Kailash not installed or corrupted   | `pip install kailash` (drivers are included in base install)        |
| Tables not created           | Insufficient database permissions    | Grant CREATE TABLE permission to the database user                  |
| Connection refused           | Wrong host/port in DATABASE_URL      | Verify the database is running and the connection string is correct |
| Workers not picking up tasks | KAILASH_QUEUE_URL not set on workers | Ensure all worker processes have the same environment variables     |
| Slow SQLite writes           | Multiple processes writing to SQLite | Switch to PostgreSQL (Level 1) for concurrent writer support        |

---

## Design Principles

1. **Environment variables, not code changes**: Moving between levels requires only environment variable changes. Application code is level-agnostic.
2. **Automatic provisioning**: Tables, indices, and queue structures are created on first use. No separate migration step.
3. **Backend transparency**: Store protocols are identical across backends. The runtime selects the implementation based on configuration.
4. **Graceful degradation**: If a Level 2 feature (e.g., SKIP LOCKED) is unavailable on the current database, the SDK falls back to a safe alternative (FIFO ordering) rather than failing.
5. **No lock-in**: Every level uses standard, widely-deployed infrastructure (SQLite, PostgreSQL, MySQL, Redis). There are no proprietary components at any level.
