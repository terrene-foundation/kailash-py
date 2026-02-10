# Rate Limiting Specification

## Overview

This specification defines a unified rate limiting system for Nexus with dual backends (in-memory for development, Redis for production), configurable per-route and per-identifier limits, and standard HTTP response headers.

## Evidence from Real Projects

| Project                 | File                       | Lines | Key Features                                       |
| ----------------------- | -------------------------- | ----- | -------------------------------------------------- |
| api_gateway_starter     | `middleware/rate_limit.py` | 222   | Token bucket, in-memory, thread-safe               |
| kaizen.trust.governance | `rate_limiter.py`          | 600   | Redis sliding window, multi-tier limits, fail-open |
| kailash.nodes.api       | `rate_limiting.py`         | 569   | Token bucket + sliding window, async support       |

## Architecture

### Component Hierarchy

```
nexus.auth.rate_limit
    RateLimitConfig          # Configuration dataclass
    RateLimitBackend (ABC)   # Abstract backend interface
        InMemoryBackend      # Development backend (token bucket)
        RedisBackend         # Production backend (sliding window)
    RateLimitResult          # Check result dataclass
    RateLimitMiddleware      # FastAPI middleware
    rate_limit()             # Decorator for per-endpoint limits
```

### File Structure

```
apps/kailash-nexus/src/nexus/auth/
    __init__.py                 # Re-export RateLimitConfig, rate_limit
    rate_limit/
        __init__.py             # Re-export all components
        config.py               # RateLimitConfig dataclass
        backends/
            __init__.py
            base.py             # RateLimitBackend ABC
            memory.py           # InMemoryBackend (token bucket)
            redis.py            # RedisBackend (sliding window)
        middleware.py           # RateLimitMiddleware
        decorators.py           # @rate_limit decorator
        result.py               # RateLimitResult dataclass
```

## Configuration

### RateLimitConfig

**Location:** `nexus/auth/rate_limit/config.py`

```python
from dataclasses import dataclass, field
from typing import Dict, Optional, Literal

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_minute: Default requests allowed per minute (default: 100)
        burst_size: Additional burst allowance above base rate (default: 20)
        backend: Backend type - "memory" or "redis" (default: "memory")
        redis_url: Redis connection URL (required if backend="redis")
        route_limits: Per-route limit overrides, path pattern -> config dict
        include_headers: Whether to add X-RateLimit-* headers (default: True)
        fail_open: Allow requests when backend unavailable (default: True)
        identifier_extractors: Custom identifier extraction functions

    Example:
        >>> config = RateLimitConfig(
        ...     requests_per_minute=100,
        ...     burst_size=20,
        ...     backend="redis",
        ...     redis_url="redis://localhost:6379/0",
        ...     route_limits={
        ...         "/api/chat/*": {"requests_per_minute": 30},
        ...         "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
        ...         "/health": None,  # No rate limit
        ...     },
        ...     include_headers=True,
        ... )
    """

    # Base limits
    requests_per_minute: int = 100
    burst_size: int = 20

    # Backend configuration
    backend: Literal["memory", "redis"] = "memory"
    redis_url: Optional[str] = None
    redis_key_prefix: str = "nexus:rl:"
    redis_connection_pool_size: int = 50
    redis_timeout_seconds: float = 5.0

    # Per-route overrides (path pattern -> config or None to disable)
    route_limits: Dict[str, Optional[Dict[str, int]]] = field(default_factory=dict)

    # Response behavior
    include_headers: bool = True

    # Failure behavior
    fail_open: bool = True  # Allow requests when backend fails

    def __post_init__(self):
        """Validate configuration."""
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if self.burst_size < 0:
            raise ValueError("burst_size cannot be negative")
        if self.backend == "redis" and not self.redis_url:
            raise ValueError("redis_url required when backend='redis'")
```

## Backend Interface

### RateLimitBackend (ABC)

**Location:** `nexus/auth/rate_limit/backends/base.py`

```python
from abc import ABC, abstractmethod
from typing import Tuple
from datetime import datetime

class RateLimitBackend(ABC):
    """Abstract interface for rate limit backends.

    All backends must implement check() and record() methods.
    Backends should be thread-safe for sync usage and async-safe
    for async usage.
    """

    @abstractmethod
    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
            - allowed: True if request is within limit
            - remaining: Requests remaining in current window
            - reset_at: When the rate limit window resets
        """
        pass

    @abstractmethod
    async def record(self, identifier: str) -> None:
        """Record a request for the identifier.

        Called after request is processed to update counters.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
        """
        pass

    @abstractmethod
    async def reset(self, identifier: str) -> None:
        """Reset rate limit for an identifier (admin override).

        Args:
            identifier: Unique identifier to reset
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (connection pools, etc.)."""
        pass
```

