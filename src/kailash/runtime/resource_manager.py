"""Runtime resource management and coordination.

This module provides resource coordination, connection pool management,
and runtime lifecycle management for the enhanced LocalRuntime with
persistent mode support.

Components:
- ResourceCoordinator: Cross-runtime resource coordination
- ConnectionPoolManager: Connection pool sharing and lifecycle
- RuntimeLifecycleManager: Runtime startup/shutdown coordination
"""

import asyncio
import gc
import hashlib
import logging
import random
import re
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

import psutil
from kailash.sdk_exceptions import CircuitBreakerOpenError, ResourceLimitExceededError

logger = logging.getLogger(__name__)


class ResourceCoordinator:
    """Coordinates resources across multiple runtime instances."""

    def __init__(self, runtime_id: str, enable_coordination: bool = True):
        """Initialize resource coordinator.

        Args:
            runtime_id: Unique identifier for this runtime instance
            enable_coordination: Whether to enable cross-runtime coordination
        """
        self.runtime_id = runtime_id
        self.enable_coordination = enable_coordination

        # Resource tracking
        self._shared_resources: Dict[str, Any] = {}
        self._resource_configs: Dict[str, Dict] = {}
        self._resource_references: Dict[str, int] = defaultdict(int)
        self._registered_runtimes: Dict[str, Dict] = {}

        # Thread safety
        self._coordination_lock = threading.RLock()

        # Async operations tracking
        self._async_operations: Dict[str, asyncio.Task] = {}

        logger.info(f"ResourceCoordinator initialized for runtime {runtime_id}")

    def register_runtime(self, runtime_id: str, config: Dict[str, Any]) -> None:
        """Register a runtime instance for coordination.

        Args:
            runtime_id: Runtime instance identifier
            config: Runtime configuration for coordination
        """
        with self._coordination_lock:
            self._registered_runtimes[runtime_id] = {
                "config": config,
                "registered_at": datetime.now(UTC),
                "last_seen": datetime.now(UTC),
            }

        logger.info(f"Registered runtime {runtime_id} for coordination")

    def allocate_shared_resource(
        self, resource_type: str, resource_config: Dict[str, Any]
    ) -> str:
        """Allocate a shared resource with reference counting.

        Args:
            resource_type: Type of resource (e.g., 'connection_pool')
            resource_config: Configuration for the resource

        Returns:
            Resource ID for future reference
        """
        with self._coordination_lock:
            # Generate resource ID based on type and config
            config_str = str(sorted(resource_config.items()))
            resource_id = (
                f"{resource_type}_{hashlib.md5(config_str.encode()).hexdigest()[:8]}"
            )

            if resource_id not in self._shared_resources:
                # Create new resource
                self._shared_resources[resource_id] = {
                    "type": resource_type,
                    "config": resource_config,
                    "created_at": datetime.now(UTC),
                    "created_by": self.runtime_id,
                    "instance": None,  # To be set by specific managers
                }
                self._resource_configs[resource_id] = resource_config

            # Increment reference count
            self._resource_references[resource_id] += 1

            logger.debug(
                f"Allocated shared resource {resource_id}, refs: {self._resource_references[resource_id]}"
            )
            return resource_id

    def get_shared_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Get shared resource by ID.

        Args:
            resource_id: Resource identifier

        Returns:
            Resource info or None if not found
        """
        with self._coordination_lock:
            return self._shared_resources.get(resource_id)

    def add_resource_reference(self, resource_id: str) -> None:
        """Add reference to shared resource.

        Args:
            resource_id: Resource identifier
        """
        with self._coordination_lock:
            if resource_id in self._shared_resources:
                self._resource_references[resource_id] += 1

    def remove_resource_reference(self, resource_id: str) -> None:
        """Remove reference to shared resource.

        Args:
            resource_id: Resource identifier
        """
        with self._coordination_lock:
            if resource_id in self._resource_references:
                self._resource_references[resource_id] -= 1

                # Clean up if no references
                if self._resource_references[resource_id] <= 0:
                    self._cleanup_resource(resource_id)

    def get_resource_reference_count(self, resource_id: str) -> int:
        """Get reference count for resource.

        Args:
            resource_id: Resource identifier

        Returns:
            Current reference count
        """
        with self._coordination_lock:
            return self._resource_references.get(resource_id, 0)

    def _cleanup_resource(self, resource_id: str) -> None:
        """Clean up resource when no references remain.

        Args:
            resource_id: Resource identifier
        """
        if resource_id in self._shared_resources:
            resource = self._shared_resources[resource_id]
            logger.info(
                f"Cleaning up shared resource {resource_id} (type: {resource['type']})"
            )

            # Remove from tracking
            del self._shared_resources[resource_id]
            del self._resource_references[resource_id]
            if resource_id in self._resource_configs:
                del self._resource_configs[resource_id]

    async def coordinate_async_operation(self, operation_name: str) -> None:
        """Coordinate async operation across runtimes.

        Args:
            operation_name: Name of the operation being coordinated
        """
        if not hasattr(self, "_async_operations"):
            self._async_operations = {}

        # Track operation
        self._async_operations[operation_name] = {
            "started_at": datetime.now(UTC),
            "runtime_id": self.runtime_id,
        }

    def get_coordination_status(self) -> Dict[str, Any]:
        """Get current coordination status.

        Returns:
            Status information including resources and runtimes
        """
        with self._coordination_lock:
            return {
                "runtime_id": self.runtime_id,
                "enable_coordination": self.enable_coordination,
                "shared_resources": len(self._shared_resources),
                "registered_runtimes": len(self._registered_runtimes),
                "total_references": sum(self._resource_references.values()),
            }


class ConnectionPoolManager:
    """Manages connection pools with sharing and lifecycle support."""

    def __init__(
        self,
        max_pools: int = 20,
        default_pool_size: int = 10,
        pool_timeout: int = 30,
        enable_sharing: bool = True,
        enable_health_monitoring: bool = True,
        pool_ttl: int = 3600,
    ):
        """Initialize connection pool manager.

        Args:
            max_pools: Maximum number of pools to maintain
            default_pool_size: Default size for new pools
            pool_timeout: Default timeout for pool operations
            enable_sharing: Enable pool sharing across runtimes
            enable_health_monitoring: Enable health monitoring
            pool_ttl: Time-to-live for unused pools in seconds
        """
        self.max_pools = max_pools
        self.default_pool_size = default_pool_size
        self.pool_timeout = pool_timeout
        self.enable_sharing = enable_sharing
        self.enable_health_monitoring = enable_health_monitoring
        self.pool_ttl = pool_ttl

        # Pool tracking
        self._pools: Dict[str, Any] = {}
        self._pool_configs: Dict[str, Dict] = {}
        self._pool_health: Dict[str, Dict] = {}
        self._pool_usage: Dict[str, Dict] = {}
        self._pool_runtimes: Dict[str, Set[str]] = defaultdict(set)

        # Lock for thread safety
        self._lock = threading.RLock()

        logger.info(f"ConnectionPoolManager initialized (max_pools={max_pools})")

    async def create_pool(self, pool_name: str, pool_config: Dict[str, Any]) -> Any:
        """Create a new connection pool.

        Args:
            pool_name: Name for the pool
            pool_config: Pool configuration

        Returns:
            Pool instance

        Raises:
            ResourceLimitExceededError: If max_pools limit exceeded
        """
        with self._lock:
            if len(self._pools) >= self.max_pools:
                raise ResourceLimitExceededError(
                    f"Maximum pools limit ({self.max_pools}) exceeded"
                )

            if pool_name in self._pools:
                return self._pools[pool_name]

            # Create appropriate pool based on database type
            database_type = pool_config.get("database_type", "").lower()

            if database_type == "sqlite":
                # For SQLite, create a simple connection object
                import aiosqlite

                connection_string = pool_config.get("database_url", ":memory:")
                pool = {
                    "database_type": "sqlite",
                    "connection_string": connection_string,
                    "aiosqlite": aiosqlite,
                }
            elif database_type == "postgresql":
                # Create real PostgreSQL connection pool using asyncpg
                pool = await self._create_postgresql_pool(pool_config)
            elif database_type == "mysql":
                # Create real MySQL connection pool using aiomysql
                pool = await self._create_mysql_pool(pool_config)
            else:
                # Fail fast for unsupported database types - no production mock fallbacks
                supported_types = ["postgresql", "mysql", "sqlite"]
                raise ValueError(
                    f"Unsupported database type '{database_type}'. "
                    f"Supported types: {supported_types}. "
                    f"Configuration error in pool '{pool_name}'"
                )

            self._pools[pool_name] = pool
            self._pool_configs[pool_name] = pool_config.copy()
            self._pool_usage[pool_name] = {
                "created_at": datetime.now(UTC),
                "last_used": datetime.now(UTC),
                "use_count": 0,
            }

            if self.enable_health_monitoring:
                self._pool_health[pool_name] = {
                    "status": "healthy",
                    "active_connections": 0,
                    "total_connections": pool_config.get(
                        "pool_size", self.default_pool_size
                    ),
                    "last_check": datetime.now(UTC),
                }

            logger.info(f"Created connection pool '{pool_name}'")
            return pool

    async def get_or_create_pool(
        self, pool_name: str, pool_config: Dict[str, Any]
    ) -> Any:
        """Get existing pool or create new one.

        Args:
            pool_name: Name for the pool
            pool_config: Pool configuration

        Returns:
            Pool instance
        """
        with self._lock:
            if pool_name in self._pools:
                # Update usage
                self._pool_usage[pool_name]["last_used"] = datetime.now(UTC)
                self._pool_usage[pool_name]["use_count"] += 1
                return self._pools[pool_name]

            return await self.create_pool(pool_name, pool_config)

    async def create_shared_pool(
        self, pool_name: str, pool_config: Dict[str, Any], runtime_id: str
    ) -> Any:
        """Create a shared pool for cross-runtime use.

        Args:
            pool_name: Name for the pool
            pool_config: Pool configuration
            runtime_id: Runtime requesting the pool

        Returns:
            Pool instance
        """
        if not self.enable_sharing:
            return await self.create_pool(pool_name, pool_config)

        with self._lock:
            pool = await self.get_or_create_pool(pool_name, pool_config)
            self._pool_runtimes[pool_name].add(runtime_id)

            logger.info(f"Shared pool '{pool_name}' with runtime {runtime_id}")
            return pool

    async def get_shared_pool(self, pool_name: str, runtime_id: str) -> Optional[Any]:
        """Get shared pool for runtime.

        Args:
            pool_name: Name of the pool
            runtime_id: Runtime requesting the pool

        Returns:
            Pool instance or None if not found
        """
        with self._lock:
            if pool_name in self._pools and self.enable_sharing:
                self._pool_runtimes[pool_name].add(runtime_id)
                return self._pools[pool_name]
            return None

    def get_pool_runtime_count(self, pool_name: str) -> int:
        """Get number of runtimes using a pool.

        Args:
            pool_name: Name of the pool

        Returns:
            Number of runtimes using the pool
        """
        with self._lock:
            return len(self._pool_runtimes.get(pool_name, set()))

    def get_pool_health(self, pool_name: str) -> Dict[str, Any]:
        """Get health status for a pool.

        Args:
            pool_name: Name of the pool

        Returns:
            Health status dictionary
        """
        with self._lock:
            if pool_name in self._pool_health:
                return self._pool_health[pool_name].copy()

            return {
                "status": "unknown",
                "active_connections": 0,
                "total_connections": 0,
                "last_check": None,
            }

    def is_pool_active(self, pool_name: str) -> bool:
        """Check if pool is active.

        Args:
            pool_name: Name of the pool

        Returns:
            True if pool is active
        """
        with self._lock:
            return pool_name in self._pools

    async def close_pool(self, pool_name: str) -> None:
        """Close and remove a pool with proper error handling and race condition protection.

        Args:
            pool_name: Name of the pool to close
        """
        # Get pool reference under lock but don't hold lock during async operations
        with self._lock:
            if pool_name not in self._pools:
                logger.debug(f"Pool '{pool_name}' not found for closure")
                return

            pool = self._pools[pool_name]
            # Remove from pools immediately to prevent race conditions
            del self._pools[pool_name]

        # Close pool outside lock to prevent deadlock
        close_error = None
        try:
            if isinstance(pool, RuntimeManagedPool):
                await pool._runtime_close()
            elif hasattr(pool, "close"):
                await pool.close()
            logger.info(f"Successfully closed connection pool '{pool_name}'")
        except Exception as e:
            close_error = e
            logger.error(f"Failed to close pool '{pool_name}': {e}")

        # Always clean up tracking dictionaries - even if close failed
        with self._lock:
            # Remove from all tracking structures
            self._pool_configs.pop(pool_name, None)
            self._pool_usage.pop(pool_name, None)
            self._pool_health.pop(pool_name, None)
            self._pool_runtimes.pop(pool_name, None)

        # Re-raise close error after cleanup
        if close_error:
            raise close_error

    async def cleanup_unused_pools(self) -> int:
        """Clean up unused pools past TTL.

        Returns:
            Number of pools cleaned up
        """
        cleaned_count = 0
        current_time = datetime.now(UTC)

        # Identify pools to cleanup while holding lock
        with self._lock:
            pools_to_cleanup = []

            for pool_name, usage in self._pool_usage.items():
                if (current_time - usage["last_used"]).total_seconds() > self.pool_ttl:
                    pools_to_cleanup.append(pool_name)

        # Close pools outside the lock to avoid async deadlock
        for pool_name in pools_to_cleanup:
            await self.close_pool(pool_name)
            cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} unused connection pools")

        return cleaned_count

    async def _create_postgresql_pool(self, pool_config: Dict[str, Any]) -> Any:
        """Create a real PostgreSQL connection pool using asyncpg."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg not installed. Install with: pip install asyncpg"
            )

        # Extract connection parameters
        connection_string = pool_config.get("connection_string") or pool_config.get(
            "database_url"
        )
        if not connection_string:
            # Build connection string from individual parameters
            host = pool_config.get("host", "localhost")
            port = pool_config.get("port", 5432)
            database = pool_config.get("database", "postgres")
            user = pool_config.get("user", "postgres")
            password = pool_config.get("password", "")
            connection_string = (
                f"postgresql://{user}:{password}@{host}:{port}/{database}"
            )

        # Extract pool size settings
        min_size = pool_config.get("min_pool_size", 1)
        max_size = pool_config.get(
            "pool_size", pool_config.get("max_pool_size", self.default_pool_size)
        )

        # Create asyncpg pool
        pool = await asyncpg.create_pool(
            connection_string, min_size=min_size, max_size=max_size, command_timeout=60
        )

        logger.info(
            f"Created PostgreSQL connection pool with {min_size}-{max_size} connections"
        )

        # Validate pool before wrapping
        if not await self._validate_pool(pool, "postgresql"):
            await pool.close()  # Clean up failed pool
            raise RuntimeError(
                f"PostgreSQL pool validation failed for connection: {connection_string}"
            )

        # Wrap pool to prevent premature closure by node-level cleanup
        return RuntimeManagedPool(pool)

    async def _create_mysql_pool(self, pool_config: Dict[str, Any]) -> Any:
        """Create a real MySQL connection pool using aiomysql."""
        try:
            import aiomysql
        except ImportError:
            raise ImportError(
                "aiomysql not installed. Install with: pip install aiomysql"
            )

        # Extract connection parameters
        host = pool_config.get("host", "localhost")
        port = pool_config.get("port", 3306)
        user = pool_config.get("user", "root")
        password = pool_config.get("password", "")
        database = pool_config.get("database", "")

        # Extract pool size settings
        minsize = pool_config.get("min_pool_size", 1)
        maxsize = pool_config.get(
            "pool_size", pool_config.get("max_pool_size", self.default_pool_size)
        )

        # Create aiomysql pool
        pool = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=database,
            minsize=minsize,
            maxsize=maxsize,
            autocommit=True,
        )

        logger.info(
            f"Created MySQL connection pool with {minsize}-{maxsize} connections"
        )

        # Validate pool before wrapping
        if not await self._validate_pool(pool, "mysql"):
            await pool.close()  # Clean up failed pool
            raise RuntimeError(
                f"MySQL pool validation failed for connection: {host}:{port}"
            )

        # Wrap pool to prevent premature closure by node-level cleanup
        return RuntimeManagedPool(pool)

    async def _validate_pool(self, pool: Any, database_type: str) -> bool:
        """Validate that a pool actually works before returning it.

        Args:
            pool: The database pool to validate
            database_type: Type of database (postgresql, mysql, sqlite)

        Returns:
            True if pool is functional, False otherwise
        """
        try:
            if database_type == "postgresql":
                async with pool.acquire() as conn:
                    await conn.fetchrow("SELECT 1 as test_connection")
                    logger.debug("PostgreSQL pool validation successful")
            elif database_type == "mysql":
                async with pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1 as test_connection")
                        await cursor.fetchone()
                    logger.debug("MySQL pool validation successful")
            elif database_type == "sqlite":
                # SQLite validation would be different since it uses dict format
                logger.debug("SQLite pool validation skipped (not a real pool)")
            else:
                logger.warning(f"Unknown database type for validation: {database_type}")
                return False
            return True
        except Exception as e:
            logger.error(f"Pool validation failed for {database_type}: {e}")
            return False


