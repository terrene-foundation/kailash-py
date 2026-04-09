# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Nexus middleware components.

Provides security headers, CSRF protection, response caching, and
other middleware for hardening Nexus deployments.
"""

from __future__ import annotations

from nexus.middleware.cache import CacheConfig, CacheStats, ResponseCacheMiddleware
from nexus.middleware.csrf import CSRFMiddleware
from nexus.middleware.governance import PACTGovernanceError, PACTMiddleware
from nexus.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)

__all__ = [
    "CacheConfig",
    "CacheStats",
    "CSRFMiddleware",
    "PACTGovernanceError",
    "PACTMiddleware",
    "ResponseCacheMiddleware",
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
]
