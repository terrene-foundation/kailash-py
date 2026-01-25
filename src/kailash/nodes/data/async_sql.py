"""Asynchronous SQL database node for the Kailash SDK.

This module provides async nodes for interacting with relational databases using SQL.
It supports PostgreSQL, MySQL, and SQLite through database-specific async libraries,
providing high-performance concurrent database operations.

Design Philosophy:
1. Async-first design for high concurrency
2. Database-agnostic interface with adapter pattern
3. Connection pooling for performance
4. Safe parameterized queries
5. Flexible result formats
6. Transaction support
7. Compatible with external repositories

Key Features:
- Non-blocking database operations
- Connection pooling with configurable limits
- Support for PostgreSQL (asyncpg), MySQL (aiomysql), SQLite (aiosqlite)
- Parameterized queries to prevent SQL injection
- Multiple fetch modes (one, all, many, iterator)
- Transaction management
- Timeout handling
- Retry logic with exponential backoff
"""

import asyncio
import inspect
import json
import logging
import os
import random
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import yaml
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

logger = logging.getLogger(__name__)

# Import optimistic locking for version control
try:
    from kailash.nodes.data.optimistic_locking import (
        ConflictResolution,
        LockStatus,
        OptimisticLockingNode,
    )

    OPTIMISTIC_LOCKING_AVAILABLE = True
except ImportError:
    OPTIMISTIC_LOCKING_AVAILABLE = False

    # Define minimal enums if not available
    class ConflictResolution:
        FAIL_FAST = "fail_fast"
        RETRY = "retry"
        MERGE = "merge"
        LAST_WRITER_WINS = "last_writer_wins"

    class LockStatus:
        SUCCESS = "success"
        VERSION_CONFLICT = "version_conflict"
        RECORD_NOT_FOUND = "record_not_found"
        RETRY_EXHAUSTED = "retry_exhausted"


class DatabaseType(Enum):
    """Supported database types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class QueryValidator:
    """Validates SQL queries for common security issues."""

    # Dangerous SQL patterns that could indicate injection attempts
    DANGEROUS_PATTERNS = [
        # Multiple statements
        r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|GRANT|REVOKE)",
        # Comments that might hide malicious code
        r"--.*$",
        r"/\*.*\*/",
        # Union-based injection
        r"\bUNION\b.*\bSELECT\b",
        # Time-based blind injection
        r"\b(SLEEP|WAITFOR|PG_SLEEP)\b",
        # Out-of-band injection
        r"\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
        # System command execution
        r"\b(XP_CMDSHELL|EXEC\s+MASTER)",
    ]

    # Patterns that should only appear in admin queries
    ADMIN_ONLY_PATTERNS = [
        r"\b(CREATE|ALTER|DROP)\s+(?:\w+\s+)*(TABLE|INDEX|VIEW|PROCEDURE|FUNCTION|TRIGGER)",
        r"\b(GRANT|REVOKE)\b",
        r"\bTRUNCATE\b",
    ]

    @classmethod
    def validate_query(cls, query: str, allow_admin: bool = False) -> None:
        """Validate a SQL query for security issues.

        Args:
            query: The SQL query to validate
            allow_admin: Whether to allow administrative commands

        Raises:
            NodeValidationError: If the query contains dangerous patterns
        """
        query_upper = query.upper()

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE | re.MULTILINE):
                raise NodeValidationError(
                    f"Query contains potentially dangerous pattern: {pattern}"
                )

        # Check for admin-only patterns if not allowed
        if not allow_admin:
            for pattern in cls.ADMIN_ONLY_PATTERNS:
                if re.search(pattern, query, re.IGNORECASE):
                    raise NodeValidationError(
                        f"Query contains administrative command that is not allowed: {pattern}"
                    )

    @classmethod
    def validate_identifier(cls, identifier: str) -> None:
        """Validate a database identifier (table/column name).

        Args:
            identifier: The identifier to validate

        Raises:
            NodeValidationError: If the identifier is invalid
        """
        # Allow alphanumeric, underscore, and dot (for schema.table)
        if not re.match(
            r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$", identifier
        ):
            raise NodeValidationError(
                f"Invalid identifier: {identifier}. "
                "Identifiers must start with letter/underscore and contain only letters, numbers, underscores."
            )

    @classmethod
    def sanitize_string_literal(cls, value: str) -> str:
        """Sanitize a string value for SQL by escaping quotes.

        Args:
            value: The string value to sanitize

        Returns:
            Escaped string safe for SQL
        """
        # This is a basic implementation - real escaping should be done by the driver
        return value.replace("'", "''").replace("\\", "\\\\")

    @classmethod
    def validate_connection_string(cls, connection_string: str) -> None:
        """Validate a database connection string.

        Args:
            connection_string: The connection string to validate

        Raises:
            NodeValidationError: If the connection string appears malicious
        """
        # Check for suspicious patterns in connection strings
        suspicious_patterns = [
            # SQL injection attempts
            r";\s*(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)",
            # Command execution attempts
            r';.*\bhost\s*=\s*[\'"]?\|',
            r';.*\bhost\s*=\s*[\'"]?`',
            r"\$\(",  # Command substitution
            r"`",  # Backticks
            # File access attempts
            r'sslcert\s*=\s*[\'"]?(/etc/passwd|/etc/shadow)',
            r'sslkey\s*=\s*[\'"]?(/etc/passwd|/etc/shadow)',
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, connection_string, re.IGNORECASE):
                raise NodeValidationError(
                    "Connection string contains suspicious pattern"
                )


class FetchMode(Enum):
    """Result fetch modes."""

    ONE = "one"  # Fetch single row
    ALL = "all"  # Fetch all rows
    MANY = "many"  # Fetch specific number of rows
    ITERATOR = "iterator"  # Return async iterator


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    # Retryable error patterns (database-specific)
    retryable_errors: list[str] = None

    def __post_init__(self):
        """Initialize default retryable errors."""
        if self.retryable_errors is None:
            self.retryable_errors = [
                # PostgreSQL
                "connection_refused",
                "connection_reset",
                "connection reset",  # Handle different cases
                "connection_aborted",
                "could not connect",
                "server closed the connection",
                "terminating connection",
                "connectionreseterror",
                "connectionrefusederror",
                "brokenpipeerror",
                # MySQL
                "lost connection to mysql server",
                "mysql server has gone away",
                "can't connect to mysql server",
                # SQLite
                "database is locked",
                "disk i/o error",
                # General
                "timeout",
                "timed out",
                "pool is closed",
                # DNS/Network errors
                "nodename nor servname provided",
                "name or service not known",
                "gaierror",
                "getaddrinfo failed",
                "temporary failure in name resolution",
            ]

    def should_retry(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        return any(pattern.lower() in error_str for pattern in self.retryable_errors)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt."""
        delay = min(
            self.initial_delay * (self.exponential_base**attempt), self.max_delay
        )

        if self.jitter:
            # Add random jitter (±25%)
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)  # Ensure non-negative


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    type: DatabaseType
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    connection_string: Optional[str] = None
    pool_size: int = 10
    max_pool_size: int = 20
    pool_timeout: float = 30.0
    command_timeout: float = 60.0

    def __post_init__(self):
        """Validate configuration."""
        if not self.connection_string:
            if self.type != DatabaseType.SQLITE:
                if not all([self.host, self.database]):
                    raise ValueError(
                        f"{self.type.value} requires host and database or connection_string"
                    )
            else:
                if not self.database:
                    raise ValueError("SQLite requires database path")


# =============================================================================
# Enterprise Connection Pool Management
# =============================================================================


@dataclass
class PoolMetrics:
    """Connection pool metrics for monitoring and analytics."""

    # Basic metrics
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    max_connections: int = 0

    # Usage metrics
    connections_created: int = 0
    connections_closed: int = 0
    connections_failed: int = 0

    # Performance metrics
    avg_query_time: float = 0.0
    total_queries: int = 0
    queries_per_second: float = 0.0

    # Health metrics
    health_check_successes: int = 0
    health_check_failures: int = 0
    last_health_check: Optional[datetime] = None

    # Pool lifecycle
    pool_created_at: Optional[datetime] = None
    pool_last_used: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "active_connections": self.active_connections,
            "idle_connections": self.idle_connections,
            "total_connections": self.total_connections,
            "max_connections": self.max_connections,
            "connections_created": self.connections_created,
            "connections_closed": self.connections_closed,
            "connections_failed": self.connections_failed,
            "avg_query_time": self.avg_query_time,
            "total_queries": self.total_queries,
            "queries_per_second": self.queries_per_second,
            "health_check_successes": self.health_check_successes,
            "health_check_failures": self.health_check_failures,
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
            "pool_created_at": (
                self.pool_created_at.isoformat() if self.pool_created_at else None
            ),
            "pool_last_used": (
                self.pool_last_used.isoformat() if self.pool_last_used else None
            ),
        }


@dataclass
class HealthCheckResult:
    """Result of a connection pool health check."""

    is_healthy: bool
    latency_ms: float
    error_message: Optional[str] = None
    checked_at: Optional[datetime] = None
    connection_count: int = 0

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now()


class CircuitBreakerState(Enum):
    """Circuit breaker states for connection management."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit breaker is open - failing fast
    HALF_OPEN = "half_open"  # Testing if service is back


class ConnectionCircuitBreaker:
    """Circuit breaker for connection pool health management."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            success_threshold: Number of successes needed to close circuit
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = threading.RLock()

    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True
            elif self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.success_count = 0
                    return True
                return False
            else:  # HALF_OPEN
                return True

    def record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.OPEN
                self.success_count = 0
            elif (
                self.state == CircuitBreakerState.CLOSED
                and self.failure_count >= self.failure_threshold
            ):
                self.state = CircuitBreakerState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True

        time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
        return time_since_failure >= self.recovery_timeout

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": (
                    self.last_failure_time.isoformat()
                    if self.last_failure_time
                    else None
                ),
            }


