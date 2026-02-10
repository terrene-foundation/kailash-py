# Auth Package Architecture Specification

## Overview

This specification defines the `NexusAuthPlugin` - a unified authentication plugin that consolidates patterns from three production projects (enterprise-app, example-project, example-backend) into ONE reusable component for Nexus.

**Evidence from Production Projects:**

- **enterprise-app**: 2,456 lines of middleware (JWT auth, RBAC+ABAC, CSRF, rate limiting, audit, feature gates, license gates, SSO config)
- **example-project**: 1,810 lines of core auth (JWT handler, RBAC with 4 roles, rate limiting, audit, password hashing)
- **example-backend**: 2,115 lines of auth (Admin permissions with scopes, Azure JWT, Apple JWT, tenant isolation, rate limiting, audit helpers)

**Goal**: Replace ~6,400 lines of custom auth code across projects with ONE plugin.

---

## File Structure

```
apps/kailash-nexus/src/nexus/auth/
    __init__.py              # NexusAuthPlugin, exports
    jwt.py                   # JWTMiddleware, token extraction/verification
    rbac.py                  # RBACMiddleware, require_role(), require_permission()
    rate_limit.py            # RateLimitMiddleware
    tenant.py                # TenantIsolationMiddleware
    audit.py                 # AuditMiddleware
    dependencies.py          # FastAPI dependencies (get_current_user, require_auth)
    models.py                # AuthenticatedUser, RoleConfig, PermissionConfig
    exceptions.py            # AuthenticationError, AuthorizationError
    sso/
        __init__.py          # SSO provider exports
        base.py              # SSOProvider protocol
        azure.py             # AzureADProvider
        google.py            # GoogleProvider
        apple.py             # AppleProvider
        github.py            # GitHubProvider
```

---

## NexusAuthPlugin Class

### Location

`/apps/kailash-nexus/src/nexus/auth/__init__.py`

### Complete Implementation Specification

