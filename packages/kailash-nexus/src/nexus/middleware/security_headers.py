# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Security headers middleware for Nexus platform.

Adds standard security headers to all HTTP responses:
- Content-Security-Policy (CSP)
- Strict-Transport-Security (HSTS)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy

Usage:
    from nexus.middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

    # Custom configuration
    from nexus.middleware.security_headers import SecurityHeadersConfig
    config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
    app.add_middleware(SecurityHeadersMiddleware, config=config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
]


@dataclass(frozen=True)
class SecurityHeadersConfig:
    """Configuration for security response headers.

    All fields have secure defaults. Override only when you have a
    specific reason to relax a policy.
    """

    # Content-Security-Policy
    csp: str = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'"

    # Strict-Transport-Security (max-age in seconds, default 1 year)
    hsts_max_age: int = 31536000
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False

    # X-Content-Type-Options
    content_type_options: str = "nosniff"

    # X-Frame-Options (DENY or SAMEORIGIN)
    frame_options: str = "DENY"

    # X-XSS-Protection (legacy, but harmless)
    xss_protection: str = "1; mode=block"

    # Referrer-Policy
    referrer_policy: str = "strict-origin-when-cross-origin"

    # Permissions-Policy (formerly Feature-Policy)
    permissions_policy: str = "camera=(), microphone=(), geolocation=(), payment=()"

    # Paths to exclude from security headers (e.g., /healthz)
    exclude_paths: Tuple[str, ...] = ()

    def to_header_pairs(self) -> List[Tuple[str, str]]:
        """Generate header name-value pairs from this configuration.

        Returns:
            List of (header_name, header_value) tuples.
        """
        headers: List[Tuple[str, str]] = []

        # CSP
        if self.csp:
            headers.append(("content-security-policy", self.csp))

        # HSTS
        hsts_parts = [f"max-age={self.hsts_max_age}"]
        if self.hsts_include_subdomains:
            hsts_parts.append("includeSubDomains")
        if self.hsts_preload:
            hsts_parts.append("preload")
        headers.append(("strict-transport-security", "; ".join(hsts_parts)))

        # X-Content-Type-Options
        if self.content_type_options:
            headers.append(("x-content-type-options", self.content_type_options))

        # X-Frame-Options
        if self.frame_options:
            headers.append(("x-frame-options", self.frame_options))

        # X-XSS-Protection
        if self.xss_protection:
            headers.append(("x-xss-protection", self.xss_protection))

        # Referrer-Policy
        if self.referrer_policy:
            headers.append(("referrer-policy", self.referrer_policy))

        # Permissions-Policy
        if self.permissions_policy:
            headers.append(("permissions-policy", self.permissions_policy))

        return headers


class SecurityHeadersMiddleware:
    """ASGI middleware that injects security headers into all responses.

    Compatible with Starlette's add_middleware() pattern.
    """

    def __init__(
        self,
        app: Any,
        config: Optional[SecurityHeadersConfig] = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            config: Security headers configuration. Uses secure defaults if None.
        """
        self.app = app
        self.config = config or SecurityHeadersConfig()
        self._header_pairs = self.config.to_header_pairs()
        self._exclude_paths = set(self.config.exclude_paths)

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check path exclusions
        path = scope.get("path", "")
        if path in self._exclude_paths:
            await self.app(scope, receive, send)
            return

        # Wrap the send callable to inject headers
        header_pairs = self._header_pairs

        async def send_with_headers(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for name, value in header_pairs:
                    headers.append((name.encode(), value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
