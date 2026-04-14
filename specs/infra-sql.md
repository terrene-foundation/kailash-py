# Kailash Infrastructure — Dialect, Connection, Credentials, Migration, Pipeline

Parent domain: Infrastructure (split from `infrastructure.md` per specs-authority Rule 8)
Scope: Dialect system (PostgreSQL/MySQL/SQLite), connection management, URL resolution, credential handling, connection URL format, progressive infrastructure model, schema migration, database execution pipeline, migration tooling, environment variables, shared ownership contract, concurrency invariants, error handling

Sibling file: `infra-stores.md` (store abstractions, task queue, worker registry, store/queue factories)

Authoritative domain truth for the infrastructure layer of the Kailash Python SDK. Covers the dialect-portable database abstraction, connection management, credential handling, schema migration, and the progressive infrastructure model.

Source modules:

- `src/kailash/db/` -- dialect system, connection manager, URL registry, schema migration
- `src/kailash/database/` -- execution pipeline
- `src/kailash/utils/url_credentials.py` -- credential decode/encode helpers

---

## Database Type Enum

`kailash.db.dialect.DatabaseType` is the canonical enum for supported database engines.

| Member       | Value          |
| ------------ | -------------- |
| `POSTGRESQL` | `"postgresql"` |
| `MYSQL`      | `"mysql"`      |
| `SQLITE`     | `"sqlite"`     |

All dialect selection, connection pooling, and query translation branches on this enum.

---

## Dialect System

Module: `kailash.db.dialect`

The dialect system is a strategy pattern for cross-database SQL generation. It has zero external dependencies -- it generates SQL strings only. All infrastructure stores, DataFlow, and any SDK-internal SQL consumer use the dialect system to produce portable DDL and DML.

### Canonical Placeholder

The SDK-wide canonical SQL placeholder is `?` (SQLite style). Every SQL string authored inside the SDK uses `?` for parameter positions. The dialect's `translate_query()` method converts to the target dialect's native format before execution. Application code never writes dialect-specific placeholders.

| Dialect    | Native Placeholder | Translation             |
| ---------- | ------------------ | ----------------------- |
| SQLite     | `?`                | Identity (no-op)        |
| PostgreSQL | `$1`, `$2`, ...    | `?` -> `$N` (1-indexed) |
| MySQL      | `%s`               | `?` -> `%s`             |

### Identifier Validation

`_validate_identifier(name: str, *, max_length: int = 128) -> None`

Validates SQL identifiers (table names, column names, index names) against injection. Raises `ValueError` on failure.

Contract:

- Input must be a string.
- Maximum length: 128 characters (default; PostgreSQL limit is 63, MySQL is 64).
- Must match regex `^[a-zA-Z_][a-zA-Z0-9_]*$`.
- Error messages include a fingerprint hash (`hash(name) & 0xFFFF`), not the raw input, to prevent log poisoning.
- Does NOT attempt to escape -- rejects invalid inputs outright.

Used by: every `CREATE TABLE`, `CREATE INDEX`, table name constructor, and DDL path in the SDK.

### JSON Path Validation

`_validate_json_path(path: str) -> None`

Validates JSON extraction paths. Must match `^[a-zA-Z0-9_.]+$`. Raises `ValueError` on invalid input.

### QueryDialect (Abstract Base)

Abstract base class. All concrete dialects inherit from this.

**Required abstract methods:**

| Method                     | Returns                 | Purpose                                   |
| -------------------------- | ----------------------- | ----------------------------------------- |
| `database_type`            | `DatabaseType`          | Property -- which engine this dialect is  |
| `placeholder(index: int)`  | `str`                   | Parameter placeholder for 0-based index   |
| `upsert(...)`              | `Tuple[str, List[str]]` | Generate atomic upsert statement          |
| `json_column_type()`       | `str`                   | Native JSON column type for DDL           |
| `json_extract(col, path)`  | `str`                   | JSON field extraction expression          |
| `for_update_skip_locked()` | `str`                   | Row-level locking clause for task dequeue |
| `timestamp_now()`          | `str`                   | Current-timestamp SQL expression          |

**Provided base methods (overridable):**

