"""Tenant resolver - extracts tenant from HTTP requests.

Provides TenantResolver with three resolution strategies:
1. X-Tenant-ID header (admin override, fail-closed)
2. JWT claim (tenant_id or org_id)
3. User organization lookup (fallback)
"""

import logging
from typing import Any, Optional

from fastapi import Request
from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import TenantInfo
from nexus.auth.tenant.exceptions import TenantAccessDeniedError, TenantNotFoundError

logger = logging.getLogger(__name__)


class TenantResolver:
    """Resolves tenant from HTTP request.

    Resolution order (in priority):
    1. X-Tenant-ID header (for admin API access across tenants)
    2. tenant_id claim from JWT token (primary method)
    3. Organization lookup from user record (fallback)

    Example:
        >>> resolver = TenantResolver(config)
        >>> tenant_info = await resolver.resolve(request)
        >>> print(f"Resolved tenant: {tenant_info.tenant_id}")
    """

    def __init__(self, config: TenantConfig, tenant_store: Optional[Any] = None):
        """Initialize resolver.

        Args:
            config: Tenant configuration
            tenant_store: Optional store for tenant validation (DataFlow, etc.)
        """
        self.config = config
        self._tenant_store = tenant_store

    async def resolve(self, request: Request) -> Optional[TenantInfo]:
        """Resolve tenant from request.

        Args:
            request: FastAPI request

        Returns:
            TenantInfo if resolved, None otherwise

        Raises:
            TenantAccessDeniedError: If admin override not allowed
        """
        # Use custom resolver if provided
        if self.config.custom_resolver:
            return await self.config.custom_resolver(request)

        tenant_id = None
        source = None

        # 1. Check header (highest priority - for admin override)
        header_value = request.headers.get(self.config.tenant_id_header)
        if header_value:
            tenant_id = header_value
            source = "header"

            # Validate admin override is allowed and user has admin role
            if self.config.allow_admin_override:
                # SECURITY: Read roles from AuthenticatedUser object set by JWT middleware
                user = getattr(request.state, "user", None)
                user_roles = getattr(user, "roles", []) if user else []
                user_id = getattr(user, "user_id", "unknown") if user else "unknown"
                if self.config.admin_role not in user_roles:
                    # SECURITY: Fail-closed - reject non-admin override attempts
                    logger.warning(
                        "Non-admin user attempted tenant override via header: "
                        "user_id=%s, tenant=%s",
                        user_id,
                        tenant_id,
                    )
                    raise TenantAccessDeniedError(
                        tenant_id=tenant_id,
                        user_id=user_id if user_id != "unknown" else None,
                        reason=f"Tenant override header requires '{self.config.admin_role}' role",
                    )
            else:
                # Admin override not allowed at all
                raise TenantAccessDeniedError(
                    tenant_id=tenant_id,
                    reason="Admin tenant override is disabled",
                )

        # 2. Check JWT claim (check both token_payload and token_claims for compatibility)
        if tenant_id is None:
            claims = getattr(request.state, "token_payload", None) or getattr(
                request.state, "token_claims", None
            )
            if claims and isinstance(claims, dict):
                tenant_id = claims.get(self.config.jwt_claim)
                if tenant_id:
                    source = "jwt"

        # 3. Fallback to user organization lookup
        if tenant_id is None and self.config.fallback_to_user_org:
            tenant_id = await self._lookup_user_org(request)
            if tenant_id:
                source = "user_org"

        if tenant_id is None:
            return None

        # Validate and create tenant info
        tenant_info = await self._validate_tenant(tenant_id)

        logger.debug("Resolved tenant '%s' from %s", tenant_id, source)
        return tenant_info

    async def _lookup_user_org(self, request: Request) -> Optional[str]:
        """Look up organization from user record.

        Args:
            request: FastAPI request

        Returns:
            Organization/tenant ID, or None
        """
        # Read from AuthenticatedUser object set by JWT middleware
        user = getattr(request.state, "user", None)
        if not user:
            return None

        if hasattr(user, self.config.org_field_name):
            return getattr(user, self.config.org_field_name)
        if isinstance(user, dict):
            return user.get(self.config.org_field_name)

        return None

    async def _validate_tenant(self, tenant_id: str) -> TenantInfo:
        """Validate tenant exists and is active.

        SECURITY: Fail-closed when validation is enabled but no store
        is configured. This prevents arbitrary tenant IDs from being accepted.

        Args:
            tenant_id: Tenant ID to validate

        Returns:
            TenantInfo for valid tenant

        Raises:
            TenantNotFoundError: If tenant validation fails or is misconfigured
        """
        if self.config.validate_tenant_exists:
            if not self._tenant_store:
                # SECURITY: Fail-closed - reject when validation is enabled
                # but no store is configured to validate against
                logger.warning(
                    "Tenant validation enabled but no tenant store configured. "
                    "Rejecting tenant '%s' (fail-closed). Configure a tenant store "
                    "or set validate_tenant_exists=False.",
                    tenant_id,
                )
                raise TenantNotFoundError(
                    tenant_id=tenant_id,
                    message=(
                        f"Cannot validate tenant '{tenant_id}': "
                        f"tenant store not configured"
                    ),
                )

            # Validate against the configured store
            # The store should implement a get/lookup method
            tenant_data = None
            if hasattr(self._tenant_store, "get_tenant"):
                tenant_data = await self._tenant_store.get_tenant(tenant_id)
            elif hasattr(self._tenant_store, "get"):
                tenant_data = self._tenant_store.get(tenant_id)

            if tenant_data is None:
                raise TenantNotFoundError(tenant_id=tenant_id)

            # Check if tenant is active (if store returns status info)
            active = True
            if isinstance(tenant_data, dict):
                active = tenant_data.get("active", True)
            elif hasattr(tenant_data, "active"):
                active = tenant_data.active

            return TenantInfo(
                tenant_id=tenant_id,
                active=active,
            )

        # Validation not enabled - accept tenant ID as-is
        return TenantInfo(
            tenant_id=tenant_id,
            active=True,
        )
