"""
External Agent Rate Limiter - Redis-backed sliding window rate limiting.

Provides multi-tier rate limiting (per-minute, per-hour, per-day) with burst handling,
graceful degradation, and performance optimization for external agent invocations.

Key Features:
- Sliding window algorithm (more accurate than fixed window)
- Multi-tier limits (requests_per_minute, requests_per_hour, requests_per_day)
- Per-agent and per-user rate limiting
- Burst handling with token bucket algorithm
- Graceful degradation when Redis unavailable (fail-open)
- Redis connection pooling for performance
- Metrics tracking for monitoring

Architecture:
- Uses Redis sorted sets (ZADD, ZREMRANGEBYSCORE, ZCARD) for sliding window
- Each window (minute/hour/day) has separate Redis key
- Keys auto-expire with TTL to prevent memory growth
- Pipeline optimization for multi-tier checks (single round-trip)

Example:
    from kaizen.governance import ExternalAgentRateLimiter, RateLimitConfig

    # Configure limits
    config = RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
        burst_multiplier=1.5,
    )

    # Initialize with Redis
    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0",
        config=config,
    )
    await limiter.initialize()

    # Check rate limit
    result = await limiter.check_rate_limit(
        agent_id="agent-001",
        user_id="user-123",
    )

    if result.allowed:
        # Proceed with invocation
        await record_invocation(agent_id, user_id)
    else:
        # Return 429 with Retry-After header
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(result.retry_after_seconds)},
        )
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

try:
    import redis.asyncio as redis
    from redis.asyncio import ConnectionPool

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore
    ConnectionPool = None  # type: ignore

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    pass


@dataclass
class RateLimitConfig:
    """
    Configuration for multi-tier rate limiting.

    Attributes:
        requests_per_minute: Maximum requests per minute (default: 60)
        requests_per_hour: Maximum requests per hour (default: 1000)
        requests_per_day: Maximum requests per day (default: 10000)
        burst_multiplier: Burst allowance multiplier (default: 1.5 = 50% burst)
        enable_burst: Whether to enable burst handling (default: True)
        redis_max_connections: Redis connection pool size (default: 50)
        redis_timeout_seconds: Redis operation timeout (default: 5.0)
        fail_open_on_error: Allow requests when Redis unavailable (default: True)
        enable_metrics: Enable metrics tracking (default: True)

    Example:
        >>> config = RateLimitConfig(
        ...     requests_per_minute=10,
        ...     requests_per_hour=100,
        ...     requests_per_day=1000,
        ...     burst_multiplier=2.0,  # 100% burst allowance
        ... )
    """

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_multiplier: float = 1.5
    enable_burst: bool = True
    redis_max_connections: int = 50
    redis_timeout_seconds: float = 5.0
    fail_open_on_error: bool = True
    enable_metrics: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if self.requests_per_hour <= 0:
            raise ValueError("requests_per_hour must be positive")
        if self.requests_per_day <= 0:
            raise ValueError("requests_per_day must be positive")
        if self.burst_multiplier < 1.0:
            raise ValueError("burst_multiplier must be >= 1.0")
        if self.redis_max_connections <= 0:
            raise ValueError("redis_max_connections must be positive")


@dataclass
class RateLimitCheckResult:
    """
    Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed
        limit_exceeded: Which limit was exceeded (None if allowed)
        remaining: Requests remaining in most restrictive window
        reset_time: When the most restrictive window resets
        retry_after_seconds: Seconds to wait before retrying (None if allowed)
        current_usage: Current usage across all windows

    Example:
        >>> result = await limiter.check_rate_limit("agent-001", "user-123")
        >>> if not result.allowed:
        ...     print(f"Retry after {result.retry_after_seconds} seconds")
    """

    allowed: bool
    limit_exceeded: Optional[str] = None
    remaining: int = -1
    reset_time: Optional[datetime] = None
    retry_after_seconds: Optional[int] = None
    current_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class RateLimitMetrics:
    """Metrics for rate limit monitoring."""

    checks_total: int = 0
    exceeded_total: int = 0
    exceeded_by_limit: dict[str, int] = field(default_factory=dict)
    check_duration_total: float = 0.0
    redis_errors_total: int = 0
    fail_open_total: int = 0


class ExternalAgentRateLimiter:
    """
    Redis-backed sliding window rate limiter for external agents.

    Features:
    - Multi-tier rate limiting (minute, hour, day)
    - Sliding window algorithm (more accurate than fixed window)
    - Burst handling with token bucket
    - Graceful degradation when Redis unavailable
    - Connection pooling for performance
    - Pipeline optimization for multi-tier checks

    Example:
        >>> limiter = ExternalAgentRateLimiter(
        ...     redis_url="redis://localhost:6379/0",
        ...     config=RateLimitConfig(requests_per_minute=10),
        ... )
        >>> await limiter.initialize()
        >>> result = await limiter.check_rate_limit("agent-001", "user-123")
        >>> if result.allowed:
        ...     await invoke_agent()
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        config: Optional[RateLimitConfig] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            redis_url: Redis connection URL (default: redis://localhost:6379/0)
            config: Rate limit configuration (default: RateLimitConfig())

        Raises:
            ImportError: If redis package not installed
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package required for ExternalAgentRateLimiter. "
                "Install with: pip install redis"
            )

        self.redis_url = redis_url
        self.config = config or RateLimitConfig()
        self.redis_client: Optional[redis.Redis] = None
        self.connection_pool: Optional[ConnectionPool] = None
        self._initialized = False

        # Metrics tracking
        self.metrics = RateLimitMetrics() if self.config.enable_metrics else None

        # Window configurations (window_name: (duration_seconds, ttl_seconds))
        self._windows = {
            "minute": (60, 61),  # 1 minute + 1s buffer
            "hour": (3600, 3601),  # 1 hour + 1s buffer
            "day": (86400, 86401),  # 1 day + 1s buffer
        }

    async def initialize(self) -> None:
        """
        Initialize Redis connection pool.

        Must be called before using the rate limiter.

        Example:
            >>> limiter = ExternalAgentRateLimiter()
            >>> await limiter.initialize()
        """
        if self._initialized:
            return

        try:
            # Create connection pool for performance
            self.connection_pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.config.redis_max_connections,
                decode_responses=False,  # Binary mode for performance
            )

            # Create Redis client with pool
            self.redis_client = redis.Redis(
                connection_pool=self.connection_pool,
                socket_timeout=self.config.redis_timeout_seconds,
                socket_connect_timeout=self.config.redis_timeout_seconds,
            )

            # Test connection
            await self.redis_client.ping()
            self._initialized = True

            logger.info(
                f"ExternalAgentRateLimiter initialized with Redis: {self.redis_url}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            if not self.config.fail_open_on_error:
                raise
            logger.warning(
                "Continuing with fail-open mode (rate limiting disabled until Redis available)"
            )

    async def close(self) -> None:
        """
        Close Redis connection pool.

        Should be called during application shutdown.

        Example:
            >>> await limiter.close()
        """
        if self.redis_client:
            await self.redis_client.close()
        if self.connection_pool:
            await self.connection_pool.disconnect()
        self._initialized = False
        logger.info("ExternalAgentRateLimiter closed")

    async def check_rate_limit(
        self,
        agent_id: str,
        user_id: str,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> RateLimitCheckResult:
        """
        Check if request is within rate limits (all tiers).

        Uses Redis pipeline for efficient multi-tier checks (single round-trip).
        Implements sliding window algorithm for accuracy.

        Args:
            agent_id: Agent identifier
            user_id: User identifier
            team_id: Optional team identifier (for team-level limits)
            org_id: Optional organization identifier (for org-level limits)

        Returns:
            RateLimitCheckResult with allowed status and quota information

        Example:
            >>> result = await limiter.check_rate_limit("agent-001", "user-123")
            >>> if result.allowed:
            ...     # Proceed with invocation
            ...     await invoke_agent()
            >>> else:
            ...     # Return 429 with Retry-After header
            ...     raise HTTPException(429, headers={"Retry-After": str(result.retry_after_seconds)})
        """
        start_time = time.time()

        try:
            # Check if Redis available
            if not self._initialized or not self.redis_client:
                return self._fail_open("Redis not initialized")

            # Build scope key (user-level by default)
            scope_key = self._build_scope_key(agent_id, user_id, team_id, org_id)

            # Check all windows with pipeline (single round-trip)
            current_usage = {}
            limits = {
                "minute": self.config.requests_per_minute,
                "hour": self.config.requests_per_hour,
                "day": self.config.requests_per_day,
            }

            # Use pipeline for efficiency
            async with self.redis_client.pipeline(transaction=True) as pipe:
                now = time.time()

                for window_name, (duration, ttl) in self._windows.items():
                    key = f"rl:ea:{scope_key}:{window_name}"
                    min_score = now - duration

                    # Remove old entries
                    pipe.zremrangebyscore(key, 0, min_score)
                    # Count current entries
                    pipe.zcard(key)
                    # Set TTL
                    pipe.expire(key, ttl)

                # Execute pipeline
                results = await pipe.execute()

                # Parse results (every 3 items: zremrangebyscore, zcard, expire)
                for i, window_name in enumerate(self._windows.keys()):
                    count = results[i * 3 + 1]  # zcard result
                    current_usage[window_name] = count

            # Check limits with burst handling
            for window_name, limit in limits.items():
                effective_limit = limit
                if self.config.enable_burst:
                    effective_limit = int(limit * self.config.burst_multiplier)

                current = current_usage[window_name]

                if current >= effective_limit:
                    # Rate limit exceeded
                    duration, _ = self._windows[window_name]
                    reset_time = datetime.now() + timedelta(seconds=duration)

                    # Calculate retry_after from oldest entry
                    oldest_key = f"rl:ea:{scope_key}:{window_name}"
                    try:
                        oldest_entries = await self.redis_client.zrange(
                            oldest_key, 0, 0, withscores=True
                        )
                        if oldest_entries:
                            oldest_timestamp = float(oldest_entries[0][1])
                            retry_after = int(
                                (oldest_timestamp + duration) - time.time()
                            )
                            retry_after = max(1, retry_after)  # At least 1 second
                        else:
                            retry_after = int(duration)
                    except Exception as e:
                        logger.warning(f"Failed to calculate retry_after: {e}")
                        retry_after = int(duration)

                    # Track metrics
                    if self.metrics:
                        self.metrics.checks_total += 1
                        self.metrics.exceeded_total += 1
                        self.metrics.exceeded_by_limit[window_name] = (
                            self.metrics.exceeded_by_limit.get(window_name, 0) + 1
                        )

                    # Log rate limit exceeded
                    logger.warning(
                        f"Rate limit exceeded: scope={scope_key}, "
                        f"window={window_name}, "
                        f"limit={effective_limit}, current={current}, "
                        f"retry_after={retry_after}s"
                    )

                    return RateLimitCheckResult(
                        allowed=False,
                        limit_exceeded=f"per_{window_name}",
                        remaining=0,
                        reset_time=reset_time,
                        retry_after_seconds=retry_after,
                        current_usage=current_usage,
                    )

            # All limits passed - calculate remaining quota (most restrictive)
            remaining = float("inf")
            most_restrictive_window = None

            for window_name, limit in limits.items():
                effective_limit = limit
                if self.config.enable_burst:
                    effective_limit = int(limit * self.config.burst_multiplier)

                current = current_usage[window_name]
                window_remaining = effective_limit - current

                if window_remaining < remaining:
                    remaining = window_remaining
                    most_restrictive_window = window_name

            # Track metrics
            if self.metrics:
                self.metrics.checks_total += 1
                self.metrics.check_duration_total += time.time() - start_time

            return RateLimitCheckResult(
                allowed=True,
                limit_exceeded=None,
                remaining=int(remaining),
                reset_time=None,
                retry_after_seconds=None,
                current_usage=current_usage,
            )

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}", exc_info=True)

            if self.metrics:
                self.metrics.redis_errors_total += 1

            # Fail-open behavior
            if self.config.fail_open_on_error:
                return self._fail_open(str(e))
            else:
                raise RateLimitError(f"Rate limit check failed: {e}") from e

    async def record_invocation(
        self,
        agent_id: str,
        user_id: str,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> None:
        """
        Record an agent invocation in all rate limit windows.

        Should be called AFTER successful invocation to update counters.

        Args:
            agent_id: Agent identifier
            user_id: User identifier
            team_id: Optional team identifier
            org_id: Optional organization identifier

        Example:
            >>> result = await limiter.check_rate_limit("agent-001", "user-123")
            >>> if result.allowed:
            ...     await invoke_agent()
            ...     await limiter.record_invocation("agent-001", "user-123")
        """
        try:
            if not self._initialized or not self.redis_client:
                logger.warning("Cannot record invocation: Redis not initialized")
                return

            scope_key = self._build_scope_key(agent_id, user_id, team_id, org_id)
            now = time.time()

            # Use pipeline to update all windows
            async with self.redis_client.pipeline(transaction=True) as pipe:
                for window_name, (_, ttl) in self._windows.items():
                    key = f"rl:ea:{scope_key}:{window_name}"
                    # Add current timestamp
                    pipe.zadd(key, {str(now): now})
                    # Set TTL
                    pipe.expire(key, ttl)

                await pipe.execute()

            logger.debug(f"Recorded invocation for scope: {scope_key}")

        except Exception as e:
            logger.error(f"Failed to record invocation: {e}")
            # Don't raise - recording failure shouldn't block invocation

    def _build_scope_key(
        self,
        agent_id: str,
        user_id: str,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """
        Build hierarchical scope key for rate limiting.

        Priority: org > team > user (most specific available).

        Args:
            agent_id: Agent identifier
            user_id: User identifier
            team_id: Optional team identifier
            org_id: Optional organization identifier

        Returns:
            Scope key string (e.g., "agent-001:user:user-123")
        """
        if org_id:
            return f"{agent_id}:org:{org_id}"
        elif team_id:
            return f"{agent_id}:team:{team_id}"
        else:
            return f"{agent_id}:user:{user_id}"

    def _fail_open(self, reason: str) -> RateLimitCheckResult:
        """
        Return fail-open result (allow request when Redis unavailable).

        Args:
            reason: Failure reason for logging

        Returns:
            RateLimitCheckResult with allowed=True
        """
        logger.warning(
            f"Rate limiting unavailable (fail-open): {reason}. "
            "Request allowed without rate limiting."
        )

        if self.metrics:
            self.metrics.fail_open_total += 1

        return RateLimitCheckResult(
            allowed=True,
            limit_exceeded=None,
            remaining=-1,  # Unknown
            reset_time=None,
            retry_after_seconds=None,
            current_usage={},
        )

    def get_metrics(self) -> Optional[RateLimitMetrics]:
        """
        Get rate limit metrics for monitoring.

        Returns:
            RateLimitMetrics if metrics enabled, None otherwise

        Example:
            >>> metrics = limiter.get_metrics()
            >>> if metrics:
            ...     print(f"Total checks: {metrics.checks_total}")
            ...     print(f"Total exceeded: {metrics.exceeded_total}")
            ...     print(f"Exceeded by limit: {metrics.exceeded_by_limit}")
        """
        return self.metrics

    def reset_metrics(self) -> None:
        """
        Reset metrics counters.

        Example:
            >>> limiter.reset_metrics()
        """
        if self.metrics:
            self.metrics = RateLimitMetrics()


__all__ = [
    "ExternalAgentRateLimiter",
    "RateLimitConfig",
    "RateLimitCheckResult",
    "RateLimitError",
    "RateLimitMetrics",
]
