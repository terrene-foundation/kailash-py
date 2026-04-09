"""Tenant isolation exceptions.

SPEC-06 Migration: Re-exports from kailash.trust.auth.context.
"""

from kailash.trust.auth.context import (
    TenantAccessDeniedError,
    TenantContextError,
    TenantError,
    TenantInactiveError,
    TenantNotFoundError,
)

__all__ = [
    "TenantError",
    "TenantContextError",
    "TenantNotFoundError",
    "TenantInactiveError",
    "TenantAccessDeniedError",
]
