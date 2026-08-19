# SQLite Concurrency Patterns

## AsyncSQLitePool

The `AsyncSQLitePool` provides read/write connection splitting optimized for SQLite's WAL mode.

### Configuration

```python
from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig

config = SQLitePoolConfig(
    db_path="/path/to/db.sqlite",
    max_read_connections=5,    # Concurrent readers (default: 5)
    max_lifetime=3600.0,       # Recycle connections after 1 hour
    acquire_timeout=10.0,      # Wait up to 10s for a connection
    pragmas={                  # Applied to every new connection
        "journal_mode": "WAL",
        "busy_timeout": "5000",
        "synchronous": "NORMAL",
        "cache_size": "-65536",
        "foreign_keys": "ON",
    },
)

pool = AsyncSQLitePool(config)
await pool.initialize()
```

### Connection Acquisition

```python
# Auto-route based on SQL prefix
async with pool.acquire("SELECT * FROM users") as conn:
    cursor = await conn.execute("SELECT * FROM users")

# Explicit read (for SELECT/WITH/EXPLAIN)
async with pool.acquire_read() as conn:
    cursor = await conn.execute("SELECT COUNT(*) FROM users")

# Explicit write (for INSERT/UPDATE/DELETE/CREATE/DROP)
async with pool.acquire_write() as conn:
    await conn.execute("INSERT INTO users VALUES (1, 'alice')")
    await conn.commit()
```

### Query Routing Logic

| Prefix                                                               | Route  | Notes                               |
| -------------------------------------------------------------------- | ------ | ----------------------------------- |
| SELECT, WITH, EXPLAIN                                                | Reader | Safe for concurrent access          |
| PRAGMA name                                                          | Reader | Read-only PRAGMA                    |
| PRAGMA name = value                                                  | Writer | Write PRAGMA                        |
| INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, BEGIN, COMMIT, ROLLBACK | Writer | All modifications                   |
| Unknown prefix                                                       | Writer | Safe default — reads work on writer |

SQL comments (`--` and `/* */`) are stripped before classification.

### Memory Database Mode

For `:memory:` databases, the pool uses single-connection mode (WAL unavailable):

```python
config = SQLitePoolConfig(db_path=":memory:")
# Internally translates to: file:memdb_<id>?mode=memory&cache=shared
# All acquire_read() calls delegate to acquire_write() (single connection)
```

### Default PRAGMAs

| PRAGMA       | Value  | Why                                      |
| ------------ | ------ | ---------------------------------------- |
| journal_mode | WAL    | Concurrent reads during writes           |
| busy_timeout | 5000   | Wait 5s instead of immediate SQLITE_BUSY |
| synchronous  | NORMAL | Balance safety/performance in WAL mode   |
| cache_size   | -65536 | 64MB page cache                          |
| foreign_keys | ON     | Enforce referential integrity            |

### Shutdown

```python
await pool.close()  # Closes writer + all readers
# After close(), acquire() raises PoolExhaustedError
```

## URI Shared-Cache for :memory: Databases

**Problem**: Each `aiosqlite.connect(":memory:")` creates a SEPARATE in-memory database.

**Solution**: Use URI shared-cache mode:

```python
# WRONG — two separate databases
conn1 = await aiosqlite.connect(":memory:")
conn2 = await aiosqlite.connect(":memory:")  # Can't see conn1's data

# CORRECT — shared database
uri = "file:mydb?mode=memory&cache=shared"
conn1 = await aiosqlite.connect(uri, uri=True)
conn2 = await aiosqlite.connect(uri, uri=True)  # Sees conn1's data
```

## Transaction Safety Model

Three-layer defense against resource leaks:

1. **`async with` (primary)** — `__aexit__` commits or rolls back, returns connection to pool
2. **`__del__` with ResourceWarning** — fires if GC collects a leaked transaction
3. **Pool-level WeakSet tracking** — `_active_transactions` detects leaks at shutdown

### New Adapter Checklist

When creating a new database adapter, ensure:

- [ ] Transaction class implements `__del__(self, _warnings=warnings)`
- [ ] Transaction class has class-level defaults: `_committed = False`, `_rolled_back = False`, `connection = None`
- [ ] Transaction class captures `_source_traceback = traceback.extract_stack()` in debug mode
- [ ] Adapter tracks active transactions via `weakref.WeakSet`
- [ ] Adapter integrates with appropriate connection pool
- [ ] `disconnect()` warns about leaked transactions before closing

## Anti-Patterns

```python
# NEVER: bare aiosqlite.connect() in adapter code
conn = await aiosqlite.connect(db_path)  # Bypasses pool

# NEVER: direct :memory: without URI shared-cache
conn = await aiosqlite.connect(":memory:")  # Isolated database

# NEVER: asyncio in __del__
def __del__(self):
    asyncio.get_event_loop().run_until_complete(self.close())  # Unreliable

# NEVER: unbounded connection pool
pool = []  # No max size, no health checks, no recycling
```