```python
"""NexusAuthPlugin - Unified authentication for Nexus.

Consolidates auth patterns from enterprise-app (2,456 lines), example-project (1,810 lines),
and example-backend (2,115 lines) into a single reusable plugin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from nexus.plugins import NexusPlugin

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration.

    Attributes:
        requests_per_minute: Max requests per minute per client (default: 100)
        requests_per_hour: Max requests per hour per client (default: None = unlimited)
        backend: Storage backend - "memory" or "redis" (default: "memory")
        redis_url: Redis URL if backend="redis"
        key_func: Optional custom key function for rate limit grouping
        exempt_paths: Paths exempt from rate limiting

    Evidence:
        - enterprise-app: middleware/rate_limit.py (200 lines)
        - example-project: core/rate_limiter.py (180 lines)
        - example-app: utils/rate_limit.py (150 lines)
    """
    requests_per_minute: int = 100
    requests_per_hour: Optional[int] = None
    backend: str = "memory"  # "memory" or "redis"
    redis_url: Optional[str] = None
    key_func: Optional[Callable] = None  # Custom key extraction
    exempt_paths: List[str] = field(default_factory=list)


@dataclass
class AuditConfig:
    """Audit logging configuration.

    Attributes:
        enabled: Enable audit logging (default: True)
        log_request_body: Log request bodies (default: False for privacy)
        log_response_body: Log response bodies (default: False)
        exclude_paths: Paths to exclude from audit (e.g., /health)
        include_headers: Headers to include in audit (default: auth headers only)
        storage: Audit storage - "log", "database", "both"

    Evidence:
        - enterprise-app: middleware/audit.py (350 lines)
        - example-project: core/audit_log.py (200 lines)
        - example-app: utils/audit_helpers.py (175 lines)
    """
    enabled: bool = True
    log_request_body: bool = False
    log_response_body: bool = False
    exclude_paths: List[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs"]
    )
    include_headers: List[str] = field(
        default_factory=lambda: ["Authorization", "X-Tenant-ID", "X-Request-ID"]
    )
    storage: str = "log"  # "log", "database", "both"


class NexusAuthPlugin(NexusPlugin):
    """Unified authentication plugin for Nexus.

    Provides:
        - JWT authentication (symmetric + asymmetric)
        - RBAC with hierarchical roles and permissions
        - SSO integration (Azure AD, Google, Apple, GitHub)
        - Rate limiting (memory or Redis backend)
        - Multi-tenant isolation
        - Comprehensive audit logging

    Usage:
        >>> from nexus.auth import NexusAuthPlugin
        >>> from nexus.auth.sso import AzureADProvider, GoogleProvider
        >>>
        >>> auth = NexusAuthPlugin(
        ...     jwt_secret="your-256-bit-secret",
        ...     jwt_algorithm="HS256",
        ...     roles={
        ...         "admin": ["*"],
        ...         "editor": ["read:*", "write:*"],
        ...         "viewer": ["read:*"],
        ...     },
        ...     sso_providers=[
        ...         AzureADProvider(
        ...             tenant_id=os.getenv("AZURE_TENANT_ID"),
        ...             client_id=os.getenv("AZURE_CLIENT_ID"),
        ...             client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        ...         ),
        ...     ],
        ...     rate_limit=RateLimitConfig(requests_per_minute=100),
        ...     tenant_isolation=True,
        ...     audit_logging=True,
        ... )
        >>> app.add_plugin(auth)

    Evidence:
        This class consolidates patterns from:
        - enterprise-app/middleware/auth.py (180 lines JWT)
        - enterprise-app/middleware/rbac.py (425 lines RBAC+ABAC)
        - example-project/core/jwt_handler.py (348 lines)
        - example-project/core/rbac.py (435 lines)
        - example-app/utils/jwt.py (143 lines)
        - example-app/auth/admin_permissions.py (177 lines)
    """

    def __init__(
        self,
        # JWT Configuration (symmetric)
        jwt_secret: Optional[str] = None,
        jwt_algorithm: str = "HS256",
        # JWT Configuration (asymmetric)
        jwt_public_key: Optional[Union[str, Path]] = None,
        jwt_private_key: Optional[Union[str, Path]] = None,
        # Token settings
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        # Token extraction
        token_url: str = "/auth/token",
        token_header: str = "Authorization",
        token_cookie: Optional[str] = None,  # Cookie name for token
        token_query_param: Optional[str] = None,  # For WebSocket auth
        # Issuer/audience validation
        jwt_issuer: Optional[str] = None,
        jwt_audience: Optional[Union[str, List[str]]] = None,
        # RBAC Configuration
        roles: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        default_role: Optional[str] = None,
        # SSO Providers
        sso_providers: Optional[List[Any]] = None,  # List[SSOProvider]
        sso_callback_url: Optional[str] = None,
        # Rate Limiting
        rate_limit: Optional[Union[int, RateLimitConfig]] = None,
        # Tenant Isolation
        tenant_isolation: bool = False,
        tenant_header: str = "X-Tenant-ID",
        tenant_from_jwt: bool = True,  # Extract tenant from JWT claim
        tenant_claim: str = "tenant_id",
        # Audit Logging
        audit_logging: Union[bool, AuditConfig] = False,
        # Path exemptions
        exempt_paths: Optional[List[str]] = None,
        # CSRF Protection
        csrf_protection: bool = False,
        csrf_exempt_methods: Optional[List[str]] = None,
    ):
        """Initialize NexusAuthPlugin.

        Args:
            jwt_secret: Secret key for HS256/HS384/HS512 algorithms
            jwt_algorithm: JWT algorithm (HS256, RS256, ES256, etc.)
            jwt_public_key: Public key path/string for RS*/ES* algorithms
            jwt_private_key: Private key path/string for RS*/ES* algorithms
            access_token_expire_minutes: Access token lifetime (default: 30)
            refresh_token_expire_days: Refresh token lifetime (default: 7)
            token_url: URL for token endpoint (default: /auth/token)
            token_header: Header name for Bearer token (default: Authorization)
            token_cookie: Cookie name for token (optional, for browser apps)
            token_query_param: Query param for token (optional, for WebSocket)
            jwt_issuer: Expected JWT issuer (optional)
            jwt_audience: Expected JWT audience (optional)
            roles: Role definitions with permissions
            default_role: Role assigned to new users (optional)
            sso_providers: List of SSO provider instances
            sso_callback_url: Base URL for SSO callbacks
            rate_limit: Rate limiting config (int for simple req/min)
            tenant_isolation: Enable tenant isolation (default: False)
            tenant_header: Header for tenant ID (default: X-Tenant-ID)
            tenant_from_jwt: Extract tenant from JWT (default: True)
            tenant_claim: JWT claim for tenant ID (default: tenant_id)
            audit_logging: Enable audit logging (bool or AuditConfig)
            exempt_paths: Paths exempt from authentication
            csrf_protection: Enable CSRF protection (default: False)
            csrf_exempt_methods: Methods exempt from CSRF (default: GET, HEAD, OPTIONS)

        Raises:
            ValueError: If neither jwt_secret nor jwt_public_key provided
            ValueError: If asymmetric algorithm used without keys
        """
        # Validate configuration
        self._validate_config(
            jwt_secret, jwt_algorithm, jwt_public_key, jwt_private_key
        )

        # Store configuration
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_public_key = self._load_key(jwt_public_key) if jwt_public_key else None
        self.jwt_private_key = self._load_key(jwt_private_key) if jwt_private_key else None
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.token_url = token_url
        self.token_header = token_header
        self.token_cookie = token_cookie
        self.token_query_param = token_query_param
        self.jwt_issuer = jwt_issuer
        self.jwt_audience = jwt_audience

        # RBAC
        self.roles = self._normalize_roles(roles or {})
        self.default_role = default_role

        # SSO
        self.sso_providers = sso_providers or []
        self.sso_callback_url = sso_callback_url

        # Rate limiting
        self.rate_limit_config = self._normalize_rate_limit(rate_limit)

        # Tenant isolation
        self.tenant_isolation = tenant_isolation
        self.tenant_header = tenant_header
        self.tenant_from_jwt = tenant_from_jwt
        self.tenant_claim = tenant_claim

        # Audit
        self.audit_config = self._normalize_audit(audit_logging)

        # Exemptions
        self.exempt_paths = exempt_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/refresh",
            "/auth/sso/*",
        ]

        # CSRF
        self.csrf_protection = csrf_protection
        self.csrf_exempt_methods = csrf_exempt_methods or ["GET", "HEAD", "OPTIONS"]

        # Internal state (populated during apply)
        self._nexus_instance = None
        self._jwt_middleware = None
        self._rbac_middleware = None
        self._rate_limit_middleware = None
        self._tenant_middleware = None
        self._audit_middleware = None

        logger.info("NexusAuthPlugin initialized")

    @property
    def name(self) -> str:
        """Plugin name for registration."""
        return "nexus_auth"

    @property
    def description(self) -> str:
        """Plugin description."""
        return "Unified authentication: JWT + RBAC + SSO + Rate Limiting + Tenant Isolation + Audit"

    def install(self, app: Any) -> None:
        """Install authentication plugin into Nexus instance.

        This method:
        1. Registers middleware in correct order (outermost to innermost):
           rate_limit -> audit -> cors -> jwt -> rbac -> tenant
        2. Registers auth-related routes (/auth/*)
        3. Provides FastAPI dependencies for endpoint-level checks

        Args:
            app: The Nexus instance to install into (matches NexusPluginProtocol)
        """
        nexus_instance = app  # Alias for clarity in method body
        self._nexus_instance = nexus_instance

        logger.info("Applying NexusAuthPlugin to Nexus instance")

        # Get FastAPI app from gateway
        if not hasattr(nexus_instance, "_gateway") or not nexus_instance._gateway:
            raise RuntimeError("Nexus gateway not initialized")

        fastapi_app = nexus_instance._gateway.app

        # Register middleware in correct order (LIFO - last added = outermost)
        # Order: rate_limit (outer) -> audit -> jwt -> rbac -> tenant (inner)

        # 5. Tenant isolation (innermost - runs last)
        if self.tenant_isolation:
            self._apply_tenant_middleware(fastapi_app)

        # 4. RBAC (runs after JWT extracts user)
        if self.roles:
            self._apply_rbac_middleware(fastapi_app)

        # 3. JWT authentication
        self._apply_jwt_middleware(fastapi_app)

        # 2. Audit logging
        if self.audit_config and self.audit_config.enabled:
            self._apply_audit_middleware(fastapi_app)

        # 1. Rate limiting (outermost - runs first)
        if self.rate_limit_config:
            self._apply_rate_limit_middleware(fastapi_app)

        # Register auth routes
        self._register_auth_routes(fastapi_app)

        # Register SSO routes
        if self.sso_providers:
            self._register_sso_routes(fastapi_app)

        # Store reference on Nexus instance
        nexus_instance._auth_plugin = self
        nexus_instance._auth_enabled = True

        logger.info(
            f"NexusAuthPlugin applied: "
            f"JWT={self.jwt_algorithm}, "
            f"roles={len(self.roles)}, "
            f"SSO={len(self.sso_providers)} providers, "
            f"rate_limit={self.rate_limit_config is not None}, "
            f"tenant={self.tenant_isolation}, "
            f"audit={self.audit_config.enabled if self.audit_config else False}"
        )

    def validate(self) -> bool:
        """Validate plugin configuration."""
        # Check JWT configuration
        if self.jwt_algorithm.startswith("HS"):
            if not self.jwt_secret:
                logger.error("HS* algorithm requires jwt_secret")
                return False
        elif self.jwt_algorithm.startswith("RS") or self.jwt_algorithm.startswith("ES"):
            if not self.jwt_public_key:
                logger.error(f"{self.jwt_algorithm} algorithm requires jwt_public_key")
                return False

        # Check SSO providers
        for provider in self.sso_providers:
            if not hasattr(provider, "name") or not hasattr(provider, "get_authorization_url"):
                logger.error(f"Invalid SSO provider: {provider}")
                return False

        return True

    # --- Private Methods ---

    def _validate_config(
        self,
        jwt_secret: Optional[str],
        jwt_algorithm: str,
        jwt_public_key: Optional[Union[str, Path]],
        jwt_private_key: Optional[Union[str, Path]],
    ) -> None:
        """Validate JWT configuration."""
        symmetric_algorithms = {"HS256", "HS384", "HS512"}
        asymmetric_algorithms = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

        if jwt_algorithm in symmetric_algorithms:
            if not jwt_secret:
                raise ValueError(
                    f"{jwt_algorithm} requires jwt_secret. "
                    f"Generate with: import secrets; secrets.token_urlsafe(32)"
                )
        elif jwt_algorithm in asymmetric_algorithms:
            if not jwt_public_key:
                raise ValueError(
                    f"{jwt_algorithm} requires jwt_public_key for verification"
                )
            # Private key only needed for signing (issuing tokens)
        else:
            raise ValueError(f"Unsupported JWT algorithm: {jwt_algorithm}")

    def _load_key(self, key: Union[str, Path]) -> str:
        """Load key from file path or return string directly."""
        if isinstance(key, Path):
            return key.read_text()
        elif isinstance(key, str) and Path(key).exists():
            return Path(key).read_text()
        return key

    def _normalize_roles(
        self, roles: Dict[str, Union[List[str], Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Any]]:
        """Normalize role definitions to standard format."""
        normalized = {}
        for role_name, role_def in roles.items():
            if isinstance(role_def, list):
                # Simple format: ["permission1", "permission2"]
                normalized[role_name] = {
                    "permissions": role_def,
                    "description": f"Role: {role_name}",
                    "inherits": [],
                }
            elif isinstance(role_def, dict):
                # Full format: {"permissions": [...], "description": "...", "inherits": [...]}
                normalized[role_name] = {
                    "permissions": role_def.get("permissions", []),
                    "description": role_def.get("description", f"Role: {role_name}"),
                    "inherits": role_def.get("inherits", []),
                }
            else:
                raise ValueError(f"Invalid role definition for {role_name}: {role_def}")
        return normalized

    def _normalize_rate_limit(
        self, rate_limit: Optional[Union[int, RateLimitConfig]]
    ) -> Optional[RateLimitConfig]:
        """Normalize rate limit configuration."""
        if rate_limit is None:
            return None
        if isinstance(rate_limit, int):
            return RateLimitConfig(requests_per_minute=rate_limit)
        return rate_limit

    def _normalize_audit(
        self, audit: Union[bool, AuditConfig]
    ) -> Optional[AuditConfig]:
        """Normalize audit configuration."""
        if audit is False:
            return None
        if audit is True:
            return AuditConfig()
        return audit

    def _apply_jwt_middleware(self, app: Any) -> None:
        """Apply JWT authentication middleware."""
        from nexus.auth.jwt import JWTMiddleware

        self._jwt_middleware = JWTMiddleware(
            secret=self.jwt_secret,
            algorithm=self.jwt_algorithm,
            public_key=self.jwt_public_key,
            private_key=self.jwt_private_key,
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
            token_header=self.token_header,
            token_cookie=self.token_cookie,
            token_query_param=self.token_query_param,
            exempt_paths=self.exempt_paths,
        )

        app.add_middleware(JWTMiddleware, config=self._jwt_middleware.config)

    def _apply_rbac_middleware(self, app: Any) -> None:
        """Apply RBAC middleware."""
        from nexus.auth.rbac import RBACMiddleware

        self._rbac_middleware = RBACMiddleware(
            roles=self.roles,
            default_role=self.default_role,
        )

        # Note: RBAC middleware is registered but actual checks are done
        # via require_role() and require_permission() dependencies

    def _apply_rate_limit_middleware(self, app: Any) -> None:
        """Apply rate limiting middleware."""
        from nexus.auth.rate_limit import RateLimitMiddleware

        self._rate_limit_middleware = RateLimitMiddleware(
            config=self.rate_limit_config,
            exempt_paths=self.exempt_paths + (self.rate_limit_config.exempt_paths or []),
        )

        app.add_middleware(
            RateLimitMiddleware,
            config=self.rate_limit_config,
        )

    def _apply_tenant_middleware(self, app: Any) -> None:
        """Apply tenant isolation middleware."""
        from nexus.auth.tenant import TenantIsolationMiddleware

        self._tenant_middleware = TenantIsolationMiddleware(
            header_name=self.tenant_header,
            from_jwt=self.tenant_from_jwt,
            jwt_claim=self.tenant_claim,
        )

        app.add_middleware(
            TenantIsolationMiddleware,
            header_name=self.tenant_header,
        )

    def _apply_audit_middleware(self, app: Any) -> None:
        """Apply audit logging middleware."""
        from nexus.auth.audit import AuditMiddleware

        self._audit_middleware = AuditMiddleware(config=self.audit_config)

        app.add_middleware(AuditMiddleware, config=self.audit_config)

    def _register_auth_routes(self, app: Any) -> None:
        """Register authentication routes."""
        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel

        router = APIRouter(prefix="/auth", tags=["Authentication"])

        class LoginRequest(BaseModel):
            username: str
            password: str

        class TokenResponse(BaseModel):
            access_token: str
            refresh_token: str
            token_type: str = "bearer"
            expires_in: int

        @router.post("/login", response_model=TokenResponse)
        async def login(request: LoginRequest):
            """Login endpoint - implement in your application."""
            raise HTTPException(
                status_code=501,
                detail="Login endpoint must be implemented by application"
            )

        @router.post("/refresh", response_model=TokenResponse)
        async def refresh(refresh_token: str):
            """Refresh access token."""
            # Implementation in jwt.py
            from nexus.auth.jwt import refresh_access_token
            return await refresh_access_token(refresh_token, self)

        @router.post("/logout")
        async def logout():
            """Logout endpoint."""
            # Implementation depends on token storage strategy
            return {"message": "Logged out successfully"}

        app.include_router(router)

    def _register_sso_routes(self, app: Any) -> None:
        """Register SSO routes for each provider."""
        from fastapi import APIRouter

        for provider in self.sso_providers:
            router = APIRouter(
                prefix=f"/auth/sso/{provider.name}",
                tags=["SSO"]
            )

            @router.get("/login")
            async def sso_login(provider=provider):
                """Redirect to SSO provider."""
                from nexus.auth.sso import initiate_sso_login
                return await initiate_sso_login(provider, self.sso_callback_url)

            @router.get("/callback")
            async def sso_callback(code: str, state: str, provider=provider):
                """Handle SSO callback."""
                from nexus.auth.sso import handle_sso_callback
                return await handle_sso_callback(provider, code, state, self)

            @router.post("/token")
            async def sso_token(code: str, provider=provider):
                """Exchange code for token (SPA flow)."""
                from nexus.auth.sso import exchange_sso_code
                return await exchange_sso_code(provider, code, self)

            app.include_router(router)


# Convenience exports
from nexus.auth.dependencies import get_current_user, require_auth, require_permission, require_role
from nexus.auth.models import AuthenticatedUser

__all__ = [
    "NexusAuthPlugin",
    "RateLimitConfig",
    "AuditConfig",
    "AuthenticatedUser",
    "get_current_user",
    "require_auth",
    "require_role",
    "require_permission",
]
```

