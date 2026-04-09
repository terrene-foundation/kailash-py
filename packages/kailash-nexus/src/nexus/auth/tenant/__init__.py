"""Nexus Tenant Isolation Package.

SPEC-06 Migration: Core tenant types extracted to kailash.trust.auth.context.
This package re-exports them for backward compatibility and retains the
Starlette/FastAPI TenantMiddleware.
"""

from nexus.auth.tenant.middleware import TenantMiddleware
from nexus.auth.tenant.resolver import TenantResolver

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
