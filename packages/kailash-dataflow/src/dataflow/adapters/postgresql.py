"""
PostgreSQL Database Adapter

PostgreSQL-specific database adapter implementation.
"""

import logging
import sys
import traceback
import warnings
from typing import Any, Dict, List, Tuple

from .base import DatabaseAdapter
from .dialect import DialectManager
from .exceptions import AdapterError, ConnectionError, QueryError, TransactionError

_pg_dialect = DialectManager.get_dialect("postgresql")


def _safe_identifier(name: str) -> str:
    """Validate and quote a SQL identifier (PostgreSQL double-quote style)."""
    return _pg_dialect.quote_identifier(name)


logger = logging.getLogger(__name__)


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter."""

    @property
    def source_type(self) -> str:
        return "postgresql"

    @property
    def default_port(self) -> int:
        return 5432

    def __init__(self, connection_string: str, **kwargs):
        super().__init__(connection_string, **kwargs)

        # PostgreSQL-specific configuration
        self.ssl_mode = self.query_params.get("sslmode", "prefer")
        self.application_name = kwargs.get("application_name", "dataflow")

        # Use actual port or default
        if self.port is None:
            self.port = self.default_port

    async def connect(self) -> None:
        """Establish PostgreSQL connection (legacy method - use create_connection_pool)."""
        await self.create_connection_pool()

    async def disconnect(self) -> None:
        """Close PostgreSQL connection (legacy method - use close_connection_pool)."""
        await self.close_connection_pool()

    async def create_connection_pool(self) -> None:
        """Create PostgreSQL connection pool using asyncpg with connection reset callback."""
        try:
            import asyncpg

            # Define connection reset callback to prevent transaction leaks
            async def reset_connection(conn):
                """Reset connection state before returning to pool."""
                try:
                    if conn.is_in_transaction():
                        logger.warning(
                            "Connection released with open transaction - rolling back"
                        )
                        await conn.execute("ROLLBACK")
                except Exception as e:
                    logger.warning(
                        "postgresql.connection_reset_failed", extra={"error": str(e)}
                    )

            # Build connection parameters
            params = self.get_connection_parameters()

            # Create connection pool with reset callback
            params["reset"] = reset_connection
            self.connection_pool = await asyncpg.create_pool(**params)
            self.is_connected = True

            # Emit a connection-established INFO without any URL-derived
            # fields (host, port, database). CodeQL's
            # ``py/clear-text-logging-sensitive-data`` taint analysis
            # traces every attribute read from ``urlparse(connection_string)``
            # through to logger sinks and cannot distinguish coordinates
            # (host/port/database) from credentials (password) by attribute
            # name alone. The custom sanitizer barrier in
            # ``.github/codeql/sanitizers/sanitizers.model.yml`` was not
            # reliably honored across CodeQL releases; the structural
            # defense is to drop the URL-derived fields from the log
            # line entirely. Operators already know which DATABASE_URL
            # they configured; the INFO only needs to confirm pool
            # creation succeeded.
            logger.info("postgresql.connection_pool.created")

        except ImportError:
            raise ConnectionError(
                "asyncpg is required for PostgreSQL support. Install with: pip install asyncpg"
            )
        except Exception as e:
            logger.error(
                "postgresql.failed_to_create_postgresql_connection_pool",
                extra={"error": str(e)},
            )
            raise ConnectionError(f"Connection failed: {e}")

    async def close_connection_pool(self) -> None:
        """Close PostgreSQL connection pool."""
        if self.connection_pool:
            await self.connection_pool.close()
            self.connection_pool = None
            self.is_connected = False
            logger.info("PostgreSQL connection pool closed")

    async def execute_query(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute PostgreSQL query and return results."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            # Format query for PostgreSQL parameter style
            pg_query, pg_params = self.format_query(query, params)

            # Execute query using connection pool
            async with self.connection_pool.acquire() as connection:
                if pg_params:
                    rows = await connection.fetch(pg_query, *pg_params)
                else:
                    rows = await connection.fetch(pg_query)

                # Convert asyncpg Records to dictionaries
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(
                "postgresql.postgresql_query_execution_failed", extra={"error": str(e)}
            )
            raise QueryError(f"Query execution failed: {e}")

    async def execute_insert(self, query: str, params: List[Any] = None) -> Any:
        """Execute INSERT query and return result."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            pg_query, pg_params = self.format_query(query, params)

            async with self.connection_pool.acquire() as connection:
                if pg_params:
                    return await connection.execute(pg_query, *pg_params)
                else:
                    return await connection.execute(pg_query)

        except Exception as e:
            logger.error("postgresql.postgresql_insert_failed", extra={"error": str(e)})
            raise QueryError(f"Insert failed: {e}")

    async def execute_bulk_insert(self, query: str, params_list: List[Tuple]) -> None:
        """Execute bulk insert operation."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            pg_query, _ = self.format_query(query, [])

            async with self.connection_pool.acquire() as connection:
                await connection.executemany(pg_query, params_list)

        except Exception as e:
            logger.error(
                "postgresql.postgresql_bulk_insert_failed", extra={"error": str(e)}
            )
            raise QueryError(f"Bulk insert failed: {e}")

    def transaction(self):
        """Return transaction context manager."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        return PostgreSQLTransaction(self.connection_pool)

    async def execute_transaction(
        self, queries: List[Tuple[str, List[Any]]]
    ) -> List[Any]:
        """Execute multiple queries in a single PostgreSQL transaction.

        All queries run on the SAME connection within an explicit transaction
        block. On success, all queries are committed atomically. On failure,
        all queries are rolled back — no partial commits.

        Args:
            queries: List of (query_string, params_list) tuples.

        Returns:
            List of result sets, one per query.

        Raises:
            TransactionError: If any query fails (all rolled back).
        """
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            results = []
            logger.debug(
                "transaction.start",
                extra={"query_count": len(queries)},
            )

            # Acquire a SINGLE connection and run all queries within its transaction
            async with self.connection_pool.acquire() as connection:
                async with connection.transaction():
                    for query, params in queries:
                        pg_query, pg_params = self.format_query(query, params)
                        if pg_params:
                            rows = await connection.fetch(pg_query, *pg_params)
                        else:
                            rows = await connection.fetch(pg_query)
                        results.append([dict(row) for row in rows])

            logger.debug(
                "transaction.ok",
                extra={"query_count": len(queries)},
            )
            return results
        except Exception as e:
            logger.error(
                "transaction.error",
                extra={"error": str(e), "query_count": len(queries)},
            )
            raise TransactionError(f"Transaction failed: {e}")

    async def get_table_schema(self, table_name: str) -> Dict[str, Dict]:
        """Get PostgreSQL table schema using INFORMATION_SCHEMA."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """

            rows = await self.execute_query(query, [table_name])

            # Get primary key information
            pk_query = """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = $1::regclass AND i.indisprimary
            """
            pk_rows = await self.execute_query(pk_query, [table_name])
            primary_keys = {row["attname"] for row in pk_rows}

            schema = {}
            for row in rows:
                column_info = {
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "primary_key": row["column_name"] in primary_keys,
                }

                if row["column_default"] is not None:
                    column_info["default"] = row["column_default"]

                if row["character_maximum_length"] is not None:
                    column_info["max_length"] = row["character_maximum_length"]

                if row["numeric_precision"] is not None:
                    column_info["precision"] = row["numeric_precision"]

                if row["numeric_scale"] is not None:
                    column_info["scale"] = row["numeric_scale"]

                schema[row["column_name"]] = column_info

            return schema

        except Exception as e:
            logger.error(
                "postgresql.failed_to_get_table_schema", extra={"error": str(e)}
            )
            raise QueryError(f"Failed to get table schema: {e}")

    async def create_table(self, table_name: str, schema: Dict[str, Dict]) -> None:
        """Create PostgreSQL table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Build CREATE TABLE statement
            columns = []
            primary_keys = []

            for col_name, col_info in schema.items():
                col_type = col_info["type"]

                # Handle max_length for varchar/char types
                if (
                    col_type.lower() in ["varchar", "character varying"]
                    and "max_length" in col_info
                ):
                    col_def = f'"{col_name}" VARCHAR({col_info["max_length"]})'
                elif (
                    col_type.lower() in ["char", "character"]
                    and "max_length" in col_info
                ):
                    col_def = f'"{col_name}" CHAR({col_info["max_length"]})'
                else:
                    col_def = f'"{col_name}" {col_type.upper()}'

                if not col_info.get("nullable", True):
                    col_def += " NOT NULL"

                if "default" in col_info and col_info["default"] is not None:
                    col_def += f" DEFAULT {col_info['default']}"

                columns.append(col_def)

                if col_info.get("primary_key"):
                    primary_keys.append(f'"{col_name}"')

            if primary_keys:
                columns.append(f"PRIMARY KEY ({', '.join(primary_keys)})")

            query = f"CREATE TABLE IF NOT EXISTS {_safe_identifier(table_name)} ({', '.join(columns)})"

            await self.execute_query(query)
            logger.info("postgresql.created_table", extra={"table_name": table_name})

        except Exception as e:
            logger.error("postgresql.failed_to_create_table", extra={"error": str(e)})
            raise QueryError(f"Failed to create table: {e}")

    async def drop_table(self, table_name: str) -> None:
        """Drop PostgreSQL table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = f"DROP TABLE IF EXISTS {_safe_identifier(table_name)}"
            await self.execute_query(query)
            logger.info("postgresql.dropped_table", extra={"table_name": table_name})

        except Exception as e:
            logger.error("postgresql.failed_to_drop_table", extra={"error": str(e)})
            raise QueryError(f"Failed to drop table: {e}")

    def get_dialect(self) -> str:
        """Get PostgreSQL dialect."""
        return "postgresql"

    def supports_feature(self, feature: str) -> bool:
        """Check PostgreSQL feature support."""
        postgresql_features = {
            "json": True,
            "arrays": True,
            "regex": True,
            "window_functions": True,
            "cte": True,
            "upsert": True,
            "hstore": True,
            "fulltext_search": True,
            "spatial_indexes": True,
            "mysql_specific": False,
            "sqlite_specific": False,
        }
        return postgresql_features.get(feature, False)

    def format_query(
        self, query: str, params: List[Any] = None
    ) -> Tuple[str, List[Any]]:
        """Format query for PostgreSQL parameter style ($1, $2, etc.)."""
        if params is None:
            params = []

        # Convert ? placeholders to $1, $2, etc.
        formatted_query = query
        param_count = 1

        while "?" in formatted_query:
            formatted_query = formatted_query.replace("?", f"${param_count}", 1)
            param_count += 1

        return formatted_query, params

    def get_connection_parameters(self) -> Dict[str, Any]:
        """Get asyncpg connection parameters.

        Forwards all URL-parsed parameters to asyncpg, including:
        - ssl: derived from sslmode (disable→False, require→True, prefer→None)
        - server_settings: application_name for pg_stat_activity visibility
        - command_timeout: from pool_timeout
        """
        params: Dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.username,
            "password": self.password,
            "min_size": self.pool_size,
            "max_size": self.pool_size + self.max_overflow,
            "command_timeout": self.pool_timeout,
        }

        # SSL mode translation for asyncpg
        # asyncpg uses ssl=bool|SSLContext, not sslmode=str
        if self.ssl_mode == "disable":
            params["ssl"] = False
        elif self.ssl_mode == "require":
            params["ssl"] = True
        elif self.ssl_mode in ("verify-ca", "verify-full"):
            import ssl

            ssl_ctx = ssl.create_default_context()
            # Load client certificates if specified in URL query params
            sslrootcert = self.query_params.get("sslrootcert")
            sslcert = self.query_params.get("sslcert")
            sslkey = self.query_params.get("sslkey")
            if sslrootcert:
                ssl_ctx.load_verify_locations(sslrootcert)
            if sslcert and sslkey:
                ssl_ctx.load_cert_chain(sslcert, sslkey)
            if self.ssl_mode == "verify-full":
                ssl_ctx.check_hostname = True
            else:
                ssl_ctx.check_hostname = False
            params["ssl"] = ssl_ctx
        # sslmode=prefer (default): asyncpg default behavior (attempt upgrade)

        # Application name for pg_stat_activity visibility
        if self.application_name:
            params["server_settings"] = {
                "application_name": self.application_name,
            }

        return params

    def get_tables_query(self) -> str:
        """Get query to list all tables."""
        return """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """

    def get_columns_query(self, table_name: str) -> str:
        """Get query to list table columns.

        Note: table_name is validated via _safe_identifier to prevent injection.
        The value is used in a WHERE clause string literal, not as a SQL identifier,
        but validation ensures it contains only safe characters.
        """
        _safe_identifier(table_name)  # validate, discard quoted form
        return f"""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = '{table_name}'
        ORDER BY ordinal_position
        """

    async def get_server_version(self) -> str:
        """Get PostgreSQL server version."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            result = await self.execute_query("SELECT version() as version")
            return result[0]["version"]
        except Exception as e:
            logger.error(
                "postgresql.failed_to_get_server_version", extra={"error": str(e)}
            )
            return "unknown"

    async def get_database_size(self) -> int:
        """Get database size in bytes."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = "SELECT pg_database_size(current_database()) as size_bytes"
            result = await self.execute_query(query)
            return result[0]["size_bytes"] or 0
        except Exception as e:
            logger.error(
                "postgresql.failed_to_get_database_size", extra={"error": str(e)}
            )
            return 0

    @property
    def supports_transactions(self) -> bool:
        """PostgreSQL supports transactions."""
        return True

    @property
    def supports_savepoints(self) -> bool:
        """PostgreSQL supports savepoints."""
        return True


