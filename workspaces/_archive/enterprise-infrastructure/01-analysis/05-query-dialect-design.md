# QueryDialect Abstraction Design & Env Var Strategy

**Date**: 2026-03-17
**Analyst**: deep-analyst
**Complexity Score**: 24 (Complex) -- Governance=4, Legal=2, Strategic=18
**Workspace**: enterprise-infrastructure
**Inputs**: `briefs/01-project-brief.md`, `briefs/02-multi-database-strategy.md`, `01-analysis/02-deep-analysis.md`, `01-analysis/04-requirements.md`, source code inspection

---

## Executive Summary

The QueryDialect abstraction should be a **strategy-pattern class hierarchy** (`PostgresDialect`, `MySQLDialect`, `SQLiteDialect`) living in a new `src/kailash/db/` package, complementing -- not replacing -- the existing `DatabaseDialect` enum in `query_builder.py`. The env var recommendation is a **three-variable model**: `KAILASH_DATABASE_URL` (infrastructure stores, with `DATABASE_URL` fallback), `KAILASH_QUEUE_URL` (task queue broker), and `KAILASH_REDIS_URL` (Redis services). This balances ergonomics (most users set one variable) against collision safety (DataFlow users need separate databases).

**Key decision**: Do NOT use SQLAlchemy's dialect abstraction as the QueryDialect. SQLAlchemy handles connection management and basic SQL generation well, but it does not abstract advisory locks, SKIP LOCKED fallback semantics, JSON operator differences, or upsert syntax into a single API. The QueryDialect is the **thin layer above SQLAlchemy** that handles these dialect-specific operations, so that store implementations can call `dialect.upsert(table, values, conflict_keys)` and get the correct SQL for any backend.

---

## Part 1: QueryDialect Class Design

### 1.1 Architecture Evaluation

Three approaches were evaluated:

**Approach A: Single class with methods per operation**

```python
class QueryDialect:
    def __init__(self, dialect_name: str): ...
    def placeholder(self, index: int) -> str: ...
    def upsert(self, table, values, conflict_keys) -> str: ...
```

Pros: Simple, one class to test. Cons: Every method becomes an if/elif chain that grows with each dialect. Violates Open/Closed Principle -- adding Oracle or DuckDB requires modifying every method. Testability is poor because you cannot test a single dialect in isolation.

**Approach B: Strategy pattern with dialect subclasses**

```python
class QueryDialect(ABC):
    @abstractmethod
    def placeholder(self, index: int) -> str: ...

class PostgresDialect(QueryDialect): ...
class MySQLDialect(QueryDialect): ...
class SQLiteDialect(QueryDialect): ...
```

Pros: Each dialect is a self-contained class. Adding a new dialect means adding one file. Each dialect can be tested in isolation. Cons: More files, more boilerplate for the three-dialect case.

**Approach C: Functional approach with dialect-specific translation functions**

```python
def pg_placeholder(index: int) -> str: ...
def mysql_placeholder(index: int) -> str: ...
DIALECTS = {"postgresql": {"placeholder": pg_placeholder, ...}}
```

Pros: Minimal. Cons: No type safety, no IDE completion, no protocol enforcement. Easy to forget a function when adding a dialect. Not how kailash-py writes code (the SDK is class-oriented with Protocol contracts).

**Recommendation: Approach B (Strategy Pattern)**

This aligns with:

- kailash-rs's strategy pattern for the same abstraction
- The existing `EventStoreBackend(Protocol)` and `StorageBackend(Protocol)` patterns throughout kailash-py
- The Open/Closed Principle (new dialects = new files, no existing code modified)
- The existing `DatabaseDialect` enum in `query_builder.py` already identifies the three dialects; the strategy classes provide the behavior

### 1.2 Class Hierarchy

```python
# src/kailash/db/dialect.py

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "DialectName",
    "QueryDialect",
    "PostgresDialect",
    "MySQLDialect",
    "SQLiteDialect",
    "detect_dialect",
    "get_dialect",
]


class DialectName(Enum):
    """Supported database dialects."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class QueryDialect(ABC):
    """Abstract base for database dialect translations.

    Provides the dialect-specific SQL fragments that differ between
    PostgreSQL, MySQL 8.0+, and SQLite. Each method returns SQL text
    or fragments that callers compose into full queries.

    All returned SQL uses parameterized placeholders -- never string
    interpolation of user values.
    """

    @property
    @abstractmethod
    def name(self) -> DialectName: ...

    # ----------------------------------------------------------------
    # Placeholder translation
    # ----------------------------------------------------------------

    @abstractmethod
    def placeholder(self, index: int) -> str:
        """Return the parameter placeholder for the given 1-based index.

        Args:
            index: 1-based parameter position.

        Returns:
            Placeholder string (e.g., "$1", "%s", "?").
        """
        ...

    def placeholders(self, count: int) -> List[str]:
        """Return a list of placeholders for count parameters."""
        return [self.placeholder(i) for i in range(1, count + 1)]

    def translate_query(self, canonical_sql: str) -> str:
        """Translate a query written with '?' placeholders to this dialect.

        The canonical form uses '?' for all placeholders. This method
        replaces them with dialect-specific placeholders in left-to-right
        order.

        Args:
            canonical_sql: SQL with '?' placeholders.

        Returns:
            SQL with dialect-specific placeholders.
        """
        index = 0
        parts = canonical_sql.split("?")
        result = []
        for i, part in enumerate(parts):
            result.append(part)
            if i < len(parts) - 1:
                index += 1
                result.append(self.placeholder(index))
        return "".join(result)

    # ----------------------------------------------------------------
    # Upsert
    # ----------------------------------------------------------------

    @abstractmethod
    def upsert_sql(
        self,
        table: str,
        columns: Sequence[str],
        conflict_keys: Sequence[str],
        update_columns: Optional[Sequence[str]] = None,
    ) -> str:
        """Generate an upsert (INSERT or UPDATE on conflict) statement.

        Args:
            table: Table name (must be a validated identifier).
            columns: All columns in the INSERT.
            conflict_keys: Column(s) that define the conflict target
                           (unique/primary key).
            update_columns: Columns to update on conflict. If None,
                            updates all non-conflict columns.

        Returns:
            Parameterized SQL string with dialect-appropriate placeholders.
        """
        ...

    # ----------------------------------------------------------------
    # JSON columns
    # ----------------------------------------------------------------

    @property
    @abstractmethod
    def json_column_type(self) -> str:
        """SQL type for JSON storage: 'JSONB', 'JSON', or 'TEXT'."""
        ...

    @abstractmethod
    def json_extract(self, column: str, path: str) -> str:
        """SQL expression to extract a value from a JSON column.

        Args:
            column: Column name containing JSON.
            path: JSON path key (single level, e.g., 'status').

        Returns:
            SQL expression string.
        """
        ...

    @abstractmethod
    def json_contains(self, column: str, value_placeholder: str) -> str:
        """SQL expression for JSON containment check.

        Args:
            column: Column name containing JSON.
            value_placeholder: Placeholder for the JSON value to check.

        Returns:
            SQL expression string.
        """
        ...

    # ----------------------------------------------------------------
    # Locking
    # ----------------------------------------------------------------

    @abstractmethod
    def for_update_skip_locked(self) -> str:
        """SQL clause for row-level locking with skip.

        Returns:
            SQL fragment (e.g., 'FOR UPDATE SKIP LOCKED') or empty
            string if not supported.
        """
        ...

    @property
    @abstractmethod
    def supports_skip_locked(self) -> bool:
        """Whether this dialect supports FOR UPDATE SKIP LOCKED."""
        ...

    @abstractmethod
    def begin_immediate(self) -> Optional[str]:
        """SQL for immediate transaction locking (SQLite alternative).

        Returns:
            SQL statement or None if not applicable.
        """
        ...

    # ----------------------------------------------------------------
    # Advisory locks
    # ----------------------------------------------------------------

    @abstractmethod
    def advisory_lock_sql(self, lock_key: int) -> str:
        """SQL to acquire an advisory lock for the given key.

        Args:
            lock_key: Integer key identifying the lock.

        Returns:
            SQL statement string. May be empty for dialects without
            advisory lock support (SQLite).
        """
        ...

    @abstractmethod
    def advisory_unlock_sql(self, lock_key: int) -> str:
        """SQL to release an advisory lock for the given key.

        Returns:
            SQL statement string. May be empty for SQLite.
        """
        ...

    @property
    @abstractmethod
    def supports_advisory_locks(self) -> bool:
        """Whether this dialect supports advisory locks."""
        ...

    # ----------------------------------------------------------------
    # Timestamp handling
    # ----------------------------------------------------------------

    @abstractmethod
    def now_expression(self) -> str:
        """SQL expression for the current timestamp.

        Returns:
            'NOW()' for PG/MySQL, "datetime('now')" for SQLite.
        """
        ...

    @property
    @abstractmethod
    def timestamp_type(self) -> str:
        """SQL type for timestamp with timezone.

        Returns:
            'TIMESTAMPTZ' for PG, 'DATETIME' for MySQL, 'TEXT' for SQLite.
        """
        ...
```

