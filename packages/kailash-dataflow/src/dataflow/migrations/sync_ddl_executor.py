"""
Synchronous DDL Executor for DataFlow Migrations.

This module provides synchronous DDL execution for database migrations,
completely separate from the async CRUD connection pool.

Key Design Principles:
- Uses psycopg2 (sync) for PostgreSQL DDL operations, not asyncpg
- Uses sqlite3 (sync) for SQLite DDL operations
- Connections are ephemeral (open -> execute -> close)
- No event loop involvement at all
- Completely separate from async CRUD operations

This architecture solves the Docker/FastAPI auto_migrate issue:
- DDL operations don't need async at all
- They're one-time setup operations
- Using sync connections avoids event loop boundary issues
"""

import logging
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from kailash.db.dialect import _validate_identifier
from kailash.utils.url_credentials import mask_url

logger = logging.getLogger(__name__)

_CREATE_INDEX_RE = re.compile(r"(?i)\bCREATE\s+(UNIQUE\s+)?INDEX\b")


def _is_benign_ddl_object_exists(error_str: str, sql: Optional[str]) -> bool:
    """Return True when a failed DDL statement means the object already exists.

    Benign already-present signals for an idempotent DDL re-run:

    * PostgreSQL / SQLite — ``"... already exists"`` (any object).
    * MySQL — error 1061 ``"Duplicate key name"`` on a ``CREATE INDEX``. MySQL's
      ``CREATE INDEX`` has no ``IF NOT EXISTS`` (issue #1537 dropped it because
      MySQL rejects it with a 1064 syntax error), so re-migrating an existing
      table raises 1061. Scope the 1061 tolerance to ``CREATE INDEX`` so a
      duplicate key *inside* a ``CREATE TABLE`` definition — a genuine schema
      authoring bug — still surfaces as an error.

    Mirrors ``schema_state_manager.py``'s index-already-exists tolerance. This
    only governs the LOG LEVEL of the executor's own line; the caller still
    receives ``{"success": False, "error": ...}`` and applies its own
    disposition.
    """
    error_lower = error_str.lower()
    if "already exists" in error_lower:
        return True
    if "duplicate key name" in error_lower and sql and _CREATE_INDEX_RE.search(sql):
        return True
    return False


