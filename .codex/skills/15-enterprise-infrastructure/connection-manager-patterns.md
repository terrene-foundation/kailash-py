# Connection Manager Patterns

You are an expert in the Kailash ConnectionManager for async database access. Guide users through connection lifecycle, transaction context managers, driver-specific behavior differences, and pool configuration.

> For full implementation details, see `docs/enterprise-infrastructure/02-store-backends.md` and the source at the ConnectionManager module.

## ConnectionManager Lifecycle

The `ConnectionManager` wraps database-specific async drivers behind a uniform interface with dialect-aware placeholder translation.

### Initialization

```python
from kailash.db.connection import ConnectionManager

# From a database URL (auto-detects dialect)
conn = ConnectionManager("postgresql://user:pass@localhost/kailash")
await conn.initialize()  # Creates the connection pool

# SQLite
conn = ConnectionManager("sqlite:///app.db")
await conn.initialize()  # Opens WAL-mode connection with foreign keys enabled

# In-memory SQLite
conn = ConnectionManager("sqlite:///:memory:")
await conn.initialize()
```

### Query Execution

All queries use `?` canonical placeholders -- the ConnectionManager translates automatically:

```python
# Execute (INSERT, UPDATE, DELETE)
await conn.execute(
    "INSERT INTO tasks (id, status) VALUES (?, ?)",
    "task-1", "pending"
)

# Fetch all rows as list of dicts
rows = await conn.fetch(
    "SELECT * FROM tasks WHERE status = ?",
    "pending"
)
# [{"id": "task-1", "status": "pending"}, ...]

# Fetch single row as dict (or None)
row = await conn.fetchone(
    "SELECT * FROM tasks WHERE id = ?",
    "task-1"
)
# {"id": "task-1", "status": "pending"} or None
```

### Cleanup

```python
await conn.close()  # Closes pool, releases resources
# Safe to call multiple times
```

### Properties

```python
conn.url          # The original database URL string
conn.dialect      # The QueryDialect instance (PostgresDialect, MySQLDialect, SQLiteDialect)
conn.dialect.database_type  # DatabaseType enum (.POSTGRESQL, .MYSQL, .SQLITE)
```

## Transaction Context Manager

The `transaction()` method provides an async context manager for multi-statement atomic operations. On normal exit, the transaction commits. On exception, it rolls back.

```python
async with conn.transaction() as tx:
    # All operations within this block are atomic
    await tx.execute("INSERT INTO events (id, data) VALUES (?, ?)", evt_id, data)
    row = await tx.fetchone("SELECT MAX(seq) as max_seq FROM events WHERE stream = ?", stream)
    await tx.execute("UPDATE counters SET value = ? WHERE key = ?", new_val, "seq")
    # Commits automatically on successful exit

# If any statement raises, the entire transaction is rolled back
```

### TransactionProxy API

The `tx` object yielded by `transaction()` is a `_TransactionProxy` with the same interface as ConnectionManager:

| Method                      | Purpose                             |
| --------------------------- | ----------------------------------- |
| `tx.execute(query, *args)`  | Execute within transaction          |
| `tx.fetch(query, *args)`    | Fetch all rows within transaction   |
| `tx.fetchone(query, *args)` | Fetch single row within transaction |

All methods perform dialect placeholder translation.

### Why Transactions Are Required

The red team validation (C1-C4) found that all multi-statement operations were non-atomic without explicit transactions:

- **Event store append**: `MAX(seq)` + `INSERT` race condition (C2)
- **Idempotency claim**: Check-then-act TOCTOU across 3 queries (C3)
- **Task queue dequeue**: `FOR UPDATE SKIP LOCKED` lock released between SELECT and UPDATE in auto-commit mode (C4)
- **Checkpoint save**: SELECT + INSERT/UPDATE not atomic (M1)

All of these were fixed by wrapping in `conn.transaction()`.

## Driver-Specific Behavior

### SQLite

```python
# SQLite uses a single connection (not a pool)
conn = ConnectionManager("sqlite:///app.db")
await conn.initialize()

# WAL mode enabled automatically for file-based databases
# PRAGMA journal_mode=WAL
# PRAGMA foreign_keys=ON

# Transactions use BEGIN IMMEDIATE (serialized writes)
async with conn.transaction() as tx:
    # BEGIN IMMEDIATE
    await tx.execute(...)
    # COMMIT (or ROLLBACK on exception)
```

**Key behaviors**:

- `aiosqlite` provides an async wrapper around `sqlite3`
- Single writer -- concurrent writes are serialized by SQLite's locking
- `FOR UPDATE SKIP LOCKED` is not supported -- `dialect.for_update_skip_locked()` returns `""` and `BEGIN IMMEDIATE` provides equivalent safety for single-process use
- `conn.row_factory = aiosqlite.Row` enables dict-like row access
- Auto-commit on individual `execute()` calls (each call commits immediately)

