"""Asynchronous connection manager for database connection pooling.

This module provides centralized connection pool management for async database
operations across the Kailash SDK and external repositories. It manages connection
lifecycles, provides health monitoring, and ensures efficient resource utilization.

Design Philosophy:
1. Singleton pattern for global connection management
2. Multi-tenant connection isolation
3. Health monitoring and auto-recovery
4. Configurable pool parameters
5. Graceful shutdown handling
6. Thread-safe operations

Key Features:
- Connection pool management for PostgreSQL, MySQL, SQLite
- Automatic connection validation and recovery
- Pool metrics and monitoring
- Multi-tenant support with isolated pools
- Connection encryption support
- Graceful degradation under load
"""

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, AsyncContextManager, Dict, Optional

from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for a connection pool."""

    created_at: float = field(default_factory=time.time)
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_wait_time: float = 0.0
    last_health_check: float = field(default_factory=time.time)
    is_healthy: bool = True


@dataclass
class PoolConfig:
    """Configuration for a connection pool."""

    min_size: int = 1
    max_size: int = 20
    max_queries: int = 50000
    max_inactive_connection_lifetime: float = 300.0
    connection_timeout: float = 10.0
    command_timeout: float = 60.0
    pool_timeout: float = 30.0
    health_check_interval: float = 60.0
    retry_attempts: int = 3
    retry_delay: float = 1.0


class AsyncConnectionManager:
    """Centralized async connection pool manager.

    This singleton class manages all database connection pools across the SDK,
    providing efficient connection reuse, health monitoring, and multi-tenant
    isolation.

    Features:
        - Singleton pattern ensures single manager instance
        - Per-tenant connection pool isolation
        - Automatic health checks and recovery
        - Connection pool metrics
        - Graceful shutdown

    Example:
        >>> manager = AsyncConnectionManager.get_instance()
        >>> async with manager.get_connection(
        ...     tenant_id="tenant1",
        ...     db_config={"type": "postgresql", "host": "localhost", ...}
        ... ) as conn:
        ...     result = await conn.fetch("SELECT * FROM users")
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize connection manager."""
        if not hasattr(self, "_initialized"):
            self._pools: Dict[str, Dict[str, Any]] = defaultdict(dict)
            self._metrics: Dict[str, Dict[str, PoolMetrics]] = defaultdict(dict)
            self._configs: Dict[str, Dict[str, PoolConfig]] = defaultdict(dict)
            self._health_check_tasks: Dict[str, asyncio.Task] = {}
            self._shutdown = False
            self._initialized = True
            logger.info("AsyncConnectionManager initialized")

    @classmethod
    def get_instance(cls) -> "AsyncConnectionManager":
        """Get singleton instance."""
        return cls()

    def _get_pool_key(self, db_config: dict) -> str:
        """Generate unique key for connection pool."""
        # Create deterministic key from connection parameters
        key_parts = [
            db_config.get("type", "unknown"),
            db_config.get("host", "localhost"),
            str(db_config.get("port", 0)),
            db_config.get("database", "default"),
            db_config.get("user", ""),
        ]
        return "|".join(key_parts)

    async def get_pool(
        self, tenant_id: str, db_config: dict, pool_config: Optional[PoolConfig] = None
    ) -> Any:
        """Get or create connection pool for tenant and database.

        Args:
            tenant_id: Tenant identifier for isolation
            db_config: Database connection configuration
            pool_config: Optional pool configuration overrides

        Returns:
            Database connection pool
        """
        if self._shutdown:
            raise NodeExecutionError("Connection manager is shutting down")

        pool_key = self._get_pool_key(db_config)

        # Check if pool exists
        if pool_key in self._pools[tenant_id]:
            pool = self._pools[tenant_id][pool_key]
            # Validate pool health
            if await self._validate_pool(tenant_id, pool_key, pool):
                self._metrics[tenant_id][pool_key].total_requests += 1
                return pool

        # Create new pool
        pool = await self._create_pool(tenant_id, db_config, pool_config)
        self._pools[tenant_id][pool_key] = pool

        # Initialize metrics
        self._metrics[tenant_id][pool_key] = PoolMetrics()
        self._configs[tenant_id][pool_key] = pool_config or PoolConfig()

        # Start health check task
        task_key = f"{tenant_id}:{pool_key}"
        if task_key in self._health_check_tasks:
            self._health_check_tasks[task_key].cancel()

        self._health_check_tasks[task_key] = asyncio.create_task(
            self._health_check_loop(tenant_id, pool_key)
        )

        return pool

    async def _create_pool(
        self, tenant_id: str, db_config: dict, pool_config: Optional[PoolConfig] = None
    ) -> Any:
        """Create new connection pool."""
        config = pool_config or PoolConfig()
        db_type = db_config.get("type", "").lower()

        try:
            if db_type == "postgresql":
                return await self._create_postgresql_pool(db_config, config)
            elif db_type == "mysql":
                return await self._create_mysql_pool(db_config, config)
            elif db_type == "sqlite":
                return await self._create_sqlite_pool(db_config, config)
            else:
                raise NodeExecutionError(f"Unsupported database type: {db_type}")
        except Exception as e:
            logger.error(f"Failed to create pool for tenant {tenant_id}: {e}")
            raise NodeExecutionError(f"Connection pool creation failed: {str(e)}")

    async def _create_postgresql_pool(
        self, db_config: dict, pool_config: PoolConfig
    ) -> Any:
        """Create PostgreSQL connection pool."""
        try:
            import asyncpg
        except ImportError:
            raise NodeExecutionError("asyncpg not installed")

        dsn = db_config.get("connection_string")
        if not dsn:
            dsn = (
                f"postgresql://{db_config.get('user')}:{db_config.get('password')}@"
                f"{db_config.get('host')}:{db_config.get('port', 5432)}/"
                f"{db_config.get('database')}"
            )

        return await asyncpg.create_pool(
            dsn,
            min_size=pool_config.min_size,
            max_size=pool_config.max_size,
            max_queries=pool_config.max_queries,
            max_inactive_connection_lifetime=pool_config.max_inactive_connection_lifetime,
            timeout=pool_config.pool_timeout,
            command_timeout=pool_config.command_timeout,
        )

    async def _create_mysql_pool(self, db_config: dict, pool_config: PoolConfig) -> Any:
        """Create MySQL connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise NodeExecutionError("aiomysql not installed")

        return await aiomysql.create_pool(
            host=db_config.get("host"),
            port=db_config.get("port", 3306),
            user=db_config.get("user"),
            password=db_config.get("password"),
            db=db_config.get("database"),
            minsize=pool_config.min_size,
            maxsize=pool_config.max_size,
            pool_recycle=int(pool_config.max_inactive_connection_lifetime),
            connect_timeout=int(pool_config.connection_timeout),
        )

    async def _create_sqlite_pool(
        self, db_config: dict, pool_config: PoolConfig
    ) -> Any:
        """Create SQLite connection pool (mock pool for consistency)."""
        try:
            import aiosqlite
        except ImportError:
            raise NodeExecutionError("aiosqlite not installed")

        # SQLite doesn't support true pooling, return config for connection creation
        return {
            "type": "sqlite",
            "database": db_config.get("database"),
            "timeout": pool_config.command_timeout,
        }

    async def _validate_pool(self, tenant_id: str, pool_key: str, pool: Any) -> bool:
        """Validate pool health."""
        metrics = self._metrics[tenant_id][pool_key]

        # Check if pool is marked unhealthy
        if not metrics.is_healthy:
            logger.warning(f"Pool {pool_key} for tenant {tenant_id} is unhealthy")
            return False

        # Quick validation based on pool type
        if hasattr(pool, "_closed"):
            # asyncpg pool
            return not pool._closed
        elif hasattr(pool, "closed"):
            # aiomysql pool
            return not pool.closed
        elif isinstance(pool, dict) and pool.get("type") == "sqlite":
            # SQLite mock pool
            return True

        return True

    @asynccontextmanager
    async def get_connection(
        self, tenant_id: str, db_config: dict, pool_config: Optional[PoolConfig] = None
    ) -> AsyncContextManager[Any]:
        """Get database connection from pool.

        Args:
            tenant_id: Tenant identifier
            db_config: Database configuration
            pool_config: Optional pool configuration

        Yields:
            Database connection
        """
        pool = await self.get_pool(tenant_id, db_config, pool_config)
        pool_key = self._get_pool_key(db_config)
        metrics = self._metrics[tenant_id][pool_key]

        start_time = time.time()

        try:
            if isinstance(pool, dict) and pool.get("type") == "sqlite":
                # SQLite special handling
                import aiosqlite

                async with aiosqlite.connect(pool["database"]) as conn:
                    conn.row_factory = aiosqlite.Row
                    metrics.active_connections += 1
                    yield conn
            else:
                # PostgreSQL/MySQL connection acquisition
                async with pool.acquire() as conn:
                    wait_time = time.time() - start_time
                    metrics.avg_wait_time = (
                        metrics.avg_wait_time * metrics.total_requests + wait_time
                    ) / (metrics.total_requests + 1)
                    metrics.active_connections += 1
                    yield conn
        except Exception as e:
            metrics.failed_requests += 1
            logger.error(f"Connection acquisition failed: {e}")
            raise
        finally:
            metrics.active_connections -= 1

    async def _health_check_loop(self, tenant_id: str, pool_key: str):
        """Background health check for connection pool."""
        config = self._configs[tenant_id][pool_key]

        while not self._shutdown:
            try:
                await asyncio.sleep(config.health_check_interval)

                pool = self._pools[tenant_id].get(pool_key)
                if not pool:
                    break

                metrics = self._metrics[tenant_id][pool_key]
                metrics.last_health_check = time.time()

                # Perform health check based on pool type
                if hasattr(pool, "fetchval"):
                    # PostgreSQL
                    try:
                        async with pool.acquire() as conn:
                            await conn.fetchval("SELECT 1")
                        metrics.is_healthy = True
                    except Exception as e:
                        logger.error(f"PostgreSQL health check failed: {e}")
                        metrics.is_healthy = False
                elif hasattr(pool, "acquire"):
                    # MySQL
                    try:
                        async with pool.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute("SELECT 1")
                        metrics.is_healthy = True
                    except Exception as e:
                        logger.error(f"MySQL health check failed: {e}")
                        metrics.is_healthy = False

                # Update pool metrics
                if hasattr(pool, "_holders"):
                    # asyncpg
                    metrics.total_connections = len(pool._holders)
                    metrics.idle_connections = pool._queue.qsize()
                elif hasattr(pool, "_free_pool"):
                    # aiomysql
                    metrics.total_connections = pool.size
                    metrics.idle_connections = len(pool._free_pool)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error for {pool_key}: {e}")

    async def close_tenant_pools(self, tenant_id: str):
        """Close all pools for a tenant."""
        if tenant_id not in self._pools:
            return

        logger.info(f"Closing all pools for tenant {tenant_id}")

        # Cancel health check tasks
        for pool_key in self._pools[tenant_id]:
            task_key = f"{tenant_id}:{pool_key}"
            if task_key in self._health_check_tasks:
                self._health_check_tasks[task_key].cancel()

        # Close pools
        for pool_key, pool in self._pools[tenant_id].items():
            try:
                if hasattr(pool, "close"):
                    await pool.close()
                    if hasattr(pool, "wait_closed"):
                        await pool.wait_closed()
            except Exception as e:
                logger.error(f"Error closing pool {pool_key}: {e}")

        # Clean up references
        del self._pools[tenant_id]
        del self._metrics[tenant_id]
        del self._configs[tenant_id]

    async def shutdown(self):
        """Shutdown all connection pools."""
        logger.info("Shutting down AsyncConnectionManager")
        self._shutdown = True

        # Cancel all health check tasks
        for task in self._health_check_tasks.values():
            task.cancel()

        # Close all pools
        for tenant_id in list(self._pools.keys()):
            await self.close_tenant_pools(tenant_id)

        self._health_check_tasks.clear()

    def get_metrics(self, tenant_id: Optional[str] = None) -> dict:
        """Get connection pool metrics.

        Args:
            tenant_id: Optional tenant ID to filter metrics

        Returns:
            Dictionary of metrics by tenant and pool
        """
        if tenant_id:
            return {
                pool_key: {
                    "created_at": metrics.created_at,
                    "total_connections": metrics.total_connections,
                    "active_connections": metrics.active_connections,
                    "idle_connections": metrics.idle_connections,
                    "total_requests": metrics.total_requests,
                    "failed_requests": metrics.failed_requests,
                    "avg_wait_time": metrics.avg_wait_time,
                    "last_health_check": metrics.last_health_check,
                    "is_healthy": metrics.is_healthy,
                }
                for pool_key, metrics in self._metrics.get(tenant_id, {}).items()
            }
        else:
            return {
                tenant_id: {
                    pool_key: {
                        "created_at": metrics.created_at,
                        "total_connections": metrics.total_connections,
                        "active_connections": metrics.active_connections,
                        "idle_connections": metrics.idle_connections,
                        "total_requests": metrics.total_requests,
                        "failed_requests": metrics.failed_requests,
                        "avg_wait_time": metrics.avg_wait_time,
                        "last_health_check": metrics.last_health_check,
                        "is_healthy": metrics.is_healthy,
                    }
                    for pool_key, metrics in tenant_metrics.items()
                }
                for tenant_id, tenant_metrics in self._metrics.items()
            }


# Global instance for easy access
_connection_manager = AsyncConnectionManager()


def get_connection_manager() -> AsyncConnectionManager:
    """Get the global connection manager instance."""
    return _connection_manager