| Method                           | Default                   | Purpose                                      |
| -------------------------------- | ------------------------- | -------------------------------------------- |
| `translate_query(query)`         | Replaces `?` via regex    | Translate canonical placeholders to dialect  |
| `insert_ignore(table, cols, ck)` | `ON CONFLICT DO NOTHING`  | INSERT that silently skips conflicts         |
| `auto_id_column()`               | `INTEGER PRIMARY KEY`     | Auto-incrementing PK DDL fragment            |
| `text_column(indexed=False)`     | `TEXT`                    | Text column type (indexed variant for MySQL) |
| `boolean_default(value)`         | `DEFAULT 0` / `DEFAULT 1` | Boolean default expression                   |
| `blob_type()`                    | `BLOB`                    | Binary data column type                      |

### PostgresDialect

| Method                     | Output                                                               |
| -------------------------- | -------------------------------------------------------------------- |
| `placeholder(i)`           | `$1`, `$2`, ...                                                      |
| `translate_query(q)`       | Base class -- replaces `?` with `$N`                                 |
| `upsert(...)`              | `INSERT INTO ... ON CONFLICT (...) DO UPDATE SET col = EXCLUDED.col` |
| `insert_ignore(...)`       | `INSERT INTO ... ON CONFLICT (...) DO NOTHING`                       |
| `auto_id_column()`         | `id SERIAL PRIMARY KEY`                                              |
| `boolean_default(v)`       | `DEFAULT TRUE` / `DEFAULT FALSE`                                     |
| `blob_type()`              | `BYTEA`                                                              |
| `json_column_type()`       | `JSONB`                                                              |
| `json_extract(col, path)`  | `col->>'path'`                                                       |
| `for_update_skip_locked()` | `FOR UPDATE SKIP LOCKED`                                             |
| `timestamp_now()`          | `NOW()`                                                              |
| `text_column(indexed)`     | `TEXT` (always -- PostgreSQL indexes TEXT natively)                  |

### MySQLDialect

| Method                     | Output                                                      |
| -------------------------- | ----------------------------------------------------------- |
| `placeholder(i)`           | `%s` (all positions)                                        |
| `translate_query(q)`       | Base class -- replaces `?` with `%s`                        |
| `upsert(...)`              | `INSERT INTO ... ON DUPLICATE KEY UPDATE col = VALUES(col)` |
| `insert_ignore(...)`       | `INSERT IGNORE INTO ...` (MySQL-specific syntax)            |
| `auto_id_column()`         | `id INTEGER PRIMARY KEY AUTO_INCREMENT`                     |
| `boolean_default(v)`       | `DEFAULT 0` / `DEFAULT 1` (base class)                      |
| `blob_type()`              | `LONGBLOB`                                                  |
| `json_column_type()`       | `JSON`                                                      |
| `json_extract(col, path)`  | `JSON_EXTRACT(col, '$.path')`                               |
| `for_update_skip_locked()` | `FOR UPDATE SKIP LOCKED` (MySQL 8.0+)                       |
| `timestamp_now()`          | `NOW()`                                                     |
| `text_column(indexed)`     | `VARCHAR(255)` if indexed, `TEXT` otherwise                 |

MySQL requires `VARCHAR(255)` for indexed columns because MySQL cannot index `TEXT` without specifying a key prefix length. This is the single most common dialect portability failure -- code that works on SQLite/PostgreSQL silently fails index creation on MySQL if it uses `TEXT` for a column that participates in a UNIQUE or INDEX constraint.

MySQL does not support `IF NOT EXISTS` on `CREATE INDEX`. The `ConnectionManager.create_index()` method catches the MySQL error 1061 (duplicate index) instead.

### SQLiteDialect

| Method                     | Output                                                               |
| -------------------------- | -------------------------------------------------------------------- |
| `placeholder(i)`           | `?`                                                                  |
| `translate_query(q)`       | Identity -- returns the input unchanged                              |
| `upsert(...)`              | `INSERT INTO ... ON CONFLICT (...) DO UPDATE SET col = excluded.col` |
| `insert_ignore(...)`       | `INSERT INTO ... ON CONFLICT (...) DO NOTHING`                       |
| `auto_id_column()`         | `INTEGER PRIMARY KEY` (base class default)                           |
| `boolean_default(v)`       | `DEFAULT 0` / `DEFAULT 1` (base class)                               |
| `blob_type()`              | `BLOB` (base class)                                                  |
| `json_column_type()`       | `TEXT` (SQLite stores JSON as text)                                  |
| `json_extract(col, path)`  | `json_extract(col, '$.path')`                                        |
| `for_update_skip_locked()` | `""` (empty string -- SQLite uses `BEGIN IMMEDIATE`)                 |
| `timestamp_now()`          | `datetime('now')`                                                    |
| `text_column(indexed)`     | `TEXT` (always -- SQLite indexes TEXT natively)                      |