class PostgreSQLTransaction:
    """PostgreSQL transaction context manager with guaranteed cleanup."""

    # Class-level defaults (safety net if __init__ fails partway)
    _committed = False
    _rolled_back = False
    connection = None
    transaction = None
    _source_traceback = None

    def __init__(self, connection_pool):
        self.connection_pool = connection_pool
        self.connection = None
        self.transaction = None
        self._committed = False
        self._rolled_back = False
        if sys.flags.dev_mode or __debug__:
            self._source_traceback = traceback.extract_stack()

    def __del__(self, _warnings=warnings):
        if self._committed or self._rolled_back or self.connection is None:
            return
        tb = ""
        if self._source_traceback:
            try:
                tb = "\n" + "".join(traceback.format_list(self._source_traceback))
            except Exception:
                tb = ""
        _warnings.warn(
            f"PostgreSQLTransaction GC'd without commit/rollback. Created at:{tb}",
            ResourceWarning,
            stacklevel=1,
        )
        # Cannot do sync rollback on asyncpg connection — just warn.
        # The connection will be reset when returned to pool via pool's reset callback.

    async def __aenter__(self):
        """Enter transaction context."""
        self.connection = await self.connection_pool.acquire()
        self.transaction = self.connection.transaction()
        await self.transaction.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context with guaranteed cleanup."""
        try:
            if exc_type is None:
                # No exception, commit transaction if not already done
                if not self._committed and not self._rolled_back:
                    await self.transaction.commit()
                    self._committed = True
            else:
                # Exception occurred, rollback transaction if not already done
                if not self._committed and not self._rolled_back:
                    await self.transaction.rollback()
                    self._rolled_back = True
        except Exception as cleanup_error:
            # Log cleanup error but don't raise (preserve original exception)
            logger.error(
                "postgresql.transaction_cleanup_failed",
                extra={"cleanup_error": cleanup_error},
                exc_info=True,
            )
        finally:
            # CRITICAL: Always release connection to pool
            if self.connection:
                await self.connection_pool.release(self.connection)

    async def commit(self):
        """Explicitly commit transaction."""
        if self._committed:
            raise TransactionError("Transaction already committed")
        if self._rolled_back:
            raise TransactionError("Transaction already rolled back")

        await self.transaction.commit()
        self._committed = True

    async def rollback(self):
        """Explicitly rollback transaction."""
        if self._committed:
            raise TransactionError("Transaction already committed")
        if self._rolled_back:
            raise TransactionError("Transaction already rolled back")

        await self.transaction.rollback()
        self._rolled_back = True