### InMemoryBackend

**Location:** `nexus/auth/rate_limit/backends/memory.py`

```python
import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from .base import RateLimitBackend

class InMemoryBackend(RateLimitBackend):
    """In-memory token bucket rate limiter for development.

    Uses token bucket algorithm with the following characteristics:
    - Tokens refill at a steady rate (requests_per_minute / 60)
    - Burst allowance through bucket capacity
    - Thread-safe via threading.Lock
    - No persistence - resets on restart

    Performance: O(1) check and record operations
    Memory: O(n) where n is number of unique identifiers

    Example:
        >>> backend = InMemoryBackend()
        >>> allowed, remaining, reset_at = await backend.check("user-123", limit=100)
        >>> if allowed:
        ...     await backend.record("user-123")
    """

    def __init__(self, burst_multiplier: float = 1.0):
        """Initialize in-memory backend.

        Args:
            burst_multiplier: Multiplier for bucket capacity (default: 1.0)
        """
        self._buckets: Dict[str, Tuple[float, datetime]] = defaultdict(
            lambda: (0.0, datetime.now(timezone.utc))
        )
        self._lock = threading.Lock()
        self._burst_multiplier = burst_multiplier

    async def check_and_record(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Atomically check rate limit and record request if allowed.

        This is the preferred method - combines check and record in a single
        atomic operation to prevent TOCTOU race conditions.
        """
        with self._lock:
            tokens, last_update = self._buckets[identifier]

            now = datetime.now(timezone.utc)
            elapsed = (now - last_update).total_seconds()

            # Refill tokens based on elapsed time
            refill_rate = limit / window_seconds
            tokens = min(
                limit * self._burst_multiplier,
                tokens + (elapsed * refill_rate)
            )

            # Calculate reset time
            reset_at = now + timedelta(seconds=window_seconds)

            if tokens >= 1.0:
                # Atomically consume token and update state
                self._buckets[identifier] = (tokens - 1.0, now)
                return True, int(tokens) - 1, reset_at
            else:
                # Update state without consuming (no token available)
                self._buckets[identifier] = (tokens, now)
                return False, 0, reset_at

    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check rate limit using token bucket algorithm.

        DEPRECATED: Use check_and_record() instead for atomic operations.
        This method exists for backwards compatibility but has TOCTOU risk
        when used with separate record() call.
        """
        with self._lock:
            tokens, last_update = self._buckets[identifier]

            now = datetime.now(timezone.utc)
            elapsed = (now - last_update).total_seconds()

            # Refill tokens based on elapsed time
            refill_rate = limit / window_seconds
            tokens = min(
                limit * self._burst_multiplier,
                tokens + (elapsed * refill_rate)
            )

            # Update bucket state
            self._buckets[identifier] = (tokens, now)

            # Calculate reset time
            reset_at = now + timedelta(seconds=window_seconds)

            if tokens >= 1.0:
                return True, int(tokens) - 1, reset_at
            else:
                return False, 0, reset_at

    async def record(self, identifier: str) -> None:
        """Consume one token from the bucket.

        DEPRECATED: Use check_and_record() instead for atomic operations.
        """
        with self._lock:
            tokens, last_update = self._buckets[identifier]
            if tokens >= 1.0:
                self._buckets[identifier] = (tokens - 1.0, last_update)

    async def reset(self, identifier: str) -> None:
        """Reset rate limit for identifier."""
        with self._lock:
            if identifier in self._buckets:
                del self._buckets[identifier]

    async def close(self) -> None:
        """No cleanup needed for in-memory backend."""
        pass
```

### RedisBackend

**Location:** `nexus/auth/rate_limit/backends/redis.py`

