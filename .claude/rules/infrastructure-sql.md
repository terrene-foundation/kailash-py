---
paths:
  - "**/db/**"
  - "**/infrastructure/**"
---

# Infrastructure SQL Rules

### 1. Validate SQL Identifiers with `_validate_identifier()`

```python
# DO:
from kailash.db.dialect import _validate_identifier
_validate_identifier(table_name)
await conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", record_id)

# DO NOT:
await conn.execute(f"SELECT * FROM {user_input} WHERE id = ?", record_id)
```

**Why**: Regex `^[a-zA-Z_][a-zA-Z0-9_]*$` prevents all SQL injection via identifiers.

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

### 3. Use `?` Canonical Placeholders

`translate_query()` converts to `$1` (PostgreSQL), `%s` (MySQL), or `?` (SQLite) automatically.

```python
# DO:
await conn.execute("INSERT INTO tasks VALUES (?, ?)", task_id, status)

# DO NOT:
await conn.execute("INSERT INTO tasks VALUES ($1, $2)", task_id, status)
```

### 4. Use `dialect.blob_type()` Not Hardcoded BLOB

```python
# DO:
blob_type = conn.dialect.blob_type()
await conn.execute(f"CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data {blob_type})")

# DO NOT (PostgreSQL uses BYTEA, not BLOB):
await conn.execute("... data BLOB)")
```

### 5. Use `dialect.upsert()` Not Check-Then-Act

```python
# DO:
sql, param_cols = conn.dialect.upsert("checkpoints", ["run_id", "node_id", "data"], ["run_id", "node_id"])

# DO NOT (TOCTOU race between SELECT and INSERT):
row = await conn.fetchone("SELECT * FROM checkpoints WHERE run_id = ?", run_id)
if row: ...update... else: ...insert...
```

### 6. Validate Table Names in Constructors

```python
# DO:
_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
def __init__(self, conn, table_name="kailash_task_queue"):
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(f"Invalid table name: must match [a-zA-Z_][a-zA-Z0-9_]*")
```

### 7. Bound In-Memory Stores

```python
# DO (max size with LRU eviction):
while len(self._store) >= self._max_entries:
    self._store.popitem(last=False)  # Evict oldest

# DO NOT:
self._store: dict = {}  # Grows without bound -> OOM
```

Default bound: 10,000 entries.

### 8. Lazy Driver Imports

`aiosqlite`, `asyncpg`, `aiomysql` are in base `pip install kailash`. Lazy imports remain acceptable for consistency.

## MUST NOT

- **No `AUTOINCREMENT`** in shared DDL — use `INTEGER PRIMARY KEY` (works on SQLite, PostgreSQL, MySQL)
- **No separate ConnectionManagers per store** — use `StoreFactory.get_default()`, all stores share one pool
- **No `FOR UPDATE SKIP LOCKED` without transaction** — lock releases on auto-commit, causing race conditions