class RuntimeManagedPool:
    """Wrapper for database pools managed by runtime to prevent external closure."""

    def __init__(self, underlying_pool):
        """Initialize with the real pool instance."""
        self._underlying_pool = underlying_pool
        self._is_runtime_managed = True
        self._pool_type = type(underlying_pool).__name__

        # Pre-validate essential attributes exist to fail fast
        required_attrs = ["acquire"]
        for attr in required_attrs:
            if not hasattr(underlying_pool, attr):
                raise ValueError(
                    f"Invalid pool type '{self._pool_type}': missing required attribute '{attr}'. "
                    f"Pool must implement acquire() method for database operations."
                )

        logger.debug(f"Created RuntimeManagedPool wrapping {self._pool_type}")

    def __getattr__(self, name):
        """Delegate all attributes to the underlying pool except close()."""
        if name == "close":
            # Prevent external closure - only runtime can close
            return self._no_close
        try:
            return getattr(self._underlying_pool, name)
        except AttributeError as e:
            # Provide clearer error messages for debugging
            raise AttributeError(
                f"RuntimeManagedPool({self._pool_type}): {e}. "
                f"The underlying {self._pool_type} pool does not support attribute '{name}'"
            ) from e

    async def _no_close(self):
        """No-op close method to prevent external closure."""
        logger.debug(f"Ignored attempt to close runtime-managed {self._pool_type} pool")
        pass

    async def _runtime_close(self):
        """Internal method for runtime to actually close the pool."""
        try:
            if hasattr(self._underlying_pool, "close"):
                await self._underlying_pool.close()
                logger.debug(f"Successfully closed underlying {self._pool_type} pool")
            else:
                logger.warning(
                    f"Underlying {self._pool_type} pool has no close() method"
                )
        except Exception as e:
            logger.error(f"Error closing underlying {self._pool_type} pool: {e}")
            raise


class MockConnectionPool:
    """Mock connection pool for testing."""

    def __init__(self, config: Dict[str, Any], pool_size: int):
        self.config = config
        self.pool_size = pool_size
        self.created_at = datetime.now(UTC)

    async def close(self):
        """Close the mock pool."""
        pass