```python
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .base import RateLimitBackend

logger = logging.getLogger(__name__)

# Optional Redis import
try:
    import redis.asyncio as redis
    from redis.asyncio import ConnectionPool
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None

class RedisBackend(RateLimitBackend):
    """Redis-backed sliding window rate limiter for production.

    Uses Redis sorted sets with sliding window algorithm:
    - More accurate than fixed window (prevents boundary bursts)
    - Automatic key expiration via TTL
    - Pipeline optimization for performance
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
        self._client: Optional[redis.Redis] = None
        self._initialized = False

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

            self._client = redis.Redis(
                connection_pool=self._pool,
                socket_timeout=self._timeout,
                socket_connect_timeout=self._timeout,
            )

            # Test connection
            await self._client.ping()
            self._initialized = True

            logger.info(f"RedisBackend initialized: {self._redis_url}")

        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            if not self._fail_open:
                raise
            logger.warning("Redis unavailable - rate limiting disabled")

    # Lua script for atomic check-and-record operation
    # This prevents TOCTOU race conditions by performing check and record atomically
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
        """
        if not self._initialized or not self._client:
            if self._fail_open:
                return True, limit, datetime.now(timezone.utc) + timedelta(seconds=window_seconds)
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
            logger.error(f"Redis rate limit check failed: {e}")
            if self._fail_open:
                return True, limit, datetime.now(timezone.utc) + timedelta(seconds=window_seconds)
            raise

    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check rate limit using sliding window algorithm.

        DEPRECATED: Use check_and_record() instead for atomic operations.
        This method exists for backwards compatibility but has TOCTOU risk
        when used with separate record() call.
        """
        if not self._initialized or not self._client:
            if self._fail_open:
                # Fail-open: allow request
                return True, limit, datetime.now(timezone.utc) + timedelta(seconds=window_seconds)
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
                    reset_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, retry_after))

                return False, 0, reset_at

        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            if self._fail_open:
                return True, limit, datetime.now(timezone.utc) + timedelta(seconds=window_seconds)
            raise

    async def record(self, identifier: str) -> None:
        """Add current timestamp to sorted set.

        DEPRECATED: Use check_and_record() instead for atomic operations.
        """
        if not self._initialized or not self._client:
            return

        try:
            key = f"{self._key_prefix}{identifier}"
            now = time.time()
            await self._client.zadd(key, {str(now): now})
        except Exception as e:
            logger.warning(f"Failed to record rate limit: {e}")

    async def reset(self, identifier: str) -> None:
        """Delete the sorted set for identifier."""
        if not self._initialized or not self._client:
            return

        try:
            key = f"{self._key_prefix}{identifier}"
            await self._client.delete(key)
        except Exception as e:
            logger.warning(f"Failed to reset rate limit: {e}")

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        self._initialized = False
        logger.info("RedisBackend closed")
```

## Result Dataclass

**Location:** `nexus/auth/rate_limit/result.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed
        limit: Maximum requests in the window
        remaining: Requests remaining in current window
        reset_at: When the rate limit window resets
        retry_after_seconds: Seconds to wait before retrying (if not allowed)
        identifier: The identifier that was checked
    """

    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after_seconds: Optional[int] = None
    identifier: Optional[str] = None

    def to_headers(self) -> dict[str, str]:
        """Generate X-RateLimit-* headers.

        Returns:
            Dictionary of header name -> value
        """
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": self.reset_at.isoformat(),
        }

        if not self.allowed and self.retry_after_seconds:
            headers["Retry-After"] = str(self.retry_after_seconds)

        return headers
```

## Middleware

**Location:** `nexus/auth/rate_limit/middleware.py`

