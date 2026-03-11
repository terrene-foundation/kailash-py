"""
Database Registry for Multi-Database Support

Manages multiple database connections and provides connection pooling
with automatic failover and load balancing.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from ..adapters.connection_parser import ConnectionParser
from ..database.multi_database import DatabaseDialect, detect_dialect

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Configuration for a database connection."""

    name: str
    database_url: str
    database_type: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    is_primary: bool = False
    is_read_replica: bool = False
    weight: int = 1
    enabled: bool = True


class DatabaseRegistry:
    """Registry for managing multiple database connections."""

    def __init__(self):
        self._databases: Dict[str, DatabaseConfig] = {}
        self._primary_db: Optional[str] = None
        self._read_replicas: List[str] = []
        self._connection_pools: Dict[str, any] = {}
        self._health_status: Dict[str, bool] = {}

    def register_database(self, config: DatabaseConfig):
        """Register a database configuration."""
        self._databases[config.name] = config
        self._health_status[config.name] = True

        # Track primary and read replicas
        if config.is_primary:
            self._primary_db = config.name
        elif config.is_read_replica:
            self._read_replicas.append(config.name)

        logger.info(f"Registered database: {config.name} ({config.database_type})")

    def get_database(self, name: str) -> Optional[DatabaseConfig]:
        """Get database configuration by name."""
        return self._databases.get(name)

    def get_database_names(self) -> List[str]:
        """Get all database names."""
        return list(self._databases.keys())

    async def get_connection(self, name: str):
        """Get async database connection by name."""
        import asyncpg

        db_config = self.get_database(name)
        if not db_config:
            raise ValueError(f"Database {name} not found")

        # Check if we already have a connection pool for this database
        if name not in self._connection_pools:
            # Parse the database URL using safe parser
            components = ConnectionParser.parse_connection_string(
                db_config.database_url
            )

            # Create async PostgreSQL connection pool
            pool = await asyncpg.create_pool(
                host=components.get("host"),
                port=components.get("port") or 5432,
                database=components.get("database"),
                user=components.get("username"),
                password=components.get("password"),
                min_size=1,
                max_size=db_config.pool_size,
            )
            self._connection_pools[name] = pool
            logger.info(f"Created async PostgreSQL connection pool for {name}")

        return self._connection_pools[name]

    def get_primary_database(self) -> Optional[DatabaseConfig]:
        """Get the primary database configuration."""
        if self._primary_db:
            return self._databases.get(self._primary_db)
        return None

    def get_read_replicas(self) -> List[DatabaseConfig]:
        """Get all read replica configurations."""
        return [
            self._databases[name]
            for name in self._read_replicas
            if name in self._databases
        ]

    def get_available_databases(self) -> List[DatabaseConfig]:
        """Get all available (healthy) databases."""
        return [
            db
            for name, db in self._databases.items()
            if self._health_status.get(name, False)
        ]

    def get_databases_by_type(self, db_type: str) -> List[DatabaseConfig]:
        """Get databases by type (postgresql, mysql, sqlite)."""
        return [db for db in self._databases.values() if db.database_type == db_type]

    def mark_database_unhealthy(self, name: str):
        """Mark a database as unhealthy."""
        self._health_status[name] = False
        logger.warning(f"Database {name} marked as unhealthy")

    def mark_database_healthy(self, name: str):
        """Mark a database as healthy."""
        self._health_status[name] = True
        logger.info(f"Database {name} marked as healthy")

    def is_database_healthy(self, name: str) -> bool:
        """Check if a database is healthy."""
        return self._health_status.get(name, False)

    def close_all_connections(self):
        """Close all database connections."""
        for name, conn in self._connection_pools.items():
            try:
                if conn and not conn.closed:
                    conn.close()
                    logger.info(f"Closed connection for {name}")
            except Exception as e:
                logger.error(f"Error closing connection for {name}: {e}")
        self._connection_pools.clear()

    def get_database_by_url(self, url: str) -> Optional[DatabaseConfig]:
        """Find database configuration by URL."""
        for db in self._databases.values():
            if db.database_url == url:
                return db
        return None

    def remove_database(self, name: str):
        """Remove a database from the registry."""
        if name in self._databases:
            db = self._databases.pop(name)
            self._health_status.pop(name, None)

            # Update primary and replica lists
            if name == self._primary_db:
                self._primary_db = None
            if name in self._read_replicas:
                self._read_replicas.remove(name)

            logger.info(f"Removed database: {name}")

    def get_connection_info(self) -> Dict[str, any]:
        """Get connection information for all databases."""
        info = {}
        for name, db in self._databases.items():
            info[name] = {
                "type": db.database_type,
                "url": db.database_url,
                "healthy": self._health_status.get(name, False),
                "is_primary": db.is_primary,
                "is_read_replica": db.is_read_replica,
                "pool_size": db.pool_size,
                "enabled": db.enabled,
            }
        return info

    def auto_configure_from_url(self, url: str, name: str = None) -> DatabaseConfig:
        """Auto-configure database from URL."""
        if not name:
            # Generate name from URL
            components = ConnectionParser.parse_connection_string(url)
            name = f"{components.get('scheme')}_{components.get('host')}_{components.get('database')}"

        # Detect database type
        dialect = detect_dialect(url)

        config = DatabaseConfig(
            name=name,
            database_url=url,
            database_type=dialect.value,
            is_primary=True,  # Default to primary
        )

        self.register_database(config)
        return config

    def get_statistics(self) -> Dict[str, any]:
        """Get registry statistics."""
        total_dbs = len(self._databases)
        healthy_dbs = sum(1 for healthy in self._health_status.values() if healthy)

        by_type = {}
        for db in self._databases.values():
            db_type = db.database_type
            by_type[db_type] = by_type.get(db_type, 0) + 1

        return {
            "total_databases": total_dbs,
            "healthy_databases": healthy_dbs,
            "unhealthy_databases": total_dbs - healthy_dbs,
            "primary_database": self._primary_db,
            "read_replicas": len(self._read_replicas),
            "databases_by_type": by_type,
        }

    def health_check(self) -> Dict[str, bool]:
        """Perform health check on all databases."""
        # In a real implementation, this would ping each database
        # For now, return current status
        return self._health_status.copy()

    def failover_to_replica(self) -> Optional[DatabaseConfig]:
        """Failover to a healthy read replica."""
        for replica_name in self._read_replicas:
            if self._health_status.get(replica_name, False):
                return self._databases[replica_name]
        return None

    def get_read_database(self) -> Optional[DatabaseConfig]:
        """Get optimal database for read operations."""
        # Try read replicas first
        healthy_replicas = [
            self._databases[name]
            for name in self._read_replicas
            if self._health_status.get(name, False)
        ]

        if healthy_replicas:
            # Simple round-robin for now
            # In production, this could use weighted selection
            return healthy_replicas[0]

        # Fallback to primary
        return self.get_primary_database()

    def get_write_database(self) -> Optional[DatabaseConfig]:
        """Get database for write operations."""
        primary = self.get_primary_database()
        if primary and self._health_status.get(primary.name, False):
            return primary

        # Fallback to any healthy database
        for name, db in self._databases.items():
            if self._health_status.get(name, False):
                return db

        return None
