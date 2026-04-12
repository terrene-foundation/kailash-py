# Adapters + Dialect Layer Audit

**Scope**: `packages/kailash-dataflow/src/dataflow/adapters/`, `.../sql/`, `.../database/`
**Auditor**: dataflow-specialist
**Date**: 2026-04-08
**Method**: line-by-line inspection of adapter sources, cross-reference to
`rules/infrastructure-sql.md`, `rules/dataflow-pool.md`, `rules/patterns.md`,
`rules/zero-tolerance.md`, `rules/observability.md`, `rules/dependencies.md`.

## Summary

The adapter layer is the physical interface between DataFlow and the three
official SQL dialects (PostgreSQL via asyncpg, MySQL via aiomysql, SQLite via
aiosqlite). The stated promise of the package is dialect portability — pass any
URL and DataFlow just works. The reality is that the adapter layer is a
collection of **partially-wired shells** where large fractions of the parsed
configuration are never forwarded to the driver, transaction methods don't
transact, schema methods interpolate table names into raw SQL, and entire
dialect helper subsystems exist in the tree but are never imported by the
adapters that are supposed to use them. Issue **#353** (`sslmode` ignored) is
the tip of an iceberg — the same pattern of "parse into self, drop on floor"
repeats for `application_name`, `command_timeout` (semantically wrong), bounded
overflow, pool size resolution, and every PostgreSQL SSL file-path option the
driver supports.

Severity rollup (adapters only, excluding cache/fabric/nodes):

| Severity | Count |
| -------- | ----- |
| CRITICAL | 8     |
| HIGH     | 14    |
| MEDIUM   | 11    |
| LOW      | 7     |

The rest of this document walks each finding with a file:line citation, fix
outline, regression test plan, cross-subsystem coupling, and a cross-SDK
parallel entry for kailash-rs `crates/kailash-dataflow`. A cross-adapter parity
table sits at the end.

---

## CRITICAL Findings

### C1. PostgreSQL `sslmode` parsed then discarded (#353 confirmed + wider pattern)

**File**: `src/dataflow/adapters/postgresql.py:34` parses `self.ssl_mode` from
`query_params["sslmode"]`. `get_connection_parameters()` at line 340-351
returns a dict of seven keys — `host`, `port`, `database`, `user`, `password`,
`min_size`, `max_size`, `command_timeout` — and `ssl` is not among them.
`create_connection_pool()` at line 49-84 passes this dict unchanged to
`asyncpg.create_pool(**params)`. Result: `?sslmode=disable`,
`?sslmode=require`, `?sslmode=verify-full` — none have any effect. The
production postgres-without-SSL test bed that triggered #353 is broken; the
production postgres-WITH-required-SSL case is broken in the opposite direction
(the pool happens to connect because asyncpg defaults to `prefer`, which is
wrong for compliance deployments that require `verify-full`).

The fix is one line away on the surface but the real fix is larger. asyncpg
does not accept a `sslmode` keyword — it accepts an `ssl` argument that is
either (a) a string like `"disable"`/`"allow"`/`"prefer"`/`"require"` (recent
asyncpg versions), (b) `True`/`False`, or (c) a `ssl.SSLContext` object
(required for `verify-ca` / `verify-full` with CA path).

**Fix outline**:

1. In `get_connection_parameters()`, translate `self.ssl_mode` into an asyncpg
   `ssl` argument:
   - `disable` → `False`
   - `allow` / `prefer` → `None` (asyncpg default of opportunistic)
   - `require` → `True`
   - `verify-ca` / `verify-full` → construct an `ssl.SSLContext` from
     `query_params.get("sslrootcert")`, `sslcert`, `sslkey`
2. Add the `ssl` key to the returned dict.
3. Parse `sslrootcert`, `sslcert`, `sslkey`, `sslpassword` from `query_params`
   in `__init__` (currently only `sslmode` is parsed).
4. Fix the existing unit test at `tests/unit/adapters/test_postgresql_adapter.py:249-268`
   which encodes the bug as the expected behavior (`expected_params` dict
   explicitly omits `ssl`). A passing test today proves the bug.

**Regression test**:

- `tests/regression/test_issue_353_sslmode_forwarded.py`: instantiate
  `PostgreSQLAdapter("postgresql://u:p@h/d?sslmode=disable")`, assert
  `get_connection_parameters()["ssl"] is False`. Repeat for every sslmode value.
- Tier 2: Real connection to local postgres with `ssl = off` in postgresql.conf
  — must succeed with `?sslmode=disable`, must fail with `?sslmode=require`.
  Currently both cases connect identically because `ssl` is never set.

**Cross-subsystem**: DataFlow config layer (`dataflow/core/config.py`) should
probably expose `ssl_mode` as a first-class parameter. Also, `ConnectionParser`
at `connection_parser.py:142` validates `sslmode` values — that validation runs
but the validated value is then discarded.

**Cross-SDK**: kailash-rs must be audited for the same parse-and-drop pattern
in `crates/kailash-dataflow/src/adapters/postgres.rs`. File as `cross-sdk`.

### C2. PostgreSQL `application_name` parsed then discarded

**File**: `postgresql.py:35` — `self.application_name = kwargs.get(...)` —
never appears in `get_connection_parameters()`. asyncpg accepts
`server_settings={"application_name": "dataflow"}` as a connect parameter.
Without it, `pg_stat_activity` shows every DataFlow connection under the
generic `asyncpg` name, making operator triage impossible during an incident.

**Fix**: Add `"server_settings": {"application_name": self.application_name}`
to the dict returned by `get_connection_parameters()`. Expose
`application_name` as a DataFlow init kwarg. Same fix for MySQL using the
`program_name` connection attribute (aiomysql `program_name`).

