---
name: async-resource-safety
description: "Patterns for __del__ hardening, double-check locking, pool lifecycle, and static analysis guardrails. Use when implementing classes that manage async resources (connections, pools, file handles)."
---

# Async Resource Safety Patterns

Patterns for classes that manage async resources (connections, pools, file handles) and must survive interpreter shutdown, GC collection, and concurrent access.

## 1. `__del__` Hardening

Python's `__del__` runs during GC — the interpreter may be partially shut down. Three rules:

### Rule 1: Bind module references at class definition time

```python
import warnings

class MyTransaction:
    def __del__(self, _warnings=warnings):
        # _warnings is bound at definition time, survives interpreter shutdown
        if not self._committed and not self._rolled_back:
            _warnings.warn(
                f"Transaction was not committed or rolled back. "
                f"Created at:\n{''.join(traceback.format_list(self._source_traceback))}",
                ResourceWarning,
                stacklevel=1,
            )
```

### Rule 2: Class-level default attributes

If `__init__` raises partway through, `__del__` still runs. Guard with defaults:

```python
class MyTransaction:
    # Safety net — __del__ can always read these even if __init__ failed
    _committed = False
    _rolled_back = False
    connection = None

    def __init__(self, conn):
        self.connection = conn
        self._source_traceback = traceback.extract_stack()

    def __del__(self, _warnings=warnings):
        if self.connection is not None and not self._committed:
            _warnings.warn("Leaked transaction", ResourceWarning, stacklevel=1)
```

### Rule 3: Never use asyncio in `__del__`

```python
# NEVER — event loop may be closed or absent
def __del__(self):
    asyncio.get_event_loop().run_until_complete(self.close())  # BROKEN

# CORRECT — emit warning only, let pool/context manager handle cleanup
def __del__(self, _warnings=warnings):
    if not self._closed:
        _warnings.warn("Resource not closed", ResourceWarning, stacklevel=1)
```

### Where this applies in Kailash

| Location                                                               | Class                         | Pattern                                                                    |
| ---------------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------------- |
| `packages/kailash-dataflow/src/dataflow/adapters/sqlite_enterprise.py` | `SQLiteEnterpriseTransaction` | `_warnings=warnings`, class-level `_committed`                             |
| `packages/kailash-dataflow/src/dataflow/adapters/postgresql.py`        | `PostgreSQLTransaction`       | Same pattern                                                               |
| `packages/kailash-dataflow/src/dataflow/adapters/mysql.py`             | `MySQLTransaction`            | Same pattern                                                               |
| `src/kailash/nodes/data/async_sql.py`                                  | `AsyncSQLDatabaseNode`        | Same pattern (node, not transaction — `__del__` guards connection cleanup) |

## 2. Double-Check Locking for asyncio

For lazy initialization of shared async resources (connections, pools), use double-check locking to avoid redundant lock contention:

```python
import asyncio

class ResourceManager:
    def __init__(self):
        self._connection = None
        self._conn_lock = asyncio.Lock()
        self._closed = False

    async def _get_connection(self):
        # Fast path — no lock needed if already initialized
        if self._connection is not None:
            if self._closed:
                raise RuntimeError("ResourceManager is closed")
            return self._connection

        async with self._conn_lock:
            # Re-check inside lock — another task may have initialized
            if self._connection is not None:
                if self._closed:
                    raise RuntimeError("ResourceManager is closed")
                return self._connection

            if self._closed:
                raise RuntimeError("ResourceManager is closed")

            self._connection = await self._create_connection()
            return self._connection
```

Key invariants:

- **Fast path** outside lock for the common case (already initialized)
- **Re-check** inside lock to prevent double initialization
- **`_closed` guard** at both levels to prevent use-after-close races

### Where this applies in Kailash

| Location                                                        | Class                              |
| --------------------------------------------------------------- | ---------------------------------- |
| `packages/kailash-kaizen/src/kaizen/memory/persistent_tiers.py` | `WarmMemoryTier._get_connection()` |
| `packages/kailash-kaizen/src/kaizen/memory/persistent_tiers.py` | `ColdMemoryTier._get_connection()` |

## 3. Pool Closed-State Guards

When a pool uses async primitives (semaphores, locks), acquisition can block. After waking up, re-check the pool's closed state:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def acquire_read(self):
    if self._closed:
        raise PoolExhaustedError("Pool is closed")

    await self._read_semaphore.acquire()
    try:
        # Re-check after potentially blocking on semaphore
        if self._closed:
            raise PoolExhaustedError("Pool closed while waiting")
        conn = await self._get_or_create_reader()
        yield conn
    finally:
        self._read_semaphore.release()