class RuntimeLifecycleManager:
    """Manages runtime lifecycle operations."""

    def __init__(self, runtime_id: str):
        """Initialize runtime lifecycle manager.

        Args:
            runtime_id: Unique runtime identifier
        """
        self.runtime_id = runtime_id
        self._is_started = False
        self._shutdown_hooks: List[Callable] = []
        self._startup_hooks: List[Callable] = []

    async def startup(self) -> None:
        """Execute startup sequence."""
        if self._is_started:
            return

        logger.info(f"Starting runtime lifecycle for {self.runtime_id}")

        # Execute startup hooks
        for hook in self._startup_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"Startup hook failed: {e}")

        self._is_started = True

    async def shutdown(self, timeout: int = 30) -> None:
        """Execute shutdown sequence.

        Args:
            timeout: Maximum time to wait for shutdown
        """
        if not self._is_started:
            return

        logger.info(f"Shutting down runtime lifecycle for {self.runtime_id}")

        # Execute shutdown hooks with timeout
        try:
            await asyncio.wait_for(self._execute_shutdown_hooks(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout after {timeout}s for runtime {self.runtime_id}"
            )

        self._is_started = False

    async def _execute_shutdown_hooks(self) -> None:
        """Execute all shutdown hooks."""
        for hook in reversed(self._shutdown_hooks):  # Reverse order for cleanup
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"Shutdown hook failed: {e}")

    def add_startup_hook(self, hook: Callable) -> None:
        """Add startup hook.

        Args:
            hook: Function to call during startup
        """
        self._startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: Callable) -> None:
        """Add shutdown hook.

        Args:
            hook: Function to call during shutdown
        """
        self._shutdown_hooks.append(hook)

    @property
    def is_started(self) -> bool:
        """Check if runtime is started."""
        return self._is_started


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker pattern for resilience and fault tolerance.

    Prevents cascading failures by temporarily blocking requests to failing services.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        expected_exception: type = Exception,
        recovery_threshold: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            name: Name of the circuit breaker for logging
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before attempting recovery
            expected_exception: Exception type that triggers the circuit breaker
            recovery_threshold: Number of successes needed to close circuit from half-open
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.expected_exception = expected_exception
        self.recovery_threshold = recovery_threshold

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._success_count = 0

        # Thread safety
        self._lock = threading.RLock()

        logger.info(f"Circuit breaker '{name}' initialized")

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function with circuit breaker protection.

        Args:
            func: Function to call (sync or async)
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitBreakerState.HALF_OPEN
                    logger.info(f"Circuit breaker '{self.name}' moved to HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )

        try:
            # Call function (handle both sync and async)
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Success - update state
            self._on_success()
            return result

        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset."""
        if self._last_failure_time is None:
            return False
        return (time.time() - self._last_failure_time) >= self.timeout_seconds

    def _on_success(self) -> None:
        """Handle successful call."""
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.recovery_threshold:
                    self._reset()
                    logger.info(f"Circuit breaker '{self.name}' CLOSED after recovery")
            elif self._state == CircuitBreakerState.CLOSED:
                self._reset()  # Reset failure count on success

    def _on_failure(self) -> None:
        """Handle failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}' OPENED after {self._failure_count} failures"
                )

    def _reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state.

        Returns:
            State information dictionary
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "failure_threshold": self.failure_threshold,
                "timeout_seconds": self.timeout_seconds,
            }

    def force_open(self) -> None:
        """Force circuit breaker to open state."""
        with self._lock:
            self._state = CircuitBreakerState.OPEN
            self._failure_count = self.failure_threshold
            self._last_failure_time = time.time()
            logger.warning(f"Circuit breaker '{self.name}' forced OPEN")

    def force_close(self) -> None:
        """Force circuit breaker to closed state."""
        with self._lock:
            self._reset()
            logger.info(f"Circuit breaker '{self.name}' forced CLOSED")


# CircuitBreakerOpenError now imported from sdk_exceptions


class RetryPolicy:
    """Retry policy with exponential backoff and jitter.

    Provides configurable retry behavior for transient failures.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retriable_exceptions: tuple = (Exception,),
    ):
        """Initialize retry policy.

        Args:
            max_attempts: Maximum number of attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add jitter to delays
            retriable_exceptions: Exception types that should trigger retry
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retriable_exceptions = retriable_exceptions

        logger.info(f"RetryPolicy initialized (max_attempts={max_attempts})")

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function with retry policy.

        Args:
            func: Function to call (sync or async)
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Call function (handle both sync and async)
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                if attempt > 1:
                    logger.info(f"Retry succeeded on attempt {attempt}")

                return result

            except self.retriable_exceptions as e:
                last_exception = e

                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt} failed, retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.max_attempts} attempts failed")

        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay


# Resource Limit Enforcement Components
# Note: gc and psutil are imported at the top of the file


class EnforcementPolicy(Enum):
    """Resource limit enforcement policies."""

    STRICT = "strict"  # Immediately reject when limits exceeded
    WARN = "warn"  # Log warnings but allow execution
    ADAPTIVE = "adaptive"  # Graceful degradation based on resource pressure


class DegradationStrategy(Enum):
    """Resource degradation strategies when limits are exceeded."""

    QUEUE = "queue"  # Queue requests when resources exhausted
    REJECT = "reject"  # Immediately reject when resources exhausted
    DEFER = "defer"  # Delay execution when resources exhausted


@dataclass
class ResourceCheckResult:
    """Result of resource limit check."""

    can_proceed: bool
    resource_type: str
    current_usage: float
    limit: float
    usage_percentage: float
    message: str


@dataclass
class ResourceMetrics:
    """Comprehensive resource usage metrics."""

    timestamp: datetime
    memory_usage_mb: float
    memory_usage_percent: float
    cpu_usage_percent: float
    active_connections: int
    peak_memory_mb: float
    peak_cpu_percent: float


class MemoryLimitExceededError(ResourceLimitExceededError):
    """Memory limit exceeded error."""

    def __init__(self, current_mb: float, limit_mb: float):
        super().__init__(
            f"Memory limit exceeded: {current_mb:.1f}MB > {limit_mb:.1f}MB"
        )
        self.current_mb = current_mb
        self.limit_mb = limit_mb


class ConnectionLimitExceededError(ResourceLimitExceededError):
    """Connection limit exceeded error."""

    def __init__(self, current_connections: int, max_connections: int):
        super().__init__(
            f"Connection limit exceeded: {current_connections} > {max_connections}"
        )
        self.current_connections = current_connections
        self.max_connections = max_connections


class CPULimitExceededError(ResourceLimitExceededError):
    """CPU limit exceeded error."""

    def __init__(self, current_percent: float, limit_percent: float):
        super().__init__(
            f"CPU limit exceeded: {current_percent:.1f}% > {limit_percent:.1f}%"
        )
        self.current_percent = current_percent
        self.limit_percent = limit_percent


