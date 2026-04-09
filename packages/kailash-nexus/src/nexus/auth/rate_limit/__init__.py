"""Nexus Rate Limiting Package.

SPEC-06 Migration: Core rate limit backends, config, and result types
extracted to kailash.trust.rate_limit. This package re-exports them
for backward compatibility and retains the Starlette/FastAPI middleware
and decorator.
"""

from nexus.auth.rate_limit.decorators import rate_limit
from nexus.auth.rate_limit.middleware import RateLimitMiddleware

from kailash.trust.rate_limit.backends.base import RateLimitBackend
from kailash.trust.rate_limit.backends.memory import InMemoryBackend
from kailash.trust.rate_limit.config import RateLimitConfig
from kailash.trust.rate_limit.result import RateLimitResult

__all__ = [
    "RateLimitConfig",
    "RateLimitBackend",
    "InMemoryBackend",
    "RateLimitMiddleware",
    "RateLimitResult",
    "rate_limit",
]
