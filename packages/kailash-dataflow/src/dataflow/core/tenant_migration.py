"""
Tenant Migration Management Module

Provides migration capabilities for multi-tenant environments.
This module is imported by tests for backwards compatibility.
"""

# Re-export from multi_tenancy module
from .multi_tenancy import TenantMigrationManager

__all__ = ["TenantMigrationManager"]