class ResourceLimitEnforcer:
    """Comprehensive resource limit enforcement for LocalRuntime.

    Provides memory, connection, and CPU limit enforcement with configurable
    policies and graceful degradation strategies. Thread-safe for concurrent
    workflow execution.

    Features:
    - Memory limit enforcement with real-time monitoring
    - Connection pool limit enforcement
    - CPU usage monitoring and throttling
    - Configurable enforcement policies (strict, warn, adaptive)
    - Graceful degradation strategies (queue, reject, defer)
    - Thread-safe operations
    - Real-time metrics and alerting
    """

    def __init__(
        self,
        max_memory_mb: Optional[int] = None,
        max_connections: Optional[int] = None,
        max_cpu_percent: Optional[float] = None,
        enforcement_policy: Union[str, EnforcementPolicy] = EnforcementPolicy.ADAPTIVE,
        degradation_strategy: Union[
            str, DegradationStrategy
        ] = DegradationStrategy.DEFER,
        monitoring_interval: float = 1.0,
        enable_alerts: bool = True,
        memory_alert_threshold: float = 0.8,
        cpu_alert_threshold: float = 0.7,
        connection_alert_threshold: float = 0.9,
        enable_metrics_history: bool = True,
        metrics_history_size: int = 1000,
    ):
        """Initialize ResourceLimitEnforcer.

        Args:
            max_memory_mb: Maximum memory usage in MB (None = no limit)
            max_connections: Maximum concurrent connections (None = no limit)
            max_cpu_percent: Maximum CPU usage percentage (None = no limit)
            enforcement_policy: How to enforce limits (strict/warn/adaptive)
            degradation_strategy: How to handle resource exhaustion
            monitoring_interval: Resource monitoring interval in seconds
            enable_alerts: Enable resource usage alerts
            memory_alert_threshold: Memory alert threshold (0.0-1.0)
            cpu_alert_threshold: CPU alert threshold (0.0-1.0)
            connection_alert_threshold: Connection alert threshold (0.0-1.0)
            enable_metrics_history: Enable metrics history tracking
            metrics_history_size: Maximum metrics history entries
        """
        # Validate parameters
        if max_memory_mb is not None and max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be positive")
        if max_connections is not None and max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if max_cpu_percent is not None and (
            max_cpu_percent <= 0 or max_cpu_percent > 100
        ):
            raise ValueError("max_cpu_percent must be between 0 and 100")
        if monitoring_interval <= 0:
            raise ValueError("monitoring_interval must be positive")

        self.max_memory_mb = max_memory_mb
        self.max_connections = max_connections
        self.max_cpu_percent = max_cpu_percent

        # Convert string policies to enums
        if isinstance(enforcement_policy, str):
            enforcement_policy = EnforcementPolicy(enforcement_policy)
        if isinstance(degradation_strategy, str):
            degradation_strategy = DegradationStrategy(degradation_strategy)

        self.enforcement_policy = enforcement_policy
        self.degradation_strategy = degradation_strategy
        self.monitoring_interval = monitoring_interval
        self.enable_alerts = enable_alerts

        # Alert thresholds
        self.memory_alert_threshold = memory_alert_threshold
        self.cpu_alert_threshold = cpu_alert_threshold
        self.connection_alert_threshold = connection_alert_threshold

        # Metrics and history
        self.enable_metrics_history = enable_metrics_history
        self.metrics_history_size = metrics_history_size
        self.metrics_history: deque = deque(maxlen=metrics_history_size)

        # Resource tracking
        self.active_connections: Set[str] = set()
        self.connection_queue: deque = deque()
        self.peak_memory_mb = 0.0
        self.peak_cpu_percent = 0.0

        # Thread safety
        self._lock = threading.RLock()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_monitoring = False

        # Performance tracking
        self.enforcement_start_time = time.time()

        logger.info(
            f"ResourceLimitEnforcer initialized: "
            f"memory={max_memory_mb}MB, connections={max_connections}, "
            f"cpu={max_cpu_percent}%, policy={enforcement_policy.value}"
        )

    def check_memory_limits(self) -> ResourceCheckResult:
        """Check if current memory usage is within limits.

        Returns:
            ResourceCheckResult indicating if execution can proceed
        """
        if self.max_memory_mb is None:
            return ResourceCheckResult(
                can_proceed=True,
                resource_type="memory",
                current_usage=0,
                limit=0,
                usage_percentage=0,
                message="No memory limit configured",
            )

        # Get current memory usage
        # Get current process memory usage, not system-wide
        process = psutil.Process()
        memory_info = process.memory_info()
        current_mb = memory_info.rss / (1024 * 1024)  # RSS is resident set size
        usage_percentage = current_mb / self.max_memory_mb

        # Update peak tracking
        with self._lock:
            self.peak_memory_mb = max(self.peak_memory_mb, current_mb)

        # Check if over limit
        if current_mb > self.max_memory_mb:
            return ResourceCheckResult(
                can_proceed=False,
                resource_type="memory",
                current_usage=current_mb,
                limit=self.max_memory_mb,
                usage_percentage=usage_percentage,
                message=f"Memory usage {current_mb:.1f}MB exceeds limit {self.max_memory_mb}MB",
            )

        # Check alert threshold
        if self.enable_alerts and usage_percentage > self.memory_alert_threshold:
            logger.warning(
                f"Memory usage alert: {current_mb:.1f}MB ({usage_percentage:.1%}) "
                f"exceeds threshold {self.memory_alert_threshold:.1%}"
            )

        return ResourceCheckResult(
            can_proceed=True,
            resource_type="memory",
            current_usage=current_mb,
            limit=self.max_memory_mb,
            usage_percentage=usage_percentage,
            message=f"Memory usage {current_mb:.1f}MB within limit",
        )

    def check_cpu_limits(self) -> ResourceCheckResult:
        """Check if current CPU usage is within limits.

        Returns:
            ResourceCheckResult indicating if execution can proceed
        """
        if self.max_cpu_percent is None:
            return ResourceCheckResult(
                can_proceed=True,
                resource_type="cpu",
                current_usage=0,
                limit=0,
                usage_percentage=0,
                message="No CPU limit configured",
            )

        # Get current CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        usage_percentage = cpu_percent / self.max_cpu_percent

        # Update peak tracking
        with self._lock:
            self.peak_cpu_percent = max(self.peak_cpu_percent, cpu_percent)

        # Check if over limit
        if cpu_percent > self.max_cpu_percent:
            return ResourceCheckResult(
                can_proceed=False,
                resource_type="cpu",
                current_usage=cpu_percent,
                limit=self.max_cpu_percent,
                usage_percentage=usage_percentage,
                message=f"CPU usage {cpu_percent:.1f}% exceeds limit {self.max_cpu_percent:.1f}%",
            )

        # Check alert threshold
        if self.enable_alerts and usage_percentage > self.cpu_alert_threshold:
            logger.warning(
                f"CPU usage alert: {cpu_percent:.1f}% "
                f"exceeds threshold {self.cpu_alert_threshold:.1%}"
            )

        return ResourceCheckResult(
            can_proceed=True,
            resource_type="cpu",
            current_usage=cpu_percent,
            limit=self.max_cpu_percent,
            usage_percentage=usage_percentage,
            message=f"CPU usage {cpu_percent:.1f}% within limit",
        )

    def request_connection(self, connection_id: str) -> Dict[str, Any]:
        """Request a new connection within limits.

        Args:
            connection_id: Unique identifier for the connection

        Returns:
            Dict with granted status and connection info

        Raises:
            ConnectionLimitExceededError: If connection limit exceeded
        """
        with self._lock:
            current_count = len(self.active_connections)

            if self.max_connections is None:
                self.active_connections.add(connection_id)
                return {
                    "granted": True,
                    "connection_id": connection_id,
                    "active_count": len(self.active_connections),
                }

            # Check if over limit
            if current_count >= self.max_connections:
                if self.enforcement_policy == EnforcementPolicy.STRICT:
                    raise ConnectionLimitExceededError(
                        current_count, self.max_connections
                    )
                elif self.enforcement_policy == EnforcementPolicy.WARN:
                    logger.warning(
                        f"Connection limit warning: {current_count} >= {self.max_connections}"
                    )
                    self.active_connections.add(connection_id)
                    return {
                        "granted": True,
                        "connection_id": connection_id,
                        "active_count": len(self.active_connections),
                        "warning": "Connection limit exceeded but allowed by policy",
                    }
                elif self.enforcement_policy == EnforcementPolicy.ADAPTIVE:
                    # Handle based on degradation strategy
                    if self.degradation_strategy == DegradationStrategy.QUEUE:
                        self.connection_queue.append(connection_id)
                        return {
                            "granted": False,
                            "connection_id": connection_id,
                            "queued": True,
                            "queue_position": len(self.connection_queue),
                        }
                    elif self.degradation_strategy == DegradationStrategy.REJECT:
                        raise ConnectionLimitExceededError(
                            current_count, self.max_connections
                        )
                    elif self.degradation_strategy == DegradationStrategy.DEFER:
                        # Return deferred status - caller should retry later
                        return {
                            "granted": False,
                            "connection_id": connection_id,
                            "deferred": True,
                            "retry_after": self.monitoring_interval,
                        }

            # Check alert threshold
            usage_percentage = current_count / self.max_connections
            if (
                self.enable_alerts
                and usage_percentage > self.connection_alert_threshold
            ):
                logger.warning(
                    f"Connection usage alert: {current_count}/{self.max_connections} "
                    f"({usage_percentage:.1%}) exceeds threshold {self.connection_alert_threshold:.1%}"
                )

            # Grant connection
            self.active_connections.add(connection_id)
            return {
                "granted": True,
                "connection_id": connection_id,
                "active_count": len(self.active_connections),
            }

    def release_connection(self, connection_id: str) -> None:
        """Release a connection and process any queued requests.

        Args:
            connection_id: Connection to release
        """
        with self._lock:
            if connection_id in self.active_connections:
                self.active_connections.remove(connection_id)

                # Process queued connections if using queue strategy
                if (
                    self.connection_queue
                    and self.degradation_strategy == DegradationStrategy.QUEUE
                ):
                    next_connection_id = self.connection_queue.popleft()
                    self.active_connections.add(next_connection_id)
                    logger.info(f"Processed queued connection: {next_connection_id}")

    def get_active_connection_count(self) -> int:
        """Get current active connection count.

        Returns:
            Number of active connections
        """
        with self._lock:
            return len(self.active_connections)

    def check_all_limits(self) -> Dict[str, ResourceCheckResult]:
        """Check all configured resource limits.

        Returns:
            Dict mapping resource types to check results
        """
        results = {}

        # Check memory limits
        results["memory"] = self.check_memory_limits()

        # Check CPU limits
        results["cpu"] = self.check_cpu_limits()

        # Check connection limits
        with self._lock:
            current_connections = len(self.active_connections)

        if self.max_connections is not None:
            usage_percentage = current_connections / self.max_connections
            can_proceed = current_connections < self.max_connections

            if not can_proceed and self.enforcement_policy == EnforcementPolicy.WARN:
                can_proceed = True

            results["connections"] = ResourceCheckResult(
                can_proceed=can_proceed,
                resource_type="connections",
                current_usage=current_connections,
                limit=self.max_connections,
                usage_percentage=usage_percentage,
                message=f"Active connections: {current_connections}/{self.max_connections}",
            )
        else:
            results["connections"] = ResourceCheckResult(
                can_proceed=True,
                resource_type="connections",
                current_usage=current_connections,
                limit=0,
                usage_percentage=0,
                message="No connection limit configured",
            )

        return results

    def enforce_memory_limits(self) -> None:
        """Enforce memory limits based on policy.

        Raises:
            MemoryLimitExceededError: If memory limit exceeded and policy is strict
        """
        result = self.check_memory_limits()

        if not result.can_proceed:
            if self.enforcement_policy == EnforcementPolicy.STRICT:
                raise MemoryLimitExceededError(result.current_usage, result.limit)
            elif self.enforcement_policy == EnforcementPolicy.WARN:
                logger.warning(f"Memory limit exceeded: {result.message}")
            elif self.enforcement_policy == EnforcementPolicy.ADAPTIVE:
                # Trigger garbage collection to try to free memory
                logger.warning(
                    f"Memory limit exceeded, triggering garbage collection: {result.message}"
                )
                gc.collect()

                # Re-check after GC
                recheck_result = self.check_memory_limits()
                if not recheck_result.can_proceed:
                    if self.degradation_strategy == DegradationStrategy.REJECT:
                        raise MemoryLimitExceededError(
                            recheck_result.current_usage, recheck_result.limit
                        )
                    else:
                        logger.warning(
                            f"Memory limit still exceeded after GC: {recheck_result.message}"
                        )

    def enforce_cpu_limits(self) -> None:
        """Enforce CPU limits based on policy.

        Raises:
            CPULimitExceededError: If CPU limit exceeded and policy is strict
        """
        result = self.check_cpu_limits()

        if not result.can_proceed:
            if self.enforcement_policy == EnforcementPolicy.STRICT:
                raise CPULimitExceededError(result.current_usage, result.limit)
            elif self.enforcement_policy == EnforcementPolicy.WARN:
                logger.warning(f"CPU limit exceeded: {result.message}")
            elif self.enforcement_policy == EnforcementPolicy.ADAPTIVE:
                # Adaptive CPU throttling - introduce delays
                throttle_delay = min(1.0, (result.usage_percentage - 1.0) * 2.0)
                if throttle_delay > 0:
                    logger.warning(f"CPU throttling: sleeping {throttle_delay:.2f}s")
                    time.sleep(throttle_delay)

    def get_resource_metrics(self) -> Dict[str, Any]:
        """Get current resource usage metrics.

        Returns:
            Dict containing comprehensive resource metrics
        """
        # Get current process metrics, not system-wide
        process = psutil.Process()
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent()

        with self._lock:
            current_memory_mb = memory_info.rss / (1024 * 1024)
            memory_usage_percent = (
                (current_memory_mb / self.max_memory_mb * 100)
                if self.max_memory_mb
                else 0
            )

            metrics = {
                "timestamp": datetime.now(UTC),
                "memory_usage_mb": current_memory_mb,
                "memory_usage_percent": memory_usage_percent,
                "cpu_usage_percent": cpu_percent,
                "active_connections": len(self.active_connections),
                "peak_memory_mb": self.peak_memory_mb,
                "peak_cpu_percent": self.peak_cpu_percent,
                "max_memory_mb": self.max_memory_mb,
                "max_connections": self.max_connections,
                "max_cpu_percent": self.max_cpu_percent,
                "enforcement_policy": self.enforcement_policy.value,
                "degradation_strategy": self.degradation_strategy.value,
                "uptime_seconds": time.time() - self.enforcement_start_time,
            }

            # Add to history if enabled
            if self.enable_metrics_history:
                self.metrics_history.append(
                    ResourceMetrics(
                        timestamp=metrics["timestamp"],
                        memory_usage_mb=metrics["memory_usage_mb"],
                        memory_usage_percent=metrics["memory_usage_percent"],
                        cpu_usage_percent=metrics["cpu_usage_percent"],
                        active_connections=metrics["active_connections"],
                        peak_memory_mb=metrics["peak_memory_mb"],
                        peak_cpu_percent=metrics["peak_cpu_percent"],
                    )
                )

        return metrics

    def get_metrics_history(
        self, duration_seconds: Optional[int] = None
    ) -> List[ResourceMetrics]:
        """Get resource metrics history.

        Args:
            duration_seconds: Only return metrics from last N seconds (None = all)

        Returns:
            List of ResourceMetrics from history
        """
        if not self.enable_metrics_history:
            return []

        with self._lock:
            if duration_seconds is None:
                return list(self.metrics_history)

            # Filter by duration
            cutoff_time = datetime.now(UTC) - timedelta(seconds=duration_seconds)
            return [
                metrics
                for metrics in self.metrics_history
                if metrics.timestamp >= cutoff_time
            ]

    async def start_monitoring(self) -> None:
        """Start asynchronous resource monitoring."""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Resource monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop asynchronous resource monitoring."""
        if not self._is_monitoring:
            return

        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Resource monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Internal monitoring loop."""
        while self._is_monitoring:
            try:
                # Collect metrics
                self.get_resource_metrics()

                # Check for limit violations
                results = self.check_all_limits()

                # Log warnings for violations
                for resource_type, result in results.items():
                    if not result.can_proceed and self.enable_alerts:
                        logger.warning(f"Resource limit violation: {result.message}")

                await asyncio.sleep(self.monitoring_interval)

            except Exception as e:
                logger.error(f"Error in resource monitoring loop: {e}")
                await asyncio.sleep(self.monitoring_interval)


