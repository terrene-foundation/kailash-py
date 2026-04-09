"""Nexus Auth Package - Authentication and authorization for Nexus.

.. deprecated::
    Auth middleware is migrating to ``kailash.trust.auth`` as the canonical
    location (SPEC-06). This package continues to work but new code should
    import from ``kailash.trust.auth`` instead.

Provides JWT middleware, RBAC, SSO, rate limiting, tenant isolation,
and audit logging as a unified NexusAuthPlugin.

Usage:
    from nexus.auth.jwt import JWTMiddleware, JWTConfig
    from nexus.auth.models import AuthenticatedUser
    from nexus.auth.exceptions import InvalidTokenError, ExpiredTokenError
"""

import warnings

warnings.warn(
    "nexus.auth is deprecated; import from kailash.trust.auth instead. "
    "See SPEC-06 auth consolidation.",
    DeprecationWarning,
    stacklevel=2,
)

from nexus.auth.audit import AuditConfig, AuditMiddleware
from nexus.auth.exceptions import (
    AuthenticationError,
    AuthError,
    AuthorizationError,
    ExpiredTokenError,
    InsufficientPermissionError,
    InsufficientRoleError,
    InvalidTokenError,
    RateLimitExceededError,
    TenantAccessError,
)
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from nexus.auth.models import AuthenticatedUser
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth.rate_limit import RateLimitConfig, RateLimitMiddleware, rate_limit
from nexus.auth.rbac import RBACManager, RBACMiddleware
from nexus.auth.tenant import TenantConfig, TenantContext, TenantMiddleware

__all__ = [
    # JWT
    "JWTConfig",
    "JWTMiddleware",
    # RBAC
    "RBACManager",
    "RBACMiddleware",
    # Rate Limiting
    "RateLimitConfig",
    "RateLimitMiddleware",
    "rate_limit",
    # Tenant Isolation
    "TenantConfig",
    "TenantContext",
    "TenantMiddleware",
    # Audit Logging
    "AuditConfig",
    "AuditMiddleware",
    # Plugin
    "NexusAuthPlugin",
    # Models
    "AuthenticatedUser",
    # Exceptions
    "AuthError",
    "AuthenticationError",
    "AuthorizationError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "InsufficientPermissionError",
    "InsufficientRoleError",
    "TenantAccessError",
    "RateLimitExceededError",
]