```python
import fnmatch
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .backends.base import RateLimitBackend
from .backends.memory import InMemoryBackend
from .backends.redis import RedisBackend
from .config import RateLimitConfig
from .result import RateLimitResult

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting.

    Extracts identifier from request (user_id from JWT or IP address),
    checks rate limit, and adds response headers.

    Middleware behavior:
    1. Extract identifier (user_id from JWT, or IP for unauthenticated)
    2. Match route against route_limits for custom limits
    3. Check rate limit against backend
    4. If exceeded: return 429 with Retry-After header
    5. If allowed: process request and add rate limit headers
    6. On backend failure: fail-open (allow) with warning log

    Example:
        >>> from fastapi import FastAPI
        >>> from nexus.auth import RateLimitConfig
        >>> from nexus.auth.rate_limit import RateLimitMiddleware
        >>>
        >>> app = FastAPI()
        >>> config = RateLimitConfig(
        ...     requests_per_minute=100,
        ...     backend="memory",
        ... )
        >>> app.add_middleware(RateLimitMiddleware, config=config)
    """

    def __init__(
        self,
        app,
        config: RateLimitConfig,
        identifier_extractor: Optional[Callable[[Request], str]] = None,
    ):
        """Initialize rate limit middleware.

        Args:
            app: FastAPI/Starlette application
            config: Rate limit configuration
            identifier_extractor: Custom function to extract identifier from request
        """
        super().__init__(app)
        self.config = config
        self._identifier_extractor = identifier_extractor or self._default_identifier_extractor
        self._backend: Optional[RateLimitBackend] = None
        self._initialized = False

    async def _ensure_backend(self) -> None:
        """Lazily initialize backend on first request."""
        if self._initialized:
            return

        if self.config.backend == "redis":
            self._backend = RedisBackend(
                redis_url=self.config.redis_url,
                key_prefix=self.config.redis_key_prefix,
                pool_size=self.config.redis_connection_pool_size,
                timeout_seconds=self.config.redis_timeout_seconds,
                fail_open=self.config.fail_open,
            )
            await self._backend.initialize()
        else:
            burst_multiplier = (
                (self.config.requests_per_minute + self.config.burst_size)
                / self.config.requests_per_minute
            )
            self._backend = InMemoryBackend(burst_multiplier=burst_multiplier)

        self._initialized = True

    def _default_identifier_extractor(self, request: Request) -> str:
        """Extract identifier from request.

        Priority:
        1. user_id from request.state (set by auth middleware)
        2. API key from X-API-Key header
        3. Client IP address

        Args:
            request: FastAPI request

        Returns:
            Identifier string
        """
        # Try user_id from auth middleware
        if hasattr(request.state, "user_id") and request.state.user_id:
            return f"user:{request.state.user_id}"

        # Try API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key[:8]}"  # Truncate for privacy

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _get_route_limit(self, path: str) -> Optional[dict]:
        """Get rate limit config for a specific route.

        Args:
            path: Request path

        Returns:
            Route-specific config dict, None to skip rate limiting,
            or empty dict to use defaults
        """
        for pattern, limit_config in self.config.route_limits.items():
            if fnmatch.fnmatch(path, pattern):
                return limit_config
        return {}  # Use defaults

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        await self._ensure_backend()

        path = request.url.path

        # Check for route-specific limits
        route_limit = self._get_route_limit(path)

        # None means skip rate limiting for this route
        if route_limit is None:
            return await call_next(request)

        # Determine limits
        limit = route_limit.get("requests_per_minute", self.config.requests_per_minute)

        # Extract identifier
        identifier = self._identifier_extractor(request)

        # Check rate limit and record atomically (prevents TOCTOU race)
        allowed, remaining, reset_at = await self._backend.check_and_record(
            identifier=identifier,
            limit=limit,
            window_seconds=60,
        )

        if not allowed:
            retry_after = int((reset_at - datetime.now(timezone.utc)).total_seconds())
            retry_after = max(1, retry_after)

            result = RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after_seconds=retry_after,
                identifier=identifier,
            )

            logger.warning(
                f"Rate limit exceeded: identifier={identifier}, "
                f"path={path}, retry_after={retry_after}s"
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers=result.to_headers() if self.config.include_headers else {},
            )

        # Request was already recorded atomically in check_and_record()
        # No separate record() call needed

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        if self.config.include_headers:
            result = RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                identifier=identifier,
            )
            for header, value in result.to_headers().items():
                response.headers[header] = value

        return response
```

## Decorator

**Location:** `nexus/auth/rate_limit/decorators.py`

```python
from functools import wraps
from typing import Callable, Optional

from fastapi import HTTPException, Request

from .backends.memory import InMemoryBackend
from .result import RateLimitResult

def rate_limit(
    requests_per_minute: int = 100,
    burst_size: int = 20,
    identifier_extractor: Optional[Callable[[Request], str]] = None,
) -> Callable:
    """Decorator for per-endpoint rate limiting.

    Creates an in-memory rate limiter scoped to the decorated endpoint.
    For Redis-backed rate limiting, use RateLimitMiddleware instead.

    Args:
        requests_per_minute: Maximum requests per minute (default: 100)
        burst_size: Additional burst allowance (default: 20)
        identifier_extractor: Custom function to extract identifier from request

    Returns:
        Decorator function

    Example:
        >>> from fastapi import FastAPI, Request
        >>> from nexus.auth import rate_limit
        >>>
        >>> app = FastAPI()
        >>>
        >>> @app.get("/api/expensive")
        >>> @rate_limit(requests_per_minute=10, burst_size=5)
        >>> async def expensive_operation(request: Request):
        ...     return {"result": "success"}
    """
    burst_multiplier = (requests_per_minute + burst_size) / requests_per_minute
    backend = InMemoryBackend(burst_multiplier=burst_multiplier)

    def _default_identifier(request: Request) -> str:
        if hasattr(request.state, "user_id") and request.state.user_id:
            return f"user:{request.state.user_id}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    extractor = identifier_extractor or _default_identifier

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            identifier = extractor(request)

            allowed, remaining, reset_at = await backend.check(
                identifier=identifier,
                limit=requests_per_minute,
                window_seconds=60,
            )

            if not allowed:
                retry_after = int((reset_at - datetime.now(timezone.utc)).total_seconds())
                retry_after = max(1, retry_after)

                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            await backend.record(identifier)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
```