# Comprehensive Retry Policy Engine Implementation


class RetryPolicyMode(Enum):
    """Retry policy operation modes."""

    STRICT = "strict"  # Fail fast on non-retriable exceptions
    PERMISSIVE = "permissive"  # Allow retries for more exception types
    ADAPTIVE = "adaptive"  # Learn and adapt retry behavior
    CIRCUIT_AWARE = "circuit_aware"  # Coordinate with circuit breakers


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""

    timestamp: datetime
    exception_type: Type[Exception]
    attempt_number: int
    delay_used: float
    success: bool
    execution_time: float
    error_message: str = ""


@dataclass
class RetryResult:
    """Result of retry policy execution."""

    success: bool
    value: Any = None
    total_attempts: int = 0
    total_time: float = 0.0
    final_exception: Optional[Exception] = None
    attempts: List[RetryAttempt] = field(default_factory=list)


class RetryStrategy(ABC):
    """Abstract base class for retry strategies."""

    def __init__(self, name: str, max_attempts: int = 3):
        """Initialize retry strategy.

        Args:
            name: Strategy name for identification
            max_attempts: Maximum number of retry attempts
        """
        self.name = name
        self.max_attempts = max_attempts

    @abstractmethod
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        pass

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if the operation should be retried.

        Args:
            exception: Exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        # Default implementation - retry for most exceptions except system ones
        non_retriable = (KeyboardInterrupt, SystemExit, SystemError)
        return not isinstance(exception, non_retriable)

    def get_config(self) -> Dict[str, Any]:
        """Get strategy configuration for serialization.

        Returns:
            Configuration dictionary
        """
        return {"strategy_type": self.name, "max_attempts": self.max_attempts}


