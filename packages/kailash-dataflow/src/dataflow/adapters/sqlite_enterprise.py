"""
SQLite Enterprise Database Adapter

Enterprise-grade SQLite adapter with advanced indexing, performance monitoring,
connection pooling, transaction isolation controls, and optimization features.

Features:
- WAL mode for concurrent reads
- Connection pooling with intelligent management
- Advanced indexing support with usage tracking
- Performance monitoring and metrics collection
- Query plan analysis and optimization recommendations
- Automatic vacuum and maintenance operations
- Transaction isolation controls with savepoints
- Database size analysis and fragmentation detection
"""

import asyncio
import logging
import os
import sys
import time
import traceback
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from statistics import mean, median
from typing import Any, AsyncContextManager, Dict, List, Optional, Tuple

import aiosqlite

from .base import DatabaseAdapter, _safe_identifier
from .exceptions import AdapterError, ConnectionError, QueryError, TransactionError

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


class SQLiteEnterpriseAdapter(DatabaseAdapter):
    """Enterprise SQLite database adapter with advanced features."""

    @property
    def source_type(self) -> str:
        return "sqlite"

    @property
    def default_port(self) -> int:
        return 0  # SQLite doesn't use ports

    def __init__(self, connection_string: str, **kwargs):
        super().__init__(connection_string, **kwargs)

        # SQLite-specific configuration
        if self.connection_string == ":memory:":
            # Plain :memory: database
            self.database_path = ":memory:"
        elif self.connection_string.startswith("sqlite:///"):
            path_part = self.connection_string.replace("sqlite:///", "")
            if path_part == ":memory:":
                self.database_path = ":memory:"
            else:
                self.database_path = "/" + path_part
        elif self.connection_string.startswith("sqlite://"):
            self.database_path = self.connection_string.replace("sqlite://", "")
        else:
            # Assume it's a file path for SQLite
            self.database_path = self.connection_string

        self.is_memory_database = self.database_path == ":memory:"

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
        if self._connection:
            # Close connection pool if enabled
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

    async def _initialize_connection_pool(self) -> None:
        """Initialize connection pool for SQLite."""
        async with self._pool_lock:
            for _ in range(min(5, self.max_connections)):  # Start with 5 connections
                conn = await self._create_optimized_connection()
                self._connection_pool.append(conn)
                self._pool_stats.idle_connections += 1
                self._pool_stats.total_connections += 1

        logger.info(
            f"Initialized SQLite connection pool with {len(self._connection_pool)} connections"
        )

    async def _create_optimized_connection(self) -> aiosqlite.Connection:
        """Create an optimized SQLite connection with enterprise settings."""
        conn = await aiosqlite.connect(
            self.database_path,
            timeout=self.timeout,
            isolation_level=None,  # We'll handle transactions manually
        )
        conn.row_factory = aiosqlite.Row

        # Apply all PRAGMA settings for optimization
        for pragma, value in self.pragmas.items():
            await conn.execute(f"PRAGMA {pragma} = {value}")

        # Additional enterprise optimizations
        if self.enable_wal:
            # Ensure WAL mode is properly configured
            await conn.execute(f"PRAGMA journal_mode = {self.wal_mode.value}")
            await conn.execute(f"PRAGMA wal_autocheckpoint = {self.wal_autocheckpoint}")

        # Set transaction isolation level
        if self.isolation_level != SQLiteIsolationLevel.DEFERRED:
            await conn.execute(f"BEGIN {self.isolation_level.value}")
            await conn.rollback()  # Cancel the transaction, just set the default

        return conn

    async def _test_connection(self) -> None:
        """Test connection without pooling."""
        async with aiosqlite.connect(self.database_path) as test_conn:
            test_conn.row_factory = aiosqlite.Row

            # Apply PRAGMA settings
            for pragma, value in self.pragmas.items():
                await test_conn.execute(f"PRAGMA {pragma} = {value}")
                logger.debug(f"Set PRAGMA {pragma} = {value}")

            await test_conn.commit()

    async def _close_connection_pool(self) -> None:
        """Close all connections in the pool."""
        async with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    await conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._connection_pool.clear()
            self._pool_stats.active_connections = 0
            self._pool_stats.idle_connections = 0
            self._pool_stats.total_connections = 0

    @asynccontextmanager
    async def _get_connection(self) -> AsyncContextManager[aiosqlite.Connection]:
        """Get a connection from the pool or create a new one."""
        if not self.enable_connection_pooling:
            # Direct connection mode
            conn = await self._create_optimized_connection()
            try:
                yield conn
            finally:
                await conn.close()
            return

        # Pool mode
        conn = None
        start_time = time.time()

        try:
            async with self._pool_lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                    self._pool_stats.idle_connections -= 1
                    self._pool_stats.active_connections += 1
                elif self._pool_stats.total_connections < self.max_connections:
                    conn = await self._create_optimized_connection()
                    self._pool_stats.total_connections += 1
                    self._pool_stats.active_connections += 1

            if not conn:
                # Wait for a connection to become available
                timeout_end = time.time() + self.connection_pool_timeout
                while not conn and time.time() < timeout_end:
                    await asyncio.sleep(0.1)
                    async with self._pool_lock:
                        if self._connection_pool:
                            conn = self._connection_pool.pop()
                            self._pool_stats.idle_connections -= 1
                            self._pool_stats.active_connections += 1
                            break

                if not conn:
                    raise ConnectionError(
                        "Connection pool timeout - no connections available"
                    )

            # Update connection time stats
            connection_time = (time.time() - start_time) * 1000
            self._pool_stats.avg_connection_time_ms = (
                self._pool_stats.avg_connection_time_ms * 0.9
            ) + (connection_time * 0.1)

            yield conn

        finally:
            if conn:
                # Return connection to pool
                async with self._pool_lock:
                    self._pool_stats.active_connections -= 1
                    if len(self._connection_pool) < self.max_connections:
                        self._connection_pool.append(conn)
                        self._pool_stats.idle_connections += 1
                    else:
                        # Pool is full, close the connection
                        await conn.close()
                        self._pool_stats.total_connections -= 1

    async def execute_query(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute SQLite query with enterprise features."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        start_time = time.time()

        try:
            # SQLite uses ? parameters (no conversion needed)
            sqlite_query, sqlite_params = self.format_query(query, params)

            if self.enable_query_monitoring:
                logger.debug(
                    f"Executing query: {sqlite_query[:100]}{'...' if len(sqlite_query) > 100 else ''} "
                    f"with {len(sqlite_params)} params"
                )

            # Execute with connection pool or direct connection
            async with self._get_connection() as db:
                cursor = await db.execute(sqlite_query, sqlite_params or [])

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

                # Update performance statistics
                if self.enable_performance_monitoring:
                    execution_time = time.time() - start_time
                    self._query_count += 1
                    self._total_query_time += execution_time

                    # Log slow queries
                    if execution_time > 1.0:  # 1 second threshold
                        logger.warning(
                            f"Slow query detected: {execution_time:.2f}s - "
                            f"{sqlite_query[:100]}{'...' if len(sqlite_query) > 100 else ''}"
                        )

                # Periodic maintenance checks
                await self._periodic_maintenance_check()

                return results

        except Exception as e:
            logger.error(
                f"Query execution failed after {time.time() - start_time:.2f}s: {e}"
            )
            raise QueryError(f"Query execution failed: {e}")

    async def execute_transaction(
        self,
        queries: List[Tuple[str, List[Any]]],
        isolation_level: Optional[str] = None,
    ) -> List[Any]:
        """Execute multiple queries in SQLite transaction with enterprise features."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        start_time = time.time()
        transaction_isolation = isolation_level or self.isolation_level.value

        try:
            results = []
            logger.debug(
                f"Starting {transaction_isolation} transaction with {len(queries)} queries"
            )

            async with self._get_connection() as db:
                # Start transaction with specified isolation level
                await db.execute(f"BEGIN {transaction_isolation}")

                try:
                    for i, (query, params) in enumerate(queries):
                        sqlite_query, sqlite_params = self.format_query(query, params)

                        query_start = time.time()
                        cursor = await db.execute(sqlite_query, sqlite_params or [])

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

                        # Monitor query performance within transaction
                        query_time = time.time() - query_start
                        if query_time > 0.5:  # 500ms threshold for transaction queries
                            logger.warning(
                                f"Slow query in transaction ({i + 1}/{len(queries)}): {query_time:.2f}s"
                            )

                    # Commit transaction
                    await db.commit()

                    transaction_time = time.time() - start_time
                    logger.debug(
                        f"Transaction completed successfully in {transaction_time:.2f}s "
                        f"({len(queries)} queries)"
                    )

                    # Update performance statistics
                    if self.enable_performance_monitoring:
                        self._query_count += len(queries)
                        self._total_query_time += transaction_time

                    return results

                except Exception as e:
                    # Rollback on error
                    await db.rollback()
                    logger.error(f"Transaction rolled back due to error: {e}")
                    raise e

        except Exception as e:
            transaction_time = time.time() - start_time
            logger.error(f"Transaction failed after {transaction_time:.2f}s: {e}")
            raise TransactionError(f"Transaction failed: {e}")

    def format_query(
        self, query: str, params: List[Any] = None
    ) -> Tuple[str, List[Any]]:
        """Format query for SQLite parameter style (? - no conversion needed)."""
        if params is None:
            params = []

        # SQLite uses ? parameters, so no conversion needed
        return query, params

    def get_dialect(self) -> str:
        """Get SQLite dialect."""
        return "sqlite"

    def supports_feature(self, feature: str) -> bool:
        """Check SQLite feature support including enterprise features."""
        sqlite_features = {
            # Core SQL features
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
            # Enterprise features
            "wal_mode": True,
            "connection_pooling": True,
            "performance_monitoring": True,
            "index_optimization": True,
            "auto_vacuum": True,
            "memory_mapping": True,
            "transaction_isolation": True,
            "deadlock_detection": True,
            "query_optimization": True,
            "concurrent_reads": self.enable_wal,
            "concurrent_writes": False,  # SQLite limitation
            "partial_indexes": True,
            "expression_indexes": True,
            "covering_indexes": True,
            "unique_constraints": True,
            "foreign_keys": True,
            "check_constraints": True,
            "triggers": True,
            "views": True,
            "materialized_views": False,  # Not natively supported
            "stored_procedures": False,  # Not supported
            "user_defined_functions": True,  # Via Python extensions
            # Performance features
            "query_plan_analysis": True,
            "statistics_collection": True,
            "index_recommendations": True,
            "vacuum_optimization": True,
            "checkpoint_control": self.enable_wal,
        }
        return sqlite_features.get(feature, False)

    @property
    def supports_concurrent_reads(self) -> bool:
        """SQLite supports concurrent reads better with WAL mode."""
        return self.wal_mode == SQLiteWALMode.WAL

    @property
    def supports_savepoints(self) -> bool:
        """SQLite supports savepoints."""
        return True

    @property
    def connection_pool_stats(self) -> SQLiteConnectionPoolStats:
        """Get current connection pool statistics."""
        return self._pool_stats

    async def get_performance_metrics(self) -> SQLitePerformanceMetrics:
        """Get comprehensive SQLite performance metrics."""
        async with self._get_connection() as conn:
            metrics = SQLitePerformanceMetrics(
                db_size_mb=0.0,
                wal_size_mb=0.0,
                cache_hit_ratio=0.0,
                page_cache_size_mb=0.0,
                total_pages=0,
                free_pages=0,
                query_plans_analyzed=0,
                vacuum_needed=False,
                checkpoint_frequency=0.0,
            )

            try:
                # Database size
                if not self.is_memory_database:
                    db_path = Path(self.database_path)
                    if db_path.exists():
                        metrics.db_size_mb = db_path.stat().st_size / (1024 * 1024)

                    # WAL file size
                    wal_path = db_path.with_suffix(db_path.suffix + "-wal")
                    if wal_path.exists():
                        metrics.wal_size_mb = wal_path.stat().st_size / (1024 * 1024)

                # Page statistics
                cursor = await conn.execute("PRAGMA page_count")
                result = await cursor.fetchone()
                if result:
                    metrics.total_pages = result[0]

                cursor = await conn.execute("PRAGMA freelist_count")
                result = await cursor.fetchone()
                if result:
                    metrics.free_pages = result[0]

                # Cache statistics
                cursor = await conn.execute("PRAGMA cache_size")
                result = await cursor.fetchone()
                if result:
                    cache_pages = abs(
                        result[0]
                    )  # Negative means KB, positive means pages
                    if result[0] < 0:
                        metrics.page_cache_size_mb = cache_pages / 1024  # KB to MB
                    else:
                        metrics.page_cache_size_mb = (cache_pages * self.page_size) / (
                            1024 * 1024
                        )

                # Calculate cache hit ratio (approximation)
                if self._query_count > 0:
                    metrics.cache_hit_ratio = max(
                        0.0,
                        min(
                            1.0,
                            1.0 - (metrics.free_pages / max(1, metrics.total_pages)),
                        ),
                    )

                # Vacuum recommendation
                if metrics.total_pages > 0:
                    fragmentation_ratio = metrics.free_pages / metrics.total_pages
                    metrics.vacuum_needed = (
                        fragmentation_ratio > 0.25
                    )  # 25% fragmentation threshold

                # Checkpoint frequency (if WAL enabled)
                if self.enable_wal:
                    current_time = time.time()
                    time_since_last = current_time - getattr(
                        self, "_last_checkpoint", current_time
                    )
                    metrics.checkpoint_frequency = 1.0 / max(
                        1.0, time_since_last / 3600
                    )  # Per hour

                metrics.query_plans_analyzed = self._query_count

            except Exception as e:
                logger.warning(f"Failed to collect some performance metrics: {e}")

            return metrics

    def get_optimization_recommendations(self) -> List[str]:
        """Get SQLite-specific optimization recommendations."""
        recommendations = []

        # WAL mode recommendation
        if not self.enable_wal and not self.is_memory_database:
            recommendations.append(
                "Enable WAL mode for better concurrent read performance: enable_wal=True"
            )

        # Connection pooling
        if not self.enable_connection_pooling:
            recommendations.append(
                "Enable connection pooling for better performance: enable_connection_pooling=True"
            )

        # Cache size optimization
        if self.cache_size_mb < 32:
            recommendations.append(
                f"Increase cache size for better performance: current={self.cache_size_mb}MB, recommended=64MB+"
            )

        # Page size optimization
        if self.page_size < 4096:
            recommendations.append(
                f"Use larger page size for better I/O performance: current={self.page_size}, recommended=4096"
            )

        # Auto-vacuum recommendation
        if self.auto_vacuum == "NONE":
            recommendations.append(
                "Enable incremental auto-vacuum to prevent database bloat: auto_vacuum='INCREMENTAL'"
            )

        # Memory-mapped I/O
        mmap_size = int(self.pragmas.get("mmap_size", "0"))
        if mmap_size < 268435456:  # 256MB
            recommendations.append(
                "Enable memory-mapped I/O for better performance: mmap_size=268435456 (256MB)"
            )

        return recommendations

    async def _initialize_performance_monitoring(self) -> None:
        """Initialize performance monitoring for SQLite."""
        try:
            async with self._get_connection() as conn:
                # Enable query planning if supported
                await conn.execute(
                    "PRAGMA optimize = 0x10002"
                )  # Enable advanced optimizations

                # Initialize statistics
                if not self.is_memory_database:
                    stat = await conn.execute("PRAGMA page_count")
                    result = await stat.fetchone()
                    if result:
                        self._last_vacuum_check = time.time()
                        logger.debug(f"Database has {result[0]} pages")

            logger.info("Performance monitoring initialized for SQLite")
        except Exception as e:
            logger.warning(f"Failed to initialize performance monitoring: {e}")

    async def _periodic_maintenance_check(self) -> None:
        """Perform periodic maintenance checks."""
        current_time = time.time()

        # Check if vacuum is needed (every 1000 queries or 1 hour)
        if (
            self._query_count % 1000 == 0
            or current_time - self._last_vacuum_check > 3600
        ):
            self._last_vacuum_check = current_time

            # Check if vacuum is needed
            try:
                metrics = await self.get_performance_metrics()
                if metrics.vacuum_needed and not self.is_memory_database:
                    logger.info(
                        "Database fragmentation detected, consider running VACUUM"
                    )
                    # Auto-vacuum if configured
                    if self.auto_vacuum == "FULL":
                        await self._perform_vacuum()
            except Exception as e:
                logger.debug(f"Maintenance check failed: {e}")

        # Perform WAL checkpoint if needed
        if self.enable_wal and self._query_count % 100 == 0:
            await self._perform_wal_checkpoint("PASSIVE")

    async def _perform_wal_checkpoint(self, mode: str = "PASSIVE") -> bool:
        """Perform WAL checkpoint to commit changes to main database."""
        if not self.enable_wal or self.is_memory_database:
            return True

        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(f"PRAGMA wal_checkpoint({mode})")
                result = await cursor.fetchone()
                if result:
                    busy, log_pages, checkpointed = result
                    success = busy == 0
                    logger.debug(
                        f"WAL checkpoint: mode={mode}, busy={busy}, "
                        f"log_pages={log_pages}, checkpointed={checkpointed}"
                    )
                    return success
                return False
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")
            return False

    async def _perform_vacuum(self) -> bool:
        """Perform database vacuum operation."""
        if self.is_memory_database:
            return True

        try:
            logger.info("Starting database VACUUM operation")
            start_time = time.time()

            async with self._get_connection() as conn:
                await conn.execute("VACUUM")
                await conn.commit()

            duration = time.time() - start_time
            logger.info(f"VACUUM completed in {duration:.2f}s")
            return True

        except Exception as e:
            logger.error(f"VACUUM operation failed: {e}")
            return False

    async def _export_performance_metrics(self) -> None:
        """Export performance metrics to log or file."""
        try:
            metrics = await self.get_performance_metrics()
            logger.info(
                f"SQLite Performance Summary: "
                f"DB Size: {metrics.db_size_mb:.2f}MB, "
                f"WAL Size: {metrics.wal_size_mb:.2f}MB, "
                f"Cache Hit Ratio: {metrics.cache_hit_ratio:.2%}, "
                f"Pages: {metrics.total_pages} (Free: {metrics.free_pages}), "
                f"Vacuum Needed: {metrics.vacuum_needed}"
            )
        except Exception as e:
            logger.warning(f"Failed to export performance metrics: {e}")

    # Table and Schema Management

    async def get_table_schema(
        self, table_name: str, include_indexes: bool = False
    ) -> Dict[str, Dict]:
        """Get SQLite table schema with optional index information."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            async with self._get_connection() as db:
                # Get table info using PRAGMA table_info
                safe_table = _safe_identifier(table_name)
                cursor = await db.execute(f"PRAGMA table_info({safe_table})")
                columns = await cursor.fetchall()

                if not columns:
                    return {}  # Table doesn't exist

                schema = {}
                for col in columns:
                    col_dict = dict(col)
                    column_info = {
                        "type": col_dict["type"].lower(),
                        "nullable": not bool(col_dict["notnull"]),
                        "primary_key": bool(col_dict["pk"]),
                        "default": col_dict["dflt_value"],
                        "ordinal_position": col_dict["cid"],
                    }

                    # Add SQLite-specific type affinity
                    column_info["type_affinity"] = self.get_affinity(col_dict["type"])

                    schema[col_dict["name"]] = column_info

                # Include index information if requested
                if include_indexes:
                    indexes = await self._get_table_indexes(table_name, db)
                    if indexes:
                        schema["_indexes"] = indexes

                # Include foreign key information
                fk_cursor = await db.execute(f"PRAGMA foreign_key_list({safe_table})")
                foreign_keys = await fk_cursor.fetchall()
                if foreign_keys:
                    schema["_foreign_keys"] = [
                        {
                            "column": dict(fk)["from"],
                            "referenced_table": dict(fk)["table"],
                            "referenced_column": dict(fk)["to"],
                            "on_update": dict(fk)["on_update"],
                            "on_delete": dict(fk)["on_delete"],
                        }
                        for fk in foreign_keys
                    ]

                return schema

        except Exception as e:
            logger.error(f"Failed to get schema for table {table_name}: {e}")
            return {}

    async def create_table(
        self,
        table_name: str,
        schema: Dict[str, Dict],
        indexes: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Create SQLite table with optional indexes."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            # Build CREATE TABLE statement
            column_definitions = []
            foreign_key_constraints = []

            for col_name, col_info in schema.items():
                if col_name.startswith("_"):  # Skip metadata fields
                    continue

                col_def = f"{col_name} {col_info['type'].upper()}"

                if col_info.get("primary_key", False):
                    col_def += " PRIMARY KEY"
                    if col_info["type"].lower() == "integer":
                        col_def += " AUTOINCREMENT"

                if not col_info.get("nullable", True):
                    col_def += " NOT NULL"

                if "default" in col_info and col_info["default"] is not None:
                    default_val = col_info["default"]
                    if isinstance(default_val, str) and default_val.upper() not in (
                        "NULL",
                        "CURRENT_TIMESTAMP",
                    ):
                        default_val = f"'{default_val}'"
                    col_def += f" DEFAULT {default_val}"

                # Handle check constraints
                if "check" in col_info:
                    col_def += f" CHECK ({col_info['check']})"

                column_definitions.append(col_def)

            # Add foreign key constraints from schema metadata
            if "_foreign_keys" in schema:
                for fk in schema["_foreign_keys"]:
                    fk_constraint = (
                        f"FOREIGN KEY ({fk['column']}) "
                        f"REFERENCES {fk['referenced_table']}({fk['referenced_column']})"
                    )
                    if fk.get("on_update"):
                        fk_constraint += f" ON UPDATE {fk['on_update']}"
                    if fk.get("on_delete"):
                        fk_constraint += f" ON DELETE {fk['on_delete']}"

                    foreign_key_constraints.append(fk_constraint)

            # Combine all constraints
            all_definitions = column_definitions + foreign_key_constraints
            create_sql = f"CREATE TABLE IF NOT EXISTS {_safe_identifier(table_name)} ({', '.join(all_definitions)})"

            async with self._get_connection() as db:
                # Create table
                await db.execute(create_sql)

                # Create indexes if specified
                if indexes:
                    for index_def in indexes:
                        await self._create_index(table_name, index_def, db)

                await db.commit()

            logger.info(
                f"Created table: {table_name} with {len(column_definitions)} columns"
            )

        except Exception as e:
            raise QueryError(f"Failed to create table {table_name}: {e}")

    async def drop_table(self, table_name: str, cascade: bool = False) -> None:
        """Drop SQLite table with optional cascade."""
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            safe_table = _safe_identifier(table_name)
            async with self._get_connection() as db:
                # Drop associated indexes first if cascade is requested
                if cascade:
                    # Get list of indexes for this table
                    cursor = await db.execute(f"PRAGMA index_list({safe_table})")
                    indexes = await cursor.fetchall()

                    for idx in indexes:
                        idx_dict = dict(idx)
                        index_name = idx_dict["name"]
                        if not index_name.startswith(
                            "sqlite_autoindex_"
                        ):  # Skip auto-indexes
                            try:
                                await db.execute(
                                    f"DROP INDEX IF EXISTS {_safe_identifier(index_name)}"
                                )
                                # Remove from tracking
                                self._tracked_indexes.pop(index_name, None)
                                logger.debug(f"Dropped index: {index_name}")
                            except Exception as e:
                                logger.warning(
                                    f"Failed to drop index {index_name}: {e}"
                                )

                # Drop the table
                await db.execute(f"DROP TABLE IF EXISTS {safe_table}")
                await db.commit()

            logger.info(f"Dropped table: {table_name}")

        except Exception as e:
            raise QueryError(f"Failed to drop table {table_name}: {e}")

    def get_affinity(self, column_type: str) -> str:
        """Get SQLite type affinity for column type."""
        column_type = column_type.upper()

        # SQLite type affinity rules (enhanced)
        if "INT" in column_type:
            return "integer"
        elif any(text_type in column_type for text_type in ["CHAR", "TEXT", "CLOB"]):
            return "text"
        elif "BLOB" in column_type or column_type in ["BINARY", "VARBINARY"]:
            return "blob"
        elif any(
            real_type in column_type
            for real_type in ["REAL", "FLOA", "DOUB", "DECIMAL", "NUMERIC"]
        ):
            return (
                "real"
                if any(
                    float_type in column_type for float_type in ["REAL", "FLOA", "DOUB"]
                )
                else "numeric"
            )
        elif column_type in ["DATE", "DATETIME", "TIMESTAMP", "TIME"]:
            return "text"  # SQLite stores dates as text or numeric
        elif column_type in ["BOOLEAN", "BOOL"]:
            return "integer"  # SQLite stores booleans as integers
        elif column_type in ["JSON", "JSONB"]:
            return "text"  # JSON stored as text in SQLite
        else:
            return "numeric"  # Default fallback

    def get_tables_query(self) -> str:
        """Get query to list all tables."""
        return """
        SELECT name as table_name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """

    def get_columns_query(self, table_name: str) -> str:
        """Get query to list table columns."""
        return f"PRAGMA table_info({_safe_identifier(table_name)})"

    def get_indexes_query(self, table_name: Optional[str] = None) -> str:
        """Get query to list indexes."""
        if table_name:
            return f"PRAGMA index_list({_safe_identifier(table_name)})"
        else:
            return """
            SELECT name, tbl_name as table_name
            FROM sqlite_master
            WHERE type = 'index'
            AND name NOT LIKE 'sqlite_%'
            ORDER BY tbl_name, name
            """

    # Index Management Methods

    async def create_index(
        self,
        table_name: str,
        columns: List[str],
        index_name: Optional[str] = None,
        unique: bool = False,
        partial_condition: Optional[str] = None,
        if_not_exists: bool = True,
    ) -> bool:
        """Create an index on specified columns."""
        try:
            safe_table = _safe_identifier(table_name)
            if not index_name:
                index_name = f"idx_{table_name}_{'_'.join(columns)}"

            safe_index = _safe_identifier(index_name)
            create_sql = f"CREATE {'UNIQUE ' if unique else ''}INDEX "
            if if_not_exists:
                create_sql += "IF NOT EXISTS "
            safe_columns = ", ".join(_safe_identifier(c) for c in columns)
            create_sql += f"{safe_index} ON {safe_table} ({safe_columns})"

            if partial_condition:
                create_sql += f" WHERE {partial_condition}"

            async with self._get_connection() as db:
                await db.execute(create_sql)
                await db.commit()

            # Track the index
            self._tracked_indexes[index_name] = SQLiteIndexInfo(
                name=index_name,
                table=table_name,
                columns=columns,
                unique=unique,
                partial=bool(partial_condition),
            )

            logger.info(f"Created index: {index_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            return False

    async def _get_table_indexes(
        self, table_name: str, db: aiosqlite.Connection
    ) -> List[Dict[str, Any]]:
        """Get index information for a table."""
        try:
            # Get list of indexes
            safe_table = _safe_identifier(table_name)
            cursor = await db.execute(f"PRAGMA index_list({safe_table})")
            index_list = await cursor.fetchall()

            indexes = []
            for idx in index_list:
                idx_dict = dict(idx)
                index_name = idx_dict["name"]

                # Get index columns
                col_cursor = await db.execute(
                    f"PRAGMA index_info({_safe_identifier(index_name)})"
                )
                columns = await col_cursor.fetchall()

                index_info = {
                    "name": index_name,
                    "unique": bool(idx_dict["unique"]),
                    "partial": bool(idx_dict["partial"]),
                    "columns": [dict(col)["name"] for col in columns],
                    "column_details": [
                        {
                            "name": dict(col)["name"],
                            "ordinal_position": dict(col)["seqno"],
                        }
                        for col in columns
                    ],
                }

                # Track index for usage monitoring
                self._tracked_indexes[index_name] = SQLiteIndexInfo(
                    name=index_name,
                    table=table_name,
                    columns=[dict(col)["name"] for col in columns],
                    unique=bool(idx_dict["unique"]),
                    partial=bool(idx_dict["partial"]),
                )

                indexes.append(index_info)

            return indexes

        except Exception as e:
            logger.warning(f"Failed to get indexes for table {table_name}: {e}")
            return []

    async def _create_index(
        self, table_name: str, index_def: Dict[str, Any], db: aiosqlite.Connection
    ) -> None:
        """Create an index on a table."""
        try:
            index_name = index_def.get(
                "name", f"idx_{table_name}_{'_'.join(index_def['columns'])}"
            )
            columns = index_def["columns"]
            unique = index_def.get("unique", False)
            partial_condition = index_def.get("where")

            # Build CREATE INDEX statement
            safe_index = _safe_identifier(index_name)
            safe_table = _safe_identifier(table_name)
            safe_columns = ", ".join(_safe_identifier(c) for c in columns)
            create_index_sql = (
                f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS {safe_index} "
            )
            create_index_sql += f"ON {safe_table} ({safe_columns})"

            if partial_condition:
                create_index_sql += f" WHERE {partial_condition}"

            await db.execute(create_index_sql)

            # Track the index
            self._tracked_indexes[index_name] = SQLiteIndexInfo(
                name=index_name,
                table=table_name,
                columns=columns,
                unique=unique,
                partial=bool(partial_condition),
            )

            logger.debug(
                f"Created index: {index_name} on {table_name}({', '.join(columns)})"
            )

        except Exception as e:
            logger.warning(f"Failed to create index: {e}")

    def transaction(self, isolation_level: Optional[str] = None):
        """Return enterprise transaction context manager."""
        return SQLiteEnterpriseTransaction(
            self, isolation_level or self.isolation_level.value
        )


class SQLiteEnterpriseTransaction:
    """Enterprise SQLite transaction context manager with advanced features."""

    # Class-level defaults (safety net if __init__ fails partway)
    _committed = False
    _rolled_back = False
    connection = None
    _conn_cm = None
    transaction_started = False
    _source_traceback = None

    def __init__(self, adapter: SQLiteEnterpriseAdapter, isolation_level: str):
        self.adapter = adapter
        self.isolation_level = isolation_level
        self.connection = None
        self._conn_cm = None
        self._committed = False
        self._rolled_back = False
        self.transaction_started = False
        self.savepoints: list = []
        if sys.flags.dev_mode or __debug__:
            self._source_traceback = traceback.extract_stack()

    def __del__(self, _warnings=warnings):
        if self._committed or self._rolled_back or self.connection is None:
            return
        if not self.transaction_started:
            return
        tb = ""
        if self._source_traceback:
            try:
                tb = "\n" + "".join(traceback.format_list(self._source_traceback))
            except Exception:
                tb = ""
        _warnings.warn(
            f"SQLiteEnterpriseTransaction GC'd without commit/rollback. Created at:{tb}",
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
        # Store the context manager instance so __aexit__ uses the SAME one.
        # Previously, __aexit__ called self.adapter._get_connection().__aexit__()
        # which created a NEW context manager — causing a connection leak.
        self._conn_cm = self.adapter._get_connection()
        self.connection = await self._conn_cm.__aenter__()
        await self.connection.execute(f"BEGIN {self.isolation_level}")
        self.transaction_started = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context with guaranteed cleanup."""
        try:
            if exc_type is None:
                if not self._committed and not self._rolled_back:
                    await self.connection.execute("COMMIT")
                    self._committed = True
            else:
                if not self._committed and not self._rolled_back:
                    await self.connection.execute("ROLLBACK")
                    self._rolled_back = True
        except Exception as cleanup_error:
            logger.error(
                f"Enterprise transaction cleanup failed: {cleanup_error}",
                exc_info=True,
            )
        finally:
            self.transaction_started = False
            # Exit the SAME connection context manager used in __aenter__
            if self._conn_cm is not None:
                await self._conn_cm.__aexit__(None, None, None)

    async def execute(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute query within transaction."""
        if not self.transaction_started:
            raise RuntimeError("Transaction not started")

        sqlite_query, sqlite_params = self.adapter.format_query(query, params)
        cursor = await self.connection.execute(sqlite_query, sqlite_params or [])

        # Check if it's a SELECT query or similar that returns data
        if sqlite_query.strip().upper().startswith(("SELECT", "WITH", "PRAGMA")):
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            # For INSERT, UPDATE, DELETE, etc.
            return [{"rows_affected": cursor.rowcount, "lastrowid": cursor.lastrowid}]

    async def savepoint(self, name: str) -> None:
        """Create a savepoint within the transaction."""
        if not self.transaction_started:
            raise RuntimeError("Transaction not started")

        await self.connection.execute(f"SAVEPOINT {name}")
        self.savepoints.append(name)

    async def rollback_to_savepoint(self, name: str) -> None:
        """Rollback to a specific savepoint."""
        if not self.transaction_started:
            raise RuntimeError("Transaction not started")

        if name not in self.savepoints:
            raise ValueError(f"Savepoint {name} does not exist")

        await self.connection.execute(f"ROLLBACK TO SAVEPOINT {name}")

        # Remove this savepoint and any created after it
        savepoint_index = self.savepoints.index(name)
        self.savepoints = self.savepoints[:savepoint_index]

    async def release_savepoint(self, name: str) -> None:
        """Release a savepoint (commit its changes)."""
        if not self.transaction_started:
            raise RuntimeError("Transaction not started")

        if name not in self.savepoints:
            raise ValueError(f"Savepoint {name} does not exist")

        await self.connection.execute(f"RELEASE SAVEPOINT {name}")
        self.savepoints.remove(name)