### 1.3 PostgreSQL Dialect

```python
class PostgresDialect(QueryDialect):
    """PostgreSQL dialect (9.5+ for ON CONFLICT, 9.6+ for SKIP LOCKED)."""

    @property
    def name(self) -> DialectName:
        return DialectName.POSTGRESQL

    def placeholder(self, index: int) -> str:
        return f"${index}"

    def upsert_sql(
        self,
        table: str,
        columns: Sequence[str],
        conflict_keys: Sequence[str],
        update_columns: Optional[Sequence[str]] = None,
    ) -> str:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        col_list = ", ".join(columns)
        ph_list = ", ".join(self.placeholders(len(columns)))
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in update_columns
        )

        return (
            f"INSERT INTO {table} ({col_list}) VALUES ({ph_list}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )

    @property
    def json_column_type(self) -> str:
        return "JSONB"

    def json_extract(self, column: str, path: str) -> str:
        return f"{column}->>{self.placeholder(1)}"
        # NOTE: Callers must manage placeholder indexing externally.
        # This returns the operator form. For composed queries, use
        # the raw operator: f"{column}->>'key'" with literal key.

    def json_contains(self, column: str, value_placeholder: str) -> str:
        return f"{column} @> {value_placeholder}"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    @property
    def supports_skip_locked(self) -> bool:
        return True

    def begin_immediate(self) -> Optional[str]:
        return None

    def advisory_lock_sql(self, lock_key: int) -> str:
        return f"SELECT pg_advisory_lock({lock_key})"

    def advisory_unlock_sql(self, lock_key: int) -> str:
        return f"SELECT pg_advisory_unlock({lock_key})"

    @property
    def supports_advisory_locks(self) -> bool:
        return True

    def now_expression(self) -> str:
        return "NOW()"

    @property
    def timestamp_type(self) -> str:
        return "TIMESTAMPTZ"
```

### 1.4 MySQL Dialect

```python
class MySQLDialect(QueryDialect):
    """MySQL 8.0+ dialect (required for SKIP LOCKED, JSON, CTEs)."""

    @property
    def name(self) -> DialectName:
        return DialectName.MYSQL

    def placeholder(self, index: int) -> str:
        # MySQL uses positional %s, but index is ignored
        return "%s"

    def upsert_sql(
        self,
        table: str,
        columns: Sequence[str],
        conflict_keys: Sequence[str],
        update_columns: Optional[Sequence[str]] = None,
    ) -> str:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        col_list = ", ".join(columns)
        ph_list = ", ".join(self.placeholders(len(columns)))
        update_set = ", ".join(
            f"{c} = VALUES({c})" for c in update_columns
        )

        return (
            f"INSERT INTO {table} ({col_list}) VALUES ({ph_list}) "
            f"ON DUPLICATE KEY UPDATE {update_set}"
        )

    @property
    def json_column_type(self) -> str:
        return "JSON"

    def json_extract(self, column: str, path: str) -> str:
        return f"JSON_EXTRACT({column}, '$.{path}')"

    def json_contains(self, column: str, value_placeholder: str) -> str:
        return f"JSON_CONTAINS({column}, {value_placeholder})"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    @property
    def supports_skip_locked(self) -> bool:
        return True

    def begin_immediate(self) -> Optional[str]:
        return None

    def advisory_lock_sql(self, lock_key: int) -> str:
        # MySQL advisory locks use string names and timeout.
        # Using a 10-second timeout to avoid indefinite blocking.
        return f"SELECT GET_LOCK('kailash_lock_{lock_key}', 10)"

    def advisory_unlock_sql(self, lock_key: int) -> str:
        return f"SELECT RELEASE_LOCK('kailash_lock_{lock_key}')"

    @property
    def supports_advisory_locks(self) -> bool:
        return True

    def now_expression(self) -> str:
        return "NOW()"

    @property
    def timestamp_type(self) -> str:
        return "DATETIME(6)"
```

### 1.5 SQLite Dialect