---

## Plugin Installation Flow

### Middleware Registration Order

The middleware order is critical for correct operation. Middleware is registered in LIFO order (last added runs first):

```
Request Flow:
    Client Request
         |
    [1] RateLimitMiddleware     # Reject if rate exceeded
         |
    [2] AuditMiddleware         # Log request start
         |
    [3] CORSMiddleware          # Handle CORS (FastAPI default)
         |
    [4] JWTMiddleware           # Extract and verify token
         |
    [5] RBACMiddleware          # Check role-based permissions
         |
    [6] TenantMiddleware        # Validate tenant context
         |
    Route Handler (endpoint)
         |
    Response flows back up through middleware
```

### Integration with Existing Nexus

```python
# In nexus/core.py, add plugin support:
class Nexus:
    def add_plugin(self, plugin: NexusPlugin) -> "Nexus":
        """Add a plugin to enhance Nexus functionality.

        Args:
            plugin: Plugin instance (must inherit from NexusPlugin)

        Returns:
            Self for chaining
        """
        if not plugin.validate():
            raise ValueError(f"Plugin {plugin.name} validation failed")

        plugin.apply(self)

        if not hasattr(self, "_plugins"):
            self._plugins = {}
        self._plugins[plugin.name] = plugin

        logger.info(f"Plugin '{plugin.name}' applied successfully")
        return self
```