class EnterpriseConnectionPool:
    """Enterprise-grade connection pool with monitoring, health checks, and adaptive sizing."""

    def __init__(
        self,
        pool_id: str,
        database_config: "DatabaseConfig",
        adapter_class: type,
        min_size: int = 5,
        max_size: int = 20,
        initial_size: int = 10,
        health_check_interval: int = 30,
        enable_analytics: bool = True,
        enable_adaptive_sizing: bool = True,
    ):
        """Initialize enterprise connection pool.

        Args:
            pool_id: Unique identifier for this pool
            database_config: Database configuration
            adapter_class: Database adapter class to use
            min_size: Minimum pool size
            max_size: Maximum pool size
            initial_size: Initial pool size
            health_check_interval: Health check interval in seconds
            enable_analytics: Enable performance analytics
            enable_adaptive_sizing: Enable adaptive pool sizing
        """
        self.pool_id = pool_id
        self.database_config = database_config
        self.adapter_class = adapter_class
        self.min_size = min_size
        self.max_size = max_size
        self._shutdown = False  # Shutdown flag for background tasks
        self.initial_size = initial_size
        self.health_check_interval = health_check_interval
        # Disable analytics during tests to prevent background tasks
        import os

        in_test_mode = os.getenv(
            "PYTEST_CURRENT_TEST"
        ) is not None or "pytest" in os.getenv("_", "")
        self.enable_analytics = enable_analytics and not in_test_mode
        if in_test_mode and enable_analytics:
            logger.info(
                f"Pool '{pool_id}': Disabled analytics in test mode to prevent background task cleanup issues"
            )
        self.enable_adaptive_sizing = enable_adaptive_sizing

        # Pool state
        self._pool = None
        self._adapter = None
        self._metrics = PoolMetrics(pool_created_at=datetime.now())
        self._circuit_breaker = ConnectionCircuitBreaker()

        # Analytics and monitoring
        self._query_times = deque(maxlen=1000)  # Last 1000 query times
        self._connection_usage_history = deque(maxlen=100)  # Last 100 usage snapshots
        self._health_check_history = deque(maxlen=50)  # Last 50 health checks

        # Adaptive sizing
        self._sizing_history = deque(maxlen=20)  # Last 20 sizing decisions
        self._last_resize_time: Optional[datetime] = None

        # Thread safety
        self._lock = asyncio.Lock()
        self._metrics_lock = threading.RLock()

        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._analytics_task: Optional[asyncio.Task] = None

        logger.info(
            f"EnterpriseConnectionPool '{pool_id}' initialized with {min_size}-{max_size} connections"
        )

    async def initialize(self) -> None:
        """Initialize the connection pool."""
        async with self._lock:
            if self._adapter is None:
                self._adapter = self.adapter_class(self.database_config)
                await self._adapter.connect()
                self._pool = self._adapter._pool

                # Update metrics
                with self._metrics_lock:
                    self._metrics.pool_created_at = datetime.now()
                    self._metrics.max_connections = self.max_size

                # Start background tasks
                if self.enable_analytics:
                    self._health_check_task = asyncio.create_task(
                        self._health_check_loop()
                    )
                    self._analytics_task = asyncio.create_task(self._analytics_loop())

                logger.info(f"Pool '{self.pool_id}' initialized successfully")

    async def get_connection(self):
        """Get a connection from the pool with circuit breaker protection."""
        if not self._circuit_breaker.can_execute():
            raise ConnectionError(f"Circuit breaker is open for pool '{self.pool_id}'")

        try:
            if self._pool is None:
                await self.initialize()

            connection = await self._get_pool_connection()
            self._circuit_breaker.record_success()

            # Update metrics
            with self._metrics_lock:
                self._metrics.pool_last_used = datetime.now()

            return connection

        except Exception as e:
            self._circuit_breaker.record_failure()
            with self._metrics_lock:
                self._metrics.connections_failed += 1
            logger.error(f"Failed to get connection from pool '{self.pool_id}': {e}")
            raise

    async def _get_pool_connection(self):
        """Get connection from the underlying pool (adapter-specific)."""
        if hasattr(self._pool, "acquire"):
            # asyncpg style pool
            return self._pool.acquire()
        elif hasattr(self._pool, "get_connection"):
            # aiomysql style pool
            return self._pool.get_connection()
        else:
            # Direct adapter access for SQLite
            return self._adapter._get_connection()

    async def execute_query(
        self, query: str, params: Optional[Union[tuple, dict]] = None, **kwargs
    ) -> Any:
        """Execute query with performance tracking."""
        start_time = time.time()

        try:
            result = await self._adapter.execute(query, params, **kwargs)

            # Record performance metrics
            execution_time = time.time() - start_time
            self._record_query_metrics(execution_time, success=True)

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            self._record_query_metrics(execution_time, success=False)
            raise

    def _record_query_metrics(self, execution_time: float, success: bool) -> None:
        """Record query performance metrics."""
        if not self.enable_analytics:
            return

        with self._metrics_lock:
            self._metrics.total_queries += 1
            self._query_times.append(execution_time)

            # Calculate rolling average
            if self._query_times:
                self._metrics.avg_query_time = sum(self._query_times) / len(
                    self._query_times
                )

            # Update QPS (simple approximation)
            now = datetime.now()
            recent_queries = [t for t in self._query_times if t is not None]
            if len(recent_queries) > 1:
                time_span = 60  # 1 minute window
                self._metrics.queries_per_second = min(
                    len(recent_queries) / time_span, len(recent_queries)
                )

    async def health_check(self) -> HealthCheckResult:
        """Perform comprehensive health check."""
        start_time = time.time()

        try:
            if self._adapter is None:
                return HealthCheckResult(
                    is_healthy=False, latency_ms=0, error_message="Pool not initialized"
                )

            # Perform simple query
            # Note: Pool-level command_timeout already provides timeout protection
            # No need for explicit timeout parameter here
            await self.execute_query("SELECT 1")

            latency = (time.time() - start_time) * 1000

            result = HealthCheckResult(
                is_healthy=True,
                latency_ms=latency,
                connection_count=self._get_active_connection_count(),
            )

            with self._metrics_lock:
                self._metrics.health_check_successes += 1
                self._metrics.last_health_check = datetime.now()

            return result

        except Exception as e:
            latency = (time.time() - start_time) * 1000

            result = HealthCheckResult(
                is_healthy=False, latency_ms=latency, error_message=str(e)
            )

            with self._metrics_lock:
                self._metrics.health_check_failures += 1
                self._metrics.last_health_check = datetime.now()

            return result

    def _get_active_connection_count(self) -> int:
        """Get current active connection count."""
        try:
            if hasattr(self._pool, "__len__"):
                return len(self._pool)
            elif hasattr(self._pool, "size"):
                return self._pool.size
            elif hasattr(self._pool, "_size"):
                return self._pool._size
            else:
                return 0
        except:
            return 0

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not getattr(self, "_shutdown", False):
            try:
                await asyncio.sleep(self.health_check_interval)
                if getattr(self, "_shutdown", False):
                    break
                result = await self.health_check()
                self._health_check_history.append(result)

                if not result.is_healthy:
                    logger.warning(
                        f"Health check failed for pool '{self.pool_id}': {result.error_message}"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error for pool '{self.pool_id}': {e}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def _analytics_loop(self) -> None:
        """Background analytics and adaptive sizing loop."""
        while not getattr(self, "_shutdown", False):
            try:
                await asyncio.sleep(60)  # Run every minute
                if getattr(self, "_shutdown", False):
                    break

                # Update connection usage history
                current_usage = {
                    "timestamp": datetime.now(),
                    "active_connections": self._get_active_connection_count(),
                    "avg_query_time": self._metrics.avg_query_time,
                    "queries_per_second": self._metrics.queries_per_second,
                }
                self._connection_usage_history.append(current_usage)

                # Perform adaptive sizing if enabled
                if self.enable_adaptive_sizing:
                    await self._consider_adaptive_resize()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Analytics loop error for pool '{self.pool_id}': {e}")

    async def _consider_adaptive_resize(self) -> None:
        """Consider resizing the pool based on usage patterns."""
        if len(self._connection_usage_history) < 5:
            return  # Not enough data

        # Prevent frequent resizing
        if (
            self._last_resize_time
            and (datetime.now() - self._last_resize_time).total_seconds() < 300
        ):  # 5 minutes
            return

        recent_usage = list(self._connection_usage_history)[-5:]  # Last 5 minutes
        avg_connections = sum(u["active_connections"] for u in recent_usage) / len(
            recent_usage
        )
        avg_qps = sum(u["queries_per_second"] for u in recent_usage) / len(recent_usage)

        current_size = self._get_active_connection_count()
        new_size = current_size

        # Scale up conditions
        if (
            avg_connections > current_size * 0.8  # High utilization
            and avg_qps > 10  # High query rate
            and current_size < self.max_size
        ):
            new_size = min(current_size + 2, self.max_size)

        # Scale down conditions
        elif (
            avg_connections < current_size * 0.3  # Low utilization
            and avg_qps < 2  # Low query rate
            and current_size > self.min_size
        ):
            new_size = max(current_size - 1, self.min_size)

        if new_size != current_size:
            logger.info(
                f"Adaptive sizing: Pool '{self.pool_id}' {current_size} -> {new_size} connections"
            )
            # Note: Actual resizing implementation depends on the underlying pool type
            # This would need to be implemented per adapter
            self._last_resize_time = datetime.now()

            self._sizing_history.append(
                {
                    "timestamp": datetime.now(),
                    "old_size": current_size,
                    "new_size": new_size,
                    "trigger_avg_connections": avg_connections,
                    "trigger_avg_qps": avg_qps,
                }
            )

    def get_metrics(self) -> PoolMetrics:
        """Get current pool metrics."""
        with self._metrics_lock:
            # Update real-time metrics
            self._metrics.active_connections = self._get_active_connection_count()
            self._metrics.total_connections = self._metrics.active_connections
            return self._metrics

    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get comprehensive analytics summary."""
        metrics = self.get_metrics()

        return {
            "pool_id": self.pool_id,
            "pool_config": {
                "min_size": self.min_size,
                "max_size": self.max_size,
                "current_size": self._get_active_connection_count(),
            },
            "metrics": metrics.to_dict(),
            "circuit_breaker": self._circuit_breaker.get_state(),
            "recent_health_checks": [
                {
                    "is_healthy": hc.is_healthy,
                    "latency_ms": hc.latency_ms,
                    "checked_at": hc.checked_at.isoformat() if hc.checked_at else None,
                    "error": hc.error_message,
                }
                for hc in list(self._health_check_history)[-5:]  # Last 5 checks
            ],
            "usage_history": [
                {
                    "timestamp": usage["timestamp"].isoformat(),
                    "active_connections": usage["active_connections"],
                    "avg_query_time": usage["avg_query_time"],
                    "queries_per_second": usage["queries_per_second"],
                }
                for usage in list(self._connection_usage_history)[
                    -10:
                ]  # Last 10 snapshots
            ],
            "sizing_history": [
                {
                    "timestamp": sizing["timestamp"].isoformat(),
                    "old_size": sizing["old_size"],
                    "new_size": sizing["new_size"],
                    "trigger_avg_connections": sizing["trigger_avg_connections"],
                    "trigger_avg_qps": sizing["trigger_avg_qps"],
                }
                for sizing in list(self._sizing_history)[
                    -5:
                ]  # Last 5 resize operations
            ],
        }

    async def close(self) -> None:
        """Close the connection pool and cleanup resources."""
        # Set shutdown flag
        self._shutdown = True

        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._analytics_task:
            self._analytics_task.cancel()
            try:
                await self._analytics_task
            except asyncio.CancelledError:
                pass

        # Close adapter and pool
        if self._adapter:
            await self._adapter.disconnect()
            self._adapter = None

        self._pool = None
        logger.info(f"Pool '{self.pool_id}' closed successfully")


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None

    def _convert_row(self, row: dict) -> dict:
        """Convert database-specific types to JSON-serializable types."""
        converted = {}
        for key, value in row.items():
            converted[key] = self._serialize_value(value)
        return converted

    def _serialize_value(self, value: Any) -> Any:
        """Convert database-specific types to JSON-serializable types."""
        if value is None:
            return None
        elif isinstance(value, bool):
            # Handle bool before int (bool is subclass of int in Python)
            return value
        elif isinstance(value, (int, float)):
            # Return numeric types as-is
            return value
        elif isinstance(value, str):
            # Return strings as-is
            return value
        elif isinstance(value, bytes):
            import base64

            result = base64.b64encode(value).decode("utf-8")
            return result
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif hasattr(value, "total_seconds"):  # timedelta
            return value.total_seconds()
        elif hasattr(value, "hex"):  # UUID
            return str(value)
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection pool."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection pool."""
        pass

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query and return results, optionally within a transaction."""
        pass

    @abstractmethod
    async def execute_many(
        self, query: str, params_list: list[Union[tuple, dict]]
    ) -> None:
        """Execute query multiple times with different parameters."""
        pass

    @abstractmethod
    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        pass

    @abstractmethod
    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        pass

    @abstractmethod
    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        pass


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL adapter using asyncpg."""

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import asyncpg
        except ImportError:
            raise NodeExecutionError(
                "asyncpg not installed. Install with: pip install asyncpg"
            )

        if self.config.connection_string:
            dsn = self.config.connection_string
        else:
            dsn = (
                f"postgresql://{self.config.user}:{self.config.password}@"
                f"{self.config.host}:{self.config.port or 5432}/{self.config.database}"
            )

        self._pool = await asyncpg.create_pool(
            dsn,
            min_size=1,
            max_size=self.config.max_pool_size,
            timeout=self.config.pool_timeout,
            command_timeout=self.config.command_timeout,
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query and return results."""

        import logging

        logger = logging.getLogger(__name__)

        # Convert dict params to positional for asyncpg
        if isinstance(params, dict):
            # Simple parameter substitution for named params
            # Fix: Use proper ordering and safe replacement to avoid collisions
            import json
            import logging

            logger = logging.getLogger(__name__)

            query_params = []
            param_names = []  # Track parameter names for type mapping

            # Keep original order for parameter values, but do replacements safely
            original_items = list(params.items())

            # Create parameter values in original order
            for key, value in original_items:
                param_names.append(key)
                # For PostgreSQL, lists should remain as lists for array operations
                # Only convert dicts to JSON strings
                if isinstance(value, dict):
                    value = json.dumps(value)
                # Fix for parameter $11 issue: Handle ambiguous integer values
                # AsyncPG has trouble with certain integer values (especially 0)
                # where it can't determine the PostgreSQL type automatically
                elif isinstance(value, int) and value == 0:
                    # Keep as int but we'll add explicit casting in the query later
                    pass
                query_params.append(value)

            # Replace parameters in the query, processing longer keys first to avoid collision
            # Sort keys by length (descending) for replacement order only
            keys_by_length = sorted(params.keys(), key=len, reverse=True)

            for key in keys_by_length:
                # Find the position of this key in the original order
                position = (
                    next(i for i, (k, v) in enumerate(original_items) if k == key) + 1
                )
                value = original_items[position - 1][1]  # Get the actual value

                # Fix for parameter $11 issue: Add explicit type casting for ambiguous values
                # Note: Check boolean first since bool is a subclass of int in Python
                if isinstance(value, bool):
                    # Cast boolean parameters to avoid type ambiguity
                    query = query.replace(f":{key}", f"${position}::boolean")
                elif isinstance(value, int):
                    # Cast integer parameters to avoid PostgreSQL type determination issues
                    query = query.replace(f":{key}", f"${position}::integer")
                else:
                    query = query.replace(f":{key}", f"${position}")

            params = query_params

            # Apply parameter type casts if provided
            if parameter_types:
                # Build a query with explicit type casts
                for i, param_name in enumerate(param_names, 1):
                    if param_name in parameter_types:
                        pg_type = parameter_types[param_name]
                        # Replace $N with $N::type in the query
                        query = query.replace(f"${i}", f"${i}::{pg_type}")

        else:
            # Parameters are not dict - they might be list/tuple

            # For positional params, apply type casts if provided
            if parameter_types and isinstance(params, (list, tuple)):
                # Build query with type casts for positional parameters
                for i, param_type in parameter_types.items():
                    if isinstance(i, int) and 0 <= i < len(params):
                        # Replace $N with $N::type
                        query = query.replace(f"${i+1}", f"${i+1}::{param_type}")

        # Ensure params is a list/tuple for asyncpg
        if params is None:
            params = []
        elif not isinstance(params, (list, tuple)):
            params = [params]

        # Execute query on appropriate connection
        if transaction:
            # Use transaction connection
            conn, tx = transaction

            # For UPDATE/DELETE queries without RETURNING, use execute() to get affected rows
            query_upper = query.upper()
            if (
                (
                    "UPDATE" in query_upper
                    or "DELETE" in query_upper
                    or "INSERT" in query_upper
                )
                and "SELECT" not in query_upper
                and "RETURNING" not in query_upper
                and fetch_mode == FetchMode.ALL
            ):
                if isinstance(params, dict):
                    result = await conn.execute(query, params)
                else:
                    result = await conn.execute(query, *params)
                # asyncpg returns a string like "UPDATE 1", extract the count
                if isinstance(result, str):
                    parts = result.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        rows_affected = int(parts[1])
                    else:
                        rows_affected = 0
                    return [{"rows_affected": rows_affected}]
                return []

            if fetch_mode == FetchMode.ONE:
                if isinstance(params, dict):
                    row = await conn.fetchrow(query, params)
                else:
                    row = await conn.fetchrow(query, *params)
                return self._convert_row(dict(row)) if row else None
            elif fetch_mode == FetchMode.ALL:
                if isinstance(params, dict):
                    rows = await conn.fetch(query, params)
                else:
                    rows = await conn.fetch(query, *params)
                return [self._convert_row(dict(row)) for row in rows]
            elif fetch_mode == FetchMode.MANY:
                if not fetch_size:
                    raise ValueError("fetch_size required for MANY mode")
                if isinstance(params, dict):
                    rows = await conn.fetch(query, params)
                else:
                    rows = await conn.fetch(query, *params)
                return [self._convert_row(dict(row)) for row in rows[:fetch_size]]
            elif fetch_mode == FetchMode.ITERATOR:
                raise NotImplementedError("Iterator mode not yet implemented")
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                # For UPDATE/DELETE queries without RETURNING, use execute() to get affected rows
                query_upper = query.upper()
                if (
                    (
                        "UPDATE" in query_upper
                        or "DELETE" in query_upper
                        or "INSERT" in query_upper
                    )
                    and "SELECT" not in query_upper
                    and "RETURNING" not in query_upper
                    and fetch_mode == FetchMode.ALL
                ):
                    if isinstance(params, dict):
                        result = await conn.execute(query, params)
                    else:
                        result = await conn.execute(query, *params)
                    # asyncpg returns a string like "UPDATE 1", extract the count
                    if isinstance(result, str):
                        parts = result.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            rows_affected = int(parts[1])
                        else:
                            rows_affected = 0
                        return [{"rows_affected": rows_affected}]
                    return []

                if fetch_mode == FetchMode.ONE:
                    if isinstance(params, dict):
                        row = await conn.fetchrow(query, params)
                    else:
                        row = await conn.fetchrow(query, *params)
                    return self._convert_row(dict(row)) if row else None
                elif fetch_mode == FetchMode.ALL:
                    if isinstance(params, dict):
                        rows = await conn.fetch(query, params)
                    else:
                        rows = await conn.fetch(query, *params)
                    return [self._convert_row(dict(row)) for row in rows]
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    if isinstance(params, dict):
                        rows = await conn.fetch(query, params)
                    else:
                        rows = await conn.fetch(query, *params)
                    return [self._convert_row(dict(row)) for row in rows[:fetch_size]]
                elif fetch_mode == FetchMode.ITERATOR:
                    raise NotImplementedError("Iterator mode not yet implemented")

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        # Convert all dict params to tuples

        converted_params = []
        query_converted = query
        for params in params_list:
            if isinstance(params, dict):
                query_params = []
                for i, (key, value) in enumerate(params.items(), 1):
                    if converted_params == []:  # Only replace on first iteration
                        query_converted = query_converted.replace(f":{key}", f"${i}")
                    # Serialize complex objects to JSON strings for PostgreSQL
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    query_params.append(value)
                converted_params.append(query_params)
            else:
                converted_params.append(params)

        if transaction:
            # Use transaction connection
            conn, tx = transaction
            await conn.executemany(query_converted, converted_params)
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                await conn.executemany(query_converted, converted_params)

    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        conn = await self._pool.acquire()
        tx = conn.transaction()
        await tx.start()
        return (conn, tx)

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        conn, tx = transaction
        await tx.commit()
        await self._pool.release(conn)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        conn, tx = transaction
        await tx.rollback()
        await self._pool.release(conn)


class MySQLAdapter(DatabaseAdapter):
    """MySQL adapter using aiomysql."""

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise NodeExecutionError(
                "aiomysql not installed. Install with: pip install aiomysql"
            )

        # Parse connection string if provided (aiomysql requires discrete params, not DSN)
        if self.config.connection_string:
            from urllib.parse import unquote, urlparse

            # Handle special characters in password before parsing
            conn_str = self.config.connection_string
            parsed = urlparse(conn_str)

            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            user = parsed.username or "root"
            password = unquote(parsed.password) if parsed.password else ""
            database = parsed.path.lstrip("/") if parsed.path else ""
        else:
            host = self.config.host
            port = self.config.port or 3306
            user = self.config.user
            password = self.config.password
            database = self.config.database

        self._pool = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=database,
            minsize=1,
            maxsize=self.config.max_pool_size,
            pool_recycle=3600,
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query and return results."""
        # Use transaction connection if provided, otherwise get from pool
        # Note: parameter_types is only used by PostgreSQL adapter
        if transaction:
            conn = transaction
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)

                # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
                query_type = query.strip().upper().split()[0] if query.strip() else ""

                if query_type in ("DELETE", "UPDATE", "INSERT"):
                    # Capture rowcount for DML operations
                    rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
                    # Use list format to match PostgreSQL adapter
                    return [{"rows_affected": rowcount}]

                if fetch_mode == FetchMode.ONE:
                    row = await cursor.fetchone()
                    if row and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return self._convert_row(dict(zip(columns, row)))
                    return None
                elif fetch_mode == FetchMode.ALL:
                    rows = await cursor.fetchall()
                    if rows and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return [
                            self._convert_row(dict(zip(columns, row))) for row in rows
                        ]
                    return []
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    rows = await cursor.fetchmany(fetch_size)
                    if rows and cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        return [
                            self._convert_row(dict(zip(columns, row))) for row in rows
                        ]
                    return []
        else:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)

                    # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
                    query_type = (
                        query.strip().upper().split()[0] if query.strip() else ""
                    )

                    if query_type in ("DELETE", "UPDATE", "INSERT"):
                        # Capture rowcount for DML operations
                        rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
                        await conn.commit()  # Commit DML operations
                        # Use list format to match PostgreSQL adapter
                        return [{"rows_affected": rowcount}]

                    if fetch_mode == FetchMode.ONE:
                        row = await cursor.fetchone()
                        if row and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return self._convert_row(dict(zip(columns, row)))
                        return None
                    elif fetch_mode == FetchMode.ALL:
                        rows = await cursor.fetchall()
                        if rows and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return [
                                self._convert_row(dict(zip(columns, row)))
                                for row in rows
                            ]
                        return []
                    elif fetch_mode == FetchMode.MANY:
                        if not fetch_size:
                            raise ValueError("fetch_size required for MANY mode")
                        rows = await cursor.fetchmany(fetch_size)
                        if rows and cursor.description:
                            columns = [desc[0] for desc in cursor.description]
                            return [
                                self._convert_row(dict(zip(columns, row)))
                                for row in rows
                            ]
                        return []

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        if transaction:
            # Use transaction connection
            async with transaction.cursor() as cursor:
                await cursor.executemany(query, params_list)
                # Don't commit here - let transaction handling do it
        else:
            # Use pool connection
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.executemany(query, params_list)
                    await conn.commit()

    async def begin_transaction(self) -> Any:
        """Begin a transaction."""
        conn = await self._pool.acquire()
        await conn.begin()
        return conn

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        await transaction.commit()
        await self._pool.release(transaction)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        await transaction.rollback()
        await self._pool.release(transaction)


