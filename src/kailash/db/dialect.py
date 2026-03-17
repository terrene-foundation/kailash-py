# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""QueryDialect strategy pattern for cross-database SQL generation.

Provides an abstract base class ``QueryDialect`` and concrete implementations
for PostgreSQL, MySQL, and SQLite.  The canonical placeholder is ``?``
(SQLite style); ``translate_query`` converts to the dialect's native format.

This module has **zero** external dependencies — it generates SQL strings only.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseType",
    "QueryDialect",
    "PostgresDialect",
    "MySQLDialect",
    "SQLiteDialect",
    "detect_dialect",
]


# ---------------------------------------------------------------------------
# DatabaseType enum
# ---------------------------------------------------------------------------
class DatabaseType(Enum):
    """Supported database engine types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class QueryDialect(ABC):
    """Abstract base for database dialect translation.

    Subclasses implement SQL generation methods that produce dialect-specific
    SQL strings.  The canonical placeholder character is ``?``.
    """

    @property
    @abstractmethod
    def database_type(self) -> DatabaseType:
        """Return the :class:`DatabaseType` for this dialect."""

    @abstractmethod
    def placeholder(self, index: int) -> str:
        """Return the parameter placeholder for the given 0-based *index*.

        PostgreSQL: ``$1``, ``$2``, ...
        MySQL: ``%s``
        SQLite: ``?``
        """

    def translate_query(self, query: str) -> str:
        """Translate a query with ``?`` placeholders to dialect-specific form.

        The default implementation calls :meth:`placeholder` for each ``?``
        found in *query*.  Subclasses that use ``?`` natively (SQLite) can
        override with a no-op for efficiency.
        """
        counter = 0

        def _replace(match: re.Match) -> str:
            nonlocal counter
            result = self.placeholder(counter)
            counter += 1
            return result

        return re.sub(r"\?", _replace, query)

    @abstractmethod
    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """Generate an upsert statement.

        Parameters
        ----------
        table:
            Target table name.
        columns:
            All columns being inserted (including conflict keys).
        conflict_keys:
            Columns that form the unique constraint.
        update_columns:
            Columns to update on conflict.  Defaults to all *columns* that
            are **not** in *conflict_keys*.

        Returns
        -------
        tuple[str, list[str]]
            ``(sql_template, param_columns)`` where *sql_template* uses
            dialect-specific placeholders and *param_columns* lists the
            column names in parameter-binding order.
        """

    @abstractmethod
    def json_column_type(self) -> str:
        """Return the native JSON column type.

        PostgreSQL: ``JSONB``, MySQL: ``JSON``, SQLite: ``TEXT``.
        """

    @abstractmethod
    def json_extract(self, column: str, path: str) -> str:
        """Generate a JSON field extraction expression.

        PostgreSQL: ``column->>'path'``
        MySQL: ``JSON_EXTRACT(column, '$.path')``
        SQLite: ``json_extract(column, '$.path')``
        """

    @abstractmethod
    def for_update_skip_locked(self) -> str:
        """Return the row-level locking clause for task-queue dequeue.

        PostgreSQL/MySQL: ``FOR UPDATE SKIP LOCKED``
        SQLite: ``""`` (use ``BEGIN IMMEDIATE`` instead)
        """

    @abstractmethod
    def timestamp_now(self) -> str:
        """Return the current-timestamp expression.

        PostgreSQL/MySQL: ``NOW()``
        SQLite: ``datetime('now')``
        """


# ---------------------------------------------------------------------------
# PostgresDialect
# ---------------------------------------------------------------------------
class PostgresDialect(QueryDialect):
    """PostgreSQL dialect — uses ``$1, $2, ...`` numbered placeholders."""

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.POSTGRESQL

    def placeholder(self, index: int) -> str:
        return f"${index + 1}"

    # translate_query inherited from base — replaces ? with $N

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        placeholders = ", ".join(self.placeholder(i) for i in range(len(columns)))
        col_list = ", ".join(columns)
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )
        return sql, list(columns)

    def json_column_type(self) -> str:
        return "JSONB"

    def json_extract(self, column: str, path: str) -> str:
        return f"{column}->>'{path}'"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    def timestamp_now(self) -> str:
        return "NOW()"


# ---------------------------------------------------------------------------
# MySQLDialect
# ---------------------------------------------------------------------------
class MySQLDialect(QueryDialect):
    """MySQL dialect — uses ``%s`` positional placeholders."""

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.MYSQL

    def placeholder(self, index: int) -> str:
        return "%s"

    # translate_query inherited from base — replaces ? with %s

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        placeholders = ", ".join(self.placeholder(i) for i in range(len(columns)))
        col_list = ", ".join(columns)
        update_set = ", ".join(f"{c} = VALUES({c})" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_set}"
        )
        return sql, list(columns)

    def json_column_type(self) -> str:
        return "JSON"

    def json_extract(self, column: str, path: str) -> str:
        return f"JSON_EXTRACT({column}, '$.{path}')"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    def timestamp_now(self) -> str:
        return "NOW()"


# ---------------------------------------------------------------------------
# SQLiteDialect
# ---------------------------------------------------------------------------
class SQLiteDialect(QueryDialect):
    """SQLite dialect — uses ``?`` positional placeholders (canonical)."""

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.SQLITE

    def placeholder(self, index: int) -> str:
        return "?"

    def translate_query(self, query: str) -> str:
        """SQLite uses ``?`` natively — identity translation."""
        return query

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]

        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(f"{c} = excluded.{c}" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )
        return sql, list(columns)

    def json_column_type(self) -> str:
        return "TEXT"

    def json_extract(self, column: str, path: str) -> str:
        return f"json_extract({column}, '$.{path}')"

    def for_update_skip_locked(self) -> str:
        return ""

    def timestamp_now(self) -> str:
        return "datetime('now')"


# ---------------------------------------------------------------------------
# detect_dialect()
# ---------------------------------------------------------------------------
def detect_dialect(url: str) -> QueryDialect:
    """Auto-detect the appropriate dialect from a database URL.

    Parameters
    ----------
    url:
        A database connection URL.  Supported schemes:

        * ``postgresql://`` or ``postgres://`` (including ``+asyncpg`` driver)
        * ``mysql://`` (including ``+aiomysql`` driver)
        * ``sqlite:///`` (including ``:///:memory:``)
        * A plain file path (treated as SQLite)

    Returns
    -------
    QueryDialect
        The dialect instance for the detected database.

    Raises
    ------
    ValueError
        If *url* is empty or uses an unsupported scheme.
    TypeError
        If *url* is not a string.
    """
    if not isinstance(url, str):
        raise TypeError(f"Database URL must be a string, got {type(url).__name__}")

    if not url.strip():
        raise ValueError(
            "Database URL must not be empty. Set KAILASH_DATABASE_URL or "
            "DATABASE_URL, or pass a URL explicitly."
        )

    url_lower = url.lower()

    # PostgreSQL
    if url_lower.startswith(("postgresql://", "postgresql+", "postgres://")):
        logger.debug("Detected PostgreSQL dialect from URL: %s", url[:40])
        return PostgresDialect()

    # MySQL
    if url_lower.startswith(("mysql://", "mysql+")):
        logger.debug("Detected MySQL dialect from URL: %s", url[:40])
        return MySQLDialect()

    # SQLite
    if url_lower.startswith("sqlite://"):
        logger.debug("Detected SQLite dialect from URL: %s", url[:40])
        return SQLiteDialect()

    # Plain file path (relative or absolute) -> SQLite
    if url.startswith(("/", "./", "../")) or not re.match(
        r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url
    ):
        logger.debug("No scheme detected; treating as SQLite file path: %s", url[:40])
        return SQLiteDialect()

    # Unknown scheme
    scheme = url.split("://", 1)[0]
    raise ValueError(
        f"Unsupported database URL scheme '{scheme}'. "
        f"Supported: postgresql, mysql, sqlite, or a file path for SQLite."
    )
