# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Nexus middleware components.

Provides security headers, CSRF protection, and other middleware
for hardening Nexus deployments.
"""

from __future__ import annotations

from nexus.middleware.csrf import CSRFMiddleware
from nexus.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware

__all__ = [
    "CSRFMiddleware",
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
]
