# Infrastructure SQL Rules

## Scope

These rules apply when editing files in:

- `src/kailash/db/**`
- `src/kailash/infrastructure/**`

## MUST Rules

### 1. Validate SQL Identifiers with `_validate_identifier()`

Every method that interpolates a table or column name into SQL MUST validate it first.

```python
# DO:
from kailash.db.dialect import _validate_identifier
_validate_identifier(table_name)
await conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", record_id)

# DO NOT:
await conn.execute(f"SELECT * FROM {user_input} WHERE id = ?", record_id)
```

**Why**: Unvalidated identifiers enable SQL injection. The regex `^[a-zA-Z_][a-zA-Z0-9_]*$` prevents all injection vectors.

**Enforced by**: Red team finding C6 — all public methods in dialect.py, task_queue.py, and worker_registry.py validate identifiers.

### 2. Use Transactions for Multi-Statement Operations

Any operation involving more than one SQL statement that must be atomic MUST use `conn.transaction()`.

```python
# DO:
async with conn.transaction() as tx:
    row = await tx.fetchone("SELECT MAX(seq) FROM events WHERE stream = ?", stream)
    await tx.execute("INSERT INTO events (stream, seq, data) VALUES (?, ?, ?)", ...)

# DO NOT:
row = await conn.fetchone("SELECT MAX(seq) FROM events WHERE stream = ?", stream)
await conn.execute("INSERT INTO events (stream, seq, data) VALUES (?, ?, ?)", ...)
```

**Why**: Without a transaction, auto-commit releases locks between statements. This causes race conditions (C2, C3, C4 in red team report): event store sequence races, idempotency TOCTOU, task queue lock release.

### 3. Use `?` Canonical Placeholders

All SQL in infrastructure code MUST use `?` as the parameter placeholder. ConnectionManager translates to dialect-specific format automatically.

```python
# DO:
await conn.execute("INSERT INTO tasks VALUES (?, ?)", task_id, status)

# DO NOT:
await conn.execute("INSERT INTO tasks VALUES ($1, $2)", task_id, status)
await conn.execute("INSERT INTO tasks VALUES (%s, %s)", task_id, status)
```

**Why**: `?` is the canonical placeholder. `translate_query()` converts to `$1` (PostgreSQL), `%s` (MySQL), or `?` (SQLite) automatically.

### 4. Use `dialect.blob_type()` Not Hardcoded BLOB

DDL that includes binary columns MUST use `dialect.blob_type()`.

```python
# DO:
blob_type = conn.dialect.blob_type()
await conn.execute(f"CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data {blob_type})")

# DO NOT:
await conn.execute("CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data BLOB)")
```

**Why**: PostgreSQL uses `BYTEA`, not `BLOB`. Hardcoded `BLOB` fails on PostgreSQL (H2 in red team report).

### 5. Use `dialect.upsert()` Not Check-Then-Act

Any "insert or update" operation MUST use `dialect.upsert()` or `dialect.insert_ignore()`.

```python
# DO:
sql, param_cols = conn.dialect.upsert(
    "checkpoints", ["run_id", "node_id", "data", "updated_at"],
    ["run_id", "node_id"]
)

# DO NOT:
row = await conn.fetchone("SELECT * FROM checkpoints WHERE run_id = ?", run_id)
if row:
    await conn.execute("UPDATE checkpoints SET data = ? WHERE run_id = ?", data, run_id)
else:
    await conn.execute("INSERT INTO checkpoints VALUES (?, ?)", run_id, data)
```

**Why**: Check-then-act is a TOCTOU race. Between the SELECT and INSERT, another process can insert the same row (M1 in red team report).

### 6. Validate Table Names in Constructors

Store classes that accept a configurable table name MUST validate it in `__init__`.

```python
# DO:
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def __init__(self, conn, table_name="kailash_task_queue"):
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(f"Invalid table name '{table_name}': must match [a-zA-Z_][a-zA-Z0-9_]*")
    self._table = table_name

# DO NOT:
def __init__(self, conn, table_name="kailash_task_queue"):
    self._table = table_name  # No validation!
```

**Why**: Constructor-time validation prevents injection before any SQL is ever generated (C6+ fix in convergence report).

### 7. Bound In-Memory Stores

In-memory stores (dicts, OrderedDicts) MUST have a maximum size with LRU eviction.

