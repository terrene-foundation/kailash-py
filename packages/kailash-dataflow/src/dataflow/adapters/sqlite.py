"""
SQLite Database Adapter

SQLite-specific database adapter implementation.
"""

import asyncio
import logging
import os
import sys
import traceback
import warnings
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from .base import DatabaseAdapter, _safe_identifier
from .exceptions import ConnectionError, QueryError, TransactionError

try:
    from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
except ImportError:
    AsyncSQLitePool = None  # type: ignore[assignment,misc]
    SQLitePoolConfig = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class SQLiteWALMode(Enum):
    """SQLite WAL mode options."""

    DELETE = "DELETE"
    WAL = "WAL"
    MEMORY = "MEMORY"
    OFF = "OFF"


class SQLiteIsolationLevel(Enum):
    """SQLite transaction isolation levels."""

    DEFERRED = "DEFERRED"
    IMMEDIATE = "IMMEDIATE"
    EXCLUSIVE = "EXCLUSIVE"


@dataclass
class SQLiteIndexInfo:
    """Information about a SQLite index."""

    name: str
    table: str
    columns: List[str]
    unique: bool
    partial: bool
    size_kb: Optional[int] = None
    usage_count: Optional[int] = None


@dataclass
class SQLitePerformanceMetrics:
    """SQLite-specific performance metrics."""

    db_size_mb: float
    wal_size_mb: float
    cache_hit_ratio: float
    page_cache_size_mb: float
    total_pages: int
    free_pages: int
    query_plans_analyzed: int
    vacuum_needed: bool
    checkpoint_frequency: float


@dataclass
class SQLiteConnectionPoolStats:
    """Connection pool statistics for SQLite."""

    active_connections: int
    idle_connections: int
    total_connections: int
    connection_reuse_rate: float
    avg_connection_time_ms: float
    wal_checkpoint_frequency: int