class ExponentialBackoffStrategy(RetryStrategy):
    """Exponential backoff retry strategy with jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize exponential backoff strategy.

        Args:
            max_attempts: Maximum number of attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            multiplier: Exponential multiplier
            jitter: Whether to add jitter to delays
        """
        super().__init__("exponential_backoff", max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with optional jitter."""
        delay = self.base_delay * (self.multiplier ** (attempt - 1))
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay

    def get_config(self) -> Dict[str, Any]:
        """Get exponential backoff configuration."""
        config = super().get_config()
        config.update(
            {
                "base_delay": self.base_delay,
                "max_delay": self.max_delay,
                "multiplier": self.multiplier,
                "jitter": self.jitter,
            }
        )
        return config


class LinearBackoffStrategy(RetryStrategy):
    """Linear backoff retry strategy with optional jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        increment: float = 1.0,
        jitter: bool = True,
    ):
        """Initialize linear backoff strategy.

        Args:
            max_attempts: Maximum number of attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            increment: Linear increment per attempt
            jitter: Whether to add jitter to delays
        """
        super().__init__("linear_backoff", max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.increment = increment
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate linear backoff delay with optional jitter."""
        delay = self.base_delay + ((attempt - 1) * self.increment)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay

    def get_config(self) -> Dict[str, Any]:
        """Get linear backoff configuration."""
        config = super().get_config()
        config.update(
            {
                "base_delay": self.base_delay,
                "max_delay": self.max_delay,
                "increment": self.increment,
                "jitter": self.jitter,
            }
        )
        return config


class FixedDelayStrategy(RetryStrategy):
    """Fixed delay retry strategy with optional jitter."""

    def __init__(self, max_attempts: int = 3, delay: float = 1.0, jitter: bool = True):
        """Initialize fixed delay strategy.

        Args:
            max_attempts: Maximum number of attempts
            delay: Fixed delay in seconds
            jitter: Whether to add jitter to delays
        """
        super().__init__("fixed_delay", max_attempts)
        self.delay = delay
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate fixed delay with optional jitter."""
        delay = self.delay

        if self.jitter:
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount

        return delay

    def get_config(self) -> Dict[str, Any]:
        """Get fixed delay configuration."""
        config = super().get_config()
        config.update({"delay": self.delay, "jitter": self.jitter})
        return config


class AdaptiveRetryStrategy(RetryStrategy):
    """Adaptive retry strategy that learns from historical success/failure patterns."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        min_delay: float = 0.1,
        max_delay: float = 30.0,
        learning_rate: float = 0.1,
        history_size: int = 1000,
    ):
        """Initialize adaptive retry strategy.

        Args:
            max_attempts: Maximum number of attempts
            initial_delay: Initial delay for new exception types
            min_delay: Minimum delay bound
            max_delay: Maximum delay bound
            learning_rate: How quickly to adapt (0.0-1.0)
            history_size: Maximum number of attempts to remember
        """
        super().__init__("adaptive_retry", max_attempts)
        self.initial_delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.learning_rate = learning_rate
        self.history_size = history_size

        # Learning data structures
        self.attempt_history: deque = deque(maxlen=history_size)
        self.exception_delays: Dict[Type[Exception], float] = {}
        self.success_rates: Dict[Type[Exception], Tuple[int, int]] = defaultdict(
            lambda: (0, 0)
        )

        # Thread safety for learning data
        self._learning_lock = threading.RLock()

    def calculate_delay(
        self, attempt: int, exception_type: Type[Exception] = Exception
    ) -> float:
        """Calculate adaptive delay based on learned patterns."""
        with self._learning_lock:
            if exception_type in self.exception_delays:
                base_delay = self.exception_delays[exception_type]
            else:
                base_delay = self.initial_delay

            # Apply attempt multiplier with learned adjustments
            delay = base_delay * (1.2 ** (attempt - 1))
            return max(self.min_delay, min(delay, self.max_delay))

    def get_recommended_delay(
        self, exception_type: Type[Exception], attempt: int
    ) -> float:
        """Get recommended delay for specific exception type and attempt."""
        return self.calculate_delay(attempt, exception_type)

    def record_attempt_result(
        self,
        exception_type: Type[Exception],
        attempt: int,
        delay_used: float,
        success: bool,
        execution_time: float = 0.0,
    ) -> None:
        """Record the result of an attempt for learning.

        Args:
            exception_type: Type of exception that occurred
            attempt: Attempt number
            delay_used: Delay that was used
            success: Whether the attempt succeeded
            execution_time: How long the operation took
        """
        with self._learning_lock:
            # Record in history
            self.attempt_history.append(
                {
                    "exception_type": exception_type,
                    "attempt": attempt,
                    "delay_used": delay_used,
                    "success": success,
                    "execution_time": execution_time,
                    "timestamp": datetime.now(UTC),
                }
            )

            # Update success rates
            successes, failures = self.success_rates[exception_type]
            if success:
                successes += 1
            else:
                failures += 1
            self.success_rates[exception_type] = (successes, failures)

            # Adapt delay based on result
            current_delay = self.exception_delays.get(
                exception_type, self.initial_delay
            )

            if success:
                # Successful retry - reduce delay slightly
                new_delay = current_delay * (1.0 - self.learning_rate * 0.5)
            else:
                # Failed retry - increase delay
                new_delay = current_delay * (1.0 + self.learning_rate)

            # Apply bounds
            new_delay = max(self.min_delay, min(new_delay, self.max_delay))
            self.exception_delays[exception_type] = new_delay

            logger.debug(
                f"Adaptive retry learned: {exception_type.__name__} delay "
                f"{current_delay:.2f}s -> {new_delay:.2f}s (success: {success})"
            )

    def get_learning_stats(self) -> Dict[str, Any]:
        """Get statistics about learned patterns.

        Returns:
            Dictionary containing learning statistics
        """
        with self._learning_lock:
            return {
                "total_attempts": len(self.attempt_history),
                "unique_exceptions": len(self.exception_delays),
                "learned_delays": {
                    exc_type.__name__: delay
                    for exc_type, delay in self.exception_delays.items()
                },
                "success_rates": {
                    exc_type.__name__: (
                        successes / (successes + failures)
                        if (successes + failures) > 0
                        else 0.0
                    )
                    for exc_type, (successes, failures) in self.success_rates.items()
                },
            }

    def get_config(self) -> Dict[str, Any]:
        """Get adaptive strategy configuration."""
        config = super().get_config()
        config.update(
            {
                "initial_delay": self.initial_delay,
                "min_delay": self.min_delay,
                "max_delay": self.max_delay,
                "learning_rate": self.learning_rate,
                "history_size": self.history_size,
            }
        )
        return config


class ExceptionClassifier:
    """Smart exception classification for retry decisions."""

    def __init__(self):
        """Initialize exception classifier with built-in rules."""
        # Built-in retriable exceptions (network, temporary failures)
        self.retriable_exceptions: Set[Type[Exception]] = {
            ConnectionError,
            TimeoutError,
            OSError,  # Network-related OS errors
            RuntimeError,  # General runtime issues
            ValueError,  # Often temporary data issues
        }

        # Built-in non-retriable exceptions (system, user, permanent)
        self.non_retriable_exceptions: Set[Type[Exception]] = {
            KeyboardInterrupt,
            SystemExit,
            SystemError,
            MemoryError,
            RecursionError,
            SyntaxError,
            TypeError,  # Usually indicates programming errors
            AttributeError,  # Usually permanent
            ImportError,  # Usually permanent
        }

        # Pattern-based rules (regex patterns to match exception messages)
        self.retriable_patterns: List[Tuple[re.Pattern, bool]] = (
            []
        )  # (pattern, case_sensitive)
        self.non_retriable_patterns: List[Tuple[re.Pattern, bool]] = []

        # Lock for thread safety
        self._lock = threading.RLock()

        logger.info("ExceptionClassifier initialized with built-in rules")

    def is_retriable(self, exception: Exception) -> bool:
        """Determine if an exception is retriable.

        Args:
            exception: Exception to classify

        Returns:
            True if the exception is retriable, False otherwise
        """
        with self._lock:
            exception_type = type(exception)
            exception_message = str(exception)

            # Check non-retriable patterns first (higher priority)
            for pattern, case_sensitive in self.non_retriable_patterns:
                if pattern.search(exception_message):
                    logger.debug(
                        f"Exception '{exception_message}' matched non-retriable pattern"
                    )
                    return False

            # Check non-retriable exception types
            for non_retriable_type in self.non_retriable_exceptions:
                if issubclass(exception_type, non_retriable_type):
                    logger.debug(
                        f"Exception type {exception_type.__name__} is non-retriable"
                    )
                    return False

            # Check retriable patterns
            for pattern, case_sensitive in self.retriable_patterns:
                if pattern.search(exception_message):
                    logger.debug(
                        f"Exception '{exception_message}' matched retriable pattern"
                    )
                    return True

            # Check retriable exception types
            for retriable_type in self.retriable_exceptions:
                if issubclass(exception_type, retriable_type):
                    logger.debug(
                        f"Exception type {exception_type.__name__} is retriable"
                    )
                    return True

            # Default to non-retriable for unknown exceptions
            logger.debug(
                f"Exception type {exception_type.__name__} not classified, defaulting to non-retriable"
            )
            return False

    def add_retriable_exception(self, exception_type: Type[Exception]) -> None:
        """Add an exception type to retriable list.

        Args:
            exception_type: Exception type to mark as retriable
        """
        with self._lock:
            self.retriable_exceptions.add(exception_type)
            # Remove from non-retriable if present
            self.non_retriable_exceptions.discard(exception_type)

        logger.info(f"Added {exception_type.__name__} to retriable exceptions")

    def add_non_retriable_exception(self, exception_type: Type[Exception]) -> None:
        """Add an exception type to non-retriable list.

        Args:
            exception_type: Exception type to mark as non-retriable
        """
        with self._lock:
            self.non_retriable_exceptions.add(exception_type)
            # Remove from retriable if present
            self.retriable_exceptions.discard(exception_type)

        logger.info(f"Added {exception_type.__name__} to non-retriable exceptions")

    def add_retriable_pattern(self, pattern: str, case_sensitive: bool = True) -> None:
        """Add a regex pattern for retriable exceptions.

        Args:
            pattern: Regex pattern to match exception messages
            case_sensitive: Whether the pattern matching is case-sensitive
        """
        with self._lock:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled_pattern = re.compile(pattern, flags)
            self.retriable_patterns.append((compiled_pattern, case_sensitive))

        logger.info(
            f"Added retriable pattern: {pattern} (case_sensitive: {case_sensitive})"
        )

    def add_non_retriable_pattern(
        self, pattern: str, case_sensitive: bool = True
    ) -> None:
        """Add a regex pattern for non-retriable exceptions.

        Args:
            pattern: Regex pattern to match exception messages
            case_sensitive: Whether the pattern matching is case-sensitive
        """
        with self._lock:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled_pattern = re.compile(pattern, flags)
            self.non_retriable_patterns.append((compiled_pattern, case_sensitive))

        logger.info(
            f"Added non-retriable pattern: {pattern} (case_sensitive: {case_sensitive})"
        )

    def get_classification_rules(self) -> Dict[str, Any]:
        """Get current classification rules.

        Returns:
            Dictionary containing all classification rules
        """
        with self._lock:
            return {
                "retriable_exceptions": [
                    exc.__name__ for exc in self.retriable_exceptions
                ],
                "non_retriable_exceptions": [
                    exc.__name__ for exc in self.non_retriable_exceptions
                ],
                "retriable_patterns": [
                    (p.pattern, cs) for p, cs in self.retriable_patterns
                ],
                "non_retriable_patterns": [
                    (p.pattern, cs) for p, cs in self.non_retriable_patterns
                ],
            }


class RetryMetrics:
    """Comprehensive retry metrics collection and analysis."""

    def __init__(self):
        """Initialize retry metrics collector."""
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0
        self.attempt_history: List[RetryAttempt] = []

        # Performance metrics
        self.total_delay_time = 0.0
        self.total_execution_time = 0.0

        # Exception tracking
        self.exception_counts: Dict[str, int] = defaultdict(int)

        # Thread safety
        self._lock = threading.RLock()

    def record_attempt(self, attempt: RetryAttempt) -> None:
        """Record a retry attempt.

        Args:
            attempt: RetryAttempt object with attempt details
        """
        with self._lock:
            self.attempt_history.append(attempt)
            self.total_attempts += 1

            if attempt.success:
                self.total_successes += 1
            else:
                self.total_failures += 1

            self.total_delay_time += attempt.delay_used
            self.total_execution_time += attempt.execution_time
            self.exception_counts[attempt.exception_type.__name__] += 1

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_attempts == 0:
            return 0.0
        return self.total_successes / self.total_attempts

    @property
    def average_delay(self) -> float:
        """Calculate average delay between attempts."""
        if self.total_attempts == 0:
            return 0.0
        return self.total_delay_time / self.total_attempts

    @property
    def average_execution_time(self) -> float:
        """Calculate average execution time per attempt."""
        if self.total_attempts == 0:
            return 0.0
        return self.total_execution_time / self.total_attempts

    def get_exception_breakdown(self) -> Dict[str, int]:
        """Get breakdown of exceptions by type.

        Returns:
            Dictionary mapping exception names to counts
        """
        with self._lock:
            return dict(self.exception_counts)

    def get_attempt_timeline(self) -> List[Dict[str, Any]]:
        """Get chronological timeline of attempts.

        Returns:
            List of attempt dictionaries sorted by timestamp
        """
        with self._lock:
            timeline = []
            for attempt in sorted(self.attempt_history, key=lambda a: a.timestamp):
                timeline.append(
                    {
                        "timestamp": attempt.timestamp,
                        "attempt_number": attempt.attempt_number,
                        "exception_type": attempt.exception_type.__name__,
                        "delay_used": attempt.delay_used,
                        "success": attempt.success,
                        "execution_time": attempt.execution_time,
                        "error_message": attempt.error_message,
                    }
                )
            return timeline

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get comprehensive summary statistics.

        Returns:
            Dictionary containing all metrics
        """
        with self._lock:
            return {
                "total_attempts": self.total_attempts,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "success_rate": self.success_rate,
                "average_delay": self.average_delay,
                "average_execution_time": self.average_execution_time,
                "total_delay_time": self.total_delay_time,
                "total_execution_time": self.total_execution_time,
                "unique_exceptions": len(self.exception_counts),
                "most_common_exception": (
                    max(self.exception_counts.items(), key=lambda x: x[1])[0]
                    if self.exception_counts
                    else None
                ),
            }


@dataclass
class RetryAnalytics:
    """Advanced retry analytics and reporting."""

    total_retry_sessions: int = 0
    total_attempts: int = 0
    total_successes: int = 0
    average_attempts_per_session: float = 0.0
    most_common_exceptions: List[Tuple[str, int]] = field(default_factory=list)

    def __post_init__(self):
        """Initialize analytics collections."""
        self.session_data: List[Dict[str, Any]] = []
        self.exception_frequencies: Dict[str, int] = defaultdict(int)
        self.strategy_performance: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_uses": 0,
                "total_successes": 0,
                "total_attempts": 0,
                "total_time": 0.0,
                "success_rate": 0.0,
                "average_attempts": 0.0,
                "average_time": 0.0,
            }
        )
        self.time_series_data: Dict[str, List[Tuple[datetime, float]]] = defaultdict(
            list
        )
        self.enable_time_series = False
        self._lock = threading.RLock()

    def record_session(
        self,
        session_id: str,
        attempts: int,
        success: bool,
        total_time: float,
        strategy_name: str,
    ) -> None:
        """Record a retry session.

        Args:
            session_id: Unique session identifier
            attempts: Number of attempts made
            success: Whether the session ultimately succeeded
            total_time: Total time spent on retries
            strategy_name: Name of retry strategy used
        """
        with self._lock:
            self.session_data.append(
                {
                    "session_id": session_id,
                    "attempts": attempts,
                    "success": success,
                    "total_time": total_time,
                    "strategy_name": strategy_name,
                    "timestamp": datetime.now(UTC),
                }
            )

            self.total_retry_sessions += 1
            self.total_attempts += attempts
            if success:
                self.total_successes += 1

            # Update running average
            self.average_attempts_per_session = (
                self.total_attempts / self.total_retry_sessions
            )

    def record_exception(self, exception_type: Type[Exception]) -> None:
        """Record an exception occurrence.

        Args:
            exception_type: Type of exception that occurred
        """
        with self._lock:
            self.exception_frequencies[exception_type.__name__] += 1
            # Update most common exceptions (top 10)
            self.most_common_exceptions = sorted(
                self.exception_frequencies.items(), key=lambda x: x[1], reverse=True
            )[:10]

    def record_strategy_performance(
        self, strategy_name: str, attempts: int, success: bool, total_time: float
    ) -> None:
        """Record performance data for a retry strategy.

        Args:
            strategy_name: Name of the retry strategy
            attempts: Number of attempts made
            success: Whether the strategy succeeded
            total_time: Total time taken
        """
        with self._lock:
            perf = self.strategy_performance[strategy_name]
            perf["total_uses"] += 1
            perf["total_attempts"] += attempts
            perf["total_time"] += total_time

            if success:
                perf["total_successes"] += 1

            # Update calculated metrics
            perf["success_rate"] = perf["total_successes"] / perf["total_uses"]
            perf["average_attempts"] = perf["total_attempts"] / perf["total_uses"]
            perf["average_time"] = perf["total_time"] / perf["total_uses"]

    def get_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """Get performance metrics for a specific strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            Performance metrics dictionary
        """
        with self._lock:
            return dict(self.strategy_performance.get(strategy_name, {}))

    def record_time_series_point(
        self, timestamp: datetime, metric: str, value: float
    ) -> None:
        """Record a time series data point.

        Args:
            timestamp: When the data point was recorded
            metric: Name of the metric
            value: Metric value
        """
        if self.enable_time_series:
            with self._lock:
                self.time_series_data[metric].append((timestamp, value))
                # Keep only last 1000 points per metric
                if len(self.time_series_data[metric]) > 1000:
                    self.time_series_data[metric] = self.time_series_data[metric][
                        -1000:
                    ]

    def get_time_series(self, metric: str) -> List[Tuple[datetime, float]]:
        """Get time series data for a metric.

        Args:
            metric: Name of the metric

        Returns:
            List of (timestamp, value) tuples
        """
        with self._lock:
            return list(self.time_series_data.get(metric, []))

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive analytics report.

        Returns:
            Complete analytics report
        """
        with self._lock:
            report = {
                "generated_at": datetime.now(UTC),
                "total_sessions": self.total_retry_sessions,
                "total_attempts": self.total_attempts,
                "total_successes": self.total_successes,
                "success_rate": (
                    self.total_successes / self.total_retry_sessions
                    if self.total_retry_sessions > 0
                    else 0.0
                ),
                "average_attempts": self.average_attempts_per_session,
                "most_common_exceptions": self.most_common_exceptions,
                "strategy_performance": dict(self.strategy_performance),
                "recommendations": self._generate_recommendations(),
            }
            return report

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on analytics.

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Success rate recommendations
        if self.total_retry_sessions > 10:
            success_rate = self.total_successes / self.total_retry_sessions
            if success_rate < 0.5:
                recommendations.append(
                    "Low success rate detected. Consider reviewing exception handling and retry strategies."
                )
            elif success_rate > 0.95:
                recommendations.append(
                    "High success rate achieved. Current retry configuration appears optimal."
                )

        # Strategy performance recommendations
        if len(self.strategy_performance) > 1:
            best_strategy = max(
                self.strategy_performance.items(), key=lambda x: x[1]["success_rate"]
            )
            recommendations.append(
                f"Strategy '{best_strategy[0]}' shows best performance with "
                f"{best_strategy[1]['success_rate']:.1%} success rate."
            )

        # Exception pattern recommendations
        if self.most_common_exceptions:
            most_common = self.most_common_exceptions[0]
            recommendations.append(
                f"Most common exception: {most_common[0]} ({most_common[1]} occurrences). "
                f"Consider targeted handling for this exception type."
            )

        return recommendations


class RetryPolicyEngine:
    """Comprehensive retry policy engine with pluggable strategies and enterprise integration."""

    def __init__(
        self,
        default_strategy: Optional[RetryStrategy] = None,
        exception_classifier: Optional[ExceptionClassifier] = None,
        enable_analytics: bool = True,
        enable_circuit_breaker_coordination: bool = False,
        enable_resource_limit_coordination: bool = False,
        circuit_breaker: Optional["CircuitBreaker"] = None,
        resource_limit_enforcer: Optional["ResourceLimitEnforcer"] = None,
        mode: RetryPolicyMode = RetryPolicyMode.ADAPTIVE,
    ):
        """Initialize retry policy engine.

        Args:
            default_strategy: Default retry strategy to use
            exception_classifier: Exception classification system
            enable_analytics: Enable analytics and metrics collection
            enable_circuit_breaker_coordination: Coordinate with circuit breakers
            enable_resource_limit_coordination: Coordinate with resource limits
            circuit_breaker: CircuitBreaker instance for coordination
            resource_limit_enforcer: ResourceLimitEnforcer instance for coordination
            mode: Retry policy operation mode
        """
        # Initialize default strategy if not provided
        if default_strategy is None:
            default_strategy = ExponentialBackoffStrategy()

        self.default_strategy = default_strategy
        self.exception_classifier = exception_classifier or ExceptionClassifier()
        self.enable_analytics = enable_analytics
        self.enable_circuit_breaker_coordination = enable_circuit_breaker_coordination
        self.enable_resource_limit_coordination = enable_resource_limit_coordination
        self.circuit_breaker = circuit_breaker
        self.resource_limit_enforcer = resource_limit_enforcer
        self.mode = mode

        # Strategy registry
        self.strategies: Dict[str, RetryStrategy] = {
            "exponential_backoff": ExponentialBackoffStrategy(),
            "linear_backoff": LinearBackoffStrategy(),
            "fixed_delay": FixedDelayStrategy(),
            "adaptive_retry": AdaptiveRetryStrategy(),
        }

        # Exception-specific strategies
        self.exception_strategies: Dict[Type[Exception], RetryStrategy] = {}

        # Metrics and analytics
        self.metrics = RetryMetrics() if enable_analytics else None
        self.analytics = RetryAnalytics() if enable_analytics else None

        # Strategy effectiveness tracking
        self.strategy_effectiveness: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"uses": 0, "successes": 0, "total_attempts": 0, "total_time": 0.0}
        )

        # Thread safety
        self._lock = threading.RLock()

        logger.info(f"RetryPolicyEngine initialized with mode: {mode.value}")

    def register_strategy(self, name: str, strategy: RetryStrategy) -> None:
        """Register a custom retry strategy.

        Args:
            name: Strategy name for identification
            strategy: RetryStrategy instance
        """
        with self._lock:
            self.strategies[name] = strategy
        logger.info(f"Registered retry strategy: {name}")

    def register_strategy_for_exception(
        self, exception_type: Type[Exception], strategy: RetryStrategy
    ) -> None:
        """Register strategy for specific exception type.

        Args:
            exception_type: Exception type to handle
            strategy: RetryStrategy to use for this exception type
        """
        with self._lock:
            self.exception_strategies[exception_type] = strategy
        logger.info(
            f"Registered strategy for {exception_type.__name__}: {strategy.name}"
        )

    def select_strategy(
        self, strategy_name: Optional[str] = None, exception: Optional[Exception] = None
    ) -> RetryStrategy:
        """Select appropriate retry strategy.

        Args:
            strategy_name: Explicit strategy name to use
            exception: Exception that occurred (for strategy selection)

        Returns:
            Selected RetryStrategy instance
        """
        with self._lock:
            # Explicit strategy selection
            if strategy_name and strategy_name in self.strategies:
                return self.strategies[strategy_name]

            # Exception-specific strategy selection
            if exception:
                exception_type = type(exception)
                for exc_type, strategy in self.exception_strategies.items():
                    if issubclass(exception_type, exc_type):
                        return strategy

            # Default strategy
            return self.default_strategy

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        strategy_name: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> RetryResult:
        """Execute function with retry policy.

        Args:
            func: Function to execute (sync or async)
            *args: Function arguments
            strategy_name: Specific strategy to use
            timeout: Overall timeout for all attempts
            **kwargs: Function keyword arguments

        Returns:
            RetryResult with execution details
        """
        session_id = str(uuid.uuid4())
        start_time = time.time()
        attempts = []
        last_exception = None

        # Initial strategy selection (may be updated based on exceptions)
        current_strategy = self.select_strategy(strategy_name)

        logger.debug(
            f"Starting retry session {session_id} with strategy: {current_strategy.name}"
        )

        for attempt_num in range(1, current_strategy.max_attempts + 1):
            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                logger.warning(f"Retry session {session_id} timed out after {timeout}s")
                break

            # Check resource limits if enabled
            if self.enable_resource_limit_coordination and self.resource_limit_enforcer:
                try:
                    limits_check = self.resource_limit_enforcer.check_all_limits()
                    for resource_type, result in limits_check.items():
                        if not result.can_proceed:
                            logger.warning(
                                f"Resource limit prevents retry: {result.message}"
                            )
                            return RetryResult(
                                success=False,
                                total_attempts=attempt_num,
                                total_time=time.time() - start_time,
                                final_exception=ResourceLimitExceededError(
                                    result.message
                                ),
                                attempts=attempts,
                            )
                except Exception as e:
                    logger.error(f"Error checking resource limits: {e}")

            # Check circuit breaker if enabled
            if self.enable_circuit_breaker_coordination and self.circuit_breaker:
                try:
                    # Execute through circuit breaker
                    attempt_start = time.time()
                    if asyncio.iscoroutinefunction(func):
                        result = await self.circuit_breaker.call(func, *args, **kwargs)
                    else:
                        result = await self.circuit_breaker.call(func, *args, **kwargs)
                    attempt_time = time.time() - attempt_start

                    # Success
                    attempt = RetryAttempt(
                        timestamp=datetime.now(UTC),
                        exception_type=type(None),
                        attempt_number=attempt_num,
                        delay_used=0.0,
                        success=True,
                        execution_time=attempt_time,
                    )
                    attempts.append(attempt)

                    # Record metrics
                    if self.metrics:
                        self.metrics.record_attempt(attempt)

                    # Record strategy effectiveness
                    self.record_strategy_effectiveness(
                        current_strategy, attempt_num, True, time.time() - start_time
                    )

                    total_time = time.time() - start_time
                    logger.info(
                        f"Retry session {session_id} succeeded on attempt {attempt_num}"
                    )

                    return RetryResult(
                        success=True,
                        value=result,
                        total_attempts=attempt_num,
                        total_time=total_time,
                        attempts=attempts,
                    )

                except CircuitBreakerOpenError as e:
                    # Circuit breaker is open, fail immediately
                    logger.warning(
                        f"Circuit breaker open, failing retry session {session_id}"
                    )
                    return RetryResult(
                        success=False,
                        total_attempts=attempt_num,
                        total_time=time.time() - start_time,
                        final_exception=e,
                        attempts=attempts,
                    )

                except Exception as e:
                    last_exception = e
            else:
                # Execute without circuit breaker
                try:
                    attempt_start = time.time()
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    attempt_time = time.time() - attempt_start

                    # Success
                    attempt = RetryAttempt(
                        timestamp=datetime.now(UTC),
                        exception_type=type(None),
                        attempt_number=attempt_num,
                        delay_used=0.0,
                        success=True,
                        execution_time=attempt_time,
                    )
                    attempts.append(attempt)

                    # Record metrics
                    if self.metrics:
                        self.metrics.record_attempt(attempt)

                    # Record strategy effectiveness
                    self.record_strategy_effectiveness(
                        current_strategy, attempt_num, True, time.time() - start_time
                    )

                    total_time = time.time() - start_time
                    logger.info(
                        f"Retry session {session_id} succeeded on attempt {attempt_num}"
                    )

                    return RetryResult(
                        success=True,
                        value=result,
                        total_attempts=attempt_num,
                        total_time=total_time,
                        attempts=attempts,
                    )

                except Exception as e:
                    last_exception = e
                    attempt_time = time.time() - attempt_start

            # Handle exception
            if last_exception:
                # Update strategy selection based on exception
                exception_specific_strategy = self.select_strategy(
                    exception=last_exception
                )
                if exception_specific_strategy != current_strategy:
                    logger.debug(
                        f"Switching strategy from {current_strategy.name} to "
                        f"{exception_specific_strategy.name} for {type(last_exception).__name__}"
                    )
                    current_strategy = exception_specific_strategy

                # Check if exception is retriable
                if not self.exception_classifier.is_retriable(last_exception):
                    logger.info(
                        f"Non-retriable exception in session {session_id}: "
                        f"{type(last_exception).__name__}: {last_exception}"
                    )

                    # Record non-retriable attempt
                    attempt = RetryAttempt(
                        timestamp=datetime.now(UTC),
                        exception_type=type(last_exception),
                        attempt_number=attempt_num,
                        delay_used=0.0,
                        success=False,
                        execution_time=attempt_time,
                        error_message=str(last_exception),
                    )
                    attempts.append(attempt)

                    if self.metrics:
                        self.metrics.record_attempt(attempt)

                    return RetryResult(
                        success=False,
                        total_attempts=attempt_num,
                        total_time=time.time() - start_time,
                        final_exception=last_exception,
                        attempts=attempts,
                    )

                # Calculate delay for next attempt
                if attempt_num < current_strategy.max_attempts:
                    delay = current_strategy.calculate_delay(attempt_num + 1)

                    # Record failed attempt
                    attempt = RetryAttempt(
                        timestamp=datetime.now(UTC),
                        exception_type=type(last_exception),
                        attempt_number=attempt_num,
                        delay_used=delay,
                        success=False,
                        execution_time=attempt_time,
                        error_message=str(last_exception),
                    )
                    attempts.append(attempt)

                    if self.metrics:
                        self.metrics.record_attempt(attempt)

                    # Record learning data for adaptive strategies
                    if isinstance(current_strategy, AdaptiveRetryStrategy):
                        current_strategy.record_attempt_result(
                            type(last_exception),
                            attempt_num,
                            delay,
                            False,
                            attempt_time,
                        )

                    logger.warning(
                        f"Attempt {attempt_num} failed in session {session_id}, "
                        f"retrying in {delay:.2f}s: {type(last_exception).__name__}: {last_exception}"
                    )

                    # Wait before retry
                    await asyncio.sleep(delay)
                else:
                    # Record final failed attempt
                    attempt = RetryAttempt(
                        timestamp=datetime.now(UTC),
                        exception_type=type(last_exception),
                        attempt_number=attempt_num,
                        delay_used=0.0,
                        success=False,
                        execution_time=attempt_time,
                        error_message=str(last_exception),
                    )
                    attempts.append(attempt)

                    if self.metrics:
                        self.metrics.record_attempt(attempt)

        # All attempts failed
        total_time = time.time() - start_time
        logger.error(
            f"Retry session {session_id} failed after {current_strategy.max_attempts} attempts "
            f"in {total_time:.2f}s"
        )

        # Record strategy effectiveness
        self.record_strategy_effectiveness(
            current_strategy, current_strategy.max_attempts, False, total_time
        )

        # Record analytics
        if self.analytics:
            self.analytics.record_session(
                session_id,
                current_strategy.max_attempts,
                False,
                total_time,
                current_strategy.name,
            )
            if last_exception:
                self.analytics.record_exception(type(last_exception))

        return RetryResult(
            success=False,
            total_attempts=current_strategy.max_attempts,
            total_time=total_time,
            final_exception=last_exception,
            attempts=attempts,
        )

    def record_strategy_effectiveness(
        self, strategy: RetryStrategy, attempts: int, success: bool, total_time: float
    ) -> None:
        """Record effectiveness data for a strategy.

        Args:
            strategy: Strategy that was used
            attempts: Number of attempts made
            success: Whether the strategy succeeded
            total_time: Total time taken
        """
        with self._lock:
            effectiveness = self.strategy_effectiveness[strategy.name]
            effectiveness["uses"] += 1
            effectiveness["total_attempts"] += attempts
            effectiveness["total_time"] += total_time

            if success:
                effectiveness["successes"] += 1

    def get_strategy_effectiveness(self) -> Dict[str, Dict[str, Any]]:
        """Get effectiveness statistics for all strategies.

        Returns:
            Dictionary mapping strategy names to effectiveness stats
        """
        with self._lock:
            result = {}
            for name, data in self.strategy_effectiveness.items():
                if data["uses"] > 0:
                    result[name] = {
                        "uses": data["uses"],
                        "success_rate": data["successes"] / data["uses"],
                        "average_attempts": data["total_attempts"] / data["uses"],
                        "average_time": data["total_time"] / data["uses"],
                    }
            return result

    def get_analytics(self) -> Optional[RetryAnalytics]:
        """Get current analytics data.

        Returns:
            RetryAnalytics instance or None if analytics disabled
        """
        return self.analytics

    def get_metrics_summary(self) -> Optional[Dict[str, Any]]:
        """Get metrics summary.

        Returns:
            Metrics summary dictionary or None if metrics disabled
        """
        if self.metrics:
            return self.metrics.get_summary_stats()
        return None

    def reset_metrics(self) -> None:
        """Reset all metrics and analytics data."""
        if self.metrics:
            self.metrics = RetryMetrics()
        if self.analytics:
            self.analytics = RetryAnalytics()
        with self._lock:
            self.strategy_effectiveness.clear()
        logger.info("Retry policy metrics reset")

    def get_configuration(self) -> Dict[str, Any]:
        """Get current retry policy configuration.

        Returns:
            Configuration dictionary
        """
        with self._lock:
            return {
                "default_strategy": self.default_strategy.get_config(),
                "mode": self.mode.value,
                "enable_analytics": self.enable_analytics,
                "enable_circuit_breaker_coordination": self.enable_circuit_breaker_coordination,
                "enable_resource_limit_coordination": self.enable_resource_limit_coordination,
                "registered_strategies": list(self.strategies.keys()),
                "exception_specific_strategies": {
                    exc_type.__name__: strategy.name
                    for exc_type, strategy in self.exception_strategies.items()
                },
                "classification_rules": self.exception_classifier.get_classification_rules(),
            }
