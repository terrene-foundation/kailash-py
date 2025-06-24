"""Workflow-scoped connection pool for production-grade database management.

This module implements a connection pool that is scoped to workflow lifecycle,
providing better resource management and isolation compared to global pools.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from kailash.core.actors import (
    ActorConnection,
    ActorSupervisor,
    ConnectionActor,
    ConnectionState,
    SupervisionStrategy,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class ConnectionPoolMetrics:
    """Metrics collector for connection pool monitoring."""

    def __init__(self, pool_name: str):
        self.pool_name = pool_name
        self.connections_created = 0
        self.connections_recycled = 0
        self.connections_failed = 0
        self.queries_executed = 0
        self.query_errors = 0
        self.acquisition_wait_times: List[float] = []
        self.health_check_results: List[bool] = []
        self.start_time = time.time()

    def record_acquisition_time(self, wait_time: float):
        """Record time waited to acquire connection."""
        self.acquisition_wait_times.append(wait_time)
        # Keep only last 1000 measurements
        if len(self.acquisition_wait_times) > 1000:
            self.acquisition_wait_times = self.acquisition_wait_times[-1000:]

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive pool statistics."""
        uptime = time.time() - self.start_time

        # Calculate averages
        avg_wait_time = (
            sum(self.acquisition_wait_times) / len(self.acquisition_wait_times)
            if self.acquisition_wait_times
            else 0.0
        )

        health_success_rate = (
            sum(1 for h in self.health_check_results if h)
            / len(self.health_check_results)
            if self.health_check_results
            else 1.0
        )

        return {
            "pool_name": self.pool_name,
            "uptime_seconds": uptime,
            "connections": {
                "created": self.connections_created,
                "recycled": self.connections_recycled,
                "failed": self.connections_failed,
            },
            "queries": {
                "executed": self.queries_executed,
                "errors": self.query_errors,
                "error_rate": (
                    self.query_errors / self.queries_executed
                    if self.queries_executed > 0
                    else 0
                ),
            },
            "performance": {
                "avg_acquisition_time_ms": avg_wait_time * 1000,
                "p99_acquisition_time_ms": (
                    sorted(self.acquisition_wait_times)[
                        int(len(self.acquisition_wait_times) * 0.99)
                    ]
                    * 1000
                    if self.acquisition_wait_times
                    else 0
                ),
            },
            "health": {
                "success_rate": health_success_rate,
                "checks_performed": len(self.health_check_results),
            },
        }


class WorkflowPatternAnalyzer:
    """Analyzes workflow patterns for optimization."""

    def __init__(self):
        self.workflow_patterns: Dict[str, Dict[str, Any]] = {}
        self.connection_usage: Dict[str, List[float]] = defaultdict(list)

    def record_workflow_start(self, workflow_id: str, workflow_type: str):
        """Record workflow start for pattern analysis."""
        self.workflow_patterns[workflow_id] = {
            "type": workflow_type,
            "start_time": time.time(),
            "connections_used": 0,
            "peak_connections": 0,
        }

    def record_connection_usage(self, workflow_id: str, active_connections: int):
        """Record connection usage for workflow."""
        if workflow_id in self.workflow_patterns:
            pattern = self.workflow_patterns[workflow_id]
            pattern["connections_used"] = max(
                pattern["connections_used"], active_connections
            )
            self.connection_usage[workflow_id].append(active_connections)

    def get_expected_connections(self, workflow_type: str) -> int:
        """Get expected connection count for workflow type."""
        # Analyze historical data for this workflow type
        similar_workflows = [
            p
            for p in self.workflow_patterns.values()
            if p["type"] == workflow_type and "connections_used" in p
        ]

        if not similar_workflows:
            return 2  # Default

        # Return 90th percentile of historical usage
        usage_values = sorted([w["connections_used"] for w in similar_workflows])
        percentile_index = int(len(usage_values) * 0.9)
        return usage_values[percentile_index] if usage_values else 2


