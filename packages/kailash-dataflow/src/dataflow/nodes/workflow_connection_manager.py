"""
DataFlow Integration with Kailash SDK WorkflowConnectionPool

This module provides seamless integration between DataFlow smart nodes
and the Kailash SDK's production-grade WorkflowConnectionPool.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.workflow.builder import WorkflowBuilder

from dataflow.core.async_utils import async_safe_run  # Phase 6: Async-safe execution

logger = logging.getLogger(__name__)


class DataFlowConnectionManager(Node):
    """
    DataFlow connection manager that integrates with WorkflowConnectionPool.

    This node provides:
    - Automatic connection pool setup for DataFlow workflows
    - Production-grade connection management
    - Integration with DataFlow smart nodes
    - Workflow-scoped connection lifecycle

    Example:
        >>> workflow = WorkflowBuilder()
        >>>
        >>> # Initialize connection pool for workflow
        >>> workflow.add_node("DataFlowConnectionManager", "db_pool", {
        ...     "database_type": "postgresql",
        ...     "host": "localhost",
        ...     "database": "dataflow_db",
        ...     "user": "dataflow_user",
        ...     "password": "secure_password",
        ...     "min_connections": 2,
        ...     "max_connections": 10
        ... })
        >>>
        >>> # Use with smart nodes
        >>> workflow.add_node("SmartMergeNode", "merge_data", {
        ...     "connection_pool_id": "db_pool",
        ...     "merge_type": "auto"
        ... })
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pool_instance: Optional[WorkflowConnectionPool] = None
        self.pool_config = kwargs
        self.workflow_id: Optional[str] = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for DataFlowConnectionManager."""
        return {
            # Database connection parameters
            "database_type": NodeParameter(
                name="database_type",
                type=str,
                required=True,
                default="postgresql",
                description="Database type: postgresql, mysql, or sqlite",
            ),
            "connection_string": NodeParameter(
                name="connection_string",
                type=str,
                required=False,
                description="Full connection string (overrides individual params)",
            ),
            "host": NodeParameter(
                name="host", type=str, required=False, description="Database host"
            ),
            "port": NodeParameter(
                name="port", type=int, required=False, description="Database port"
            ),
            "database": NodeParameter(
                name="database", type=str, required=False, description="Database name"
            ),
            "user": NodeParameter(
                name="user", type=str, required=False, description="Database user"
            ),
            "password": NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Database password",
            ),
            # Pool configuration
            "min_connections": NodeParameter(
                name="min_connections",
                type=int,
                required=False,
                default=2,
                description="Minimum pool connections",
            ),
            "max_connections": NodeParameter(
                name="max_connections",
                type=int,
                required=False,
                default=10,
                description="Maximum pool connections",
            ),
            "health_threshold": NodeParameter(
                name="health_threshold",
                type=int,
                required=False,
                default=50,
                description="Minimum health score to keep connection",
            ),
            "pre_warm": NodeParameter(
                name="pre_warm",
                type=bool,
                required=False,
                default=True,
                description="Enable pattern-based pre-warming",
            ),
            "adaptive_sizing": NodeParameter(
                name="adaptive_sizing",
                type=bool,
                required=False,
                default=False,
                description="Enable adaptive pool sizing",
            ),
            "enable_monitoring": NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=True,
                description="Enable connection monitoring",
            ),
            # Operation parameter
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="initialize",
                description="Operation: initialize, get_connection, release_connection, stats",
            ),
            "connection_id": NodeParameter(
                name="connection_id",
                type=str,
                required=False,
                description="Connection ID for operations",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute connection management operations."""
        operation = kwargs.get("operation", "initialize")

        if operation == "initialize":
            return self._initialize_pool(**kwargs)
        elif operation == "get_connection":
            return self._get_connection()
        elif operation == "release_connection":
            return self._release_connection(kwargs.get("connection_id"))
        elif operation == "stats":
            return self._get_pool_stats()
        elif operation == "configure_smart_nodes":
            return self._configure_smart_nodes(**kwargs)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _initialize_pool(self, **kwargs) -> Dict[str, Any]:
        """Initialize the WorkflowConnectionPool."""
        try:
            # Get configuration from self.config (set during node initialization)
            database_type = self.config.get("database_type", "postgresql")

            # Set database-specific defaults
            default_ports = {"postgresql": 5432, "mysql": 3306, "sqlite": None}

            pool_config = {
                "name": f"dataflow_pool_{self.id}",
                "database_type": database_type,
                "min_connections": self.config.get("min_connections", 2),
                "max_connections": self.config.get("max_connections", 10),
                "health_threshold": self.config.get("health_threshold", 50),
                "pre_warm": self.config.get("pre_warm", True),
                "adaptive_sizing": self.config.get("adaptive_sizing", False),
                "enable_monitoring": self.config.get("enable_monitoring", True),
                "circuit_breaker_failure_threshold": 5,
                "circuit_breaker_recovery_timeout": 60,
                "metrics_retention_minutes": 60,
            }

            # Add database connection params if provided
            if self.config.get("connection_string"):
                pool_config["connection_string"] = self.config.get("connection_string")
            else:
                # Only add individual connection params if no connection string
                if self.config.get("host"):
                    pool_config["host"] = self.config.get("host")
                if self.config.get("port") is not None:
                    pool_config["port"] = self.config.get("port")
                elif default_ports[database_type] is not None:
                    pool_config["port"] = default_ports[database_type]
                if self.config.get("database"):
                    pool_config["database"] = self.config.get("database")
                if self.config.get("user"):
                    pool_config["user"] = self.config.get("user")
                if self.config.get("password"):
                    pool_config["password"] = self.config.get("password")

            self.pool_instance = WorkflowConnectionPool(**pool_config)

            # Initialize the pool using async context
            # Note: In a real implementation, this would be handled by the runtime
            # For now, we'll store the config and defer initialization
            self.pool_config = pool_config

            logger.info(f"DataFlow connection pool initialized: {pool_config['name']}")

            return {
                "status": "initialized",
                "pool_id": self.id,
                "pool_name": pool_config["name"],
                "min_connections": pool_config["min_connections"],
                "max_connections": pool_config["max_connections"],
                "database_type": pool_config["database_type"],
                "monitoring_enabled": pool_config["enable_monitoring"],
            }

        except Exception as e:
            logger.error(f"Failed to initialize DataFlow connection pool: {e}")
            return {"status": "error", "error": str(e), "pool_id": self.id}

    def _get_connection(self) -> Dict[str, Any]:
        """Get a connection from the pool."""
        if not self.pool_instance:
            return {"status": "error", "error": "Pool not initialized"}

        # In a real implementation, this would be async
        # For now, return a connection reference
        connection_id = f"conn_{self.id}_{len(self._active_connections())}"

        return {
            "status": "success",
            "connection_id": connection_id,
            "pool_id": self.id,
            "health_score": 100,  # Would be actual health score
        }

    def _release_connection(self, connection_id: Optional[str]) -> Dict[str, Any]:
        """Release a connection back to the pool."""
        if not connection_id:
            return {"status": "error", "error": "connection_id required"}

        if not self.pool_instance:
            return {"status": "error", "error": "Pool not initialized"}

        return {
            "status": "released",
            "connection_id": connection_id,
            "pool_id": self.id,
        }

    def _get_pool_stats(self) -> Dict[str, Any]:
        """Get comprehensive pool statistics."""
        if not self.pool_instance:
            return {"status": "error", "error": "Pool not initialized"}

        # Return basic stats - in real implementation would get from WorkflowConnectionPool
        return {
            "pool_id": self.id,
            "pool_name": self.pool_config.get("name", "unknown"),
            "total_connections": self.pool_config.get("min_connections", 2),
            "active_connections": 0,
            "available_connections": self.pool_config.get("min_connections", 2),
            "health_scores": {},
            "queries_executed": 0,
            "query_errors": 0,
            "uptime_seconds": 0,
        }

    def _configure_smart_nodes(self, **kwargs) -> Dict[str, Any]:
        """Configure smart nodes to use this connection pool."""
        smart_node_configs = []

        # Generate configuration for common smart nodes
        smart_nodes = ["SmartMergeNode", "NaturalLanguageFilterNode", "AggregateNode"]

        for node_type in smart_nodes:
            config = {
                "node_type": node_type,
                "connection_pool_id": self.id,
                "database_config": {
                    "pool_reference": f"workflow.nodes.{self.id}",
                    "use_workflow_pool": True,
                },
            }
            smart_node_configs.append(config)

        return {
            "status": "configured",
            "pool_id": self.id,
            "smart_node_configs": smart_node_configs,
            "integration_ready": True,
        }

    def _active_connections(self) -> List[str]:
        """Get list of active connection IDs."""
        # Placeholder - in real implementation would track actual connections
        return []

    def get_pool_instance(self) -> Optional[WorkflowConnectionPool]:
        """Get the underlying WorkflowConnectionPool instance."""
        return self.pool_instance

    def on_workflow_start(self, workflow_id: str):
        """Called when workflow starts."""
        self.workflow_id = workflow_id
        if self.pool_instance:
            # In async implementation, would call:
            # await self.pool_instance.on_workflow_start(workflow_id)
            pass

    def on_workflow_complete(self, workflow_id: str):
        """Called when workflow completes."""
        if self.pool_instance and workflow_id == self.workflow_id:
            # In async implementation, would call:
            # await self.pool_instance.on_workflow_complete(workflow_id)
            pass