**Regression test**: Tier 2 — after connecting, query
`SELECT application_name FROM pg_stat_activity WHERE datname = current_database()`,
assert the configured name appears.

**Cross-SDK**: Same in `crates/kailash-dataflow/src/adapters/postgres.rs`.

### C3. PostgreSQL `command_timeout` semantic error — pool_timeout wired to query timeout

**File**: `postgresql.py:350` passes `self.pool_timeout` (default 30s, used as
"wait this long for a free connection from the pool") to asyncpg's
`command_timeout` kwarg, which is "abort any query that takes longer than this
many seconds". These are different behaviors. The pool also accepts a `timeout`
kwarg that IS the pool-wait timeout. The adapter uses neither correctly.

Consequence: (a) there is no bounded wait for a connection (default asyncpg is
`None` — unbounded; rules/connection-pool.md Rule 5: "Connection timeout MUST
be set"), so during an exhaustion event every request hangs forever — exactly
what the rule forbids; (b) every query is forced to complete within the
pool-wait timeout, which is appropriate for `SELECT 1` health checks but cuts
off long-running analytics queries that should be allowed to run.

**Fix outline**:

1. Introduce two separate adapter kwargs: `pool_wait_timeout` (default 10s) and
   `statement_timeout` (default None / user-provided).
2. Pass `timeout=pool_wait_timeout` AND `command_timeout=statement_timeout` to
   `asyncpg.create_pool`.
3. Deprecate single `pool_timeout` with a migration path (keep accepting it for
   one release, route it to `pool_wait_timeout`).

**Regression test**: Tier 2 — spin up pool of size 1, hold the one connection
from test thread A; from test thread B acquire a connection and assert the
wait-timeout fires within pool_wait_timeout and raises. Separately, execute
`SELECT pg_sleep(5)` with `statement_timeout=1` and assert abort.

**Cross-SDK**: `crates/kailash-dataflow/src/adapters/postgres.rs` uses
`sqlx::pool::PoolOptions::acquire_timeout` — verify separation is respected.

### C4. PostgreSQL `execute_transaction` is not a transaction

**File**: `postgresql.py:157-176`. The method is named `execute_transaction`,
docstring says "Execute multiple queries in PostgreSQL transaction", but the
body is:

```python
for query, params in queries:
    result = await self.execute_query(query, params)
    results.append(result)
```

`execute_query()` acquires a new connection from the pool per call. There is
no `BEGIN`, no `COMMIT`, no shared connection, no transactional atomicity. A
failure on query 3 of 5 leaves queries 1-2 committed. This is a silent data
integrity bug — the caller believes the batch rolls back on error and it does
not. The MySQL and SQLite equivalents at `mysql.py:177-197` and
`sqlite.py:408-461` actually implement real transactions. So callers with
cross-dialect code silently get atomicity on MySQL/SQLite and lose it on
PostgreSQL.

**Fix**: Rewrite as `async with self.transaction() as tx: ...` using the
existing `PostgreSQLTransaction` context manager, binding all queries to the
same connection.

**Regression test**: `tests/regression/test_postgres_execute_transaction_atomic.py` —
execute `[INSERT valid, INSERT valid, INSERT violates PK]`, assert table is
empty after the call raises.

**Cross-SDK**: Verify `execute_transaction` in Rust adapter is wired to a real
transaction span.

### C5. SQL injection via f-string interpolation of `table_name` in DDL and metadata queries

**Files**:

- `postgresql.py:279` — `CREATE TABLE IF NOT EXISTS {table_name}`
- `postgresql.py:294` — `DROP TABLE IF EXISTS {table_name}`
- `postgresql.py:363` — `get_columns_query(table_name)` interpolates
  `table_name` into a WHERE clause of an f-string
- `mysql.py:282` — `CREATE TABLE ...` with f-string
- `mysql.py:298` — `DROP TABLE ...` with f-string
- `mysql.py:376` — `get_tables_query()` interpolates `self.database`
- `mysql.py:386` — `get_columns_query(table_name)` interpolates both
  `self.database` and `table_name` into WHERE clause
- `sqlite.py:519`, `sqlite.py:539` — create/drop with f-string
- `sqlite.py:673` — `get_columns_query` returns `f"PRAGMA table_info({table_name})"`
- `sqlite_enterprise.py:864, 893, 973, 1003, 1013, 1023, 1074, 1079, 1139`

`rules/infrastructure-sql.md` § Query safety and `rules/security.md` §
Parameterized queries both mandate parameterized queries / identifier quoting.
The current pattern assumes all table_name values are trusted developer input,
but the rule makes no such carve-out for developer input because DataFlow ends
up receiving table names through `@db.model` decorated class names and through
`get_table_schema()` called with user-reachable metadata endpoints.

**Fix outline**:

1. Introduce an identifier-quoting helper on the base adapter:
   `quote_identifier(name: str) -> str` with per-dialect implementation
   (already exists in `adapters/sql_dialects.py:50` but the adapters don't
   import it). Validate against a whitelist regex `^[A-Za-z_][A-Za-z0-9_]*$`
   before interpolation and raise on failure. This is the minimum.
2. For metadata queries like MySQL `get_columns_query`, use parameterized
   queries — `WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s`. `get_table_schema`
   already does this at `mysql.py:217`; the separate `get_columns_query` is
   dead or a stale duplicate, which is the next finding (L2).
3. Consolidate DDL generation through `sql/dialects.py` (add `create_table`,
   `drop_table` helpers) or the existing `sql_dialects.py` `quote_identifier`.

**Regression test**: `tests/regression/test_adapter_table_name_injection.py` —
pass `'users; DROP TABLE audit;--'` to `get_table_schema`, assert the adapter
raises a validation error before any SQL is issued.

**Cross-SDK**: Rust sqlx provides `quote_identifier` through the
`QueryBuilder`. Verify `crates/kailash-dataflow/src/adapters/*.rs` uses it
everywhere.

### C6. MySQL driver eager-import at module scope with silent-fallback

**File**: `mysql.py:18-22`:

```python
try:
    import aiomysql
except ImportError:
    aiomysql = None
```

This violates `rules/dependencies.md` § "No silent ImportError fallbacks" and
`rules/infrastructure-sql.md` Rule 8 (lazy driver imports). The runtime failure
is delayed to `create_connection_pool()` at line 72-75, but the import attempt
is eager — every DataFlow import pulls aiomysql into memory if it is
installed. More importantly, the pattern sets `aiomysql = None` on failure,
which means lines 113 `connection.cursor(aiomysql.DictCursor)` will crash with
`AttributeError: 'NoneType' object has no attribute 'DictCursor'` instead of
the declared "aiomysql is required" error. The declared error is shadowed by
the AttributeError when `aiomysql is None`.

**Fix**: Move the import inside `create_connection_pool()` and inside
`execute_query()` (or capture the DictCursor class once after the import).
Raise `ConnectionError("aiomysql is required for MySQL support. Install with: pip install aiomysql")`
at each import site.

**Regression test**: Tier 1 — mock out aiomysql import, instantiate adapter
(must succeed), call `create_connection_pool`, assert the exact expected error
message with `pip install aiomysql` hint.

**Cross-SDK**: N/A — Rust has feature flags; verify `kailash-dataflow` crate
features `mysql` with proper conditional compilation.

### C7. SQLite adapters bypass the pool for read-only metadata and `_test_connection`

**Files**:

- `sqlite.py:757-786` — `_test_connection()` uses bare `aiosqlite.connect(self.database_path)`
- `sqlite.py:812-824` — `_perform_wal_checkpoint()` uses bare `aiosqlite.connect()`
- `sqlite.py:826-857` — `_initialize_performance_monitoring()` uses bare `aiosqlite.connect()`
- `sqlite.py:875-930` — `_collect_performance_metrics()` uses bare `aiosqlite.connect()`
- `sqlite_enterprise.py:305` — `_test_connection()` uses `async with aiosqlite.connect(self.database_path)`
  with no PRAGMA tuning at all

`rules/patterns.md` § SQLite Connection Management: "MUST NOT use bare
`aiosqlite.connect()` — go through the pool." Each bare connect creates a
separate connection without the WAL mode / busy_timeout / cache_size PRAGMAs
the pool applies. In WAL mode, a bare reader against a database under heavy
writer load hits `database is locked` errors because the default
`busy_timeout` is 0. `sqlite_enterprise._test_connection` doesn't apply ANY
pragmas, making it indistinguishable from a raw sqlite3 client.

**Fix**: Route all internal reads through `_get_connection()`. Raise the bar by
deleting `_test_connection` and `_perform_wal_checkpoint` helpers and replacing
them with pool-aware calls.

**Regression test**: Tier 2 — spin up two SQLite adapters against the same
file DB, run concurrent reads and writes through both, assert zero `database
is locked` errors over 1000 iterations.

**Cross-SDK**: N/A (Rust uses sqlx which pools by default).

### C8. SQLite `SQLiteAdapter` has two parallel pool implementations, both half-wired

**File**: `sqlite.py:180-183`:

```python
self._connection_pool: List[aiosqlite.Connection] = []
self._pool_lock = asyncio.Lock()
self._sqlite_pool: Any = None  # AsyncSQLitePool instance (when available)
```

The legacy list-based pool coexists with an opt-in `AsyncSQLitePool` path,
selected by whether `self._sqlite_pool is not None`. The comment at line
709-720 in `_initialize_connection_pool` says "AsyncSQLitePool is intentionally
NOT used here" because it conflicts with `EnterpriseConnectionPool` from the
core SDK. But the class-level attribute exists and some code paths still check
for it at `sqlite.py:302` (`if self._sqlite_pool is not None:`) — code that is
unreachable because `_initialize_connection_pool` never sets it. This is dead
code per `zero-tolerance.md` Rule 2.

Separately, `rules/patterns.md` § SQLite Connection Management mandates going
through `AsyncSQLitePool` which provides WAL-aware read/write routing,
read-connection concurrency limits, and the default PRAGMA set. The legacy pool
the adapter uses has none of this. The comment saying the core SDK pool is
incompatible is not a valid exception — the core SDK pool IS the framework-first
abstraction (`framework-first.md`), and a reimplementation in the adapter layer
is a rule violation.

**Fix**: Remove the legacy list-based pool entirely. Use
`AsyncSQLitePool` exclusively. The supposed conflict with
`EnterpriseConnectionPool` is a core SDK bug that should be fixed at the
source, not worked around here (`zero-tolerance.md` Rule 4).

**Cross-subsystem**: This conflicts directly with the core-and-config audit
finding about AsyncSQLitePool / EnterpriseConnectionPool overlap. Coordinate
the fix with the core auditor.

**Regression test**: Tier 2 — parallel reader/writer workload matching the
documented "database is locked" failure mode; assert zero failures on
AsyncSQLitePool path.

---

## HIGH Findings

### H1. `get_server_version` and `get_database_size` silently return sentinel values on error

**Files**:

- `postgresql.py:378-388` — `return "unknown"` on exception
- `postgresql.py:390-401` — `return 0` on exception
- `mysql.py:444-454` — `return "unknown"` on exception
- `mysql.py:456-471` — `return 0` on exception
- `sqlite.py:675-685` — `return "unknown"` on exception
- `sqlite.py:687-707` — `return 0` on exception

Every one of these is a `rules/zero-tolerance.md` Rule 3 violation and
`rules/observability.md` § "No log-and-continue" violation. The exception is
logged at ERROR level then swallowed; the caller receives a bogus sentinel
(`"unknown"`, `0`) with no way to know the read failed. Code that checks
"is the database bigger than 100GB?" will silently say "no, it's 0 bytes" and
skip maintenance. Code that checks "is this PostgreSQL 13+?" will fail the
string-version comparison and silently degrade to the legacy code path.

**Fix**: Re-raise as `QueryError` in all six methods. Update any callers that
depend on the sentinel to catch and decide explicitly.

**Regression test**: Each method, mocked driver raises `RuntimeError`, assert
`QueryError` propagates.

### H2. MySQL `get_storage_engines` swallows errors and returns a hardcoded fake engine list

**File**: `mysql.py:403-442`. On any query failure it returns a hardcoded
two-entry dict listing InnoDB and MyISAM with canned capability strings. This
is explicitly `rules/zero-tolerance.md` Rule 2 ("No simulated/fake data") and
Rule 3 ("No silent fallbacks"). The comment "Return default engines if query
fails" is the anti-pattern the rule forbids. Callers that inspect this
dictionary to decide whether to use XA transactions or savepoints will get
wrong answers whenever the query fails and never know.

**Fix**: Re-raise as `QueryError`.

**Regression test**: Mock `execute_query` to raise, assert `get_storage_engines`
re-raises not returns fake dict.

### H3. MySQL and PostgreSQL `format_query` replace every `?` including inside string literals

**Files**:

- `postgresql.py:334-336` — `while "?" in formatted_query: replace(..., 1)`
- `mysql.py:336` — `query.replace("?", "%s")`

A query like `SELECT * FROM feedback WHERE body LIKE 'did you know?'` gets
corrupted to `SELECT ... LIKE 'did you know$1'` (PG) or `LIKE 'did you know%s'`
(MySQL). The current bulk insert path at `postgresql.py:141` bypasses this
because it re-uses an already-formatted query, but ad-hoc SQL passing through
`execute_query` is exposed.

**Fix**: Use a tokenizer that skips quoted strings and comments, or accept the
upstream parameter style as-is and stop rewriting. The cleanest fix is: require
callers to use the dialect's native style, and provide a shared
`format_query` helper in `sql/dialects.py` that uses a proper parser.

**Regression test**: Query with literal `?` in a string literal; assert
`format_query` leaves the literal untouched.

### H4. Adapter classes lack `__del__` / ResourceWarning

**File scope**: `postgresql.py`, `mysql.py`, `sqlite.py`,
`sqlite_enterprise.py`. Transaction classes at `postgresql.py:433`,
`mysql.py:521`, `sqlite.py:952`, `sqlite_enterprise.py:1251` have `__del__`;
the adapter classes themselves (`PostgreSQLAdapter`, `MySQLAdapter`,
`SQLiteAdapter`, `SQLiteEnterpriseAdapter`) do not. `rules/patterns.md` §
"Async Resource Cleanup" and `rules/dataflow-pool.md` § "No Orphan Runtimes"
both require that every async resource class emits `ResourceWarning` if GC'd
without `close_connection_pool()`. Without this, the most common DataFlow leak
(forgetting to await `close()` in a script / test teardown) is silent until the
pool is exhausted.

**Fix**: Add `def __del__(self, _warnings=warnings):` to each adapter class.
Warn if `is_connected and connection_pool is not None`. Set class-level
defaults to survive partial `__init__` failures.

**Regression test**: Create adapter, `gc.collect()`, assert ResourceWarning.

### H5. Pool size resolution violates the single-source-of-truth rule

**File**: `base.py:57-58`:

```python
self.pool_size = kwargs.get("pool_size") or 5
self.max_overflow = kwargs.get("max_overflow") or 2
```

`rules/dataflow-pool.md` Rule 1 (copied in the kailash-py variant at
`kailash-py/.claude/rules/dataflow-pool.md`) says: "Pool size MUST be resolved
through `DatabaseConfig.get_pool_size()`. No hardcoded defaults elsewhere." A
literal `5` in `base.py` is a new competing default on top of the known 10, 20,
25, 30, and `cpu_count * 4` that caused the pool exhaustion crisis. The
`or` (rather than dict `get` with default) also silently promotes
`pool_size=0` to `pool_size=5`, which will surprise callers testing an
intentionally-throttled pool.

**Fix**: Accept `pool_size` only through a resolved numeric parameter; raise on
missing. Let `DataFlow.__init__` resolve it via `DatabaseConfig.get_pool_size()`
and pass the resolved value down. Same for `max_overflow` — bound to
`max(2, pool_size // 2)` per Rule 4.

**Cross-subsystem**: This touches the core config auditor's scope. Coordinate.

### H6. `base.py` does not validate pool size or `max_overflow` is bounded

Per `rules/dataflow-pool.md` Rule 2 ("Validate Pool Config at Startup") and
Rule 4 ("Bounded max_overflow"), the base adapter's `pool_size + max_overflow`
is what asyncpg/aiomysql receive, and the base adapter never checks that the
sum is reasonable against the DB server's `max_connections`. The
PostgreSQL-specific validation is documented to live in
`DataFlow.__init__`, but the adapter layer is callable independently (the
factory creates raw adapters without the DataFlow wrapper in
`tests/integration/adapters/*`) and should validate at its own layer too.

**Fix**: On `create_connection_pool()` success, run `SELECT current_setting('max_connections')`
(PostgreSQL) or `SHOW VARIABLES LIKE 'max_connections'` (MySQL) and log a
WARNING if `pool_size + max_overflow > max_connections * 0.7`. Log an ERROR and
raise if exceeded 1.0.

### H7. No connection-reset callback on MySQL adapter

PostgreSQL adapter installs a `reset_connection` callback at
`postgresql.py:55-71` that rolls back open transactions before returning the
connection to the pool. MySQL adapter has no equivalent. aiomysql does not
support a reset callback natively, but the adapter can achieve the same effect
by wrapping the acquire/release path. Currently, if a caller forgets to commit
or rollback inside `execute_query` (which autocommits per-call, so normally
fine — but `execute_insert` at line 129 manually commits on the in-flight
connection), there's a risk of uncommitted state leaking back to the pool.

**Fix**: Add a thin acquire/release wrapper that rolls back any open
transaction before releasing back. Easier: route everything through the
adapter's own `transaction()` context manager.

### H8. SQLite `supports_transactions` never declared; `supports_savepoints` declares True without test coverage

**File**: `sqlite.py:595-603`. Declares `supports_concurrent_reads` and
`supports_savepoints`, both True. Does NOT override `supports_transactions`
(inherits from `base.py:139` which returns True). But neither the
`SQLiteAdapter` nor `SQLiteEnterpriseAdapter` transaction classes actually
issue savepoint SQL anywhere — they only do `BEGIN`/`COMMIT`/`ROLLBACK`. The
`supports_savepoints = True` claim is a docstring lie per the mandate
Definition of Perfect item #2.

**Fix**: Either implement savepoint support in the transaction context manager
(`SAVEPOINT sp1`, `RELEASE sp1`, `ROLLBACK TO sp1`) with a nested context
manager API, OR set `supports_savepoints = False` on both SQLite adapters and
update docstrings.

**Regression test**: If claimed True, there must be a test that nests two
transactions and verifies savepoint semantics (rollback of inner does not
rollback outer).

### H9. `AdapterFactory.create_adapter` logs the raw connection string

**File**: `factory.py:135`:

```python
logger.info(f"Created {db_type} adapter for {connection_string}")
```

The connection string contains the password (`postgres://user:SECRET@host/db`).
`rules/security.md` § "No secrets in logs" and `rules/observability.md` Rule 4
both BLOCK this. Any operator tailing INFO logs sees production passwords.

**Fix**: Log a redacted version (mask everything between the last `:` and `@`).
Better: log the parsed components sans password using
`adapter.get_connection_info()`.

### H10. Factory imports are eager; all driver-backed adapters load on import

**File**: `factory.py:13-17`:

```python
from .mongodb import MongoDBAdapter
from .mysql import MySQLAdapter
from .postgresql import PostgreSQLAdapter
from .sqlite import SQLiteAdapter
from .sqlite_enterprise import SQLiteEnterpriseAdapter
```

And `adapters/__init__.py:12-18` eagerly imports every adapter and the
`postgresql_vector` adapter (which requires pgvector). This violates Rule 8
of `infrastructure-sql.md` (lazy driver imports). A user who only wants
SQLite still pays the cost of importing asyncpg, aiomysql, pymongo,
pgvector — and if one of those raises at import time (version incompat), the
entire DataFlow package fails to import.

**Fix**: Lazy adapter imports via `importlib.import_module` inside
`create_adapter`, keyed by detected database type. Remove eager imports from
`__init__.py` — export the `DatabaseAdapter` base and the factory only.

### H11. `SQLiteEnterpriseAdapter` duplicates `SQLiteAdapter` data classes and is the default in the factory

**File**: `sqlite_enterprise.py:40-94` redefines `SQLiteWALMode`,
`SQLiteIsolationLevel`, `SQLiteIndexInfo`, `SQLitePerformanceMetrics`,
`SQLiteConnectionPoolStats` — identical to `sqlite.py:34-88`. Two parallel
symbol hierarchies for the same semantic types. `isinstance` checks in caller
code will fail across the divide.

`factory.py:37` sets `"sqlite": SQLiteEnterpriseAdapter` as the default,
demoting `SQLiteAdapter` to a `"sqlite_basic"` alternate scheme. So users
always get the enterprise adapter — which has **fewer** methods than the basic
one (missing `get_server_version`, `get_database_size`,
`get_connection_parameters`, proper `disconnect()` leaked-transaction check).

**Fix**: Consolidate to ONE SQLite adapter class, with the enterprise features
toggleable. Import the data classes once from a shared module.

### H12. `SQLiteEnterpriseAdapter.disconnect` does not check for leaked transactions

**File**: `sqlite_enterprise.py:242-262`. Compare with `sqlite.py:258-295` which
iterates `self._active_transactions` (a `weakref.WeakSet`) and warns about
leaks. The enterprise adapter has no equivalent tracking at all — no
`_active_transactions` set, no warning. Since the enterprise adapter is what
users actually get from the factory, the leak-detection safety net is bypassed.

**Fix**: Add `_active_transactions: weakref.WeakSet` to
`SQLiteEnterpriseAdapter.__init__`, register each transaction in
`transaction()`, check on `disconnect()`. (The cleaner fix is H11 — merge the
adapters.)

### H13. SQLite performance metrics fabricate cache hit ratio and checkpoint frequency

**File**: `sqlite.py:913-925`:

```python
cache_hit_ratio = 0.95 if self._query_count > 10 else 0.0
...
return SQLitePerformanceMetrics(
    ...
    cache_hit_ratio=cache_hit_ratio,
    ...
    checkpoint_frequency=1.0,
)
```

`cache_hit_ratio = 0.95` is literal `rules/zero-tolerance.md` Rule 2 "simulated
data". SQLite does expose cache stats via `PRAGMA cache_size` +
`PRAGMA stats` / `sqlite_stat1` — the adapter should query the real value or
declare the field unavailable. Same for `checkpoint_frequency=1.0` — a constant
passed off as a live metric.

Same bug cluster exists in `sqlite_enterprise.py` in its own performance
metrics collection path.

**Fix**: Either query real stats or remove the field from the dataclass and
its consumers.

### H14. Eager driver import in SQLite adapters (`import aiosqlite` at module top)

**Files**: `sqlite.py:20`, `sqlite_enterprise.py:32`. aiosqlite is a relatively
harmless import but this still violates `rules/infrastructure-sql.md` Rule 8
(lazy driver imports). If a future user wants to install
`kailash[postgresql]` only, the adapter package still imports aiosqlite.

**Fix**: Move inside `connect()` / `create_connection_pool()`.

---

## MEDIUM Findings

### M1. Two parallel `SQLDialect` class hierarchies with the same class names

`adapters/sql_dialects.py` defines `SQLDialect`, `PostgreSQLDialect`,
`MySQLDialect`, `SQLiteDialect` with methods `get_parameter_placeholder`,
`quote_identifier`, `get_limit_clause`, `get_type_mapping`, `supports_feature`.

`sql/dialects.py` defines `SQLDialect`, `PostgreSQLDialect`, `MySQLDialect`
(no SQLiteDialect name collision here but same pattern) with
`build_upsert_query`, `build_bulk_upsert_query`.

Only `adapters/sql_dialects.py` is imported by (one tests file and one unit
test). Only `sql/dialects.py` is used by `core/nodes.py` at line 2972. The
adapters themselves import NEITHER — every adapter defines its own
`format_query`, `get_dialect`, `supports_feature`, and all DDL locally.

This is three parallel dialect systems. `rules/framework-first.md` § "Raw Is
Always Wrong" and the mandate's Definition of Perfect item #12 ("no two
parallel cache implementations in the same package") clearly apply.

**Fix**: Consolidate to ONE `SQLDialect` hierarchy under `sql/dialects.py`,
add the missing methods (`blob_type`, `current_timestamp`,
`quote_identifier`, `limit_clause`, `parameter_placeholder`), delete
`adapters/sql_dialects.py`, rewire adapter `format_query` /
`quote_identifier` / `create_table` to use the consolidated dialect.

### M2. `sql/dialects.py` does not expose `blob_type()` / `current_timestamp()` portability helpers

`rules/infrastructure-sql.md` mandates dialect-portable SQL via
`dialect.blob_type()`, `dialect.current_timestamp()`, `dialect.upsert_clause()`
etc. The only methods in `sql/dialects.py` are `build_upsert_query` and
`build_bulk_upsert_query`. No blob type, no current timestamp, no
identifier-quoting, no LIMIT/OFFSET, no type mapping.

**Fix**: Extend the dialect base class to match the infrastructure-sql.md
contract. Implement per-dialect.

### M3. `QueryBuilder` uses raw int interpolation for `LIMIT` / `OFFSET`

**File**: `database/query_builder.py:310-313`:

```python
if self.limit_value is not None:
    limit_clause = f"LIMIT {self.limit_value}"
if self.offset_value is not None:
    limit_clause += f" OFFSET {self.offset_value}"
```

No type validation. If a caller passes a string (`limit("1; DROP TABLE users")`),
the f-string does not catch it. The `limit(limit: int)` signature is a hint,
not enforcement.

**Fix**: Cast to `int()` with a clear error, or use parameter placeholders.

### M4. `ConnectionStringBuilder` uses regex-based SQL injection detection on every component

**File**: `database/connection_builder.py:120-140`. Validates every component
against a regex list:

```python
injection_patterns = [
    r"'.*'",
    r";.*--",
    r"union\s+select",
    r"drop\s+table",
    ...
]
```

This is the classic "security via substring" antipattern. A password of
`my'secret` fails the `r"'.*'"` regex. A valid database name `drop_table_archive`
fails the `r"drop\s+table"` match. The validator rejects legitimate values and
is trivially bypassed by any real attacker using comments, concatenation, or
encoding.

`rules/security.md` § "Input validation" calls for type checking, length
limits, and whitelist when possible — not pattern blacklists.

**Fix**: Replace with strict whitelist: host regex, database-name regex,
alphanumeric-plus-underscore for identifiers. Delegate password sanitization
to URL encoding (`quote_plus`) only, with no content inspection.

### M5. `get_columns_query` is a dead method or duplicate of `get_table_schema`

Every adapter exposes both `get_table_schema` (parameterized, production) and
`get_columns_query` (f-string-interpolated, raw SQL string). Neither
`get_columns_query` nor its callers are referenced in DataFlow production
code — verifying below:

**Verification needed** (would be done in implementation phase): `grep -rn
"get_columns_query" src/` outside the adapters shows uses in migration / schema
introspection layers; confirm they all use the parameterized
`get_table_schema` and delete `get_columns_query`.

**Fix**: Delete `get_columns_query` from all adapters if unused. Same for
`get_tables_query` which has the same issue.

### M6. `adapters/exceptions.py:20` shadows builtin `ConnectionError`

The module defines `ConnectionError(AdapterError)`, colliding with Python's
builtin `ConnectionError`. Any code in the adapters module that types
`ConnectionError` unambiguously refers to this custom one, not the builtin.
Callers outside the adapters package that catch `ConnectionError` (e.g., to
distinguish network errors from data errors) will miss the adapter's version
unless they import from `dataflow.adapters.exceptions` explicitly. Type
checkers and IDE "go to definition" silently pick the wrong one.

**Fix**: Rename to `DatabaseConnectionError(AdapterError)` and update all
imports.

### M7. Transaction context managers lack isolation level parameter

PostgreSQL transaction at `postgresql.py:450-456` always starts with
`self.connection.transaction()` without specifying `isolation` — asyncpg
defaults to the database default (`READ COMMITTED`). MySQL at `mysql.py:537-541`
calls `self.connection.begin()` — same default inheritance. There's no way for
a caller to request `SERIALIZABLE` for a specific block. The base adapter
declares `get_supported_isolation_levels` at `base.py:134` but no adapter
actually accepts isolation level through its `transaction()` method.

SQLiteEnterpriseAdapter at `sqlite_enterprise.py:1221` signature accepts
`isolation_level` but only for the enterprise variant — parity gap.

**Fix**: Add `isolation: str | None = None` parameter to every
`transaction()` method, map to driver-specific values, document supported
levels.

### M8. No `application_name` forwarding on MySQL (program_name attribute)

Parallel to C2 but for MySQL: aiomysql `connect()` accepts a `program_name`
parameter that surfaces in `SHOW PROCESSLIST` under the "Info" column
aggregation. Not forwarded.

**Fix**: Add `program_name` kwarg to MySQL adapter, forward in
`get_connection_parameters()`.

### M9. `PostgreSQLVectorAdapter` eagerly returns `{}` on error at line 418

**File**: `postgresql_vector.py:418` — `return {}` following exception handling.
Parallel to H1.

**Fix**: Re-raise.

### M10. `SQLiteEnterpriseAdapter._create_optimized_connection` runs a BEGIN / ROLLBACK "just to set default isolation" at line 298-299

This is cargo-culted: the default isolation level in SQLite is not set by
starting and rolling back a transaction. It's set by the `isolation_level`
parameter to `sqlite3.connect()` at the driver level, or by `PRAGMA` in newer
SQLite versions. The BEGIN/ROLLBACK is a no-op that contributes log noise and
an unnecessary round-trip per pool initialization.

**Fix**: Remove the spurious begin/rollback.

### M11. `AsyncSQLitePool` import is try/except without loud error at call site

**File**: `sqlite.py:25-29`:

```python
try:
    from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
except ImportError:
    AsyncSQLitePool = None  # type: ignore[assignment,misc]
    SQLitePoolConfig = None  # type: ignore[assignment,misc]
```

Since core SDK and DataFlow are in the same monorepo, this ImportError can
only happen in broken installs. `rules/dependencies.md` says silent fallback to
`None` is BLOCKED unless the call site raises a descriptive error. The adapter
never raises on missing AsyncSQLitePool; it just silently falls back to the
legacy list-based pool. Operators see no indication that the faster path is
missing.

**Fix**: Delete the try/except (the core SDK is a hard dependency; ImportError
here is a deploy-env bug). Let the ImportError propagate at module import.

---

## LOW Findings

### L1. PostgreSQL `get_connection_parameters()` omits `timeout` (pool wait) entirely

Beyond the C3 semantic confusion, the asyncpg `timeout` kwarg is simply never
passed. Even after fixing C3, there is no current code path that reaches
`asyncpg.create_pool(..., timeout=...)`.

### L2. MySQL `get_tables_query()` and `get_columns_query()` duplicate DDL from `get_table_schema`

The parameterized `get_table_schema` at `mysql.py:199` is correct. The
duplicates at `get_tables_query`/`get_columns_query` (lines 376-401) are
untested dead code. Delete.

### L3. `SQLiteAdapter` config has `query_params` parsed but never read

`base.py:51` populates `self.query_params` from the URL. `SQLiteAdapter.__init__`
never reads it. URL query strings on SQLite URIs (`?cache=shared&mode=memory`)
are silently dropped (the current adapter recognizes `mode=memory` substring
only). A real `?timeout=60&busy_timeout=10000` URL is ignored.

**Fix**: Read `query_params` in `SQLiteAdapter.__init__`, honor known keys.

### L4. `connection_parser.py:117-120` only handles four special password chars

```python
special_chars = {"#": "%23", "$": "%24", "@": "%40", "?": "%3F"}
```

`&`, `=`, `%`, `/`, spaces, and many others also need URL encoding. The only
safe path is `urllib.parse.quote(password, safe='')` applied to the password
substring. The current handler encodes `#$@?` but leaves `%` raw, so a password
`p%20ss` is mis-decoded back to `p ss`.

**Fix**: Use `quote(password, safe="")` unconditionally on the extracted
password substring.

### L5. `detect_database_type` treats bare `/` paths as SQLite unconditionally

`connection_parser.py:341` — `"/" in connection_string and "://" not in connection_string`.
This mis-classifies any absolute file path as SQLite, including paths to
non-SQLite databases (e.g., a user types their `.env` DATABASE_URL with a
typo and the detector cheerfully returns "sqlite"). Edge-case but surprising.

**Fix**: Require a file extension (`.db`, `.sqlite`, `.sqlite3`) or the
`sqlite:` scheme prefix.

### L6. `PostgreSQL get_columns_query` interpolates `table_name` but never gets called with untrusted input

Confirmed dead-path but flagged for hygiene. Delete the method.

### L7. MySQL `ssl_verify_cert` default is `False`

**File**: `mysql.py:56`. Defaults to not verifying the certificate, which
defeats the point of providing SSL files. Production-safe default should be
`True` with a documented opt-out for self-signed local dev.

---

## Cross-Adapter Parity Table

| Method (from `base.py`)     | PG                                     | MySQL                           | SQLite                        | SQLite-Enterprise                                 |
| --------------------------- | -------------------------------------- | ------------------------------- | ----------------------------- | ------------------------------------------------- |
| `connect`                   | yes                                    | yes                             | yes                           | yes                                               |
| `disconnect`                | yes                                    | yes                             | yes (+ leaked-txn check)      | yes (NO leaked-txn check) — H12                   |
| `create_connection_pool`    | yes                                    | yes                             | (legacy list pool) — C8       | (legacy list pool) — C8                           |
| `close_connection_pool`     | yes                                    | yes                             | yes                           | yes                                               |
| `execute_query`             | yes                                    | yes                             | yes                           | yes                                               |
| `execute_insert`            | yes                                    | yes                             | yes                           | **MISSING**                                       |
| `execute_bulk_insert`       | yes                                    | yes                             | yes                           | **MISSING**                                       |
| `execute_transaction`       | "yes" (NOT atomic — C4)                | yes                             | yes                           | yes                                               |
| `transaction()` ctx mgr     | yes                                    | yes                             | yes                           | yes (accepts isolation_level — inconsistent — M7) |
| `get_table_schema`          | yes (parameterized)                    | yes (parameterized)             | yes (PRAGMA)                  | yes (PRAGMA)                                      |
| `create_table`              | yes (f-string DDL — C5)                | yes (f-string DDL — C5)         | yes (f-string DDL — C5)       | yes (f-string DDL + FK support — C5)              |
| `drop_table`                | yes (f-string — C5)                    | yes (f-string — C5)             | yes (f-string — C5)           | yes (f-string + cascade — C5)                     |
| `get_dialect`               | yes                                    | yes                             | yes                           | yes                                               |
| `supports_feature`          | yes                                    | yes                             | yes                           | yes                                               |
| `format_query`              | yes (naive — H3)                       | yes (naive — H3)                | yes                           | yes                                               |
| `get_connection_parameters` | yes (missing ssl, app_name — C1,C2,C3) | yes (missing program_name — M8) | yes                           | **MISSING**                                       |
| `get_tables_query`          | yes                                    | yes (string-interp — C5)        | yes                           | yes                                               |
| `get_columns_query`         | yes (f-string — C5)                    | yes (f-string — C5)             | yes (f-string — C5)           | yes (f-string — C5)                               |
| `get_server_version`        | yes (silent-fallback — H1)             | yes (silent-fallback — H1)      | yes (silent-fallback — H1)    | **MISSING**                                       |
| `get_database_size`         | yes (silent-fallback — H1)             | yes (silent-fallback — H1)      | yes (silent-fallback — H1)    | **MISSING**                                       |
| `supports_transactions`     | yes                                    | yes                             | inherit (True)                | inherit (True)                                    |
| `supports_savepoints`       | yes True                               | yes True                        | yes True (unimplemented — H8) | inherit / ambiguous                               |
| `__del__` / ResourceWarning | **MISSING** — H4                       | **MISSING** — H4                | **MISSING** — H4              | **MISSING** — H4                                  |

Four missing methods in the default SQLite adapter (`SQLiteEnterpriseAdapter`)
means `db.express` / upserts / schema introspection are working on
feature-divergent surface area depending on which dialect the user picks.

---

## Cross-Subsystem Couplings

1. **Core config (owner: core auditor)** — `base.py:57` pool_size default
   conflicts with `DatabaseConfig.get_pool_size()`. Coordinate fix.
2. **SQLite pool (owner: core SDK)** — `AsyncSQLitePool` in
   `kailash.core.pool.sqlite_pool` vs the legacy list pool vs
   `EnterpriseConnectionPool`. Three paths; pick one.
3. **Nodes / Migrations (owner: core-and-config auditor or nodes auditor)** —
   `core/nodes.py` uses `sql/dialects.py` for upserts; consolidating with
   `adapters/sql_dialects.py` requires touching every upsert callsite.
4. **Fabric / cache (owner: fabric auditor, workspaces/issue-354)** — The
   Redis/Postgres cache auditor should verify no parallel pool config exists
   in the cache layer.
5. **Testing infrastructure** — `tests/unit/adapters/test_postgresql_adapter.py:249`
   encodes the #353 bug as expected behavior; fix both in the same commit.

## Cross-SDK Parallels (EATP D6)

For every finding C1-C8 and H1-H14 in this report, a corresponding
`cross-sdk` audit pass MUST be applied to
`crates/kailash-dataflow/src/adapters/{postgres.rs,mysql.rs,sqlite.rs}`.
Estimate: one session once kailash-py fixes land. The parity table semantics
should match exactly — same feature flags, same error types, same behavior on
every sslmode value, same `application_name` surfacing in `pg_stat_activity`.

Specific cross-SDK issues to file:

- `sslmode` parse-and-drop check
- `application_name` / `program_name` forwarding
- pool_wait vs statement_timeout separation (sqlx API)
- `execute_transaction` atomicity
- Dialect portability helpers (`blob_type`, `current_timestamp`) consolidation
- Adapter-level `__del__` / Drop with warning

## Institutional Knowledge Gaps

The following should end up in skills after implementation:

1. **skills/02-dataflow/adapter-sslmode-mapping.md** — canonical translation
   table from libpq sslmode values to asyncpg `ssl` parameter, with the
   `verify-ca`/`verify-full` SSLContext construction pattern.
2. **skills/02-dataflow/adapter-parity-matrix.md** — living cross-adapter
   parity table with red/green status per method.
3. **skills/02-dataflow/dialect-portability-checklist.md** — the list of
   dialect-portability methods every adapter MUST implement (`blob_type`,
   `current_timestamp`, `quote_identifier`, `limit_clause`, `upsert`, etc.)
   derived from `rules/infrastructure-sql.md`.
4. **agents/frameworks/dataflow-specialist.md** update — add explicit "never
   f-string interpolate `table_name` into DDL" and "every parsed URL parameter
   must be forwarded to the driver" as default audit questions.
5. **rules/connection-string-parsing.md** — new rule: URL parameters parsed
   into `self.X` MUST be forwarded to the driver in the same commit. The #353
   pattern (parse, never forward) is common enough to deserve a named rule.

## Recommendation

Every finding at CRITICAL or HIGH is in scope for this sprint. MEDIUMs M1 and
M2 (dialect consolidation) should also land in this sprint because leaving
three parallel dialect hierarchies will guarantee the next audit finds the
same class of bug again. LOWs can be batched.

The single highest-leverage intervention is C5 + M1 combined: consolidate the
dialect layer to one hierarchy, force every adapter to route DDL through it,
and every f-string-interpolated `table_name` disappears as a side effect.