Note on upsert: SQLite uses lowercase `excluded.col` while PostgreSQL uses uppercase `EXCLUDED.col`. Both are valid in their respective dialects.

### detect_dialect(url: str) -> QueryDialect

Auto-detects the appropriate dialect from a database connection URL.

**Detection rules (evaluated in order):**

1. `postgresql://`, `postgresql+...`, `postgres://` -> `PostgresDialect`
2. `mysql://`, `mysql+...` -> `MySQLDialect`
3. `sqlite://` -> `SQLiteDialect`
4. Plain file path (starts with `/`, `./`, `../`, or has no URL scheme) -> `SQLiteDialect`
5. Anything else -> raises `ValueError` with the unrecognized scheme

**Error cases:**

- `None` input -> `TypeError`
- Empty or whitespace-only string -> `ValueError` with actionable message mentioning `KAILASH_DATABASE_URL`
- Unknown scheme -> `ValueError` listing supported schemes

### Dialect Portability Matrix

| Feature                    | PostgreSQL                                         | MySQL                                       | SQLite                                             |
| -------------------------- | -------------------------------------------------- | ------------------------------------------- | -------------------------------------------------- |
| Placeholder                | `$1`                                               | `%s`                                        | `?`                                                |
| Upsert syntax              | `ON CONFLICT ... DO UPDATE SET col = EXCLUDED.col` | `ON DUPLICATE KEY UPDATE col = VALUES(col)` | `ON CONFLICT ... DO UPDATE SET col = excluded.col` |
| Insert-ignore              | `ON CONFLICT DO NOTHING`                           | `INSERT IGNORE INTO`                        | `ON CONFLICT DO NOTHING`                           |
| Auto-increment PK          | `SERIAL PRIMARY KEY`                               | `INTEGER PRIMARY KEY AUTO_INCREMENT`        | `INTEGER PRIMARY KEY`                              |
| Binary type                | `BYTEA`                                            | `LONGBLOB`                                  | `BLOB`                                             |
| JSON type                  | `JSONB`                                            | `JSON`                                      | `TEXT`                                             |
| Indexed text type          | `TEXT`                                             | `VARCHAR(255)`                              | `TEXT`                                             |
| Boolean default            | `DEFAULT TRUE/FALSE`                               | `DEFAULT 0/1`                               | `DEFAULT 0/1`                                      |
| Row locking                | `FOR UPDATE SKIP LOCKED`                           | `FOR UPDATE SKIP LOCKED`                    | _(empty -- uses BEGIN IMMEDIATE)_                  |
| Current timestamp          | `NOW()`                                            | `NOW()`                                     | `datetime('now')`                                  |
| CREATE INDEX IF NOT EXISTS | Supported                                          | Not supported (catch error)                 | Supported                                          |

---

## Connection Management

Module: `kailash.db.connection`

### ConnectionManager

The central async database connection manager. Wraps database-specific async drivers behind a uniform interface. All infrastructure stores, the StoreFactory, and any SDK-internal SQL consumer use ConnectionManager.

**Constructor:** `ConnectionManager(url: str)`

- Stores the URL.
- Calls `detect_dialect(url)` to set `self.dialect`.
- Does NOT create a connection pool -- that happens in `initialize()`.
- Raises `ValueError` for empty or unsupported URLs (via `detect_dialect`).

**Lifecycle methods:**

| Method         | Behavior                                                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `initialize()` | Creates the connection pool. Imports the async driver lazily. Raises `ImportError` with an actionable message if the driver is missing. |
| `close()`      | Closes the pool and sets `self._pool = None`. Safe to call multiple times. After close, `initialize()` can be called again.             |

**Driver initialization details:**

