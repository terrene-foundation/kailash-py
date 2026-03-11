"""Shared fixtures for auth E2E tests (TODO-310H).

Tier 3 tests - NO MOCKING. Real FastAPI app with real middleware stack,
real JWT tokens, real RBAC enforcement, real audit logging.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nexus.auth.audit.config import AuditConfig
from nexus.auth.dependencies import require_permission, require_role
from nexus.auth.jwt import JWTConfig
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import get_current_tenant_id

# Test secret used across all E2E tests
TEST_SECRET = "e2e-test-secret-key-very-secure-123"


@pytest.fixture
def jwt_config():
    """JWT configuration for E2E tests."""
    return JWTConfig(
        secret=TEST_SECRET,
        exempt_paths=["/health", "/api/public"],
    )


@pytest.fixture
def create_token():
    """Factory to create JWT tokens for testing."""

    def _create(
        user_id: str = "user-1",
        email: str = "user@example.com",
        roles: Optional[list] = None,
        permissions: Optional[list] = None,
        tenant_id: Optional[str] = None,
        expired: bool = False,
        **extra_claims,
    ) -> str:
        now = datetime.now(timezone.utc)
        if expired:
            exp = now - timedelta(hours=1)
        else:
            exp = now + timedelta(hours=1)

        payload = {
            "sub": user_id,
            "email": email,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "token_type": "access",
        }
        if roles:
            payload["roles"] = roles
        if permissions:
            payload["permissions"] = permissions
        if tenant_id:
            payload["tenant_id"] = tenant_id
        payload.update(extra_claims)

        return pyjwt.encode(payload, TEST_SECRET, algorithm="HS256")

    return _create


@pytest.fixture
def full_auth_app(jwt_config):
    """FastAPI app with complete auth stack (JWT + RBAC + tenant + rate limit + audit)."""
    app = FastAPI()

    plugin = NexusAuthPlugin(
        jwt=jwt_config,
        rbac={
            "admin": ["*"],
            "user": ["read:profile", "write:profile", "read:data"],
            "viewer": ["read:data"],
        },
        # Rate limiting tested separately in test_security_e2e.py
        # with isolated per-test apps to avoid shared state.
        tenant_isolation=TenantConfig(
            jwt_claim="tenant_id",
            validate_tenant_exists=False,
            validate_tenant_active=False,
            allow_admin_override=True,
            admin_role="admin",
            exclude_paths=["/health", "/api/public"],
        ),
        audit=AuditConfig(
            backend="logging",
            exclude_paths=["/health"],
        ),
    )
    plugin.install(app)

    # --- Public endpoints ---

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/public")
    async def public_endpoint():
        return {"message": "public data"}

    # --- Protected endpoints ---

    @app.get("/api/profile")
    async def get_profile(request: Request):
        user = getattr(request.state, "user", None)
        # Use contextvars first, fall back to request.state (BaseHTTPMiddleware compat)
        tenant = get_current_tenant_id() or getattr(request.state, "tenant_id", None)
        return {
            "user_id": user.user_id if user else None,
            "email": user.email if user else None,
            "tenant_id": tenant,
        }

    @app.get("/api/data")
    async def get_data(
        request: Request,
        user=Depends(require_permission("read:data")),
    ):
        # Use contextvars first, fall back to request.state (BaseHTTPMiddleware compat)
        tenant = get_current_tenant_id() or getattr(request.state, "tenant_id", None)
        return {
            "data": [1, 2, 3],
            "tenant_id": tenant,
            "user_id": user.user_id,
        }

    @app.get("/api/admin/users")
    async def admin_users(
        request: Request,
        user=Depends(require_role("admin")),
    ):
        return {"users": [], "admin_id": user.user_id}

    @app.post("/api/admin/settings")
    async def admin_settings(
        request: Request,
        user=Depends(require_permission("write:settings")),
    ):
        return {"updated": True}

    @app.get("/api/error")
    async def error_endpoint(request: Request):
        return JSONResponse(status_code=500, content={"error": "Internal error"})

    return app


@pytest.fixture
def full_auth_client(full_auth_app):
    """TestClient for the full auth app."""
    return TestClient(full_auth_app)


@pytest.fixture
def auth_header(create_token):
    """Factory to create Authorization header."""

    def _header(
        user_id="user-1",
        roles=None,
        permissions=None,
        tenant_id=None,
        expired=False,
        **extra,
    ):
        token = create_token(
            user_id=user_id,
            roles=roles,
            permissions=permissions,
            tenant_id=tenant_id,
            expired=expired,
            **extra,
        )
        return {"Authorization": f"Bearer {token}"}

    return _header
