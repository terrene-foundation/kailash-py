"""
DataFlow Connection Management

Database connection pooling and management utilities.
"""

import os
from typing import Any, Dict, Optional

from ..adapters.connection_parser import ConnectionParser


class ConnectionManager:
    """Database connection management for DataFlow.

    Args:
        dataflow_instance: The owning DataFlow instance.
        url_override: When provided, overrides the DataFlow's database URL.
            Used by TSG-105 to create a separate read-replica connection pool.
        pool_size_override: When provided, overrides the configured pool size.
            Used by TSG-105 for independent read-pool sizing.
    """

    def __init__(
        self,
        dataflow_instance,
        url_override: Optional[str] = None,
        pool_size_override: Optional[int] = None,
    ):
        self.dataflow = dataflow_instance
        self._url_override = url_override
        self._pool_size_override = pool_size_override
        self._connection_pool = None

        effective_pool_size = (
            pool_size_override
            if pool_size_override is not None
            else dataflow_instance.config.database.get_pool_size(
                dataflow_instance.config.environment
            )
        )
        self._connection_stats = {
            "active_connections": 0,
            "total_connections": 0,
            "pool_size": effective_pool_size,
        }

    def initialize_pool(self) -> Dict[str, Any]:
        """Initialize the connection pool."""
        config = self.dataflow.config

        # TSG-105: Use url_override when provided (read replica)
        if self._url_override:
            db_url = self._url_override
        else:
            db_url = config.database.get_connection_url(config.environment)

        if not isinstance(db_url, str):
            raise ValueError(
                f"Expected database URL to be a string, got {type(db_url).__name__}: {db_url}"
            )
        parsed_components = ConnectionParser.parse_connection_string(db_url)

        effective_pool_size = (
            self._pool_size_override
            if self._pool_size_override is not None
            else config.database.get_pool_size(config.environment)
        )
        pool_config = {
            "database_url": db_url,
            "pool_size": effective_pool_size,
            "max_overflow": max(2, effective_pool_size // 2),
            "pool_recycle": config.database.pool_recycle or 3600,
            "echo": config.database.echo or False,
        }

        # In real implementation, would create SQLAlchemy engine and pool
        self._connection_pool = pool_config

        return {
            "pool_initialized": True,
            "config": pool_config,
            "success": True,
        }

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        return self._connection_stats.copy()

    def health_check(self) -> Dict[str, Any]:
        """Check database connection health."""
        try:
            # In real implementation, would test actual database connection
            return {
                "database_reachable": True,
                "connection_pool_healthy": True,
                "active_connections": self._connection_stats["active_connections"],
                "pool_size": self._connection_stats["pool_size"],
                "success": True,
            }
        except Exception as e:
            return {
                "database_reachable": False,
                "error": str(e),
                "success": False,
            }

    def parse_database_url(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Parse database URL into components using safe parser."""
        target_url = url or self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        components = ConnectionParser.parse_connection_string(target_url)

        return {
            "scheme": components.get("scheme"),
            "hostname": components.get(
                "host"
            ),  # Note: ConnectionParser uses 'host', not 'hostname'
            "port": components.get("port"),
            "database": components.get("database"),
            "username": components.get("username"),
            "has_password": bool(components.get("password")),
        }

    def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Test database connection."""
        target_url = url or self.dataflow.config.database_url

        try:
            # In real implementation, would test actual connection
            parsed = self.parse_database_url(target_url)

            return {
                "connection_successful": True,
                "database_type": parsed["scheme"],
                "host": parsed["hostname"],
                "port": parsed["port"],
                "success": True,
            }
        except Exception as e:
            return {
                "connection_successful": False,
                "error": str(e),
                "success": False,
            }

    def close_all_connections(self) -> Dict[str, Any]:
        """Close all connections in the pool."""
        active_connections = self._connection_stats["active_connections"]

        # Reset stats
        self._connection_stats["active_connections"] = 0

        return {
            "closed_connections": active_connections,
            "success": True,
        }