| Dialect    | Driver      | Pool Type                      | Additional Setup                                                                                                                                   |
| ---------- | ----------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| SQLite     | `aiosqlite` | Single connection (not a pool) | `row_factory = aiosqlite.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON` (file-based only, not `:memory:`)                               |
| PostgreSQL | `asyncpg`   | `asyncpg.create_pool(url)`     | None                                                                                                                                               |
| MySQL      | `aiomysql`  | `aiomysql.create_pool(...)`    | URL parsed via `urlparse` after `preencode_password_special_chars`. Credentials decoded via `decode_userinfo_or_raise` with `default_user="root"`. |

**SQLite URL parsing:**

- `sqlite:///path` -> strips `sqlite:///` prefix, uses `path`
- `sqlite://` without path -> treated as `:memory:`
- File-based databases get WAL mode and foreign keys enabled automatically

**Query execution methods:**

All query methods translate `?` placeholders to the dialect's native format before execution. All raise `RuntimeError` if `initialize()` has not been called.

| Method                   | Returns                    | Behavior                                                                          |
| ------------------------ | -------------------------- | --------------------------------------------------------------------------------- |
| `execute(query, *args)`  | Driver-specific cursor     | Execute a statement (DDL, DML). For SQLite, auto-commits after each execute.      |
| `fetch(query, *args)`    | `List[Dict[str, Any]]`     | Fetch all rows as dicts. Uses `cursor.description` for column names where needed. |
| `fetchone(query, *args)` | `Optional[Dict[str, Any]]` | Fetch a single row as dict, or `None`.                                            |

**Index creation:**

`create_index(index_name, table, columns) -> None`

- Validates all identifiers via `_validate_identifier`.
- PostgreSQL/SQLite: `CREATE INDEX IF NOT EXISTS ...`
- MySQL: `CREATE INDEX ...` with `except` to catch duplicate-index error 1061.
- Columns parameter is a comma-separated string (e.g. `"status, created_at"` for composite index).

**Transaction support:**

`transaction()` is an async context manager yielding a `_TransactionProxy`.

| Dialect    | Transaction Mechanism                                                             |
| ---------- | --------------------------------------------------------------------------------- |
| SQLite     | `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` on the single connection                |
| PostgreSQL | `pool.acquire()` -> `conn.transaction()` -> `start()` / `commit()` / `rollback()` |
| MySQL      | `pool.acquire()` -> `conn.begin()` / `conn.commit()` / `conn.rollback()`          |

On normal exit: commit. On exception: rollback, then re-raise.

The `_TransactionProxy` exposes `execute`, `fetch`, `fetchone` with the same signatures as ConnectionManager, but all operations run within the transaction's connection. Placeholder translation is applied identically.

---

## URL Resolution

Module: `kailash.db.registry`

### resolve_database_url() -> Optional[str]

Resolves the database URL from environment variables.

**Priority order:**

1. `KAILASH_DATABASE_URL` (Kailash-specific)
2. `DATABASE_URL` (generic / Heroku-style)
3. Returns `None` (Level 0 -- no database configured)

Both variables are checked; the first non-empty value wins.

### resolve_queue_url() -> Optional[str]

Resolves the queue URL from environment variables.

Checks `KAILASH_QUEUE_URL` only. Returns `None` if not set or empty.

---

## Credential Handling

Module: `kailash.utils.url_credentials`

### preencode_password_special_chars(connection_string) -> str

Pre-encodes raw `#$@?` characters in the password portion of a URL so that `urlparse` does not misparse them. Without this, a password containing `#` causes `urlparse` to treat everything after `#` as a URL fragment, silently dropping part of the password.

**Algorithm:**

1. If input is `None`, return `""`.
2. If no `://` in input, return unchanged.
3. If no `@` in the non-scheme portion, return unchanged.
4. Split on the LAST `@` (so `@` in passwords survives).
5. Split credentials on the FIRST `:` (so `:` in passwords survives).
6. Percent-encode `#` -> `%23`, `$` -> `%24`, `@` -> `%40`, `?` -> `%3F` in the password.
7. Reassemble.

**Called by:** Every URL parsing site in the SDK before `urlparse`.

### decode_userinfo_or_raise(parsed, \*, default_user="root") -> (str, str)

Decodes and validates userinfo from a `urlparse` result. Returns `(user, password)` with percent-encoding removed.

