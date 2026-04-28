---
priority: 10
scope: path-scoped
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

## Paired Public Surface — Consistent Async-ness (MUST)

When two top-level functions form a canonical user pipeline — pairs like `train`/`register`, `fit`/`predict`, `encrypt`/`decrypt`, `publish`/`subscribe`, `login`/`logout` — BOTH MUST be either async OR sync. Mixing (one `async def`, one sync-wrapping-`asyncio.run()`) is BLOCKED. Agents, Nexus handlers, pytest-asyncio tests, and Jupyter kernels all run inside an active event loop; a sync function that internally calls `asyncio.run()` raises `RuntimeError: This event loop is already running` in every async caller.

```python
# DO — both async, composable under any event-loop context
# kailash_ml/__init__.py
async def train(df, target): ...
async def register(result, *, name): ...

# User code inside pytest-asyncio / Nexus handler / Jupyter:
result = await km.train(df, target="y")
registered = await km.register(result, name="demo")  # works in any event loop

# DO NOT — async train + sync register that wraps asyncio.run()
async def train(df, target): ...
def register(result, *, name):   # sync surface hiding asyncio.run()
    return asyncio.run(_register_impl(result, name))  # RuntimeError in async callers

# In pytest-asyncio:
result = await km.train(df, target="y")
km.register(result, name="demo")  # RuntimeError: This event loop is already running
```

**BLOCKED rationalizations:**

- "Notebook users want sync; agent users want async; we'll offer both shapes"
- "`asyncio.run()` handles the wrapping transparently"
- "A sync wrapper is a convenience, users can opt out by awaiting directly"
- "The async caller is a rare case, the sync path covers 95%"
- "We'll document the async requirement in the docstring"

**Why:** `asyncio.run()` creates a new event loop and raises if one is already running. Every modern Python async context — `pytest.mark.asyncio`, Nexus's FastAPI handlers, Jupyter's IPKernel, any Kaizen agent loop — has a running loop. A sync-wrapping-`asyncio.run()` surface works only in pure-CLI contexts and crashes everywhere else with an opaque `RuntimeError`. The "both shapes" trap (offering `km.register` sync AND `km.register_async`) doubles the public API surface, forces every caller to remember which variant their context permits, and ships two implementations of the same primitive that drift. Canonical pairs MUST pick one async-ness and commit. Evidence: kailash-ml 1.0.0 W33/W33c — `km.train` was async (W33), `km.register` landed sync (W33c) with internal `asyncio.run()`; the canonical 3-line Quick Start `result = await km.train(...); registered = km.register(result, ...)` crashed in every async context. Fix commit `fdd3040e` converted `km.register` to `async def`, matching `km.train`.

Origin: kailash-ml-audit session 2026-04-23 — W33c async/sync inconsistency caught by end-to-end README regression test.

## Callable Module + Subpackage Coexistence (MUST — PEP 562)

When a package exports BOTH a top-level callable (`pkg.foo` imported from `_wrappers` or similar) AND contains a subpackage of the same name (`pkg/foo/`), Python's import machinery unconditionally sets `pkg.foo` to the subpackage module the moment ANYTHING runs `from pkg.foo import <X>` — silently shadowing the callable. In test-collection order, this surfaces as `AssertionError: pkg.foo MUST be callable (got module)` after an unrelated test imports the subpackage.

The subpackage's `__init__.py` MUST install a PEP 562 callable-module subclass so both surfaces coexist: `from pkg.foo import Klass` resolves the subpackage; `pkg.foo(...)` still invokes the wrapper callable.

```python
# DO — subpackage __init__.py installs _CallableModule so pkg.foo remains callable
# kailash_ml/dashboard/__init__.py
import sys
from types import ModuleType
from kailash_ml._wrappers.dashboard import dashboard as _dashboard_callable

class _CallableDashboardModule(ModuleType):
    def __call__(self, *args, **kwargs):
        return _dashboard_callable(*args, **kwargs)

sys.modules[__name__].__class__ = _CallableDashboardModule

# DO NOT — subpackage ships without PEP 562 install; shadow the callable silently
# kailash_ml/dashboard/__init__.py
from .views import DashboardView   # first `from pkg.dashboard import …` runs this file
# sys.modules["kailash_ml"].dashboard is now this module; km.dashboard(...) → TypeError
```

**BLOCKED rationalizations:**

- "Users will always import from one place"
- "Test order is stable"
- "We can rename one of the surfaces later"
- "The `_wrappers` callable is the canonical form; the subpackage is niche"

**Why:** Python binds `pkg.foo` to whichever object was most recently assigned to `sys.modules["pkg"].foo`; the subpackage's `__init__.py` executing is enough to replace the wrapper callable. Test collection order is NOT stable across Python versions (3.13 → 3.14 re-ordered `pytest` discovery) and unrelated modules importing the subpackage counts as a trigger. PEP 562 `__class__` assignment on the subpackage's own module object is the single structural defense — both surfaces coexist without special-casing callers.

Origin: kailash-ml 1.1.0 release cycle (2026-04-23) — `km.dashboard` shadowed by `kailash_ml/dashboard/` subpackage after Python 3.14 test-collection reordering; fix commit `8914de3b` installed `_CallableDashboardModule`.

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
