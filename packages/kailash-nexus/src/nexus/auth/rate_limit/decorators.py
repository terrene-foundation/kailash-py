"""Per-endpoint rate limiting decorator.

Provides @rate_limit() decorator for applying rate limits to
individual FastAPI endpoints without middleware.
"""

from datetime import datetime, timezone
from functools import wraps
from typing import Callable, Optional

from fastapi import HTTPException, Request
from nexus.auth.rate_limit.backends.memory import InMemoryBackend


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
        >>> from nexus.auth.rate_limit import rate_limit
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
        user = getattr(request.state, "user", None)
        if user and getattr(user, "user_id", None):
            return f"user:{user.user_id}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    extractor = identifier_extractor or _default_identifier

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            identifier = extractor(request)

            # Atomic check-and-record to prevent TOCTOU race condition
            allowed, remaining, reset_at = await backend.check_and_record(
                identifier=identifier,
                limit=requests_per_minute,
                window_seconds=60,
            )

            if not allowed:
                retry_after = int(
                    (reset_at - datetime.now(timezone.utc)).total_seconds()
                )
                retry_after = max(1, retry_after)

                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