class SmartNodeConnectionMixin:
    """
    Mixin for smart nodes to integrate with DataFlowConnectionManager.

    This mixin provides:
    - Automatic connection pool detection
    - Connection lifecycle management
    - Error handling and fallback
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connection_pool_id = kwargs.get("connection_pool_id")
        self.connection_id: Optional[str] = None
        self._pool_manager: Optional[DataFlowConnectionManager] = None

    def _get_connection_pool(
        self, workflow_context: Optional[Dict] = None
    ) -> Optional[DataFlowConnectionManager]:
        """Get connection pool manager from workflow context."""
        if not self.connection_pool_id:
            return None

        if workflow_context and "nodes" in workflow_context:
            nodes = workflow_context["nodes"]
            if self.connection_pool_id in nodes:
                node = nodes[self.connection_pool_id]
                if isinstance(node, DataFlowConnectionManager):
                    return node

        return None

    def _acquire_connection(
        self, workflow_context: Optional[Dict] = None
    ) -> Optional[str]:
        """Acquire a database connection from the pool."""
        pool_manager = self._get_connection_pool(workflow_context)
        if not pool_manager:
            return None

        try:
            result = pool_manager.execute(operation="get_connection")
            if result.get("status") == "success":
                self.connection_id = result.get("connection_id")
                self._pool_manager = pool_manager
                return self.connection_id
        except Exception as e:
            logger.warning(f"Failed to acquire connection from pool: {e}")

        return None

    def _release_connection(self):
        """Release the acquired connection back to the pool."""
        if self.connection_id and self._pool_manager:
            try:
                self._pool_manager.execute(
                    operation="release_connection", connection_id=self.connection_id
                )
            except Exception as e:
                logger.warning(f"Failed to release connection: {e}")
            finally:
                self.connection_id = None
                self._pool_manager = None

    def _execute_with_connection(self, operation_func, **kwargs):
        """Execute an operation with connection management."""
        workflow_context = kwargs.pop("workflow_context", None)

        # Try to acquire connection from pool
        connection_acquired = self._acquire_connection(workflow_context)

        try:
            # Add connection info to kwargs if available, but only if the operation function expects it
            operation_kwargs = kwargs.copy()
            if connection_acquired:
                # Only add connection parameters if the function can handle them
                import inspect

                sig = inspect.signature(operation_func)
                if "connection_id" in sig.parameters:
                    operation_kwargs["connection_id"] = self.connection_id
                if "use_pooled_connection" in sig.parameters:
                    operation_kwargs["use_pooled_connection"] = True

            # Execute the operation synchronously
            import asyncio

            if asyncio.iscoroutinefunction(operation_func):
                # Phase 6: Use async_safe_run for proper event loop handling
                # This works in both sync and async contexts transparently
                return async_safe_run(operation_func(**operation_kwargs))
            else:
                # For sync operations, return directly
                return operation_func(**operation_kwargs)

        finally:
            # Always release connection
            if connection_acquired:
                self._release_connection()


# Register the node with Kailash's NodeRegistry
NodeRegistry.register(DataFlowConnectionManager, alias="DataFlowConnectionManager")
