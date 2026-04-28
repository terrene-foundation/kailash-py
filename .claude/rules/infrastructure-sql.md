---
priority: 10
scope: path-scoped
paths:
  - "**/db/**"
  - "**/infrastructure/**"
---

# Infrastructure SQL Rules


<!-- slot:neutral-body -->

> **Scope**: Application code MUST go through DataFlow (`@db.model`, `db.express`) — see `framework-first.md` § Work-Domain Binding. The patterns here are for the SDK source tree and dialect helper layer where DataFlow itself generates SQL underneath. Application code never writes these patterns directly.

### 1. Validate SQL Identifiers with `_validate_identifier()`

```python
# DO:
from kailash.db.dialect import _validate_identifier
_validate_identifier(table_name)
await conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", record_id)

# DO NOT:
await conn.execute(f"SELECT * FROM {user_input} WHERE id = ?", record_id)
```

**Why:** Regex `^[a-zA-Z_][a-zA-Z0-9_]*$` prevents all SQL injection via identifiers.

### 2. Use Transactions for Multi-Statement Operations

```python
# DO:
async with conn.transaction() as tx:
    row = await tx.fetchone("SELECT MAX(seq) FROM events WHERE stream = ?", stream)
    await tx.execute("INSERT INTO events (stream, seq, data) VALUES (?, ?, ?)", ...)

# DO NOT (auto-commit releases locks between statements — race conditions):
row = await conn.fetchone(...)
await conn.execute(...)
```

**Why:** Without a transaction, another connection can modify rows between your SELECT and INSERT, causing duplicate sequences, lost updates, or constraint violations.

### 3. Use `?` Canonical Placeholders

`translate_query()` converts to `$1` (PostgreSQL), `%s` (MySQL), or `?` (SQLite) automatically.

```python
# DO:
await conn.execute("INSERT INTO tasks VALUES (?, ?)", task_id, status)

# DO NOT:
await conn.execute("INSERT INTO tasks VALUES ($1, $2)", task_id, status)
```

**Why:** Hardcoded dialect-specific placeholders silently break when switching databases — `$1` syntax causes a parse error on SQLite and MySQL.

### 4. Use `dialect.blob_type()` Not Hardcoded BLOB

```python
# DO:
blob_type = conn.dialect.blob_type()
await conn.execute(f"CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data {blob_type})")

# DO NOT (PostgreSQL uses BYTEA, not BLOB):
await conn.execute("... data BLOB)")
```

**Why:** PostgreSQL rejects `BLOB` (it uses `BYTEA`), so hardcoded type names cause DDL failures that only surface when switching from SQLite to production.

### 5. Use `dialect.upsert()` Not Check-Then-Act

```python
# DO:
sql, param_cols = conn.dialect.upsert("checkpoints", ["run_id", "node_id", "data"], ["run_id", "node_id"])

# DO NOT (TOCTOU race between SELECT and INSERT):
row = await conn.fetchone("SELECT * FROM checkpoints WHERE run_id = ?", run_id)
if row: ...update... else: ...insert...
```

**Why:** Check-then-act has a TOCTOU race — two concurrent requests can both see "not found" and both INSERT, causing a duplicate key error or data loss.

### 6. Validate Table Names in Constructors

```python
# DO:
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
def __init__(self, conn, table_name="kailash_task_queue"):
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(f"Invalid table name: must match [a-zA-Z_][a-zA-Z0-9_]*")
```

**Why:** Table names cannot be parameterized in SQL, so constructor-time validation is the only defense against SQL injection through dynamic table names.

### 7. Bound In-Memory Stores

```python
# DO (max size with LRU eviction):
while len(self._store) >= self._max_entries:
    self._store.popitem(last=False)  # Evict oldest

# DO NOT:
self._store: dict = {}  # Grows without bound -> OOM
```

**Why:** An unbounded in-memory store in a long-running server process grows until OOM kills the process, taking down all active connections.

Default bound: 10,000 entries.

### 8. Adapter Classes MUST Import Drivers Lazily

Every adapter class wrapping an optional backend driver (`motor`, `pymongo`, `aiomysql`, `asyncpg`, `aiosqlite`, `aiokafka`, `redis.asyncio`, etc.) MUST import the driver **inside** `connect()` / `__aenter__` and raise a descriptive `ImportError` at the call site if missing. Top-level `from <driver> import ...` on the adapter module is BLOCKED.

```python
# DO
class MongoDBAdapter(BaseAdapter):
    async def connect(self) -> None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:
            raise ImportError(
                "MongoDB support requires motor. pip install motor pymongo"
            ) from exc
        self._client = AsyncIOMotorClient(self._url)

# DO NOT — top-level import kills every consumer
from motor.motor_asyncio import AsyncIOMotorClient  # breaks `from dataflow import DataFlow`
```

**BLOCKED rationalizations:** "motor is in our main deps anyway"; "the driver is small"; "users who don't want MongoDB will install kailash[sql-only]".

**Why:** A top-level `from motor...` executes on `from dataflow import DataFlow` even for PostgreSQL-only projects. When the driver is absent the package fails to import at all — users see cryptic errors from modules they never intended to use. Lazy imports turn that into actionable errors at `connect()` time.

### 8a. Lazy-Import Regression Test Required

Every lazy-driver adapter MUST have a regression test that asserts the top-level package import succeeds with the driver absent. Static grep alone is BLOCKED — a future "tidy up imports" refactor silently reintroduces the bug.

```python
# DO
def test_dataflow_importable_without_motor(monkeypatch):
    import sys
    class _Block:
        def find_module(self, name, path=None):
            return self if name.startswith("motor") else None
        def load_module(self, name):
            raise ImportError(f"simulated: {name} not installed")
    monkeypatch.setattr(sys, "meta_path", [_Block(), *sys.meta_path])
    for mod in [m for m in sys.modules if m.startswith(("dataflow", "motor"))]:
        sys.modules.pop(mod, None)
    from dataflow import DataFlow
    assert DataFlow is not None
```

**Why:** Without a behavioral test the pattern is only human-enforced. The MongoDB adapter regression that motivated this rule had passed code review — the lazy pattern only surfaced when a downstream Docker build died on missing motor.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-11) — `packages/kailash-dataflow/src/dataflow/adapters/mongodb.py` imported `motor.motor_asyncio` at module top, breaking `from dataflow import DataFlow` for every non-MongoDB project.

## MUST NOT

- **No `AUTOINCREMENT`** in shared DDL — use `INTEGER PRIMARY KEY` (works on SQLite, PostgreSQL, MySQL)
  **Why:** `AUTOINCREMENT` is SQLite-specific syntax that fails on PostgreSQL and MySQL, breaking dialect portability.
- **No separate ConnectionManagers per store** — use `StoreFactory.get_default()`, all stores share one pool
  **Why:** Each ConnectionManager creates its own pool, so N stores means N pools competing for the same `max_connections` limit — pool math breaks silently.
- **No `FOR UPDATE SKIP LOCKED` without transaction** — lock releases on auto-commit, causing race conditions
  **Why:** Without a transaction, the row lock acquired by `FOR UPDATE` releases immediately on auto-commit, and another worker grabs the same row.

<!-- /slot:neutral-body -->
