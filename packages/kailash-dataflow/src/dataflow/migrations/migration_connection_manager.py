"""
MigrationConnectionManager - Efficient connection reuse for migration operations.

Provides connection pool management and retry logic for DataFlow migration operations,
optimizing connection usage for better performance while maintaining safety.

Key Features:
- Connection pooling with configurable size and lifecycle
- Retry logic with exponential backoff for reliable operations
- Context manager support for automatic connection cleanup
- Thread-safe connection management
- Support for both SQLite and PostgreSQL connections
- Integration with BatchedMigrationExecutor

Performance Goals:
- Efficient connection reuse across migration operations
- Support for concurrent migration operations
- Proper connection lifecycle management
- Target: <2s overhead for connection management
"""

import asyncio
import logging
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ConnectionError(Exception):
    """Exception raised when connection operations fail."""

    pass


class PoolExhaustedError(ConnectionError):
    """Exception raised when connection pool is exhausted."""

    pass


class OperationTimeoutError(ConnectionError):
    """Exception raised when operation times out."""

    pass


@dataclass
class ConnectionPoolConfig:
    """Configuration for connection pool behavior."""

    pool_size: int = 3  # Conservative size for migrations
    max_lifetime: int = 3600  # 1 hour maximum connection lifetime
    acquire_timeout: int = 30  # 30 seconds to acquire connection
    enable_pooling: bool = True  # Enable connection pooling


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 30.0  # Maximum delay in seconds
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier


@dataclass
class ConnectionPoolStats:
    """Statistics for connection pool usage."""

    active_connections: int = 0
    total_created: int = 0
    total_reused: int = 0
    pool_size: int = 0
    max_pool_size: int = 0


