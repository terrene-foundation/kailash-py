# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Async ConnectionManager with dialect-aware placeholder translation.

Wraps database-specific async drivers (``asyncpg``, ``aiomysql``,
``aiosqlite``) behind a uniform interface.  Optional driver dependencies
are imported lazily and produce clear errors if missing.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Dict, List, Optional

from kailash.db.dialect import (
    DatabaseType,
    QueryDialect,
    detect_dialect,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConnectionManager",
]


class ConnectionManager:
    """Manages async database connections with dialect-aware pooling.

    Parameters
    ----------
    url:
        A database connection URL (see :func:`detect_dialect` for formats).

    Raises
    ------
    ValueError
        If *url* is empty or uses an unsupported scheme.
    """

    def __init__(self, url: str) -> None:
        self.url: str = url
        self.dialect: QueryDialect = detect_dialect(url)
        self._pool: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the connection pool for the configured dialect.

        Raises
        ------
        ImportError
            If the required async driver is not installed.
        """
        db_type = self.dialect.database_type

        if db_type == DatabaseType.SQLITE:
            await self._init_sqlite()
        elif db_type == DatabaseType.POSTGRESQL:
            await self._init_postgres()
        elif db_type == DatabaseType.MYSQL:
            await self._init_mysql()
        else:
            raise ValueError(
                f"Cannot initialize pool for unknown database type: {db_type}"
            )

        logger.info("ConnectionManager initialized for %s", db_type.value)

    async def close(self) -> None:
        """Close the connection pool and release resources."""
        if self._pool is None:
            return

        db_type = self.dialect.database_type
        try:
            if db_type == DatabaseType.SQLITE:
                await self._pool.close()
            elif db_type == DatabaseType.POSTGRESQL:
                await self._pool.close()
            elif db_type == DatabaseType.MYSQL:
                self._pool.close()
                await self._pool.wait_closed()
        except Exception:
            logger.exception("Error closing connection pool for %s", db_type.value)
            raise
        finally:
            self._pool = None
            logger.info("ConnectionManager closed for %s", db_type.value)

    async def create_index(self, index_name: str, table: str, columns: str) -> None:
        """Create an index, ignoring if it already exists.

        Uses ``CREATE INDEX IF NOT EXISTS`` on PostgreSQL/SQLite and
        catches duplicate-index errors on MySQL (which does not support
        ``IF NOT EXISTS`` for indexes).

        Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, every
        dynamic identifier interpolated into DDL MUST route through
        ``dialect.quote_identifier()`` — which both validates against
        the allowlist regex AND wraps in dialect-appropriate quotes.
        """
        quoted_index = self.dialect.quote_identifier(index_name)
        quoted_table = self.dialect.quote_identifier(table)
        quoted_cols = ", ".join(
            self.dialect.quote_identifier(c.strip()) for c in columns.split(",")
        )
        if self.dialect.database_type == DatabaseType.MYSQL:
            try:
                await self.execute(
                    f"CREATE INDEX {quoted_index} ON {quoted_table}({quoted_cols})"
                )
            except Exception:
                # MySQL raises error 1061 if index already exists
                logger.warning(
                    "create_index.mysql_error index=%s table=%s",
                    index_name,
                    table,
                )
        else:
            await self.execute(
                f"CREATE INDEX IF NOT EXISTS {quoted_index} "
                f"ON {quoted_table}({quoted_cols})"
            )

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------
    async def execute(self, query: str, *args: Any) -> Any:
        """Execute a query with dialect placeholder translation.

        Parameters
        ----------
        query:
            SQL query using ``?`` canonical placeholders.
        *args:
            Positional parameters matching the placeholders.

        Raises
        ------
        RuntimeError
            If :meth:`initialize` has not been called.
        """
        self._check_initialized()
        translated = self.dialect.translate_query(query)
        return await self._execute_raw(translated, args)

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Fetch all rows as a list of dicts with dialect translation.

        Raises
        ------
        RuntimeError
            If :meth:`initialize` has not been called.
        """
        self._check_initialized()
        translated = self.dialect.translate_query(query)
        return await self._fetch_raw(translated, args)

    async def fetchone(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dict, or ``None`` if no match.

        Raises
        ------
        RuntimeError
            If :meth:`initialize` has not been called.
        """
        self._check_initialized()
        translated = self.dialect.translate_query(query)
        return await self._fetchone_raw(translated, args)

    @contextlib.asynccontextmanager
    async def transaction(self):
        """Async context manager for multi-statement transactions.

        Yields a ``TransactionProxy`` that provides ``execute``, ``fetch``,
        and ``fetchone`` methods operating within a single transaction.

        On normal exit the transaction is committed; on exception it is
        rolled back.

        Usage::

            async with conn.transaction() as tx:
                await tx.execute("INSERT INTO ...", ...)
                row = await tx.fetchone("SELECT ...", ...)
        """
        self._check_initialized()
        db_type = self.dialect.database_type

        if db_type == DatabaseType.SQLITE:
            # SQLite: single connection, use BEGIN/COMMIT/ROLLBACK
            await self._pool.execute("BEGIN IMMEDIATE")
            try:
                yield _TransactionProxy(self, db_type, conn=self._pool)
                await self._pool.commit()
            except BaseException:
                await self._pool.rollback()
                raise

        elif db_type == DatabaseType.POSTGRESQL:
            # PostgreSQL: acquire connection, use transaction block
            async with self._pool.acquire() as pg_conn:
                tr = pg_conn.transaction()
                await tr.start()
                try:
                    yield _TransactionProxy(self, db_type, conn=pg_conn)
                    await tr.commit()
                except BaseException:
                    await tr.rollback()
                    raise

        elif db_type == DatabaseType.MYSQL:
            # MySQL: acquire connection, begin transaction
            async with self._pool.acquire() as my_conn:
                await my_conn.begin()
                try:
                    yield _TransactionProxy(self, db_type, conn=my_conn)
                    await my_conn.commit()
                except BaseException:
                    await my_conn.rollback()
                    raise

        else:
            raise ValueError(f"Unsupported database type for transactions: {db_type}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _check_initialized(self) -> None:
        if self._pool is None:
            raise RuntimeError(
                "ConnectionManager is not initialized. "
                "Call await manager.initialize() first."
            )

    # -- SQLite ---------------------------------------------------------
    async def _init_sqlite(self) -> None:
        try:
            import aiosqlite
        except ImportError as exc:
            raise ImportError(
                "aiosqlite is required for SQLite connections. "
                "Install it with: pip install kailash"
            ) from exc

        # Extract path from sqlite:///path or sqlite:///:memory:
        path = self.url
        if path.startswith("sqlite:///"):
            path = path[len("sqlite:///") :]
        elif path.startswith("sqlite://"):
            path = path[len("sqlite://") :]

        # aiosqlite returns a Connection, not a pool.
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        # Enable WAL mode for file-based databases
        if path and path != ":memory:":
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
        self._pool = conn
        logger.debug("SQLite connection opened: %s", path)

    async def _execute_raw(self, query: str, args: tuple) -> Any:
        db_type = self.dialect.database_type
        if db_type == DatabaseType.SQLITE:
            cursor = await self._pool.execute(query, args)
            await self._pool.commit()
            return cursor
        elif db_type == DatabaseType.POSTGRESQL:
            return await self._pool.execute(query, *args)
        elif db_type == DatabaseType.MYSQL:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, args)
                    await conn.commit()
                    return cur
        raise ValueError(f"Unsupported database type: {db_type}")

    async def _fetch_raw(self, query: str, args: tuple) -> List[Dict[str, Any]]:
        db_type = self.dialect.database_type
        if db_type == DatabaseType.SQLITE:
            cursor = await self._pool.execute(query, args)
            rows = await cursor.fetchall()
            if rows and hasattr(rows[0], "keys"):
                return [dict(row) for row in rows]
            # Fallback: use cursor.description for column names
            if rows and cursor.description:
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
            return []
        elif db_type == DatabaseType.POSTGRESQL:
            return [dict(row) for row in await self._pool.fetch(query, *args)]
        elif db_type == DatabaseType.MYSQL:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, args)
                    columns = [desc[0] for desc in cur.description]
                    rows = await cur.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
        raise ValueError(f"Unsupported database type: {db_type}")

    async def _fetchone_raw(self, query: str, args: tuple) -> Optional[Dict[str, Any]]:
        db_type = self.dialect.database_type
        if db_type == DatabaseType.SQLITE:
            cursor = await self._pool.execute(query, args)
            row = await cursor.fetchone()
            if row is None:
                return None
            if hasattr(row, "keys"):
                return dict(row)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        elif db_type == DatabaseType.POSTGRESQL:
            row = await self._pool.fetchrow(query, *args)
            return dict(row) if row else None
        elif db_type == DatabaseType.MYSQL:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, args)
                    columns = [desc[0] for desc in cur.description]
                    row = await cur.fetchone()
                    return dict(zip(columns, row)) if row else None
        raise ValueError(f"Unsupported database type: {db_type}")

    # -- PostgreSQL -----------------------------------------------------
    async def _init_postgres(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:
            raise ImportError(
                "asyncpg is required for PostgreSQL connections. "
                "Install it with: pip install kailash"
            ) from exc

        self._pool = await asyncpg.create_pool(self.url)
        logger.debug("PostgreSQL pool created")

    # -- MySQL ----------------------------------------------------------
    async def _init_mysql(self) -> None:
        try:
            import aiomysql
        except ImportError as exc:
            raise ImportError(
                "aiomysql is required for MySQL connections. "
                "Install it with: pip install kailash"
            ) from exc

        from urllib.parse import urlparse

        from kailash.utils.url_credentials import (
            decode_userinfo_or_raise,
            preencode_password_special_chars,
        )

        # Pre-encode raw ``#$@?`` in the password so operators who
        # paste a literal DATABASE_URL work uniformly across sites,
        # then decode userinfo and reject null bytes via the shared
        # helper — see ``kailash/utils/url_credentials.py``.
        parsed = urlparse(preencode_password_special_chars(self.url))
        user, password = decode_userinfo_or_raise(parsed, default_user="root")
        self._pool = await aiomysql.create_pool(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=user,
            password=password,
            db=parsed.path.lstrip("/") if parsed.path else "",
        )
        logger.debug("MySQL pool created")


class _TransactionProxy:
    """Lightweight proxy that executes queries within a transaction.

    Created by :meth:`ConnectionManager.transaction`; do not instantiate
    directly.
    """

    def __init__(
        self, manager: ConnectionManager, db_type: DatabaseType, conn: Any
    ) -> None:
        self._manager = manager
        self._db_type = db_type
        self._conn = conn

    async def execute(self, query: str, *args: Any) -> Any:
        """Execute a query within the transaction."""
        translated = self._manager.dialect.translate_query(query)
        if self._db_type == DatabaseType.SQLITE:
            cursor = await self._conn.execute(translated, args)
            return cursor
        elif self._db_type == DatabaseType.POSTGRESQL:
            return await self._conn.execute(translated, *args)
        elif self._db_type == DatabaseType.MYSQL:
            async with self._conn.cursor() as cur:
                await cur.execute(translated, args)
                return cur
        raise ValueError(f"Unsupported database type: {self._db_type}")

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """Fetch all rows within the transaction."""
        translated = self._manager.dialect.translate_query(query)
        if self._db_type == DatabaseType.SQLITE:
            cursor = await self._conn.execute(translated, args)
            rows = await cursor.fetchall()
            if rows and hasattr(rows[0], "keys"):
                return [dict(row) for row in rows]
            if rows and cursor.description:
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
            return []
        elif self._db_type == DatabaseType.POSTGRESQL:
            return [dict(row) for row in await self._conn.fetch(translated, *args)]
        elif self._db_type == DatabaseType.MYSQL:
            async with self._conn.cursor() as cur:
                await cur.execute(translated, args)
                columns = [desc[0] for desc in cur.description]
                rows = await cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        raise ValueError(f"Unsupported database type: {self._db_type}")

    async def fetchone(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Fetch a single row within the transaction."""
        translated = self._manager.dialect.translate_query(query)
        if self._db_type == DatabaseType.SQLITE:
            cursor = await self._conn.execute(translated, args)
            row = await cursor.fetchone()
            if row is None:
                return None
            if hasattr(row, "keys"):
                return dict(row)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        elif self._db_type == DatabaseType.POSTGRESQL:
            row = await self._conn.fetchrow(translated, *args)
            return dict(row) if row else None
        elif self._db_type == DatabaseType.MYSQL:
            async with self._conn.cursor() as cur:
                await cur.execute(translated, args)
                columns = [desc[0] for desc in cur.description]
                row = await cur.fetchone()
                return dict(zip(columns, row)) if row else None
        raise ValueError(f"Unsupported database type: {self._db_type}")
