---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
---

# Kailash Pattern Rules

## Runtime Execution

MUST use `runtime.execute(workflow.build())`.

**Why:** Calling `runtime.execute(workflow)` without `.build()` passes an unvalidated builder object, causing a cryptic `AttributeError` deep in the runtime instead of a clear validation error.

```python
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ❌ workflow.execute(runtime)  — wrong direction
# ❌ runtime.execute(workflow)  — missing .build()
```

## Node API

- Node IDs MUST be string literals (not variables, not f-strings)
  **Why:** Dynamic node IDs break workflow graph analysis, checkpoint recovery, and node-level debugging since the ID is only known at runtime.
- 4-parameter order: `add_node("NodeType", "node_id", {config}, connections)`
- Absolute imports only (`from kailash.workflow.builder import WorkflowBuilder`)
  **Why:** Relative imports break when files are moved or when the same module is loaded from different entry points, causing silent import duplication.
- Load .env before any operation (see `env-models.md`)

## DataFlow Express (Default for CRUD)

Use `db.express` for all single-record CRUD. WorkflowBuilder only for multi-step operations.

**Why:** WorkflowBuilder for simple CRUD is ~23x slower due to graph construction, validation, and runtime overhead that adds zero value for single-record operations.

```python
result = await db.express.create("User", {"name": "Alice", "email": "alice@example.com"})
user = await db.express.read("User", result["id"])  # accepts both str and int IDs
users = await db.express.list("User", {"active": True})
await db.express.update("User", result["id"], {"name": "Bob"})
await db.express.delete("User", result["id"])

# ❌ Don't use WorkflowBuilder for simple CRUD — 23x slower
```

## DataFlow Models & Workflows

```python
@db.model
class User:
    id: int = field(primary_key=True)  # PK MUST be named 'id'
    # Never manually set timestamps — auto-managed

# CreateNode: FLAT params (not nested)
workflow.add_node("CreateUser", "create", {"name": "test"})
# ❌ {"data": {"name": "test"}}

# UpdateNode: filter + fields
workflow.add_node("UpdateUser", "update", {"filter": {"id": 1}, "fields": {"name": "new"}})
```

## Nexus

```python
app = Nexus()
app.register(my_workflow)  # Register first
app.start()                # Then start
session = app.create_session()  # Unified session for state across channels
```

## Kaizen

```python
# Delegate (recommended for autonomous agents)
from kaizen_agents import Delegate
delegate = Delegate(model=os.environ["OPENAI_PROD_MODEL"])

# BaseAgent (for custom logic only)
from kaizen.core import BaseAgent, Signature, InputField, OutputField
```

## Async vs Sync Runtime

- **Docker/Nexus**: `AsyncLocalRuntime` + `await runtime.execute_workflow_async(workflow.build())`
- **CLI/Scripts**: `LocalRuntime` + `runtime.execute(workflow.build())`

## SQLite Connection Management

- Acquire through `AsyncSQLitePool` (`acquire_read` / `acquire_write`)
- URI shared-cache for `:memory:` (`file:memdb_NAME?mode=memory&cache=shared`)
- `async with` for all transactions
- Default PRAGMAs on every connection (WAL, busy_timeout, synchronous, cache_size, foreign_keys)
- Always set `max_read_connections` (bounded concurrency)
- MUST NOT use bare `aiosqlite.connect()` — go through the pool

**Why:** Bare `aiosqlite.connect()` bypasses WAL mode, busy_timeout, and connection limits, causing "database is locked" errors under concurrent access.

## Async Resource Cleanup

- All async resource classes MUST implement `__del__` with `ResourceWarning`
- Use `def __del__(self, _warnings=warnings)` signature (survives interpreter shutdown)
- Set class-level defaults for `__del__` safety
- MUST NOT use `asyncio` in `__del__` — async cleanup in finalizers is unreliable
- MUST NOT call `close()` / `cleanup()` / any method that might emit a log line from `__del__` — emit `ResourceWarning` and return. Real cleanup is the caller's responsibility via `with` / `await obj.close_async()`.

**Why:** Without `__del__` warnings, leaked connections and file handles go undetected until resource exhaustion crashes the process in production. Calling `close()` from `__del__` on an async resource is worse than leaking: the finalizer fires from inside Python's logging machinery during GC, `close()` spawns a new event loop whose selector init calls `logger.debug()`, and that acquires the root logging lock already held by the finalizer thread — deadlocking the process.

```python
# DO — emit warning, do nothing else
def __del__(self, _warnings=warnings):
    if not self._closed:
        _warnings.warn(
            f"{type(self).__name__} not closed; call await obj.close_async()",
            ResourceWarning,
            stacklevel=2,
        )

# DO NOT — async cleanup routed through logging-touching paths
def __del__(self):
    if not self._closed:
        async_safe_run(self.close())  # deadlocks when __del__ fires from logging GC
```

**BLOCKED rationalizations:**

- "We just need to close the connection to prevent leaks"
- "The resource warning is too noisy; let's just clean up silently"
- "async_safe_run handles the event loop correctly"
- "It only deadlocks sometimes, and only in tests"

**Why:** Every one of these has been argued before and reintroduced the deadlock. The deadlock is non-deterministic — it fires only when GC happens to finalize the resource while the logging root lock is held, which happens most often under test load. "It works in dev" is exactly the path to a production incident.

Origin: kailash-py commit `4f5dbe7f` (2026-04-16) and prior "DataFlow unit suite hangs" reports across multiple sessions. `DataFlow.__del__` called `self.close()` → `async_safe_run()` → `asyncio.new_event_loop()` → selector init → `logger.debug()` → deadlock on root logging lock held by GC finalizer.