## Integration with Nexus

### Nexus Configuration

```python
from nexus import Nexus
from nexus.auth import RateLimitConfig

app = Nexus(
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
        backend="redis",
        redis_url="redis://localhost:6379/0",
        route_limits={
            "/api/chat/*": {"requests_per_minute": 30},
            "/api/auth/login": {"requests_per_minute": 10},
            "/health": None,  # No limit
            "/metrics": None,
        },
    ),
)
```

### Manual Middleware Setup

```python
from fastapi import FastAPI
from nexus.auth import RateLimitConfig
from nexus.auth.rate_limit import RateLimitMiddleware

app = FastAPI()

config = RateLimitConfig(
    requests_per_minute=100,
    backend="memory",
)

app.add_middleware(RateLimitMiddleware, config=config)
```

## Error Handling

### 429 Response Format

```json
{
  "detail": "Rate limit exceeded. Retry after 45 seconds.",
  "retry_after": 45
}
```

### Response Headers

| Header                  | Description                    | Example                |
| ----------------------- | ------------------------------ | ---------------------- |
| `X-RateLimit-Limit`     | Maximum requests per window    | `100`                  |
| `X-RateLimit-Remaining` | Requests remaining             | `45`                   |
| `X-RateLimit-Reset`     | Window reset time (ISO 8601)   | `2024-01-15T10:30:00Z` |
| `Retry-After`           | Seconds until retry (429 only) | `45`                   |

## Testing Requirements

### Tier 1: Unit Tests (Mocking Allowed)

**Location:** `tests/unit/auth/rate_limit/`

```python
# test_config.py
def test_config_defaults():
    """Test default configuration values."""
    config = RateLimitConfig()
    assert config.requests_per_minute == 100
    assert config.burst_size == 20
    assert config.backend == "memory"
    assert config.fail_open is True

def test_config_validation_rejects_negative():
    """Test validation rejects invalid values."""
    with pytest.raises(ValueError, match="must be positive"):
        RateLimitConfig(requests_per_minute=-1)

def test_config_requires_redis_url():
    """Test Redis backend requires URL."""
    with pytest.raises(ValueError, match="redis_url required"):
        RateLimitConfig(backend="redis")

# test_memory_backend.py
@pytest.mark.asyncio
async def test_memory_backend_allows_under_limit():
    """Test requests under limit are allowed."""
    backend = InMemoryBackend()
    allowed, remaining, _ = await backend.check("user-1", limit=10)
    assert allowed is True
    assert remaining == 9

@pytest.mark.asyncio
async def test_memory_backend_blocks_over_limit():
    """Test requests over limit are blocked."""
    backend = InMemoryBackend()

    # Exhaust limit
    for _ in range(10):
        await backend.check("user-1", limit=10)
        await backend.record("user-1")

    # Next request should be blocked
    allowed, remaining, _ = await backend.check("user-1", limit=10)
    assert allowed is False
    assert remaining == 0

@pytest.mark.asyncio
async def test_memory_backend_token_refill():
    """Test tokens refill over time."""
    backend = InMemoryBackend()

    # Exhaust limit
    for _ in range(10):
        await backend.check("user-1", limit=10)
        await backend.record("user-1")

    # Wait for refill (use time mocking)
    # ... tokens should refill

# test_result.py
def test_result_to_headers():
    """Test header generation."""
    result = RateLimitResult(
        allowed=True,
        limit=100,
        remaining=45,
        reset_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )

    headers = result.to_headers()
    assert headers["X-RateLimit-Limit"] == "100"
    assert headers["X-RateLimit-Remaining"] == "45"
    assert "Retry-After" not in headers

def test_result_to_headers_includes_retry_after_when_blocked():
    """Test Retry-After header when blocked."""
    result = RateLimitResult(
        allowed=False,
        limit=100,
        remaining=0,
        reset_at=datetime.now(timezone.utc),
        retry_after_seconds=45,
    )

    headers = result.to_headers()
    assert headers["Retry-After"] == "45"
```