class SQLiteAdapter(DatabaseAdapter):
    """SQLite adapter using aiosqlite."""

    # Class-level shared connections for memory databases to solve isolation issues
    _shared_memory_connections = {}
    _connection_locks = {}

    def __init__(self, config: DatabaseConfig):
        """Initialize SQLite adapter."""
        super().__init__(config)
        # Initialize SQLite-specific attributes
        self._db_path = config.connection_string or config.database or ":memory:"
        self._is_memory_db = self._db_path == ":memory:"
        self._connection = None
        # Transaction nesting support (for SQLite nested transaction bug fix)
        self._transaction_depth = 0
        self._savepoint_counter = 0
        # Import aiosqlite on init
        try:
            import aiosqlite

            self._aiosqlite = aiosqlite
        except ImportError:
            self._aiosqlite = None

    async def connect(self) -> None:
        """Establish connection pool."""
        try:
            import aiosqlite
        except ImportError:
            raise NodeExecutionError(
                "aiosqlite not installed. Install with: pip install aiosqlite"
            )

        # SQLite doesn't have true connection pooling
        # We'll manage connections based on database type
        self._aiosqlite = aiosqlite

        # Extract database path from connection string if database path not provided
        if self.config.database:
            self._db_path = self.config.database
        elif self.config.connection_string:
            # Parse SQLite connection string formats:
            # sqlite:///path/to/file.db (absolute path)
            # sqlite://path/to/file.db (relative path - rare)
            # file:path/to/file.db (file URI scheme)
            conn_str = self.config.connection_string
            if conn_str.startswith("sqlite:///"):
                # Absolute path: sqlite:///path/to/file.db -> /path/to/file.db
                # Special case: sqlite:///:memory: -> :memory:
                path_part = conn_str[9:]  # Remove "sqlite://" to keep the leading slash
                if path_part == "/:memory:":
                    self._db_path = ":memory:"
                else:
                    self._db_path = path_part
            elif conn_str.startswith("sqlite://"):
                # Relative path: sqlite://path/to/file.db -> path/to/file.db
                self._db_path = conn_str[9:]  # Remove "sqlite://"
            elif conn_str.startswith("file:"):
                # File URI: file:path/to/file.db -> path/to/file.db
                self._db_path = conn_str[5:]  # Remove "file:"
            else:
                # Assume the connection string IS the path
                self._db_path = conn_str
        else:
            raise NodeExecutionError(
                "SQLite requires either 'database' path or 'connection_string'"
            )

        # Set up connection sharing for memory databases to prevent isolation
        self._is_memory_db = self._db_path == ":memory:"
        if self._is_memory_db:
            import asyncio

            # All :memory: databases should share the same connection to avoid isolation
            self._memory_key = "global_memory_db"
            if self._memory_key not in self._connection_locks:
                self._connection_locks[self._memory_key] = asyncio.Lock()

    async def _get_connection(self):
        """Get a database connection, using shared connection for memory databases."""
        if self._is_memory_db:
            # Use shared connection for memory databases to prevent isolation
            async with self._connection_locks[self._memory_key]:
                if self._memory_key not in self._shared_memory_connections:
                    # Create the shared memory connection
                    conn = await self._aiosqlite.connect(self._db_path)
                    conn.row_factory = self._aiosqlite.Row
                    self._shared_memory_connections[self._memory_key] = conn
                return self._shared_memory_connections[self._memory_key]
        else:
            # For file databases, create new connections as before
            conn = await self._aiosqlite.connect(self._db_path)
            conn.row_factory = self._aiosqlite.Row
            return conn

    async def disconnect(self) -> None:
        """Close connection."""
        # For memory databases, we keep the shared connection alive
        # For file databases, connections are managed per-operation
        pass

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query and return results."""
        if transaction:
            # Handle both old API (just connection) and new API (tuple)
            # begin_transaction() returns (db, savepoint_name, depth) tuple
            if isinstance(transaction, tuple):
                db, _savepoint_name, _depth = transaction
            else:
                db = transaction
            cursor = await db.execute(query, params or [])

            # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
            query_type = query.strip().upper().split()[0] if query.strip() else ""

            if query_type in ("DELETE", "UPDATE", "INSERT"):
                # Capture rowcount for DML operations
                rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
                # Use list format to match PostgreSQL/MySQL adapters
                return [{"rows_affected": rowcount}]

            if fetch_mode == FetchMode.ONE:
                row = await cursor.fetchone()
                result = self._convert_row(dict(row)) if row else None
            elif fetch_mode == FetchMode.ALL:
                rows = await cursor.fetchall()
                result = [self._convert_row(dict(row)) for row in rows]
            elif fetch_mode == FetchMode.MANY:
                if not fetch_size:
                    raise ValueError("fetch_size required for MANY mode")
                rows = await cursor.fetchmany(fetch_size)
                result = [self._convert_row(dict(row)) for row in rows]
            else:
                result = []

            # Check if this was an INSERT and capture lastrowid for SQLite
            if query_type == "INSERT" and (
                not result or result == [] or result is None
            ):
                # For INSERT without RETURNING, capture lastrowid
                lastrowid = cursor.lastrowid if hasattr(cursor, "lastrowid") else None
                if lastrowid is not None:
                    return {"lastrowid": lastrowid}

            return result
        else:
            # Create new connection for non-transactional queries
            if self._is_memory_db:
                # Use shared connection for memory databases
                db = await self._get_connection()
                cursor = await db.execute(query, params or [])

                # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
                query_type = query.strip().upper().split()[0] if query.strip() else ""

                if query_type in ("DELETE", "UPDATE", "INSERT"):
                    # Capture rowcount for DML operations
                    rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
                    await db.commit()
                    # Use list format to match PostgreSQL/MySQL adapters
                    return [{"rows_affected": rowcount}]

                if fetch_mode == FetchMode.ONE:
                    row = await cursor.fetchone()
                    result = self._convert_row(dict(row)) if row else None
                elif fetch_mode == FetchMode.ALL:
                    rows = await cursor.fetchall()
                    result = [self._convert_row(dict(row)) for row in rows]
                elif fetch_mode == FetchMode.MANY:
                    if not fetch_size:
                        raise ValueError("fetch_size required for MANY mode")
                    rows = await cursor.fetchmany(fetch_size)
                    result = [self._convert_row(dict(row)) for row in rows]
                else:
                    result = []

                # Check if this was an INSERT and capture lastrowid for SQLite
                if query_type == "INSERT" and (not result or result == []):
                    # For INSERT without RETURNING, capture lastrowid
                    lastrowid = (
                        cursor.lastrowid if hasattr(cursor, "lastrowid") else None
                    )
                    if lastrowid is not None:
                        result = {"lastrowid": lastrowid}

                # Commit for memory databases (needed for INSERT/UPDATE/DELETE)
                await db.commit()
                return result
            else:
                # Use context manager for file databases
                async with self._aiosqlite.connect(self._db_path) as db:
                    db.row_factory = self._aiosqlite.Row
                    cursor = await db.execute(query, params or [])

                    # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
                    query_type = (
                        query.strip().upper().split()[0] if query.strip() else ""
                    )

                    if query_type in ("DELETE", "UPDATE", "INSERT"):
                        # Capture rowcount for DML operations
                        rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
                        await db.commit()
                        # Use list format to match PostgreSQL/MySQL adapters
                        return [{"rows_affected": rowcount}]

                    if fetch_mode == FetchMode.ONE:
                        row = await cursor.fetchone()
                        await db.commit()
                        return self._convert_row(dict(row)) if row else None
                    elif fetch_mode == FetchMode.ALL:
                        rows = await cursor.fetchall()
                        await db.commit()
                        return [self._convert_row(dict(row)) for row in rows]
                    elif fetch_mode == FetchMode.MANY:
                        if not fetch_size:
                            raise ValueError("fetch_size required for MANY mode")
                        rows = await cursor.fetchmany(fetch_size)
                        result = [self._convert_row(dict(row)) for row in rows]
                    else:
                        result = []

                    # Check if this was an INSERT and capture lastrowid for SQLite
                    if query_type == "INSERT" and (not result or result == []):
                        # For INSERT without RETURNING, capture lastrowid
                        lastrowid = (
                            cursor.lastrowid if hasattr(cursor, "lastrowid") else None
                        )
                        if lastrowid is not None:
                            await db.commit()  # Commit before returning
                            return {"lastrowid": lastrowid}

                    await db.commit()
                    return result

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        if transaction:
            # Handle both old API (just connection) and new API (tuple)
            # begin_transaction() returns (db, savepoint_name, depth) tuple
            if isinstance(transaction, tuple):
                db, _savepoint_name, _depth = transaction
            else:
                db = transaction
            await db.executemany(query, params_list)
            # Don't commit here - let transaction handling do it
        else:
            # Create new connection for non-transactional queries
            if self._is_memory_db:
                # Use shared connection for memory databases
                db = await self._get_connection()
                await db.executemany(query, params_list)
                await db.commit()
            else:
                # Use context manager for file databases
                async with self._aiosqlite.connect(self._db_path) as db:
                    await db.executemany(query, params_list)
                    await db.commit()

    async def begin_transaction(self) -> Any:
        """
        Begin a transaction with nested transaction support.

        SQLite Nested Transaction Fix:
        - First call: BEGIN (outer transaction)
        - Nested calls: SAVEPOINT sp_N (nested transactions)

        This prevents "cannot start a transaction within a transaction" error
        that occurs when BEGIN is called while already in a transaction.

        Returns:
            tuple: (connection, savepoint_name or None, transaction_depth)
        """
        if self._is_memory_db:
            # Use shared connection for memory databases
            db = await self._get_connection()
        else:
            # Create new connection for file databases
            db = await self._aiosqlite.connect(self._db_path)
            db.row_factory = self._aiosqlite.Row

        # Check current transaction depth
        if self._transaction_depth == 0:
            # First transaction - use BEGIN
            await db.execute("BEGIN")
            self._transaction_depth += 1
            return (db, None, self._transaction_depth)
        else:
            # Nested transaction - use SAVEPOINT
            self._savepoint_counter += 1
            savepoint_name = f"sp_{self._savepoint_counter}"
            await db.execute(f"SAVEPOINT {savepoint_name}")
            self._transaction_depth += 1
            return (db, savepoint_name, self._transaction_depth)

    async def commit_transaction(self, transaction: Any) -> None:
        """
        Commit a transaction or release a savepoint.

        SQLite Nested Transaction Fix:
        - If savepoint: RELEASE SAVEPOINT sp_N
        - If outer transaction: COMMIT

        Args:
            transaction: tuple of (connection, savepoint_name or None, depth)
        """
        # Handle both old API (just connection) and new API (tuple)
        if isinstance(transaction, tuple):
            db, savepoint_name, depth = transaction

            if savepoint_name:
                # Nested transaction - release savepoint
                await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            else:
                # Outer transaction - commit
                await db.commit()

            # Decrement transaction depth
            self._transaction_depth -= 1

            # Close connection if not memory database and depth is 0
            if not self._is_memory_db and self._transaction_depth == 0:
                await db.close()
        else:
            # Old API - just commit (backward compatibility)
            await transaction.commit()
            # Don't close shared memory connections
            if not self._is_memory_db:
                await transaction.close()

    async def rollback_transaction(self, transaction: Any) -> None:
        """
        Rollback a transaction or rollback to a savepoint.

        SQLite Nested Transaction Fix:
        - If savepoint: ROLLBACK TO SAVEPOINT sp_N
        - If outer transaction: ROLLBACK

        Args:
            transaction: tuple of (connection, savepoint_name or None, depth)
        """
        # Handle both old API (just connection) and new API (tuple)
        if isinstance(transaction, tuple):
            db, savepoint_name, depth = transaction

            if savepoint_name:
                # Nested transaction - rollback to savepoint
                await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            else:
                # Outer transaction - rollback
                await db.rollback()

            # Decrement transaction depth
            self._transaction_depth -= 1

            # Close connection if not memory database and depth is 0
            if not self._is_memory_db and self._transaction_depth == 0:
                await db.close()
        else:
            # Old API - just rollback (backward compatibility)
            await transaction.rollback()
            # Don't close shared memory connections
            if not self._is_memory_db:
                await transaction.close()


class DatabaseConfigManager:
    """Manager for database configurations from YAML files."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with configuration file path.

        Args:
            config_path: Path to YAML configuration file. If not provided,
                        looks for 'database.yaml' in current directory.
        """
        self.config_path = config_path or "database.yaml"
        self._config: Optional[dict[str, Any]] = None
        self._config_cache: dict[str, tuple[str, dict[str, Any]]] = {}

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if self._config is not None:
            return self._config

        if not os.path.exists(self.config_path):
            # No config file, return empty config
            self._config = {}
            return self._config

        try:
            with open(self.config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}
                return self._config
        except yaml.YAMLError as e:
            raise NodeValidationError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise NodeExecutionError(f"Failed to load configuration file: {e}")

    def get_database_config(self, connection_name: str) -> tuple[str, dict[str, Any]]:
        """Get database configuration by connection name.

        Args:
            connection_name: Name of the database connection from config

        Returns:
            Tuple of (connection_string, additional_config)

        Raises:
            NodeExecutionError: If connection not found
        """
        # Check cache first
        if connection_name in self._config_cache:
            return self._config_cache[connection_name]

        config = self._load_config()
        databases = config.get("databases", {})

        if connection_name in databases:
            db_config = databases[connection_name].copy()
            connection_string = db_config.pop(
                "connection_string", db_config.pop("url", None)
            )

            if not connection_string:
                raise NodeExecutionError(
                    f"No 'connection_string' or 'url' specified for database '{connection_name}'"
                )

            # Handle environment variable substitution
            connection_string = self._substitute_env_vars(connection_string)

            # Process other config values
            for key, value in db_config.items():
                if isinstance(value, str):
                    db_config[key] = self._substitute_env_vars(value)

            # Cache the result
            self._config_cache[connection_name] = (connection_string, db_config)
            return connection_string, db_config

        # Try default connection
        if "default" in databases:
            return self.get_database_config("default")

        # No configuration found
        available = list(databases.keys()) if databases else []
        raise NodeExecutionError(
            f"Database connection '{connection_name}' not found in configuration. "
            f"Available connections: {available}"
        )

    def _substitute_env_vars(self, value: str) -> str:
        """Substitute environment variables in configuration values.

        Supports:
        - ${VAR_NAME} - Full substitution
        - $VAR_NAME - Simple substitution
        """
        if not isinstance(value, str):
            return value

        # Handle ${VAR_NAME} format
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            env_value = os.getenv(env_var)
            if env_value is None:
                raise NodeExecutionError(f"Environment variable '{env_var}' not found")
            return env_value

        # Handle $VAR_NAME and ${VAR_NAME} formats in connection strings
        import re

        # Pattern to match both $VAR_NAME and ${VAR_NAME}
        pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)"

        def replace_var(match):
            # Group 1 is for ${VAR_NAME}, group 2 is for $VAR_NAME
            var_name = match.group(1) or match.group(2)
            var_value = os.getenv(var_name)
            if var_value is None:
                raise NodeExecutionError(f"Environment variable '{var_name}' not found")
            return var_value

        return re.sub(pattern, replace_var, value)

    def list_connections(self) -> list[str]:
        """List all available database connections."""
        config = self._load_config()
        databases = config.get("databases", {})
        return list(databases.keys())

    def validate_config(self) -> None:
        """Validate the configuration file."""
        config = self._load_config()
        databases = config.get("databases", {})

        for name, db_config in databases.items():
            if not isinstance(db_config, dict):
                raise NodeValidationError(
                    f"Database '{name}' configuration must be a dictionary"
                )

            # Must have connection string
            if "connection_string" not in db_config and "url" not in db_config:
                raise NodeValidationError(
                    f"Database '{name}' must have 'connection_string' or 'url'"
                )


# =============================================================================
# Production Database Adapters
# =============================================================================


class ProductionPostgreSQLAdapter(PostgreSQLAdapter):
    """Production-ready PostgreSQL adapter with enterprise features."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self._enterprise_pool: Optional[EnterpriseConnectionPool] = None
        self._pool_config = {
            "min_size": getattr(config, "min_pool_size", 5),
            "max_size": getattr(config, "max_pool_size", 20),
            "health_check_interval": getattr(config, "health_check_interval", 30),
            "enable_analytics": getattr(config, "enable_analytics", True),
            "enable_adaptive_sizing": getattr(config, "enable_adaptive_sizing", True),
        }

    async def connect(self) -> None:
        """Connect using enterprise pool."""
        if self._enterprise_pool is None:
            pool_id = f"postgresql_{hash(str(self.config.__dict__))}"
            self._enterprise_pool = EnterpriseConnectionPool(
                pool_id=pool_id,
                database_config=self.config,
                adapter_class=PostgreSQLAdapter,
                **self._pool_config,
            )
            await self._enterprise_pool.initialize()
            self._pool = self._enterprise_pool._pool

    async def execute(
        self, query: str, params: Optional[Union[tuple, dict]] = None, **kwargs
    ) -> Any:
        """Execute with enterprise monitoring."""
        if self._enterprise_pool:
            return await self._enterprise_pool.execute_query(query, params, **kwargs)
        else:
            return await super().execute(query, params, **kwargs)

    async def health_check(self) -> HealthCheckResult:
        """Perform health check."""
        if self._enterprise_pool:
            return await self._enterprise_pool.health_check()
        else:
            # Fallback basic health check
            try:
                await self.execute("SELECT 1")
                return HealthCheckResult(is_healthy=True, latency_ms=0)
            except Exception as e:
                return HealthCheckResult(
                    is_healthy=False, latency_ms=0, error_message=str(e)
                )

    def get_pool_metrics(self) -> Optional[PoolMetrics]:
        """Get pool metrics."""
        return self._enterprise_pool.get_metrics() if self._enterprise_pool else None

    def get_analytics_summary(self) -> Optional[Dict[str, Any]]:
        """Get analytics summary."""
        return (
            self._enterprise_pool.get_analytics_summary()
            if self._enterprise_pool
            else None
        )

    async def disconnect(self) -> None:
        """Disconnect enterprise pool."""
        if self._enterprise_pool:
            await self._enterprise_pool.close()
            self._enterprise_pool = None
        else:
            await super().disconnect()