```python
class SQLiteDialect(QueryDialect):
    """SQLite dialect (3.24+ for upsert, WAL mode recommended)."""

    @property
    def name(self) -> DialectName:
        return DialectName.SQLITE

    def placeholder(self, index: int) -> str:
        return "?"

    def upsert_sql(
        self,
        table: str,
        columns: Sequence[str],
        conflict_keys: Sequence[str],
        update_columns: Optional[Sequence[str]] = None,
    ) -> str:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        col_list = ", ".join(columns)
        ph_list = ", ".join(self.placeholders(len(columns)))
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(
            f"{c} = excluded.{c}" for c in update_columns
        )

        return (
            f"INSERT INTO {table} ({col_list}) VALUES ({ph_list}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )

    @property
    def json_column_type(self) -> str:
        return "TEXT"

    def json_extract(self, column: str, path: str) -> str:
        return f"json_extract({column}, '$.{path}')"

    def json_contains(self, column: str, value_placeholder: str) -> str:
        # SQLite has no native containment operator.
        # Use json_each + comparison. Callers needing this should
        # fall back to application-level filtering for complex cases.
        return f"json_extract({column}, '$') = {value_placeholder}"

    def for_update_skip_locked(self) -> str:
        # SQLite has no row-level locking. Return empty string.
        # Callers must check supports_skip_locked and use
        # begin_immediate() as the alternative.
        return ""

    @property
    def supports_skip_locked(self) -> bool:
        return False

    def begin_immediate(self) -> Optional[str]:
        return "BEGIN IMMEDIATE"

    def advisory_lock_sql(self, lock_key: int) -> str:
        # SQLite has no advisory locks. File-level locking is
        # handled by the connection itself. Return empty string.
        return ""

    def advisory_unlock_sql(self, lock_key: int) -> str:
        return ""

    @property
    def supports_advisory_locks(self) -> bool:
        return False

    def now_expression(self) -> str:
        return "datetime('now')"

    @property
    def timestamp_type(self) -> str:
        return "TEXT"
```

### 1.6 Auto-Detection and Factory

```python
# URL parsing regex: scheme://... or scheme+driver://... or file path
_PG_PREFIXES = ("postgresql://", "postgres://", "postgresql+")
_MYSQL_PREFIXES = ("mysql://", "mysql+")
_SQLITE_PREFIXES = ("sqlite://", "sqlite+", "sqlite:///")

# Singleton dialect instances (immutable, safe to share)
_DIALECTS: Dict[DialectName, QueryDialect] = {
    DialectName.POSTGRESQL: PostgresDialect(),
    DialectName.MYSQL: MySQLDialect(),
    DialectName.SQLITE: SQLiteDialect(),
}


def detect_dialect(url: str) -> DialectName:
    """Detect the database dialect from a connection URL.

    Args:
        url: Database connection URL or file path.

    Returns:
        The detected DialectName.

    Raises:
        ValueError: If the URL scheme is unrecognized.

    Examples:
        detect_dialect("postgresql://localhost/db")    -> POSTGRESQL
        detect_dialect("postgres://localhost/db")      -> POSTGRESQL
        detect_dialect("postgresql+asyncpg://...")     -> POSTGRESQL
        detect_dialect("mysql://localhost/db")         -> MYSQL
        detect_dialect("mysql+aiomysql://...")         -> MYSQL
        detect_dialect("sqlite:///path/to/db.sqlite")  -> SQLITE
        detect_dialect("sqlite+aiosqlite:///...")      -> SQLITE
        detect_dialect("/path/to/file.db")             -> SQLITE
        detect_dialect("kailash.db")                   -> SQLITE
    """
    url_lower = url.lower().strip()

    if any(url_lower.startswith(p) for p in _PG_PREFIXES):
        return DialectName.POSTGRESQL
    if any(url_lower.startswith(p) for p in _MYSQL_PREFIXES):
        return DialectName.MYSQL
    if any(url_lower.startswith(p) for p in _SQLITE_PREFIXES):
        return DialectName.SQLITE

    # Bare file paths (no scheme) are treated as SQLite
    if url_lower.endswith((".db", ".sqlite", ".sqlite3")):
        return DialectName.SQLITE
    if url_lower.startswith("/") or url_lower.startswith("./"):
        return DialectName.SQLITE

    raise ValueError(
        f"Cannot detect database dialect from URL: {url!r}. "
        f"Expected postgresql://, mysql://, sqlite:/// or a file path."
    )


def get_dialect(url_or_name: str) -> QueryDialect:
    """Get a QueryDialect instance from a URL or dialect name.

    Args:
        url_or_name: Either a connection URL (auto-detected) or
                     a dialect name ('postgresql', 'mysql', 'sqlite').

    Returns:
        Singleton QueryDialect instance for the detected dialect.
    """
    # Check if it is a dialect name directly
    try:
        dialect_name = DialectName(url_or_name.lower())
    except ValueError:
        # Not a dialect name -- try URL detection
        dialect_name = detect_dialect(url_or_name)

    return _DIALECTS[dialect_name]
```

### 1.7 Relationship to Existing `DatabaseDialect` Enum

The existing `DatabaseDialect` enum in `src/kailash/nodes/data/query_builder.py` serves the DataFlow `QueryBuilder` class for user-facing MongoDB-style query translation. It should NOT be modified or replaced. The reasons:

1. `QueryBuilder` is a user-facing API for building data pipeline queries. `QueryDialect` is an internal infrastructure layer for runtime stores.
2. `QueryBuilder` uses `$N` placeholders for ALL dialects (a bug -- MySQL and SQLite do not use `$N`). Fixing this is a separate concern that should reference `QueryDialect.translate_query()` in a future PR.
3. `DatabaseDialect(Enum)` in `query_builder.py` has three values identical to `DialectName(Enum)` in `dialect.py`. Once `QueryDialect` ships, the `QueryBuilder` should be migrated to use `DialectName` and `QueryDialect.placeholder()` to fix the placeholder bug. This is a follow-up task, not part of the initial implementation.

### 1.8 Design Rationale: Why Not Use SQLAlchemy Directly?

The question arises: if we are already adopting SQLAlchemy Core (per `02-multi-database-strategy.md`), why build a separate `QueryDialect` abstraction?

SQLAlchemy handles:

- Connection pooling and lifecycle
- Basic SQL compilation (SELECT, INSERT, UPDATE, DELETE)
- Parameter binding (converts `?` to dialect-specific placeholders internally)
- `LargeBinary`, `JSON`, `Text` type mapping

SQLAlchemy does NOT handle (or handles poorly):

- `ON CONFLICT DO UPDATE` vs `ON DUPLICATE KEY UPDATE` -- SQLAlchemy has dialect-specific methods (`insert().on_conflict_do_update()` for PG, `insert().on_duplicate_key_update()` for MySQL), but there is no generic `upsert()`. Callers must know which dialect they are on.
- Advisory locks -- not part of SQLAlchemy's API at all.
- `SKIP LOCKED` -- SQLAlchemy's `with_for_update(skip_locked=True)` compiles correctly for PG and MySQL but produces a silent no-op for SQLite (no error, no locking). This is dangerous.
- JSON operators -- `JSONB @>` (PG containment) vs `JSON_CONTAINS()` (MySQL) vs `json_extract()` (SQLite) are completely different expressions that SQLAlchemy does not unify.
- `BEGIN IMMEDIATE` (SQLite) -- not expressible through SQLAlchemy's transaction API.

`QueryDialect` is the **semantic layer above SQLAlchemy** that makes the store implementations database-agnostic. A store calls `dialect.upsert_sql(...)` and gets correct SQL regardless of backend. The store then executes that SQL through SQLAlchemy's connection.

**Architecture**:

```
Store (EventStore, Checkpoint, DLQ, ...)
    |
    v
QueryDialect (upsert, advisory lock, JSON ops, placeholder translation)
    |
    v
SQLAlchemy Core (connection pool, parameter binding, basic SQL compilation)
    |
    v
asyncpg / aiomysql / aiosqlite (wire protocol)
```