### Tier 2: Integration Tests (NO MOCKING - Real Infrastructure)

**Location:** `tests/integration/auth/rate_limit/`

```python
# test_redis_backend_integration.py
@pytest.fixture
async def redis_backend():
    """Create Redis backend with real Redis."""
    backend = RedisBackend(
        redis_url=os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0"),
        key_prefix="test:rl:",
    )
    await backend.initialize()
    yield backend
    await backend.close()

@pytest.mark.asyncio
async def test_redis_backend_real_rate_limiting(redis_backend):
    """Test real Redis rate limiting (NO MOCKING)."""
    identifier = f"test-{uuid.uuid4()}"

    # Make requests up to limit
    for i in range(10):
        allowed, remaining, _ = await redis_backend.check(identifier, limit=10)
        assert allowed is True
        await redis_backend.record(identifier)

    # Next request should be blocked
    allowed, remaining, reset_at = await redis_backend.check(identifier, limit=10)
    assert allowed is False
    assert remaining == 0

@pytest.mark.asyncio
async def test_redis_backend_sliding_window(redis_backend):
    """Test sliding window behavior (NO MOCKING)."""
    identifier = f"test-{uuid.uuid4()}"

    # Make half the requests
    for _ in range(5):
        await redis_backend.check(identifier, limit=10)
        await redis_backend.record(identifier)

    # Wait for window to partially pass
    await asyncio.sleep(35)  # Half window

    # Should have more capacity now due to sliding window
    allowed, remaining, _ = await redis_backend.check(identifier, limit=10)
    assert allowed is True

@pytest.mark.asyncio
async def test_redis_backend_failover(redis_backend):
    """Test fail-open when Redis unavailable (NO MOCKING)."""
    # Close connection
    await redis_backend.close()
    redis_backend._initialized = False

    # Should fail-open
    allowed, _, _ = await redis_backend.check("user-1", limit=10)
    assert allowed is True  # Fail-open

# test_middleware_integration.py
@pytest.fixture
def test_client():
    """Create test client with rate limiting."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    config = RateLimitConfig(
        requests_per_minute=10,
        burst_size=5,
        backend="memory",
    )
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    return TestClient(app)

def test_middleware_returns_429_when_exceeded(test_client):
    """Test 429 response when rate limit exceeded (NO MOCKING)."""
    # Make requests up to limit + burst
    for _ in range(15):
        response = test_client.get("/test")
        # First 15 should succeed

    # Next request should get 429
    response = test_client.get("/test")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.json()["detail"].startswith("Rate limit exceeded")

def test_middleware_adds_headers(test_client):
    """Test rate limit headers are added (NO MOCKING)."""
    response = test_client.get("/test")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
```

### Tier 3: E2E Tests (NO MOCKING - Full Stack)

**Location:** `tests/e2e/auth/rate_limit/`

```python
# test_rate_limit_e2e.py
@pytest.mark.asyncio
async def test_concurrent_requests_rate_limited():
    """Test concurrent requests are properly rate limited (NO MOCKING)."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        # Send 50 concurrent requests
        tasks = [
            session.get("http://localhost:8000/api/test")
            for _ in range(50)
        ]

        responses = await asyncio.gather(*tasks)

        # Count responses
        success_count = sum(1 for r in responses if r.status == 200)
        rate_limited_count = sum(1 for r in responses if r.status == 429)

        # Should have some successes and some rate limited
        assert success_count > 0
        assert rate_limited_count > 0
        assert success_count + rate_limited_count == 50
```

## Performance Considerations

### Memory Backend

- **Check**: O(1) time complexity
- **Memory**: O(n) where n = unique identifiers
- **Cleanup**: Manual or LRU eviction recommended for long-running services

### Redis Backend

- **Check**: ~2-5ms with pipeline
- **Memory**: O(requests_in_window) per identifier in Redis
- **Key expiration**: Automatic via TTL

### Recommendations

1. Use **memory backend** for:
   - Development and testing
   - Single-instance deployments
   - Low-traffic applications

2. Use **Redis backend** for:
   - Production deployments
   - Multi-instance deployments
   - High-traffic applications

## Migration Path

### From Custom Implementations

```python
# Before: Custom rate limiting
from myapp.middleware import CustomRateLimiter

app.add_middleware(CustomRateLimiter, rate=100)

# After: Nexus rate limiting
from nexus.auth import RateLimitConfig
from nexus.auth.rate_limit import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    config=RateLimitConfig(requests_per_minute=100),
)
```