class SyncDDLExecutor:
    """
    Executes DDL operations using synchronous database connections.

    This class is specifically designed for migrations and schema operations
    which are one-time setup operations that don't need async pooling.

    Works in ANY context:
    - CLI scripts (no event loop)
    - FastAPI/Docker (event loop running)
    - pytest (both sync and async)

    No async_safe_run or thread pools needed - pure synchronous execution.
    """

    def __init__(self, database_url: str):
        """
        Initialize the sync DDL executor.

        Args:
            database_url: Database connection URL (postgresql:// or sqlite://)
        """
        self.database_url = database_url
        self._db_type = self._detect_db_type()

    def _detect_db_type(self) -> str:
        """Detect the database type from the URL."""
        if "postgresql" in self.database_url or "postgres" in self.database_url:
            return "postgresql"
        elif "sqlite" in self.database_url or self.database_url == ":memory:":
            return "sqlite"
        elif "mysql" in self.database_url:
            return "mysql"
        elif "mongodb" in self.database_url:
            # MongoDB is a document database - no SQL DDL needed
            return "mongodb"
        else:
            # Default to SQLite for safety.
            # Round 2 red team fix: route the URL through mask_url so
            # operators see a hint about what failed without leaking
            # the userinfo into the log. See rules/security.md
            # § "No secrets in logs".
            logger.warning(
                f"Unknown database type in URL, defaulting to SQLite: {mask_url(self.database_url)}"
            )
            return "sqlite"

    def _get_sync_connection(self):
        """
        Get a synchronous database connection for DDL operations.

        Returns a fresh connection each time - no pooling needed for DDL.
        The connection should be closed after use.
        """
        if self._db_type == "postgresql":
            return self._get_postgresql_connection()
        elif self._db_type == "sqlite":
            return self._get_sqlite_connection()
        elif self._db_type == "mysql":
            return self._get_mysql_connection()
        elif self._db_type == "mongodb":
            raise NotImplementedError(
                "MongoDB is a document database and doesn't use SQL DDL. "
                "SyncDDLExecutor is only for SQL databases (PostgreSQL, MySQL, SQLite). "
                "MongoDB collections are created automatically on first document insert."
            )
        else:
            return self._get_sqlite_connection()

    def _get_postgresql_connection(self):
        """Get a synchronous PostgreSQL connection using psycopg2."""
        try:
            import psycopg2

            from dataflow.adapters.connection_parser import ConnectionParser

            components = ConnectionParser.parse_connection_string(self.database_url)

            conn = psycopg2.connect(
                host=components.get("host", "localhost"),
                port=int(components.get("port", 5432)),
                database=components.get("database", "postgres"),
                user=components.get("username", "postgres"),
                password=components.get("password", ""),
            )
            # DDL in PostgreSQL auto-commits, but we want explicit control
            conn.autocommit = True
            logger.debug("Created sync PostgreSQL connection for DDL")
            return conn

        except ImportError:
            raise ImportError(
                "psycopg2 is required for the synchronous PostgreSQL DDL path. "
                "DataFlow is async-first (asyncpg is baseline); psycopg2 is opt-in. "
                'Install with: pip install "kailash-dataflow[postgres-sync]"'
            )

    def _get_sqlite_connection(self):
        """Get a synchronous SQLite connection."""
        db_path = self.database_url

        # Issue #1502: a ``file:...?mode=memory&cache=shared`` URI reaches the
        # per-DataFlow-instance shared in-memory DB. It MUST be opened with
        # ``uri=True`` and MUST NOT be run through the ``sqlite://`` stripping
        # below, or sqlite3 would treat the literal ``file:...`` text as a
        # filesystem path and create a separate on-disk DB.
        if db_path.startswith("file:"):
            conn = sqlite3.connect(db_path, check_same_thread=False, uri=True)
            logger.debug(
                "sync_ddl_executor.created_sync_sqlite_uri_connection_for_ddl",
                extra={"db_path": db_path},
            )
            return conn

        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        elif db_path.startswith("sqlite://"):
            db_path = db_path.replace("sqlite://", "")

        # For in-memory databases
        if db_path == "" or db_path == ":memory:":
            db_path = ":memory:"

        conn = sqlite3.connect(db_path, check_same_thread=False)
        logger.debug(
            "sync_ddl_executor.created_sync_sqlite_connection_for_ddl",
            extra={"db_path": db_path},
        )
        return conn

    def _get_mysql_connection(self):
        """Get a synchronous MySQL connection using pymysql."""
        try:
            import pymysql

            from dataflow.adapters.connection_parser import ConnectionParser

            components = ConnectionParser.parse_connection_string(self.database_url)

            conn = pymysql.connect(
                host=components.get("host", "localhost"),
                port=int(components.get("port", 3306)),
                database=components.get("database", "mysql"),
                user=components.get("username", "root"),
                password=components.get("password", ""),
                autocommit=True,
            )
            logger.debug("Created sync MySQL connection for DDL")
            return conn

        except ImportError:
            raise ImportError(
                "pymysql is required for MySQL migrations. "
                "Install with: pip install pymysql"
            )

    def execute_ddl(self, sql: str) -> Dict[str, Any]:
        """
        Execute a DDL statement synchronously.

        Args:
            sql: The DDL SQL statement (CREATE TABLE, ALTER TABLE, etc.)

        Returns:
            Dict with 'success' and optionally 'error'
        """
        conn = None
        try:
            conn = self._get_sync_connection()
            cursor = conn.cursor()

            # Execute the DDL
            cursor.execute(sql)

            # For databases without autocommit, commit explicitly
            if hasattr(conn, "autocommit") and not conn.autocommit:
                conn.commit()
            elif self._db_type == "sqlite":
                conn.commit()

            cursor.close()
            logger.debug(
                "sync_ddl_executor.successfully_executed_ddl", extra={"sql": sql[:100]}
            )
            return {"success": True, "sql": sql}

        except Exception as e:
            error_str = str(e)
            # #1537: MySQL's CREATE INDEX has no IF NOT EXISTS, so a re-migration
            # (auto_migrate on an existing table) raises 1061 "Duplicate key
            # name". That — and the PG/SQLite "already exists" form — means the
            # object is already present, which is benign for an idempotent DDL
            # re-run. Log it at DEBUG, not ERROR (scope 1061 to CREATE INDEX so a
            # duplicate key inside a CREATE TABLE still surfaces as ERROR). The
            # return value is unchanged: the caller still receives
            # {success: False, error} and applies its own disposition. Mirrors
            # schema_state_manager.py's index-already-exists tolerance.
            if _is_benign_ddl_object_exists(error_str, sql):
                logger.debug(
                    "sync_ddl_executor.ddl_object_already_exists",
                    extra={"error": error_str, "sql": (sql or "")[:100]},
                )
            else:
                logger.error(
                    "sync_ddl_executor.ddl_execution_failed",
                    extra={"error": error_str},
                )
            return {"success": False, "error": error_str, "sql": sql}

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute_ddl_batch(self, sql_statements: List[str]) -> Dict[str, Any]:
        """
        Execute multiple DDL statements in sequence.

        Args:
            sql_statements: List of DDL SQL statements

        Returns:
            Dict with 'success', 'executed_count', and optionally 'error'
        """
        conn = None
        executed = 0
        try:
            conn = self._get_sync_connection()
            cursor = conn.cursor()

            for sql in sql_statements:
                cursor.execute(sql)
                executed += 1

            # Commit all changes
            if hasattr(conn, "autocommit") and not conn.autocommit:
                conn.commit()
            elif self._db_type == "sqlite":
                conn.commit()

            cursor.close()
            logger.debug(
                "sync_ddl_executor.successfully_executed_ddl_statements",
                extra={"executed": executed},
            )
            return {"success": True, "executed_count": executed}

        except Exception as e:
            error_str = str(e)
            failed_sql = (
                sql_statements[executed] if executed < len(sql_statements) else None
            )
            # #1537: a MySQL re-migration aborts this batch at the first
            # IF-NOT-EXISTS-less CREATE INDEX with 1061 "Duplicate key name" —
            # a benign already-present object (scoped to CREATE INDEX). Log at
            # DEBUG, not ERROR; the caller still gets {success: False, error}
            # and decides. Mirrors schema_state_manager.py.
            if _is_benign_ddl_object_exists(error_str, failed_sql):
                logger.debug(
                    "sync_ddl_executor.ddl_batch_object_already_exists",
                    extra={"executed_1": executed + 1, "error": error_str},
                )
            else:
                logger.error(
                    "sync_ddl_executor.ddl_batch_execution_failed_at_statement",
                    extra={"executed_1": executed + 1, "error": error_str},
                )
            return {
                "success": False,
                "error": error_str,
                "executed_count": executed,
                "failed_sql": failed_sql,
            }

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute_ddl_batch_per_statement(
        self, sql_statements: List[str]
    ) -> List[Dict[str, Any]]:
        """Execute multiple DDL statements on ONE connection, per-statement results.

        Issue #714 — DDL connection thrash. Routing every DDL through a
        fresh ``AsyncSQLDatabaseNode`` (or fresh sync connection) is
        overkill: DDL is single-connection work that does NOT need a
        pool, transaction-mode, or fetch-mode plumbing. This method
        acquires ONE sync connection from the dialect driver
        (psycopg2 / sqlite3 / pymysql), iterates the statements in
        order, and releases the connection in a try/finally.

        Unlike :meth:`execute_ddl_batch`, this method does NOT abort on
        first error. Each statement's success/error is captured and
        returned as a separate dict so the caller (DataFlow's
        ``_execute_ddl`` path) can apply the issue #696 fail-fast
        circuit-breaker per CREATE TABLE failure while continuing past
        index/FK/auxiliary failures (legacy semantics).

        Args:
            sql_statements: List of DDL SQL statements (CREATE/ALTER/INDEX/etc.)

        Returns:
            List of per-statement result dicts with shape::

                {"sql": str, "success": bool, "error": Optional[str], "duration_ms": float}

            One entry per input statement; ordering preserved.
        """
        import time

        conn = None
        results: List[Dict[str, Any]] = []
        try:
            conn = self._get_sync_connection()
            for sql in sql_statements:
                if not sql or not sql.strip():
                    # Preserve indexing parity with the input list.
                    results.append(
                        {
                            "sql": sql,
                            "success": True,
                            "error": None,
                            "duration_ms": 0.0,
                        }
                    )
                    continue

                t0 = time.monotonic()
                try:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    # Per-statement commit for sqlite; psycopg2/pymysql
                    # are autocommit-true at connection setup time.
                    if hasattr(conn, "autocommit") and not conn.autocommit:
                        conn.commit()
                    elif self._db_type == "sqlite":
                        conn.commit()
                    cursor.close()
                    duration_ms = (time.monotonic() - t0) * 1000.0
                    results.append(
                        {
                            "sql": sql,
                            "success": True,
                            "error": None,
                            "duration_ms": duration_ms,
                        }
                    )
                except Exception as e:
                    # Per-statement failure: preserve traceback chain
                    # via _last_exception so caller can re-raise as
                    # DDLFailedError without losing the original cause.
                    duration_ms = (time.monotonic() - t0) * 1000.0
                    results.append(
                        {
                            "sql": sql,
                            "success": False,
                            "error": str(e),
                            "exception": e,
                            "duration_ms": duration_ms,
                        }
                    )
                    # Cursor may be in a bad state on PostgreSQL after a
                    # failed DDL — rollback so the connection is reusable
                    # for subsequent statements (legacy semantics).
                    try:
                        if hasattr(conn, "rollback"):
                            conn.rollback()
                    except Exception:
                        pass
            return results
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute_query(self, sql: str, params: Optional[Tuple] = None) -> Dict[str, Any]:
        """
        Execute a query and return results (for schema inspection).

        Args:
            sql: The SQL query
            params: Optional query parameters as tuple

        Returns:
            Dict with 'result' (list of tuples) or 'error'
        """
        conn = None
        try:
            conn = self._get_sync_connection()
            cursor = conn.cursor()

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Fetch all rows
            rows = cursor.fetchall()

            # Get column names if available
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else None
            )

            cursor.close()
            return {"result": rows, "columns": columns}

        except Exception as e:
            logger.error(
                "sync_ddl_executor.query_execution_failed", extra={"error": str(e)}
            )
            return {"error": str(e), "sql": sql}

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        if self._db_type == "postgresql":
            sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
            """
            result = self.execute_query(sql, (table_name,))
        elif self._db_type == "sqlite":
            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            result = self.execute_query(sql, (table_name,))
        elif self._db_type == "mysql":
            sql = "SHOW TABLES LIKE %s"
            result = self.execute_query(sql, (table_name,))
        else:
            return False

        if "error" in result:
            logger.error(
                "sync_ddl_executor.failed_to_check_table_existence",
                extra={"error": result["error"]},
            )
            return False

        rows = result.get("result", [])
        if self._db_type == "postgresql":
            return rows[0][0] if rows else False
        else:
            return len(rows) > 0

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        Args:
            table_name: Name of the table

        Returns:
            List of column info dicts with 'name', 'type', 'nullable', etc.
        """
        if self._db_type == "postgresql":
            sql = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """
            result = self.execute_query(sql, (table_name,))
        elif self._db_type == "sqlite":
            # rules/dataflow-identifier-safety.md MUST 1: identifiers in DDL/PRAGMA
            # paths MUST be validated against the canonical regex before
            # interpolation. PRAGMA arguments are not parameterizable.
            _validate_identifier(table_name)
            sql = f"PRAGMA table_info({table_name})"
            result = self.execute_query(sql)
        else:
            return []

        if "error" in result:
            logger.error(
                "sync_ddl_executor.failed_to_get_columns",
                extra={"error": result["error"]},
            )
            return []

        columns = []
        rows = result.get("result", [])

        if self._db_type == "postgresql":
            for row in rows:
                columns.append(
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                        "max_length": row[4],
                    }
                )
        elif self._db_type == "sqlite":
            for row in rows:
                columns.append(
                    {
                        "name": row[1],
                        "type": row[2],
                        "nullable": row[3] == 0,
                        "default": row[4],
                        "primary_key": row[5] == 1,
                    }
                )

        return columns