The stores use QueryDialect for dialect-specific SQL fragments and SQLAlchemy for connection management and basic queries. This is the same pattern kailash-rs uses with sqlx.

---

## Part 2: ConnectionManager Design

### 2.1 Architecture

The ConnectionManager wraps SQLAlchemy's engine creation and provides a uniform `acquire()` context manager. It is a thin facade, not a replacement for SQLAlchemy.

```python
# src/kailash/db/connection.py

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ConnectionManager",
    "AsyncConnectionManager",
]


class ConnectionManager:
    """Synchronous database connection manager backed by SQLAlchemy.

    Creates a shared Engine from a URL and provides connection acquisition
    with proper lifecycle management.

    Usage:
        mgr = ConnectionManager("postgresql://localhost/kailash")

        with mgr.acquire() as conn:
            result = conn.execute(text("SELECT 1"))

        mgr.close()  # Disposes the engine and pool
    """

    def __init__(
        self,
        url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo: bool = False,
    ):
        from sqlalchemy import create_engine
        from kailash.db.dialect import detect_dialect, get_dialect, DialectName

        self._url = url
        self._dialect_name = detect_dialect(url)
        self.dialect = get_dialect(url)

        # SQLite-specific: use NullPool (single writer), enable WAL
        engine_kwargs: Dict[str, Any] = {"echo": echo}
        if self._dialect_name == DialectName.SQLITE:
            from sqlalchemy.pool import StaticPool
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_size"] = pool_size
            engine_kwargs["max_overflow"] = max_overflow
            engine_kwargs["pool_timeout"] = pool_timeout
            engine_kwargs["pool_recycle"] = pool_recycle
            engine_kwargs["pool_pre_ping"] = pool_pre_ping

        self._engine = create_engine(url, **engine_kwargs)

        # Enable SQLite WAL mode on first connect
        if self._dialect_name == DialectName.SQLITE:
            from sqlalchemy import event, text

            @event.listens_for(self._engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-64000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    @contextmanager
    def acquire(self) -> Iterator[Any]:
        """Acquire a database connection from the pool.

        Yields a SQLAlchemy Connection. The connection is returned
        to the pool when the context manager exits.
        """
        with self._engine.connect() as conn:
            yield conn

    def close(self) -> None:
        """Dispose the engine and close all pooled connections."""
        self._engine.dispose()
        logger.info("ConnectionManager closed: %s", self._dialect_name.value)


class AsyncConnectionManager:
    """Asynchronous database connection manager backed by SQLAlchemy.

    Creates a shared AsyncEngine from a URL and provides async connection
    acquisition with proper lifecycle management.

    Usage:
        mgr = AsyncConnectionManager(
            "postgresql+asyncpg://localhost/kailash"
        )

        async with mgr.acquire() as conn:
            result = await conn.execute(text("SELECT 1"))

        await mgr.close()
    """

    def __init__(
        self,
        url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo: bool = False,
    ):
        from sqlalchemy.ext.asyncio import create_async_engine
        from kailash.db.dialect import detect_dialect, get_dialect, DialectName

        self._url = self._normalize_async_url(url)
        self._dialect_name = detect_dialect(url)
        self.dialect = get_dialect(url)

        engine_kwargs: Dict[str, Any] = {"echo": echo}
        if self._dialect_name == DialectName.SQLITE:
            from sqlalchemy.pool import StaticPool
            engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["pool_size"] = pool_size
            engine_kwargs["max_overflow"] = max_overflow
            engine_kwargs["pool_timeout"] = pool_timeout
            engine_kwargs["pool_recycle"] = pool_recycle
            engine_kwargs["pool_pre_ping"] = pool_pre_ping

        self._engine = create_async_engine(self._url, **engine_kwargs)

    @staticmethod
    def _normalize_async_url(url: str) -> str:
        """Ensure the URL uses an async-compatible driver.

        Converts bare scheme URLs to async driver variants:
        - postgresql:// -> postgresql+asyncpg://
        - mysql:// -> mysql+aiomysql://
        - sqlite:/// -> sqlite+aiosqlite:///
        """
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+aiomysql://", 1)
        if url.startswith("sqlite:///") and "+aiosqlite" not in url:
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return url

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """Acquire an async database connection from the pool.

        Yields a SQLAlchemy AsyncConnection. The connection is returned
        to the pool when the context manager exits.
        """
        async with self._engine.connect() as conn:
            yield conn

    async def close(self) -> None:
        """Dispose the async engine and close all pooled connections."""
        await self._engine.dispose()
        logger.info(
            "AsyncConnectionManager closed: %s", self._dialect_name.value
        )
```

### 2.2 Shared Engine Singleton

The deep analysis (Section 7, Issue 5) identified a critical risk: 8 stores each creating their own engine would open 40-120 connections. The solution is a registry that creates one engine per URL.

```python
# src/kailash/db/registry.py

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["EngineRegistry"]

# Module-level singleton
_registry_lock = threading.Lock()
_sync_managers: Dict[str, "ConnectionManager"] = {}
_async_managers: Dict[str, "AsyncConnectionManager"] = {}


def get_connection_manager(
    url: str, **kwargs
) -> "ConnectionManager":
    """Get or create a shared synchronous ConnectionManager for the URL.

    Multiple stores calling this with the same URL share one engine.
    """
    with _registry_lock:
        if url not in _sync_managers:
            from kailash.db.connection import ConnectionManager
            _sync_managers[url] = ConnectionManager(url, **kwargs)
            logger.info("Created shared sync engine for %s", _redact_url(url))
        return _sync_managers[url]


def get_async_connection_manager(
    url: str, **kwargs
) -> "AsyncConnectionManager":
    """Get or create a shared async ConnectionManager for the URL.

    Multiple stores calling this with the same URL share one engine.
    """
    with _registry_lock:
        if url not in _async_managers:
            from kailash.db.connection import AsyncConnectionManager
            _async_managers[url] = AsyncConnectionManager(url, **kwargs)
            logger.info("Created shared async engine for %s", _redact_url(url))
        return _async_managers[url]


async def close_all() -> None:
    """Close all registered engines. Call during shutdown."""
    with _registry_lock:
        for mgr in _sync_managers.values():
            mgr.close()
        _sync_managers.clear()

        for mgr in _async_managers.values():
            await mgr.close()
        _async_managers.clear()

    logger.info("All database engines closed")


def _redact_url(url: str) -> str:
    """Redact password from URL for logging."""
    import re
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)
```

### 2.3 How Stores Use This

