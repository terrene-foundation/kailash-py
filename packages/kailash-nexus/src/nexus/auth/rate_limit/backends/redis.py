"""Redis-backed sliding window rate limiter for production.

Uses Redis sorted sets with sliding window algorithm for accurate
rate limiting across distributed deployments.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from nexus.auth.rate_limit.backends.base import RateLimitBackend

logger = logging.getLogger(__name__)

# Optional Redis import
try:
    import redis.asyncio as aioredis
    from redis.asyncio import ConnectionPool

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment, misc]


class RedisBackend(RateLimitBackend):
    """Redis-backed sliding window rate limiter for production.

    Uses Redis sorted sets with sliding window algorithm:
    - More accurate than fixed window (prevents boundary bursts)
    - Automatic key expiration via TTL
    - Lua script for atomic check-and-record
    - Graceful degradation when Redis unavailable

    Algorithm:
    1. Remove entries older than window from sorted set (ZREMRANGEBYSCORE)
    2. Count remaining entries (ZCARD)
    3. If under limit, add current timestamp (ZADD)
    4. Set TTL to prevent memory growth (EXPIRE)

    Performance:
    - Check: ~2-5ms with Redis pipeline
    - Memory: O(requests_in_window) per identifier

    Example:
        >>> backend = RedisBackend(
        ...     redis_url="redis://localhost:6379/0",
        ...     key_prefix="nexus:rl:",
        ... )
        >>> await backend.initialize()
        >>> allowed, remaining, reset_at = await backend.check("user-123", limit=100)
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "nexus:rl:",
        pool_size: int = 50,
        timeout_seconds: float = 5.0,
        fail_open: bool = True,
    ):
        """Initialize Redis backend.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            key_prefix: Prefix for all rate limit keys (default: "nexus:rl:")
            pool_size: Connection pool size (default: 50)
            timeout_seconds: Operation timeout (default: 5.0)
            fail_open: Allow requests when Redis unavailable (default: True)

        Raises:
            ImportError: If redis package not installed
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis package required for RedisBackend. "
                "Install with: pip install redis"
            )

        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._pool_size = pool_size
        self._timeout = timeout_seconds
        self._fail_open = fail_open

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None  # type: ignore[union-attr]
        self._initialized = False

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """Remove credentials from Redis URL for safe logging."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.username or parsed.password:
                safe_host = parsed.hostname or "localhost"
                safe_port = f":{parsed.port}" if parsed.port else ""
                return f"{parsed.scheme}://{safe_host}{safe_port}{parsed.path}"
            return url
        except Exception:
            return "redis://***"

    async def initialize(self) -> None:
        """Initialize Redis connection pool.

        Must be called before using the backend.
        """
        if self._initialized:
            return

        try:
            self._pool = ConnectionPool.from_url(
                self._redis_url,
                max_connections=self._pool_size,
                decode_responses=False,
            )

            self._client = aioredis.Redis(
                connection_pool=self._pool,
                socket_timeout=self._timeout,
                socket_connect_timeout=self._timeout,
            )

            # Test connection
            await self._client.ping()
            self._initialized = True

            # SECURITY: Sanitize URL before logging to avoid credential leaks
            logger.info(
                "RedisBackend initialized: %s", self._sanitize_url(self._redis_url)
            )

        except Exception as e:
            logger.error("Failed to initialize Redis: %s", e)
            if not self._fail_open:
                raise
            logger.warning("Redis unavailable - rate limiting disabled")

    # Lua script for atomic check-and-record operation
    _RATE_LIMIT_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window_start = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local window_seconds = tonumber(ARGV[4])

    -- Remove old entries
    redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

    -- Count current entries
    local current_count = redis.call('ZCARD', key)

    if current_count < limit then
        -- Under limit: add this request atomically
        redis.call('ZADD', key, now, now)
        redis.call('EXPIRE', key, window_seconds + 1)
        return {1, limit - current_count - 1}  -- allowed=true, remaining
    else
        -- Over limit: get oldest entry for retry-after calculation
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local retry_after = 0
        if oldest and oldest[2] then
            retry_after = math.ceil((tonumber(oldest[2]) + window_seconds) - now)
            if retry_after < 1 then retry_after = 1 end
        end
        return {0, retry_after}  -- allowed=false, retry_after
    end
    """

    async def check_and_record(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Atomically check rate limit and record request if allowed.

        Uses Lua script for atomic execution - this is the preferred method
        to prevent TOCTOU race conditions.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
        """
        if not self._initialized or not self._client:
            if self._fail_open:
                return (
                    True,
                    limit,
                    datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
                )
            raise RuntimeError("RedisBackend not initialized")

        try:
            key = f"{self._key_prefix}{identifier}"
            now = time.time()
            window_start = now - window_seconds

            # Execute Lua script atomically
            result = await self._client.eval(
                self._RATE_LIMIT_SCRIPT,
                1,  # Number of keys
                key,
                now,
                window_start,
                limit,
                window_seconds,
            )

            allowed = bool(result[0])
            reset_at = datetime.now(timezone.utc) + timedelta(seconds=window_seconds)

            if allowed:
                remaining = int(result[1])
                return True, remaining, reset_at
            else:
                retry_after = int(result[1])
                reset_at = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                return False, 0, reset_at

        except Exception as e:
            logger.error("Redis rate limit check failed: %s", e)
            if self._fail_open:
                return (
                    True,
                    limit,
                    datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
                )
            raise

    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check rate limit using sliding window algorithm.

        DEPRECATED: Use check_and_record() instead for atomic operations.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
        """
        if not self._initialized or not self._client:
            if self._fail_open:
                return (
                    True,
                    limit,
                    datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
                )
            raise RuntimeError("RedisBackend not initialized")

        try:
            key = f"{self._key_prefix}{identifier}"
            now = time.time()
            window_start = now - window_seconds

            async with self._client.pipeline(transaction=True) as pipe:
                # Remove old entries
                pipe.zremrangebyscore(key, 0, window_start)
                # Count current entries
                pipe.zcard(key)
                # Set TTL
                pipe.expire(key, window_seconds + 1)

                results = await pipe.execute()

            current_count = results[1]  # ZCARD result
            remaining = max(0, limit - current_count)
            reset_at = datetime.now(timezone.utc) + timedelta(seconds=window_seconds)

            if current_count < limit:
                return True, remaining - 1, reset_at
            else:
                # Calculate retry_after from oldest entry
                oldest = await self._client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = float(oldest[0][1])
                    retry_after = int((oldest_time + window_seconds) - now)
                    reset_at = datetime.now(timezone.utc) + timedelta(
                        seconds=max(1, retry_after)
                    )

                return False, 0, reset_at

        except Exception as e:
            logger.error("Redis rate limit check failed: %s", e)
            if self._fail_open:
                return (
                    True,
                    limit,
                    datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
                )
            raise

    async def record(self, identifier: str) -> None:
        """Add current timestamp to sorted set.

        DEPRECATED: Use check_and_record() instead for atomic operations.

        Args:
            identifier: Unique identifier
        """
        if not self._initialized or not self._client:
            return

        try:
            key = f"{self._key_prefix}{identifier}"
            now = time.time()
            await self._client.zadd(key, {str(now): now})
        except Exception as e:
            logger.warning("Failed to record rate limit: %s", e)

    async def reset(self, identifier: str) -> None:
        """Delete the sorted set for identifier.

        Args:
            identifier: Unique identifier to reset
        """
        if not self._initialized or not self._client:
            return

        try:
            key = f"{self._key_prefix}{identifier}"
            await self._client.delete(key)
        except Exception as e:
            logger.warning("Failed to reset rate limit: %s", e)

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        self._initialized = False
        logger.info("RedisBackend closed")