class MigrationConnectionManager:
    """
    Manages database connections for migration operations with pooling and retry logic.

    Provides efficient connection reuse, proper lifecycle management, and retry
    capabilities for reliable migration execution.
    """

    def __init__(
        self, dataflow_instance, pool_config: Optional[ConnectionPoolConfig] = None
    ):
        """
        Initialize MigrationConnectionManager.

        Args:
            dataflow_instance: DataFlow instance for configuration access
            pool_config: Optional custom pool configuration
        """
        self.dataflow = dataflow_instance
        self.config = pool_config or ConnectionPoolConfig()

        # Connection pool and tracking
        self._connection_pool: Dict[str, Dict[str, Any]] = {}
        self._pool_lock = Lock()

        # Statistics tracking
        self.stats = ConnectionPoolStats()
        self.stats.max_pool_size = self.config.pool_size

        logger.info(
            f"MigrationConnectionManager initialized with pool_size={self.config.pool_size}"
        )

    def get_migration_connection(self):
        """
        Get a migration connection from the pool or create a new one.

        Returns:
            Database connection for migration operations
        """
        if not self.config.enable_pooling:
            # When pooling is disabled, always create new connections
            connection = self._create_new_connection()
            self.stats.total_created += 1
            return connection

        with self._pool_lock:
            # Try to reuse an existing connection from pool
            reusable_connection = self._find_reusable_connection()
            if reusable_connection:
                self.stats.total_reused += 1
                return reusable_connection

            # Create new connection if pool not at capacity
            if self.stats.active_connections < self.config.pool_size:
                connection = self._create_new_connection()
                self.stats.active_connections += 1
                self.stats.total_created += 1
                return connection

            # Pool is full - reuse oldest connection (LRU eviction)
            oldest_connection = self._evict_oldest_connection()
            if oldest_connection:
                self.stats.total_reused += 1
                return oldest_connection

            # Fallback - create new connection anyway
            connection = self._create_new_connection()
            self.stats.total_created += 1
            return connection

    def _find_reusable_connection(self):
        """Find a reusable connection from the pool."""
        current_time = time.time()

        for connection_id, pool_entry in list(self._connection_pool.items()):
            connection = pool_entry["connection"]
            created_at = pool_entry["created_at"]

            # Check if connection is still alive
            if not self._is_connection_alive(connection):
                # Remove dead connection
                self._close_connection(connection)
                del self._connection_pool[connection_id]
                self.stats.active_connections -= 1
                continue

            # Check if connection has exceeded max lifetime
            if current_time - created_at > self.config.max_lifetime:
                # Remove expired connection
                self._close_connection(connection)
                del self._connection_pool[connection_id]
                self.stats.active_connections -= 1
                continue

            # Found reusable connection
            pool_entry["last_used"] = current_time
            return connection

        return None

    def _evict_oldest_connection(self):
        """Evict the oldest connection from pool to make space."""
        if not self._connection_pool:
            return None

        # Find oldest connection by last_used time
        oldest_id = min(
            self._connection_pool.keys(),
            key=lambda cid: self._connection_pool[cid]["last_used"],
        )

        pool_entry = self._connection_pool[oldest_id]
        connection = pool_entry["connection"]

        # Update usage time and return
        pool_entry["last_used"] = time.time()
        return connection

    def return_migration_connection(self, connection) -> Optional[str]:
        """
        Return a connection to the pool.

        Args:
            connection: Database connection to return

        Returns:
            Connection ID if added to pool, None otherwise
        """
        if not self.config.enable_pooling:
            # When pooling is disabled, close the connection
            self._close_connection(connection)
            return None

        # Check if connection is still alive
        if not self._is_connection_alive(connection):
            self._close_connection(connection)
            return None

        with self._pool_lock:
            # Add connection to pool
            connection_id = str(uuid.uuid4())
            current_time = time.time()

            self._connection_pool[connection_id] = {
                "connection": connection,
                "created_at": current_time,
                "last_used": current_time,
            }

            return connection_id

    async def execute_with_retry(
        self,
        operation: Callable,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> Any:
        """
        Execute an operation with retry logic and timeout.

        Args:
            operation: Async callable to execute
            max_retries: Maximum number of retries (overrides config)
            timeout: Operation timeout in seconds
            retry_config: Custom retry configuration

        Returns:
            Result of the operation

        Raises:
            OperationTimeoutError: If operation times out
            ConnectionError: If operation fails after all retries
        """
        config = retry_config or RetryConfig()
        retries = max_retries if max_retries is not None else config.max_retries
        delay = config.initial_delay

        for attempt in range(retries + 1):  # +1 for initial attempt
            try:
                if timeout:
                    # Execute with timeout
                    result = await asyncio.wait_for(operation(), timeout=timeout)
                else:
                    # Execute without timeout
                    result = await operation()

                logger.debug(f"Operation succeeded on attempt {attempt + 1}")
                return result

            except asyncio.TimeoutError:
                raise OperationTimeoutError(f"Operation timed out after {timeout}s")

            except Exception as e:
                # Check if this is the last attempt
                if attempt == retries:
                    logger.error(f"Operation failed after {attempt + 1} attempts: {e}")
                    raise e

                # Check if error is retryable
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise e

                # Wait before retry with exponential backoff
                logger.warning(
                    f"Operation failed on attempt {attempt + 1}, retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)

                # Increase delay for next attempt
                delay = min(delay * config.backoff_multiplier, config.max_delay)

        # Should not reach here, but just in case
        raise ConnectionError("Operation failed after all retry attempts")

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        retryable_types = (
            ConnectionError,
            PoolExhaustedError,
            OSError,  # Network errors
            sqlite3.OperationalError,  # SQLite connection issues
        )

        # Add psycopg2 errors if available
        try:
            import psycopg2

            retryable_types += (psycopg2.OperationalError, psycopg2.InterfaceError)
        except ImportError:
            pass

        return isinstance(error, retryable_types)

    def _is_connection_alive(self, connection) -> bool:
        """Check if a connection is still alive."""
        try:
            # SQLite connection check
            if hasattr(connection, "execute") and hasattr(connection, "close"):
                # Try a simple query
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return True

            # PostgreSQL connection check
            if hasattr(connection, "closed"):
                return connection.closed == 0

            # AsyncSQL wrapper check
            if hasattr(connection, "connection_string"):
                return True  # Assume alive for wrappers

            # Default assumption
            return True

        except Exception:
            return False

    def _create_new_connection(self):
        """Create a new database connection."""
        database_url = self.dataflow.config.database.url or ":memory:"

        try:
            if database_url == ":memory:" or database_url.startswith("sqlite"):
                # SQLite connection
                # check_same_thread=False allows use with async_safe_run thread pool
                import sqlite3

                connection = sqlite3.connect(database_url, check_same_thread=False)
                logger.debug("Created new SQLite connection")
                return connection

            elif "postgresql" in database_url or "postgres" in database_url:
                # PostgreSQL connection
                try:
                    import psycopg2

                    from ..adapters.connection_parser import ConnectionParser

                    # Parse connection safely
                    components = ConnectionParser.parse_connection_string(database_url)

                    connection = psycopg2.connect(
                        host=components.get("host", "localhost"),
                        port=components.get("port", 5432),
                        database=components.get("database", "postgres"),
                        user=components.get("username", "postgres"),
                        password=components.get("password", ""),
                    )
                    connection.autocommit = False
                    logger.debug("Created new PostgreSQL connection")
                    return connection

                except ImportError:
                    logger.warning("psycopg2 not available, using AsyncSQL wrapper")
                    return self._create_async_sql_wrapper()

            else:
                # Fallback to AsyncSQL wrapper
                return self._create_async_sql_wrapper()

        except Exception as e:
            logger.error(f"Failed to create database connection: {e}")
            # Ultimate fallback - SQLite memory
            # check_same_thread=False allows use with async_safe_run thread pool
            import sqlite3

            return sqlite3.connect(":memory:", check_same_thread=False)

    def _create_async_sql_wrapper(self):
        """Create AsyncSQL wrapper connection."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            from ..adapters.connection_parser import ConnectionParser

            # Create safe connection string
            components = ConnectionParser.parse_connection_string(
                self.dataflow.config.database.url
            )
            safe_connection_string = ConnectionParser.build_connection_string(
                scheme=components.get("scheme"),
                host=components.get("host"),
                database=components.get("database"),
                username=components.get("username"),
                password=components.get("password"),
                port=components.get("port"),
                **components.get("query_params", {}),
            )

            # Create wrapper that supports the needed interface
            class AsyncSQLConnectionWrapper:
                def __init__(self, connection_string):
                    self.connection_string = connection_string
                    self._transaction = None

                    # Detect database type for AsyncSQLDatabaseNode
                    from ..adapters.connection_parser import ConnectionParser

                    self.database_type = ConnectionParser.detect_database_type(
                        connection_string
                    )

                def cursor(self):
                    return self

                def execute(self, sql, params=None):
                    node = AsyncSQLDatabaseNode(
                        node_id="migration_executor",
                        connection_string=self.connection_string,
                        database_type=self.database_type,
                        query=sql,
                        fetch_mode="all",
                        validate_queries=False,
                    )
                    return node.execute()

                def fetchall(self):
                    return []

                def fetchone(self):
                    return None

                def commit(self):
                    pass

                def rollback(self):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass

                def transaction(self):
                    return self

                def close(self):
                    pass

                def begin(self):
                    self._transaction = self
                    return self._transaction

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    if exc_type is None:
                        self.commit()
                    else:
                        self.rollback()
                    return False

            logger.debug("Created AsyncSQL wrapper connection")
            return AsyncSQLConnectionWrapper(safe_connection_string)

        except Exception as e:
            logger.error(f"Failed to create AsyncSQL wrapper: {e}")
            # Ultimate fallback
            # check_same_thread=False allows use with async_safe_run thread pool
            import sqlite3

            return sqlite3.connect(":memory:", check_same_thread=False)

    def _close_connection(self, connection):
        """Close a database connection safely."""
        try:
            if hasattr(connection, "close"):
                connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")

    def get_pool_stats(self) -> ConnectionPoolStats:
        """Get current connection pool statistics."""
        with self._pool_lock:
            self.stats.pool_size = len(self._connection_pool)
            return ConnectionPoolStats(
                active_connections=self.stats.active_connections,
                total_created=self.stats.total_created,
                total_reused=self.stats.total_reused,
                pool_size=self.stats.pool_size,
                max_pool_size=self.stats.max_pool_size,
            )

    def cleanup_expired_connections(self):
        """Clean up expired connections from the pool."""
        current_time = time.time()
        expired_connections = []

        with self._pool_lock:
            for connection_id, pool_entry in list(self._connection_pool.items()):
                created_at = pool_entry["created_at"]

                if current_time - created_at > self.config.max_lifetime:
                    expired_connections.append(
                        (connection_id, pool_entry["connection"])
                    )
                    del self._connection_pool[connection_id]
                    self.stats.active_connections -= 1

        # Close expired connections outside the lock
        for connection_id, connection in expired_connections:
            self._close_connection(connection)
            logger.debug(f"Cleaned up expired connection {connection_id}")

    def close_all_connections(self):
        """Close all connections in the pool."""
        connections_to_close = []

        with self._pool_lock:
            for pool_entry in self._connection_pool.values():
                connections_to_close.append(pool_entry["connection"])

            self._connection_pool.clear()
            self.stats.active_connections = 0

        # Close connections outside the lock
        for connection in connections_to_close:
            self._close_connection(connection)

        logger.info(f"Closed {len(connections_to_close)} connections")

    @contextmanager
    def get_connection(self):
        """Context manager for automatic connection management."""
        connection = self.get_migration_connection()
        try:
            yield connection
        finally:
            self.return_migration_connection(connection)

    def __enter__(self):
        """Support for using as context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context manager."""
        self.close_all_connections()
        return False