class ProductionMySQLAdapter(MySQLAdapter):
    """Production-ready MySQL adapter with enterprise features."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self._enterprise_pool: Optional[EnterpriseConnectionPool] = None
        self._pool_config = {
            "min_size": getattr(config, "min_pool_size", 5),
            "max_size": getattr(config, "max_pool_size", 20),
            "health_check_interval": getattr(config, "health_check_interval", 30),
            "enable_analytics": getattr(config, "enable_analytics", True),
            "enable_adaptive_sizing": getattr(config, "enable_adaptive_sizing", True),
        }

    async def connect(self) -> None:
        """Connect using enterprise pool."""
        if self._enterprise_pool is None:
            pool_id = f"mysql_{hash(str(self.config.__dict__))}"
            self._enterprise_pool = EnterpriseConnectionPool(
                pool_id=pool_id,
                database_config=self.config,
                adapter_class=MySQLAdapter,
                **self._pool_config,
            )
            await self._enterprise_pool.initialize()
            self._pool = self._enterprise_pool._pool

    async def execute(
        self, query: str, params: Optional[Union[tuple, dict]] = None, **kwargs
    ) -> Any:
        """Execute with enterprise monitoring."""
        if self._enterprise_pool:
            return await self._enterprise_pool.execute_query(query, params, **kwargs)
        else:
            return await super().execute(query, params, **kwargs)

    async def health_check(self) -> HealthCheckResult:
        """Perform health check."""
        if self._enterprise_pool:
            return await self._enterprise_pool.health_check()
        else:
            # Fallback basic health check
            try:
                await self.execute("SELECT 1")
                return HealthCheckResult(is_healthy=True, latency_ms=0)
            except Exception as e:
                return HealthCheckResult(
                    is_healthy=False, latency_ms=0, error_message=str(e)
                )

    def get_pool_metrics(self) -> Optional[PoolMetrics]:
        """Get pool metrics."""
        return self._enterprise_pool.get_metrics() if self._enterprise_pool else None

    def get_analytics_summary(self) -> Optional[Dict[str, Any]]:
        """Get analytics summary."""
        return (
            self._enterprise_pool.get_analytics_summary()
            if self._enterprise_pool
            else None
        )

    async def disconnect(self) -> None:
        """Disconnect enterprise pool."""
        if self._enterprise_pool:
            await self._enterprise_pool.close()
            self._enterprise_pool = None
        else:
            await super().disconnect()


class ProductionSQLiteAdapter(SQLiteAdapter):
    """Production-ready SQLite adapter with enterprise features."""

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        # Initialize SQLite-specific attributes
        self._db_path = config.connection_string or config.database or ":memory:"
        self._is_memory_db = self._db_path == ":memory:"
        self._connection = None
        self._aiosqlite = None

        self._enterprise_pool: Optional[EnterpriseConnectionPool] = None
        self._pool_config = {
            "min_size": 1,  # SQLite is typically single-connection
            "max_size": getattr(config, "max_pool_size", 5),
            "health_check_interval": getattr(config, "health_check_interval", 60),
            "enable_analytics": getattr(config, "enable_analytics", True),
            "enable_adaptive_sizing": False,  # SQLite doesn't benefit from adaptive sizing
        }

    async def connect(self) -> None:
        """Connect using enterprise pool."""
        # Import aiosqlite module reference
        import aiosqlite as _aiosqlite

        self._aiosqlite = _aiosqlite

        # Initialize enterprise pool if not already done
        if self._enterprise_pool is None:
            pool_id = f"sqlite_{hash(str(self.config.__dict__))}"
            self._enterprise_pool = EnterpriseConnectionPool(
                pool_id=pool_id,
                database_config=self.config,
                adapter_class=SQLiteAdapter,
                **self._pool_config,
            )
            await self._enterprise_pool.initialize()

        # Also initialize base connection for compatibility
        await super().connect()

    async def execute(
        self, query: str, params: Optional[Union[tuple, dict]] = None, **kwargs
    ) -> Any:
        """Execute with enterprise monitoring."""
        if self._enterprise_pool:
            return await self._enterprise_pool.execute_query(query, params, **kwargs)
        else:
            return await super().execute(query, params, **kwargs)

    async def health_check(self) -> HealthCheckResult:
        """Perform health check."""
        if self._enterprise_pool:
            return await self._enterprise_pool.health_check()
        else:
            # Fallback basic health check
            try:
                await self.execute("SELECT 1")
                return HealthCheckResult(is_healthy=True, latency_ms=0)
            except Exception as e:
                return HealthCheckResult(
                    is_healthy=False, latency_ms=0, error_message=str(e)
                )

    def get_pool_metrics(self) -> Optional[PoolMetrics]:
        """Get pool metrics."""
        return self._enterprise_pool.get_metrics() if self._enterprise_pool else None

    def get_analytics_summary(self) -> Optional[Dict[str, Any]]:
        """Get analytics summary."""
        return (
            self._enterprise_pool.get_analytics_summary()
            if self._enterprise_pool
            else None
        )

    async def disconnect(self) -> None:
        """Disconnect enterprise pool."""
        if self._enterprise_pool:
            await self._enterprise_pool.close()
            self._enterprise_pool = None
        else:
            await super().disconnect()


# =============================================================================
# Runtime Integration Components
# =============================================================================


class DatabasePoolCoordinator:
    """Coordinates database pools with the LocalRuntime ConnectionPoolManager."""

    def __init__(self, runtime_pool_manager=None):
        """Initialize with reference to runtime pool manager.

        Args:
            runtime_pool_manager: Reference to LocalRuntime's ConnectionPoolManager
        """
        self.runtime_pool_manager = runtime_pool_manager
        self._active_pools: Dict[str, EnterpriseConnectionPool] = {}
        self._pool_metrics_cache: Dict[str, Dict[str, Any]] = {}
        self._coordination_lock = asyncio.Lock()

        logger.info("DatabasePoolCoordinator initialized")

    async def get_or_create_pool(
        self,
        pool_id: str,
        database_config: DatabaseConfig,
        adapter_type: str = "auto",
        pool_config: Optional[Dict[str, Any]] = None,
    ) -> EnterpriseConnectionPool:
        """Get existing pool or create new one with runtime coordination.

        Args:
            pool_id: Unique pool identifier
            database_config: Database configuration
            adapter_type: Type of adapter (postgresql, mysql, sqlite, auto)
            pool_config: Pool configuration override

        Returns:
            Enterprise connection pool instance
        """
        async with self._coordination_lock:
            if pool_id in self._active_pools:
                return self._active_pools[pool_id]

            # Determine adapter class
            if adapter_type == "auto":
                adapter_type = database_config.type.value

            adapter_classes = {
                "postgresql": ProductionPostgreSQLAdapter,
                "mysql": ProductionMySQLAdapter,
                "sqlite": ProductionSQLiteAdapter,
            }

            adapter_class = adapter_classes.get(adapter_type)
            if not adapter_class:
                raise ValueError(f"Unsupported adapter type: {adapter_type}")

            # Create enterprise pool
            enterprise_pool = EnterpriseConnectionPool(
                pool_id=pool_id,
                database_config=database_config,
                adapter_class=adapter_class,
                **(pool_config or {}),
            )

            # Initialize and register
            await enterprise_pool.initialize()
            self._active_pools[pool_id] = enterprise_pool

            # Register with runtime pool manager if available
            if self.runtime_pool_manager:
                await self._register_with_runtime(pool_id, enterprise_pool)

            logger.info(f"Created and registered enterprise pool '{pool_id}'")
            return enterprise_pool

    async def _register_with_runtime(
        self, pool_id: str, enterprise_pool: EnterpriseConnectionPool
    ):
        """Register pool with runtime pool manager."""
        try:
            if hasattr(self.runtime_pool_manager, "register_pool"):
                await self.runtime_pool_manager.register_pool(
                    pool_id,
                    {
                        "type": "enterprise_database_pool",
                        "adapter_type": enterprise_pool.database_config.type.value,
                        "pool_instance": enterprise_pool,
                        "metrics_callback": enterprise_pool.get_metrics,
                        "analytics_callback": enterprise_pool.get_analytics_summary,
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to register pool with runtime: {e}")

    async def get_pool_metrics(self, pool_id: Optional[str] = None) -> Dict[str, Any]:
        """Get metrics for specific pool or all pools.

        Args:
            pool_id: Pool ID to get metrics for, or None for all pools

        Returns:
            Pool metrics dictionary
        """
        if pool_id:
            pool = self._active_pools.get(pool_id)
            if pool:
                return {pool_id: pool.get_analytics_summary()}
            return {}

        # Return metrics for all pools
        all_metrics = {}
        for pid, pool in self._active_pools.items():
            all_metrics[pid] = pool.get_analytics_summary()

        return all_metrics

    async def health_check_all(self) -> Dict[str, HealthCheckResult]:
        """Perform health check on all active pools.

        Returns:
            Dictionary mapping pool IDs to health check results
        """
        results = {}

        for pool_id, pool in self._active_pools.items():
            try:
                result = await pool.health_check()
                results[pool_id] = result
            except Exception as e:
                results[pool_id] = HealthCheckResult(
                    is_healthy=False,
                    latency_ms=0,
                    error_message=f"Health check failed: {str(e)}",
                )

        return results

    async def cleanup_idle_pools(self, idle_timeout: int = 3600) -> int:
        """Clean up pools that have been idle for too long.

        Args:
            idle_timeout: Idle timeout in seconds

        Returns:
            Number of pools cleaned up
        """
        cleaned_up = 0
        pools_to_remove = []

        current_time = datetime.now()

        for pool_id, pool in self._active_pools.items():
            metrics = pool.get_metrics()

            if (
                metrics.pool_last_used
                and (current_time - metrics.pool_last_used).total_seconds()
                > idle_timeout
            ):
                pools_to_remove.append(pool_id)

        # Clean up identified pools
        for pool_id in pools_to_remove:
            await self.close_pool(pool_id)
            cleaned_up += 1

        if cleaned_up > 0:
            logger.info(f"Cleaned up {cleaned_up} idle database pools")

        return cleaned_up

    async def close_pool(self, pool_id: str) -> bool:
        """Close and remove a specific pool.

        Args:
            pool_id: Pool ID to close

        Returns:
            True if pool was found and closed, False otherwise
        """
        async with self._coordination_lock:
            pool = self._active_pools.get(pool_id)
            if pool:
                await pool.close()
                del self._active_pools[pool_id]

                # Unregister from runtime if needed
                if self.runtime_pool_manager and hasattr(
                    self.runtime_pool_manager, "unregister_pool"
                ):
                    try:
                        await self.runtime_pool_manager.unregister_pool(pool_id)
                    except Exception as e:
                        logger.warning(f"Failed to unregister pool from runtime: {e}")

                logger.info(f"Closed database pool '{pool_id}'")
                return True

            return False

    async def close_all_pools(self) -> int:
        """Close all active pools.

        Returns:
            Number of pools closed
        """
        pool_ids = list(self._active_pools.keys())
        closed = 0

        for pool_id in pool_ids:
            if await self.close_pool(pool_id):
                closed += 1

        return closed

    def get_active_pool_count(self) -> int:
        """Get count of active pools."""
        return len(self._active_pools)

    def get_pool_summary(self) -> Dict[str, Any]:
        """Get summary of all active pools."""
        return {
            "active_pools": self.get_active_pool_count(),
            "pool_ids": list(self._active_pools.keys()),
            "total_connections": sum(
                pool._get_active_connection_count()
                for pool in self._active_pools.values()
            ),
            "healthy_pools": sum(
                1
                for pool in self._active_pools.values()
                if pool._circuit_breaker.state == CircuitBreakerState.CLOSED
            ),
        }


@register_node()
class AsyncSQLDatabaseNode(AsyncNode):
    """Asynchronous SQL database node for high-concurrency database operations.

    This node provides non-blocking database operations with connection pooling,
    supporting PostgreSQL, MySQL, and SQLite databases. It's designed for
    high-concurrency scenarios and can handle hundreds of simultaneous connections.

    Parameters:
        database_type: Type of database (postgresql, mysql, sqlite)
        connection_string: Full database connection string (optional)
        host: Database host (required if no connection_string)
        port: Database port (optional, uses defaults)
        database: Database name
        user: Database user
        password: Database password
        query: SQL query to execute
        params: Query parameters (dict or tuple)
        fetch_mode: How to fetch results (one, all, many)
        fetch_size: Number of rows for 'many' mode
        pool_size: Initial connection pool size
        max_pool_size: Maximum connection pool size
        timeout: Query timeout in seconds
        transaction_mode: Transaction handling mode ('auto', 'manual', 'none')
        share_pool: Whether to share connection pool across instances (default: True)

    Per-Pool Locking Architecture:
        The node implements per-pool locking to eliminate lock contention bottlenecks
        in high-concurrency scenarios. Instead of a single global lock that serializes
        all pool operations, each unique pool configuration gets its own asyncio.Lock:

        - Different database pools can operate concurrently (no blocking)
        - Same pool operations are properly serialized for safety
        - Supports 300+ concurrent workflows with 100% success rate
        - 5-second timeout prevents deadlocks on lock acquisition
        - Event loop isolation prevents cross-loop lock interference
        - Memory leak prevention with automatic unused lock cleanup

    Pytest-Asyncio Compatibility:
        The node automatically detects test environments (pytest, unittest) and adapts
        pool key generation to enable pool reuse across tests. In pytest-asyncio, each
        test function gets a new event loop, which would normally create stale pool keys.
        The adaptive logic uses a constant "test" string instead of loop IDs in tests,
        allowing pools to be reused safely across sequential test functions.

        - Test mode: Pool keys use "test" instead of loop ID
        - Production mode: Pool keys include loop ID for proper isolation
        - Automatic detection via sys.modules, environment variables, and stack inspection
        - Zero configuration required - works out of the box with pytest and unittest
        - Fixes "404 context not found" errors in pytest-asyncio tests

    Transaction Modes:
        - 'auto' (default): Each query runs in its own transaction, automatically
          committed on success or rolled back on error
        - 'manual': Transactions must be explicitly managed using begin_transaction(),
          commit(), and rollback() methods
        - 'none': No transaction wrapping, queries execute immediately

    Example (auto transaction):
        >>> node = AsyncSQLDatabaseNode(
        ...     name="update_users",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass"
        ... )
        >>> # This will automatically rollback on error
        >>> await node.async_run(query="INSERT INTO users VALUES (1, 'test')")
        >>> await node.async_run(query="INVALID SQL")  # Previous insert rolled back

    Example (manual transaction):
        >>> node = AsyncSQLDatabaseNode(
        ...     name="transfer_funds",
        ...     database_type="postgresql",
        ...     host="localhost",
        ...     database="myapp",
        ...     user="dbuser",
        ...     password="dbpass",
        ...     transaction_mode="manual"
        ... )
        >>> await node.begin_transaction()
        >>> try:
        ...     await node.async_run(query="UPDATE accounts SET balance = balance - 100 WHERE id = 1")
        ...     await node.async_run(query="UPDATE accounts SET balance = balance + 100 WHERE id = 2")
        ...     await node.commit()
        >>> except Exception:
        ...     await node.rollback()
        ...     raise
    """

    # Class-level pool storage for sharing across instances
    _shared_pools: dict[str, tuple[DatabaseAdapter, int]] = {}
    _total_pools_created: int = 0  # ADR-017: Track total pools created
    _pool_lock: Optional[asyncio.Lock] = None

    # TASK-141.5: Per-pool lock registry infrastructure
    # Maps event_loop_id -> {pool_key -> lock} for per-pool locking
    _pool_locks_by_loop: dict[int, dict[str, asyncio.Lock]] = {}
    _pool_locks_mutex = threading.Lock()  # Thread safety for registry access

    # Feature flag for gradual rollout - allows reverting to legacy global locking
    _use_legacy_locking = (
        os.environ.get("KAILASH_USE_LEGACY_POOL_LOCKING", "false").lower() == "true"
    )

    # Cache for test environment detection (performance optimization)
    _test_env_cache: Optional[bool] = None
    _test_env_cache_lock = threading.Lock()

    @classmethod
    def _is_test_environment(cls) -> bool:
        """Detect if running in a test environment (cached after first call).

        This method detects pytest, unittest, or explicit test environment markers
        to enable test-specific behavior like pool key generation without loop IDs.

        Detection Methods (in order):
        1. Check sys.modules for pytest/unittest frameworks
        2. Check PYTEST_CURRENT_TEST environment variable
        3. Check KAILASH_TEST_ENV environment variable
        4. Stack inspection fallback for test framework detection

        Returns:
            bool: True if running in test environment, False in production

        Performance:
            - First call: ~1ms overhead (full detection)
            - Subsequent calls: ~0.001ms overhead (cache hit)
            - Cache is thread-safe with Lock protection
            - Prevents 1s overhead with 100+ node instantiations

        Usage:
            >>> AsyncSQLDatabaseNode._is_test_environment()
            True  # When running in pytest
            False  # When running in production

        Note:
            This is a class method to avoid requiring instance creation
            and to enable caching across all instances. The result is
            cached after first call for performance optimization.
        """
        # Check cache first (thread-safe)
        with cls._test_env_cache_lock:
            if cls._test_env_cache is not None:
                logger.debug(
                    f"Test environment detection: cache hit (result={cls._test_env_cache})"
                )
                return cls._test_env_cache

        import sys

        logger.debug("Test environment detection: cache miss, running detection logic")

        # Method 1: Check if pytest/unittest is in sys.modules (fastest)
        if "pytest" in sys.modules or "unittest" in sys.modules:
            framework = "pytest" if "pytest" in sys.modules else "unittest"
            logger.debug(f"Test environment detected via sys.modules ({framework})")
            with cls._test_env_cache_lock:
                cls._test_env_cache = True
            return True

        # Method 2: Check pytest environment variable
        if os.environ.get("PYTEST_CURRENT_TEST"):
            logger.debug(
                f"Test environment detected via PYTEST_CURRENT_TEST={os.environ.get('PYTEST_CURRENT_TEST')}"
            )
            with cls._test_env_cache_lock:
                cls._test_env_cache = True
            return True

        # Method 3: Check Kailash test environment flag
        if os.environ.get("KAILASH_TEST_ENV", "").lower() == "true":
            logger.debug("Test environment detected via KAILASH_TEST_ENV=true")
            with cls._test_env_cache_lock:
                cls._test_env_cache = True
            return True

        # Method 4: Stack inspection fallback (slower but comprehensive)
        try:
            stack = inspect.stack()
            for frame_info in stack:
                filename = frame_info.filename.lower()
                if (
                    "pytest" in filename
                    or "unittest" in filename
                    or "_pytest" in filename
                ):
                    logger.debug(
                        f"Test environment detected via stack inspection (file={frame_info.filename})"
                    )
                    with cls._test_env_cache_lock:
                        cls._test_env_cache = True
                    return True
        except Exception as e:
            # Stack inspection failed, assume production
            logger.debug(
                f"Stack inspection failed (error={type(e).__name__}), assuming production"
            )
            pass

        # No test environment detected - cache production result
        logger.debug("Production environment detected (no test markers found)")
        with cls._test_env_cache_lock:
            cls._test_env_cache = False
        return False

    @classmethod
    def _reset_test_environment_cache(cls) -> None:
        """Reset cached test environment detection result.

        This method clears the cached test environment detection result,
        forcing the next call to _is_test_environment() to re-run the
        full detection logic.

        Use cases:
            - Testing: Verify detection logic with different configurations
            - Debugging: Force re-detection if environment changes at runtime
            - Edge cases: Handle dynamic environment changes (rare)

        Usage:
            >>> AsyncSQLDatabaseNode._reset_test_environment_cache()
            >>> # Next _is_test_environment() call will re-run detection
        """
        with cls._test_env_cache_lock:
            cls._test_env_cache = None

    @classmethod
    def _get_pool_lock(cls) -> asyncio.Lock:
        """Get or create pool lock for the current event loop."""
        # Check if we have a lock and if it's for the current loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create a new lock
            cls._pool_lock = asyncio.Lock()
            return cls._pool_lock

        # Check if existing lock is for current loop
        if cls._pool_lock is None:
            cls._pool_lock = asyncio.Lock()
            cls._pool_lock_loop_id = id(loop)
        else:
            # Verify the lock is for the current event loop
            # Just create a new lock if we're in a different loop
            # The simplest approach is to store the loop ID with the lock
            if not hasattr(cls, "_pool_lock_loop_id"):
                cls._pool_lock_loop_id = id(loop)
            elif cls._pool_lock_loop_id != id(loop):
                # Different event loop, clear everything
                cls._pool_lock = asyncio.Lock()
                cls._pool_lock_loop_id = id(loop)
                cls._shared_pools.clear()

        return cls._pool_lock

    @classmethod
    def _get_pool_creation_lock(cls, pool_key: str) -> asyncio.Lock:
        """TASK-141.6: Get or create a per-pool creation lock.

        This method ensures each unique pool gets its own lock for creation
        operations, allowing different pools to be created concurrently while
        serializing creation operations for the same pool.

        Args:
            pool_key: Unique identifier for the pool

        Returns:
            asyncio.Lock: Lock specific to this pool
        """
        with cls._pool_locks_mutex:
            # Get current event loop ID, or use a default for no-loop contexts
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                # No running loop - use a special key for synchronous contexts
                loop_id = 0

            # Initialize loop registry if needed
            if loop_id not in cls._pool_locks_by_loop:
                cls._pool_locks_by_loop[loop_id] = {}

            # Get or create lock for this pool
            if pool_key not in cls._pool_locks_by_loop[loop_id]:
                cls._pool_locks_by_loop[loop_id][pool_key] = asyncio.Lock()

            return cls._pool_locks_by_loop[loop_id][pool_key]

    @classmethod
    def _acquire_pool_lock_with_timeout(cls, pool_key: str, timeout: float = 5.0):
        """TASK-141.10: Acquire per-pool lock with timeout protection.

        This is an async context manager that provides timeout protection
        while maintaining the original lock API contract.

        Args:
            pool_key: Unique identifier for the pool
            timeout: Maximum time to wait for lock acquisition

        Returns:
            Async context manager for the lock
        """

        class TimeoutLockManager:
            def __init__(self, lock: asyncio.Lock, pool_key: str, timeout: float):
                self.lock = lock
                self.pool_key = pool_key
                self.timeout = timeout
                self._acquire_start_time = None

            async def __aenter__(self):
                import logging
                import time

                logger = logging.getLogger(f"{__name__}.PoolLocking")
                self._acquire_start_time = time.time()

                logger.debug(
                    f"Attempting to acquire pool lock for '{self.pool_key}' (timeout: {self.timeout}s)"
                )

                try:
                    await asyncio.wait_for(self.lock.acquire(), timeout=self.timeout)
                    acquire_time = time.time() - self._acquire_start_time
                    logger.debug(
                        f"Successfully acquired pool lock for '{self.pool_key}' in {acquire_time:.3f}s"
                    )
                    return self
                except asyncio.TimeoutError:
                    acquire_time = time.time() - self._acquire_start_time
                    logger.warning(
                        f"TIMEOUT: Failed to acquire pool lock for '{self.pool_key}' after {acquire_time:.3f}s "
                        f"(timeout: {self.timeout}s). This may indicate deadlock or excessive lock contention."
                    )
                    raise RuntimeError(
                        f"Failed to acquire pool lock for '{self.pool_key}' within {self.timeout}s timeout. "
                        f"This may indicate deadlock or excessive lock contention."
                    )

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                import logging
                import time

                logger = logging.getLogger(f"{__name__}.PoolLocking")

                if self._acquire_start_time:
                    hold_time = time.time() - self._acquire_start_time
                    logger.debug(
                        f"Releasing pool lock for '{self.pool_key}' (held for {hold_time:.3f}s)"
                    )

                self.lock.release()
                logger.debug(f"Released pool lock for '{self.pool_key}'")

        # Check feature flag - if legacy mode is enabled, use global lock
        if cls._use_legacy_locking:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(
                f"Using legacy global locking for pool '{pool_key}' (KAILASH_USE_LEGACY_POOL_LOCKING=true)"
            )
            lock = cls._get_pool_lock()
            return TimeoutLockManager(lock, pool_key, timeout)

        # Use per-pool locking (default behavior)
        lock = cls._get_pool_creation_lock(pool_key)
        return TimeoutLockManager(lock, pool_key, timeout)

    @classmethod
    def set_legacy_locking(cls, enabled: bool) -> None:
        """Control the legacy locking behavior programmatically.

        This method allows runtime control of the locking strategy, useful for
        testing or gradual rollouts. The environment variable KAILASH_USE_LEGACY_POOL_LOCKING
        takes precedence over this setting.

        Args:
            enabled: True to use legacy global locking, False for per-pool locking
        """
        cls._use_legacy_locking = enabled
        import logging

        logger = logging.getLogger(__name__)
        mode = "legacy global locking" if enabled else "per-pool locking"
        logger.info(f"AsyncSQL locking mode set to: {mode}")

    @classmethod
    def get_locking_mode(cls) -> str:
        """Get the current locking mode.

        Returns:
            "legacy" if using global locking, "per-pool" if using per-pool locking
        """
        return "legacy" if cls._use_legacy_locking else "per-pool"

    @classmethod
    def _cleanup_unused_locks(cls) -> None:
        """TASK-141.9: Clean up unused locks to prevent memory leaks.

        This method removes lock entries for event loops that no longer exist
        and pools that are no longer in use. It's designed to be called
        periodically or when the registry grows too large.
        """
        with cls._pool_locks_mutex:
            # Get currently running event loop IDs (if any)
            current_loop_id = None
            try:
                current_loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                pass  # No running loop

            # Clean up locks for non-existent event loops
            # Keep current loop and loop ID 0 (no-loop contexts)
            loops_to_keep = {0}  # Always keep no-loop context
            if current_loop_id is not None:
                loops_to_keep.add(current_loop_id)

            # Remove entries for old event loops
            old_loops = set(cls._pool_locks_by_loop.keys()) - loops_to_keep
            for loop_id in old_loops:
                del cls._pool_locks_by_loop[loop_id]

            # For remaining loops, clean up locks for pools that no longer exist
            for loop_id in list(cls._pool_locks_by_loop.keys()):
                pool_locks = cls._pool_locks_by_loop[loop_id]
                # Keep locks for pools that still exist in _shared_pools
                # or if we have very few locks (to avoid aggressive cleanup)
                if len(pool_locks) > 10:  # Only cleanup if we have many locks
                    existing_pools = set(cls._shared_pools.keys())
                    unused_pools = set(pool_locks.keys()) - existing_pools
                    for pool_key in unused_pools:
                        del pool_locks[pool_key]

                # If loop has no locks left, remove it
                if not pool_locks and loop_id != 0 and loop_id != current_loop_id:
                    del cls._pool_locks_by_loop[loop_id]

    @classmethod
    def get_lock_metrics(cls) -> dict:
        """TASK-141.12: Get pool lock metrics for monitoring and debugging.

        Returns:
            dict: Comprehensive lock metrics including:
                - total_event_loops: Number of event loops with locks
                - total_locks: Total number of pool locks across all loops
                - locks_per_loop: Breakdown by event loop ID
                - active_pools: Number of active shared pools
                - lock_to_pool_ratio: Ratio of locks to active pools
        """
        with cls._pool_locks_mutex:
            metrics = {
                "total_event_loops": len(cls._pool_locks_by_loop),
                "total_locks": 0,
                "locks_per_loop": {},
                "active_pools": len(cls._shared_pools),
                "lock_to_pool_ratio": 0.0,
                "registry_size_bytes": 0,
            }

            # Count locks per event loop
            for loop_id, pool_locks in cls._pool_locks_by_loop.items():
                lock_count = len(pool_locks)
                metrics["total_locks"] += lock_count
                metrics["locks_per_loop"][str(loop_id)] = {
                    "lock_count": lock_count,
                    "pool_keys": list(pool_locks.keys()),
                }

            # Calculate ratio
            if metrics["active_pools"] > 0:
                metrics["lock_to_pool_ratio"] = (
                    metrics["total_locks"] / metrics["active_pools"]
                )

            # Estimate memory usage
            try:
                import sys

                metrics["registry_size_bytes"] = sys.getsizeof(cls._pool_locks_by_loop)
                for loop_dict in cls._pool_locks_by_loop.values():
                    metrics["registry_size_bytes"] += sys.getsizeof(loop_dict)
            except ImportError:
                metrics["registry_size_bytes"] = -1  # Not available

            # Add current event loop info
            try:
                current_loop_id = id(asyncio.get_running_loop())
                metrics["current_event_loop"] = str(current_loop_id)
                metrics["current_loop_locks"] = len(
                    cls._pool_locks_by_loop.get(current_loop_id, {})
                )
            except RuntimeError:
                metrics["current_event_loop"] = None
                metrics["current_loop_locks"] = 0

            return metrics

    async def _create_adapter_with_runtime_pool(self, shared_pool) -> DatabaseAdapter:
        """Create an adapter that uses a runtime-managed connection pool."""
        # Create a simple wrapper adapter that uses the shared pool
        db_type = DatabaseType(self.config["database_type"].lower())
        db_config = DatabaseConfig(
            type=db_type,
            host=self.config.get("host"),
            port=self.config.get("port"),
            database=self.config.get("database"),
            user=self.config.get("user"),
            password=self.config.get("password"),
            connection_string=self.config.get("connection_string"),
            pool_size=self.config.get("pool_size", 10),
            max_pool_size=self.config.get("max_pool_size", 20),
        )

        # Create appropriate adapter with the shared pool
        if db_type == DatabaseType.POSTGRESQL:
            adapter = PostgreSQLAdapter(db_config)
        elif db_type == DatabaseType.MYSQL:
            adapter = MySQLAdapter(db_config)
        elif db_type == DatabaseType.SQLITE:
            adapter = SQLiteAdapter(db_config)
        else:
            raise NodeExecutionError(f"Unsupported database type: {db_type}")

        # Inject the shared pool
        adapter._pool = shared_pool
        adapter._connected = True
        return adapter

    async def _get_runtime_pool_adapter(self) -> Optional[DatabaseAdapter]:
        """Try to get adapter from runtime connection pool manager with DatabasePoolCoordinator."""
        try:
            # Check if we have access to a runtime with connection pool manager
            import inspect

            frame = inspect.currentframe()

            # Look for runtime context in the call stack
            while frame:
                frame_locals = frame.f_locals
                if "self" in frame_locals:
                    obj = frame_locals["self"]
                    logger.debug(f"Checking call stack object: {type(obj).__name__}")

                    # Check if this is a LocalRuntime with connection pool manager
                    if hasattr(obj, "_pool_coordinator") and hasattr(
                        obj, "_persistent_mode"
                    ):
                        logger.debug(
                            f"Found potential runtime: persistent_mode={getattr(obj, '_persistent_mode', False)}, pool_coordinator={getattr(obj, '_pool_coordinator', None) is not None}"
                        )

                        if obj._persistent_mode and obj._pool_coordinator:
                            # Generate pool configuration
                            pool_config = {
                                "database_url": self.config.get("connection_string")
                                or self._build_connection_string(),
                                "pool_size": self.config.get("pool_size", 10),
                                "max_pool_size": self.config.get("max_pool_size", 20),
                                "database_type": self.config.get("database_type"),
                            }

                            # Try to get shared pool from runtime
                            pool_name = self._generate_pool_key()

                            # Register the pool with runtime's ConnectionPoolManager
                            if hasattr(obj._pool_coordinator, "get_or_create_pool"):
                                shared_pool = (
                                    await obj._pool_coordinator.get_or_create_pool(
                                        pool_name, pool_config
                                    )
                                )
                                if shared_pool:
                                    # Create adapter that uses the runtime-managed pool
                                    return await self._create_adapter_with_runtime_pool(
                                        shared_pool
                                    )

                            # Fallback: Create DatabasePoolCoordinator if needed
                            if not hasattr(obj, "_database_pool_coordinator"):
                                obj._database_pool_coordinator = (
                                    DatabasePoolCoordinator(obj._pool_coordinator)
                                )

                            # Generate pool configuration for enterprise pool
                            db_config = DatabaseConfig(
                                type=DatabaseType(self.config["database_type"].lower()),
                                host=self.config.get("host"),
                                port=self.config.get("port"),
                                database=self.config.get("database"),
                                user=self.config.get("user"),
                                password=self.config.get("password"),
                                connection_string=self.config.get("connection_string"),
                                pool_size=self.config.get("pool_size", 10),
                                max_pool_size=self.config.get("max_pool_size", 20),
                                command_timeout=self.config.get("timeout", 60.0),
                                enable_analytics=self.config.get(
                                    "enable_analytics", True
                                ),
                                enable_adaptive_sizing=self.config.get(
                                    "enable_adaptive_sizing", True
                                ),
                                health_check_interval=self.config.get(
                                    "health_check_interval", 30
                                ),
                                min_pool_size=self.config.get("min_pool_size", 5),
                            )

                            # Generate unique pool ID
                            pool_id = f"{self.config['database_type']}_{hash(str(self.config))}"

                            # Get or create enterprise pool through coordinator
                            enterprise_pool = (
                                await obj._database_pool_coordinator.get_or_create_pool(
                                    pool_id=pool_id,
                                    database_config=db_config,
                                    adapter_type=self.config["database_type"],
                                    pool_config={
                                        "min_size": self.config.get("min_pool_size", 5),
                                        "max_size": self.config.get(
                                            "max_pool_size", 20
                                        ),
                                        "enable_analytics": self.config.get(
                                            "enable_analytics", True
                                        ),
                                        "enable_adaptive_sizing": self.config.get(
                                            "enable_adaptive_sizing", True
                                        ),
                                        "health_check_interval": self.config.get(
                                            "health_check_interval", 30
                                        ),
                                    },
                                )
                            )

                            if enterprise_pool:
                                logger.info(
                                    f"Using runtime-coordinated enterprise pool: {pool_id}"
                                )
                                # Return the adapter from the enterprise pool
                                return enterprise_pool._adapter

                frame = frame.f_back

        except Exception as e:
            # Silently fall back to class-level pools if runtime integration fails
            logger.debug(
                f"Runtime pool integration failed, falling back to class pools: {e}"
            )
            pass

        return None

    async def _create_adapter_with_runtime_coordination(
        self, runtime_pool
    ) -> DatabaseAdapter:
        """Create adapter that coordinates with runtime connection pool."""
        # Create standard adapter but mark it as runtime-coordinated
        adapter = await self._create_adapter()

        # Mark adapter as runtime-coordinated for proper cleanup
        if hasattr(adapter, "_set_runtime_coordinated"):
            adapter._set_runtime_coordinated(True)
        else:
            # Add runtime coordination flag
            adapter._runtime_coordinated = True
            adapter._runtime_pool = runtime_pool

        return adapter

    def __init__(self, **config):
        self._adapter: Optional[DatabaseAdapter] = None
        self._connected = False
        # Extract access control manager before passing to parent
        self.access_control_manager = config.pop("access_control_manager", None)

        # Transaction state management
        self._active_transaction = None
        self._transaction_connection = None
        self._transaction_mode = config.get("transaction_mode", "auto")

        # Pool sharing configuration
        self._share_pool = config.get("share_pool", True)
        self._pool_key = None

        # Security configuration
        self._validate_queries = config.get("validate_queries", True)
        self._allow_admin = config.get("allow_admin", False)

        # Retry configuration
        retry_config = config.get("retry_config")
        if retry_config:
            if isinstance(retry_config, dict):
                self._retry_config = RetryConfig(**retry_config)
            else:
                self._retry_config = retry_config
        else:
            # Build from individual parameters
            self._retry_config = RetryConfig(
                max_retries=config.get("max_retries", 3),
                initial_delay=config.get("retry_delay", 1.0),
            )

        # Optimistic locking configuration
        self._enable_optimistic_locking = config.get("enable_optimistic_locking", False)
        self._version_field = config.get("version_field", "version")
        self._conflict_resolution = config.get("conflict_resolution", "fail_fast")
        self._version_retry_attempts = config.get("version_retry_attempts", 3)

        super().__init__(**config)

    def _reinitialize_from_config(self):
        """Re-initialize instance variables from config after config file loading."""
        # Update transaction mode
        self._transaction_mode = self.config.get("transaction_mode", "auto")

        # Update pool sharing configuration
        self._share_pool = self.config.get("share_pool", True)

        # Update security configuration
        self._validate_queries = self.config.get("validate_queries", True)
        self._allow_admin = self.config.get("allow_admin", False)

        # Update retry configuration
        retry_config = self.config.get("retry_config")
        if retry_config:
            if isinstance(retry_config, dict):
                self._retry_config = RetryConfig(**retry_config)
            else:
                self._retry_config = retry_config
        else:
            # Build from individual parameters
            self._retry_config = RetryConfig(
                max_retries=self.config.get("max_retries", 3),
                initial_delay=self.config.get("retry_delay", 1.0),
            )

        # Update optimistic locking configuration
        self._enable_optimistic_locking = self.config.get(
            "enable_optimistic_locking", False
        )
        self._version_field = self.config.get("version_field", "version")
        self._conflict_resolution = self.config.get("conflict_resolution", "fail_fast")
        self._version_retry_attempts = self.config.get("version_retry_attempts", 3)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        params = [
            NodeParameter(
                name="database_type",
                type=str,
                required=True,
                default="postgresql",
                description="Type of database: postgresql, mysql, or sqlite",
            ),
            NodeParameter(
                name="connection_string",
                type=str,
                required=False,
                description="Full database connection string (overrides individual params)",
            ),
            NodeParameter(
                name="connection_name",
                type=str,
                required=False,
                description="Name of database connection from config file",
            ),
            NodeParameter(
                name="config_file",
                type=str,
                required=False,
                description="Path to YAML configuration file (default: database.yaml)",
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
            NodeParameter(
                name="query",
                type=str,
                required=True,
                description="SQL query to execute",
            ),
            NodeParameter(
                name="params",
                type=Any,
                required=False,
                description="Query parameters as dict or tuple",
            ),
            NodeParameter(
                name="fetch_mode",
                type=str,
                required=False,
                default="all",
                description="Fetch mode: one, all, many",
            ),
            NodeParameter(
                name="fetch_size",
                type=int,
                required=False,
                description="Number of rows to fetch in 'many' mode",
            ),
            NodeParameter(
                name="pool_size",
                type=int,
                required=False,
                default=10,
                description="Initial connection pool size",
            ),
            NodeParameter(
                name="max_pool_size",
                type=int,
                required=False,
                default=20,
                description="Maximum connection pool size",
            ),
            NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=60.0,
                description="Query timeout in seconds",
            ),
            NodeParameter(
                name="user_context",
                type=Any,
                required=False,
                description="User context for access control",
            ),
            NodeParameter(
                name="transaction_mode",
                type=str,
                required=False,
                default="auto",
                description="Transaction mode: 'auto' (default), 'manual', or 'none'",
            ),
            NodeParameter(
                name="share_pool",
                type=bool,
                required=False,
                default=True,
                description="Whether to share connection pool across instances with same config",
            ),
            NodeParameter(
                name="validate_queries",
                type=bool,
                required=False,
                default=True,
                description="Whether to validate queries for SQL injection attempts",
            ),
            NodeParameter(
                name="allow_admin",
                type=bool,
                required=False,
                default=False,
                description="Allow administrative operations (USE WITH CAUTION)",
            ),
            # Enterprise features parameters
            NodeParameter(
                name="enable_analytics",
                type=bool,
                required=False,
                default=True,
                description="Enable connection pool analytics and monitoring",
            ),
            NodeParameter(
                name="enable_adaptive_sizing",
                type=bool,
                required=False,
                default=True,
                description="Enable adaptive connection pool sizing",
            ),
            NodeParameter(
                name="health_check_interval",
                type=int,
                required=False,
                default=30,
                description="Health check interval in seconds",
            ),
            NodeParameter(
                name="min_pool_size",
                type=int,
                required=False,
                default=5,
                description="Minimum connection pool size",
            ),
            NodeParameter(
                name="circuit_breaker_enabled",
                type=bool,
                required=False,
                default=True,
                description="Enable circuit breaker for connection failure protection",
            ),
            NodeParameter(
                name="parameter_types",
                type=dict,
                required=False,
                default=None,
                description="Optional PostgreSQL type hints for parameters (e.g., {'role_id': 'text', 'metadata': 'jsonb'})",
            ),
            NodeParameter(
                name="retry_config",
                type=Any,
                required=False,
                description="Retry configuration dict or RetryConfig object",
            ),
            NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum number of retry attempts for transient failures",
            ),
            NodeParameter(
                name="retry_delay",
                type=float,
                required=False,
                default=1.0,
                description="Initial retry delay in seconds",
            ),
            NodeParameter(
                name="enable_optimistic_locking",
                type=bool,
                required=False,
                default=False,
                description="Enable optimistic locking for version control",
            ),
            NodeParameter(
                name="version_field",
                type=str,
                required=False,
                default="version",
                description="Column name for version tracking",
            ),
            NodeParameter(
                name="conflict_resolution",
                type=str,
                required=False,
                default="fail_fast",
                description="How to handle version conflicts: fail_fast, retry, last_writer_wins",
            ),
            NodeParameter(
                name="version_retry_attempts",
                type=int,
                required=False,
                default=3,
                description="Maximum retries for version conflicts",
            ),
            NodeParameter(
                name="result_format",
                type=str,
                required=False,
                default="dict",
                description="Result format: 'dict' (default), 'list', or 'dataframe'",
            ),
        ]

        # Convert list to dict as required by base class
        return {param.name: param for param in params}

    def _validate_config(self):
        """Validate node configuration."""
        super()._validate_config()

        # Handle config file loading
        connection_name = self.config.get("connection_name")
        config_file = self.config.get("config_file")

        if connection_name:
            # Load from config file
            config_manager = DatabaseConfigManager(config_file)
            try:
                conn_string, db_config = config_manager.get_database_config(
                    connection_name
                )
                # Update config with values from file
                self.config["connection_string"] = conn_string
                # Merge additional config
                # Config file values should override defaults but not explicit params
                for key, value in db_config.items():
                    # Check if this was explicitly provided by user
                    param_info = self.get_parameters().get(key)
                    if param_info and key in self.config:
                        # If it equals the default, it wasn't explicitly set
                        if self.config[key] == param_info.default:
                            self.config[key] = value
                    else:
                        # Not a parameter or not in config yet
                        self.config[key] = value
            except Exception as e:
                raise NodeValidationError(
                    f"Failed to load config '{connection_name}': {e}"
                )

        # Re-initialize instance variables with updated config
        self._reinitialize_from_config()

        # Auto-detect database type from connection string if not explicitly set
        db_type = self.config.get("database_type", "").lower()
        connection_string = self.config.get("connection_string")

        # If database_type is the default and we have a connection string, try to auto-detect
        if (
            db_type == "postgresql"
            and connection_string
            and self.config.get("database_type")
            == self.get_parameters()["database_type"].default
        ):
            try:
                # Simple detection based on connection string patterns
                conn_lower = connection_string.lower()
                if (
                    connection_string == ":memory:"
                    or conn_lower.endswith(".db")
                    or conn_lower.endswith(".sqlite")
                    or conn_lower.endswith(".sqlite3")
                    or conn_lower.startswith("sqlite")
                    or
                    # File path without URL scheme (likely SQLite)
                    ("/" in connection_string and "://" not in connection_string)
                ):
                    db_type = "sqlite"
                    self.config["database_type"] = "sqlite"
                elif conn_lower.startswith("mysql"):
                    db_type = "mysql"
                    self.config["database_type"] = "mysql"
                elif conn_lower.startswith(("postgresql", "postgres")):
                    db_type = "postgresql"
                    self.config["database_type"] = "postgresql"
                # Otherwise keep default postgresql
            except Exception:
                # If detection fails, keep the default
                pass

        # Validate database type
        if db_type not in ["postgresql", "mysql", "sqlite"]:
            raise NodeValidationError(
                f"Invalid database_type: {db_type}. "
                "Must be one of: postgresql, mysql, sqlite"
            )

        # Validate connection parameters
        connection_string = self.config.get("connection_string")
        if connection_string:
            # Validate connection string for security
            if self._validate_queries:
                try:
                    QueryValidator.validate_connection_string(connection_string)
                except NodeValidationError:
                    raise NodeValidationError(
                        "Connection string failed security validation. "
                        "Set validate_queries=False to bypass (not recommended)."
                    )
        else:
            if db_type != "sqlite":
                if not self.config.get("host") or not self.config.get("database"):
                    raise NodeValidationError(
                        f"{db_type} requires host and database or connection_string"
                    )
            else:
                if not self.config.get("database"):
                    raise NodeValidationError("SQLite requires database path")

        # Validate fetch mode
        fetch_mode = self.config.get("fetch_mode", "all").lower()
        if fetch_mode not in ["one", "all", "many", "iterator"]:
            raise NodeValidationError(
                f"Invalid fetch_mode: {fetch_mode}. "
                "Must be one of: one, all, many, iterator"
            )

        if fetch_mode == "many" and not self.config.get("fetch_size"):
            raise NodeValidationError("fetch_size required when fetch_mode is 'many'")

        # Validate initial query if provided
        if self.config.get("query") and self._validate_queries:
            try:
                QueryValidator.validate_query(
                    self.config["query"], allow_admin=self._allow_admin
                )
            except NodeValidationError as e:
                raise NodeValidationError(
                    f"Initial query validation failed: {e}. "
                    "Set validate_queries=False to bypass (not recommended)."
                )

    def _generate_pool_key(self) -> str:
        """Generate a unique key for connection pool sharing.

        The pool key ALWAYS includes the actual event loop ID to prevent
        "Task got Future attached to a different loop" errors when pools
        are reused across different event loops.

        In test environments, this means each pytest-asyncio test that creates
        a new event loop will get its own pool. This is the correct behavior
        to prevent asyncio errors, even though it means less pool reuse.

        Returns:
            str: Pool key in format "loop_id|db_type|connection|pool_size|max_pool_size"

        Examples:
            With running loop:  "140736120345216|postgresql|localhost:5432|10|20"
            Without loop:       "no_loop|postgresql|localhost:5432|10|20"
        """
        # Always use actual loop ID for proper event loop isolation
        # This prevents "attached to different loop" errors
        try:
            loop = asyncio.get_running_loop()
            loop_id = str(id(loop))
        except RuntimeError:
            # No running loop (sync context like auto_migrate)
            loop_id = "no_loop"

        # Create a unique key based on event loop and connection parameters
        key_parts = [
            loop_id,  # Event loop isolation (adaptive)
            self.config.get("database_type", ""),
            self.config.get("connection_string", "")
            or (
                f"{self.config.get('host', '')}:"
                f"{self.config.get('port', '')}:"
                f"{self.config.get('database', '')}:"
                f"{self.config.get('user', '')}"
            ),
            str(self.config.get("pool_size", 10)),
            str(self.config.get("max_pool_size", 20)),
        ]
        return "|".join(key_parts)

    async def _get_adapter(self) -> DatabaseAdapter:
        """Get or create database adapter with optional pool sharing."""
        if not self._adapter:
            if self._share_pool:
                # PRIORITY 1: Try to get adapter from runtime connection pool manager
                runtime_adapter = await self._get_runtime_pool_adapter()
                if runtime_adapter:
                    self._adapter = runtime_adapter
                    self._connected = True
                    logger.debug(
                        f"Using runtime-coordinated connection pool for {self.id}"
                    )
                    return self._adapter

                # FALLBACK: Use class-level shared pool for backward compatibility
                # TASK-141.7: Replace global lock with per-pool locks
                self._pool_key = self._generate_pool_key()

                try:
                    # TASK-141.11: Attempt per-pool locking with fallback mechanism
                    async with self._acquire_pool_lock_with_timeout(
                        self._pool_key, timeout=5.0
                    ):

                        if self._pool_key in self._shared_pools:
                            # Validate pool's event loop is still running before reuse
                            adapter, ref_count = self._shared_pools[self._pool_key]

                            try:
                                # Check if we have a running event loop
                                pool_loop = asyncio.get_running_loop()
                                # If we got here, loop is running - safe to reuse
                                self._shared_pools[self._pool_key] = (
                                    adapter,
                                    ref_count + 1,
                                )
                                self._adapter = adapter
                                self._connected = True
                                logger.debug(
                                    f"Using class-level shared pool for {self.id}"
                                )
                                return self._adapter
                            except RuntimeError:
                                # Loop is closed - remove stale pool
                                logger.warning(
                                    f"Removing stale pool for {self._pool_key} - event loop closed"
                                )
                                del self._shared_pools[self._pool_key]
                                # Fall through to create new pool

                        # Create new shared pool
                        self._adapter = await self._create_adapter()
                        self._shared_pools[self._pool_key] = (self._adapter, 1)
                        AsyncSQLDatabaseNode._total_pools_created += 1  # ADR-017
                        logger.debug(
                            f"Created new class-level shared pool for {self.id}"
                        )

                except (RuntimeError, asyncio.TimeoutError, Exception) as e:
                    # FALLBACK: Graceful degradation to dedicated pool mode
                    logger.warning(
                        f"Per-pool locking failed for {self.id} (pool_key: {self._pool_key}): {e}. "
                        f"Falling back to dedicated pool mode."
                    )
                    # Clear pool sharing for this instance and create dedicated pool
                    self._share_pool = False
                    self._pool_key = None
                    self._adapter = await self._create_adapter()
                    logger.info(
                        f"Successfully created dedicated connection pool for {self.id} as fallback"
                    )
            else:
                # Create dedicated pool
                self._adapter = await self._create_adapter()
                logger.debug(f"Created dedicated connection pool for {self.id}")

        return self._adapter

    async def _create_adapter(self) -> DatabaseAdapter:
        """Create a new database adapter with retry logic for initial connection."""
        db_type = DatabaseType(self.config["database_type"].lower())
        db_config = DatabaseConfig(
            type=db_type,
            host=self.config.get("host"),
            port=self.config.get("port"),
            database=self.config.get("database"),
            user=self.config.get("user"),
            password=self.config.get("password"),
            connection_string=self.config.get("connection_string"),
            pool_size=self.config.get("pool_size", 10),
            max_pool_size=self.config.get("max_pool_size", 20),
            command_timeout=self.config.get("timeout", 60.0),
        )

        # Add enterprise features configuration to database config
        db_config.enable_analytics = self.config.get("enable_analytics", True)
        db_config.enable_adaptive_sizing = self.config.get(
            "enable_adaptive_sizing", True
        )
        db_config.health_check_interval = self.config.get("health_check_interval", 30)
        db_config.min_pool_size = self.config.get("min_pool_size", 5)

        # Use production adapters with enterprise features
        if db_type == DatabaseType.POSTGRESQL:
            adapter = ProductionPostgreSQLAdapter(db_config)
        elif db_type == DatabaseType.MYSQL:
            adapter = ProductionMySQLAdapter(db_config)
        elif db_type == DatabaseType.SQLITE:
            adapter = ProductionSQLiteAdapter(db_config)
        else:
            raise NodeExecutionError(f"Unsupported database type: {db_type}")

        # Retry connection with exponential backoff
        last_error = None
        for attempt in range(self._retry_config.max_retries):
            try:
                await adapter.connect()
                self._connected = True
                return adapter
            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise NodeExecutionError(
                        f"Failed to connect after {self._retry_config.max_retries} attempts: {e}"
                    )

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Wait before retry
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        raise NodeExecutionError(
            f"Failed to connect after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def async_run(self, **inputs) -> dict[str, Any]:
        """Execute database query asynchronously with optional access control."""
        try:
            # Get runtime parameters
            query = inputs.get("query", self.config.get("query"))
            params = inputs.get("params", self.config.get("params"))
            fetch_mode = FetchMode(
                inputs.get("fetch_mode", self.config.get("fetch_mode", "all")).lower()
            )
            fetch_size = inputs.get("fetch_size", self.config.get("fetch_size"))
            result_format = inputs.get(
                "result_format", self.config.get("result_format", "dict")
            )
            user_context = inputs.get("user_context")
            parameter_types = inputs.get(
                "parameter_types", self.config.get("parameter_types")
            )

            if not query:
                raise NodeExecutionError("No query provided")

            # Handle parameter style conversion
            # MySQL uses %s positional parameters and expects tuple/list, not named params
            # PostgreSQL/SQLite support :name style named parameters
            db_type = self.config.get("database_type", "").lower()

            if params is not None:
                if db_type == "mysql":
                    # MySQL: Keep %s placeholders and convert params to tuple
                    if isinstance(params, dict):
                        # If dict provided, convert to MySQL %(name)s style
                        # But for now, just keep as dict - aiomysql handles it
                        pass
                    elif isinstance(params, (list, tuple)):
                        # Keep as tuple for %s placeholders
                        params = tuple(params) if isinstance(params, list) else params
                    else:
                        # Single param - wrap in tuple
                        params = (params,)
                else:
                    # PostgreSQL/SQLite: Convert to named parameters (:p0, :p1)
                    if isinstance(params, (list, tuple)):
                        # Convert positional parameters to named parameters
                        query, params = self._convert_to_named_parameters(query, params)
                    elif not isinstance(params, dict):
                        # Single parameter - wrap in list and convert
                        query, params = self._convert_to_named_parameters(
                            query, [params]
                        )

            # Validate query for security
            if self._validate_queries:
                try:
                    QueryValidator.validate_query(query, allow_admin=self._allow_admin)
                except NodeValidationError as e:
                    raise NodeExecutionError(
                        f"Query validation failed: {e}. "
                        "Set validate_queries=False to bypass (not recommended)."
                    )

            # Check access control if enabled
            if self.access_control_manager and user_context:
                from kailash.access_control import NodePermission

                decision = self.access_control_manager.check_node_access(
                    user_context, self.metadata.name, NodePermission.EXECUTE
                )
                if not decision.allowed:
                    raise NodeExecutionError(f"Access denied: {decision.reason}")

            # Get adapter
            adapter = await self._get_adapter()

            # Execute query with retry logic
            result = await self._execute_with_retry(
                adapter=adapter,
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                user_context=user_context,
                parameter_types=parameter_types,
            )

            # Check for special SQLite lastrowid result
            if isinstance(result, dict) and "lastrowid" in result:
                # This is a special SQLite INSERT result
                formatted_data = result  # Keep as-is
                row_count = 1  # One row was inserted
            else:
                # Ensure all data is JSON-serializable (safety net for adapter inconsistencies)
                result = self._ensure_serializable(result)

                # Format results based on requested format
                formatted_data = self._format_results(result, result_format)
                row_count = None  # Will be calculated below

            # For DataFrame, we need special handling for row count
            if row_count is None:  # Only calculate if not already set
                if result_format == "dataframe":
                    try:
                        row_count = len(formatted_data)
                    except:
                        # If pandas isn't available, formatted_data is still a list
                        row_count = (
                            len(result)
                            if isinstance(result, list)
                            else (1 if result else 0)
                        )
                else:
                    row_count = (
                        len(result)
                        if isinstance(result, list)
                        else (1 if result else 0)
                    )

            # Extract column names if available
            columns = []
            if result and isinstance(result, list) and result:
                if isinstance(result[0], dict):
                    columns = list(result[0].keys())

            # Handle DataFrame serialization for JSON compatibility
            if result_format == "dataframe":
                try:
                    import pandas as pd

                    if isinstance(formatted_data, pd.DataFrame):
                        # Convert DataFrame to JSON-compatible format
                        serializable_data = {
                            "dataframe": formatted_data.to_dict("records"),
                            "columns": formatted_data.columns.tolist(),
                            "index": formatted_data.index.tolist(),
                            "_type": "dataframe",
                        }
                    else:
                        # pandas not available, use regular data
                        serializable_data = formatted_data
                except ImportError:
                    serializable_data = formatted_data
            else:
                serializable_data = formatted_data

            result_dict = {
                "result": {
                    "data": serializable_data,
                    "row_count": row_count,
                    "query": query,
                    "database_type": self.config["database_type"],
                    "format": result_format,
                }
            }

            # Add columns info for list format
            if result_format == "list" and columns:
                result_dict["result"]["columns"] = columns

            return result_dict

        except NodeExecutionError:
            # Re-raise our own errors
            raise
        except Exception as e:
            # Wrap other errors
            raise NodeExecutionError(f"Database query failed: {str(e)}")

    async def process(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Async process method for middleware compatibility."""
        return await self.async_run(**inputs)

    async def execute_many_async(
        self, query: str, params_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute the same query multiple times with different parameters.

        This is useful for bulk inserts, updates, or deletes. The operation
        runs in a single transaction (in auto or manual mode) for better
        performance and atomicity.

        Args:
            query: SQL query to execute multiple times
            params_list: List of parameter dictionaries

        Returns:
            dict: Result with affected row count

        Example:
            >>> params_list = [
            ...     {"name": "Alice", "age": 30},
            ...     {"name": "Bob", "age": 25},
            ...     {"name": "Charlie", "age": 35},
            ... ]
            >>> result = await node.execute_many_async(
            ...     query="INSERT INTO users (name, age) VALUES (:name, :age)",
            ...     params_list=params_list
            ... )
            >>> print(result["result"]["affected_rows"])  # 3
        """
        if not params_list:
            return {
                "result": {
                    "affected_rows": 0,
                    "query": query,
                    "database_type": self.config["database_type"],
                }
            }

        # Validate query if security is enabled
        if self._validate_queries:
            try:
                QueryValidator.validate_query(query, allow_admin=self._allow_admin)
            except NodeValidationError as e:
                raise NodeExecutionError(
                    f"Query validation failed: {e}. "
                    "Set validate_queries=False to bypass (not recommended)."
                )

        try:
            # Get adapter
            adapter = await self._get_adapter()

            # Execute batch with retry logic
            affected_rows = await self._execute_many_with_retry(
                adapter=adapter,
                query=query,
                params_list=params_list,
            )

            return {
                "result": {
                    "affected_rows": affected_rows,
                    "batch_size": len(params_list),
                    "query": query,
                    "database_type": self.config["database_type"],
                }
            }

        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(f"Batch operation failed: {str(e)}")

    async def begin_transaction(self):
        """Begin a manual transaction.

        Returns:
            Transaction context that can be used for manual control

        Raises:
            NodeExecutionError: If transaction already active or mode is 'auto'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "begin_transaction() can only be called in 'manual' transaction mode"
            )

        if self._active_transaction:
            raise NodeExecutionError("Transaction already active")

        adapter = await self._get_adapter()
        self._active_transaction = await adapter.begin_transaction()
        return self._active_transaction

    async def commit(self):
        """Commit the active transaction.

        Raises:
            NodeExecutionError: If no active transaction or mode is not 'manual'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "commit() can only be called in 'manual' transaction mode"
            )

        if not self._active_transaction:
            raise NodeExecutionError("No active transaction to commit")

        adapter = await self._get_adapter()
        try:
            await adapter.commit_transaction(self._active_transaction)
        finally:
            # Always clear transaction, even on error
            self._active_transaction = None

    async def rollback(self):
        """Rollback the active transaction.

        Raises:
            NodeExecutionError: If no active transaction or mode is not 'manual'
        """
        if self._transaction_mode != "manual":
            raise NodeExecutionError(
                "rollback() can only be called in 'manual' transaction mode"
            )

        if not self._active_transaction:
            raise NodeExecutionError("No active transaction to rollback")

        adapter = await self._get_adapter()
        try:
            await adapter.rollback_transaction(self._active_transaction)
        finally:
            # Always clear transaction, even on error
            self._active_transaction = None

    async def _execute_with_retry(
        self,
        adapter: DatabaseAdapter,
        query: str,
        params: Any,
        fetch_mode: FetchMode,
        fetch_size: Optional[int],
        user_context: Any = None,
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query with retry logic for transient failures.

        Args:
            adapter: Database adapter
            query: SQL query
            params: Query parameters
            fetch_mode: How to fetch results
            fetch_size: Number of rows for 'many' mode
            user_context: User context for access control

        Returns:
            Query results

        Raises:
            NodeExecutionError: After all retry attempts are exhausted
        """
        last_error = None

        for attempt in range(self._retry_config.max_retries):
            try:
                # Execute query with transaction
                result = await self._execute_with_transaction(
                    adapter=adapter,
                    query=query,
                    params=params,
                    fetch_mode=fetch_mode,
                    fetch_size=fetch_size,
                    parameter_types=parameter_types,
                )

                # Apply data masking if access control is enabled
                if self.access_control_manager and user_context:
                    if isinstance(result, list):
                        masked_result = []
                        for row in result:
                            masked_row = self.access_control_manager.apply_data_masking(
                                user_context, self.metadata.name, row
                            )
                            masked_result.append(masked_row)
                        result = masked_result
                    elif isinstance(result, dict):
                        result = self.access_control_manager.apply_data_masking(
                            user_context, self.metadata.name, result
                        )

                return result

            except Exception as e:
                last_error = e

                # Parameter type determination is now handled during dict-to-positional conversion
                # No special retry logic needed for parameter $11

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Log retry attempt (if logging is available)
                try:
                    self.logger.warning(
                        f"Query failed (attempt {attempt + 1}/{self._retry_config.max_retries}): {e}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                except AttributeError:
                    # No logger available
                    pass

                # Wait before retry
                await asyncio.sleep(delay)

                # For connection errors, try to reconnect
                if "pool is closed" in str(e).lower() or "connection" in str(e).lower():
                    try:
                        # Clear existing adapter to force reconnection
                        if self._share_pool and self._pool_key:
                            # Remove from shared pools to force recreation
                            async with self._acquire_pool_lock_with_timeout(
                                self._pool_key, timeout=5.0
                            ):
                                if self._pool_key in self._shared_pools:
                                    _, ref_count = self._shared_pools[self._pool_key]
                                    if ref_count <= 1:
                                        del self._shared_pools[self._pool_key]
                                    else:
                                        # This shouldn't happen with a closed pool
                                        del self._shared_pools[self._pool_key]

                        self._adapter = None
                        self._connected = False
                        adapter = await self._get_adapter()
                    except Exception:
                        # If reconnection fails, continue with retry loop
                        pass

        # All retries exhausted
        raise NodeExecutionError(
            f"Query failed after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def _execute_many_with_retry(
        self, adapter: DatabaseAdapter, query: str, params_list: list[dict[str, Any]]
    ) -> int:
        """Execute batch operation with retry logic.

        Args:
            adapter: Database adapter
            query: SQL query to execute
            params_list: List of parameter dictionaries

        Returns:
            Number of affected rows

        Raises:
            NodeExecutionError: After all retry attempts are exhausted
        """
        last_error = None

        for attempt in range(self._retry_config.max_retries):
            try:
                # Execute batch with transaction
                return await self._execute_many_with_transaction(
                    adapter=adapter,
                    query=query,
                    params_list=params_list,
                )

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self._retry_config.should_retry(e):
                    raise

                # Check if we have more attempts
                if attempt >= self._retry_config.max_retries - 1:
                    raise

                # Calculate delay
                delay = self._retry_config.get_delay(attempt)

                # Wait before retry
                await asyncio.sleep(delay)

                # For connection errors, try to reconnect
                if "pool is closed" in str(e).lower() or "connection" in str(e).lower():
                    try:
                        # Clear existing adapter to force reconnection
                        if self._share_pool and self._pool_key:
                            # Remove from shared pools to force recreation
                            async with self._acquire_pool_lock_with_timeout(
                                self._pool_key, timeout=5.0
                            ):
                                if self._pool_key in self._shared_pools:
                                    _, ref_count = self._shared_pools[self._pool_key]
                                    if ref_count <= 1:
                                        del self._shared_pools[self._pool_key]
                                    else:
                                        # This shouldn't happen with a closed pool
                                        del self._shared_pools[self._pool_key]

                        self._adapter = None
                        self._connected = False
                        adapter = await self._get_adapter()
                    except Exception:
                        # If reconnection fails, continue with retry loop
                        pass

        # All retries exhausted
        raise NodeExecutionError(
            f"Batch operation failed after {self._retry_config.max_retries} attempts: {last_error}"
        )

    async def _execute_many_with_transaction(
        self, adapter: DatabaseAdapter, query: str, params_list: list[dict[str, Any]]
    ) -> int:
        """Execute batch operation with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query to execute
            params_list: List of parameter dictionaries

        Returns:
            Number of affected rows (estimated)

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if self._active_transaction:
            # Use existing transaction (manual mode)
            await adapter.execute_many(query, params_list, self._active_transaction)
            # Most adapters don't return row count from execute_many
            return len(params_list)
        elif self._transaction_mode == "auto":
            # Auto-transaction mode
            transaction = await adapter.begin_transaction()
            try:
                await adapter.execute_many(query, params_list, transaction)
                await adapter.commit_transaction(transaction)
                return len(params_list)
            except Exception:
                await adapter.rollback_transaction(transaction)
                raise
        else:
            # No transaction mode
            await adapter.execute_many(query, params_list)
            return len(params_list)

    async def _execute_with_transaction(
        self,
        adapter: DatabaseAdapter,
        query: str,
        params: Any,
        fetch_mode: FetchMode,
        fetch_size: Optional[int],
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query
            params: Query parameters
            fetch_mode: How to fetch results
            fetch_size: Number of rows for 'many' mode

        Returns:
            Query results

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if self._active_transaction:
            # Use existing transaction (manual mode)
            return await adapter.execute(
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                transaction=self._active_transaction,
                parameter_types=parameter_types,
            )
        elif self._transaction_mode == "auto":
            # Auto-transaction mode
            transaction = await adapter.begin_transaction()
            try:
                result = await adapter.execute(
                    query=query,
                    params=params,
                    fetch_mode=fetch_mode,
                    fetch_size=fetch_size,
                    transaction=transaction,
                    parameter_types=parameter_types,
                )
                await adapter.commit_transaction(transaction)
                return result
            except Exception:
                await adapter.rollback_transaction(transaction)
                raise
        else:
            # No transaction mode
            return await adapter.execute(
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                parameter_types=parameter_types,
            )

    @classmethod
    async def get_pool_metrics(cls) -> dict[str, Any]:
        """Get metrics for all shared connection pools.

        Returns:
            dict: Pool metrics including pool count, connections per pool, etc.
        """
        async with cls._get_pool_lock():
            metrics = {"total_pools": len(cls._shared_pools), "pools": []}

            for pool_key, (adapter, ref_count) in cls._shared_pools.items():
                pool_info = {
                    "key": pool_key,
                    "reference_count": ref_count,
                    "type": adapter.__class__.__name__,
                }

                # Try to get pool-specific metrics if available
                if hasattr(adapter, "_pool") and adapter._pool:
                    pool = adapter._pool
                    if hasattr(pool, "size"):
                        pool_info["pool_size"] = pool.size()
                    if hasattr(pool, "_holders"):
                        pool_info["active_connections"] = len(
                            [h for h in pool._holders if h._in_use]
                        )
                    elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                        pool_info["active_connections"] = pool.size - pool.freesize

                metrics["pools"].append(pool_info)

            # Clean up stale pools from closed event loops
            cleaned_pools = cls._cleanup_closed_loop_pools()
            if cleaned_pools > 0:
                metrics["cleaned_stale_pools"] = cleaned_pools

            return metrics

    @classmethod
    async def _cleanup_closed_loop_pools(cls) -> int:
        """Proactively remove pools from closed event loops.

        Enhanced with ADR-017:
        - Async-first design (proper await for pool cleanup)
        - Detailed logging
        - Graceful error handling
        - Metrics tracking

        Returns:
            int: Number of pools cleaned
        """
        cleaned_count = 0
        pools_to_remove = []

        try:
            current_loop = asyncio.get_event_loop()
            current_loop_id = id(current_loop)
        except RuntimeError:
            logger.warning("AsyncSQLDatabaseNode: No event loop available for cleanup")
            return 0

        # Phase 1: Identify stale pools
        for pool_key, (adapter, creation_time) in list(cls._shared_pools.items()):
            loop_id_str = pool_key.split("|")[0]

            try:
                pool_loop_id = int(loop_id_str)
            except (ValueError, IndexError):
                logger.warning(
                    f"AsyncSQLDatabaseNode: Invalid pool key format: {pool_key}"
                )
                continue

            # Check if pool's event loop differs from current
            if pool_loop_id != current_loop_id:
                pools_to_remove.append(pool_key)
                logger.debug(
                    f"AsyncSQLDatabaseNode: Marked stale pool {pool_key} "
                    f"(loop {pool_loop_id} != current {current_loop_id})"
                )

        # Phase 2: Cleanup stale pools
        for pool_key in pools_to_remove:
            try:
                adapter, creation_time = cls._shared_pools.pop(pool_key)

                # Attempt graceful close
                try:
                    if hasattr(adapter, "close"):
                        await adapter.close()
                except Exception as close_error:
                    logger.debug(
                        f"AsyncSQLDatabaseNode: Could not close adapter for "
                        f"{pool_key}: {close_error}"
                    )

                cleaned_count += 1
                logger.info(f"AsyncSQLDatabaseNode: Cleaned stale pool {pool_key}")
            except Exception as e:
                logger.warning(
                    f"AsyncSQLDatabaseNode: Failed to cleanup pool {pool_key}: {e}"
                )

        if cleaned_count > 0:
            logger.info(f"AsyncSQLDatabaseNode: Cleaned {cleaned_count} stale pools")

        return cleaned_count

    @classmethod
    async def clear_shared_pools(cls, graceful: bool = True) -> Dict[str, Any]:
        """Clear all shared connection pools with enhanced error handling (ADR-017).

        Args:
            graceful: If True, attempts graceful close. If False, immediately removes pools.

        Returns:
            Dict[str, Any]: Cleanup metrics
        """
        total_pools = len(cls._shared_pools)
        pools_cleared = 0
        clear_failures = 0
        clear_errors = []

        if total_pools == 0:
            return {
                "total_pools": 0,
                "pools_cleared": 0,
                "clear_failures": 0,
                "clear_errors": [],
            }

        logger.info(
            f"AsyncSQLDatabaseNode: Clearing {total_pools} shared pools "
            f"(graceful={graceful})"
        )

        pool_keys = list(cls._shared_pools.keys())

        for pool_key in pool_keys:
            try:
                adapter, creation_time = cls._shared_pools.pop(pool_key)

                if graceful and hasattr(adapter, "close"):
                    try:
                        await adapter.close()
                        logger.debug(
                            f"AsyncSQLDatabaseNode: Gracefully closed pool {pool_key}"
                        )
                    except Exception as close_error:
                        logger.warning(
                            f"AsyncSQLDatabaseNode: Error closing pool {pool_key}: "
                            f"{close_error}"
                        )

                pools_cleared += 1
            except Exception as e:
                clear_failures += 1
                error_msg = f"Failed to clear pool {pool_key}: {str(e)}"
                clear_errors.append(error_msg)
                logger.error(f"AsyncSQLDatabaseNode: {error_msg}")

        logger.info(
            f"AsyncSQLDatabaseNode: Cleared {pools_cleared}/{total_pools} pools "
            f"({clear_failures} failures)"
        )

        return {
            "total_pools": total_pools,
            "pools_cleared": pools_cleared,
            "clear_failures": clear_failures,
            "clear_errors": clear_errors,
        }

    def get_pool_info(self) -> dict[str, Any]:
        """Get information about this instance's connection pool.

        Returns:
            dict: Pool information including shared status and metrics
        """
        info = {
            "shared": self._share_pool,
            "pool_key": self._pool_key,
            "connected": self._connected,
        }

        if self._adapter and hasattr(self._adapter, "_pool") and self._adapter._pool:
            pool = self._adapter._pool
            if hasattr(pool, "size"):
                info["pool_size"] = pool.size()
            if hasattr(pool, "_holders"):
                info["active_connections"] = len(
                    [h for h in pool._holders if h._in_use]
                )
            elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                info["active_connections"] = pool.size - pool.freesize

        return info

    async def execute_with_version_check(
        self,
        query: str,
        params: dict[str, Any],
        expected_version: Optional[int] = None,
        record_id: Optional[Any] = None,
        table_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a query with optimistic locking version check.

        Args:
            query: SQL query to execute (UPDATE or DELETE)
            params: Query parameters
            expected_version: Expected version number for conflict detection
            record_id: ID of the record being updated (for retry)
            table_name: Table name (for retry to re-read current version)

        Returns:
            dict: Result with version information and conflict status

        Raises:
            NodeExecutionError: On version conflict or database error
        """
        if not self._enable_optimistic_locking:
            # Just execute normally if optimistic locking is disabled
            result = await self.execute_async(query=query, params=params)
            return {
                "result": result,
                "version_checked": False,
                "status": LockStatus.SUCCESS,
            }

        # Add version check to the query
        if expected_version is not None:
            # Ensure version field is in params
            if "expected_version" in query:
                # Query already uses :expected_version, just ensure it's set
                params["expected_version"] = expected_version
            else:
                # Use standard version field
                params[self._version_field] = expected_version

            # For UPDATE queries, also add version increment
            if "UPDATE" in query.upper() and "SET" in query.upper():
                # Find SET clause and add version increment
                set_match = re.search(r"(SET\s+)(.+?)(\s+WHERE)", query, re.IGNORECASE)
                if set_match:
                    set_clause = set_match.group(2)
                    # Add version increment if not already present
                    if self._version_field not in set_clause:
                        new_set_clause = f"{set_clause}, {self._version_field} = {self._version_field} + 1"
                        query = (
                            query[: set_match.start(2)]
                            + new_set_clause
                            + query[set_match.end(2) :]
                        )

            # Modify query to include version check in WHERE clause (only if not already present)
            # Check for version condition in WHERE clause specifically, not just anywhere in query
            where_clause_pattern = (
                r"WHERE\s+.*?" + re.escape(self._version_field) + r"\s*="
            )
            has_version_check_in_where = (
                re.search(where_clause_pattern, query, re.IGNORECASE) is not None
                or ":expected_version" in query
            )
            if not has_version_check_in_where:
                if "WHERE" in query.upper():
                    query += f" AND {self._version_field} = :{self._version_field}"
                else:
                    query += f" WHERE {self._version_field} = :{self._version_field}"

        # Try to execute with version check
        retry_count = 0
        for attempt in range(self._version_retry_attempts):
            try:
                result = await self.execute_async(query=query, params=params)

                # Check if any rows were affected
                rows_affected = 0
                rows_affected_found = False
                if isinstance(result.get("result"), dict):
                    # Check if we have data array with rows_affected
                    data = result["result"].get("data", [])
                    if data and isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], dict) and "rows_affected" in data[0]:
                            rows_affected = data[0]["rows_affected"]
                            rows_affected_found = True

                    # Only check direct keys if we haven't found rows_affected in data
                    if not rows_affected_found:
                        rows_affected = (
                            result["result"].get("rows_affected", 0)
                            or result["result"].get("rowcount", 0)
                            or result["result"].get("affected_rows", 0)
                            or result["result"].get("row_count", 0)
                        )

                if rows_affected == 0 and expected_version is not None:
                    # Version conflict detected
                    if self._conflict_resolution == "fail_fast":
                        raise NodeExecutionError(
                            f"Version conflict: expected version {expected_version} not found"
                        )
                    elif (
                        self._conflict_resolution == "retry"
                        and record_id
                        and table_name
                    ):
                        # Read current version
                        current = await self.execute_async(
                            query=f"SELECT {self._version_field} FROM {table_name} WHERE id = :id",
                            params={"id": record_id},
                        )

                        if current["result"]["data"]:
                            current_version = current["result"]["data"][0][
                                self._version_field
                            ]
                            params[self._version_field] = current_version
                            # Update expected version for next attempt
                            expected_version = current_version
                            retry_count += 1
                            continue
                        else:
                            return {
                                "result": None,
                                "status": LockStatus.RECORD_NOT_FOUND,
                                "version_checked": True,
                                "retry_count": retry_count,
                            }
                    elif self._conflict_resolution == "last_writer_wins":
                        # Remove version check and try again
                        params_no_version = params.copy()
                        params_no_version.pop(self._version_field, None)
                        query_no_version = query.replace(
                            f" AND {self._version_field} = :{self._version_field}", ""
                        )
                        result = await self.execute_async(
                            query=query_no_version, params=params_no_version
                        )
                        return {
                            "result": result,
                            "status": LockStatus.SUCCESS,
                            "version_checked": False,
                            "conflict_resolved": "last_writer_wins",
                            "retry_count": retry_count,
                        }

                # Success - increment version for UPDATE queries
                if "UPDATE" in query.upper() and rows_affected > 0:
                    # The query should have incremented the version
                    new_version = (
                        (expected_version or 0) + 1
                        if expected_version is not None
                        else None
                    )
                    return {
                        "result": result,
                        "status": LockStatus.SUCCESS,
                        "version_checked": True,
                        "new_version": new_version,
                        "rows_affected": rows_affected,
                        "retry_count": retry_count,
                    }
                else:
                    return {
                        "result": result,
                        "status": LockStatus.SUCCESS,
                        "version_checked": True,
                        "rows_affected": rows_affected,
                        "retry_count": retry_count,
                    }

            except NodeExecutionError:
                if attempt >= self._version_retry_attempts - 1:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff

        return {
            "result": None,
            "status": LockStatus.RETRY_EXHAUSTED,
            "version_checked": True,
            "retry_count": self._version_retry_attempts,
        }

    async def read_with_version(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a SELECT query and extract version information.

        Args:
            query: SELECT query to execute
            params: Query parameters

        Returns:
            dict: Result with version information included
        """
        result = await self.execute_async(query=query, params=params)

        if self._enable_optimistic_locking and result.get("result", {}).get("data"):
            # Extract version from results
            data = result["result"]["data"]
            if isinstance(data, list) and len(data) > 0:
                # Single record
                if len(data) == 1 and self._version_field in data[0]:
                    return {
                        "result": result,
                        "version": data[0][self._version_field],
                        "record": data[0],
                    }
                # Multiple records - include version in each
                else:
                    versions = []
                    for record in data:
                        if self._version_field in record:
                            versions.append(record[self._version_field])
                    return {
                        "result": result,
                        "versions": versions,
                        "records": data,
                    }

        return result

    def build_versioned_update_query(
        self,
        table_name: str,
        update_fields: dict[str, Any],
        where_clause: str,
        increment_version: bool = True,
    ) -> str:
        """Build an UPDATE query with version increment.

        Args:
            table_name: Name of the table to update
            update_fields: Fields to update (excluding version)
            where_clause: WHERE clause (without WHERE keyword)
            increment_version: Whether to increment the version field

        Returns:
            str: UPDATE query with version handling
        """
        if not self._enable_optimistic_locking:
            # Build normal update query
            set_parts = [f"{field} = :{field}" for field in update_fields]
            return (
                f"UPDATE {table_name} SET {', '.join(set_parts)} WHERE {where_clause}"
            )

        # Build versioned update query
        set_parts = [f"{field} = :{field}" for field in update_fields]

        if increment_version:
            set_parts.append(f"{self._version_field} = {self._version_field} + 1")

        return f"UPDATE {table_name} SET {', '.join(set_parts)} WHERE {where_clause}"

    def _convert_to_named_parameters(
        self, query: str, parameters: list
    ) -> tuple[str, dict]:
        """Convert positional parameters to named parameters for various SQL dialects.

        This method handles conversion from different SQL parameter styles to a
        consistent named parameter format that works with async database drivers.

        Args:
            query: SQL query with positional placeholders (?, $1, %s)
            parameters: List of parameter values

        Returns:
            Tuple of (modified_query, parameter_dict)

        Examples:
            >>> # SQLite style
            >>> query = "SELECT * FROM users WHERE age > ? AND active = ?"
            >>> params = [25, True]
            >>> new_query, param_dict = node._convert_to_named_parameters(query, params)
            >>> # Returns: ("SELECT * FROM users WHERE age > :p0 AND active = :p1",
            >>> #          {"p0": 25, "p1": True})

            >>> # PostgreSQL style
            >>> query = "UPDATE users SET name = $1 WHERE id = $2"
            >>> params = ["John", 123]
            >>> new_query, param_dict = node._convert_to_named_parameters(query, params)
            >>> # Returns: ("UPDATE users SET name = :p0 WHERE id = :p1",
            >>> #          {"p0": "John", "p1": 123})
        """
        # Create parameter dictionary
        param_dict = {}
        for i, value in enumerate(parameters):
            param_dict[f"p{i}"] = value

        # Replace different placeholder formats with named parameters
        modified_query = query

        # Handle SQLite-style ? placeholders
        placeholder_count = 0

        def replace_question_mark(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"\?", replace_question_mark, modified_query)

        # Handle PostgreSQL-style $1, $2, etc. placeholders
        def replace_postgres_placeholder(match):
            index = int(match.group(1)) - 1  # PostgreSQL uses 1-based indexing
            return f":p{index}"

        modified_query = re.sub(
            r"\$(\d+)", replace_postgres_placeholder, modified_query
        )

        # Handle MySQL-style %s placeholders
        placeholder_count = 0

        def replace_mysql_placeholder(match):
            nonlocal placeholder_count
            replacement = f":p{placeholder_count}"
            placeholder_count += 1
            return replacement

        modified_query = re.sub(r"%s", replace_mysql_placeholder, modified_query)

        return modified_query, param_dict

    def _ensure_serializable(self, data: Any) -> Any:
        """Ensure all data types are JSON-serializable.

        This is a safety net for cases where adapter _convert_row might not be called
        or might miss certain data types. It recursively processes the data structure
        to ensure datetime objects and other non-JSON-serializable types are converted.

        Args:
            data: Raw data from database adapter

        Returns:
            JSON-serializable data structure
        """
        if data is None:
            return None
        elif isinstance(data, bool):
            return data
        elif isinstance(data, (int, float, str)):
            return data
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, date):
            return data.isoformat()
        elif hasattr(data, "total_seconds"):  # timedelta
            return data.total_seconds()
        elif isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, bytes):
            import base64

            return base64.b64encode(data).decode("utf-8")
        elif hasattr(data, "__str__") and hasattr(data, "hex"):  # UUID-like objects
            return str(data)
        elif isinstance(data, dict):
            return {
                key: self._ensure_serializable(value) for key, value in data.items()
            }
        elif isinstance(data, (list, tuple)):
            return [self._ensure_serializable(item) for item in data]
        else:
            # For any other type, try to convert to string as fallback
            try:
                # Test if it's already JSON serializable
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # Not serializable, convert to string
                return str(data)

    def _format_results(self, data: list[dict], result_format: str) -> Any:
        """Format query results according to specified format.

        Args:
            data: List of dictionaries from database query
            result_format: Desired output format ('dict', 'list', 'dataframe')

        Returns:
            Formatted results

        Formats:
            - 'dict': List of dictionaries (default) - column names as keys
            - 'list': List of lists - values only, no column names
            - 'dataframe': Pandas DataFrame (if pandas is available)
        """
        if not data:
            # Return empty structure based on format
            if result_format == "dataframe":
                try:
                    import pandas as pd

                    return pd.DataFrame()
                except ImportError:
                    # Fall back to dict if pandas not available
                    return []
            elif result_format == "list":
                return []
            else:
                return []

        if result_format == "dict":
            # Already in dict format from adapters
            return data

        elif result_format == "list":
            # Convert to list of lists (values only)
            if data:
                # Get column order from first row
                columns = list(data[0].keys())
                return [[row.get(col) for col in columns] for row in data]
            return []

        elif result_format == "dataframe":
            # Convert to pandas DataFrame if available
            try:
                import pandas as pd

                return pd.DataFrame(data)
            except ImportError:
                # Log warning and fall back to dict format
                if hasattr(self, "logger"):
                    self.logger.warning(
                        "Pandas not installed. Install with: pip install pandas. "
                        "Falling back to dict format."
                    )
                return data

        else:
            # Unknown format - default to dict with warning
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"Unknown result_format '{result_format}', defaulting to 'dict'"
                )
            return data

    # =============================================================================
    # Enterprise Features and Monitoring Methods
    # =============================================================================
    # Note: get_pool_metrics() is already defined above at line 3630

    async def get_pool_analytics(self) -> Optional[Dict[str, Any]]:
        """Get comprehensive pool analytics summary.

        Returns:
            Dictionary with detailed analytics, or None if not available
        """
        try:
            adapter = await self._get_or_create_adapter()
            if hasattr(adapter, "get_analytics_summary"):
                return adapter.get_analytics_summary()
        except Exception as e:
            logger.warning(f"Failed to get pool analytics: {e}")

        return None

    async def health_check(self) -> Optional[HealthCheckResult]:
        """Perform connection pool health check.

        Returns:
            HealthCheckResult with health status, or None if not available
        """
        try:
            adapter = await self._get_or_create_adapter()
            if hasattr(adapter, "health_check"):
                return await adapter.health_check()
            else:
                # Fallback basic health check
                await self._execute_query_with_retry(adapter, "SELECT 1")
                return HealthCheckResult(is_healthy=True, latency_ms=0)
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return HealthCheckResult(
                is_healthy=False, latency_ms=0, error_message=str(e)
            )

    def get_circuit_breaker_state(self) -> Optional[Dict[str, Any]]:
        """Get circuit breaker state if available.

        Returns:
            Dictionary with circuit breaker state, or None if not available
        """
        try:
            if self._adapter and hasattr(self._adapter, "_enterprise_pool"):
                enterprise_pool = self._adapter._enterprise_pool
                if enterprise_pool and hasattr(enterprise_pool, "_circuit_breaker"):
                    return enterprise_pool._circuit_breaker.get_state()
        except Exception as e:
            logger.warning(f"Failed to get circuit breaker state: {e}")

        return None

    async def get_connection_usage_history(self) -> List[Dict[str, Any]]:
        """Get connection usage history for analysis.

        Returns:
            List of usage snapshots with timestamps and metrics
        """
        try:
            analytics = await self.get_pool_analytics()
            if analytics and "usage_history" in analytics:
                return analytics["usage_history"]
        except Exception as e:
            logger.warning(f"Failed to get usage history: {e}")

        return []

    async def force_pool_health_check(self) -> Dict[str, Any]:
        """Force immediate health check and return comprehensive status.

        Returns:
            Dictionary with health status, metrics, and diagnostic information
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "node_id": getattr(self, "id", "unknown"),
            "database_type": self.config.get("database_type", "unknown"),
            "health": None,
            "metrics": None,
            "circuit_breaker": None,
            "adapter_type": None,
            "error": None,
        }

        try:
            # Get health check result
            health = await self.health_check()
            result["health"] = (
                {
                    "is_healthy": health.is_healthy,
                    "latency_ms": health.latency_ms,
                    "error_message": health.error_message,
                    "checked_at": (
                        health.checked_at.isoformat() if health.checked_at else None
                    ),
                    "connection_count": health.connection_count,
                }
                if health
                else None
            )

            # Get metrics
            metrics = await self.get_pool_metrics()
            result["metrics"] = metrics.to_dict() if metrics else None

            # Get circuit breaker state
            result["circuit_breaker"] = self.get_circuit_breaker_state()

            # Get adapter type
            if self._adapter:
                result["adapter_type"] = type(self._adapter).__name__

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Force health check failed: {e}")

        return result

    async def get_enterprise_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive enterprise features status summary.

        Returns:
            Dictionary with complete enterprise features status
        """
        try:
            analytics = await self.get_pool_analytics()
            health = await self.health_check()
            circuit_breaker = self.get_circuit_breaker_state()

            return {
                "timestamp": datetime.now().isoformat(),
                "node_id": getattr(self, "id", "unknown"),
                "database_type": self.config.get("database_type", "unknown"),
                "enterprise_features": {
                    "analytics_enabled": self.config.get("enable_analytics", True),
                    "adaptive_sizing_enabled": self.config.get(
                        "enable_adaptive_sizing", True
                    ),
                    "circuit_breaker_enabled": self.config.get(
                        "circuit_breaker_enabled", True
                    ),
                    "health_check_interval": self.config.get(
                        "health_check_interval", 30
                    ),
                },
                "pool_configuration": {
                    "min_size": self.config.get("min_pool_size", 5),
                    "max_size": self.config.get("max_pool_size", 20),
                    "current_size": (
                        analytics["pool_config"]["current_size"] if analytics else 0
                    ),
                    "share_pool": self.config.get("share_pool", True),
                },
                "health_status": {
                    "is_healthy": health.is_healthy if health else False,
                    "latency_ms": health.latency_ms if health else 0,
                    "last_check": (
                        health.checked_at.isoformat()
                        if health and health.checked_at
                        else None
                    ),
                    "error": health.error_message if health else None,
                },
                "circuit_breaker": circuit_breaker,
                "performance_metrics": analytics["metrics"] if analytics else None,
                "recent_usage": (
                    analytics.get("usage_history", [])[-5:] if analytics else []
                ),
                "adapter_type": type(self._adapter).__name__ if self._adapter else None,
                "runtime_coordinated": (
                    getattr(self._adapter, "_runtime_coordinated", False)
                    if self._adapter
                    else False
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get enterprise status summary: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "node_id": getattr(self, "id", "unknown"),
                "error": str(e),
                "enterprise_features_available": False,
            }

    async def cleanup(self):
        """Clean up database connections."""
        try:
            # Check if we have a running event loop
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                # Event loop is closing, skip cleanup
                return
        except RuntimeError:
            # No event loop, skip cleanup
            return

        # Rollback any active transaction
        if self._active_transaction and self._adapter:
            try:
                await asyncio.wait_for(
                    self._adapter.rollback_transaction(self._active_transaction),
                    timeout=1.0,
                )
            except (Exception, asyncio.TimeoutError):
                pass  # Best effort cleanup
            self._active_transaction = None

        if self._adapter and self._connected:
            try:
                if self._share_pool and self._pool_key:
                    # TASK-141.8: Update disconnect() for per-pool locks
                    # Decrement reference count for shared pool with timeout
                    async with self._acquire_pool_lock_with_timeout(
                        self._pool_key, timeout=5.0
                    ):
                        if self._pool_key in self._shared_pools:
                            adapter, ref_count = self._shared_pools[self._pool_key]
                            if ref_count > 1:
                                # Others still using the pool
                                self._shared_pools[self._pool_key] = (
                                    adapter,
                                    ref_count - 1,
                                )
                            else:
                                # Last reference, close the pool
                                del self._shared_pools[self._pool_key]
                                await asyncio.wait_for(
                                    adapter.disconnect(), timeout=1.0
                                )
                else:
                    # Dedicated pool, close directly
                    await asyncio.wait_for(self._adapter.disconnect(), timeout=1.0)
            except (Exception, asyncio.TimeoutError):
                pass  # Best effort cleanup

            self._connected = False
            self._adapter = None

    def __del__(self):
        """Ensure connections are closed safely."""
        if self._adapter and self._connected:
            # Try to schedule cleanup, but be resilient to event loop issues
            try:
                import asyncio

                # Check if there's a running event loop that's not closed
                try:
                    loop = asyncio.get_running_loop()
                    if loop and not loop.is_closed():
                        # Create cleanup task only if loop is healthy
                        try:
                            loop.create_task(self.cleanup())
                        except RuntimeError as e:
                            # Loop might be closing, ignore gracefully
                            logger.debug(f"Could not schedule cleanup task: {e}")
                    else:
                        logger.debug("Event loop is closed, skipping async cleanup")
                except RuntimeError:
                    # No running event loop - this is normal during shutdown
                    logger.debug(
                        "No running event loop for cleanup, connections will be cleaned by GC"
                    )
            except Exception as e:
                # Complete fallback - any unexpected error should not crash __del__
                logger.debug(f"Error during connection cleanup: {e}")
                pass
