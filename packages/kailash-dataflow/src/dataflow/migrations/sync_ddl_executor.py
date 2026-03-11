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
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
            # Default to SQLite for safety
            logger.warning(
                f"Unknown database type in URL, defaulting to SQLite: {self.database_url}"
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
                "psycopg2 is required for PostgreSQL migrations. "
                "Install with: pip install psycopg2-binary"
            )

    def _get_sqlite_connection(self):
        """Get a synchronous SQLite connection."""
        db_path = self.database_url
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        elif db_path.startswith("sqlite://"):
            db_path = db_path.replace("sqlite://", "")

        # For in-memory databases
        if db_path == "" or db_path == ":memory:":
            db_path = ":memory:"

        conn = sqlite3.connect(db_path, check_same_thread=False)
        logger.debug(f"Created sync SQLite connection for DDL: {db_path}")
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
            logger.debug(f"Successfully executed DDL: {sql[:100]}...")
            return {"success": True, "sql": sql}

        except Exception as e:
            logger.error(f"DDL execution failed: {e}")
            return {"success": False, "error": str(e), "sql": sql}

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
            logger.debug(f"Successfully executed {executed} DDL statements")
            return {"success": True, "executed_count": executed}

        except Exception as e:
            logger.error(f"DDL batch execution failed at statement {executed + 1}: {e}")
            return {
                "success": False,
                "error": str(e),
                "executed_count": executed,
                "failed_sql": (
                    sql_statements[executed] if executed < len(sql_statements) else None
                ),
            }

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
            logger.error(f"Query execution failed: {e}")
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
            logger.error(f"Failed to check table existence: {result['error']}")
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
            sql = f"PRAGMA table_info({table_name})"
            result = self.execute_query(sql)
        else:
            return []

        if "error" in result:
            logger.error(f"Failed to get columns: {result['error']}")
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
