"""
Database Query Router for Multi-Database Support

Routes queries to appropriate databases based on operation type,
load balancing, and failover logic.
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Union

from .database_registry import DatabaseConfig, DatabaseRegistry

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of database queries."""

    READ = "read"
    WRITE = "write"
    ANALYTICS = "analytics"
    ADMIN = "admin"


class RoutingStrategy(Enum):
    """Routing strategies for database selection."""

    PRIMARY_ONLY = "primary_only"
    READ_REPLICA = "read_replica"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LEAST_CONNECTIONS = "least_connections"


class DatabaseQueryRouter:
    """Routes queries to appropriate databases based on strategy."""

    def __init__(self, registry: DatabaseRegistry):
        self.registry = registry
        self.default_read_strategy = RoutingStrategy.READ_REPLICA
        self.default_write_strategy = RoutingStrategy.PRIMARY_ONLY
        self._connection_counts: Dict[str, int] = {}
        self._round_robin_index = 0

    def route_query(
        self,
        query_type: QueryType,
        strategy: Optional[RoutingStrategy] = None,
        preferred_database: Optional[str] = None,
        database_type: Optional[str] = None,
    ) -> Optional[DatabaseConfig]:
        """
        Route a query to the appropriate database.

        Args:
            query_type: Type of query (read/write/analytics/admin)
            strategy: Routing strategy to use
            preferred_database: Specific database to prefer
            database_type: Required database type (postgresql, mysql, sqlite)

        Returns:
            Database configuration to use, or None if no suitable database found
        """
        logger.debug(f"Routing {query_type.value} query with strategy {strategy}")

        # If specific database requested, try to use it
        if preferred_database:
            db = self.registry.get_database(preferred_database)
            if db and self.registry.is_database_healthy(preferred_database):
                return db
            logger.warning(f"Preferred database {preferred_database} not available")

        # Filter databases by type if specified
        available_dbs = self.registry.get_available_databases()
        if database_type:
            available_dbs = [
                db for db in available_dbs if db.database_type == database_type
            ]

        if not available_dbs:
            logger.error(f"No available databases found for type: {database_type}")
            return None

        # Choose strategy based on query type
        if not strategy:
            strategy = self._get_default_strategy(query_type)

        return self._select_database(available_dbs, strategy, query_type)

    def _get_default_strategy(self, query_type: QueryType) -> RoutingStrategy:
        """Get default routing strategy for query type."""
        if query_type == QueryType.WRITE:
            return self.default_write_strategy
        elif query_type == QueryType.READ:
            return self.default_read_strategy
        elif query_type == QueryType.ANALYTICS:
            return RoutingStrategy.READ_REPLICA
        else:  # ADMIN
            return RoutingStrategy.PRIMARY_ONLY

    def _select_database(
        self,
        available_dbs: List[DatabaseConfig],
        strategy: RoutingStrategy,
        query_type: QueryType,
    ) -> Optional[DatabaseConfig]:
        """Select database based on routing strategy."""

        if strategy == RoutingStrategy.PRIMARY_ONLY:
            return self._select_primary(available_dbs)

        elif strategy == RoutingStrategy.READ_REPLICA:
            return self._select_read_replica(available_dbs)

        elif strategy == RoutingStrategy.ROUND_ROBIN:
            return self._select_round_robin(available_dbs)

        elif strategy == RoutingStrategy.WEIGHTED:
            return self._select_weighted(available_dbs)

        elif strategy == RoutingStrategy.LEAST_CONNECTIONS:
            return self._select_least_connections(available_dbs)

        else:
            logger.error(f"Unknown routing strategy: {strategy}")
            return available_dbs[0] if available_dbs else None

    def _select_primary(
        self, available_dbs: List[DatabaseConfig]
    ) -> Optional[DatabaseConfig]:
        """Select primary database."""
        for db in available_dbs:
            if db.is_primary:
                return db

        # If no primary found, select first available
        return available_dbs[0] if available_dbs else None

    def _select_read_replica(
        self, available_dbs: List[DatabaseConfig]
    ) -> Optional[DatabaseConfig]:
        """Select read replica, fallback to primary."""
        # Try read replicas first
        replicas = [db for db in available_dbs if db.is_read_replica]
        if replicas:
            return replicas[0]

        # Fallback to primary
        return self._select_primary(available_dbs)

    def _select_round_robin(
        self, available_dbs: List[DatabaseConfig]
    ) -> Optional[DatabaseConfig]:
        """Select database using round-robin strategy."""
        if not available_dbs:
            return None

        # Sort by name for consistent ordering
        sorted_dbs = sorted(available_dbs, key=lambda db: db.name)

        selected = sorted_dbs[self._round_robin_index % len(sorted_dbs)]
        self._round_robin_index += 1

        return selected

    def _select_weighted(
        self, available_dbs: List[DatabaseConfig]
    ) -> Optional[DatabaseConfig]:
        """Select database using weighted strategy."""
        if not available_dbs:
            return None

        # Calculate total weight
        total_weight = sum(db.weight for db in available_dbs)
        if total_weight == 0:
            return available_dbs[0]

        # For now, just select highest weight
        # In production, this would use proper weighted random selection
        return max(available_dbs, key=lambda db: db.weight)

    def _select_least_connections(
        self, available_dbs: List[DatabaseConfig]
    ) -> Optional[DatabaseConfig]:
        """Select database with least connections."""
        if not available_dbs:
            return None

        # Find database with minimum connections
        min_connections = float("inf")
        selected_db = None

        for db in available_dbs:
            connections = self._connection_counts.get(db.name, 0)
            if connections < min_connections:
                min_connections = connections
                selected_db = db

        return selected_db or available_dbs[0]

    def increment_connection_count(self, database_name: str):
        """Increment connection count for a database."""
        self._connection_counts[database_name] = (
            self._connection_counts.get(database_name, 0) + 1
        )

    def decrement_connection_count(self, database_name: str):
        """Decrement connection count for a database."""
        current = self._connection_counts.get(database_name, 0)
        self._connection_counts[database_name] = max(0, current - 1)

    def get_connection_counts(self) -> Dict[str, int]:
        """Get current connection counts."""
        return self._connection_counts.copy()

    def route_read_query(
        self,
        preferred_database: Optional[str] = None,
        database_type: Optional[str] = None,
    ) -> Optional[DatabaseConfig]:
        """Route a read query."""
        return self.route_query(
            QueryType.READ,
            preferred_database=preferred_database,
            database_type=database_type,
        )

    def route_write_query(
        self,
        preferred_database: Optional[str] = None,
        database_type: Optional[str] = None,
    ) -> Optional[DatabaseConfig]:
        """Route a write query."""
        return self.route_query(
            QueryType.WRITE,
            preferred_database=preferred_database,
            database_type=database_type,
        )

    def route_analytics_query(
        self,
        preferred_database: Optional[str] = None,
        database_type: Optional[str] = None,
    ) -> Optional[DatabaseConfig]:
        """Route an analytics query."""
        return self.route_query(
            QueryType.ANALYTICS,
            preferred_database=preferred_database,
            database_type=database_type,
        )

    def set_default_strategies(
        self, read_strategy: RoutingStrategy, write_strategy: RoutingStrategy
    ):
        """Set default routing strategies."""
        self.default_read_strategy = read_strategy
        self.default_write_strategy = write_strategy

    def get_routing_statistics(self) -> Dict[str, any]:
        """Get routing statistics."""
        return {
            "default_read_strategy": self.default_read_strategy.value,
            "default_write_strategy": self.default_write_strategy.value,
            "connection_counts": self._connection_counts,
            "round_robin_index": self._round_robin_index,
        }

    def reset_statistics(self):
        """Reset routing statistics."""
        self._connection_counts.clear()
        self._round_robin_index = 0
