# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kailash Trust Rate Limiting -- framework-agnostic rate limit primitives.

Extracted from ``nexus.auth.rate_limit`` (SPEC-06) to provide reusable rate
limiting backends and configuration that any Kailash framework can use.

Components:
    - ``RateLimitConfig``: Rate limiting configuration
    - ``RateLimitResult``: Result of a rate limit check
    - ``RateLimitBackend``: Abstract backend interface
    - ``InMemoryBackend``: Token bucket backend for development
    - ``RedisBackend``: Sliding window backend for production (requires redis)

The Starlette/FastAPI ``RateLimitMiddleware`` and ``@rate_limit`` decorator
remain in Nexus and delegate to these backends for the actual rate limiting.
"""

from __future__ import annotations

import logging

from kailash.trust.rate_limit.backends.base import RateLimitBackend
from kailash.trust.rate_limit.backends.memory import InMemoryBackend
from kailash.trust.rate_limit.config import RateLimitConfig
from kailash.trust.rate_limit.result import RateLimitResult

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitConfig",
    "RateLimitBackend",
    "InMemoryBackend",
    "RateLimitResult",
]