**Null-byte rejection:** Raises `ValueError` if either decoded field contains `\x00`. This prevents the MySQL C client null-byte truncation auth bypass where `mysql://user:%00bypass@host/db` decodes to `\x00bypass` and the driver sends an empty password.

**Contract:**

- `parsed.username` is `None` -> returns `default_user`.
- `parsed.password` is `None` -> returns `""`.
- Both fields are `unquote()`-ed.
- If either decoded value contains `\x00`, raises `ValueError` with a message that identifies the field name but does NOT echo the raw value.

---

## Connection URL Format

### PostgreSQL

```
postgresql://user:password@host:port/database
postgresql+asyncpg://user:password@host:port/database
postgres://user:password@host:port/database
```

Default port: 5432. Driver: `asyncpg`.

### MySQL

```
mysql://user:password@host:port/database
mysql+aiomysql://user:password@host:port/database
```

Default port: 3306. Default user: `root`. Driver: `aiomysql`.

Special character handling: Passwords with `#`, `$`, `@`, `?` must be either pre-encoded by the user or will be auto-encoded by `preencode_password_special_chars`.

### SQLite

```
sqlite:///path/to/database.db      (file-based)
sqlite:///:memory:                 (in-memory)
sqlite:///                         (empty path -> :memory:)
/path/to/database.db               (plain file path -> SQLite)
./relative/path.db                 (relative path -> SQLite)
```

Driver: `aiosqlite`. File-based databases automatically get WAL mode and foreign keys enabled.

---

## Progressive Infrastructure Model

The Kailash SDK uses a progressive infrastructure model where the same application code runs identically across deployment tiers. The `StoreFactory` abstracts the tier selection.

### Level 0 -- No Database

- **Config:** No `KAILASH_DATABASE_URL` set.
- **Event store:** SQLite file-based (`SqliteEventStoreBackend`).
- **Checkpoints:** Disk-based file storage (`DiskStorage`).
- **DLQ:** SQLite file-based (`PersistentDLQ`).
- **Execution store:** In-memory with LRU eviction (`InMemoryExecutionStore`, max 10,000 entries).
- **Idempotency:** None (no deduplication).
- **Task queue:** None (single-process execution only).
- **Use case:** Local development, prototyping, single-process scripts.

### Level 1 -- SQLite

- **Config:** `KAILASH_DATABASE_URL=sqlite:///app.db`
- **All stores:** DB-backed via `ConnectionManager` with `aiosqlite`.
- **Task queue:** Optional via `KAILASH_QUEUE_URL=sqlite:///queue.db`.
- **Concurrency:** Single-writer via `BEGIN IMMEDIATE`. Concurrent reads via WAL mode.
- **Use case:** Single-server applications, embedded deployments, heavy researcher workloads.

### Level 2 -- PostgreSQL / MySQL

- **Config:** `KAILASH_DATABASE_URL=postgresql://...` or `mysql://...`
- **All stores:** DB-backed via `ConnectionManager` with `asyncpg` or `aiomysql`.
- **Task queue:** Redis (`redis://...`) or SQL-backed (`postgresql://...`).
- **Concurrency:** Full connection pooling, `FOR UPDATE SKIP LOCKED` for task dequeue.
- **Use case:** Production multi-worker deployments.

### Upgrade Path

Switching from SQLite to PostgreSQL requires only changing the `KAILASH_DATABASE_URL` environment variable. All store schemas are created automatically via `CREATE TABLE IF NOT EXISTS`. No data migration tool is currently provided for moving data between tiers -- the infrastructure tables are operational state (checkpoints, execution history) rather than application data.

---

## Schema Migration

Module: `kailash.db.migration`

### Schema Version Tracking

`SCHEMA_VERSION = 1` -- Current version for all infrastructure tables.

`check_schema_version(conn) -> Optional[int]` -- Read the current schema version from `kailash_meta`. Returns `None` if the table does not exist or has no entry.

`stamp_schema_version(conn, version=SCHEMA_VERSION)` -- Create or update the schema version. Raises `RuntimeError` if the existing version is newer than the code version (downgrade protection). Creates the `kailash_meta` table if it does not exist.

### Infrastructure Table List

All tables created by the infrastructure layer:

