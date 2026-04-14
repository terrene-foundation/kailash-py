# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Typed error classes for cross-channel (HTTP/CLI/MCP) error translation.

Each error class carries an HTTP status code and a machine-readable
``error_code`` string. Transports translate these into channel-appropriate
responses:

- **HTTP**: JSON ``{"error": error_code, "detail": message}`` with the
  matching status code.
- **CLI**: Formatted error message with exit code derived from the status
  (4xx -> 1, 5xx -> 2).
- **MCP**: JSON-RPC error response with the ``error_code`` as the error
  data payload.

Usage::

    from nexus.errors import NotFoundError, ValidationError

    @app.handler("get_user")
    async def get_user(user_id: str) -> dict:
        user = await db.express.read("User", user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found")
        return user

The Nexus HTTP transport catches ``NexusError`` subclasses and returns
the appropriate JSON response. Handlers that raise plain ``Exception``
get a generic 500 response (no detail leaked to the client).
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "NexusError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "UnauthorizedError",
    "ForbiddenError",  # canonical name for 403
    "PermissionError",  # deprecated alias for ForbiddenError (shadows stdlib)
    "RateLimitError",
    "ServiceUnavailableError",
    "BadGatewayError",
    "TimeoutError",
]


class NexusError(Exception):
    """Base class for all Nexus typed errors.

    Every subclass carries:

    - ``status_code``: HTTP status code for the HTTP transport.
    - ``error_code``: Machine-readable error identifier (e.g.
      ``"not_found"``, ``"validation_error"``).
    - ``detail``: Human-readable error message.
    - ``context``: Optional dict of structured context for debugging
      (never exposed to the client in production).
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        detail: str = "Internal server error",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.detail = detail
        self.context = context or {}
        super().__init__(detail)

    def to_response_dict(self) -> Dict[str, Any]:
        """Serialize to a transport-agnostic response dict.

        The ``context`` field is intentionally excluded: it may contain
        schema-level or internal state that must not reach the client.
        Transports that want to include context (e.g., a debug mode)
        must opt-in explicitly.
        """
        return {
            "error": self.error_code,
            "detail": self.detail,
        }

    def __repr__(self) -> str:
        ctx = f", context={self.context!r}" if self.context else ""
        return (
            f"{type(self).__name__}("
            f"status_code={self.status_code}, "
            f"error_code={self.error_code!r}, "
            f"detail={self.detail!r}"
            f"{ctx})"
        )


class ValidationError(NexusError):
    """Request validation failed (400).

    Raised when handler input fails type checking, format validation,
    or business-rule validation before processing begins.
    """

    status_code: int = 400
    error_code: str = "validation_error"

    def __init__(
        self,
        detail: str = "Validation error",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class NotFoundError(NexusError):
    """Requested resource does not exist (404).

    Raised when a handler looks up an entity by ID and the entity is
    absent.  The ``detail`` message should name the resource type and
    identifier without leaking internal schema details.
    """

    status_code: int = 404
    error_code: str = "not_found"

    def __init__(
        self,
        detail: str = "Resource not found",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class ConflictError(NexusError):
    """Request conflicts with current state (409).

    Raised when a create or update would violate a uniqueness constraint
    or an optimistic-concurrency check (e.g., version mismatch).
    """

    status_code: int = 409
    error_code: str = "conflict"

    def __init__(
        self,
        detail: str = "Resource conflict",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class UnauthorizedError(NexusError):
    """Authentication required or failed (401).

    Raised when the request has no credentials or the credentials are
    invalid.  Do NOT use for authorization failures (missing roles or
    permissions) -- use ``ForbiddenError`` (403) instead.
    """

    status_code: int = 401
    error_code: str = "unauthorized"

    def __init__(
        self,
        detail: str = "Authentication required",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class ForbiddenError(NexusError):
    """Authenticated but lacks required permission (403).

    The request was authenticated (valid JWT, API key, etc.) but the
    identity does not have the role or permission needed to access this
    resource.  The ``detail`` message intentionally does NOT reveal which
    permission is missing (information leakage).

    .. note::
        Renamed from ``PermissionError`` to avoid shadowing the stdlib
        ``PermissionError`` exception. ``PermissionError`` remains as a
        deprecated alias; use ``ForbiddenError`` for new code.
    """

    status_code: int = 403
    error_code: str = "forbidden"

    def __init__(
        self,
        detail: str = "Forbidden",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


# Deprecated alias — shadows stdlib PermissionError. New code MUST use
# ForbiddenError. Kept for backwards compatibility with code that imports
# ``from nexus.errors import PermissionError`` directly.
PermissionError = ForbiddenError


class RateLimitError(NexusError):
    """Too many requests (429).

    Raised when a client exceeds the configured rate limit. The
    ``context`` dict may include ``retry_after_seconds`` for the
    transport to set the ``Retry-After`` header.
    """

    status_code: int = 429
    error_code: str = "rate_limit_exceeded"

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        *,
        retry_after_seconds: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = dict(context) if context else {}
        if retry_after_seconds is not None:
            ctx["retry_after_seconds"] = retry_after_seconds
        super().__init__(detail, context=ctx)

    @property
    def retry_after_seconds(self) -> Optional[int]:
        """Seconds until the client may retry, or None."""
        return self.context.get("retry_after_seconds")


class ServiceUnavailableError(NexusError):
    """Service temporarily unavailable (503).

    Raised when a downstream dependency (database, external API) is
    unreachable and the handler cannot serve the request.
    """

    status_code: int = 503
    error_code: str = "service_unavailable"

    def __init__(
        self,
        detail: str = "Service temporarily unavailable",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class BadGatewayError(NexusError):
    """Upstream returned an invalid response (502)."""

    status_code: int = 502
    error_code: str = "bad_gateway"

    def __init__(
        self,
        detail: str = "Bad gateway",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)


class TimeoutError(NexusError):
    """Request or upstream call timed out (504)."""

    status_code: int = 504
    error_code: str = "timeout"

    def __init__(
        self,
        detail: str = "Request timed out",
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail, context=context)