```python
# DO:
from collections import OrderedDict

_MAX_ENTRIES = 10000

class InMemoryExecutionStore:
    def __init__(self, max_entries=_MAX_ENTRIES):
        self._store: OrderedDict[str, Dict] = OrderedDict()
        self._max_entries = max_entries

    async def record_start(self, run_id, ...):
        while len(self._store) >= self._max_entries:
            self._store.popitem(last=False)  # Evict oldest
        self._store[run_id] = {...}

# DO NOT:
class InMemoryExecutionStore:
    def __init__(self):
        self._store: dict = {}  # Grows without bound -> OOM
```

**Why**: Unbounded collections in long-running processes lead to memory exhaustion (H1 in red team report). Default bound: 10,000 entries.

### 8. Lazy Driver Imports

Database driver packages (`aiosqlite`, `asyncpg`, `aiomysql`) MUST be imported inside the method that uses them, not at module top level.

```python
# DO:
async def _init_postgres(self):
    try:
        import asyncpg
    except ImportError as exc:
        raise ImportError(
            "asyncpg is required for PostgreSQL connections. "
            "Install it with: pip install kailash[postgres]"
        ) from exc
    self._pool = await asyncpg.create_pool(self.url)

# DO NOT:
import asyncpg  # Module-level import -- fails at import time if not installed
```

**Why**: `pip install kailash` (without extras) must work at Level 0. Lazy imports ensure optional drivers are only required when actually used.

## MUST NOT Rules

### 1. No `AUTOINCREMENT` in Shared DDL

MUST NOT use `AUTOINCREMENT` in table definitions that must work across databases.

```python
# DO:
"CREATE TABLE events (id INTEGER PRIMARY KEY, ...)"
# INTEGER PRIMARY KEY auto-increments natively on SQLite, PostgreSQL, and MySQL

# DO NOT:
"CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ...)"
# AUTOINCREMENT is SQLite-specific and fails on PostgreSQL/MySQL
```

**Why**: `AUTOINCREMENT` is a SQLite keyword. PostgreSQL uses `SERIAL` or `GENERATED`, MySQL uses `AUTO_INCREMENT`. `INTEGER PRIMARY KEY` auto-increments natively on all three databases (C5 in red team report).

### 2. No Separate ConnectionManagers Per Store

MUST NOT create a new `ConnectionManager` for each store instance.

```python
# DO:
factory = StoreFactory.get_default()
await factory.initialize()
# All stores share factory._conn internally

# DO NOT:
conn1 = ConnectionManager("postgresql://...")
conn2 = ConnectionManager("postgresql://...")
event_store = DBEventStoreBackend(conn1)
exec_store = DBExecutionStore(conn2)
```

**Why**: Each ConnectionManager creates its own connection pool. Multiple pools to the same database waste connections and prevent transaction isolation across stores.

### 3. No `FOR UPDATE SKIP LOCKED` Without a Transaction

MUST NOT use `FOR UPDATE SKIP LOCKED` outside of an explicit transaction.

```python
# DO:
async with conn.transaction() as tx:
    row = await tx.fetchone(
        "SELECT task_id FROM tasks WHERE status = 'pending' "
        "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
        ...
    )
    await tx.execute("UPDATE tasks SET status = 'processing' WHERE task_id = ?", ...)

# DO NOT:
row = await conn.fetchone(
    "SELECT task_id FROM tasks WHERE status = 'pending' "
    "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
)
# Lock is released immediately on auto-commit! Another worker can claim the same row.
await conn.execute("UPDATE tasks SET status = 'processing' WHERE task_id = ?", ...)
```

**Why**: `FOR UPDATE SKIP LOCKED` acquires a row-level lock. In auto-commit mode, the lock is released as soon as the SELECT completes. The subsequent UPDATE then races with other workers (C4 in red team report).

## Cross-References

- `src/kailash/db/dialect.py` — QueryDialect, `_validate_identifier()`, `_validate_json_path()`
- `src/kailash/db/connection.py` — ConnectionManager, `_TransactionProxy`
- `src/kailash/infrastructure/factory.py` — StoreFactory singleton
- `workspaces/enterprise-infrastructure/04-validate/01-redteam-report.md` — Red team findings (C1-C8, H1-H7)
- `workspaces/enterprise-infrastructure/04-validate/02-convergence-round1.md` — All fixes verified
- `.claude/rules/security.md` — Global security rules (parameterized queries, no secrets)