class SQLiteAdapter(DatabaseAdapter):
    """SQLite database adapter."""

    @property
    def source_type(self) -> str:
        return "sqlite"

    @property
    def default_port(self) -> int:
        return 0  # SQLite doesn't use ports

    def __init__(self, connection_string: str, **kwargs):
        super().__init__(connection_string, **kwargs)

        # SQLite-specific configuration
        self._connect_kwargs: Dict[str, Any] = {}
        memory_db_name = kwargs.get("memory_db_name")

        if self.connection_string == ":memory:":
            self.database_path = ":memory:"
        elif self.connection_string.startswith("sqlite:///"):
            path_part = self.connection_string.replace("sqlite:///", "")
            if path_part == ":memory:":
                self.database_path = ":memory:"
            else:
                self.database_path = "/" + path_part
        elif self.connection_string.startswith("sqlite://"):
            self.database_path = self.connection_string.replace("sqlite://", "")
        elif self.connection_string.startswith("file:"):
            if "?" in self.connection_string:
                # URI with parameters — preserve full string
                self.database_path = self.connection_string
                self._connect_kwargs["uri"] = True
            else:
                self.database_path = self.connection_string[5:]
        else:
            # Assume it's a file path for SQLite
            self.database_path = self.connection_string

        # Detect memory databases and translate to URI shared-cache mode.
        # Each aiosqlite.connect(":memory:") creates a SEPARATE database.
        # URI shared-cache lets multiple connections see the SAME in-memory DB.
        self.is_memory_database = (
            self.database_path == ":memory:" or "mode=memory" in self.database_path
        )
        if self.database_path == ":memory:":
            name = memory_db_name or f"dataflow_{id(self)}"
            self.database_path = f"file:{name}?mode=memory&cache=shared"
            self._connect_kwargs["uri"] = True

        # Enterprise SQLite configuration
        self.enable_wal = kwargs.get(
            "enable_wal", True
        )  # Default to WAL for better concurrency
        self.wal_mode = SQLiteWALMode(
            kwargs.get("wal_mode", "WAL" if self.enable_wal else "DELETE")
        )
        self.isolation_level = SQLiteIsolationLevel(
            kwargs.get("isolation_level", "DEFERRED")
        )
        self.timeout = kwargs.get("timeout", 30.0)  # Increased for enterprise workloads
        self.busy_timeout = kwargs.get("busy_timeout", 30000)  # 30 seconds

        # Connection pooling settings
        self.max_connections = kwargs.get("max_connections", 20)
        self.connection_pool_timeout = kwargs.get("connection_pool_timeout", 10.0)
        self.enable_connection_pooling = kwargs.get("enable_connection_pooling", True)

        # Performance optimization settings
        self.cache_size_mb = kwargs.get("cache_size_mb", 64)  # 64MB default cache
        self.page_size = kwargs.get(
            "page_size", 4096
        )  # 4KB pages for optimal performance
        self.auto_vacuum = kwargs.get("auto_vacuum", "INCREMENTAL")
        self.temp_store = kwargs.get("temp_store", "MEMORY")

        # WAL mode settings
        self.wal_autocheckpoint = kwargs.get(
            "wal_autocheckpoint", 1000
        )  # Checkpoint every 1000 pages
        self.wal_checkpoint_mode = kwargs.get("wal_checkpoint_mode", "PASSIVE")

        # Monitoring settings
        self.enable_query_monitoring = kwargs.get("enable_query_monitoring", True)
        self.enable_performance_monitoring = kwargs.get(
            "enable_performance_monitoring", True
        )

        # Connection pool management
        self._connection_pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._sqlite_pool: Any = None  # AsyncSQLitePool instance (when available)
        self._active_transactions: weakref.WeakSet = weakref.WeakSet()
        self._pool_stats = SQLiteConnectionPoolStats(
            active_connections=0,
            idle_connections=0,
            total_connections=0,
            connection_reuse_rate=0.0,
            avg_connection_time_ms=0.0,
            wal_checkpoint_frequency=0,
        )

        # Performance monitoring
        self._query_count = 0
        self._total_query_time = 0.0
        self._last_vacuum_check = 0
        self._vacuum_threshold_mb = kwargs.get("vacuum_threshold_mb", 100)
        self._initial_page_count = 0
        self._initial_free_pages = 0

        # Index management
        self._tracked_indexes: Dict[str, SQLiteIndexInfo] = {}
        self._index_usage_stats: Dict[str, int] = {}

        # Enterprise PRAGMA settings optimized for performance
        self.pragmas = kwargs.get(
            "pragmas",
            {
                "foreign_keys": "ON",
                "journal_mode": self.wal_mode.value,
                "synchronous": "NORMAL",  # Balance between safety and performance
                "cache_size": f"-{self.cache_size_mb * 1024}",  # Negative for KB
                "page_size": str(self.page_size),
                "auto_vacuum": self.auto_vacuum,
                "temp_store": self.temp_store,
                "busy_timeout": str(self.busy_timeout),
                "wal_autocheckpoint": str(self.wal_autocheckpoint),
                "mmap_size": "268435456",  # 256MB memory-mapped I/O
                "optimize": "1",  # Enable query optimizer
            },
        )

        # Override with user-provided pragmas
        if "pragma_overrides" in kwargs:
            self.pragmas.update(kwargs["pragma_overrides"])

    async def connect(self) -> None:
        """Establish SQLite connection with enterprise features."""
        try:
            # Initialize connection pool if enabled
            if self.enable_connection_pooling:
                await self._initialize_connection_pool()
            else:
                # Test single connection
                await self._test_connection()

            # Store connection info
            self._connection = self.database_path
            self.is_connected = True

            # Initialize performance monitoring
            if self.enable_performance_monitoring:
                await self._initialize_performance_monitoring()

            # Create database directory if needed
            if not self.is_memory_database:
                db_path = Path(self.database_path)
                db_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(
                f"Connected to SQLite database: {self.database_path} "
                f"(WAL: {self.enable_wal}, Pool: {self.enable_connection_pooling})"
            )

        except Exception as e:
            raise ConnectionError(f"Failed to connect to SQLite: {e}")

    async def disconnect(self) -> None:
        """Close SQLite connection and cleanup resources."""
        # Check for leaked transactions before shutdown
        leaked = [
            t
            for t in self._active_transactions
            if not t._committed and not t._rolled_back
        ]
        if leaked:
            warnings.warn(
                f"SQLiteAdapter.disconnect(): {len(leaked)} transaction(s) still active. "
                f"These will be abandoned. Use 'async with' for all transactions.",
                ResourceWarning,
            )
        if self._connection:
            # Close AsyncSQLitePool if active
            if self._sqlite_pool is not None:
                await self._sqlite_pool.close()
                self._sqlite_pool = None

            # Close legacy connection pool if enabled
            if self.enable_connection_pooling:
                await self._close_connection_pool()

            # Perform final WAL checkpoint if needed
            if self.enable_wal and not self.is_memory_database:
                try:
                    await self._perform_wal_checkpoint()
                except Exception as e:
                    logger.warning(f"Failed to perform final WAL checkpoint: {e}")

            # Export performance metrics if monitoring enabled
            if self.enable_performance_monitoring:
                await self._export_performance_metrics()

            self._connection = None
            self.is_connected = False
            logger.info("Disconnected from SQLite with cleanup completed")

    @asynccontextmanager
    async def _get_connection(self):
        """Get connection from pool or create new one."""
        # Prefer AsyncSQLitePool when available (handles read/write routing,
        # health checks, connection recycling, and memory DB mode)
        if self._sqlite_pool is not None:
            async with self._sqlite_pool.acquire_write() as conn:
                yield conn
            return

        if self.enable_connection_pooling and self._connection_pool:
            # Try to get connection from pool
            async with self._pool_lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop(0)
                    self._pool_stats.idle_connections -= 1
                    self._pool_stats.active_connections += 1
                else:
                    # Pool exhausted, create new connection
                    conn = await aiosqlite.connect(
                        self.database_path, **self._connect_kwargs
                    )
                    conn.row_factory = aiosqlite.Row
                    for pragma, value in self.pragmas.items():
                        if self.is_memory_database and pragma in (
                            "journal_mode",
                            "wal_autocheckpoint",
                            "mmap_size",
                        ):
                            continue
                        await conn.execute(f"PRAGMA {pragma} = {value}")
                    self._pool_stats.total_connections += 1
                    self._pool_stats.active_connections += 1

            try:
                yield conn
            finally:
                # Reset connection state before returning to pool
                try:
                    if conn.in_transaction:
                        logger.warning(
                            "Connection released with open transaction - rolling back"
                        )
                        await conn.rollback()
                except Exception as e:
                    logger.warning(f"Connection reset failed: {e}")

                # Return connection to pool
                async with self._pool_lock:
                    self._connection_pool.append(conn)
                    self._pool_stats.idle_connections += 1
                    self._pool_stats.active_connections -= 1
        else:
            # No pooling, create temporary connection
            async with aiosqlite.connect(
                self.database_path, **self._connect_kwargs
            ) as conn:
                conn.row_factory = aiosqlite.Row
                for pragma, value in self.pragmas.items():
                    if self.is_memory_database and pragma in (
                        "journal_mode",
                        "wal_autocheckpoint",
                        "mmap_size",
                    ):
                        continue
                    await conn.execute(f"PRAGMA {pragma} = {value}")
                yield conn

    async def execute_query(
        self, query: str, params: Optional[List[Any]] = None
    ) -> List[Dict]:
        """Execute SQLite query."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # SQLite uses ? parameters (no conversion needed)
            sqlite_query, sqlite_params = self.format_query(query, params)

            logger.debug(
                f"Executing query: {sqlite_query} with params: {sqlite_params}"
            )

            # Use connection from pool
            async with self._get_connection() as db:
                cursor = await db.execute(sqlite_query, sqlite_params)

                # Check if it's a SELECT query or similar that returns data
                if (
                    sqlite_query.strip()
                    .upper()
                    .startswith(("SELECT", "WITH", "PRAGMA"))
                ):
                    rows = await cursor.fetchall()
                    results = [dict(row) for row in rows]
                else:
                    # For INSERT, UPDATE, DELETE, etc.
                    await db.commit()
                    results = [
                        {
                            "rows_affected": cursor.rowcount,
                            "lastrowid": cursor.lastrowid,
                        }
                    ]

                await cursor.close()
                return results

        except Exception as e:
            raise QueryError(f"Query execution failed: {e}")

    async def execute_transaction(
        self, queries: List[Tuple[str, List[Any]]]
    ) -> List[Any]:
        """Execute multiple queries in SQLite transaction."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            results = []
            logger.debug(f"Starting transaction with {len(queries)} queries")

            # Use connection from pool
            async with self._get_connection() as db:
                # Start transaction using configured isolation level
                await db.execute(f"BEGIN {self.isolation_level.value}")

                try:
                    for query, params in queries:
                        sqlite_query, sqlite_params = self.format_query(query, params)
                        cursor = await db.execute(sqlite_query, sqlite_params)

                        # Check if it's a SELECT query or similar that returns data
                        if (
                            sqlite_query.strip()
                            .upper()
                            .startswith(("SELECT", "WITH", "PRAGMA"))
                        ):
                            rows = await cursor.fetchall()
                            result = [dict(row) for row in rows]
                        else:
                            # For INSERT, UPDATE, DELETE, etc.
                            result = [
                                {
                                    "rows_affected": cursor.rowcount,
                                    "lastrowid": cursor.lastrowid,
                                }
                            ]

                        results.append(result)
                        await cursor.close()

                    # Commit transaction
                    await db.commit()
                    logger.debug("Transaction completed successfully")
                    return results

                except Exception as e:
                    # Rollback on error
                    await db.rollback()
                    raise e

        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            raise TransactionError(f"Transaction failed: {e}")

    async def get_table_schema(self, table_name: str) -> Dict[str, Dict]:
        """Get SQLite table schema."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Use connection from pool
            async with self._get_connection() as db:
                # Get table info using PRAGMA table_info
                cursor = await db.execute(
                    f"PRAGMA table_info({_safe_identifier(table_name)})"
                )
                columns = await cursor.fetchall()
                await cursor.close()

                if not columns:
                    return {}  # Table doesn't exist

                schema = {}
                for col in columns:
                    col_dict = dict(col)
                    schema[col_dict["name"]] = {
                        "type": col_dict["type"].lower(),
                        "nullable": not bool(col_dict["notnull"]),
                        "primary_key": bool(col_dict["pk"]),
                        "default": col_dict["dflt_value"],
                    }

                return schema

        except Exception as e:
            logger.error(f"Failed to get schema for table {table_name}: {e}")
            return {}

    async def create_table(self, table_name: str, schema: Dict[str, Dict]) -> None:
        """Create SQLite table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Build CREATE TABLE statement
            column_definitions = []
            for col_name, col_info in schema.items():
                col_def = f"{col_name} {col_info['type'].upper()}"

                if col_info.get("primary_key", False):
                    col_def += " PRIMARY KEY"
                    if col_info["type"].lower() == "integer":
                        col_def += " AUTOINCREMENT"

                if not col_info.get("nullable", True):
                    col_def += " NOT NULL"

                if "default" in col_info and col_info["default"] is not None:
                    col_def += f" DEFAULT {col_info['default']}"

                column_definitions.append(col_def)

            create_sql = f"CREATE TABLE IF NOT EXISTS {_safe_identifier(table_name)} ({', '.join(column_definitions)})"

            # Use connection from pool
            async with self._get_connection() as db:
                await db.execute(create_sql)
                await db.commit()

            logger.info(f"Created table: {table_name}")

        except Exception as e:
            raise QueryError(f"Failed to create table {table_name}: {e}")

    async def drop_table(self, table_name: str) -> None:
        """Drop SQLite table."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Use connection from pool
            async with self._get_connection() as db:
                await db.execute(f"DROP TABLE IF EXISTS {_safe_identifier(table_name)}")
                await db.commit()

            logger.info(f"Dropped table: {table_name}")

        except Exception as e:
            raise QueryError(f"Failed to drop table {table_name}: {e}")

    def get_dialect(self) -> str:
        """Get SQLite dialect."""
        return "sqlite"

    def supports_feature(self, feature: str) -> bool:
        """Check SQLite feature support."""
        sqlite_features = {
            "json": True,  # SQLite 3.38+
            "arrays": False,
            "regex": False,  # Requires extension
            "window_functions": True,  # SQLite 3.25+
            "cte": True,
            "upsert": True,  # INSERT ... ON CONFLICT
            "fts": True,  # Full-text search
            "fulltext_search": True,
            "spatial_indexes": False,  # Requires extension
            "hstore": False,  # PostgreSQL-specific
            "mysql_specific": False,
            "sqlite_specific": True,
        }
        return sqlite_features.get(feature, False)

    def format_query(
        self, query: str, params: Optional[List[Any]] = None
    ) -> Tuple[str, List[Any]]:
        """Format query for SQLite parameter style (? - no conversion needed)."""
        if params is None:
            return query, []

        # SQLite uses ? parameters, so no conversion needed
        return query, params

    def get_affinity(self, column_type: str) -> str:
        """Get SQLite type affinity for column type."""
        column_type = column_type.upper()

        # SQLite type affinity rules
        if "INT" in column_type:
            return "integer"
        elif any(text_type in column_type for text_type in ["CHAR", "TEXT", "CLOB"]):
            return "text"
        elif "BLOB" in column_type:
            return "blob"
        elif any(real_type in column_type for real_type in ["REAL", "FLOA", "DOUB"]):
            return "real"
        else:
            return "numeric"

    @property
    def supports_concurrent_reads(self) -> bool:
        """SQLite supports concurrent reads better with WAL mode."""
        return self.wal_mode == SQLiteWALMode.WAL

    @property
    def supports_savepoints(self) -> bool:
        """SQLite supports savepoints."""
        return True

    def transaction(self):
        """Return transaction context manager."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        txn = SQLiteTransaction(self)
        self._active_transactions.add(txn)
        return txn

    async def execute_insert(
        self, query: str, params: Optional[List[Any]] = None
    ) -> Any:
        """Execute INSERT query and return last insert ID."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            sqlite_query, sqlite_params = self.format_query(query, params)

            async with self._get_connection() as db:
                cursor = await db.execute(sqlite_query, sqlite_params)
                await db.commit()

                # Return last insert ID and rows affected
                return {"lastrowid": cursor.lastrowid, "rowcount": cursor.rowcount}

        except Exception as e:
            logger.error(f"SQLite insert failed: {e}")
            raise QueryError(f"Insert failed: {e}")

    async def execute_bulk_insert(self, query: str, params_list: List[Tuple]) -> None:
        """Execute bulk insert operation."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            sqlite_query, _ = self.format_query(query, [])

            async with self._get_connection() as db:
                await db.executemany(sqlite_query, params_list)
                await db.commit()

        except Exception as e:
            logger.error(f"SQLite bulk insert failed: {e}")
            raise QueryError(f"Bulk insert failed: {e}")

    def get_connection_parameters(self) -> Dict[str, Any]:
        """Get SQLite connection parameters."""
        return {
            "database": self.database_path,
            "timeout": self.timeout,
            "isolation_level": self.isolation_level.value,
            "check_same_thread": False,  # Allow multi-threaded access
            "cached_statements": 100,
            "pragmas": self.pragmas,
        }

    def get_tables_query(self) -> str:
        """Get query to list all tables."""
        return """
        SELECT name as table_name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """

    def get_columns_query(self, table_name: str) -> str:
        """Get query to list table columns."""
        return f"PRAGMA table_info({_safe_identifier(table_name)})"

    async def get_server_version(self) -> str:
        """Get SQLite version."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            result = await self.execute_query("SELECT sqlite_version() as version")
            return result[0]["version"]
        except Exception as e:
            logger.error(f"Failed to get SQLite version: {e}")
            return "unknown"

    async def get_database_size(self) -> int:
        """Get database size in bytes."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            if not self.is_memory_database:
                db_size = os.path.getsize(self.database_path)

                # Add WAL file size if it exists
                wal_path = self.database_path + "-wal"
                if os.path.exists(wal_path):
                    db_size += os.path.getsize(wal_path)

                return db_size
            else:
                return 0  # In-memory database

        except Exception as e:
            logger.error(f"Failed to get database size: {e}")
            return 0

    async def _initialize_connection_pool(self) -> None:
        """Initialize SQLite connection pool.

        Note: AsyncSQLitePool is intentionally NOT used here. The DataFlow
        adapter's pool coexists with the Core SDK node execution path
        (AsyncSQLDatabaseNode → ProductionSQLiteAdapter → EnterpriseConnectionPool
        → SQLiteAdapter), which creates its own connections. AsyncSQLitePool's
        persistent dedicated writer conflicts with those connections, causing
        "database is locked" errors. The legacy list-based pool avoids this
        because connections are borrowed/returned per operation without holding
        persistent write locks.
        """
        async with self._pool_lock:
            if self.enable_connection_pooling:
                # Legacy list-based pool (fallback)
                for _ in range(min(5, self.max_connections)):
                    try:
                        conn = await aiosqlite.connect(
                            self.database_path, **self._connect_kwargs
                        )
                        conn.row_factory = aiosqlite.Row

                        # Apply SQLite pragmas for enterprise features
                        for pragma, value in self.pragmas.items():
                            if self.is_memory_database and pragma in (
                                "journal_mode",
                                "wal_autocheckpoint",
                                "mmap_size",
                            ):
                                continue
                            await conn.execute(f"PRAGMA {pragma} = {value}")

                        self._connection_pool.append(conn)
                        self._pool_stats.total_connections += 1
                        self._pool_stats.idle_connections += 1

                    except Exception as e:
                        logger.warning(f"Failed to create connection in pool: {e}")
                        break

                logger.info(
                    f"SQLite connection pool initialized with {len(self._connection_pool)} connections"
                )

            # Test single connection if no pool
            else:
                await self._test_connection()

    async def _test_connection(self) -> None:
        """Test SQLite connection."""
        try:
            async with aiosqlite.connect(
                self.database_path, **self._connect_kwargs
            ) as conn:
                conn.row_factory = aiosqlite.Row

                # Apply pragmas
                for pragma, value in self.pragmas.items():
                    if self.is_memory_database and pragma in (
                        "journal_mode",
                        "wal_autocheckpoint",
                        "mmap_size",
                    ):
                        continue
                    await conn.execute(f"PRAGMA {pragma} = {value}")

                # Test query
                cursor = await conn.execute("SELECT 1 as test")
                result = await cursor.fetchone()
                await cursor.close()

                if result and result[0] == 1:
                    logger.debug("SQLite connection test successful")
                else:
                    raise ConnectionError("SQLite connection test failed")

        except Exception as e:
            raise ConnectionError(f"SQLite connection test failed: {e}")

    async def _close_connection_pool(self) -> None:
        """Close SQLite connection pool."""
        # AsyncSQLitePool handles its own cleanup
        if self._sqlite_pool is not None:
            await self._sqlite_pool.close()
            self._sqlite_pool = None
            logger.info("SQLite connection pool (AsyncSQLitePool) closed")
            return

        # Legacy list-based pool cleanup
        async with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    await conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._connection_pool.clear()
            self._pool_stats.total_connections = 0
            self._pool_stats.idle_connections = 0
            self._pool_stats.active_connections = 0

            logger.info("SQLite connection pool closed")

    async def _perform_wal_checkpoint(self) -> None:
        """Perform WAL checkpoint for SQLite."""
        if not self.enable_wal or self.is_memory_database:
            return

        try:
            async with aiosqlite.connect(
                self.database_path, **self._connect_kwargs
            ) as conn:
                await conn.execute(f"PRAGMA wal_checkpoint({self.wal_checkpoint_mode})")
                logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")

    async def _initialize_performance_monitoring(self) -> None:
        """Initialize SQLite performance monitoring."""
        if not self.enable_performance_monitoring:
            return

        try:
            # Get initial database stats
            async with aiosqlite.connect(
                self.database_path, **self._connect_kwargs
            ) as conn:
                cursor = await conn.execute("PRAGMA page_count")
                page_count_result = await cursor.fetchone()
                await cursor.close()

                cursor = await conn.execute("PRAGMA freelist_count")
                free_pages_result = await cursor.fetchone()
                await cursor.close()

                # Store initial metrics
                self._initial_page_count = (
                    page_count_result[0] if page_count_result else 0
                )
                self._initial_free_pages = (
                    free_pages_result[0] if free_pages_result else 0
                )

                logger.debug(
                    f"Performance monitoring initialized: {self._initial_page_count} pages, {self._initial_free_pages} free"
                )

        except Exception as e:
            logger.warning(f"Failed to initialize performance monitoring: {e}")

    async def _export_performance_metrics(self) -> None:
        """Export SQLite performance metrics."""
        if not self.enable_performance_monitoring:
            return

        try:
            metrics = await self._collect_performance_metrics()
            if metrics:
                logger.info(
                    f"SQLite Performance: {metrics.db_size_mb:.1f}MB, "
                    f"cache hit: {metrics.cache_hit_ratio:.2%}, "
                    f"queries: {self._query_count}"
                )
        except Exception as e:
            logger.warning(f"Failed to export performance metrics: {e}")

    async def _collect_performance_metrics(self) -> Optional[SQLitePerformanceMetrics]:
        """Collect current SQLite performance metrics."""
        try:
            async with aiosqlite.connect(
                self.database_path, **self._connect_kwargs
            ) as conn:
                # Get database size
                if not self.is_memory_database:
                    import os

                    db_size_mb = os.path.getsize(self.database_path) / (1024 * 1024)

                    # Check for WAL file
                    wal_path = self.database_path + "-wal"
                    wal_size_mb = 0
                    if os.path.exists(wal_path):
                        wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
                else:
                    db_size_mb = 0.0
                    wal_size_mb = 0.0

                # Get page info
                cursor = await conn.execute("PRAGMA page_count")
                page_count_result = await cursor.fetchone()
                total_pages = page_count_result[0] if page_count_result else 0
                await cursor.close()

                cursor = await conn.execute("PRAGMA freelist_count")
                free_pages_result = await cursor.fetchone()
                free_pages = free_pages_result[0] if free_pages_result else 0
                await cursor.close()

                # Get cache size
                cursor = await conn.execute("PRAGMA cache_size")
                cache_size_result = await cursor.fetchone()
                cache_size_pages = abs(cache_size_result[0]) if cache_size_result else 0
                await cursor.close()

                # Calculate cache hit ratio (simplified)
                cache_hit_ratio = 0.95 if self._query_count > 10 else 0.0

                return SQLitePerformanceMetrics(
                    db_size_mb=db_size_mb,
                    wal_size_mb=wal_size_mb,
                    cache_hit_ratio=cache_hit_ratio,
                    page_cache_size_mb=(cache_size_pages * 4096) / (1024 * 1024),
                    total_pages=total_pages,
                    free_pages=free_pages,
                    query_plans_analyzed=self._query_count,
                    vacuum_needed=free_pages > (total_pages * 0.25),
                    checkpoint_frequency=1.0,
                )

        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {e}")
            return None


