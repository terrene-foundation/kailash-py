"""Tenant isolation configuration.

SPEC-06 Migration: Re-exports TenantConfig from kailash.trust.auth.context.
"""

from kailash.trust.auth.context import TenantConfig

__all__ = ["TenantConfig"]
