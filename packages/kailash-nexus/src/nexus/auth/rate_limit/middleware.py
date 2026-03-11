"""Rate limiting middleware for FastAPI/Starlette.

Provides RateLimitMiddleware that extracts identifiers from requests,
checks rate limits against the configured backend, and returns 429
responses when limits are exceeded.
"""

import fnmatch
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Request, Response
from nexus.auth.rate_limit.backends.base import RateLimitBackend
from nexus.auth.rate_limit.backends.memory import InMemoryBackend
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.rate_limit.result import RateLimitResult
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
        self._identifier_extractor = (
            identifier_extractor or self._default_identifier_extractor
        )
        self._backend: Optional[RateLimitBackend] = None
        self._initialized = False

    async def _ensure_backend(self) -> None:
        """Lazily initialize backend on first request."""
        if self._initialized:
            return

        if self.config.backend == "redis":
            from nexus.auth.rate_limit.backends.redis import RedisBackend

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
                self.config.requests_per_minute + self.config.burst_size
            ) / self.config.requests_per_minute
            self._backend = InMemoryBackend(burst_multiplier=burst_multiplier)

        self._initialized = True

    def _default_identifier_extractor(self, request: Request) -> str:
        """Extract identifier from request.

        Priority:
        1. user_id from request.state.user (set by JWT middleware)
        2. API key from X-API-Key header
        3. Client IP address

        Args:
            request: FastAPI request

        Returns:
            Identifier string
        """
        # Try user_id from AuthenticatedUser set by JWT middleware
        user = getattr(request.state, "user", None)
        if user and getattr(user, "user_id", None):
            return f"user:{user.user_id}"

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
                "Rate limit exceeded: identifier=%s, path=%s, retry_after=%ds",
                identifier,
                path,
                retry_after,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers=result.to_headers() if self.config.include_headers else {},
            )

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