class SQLiteTransaction:
    """SQLite transaction context manager with guaranteed cleanup."""

    # Class-level defaults (safety net if __init__ fails partway)
    _committed = False
    _rolled_back = False
    connection = None
    _source_traceback = None
    _pool_cm: Any = None  # AsyncSQLitePool context manager (when using pool)

    def __init__(self, adapter: "SQLiteAdapter"):
        self.adapter = adapter
        self.connection: Optional[aiosqlite.Connection] = None
        self._committed = False
        self._rolled_back = False
        self._pool_cm: Any = None
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
            f"SQLiteTransaction GC'd without commit/rollback. Created at:{tb}",
            ResourceWarning,
            stacklevel=1,
        )
        # Sync rollback via underlying sqlite3 connection
        try:
            if hasattr(self.connection, "_conn") and self.connection._conn is not None:
                self.connection._conn.rollback()
        except Exception:
            pass

    async def __aenter__(self):
        """Enter transaction context."""
        # Prefer AsyncSQLitePool when available
        if self.adapter._sqlite_pool is not None:
            self._pool_cm = self.adapter._sqlite_pool.acquire_write()
            self.connection = await self._pool_cm.__aenter__()
        else:
            # Legacy list-based pool
            async with self.adapter._pool_lock:
                if self.adapter._connection_pool:
                    self.connection = self.adapter._connection_pool.pop(0)
                    self.adapter._pool_stats.idle_connections -= 1
                    self.adapter._pool_stats.active_connections += 1
                else:
                    # Pool exhausted, create new connection
                    self.connection = await aiosqlite.connect(
                        self.adapter.database_path, **self.adapter._connect_kwargs
                    )
                    self.connection.row_factory = aiosqlite.Row
                    for pragma, value in self.adapter.pragmas.items():
                        if self.adapter.is_memory_database and pragma in (
                            "journal_mode",
                            "wal_autocheckpoint",
                            "mmap_size",
                        ):
                            continue
                        await self.connection.execute(f"PRAGMA {pragma} = {value}")
                    self.adapter._pool_stats.total_connections += 1
                    self.adapter._pool_stats.active_connections += 1

        # Start transaction using configured isolation level
        conn = self.connection
        assert conn is not None, "Connection should be acquired by this point"
        isolation = getattr(self.adapter, "isolation_level", None)
        level = isolation.value if isolation else "DEFERRED"
        await conn.execute(f"BEGIN {level}")
        return self

    async def __aexit__(self, exc_type: Any, _exc_val: Any, _exc_tb: Any) -> bool:
        """Exit transaction context with guaranteed cleanup."""
        conn = self.connection
        if conn is None:
            return False
        try:
            if exc_type is None:
                # No exception, commit transaction if not already done
                if not self._committed and not self._rolled_back:
                    await conn.commit()
                    self._committed = True
            else:
                # Exception occurred, rollback transaction if not already done
                if not self._committed and not self._rolled_back:
                    await conn.rollback()
                    self._rolled_back = True
        except Exception as cleanup_error:
            # Log cleanup error but don't raise (preserve original exception)
            logger.error(
                f"SQLite transaction cleanup failed: {cleanup_error}", exc_info=True
            )
        finally:
            # CRITICAL: Always return connection to pool
            if self._pool_cm is not None:
                # Release back to AsyncSQLitePool
                try:
                    await self._pool_cm.__aexit__(None, None, None)
                except Exception as pool_error:
                    logger.error(
                        f"Failed to release pool connection: {pool_error}",
                        exc_info=True,
                    )
                self._pool_cm = None
            else:
                # Legacy list-based pool
                try:
                    async with self.adapter._pool_lock:
                        self.adapter._connection_pool.append(conn)
                        self.adapter._pool_stats.idle_connections += 1
                        self.adapter._pool_stats.active_connections -= 1
                except Exception as pool_error:
                    logger.error(
                        f"Failed to return connection to pool: {pool_error}",
                        exc_info=True,
                    )

        # Return False to propagate exceptions
        return False

    async def commit(self) -> None:
        """Explicitly commit transaction."""
        if self._committed:
            raise Exception("Transaction already committed")
        if self._rolled_back:
            raise Exception("Transaction already rolled back")
        if self.connection is None:
            raise Exception("No active connection")

        await self.connection.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Explicitly rollback transaction."""
        if self._committed:
            raise Exception("Transaction already committed")
        if self._rolled_back:
            raise Exception("Transaction already rolled back")
        if self.connection is None:
            raise Exception("No active connection")

        await self.connection.rollback()
        self._rolled_back = True
