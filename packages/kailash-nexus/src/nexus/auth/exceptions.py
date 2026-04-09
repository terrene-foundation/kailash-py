"""Authentication and authorization exceptions for Nexus auth package.

SPEC-06 Migration: These exceptions now re-export from kailash.trust.auth.exceptions.
Import from kailash.trust.auth.exceptions directly for new code.
"""

from __future__ import annotations

import warnings

from kailash.trust.auth.exceptions import (
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

__all__ = [
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
