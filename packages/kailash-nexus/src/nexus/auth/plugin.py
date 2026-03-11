"""NexusAuthPlugin - Unified auth plugin for Nexus (TODO-310G).

Combines JWT, RBAC, rate limiting, tenant isolation, and audit logging
into a single plugin following the NexusPlugin protocol.

Note: Do NOT use ``from __future__ import annotations`` in this module.
FastAPI inspects parameter annotations at runtime to recognize special types.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from nexus.auth.audit.config import AuditConfig
from nexus.auth.jwt import JWTConfig
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.tenant.config import TenantConfig
from nexus.plugins import NexusPlugin

logger = logging.getLogger(__name__)


class NexusAuthPlugin(NexusPlugin):
    """Unified auth plugin for Nexus.

    Combines JWT, RBAC, rate limiting, tenant isolation, and audit logging
    into a single plugin with correct middleware ordering and configuration
    management.

    Request execution order (outermost to innermost):
        1. Audit (captures everything)
        2. RateLimit (before auth, prevent abuse)
        3. JWT (core authentication)
        4. Tenant (needs JWT user for tenant claim resolution)
        5. RBAC (needs JWT user for role→permission resolution)

    Example:
        >>> from nexus.auth.plugin import NexusAuthPlugin
        >>> from nexus.auth import JWTConfig, AuditConfig
        >>>
        >>> auth = NexusAuthPlugin(
        ...     jwt=JWTConfig(secret="my-secret-at-least-32-chars-long!"),
        ...     audit=AuditConfig(backend="logging"),
        ... )
        >>> app = Nexus()
        >>> app.add_plugin(auth)
    """

    def __init__(
        self,
        jwt: Optional[JWTConfig] = None,
        rbac: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        rbac_default_role: Optional[str] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        tenant_isolation: Optional[TenantConfig] = None,
        audit: Optional[AuditConfig] = None,
    ):
        """Initialize auth plugin with component configs.

        Args:
            jwt: JWT middleware configuration
            rbac: RBAC role definitions (dict of role_name -> permissions)
            rbac_default_role: Default role for users without explicit roles
            rate_limit: Rate limiting configuration
            tenant_isolation: Tenant isolation configuration
            audit: Audit logging configuration

        Raises:
            ValueError: If component dependencies are not satisfied
        """
        self.jwt_config = jwt
        self.rbac_roles = rbac
        self.rbac_default_role = rbac_default_role
        self.rate_limit_config = rate_limit
        self.tenant_config = tenant_isolation
        self.audit_config = audit

        self._validate_dependencies()

    @property
    def name(self) -> str:
        """Plugin name."""
        return "nexus_auth"

    @property
    def description(self) -> str:
        """Plugin description."""
        components = []
        if self.jwt_config:
            components.append("JWT")
        if self.rbac_roles:
            components.append("RBAC")
        if self.rate_limit_config:
            components.append("RateLimit")
        if self.tenant_config:
            components.append("Tenant")
        if self.audit_config:
            components.append("Audit")
        return f"Auth plugin ({', '.join(components) or 'none'})"

    def _validate_dependencies(self):
        """Validate component dependencies.

        Raises:
            ValueError: If required dependencies are missing
        """
        if self.rbac_roles and not self.jwt_config:
            raise ValueError(
                "RBAC requires JWT middleware. "
                "Provide jwt=JWTConfig(...) when using rbac."
            )
        if self.tenant_config and not self.jwt_config:
            raise ValueError(
                "Tenant isolation requires JWT middleware. "
                "Provide jwt=JWTConfig(...) when using tenant_isolation."
            )

    def apply(self, nexus_instance: Any) -> None:
        """Apply plugin to Nexus instance (NexusPlugin ABC interface)."""
        self.install(nexus_instance)

    def install(self, app: Any) -> None:
        """Install middleware in correct order.

        Request execution order (outermost to innermost):
            1. Audit (captures everything, outermost)
            2. RateLimit (before auth, prevent abuse)
            3. JWT (core authentication - must run before RBAC/Tenant)
            4. Tenant (needs JWT user for tenant resolution from claims)
            5. RBAC (needs JWT user for role→permission resolution)

        Note: In Starlette, middleware added later wraps middleware added
        earlier. So we add in reverse order: innermost first (RBAC),
        then Tenant, then JWT, then RateLimit, then Audit (outermost).
        """
        # Add in reverse order (innermost first)

        # 5. RBAC context (innermost - needs request.state.user from JWT)
        if self.rbac_roles:
            from nexus.auth.rbac import RBACMiddleware

            app.add_middleware(
                RBACMiddleware,
                roles=self.rbac_roles,
                default_role=self.rbac_default_role,
            )
            logger.info("NexusAuthPlugin: RBAC middleware installed")

        # 4. Tenant isolation (needs request.state.token_payload from JWT)
        if self.tenant_config:
            from nexus.auth.tenant import TenantMiddleware

            app.add_middleware(TenantMiddleware, config=self.tenant_config)
            logger.info("NexusAuthPlugin: Tenant middleware installed")

        # 3. JWT authentication (must run before Tenant and RBAC)
        if self.jwt_config:
            from nexus.auth.jwt import JWTMiddleware

            app.add_middleware(JWTMiddleware, config=self.jwt_config)
            logger.info("NexusAuthPlugin: JWT middleware installed")

        # 2. Rate limiting
        if self.rate_limit_config:
            from nexus.auth.rate_limit import RateLimitMiddleware

            app.add_middleware(RateLimitMiddleware, config=self.rate_limit_config)
            logger.info("NexusAuthPlugin: Rate limit middleware installed")

        # 1. Audit (outermost - added last so it wraps everything)
        if self.audit_config:
            from nexus.auth.audit import AuditMiddleware

            app.add_middleware(AuditMiddleware, config=self.audit_config)
            logger.info("NexusAuthPlugin: Audit middleware installed")

    @property
    def enabled_components(self) -> List[str]:
        """List of enabled component names."""
        components = []
        if self.jwt_config:
            components.append("jwt")
        if self.rbac_roles:
            components.append("rbac")
        if self.rate_limit_config:
            components.append("rate_limit")
        if self.tenant_config:
            components.append("tenant")
        if self.audit_config:
            components.append("audit")
        return components

    @classmethod
    def basic_auth(
        cls,
        jwt: JWTConfig,
        audit: Optional[AuditConfig] = None,
    ) -> "NexusAuthPlugin":
        """Factory for basic authentication setup (JWT + audit).

        Args:
            jwt: JWT configuration
            audit: Audit configuration (defaults to logging backend)

        Returns:
            NexusAuthPlugin with JWT and audit enabled
        """
        return cls(
            jwt=jwt,
            audit=audit or AuditConfig(backend="logging"),
        )

    @classmethod
    def saas_app(
        cls,
        jwt: JWTConfig,
        rbac: Dict[str, Union[List[str], Dict[str, Any]]],
        tenant_isolation: TenantConfig,
        audit: Optional[AuditConfig] = None,
        rbac_default_role: Optional[str] = None,
    ) -> "NexusAuthPlugin":
        """Factory for multi-tenant SaaS application.

        Args:
            jwt: JWT configuration
            rbac: RBAC role definitions
            tenant_isolation: Tenant isolation configuration
            audit: Audit configuration (defaults to logging backend)
            rbac_default_role: Default role for users

        Returns:
            NexusAuthPlugin with JWT, RBAC, tenant, and audit enabled
        """
        return cls(
            jwt=jwt,
            rbac=rbac,
            rbac_default_role=rbac_default_role,
            tenant_isolation=tenant_isolation,
            audit=audit or AuditConfig(backend="logging"),
        )

    @classmethod
    def enterprise(
        cls,
        jwt: JWTConfig,
        rbac: Dict[str, Union[List[str], Dict[str, Any]]],
        rate_limit: RateLimitConfig,
        tenant_isolation: TenantConfig,
        audit: AuditConfig,
        rbac_default_role: Optional[str] = None,
    ) -> "NexusAuthPlugin":
        """Factory for full enterprise setup with all components.

        Args:
            jwt: JWT configuration
            rbac: RBAC role definitions
            rate_limit: Rate limiting configuration
            tenant_isolation: Tenant isolation configuration
            audit: Audit logging configuration
            rbac_default_role: Default role for users

        Returns:
            NexusAuthPlugin with all components enabled
        """
        return cls(
            jwt=jwt,
            rbac=rbac,
            rbac_default_role=rbac_default_role,
            rate_limit=rate_limit,
            tenant_isolation=tenant_isolation,
            audit=audit,
        )
