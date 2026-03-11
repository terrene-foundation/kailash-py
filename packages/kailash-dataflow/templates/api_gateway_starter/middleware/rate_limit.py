"""
Rate Limiting middleware for API Gateway.

Provides token bucket rate limiting with in-memory storage.
"""

import threading
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Dict, Tuple

from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    """
    In-memory token bucket rate limiter with thread safety.

    Attributes:
        rate: Maximum requests allowed per window
        window: Time window in seconds

    Example:
        ```python
        limiter = InMemoryRateLimiter(rate=1000, window=3600)

        # Check if request is allowed
        allowed, info = limiter.check_rate_limit("user-123")
        if not allowed:
            print(f"Rate limit exceeded. Retry after {info['retry_after']} seconds")
        ```
    """

    def __init__(self, rate: int = 1000, window: int = 3600):
        """
        Initialize rate limiter.

        Args:
            rate: Requests per window (default: 1000)
            window: Time window in seconds (default: 3600 = 1 hour)
        """
        self.rate = rate
        self.window = window
        self._buckets: Dict[str, Tuple[int, datetime]] = defaultdict(
            lambda: (rate, datetime.now())
        )
        self._lock = threading.Lock()

    def check_rate_limit(self, key: str) -> Tuple[bool, Dict]:
        """
        Check if request is within rate limit (thread-safe).

        Args:
            key: Unique identifier for rate limit (user_id, API key, IP address)

        Returns:
            Tuple of (allowed, info_dict)
            - allowed: True if within limit, False if exceeded
            - info_dict: Contains 'remaining', 'reset_at', 'retry_after' (if blocked)

        Example:
            ```python
            allowed, info = limiter.check_rate_limit("user-123")

            if allowed:
                print(f"Requests remaining: {info['remaining']}")
            else:
                print(f"Rate limit exceeded. Retry after {info['retry_after']}s")
            ```
        """
        with self._lock:
            tokens, last_update = self._buckets[key]

            # Calculate time elapsed
            now = datetime.now()
            elapsed = (now - last_update).total_seconds()

            # Refill tokens if window expired
            if elapsed >= self.window:
                tokens = self.rate
                last_update = now

            # Check if request can be made
            if tokens > 0:
                # Allow request and decrement token
                self._buckets[key] = (tokens - 1, last_update)

                reset_at = last_update + timedelta(seconds=self.window)
                return True, {
                    "remaining": tokens - 1,
                    "reset_at": reset_at.isoformat(),
                    "limit": self.rate,
                }
            else:
                # Rate limit exceeded
                reset_at = last_update + timedelta(seconds=self.window)
                retry_after = (reset_at - now).total_seconds()

                return False, {
                    "remaining": 0,
                    "reset_at": reset_at.isoformat(),
                    "retry_after": int(retry_after) + 1,
                    "limit": self.rate,
                }

    def reset_rate_limit(self, key: str):
        """
        Reset rate limit for key (admin override).

        Args:
            key: Unique identifier to reset

        Example:
            ```python
            # Admin resets user's rate limit
            limiter.reset_rate_limit("user-123")
            ```
        """
        with self._lock:
            self._buckets[key] = (self.rate, datetime.now())


async def rate_limit_middleware(
    request: Request, call_next: Callable, limiter: InMemoryRateLimiter
):
    """
    Apply rate limiting to request.

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler
        limiter: InMemoryRateLimiter instance

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded

    Example:
        ```python
        from fastapi import FastAPI

        app = FastAPI()
        limiter = InMemoryRateLimiter(rate=100, window=3600)

        @app.middleware("http")
        async def rate_limit_middleware_wrapper(request: Request, call_next):
            return await rate_limit_middleware(request, call_next, limiter)
        ```
    """
    # Get rate limit key (user_id from JWT or API key)
    key = getattr(request.state, "user_id", None) or request.client.host

    # Check rate limit
    allowed, info = limiter.check_rate_limit(key)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {info['retry_after']} seconds",
            headers={
                "Retry-After": str(info["retry_after"]),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": info["reset_at"],
            },
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers to response
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = info["reset_at"]

    return response


def rate_limit(rate: int = 1000, window: int = 3600) -> Callable:
    """
    Decorator for rate-limited endpoints.

    Args:
        rate: Maximum requests per window
        window: Time window in seconds

    Returns:
        Decorator function

    Example:
        ```python
        limiter = InMemoryRateLimiter(rate=100, window=3600)

        @app.get("/api/data")
        @rate_limit(rate=100, window=3600)
        async def get_data(request: Request):
            return {"data": "protected"}
        ```
    """
    limiter = InMemoryRateLimiter(rate=rate, window=window)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get rate limit key
            key = getattr(request.state, "user_id", None) or request.client.host

            # Check rate limit
            allowed, info = limiter.check_rate_limit(key)

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Retry after {info['retry_after']} seconds",
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