---

## Dependencies

### Required (install with plugin)

```
pyjwt>=2.8.0           # JWT encoding/decoding
python-jose[cryptography]>=3.3.0  # Extended JWT support (JWK, JWE)
bcrypt>=4.0.0          # Password hashing
passlib>=1.7.4         # Password hashing utilities
```

### Optional (install as needed)

```
redis>=5.0.0           # Rate limiting with Redis backend
httpx>=0.25.0          # SSO provider callbacks (async HTTP)
aioredis>=2.0.0        # Async Redis for rate limiting
```

### Package Installation

```bash
# Minimal installation
pip install kailash-nexus[auth]

# With Redis support
pip install kailash-nexus[auth,redis]

# With all SSO providers
pip install kailash-nexus[auth,sso]

# Everything
pip install kailash-nexus[auth,redis,sso]
```

---

## Testing Strategy

### Tier 1: Unit Tests (Mocking Allowed)

```python
# tests/unit/auth/test_jwt_parsing.py
"""Unit tests for JWT parsing logic."""
import pytest
from nexus.auth.jwt import parse_jwt_claims, validate_jwt_structure

def test_parse_jwt_claims_extracts_standard_claims():
    """Test that standard JWT claims are extracted correctly."""
    token_payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "roles": ["admin"],
        "tenant_id": "tenant-456",
    }

    user = parse_jwt_claims(token_payload)

    assert user.user_id == "user-123"
    assert user.email == "user@example.com"
    assert user.roles == ["admin"]
    assert user.tenant_id == "tenant-456"

def test_permission_wildcard_matching():
    """Test permission wildcard matching logic."""
    from nexus.auth.rbac import matches_permission

    # Exact match
    assert matches_permission("read:users", "read:users") is True

    # Wildcard action
    assert matches_permission("read:*", "read:users") is True
    assert matches_permission("read:*", "write:users") is False

    # Super wildcard
    assert matches_permission("*", "read:users") is True
    assert matches_permission("*", "write:articles") is True
```

