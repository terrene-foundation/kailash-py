"""Abstract base class for rate limit backends.

SPEC-06 Migration: Re-exports from kailash.trust.rate_limit.backends.base.
"""

from kailash.trust.rate_limit.backends.base import RateLimitBackend

__all__ = ["RateLimitBackend"]
