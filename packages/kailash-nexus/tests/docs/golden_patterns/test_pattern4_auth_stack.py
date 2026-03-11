"""Golden Pattern 4: Auth Middleware Stack - Validation Tests.

Validates NexusAuthPlugin with CORRECT WS02 imports and configuration.
This is the most critical pattern to validate since the spec had incorrect imports.
"""

import time

import jwt
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequirePermission, RequireRole, get_current_user
from nexus.auth.plugin import NexusAuthPlugin

TEST_SECRET = "test-golden-pattern-4-secret-key-256bit"


def _make_token(payload: dict, secret: str = TEST_SECRET) -> str:
    """Create a JWT token."""
    defaults = {
        "sub": "user-1",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "roles": ["member"],
    }
    defaults.update(payload)
    return jwt.encode(defaults, secret, algorithm="HS256")


class TestGoldenPattern4AuthStack:
    """Validate Pattern 4: Auth Middleware Stack with correct WS02 imports."""

    @pytest.fixture
    def auth_app(self):
        """Create FastAPI app with NexusAuthPlugin."""
        app = FastAPI()

        # CORRECT WS02 pattern - this is what the golden pattern documents
        auth = NexusAuthPlugin(
            jwt=JWTConfig(
                secret=TEST_SECRET,  # CORRECT: 'secret' not 'secret_key'
                algorithm="HS256",
                exempt_paths=["/health"],  # CORRECT: 'exempt_paths' not 'exclude_paths'
            ),
            rbac={  # CORRECT: plain dict, not RBACConfig
                "admin": ["*"],
                "member": ["contacts:read", "contacts:create"],
                "viewer": ["contacts:read"],
            },
            tenant_isolation=TenantConfig(  # CORRECT: TenantConfig, not True
                jwt_claim="tenant_id",
                validate_tenant_exists=False,
                validate_tenant_active=False,
                allow_admin_override=True,
                admin_role="admin",  # CORRECT: singular 'admin_role'
                exclude_paths=["/health"],
            ),
        )

        auth.install(app)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.get("/admin")
        async def admin_only(user=Depends(RequireRole("admin"))):
            return {"admin": True, "user_id": user.user_id}

        @app.get("/contacts")
        async def list_contacts(user=Depends(RequirePermission("contacts:read"))):
            return {"contacts": [], "user_id": user.user_id}

        @app.post("/contacts")
        async def create_contact(user=Depends(RequirePermission("contacts:create"))):
            return {"created": True, "user_id": user.user_id}

        @app.get("/profile")
        async def profile(user=Depends(get_current_user)):
            return {"user_id": user.user_id, "roles": user.roles}

        return TestClient(app)

    def test_health_no_auth_required(self, auth_app):
        """Exempt paths don't require authentication."""
        response = auth_app.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_admin_with_admin_token(self, auth_app):
        """Admin endpoint accepts admin token."""
        token = _make_token({"roles": ["admin"], "tenant_id": "org-1"})
        response = auth_app.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["admin"] is True

    def test_admin_rejected_for_member(self, auth_app):
        """Admin endpoint rejects member token."""
        token = _make_token({"roles": ["member"], "tenant_id": "org-1"})
        response = auth_app.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_contacts_read_with_member(self, auth_app):
        """Member can read contacts."""
        token = _make_token({"roles": ["member"], "tenant_id": "org-1"})
        response = auth_app.get(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_contacts_create_with_member(self, auth_app):
        """Member can create contacts."""
        token = _make_token({"roles": ["member"], "tenant_id": "org-1"})
        response = auth_app.post(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["created"] is True

    def test_contacts_create_rejected_for_viewer(self, auth_app):
        """Viewer cannot create contacts."""
        token = _make_token({"roles": ["viewer"], "tenant_id": "org-1"})
        response = auth_app.post(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403

    def test_profile_any_authenticated(self, auth_app):
        """Any authenticated user can access profile."""
        token = _make_token({"roles": ["viewer"], "tenant_id": "org-1"})
        response = auth_app.get(
            "/profile", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == "user-1"

    def test_no_auth_rejected(self, auth_app):
        """Endpoints without auth header are rejected."""
        response = auth_app.get("/contacts")
        assert response.status_code == 401

    def test_expired_token_rejected(self, auth_app):
        """Expired tokens are rejected."""
        token = _make_token(
            {
                "exp": int(time.time()) - 100,
                "tenant_id": "org-1",
            }
        )
        response = auth_app.get(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_correct_import_paths(self):
        """Verify WS02 import paths are correct."""
        # These imports should all work - validates the golden pattern documentation
        from nexus.auth import JWTConfig, TenantConfig
        from nexus.auth.dependencies import (
            RequirePermission,
            RequireRole,
            get_current_user,
        )
        from nexus.auth.plugin import NexusAuthPlugin

        assert NexusAuthPlugin is not None
        assert JWTConfig is not None
        assert TenantConfig is not None
        assert RequireRole is not None
        assert RequirePermission is not None
        assert get_current_user is not None