### Tier 2: Integration Tests (Real Infrastructure)

```python
# tests/integration/auth/test_jwt_flow.py
"""Integration tests for JWT authentication flow."""
import pytest
from nexus import Nexus
from nexus.auth import NexusAuthPlugin

@pytest.fixture
def auth_app():
    """Create Nexus app with auth plugin."""
    app = Nexus(api_port=8001)
    auth = NexusAuthPlugin(
        jwt_secret="test-secret-key-at-least-32-chars",
        jwt_algorithm="HS256",
        roles={"admin": ["*"], "viewer": ["read:*"]},
    )
    app.add_plugin(auth)
    return app

@pytest.mark.asyncio
async def test_jwt_authentication_flow(auth_app):
    """Test complete JWT authentication flow."""
    from httpx import AsyncClient

    async with AsyncClient(app=auth_app._gateway.app, base_url="http://test") as client:
        # Access protected endpoint without token
        response = await client.get("/workflows/test/info")
        assert response.status_code == 401

        # Get token (would normally be from login)
        from nexus.auth.jwt import create_access_token
        token = create_access_token(
            auth_app._auth_plugin,
            user_id="test-user",
            roles=["admin"],
        )

        # Access with valid token
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.get("/workflows/test/info", headers=headers)
        # Note: 404 expected if workflow doesn't exist, but not 401
        assert response.status_code != 401
```

