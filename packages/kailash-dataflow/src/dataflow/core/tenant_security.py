"""
Tenant Security Management Module

Provides security capabilities for multi-tenant environments.
This module is imported by tests for backwards compatibility.
"""

# Re-export from multi_tenancy module
from .multi_tenancy import TenantSecurityManager

__all__ = ["TenantSecurityManager"]
