"""Tenant context management.

SPEC-06 Migration: Re-exports from kailash.trust.auth.context.
"""

from kailash.trust.auth.context import (
    TenantContext,
    TenantInfo,
    _current_tenant,
    get_current_tenant,
    get_current_tenant_id,
    require_tenant,
)

__all__ = [
    "TenantContext",
    "TenantInfo",
    "_current_tenant",
    "get_current_tenant",
    "get_current_tenant_id",
    "require_tenant",
]