### Tier 3: E2E Tests (Full System)

```python
# tests/e2e/auth/test_complete_auth_workflow.py
"""E2E tests for complete authentication workflow."""
import pytest
import asyncio
from nexus import Nexus
from nexus.auth import NexusAuthPlugin

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_auth_workflow_with_rbac():
    """Test complete auth workflow including RBAC."""
    # Start Nexus in background
    app = Nexus(api_port=8888)
    auth = NexusAuthPlugin(
        jwt_secret="e2e-test-secret-key-32-chars-min",
        roles={
            "admin": ["*"],
            "editor": ["read:*", "write:articles"],
            "viewer": ["read:*"],
        },
    )
    app.add_plugin(auth)

    # Register test workflow
    from kailash.workflow.builder import WorkflowBuilder
    wf = WorkflowBuilder()
    wf.add_node("ConstantNode", "result", {"value": "test"})
    app.register("test_workflow", wf.build())

    # Start server in background
    import threading
    server_thread = threading.Thread(target=app.start, daemon=True)
    server_thread.start()
    await asyncio.sleep(1)  # Wait for startup

    try:
        from httpx import AsyncClient
        async with AsyncClient(base_url="http://localhost:8888") as client:
            # Test viewer can read but not write
            viewer_token = auth._jwt_middleware.create_token(
                user_id="viewer-1",
                roles=["viewer"],
            )

            # Can read
            response = await client.get(
                "/workflows/test_workflow/info",
                headers={"Authorization": f"Bearer {viewer_token}"}
            )
            assert response.status_code == 200

            # Cannot execute (write operation)
            # This depends on how execute permission is configured
    finally:
        app.stop()
```

