"""Rate limit backends.

SPEC-06 Migration: Re-exports from kailash.trust.rate_limit.backends.
"""

from kailash.trust.rate_limit.backends.base import RateLimitBackend
from kailash.trust.rate_limit.backends.memory import InMemoryBackend

__all__ = [
    "RateLimitBackend",
    "InMemoryBackend",
]