```python
# Example: SqlAlchemyEventStoreBackend (sketch)

class SqlAlchemyEventStoreBackend:
    def __init__(self, url: Optional[str] = None):
        from kailash.db.registry import get_async_connection_manager
        from kailash.db.dialect import get_dialect

        self._url = url or os.environ.get("KAILASH_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not self._url:
            raise ValueError("No database URL configured")

        self._mgr = get_async_connection_manager(self._url)
        self._dialect = self._mgr.dialect

    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        upsert = self._dialect.upsert_sql(
            table="kailash_events",
            columns=["event_id", "stream_key", "sequence", "event_type", "data", "timestamp"],
            conflict_keys=["event_id"],
        )
        async with self._mgr.acquire() as conn:
            for event in events:
                await conn.execute(text(upsert), {...})
            await conn.commit()
```

---

## Part 3: Env Var Naming Recommendation

### 3.1 Analysis of Prior Art

| Framework             | Store URL                             | Queue/Broker URL    | Override Pattern              |
| --------------------- | ------------------------------------- | ------------------- | ----------------------------- |
| Django                | `DATABASE_URL`                        | `CELERY_BROKER_URL` | None (single DB assumed)      |
| Rails                 | `DATABASE_URL`                        | `REDIS_URL`         | Per-DB: `DATABASE_URL_{NAME}` |
| Temporal              | `DB` + `DB_PORT` + `DB_USER`          | None (built-in)     | Granular per-component        |
| Prefect               | `PREFECT_API_DATABASE_CONNECTION_URL` | None                | Namespaced                    |
| Celery                | `result_backend` (config)             | `CELERY_BROKER_URL` | Config-based                  |
| 12-factor             | `DATABASE_URL`                        | `REDIS_URL`         | Service-specific vars         |
| Kaizen (.env.example) | `DATABASE_URL`                        | `REDIS_URL`         | --                            |

**Key observations**:

1. `DATABASE_URL` is the universal convention (12-factor, Heroku, Railway, Render, every PaaS).
2. Most frameworks own `DATABASE_URL` exclusively. Kailash cannot do this because DataFlow uses `DATABASE_URL` for the user's application database, which may be a different server than the infrastructure stores.
3. Temporal uses granular per-component env vars. This is over-engineering for a library (Temporal is a platform with 4 separate services).
4. Prefect namespaces with `PREFECT_` prefix. This is clean but verbose.

### 3.2 The Collision Problem

DataFlow reads `DATABASE_URL` to connect to the user's application database (e.g., a SaaS product's PostgreSQL). The infrastructure stores also need a database URL. Three scenarios:

**Scenario A: Same database for everything (common)**

- Small deployment, one PostgreSQL instance
- `DATABASE_URL=postgresql://...` serves both DataFlow and infrastructure
- User sets ONE variable, everything works

**Scenario B: Separate databases (enterprise)**

- Application data in one PostgreSQL cluster, infra stores in another
- User needs TWO URLs
- If both are `DATABASE_URL`, this is impossible

**Scenario C: Mixed backends (advanced)**

- Application data in PostgreSQL (DataFlow), infra in MySQL (legacy)
- User needs TWO URLs with different dialects
- Or infra in SQLite (Level 0) while DataFlow uses PostgreSQL

### 3.3 Recommended Env Vars

**Three variables, one required path, two optional overrides.**

| Env Var                | Purpose                                                                                                                  | Default                                                     | When to Set        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- | ------------------ |
| `KAILASH_DATABASE_URL` | Infrastructure stores (event, checkpoint, DLQ, execution, idempotency, search attributes, saga state, task queue tables) | Falls back to `DATABASE_URL`, then SQLite                   | Always (Level 1+)  |
| `KAILASH_QUEUE_URL`    | Task queue broker (Redis or SQL-backed)                                                                                  | Falls back to `KAILASH_DATABASE_URL` (uses SQL SKIP LOCKED) | Level 2 with Redis |
| `KAILASH_REDIS_URL`    | Redis services (distributed circuit breaker, pub/sub, caching)                                                           | Falls back to `KAILASH_QUEUE_URL` if redis://               | Level 2 with Redis |

**Resolution logic (pseudocode)**:

```python
def resolve_database_url() -> Optional[str]:
    """Resolve the infrastructure store database URL.

    Priority:
    1. KAILASH_DATABASE_URL (explicit infrastructure override)
    2. DATABASE_URL (12-factor convention, shared with DataFlow)
    3. None (fall back to SQLite at ~/.kailash/kailash.db)
    """
    return (
        os.environ.get("KAILASH_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or None
    )


def resolve_queue_url() -> Optional[str]:
    """Resolve the task queue broker URL.

    Priority:
    1. KAILASH_QUEUE_URL (explicit queue override)
    2. KAILASH_REDIS_URL (if set, assume Redis queue)
    3. KAILASH_DATABASE_URL / DATABASE_URL (use SQL SKIP LOCKED)
    4. None (no queue, single-process mode)
    """
    return (
        os.environ.get("KAILASH_QUEUE_URL")
        or os.environ.get("KAILASH_REDIS_URL")
        or resolve_database_url()
        or None
    )


def resolve_redis_url() -> Optional[str]:
    """Resolve the Redis URL for non-queue Redis services.

    Priority:
    1. KAILASH_REDIS_URL (explicit Redis override)
    2. KAILASH_QUEUE_URL (if it is a redis:// URL)
    3. None (Redis services disabled)
    """
    explicit = os.environ.get("KAILASH_REDIS_URL")
    if explicit:
        return explicit

    queue = os.environ.get("KAILASH_QUEUE_URL", "")
    if queue.startswith("redis://") or queue.startswith("rediss://"):
        return queue

    return None
```

### 3.4 Justification for Each Variable

**`KAILASH_DATABASE_URL`**

Why not just `DATABASE_URL`?

DataFlow already uses `DATABASE_URL` to connect to the user's application database. If a user has DataFlow connected to `postgresql://app-db:5432/myapp` and wants infrastructure stores on a separate instance `postgresql://infra-db:5432/kailash_infra`, there is no way to express this with a single `DATABASE_URL`.

The `KAILASH_` prefix provides:

- **No collision**: DataFlow continues to use `DATABASE_URL` for application data
- **Explicit intent**: Setting `KAILASH_DATABASE_URL` is an intentional infrastructure decision
- **Graceful fallback**: If not set, falls back to `DATABASE_URL`, which covers the common single-database case

Why not `KAILASH_STORE_URL` or `KAILASH_INFRA_URL`?

- `KAILASH_STORE_URL` -- "store" is ambiguous (event store? key-value store? data store?). Also not how any framework names its DB URL.
- `KAILASH_INFRA_URL` -- "infra" is internal jargon. A user configuring their database should not need to know the internal architecture.
- `KAILASH_DATABASE_URL` -- immediately understood by any developer who has seen `DATABASE_URL`. The `KAILASH_` prefix signals "this is for Kailash internals, not your application data."

**`KAILASH_QUEUE_URL`**

Why not `TASK_QUEUE` (as suggested in the brief)?

- `TASK_QUEUE=redis://...` is not a standard env var name (underscore, no `_URL` suffix)
- `KAILASH_QUEUE_URL` follows the `KAILASH_*_URL` naming pattern
- The `_URL` suffix signals that it expects a connection string, not a boolean or enum

Why not `KAILASH_BROKER_URL`?