### PostgreSQL

```python
# PostgreSQL uses asyncpg connection pool
conn = ConnectionManager("postgresql://user:pass@localhost/kailash")
await conn.initialize()

# Transactions acquire a connection from the pool
async with conn.transaction() as tx:
    # Acquires connection, starts transaction
    await tx.execute(...)
    # Commits (or rollbacks), releases connection back to pool
```

**Key behaviors**:

- `asyncpg.create_pool()` manages the connection pool
- `$1, $2, ...` numbered placeholders (translated from `?`)
- `FOR UPDATE SKIP LOCKED` fully supported for concurrent dequeue
- `fetchrow()` returns a `Record` (dict-like), converted to dict by ConnectionManager
- Pool connections are automatically released after each `execute()`/`fetch()`/`fetchone()` call

### MySQL

```python
# MySQL uses aiomysql connection pool
conn = ConnectionManager("mysql://user:pass@localhost/kailash")
await conn.initialize()

# URL components parsed: host, port, user, password, database
```

**Key behaviors**:

- `aiomysql.create_pool()` manages the connection pool
- `%s` positional placeholders (translated from `?`)
- `FOR UPDATE SKIP LOCKED` supported (MySQL 8.0+)
- Cursor-based row fetching with column names from `cursor.description`
- `INSERT IGNORE INTO` instead of `ON CONFLICT ... DO NOTHING`
- `ON DUPLICATE KEY UPDATE col = VALUES(col)` instead of `ON CONFLICT ... DO UPDATE SET col = EXCLUDED.col`
- Pool connections acquired/released per operation

## Pool Configuration

### Current Defaults

| Database   | Pool Type                | Default Size          |
| ---------- | ------------------------ | --------------------- |
| SQLite     | Single connection        | 1 (single-writer)     |
| PostgreSQL | `asyncpg.create_pool()`  | 10 (asyncpg default)  |
| MySQL      | `aiomysql.create_pool()` | 10 (aiomysql default) |

### Driver Installation

```bash
pip install kailash             # includes aiosqlite, asyncpg, aiomysql
```

Drivers are imported lazily inside `ConnectionManager._init_*()` methods. If the driver is not installed, a clear `ImportError` with installation instructions is raised.

## Sharing ConnectionManager via StoreFactory

**Rule**: Never create separate `ConnectionManager` instances for each store. All infrastructure stores MUST share a single instance through the `StoreFactory`:

```python
# WRONG: Multiple ConnectionManagers for the same database
conn1 = ConnectionManager("postgresql://...")
conn2 = ConnectionManager("postgresql://...")  # Wasteful, duplicates pool
event_store = DBEventStoreBackend(conn1)
exec_store = DBExecutionStore(conn2)

# CORRECT: Single ConnectionManager shared via StoreFactory
factory = StoreFactory.get_default()
await factory.initialize()  # Creates one ConnectionManager, shares it
event_store = await factory.create_event_store()    # Uses factory._conn
exec_store = await factory.create_execution_store()  # Uses same factory._conn
```

## Uninitialized Access Protection

Calling `execute()`, `fetch()`, `fetchone()`, or `transaction()` before `initialize()` raises a clear `RuntimeError`:

```python
conn = ConnectionManager("sqlite:///app.db")
# Forgot to call await conn.initialize()!

await conn.execute("SELECT 1")
# RuntimeError: ConnectionManager is not initialized.
#               Call await manager.initialize() first.
```

## Testing with ConnectionManager

```python
import pytest
from kailash.db.connection import ConnectionManager

@pytest.fixture
async def conn():
    """Provide an initialized in-memory SQLite ConnectionManager."""
    cm = ConnectionManager("sqlite:///:memory:")
    await cm.initialize()
    yield cm
    await cm.close()

async def test_insert_and_fetch(conn):
    await conn.execute(
        "CREATE TABLE test (id TEXT PRIMARY KEY, val INTEGER)"
    )
    await conn.execute("INSERT INTO test VALUES (?, ?)", "a", 42)
    row = await conn.fetchone("SELECT * FROM test WHERE id = ?", "a")
    assert row["val"] == 42
```

## When to Engage

- User asks about "ConnectionManager", "connection pool", "database connection"
- User asks about "transaction", "atomic operations", "rollback"
- User encounters "ConnectionManager is not initialized" errors
- User asks about driver differences (asyncpg vs aiosqlite vs aiomysql)
- User needs to understand placeholder translation
- User asks about sharing connections between stores