| Table                     | Created By            | Purpose                    |
| ------------------------- | --------------------- | -------------------------- |
| `kailash_meta`            | `StoreFactory`        | Schema version tracking    |
| `kailash_checkpoints`     | `DBCheckpointStore`   | Workflow state persistence |
| `kailash_events`          | `DBEventStoreBackend` | Immutable event audit log  |
| `kailash_executions`      | `DBExecutionStore`    | Execution history          |
| `kailash_idempotency`     | `DBIdempotencyStore`  | Request deduplication      |
| `kailash_dlq`             | `DBDeadLetterQueue`   | Failed task handling       |
| `kailash_task_queue`      | `SQLTaskQueue`        | Task scheduling/dispatch   |
| `kailash_worker_registry` | `SQLWorkerRegistry`   | Worker health tracking     |

All tables use `CREATE TABLE IF NOT EXISTS` and are idempotent to create.

---

## Database Execution Pipeline

Module: `kailash.database.execution_pipeline`

A pipeline-based approach to database operations with clean separation of concerns. This is the higher-level execution framework that DataFlow and other SDK components use, layering permission checking, validation, execution, and masking.

### Pipeline Stages

Stages execute in sequence. Each stage receives the `ExecutionContext` and the result from the previous stage.

| Stage                      | Position | Purpose                                                                                                                                                                                   |
| -------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PermissionCheckStage`     | 1        | Check user permissions via `AccessControlManager`. Skips if no ACM or no user context. Raises `NodeExecutionError` on denial.                                                             |
| `QueryValidationStage`     | 2        | Validate query safety. Checks for empty queries. Logs dangerous keywords (DROP, DELETE, TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXEC, EXECUTE, SHUTDOWN, BACKUP, RESTORE) at DEBUG level. |
| _(custom stages)_          | 3        | Optional user-provided stages inserted before execution.                                                                                                                                  |
| `QueryExecutionStage`      | 4        | Execute the query via the provided executor. Records execution time. Wraps errors in `NodeExecutionError`.                                                                                |
| `DataMaskingStage`         | 5        | Apply data masking based on user attributes via `AccessControlManager.apply_data_masking()`. Only applies to dict-format list results.                                                    |
| _(post-processing stages)_ | 6        | Optional user-provided stages with `get_stage_name() == "post_processing"`.                                                                                                               |

### ExecutionContext

Dataclass carrying the query and metadata through the pipeline.

| Field             | Type                    | Default          |
| ----------------- | ----------------------- | ---------------- | ------ |
| `query`           | `str`                   | required         |
| `parameters`      | `Optional[Dict          | List]`           | `None` |
| `user_context`    | `Optional[UserContext]` | `None`           |
| `node_name`       | `str`                   | `"unknown_node"` |
| `result_format`   | `str`                   | `"dict"`         |
| `runtime_context` | `Optional[Dict]`        | `None`           |

### ExecutionResult

Dataclass carrying query results through the pipeline.

| Field            | Type             | Default |
| ---------------- | ---------------- | ------- |
| `data`           | `Any`            | --      |
| `row_count`      | `int`            | --      |
| `columns`        | `List[str]`      | --      |
| `execution_time` | `float`          | --      |
| `metadata`       | `Optional[Dict]` | `None`  |

### DatabaseExecutionPipeline

Constructor: `DatabaseExecutionPipeline(access_control_manager=None, query_executor=None, validation_rules=None, custom_stages=None)`

Methods:

- `execute(context) -> ExecutionResult` -- Run the full pipeline.
- `add_stage(stage, position=None)` -- Add a custom stage at a specific position.
- `remove_stage(stage_name) -> bool` -- Remove a stage by name.
- `get_stage_info() -> [dict]` -- List all stages with name and type.

---

## Migration Tooling

Module: `kailash.migration`

This is a separate concern from schema migration -- it provides tools for migrating application code that uses the `LocalRuntime` to newer API versions.

### Components

| Class                    | Purpose                                               |
| ------------------------ | ----------------------------------------------------- |
| `CompatibilityChecker`   | Analyze existing code for API compatibility issues    |
| `MigrationAssistant`     | Automated configuration conversion and code rewriting |
| `PerformanceComparator`  | Before/after performance analysis                     |
| `ConfigurationValidator` | Runtime configuration validation                      |
| `MigrationDocGenerator`  | Automated migration guide generation                  |
| `RegressionDetector`     | Post-migration validation                             |

### MigrationAssistant

The primary tool. Operates in `dry_run` mode by default.

**Parameter mappings** (old -> new):

| Old Parameter           | New Parameter               |
| ----------------------- | --------------------------- |
| `debug_mode`            | `debug`                     |
| `enable_parallel`       | `max_concurrency`           |
| `thread_pool_size`      | `max_concurrency`           |
| `parallel_execution`    | `max_concurrency`           |
| `enable_security_audit` | `enable_audit`              |
| `connection_pooling`    | `enable_connection_sharing` |
| `persistent_resources`  | `persistent_mode`           |
| `memory_limit`          | `resource_limits`           |
| `timeout`               | `resource_limits`           |
| `retry_count`           | `retry_policy_config`       |

**Workflow:**

1. `create_migration_plan(root_path)` -- Analyze codebase, return `MigrationPlan` with steps.
2. `execute_migration(plan)` -- Execute (or validate in dry_run mode). Returns `MigrationResult`.
3. `rollback_migration(result)` -- Restore from backup if needed.

---

## Environment Variables Summary

| Variable               | Purpose                                    | Default |
| ---------------------- | ------------------------------------------ | ------- |
| `KAILASH_DATABASE_URL` | Primary database URL                       | None    |
| `DATABASE_URL`         | Fallback database URL (Heroku-style)       | None    |
| `KAILASH_QUEUE_URL`    | Task queue URL (Redis, PostgreSQL, SQLite) | None    |

---

## Shared Ownership Contract

All store backends follow the same ownership contract for `ConnectionManager`:

- The store does NOT own the ConnectionManager.
- The store's `close()` method does NOT close the ConnectionManager.
- Multiple stores share a single ConnectionManager (and therefore a single connection pool).
- The caller (typically `StoreFactory`) is responsible for closing the ConnectionManager.

This is enforced by the `StoreFactory` pattern: one factory creates one ConnectionManager, passes it to all stores, and closes it when `factory.close()` is called.

**Exception:** The `queue_factory.create_task_queue()` function creates its own ConnectionManager for SQL-backed queues. This is a separate pool from the store factory's pool.

---

## Concurrency Invariants

### SQLite

- Single connection (not a pool). All operations are serialized.
- `BEGIN IMMEDIATE` for transactions -- acquires write lock immediately, preventing other writers.
- WAL mode enabled for file-based databases -- concurrent reads are possible alongside a single writer.
- `FOR UPDATE SKIP LOCKED` is not supported -- the dialect returns an empty string, and task dequeue relies on the serialized transaction instead.

### PostgreSQL

- Connection pool via `asyncpg.create_pool()`.
- Full `FOR UPDATE SKIP LOCKED` support for concurrent task dequeue.
- Transactions use `asyncpg` connection-level transaction management.

### MySQL

- Connection pool via `aiomysql.create_pool()`.
- `FOR UPDATE SKIP LOCKED` requires MySQL 8.0+.
- Connections acquired from the pool for each operation outside transactions.
- MySQL-specific: `INSERT IGNORE INTO` instead of `ON CONFLICT DO NOTHING`.
- MySQL-specific: `ON DUPLICATE KEY UPDATE col = VALUES(col)` instead of `ON CONFLICT DO UPDATE SET col = EXCLUDED.col`.
- MySQL-specific: `VARCHAR(255)` required for indexed text columns.
- MySQL-specific: `CREATE INDEX` without `IF NOT EXISTS` (error 1061 caught).
- MySQL-specific: `LONGBLOB` instead of `BLOB`.
- MySQL-specific: `AUTO_INCREMENT` in `auto_id_column()`.

---

## Error Handling

All stores and the ConnectionManager follow these error handling patterns:

- `RuntimeError` when `ConnectionManager.execute/fetch/fetchone` is called before `initialize()`.
- `RuntimeError` from `stamp_schema_version` when the database has a newer schema than the running code (downgrade protection).
- `ValueError` from `_validate_identifier` when a table name, column name, or index name fails the allowlist regex.
- `ImportError` with actionable install instructions when a required async driver is missing.
- `ValueError` from `decode_userinfo_or_raise` when decoded credentials contain null bytes.

No store silently swallows exceptions. All exceptions propagate to the caller. Logging is used for operational visibility (INFO for lifecycle events, DEBUG for per-operation detail, WARNING for degraded paths like dead worker reaping).