---

## Error Handling

### Exception Hierarchy

```python
# nexus/auth/exceptions.py
"""Authentication and authorization exceptions."""

class AuthError(Exception):
    """Base class for auth errors."""
    status_code: int = 500
    detail: str = "Authentication error"

class AuthenticationError(AuthError):
    """Authentication failed (401)."""
    status_code = 401
    detail = "Not authenticated"

class InvalidTokenError(AuthenticationError):
    """Token is invalid."""
    detail = "Invalid authentication token"

class ExpiredTokenError(AuthenticationError):
    """Token has expired."""
    detail = "Token has expired"

class AuthorizationError(AuthError):
    """Authorization failed (403)."""
    status_code = 403
    detail = "Not authorized"

class InsufficientPermissionError(AuthorizationError):
    """User lacks required permission."""
    def __init__(self, permission: str):
        self.detail = f"Missing required permission: {permission}"
        super().__init__(self.detail)

class InsufficientRoleError(AuthorizationError):
    """User lacks required role."""
    def __init__(self, roles: list):
        self.detail = f"Requires one of roles: {', '.join(roles)}"
        super().__init__(self.detail)

class TenantAccessError(AuthorizationError):
    """Tenant access denied."""
    detail = "Access to this tenant is not allowed"

class RateLimitExceededError(AuthError):
    """Rate limit exceeded (429)."""
    status_code = 429
    detail = "Rate limit exceeded"
```