- "Broker" implies a message broker (RabbitMQ, Kafka). The task queue can be SQL-backed (no broker).
- "Queue" is more accurate for the SKIP LOCKED use case.
- Celery uses `CELERY_BROKER_URL`, but Celery is a dedicated broker framework; Kailash is not.

**`KAILASH_REDIS_URL`**

Why a separate Redis URL?

Redis is used for more than just the task queue:

- Distributed circuit breaker (Lua scripts, `kailash[distributed]`)
- `RedisStateStorage` for sagas
- Potential future pub/sub and caching

A user running the SQL SKIP LOCKED task queue (no Redis) but who also has a Redis instance for the circuit breaker needs to express "queue = SQL, Redis = this address." Without `KAILASH_REDIS_URL`, this is impossible.

Kaizen already uses `REDIS_URL` in its `.env.example`. Using `KAILASH_REDIS_URL` avoids colliding with an existing `REDIS_URL` that might be set for other applications, while maintaining the `KAILASH_*` namespace.

### 3.5 What About Per-Store Overrides?

Should users be able to point specific stores at different databases?

```
KAILASH_EVENT_STORE_URL=postgresql://events-db/...
KAILASH_CHECKPOINT_STORE_URL=postgresql://checkpoint-db/...
```

**No. This is over-engineering.** Analysis:

1. **No one asked for it.** The brief, gap analysis, and value audit all describe a single `DATABASE_URL` for all stores.
2. **It violates the "fewer env vars = better" principle.** 8 store-specific URLs is a configuration nightmare.
3. **It complicates the shared-engine registry.** If each store can have its own URL, the engine registry must track N engines instead of 1.
4. **The actual use case is covered by KAILASH_DATABASE_URL.** If a user needs stores on a different database than DataFlow, `KAILASH_DATABASE_URL` handles it. If they need different stores on different databases, they are doing something unusual and can configure it programmatically via the `StoreFactory` constructor.

Reserve per-store overrides for a future version if real user demand emerges.

### 3.6 Common Configurations

**Level 0: Zero config**

```bash
# No env vars set. All stores use SQLite at ~/.kailash/kailash.db
pip install kailash
python my_workflow.py
```

**Level 1: One env var, same DB for everything**

```bash
export DATABASE_URL=postgresql://user:pass@localhost/kailash
pip install kailash[database,postgres]
python my_workflow.py
# DataFlow uses DATABASE_URL for app data.
# Infrastructure stores also use DATABASE_URL (fallback).
# All stores on one PostgreSQL instance.
```

**Level 1: Separate infra database**

```bash
export DATABASE_URL=postgresql://app-db/myapp            # DataFlow
export KAILASH_DATABASE_URL=postgresql://infra-db/kailash # Stores
pip install kailash[database,postgres]
python my_workflow.py
```

**Level 1: MySQL**

```bash
export KAILASH_DATABASE_URL=mysql://user:pass@localhost/kailash
pip install kailash[database,mysql]
python my_workflow.py
```

**Level 2: Redis task queue**

```bash
export DATABASE_URL=postgresql://localhost/kailash
export KAILASH_QUEUE_URL=redis://localhost:6379/0
pip install kailash[database,postgres,distributed]
python my_worker.py
```

**Level 2: SQL task queue (no Redis)**

```bash
export DATABASE_URL=postgresql://localhost/kailash
# KAILASH_QUEUE_URL not set -- falls back to DATABASE_URL, uses SKIP LOCKED
pip install kailash[database,postgres]
python my_worker.py
```

**Level 2: SQL queue + separate Redis for circuit breaker**

```bash
export DATABASE_URL=postgresql://localhost/kailash
export KAILASH_REDIS_URL=redis://redis-host:6379/0
# Queue uses SQL SKIP LOCKED (no KAILASH_QUEUE_URL).
# Circuit breaker uses Redis.
pip install kailash[database,postgres,distributed]
```

---

## Part 4: File Organization

### 4.1 Evaluation of Candidate Locations

| Location                                  | Pros                                                           | Cons                                                                                         |
| ----------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `src/kailash/db/dialect.py`               | Clean namespace, dedicated package for DB concerns, extensible | New package to create                                                                        |
| `src/kailash/core/dialect.py`             | "Core" suggests foundational                                   | `core/` contains actors, ML, monitoring, optimization, pool -- unrelated. Pollutes namespace |
| `src/kailash/runtime/dialect.py`          | Close to where stores live                                     | `runtime/` is already crowded (27 files). Dialect is not a runtime concept                   |
| `src/kailash/nodes/data/query_builder.py` | Existing dialect enum lives here                               | `nodes/data/` is for user-facing data nodes, not infrastructure. Mixing concerns             |
| `src/kailash/config/dialect.py`           | Config-adjacent                                                | `config/` has `database_config.py` but dialect is not configuration                          |

### 4.2 Recommendation: New `src/kailash/db/` Package

Create a new `db` package at `src/kailash/db/` with the following structure:

```
src/kailash/db/
    __init__.py          # Exports: QueryDialect, get_dialect, detect_dialect,
                         #          ConnectionManager, AsyncConnectionManager,
                         #          get_connection_manager, get_async_connection_manager
    dialect.py           # DialectName, QueryDialect (ABC), PostgresDialect,
                         #   MySQLDialect, SQLiteDialect, detect_dialect, get_dialect
    connection.py        # ConnectionManager, AsyncConnectionManager
    registry.py          # Shared engine singleton registry
    migration.py         # Schema migration framework (trust-plane pattern,
                         #   ported to SQLAlchemy -- PY-EI-006)
```

**Why a new package?**

1. **Separation of concerns.** Database dialect logic, connection management, and schema migration are a cohesive unit. They do not belong in `runtime/` (execution engine), `nodes/data/` (user-facing data pipeline), `config/` (configuration loading), or `core/` (internal utilities).

2. **The `database/` package already exists** at `src/kailash/database/` but it contains `ExecutionPipeline` -- a permission-checking, data-masking, query-validation pipeline for user-facing database operations. This is a different concern. Using `db/` (shorter, distinct) avoids confusion with `database/`.

3. **Consumers.** The `db` package will be imported by:
   - Infrastructure stores (EventStore, Checkpoint, DLQ, ExecutionStore, IdempotencyStore) -- in `middleware/gateway/` and `runtime/`
   - The distributed task queue (`runtime/task_queue_postgres.py`)
   - The `StoreFactory` (`runtime/store_factory.py`)
   - Future DataFlow migration (if DataFlow adopts QueryDialect to fix its placeholder bug)

4. **Minimal import surface.** `from kailash.db import get_dialect, AsyncConnectionManager` is clean and discoverable.

### 4.3 Package `__init__.py`

