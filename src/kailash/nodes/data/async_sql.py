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
- Multiple fetch modes (one, all, many)
- Transaction management
- Timeout handling
- Retry logic with exponential backoff
"""

import asyncio
import contextlib
import inspect
import json
import logging
import os
import random
import re
import sys
import threading
import time
import traceback
import uuid
import warnings
import weakref
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
from kailash.nodes.data.exceptions import PoolExhaustedError
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from kailash.utils.loop_pool_registry import register_pool_drain_on_current_loop
from kailash.utils.url_credentials import redact_pool_key

logger = logging.getLogger(__name__)

# Import optimistic locking for version control. Only the symbols
# actually referenced downstream are imported here — ``ConflictResolution``
# and ``LockStatus``. ``OptimisticLockingNode`` was historically
# imported but never used; removed in arbor R3 to clear a CodeQL
# ``py/unused-import`` false positive at the import site.
try:
    from kailash.nodes.data.optimistic_locking import (
        ConflictResolution,  # type: ignore[assignment]
    )
    from kailash.nodes.data.optimistic_locking import (
        LockStatus,  # type: ignore[assignment]
    )

    OPTIMISTIC_LOCKING_AVAILABLE = True
except ImportError:
    OPTIMISTIC_LOCKING_AVAILABLE = False

try:
    from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
except ImportError:
    AsyncSQLitePool = None  # type: ignore[assignment,misc]
    SQLitePoolConfig = None  # type: ignore[assignment,misc]

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


# Default number of rows pulled per server-side-cursor round trip for
# ``stream()``. This is SEPARATE from ``fetch_size`` (which selects how many
# rows ``FetchMode.MANY`` materializes in a single ``execute()`` call); a
# streaming cursor keeps its connection open and pulls rows lazily in batches
# of this size so peak memory stays bounded regardless of result-set size.
DEFAULT_STREAM_BATCH_SIZE = 1000


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    # Retryable error patterns (database-specific)
    retryable_errors: Optional[list[str]] = None

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
        return any(
            pattern.lower() in error_str for pattern in (self.retryable_errors or [])
        )

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
    enable_analytics: bool = True
    enable_adaptive_sizing: bool = True
    health_check_interval: int = 30
    min_pool_size: int = 5
    # Issue #1741: optional per-physical-connection credential callback for
    # token-based DB auth (Azure AD / AWS IAM). When set, PostgreSQLAdapter.
    # connect() wires it into asyncpg's per-connection ``connect`` hook so a
    # FRESH credential is minted for EVERY physical connection (initial,
    # recycled, overflow, reconnect) — never the static ``password`` above.
    # Absent (None), behavior is UNCHANGED. A raising callback fails closed
    # (raises NodeExecutionError); it NEVER falls back to a stale token. The
    # returned value is a live secret — it MUST NEVER be logged (not the
    # value, not its length, not a prefix). See
    # kailash.nodes.data.credential_provider for the full contract.
    credential_provider: Optional[Callable[[], str]] = None

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
        idle_timeout: Optional[int] = None,
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
            idle_timeout: Per-pool idle-timeout override (seconds). When
                ``None`` (the default) the pool reads
                ``_POOL_DEFAULTS["idle_timeout"]`` at every
                ``is_idle()`` check, so process-wide
                ``set_pool_defaults`` overrides take effect immediately.
                Pass an explicit value to pin a single pool to a
                non-default timeout (rarely needed).
        """
        self.pool_id = pool_id
        self.database_config = database_config
        self.adapter_class = adapter_class
        self.min_size = min_size
        self.max_size = max_size
        self._shutdown = False  # Shutdown flag for background tasks
        self.initial_size = initial_size
        self.health_check_interval = health_check_interval
        # DPI-B3: per-pool idle override; None means "follow process default"
        self._idle_timeout_override: Optional[int] = idle_timeout
        # DPI-B3: monotonic timestamp of last get_connection() call.
        # Initialised to "now" so a freshly-created pool is not
        # immediately reaped on the first reaper iteration.
        self._last_activity_at: float = time.monotonic()
        # DPI-B3: forensic counter — operators see "how many pools have
        # we reaped" via this on health/diagnostic dumps.
        self._reaped_count: int = 0
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
            # DPI-B3: refresh idle timestamp; the reaper uses this to
            # decide whether to close the pool.
            self._last_activity_at = time.monotonic()

            return connection

        except Exception as e:
            self._circuit_breaker.record_failure()
            with self._metrics_lock:
                self._metrics.connections_failed += 1
            logger.error(f"Failed to get connection from pool '{self.pool_id}': {e}")
            raise

    @property
    def idle_timeout(self) -> int:
        """Effective idle timeout for this pool (seconds, DPI-B3).

        Returns the per-pool override if one was passed at construction;
        otherwise reads ``_POOL_DEFAULTS["idle_timeout"]`` so process-wide
        ``set_pool_defaults`` calls take effect immediately on existing
        pools without requiring re-instantiation.
        """
        if self._idle_timeout_override is not None:
            return self._idle_timeout_override
        return _POOL_DEFAULTS["idle_timeout"]

    def is_idle(self, now: Optional[float] = None) -> bool:
        """Return True when the pool's last activity is older than the timeout.

        Args:
            now: Optional monotonic timestamp to compare against. When
                ``None`` the function calls ``time.monotonic()``
                itself. Tests that need deterministic time-warping
                pass an explicit value.

        Returns:
            bool: True when ``now - self._last_activity_at >=
                self.idle_timeout``. False on a freshly-created pool
                (the constructor seeds ``_last_activity_at = now``).
        """
        if now is None:
            now = time.monotonic()
        return (now - self._last_activity_at) >= self.idle_timeout

    async def _get_pool_connection(self):
        """Get connection from the underlying pool (adapter-specific)."""
        if hasattr(self._pool, "acquire"):
            # asyncpg style pool
            return self._pool.acquire()  # type: ignore[union-attr]
        elif hasattr(self._pool, "get_connection"):
            # aiomysql style pool
            return self._pool.get_connection()  # type: ignore[union-attr]
        else:
            # Direct adapter access for SQLite
            return self._adapter._get_connection()  # type: ignore[union-attr]

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic (Node ABC contract)."""
        return self.execute(**kwargs)

    async def execute_query(
        self, query: str, params: Optional[Union[tuple, dict]] = None, **kwargs
    ) -> Any:
        """Execute query with performance tracking."""
        start_time = time.time()

        try:
            assert self._adapter is not None
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
                return len(self._pool)  # type: ignore[arg-type]
            elif hasattr(self._pool, "size"):
                return self._pool.size  # type: ignore[union-attr]
            elif hasattr(self._pool, "_size"):
                return self._pool._size  # type: ignore[union-attr]
            else:
                return 0
        except Exception:
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


class _AdapterTransactionScope:
    """Scope yielded by :meth:`DatabaseAdapter.transaction`.

    Exposes the surface DataFlow's transaction nodes and every dialect-level
    ``adapter.transaction()`` already rely on: a live ``.connection`` to run
    statements on (savepoints, in-transaction queries) plus explicit async
    ``.commit()`` / ``.rollback()``. It wraps the adapter's
    ``begin/commit/rollback_transaction`` primitives so both are driven through
    one uniform contract. ``.commit()`` / ``.rollback()`` are idempotent — a
    caller that commits explicitly and then lets the context manager exit does
    NOT double-commit or double-release the connection.
    """

    def __init__(self, adapter: "DatabaseAdapter", txn: Any):
        self._adapter = adapter
        self._txn = txn
        # PostgreSQL returns ``(conn, tx)`` and SQLite ``(conn, savepoint, depth)``;
        # MySQL returns the connection directly. The live connection is the first
        # element of the tuple, or the value itself.
        self.connection = txn[0] if isinstance(txn, tuple) else txn
        self._committed = False
        self._rolled_back = False

    async def commit(self) -> None:
        if self._committed or self._rolled_back:
            return
        # Single-shot: mark terminal BEFORE the await. A commit_transaction that
        # partially completes then raises mid-teardown (e.g. SQLite ``db.close()``
        # after the depth decrement, or PG ``pool.release`` after ``tx.commit``)
        # MUST NOT let a fallback ``__aexit__`` re-enter ``rollback`` over the
        # half-torn-down transaction — that double-decrements the SQLite nesting
        # depth (issue #1070 class) / double-releases the pooled connection. The
        # exception still propagates to the caller; the scope is simply spent.
        self._committed = True
        await self._adapter.commit_transaction(self._txn)

    async def rollback(self) -> None:
        if self._committed or self._rolled_back:
            return
        # Single-shot (see commit above): an attempted rollback is terminal even
        # if the primitive raises mid-teardown.
        self._rolled_back = True
        await self._adapter.rollback_transaction(self._txn)

    @property
    def transaction(self) -> Any:
        """The raw adapter transaction handle for ``adapter.execute(transaction=...)``.

        This is the same object ``adapter.begin_transaction()`` returns — the
        exact shape the ``execute`` / ``execute_many`` ``transaction=`` kwarg
        expects. DataFlow's generated CRUD nodes read this off the
        workflow-context scope (``active_transaction``) and pass it into
        ``AsyncSQLDatabaseNode.async_run(transaction=...)`` so a CRUD statement
        joins the scope's transaction instead of opening its own auto-commit
        transaction (#1581). Exposed as a property so callers never reach into
        the private ``_txn`` attribute.
        """
        return self._txn


class _AdapterTransactionContext:
    """Async context manager returned by :meth:`DatabaseAdapter.transaction`.

    On enter, opens a transaction via ``adapter.begin_transaction()`` and yields
    an :class:`_AdapterTransactionScope`. On exit it commits when the body left
    cleanly and rolls back when an exception propagated — both idempotent, so an
    explicit ``scope.commit()`` inside the body makes the exit a no-op.
    """

    def __init__(self, adapter: "DatabaseAdapter"):
        self._adapter = adapter
        self._scope: Optional[_AdapterTransactionScope] = None

    async def __aenter__(self) -> "_AdapterTransactionScope":
        txn = await self._adapter.begin_transaction()
        self._scope = _AdapterTransactionScope(self._adapter, txn)
        return self._scope

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._scope is None:
            return False
        try:
            if exc_type is None:
                await self._scope.commit()
            else:
                await self._scope.rollback()
        except Exception as cleanup_error:
            if exc_type is None:
                # Clean body: a commit failure IS the error the caller must see.
                raise
            # Body already raising: log the rollback failure but let the ORIGINAL
            # exception propagate — never mask the real cause with a cleanup error
            # (mirrors dataflow PostgreSQLTransaction.__aexit__).
            logger.error(
                "async_sql.transaction_context.cleanup_failed",
                extra={"cleanup_error": str(cleanup_error)},
                exc_info=True,
            )
        return False


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool = None
        self._connected: bool = False
        self._runtime_coordinated: bool = False
        self._runtime_pool: Any | None = None

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
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute query and return results, optionally within a transaction."""
        pass

    @abstractmethod
    def stream(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    ) -> "contextlib.AbstractAsyncContextManager":
        """Stream query results lazily via a server-side cursor.

        Returns an async context manager whose ``__aenter__`` yields an async
        iterator of rows. Each yielded row is a ``dict`` already passed through
        ``self._convert_row`` — byte-identical to a row materialized by
        ``execute(..., fetch_mode=FetchMode.ALL)``.

        LIFETIME CONTRACT (load-bearing): the underlying connection (and, for
        PostgreSQL, the wrapping transaction) MUST stay OPEN for the entire
        duration of iteration. The connection/transaction are owned by the
        context-manager body and are NOT released until ``__aexit__`` — which
        MUST release them on normal completion, early ``break``, AND exception
        unwind. This is exactly why streaming cannot be a value returned from
        ``execute()``: a returned cursor would outlive its connection scope.

        Streaming does NOT use the node's retry logic: a transient failure may
        be retried only during the connect + cursor-open phase (before the
        first row is yielded). Once the first row has been yielded, errors
        propagate to the caller — re-driving the query mid-iteration would
        double-yield already-consumed rows.

        Args:
            query: SQL query to stream. Parameters arrive positionally by the
                time they reach the adapter (the node converts dict→named→
                positional), mirroring ``execute``.
            params: Query parameters (tuple/list positional, or dict for the
                PostgreSQL ``:name`` style mirrored from ``execute``).
            batch_size: Rows pulled per server-round-trip / ``fetchmany`` chunk
                (prefetch for asyncpg). Bounds peak memory.

        Yields:
            dict: One converted row at a time.
        """
        raise NotImplementedError  # pragma: no cover - abstract

    @abstractmethod
    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
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

    def transaction(self) -> "_AdapterTransactionContext":
        """Return an async context manager for a transaction scope.

        Yields an :class:`_AdapterTransactionScope` with a live ``.connection``
        plus explicit async ``.commit()`` / ``.rollback()``, wrapping this
        adapter's ``begin/commit/rollback_transaction`` primitives. Every
        adapter that implements those three primitives therefore exposes one
        uniform ``transaction()`` contract — matching the dialect-level
        ``adapter.transaction()`` the DataFlow transaction nodes rely on::

            async with adapter.transaction() as txn:
                await txn.connection.execute("INSERT ...")
                # commits on clean exit, rolls back if the block raises
        """
        return _AdapterTransactionContext(self)


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

        async def _init_connection(conn):
            """Set session-level parameters on each new connection."""
            await conn.execute("SET idle_in_transaction_session_timeout = '30s'")
            await conn.execute("SET statement_timeout = '60s'")

        create_pool_kwargs = dict(
            min_size=1,
            max_size=self.config.max_pool_size,
            timeout=self.config.pool_timeout,
            command_timeout=self.config.command_timeout,
            max_inactive_connection_lifetime=300.0,
            init=_init_connection,
        )

        if self.config.credential_provider is not None:
            # Issue #1741: token-based DB auth (Azure AD / AWS IAM). Mint a
            # FRESH credential per physical connection via asyncpg's per-
            # connection ``connect`` hook — this is the CRUD hot-path pool the
            # db.express / db.transactions / bulk path actually opens. The
            # helper's fail-closed contract (raise, never fall back to a stale
            # token) and no-secret-in-logs guarantee live in
            # kailash.nodes.data.credential_provider.
            from kailash.nodes.data.credential_provider import (
                build_asyncpg_credential_connect,
            )

            create_pool_kwargs["connect"] = build_asyncpg_credential_connect(
                self.config.credential_provider, asyncpg, context="PostgreSQL"
            )
            try:
                self._pool = await asyncpg.create_pool(dsn, **create_pool_kwargs)
            except Exception as exc:
                # Redacting guard: the DSN embeds a password and a raising
                # provider surfaces here on the initial fill. Do NOT log the
                # DSN / exc_info and sever the cause chain (``from None``) so
                # no credential material (static password OR minted token)
                # reaches a traceback (security.md "No secrets in logs").
                raise NodeExecutionError(
                    "Failed to create PostgreSQL connection pool with "
                    f"credential_provider ({type(exc).__name__})"
                ) from None
        else:
            # None path: behavior is UNCHANGED from before #1741.
            self._pool = await asyncpg.create_pool(dsn, **create_pool_kwargs)
        # Issue #1572: if this pool was created on a transient bridge loop,
        # register ``disconnect`` so the bridge drains it before closing the
        # loop (no-op on a persistent app loop — the marker gates it).
        register_pool_drain_on_current_loop(self.disconnect)

    async def disconnect(self) -> None:
        """Close connection pool (idempotent)."""
        if self._pool:
            await self._pool.close()
            # Null the pool so a later cleanup()/bridge-drain double-close is a
            # guarded no-op (issue #1572).
            self._pool = None

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

            params = tuple(query_params)

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
            params = tuple()
        elif not isinstance(params, (list, tuple)):
            params = (params,)

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
            else:
                raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")
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
                else:
                    raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")

    @contextlib.asynccontextmanager
    async def stream(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    ):
        """Stream PostgreSQL rows via an asyncpg server-side cursor.

        asyncpg's ``connection.cursor()`` requires an explicit transaction —
        the transaction + acquired connection are held open by THIS context
        manager for the full duration of iteration and released on
        ``__aexit__`` (normal completion, early ``break``, or exception
        unwind). ``prefetch`` bounds how many rows asyncpg buffers per
        server round trip.

        Dict params are converted to positional ``$N`` placeholders mirroring
        ``execute`` (asyncpg has no native named-parameter support).
        """
        # Mirror execute()'s dict→positional ($N) conversion so a streamed
        # query accepts the same param shapes the materialized path does.
        if isinstance(params, dict):
            query, positional = self._convert_named_to_positional(query, params)
            params = positional
        elif params is None:
            params = ()
        elif not isinstance(params, (list, tuple)):
            params = (params,)

        async def _iter_rows(conn):
            # asyncpg server-side cursor — REQUIRES an open transaction.
            async with conn.transaction():
                cur = conn.cursor(query, *params, prefetch=batch_size)
                async for record in cur:
                    yield self._convert_row(dict(record))

        async with self._pool.acquire() as conn:
            yield _iter_rows(conn)

    def _convert_named_to_positional(
        self, query: str, params: dict
    ) -> tuple[str, tuple]:
        """Convert a ``:name`` dict-param query to asyncpg ``$N`` positional.

        Mirrors the dict-handling half of ``execute`` (longest-key-first
        replacement to avoid prefix collisions, bool/int explicit casts to
        avoid asyncpg type-inference ambiguity), but returns the rewritten
        query + positional tuple instead of executing.
        """
        original_items = list(params.items())
        query_params = []
        for _key, value in original_items:
            if isinstance(value, dict):
                value = json.dumps(value)
            query_params.append(value)

        # Replace longer keys first so ":userid" isn't clobbered by ":user".
        keys_by_length = sorted(params.keys(), key=len, reverse=True)
        for key in keys_by_length:
            position = (
                next(i for i, (k, _v) in enumerate(original_items) if k == key) + 1
            )
            value = original_items[position - 1][1]
            if isinstance(value, bool):
                query = query.replace(f":{key}", f"${position}::boolean")
            elif isinstance(value, int):
                query = query.replace(f":{key}", f"${position}::integer")
            else:
                query = query.replace(f":{key}", f"${position}")

        return query, tuple(query_params)

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
        started = False
        try:
            tx = conn.transaction()
            await tx.start()
            started = True
            return (conn, tx)
        finally:
            if not started:
                # Release the pooled connection if the transaction fails to
                # start (or the start is cancelled) — otherwise a repeated
                # BEGIN-failure workload orphans connections and drains the
                # bounded pool. This is the begin half of the acquire->teardown
                # window; commit_transaction / rollback_transaction guard the
                # commit/rollback half (issue #1580 redteam).
                await self._release_quietly(conn)

    async def _release_quietly(self, conn: Any) -> None:
        """Return ``conn`` to the pool, logging (not raising) a release error.

        A release failure MUST NOT mask the in-flight driver error the caller
        needs (e.g. the serialization failure it keys a retry on); asyncpg
        already terminates + reclaims the pool slot on a release error, so
        logging is the correct disposition (issue #1580 redteam LOW).
        """
        try:
            await self._pool.release(conn)
        except Exception:
            logger.error("async_sql.postgresql.pool_release_failed", exc_info=True)

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        conn, tx = transaction
        try:
            await tx.commit()
        finally:
            # Always return the connection to the bounded pool, even if the
            # driver commit raises (serialization failure, deferred-constraint
            # violation fired at COMMIT, mid-commit connection loss). Without the
            # finally the connection is orphaned and the pool drains under a
            # repeated commit-failure workload (issue #1580 redteam MEDIUM). The
            # caller MUST NOT also roll back after a failed commit — this
            # primitive self-releases (issue #1580 redteam HIGH).
            await self._release_quietly(conn)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        conn, tx = transaction
        try:
            await tx.rollback()
        finally:
            # Release even if the driver rollback raises (see commit_transaction).
            await self._release_quietly(conn)


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
            from urllib.parse import urlparse

            from kailash.utils.url_credentials import (
                decode_userinfo_or_raise,
                preencode_password_special_chars,
            )

            # Pre-encode raw ``#$@?`` in password so operators who paste
            # a literal DATABASE_URL without URL-encoding their special
            # characters still get a working parse — see the helper's
            # docstring for the Arbor P3 provenance.
            conn_str = preencode_password_special_chars(self.config.connection_string)
            parsed = urlparse(conn_str)

            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            # Decode username/password and reject null bytes in the
            # decoded credentials via the shared helper — see
            # ``kailash/utils/url_credentials.py``.
            user, password = decode_userinfo_or_raise(parsed, default_user="root")
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
            minsize=min(5, self.config.max_pool_size),
            maxsize=self.config.max_pool_size,
            pool_recycle=3600,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=10,
        )
        # Issue #1572: if this pool was created on a transient bridge loop,
        # register ``disconnect`` so the bridge drains it before closing the
        # loop (no-op on a persistent app loop — the marker gates it).
        register_pool_drain_on_current_loop(self.disconnect)

    async def disconnect(self) -> None:
        """Close connection pool (idempotent)."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            # Null the pool so a later cleanup()/bridge-drain double-close is a
            # guarded no-op (issue #1572).
            self._pool = None

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
                    raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")
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
                    else:
                        raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")

    @contextlib.asynccontextmanager
    async def stream(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    ):
        """Stream MySQL rows via an UNBUFFERED ``aiomysql.SSCursor``.

        ``SSCursor`` does not buffer the whole result set client-side — rows
        are pulled from the server in ``batch_size`` chunks via ``fetchmany``.
        The cursor holds the server-side result set, so the lifecycle ORDER is
        load-bearing on every exit path (completion / early ``break`` /
        exception unwind):

        1. the SSCursor is opened and closed in THIS context-manager body (not
           the inner row generator) so ``cursor.close()`` sequences strictly
           before the connection is released;
        2. the read transaction is rolled back before the connection returns
           to the pool — the pool runs ``autocommit=False``, so a streamed
           SELECT leaves an open read transaction; returning the connection
           dirty makes the NEXT query (especially DDL, which implicitly
           commits) block on the prior open transaction.

        Closing the SSCursor before draining (early break) also discards the
        remaining server-side rows so the connection is not left mid-result.
        The acquired connection is held open by this CM for the whole
        iteration and released on exit.
        """
        import aiomysql

        async def _iter_rows(cursor, columns):
            while True:
                batch = await cursor.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    yield self._convert_row(dict(zip(columns, row)))

        async with self._pool.acquire() as conn:
            cursor = await conn.cursor(aiomysql.SSCursor)
            try:
                await cursor.execute(query, params)
                columns = [d[0] for d in cursor.description]
                yield _iter_rows(cursor, columns)
            finally:
                # Close the SSCursor FIRST (discards any unread server-side
                # rows on an early break), THEN clear the read transaction so
                # the connection returns to the pool clean.
                await cursor.close()
                try:
                    await conn.rollback()
                except Exception:  # noqa: BLE001 - best-effort txn reset
                    # A rollback failure here must not mask the real exception
                    # being unwound; the connection will be recycled by the
                    # pool's own health check. Logged for triage.
                    logger.warning(
                        "async_sql.mysql_stream.rollback_failed",
                        exc_info=True,
                    )

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
        started = False
        try:
            await conn.begin()
            started = True
            return conn
        finally:
            if not started:
                # Release if BEGIN fails/cancels — otherwise a repeated
                # BEGIN-failure workload orphans connections and drains the
                # bounded pool (see PostgreSQLAdapter.begin_transaction,
                # issue #1580 redteam).
                await self._release_quietly(conn)

    async def _release_quietly(self, conn: Any) -> None:
        """Return ``conn`` to the pool, logging (not raising) a release error.

        A release failure MUST NOT mask the in-flight driver error the caller
        needs (issue #1580 redteam LOW; see PostgreSQLAdapter._release_quietly).
        """
        try:
            await self._pool.release(conn)
        except Exception:
            logger.error("async_sql.mysql.pool_release_failed", exc_info=True)

    async def commit_transaction(self, transaction: Any) -> None:
        """Commit a transaction."""
        try:
            await transaction.commit()
        finally:
            # Always return the connection to the bounded pool even if the driver
            # commit raises — otherwise the connection is orphaned and the pool
            # drains under repeated commit failures (issue #1580 redteam MEDIUM).
            # The caller MUST NOT also roll back after a failed commit — this
            # primitive self-releases (issue #1580 redteam HIGH).
            await self._release_quietly(transaction)

    async def rollback_transaction(self, transaction: Any) -> None:
        """Rollback a transaction."""
        try:
            await transaction.rollback()
        finally:
            # Release even if the driver rollback raises (see commit_transaction).
            await self._release_quietly(transaction)


class SQLiteAdapter(DatabaseAdapter):
    """SQLite adapter using aiosqlite."""

    # URI shared-cache mode replaces the old _shared_memory_connections dict.
    # Each :memory: DB is translated to file:memdb_NAME?mode=memory&cache=shared
    # so multiple connections see the SAME in-memory database.

    # Essential PRAGMAs applied to every connection (mirrors Rust SDK's after_connect hook)
    _DEFAULT_PRAGMAS = {
        "journal_mode": "WAL",
        "busy_timeout": "5000",
        "synchronous": "NORMAL",
        "cache_size": "-65536",  # 64MB (negative = KiB)
        "foreign_keys": "ON",
    }

    def __init__(self, config: DatabaseConfig, memory_db_name: Optional[str] = None):
        """Initialize SQLite adapter."""
        super().__init__(config)
        # Initialize SQLite-specific attributes
        self._db_path = config.connection_string or config.database or ":memory:"
        self._is_memory_db = (
            self._db_path == ":memory:" or "mode=memory" in self._db_path
        )
        self._connect_kwargs: dict[str, Any] = {}
        self._connection = None
        self._memory_db_name = memory_db_name
        # Connection pool (initialized in connect())
        self._pool: Any | None = None
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
                if "?" in conn_str:
                    # URI with parameters — preserve full string (e.g. file:db?mode=memory&cache=shared)
                    self._db_path = conn_str
                    self._connect_kwargs["uri"] = True
                else:
                    # Simple file: prefix — strip it
                    self._db_path = conn_str[5:]
            else:
                # Assume the connection string IS the path
                self._db_path = conn_str
        else:
            raise NodeExecutionError(
                "SQLite requires either 'database' path or 'connection_string'"
            )

        # Detect memory databases and translate to URI shared-cache mode.
        # Each aiosqlite.connect(":memory:") creates a SEPARATE database.
        # URI shared-cache mode lets multiple connections see the SAME in-memory DB.
        self._is_memory_db = (
            self._db_path == ":memory:" or "mode=memory" in self._db_path
        )
        if self._db_path == ":memory:":
            name = self._memory_db_name or f"kailash_{id(self)}"
            self._db_path = f"file:{name}?mode=memory&cache=shared"
            self._connect_kwargs["uri"] = True

        # Note: The Core SDK SQLiteAdapter intentionally does NOT create
        # an AsyncSQLitePool here.  When used inside ProductionSQLiteAdapter
        # + EnterpriseConnectionPool, each internal adapter would create its
        # own pool, leading to dozens of persistent connections targeting the
        # same file and "database is locked" errors.  Instead, connections
        # are created on-demand in execute() and closed after each query.
        # The DataFlow SQLiteAdapter (apps/kailash-dataflow) is the correct
        # place for pool-based connection management.

    async def _configure_connection(self, conn):
        """Apply essential PRAGMAs to a new connection.

        Mirrors the Rust SDK's after_connect hook — every connection gets WAL,
        busy_timeout, synchronous=NORMAL, cache_size, and foreign_keys before
        any user query runs.
        """
        for pragma, value in self._DEFAULT_PRAGMAS.items():
            if self._is_memory_db and pragma == "journal_mode":
                continue  # WAL not supported for shared-cache memory DBs
            await conn.execute(f"PRAGMA {pragma} = {value}")

    async def _get_connection(self):
        """Get a database connection.

        For memory databases, uses URI shared-cache mode so all connections
        see the same in-memory database. For file databases, uses the pool
        for connection reuse and bounded thread count.
        """
        assert self._aiosqlite is not None
        if self._is_memory_db:
            # Issue #1051: one reused connection per adapter instance for
            # :memory:. The non-pool memory path (execute/execute_many/
            # begin_transaction) calls _get_connection() per query; creating
            # a fresh aiosqlite.connect() each time leaked every one of them
            # because disconnect() only closes self._pool, which is None for
            # :memory: by design. The "shared connection for memory databases"
            # comments and the "don't close shared memory connections"
            # transaction paths already assume a single reused connection —
            # self._connection (set None at __init__) is the tracking slot
            # this completes. disconnect() now owns its lifecycle.
            if self._connection is None:
                self._connection = await self._aiosqlite.connect(
                    self._db_path, **self._connect_kwargs
                )
                self._connection.row_factory = self._aiosqlite.Row
                await self._configure_connection(self._connection)
            return self._connection
        conn = await self._aiosqlite.connect(self._db_path, **self._connect_kwargs)
        conn.row_factory = self._aiosqlite.Row
        await self._configure_connection(conn)
        return conn

    async def disconnect(self) -> None:
        """Close pool and connections."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        # Issue #1051: close the reused :memory: connection (untracked by the
        # pool path, which is None for :memory:). Without this it survives to
        # GC and aiosqlite.Connection.__del__ emits a ResourceWarning.
        if self._connection is not None:
            try:
                await self._connection.close()
            finally:
                self._connection = None

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
        assert self._aiosqlite is not None
        if transaction:
            # Handle both old API (just connection) and new API (tuple)
            # begin_transaction() returns (db, savepoint_name, depth) tuple
            if isinstance(transaction, tuple):
                db, _savepoint_name, _depth = transaction
            else:
                db = transaction
            cursor = await db.execute(query, params or [])

            try:
                # Detect DML operations (DELETE/UPDATE/INSERT) to capture rowcount
                query_type = query.strip().upper().split()[0] if query.strip() else ""

                if (
                    query_type in ("DELETE", "UPDATE", "INSERT")
                    and "RETURNING" not in query.upper()
                ):
                    # Capture rowcount for DML operations.
                    # RETURNING queries fall through so the returned rows are
                    # fetched (parity with the PostgreSQL adapter guard above);
                    # without this, SQLite upsert/INSERT ... RETURNING silently
                    # discarded the row and returned {"rows_affected": 0}.
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
                    raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")

                # Check if this was an INSERT and capture lastrowid for SQLite
                if query_type == "INSERT" and (
                    not result or result == [] or result is None
                ):
                    # For INSERT without RETURNING, capture lastrowid
                    lastrowid = (
                        cursor.lastrowid if hasattr(cursor, "lastrowid") else None
                    )
                    if lastrowid is not None:
                        return {"lastrowid": lastrowid}

                return result
            finally:
                # Close cursor to release the underlying SQLite statement.
                # Without this, subsequent commits fail with
                # "cannot commit transaction - SQL statements in progress".
                await cursor.close()
        else:
            # Use pool for connection management (handles both memory and file DBs)
            if self._pool is not None:
                async with self._pool.acquire(query) as db:
                    return await self._execute_on_connection(
                        db, query, params, fetch_mode, fetch_size
                    )
            elif self._is_memory_db:
                # Fallback: shared connection for memory databases (no pool)
                db = await self._get_connection()
                return await self._execute_on_connection(
                    db, query, params, fetch_mode, fetch_size
                )
            else:
                # Fallback: inline connection for file databases (no pool)
                async with self._aiosqlite.connect(
                    self._db_path, **self._connect_kwargs
                ) as db:
                    db.row_factory = self._aiosqlite.Row
                    await self._configure_connection(db)
                    return await self._execute_on_connection(
                        db, query, params, fetch_mode, fetch_size
                    )

    async def _execute_on_connection(
        self,
        db: Any,
        query: str,
        params: Optional[Union[tuple, dict]],
        fetch_mode: "FetchMode",
        fetch_size: Optional[int],
    ) -> Any:
        """Execute a query on an existing connection and return results."""
        cursor = await db.execute(query, params or [])
        query_type = query.strip().upper().split()[0] if query.strip() else ""

        if (
            query_type in ("DELETE", "UPDATE", "INSERT")
            and "RETURNING" not in query.upper()
        ):
            # RETURNING queries fall through to the fetch below so the returned
            # rows survive (parity with the PostgreSQL adapter guard).
            rowcount = cursor.rowcount if hasattr(cursor, "rowcount") else 0
            await db.commit()
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
            raise ValueError(f"Unsupported fetch_mode: {fetch_mode}")

        if query_type == "INSERT" and (not result or result == []):
            lastrowid = cursor.lastrowid if hasattr(cursor, "lastrowid") else None
            if lastrowid is not None:
                await db.commit()
                return {"lastrowid": lastrowid}

        await db.commit()
        return result

    @contextlib.asynccontextmanager
    async def stream(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
    ):
        """Stream SQLite rows via a chunked ``fetchmany`` loop.

        SQLite has no true server-side cursor; ``fetchmany(batch_size)`` bounds
        peak Python-object memory by pulling at most ``batch_size`` rows per
        round trip. The connection is reused from the pool / shared-memory
        helper / inline-file path (mirroring ``execute``).

        Cursor + connection lifecycle ORDER is load-bearing: the cursor MUST
        be closed BEFORE its connection is released, on every exit path
        (normal completion, early ``break``, exception unwind). The cursor is
        therefore opened and closed in THIS context-manager body — not inside
        the row-yielding inner generator — so the explicit ``await
        cursor.close()`` sequences strictly before the connection's
        ``__aexit__`` runs. The shared ``:memory:`` connection is NEVER closed
        here — ``disconnect()`` owns that connection's lifecycle (issue #1051).
        """
        assert self._aiosqlite is not None

        async def _iter_rows(cursor):
            while True:
                batch = await cursor.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    yield self._convert_row(dict(row))

        if self._pool is not None:
            # Pool path: hold the acquired connection open for the whole
            # iteration. ``acquire`` keeps the connection checked out until
            # the ``async with`` block exits (i.e. __aexit__).
            async with self._pool.acquire(query) as db:
                cursor = await db.execute(query, params or [])
                try:
                    yield _iter_rows(cursor)
                finally:
                    await cursor.close()
        elif self._is_memory_db:
            # Shared :memory: connection — owned by disconnect(); do NOT close.
            db = await self._get_connection()
            cursor = await db.execute(query, params or [])
            try:
                yield _iter_rows(cursor)
            finally:
                await cursor.close()
        else:
            # File DB with no pool — own the connection for the iteration's
            # lifetime; the ``async with aiosqlite.connect`` closes it on
            # __aexit__. The cursor is closed FIRST (the explicit finally
            # below), then the connection, so an early break never closes a
            # connection out from under a still-open cursor.
            async with self._aiosqlite.connect(
                self._db_path, **self._connect_kwargs
            ) as db:
                db.row_factory = self._aiosqlite.Row
                await self._configure_connection(db)
                cursor = await db.execute(query, params or [])
                try:
                    yield _iter_rows(cursor)
                finally:
                    await cursor.close()

    async def execute_many(
        self,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> None:
        """Execute query multiple times with different parameters."""
        assert self._aiosqlite is not None
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
            if self._pool is not None:
                async with self._pool.acquire_write() as db:
                    await db.executemany(query, params_list)
                    await db.commit()
            elif self._is_memory_db:
                db = await self._get_connection()
                await db.executemany(query, params_list)
                await db.commit()
            else:
                async with self._aiosqlite.connect(
                    self._db_path, **self._connect_kwargs
                ) as db:
                    await self._configure_connection(db)
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
        assert self._aiosqlite is not None
        if self._is_memory_db:
            # Use shared connection for memory databases
            db = await self._get_connection()
        else:
            # Create new connection for file databases
            db = await self._aiosqlite.connect(self._db_path, **self._connect_kwargs)
            db.row_factory = self._aiosqlite.Row
            await self._configure_connection(db)

        # Issue #1070: capture pre-call state so the abort path can restore it
        # exactly. Without a try/except here, a caller cancelled/raising
        # *between* begin_transaction() and its paired commit/rollback leaves
        # _transaction_depth > 0 and the underlying :memory: connection
        # mid-BEGIN. Because :memory: reuses one per-adapter connection, the
        # NEXT begin_transaction() then observes depth > 0, takes the SAVEPOINT
        # branch, and issues SAVEPOINT against a poisoned outer transaction.
        depth_before = self._transaction_depth
        savepoint_counter_before = self._savepoint_counter

        # Check current transaction depth
        if self._transaction_depth == 0:
            # First transaction - use BEGIN IMMEDIATE to acquire write lock
            # immediately, preventing "database is locked" under concurrency.
            # Mirrors the Rust SDK's begin_immediate() API.
            try:
                await db.execute("BEGIN IMMEDIATE")
                self._transaction_depth += 1
                return (db, None, self._transaction_depth)
            except BaseException:
                # BaseException (not Exception) so asyncio.CancelledError is
                # also caught — cancellation is the primary trigger for #1070.
                await self._abort_begin(
                    db,
                    savepoint_name=None,
                    depth_before=depth_before,
                    savepoint_counter_before=savepoint_counter_before,
                )
                raise
        else:
            # Nested transaction - use SAVEPOINT
            savepoint_name = f"sp_{self._savepoint_counter + 1}"
            try:
                self._savepoint_counter += 1
                await db.execute(f"SAVEPOINT {savepoint_name}")
                self._transaction_depth += 1
                return (db, savepoint_name, self._transaction_depth)
            except BaseException:
                await self._abort_begin(
                    db,
                    savepoint_name=savepoint_name,
                    depth_before=depth_before,
                    savepoint_counter_before=savepoint_counter_before,
                )
                raise

    async def _abort_begin(
        self,
        db: Any,
        *,
        savepoint_name: Optional[str],
        depth_before: int,
        savepoint_counter_before: int,
    ) -> None:
        """Restore transaction state after begin_transaction() is aborted.

        Issue #1070: invoked when a caller is cancelled or raises *between*
        begin_transaction() and its paired commit/rollback. Resets the
        instance nesting counters to their pre-call values AND rolls back the
        underlying connection so the NEXT begin_transaction() on the same
        adapter starts from a clean outer-transaction state.

        For the :memory: shared-connection path the connection MUST NOT be
        closed — closing destroys the in-memory database (per the SQLite
        connection-management contract). Only the transaction state is
        unwound: ROLLBACK TO / RELEASE for the nested SAVEPOINT case, or
        ROLLBACK of the outer transaction for the first-transaction case.

        This method MUST NOT mask the original cancellation/exception — the
        caller re-raises immediately after this returns. Any failure while
        unwinding the connection is logged at WARN and swallowed (the
        connection is already in an error/aborting state; the original
        exception is the one that matters).
        """
        # 1. Restore the instance nesting counters to pre-call values so the
        #    next begin_transaction() takes the correct (BEGIN vs SAVEPOINT)
        #    branch.
        self._transaction_depth = depth_before
        self._savepoint_counter = savepoint_counter_before

        # 2. Unwind the underlying connection so it is no longer mid-BEGIN /
        #    mid-SAVEPOINT. Closing is deliberately NOT done here: for
        #    :memory: it would destroy the shared in-memory DB; for file DBs
        #    the per-call connection is discarded by the caller's failure path
        #    and GC, and ROLLBACK leaves it in a consistent state regardless.
        try:
            if savepoint_name is not None:
                # Nested abort: undo just the savepoint we created, leaving
                # the outer transaction (owned by an outer caller) intact.
                await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            else:
                # Outer abort: roll back the transaction this aborted
                # begin_transaction() opened (or attempted to open).
                await db.rollback()
        except BaseException as unwind_error:  # noqa: BLE001
            # The connection may already be in an aborted state (e.g. the
            # BEGIN itself failed). Surface it at WARN for observability but
            # do NOT raise — the original exception is re-raised by the
            # caller and is the one operators must see.
            logger.warning(
                "sqlite.begin_transaction.abort_unwind_failed",
                extra={
                    "savepoint_name": savepoint_name,
                    "depth_restored_to": depth_before,
                    "unwind_error": str(unwind_error),
                },
            )

    async def _close_quietly(self, db: Any) -> None:
        """Close ``db``, logging (not raising) a close error.

        A close failure in a terminal ``finally`` MUST NOT replace the in-flight
        driver commit/rollback error the caller keys a retry on (issue #1580
        redteam LOW; the SQLite sibling of PostgreSQLAdapter._release_quietly).
        The depth-decrement precedes the close, so the #1070 depth invariant
        holds regardless of whether close raises.
        """
        try:
            await db.close()
        except Exception:
            logger.error("async_sql.sqlite.close_failed", exc_info=True)

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

            try:
                if savepoint_name:
                    # Nested transaction - release savepoint
                    await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                else:
                    # Outer transaction - commit
                    await db.commit()
            except BaseException:
                # Commit / RELEASE SAVEPOINT failed: roll the SQLite transaction
                # back so a shared :memory: connection is not left mid-transaction
                # (which would poison the next begin_transaction with "cannot
                # start a transaction within a transaction"). The finally still
                # performs the single depth-decrement + close, so the caller MUST
                # NOT issue a separate rollback_transaction after a failed commit
                # — that double-decrements _transaction_depth (issue #1070 class,
                # #1580 redteam HIGH). Best-effort; the original commit error
                # propagates via the bare raise.
                try:
                    if savepoint_name:
                        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                        await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                    else:
                        await db.rollback()
                except BaseException:
                    logger.error(
                        "async_sql.sqlite.commit_cleanup_rollback_failed",
                        exc_info=True,
                    )
                raise
            finally:
                # Decrement transaction depth exactly once (success OR failure)
                # and close the connection (non-memory) when the outermost
                # transaction ends — mirrors the PG/MySQL "always release" contract.
                self._transaction_depth -= 1
                if not self._is_memory_db and self._transaction_depth == 0:
                    await self._close_quietly(db)
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

            try:
                if savepoint_name:
                    # Nested transaction - rollback to savepoint
                    await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    await db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                else:
                    # Outer transaction - rollback
                    await db.rollback()
            finally:
                # Decrement transaction depth exactly once and close (non-memory)
                # even if the driver rollback raises — otherwise a failed rollback
                # leaves _transaction_depth > 0 and poisons the next
                # begin_transaction (issue #1070 class; mirrors commit_transaction).
                self._transaction_depth -= 1
                if not self._is_memory_db and self._transaction_depth == 0:
                    await self._close_quietly(db)
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
            config: dict[str, Any] = {}
            self._config = config
            return config

        try:
            with open(self.config_path, "r") as f:
                loaded: dict[str, Any] = yaml.safe_load(f) or {}
                self._config = loaded
                return loaded
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
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        """Execute with enterprise monitoring."""
        if transaction is not None:
            return await super().execute(
                query, params, fetch_mode, fetch_size, transaction, parameter_types
            )
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
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        """Execute with enterprise monitoring."""
        if transaction is not None:
            return await super().execute(
                query, params, fetch_mode, fetch_size, transaction, parameter_types
            )
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
        self._is_memory_db = (
            self._db_path == ":memory:" or "mode=memory" in self._db_path
        )
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

        # Initialize base adapter for path parsing and compatibility.
        await super().connect()

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        """Execute with enterprise monitoring."""
        if transaction is not None:
            # When a transaction is provided, use the base class path which
            # executes on the transaction's connection. Routing through the
            # enterprise pool would create a DIFFERENT connection, causing
            # "database is locked" because the transaction holds BEGIN IMMEDIATE.
            return await super().execute(
                query, params, fetch_mode, fetch_size, transaction, parameter_types
            )
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
        try:
            if self._enterprise_pool:
                await self._enterprise_pool.close()
                self._enterprise_pool = None
        finally:
            # Issue #1051: ProductionSQLiteAdapter inherits SQLiteAdapter's
            # _get_connection()/begin_transaction(), so the :memory:
            # transaction path populates the inherited self._connection
            # slot — which _enterprise_pool does NOT own. The pre-fix
            # if/else only reached super().disconnect() (the connection
            # close) when _enterprise_pool was None; on a connected adapter
            # it is always set, so the inherited :memory: connection leaked
            # to GC. super().disconnect() is idempotent (guards on
            # self._connection is not None), so calling it unconditionally
            # is safe.
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
                await self.runtime_pool_manager.register_pool(  # type: ignore[union-attr]
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


# ============================================================================
# DPI-B2 / B3: Process-wide pool registry + lifecycle defaults (issue #697 + #698)
# ----------------------------------------------------------------------------
# The legacy ``AsyncSQLDatabaseNode._shared_pools`` dict tracked POOLS THAT
# SUCCESSFULLY ATTACHED to the per-pool lock-protected shared path. Pools
# created on the FALLBACK path (lock-timeout / RuntimeError) were attached
# only to the requesting node instance and held until the parent process
# died — the JourneyMate / Azure PostgreSQL connection-leak class.
#
# ``_PROCESS_POOL_REGISTRY`` is the single source of truth for "how many
# pools currently exist in this process." The registry tracks BOTH the
# shared-path pools AND the fallback-path pools so the cap in
# ``_POOL_DEFAULTS["max_pool_count_per_process"]`` is honoured uniformly.
#
# ``WeakValueDictionary`` semantics provide automatic GC reaping when an
# event loop closes (the pool drops its last strong ref and disappears
# from the registry on the next mapping access). The explicit reaper
# task added in DPI-B3 covers the live-but-idle case the WeakValue
# semantics cannot.
# ============================================================================

# Pool registry. Keys are pool keys produced by ``_generate_pool_key()`` for
# the shared path, or ``f"fallback_{id(node)}_{pool_key}"`` for the fallback
# path. Values are the EnterpriseConnectionPool / DatabaseAdapter instances.
# WeakValueDictionary auto-reaps entries whose value has been garbage-collected.
_PROCESS_POOL_REGISTRY: "weakref.WeakValueDictionary[str, Any]" = (
    weakref.WeakValueDictionary()
)

# Lifecycle defaults. ``idle_timeout`` is the seconds-of-no-activity a pool
# may sit before the reaper closes it. ``max_pool_count_per_process`` is the
# hard ceiling that turns the silent-fallback bug into a typed
# ``PoolExhaustedError``. Both values are int-positive; the validator in
# ``set_pool_defaults`` enforces this.
_POOL_DEFAULTS: dict[str, int] = {
    "idle_timeout": 300,
    "max_pool_count_per_process": 100,
}

# Reaper task registry — one task per event loop, keyed on
# ``id(get_running_loop())``. ``_REAPER_TASKS`` holds STRONG refs so the
# task is not GC'd while the loop is alive; the loop's own task tracking
# would also keep it but the explicit dict is grep-able.
_REAPER_TASKS: dict[int, asyncio.Task] = {}

# Lock for thread-safe ``_POOL_DEFAULTS`` mutation. Uses module-scope
# ``threading.Lock()`` factory; per ``rules/python-environment.md`` Rule 5
# the FACTORY return value is a class on Python 3.11+, so any future
# ``isinstance`` check must use ``type(threading.Lock())`` not
# ``threading.Lock`` — but this site never type-checks, only ``with``-acquires.
_POOL_DEFAULTS_LOCK = threading.Lock()


def set_pool_defaults(
    *,
    idle_timeout: Optional[int] = None,
    max_pool_count_per_process: Optional[int] = None,
) -> None:
    """Configure process-wide pool lifecycle defaults (DPI-B2 / issue #697).

    Mutates the ``_POOL_DEFAULTS`` dict that gates the
    ``AsyncSQLDatabaseNode._get_adapter`` fallback path and the
    ``EnterpriseConnectionPool`` idle-timeout reaper.

    Both parameters are KEYWORD-ONLY and OPTIONAL. Passing ``None`` for
    a parameter leaves that default unchanged. Unknown keyword arguments
    raise ``TypeError`` per ``rules/python-environment.md`` discipline
    (no silent typos that look like the override worked).

    Args:
        idle_timeout: Seconds-of-no-activity before the reaper closes a
            pool. Must be a positive int. Default 300 s.
        max_pool_count_per_process: Hard ceiling on total pool count.
            When the registry size exceeds this, the
            ``_get_adapter`` fallback raises ``PoolExhaustedError``
            instead of silently creating yet another pool. Must be a
            positive int. Default 100.

    Raises:
        TypeError: If an unknown keyword argument is supplied (the
            keyword-only signature already rejects positional args).
        ValueError: If a parameter is not a positive int.

    Example:
        >>> set_pool_defaults(max_pool_count_per_process=50)  # cap lower for tests
        >>> set_pool_defaults(idle_timeout=2)                 # aggressive reap
    """
    if idle_timeout is not None:
        if not isinstance(idle_timeout, int) or idle_timeout < 1:
            raise ValueError(
                f"idle_timeout must be a positive int (got {idle_timeout!r})"
            )
    if max_pool_count_per_process is not None:
        if (
            not isinstance(max_pool_count_per_process, int)
            or max_pool_count_per_process < 1
        ):
            raise ValueError(
                "max_pool_count_per_process must be a positive int "
                f"(got {max_pool_count_per_process!r})"
            )
    with _POOL_DEFAULTS_LOCK:
        if idle_timeout is not None:
            _POOL_DEFAULTS["idle_timeout"] = idle_timeout
        if max_pool_count_per_process is not None:
            _POOL_DEFAULTS["max_pool_count_per_process"] = max_pool_count_per_process


def _reset_pool_defaults_for_tests() -> None:
    """Restore ``_POOL_DEFAULTS`` to factory values (test-fixture helper).

    Tests that mutate the defaults via ``set_pool_defaults()`` MUST
    restore them afterwards or downstream tests inherit the override.
    The ``reset_pool_registry`` autouse fixture in ``tests/conftest.py``
    calls this helper between every test.
    """
    with _POOL_DEFAULTS_LOCK:
        _POOL_DEFAULTS["idle_timeout"] = 300
        _POOL_DEFAULTS["max_pool_count_per_process"] = 100


# ============================================================================
# DPI-B3: Idle-timeout reaper (issue #698)
# ----------------------------------------------------------------------------
# One reaper task per event loop. Started lazily on the first pool
# creation in that loop. Walks ``_PROCESS_POOL_REGISTRY`` every
# ``idle_timeout / 4`` seconds, closes any pool whose
# ``is_idle()`` returns True, and removes it from the registry. Pools
# whose event loop is already closed are reaped automatically by the
# WeakValueDictionary; this reaper covers the live-but-idle case.
# ============================================================================


async def _idle_pool_reaper_loop() -> None:
    """Background task that closes idle pools (DPI-B3).

    Runs forever (until cancelled). Each iteration:
        1. Sleeps for ``idle_timeout / 4`` seconds (max 75s default).
        2. Walks ``_PROCESS_POOL_REGISTRY`` keys (snapshot list).
        3. For each pool whose ``is_idle()`` is True, calls
           ``await pool.close()`` and pops it from the registry.

    Exits cleanly on ``CancelledError`` (event-loop shutdown). Logs
    every reap event at INFO with a structured log line per
    ``rules/observability.md`` Rule 4.
    """
    try:
        while True:
            interval = max(1, _POOL_DEFAULTS["idle_timeout"] // 4)
            await asyncio.sleep(interval)

            # Snapshot keys — avoids "dict changed size during iter".
            try:
                items = list(_PROCESS_POOL_REGISTRY.items())
            except RuntimeError:
                # WeakValueDictionary raises on iteration when finalisers
                # mutate it. Try once more with a defensive copy.
                items = []

            now = time.monotonic()
            for key, pool in items:
                # Pools must expose is_idle()/close(); fallback adapter
                # objects that wrap _shared_pools may not. Skip silently.
                try:
                    if not hasattr(pool, "is_idle") or not callable(
                        getattr(pool, "is_idle", None)
                    ):
                        continue
                    if not pool.is_idle(now):
                        continue
                except Exception:
                    # Defensive — never let a bad pool break the reaper.
                    continue

                # Close + reap.
                try:
                    if hasattr(pool, "close") and asyncio.iscoroutinefunction(
                        pool.close
                    ):
                        await asyncio.wait_for(pool.close(), timeout=5.0)
                    elif hasattr(pool, "close"):
                        pool.close()
                    if hasattr(pool, "_reaped_count"):
                        pool._reaped_count += 1
                    # WeakValueDictionary.pop is safe on missing keys
                    # (raises KeyError; suppress).
                    try:
                        del _PROCESS_POOL_REGISTRY[key]
                    except KeyError:
                        pass
                    logger.info(
                        "async_sql.pool_reaped",
                        extra={
                            "pool_key": redact_pool_key(key),
                            "registry_size_after": len(_PROCESS_POOL_REGISTRY),
                        },
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "async_sql.pool_reap_timeout",
                        extra={"pool_key": redact_pool_key(key)},
                    )
                except Exception as e:
                    # Never let a single bad pool kill the reaper.
                    logger.warning(
                        "async_sql.pool_reap_error",
                        extra={"pool_key": redact_pool_key(key), "error": str(e)},
                    )
    except asyncio.CancelledError:
        # Expected on event-loop shutdown / cleanup_all_pools.
        logger.info("async_sql.pool_reaper_cancelled")
        raise


def _ensure_reaper_started(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Start the reaper task for the current event loop if absent (DPI-B3).

    Idempotent: a second call from the same loop is a no-op. A call
    from a DIFFERENT loop registers a separate task for that loop, so
    multi-loop test setups (each pytest-asyncio test creates its own
    loop) get their own reaper.

    Args:
        loop: Optional event loop. Defaults to the running loop. When
            no loop is running this function is a no-op (the next
            ``await`` from the caller will provide a loop).
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

    loop_id = id(loop)
    existing = _REAPER_TASKS.get(loop_id)
    if existing is not None and not existing.done():
        return

    task = loop.create_task(_idle_pool_reaper_loop())
    _REAPER_TASKS[loop_id] = task


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
        external_pool: Pre-created connection pool to inject (constructor-only,
            not serializable). When provided, the SDK borrows this pool instead of
            creating its own. The pool must match database_type (asyncpg.Pool for
            postgresql, aiomysql.Pool for mysql, aiosqlite.Connection for sqlite).
            The SDK will NOT close this pool — the caller retains ownership.
            Useful for multi-worker deployments (Gunicorn + FastAPI) where a single
            shared pool prevents connection exhaustion.

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

    # Class-level defaults (safety net if __init__ fails partway or __del__ runs early)
    _connected = False
    _adapter: Optional["DatabaseAdapter"] = None
    _source_traceback = None

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
                # Different event loop — best-effort dispose before clearing
                for pool_key, (adapter, _ref_count) in list(cls._shared_pools.items()):
                    try:
                        if hasattr(adapter, "disconnect"):
                            # Cannot await in sync context; force-close underlying pool
                            if hasattr(adapter, "_pool") and adapter._pool is not None:
                                adapter._pool.close()
                    except Exception:
                        pass
                cls._shared_pools.clear()
                cls._pool_lock = asyncio.Lock()
                cls._pool_lock_loop_id = id(loop)

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
                    f"Attempting to acquire pool lock for '{redact_pool_key(self.pool_key)}' (timeout: {self.timeout}s)"
                )

                try:
                    await asyncio.wait_for(self.lock.acquire(), timeout=self.timeout)
                    acquire_time = time.time() - self._acquire_start_time
                    logger.debug(
                        f"Successfully acquired pool lock for '{redact_pool_key(self.pool_key)}' in {acquire_time:.3f}s"
                    )
                    return self
                except asyncio.TimeoutError:
                    acquire_time = time.time() - self._acquire_start_time
                    logger.warning(
                        f"TIMEOUT: Failed to acquire pool lock for '{redact_pool_key(self.pool_key)}' after {acquire_time:.3f}s "
                        f"(timeout: {self.timeout}s). This may indicate deadlock or excessive lock contention."
                    )
                    raise RuntimeError(
                        f"Failed to acquire pool lock for '{redact_pool_key(self.pool_key)}' within {self.timeout}s timeout. "
                        f"This may indicate deadlock or excessive lock contention."
                    )

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                import logging
                import time

                logger = logging.getLogger(f"{__name__}.PoolLocking")

                if self._acquire_start_time:
                    hold_time = time.time() - self._acquire_start_time
                    logger.debug(
                        f"Releasing pool lock for '{redact_pool_key(self.pool_key)}' (held for {hold_time:.3f}s)"
                    )

                self.lock.release()
                logger.debug(
                    f"Released pool lock for '{redact_pool_key(self.pool_key)}'"
                )

        # Check feature flag - if legacy mode is enabled, use global lock
        if cls._use_legacy_locking:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(
                f"Using legacy global locking for pool '{redact_pool_key(pool_key)}' (KAILASH_USE_LEGACY_POOL_LOCKING=true)"
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
                    # Redacted: lock keys are pool keys carrying the connection
                    # string with credentials, and this is a public diagnostic
                    # return surface (issue #1260).
                    "pool_keys": [redact_pool_key(k) for k in pool_locks.keys()],
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

    @staticmethod
    def _validate_pool_type(pool: object, db_type: DatabaseType) -> None:
        """Validate that the external pool type matches the declared database_type.

        Uses optional imports — if the driver library isn't installed,
        validation is skipped (the adapter will fail at query time anyway).
        """
        if db_type == DatabaseType.POSTGRESQL:
            try:
                import asyncpg

                if not isinstance(pool, asyncpg.Pool):
                    raise NodeValidationError(
                        f"database_type is 'postgresql' but external_pool is "
                        f"{type(pool).__name__}, expected asyncpg.Pool"
                    )
            except ImportError:
                pass
        elif db_type == DatabaseType.MYSQL:
            try:
                import aiomysql

                if not isinstance(pool, aiomysql.Pool):
                    raise NodeValidationError(
                        f"database_type is 'mysql' but external_pool is "
                        f"{type(pool).__name__}, expected aiomysql.Pool"
                    )
            except ImportError:
                pass
        elif db_type == DatabaseType.SQLITE:
            try:
                import aiosqlite

                if not isinstance(pool, aiosqlite.Connection):
                    raise NodeValidationError(
                        f"database_type is 'sqlite' but external_pool is "
                        f"{type(pool).__name__}, expected aiosqlite.Connection"
                    )
            except ImportError:
                pass

    def _wrap_external_pool(self, external_pool) -> DatabaseAdapter:
        """Wrap an externally provided connection pool in a DatabaseAdapter.

        The adapter borrows the pool reference but does NOT own it.
        disconnect() is a no-op because the caller manages pool lifecycle.

        Args:
            external_pool: An asyncpg.Pool, aiomysql.Pool, or aiosqlite connection.

        Returns:
            DatabaseAdapter configured to use the external pool.
        """
        db_type = DatabaseType(self.config["database_type"].lower())
        # Use existing connection info, or a placeholder for DatabaseConfig validation
        # (the pool is already connected — these are only needed for adapter metadata)
        connection_string = self.config.get("connection_string")
        host = self.config.get("host")
        database = self.config.get("database")
        if not connection_string and not (host and database):
            # Provide a placeholder — the adapter won't use it since we inject the pool
            if db_type == DatabaseType.SQLITE:
                database = ":memory:"
            else:
                connection_string = "external-pool://injected"

        db_config = DatabaseConfig(
            type=db_type,
            host=host,
            port=self.config.get("port"),
            database=database,
            user=self.config.get("user"),
            password=self.config.get("password"),
            connection_string=connection_string,
            pool_size=0,
            max_pool_size=0,
        )

        self._validate_pool_type(external_pool, db_type)

        if db_type == DatabaseType.POSTGRESQL:
            adapter = PostgreSQLAdapter(db_config)
        elif db_type == DatabaseType.MYSQL:
            adapter = MySQLAdapter(db_config)
        elif db_type == DatabaseType.SQLITE:
            adapter = SQLiteAdapter(db_config)
        else:
            raise NodeExecutionError(f"Unsupported database type: {db_type}")

        # Inject external pool — adapter borrows, does not own
        adapter._pool = external_pool
        adapter._connected = True

        # Override disconnect to prevent closing the external pool.
        # Use a weak reference to avoid a reference cycle (adapter -> disconnect -> adapter).
        adapter_ref = weakref.ref(adapter)

        async def _noop_disconnect():
            a = adapter_ref()
            if a is not None:
                a._connected = False

        adapter.disconnect = _noop_disconnect  # type: ignore[method-assign]

        return adapter

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
                                or self._build_connection_string(),  # type: ignore[attr-defined]
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
            adapter._set_runtime_coordinated(True)  # type: ignore[attr-defined]
        else:
            # Add runtime coordination flag
            adapter._runtime_coordinated = True
            adapter._runtime_pool = runtime_pool

        return adapter

    def __init__(self, **config):
        self._adapter: Optional[DatabaseAdapter] = None
        # Issue #1051: a single node can create more than one adapter over
        # its lifetime (retry path, runtime-pool fallback). close() used to
        # disconnect only self._adapter (the last), orphaning the prior
        # adapters — each holding an open :memory: connection that leaked to
        # GC. Every adapter built by _create_adapter() is registered here so
        # close() can tear all of them down.
        self._owned_adapters: list[DatabaseAdapter] = []
        self._connected = False
        # Extract access control manager before passing to parent
        self.access_control_manager = config.pop("access_control_manager", None)

        # Transaction state management
        self._active_transaction = None
        self._transaction_connection = None
        self._transaction_mode = config.get("transaction_mode", "auto")

        # External pool injection — user provides their own pool, SDK borrows it
        self._external_pool = config.pop("external_pool", None)

        # Pool sharing configuration
        self._share_pool = config.get("share_pool", True)
        if self._external_pool is not None:
            self._share_pool = False  # Never track injected pools in _shared_pools
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

        # Source traceback for leak diagnostics
        if sys.flags.dev_mode or __debug__:
            self._source_traceback = traceback.extract_stack()
        else:
            self._source_traceback = None

        super().__init__(**config)

    def _reinitialize_from_config(self):
        """Re-initialize instance variables from config after config file loading."""
        # Update transaction mode
        self._transaction_mode = self.config.get("transaction_mode", "auto")

        # Update pool sharing configuration
        self._share_pool = self.config.get("share_pool", True)
        if self._external_pool is not None:
            self._share_pool = (
                False  # External pools are never shared via _shared_pools
            )

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary.

        Raises NodeExecutionError if external_pool is set, since live pool
        handles cannot be serialized and the deserialized node would silently
        lose its pool injection.
        """
        if self._external_pool is not None:
            raise NodeExecutionError(
                f"Node '{self.id}' uses an external connection pool which cannot "
                f"be serialized. External pool nodes are runtime-only — remove "
                f"external_pool or provide connection_string for serializable config."
            )
        return super().to_dict()

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
                type=object,
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
                type=object,
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
                type=object,
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

        # Validate connection parameters (skip when external pool is injected)
        if self._external_pool is None:
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
        if fetch_mode not in ["one", "all", "many"]:
            raise NodeValidationError(
                f"Invalid fetch_mode: {fetch_mode}. " "Must be one of: one, all, many"
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
        """Get or create database adapter with optional pool sharing.

        DPI-B4 (issue #697): The fallback path used to swallow bare
        ``Exception`` and silently create a dedicated pool with no
        process-wide registration. That produced the JourneyMate
        connection-leak class — every per-pool-lock timeout under
        saturation created a fresh 5-20 connection pool that lived
        until process shutdown.

        The bounded path:
            - Catches ONLY (RuntimeError, asyncio.TimeoutError) — known
              fallback triggers per zero-tolerance.md Rule 3. Bare
              ``Exception`` no longer reaches here; it propagates to the
              caller as the original error.
            - Checks ``len(_PROCESS_POOL_REGISTRY) <
              _POOL_DEFAULTS['max_pool_count_per_process']`` BEFORE
              creating the dedicated pool. At cap, raises
              ``PoolExhaustedError`` with the original exception as
              ``__cause__``.
            - Registers EVERY successfully-created pool (shared AND
              fallback) in ``_PROCESS_POOL_REGISTRY``.
            - Calls ``_ensure_reaper_started()`` on first successful
              creation.
        """
        if not self._adapter:
            # PRIORITY 0: Use externally provided pool (bypasses all internal pool management)
            if self._external_pool is not None:
                self._adapter = self._wrap_external_pool(self._external_pool)
                self._connected = True
                self._pool_key = None
                logger.info(f"Using externally provided connection pool for {self.id}")
                return self._adapter

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
                                    f"Removing stale pool for {redact_pool_key(self._pool_key)} - event loop closed"
                                )
                                del self._shared_pools[self._pool_key]
                                # Fall through to create new pool

                        # Create new shared pool
                        self._adapter = await self._create_adapter()
                        self._shared_pools[self._pool_key] = (self._adapter, 1)
                        AsyncSQLDatabaseNode._total_pools_created += 1  # type: ignore[attr-defined]  # ADR-017
                        # DPI-B2/B4: register in process-wide registry so
                        # the cap accounts for shared pools as well.
                        _PROCESS_POOL_REGISTRY[self._pool_key] = self._adapter
                        # DPI-B3: ensure the idle-pool reaper is running.
                        _ensure_reaper_started()
                        logger.debug(
                            f"Created new class-level shared pool for {self.id}"
                        )

                except (RuntimeError, asyncio.TimeoutError) as e:
                    # DPI-B4: bounded fallback. The bare ``except
                    # Exception`` was zero-tolerance Rule 3 (silent
                    # fallback) — narrowed to the only legitimate
                    # triggers (lock-timeout, dead loop). Anything else
                    # propagates with its original stack trace.
                    cap = _POOL_DEFAULTS["max_pool_count_per_process"]
                    current = len(_PROCESS_POOL_REGISTRY)
                    if current >= cap:
                        # Cap reached — refuse to create yet another
                        # dedicated pool. Operator must either raise the
                        # cap via set_pool_defaults or fix the
                        # contention root cause.
                        raise PoolExhaustedError(
                            current=current,
                            cap=cap,
                            pool_key=self._pool_key or "",
                        ) from e

                    # Under cap — create the dedicated fallback pool
                    # AND register it so the reaper can reclaim it.
                    fallback_pool_key = f"fallback_{id(self)}_{self._pool_key}"
                    logger.warning(
                        "async_sql.fallback_pool_created",
                        extra={
                            "node_id": self.id,
                            "pool_key": redact_pool_key(self._pool_key),
                            "fallback_pool_key": redact_pool_key(fallback_pool_key),
                            "registry_size": current,
                            "cap": cap,
                            "trigger": type(e).__name__,
                        },
                    )
                    # Clear pool sharing for this instance and create dedicated pool
                    self._share_pool = False
                    self._pool_key = None
                    self._adapter = await self._create_adapter()
                    # DPI-B2/B4: register the fallback pool. The reaper
                    # will reap it once idle; the cap honours it.
                    _PROCESS_POOL_REGISTRY[fallback_pool_key] = self._adapter
                    _ensure_reaper_started()
            else:
                # Create dedicated pool
                self._adapter = await self._create_adapter()
                # DPI-B2/B4: register dedicated-mode pools too — the
                # cap is process-wide, share_pool=False is not exempt.
                dedicated_key = f"dedicated_{id(self)}"
                _PROCESS_POOL_REGISTRY[dedicated_key] = self._adapter
                _ensure_reaper_started()
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
            # Issue #1741: ride-along per-connection credential callback for
            # token-based DB auth (Azure AD / AWS IAM). None (default) leaves
            # pool behavior unchanged; a callable is wired into asyncpg's
            # per-connection ``connect`` hook by PostgreSQLAdapter.connect().
            credential_provider=self.config.get("credential_provider"),
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

        # Issue #1051: register every adapter this node builds so close()
        # can disconnect ALL of them (not just the last self._adapter).
        # Tracked before connect() so a connect-retry that discards this
        # adapter and builds another still leaves this one reachable for
        # teardown.
        #
        # Bounded growth (#1051 redteam MEDIUM-1): a long-lived *cached*
        # node under connect-retry / pool churn calls _create_adapter()
        # repeatedly while cleanup() only runs at engine close — an
        # unbounded reference accumulation. Dedupe by identity (the
        # runtime-coordination path delegates here, so the same adapter
        # can arrive twice) and cap the retained list; when over cap the
        # oldest entries are stale retry-discards — best-effort disconnect
        # (idempotent) + drop so a reference bound never becomes a handle
        # leak.
        if not any(a is adapter for a in self._owned_adapters):
            self._owned_adapters.append(adapter)
        _OWNED_ADAPTERS_CAP = 32
        while len(self._owned_adapters) > _OWNED_ADAPTERS_CAP:
            stale = self._owned_adapters.pop(0)
            try:
                await asyncio.wait_for(stale.disconnect(), timeout=1.0)
            except (Exception, asyncio.TimeoutError):
                pass  # Best effort — stale retry-discard; never block create

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
            # #1581: an explicit borrowed transaction (a workflow-context
            # scope's raw txn handle, threaded by DataFlow's generated CRUD
            # nodes). When present the query runs ON that transaction and the
            # node does NOT begin/commit/rollback — the scope owns lifecycle.
            borrowed_transaction = inputs.get("transaction")

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
                transaction=borrowed_transaction,
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
                    except Exception:
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

    @contextlib.asynccontextmanager
    async def stream(
        self,
        query: Optional[str] = None,
        params: Optional[Union[tuple, dict, list]] = None,
        batch_size: int = DEFAULT_STREAM_BATCH_SIZE,
        user_context: Any | None = None,
    ):
        """Stream query results lazily via a server-side cursor.

        Public streaming surface — the replacement for the removed
        ``FetchMode.ITERATOR``. Use it for result sets too large to
        materialize:

            async with node.stream(query=q, params=p, batch_size=1000) as cursor:
                async for row in cursor:        # row is a dict, _convert_row-converted
                    ...

        LIFETIME CONTRACT: the underlying connection (and PostgreSQL
        transaction) stay open for the whole iteration and are released on
        ``__aexit__`` — normal completion, early ``break``, or exception
        unwind. The connection cannot be returned from a call and iterated
        later; it MUST be consumed inside the ``async with`` block.

        RETRY: streaming does NOT use ``_execute_with_retry``. A transient
        failure may be retried only during the connect + cursor-open phase
        (before the first row); once iteration has begun, errors propagate to
        the caller (re-driving mid-iteration would double-yield rows). The
        connect/cursor-open phase is covered by the adapter pool's own
        connection acquisition.

        ACCESS CONTROL: when ``access_control_manager`` + ``user_context`` are
        set, EXECUTE access is checked before streaming and ``apply_data_masking``
        is applied PER ROW (the materialized path masks per row too — streaming
        MUST NOT silently bypass masking).

        Args:
            query: SQL query (falls back to the node's configured ``query``).
            params: Query parameters (tuple/list positional or dict named).
            batch_size: Rows pulled per server round trip.
            user_context: Access-control context for the EXECUTE check + masking.
        """
        # Pre-flight mirrors async_run: resolve query/params, convert param
        # style, validate, check access — all BEFORE opening the cursor.
        query = query if query is not None else self.config.get("query")
        if params is None:
            params = self.config.get("params")
        if not query:
            raise NodeExecutionError("No query provided")

        db_type = self.config.get("database_type", "").lower()

        if params is not None:
            if db_type == "mysql":
                if isinstance(params, dict):
                    pass  # aiomysql handles dict params directly
                elif isinstance(params, (list, tuple)):
                    params = tuple(params) if isinstance(params, list) else params
                else:
                    params = (params,)
            else:
                # PostgreSQL/SQLite: convert positional → named (:p0, :p1 ...);
                # the adapter then re-converts named → dialect-positional.
                if isinstance(params, (list, tuple)):
                    query, params = self._convert_to_named_parameters(query, params)
                elif not isinstance(params, dict):
                    query, params = self._convert_to_named_parameters(query, [params])

        # Validate query for security (same gate as async_run).
        if self._validate_queries:
            try:
                QueryValidator.validate_query(query, allow_admin=self._allow_admin)
            except NodeValidationError as e:
                raise NodeExecutionError(
                    f"Query validation failed: {e}. "
                    "Set validate_queries=False to bypass (not recommended)."
                )

        # Access-control EXECUTE check (same gate as async_run).
        if self.access_control_manager and user_context:
            from kailash.access_control import NodePermission

            decision = self.access_control_manager.check_node_access(
                user_context, self.metadata.name, NodePermission.EXECUTE
            )
            if not decision.allowed:
                raise NodeExecutionError(f"Access denied: {decision.reason}")

        adapter = await self._get_adapter()

        correlation_id = uuid.uuid4().hex
        start_time = time.monotonic()
        rows_yielded = 0
        # Observability: structured log at stream OPEN (intent + batch_size +
        # correlation id). Do NOT log per row (hot-loop spam).
        logger.info(
            "async_sql.stream.open",
            extra={
                "node_id": self.id,
                "correlation_id": correlation_id,
                "database_type": db_type,
                "batch_size": batch_size,
                "has_masking": bool(self.access_control_manager and user_context),
            },
        )

        async def _masked_rows(raw_cursor):
            nonlocal rows_yielded
            apply_mask = bool(self.access_control_manager and user_context)
            async for row in raw_cursor:
                if apply_mask:
                    # Per-row masking — streaming MUST NOT bypass the
                    # masking the materialized path applies (security gap).
                    row = self.access_control_manager.apply_data_masking(
                        user_context, self.metadata.name, row
                    )
                rows_yielded += 1
                yield row

        try:
            async with adapter.stream(query, params, batch_size=batch_size) as cursor:
                yield _masked_rows(cursor)
        finally:
            # Observability: structured log at stream CLOSE (rows + duration).
            logger.info(
                "async_sql.stream.close",
                extra={
                    "node_id": self.id,
                    "correlation_id": correlation_id,
                    "rows_yielded": rows_yielded,
                    "duration_ms": round((time.monotonic() - start_time) * 1000, 2),
                },
            )

    async def execute_many_async(
        self,
        query: str,
        params_list: list[dict[str, Any]],
        transaction: Optional[Any] = None,
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
                params_list=params_list,  # type: ignore[arg-type]
                transaction=transaction,
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
        user_context: Any | None = None,
        parameter_types: Optional[dict[str, str]] = None,
        transaction: Optional[Any] = None,
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
                    transaction=transaction,
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

                # For external pools, fail fast on pool/connection errors.
                # The SDK cannot reconnect to a pool it does not own.
                if self._external_pool is not None:
                    err_msg = str(e).lower()
                    pool_dead = getattr(self._external_pool, "_closed", False)
                    if pool_dead or any(
                        p in err_msg
                        for p in (
                            "pool is closed",
                            "pool has been terminated",
                            "pool is being closed",
                            "connection",
                            "closed database",
                        )
                    ):
                        raise NodeExecutionError(
                            f"External connection pool is closed or unavailable. "
                            f"The SDK does not manage external pool lifecycle — "
                            f"ensure the pool is alive before executing queries. "
                            f"Original error: {e}"
                        ) from e

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
                                    adapter, _ref_count = self._shared_pools[
                                        self._pool_key
                                    ]
                                    try:
                                        await asyncio.wait_for(
                                            adapter.disconnect(), timeout=2.0
                                        )
                                    except Exception:
                                        pass
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
        self,
        adapter: DatabaseAdapter,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
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
                    transaction=transaction,
                )

            except Exception as e:
                last_error = e

                # For external pools, fail fast on pool/connection errors.
                # The SDK cannot reconnect to a pool it does not own.
                if self._external_pool is not None:
                    err_msg = str(e).lower()
                    pool_dead = getattr(self._external_pool, "_closed", False)
                    if pool_dead or any(
                        p in err_msg
                        for p in (
                            "pool is closed",
                            "pool has been terminated",
                            "pool is being closed",
                            "connection",
                            "closed database",
                        )
                    ):
                        raise NodeExecutionError(
                            f"External connection pool is closed or unavailable. "
                            f"The SDK does not manage external pool lifecycle — "
                            f"ensure the pool is alive before executing queries. "
                            f"Original error: {e}"
                        ) from e

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
                                    adapter, _ref_count = self._shared_pools[
                                        self._pool_key
                                    ]
                                    try:
                                        await asyncio.wait_for(
                                            adapter.disconnect(), timeout=2.0
                                        )
                                    except Exception:
                                        pass
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
        self,
        adapter: DatabaseAdapter,
        query: str,
        params_list: list[Union[tuple, dict]],
        transaction: Optional[Any] = None,
    ) -> int:
        """Execute batch operation with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query to execute
            params_list: List of parameter dictionaries
            transaction: An explicit borrowed transaction handle (#1581). When
                provided, the batch runs ON that transaction and this method
                does NOT begin/commit/rollback — the borrowing scope owns the
                transaction lifecycle.

        Returns:
            Number of affected rows (estimated)

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if transaction is not None:
            # #1581: borrowed transaction (a workflow-context scope). Run ON the
            # caller's transaction; the scope's commit/rollback node governs the
            # batch. Mirrors the manual `_active_transaction` branch below but
            # sources the handle from the explicit param (see
            # _execute_with_transaction for why instance state is not mutated).
            await adapter.execute_many(query, params_list, transaction)
            return len(params_list)
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
            except BaseException:
                # Issue #1070: BaseException (not Exception) so a cancelled
                # coroutine (asyncio.CancelledError is BaseException, not
                # Exception, on Py3.8+) ALSO runs rollback_transaction —
                # which resets _transaction_depth. Without this, a
                # cancellation between begin and the execute skips the rollback,
                # leaves depth > 0, and poisons the next begin_transaction()
                # on the same (e.g. :memory: shared-connection) adapter.
                await adapter.rollback_transaction(transaction)
                raise
            # Commit OUTSIDE the try/except: commit_transaction fully tears the
            # transaction down on failure too (PG/MySQL release the pooled
            # connection; SQLite rolls back + resets depth), so a failed commit
            # MUST NOT be followed by rollback_transaction — that would
            # double-release the pooled connection / double-decrement the SQLite
            # depth (issue #1070 class, #1580 redteam HIGH).
            await adapter.commit_transaction(transaction)
            return len(params_list)
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
        transaction: Optional[Any] = None,
    ) -> Any:
        """Execute query with automatic transaction management.

        Args:
            adapter: Database adapter
            query: SQL query
            params: Query parameters
            fetch_mode: How to fetch results
            fetch_size: Number of rows for 'many' mode
            transaction: An explicit borrowed transaction handle (#1581). When
                provided, the query runs ON that transaction and this method
                does NOT begin/commit/rollback — the borrowing scope owns the
                transaction lifecycle.

        Returns:
            Query results

        Raises:
            Exception: Re-raises any execution errors after rollback
        """
        if transaction is not None:
            # #1581: borrowed transaction (a workflow-context scope). Run ON the
            # caller's transaction; do NOT begin/commit/rollback — the scope's
            # commit/rollback node governs the write. This mirrors the manual
            # `_active_transaction` branch below but sources the handle from the
            # explicit param instead of mutating instance state (the per-loop
            # cached node is shared across operations, so mutating
            # `_active_transaction` would leak the scope into unrelated calls).
            return await adapter.execute(
                query=query,
                params=params,
                fetch_mode=fetch_mode,
                fetch_size=fetch_size,
                transaction=transaction,
                parameter_types=parameter_types,
            )
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
            except BaseException:
                # Issue #1070: see _execute_many_with_transaction — catch
                # BaseException so an asyncio.CancelledError between begin and
                # the execute still runs rollback_transaction (which resets
                # _transaction_depth) instead of leaking a poisoned state into
                # the next begin_transaction() on the same adapter.
                await adapter.rollback_transaction(transaction)
                raise
            # Commit OUTSIDE the try/except: commit_transaction self-cleans on
            # failure (releases the pooled connection / resets SQLite depth), so
            # a failed commit MUST NOT be followed by rollback_transaction —
            # that double-releases / double-decrements depth (issue #1070 class,
            # #1580 redteam HIGH). See _execute_many_with_transaction.
            await adapter.commit_transaction(transaction)
            return result
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
                    # Redacted: the raw key carries the connection string with
                    # credentials and this diagnostic dict is commonly logged /
                    # serialized by callers (issue #1260). Deterministic, so it
                    # still correlates with the redacted log/metric surfaces.
                    "key": redact_pool_key(pool_key),
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
                            [h for h in pool._holders if h._in_use]  # type: ignore[union-attr]
                        )
                    elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                        pool_info["active_connections"] = pool.size - pool.freesize

                metrics["pools"].append(pool_info)

            # Clean up stale pools from closed event loops
            cleaned_pools = await cls._cleanup_closed_loop_pools()
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
        for pool_key, (adapter, ref_count) in list(cls._shared_pools.items()):
            loop_id_str = pool_key.split("|")[0]

            try:
                pool_loop_id = int(loop_id_str)
            except (ValueError, IndexError):
                logger.warning(
                    f"AsyncSQLDatabaseNode: Invalid pool key format: {redact_pool_key(pool_key)}"
                )
                continue

            # Check if pool's event loop differs from current
            if pool_loop_id != current_loop_id:
                pools_to_remove.append(pool_key)
                logger.debug(
                    f"AsyncSQLDatabaseNode: Marked stale pool {redact_pool_key(pool_key)} "
                    f"(loop {pool_loop_id} != current {current_loop_id})"
                )

        # Phase 2: Cleanup stale pools
        for pool_key in pools_to_remove:
            try:
                adapter, _ref_count = cls._shared_pools.pop(pool_key)

                # Attempt graceful disconnect
                try:
                    if hasattr(adapter, "disconnect"):
                        await asyncio.wait_for(adapter.disconnect(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"AsyncSQLDatabaseNode: Timeout disconnecting stale pool "
                        f"{redact_pool_key(pool_key)}"
                    )
                except Exception as close_error:
                    logger.debug(
                        f"AsyncSQLDatabaseNode: Could not disconnect adapter for "
                        f"{redact_pool_key(pool_key)}: {close_error}"
                    )

                cleaned_count += 1
                logger.info(
                    f"AsyncSQLDatabaseNode: Cleaned stale pool {redact_pool_key(pool_key)}"
                )
            except Exception as e:
                logger.warning(
                    f"AsyncSQLDatabaseNode: Failed to cleanup pool {redact_pool_key(pool_key)}: {e}"
                )

        if cleaned_count > 0:
            logger.info(f"AsyncSQLDatabaseNode: Cleaned {cleaned_count} stale pools")

        return cleaned_count

    # ------------------------------------------------------------------
    # DPI-B2: Process-wide pool registry inspection surface (issue #697 + #698)
    # ------------------------------------------------------------------

    @classmethod
    def pool_count(cls) -> int:
        """Return total live pool count across the process (DPI-B2).

        Reads ``len(_PROCESS_POOL_REGISTRY)`` — the SINGLE source of truth
        for "how many pools currently exist." The legacy
        ``cls._shared_pools`` dict tracks ONLY pools that took the
        successful shared path; the registry tracks BOTH shared and
        fallback-path pools, which is the count that matters against the
        cap.

        Returns:
            int: Live pool count. Includes pools whose event loop is
                still running. Pools whose loop closed are reaped by the
                ``WeakValueDictionary`` semantics on next access.
        """
        # Touching len() iterates the mapping; dead-loop pools whose
        # ``EnterpriseConnectionPool`` instance has been GC'd disappear
        # at this point.
        return len(_PROCESS_POOL_REGISTRY)

    @classmethod
    def pool_keys(cls) -> List[str]:
        """Return sorted list of live pool keys (DPI-B2 diagnostic surface).

        Used by Tier-2 regression tests and operator diagnostics. Sorted
        so test assertions are deterministic. The keys are returned with
        their connection-string segment redacted (issue #1260) — they
        mirror the ``pool_key`` field emitted by the WARN logger on
        fallback, which is ALSO redacted, so cross-correlation between
        live registry state and incident logs still works by string
        equality (redaction is deterministic).

        Returns:
            list[str]: Sorted snapshot of redacted pool keys at call
                time. Read is non-locking; concurrent mutations may
                produce a count drift between this call and a sibling
                ``pool_count()`` call (acceptable; both are diagnostic).
        """
        return sorted(redact_pool_key(k) for k in _PROCESS_POOL_REGISTRY.keys())

    @classmethod
    async def clear_shared_pools(
        cls, graceful: bool = True, *, loop_id: int | None = None
    ) -> Dict[str, Any]:
        """Clear shared connection pools with enhanced error handling (ADR-017).

        Args:
            graceful: If True, attempts graceful close. If False, immediately removes pools.
            loop_id: If given, dispose ONLY the pools owned by that event loop
                — i.e. pools whose key begins with ``f"{loop_id}|"`` (the
                ``loop_id`` is the first ``|``-delimited segment of the pool
                key per ``_generate_pool_key``). Pools owned by other,
                still-live event loops are left intact. This is the
                loop-ownership guard a teardown on one loop MUST use so it
                does not dispose another loop's live pools (issue #1248). When
                ``None`` (the default), every pool in the process-wide
                registry is disposed (the original, unscoped behavior).

        Returns:
            Dict[str, Any]: Cleanup metrics

        DPI-B2 extension: when ``loop_id`` is ``None``, also clears
        ``_PROCESS_POOL_REGISTRY`` (the process-wide registry that tracks
        both shared and fallback pools) so test fixtures get a clean slate.
        Production callers SHOULD prefer ``cleanup_all_pools()`` (alias
        defined below) for the registry-clearing semantic. A loop-scoped
        clear (``loop_id`` set) does NOT blanket-clear the process registry —
        that would corrupt cap accounting for other loops' pools; the
        ``WeakValueDictionary`` self-prunes the disposed adapters on GC.
        """
        if loop_id is not None:
            # ``id(loop)`` reuse after a loop is GC'd is benign here: a closed
            # loop's pool is already dead/unusable, so disposing it on a
            # recycled-id collision is the correct outcome (identical to
            # ``_cleanup_closed_loop_pools``). A live loop's pools hold refs
            # that keep its ``id()`` from being recycled while they exist, so
            # the "recycled id + stale live pool" window is empty under normal
            # GC. Do NOT "fix" this by adding loop-identity bookkeeping.
            _loop_prefix = f"{loop_id}|"
            pool_keys = [
                key for key in cls._shared_pools if key.startswith(_loop_prefix)
            ]
        else:
            pool_keys = list(cls._shared_pools.keys())
        total_pools = len(pool_keys)
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

        _scope = "" if loop_id is None else f", loop_id={loop_id}"
        logger.info(
            f"AsyncSQLDatabaseNode: Clearing {total_pools} shared pools "
            f"(graceful={graceful}{_scope})"
        )

        for pool_key in pool_keys:
            try:
                adapter, _ref_count = cls._shared_pools.pop(pool_key)

                if graceful and hasattr(adapter, "disconnect"):
                    try:
                        await asyncio.wait_for(adapter.disconnect(), timeout=2.0)
                        logger.debug(
                            f"AsyncSQLDatabaseNode: Gracefully disconnected pool {redact_pool_key(pool_key)}"
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"AsyncSQLDatabaseNode: Timeout disconnecting pool {redact_pool_key(pool_key)}"
                        )
                        clear_failures += 1
                    except Exception as close_error:
                        logger.warning(
                            f"AsyncSQLDatabaseNode: Error disconnecting pool {redact_pool_key(pool_key)}: "
                            f"{close_error}"
                        )

                pools_cleared += 1
            except Exception as e:
                clear_failures += 1
                error_msg = (
                    f"Failed to clear pool {redact_pool_key(pool_key)}: {str(e)}"
                )
                clear_errors.append(error_msg)
                logger.error(f"AsyncSQLDatabaseNode: {error_msg}")

        logger.info(
            f"AsyncSQLDatabaseNode: Cleared {pools_cleared}/{total_pools} pools "
            f"({clear_failures} failures)"
        )

        # DPI-B2: also reap the process-wide registry. Tests that mutate
        # the cap or seed pools via the fallback path leak entries into
        # ``_PROCESS_POOL_REGISTRY`` that the legacy ``_shared_pools``
        # path never tracked. Clearing both keeps the cap honest across
        # test runs. A loop-scoped clear (issue #1248) MUST NOT blanket-clear
        # the registry — that would drop cap-accounting entries for pools
        # owned by other, still-live loops. The ``WeakValueDictionary``
        # self-prunes the adapters disposed above once their strong refs drop.
        if loop_id is None:
            registry_size = len(_PROCESS_POOL_REGISTRY)
            if registry_size > 0:
                # WeakValueDictionary clears in-place; values whose strong
                # refs live elsewhere stay alive (test fixtures that hold a
                # ref deliberately are unaffected).
                _PROCESS_POOL_REGISTRY.clear()
                logger.info(
                    f"AsyncSQLDatabaseNode: Cleared "
                    f"{registry_size} entries from process pool registry"
                )

        # DPI-B3: cancel reaper tasks for any closed event loops.
        # Tasks for the CURRENT loop stay alive; cleanup runs in a
        # ``cleanup_all_pools`` call to keep ``clear_shared_pools``
        # signature unchanged.

        return {
            "total_pools": total_pools,
            "pools_cleared": pools_cleared,
            "clear_failures": clear_failures,
            "clear_errors": clear_errors,
        }

    @classmethod
    async def cleanup_all_pools(cls, graceful: bool = True) -> Dict[str, Any]:
        """Tear down every pool in the process (DPI-B2 alias + reaper cleanup).

        Composed wrapper around ``clear_shared_pools`` that also cancels
        every reaper task in ``_REAPER_TASKS``. Use this in test
        teardown and graceful shutdown paths; production callers can
        invoke ``clear_shared_pools`` directly when reaper cancellation
        is undesirable (the reaper's own ``CancelledError`` handler
        already exits cleanly on event-loop shutdown).

        Args:
            graceful: Forwarded to ``clear_shared_pools``.

        Returns:
            dict: ``clear_shared_pools`` metrics plus a
                ``reaper_tasks_cancelled`` count.
        """
        result = await cls.clear_shared_pools(graceful=graceful)

        cancelled = 0
        for loop_id, task in list(_REAPER_TASKS.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    # Reaper exits via CancelledError — expected
                    pass
                cancelled += 1
            _REAPER_TASKS.pop(loop_id, None)
        result["reaper_tasks_cancelled"] = cancelled
        return result

    def get_pool_info(self) -> dict[str, Any]:
        """Get information about this instance's connection pool.

        Returns:
            dict: Pool information including shared status and metrics
        """
        info = {
            "shared": self._share_pool,
            # Redacted: the raw pool key carries the connection string with
            # credentials; this diagnostic dict is commonly logged/serialized
            # by callers, so mask before exposing (issue #1260).
            "pool_key": redact_pool_key(self._pool_key),
            "connected": self._connected,
        }

        if self._adapter and hasattr(self._adapter, "_pool") and self._adapter._pool:
            pool = self._adapter._pool
            if hasattr(pool, "size"):
                info["pool_size"] = pool.size()
            if hasattr(pool, "_holders"):
                info["active_connections"] = len(
                    [h for h in pool._holders if h._in_use]  # type: ignore[union-attr]
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
        self, query: str, parameters: Union[list, tuple]
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
            adapter = await self._get_adapter()
            if hasattr(adapter, "get_analytics_summary"):
                return adapter.get_analytics_summary()  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"Failed to get pool analytics: {e}")

        return None

    async def health_check(self) -> Optional[HealthCheckResult]:
        """Perform connection pool health check.

        Returns:
            HealthCheckResult with health status, or None if not available
        """
        try:
            adapter = await self._get_adapter()
            if hasattr(adapter, "health_check"):
                return await adapter.health_check()  # type: ignore[attr-defined]
            else:
                # Fallback basic health check
                await adapter.execute("SELECT 1")
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
                enterprise_pool = self._adapter._enterprise_pool  # type: ignore[attr-defined]
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
            result["metrics"] = metrics if metrics else None

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

        # Issue #1051: disconnect every adapter this node created, not just
        # the last self._adapter handled above. Connect-retry / runtime-pool
        # fallback can build several ProductionSQLiteAdapters, each holding
        # an open inherited :memory: connection; only one ever became
        # self._adapter. Best-effort, guarded, idempotent (disconnect()
        # guards on its own state). Runs regardless of self._connected so
        # orphaned adapters are still torn down.
        if self._owned_adapters:
            for _adapter in self._owned_adapters:
                try:
                    await asyncio.wait_for(_adapter.disconnect(), timeout=1.0)
                except (Exception, asyncio.TimeoutError) as e:
                    # Best effort cleanup — but log at DEBUG for parity with
                    # the sibling cached-node teardown in engine.py
                    # (observability.md Rule 5: teardown swallows still emit
                    # a DEBUG breadcrumb so a stuck disconnect is diagnosable).
                    logger.debug(
                        "async_sql.owned_adapter_disconnect_failed",
                        extra={"error": str(e)},
                    )
            self._owned_adapters.clear()

    def __del__(self, _warnings=warnings):
        """Warn and attempt sync cleanup if node is GC'd while still connected."""
        if not self._connected or self._adapter is None:
            return

        tb = ""
        if self._source_traceback:
            try:
                tb = "\n" + "".join(traceback.format_list(self._source_traceback))
            except Exception:
                tb = ""
        _warnings.warn(
            f"AsyncSQLDatabaseNode GC'd while still connected. Created at:{tb}",
            ResourceWarning,
            stacklevel=1,
        )

        # Best-effort sync close for SQLite (the only adapter with sync access)
        # Skip for external pools — the caller owns the connection.
        if getattr(self, "_external_pool", None) is not None:
            return
        try:
            adapter = self._adapter
            conn = getattr(adapter, "_connection", None)
            if conn is not None:
                raw = getattr(conn, "_conn", None)
                if raw is not None:
                    raw.close()
        except Exception:
            pass