@asynccontextmanager
async def acquire_write(self):
    if self._closed:
        raise PoolExhaustedError("Pool is closed")

    await self._write_lock.acquire()
    try:
        # Re-check after potentially blocking on lock
        if self._closed:
            raise PoolExhaustedError("Pool closed while waiting")
        yield self._writer
    finally:
        self._write_lock.release()
```

### Where this applies in Kailash

| Location                               | Class                                               |
| -------------------------------------- | --------------------------------------------------- |
| `src/kailash/core/pool/sqlite_pool.py` | `AsyncSQLitePool.acquire_read()`, `acquire_write()` |

## 4. Memory Database URI Detection

SQLite `:memory:` databases can also use URI format. Detection must handle both:

```python
def _is_memory_db(db_path: str) -> bool:
    return db_path == ":memory:" or "mode=memory" in db_path
```

This must be consistent across all locations that check for memory databases:

- Pool configuration
- Connection factory (skip PRAGMAs like `journal_mode` for memory DBs)
- Adapter initialization
- Test utilities

URI shared-cache pattern for memory DBs that need multiple connections:

```python
# WRONG — each connect() creates a separate database
conn1 = await aiosqlite.connect(":memory:")
conn2 = await aiosqlite.connect(":memory:")  # Can't see conn1's tables

# CORRECT — shared database via URI
uri = "file:mydb?mode=memory&cache=shared"
conn1 = await aiosqlite.connect(uri, uri=True)
conn2 = await aiosqlite.connect(uri, uri=True)  # Same database
```

## 5. Static Analysis Guardrail Tests

Regex-based tests that scan source files for banned patterns. Useful for enforcing architectural boundaries:

```python
import re
from pathlib import Path

class TestNoDirectAiosqliteConnect:
    """Ensure all SQLite connections go through the pool."""

    _BANNED = re.compile(r"aiosqlite\.connect\(")
    _ALLOWED_FILES = {"sqlite_pool.py", "connection_factory.py"}  # Pool internals

    def test_no_bare_aiosqlite_connect(self):
        violations = []
        for py in Path("src/kailash/nodes/data").rglob("*.py"):
            if py.name in self._ALLOWED_FILES:
                continue
            text = py.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                if self._BANNED.search(line) and not line.lstrip().startswith("#"):
                    violations.append(f"{py.name}:{i}: {line.strip()}")

        assert not violations, (
            f"Found {len(violations)} bare aiosqlite.connect() call(s) — "
            f"use AsyncSQLitePool instead:\n" + "\n".join(violations)
        )
```

### When to use this pattern

- Enforcing pool usage (no direct `aiosqlite.connect()`)
- Preventing relative imports (`from ..` patterns)
- Blocking hardcoded secrets (`api_key = "sk-"` patterns)
- Ensuring parameterized queries (no f-string SQL)

### Where this applies in Kailash

| Location                               | Test                           |
| -------------------------------------- | ------------------------------ |
| `tests/unit/test_sqlite_invariants.py` | `TestNoDirectAiosqliteConnect` |

## 6. Transaction Bypass in Adapters

When an adapter uses a connection pool but also supports explicit transactions, the transaction's connection must take precedence:

```python
async def execute(self, query, params=None, *, transaction=None):
    if transaction is not None:
        # Delegate to base class — uses transaction's own connection
        return await super().execute(query, params, transaction=transaction)

    # Normal path — use pool
    async with self._pool.acquire(query) as conn:
        return await conn.execute(query, params)
```

Without this bypass, the pool would hand out a different connection than the transaction's, breaking ACID guarantees.

## Anti-Patterns Summary

| Anti-Pattern                          | Correct Pattern                       | Risk                                 |
| ------------------------------------- | ------------------------------------- | ------------------------------------ |
| `asyncio.run()` in `__del__`          | `warnings.warn()` only                | Crashes during shutdown              |
| No class-level defaults               | `_committed = False` at class level   | `AttributeError` if `__init__` fails |
| `warnings` used directly in `__del__` | `_warnings=warnings` parameter        | `None` during shutdown               |
| Single check before async wait        | Double-check after lock/semaphore     | Use-after-close race                 |
| `db_path == ":memory:"` only          | Also check `"mode=memory" in db_path` | URI memory DBs missed                |
| No guardrail tests                    | Regex scan for banned patterns        | Architectural drift                  |

## Related Skills

- **[dataflow-sqlite-concurrency](../02-dataflow/dataflow-sqlite-concurrency.md)** — SQLite-specific pool config, acquisition, query routing, memory mode
- **[dataflow-gotchas](../02-dataflow/dataflow-gotchas.md)** — DataFlow common pitfalls including URI shared-cache
