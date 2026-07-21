# Dialect-Portable SQL

You are an expert in writing dialect-portable SQL for Kailash infrastructure stores. Guide users through the QueryDialect strategy pattern, canonical placeholder convention, identifier validation, and cross-database differences.

> For full implementation details, see `docs/enterprise-infrastructure/` and the source at the QueryDialect module.

## QueryDialect Strategy Pattern

The `QueryDialect` abstract base class defines dialect-specific SQL generation methods. Three concrete implementations cover all supported databases.

### Architecture

```
QueryDialect (ABC)
├── PostgresDialect   — $1, $2 placeholders, JSONB, BYTEA, FOR UPDATE SKIP LOCKED
├── MySQLDialect      — %s placeholders, JSON, BLOB, FOR UPDATE SKIP LOCKED
└── SQLiteDialect     — ? placeholders (canonical), TEXT for JSON, BLOB, BEGIN IMMEDIATE
```

### Abstract Methods

Every dialect MUST implement:

| Method                                  | Purpose                                 | PostgreSQL                  | MySQL                         | SQLite                        |
| --------------------------------------- | --------------------------------------- | --------------------------- | ----------------------------- | ----------------------------- |
| `database_type`                         | Property returning `DatabaseType` enum  | `.POSTGRESQL`               | `.MYSQL`                      | `.SQLITE`                     |
| `placeholder(index)`                    | Parameter placeholder for 0-based index | `$1`, `$2`                  | `%s`                          | `?`                           |
| `upsert(table, columns, conflict_keys)` | Upsert statement                        | `ON CONFLICT ... DO UPDATE` | `ON DUPLICATE KEY UPDATE`     | `ON CONFLICT ... DO UPDATE`   |
| `json_column_type()`                    | JSON storage column type                | `JSONB`                     | `JSON`                        | `TEXT`                        |
| `json_extract(column, path)`            | JSON field extraction expression        | `col->>'path'`              | `JSON_EXTRACT(col, '$.path')` | `json_extract(col, '$.path')` |
| `for_update_skip_locked()`              | Row-level locking clause                | `FOR UPDATE SKIP LOCKED`    | `FOR UPDATE SKIP LOCKED`      | `""` (empty)                  |
| `timestamp_now()`                       | Current-timestamp expression            | `NOW()`                     | `NOW()`                       | `datetime('now')`             |

### Base Class Methods (Shared)

| Method                                         | Purpose                             | Notes                                |
| ---------------------------------------------- | ----------------------------------- | ------------------------------------ |
| `translate_query(query)`                       | Convert `?` to dialect placeholders | SQLite overrides with identity       |
| `insert_ignore(table, columns, conflict_keys)` | INSERT ignore-on-conflict           | MySQL overrides with `INSERT IGNORE` |
| `blob_type()`                                  | Binary column type                  | PostgreSQL overrides with `BYTEA`    |

## Canonical Placeholder Convention

All SQL in Kailash infrastructure uses `?` as the canonical placeholder character:

```python
# Write SQL with ? placeholders everywhere
await conn.execute(
    "INSERT INTO kailash_executions (run_id, status) VALUES (?, ?)",
    run_id, "pending"
)

# ConnectionManager.execute() calls dialect.translate_query() automatically:
# PostgreSQL: INSERT INTO kailash_executions (run_id, status) VALUES ($1, $2)
# MySQL:      INSERT INTO kailash_executions (run_id, status) VALUES (%s, %s)
# SQLite:     INSERT INTO kailash_executions (run_id, status) VALUES (?, ?)
```

**Rule**: Never write `$1` or `%s` in store code. Always use `?`. The ConnectionManager handles translation.

## Identifier Validation (MANDATORY)

The `_validate_identifier()` function prevents SQL injection through table and column names:

```python
from kailash.db.dialect import _validate_identifier, _validate_json_path

# Regex: ^[a-zA-Z_][a-zA-Z0-9_]*$
_validate_identifier("kailash_tasks")      # OK
_validate_identifier("user_name")          # OK
_validate_identifier("Robert'; DROP--")    # Raises ValueError
_validate_identifier("../../../etc")       # Raises ValueError

# JSON path validation: ^[a-zA-Z0-9_.]+$
_validate_json_path("metadata.key")        # OK
_validate_json_path("a.b.c")              # OK
_validate_json_path("'; DROP TABLE--")     # Raises ValueError
```

**Rule**: Every method that interpolates a table or column name into SQL MUST call `_validate_identifier()` first. This is enforced by `.claude/rules/infrastructure-sql.md`.

## Auto-Detection

The `detect_dialect()` function selects the correct dialect from a database URL:

```python
from kailash.db.dialect import detect_dialect

dialect = detect_dialect("postgresql://localhost/mydb")     # PostgresDialect
dialect = detect_dialect("postgresql+asyncpg://...")        # PostgresDialect
dialect = detect_dialect("mysql://localhost/mydb")          # MySQLDialect
dialect = detect_dialect("sqlite:///app.db")               # SQLiteDialect
dialect = detect_dialect("sqlite:///:memory:")              # SQLiteDialect
dialect = detect_dialect("/path/to/file.db")               # SQLiteDialect (plain path)
dialect = detect_dialect("./local.db")                     # SQLiteDialect (relative path)
```