---

## Configuration Reference

| Parameter                     | Type                | Default          | Description                |
| ----------------------------- | ------------------- | ---------------- | -------------------------- |
| `jwt_secret`                  | str                 | None             | Secret for HS\* algorithms |
| `jwt_algorithm`               | str                 | "HS256"          | JWT algorithm              |
| `jwt_public_key`              | str/Path            | None             | Public key for RS*/ES*     |
| `jwt_private_key`             | str/Path            | None             | Private key for RS*/ES*    |
| `access_token_expire_minutes` | int                 | 30               | Access token lifetime      |
| `refresh_token_expire_days`   | int                 | 7                | Refresh token lifetime     |
| `roles`                       | dict                | {}               | Role definitions           |
| `sso_providers`               | list                | []               | SSO provider instances     |
| `rate_limit`                  | int/RateLimitConfig | None             | Rate limiting config       |
| `tenant_isolation`            | bool                | False            | Enable tenant isolation    |
| `tenant_header`               | str                 | "X-Tenant-ID"    | Tenant ID header           |
| `audit_logging`               | bool/AuditConfig    | False            | Audit logging config       |
| `exempt_paths`                | list                | ["/health", ...] | Paths exempt from auth     |

---

## Migration from Existing Projects

### From enterprise-app

```python
# Before (enterprise-app)
from middleware.auth import JWTAuthMiddleware
from middleware.rbac import RBACService, require_role

app.add_middleware(JWTAuthMiddleware, secret=SECRET)
rbac = RBACService(roles=ROLE_CONFIG)

# After (NexusAuthPlugin)
from nexus.auth import NexusAuthPlugin

auth = NexusAuthPlugin(
    jwt_secret=SECRET,
    roles=ROLE_CONFIG,  # Same format
)
app.add_plugin(auth)
```

### From example-project

```python
# Before (example-project)
from core.jwt_handler import JWTHandler
from core.rbac import RBACManager, require_permission

jwt = JWTHandler(secret_key=SECRET)
rbac = RBACManager()

# After (NexusAuthPlugin)
from nexus.auth import NexusAuthPlugin

auth = NexusAuthPlugin(
    jwt_secret=SECRET,
    roles={
        "admin": ["*"],
        "moderator": ["read:*", "write:*", "delete:flagged"],
        "creator": ["read:*", "write:own"],
        "viewer": ["read:*"],
    },
)
app.add_plugin(auth)
```

### From example-backend

```python
# Before (example-app)
from utils.jwt import JWTValidator
from utils.azure_jwt import AzureJWTValidator
from auth.admin_permissions import AdminScope, has_admin_permission

jwt = JWTValidator(secret=SECRET)
azure_jwt = AzureJWTValidator(tenant_id=AZURE_TENANT)

# After (NexusAuthPlugin)
from nexus.auth import NexusAuthPlugin
from nexus.auth.sso import AzureADProvider

auth = NexusAuthPlugin(
    jwt_secret=SECRET,
    sso_providers=[
        AzureADProvider(
            tenant_id=AZURE_TENANT,
            client_id=AZURE_CLIENT,
            client_secret=AZURE_SECRET,
        ),
    ],
    tenant_isolation=True,
)
app.add_plugin(auth)
```
