"""Rate limiting configuration.

SPEC-06 Migration: Re-exports RateLimitConfig from kailash.trust.rate_limit.config.
"""

from kailash.trust.rate_limit.config import RateLimitConfig

__all__ = ["RateLimitConfig"]
