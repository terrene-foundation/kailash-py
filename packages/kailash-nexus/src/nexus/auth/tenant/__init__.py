"""Nexus Tenant Isolation Package.

Provides automatic tenant isolation for multi-tenant applications
using contextvars for async-safe tenant context.

Usage:
    >>> from nexus.auth.tenant import TenantConfig, TenantMiddleware
    >>>
    >>> config = TenantConfig(jwt_claim="org_id")
    >>> app.add_middleware(TenantMiddleware, config=config)
"""

from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import (
    TenantContext,
    TenantInfo,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant,
)
from nexus.auth.tenant.exceptions import (
    TenantAccessDeniedError,
    TenantContextError,
    TenantError,
    TenantInactiveError,
    TenantNotFoundError,
)
from nexus.auth.tenant.middleware import TenantMiddleware
from nexus.auth.tenant.resolver import TenantResolver

__all__ = [
    "TenantConfig",
    "TenantContext",
    "TenantInfo",
    "TenantMiddleware",
    "TenantResolver",
    "TenantError",
    "TenantContextError",
    "TenantNotFoundError",
    "TenantInactiveError",
    "TenantAccessDeniedError",
    "get_current_tenant",
    "get_current_tenant_id",
    "require_tenant",
]
