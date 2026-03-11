"""Authentication and authorization exceptions for Nexus auth package."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for auth errors."""

    status_code: int = 500
    detail: str = "Authentication error"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class AuthenticationError(AuthError):
    """Authentication failed (401)."""

    status_code = 401
    detail = "Not authenticated"


class InvalidTokenError(AuthenticationError):
    """Token is invalid."""

    detail = "Invalid authentication token"


class ExpiredTokenError(AuthenticationError):
    """Token has expired."""

    detail = "Token has expired"


class AuthorizationError(AuthError):
    """Authorization failed (403)."""

    status_code = 403
    detail = "Not authorized"


class InsufficientPermissionError(AuthorizationError):
    """User lacks required permission."""

    detail = "Forbidden"

    def __init__(self, permission: str):
        # SECURITY: Generic detail; specifics logged server-side by caller
        super().__init__()


class InsufficientRoleError(AuthorizationError):
    """User lacks required role."""

    detail = "Forbidden"

    def __init__(self, roles: list):
        # SECURITY: Generic detail; specifics logged server-side by caller
        super().__init__()


class TenantAccessError(AuthorizationError):
    """Tenant access denied."""

    detail = "Access to this tenant is not allowed"


class RateLimitExceededError(AuthError):
    """Rate limit exceeded (429)."""

    status_code = 429
    detail = "Rate limit exceeded"