@register_node()
class WorkflowConnectionPool(AsyncNode):
    """
    Workflow-scoped connection pool with production-grade features.

    This node provides:
    - Connections scoped to workflow lifecycle
    - Actor-based isolation for each connection
    - Automatic health monitoring and recycling
    - Pattern-based pre-warming
    - Comprehensive metrics and monitoring

    Example:
        >>> pool = WorkflowConnectionPool(
        ...     name="workflow_db_pool",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass",
        ...     min_connections=2,
        ...     max_connections=10
        ... )
        >>>
        >>> # Get connection
        >>> result = await pool.process({"operation": "acquire"})
        >>> conn_id = result["connection_id"]
        >>>
        >>> # Execute query
        >>> query_result = await pool.process({
        ...     "operation": "execute",
        ...     "connection_id": conn_id,
        ...     "query": "SELECT * FROM users WHERE active = true",
        ... })
    """

    def __init__(self, **config):
        super().__init__(**config)

        # Pool configuration
        self.min_connections = config.get("min_connections", 2)
        self.max_connections = config.get("max_connections", 10)
        self.health_threshold = config.get("health_threshold", 50)
        self.pre_warm_enabled = config.get("pre_warm", True)

        # Database configuration
        self.db_config = {
            "type": config.get("database_type", "postgresql"),
            "host": config.get("host"),
            "port": config.get("port"),
            "database": config.get("database"),
            "user": config.get("user"),
            "password": config.get("password"),
            "connection_string": config.get("connection_string"),
        }

        # Actor supervision
        self.supervisor = ActorSupervisor(
            name=f"{self.metadata.name}_supervisor",
            strategy=SupervisionStrategy.ONE_FOR_ONE,
            max_restarts=3,
            restart_window=60.0,
        )

        # Connection tracking
        self.available_connections: asyncio.Queue = asyncio.Queue()
        self.active_connections: Dict[str, ConnectionActor] = {}
        self.all_connections: Dict[str, ConnectionActor] = {}

        # Workflow integration
        self.workflow_id: Optional[str] = None
        self.pattern_analyzer = WorkflowPatternAnalyzer()

        # Metrics
        self.metrics = ConnectionPoolMetrics(self.metadata.name)

        # State
        self._initialized = False
        self._closing = False

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters."""
        params = [
            # Database connection parameters
            NodeParameter(
                name="database_type",
                type=str,
                required=True,
                default="postgresql",
                description="Database type: postgresql, mysql, or sqlite",
            ),
            NodeParameter(
                name="connection_string",
                type=str,
                required=False,
                description="Full connection string (overrides individual params)",
            ),
            NodeParameter(
                name="host", type=str, required=False, description="Database host"
            ),
            NodeParameter(
                name="port", type=int, required=False, description="Database port"
            ),
            NodeParameter(
                name="database", type=str, required=False, description="Database name"
            ),
            NodeParameter(
                name="user", type=str, required=False, description="Database user"
            ),
            NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Database password",
            ),
            # Pool configuration
            NodeParameter(
                name="min_connections",
                type=int,
                required=False,
                default=2,
                description="Minimum pool connections",
            ),
            NodeParameter(
                name="max_connections",
                type=int,
                required=False,
                default=10,
                description="Maximum pool connections",
            ),
            NodeParameter(
                name="health_threshold",
                type=int,
                required=False,
                default=50,
                description="Minimum health score to keep connection",
            ),
            NodeParameter(
                name="pre_warm",
                type=bool,
                required=False,
                default=True,
                description="Enable pattern-based pre-warming",
            ),
            # Operation parameters
            NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: initialize, acquire, release, execute, stats",
            ),
            NodeParameter(
                name="connection_id",
                type=str,
                required=False,
                description="Connection ID for operations",
            ),
            NodeParameter(
                name="query",
                type=str,
                required=False,
                description="SQL query to execute",
            ),
            NodeParameter(
                name="params", type=Any, required=False, description="Query parameters"
            ),
            NodeParameter(
                name="fetch_mode",
                type=str,
                required=False,
                default="all",
                description="Fetch mode: one, all, many",
            ),
        ]

        # Convert list to dict as required by base class
        return {param.name: param for param in params}

    async def on_workflow_start(
        self, workflow_id: str, workflow_type: Optional[str] = None
    ):
        """Called when workflow starts - pre-warm connections."""
        self.workflow_id = workflow_id
        self.pattern_analyzer.record_workflow_start(
            workflow_id, workflow_type or "unknown"
        )

        if self.pre_warm_enabled and workflow_type:
            expected_connections = self.pattern_analyzer.get_expected_connections(
                workflow_type
            )
            await self._pre_warm_connections(expected_connections)

    async def on_workflow_complete(self, workflow_id: str):
        """Called when workflow completes - clean up resources."""
        if workflow_id == self.workflow_id:
            await self._cleanup()

    async def async_run(self, **inputs) -> Dict[str, Any]:
        """Process connection pool operations."""
        operation = inputs.get("operation")

        if operation == "initialize":
            return await self._initialize()
        elif operation == "acquire":
            return await self._acquire_connection()
        elif operation == "release":
            return await self._release_connection(inputs.get("connection_id"))
        elif operation == "execute":
            return await self._execute_query(inputs)
        elif operation == "stats":
            return await self._get_stats()
        else:
            raise NodeExecutionError(f"Unknown operation: {operation}")

    async def _initialize(self) -> Dict[str, Any]:
        """Initialize the connection pool."""
        if self._initialized:
            return {"status": "already_initialized"}

        try:
            # Start supervisor
            await self.supervisor.start()

            # Set up callbacks
            self.supervisor.on_actor_failure = self._on_connection_failure
            self.supervisor.on_actor_restart = self._on_connection_restart

            # Create minimum connections
            await self._ensure_min_connections()

            self._initialized = True

            return {
                "status": "initialized",
                "min_connections": self.min_connections,
                "max_connections": self.max_connections,
            }

        except Exception as e:
            logger.error(f"Failed to initialize pool: {e}")
            raise NodeExecutionError(f"Pool initialization failed: {e}")

    async def _acquire_connection(self) -> Dict[str, Any]:
        """Acquire a connection from the pool."""
        if not self._initialized:
            await self._initialize()

        start_time = time.time()

        try:
            # Try to get available connection
            connection = None

            # Fast path: try to get immediately available connection
            try:
                connection = await asyncio.wait_for(
                    self.available_connections.get(), timeout=0.1
                )
            except asyncio.TimeoutError:
                # Need to create new connection or wait
                if len(self.all_connections) < self.max_connections:
                    # Create new connection
                    connection = await self._create_connection()
                    # Don't put it in available queue - we'll use it directly
                else:
                    # Wait for available connection
                    connection = await self.available_connections.get()

            # Record acquisition time
            wait_time = time.time() - start_time
            self.metrics.record_acquisition_time(wait_time)

            # Move to active
            self.active_connections[connection.id] = connection

            # Update pattern analyzer
            if self.workflow_id:
                self.pattern_analyzer.record_connection_usage(
                    self.workflow_id, len(self.active_connections)
                )

            return {
                "connection_id": connection.id,
                "health_score": connection.health_score,
                "acquisition_time_ms": wait_time * 1000,
            }

        except Exception as e:
            logger.error(f"Failed to acquire connection: {e}")
            raise NodeExecutionError(f"Connection acquisition failed: {e}")

    async def _release_connection(self, connection_id: Optional[str]) -> Dict[str, Any]:
        """Release a connection back to the pool."""
        if not connection_id:
            raise NodeExecutionError("connection_id required for release")

        if connection_id not in self.active_connections:
            raise NodeExecutionError(f"Connection {connection_id} not active")

        connection = self.active_connections.pop(connection_id)

        # Check if connection should be recycled
        if connection.health_score < self.health_threshold:
            await self._recycle_connection(connection)
            return {"status": "recycled", "connection_id": connection_id}
        else:
            # Return to available pool
            await self.available_connections.put(connection)
            return {"status": "released", "connection_id": connection_id}

    async def _execute_query(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a query on a specific connection."""
        connection_id = inputs.get("connection_id")
        if not connection_id or connection_id not in self.active_connections:
            raise NodeExecutionError(f"Invalid connection_id: {connection_id}")

        connection = self.active_connections[connection_id]

        try:
            # Execute query
            result = await connection.execute(
                query=inputs.get("query"),
                params=inputs.get("params"),
                fetch_mode=inputs.get("fetch_mode", "all"),
            )

            # Update metrics
            self.metrics.queries_executed += 1
            if not result.success:
                self.metrics.query_errors += 1

            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "execution_time_ms": result.execution_time * 1000,
                "connection_id": connection_id,
            }

        except Exception as e:
            self.metrics.query_errors += 1
            logger.error(f"Query execution failed: {e}")
            raise NodeExecutionError(f"Query execution failed: {e}")

    async def _get_stats(self) -> Dict[str, Any]:
        """Get comprehensive pool statistics."""
        pool_stats = self.metrics.get_stats()
        supervisor_stats = self.supervisor.get_stats()

        # Add current pool state
        pool_stats["current_state"] = {
            "total_connections": len(self.all_connections),
            "active_connections": len(self.active_connections),
            "available_connections": self.available_connections.qsize(),
            "health_scores": {
                conn_id: conn.health_score
                for conn_id, conn in self.all_connections.items()
            },
        }

        pool_stats["supervisor"] = supervisor_stats

        return pool_stats

    async def _create_connection(self) -> ConnectionActor:
        """Create a new connection actor."""
        conn_id = f"conn_{uuid.uuid4().hex[:8]}"

        # Create actor connection
        actor_conn = ActorConnection(
            connection_id=conn_id,
            db_config=self.db_config,
            health_check_interval=30.0,
            max_lifetime=3600.0,
            max_idle_time=600.0,
        )

        # Add to supervisor
        self.supervisor.add_actor(actor_conn)

        # Create high-level interface
        connection = ConnectionActor(actor_conn)

        # Track connection
        self.all_connections[conn_id] = connection
        self.metrics.connections_created += 1

        logger.info(f"Created connection {conn_id} for pool {self.metadata.name}")

        return connection

    async def _ensure_min_connections(self):
        """Ensure minimum connections are available."""
        current_count = len(self.all_connections)

        for _ in range(self.min_connections - current_count):
            connection = await self._create_connection()
            await self.available_connections.put(connection)

    async def _pre_warm_connections(self, target_count: int):
        """Pre-warm connections based on expected usage."""
        current_count = len(self.all_connections)
        to_create = min(
            target_count - current_count, self.max_connections - current_count
        )

        if to_create > 0:
            logger.info(
                f"Pre-warming {to_create} connections for pool {self.metadata.name}"
            )

            # Create connections in parallel
            tasks = [self._create_connection() for _ in range(to_create)]
            connections = await asyncio.gather(*tasks)

            # Add to available pool
            for conn in connections:
                await self.available_connections.put(conn)

    async def _recycle_connection(self, connection: ConnectionActor):
        """Recycle a connection."""
        logger.info(
            f"Recycling connection {connection.id} (health: {connection.health_score})"
        )

        # Remove from all connections
        if connection.id in self.all_connections:
            del self.all_connections[connection.id]

        # Request recycling
        await connection.recycle()

        # Update metrics
        self.metrics.connections_recycled += 1

        # Ensure minimum connections
        await self._ensure_min_connections()

    async def _cleanup(self):
        """Clean up all connections and resources."""
        if self._closing:
            return

        self._closing = True
        logger.info(f"Cleaning up pool {self.metadata.name}")

        # Stop accepting new connections
        self._initialized = False

        # Stop all connection actors gracefully
        actors_to_stop = list(self.all_connections.values())
        for actor in actors_to_stop:
            try:
                await actor.stop()
            except Exception as e:
                logger.warning(f"Error stopping actor {actor.id}: {e}")

        # Stop supervisor
        try:
            await self.supervisor.stop()
        except Exception as e:
            logger.warning(f"Error stopping supervisor: {e}")

        # Clear connection tracking
        self.available_connections = asyncio.Queue()
        self.active_connections.clear()
        self.all_connections.clear()

        logger.info(f"Pool {self.metadata.name} cleaned up")

    def _on_connection_failure(self, actor_id: str, error: Exception):
        """Handle connection failure."""
        logger.error(f"Connection {actor_id} failed: {error}")
        self.metrics.connections_failed += 1

        # Remove from tracking
        if actor_id in self.all_connections:
            del self.all_connections[actor_id]
        if actor_id in self.active_connections:
            del self.active_connections[actor_id]

    def _on_connection_restart(self, actor_id: str, restart_count: int):
        """Handle connection restart."""
        logger.info(f"Connection {actor_id} restarted (count: {restart_count})")

    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Async process method for middleware compatibility."""
        return await self.async_run(**inputs)

    async def __aenter__(self):
        """Context manager entry."""
        await self._initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self._cleanup()
