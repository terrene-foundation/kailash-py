"""Redis connection pool manager for enterprise-grade connection handling.

Provides connection pooling, health monitoring, and automatic failover
for Redis operations with comprehensive metrics and circuit breaker integration.
"""

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

try:
    import redis.asyncio as redis
    from redis.asyncio.connection import ConnectionPool

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class PoolHealth(Enum):
    """Pool health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


class ConnectionStatus(Enum):
    """Connection status tracking."""

    ACTIVE = "active"
    IDLE = "idle"
    FAILED = "failed"
    RECOVERING = "recovering"


@register_node()
class RedisPoolManagerNode(AsyncNode):
    """Enterprise Redis connection pool manager.

    Provides:
    - Connection pooling with health monitoring
    - Automatic failover and recovery
    - Real-time metrics and alerting
    - Circuit breaker integration
    - Connection lifecycle optimization

    Design Purpose:
    - Prevent connection leaks and resource exhaustion
    - Ensure high availability for Redis operations
    - Provide enterprise-grade monitoring and alerting
    - Support multiple Redis instances and databases

    Examples:
        >>> # Create pool manager
        >>> pool_manager = RedisPoolManagerNode(
        ...     pool_size=10,
        ...     max_overflow=20,
        ...     health_check_interval=30
        ... )

        >>> # Execute Redis operation with pooling
        >>> result = await pool_manager.execute(
        ...     action="execute_command",
        ...     command="SET",
        ...     args=["key", "value"],
        ...     redis_url="redis://localhost:6380"
        ... )

        >>> # Monitor pool health
        >>> health = await pool_manager.execute(
        ...     action="get_pool_status"
        ... )
    """

    def __init__(
        self,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        health_check_interval: int = 60,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        **kwargs,
    ):
        """Initialize Redis pool manager."""
        super().__init__(**kwargs)

        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.health_check_interval = health_check_interval
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Shared pools keyed by (redis_url, database)
        self._pools: Dict[str, ConnectionPool] = {}
        self._pool_metrics: Dict[str, Dict[str, Any]] = {}
        self._pool_health: Dict[str, PoolHealth] = {}
        self._pool_lock = threading.Lock()

        # Connection tracking
        self._active_connections: Dict[str, List[Dict[str, Any]]] = {}
        self._failed_connections: Dict[str, List[Dict[str, Any]]] = {}

        # Health monitoring
        self._last_health_check: Dict[str, datetime] = {}
        self._health_history: Dict[str, List[Dict[str, Any]]] = {}

        self.logger.info(f"Initialized RedisPoolManagerNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Action to perform (execute_command, get_pool_status, health_check)",
            ),
            "redis_url": NodeParameter(
                name="redis_url",
                type=str,
                required=False,
                default="redis://localhost:6379",
                description="Redis connection URL",
            ),
            "database": NodeParameter(
                name="database",
                type=int,
                required=False,
                default=0,
                description="Redis database number",
            ),
            "command": NodeParameter(
                name="command",
                type=str,
                required=False,
                description="Redis command to execute",
            ),
            "args": NodeParameter(
                name="args",
                type=list,
                required=False,
                default=[],
                description="Redis command arguments",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Operation timeout in seconds",
            ),
            "pool_name": NodeParameter(
                name="pool_name",
                type=str,
                required=False,
                description="Specific pool name for operations",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "success": NodeParameter(
                name="success",
                type=bool,
                description="Whether the operation succeeded",
            ),
            "result": NodeParameter(
                name="result",
                type=Any,
                required=False,
                description="Command result or operation output",
            ),
            "pool_status": NodeParameter(
                name="pool_status",
                type=dict,
                required=False,
                description="Pool status information",
            ),
            "health_report": NodeParameter(
                name="health_report",
                type=dict,
                required=False,
                description="Health check results",
            ),
            "execution_time": NodeParameter(
                name="execution_time",
                type=float,
                description="Operation execution time",
            ),
            "pool_used": NodeParameter(
                name="pool_used",
                type=str,
                required=False,
                description="Pool identifier used for operation",
            ),
            "metrics": NodeParameter(
                name="metrics",
                type=dict,
                required=False,
                description="Pool metrics and statistics",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute Redis pool management operations."""
        action = kwargs["action"]
        start_time = time.time()

        try:
            if action == "execute_command":
                result = await self._execute_redis_command(
                    kwargs.get("command"),
                    kwargs.get("args", []),
                    kwargs.get("redis_url", "redis://localhost:6379"),
                    kwargs.get("database", 0),
                    kwargs.get("timeout", 30),
                )
            elif action == "get_pool_status":
                result = await self._get_pool_status(kwargs.get("pool_name"))
            elif action == "health_check":
                result = await self._perform_health_check(kwargs.get("pool_name"))
            elif action == "cleanup_pools":
                result = await self._cleanup_inactive_pools()
            else:
                raise ValueError(f"Unknown action: {action}")

            execution_time = time.time() - start_time

            return {"success": True, "execution_time": execution_time, **result}

        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Redis pool operation failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
            }

    async def _get_connection_pool(
        self, redis_url: str, database: int = 0
    ) -> ConnectionPool:
        """Get or create Redis connection pool."""
        pool_key = f"{redis_url}/db{database}"

        with self._pool_lock:
            if pool_key not in self._pools:
                if not REDIS_AVAILABLE:
                    raise NodeExecutionError(
                        "Redis is not available. Install with: pip install redis"
                    )

                try:
                    pool = ConnectionPool.from_url(
                        redis_url,
                        db=database,
                        max_connections=self.pool_size + self.max_overflow,
                        socket_timeout=self.pool_timeout,
                        socket_connect_timeout=10,
                        health_check_interval=self.health_check_interval,
                        retry_on_timeout=True,
                        retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                    )

                    self._pools[pool_key] = pool
                    self._pool_health[pool_key] = PoolHealth.HEALTHY
                    self._pool_metrics[pool_key] = {
                        "created_at": datetime.now(UTC),
                        "total_connections": 0,
                        "active_connections": 0,
                        "failed_connections": 0,
                        "total_commands": 0,
                        "successful_commands": 0,
                        "failed_commands": 0,
                        "avg_response_time": 0.0,
                        "last_activity": datetime.now(UTC),
                    }
                    self._active_connections[pool_key] = []
                    self._failed_connections[pool_key] = []
                    self._health_history[pool_key] = []

                    self.logger.info(f"Created Redis pool: {pool_key}")

                except Exception as e:
                    self.logger.error(f"Failed to create Redis pool {pool_key}: {e}")
                    raise NodeExecutionError(f"Failed to create Redis pool: {e}")

            return self._pools[pool_key]

    async def _execute_redis_command(
        self, command: str, args: List[Any], redis_url: str, database: int, timeout: int
    ) -> Dict[str, Any]:
        """Execute Redis command using connection pool."""
        pool_key = f"{redis_url}/db{database}"
        pool = await self._get_connection_pool(redis_url, database)

        connection = None
        start_time = time.time()

        try:
            # Get connection from pool
            connection = redis.Redis(connection_pool=pool)

            # Track active connection
            conn_info = {
                "connection_id": id(connection),
                "started_at": datetime.now(UTC),
                "command": command,
                "status": ConnectionStatus.ACTIVE,
            }
            self._active_connections[pool_key].append(conn_info)

            # Execute command with timeout
            result = await asyncio.wait_for(
                connection.execute_command(command, *args), timeout=timeout
            )

            # Update metrics
            execution_time = time.time() - start_time
            self._update_pool_metrics(pool_key, True, execution_time)

            return {
                "result": result,
                "pool_used": pool_key,
                "execution_time": execution_time,
                "connection_id": id(connection),
            }

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self._update_pool_metrics(pool_key, False, execution_time)
            self._record_connection_failure(pool_key, "timeout", execution_time)
            raise NodeExecutionError(f"Redis command timeout after {timeout}s")

        except Exception as e:
            execution_time = time.time() - start_time
            self._update_pool_metrics(pool_key, False, execution_time)
            self._record_connection_failure(pool_key, str(e), execution_time)
            raise NodeExecutionError(f"Redis command failed: {e}")

        finally:
            # Clean up connection tracking
            if connection:
                self._remove_active_connection(pool_key, id(connection))

            # Close connection properly
            if connection:
                try:
                    await connection.aclose()
                except Exception:
                    pass  # Ignore cleanup errors

    def _update_pool_metrics(self, pool_key: str, success: bool, execution_time: float):
        """Update pool metrics."""
        if pool_key not in self._pool_metrics:
            return

        metrics = self._pool_metrics[pool_key]

        metrics["total_commands"] += 1
        metrics["last_activity"] = datetime.now(UTC)

        if success:
            metrics["successful_commands"] += 1
        else:
            metrics["failed_commands"] += 1

        # Update average response time
        total_successful = metrics["successful_commands"]
        if total_successful > 0:
            current_avg = metrics["avg_response_time"]
            metrics["avg_response_time"] = (
                current_avg * (total_successful - 1) + execution_time
            ) / total_successful

    def _record_connection_failure(
        self, pool_key: str, error: str, execution_time: float
    ):
        """Record connection failure for analysis."""
        failure_info = {
            "timestamp": datetime.now(UTC),
            "error": error,
            "execution_time": execution_time,
            "pool_key": pool_key,
        }

        if pool_key not in self._failed_connections:
            self._failed_connections[pool_key] = []

        self._failed_connections[pool_key].append(failure_info)

        # Keep only recent failures (last 100)
        if len(self._failed_connections[pool_key]) > 100:
            self._failed_connections[pool_key] = self._failed_connections[pool_key][
                -100:
            ]

        # Update pool health based on failure rate
        self._assess_pool_health(pool_key)

    def _remove_active_connection(self, pool_key: str, connection_id: int):
        """Remove connection from active tracking."""
        if pool_key in self._active_connections:
            self._active_connections[pool_key] = [
                conn
                for conn in self._active_connections[pool_key]
                if conn["connection_id"] != connection_id
            ]

    def _assess_pool_health(self, pool_key: str):
        """Assess pool health based on recent metrics."""
        if pool_key not in self._pool_metrics:
            return

        metrics = self._pool_metrics[pool_key]
        total_commands = metrics["total_commands"]
        failed_commands = metrics["failed_commands"]

        if total_commands == 0:
            health = PoolHealth.HEALTHY
        else:
            failure_rate = failed_commands / total_commands
            avg_response_time = metrics["avg_response_time"]

            if failure_rate > 0.5 or avg_response_time > 10.0:
                health = PoolHealth.FAILED
            elif failure_rate > 0.2 or avg_response_time > 5.0:
                health = PoolHealth.CRITICAL
            elif failure_rate > 0.1 or avg_response_time > 2.0:
                health = PoolHealth.DEGRADED
            else:
                health = PoolHealth.HEALTHY

        self._pool_health[pool_key] = health

        # Record health history
        health_record = {
            "timestamp": datetime.now(UTC),
            "health": health.value,
            "failure_rate": failed_commands / max(total_commands, 1),
            "avg_response_time": metrics["avg_response_time"],
            "active_connections": len(self._active_connections.get(pool_key, [])),
        }

        if pool_key not in self._health_history:
            self._health_history[pool_key] = []

        self._health_history[pool_key].append(health_record)

        # Keep only recent history (last 100 records)
        if len(self._health_history[pool_key]) > 100:
            self._health_history[pool_key] = self._health_history[pool_key][-100:]

    async def _get_pool_status(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """Get status of all pools or specific pool."""
        if pool_name:
            if pool_name not in self._pools:
                return {"error": f"Pool {pool_name} not found"}

            return {"pool_status": {pool_name: self._get_single_pool_status(pool_name)}}
        else:
            return {
                "pool_status": {
                    pool_key: self._get_single_pool_status(pool_key)
                    for pool_key in self._pools.keys()
                }
            }

    def _get_single_pool_status(self, pool_key: str) -> Dict[str, Any]:
        """Get status of a single pool."""
        pool = self._pools.get(pool_key)
        metrics = self._pool_metrics.get(pool_key, {})
        health = self._pool_health.get(pool_key, PoolHealth.HEALTHY)

        if not pool:
            return {"status": "not_found"}

        # Get pool connection info
        try:
            created_connections = pool.created_connections
            available_connections = pool.available_connections
            in_use_connections = created_connections - available_connections
        except AttributeError:
            # Fallback for different Redis versions
            created_connections = 0
            available_connections = 0
            in_use_connections = len(self._active_connections.get(pool_key, []))

        return {
            "health": health.value,
            "created_connections": created_connections,
            "available_connections": available_connections,
            "in_use_connections": in_use_connections,
            "max_connections": self.pool_size + self.max_overflow,
            "metrics": metrics,
            "active_connections_count": len(self._active_connections.get(pool_key, [])),
            "recent_failures": len(self._failed_connections.get(pool_key, [])),
        }

    async def _perform_health_check(
        self, pool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        pools_to_check = [pool_name] if pool_name else list(self._pools.keys())
        health_results = {}

        for pool_key in pools_to_check:
            if pool_key not in self._pools:
                continue

            pool = self._pools[pool_key]
            start_time = time.time()

            try:
                # Test connection with ping
                test_connection = redis.Redis(connection_pool=pool)
                await test_connection.ping()
                await test_connection.aclose()

                response_time = time.time() - start_time

                health_results[pool_key] = {
                    "healthy": True,
                    "response_time": response_time,
                    "last_check": datetime.now(UTC).isoformat(),
                    "pool_status": self._get_single_pool_status(pool_key),
                }

            except Exception as e:
                response_time = time.time() - start_time

                health_results[pool_key] = {
                    "healthy": False,
                    "error": str(e),
                    "response_time": response_time,
                    "last_check": datetime.now(UTC).isoformat(),
                    "pool_status": self._get_single_pool_status(pool_key),
                }

                # Mark pool as failed
                self._pool_health[pool_key] = PoolHealth.FAILED

        self._last_health_check[pool_name or "all"] = datetime.now(UTC)

        return {"health_report": health_results}

    async def _cleanup_inactive_pools(self) -> Dict[str, Any]:
        """Clean up inactive pools to free resources."""
        cleanup_threshold = datetime.now(UTC) - timedelta(hours=1)
        cleaned_pools = []

        with self._pool_lock:
            pools_to_remove = []

            for pool_key, metrics in self._pool_metrics.items():
                last_activity = metrics.get("last_activity")
                if last_activity and last_activity < cleanup_threshold:
                    pools_to_remove.append(pool_key)

            for pool_key in pools_to_remove:
                try:
                    pool = self._pools.get(pool_key)
                    if pool:
                        await pool.aclose()

                    # Clean up tracking data
                    del self._pools[pool_key]
                    del self._pool_metrics[pool_key]
                    del self._pool_health[pool_key]
                    self._active_connections.pop(pool_key, None)
                    self._failed_connections.pop(pool_key, None)
                    self._health_history.pop(pool_key, None)

                    cleaned_pools.append(pool_key)
                    self.logger.info(f"Cleaned up inactive pool: {pool_key}")

                except Exception as e:
                    self.logger.error(f"Error cleaning up pool {pool_key}: {e}")

        return {"cleaned_pools": cleaned_pools, "cleanup_count": len(cleaned_pools)}
