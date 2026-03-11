"""DataFlow Production Engine - DEPRECATED.

.. deprecated:: 0.7.0
   This module has been moved to tests.fixtures.engine_testing_mocks.
   Import from there instead:

   from tests.fixtures.engine_testing_mocks import (
       MockConnectionPool,
       MockConnection,
       MockCursor,
       DataFlowProductionEngine
   )

This module will be removed in v0.8.0.
"""

import asyncio
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import DatabaseConfig, DataFlowConfig, Environment

# Issue deprecation warning when this module is imported
warnings.warn(
    "The module dataflow.core.engine_production is deprecated and has been moved to "
    "tests.fixtures.engine_testing_mocks. Please update your imports. "
    "This module will be removed in v0.8.0.",
    DeprecationWarning,
    stacklevel=2,
)


class MockConnectionPool:
    """Mock connection pool for testing purposes."""

    def __init__(self, database_config: DatabaseConfig):
        self.database_config = database_config
        self.max_connections = database_config.pool_size

    async def get_metrics(self) -> Dict[str, Any]:
        """Get connection pool metrics."""
        return {
            "connections_created": 1,
            "connections_reused": 5,
            "active_connections": 1,
            "total_connections": self.max_connections,
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """Get connection pool health status."""
        return {
            "status": "healthy",
            "total_connections": self.max_connections,
            "active_connections": 1,
        }

    def get_connection(self):
        """Get a mock database connection."""
        return MockConnection()

    async def close(self):
        """Close the connection pool."""
        pass


class MockConnection:
    """Mock database connection for testing."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query: str, params: tuple = ()):
        """Execute a mock query."""
        return MockCursor()

    def commit(self):
        """Mock commit."""
        pass

    def rollback(self):
        """Mock rollback."""
        pass


class MockCursor:
    """Mock database cursor for testing."""

    def fetchone(self):
        """Mock fetchone."""
        return ("Test Laptop", 999.99, "electronics")

    def fetchall(self):
        """Mock fetchall."""
        return [("Test Laptop", 999.99, "electronics")]


class DataFlowProductionEngine:
    """Production-ready DataFlow engine with real database operations."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        database_url: Optional[str] = None,
        **kwargs,
    ):
        """Initialize DataFlow production engine."""
        self.config = config or {}

        # Handle direct database_url parameter
        if database_url:
            self.config["database_url"] = database_url

        # Apply any additional kwargs to config
        self.config.update(kwargs)

        # Initialize database configuration
        self.database_config = DatabaseConfig(
            database_url=self.config.get("database_url", "sqlite:///:memory:"),
            pool_size=self.config.get("pool_size", 10),
            pool_max_overflow=self.config.get("pool_max_overflow", 20),
            pool_timeout=self.config.get("pool_timeout", 30),
            monitoring=self.config.get("monitoring", True),
            cache_enabled=self.config.get("cache_enabled", True),
        )

        # Initialize runtime configuration
        self.dataflow_config = DataFlowConfig(
            environment=Environment.PRODUCTION,
            debug=self.config.get("debug", False),
            auto_commit=self.config.get("auto_commit", True),
            batch_size=self.config.get("batch_size", 1000),
            connection_pool_size=self.config.get("pool_size", 10),
        )

        # Connection pool and management
        self._connection_pool = None
        self._models = {}
        self._nodes = {}

    def model(self, cls=None):
        """Decorator to register a model class."""

        def decorator(model_class):
            # Store model metadata
            self._models[model_class.__name__] = {
                "class": model_class,
                "table_name": getattr(
                    model_class, "__tablename__", model_class.__name__.lower()
                ),
                "fields": self._extract_fields(model_class),
                "config": getattr(model_class, "__dataflow__", {}),
            }

            # Generate nodes for this model
            self._generate_model_nodes(model_class)

            return model_class

        if cls is None:
            return decorator
        else:
            return decorator(cls)

    def _extract_fields(self, model_class):
        """Extract field information from model class."""
        fields = {}

        # Get type annotations if available
        annotations = getattr(model_class, "__annotations__", {})
        for field_name, field_type in annotations.items():
            fields[field_name] = {
                "type": field_type,
                "required": True,  # Default assumption
                "default": getattr(model_class, field_name, None),
            }

        return fields

    def _generate_model_nodes(self, model_class):
        """Generate DataFlow nodes for a model."""
        model_name = model_class.__name__
        table_name = getattr(model_class, "__tablename__", model_name.lower())

        # Create node classes for this model
        node_classes = {
            f"{model_name}CreateNode": self._create_node_class(model_name, "create"),
            f"{model_name}ReadNode": self._create_node_class(model_name, "read"),
            f"{model_name}UpdateNode": self._create_node_class(model_name, "update"),
            f"{model_name}DeleteNode": self._create_node_class(model_name, "delete"),
            f"{model_name}ListNode": self._create_node_class(model_name, "list"),
            f"{model_name}BulkCreateNode": self._create_node_class(
                model_name, "bulk_create"
            ),
            f"{model_name}BulkUpdateNode": self._create_node_class(
                model_name, "bulk_update"
            ),
            f"{model_name}BulkDeleteNode": self._create_node_class(
                model_name, "bulk_delete"
            ),
            f"{model_name}BulkUpsertNode": self._create_node_class(
                model_name, "bulk_upsert"
            ),
        }

        self._nodes.update(node_classes)

    def _create_node_class(self, model_name: str, operation: str):
        """Create a node class for a specific model and operation."""

        class DynamicNode:
            def __init__(self, node_id: str, **kwargs):
                self.node_id = node_id
                self.model_name = model_name
                self.operation = operation
                self.kwargs = kwargs

            async def execute(self, **params):
                """Execute the node operation."""
                return await self._execute_operation(params)

            async def _execute_operation(self, params):
                """Mock implementation of database operation."""
                if operation == "create":
                    return {"success": True, "id": 1, "created": params}
                elif operation == "read":
                    return {
                        "success": True,
                        "data": {"id": params.get("id", 1), "name": "Mock Data"},
                    }
                elif operation == "update":
                    return {"success": True, "updated": params, "rows_affected": 1}
                elif operation == "delete":
                    return {
                        "success": True,
                        "deleted_id": params.get("id", 1),
                        "rows_affected": 1,
                    }
                elif operation == "list":
                    return {
                        "success": True,
                        "data": [{"id": 1, "name": "Mock Item"}],
                        "total": 1,
                    }
                elif operation.startswith("bulk_"):
                    bulk_op = operation.replace("bulk_", "")
                    data = params.get("data", [])
                    return {
                        "success": True,
                        "operation": bulk_op,
                        "rows_affected": len(data) if isinstance(data, list) else 1,
                        "processed": len(data) if isinstance(data, list) else 1,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unknown operation: {operation}",
                    }

        return DynamicNode

    async def execute_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ):
        """Execute a raw SQL query."""
        # Mock implementation for testing
        return {
            "success": True,
            "query": query,
            "parameters": parameters or {},
            "rows_affected": 1,
            "data": [{"mock": "data"}],
        }

    async def test_connection(self) -> bool:
        """Test database connection."""
        try:
            # Mock connection test
            return True
        except Exception:
            return False

    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get information about a database table."""
        return {
            "table_name": table_name,
            "columns": ["id", "name", "created_at"],
            "indexes": ["PRIMARY"],
            "row_count": 0,
        }

    async def create_table(self, table_name: str, schema: Dict[str, Any]) -> bool:
        """Create a database table."""
        # Mock implementation
        return True

    async def drop_table(self, table_name: str) -> bool:
        """Drop a database table."""
        # Mock implementation
        return True

    def get_node_class(self, node_name: str):
        """Get a generated node class by name."""
        return self._nodes.get(node_name)

    def list_models(self) -> List[str]:
        """List all registered models."""
        return list(self._models.keys())

    def list_nodes(self) -> List[str]:
        """List all generated nodes."""
        return list(self._nodes.keys())

    async def close(self):
        """Close database connections and cleanup."""
        # Cleanup connection pool
        if self._connection_pool:
            await self._connection_pool.close()

    def close_sync(self):
        """Synchronous close method for non-async contexts."""
        # For synchronous closing, we'll just reset the connection pool
        self._connection_pool = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def set_tenant_context(self, tenant_id: str):
        """Set the current tenant context for multi-tenant operations."""
        if not self.config.get("multi_tenant", False):
            raise ValueError("Multi-tenant mode is not enabled")

        if not hasattr(self, "_tenant_context"):
            self._tenant_context = {}

        self._tenant_context["current_tenant"] = tenant_id

    def get_tenant_context(self) -> Optional[str]:
        """Get the current tenant context."""
        if not hasattr(self, "_tenant_context") or not self._tenant_context:
            return None
        return self._tenant_context.get("current_tenant")

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on the DataFlow engine."""
        try:
            # Basic health check structure
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "database": {
                        "status": "healthy",
                        "url": "***masked***",  # Don't expose sensitive info
                        "pool_size": self.database_config.pool_size,
                    },
                    "connection_pool": {
                        "status": "healthy",
                        "max_connections": self.database_config.pool_size,
                        "total_connections": self.database_config.pool_size,
                    },
                },
            }

            # Add database URL info (masked)
            if (
                hasattr(self.database_config, "database_url")
                and self.database_config.database_url
            ):
                db_url = self.database_config.database_url
                if "sqlite" in db_url.lower():
                    health_status["components"]["database"]["type"] = "sqlite"
                elif "postgresql" in db_url.lower():
                    health_status["components"]["database"]["type"] = "postgresql"
                elif "mysql" in db_url.lower():
                    health_status["components"]["database"]["type"] = "mysql"

            return health_status

        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "components": {
                    "database": {"status": "unhealthy", "error": str(e)},
                    "connection_pool": {"status": "unknown"},
                },
            }

    def get_connection_pool(self):
        """Get the connection pool instance."""
        if not hasattr(self, "_connection_pool") or self._connection_pool is None:
            # Initialize a mock connection pool for testing
            self._connection_pool = MockConnectionPool(self.database_config)
        return self._connection_pool

    async def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return {
            "connections_created": 0,
            "connections_reused": 0,
            "total_queries": 0,
            "avg_query_time": 0.0,
            "active_connections": 0,
        }

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        # Mock implementation - always return True for testing
        return True

    async def cleanup_test_tables(self):
        """Clean up test tables."""
        # Mock implementation for testing
        pass
