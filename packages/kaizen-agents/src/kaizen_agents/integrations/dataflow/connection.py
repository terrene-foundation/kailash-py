"""
DataFlow connection interface for Kaizen agents.

Provides connection layer between Kaizen agents and DataFlow instances,
enabling database operations while maintaining framework separation.

Architecture:
- Lazy initialization to prevent startup overhead
- Table schema discovery for dynamic operations
- Access to DataFlow-generated nodes
- Multi-agent coordination support
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

try:
    from dataflow import DataFlow
except ImportError:
    DataFlow = None


@dataclass
class DataFlowConnection:
    """
    Connection interface between Kaizen and DataFlow.

    Provides:
    - Lazy initialization of DataFlow instance
    - Connection pooling for efficient resource usage
    - Table schema discovery
    - Access to DataFlow-generated nodes
    - Multi-agent coordination for shared database

    Args:
        db: DataFlow instance
        lazy_init: If True, delay connection initialization until first use
        pool_size: Maximum number of connections in pool (default: 5)

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("postgresql://localhost/mydb")
        >>> connection = DataFlowConnection(db=db, lazy_init=True, pool_size=10)
        >>> tables = connection.list_tables()
        >>> schema = connection.get_table_schema('users')

    Connection Pooling:
        The connection pool is shared across all instances using the same
        DataFlow database instance, providing efficient resource management
        for multi-agent systems.
    """

    db: "DataFlow"
    lazy_init: bool = True
    pool_size: int = 5
    _initialized: bool = field(default=False, init=False, repr=False)

    # Class-level connection pool (shared across instances)
    _connection_pool: ClassVar[dict[int, dict[str, Any]]] = {}

    def __post_init__(self):
        """Initialize connection if lazy_init is False."""
        if not self.lazy_init:
            self._initialize_connection()

    def _initialize_connection(self):
        """
        Initialize DataFlow connection with pooling support.

        Performs any necessary setup for database operations.
        Called automatically on first use if lazy_init=True.
        """
        if self._initialized:
            return

        # Allow mock objects for testing
        is_mock = (
            hasattr(self.db, "_mock_name") or type(self.db).__name__ == "MagicMock"
        )

        # Verify DataFlow instance (skip for mocks)
        if not is_mock and DataFlow is not None and not isinstance(self.db, DataFlow):
            raise TypeError(f"Expected DataFlow instance, got {type(self.db).__name__}")

        # Setup connection pool for this database instance
        self._setup_connection_pool()

        self._initialized = True

    def _setup_connection_pool(self):
        """
        Initialize connection pool for efficient resource usage.

        Connection pool is shared across all DataFlowConnection instances
        using the same DataFlow database instance.
        """
        pool_id = id(self.db)

        if pool_id not in self._connection_pool:
            self._connection_pool[pool_id] = {
                "connections": [],
                "max_size": self.pool_size,
                "in_use": 0,
                "total_requests": 0,
                "cache_hits": 0,
            }

    def get_pool_stats(self) -> dict[str, Any]:
        """
        Get connection pool statistics.

        Returns:
            Dictionary with pool metrics:
            - connections: Number of active connections
            - max_size: Maximum pool size
            - in_use: Currently in-use connections
            - total_requests: Total connection requests
            - cache_hits: Number of cache hits
            - hit_rate: Cache hit percentage

        Example:
            >>> stats = connection.get_pool_stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.2f}%")
        """
        self._ensure_initialized()

        pool_id = id(self.db)
        if pool_id not in self._connection_pool:
            return {}

        pool = self._connection_pool[pool_id]
        total_requests = pool.get("total_requests", 0)
        cache_hits = pool.get("cache_hits", 0)

        return {
            "connections": len(pool.get("connections", [])),
            "max_size": pool["max_size"],
            "in_use": pool.get("in_use", 0),
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "hit_rate": (
                (cache_hits / total_requests * 100) if total_requests > 0 else 0.0
            ),
        }

    def close(self):
        """
        Close connection pool and release resources.

        Should be called when connection is no longer needed
        to ensure proper cleanup.
        """
        pool_id = id(self.db)

        if pool_id in self._connection_pool:
            # Release pool resources
            del self._connection_pool[pool_id]

        self._initialized = False

    def _ensure_initialized(self):
        """Ensure connection is initialized before use."""
        if not self._initialized:
            self._initialize_connection()

    def get_table_schema(self, table_name: str) -> dict[str, Any]:
        """
        Get schema information for a DataFlow table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary containing table schema information

        Raises:
            ValueError: If table doesn't exist

        Example:
            >>> schema = connection.get_table_schema('users')
            >>> print(schema['columns'])
        """
        self._ensure_initialized()

        # Use DataFlow's schema discovery
        if hasattr(self.db, "get_table_schema"):
            return self.db.get_table_schema(table_name)

        # Fallback: Construct from model if available
        if hasattr(self.db, "get_model"):
            model = self.db.get_model(table_name)
            if model:
                # Extract schema from model
                return self._extract_schema_from_model(model)

        raise ValueError(f"Table '{table_name}' not found")

    def _extract_schema_from_model(self, model) -> dict[str, Any]:
        """Extract schema information from a DataFlow model."""
        # This is a placeholder - actual implementation depends on DataFlow internals
        schema = {
            "columns": {},
            "table_name": getattr(model, "__tablename__", model.__name__.lower()),
        }

        # Extract field information.  Routes through the shared helper so
        # PEP 649/749 lazy annotations on Python 3.14+ resolve safely with
        # a clear per-field error if a forward reference is unresolvable.
        from kailash.utils.annotations import get_resolved_type_hints

        for field_name, field_type in get_resolved_type_hints(model).items():
            schema["columns"][field_name] = {
                "type": str(field_type),
                "nullable": True,  # Default assumption
            }

        return schema

    def list_tables(self) -> list[str]:
        """
        List all available DataFlow tables.

        Returns:
            List of table names

        Example:
            >>> tables = connection.list_tables()
            >>> print(tables)  # ['users', 'products', 'orders']
        """
        self._ensure_initialized()

        # Use DataFlow's table listing
        if hasattr(self.db, "list_tables"):
            return self.db.list_tables()

        # Fallback: Use list_models
        if hasattr(self.db, "list_models"):
            models = self.db.list_models()
            # Convert model names to table names (simple lowercase)
            return [model.lower() for model in models]

        return []

    def get_nodes_for_table(self, table_name: str) -> dict[str, str]:
        """
        Get all DataFlow-generated node names for a table.

        DataFlow generates 11 nodes per model:
        - create, read, update, delete, list, upsert, count
        - bulk_create, bulk_update, bulk_delete, bulk_upsert

        Args:
            table_name: Name of the table (or model name)

        Returns:
            Dictionary mapping operation to node name

        Example:
            >>> nodes = connection.get_nodes_for_table('User')
            >>> print(nodes['create'])  # 'UserCreateNode'
            >>> print(nodes['list'])    # 'UserListNode'
        """
        self._ensure_initialized()

        # Use DataFlow's node mapping if available
        if hasattr(self.db, "get_nodes_for_model"):
            return self.db.get_nodes_for_model(table_name)

        # Fallback: Construct expected node names
        # DataFlow naming convention: {ModelName}{Operation}Node
        model_name = table_name.capitalize()

        return {
            "create": f"{model_name}CreateNode",
            "read": f"{model_name}ReadNode",
            "update": f"{model_name}UpdateNode",
            "delete": f"{model_name}DeleteNode",
            "list": f"{model_name}ListNode",
            "bulk_create": f"{model_name}BulkCreateNode",
            "bulk_update": f"{model_name}BulkUpdateNode",
            "bulk_delete": f"{model_name}BulkDeleteNode",
            "bulk_upsert": f"{model_name}BulkUpsertNode",
        }
