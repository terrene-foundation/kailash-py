"""
MySQL Database Adapter

MySQL-specific database adapter implementation with real aiomysql support.
"""

import logging
import sys
import traceback
import warnings
from typing import Any, Dict, List, Tuple

from .base import DatabaseAdapter
from .dialect import DialectManager
from .exceptions import AdapterError, ConnectionError, QueryError, TransactionError

_mysql_dialect = DialectManager.get_dialect("mysql")


def _safe_identifier(name: str) -> str:
    """Validate and quote a SQL identifier (MySQL backtick style)."""
    return _mysql_dialect.quote_identifier(name)


logger = logging.getLogger(__name__)

# Import aiomysql at module level
try:
    import aiomysql
except ImportError:
    aiomysql = None


class MySQLAdapter(DatabaseAdapter):
    """MySQL database adapter with real aiomysql support."""

    @property
    def source_type(self) -> str:
        return "mysql"

    @property
    def default_port(self) -> int:
        return 3306

    def __init__(self, connection_string: str, **kwargs):
        super().__init__(connection_string, **kwargs)

        # MySQL-specific configuration
        self.charset = kwargs.get(
            "charset", self.query_params.get("charset", "utf8mb4")
        )
        self.collation = kwargs.get("collation", "utf8mb4_unicode_ci")
        self.autocommit = kwargs.get("autocommit", False)
        self.use_unicode = kwargs.get("use_unicode", True)

        # Connection settings
        self.connect_timeout = kwargs.get("connect_timeout", 10)
        self.read_timeout = kwargs.get("read_timeout", None)
        self.write_timeout = kwargs.get("write_timeout", None)

        # SSL configuration
        self.ssl_ca = kwargs.get("ssl_ca", self.query_params.get("ssl-ca"))
        self.ssl_cert = kwargs.get("ssl_cert", self.query_params.get("ssl-cert"))
        self.ssl_key = kwargs.get("ssl_key", self.query_params.get("ssl-key"))
        self.ssl_verify_cert = kwargs.get("ssl_verify_cert", False)

        # Use actual port or default
        if self.port is None:
            self.port = self.default_port

    async def connect(self) -> None:
        """Establish MySQL connection (legacy method - use create_connection_pool)."""
        await self.create_connection_pool()

    async def disconnect(self) -> None:
        """Close MySQL connection (legacy method - use close_connection_pool)."""
        await self.close_connection_pool()

    async def create_connection_pool(self) -> None:
        """Create MySQL connection pool using aiomysql."""
        if aiomysql is None:
            raise ConnectionError(
                "aiomysql is required for MySQL support. Install with: pip install aiomysql"
            )

        try:
            # Build connection parameters
            params = self.get_connection_parameters()

            # Create connection pool
            self.connection_pool = await aiomysql.create_pool(**params)
            self.is_connected = True

            logger.info(
                f"Created MySQL connection pool: {self.host}:{self.port}/{self.database}"
            )

        except Exception as e:
            logger.error(f"Failed to create MySQL connection pool: {e}")
            raise ConnectionError(f"Connection failed: {e}")

    async def close_connection_pool(self) -> None:
        """Close MySQL connection pool."""
        if self.connection_pool:
            self.connection_pool.close()
            await self.connection_pool.wait_closed()
            self.connection_pool = None
            self.is_connected = False
            logger.info("MySQL connection pool closed")

    async def execute_query(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute MySQL query and return results."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            # Format query for MySQL parameter style
            mysql_query, mysql_params = self.format_query(query, params)

            # Execute query using connection pool
            async with self.connection_pool.acquire() as connection:
                async with connection.cursor(aiomysql.DictCursor) as cursor:
                    if mysql_params:
                        await cursor.execute(mysql_query, mysql_params)
                    else:
                        await cursor.execute(mysql_query)

                    # Fetch all results
                    rows = await cursor.fetchall()

                    # aiomysql DictCursor returns list of dicts
                    return list(rows) if rows else []

        except Exception as e:
            logger.error(f"MySQL query execution failed: {e}")
            raise QueryError(f"Query execution failed: {e}")

    async def execute_insert(self, query: str, params: List[Any] = None) -> Any:
        """Execute INSERT query and return last insert ID."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            mysql_query, mysql_params = self.format_query(query, params)

            async with self.connection_pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    if mysql_params:
                        await cursor.execute(mysql_query, mysql_params)
                    else:
                        await cursor.execute(mysql_query)

                    await connection.commit()

                    # Return last insert ID and rows affected
                    return {"lastrowid": cursor.lastrowid, "rowcount": cursor.rowcount}

        except Exception as e:
            logger.error(f"MySQL insert failed: {e}")
            raise QueryError(f"Insert failed: {e}")

    async def execute_bulk_insert(self, query: str, params_list: List[Tuple]) -> None:
        """Execute bulk insert operation."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            mysql_query, _ = self.format_query(query, [])

            async with self.connection_pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    await cursor.executemany(mysql_query, params_list)
                    await connection.commit()

        except Exception as e:
            logger.error(f"MySQL bulk insert failed: {e}")
            raise QueryError(f"Bulk insert failed: {e}")

    def transaction(self):
        """Return transaction context manager."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        return MySQLTransaction(self.connection_pool)

    async def execute_transaction(
        self, queries: List[Tuple[str, List[Any]]]
    ) -> List[Any]:
        """Execute multiple queries in MySQL transaction."""
        if not self.is_connected or not self.connection_pool:
            raise ConnectionError("Not connected to database")

        try:
            results = []
            logger.debug(f"Starting transaction with {len(queries)} queries")

            async with self.transaction() as trans:
                for query, params in queries:
                    result = await self.execute_query(query, params)
                    results.append(result)

            logger.debug("Transaction completed successfully")
            return results
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            raise TransactionError(f"Transaction failed: {e}")

    async def get_table_schema(self, table_name: str) -> Dict[str, Dict]:
        """Get MySQL table schema using INFORMATION_SCHEMA."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = """
            SELECT
                COLUMN_NAME,
                COLUMN_TYPE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_DEFAULT,
                EXTRA,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """

            rows = await self.execute_query(query, [self.database, table_name])

            schema = {}
            for row in rows:
                column_info = {
                    "type": row["COLUMN_TYPE"],
                    "nullable": row["IS_NULLABLE"] == "YES",
                    "primary_key": row["COLUMN_KEY"] == "PRI",
                    "auto_increment": "auto_increment" in row["EXTRA"].lower(),
                }

                if row["COLUMN_DEFAULT"] is not None:
                    column_info["default"] = row["COLUMN_DEFAULT"]

                if row["CHARACTER_MAXIMUM_LENGTH"] is not None:
                    column_info["max_length"] = row["CHARACTER_MAXIMUM_LENGTH"]

                if row["NUMERIC_PRECISION"] is not None:
                    column_info["precision"] = row["NUMERIC_PRECISION"]

                if row["NUMERIC_SCALE"] is not None:
                    column_info["scale"] = row["NUMERIC_SCALE"]

                schema[row["COLUMN_NAME"]] = column_info

            return schema

        except Exception as e:
            logger.error(f"Failed to get table schema: {e}")
            raise QueryError(f"Failed to get table schema: {e}")

    async def create_table(self, table_name: str, schema: Dict[str, Dict]) -> None:
        """Create MySQL table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Build CREATE TABLE statement
            columns = []
            primary_keys = []

            for col_name, col_info in schema.items():
                col_def = f"`{col_name}` {col_info['type']}"

                if not col_info.get("nullable", True):
                    col_def += " NOT NULL"

                if col_info.get("auto_increment"):
                    col_def += " AUTO_INCREMENT"

                if "default" in col_info:
                    col_def += f" DEFAULT {col_info['default']}"

                columns.append(col_def)

                if col_info.get("primary_key"):
                    primary_keys.append(f"`{col_name}`")

            if primary_keys:
                columns.append(f"PRIMARY KEY ({', '.join(primary_keys)})")

            _safe_identifier(table_name)  # validate (MySQL uses backtick quoting)
            query = f"CREATE TABLE `{table_name}` ({', '.join(columns)})"
            query += f" ENGINE=InnoDB DEFAULT CHARSET={self.charset} COLLATE={self.collation}"

            await self.execute_query(query)
            logger.info(f"Created table: {table_name}")

        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise QueryError(f"Failed to create table: {e}")

    async def drop_table(self, table_name: str) -> None:
        """Drop MySQL table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            _safe_identifier(table_name)  # validate (MySQL uses backtick quoting)
            query = f"DROP TABLE IF EXISTS `{table_name}`"
            await self.execute_query(query)
            logger.info(f"Dropped table: {table_name}")

        except Exception as e:
            logger.error(f"Failed to drop table: {e}")
            raise QueryError(f"Failed to drop table: {e}")

    def get_dialect(self) -> str:
        """Get MySQL dialect."""
        return "mysql"

    def supports_feature(self, feature: str) -> bool:
        """Check MySQL feature support."""
        mysql_features = {
            "json": True,  # MySQL 5.7+
            "arrays": False,
            "regex": True,
            "window_functions": True,  # MySQL 8.0+
            "cte": True,  # MySQL 8.0+
            "upsert": True,  # INSERT ... ON DUPLICATE KEY UPDATE
            "fulltext_search": True,
            "spatial_indexes": True,
            "hstore": False,  # PostgreSQL-specific
            "mysql_specific": True,
            "sqlite_specific": False,
            "postgresql_specific": False,
        }
        return mysql_features.get(feature, False)

    def format_query(
        self, query: str, params: List[Any] = None
    ) -> Tuple[str, List[Any]]:
        """Format query for MySQL parameter style (%s)."""
        if params is None:
            params = []

        # Convert ? placeholders to %s
        formatted_query = query.replace("?", "%s")

        return formatted_query, params

    def get_connection_parameters(self) -> Dict[str, Any]:
        """Get aiomysql connection parameters."""
        params = {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "password": self.password,
            "db": self.database,
            "charset": self.charset,
            "autocommit": self.autocommit,
            "minsize": self.pool_size,
            "maxsize": self.pool_size + self.max_overflow,
            "pool_recycle": self.pool_recycle,
            "connect_timeout": self.connect_timeout,
        }

        # Add optional parameters
        if self.read_timeout:
            params["read_timeout"] = self.read_timeout
        if self.write_timeout:
            params["write_timeout"] = self.write_timeout

        # Add SSL parameters if configured
        if self.ssl_ca or self.ssl_cert or self.ssl_key:
            ssl_params = {}
            if self.ssl_ca:
                ssl_params["ca"] = self.ssl_ca
            if self.ssl_cert:
                ssl_params["cert"] = self.ssl_cert
            if self.ssl_key:
                ssl_params["key"] = self.ssl_key
            ssl_params["check_hostname"] = self.ssl_verify_cert
            params["ssl"] = ssl_params

        return params

    def get_tables_query(self) -> str:
        """Get query to list all tables.

        Note: self.database is validated via _safe_identifier to prevent injection.
        """
        _safe_identifier(self.database)  # validate
        return f"""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{self.database}'
        AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """

    def get_columns_query(self, table_name: str) -> str:
        """Get query to list table columns.

        Note: self.database and table_name are validated via _safe_identifier
        to prevent injection.
        """
        _safe_identifier(self.database)  # validate
        _safe_identifier(table_name)  # validate
        return f"""
        SELECT
            COLUMN_NAME,
            COLUMN_TYPE,
            IS_NULLABLE,
            COLUMN_DEFAULT,
            CHARACTER_MAXIMUM_LENGTH,
            COLUMN_KEY,
            EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{self.database}'
        AND TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """

    async def get_storage_engines(self) -> Dict[str, Dict]:
        """Get available MySQL storage engines."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = "SHOW ENGINES"
            rows = await self.execute_query(query)

            engines = {}
            for row in rows:
                engines[row["Engine"]] = {
                    "support": row["Support"],
                    "comment": row["Comment"],
                    "transactions": row.get("Transactions", "NO"),
                    "xa": row.get("XA", "NO"),
                    "savepoints": row.get("Savepoints", "NO"),
                }

            return engines

        except Exception as e:
            logger.error(f"Failed to get storage engines: {e}")
            # Return default engines if query fails
            return {
                "InnoDB": {
                    "support": "DEFAULT",
                    "comment": "Supports transactions, row-level locking, and foreign keys",
                    "transactions": "YES",
                    "xa": "YES",
                    "savepoints": "YES",
                },
                "MyISAM": {
                    "support": "YES",
                    "comment": "MyISAM storage engine",
                    "transactions": "NO",
                    "xa": "NO",
                    "savepoints": "NO",
                },
            }

    async def get_server_version(self) -> str:
        """Get MySQL server version."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            result = await self.execute_query("SELECT VERSION() as version")
            return result[0]["version"]
        except Exception as e:
            logger.error(f"Failed to get server version: {e}")
            return "unknown"

    async def get_database_size(self) -> int:
        """Get database size in bytes."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            query = """
            SELECT SUM(data_length + index_length) as size_bytes
            FROM information_schema.TABLES
            WHERE table_schema = %s
            """
            result = await self.execute_query(query, [self.database])
            return result[0]["size_bytes"] or 0
        except Exception as e:
            logger.error(f"Failed to get database size: {e}")
            return 0

    def encode_string(self, text: str) -> str:
        """Encode string for MySQL charset."""
        # Map MySQL charset names to Python encoding names
        charset_mapping = {
            "utf8mb4": "utf-8",
            "utf8": "utf-8",
            "latin1": "latin-1",
            "ascii": "ascii",
        }
        python_charset = charset_mapping.get(self.charset, self.charset)
        try:
            return text.encode(python_charset).decode(python_charset)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback to UTF-8 if encoding fails
            return text.encode("utf-8").decode("utf-8")

    def decode_string(self, text: str) -> str:
        """Decode string from MySQL charset."""
        return text

    @property
    def supports_savepoints(self) -> bool:
        """MySQL supports savepoints with InnoDB."""
        return True

    @property
    def supports_transactions(self) -> bool:
        """MySQL supports transactions with InnoDB."""
        return True


class MySQLTransaction:
    """MySQL transaction context manager."""

    # Class-level defaults (safety net if __init__ fails partway)
    _committed = False
    _rolled_back = False
    connection = None
    _source_traceback = None

    def __init__(self, connection_pool):
        self.connection_pool = connection_pool
        self.connection = None
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
            f"MySQLTransaction GC'd without commit/rollback. Created at:{tb}",
            ResourceWarning,
            stacklevel=1,
        )
        # Cannot do sync rollback on aiomysql connection — just warn.

    async def __aenter__(self):
        """Enter transaction context."""
        self.connection = await self.connection_pool.acquire()
        await self.connection.begin()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context with guaranteed cleanup."""
        try:
            if exc_type is None:
                if not self._committed and not self._rolled_back:
                    await self.connection.commit()
                    self._committed = True
            else:
                if not self._committed and not self._rolled_back:
                    await self.connection.rollback()
                    self._rolled_back = True
        except Exception as cleanup_error:
            logger.error(
                f"MySQL transaction cleanup failed: {cleanup_error}", exc_info=True
            )
        finally:
            if self.connection is not None:
                self.connection_pool.release(self.connection)

    async def commit(self):
        """Explicitly commit transaction."""
        if self._committed:
            raise Exception("Transaction already committed")
        if self._rolled_back:
            raise Exception("Transaction already rolled back")
        if self.connection is None:
            raise Exception("No active connection")
        await self.connection.commit()
        self._committed = True

    async def rollback(self):
        """Explicitly rollback transaction."""
        if self._committed:
            raise Exception("Transaction already committed")
        if self._rolled_back:
            raise Exception("Transaction already rolled back")
        if self.connection is None:
            raise Exception("No active connection")
        await self.connection.rollback()
        self._rolled_back = True
