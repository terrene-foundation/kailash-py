# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""CSRF (Cross-Site Request Forgery) protection middleware for Nexus.

Validates Origin and Referer headers for state-changing HTTP methods
(POST, PUT, DELETE, PATCH). Safe methods (GET, HEAD, OPTIONS) bypass
validation entirely.

This is a lightweight, stateless CSRF protection suitable for API
servers. For cookie-based CSRF with token generation, use a
dedicated CSRF library.

Usage:
    from nexus.middleware.csrf import CSRFMiddleware

    # Allow requests from specific origins
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=["https://app.example.com", "https://admin.example.com"],
    )

    # Exempt specific paths (e.g., webhooks)
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=["https://app.example.com"],
        exempt_paths=["/webhooks/stripe"],
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__all__ = [
    "CSRFMiddleware",
]

# HTTP methods that may change server state
_UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# HTTP methods that are safe (idempotent reads)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _extract_origin(header_value: str) -> Optional[str]:
    """Extract the origin (scheme + host + port) from a URL or Origin header.

    Args:
        header_value: The raw header value.

    Returns:
        Normalized origin string, or None if parsing fails.
    """
    if not header_value:
        return None

    # Origin header is already scheme://host[:port]
    # Referer is a full URL — extract origin from it
    try:
        parsed = urlparse(header_value)
        if not parsed.scheme or not parsed.netloc:
            return None
        # Rebuild as origin (scheme://host[:port])
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return None


class CSRFMiddleware:
    """ASGI middleware for CSRF protection via Origin/Referer validation.

    For state-changing requests (POST, PUT, DELETE, PATCH), validates
    that the Origin or Referer header matches one of the allowed origins.

    Safe methods (GET, HEAD, OPTIONS) are always allowed.
    """

    def __init__(
        self,
        app: Any,
        allowed_origins: Optional[List[str]] = None,
        exempt_paths: Optional[List[str]] = None,
        allow_missing_origin: bool = False,
    ) -> None:
        """Initialize CSRF middleware.

        Args:
            app: The ASGI application to wrap.
            allowed_origins: List of allowed origin strings
                (e.g., ["https://app.example.com"]). If None or empty,
                all origins are rejected for unsafe methods.
            exempt_paths: Paths exempt from CSRF validation
                (e.g., ["/webhooks/stripe"]).
            allow_missing_origin: If True, requests without Origin AND
                Referer headers are allowed (useful for non-browser clients).
                Defaults to False for maximum security.
        """
        self.app = app
        self._allowed_origins: Set[str] = set()
        for origin in (allowed_origins or []):
            normalized = origin.rstrip("/").lower()
            self._allowed_origins.add(normalized)

        self._exempt_paths: Set[str] = set(exempt_paths or [])
        self._allow_missing_origin = allow_missing_origin

    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if the given origin is in the allowed set.

        Args:
            origin: Normalized origin string.

        Returns:
            True if origin is allowed.
        """
        if not origin:
            return self._allow_missing_origin
        return origin.lower() in self._allowed_origins

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()

        # Safe methods bypass CSRF
        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Exempt paths bypass CSRF
        path = scope.get("path", "")
        if path in self._exempt_paths:
            await self.app(scope, receive, send)
            return

        # For unsafe methods, validate Origin/Referer
        headers = dict(scope.get("headers", []))
        origin_header = headers.get(b"origin", b"").decode("latin-1", errors="replace")
        referer_header = headers.get(b"referer", b"").decode(
            "latin-1", errors="replace"
        )

        # Try Origin first, then Referer
        origin = _extract_origin(origin_header) if origin_header else None
        if origin is None and referer_header:
            origin = _extract_origin(referer_header)

        if self._is_origin_allowed(origin):
            await self.app(scope, receive, send)
            return

        # CSRF validation failed — return 403
        logger.warning(
            "CSRF validation failed: method=%s path=%s origin=%s",
            method,
            path,
            origin or "(missing)",
        )

        response_body = b'{"error": "CSRF validation failed"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(response_body)).encode()),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": response_body,
            }
        )