Raises `ValueError` for unsupported schemes, `TypeError` for non-string input, `ValueError` for empty strings.

## Dialect Difference Table

| Feature           | PostgreSQL                                         | MySQL 8.0+                                  | SQLite                                             |
| ----------------- | -------------------------------------------------- | ------------------------------------------- | -------------------------------------------------- |
| Placeholder       | `$1, $2, ...`                                      | `%s`                                        | `?`                                                |
| Upsert            | `ON CONFLICT ... DO UPDATE SET col = EXCLUDED.col` | `ON DUPLICATE KEY UPDATE col = VALUES(col)` | `ON CONFLICT ... DO UPDATE SET col = excluded.col` |
| Insert ignore     | `ON CONFLICT ... DO NOTHING`                       | `INSERT IGNORE INTO`                        | `ON CONFLICT ... DO NOTHING`                       |
| JSON type         | `JSONB`                                            | `JSON`                                      | `TEXT`                                             |
| JSON extract      | `col->>'path'`                                     | `JSON_EXTRACT(col, '$.path')`               | `json_extract(col, '$.path')`                      |
| Binary type       | `BYTEA`                                            | `BLOB`                                      | `BLOB`                                             |
| Row lock          | `FOR UPDATE SKIP LOCKED`                           | `FOR UPDATE SKIP LOCKED`                    | N/A (use `BEGIN IMMEDIATE`)                        |
| Timestamp         | `NOW()`                                            | `NOW()`                                     | `datetime('now')`                                  |
| Auto-increment PK | `SERIAL` or `GENERATED`                            | `AUTO_INCREMENT`                            | `INTEGER PRIMARY KEY` (implicit)                   |

## Code Examples from Implementation

### Using upsert() for Checkpoint Save

```python
# From kailash/infrastructure/checkpoint_store.py
# Uses dialect.upsert() instead of check-then-act (TOCTOU fix)
sql, param_cols = self._conn.dialect.upsert(
    self.TABLE_NAME,
    ["run_id", "node_id", "checkpoint_data", "updated_at"],
    ["run_id", "node_id"],  # conflict keys
)
translated = self._conn.dialect.translate_query(sql)
```

### Using insert_ignore() for Idempotency Claims

```python
# From kailash/infrastructure/idempotency_store.py
_cols = [
    "idempotency_key", "fingerprint", "response_data",
    "status_code", "headers", "created_at", "expires_at",
]
sql = self._conn.dialect.insert_ignore(
    self.TABLE_NAME, _cols, ["idempotency_key"]
)
# PostgreSQL/SQLite: INSERT INTO ... ON CONFLICT (idempotency_key) DO NOTHING
# MySQL: INSERT IGNORE INTO ...
```

### Using for_update_skip_locked() for Task Dequeue

```python
# From kailash/infrastructure/task_queue.py
lock_clause = self._conn.dialect.for_update_skip_locked()

async with self._conn.transaction() as tx:
    select_sql = (
        f"SELECT task_id FROM {self._table} "
        f"WHERE queue_name = ? AND status = 'pending' "
        f"ORDER BY created_at ASC LIMIT 1"
    )
    if lock_clause:
        select_sql += f" {lock_clause}"

    row = await tx.fetchone(select_sql, queue_name)
```

## Anti-Patterns

### Never Hardcode Dialect-Specific SQL

```python
# WRONG: PostgreSQL-specific
await conn.execute("INSERT INTO tasks VALUES ($1, $2)", task_id, status)

# WRONG: SQLite-specific in shared code
await conn.execute(
    "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ...)"
)

# CORRECT: Use canonical ? placeholders
await conn.execute("INSERT INTO tasks VALUES (?, ?)", task_id, status)

# CORRECT: INTEGER PRIMARY KEY auto-increments natively on all dialects
await conn.execute(
    "CREATE TABLE events (id INTEGER PRIMARY KEY, ...)"
)
```

### Never Interpolate Unvalidated Identifiers

```python
# WRONG: SQL injection via table name
table = user_input
await conn.execute(f"SELECT * FROM {table} WHERE id = ?", record_id)

# CORRECT: Validate first
from kailash.db.dialect import _validate_identifier
_validate_identifier(table)
await conn.execute(f"SELECT * FROM {table} WHERE id = ?", record_id)
```

### Never Use BLOB Without dialect.blob_type()

```python
# WRONG: Fails on PostgreSQL (BLOB is not a valid type)
await conn.execute(
    "CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data BLOB)"
)

# CORRECT: Dialect-aware binary type
blob_type = conn.dialect.blob_type()
await conn.execute(
    f"CREATE TABLE checkpoints (id TEXT PRIMARY KEY, data {blob_type})"
)
```

## When to Engage

- User asks about "cross-database SQL", "dialect portability", "QueryDialect"
- User needs to write SQL that works on PostgreSQL, MySQL, AND SQLite
- User encounters placeholder translation issues
- User asks about SQL injection prevention in infrastructure code
- User needs upsert, insert-ignore, or JSON extraction across databases
