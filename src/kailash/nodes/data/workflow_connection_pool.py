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
from kailash.core.actors.adaptive_pool_controller import AdaptivePoolController
from kailash.core.ml.query_patterns import QueryPatternTracker
from kailash.core.monitoring.connection_metrics import (
    ConnectionMetricsCollector,
    ErrorCategory,
)
from kailash.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    ConnectionCircuitBreaker,
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
        self.adaptive_sizing_enabled = config.get("adaptive_sizing", False)
        self.enable_query_routing = config.get("enable_query_routing", False)

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

        # Phase 2 components
        self.query_pattern_tracker = None
        self.adaptive_controller = None

        if self.enable_query_routing:
            self.query_pattern_tracker = QueryPatternTracker()

        if self.adaptive_sizing_enabled:
            self.adaptive_controller = AdaptivePoolController(
                min_size=self.min_connections, max_size=self.max_connections
            )

        # Phase 3 components
        # Circuit breaker for connection failures
        self.circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=config.get("circuit_breaker_failure_threshold", 5),
            recovery_timeout=config.get("circuit_breaker_recovery_timeout", 60),
            error_rate_threshold=config.get("circuit_breaker_error_rate", 0.5),
        )
        self.circuit_breaker = ConnectionCircuitBreaker(self.circuit_breaker_config)

        # Comprehensive metrics collector
        self.metrics_collector = ConnectionMetricsCollector(
            pool_name=self.metadata.name,
            retention_minutes=config.get("metrics_retention_minutes", 60),
        )

        # Enable query pipelining support
        self.enable_pipelining = config.get("enable_pipelining", False)
        self.pipeline_batch_size = config.get("pipeline_batch_size", 100)

        # Monitoring dashboard integration
        self.enable_monitoring = config.get("enable_monitoring", False)
        self.monitoring_port = config.get("monitoring_port", 8080)

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
            NodeParameter(
                name="adaptive_sizing",
                type=bool,
                required=False,
                default=False,
                description="Enable adaptive pool sizing based on workload",
            ),
            NodeParameter(
                name="enable_query_routing",
                type=bool,
                required=False,
                default=False,
                description="Enable query pattern tracking for routing optimization",
            ),
            # Phase 3 parameters
            NodeParameter(
                name="circuit_breaker_failure_threshold",
                type=int,
                required=False,
                default=5,
                description="Failures before circuit breaker opens",
            ),
            NodeParameter(
                name="circuit_breaker_recovery_timeout",
                type=int,
                required=False,
                default=60,
                description="Seconds before circuit breaker tries recovery",
            ),
            NodeParameter(
                name="circuit_breaker_error_rate",
                type=float,
                required=False,
                default=0.5,
                description="Error rate threshold to open circuit",
            ),
            NodeParameter(
                name="metrics_retention_minutes",
                type=int,
                required=False,
                default=60,
                description="How long to retain detailed metrics",
            ),
            NodeParameter(
                name="enable_pipelining",
                type=bool,
                required=False,
                default=False,
                description="Enable query pipelining for batch operations",
            ),
            NodeParameter(
                name="pipeline_batch_size",
                type=int,
                required=False,
                default=100,
                description="Maximum queries per pipeline batch",
            ),
            NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=False,
                description="Enable monitoring dashboard",
            ),
            NodeParameter(
                name="monitoring_port",
                type=int,
                required=False,
                default=8080,
                description="Port for monitoring dashboard",
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
        elif operation == "get_status":
            return await self._get_pool_status()
        elif operation == "adjust_pool_size":
            return await self.adjust_pool_size(inputs.get("new_size"))
        elif operation == "get_pool_statistics":
            return await self.get_pool_statistics()
        elif operation == "get_comprehensive_status":
            return await self.get_comprehensive_status()
        elif operation == "start_monitoring":
            return await self._start_monitoring_dashboard()
        elif operation == "stop_monitoring":
            return await self._stop_monitoring_dashboard()
        elif operation == "export_metrics":
            return {"prometheus_metrics": self.metrics_collector.export_prometheus()}
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

            # Start adaptive controller if enabled
            if self.adaptive_controller:
                await self.adaptive_controller.start(
                    pool_ref=self, pattern_tracker=self.query_pattern_tracker
                )

            self._initialized = True

            return {
                "status": "initialized",
                "min_connections": self.min_connections,
                "max_connections": self.max_connections,
                "adaptive_sizing": self.adaptive_sizing_enabled,
                "query_routing": self.enable_query_routing,
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
            # Use circuit breaker to protect connection acquisition
            async def acquire_with_circuit_breaker():
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

                return connection

            # Execute with circuit breaker protection
            connection = await self.circuit_breaker.call(acquire_with_circuit_breaker)

            # Record acquisition time
            wait_time = time.time() - start_time
            self.metrics.record_acquisition_time(wait_time)

            # Track in comprehensive metrics
            with self.metrics_collector.track_acquisition() as timer:
                pass  # Already acquired, just recording time

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

        except CircuitBreakerError as e:
            # Circuit is open - pool is experiencing failures
            self.metrics_collector.track_pool_exhaustion()
            logger.error(f"Circuit breaker open: {e}")
            raise NodeExecutionError(f"Connection pool circuit breaker open: {e}")
        except Exception as e:
            logger.error(f"Failed to acquire connection: {e}")
            self.metrics_collector.track_query_error("ACQUIRE", e)
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

        # Determine query type for metrics
        query = inputs.get("query", "").strip().upper()
        query_type = "UNKNOWN"
        if query.startswith("SELECT"):
            query_type = "SELECT"
        elif query.startswith("INSERT"):
            query_type = "INSERT"
        elif query.startswith("UPDATE"):
            query_type = "UPDATE"
        elif query.startswith("DELETE"):
            query_type = "DELETE"

        try:
            # Execute query with comprehensive metrics tracking
            with self.metrics_collector.track_query(query_type) as timer:
                result = await connection.execute(
                    query=inputs.get("query"),
                    params=inputs.get("params"),
                    fetch_mode=inputs.get("fetch_mode", "all"),
                )

            # Update metrics
            self.metrics.queries_executed += 1
            if not result.success:
                self.metrics.query_errors += 1
                self.metrics_collector.track_query_error(
                    query_type, Exception(result.error)
                )

            # Track query pattern if enabled
            if self.query_pattern_tracker and inputs.get("query"):
                self.query_pattern_tracker.record_execution(
                    fingerprint=inputs.get("query_fingerprint", inputs.get("query")),
                    execution_time_ms=result.execution_time * 1000,
                    connection_id=connection_id,
                    parameters=inputs.get("params", {}),
                    success=result.success,
                    result_size=len(result.data) if result.data else 0,
                )

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

        # Stop adaptive controller if running
        if self.adaptive_controller:
            await self.adaptive_controller.stop()

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

    async def _get_pool_status(self) -> Dict[str, Any]:
        """Get pool status for query router."""
        connections = {}

        for conn_id, conn in self.all_connections.items():
            connections[conn_id] = {
                "health_score": conn.health_score,
                "active_queries": 1 if conn_id in self.active_connections else 0,
                "capabilities": [
                    "read",
                    "write",
                ],  # TODO: Add actual capability detection
                "avg_latency_ms": 0.0,  # TODO: Track actual latency
                "last_used": datetime.now().isoformat(),
            }

        return {
            "connections": connections,
            "pool_size": len(self.all_connections),
            "active_count": len(self.active_connections),
            "available_count": self.available_connections.qsize(),
        }

    async def adjust_pool_size(self, new_size: int) -> Dict[str, Any]:
        """Dynamically adjust pool size."""
        if new_size < self.min_connections or new_size > self.max_connections:
            return {
                "success": False,
                "reason": f"Size must be between {self.min_connections} and {self.max_connections}",
            }

        current_size = len(self.all_connections)

        if new_size > current_size:
            # Scale up
            connections_to_add = new_size - current_size
            for _ in range(connections_to_add):
                try:
                    await self._create_connection()
                except Exception as e:
                    logger.error(f"Failed to create connection during scale up: {e}")

        elif new_size < current_size:
            # Scale down - remove idle connections first
            connections_to_remove = current_size - new_size
            removed = 0

            # Try to remove idle connections
            while (
                removed < connections_to_remove
                and not self.available_connections.empty()
            ):
                try:
                    conn = await asyncio.wait_for(
                        self.available_connections.get(), timeout=0.1
                    )
                    await self._recycle_connection(conn)
                    removed += 1
                except asyncio.TimeoutError:
                    break

        return {
            "success": True,
            "previous_size": current_size,
            "new_size": len(self.all_connections),
        }

    async def get_pool_statistics(self) -> Dict[str, Any]:
        """Get detailed pool statistics for adaptive sizing."""
        total_connections = len(self.all_connections)
        active_connections = len(self.active_connections)
        idle_connections = self.available_connections.qsize()

        # Calculate metrics
        utilization_rate = (
            active_connections / total_connections if total_connections > 0 else 0
        )

        # Get average health score
        health_scores = [conn.health_score for conn in self.all_connections.values()]
        avg_health_score = (
            sum(health_scores) / len(health_scores) if health_scores else 100
        )

        # Queue depth (approximate based on waiters)
        queue_depth = 0  # TODO: Track actual queue depth

        # Get timing metrics from pool metrics
        stats = self.metrics.get_stats()

        return {
            "total_connections": total_connections,
            "active_connections": active_connections,
            "idle_connections": idle_connections,
            "queue_depth": queue_depth,
            "utilization_rate": utilization_rate,
            "avg_health_score": avg_health_score,
            "avg_acquisition_time_ms": stats["performance"]["avg_acquisition_time_ms"],
            "avg_query_time_ms": 50.0,  # TODO: Track actual query time
            "queries_per_second": (
                stats["queries"]["executed"] / stats["uptime_seconds"]
                if stats["uptime_seconds"] > 0
                else 0
            ),
            # Phase 3 additions
            "circuit_breaker_status": self.circuit_breaker.get_status(),
            "comprehensive_metrics": self.metrics_collector.get_all_metrics(),
            "error_rate": self.metrics_collector.get_error_summary()["error_rate"],
            "health_score": avg_health_score,
            "pool_name": self.metadata.name,
        }

    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status including all Phase 3 features."""
        base_stats = await self.get_pool_statistics()

        # Add circuit breaker details
        cb_status = self.circuit_breaker.get_status()

        # Add comprehensive metrics
        metrics = self.metrics_collector.get_all_metrics()

        # Add pattern learning insights if enabled
        pattern_insights = {}
        if self.query_pattern_tracker:
            patterns = self.query_pattern_tracker.get_all_patterns()
            pattern_insights = {
                "detected_patterns": len(patterns),
                "workload_forecast": self.query_pattern_tracker.get_workload_forecast(
                    15
                ),
            }

        # Add adaptive controller status if enabled
        adaptive_status = {}
        if self.adaptive_controller:
            adaptive_status = {
                "current_size": len(self.all_connections),
                "recommended_size": self.adaptive_controller.get_recommended_size(),
                "last_adjustment": self.adaptive_controller.get_last_adjustment(),
            }

        return {
            **base_stats,
            "circuit_breaker": {
                "state": cb_status["state"],
                "metrics": cb_status["metrics"],
                "time_until_recovery": cb_status.get("time_until_recovery"),
            },
            "detailed_metrics": {
                "counters": metrics["counters"],
                "gauges": metrics["gauges"],
                "histograms": metrics["histograms"],
                "errors": metrics["errors"],
                "query_summary": metrics["queries"],
            },
            "pattern_insights": pattern_insights,
            "adaptive_control": adaptive_status,
            "monitoring": {
                "dashboard_enabled": self.enable_monitoring,
                "dashboard_url": (
                    f"http://localhost:{self.monitoring_port}"
                    if self.enable_monitoring
                    else None
                ),
            },
        }

    async def _start_monitoring_dashboard(self) -> Dict[str, Any]:
        """Start the monitoring dashboard if enabled."""
        if not self.enable_monitoring:
            return {"error": "Monitoring not enabled in configuration"}

        try:
            # Register this pool with the global metrics aggregator
            if hasattr(self.runtime, "metrics_aggregator"):
                self.runtime.metrics_aggregator.register_collector(
                    self.metrics_collector
                )

            # Start monitoring dashboard if not already running
            if not hasattr(self.runtime, "monitoring_dashboard"):
                from kailash.nodes.monitoring.connection_dashboard import (
                    ConnectionDashboardNode,
                )

                dashboard = ConnectionDashboardNode(
                    name="global_dashboard",
                    port=self.monitoring_port,
                    update_interval=1.0,
                )

                # Store dashboard in runtime for sharing
                self.runtime.monitoring_dashboard = dashboard
                await dashboard.start()

                return {
                    "status": "started",
                    "dashboard_url": f"http://localhost:{self.monitoring_port}",
                }
            else:
                return {
                    "status": "already_running",
                    "dashboard_url": f"http://localhost:{self.monitoring_port}",
                }

        except Exception as e:
            logger.error(f"Failed to start monitoring dashboard: {e}")
            return {"error": str(e)}

    async def _stop_monitoring_dashboard(self) -> Dict[str, Any]:
        """Stop the monitoring dashboard."""
        try:
            if hasattr(self.runtime, "monitoring_dashboard"):
                await self.runtime.monitoring_dashboard.stop()
                del self.runtime.monitoring_dashboard
                return {"status": "stopped"}
            else:
                return {"status": "not_running"}
        except Exception as e:
            logger.error(f"Failed to stop monitoring dashboard: {e}")
            return {"error": str(e)}

    def _update_pool_metrics(self):
        """Update pool metrics for monitoring."""
        total = len(self.all_connections)
        active = len(self.active_connections)
        idle = self.available_connections.qsize()

        # Update comprehensive metrics
        self.metrics_collector.update_pool_stats(active, idle, total)

        # Track health checks
        for conn in self.all_connections.values():
            self.metrics_collector.track_health_check(
                success=conn.health_score > self.health_threshold,
                duration_ms=5.0,  # Placeholder - real implementation would track actual time
            )