```python
# src/kailash/db/__init__.py
"""Database dialect abstraction and connection management.

This package provides:
- QueryDialect: Database-portable SQL fragment generation
- ConnectionManager: Synchronous connection pool management
- AsyncConnectionManager: Asynchronous connection pool management
- Engine registry: Shared connection pools across stores

Usage:
    from kailash.db import get_dialect, get_async_connection_manager

    dialect = get_dialect("postgresql://localhost/kailash")
    mgr = get_async_connection_manager("postgresql+asyncpg://localhost/kailash")
"""

from kailash.db.dialect import (
    DialectName,
    QueryDialect,
    PostgresDialect,
    MySQLDialect,
    SQLiteDialect,
    detect_dialect,
    get_dialect,
)
from kailash.db.connection import (
    ConnectionManager,
    AsyncConnectionManager,
)
from kailash.db.registry import (
    get_connection_manager,
    get_async_connection_manager,
    close_all,
)

__all__ = [
    "DialectName",
    "QueryDialect",
    "PostgresDialect",
    "MySQLDialect",
    "SQLiteDialect",
    "detect_dialect",
    "get_dialect",
    "ConnectionManager",
    "AsyncConnectionManager",
    "get_connection_manager",
    "get_async_connection_manager",
    "close_all",
]
```

---

## Part 5: Risk Analysis

### 5.1 Risk Register

| ID    | Risk                                                                                                                                                     | Likelihood | Impact | Severity    | Mitigation                                                                                                                                                                                                                       |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| QD-01 | MySQL `%s` placeholder makes translate_query() ambiguous when SQL contains literal `%` (e.g., `LIKE '%abc%'`)                                            | Medium     | Medium | MAJOR       | Escape `%%` in canonical SQL before translation. Document that canonical SQL must use `?` placeholders exclusively and `%%` for literal percent signs.                                                                           |
| QD-02 | SQLite `json_contains()` fallback (equality check) is semantically different from PG `@>` (deep containment)                                             | High       | Medium | MAJOR       | Document limitation. Provide `supports_json_containment` property. Stores that need deep containment should do application-level filtering on SQLite.                                                                            |
| QD-03 | Multiple SQLAlchemy engines created if `DATABASE_URL` and `KAILASH_DATABASE_URL` point to the same server but with different URL formats                 | Low        | Low    | MINOR       | Normalize URLs in the registry (strip driver suffix, normalize hostname).                                                                                                                                                        |
| QD-04 | `detect_dialect()` fails for non-standard URL schemes (e.g., `cockroachdb://`, `mariadb://`)                                                             | Low        | Medium | SIGNIFICANT | Raise clear `ValueError` with list of supported schemes. Document that CockroachDB uses `postgresql://` and MariaDB uses `mysql://`.                                                                                             |
| QD-05 | SQLite advisory lock gap: schema migrations cannot use advisory locks, risk of concurrent migration on multi-process SQLite                              | Medium     | High   | MAJOR       | SQLite migrations must use file-based locking (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). Implement in `migration.py` with dialect-specific lock strategy.                                                            |
| QD-06 | `KAILASH_DATABASE_URL` fallback to `DATABASE_URL` breaks when DataFlow uses a different schema/database on the same server                               | Low        | Medium | SIGNIFICANT | Document clearly: `KAILASH_DATABASE_URL` takes precedence. If DataFlow and stores share a server, use the same URL. If they need isolation, set both.                                                                            |
| QD-07 | MySQL `GET_LOCK()` advisory lock is connection-scoped, not session-scoped like PG `pg_advisory_lock()` -- connection pool recycling can release the lock | Medium     | High   | MAJOR       | Use MySQL session-level locks (`GET_LOCK` is already session-scoped in MySQL 5.7+). Document that connection must not be returned to pool while holding advisory lock. Wrap in a dedicated non-pooled connection for migrations. |
| QD-08 | Existing `DatabaseDialect` enum in `query_builder.py` and new `DialectName` enum are duplicative                                                         | Low        | Low    | MINOR       | Phase 2: deprecate `DatabaseDialect` in favor of `DialectName`. Phase 3: migrate `QueryBuilder` to use `QueryDialect.translate_query()`. No immediate action needed.                                                             |

### 5.2 Cross-Reference Audit

**Documents/files affected by this design:**

- `src/kailash/nodes/data/query_builder.py` -- Contains `DatabaseDialect` enum that will eventually be superseded by `DialectName`. The `QueryBuilder._build_condition_clause()` method hardcodes `$N` placeholders for all dialects, which is a bug that `QueryDialect.translate_query()` will fix in a follow-up.

- `src/kailash/config/database_config.py` -- Contains `DatabaseConfig` with `_validate_connection_string()` that accepts `postgresql://`, `mysql://`, `sqlite:///`. The new `detect_dialect()` handles the same URL parsing. These should share validation logic. `DatabaseConfig` should be updated to use `detect_dialect()` internally.

- `src/kailash/middleware/gateway/storage_backends.py` -- Contains `PostgreSQLStorage` and `PostgreSQLEventStorage` with bare `import asyncpg` at line 28 (blocking defect identified in deep analysis). These classes use raw asyncpg. They should be migrated to use `AsyncConnectionManager` and `QueryDialect` in PY-EI-001/002.

- `workspaces/enterprise-infrastructure/todos/active/PY-EI-001.md` through `PY-EI-005.md` -- All store TODOs currently say "using asyncpg" or "using psycopg3". These must be updated to say "using SQLAlchemy Core with QueryDialect."

- `workspaces/enterprise-infrastructure/todos/active/PY-EI-006.md` -- Schema migration utility. Must use `QueryDialect.advisory_lock_sql()` for safe concurrent migration. The migration framework goes in `src/kailash/db/migration.py`.

- `workspaces/enterprise-infrastructure/todos/active/PY-EI-009.md` -- SQL SKIP LOCKED task queue. Must use `QueryDialect.for_update_skip_locked()` and `QueryDialect.supports_skip_locked` to determine behavior. SQLite fallback uses `dialect.begin_immediate()`.

- `workspaces/enterprise-infrastructure/todos/active/PY-EI-016.md` -- Env var configuration. The env var names proposed there (`DATABASE_URL`, `KAILASH_STORE_URL`, `KAILASH_REDIS_URL`) differ from this analysis's recommendation (`KAILASH_DATABASE_URL`, `KAILASH_QUEUE_URL`, `KAILASH_REDIS_URL`). PY-EI-016 must be updated.

- `packages/kailash-kaizen/.env.example` -- Uses `DATABASE_URL` and `REDIS_URL`. Kaizen should document that `KAILASH_DATABASE_URL` overrides `DATABASE_URL` for Kailash infrastructure stores if both are set.

- `.env` -- Currently has `# DATABASE_URL=postgresql://user:pass@localhost:5432/dbname`. Should add `# KAILASH_DATABASE_URL=` comment.

**Inconsistencies found:**

1. `PY-EI-016` proposes `KAILASH_STORE_URL`. This analysis recommends `KAILASH_DATABASE_URL`. The term "store" is ambiguous and non-standard. Resolution: update PY-EI-016.

2. The project brief uses `TASK_QUEUE=redis://...` and `TASK_QUEUE=postgresql://...`. This analysis recommends `KAILASH_QUEUE_URL`. Resolution: update brief with the finalized naming.

