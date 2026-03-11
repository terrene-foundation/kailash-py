"""Nexus Rate Limiting Package.

Provides configurable rate limiting with dual backends (in-memory for
development, Redis for production), per-route overrides, and standard
HTTP response headers.

Usage:
    >>> from nexus.auth.rate_limit import RateLimitConfig, RateLimitMiddleware
    >>>
    >>> config = RateLimitConfig(
    ...     requests_per_minute=100,
    ...     burst_size=20,
    ...     backend="memory",
    ... )
    >>> app.add_middleware(RateLimitMiddleware, config=config)
"""

from nexus.auth.rate_limit.backends.base import RateLimitBackend
from nexus.auth.rate_limit.backends.memory import InMemoryBackend
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.rate_limit.decorators import rate_limit
from nexus.auth.rate_limit.middleware import RateLimitMiddleware
from nexus.auth.rate_limit.result import RateLimitResult

__all__ = [
    "RateLimitConfig",
    "RateLimitBackend",
    "InMemoryBackend",
    "RateLimitMiddleware",
    "RateLimitResult",
    "rate_limit",
]
