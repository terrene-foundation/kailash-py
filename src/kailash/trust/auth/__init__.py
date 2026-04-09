# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kailash Trust Auth -- framework-agnostic authentication and authorization primitives.

Extracted from Nexus (SPEC-06) to provide reusable auth building blocks for any
Kailash framework (Nexus, Kaizen, MCP, etc.).

Components:
    - ``AuthenticatedUser``: Normalized user representation from JWT claims
    - ``JWTValidator``: Stateless JWT token verification and creation
    - ``JWTConfig``: JWT validation configuration
    - ``RBACManager``: Role-based access control with permission inheritance
    - ``TenantContext``: Multi-tenant context management via contextvars
    - ``TenantInfo``: Tenant information dataclass
    - ``SessionStore``: SSO state nonce validation
    - ``AuthMiddlewareChain``: Middleware ordering enforcement

Auth exceptions:
    - ``AuthError``, ``AuthenticationError``, ``AuthorizationError``
    - ``InvalidTokenError``, ``ExpiredTokenError``
    - ``InsufficientPermissionError``, ``InsufficientRoleError``
    - ``TenantAccessError``, ``RateLimitExceededError``

SSO providers:
    - ``GoogleProvider``, ``AzureADProvider``, ``GitHubProvider``, ``AppleProvider``
    - ``SSOProvider`` protocol, ``BaseSSOProvider`` base class
"""

from __future__ import annotations

from kailash.trust.auth.chain import AuthMiddlewareChain

# --- Tenant ---
from kailash.trust.auth.context import (
    TenantAccessDeniedError,
    TenantConfig,
    TenantContext,
    TenantContextError,
    TenantError,
    TenantInactiveError,
    TenantInfo,
    TenantNotFoundError,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant,
)

# --- Exceptions ---
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

# --- JWT ---
from kailash.trust.auth.jwt import JWTConfig, JWTValidator

# --- Models ---
from kailash.trust.auth.models import AuthenticatedUser

# --- RBAC ---
from kailash.trust.auth.rbac import (
    RBACManager,
    RoleDefinition,
    matches_permission,
    matches_permission_set,
)

# --- Session / SSO state ---
from kailash.trust.auth.session import (
    InMemorySessionStore,
    InvalidStateError,
    SessionStore,
)

__all__ = [
    # Exceptions
    "AuthError",
    "AuthenticationError",
    "AuthorizationError",
    "ExpiredTokenError",
    "InsufficientPermissionError",
    "InsufficientRoleError",
    "InvalidTokenError",
    "RateLimitExceededError",
    "TenantAccessError",
    # Models
    "AuthenticatedUser",
    # JWT
    "JWTConfig",
    "JWTValidator",
    # RBAC
    "RBACManager",
    "RoleDefinition",
    "matches_permission",
    "matches_permission_set",
    # Tenant
    "TenantConfig",
    "TenantContext",
    "TenantInfo",
    "get_current_tenant",
    "get_current_tenant_id",
    "require_tenant",
    "TenantError",
    "TenantContextError",
    "TenantNotFoundError",
    "TenantInactiveError",
    "TenantAccessDeniedError",
    # Session
    "SessionStore",
    "InMemorySessionStore",
    "InvalidStateError",
    # Chain
    "AuthMiddlewareChain",
]
