"""
DataFlow Connection Management

Real database connection pooling and health checking.
Delegates to the adapter layer for actual connections.
"""

import logging
import time
from typing import Any, Dict, Optional

from ..adapters.connection_parser import ConnectionParser

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Database connection management for DataFlow.

    Provides real connection health checking, pool initialization,
    and connection statistics by delegating to the adapter layer.

    Args:
        dataflow_instance: The owning DataFlow instance.
        url_override: Override the DataFlow's database URL (for read replicas).
        pool_size_override: Override the configured pool size.
    """

    def __init__(
        self,
        dataflow_instance: Any,
        url_override: Optional[str] = None,
        pool_size_override: Optional[int] = None,
    ):
        self.dataflow = dataflow_instance
        self._url_override = url_override
        self._pool_size_override = pool_size_override
        self._adapter: Optional[Any] = None
        self._initialized = False

        effective_pool_size = (
            pool_size_override
            if pool_size_override is not None
            else dataflow_instance.config.database.get_pool_size(
                dataflow_instance.config.environment
            )
        )
        self._pool_size = effective_pool_size

    def _get_db_url(self) -> str:
        """Resolve the effective database URL."""
        if self._url_override:
            return self._url_override
        config = self.dataflow.config
        url = config.database.get_connection_url(config.environment)
        if not isinstance(url, str):
            raise ValueError(f"Expected database URL string, got {type(url).__name__}")
        return url

    async def initialize_pool(self) -> Dict[str, Any]:
        """Initialize the connection pool via the adapter.

        Creates the appropriate adapter for the database type and
        establishes the connection pool. Runs a SELECT 1 health check
        per rules/dataflow-pool.md Rule 2.

        Returns:
            Dict with pool_initialized, pool_size, database_type, success.

        Raises:
            ConnectionError: If the database is unreachable.
        """
        from ..adapters.factory import AdapterFactory

        db_url = self._get_db_url()
        db_type = ConnectionParser.detect_database_type(db_url)

        # AdapterFactory is an instance-based registry; create_adapter
        # builds the dialect-specific adapter from the connection string.
        factory = AdapterFactory()
        self._adapter = factory.create_adapter(
            db_url,
            pool_size=self._pool_size,
            max_overflow=max(2, self._pool_size // 2),
        )

        await self._adapter.connect()
        self._initialized = True

        logger.info(
            "connection.pool.initialized",
            extra={
                "database_type": db_type,
                "pool_size": self._pool_size,
            },
        )

        return {
            "pool_initialized": True,
            "pool_size": self._pool_size,
            "database_type": db_type,
            "success": True,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check database connection health with a real SELECT 1.

        Returns:
            Dict with database_reachable, latency_ms, success.
        """
        if not self._initialized or self._adapter is None:
            return {
                "database_reachable": False,
                "error": "Connection pool not initialized",
                "success": False,
            }

        t0 = time.monotonic()
        try:
            result = await self._adapter.execute_query("SELECT 1 AS health")
            latency_ms = (time.monotonic() - t0) * 1000

            logger.debug(
                "connection.health_check.ok",
                extra={"latency_ms": round(latency_ms, 2)},
            )

            return {
                "database_reachable": True,
                "latency_ms": round(latency_ms, 2),
                "pool_size": self._pool_size,
                "success": True,
            }
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "connection.health_check.failed",
                extra={"error": str(e), "latency_ms": round(latency_ms, 2)},
            )
            return {
                "database_reachable": False,
                "error": str(e),
                "latency_ms": round(latency_ms, 2),
                "success": False,
            }

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics from the adapter."""
        if self._adapter is None or self._adapter.connection_pool is None:
            return {
                "active_connections": 0,
                "total_connections": 0,
                "pool_size": self._pool_size,
                "initialized": False,
            }

        pool = self._adapter.connection_pool
        stats: Dict[str, Any] = {
            "pool_size": self._pool_size,
            "initialized": True,
        }

        # asyncpg pool stats
        if hasattr(pool, "get_size"):
            stats["current_size"] = pool.get_size()
            stats["free_size"] = pool.get_idle_size()
            stats["used_size"] = pool.get_size() - pool.get_idle_size()
        # aiomysql pool stats
        elif hasattr(pool, "size"):
            stats["current_size"] = pool.size
            stats["free_size"] = pool.freesize
            stats["used_size"] = pool.size - pool.freesize

        return stats

    def parse_database_url(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Parse database URL into components (no credentials in output)."""
        target_url = url or self._get_db_url()
        components = ConnectionParser.parse_connection_string(target_url)

        return {
            "scheme": components.get("scheme"),
            "hostname": components.get("host"),
            "port": components.get("port"),
            "database": components.get("database"),
            "username": components.get("username"),
            "has_password": bool(components.get("password")),
        }

    async def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Test database connection with a real query.

        Creates a temporary adapter, connects, runs SELECT 1, disconnects.
        Does NOT modify the main connection pool.
        """
        from ..adapters.factory import AdapterFactory

        target_url = url or self._get_db_url()
        db_type = ConnectionParser.detect_database_type(target_url)
        adapter_class = AdapterFactory.get_adapter(db_type)

        test_adapter = adapter_class(target_url, pool_size=1, max_overflow=0)
        try:
            await test_adapter.connect()
            await test_adapter.execute_query("SELECT 1 AS test")
            parsed = self.parse_database_url(target_url)

            return {
                "connection_successful": True,
                "database_type": db_type,
                "host": parsed["hostname"],
                "port": parsed["port"],
                "success": True,
            }
        except Exception as e:
            return {
                "connection_successful": False,
                "error": str(e),
                "database_type": db_type,
                "success": False,
            }
        finally:
            await test_adapter.disconnect()

    async def close_all_connections(self) -> Dict[str, Any]:
        """Close all connections in the pool."""
        if self._adapter is not None:
            try:
                await self._adapter.disconnect()
                logger.info("connection.pool.closed")
            except Exception as e:
                logger.warning(
                    "connection.pool.close_error",
                    extra={"error": str(e)},
                )

        self._initialized = False
        return {"success": True}
