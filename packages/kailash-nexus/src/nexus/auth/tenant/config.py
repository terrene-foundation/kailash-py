"""Tenant isolation configuration.

Provides TenantConfig dataclass for configuring tenant resolution,
validation, and admin override behavior.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class TenantConfig:
    """Configuration for tenant isolation.

    Attributes:
        enabled: Whether tenant isolation is enabled (default: True)
        tenant_id_header: Header name for explicit tenant ID (default: "X-Tenant-ID")
        jwt_claim: JWT claim containing tenant ID (default: "tenant_id")
        fallback_to_user_org: Look up org from user record if not in JWT (default: True)
        org_field_name: Field name for organization in user record (default: "organization_id")
        validate_tenant_exists: Validate tenant exists in database (default: True)
        validate_tenant_active: Validate tenant is active (default: True)
        allow_admin_override: Allow super admins to access any tenant (default: True)
        admin_role: Role name for super admins (default: "super_admin")
        exclude_paths: Paths to exclude from tenant isolation

    Example:
        >>> config = TenantConfig(
        ...     tenant_id_header="X-Tenant-ID",
        ...     jwt_claim="org_id",
        ...     fallback_to_user_org=True,
        ...     validate_tenant_exists=True,
        ...     exclude_paths=["/health", "/metrics", "/api/public/*"],
        ... )
    """

    enabled: bool = True
    tenant_id_header: str = "X-Tenant-ID"
    jwt_claim: str = "tenant_id"
    fallback_to_user_org: bool = True
    org_field_name: str = "organization_id"
    validate_tenant_exists: bool = True
    validate_tenant_active: bool = True
    allow_admin_override: bool = True
    admin_role: str = "super_admin"
    exclude_paths: List[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs", "/openapi.json"]
    )

    # Custom tenant resolver (optional)
    custom_resolver: Optional[Callable] = None