3. `DatabaseConfig._validate_connection_string()` does not accept `postgres://` (without `ql`). `detect_dialect()` does. Resolution: align both.

### 5.3 Decision Points Requiring Stakeholder Input

1. **Env var naming**: Accept `KAILASH_DATABASE_URL` / `KAILASH_QUEUE_URL` / `KAILASH_REDIS_URL` as the final names, or prefer shorter alternatives? The three-variable model is recommended. The brief's `TASK_QUEUE` is non-standard and should be changed.

2. **Sync vs async engine default**: Should `StoreFactory` create a sync `ConnectionManager` or async `AsyncConnectionManager` by default? The deep analysis recommends sync for `LocalRuntime` (synchronous execution) and async for `DistributedRuntime` (async workers). The `StoreFactory` should detect the runtime context and create the appropriate manager.

3. **SQLite default path**: Level 0 uses SQLite at `~/.kailash/kailash.db`. Should all stores share one SQLite file, or should each store have its own file (e.g., `~/.kailash/events.db`, `~/.kailash/checkpoints.db`)? One file is simpler (one WAL, one connection). Multiple files allow independent backup/deletion. Recommendation: one file, separate tables. The existing `SqliteEventStoreBackend` uses `~/.kailash/events/event_store.db` -- this will change.

4. **`DatabaseDialect` deprecation timeline**: When should the existing `DatabaseDialect` enum in `query_builder.py` be deprecated in favor of `DialectName`? Recommendation: v1.1.0 deprecation notice, v2.0.0 removal.

5. **MySQL version enforcement**: The dialect assumes MySQL 8.0+ (required for SKIP LOCKED, JSON functions, CTEs). Should `detect_dialect()` or `ConnectionManager.__init__()` verify the MySQL version and raise an error for MySQL 5.x? Recommendation: yes, check on first connection and log a warning if < 8.0.

---

## Part 6: Implementation Roadmap

### Phase 1: Foundation (3-4 days)

1. Create `src/kailash/db/__init__.py`, `dialect.py`, `connection.py`, `registry.py`
2. Implement all three dialect classes with full method coverage
3. Implement `detect_dialect()` and `get_dialect()`
4. Implement `ConnectionManager` and `AsyncConnectionManager`
5. Implement `get_connection_manager()` and `get_async_connection_manager()` registry
6. Unit tests: placeholder translation, upsert generation, URL detection, dialect selection

### Phase 2: Env Var Resolution (1-2 days)

7. Create `src/kailash/db/env.py` with `resolve_database_url()`, `resolve_queue_url()`, `resolve_redis_url()`
8. Unit tests: all priority/fallback scenarios from Section 3.6
9. Update `.env` template with new variable names

### Phase 3: Store Integration (follows PY-EI-001 through PY-EI-005)

10. Each SQLAlchemy store backend uses `get_async_connection_manager(resolve_database_url())` for shared engine
11. Each store uses `self._mgr.dialect` for dialect-specific SQL
12. Integration tests across PostgreSQL, MySQL, SQLite

### Phase 4: Migration Framework (follows PY-EI-006)

13. `src/kailash/db/migration.py` uses `dialect.advisory_lock_sql()` for safe concurrent migration
14. SQLite fallback uses file-based locking

### Phase 5: Task Queue (follows PY-EI-009)

15. SQL task queue uses `dialect.for_update_skip_locked()` with `supports_skip_locked` guard
16. SQLite mode uses `dialect.begin_immediate()` with single-writer semantics

### Success Criteria

| Criterion                 | Measurement                                                                                                           |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Dialect correctness       | All 3 dialects produce valid SQL verified by executing against real databases in CI                                   |
| Placeholder translation   | `translate_query("SELECT * FROM t WHERE id = ? AND name = ?")` produces `$1/$2` (PG), `%s/%s` (MySQL), `?/?` (SQLite) |
| Upsert portability        | Same `upsert_sql()` call produces valid upsert for all 3 dialects, verified by integration test                       |
| URL detection             | 100% of URL formats from Section 1.6 examples detected correctly                                                      |
| Shared engine             | With `KAILASH_DATABASE_URL` set, all 8 stores use one connection pool (verified by pool size metrics)                 |
| Env var fallback          | Setting only `DATABASE_URL` (no `KAILASH_DATABASE_URL`) works for all stores                                          |
| No new mandatory deps     | `pip install kailash` (no extras) still works with 4 mandatory deps                                                   |
| `QueryBuilder` unaffected | Existing `query_builder.py` tests pass unchanged                                                                      |

---

## Appendix A: Comparison with kailash-rs

The kailash-rs SDK uses sqlx's `Any` driver type, which provides compile-time dialect abstraction. The Python equivalent is this QueryDialect + SQLAlchemy combination. Key alignment points:

| Concern          | kailash-rs                                                                      | kailash-py (this design)                                                    |
| ---------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Strategy pattern | `trait DatabaseDialect` with `PostgresDialect`, `MySQLDialect`, `SQLiteDialect` | `QueryDialect(ABC)` with `PostgresDialect`, `MySQLDialect`, `SQLiteDialect` |
| URL detection    | `detect_from_url()` function                                                    | `detect_dialect()` function                                                 |
| Connection pool  | sqlx `AnyPool`                                                                  | SQLAlchemy `Engine` / `AsyncEngine` via registry                            |
| Shared pool      | Application-level singleton                                                     | Module-level registry (`get_connection_manager()`)                          |
| Upsert           | `dialect.upsert_query()`                                                        | `dialect.upsert_sql()`                                                      |
| Advisory locks   | `dialect.advisory_lock()`                                                       | `dialect.advisory_lock_sql()`                                               |
| Env var          | `KAILASH_DATABASE_URL`                                                          | `KAILASH_DATABASE_URL` (aligned)                                            |

The Python design intentionally mirrors the Rust SDK's naming and structure to ensure cross-SDK consistency per the EATP cross-SDK alignment rules.

## Appendix B: `json_extract` Placeholder Management

The `json_extract()` method in Section 1.3 returns an expression with a hardcoded `$1` placeholder. This is a design limitation because callers compose queries with multiple placeholders and cannot control the index inside `json_extract()`.

**Recommended fix**: Change `json_extract()` to accept a literal path key (not a placeholder) since JSON path keys are schema-defined constants, not user input. The method signature becomes:

```python
def json_extract(self, column: str, path: str) -> str:
    """SQL expression to extract a JSON field by literal key.

    Args:
        column: Column name.
        path: Literal JSON key (e.g., 'status'). NOT user input.

    Returns:
        SQL expression with the path embedded as a literal.
    """
```

PostgreSQL: `column->>'status'` (literal key, no placeholder needed)
MySQL: `JSON_EXTRACT(column, '$.status')` (literal path)
SQLite: `json_extract(column, '$.status')` (literal path)

This is safe because JSON path keys are defined in the schema, not by users. If user-supplied paths are ever needed, a separate `json_extract_param()` method should be added with proper parameterization.
