"""Scaffolding Template 1: SaaS API Backend - Validation Tests.

Validates the SaaS API template from the codegen decision tree.
Tests that the template patterns work with correct WS02 auth imports.
"""

import time

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from nexus import Nexus
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequirePermission, RequireRole, get_current_user
from nexus.auth.plugin import NexusAuthPlugin

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import LocalRuntime

TEST_SECRET = "test-saas-template-secret-256bit"


def _make_token(payload: dict) -> str:
    defaults = {
        "sub": "user-1",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "roles": ["member"],
        "tenant_id": "org-1",
    }
    defaults.update(payload)
    return jwt.encode(defaults, TEST_SECRET, algorithm="HS256")


class TestSaaSAPITemplate:
    """Validate SaaS API Template patterns."""

    @pytest.fixture
    def saas_app(self):
        """Create SaaS API app following the template pattern."""
        app = FastAPI()

        auth = NexusAuthPlugin(
            jwt=JWTConfig(
                secret=TEST_SECRET,
                algorithm="HS256",
                exempt_paths=["/health"],
            ),
            rbac={
                "admin": ["*"],
                "member": [
                    "users:read",
                    "contacts:read",
                    "contacts:create",
                    "contacts:update",
                ],
                "viewer": ["users:read", "contacts:read"],
            },
            tenant_isolation=TenantConfig(
                jwt_claim="tenant_id",
                validate_tenant_exists=False,
                validate_tenant_active=False,
                allow_admin_override=True,
                admin_role="admin",
                exclude_paths=["/health"],
            ),
        )

        auth.install(app)

        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "version": "1.0.0"}

        @app.post("/contacts")
        async def create_contact(user=Depends(RequirePermission("contacts:create"))):
            return {"created": True, "user_id": user.user_id}

        @app.get("/contacts")
        async def list_contacts(user=Depends(RequirePermission("contacts:read"))):
            return {"contacts": [], "total": 0}

        @app.delete("/contacts/{contact_id}")
        async def delete_contact(
            contact_id: str, user=Depends(RequirePermission("contacts:delete"))
        ):
            return {"deleted": True, "id": contact_id}

        return TestClient(app)

    def test_health_endpoint_public(self, saas_app):
        """Health check is public (no auth)."""
        response = saas_app.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_create_contact_member(self, saas_app):
        """Member can create contacts."""
        token = _make_token({"roles": ["member"]})
        response = saas_app.post(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_list_contacts_viewer(self, saas_app):
        """Viewer can read contacts."""
        token = _make_token({"roles": ["viewer"]})
        response = saas_app.get(
            "/contacts", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_delete_contacts_admin_only(self, saas_app):
        """Only admin can delete (viewer/member lack contacts:delete)."""
        token = _make_token({"roles": ["admin"]})
        response = saas_app.delete(
            "/contacts/c-123", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_delete_rejected_for_member(self, saas_app):
        """Member cannot delete contacts."""
        token = _make_token({"roles": ["member"]})
        response = saas_app.delete(
            "/contacts/c-123", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403

    def test_no_auth_rejected(self, saas_app):
        """Protected endpoints require auth."""
        response = saas_app.post("/contacts")
        assert response.status_code == 401

    def test_handler_with_nexus_registration(self):
        """Handler registration on Nexus follows template pattern."""
        app = Nexus(auto_discovery=False)

        @app.handler("create_contact", description="Create a new contact")
        async def create_contact(email: str, name: str, company: str = None) -> dict:
            return {"email": email, "name": name, "company": company}

        assert "create_contact" in app._handler_registry
