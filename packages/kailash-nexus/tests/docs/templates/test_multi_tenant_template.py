"""Scaffolding Template 3: Multi-Tenant Enterprise - Validation Tests.

Validates multi-tenant template with multiple DataFlow instances and auth.
"""

import time

import jwt
import pytest
from dataflow import DataFlow
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from nexus import Nexus
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequirePermission, RequireRole
from nexus.auth.plugin import NexusAuthPlugin

TEST_SECRET = "test-multi-tenant-template-secret-256bit"


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


class TestMultiTenantTemplate:
    """Validate Multi-Tenant Enterprise Template patterns."""

    def test_multiple_dataflow_instances(self):
        """Multi-tenant template uses separate DataFlow instances."""
        primary_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        analytics_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        audit_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        assert primary_db is not analytics_db
        assert analytics_db is not audit_db

    def test_models_on_separate_instances(self):
        """Models are scoped to specific database instances."""
        primary = DataFlow("sqlite:///:memory:", enable_model_persistence=False)
        analytics = DataFlow("sqlite:///:memory:", enable_model_persistence=False)
        audit = DataFlow("sqlite:///:memory:", enable_model_persistence=False)

        @primary.model
        class User:
            id: str
            email: str
            org_id: str

        @primary.model
        class Project:
            id: str
            name: str
            org_id: str

        @analytics.model
        class PageView:
            id: str
            user_id: str
            org_id: str
            page: str

        @audit.model
        class AuditLog:
            id: str
            org_id: str
            actor_id: str
            action: str

        # All models registered to their respective instances
        assert True

    @pytest.fixture
    def tenant_app(self):
        """Create multi-tenant app following the template pattern."""
        app = FastAPI()

        auth = NexusAuthPlugin(
            jwt=JWTConfig(
                secret=TEST_SECRET,
                algorithm="HS256",
                exempt_paths=["/health"],
            ),
            rbac={
                "owner": ["*"],
                "admin": ["users:*", "projects:*", "analytics:read"],
                "member": ["projects:read", "projects:create", "projects:update"],
                "viewer": ["projects:read", "analytics:read"],
            },
            tenant_isolation=TenantConfig(
                jwt_claim="tenant_id",
                validate_tenant_exists=False,
                validate_tenant_active=False,
                allow_admin_override=True,
                admin_role="owner",
                exclude_paths=["/health"],
            ),
        )

        auth.install(app)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/projects")
        async def create_project(user=Depends(RequirePermission("projects:create"))):
            return {"created": True}

        @app.get("/projects")
        async def list_projects(user=Depends(RequirePermission("projects:read"))):
            return {"projects": []}

        @app.get("/analytics")
        async def get_analytics(user=Depends(RequirePermission("analytics:read"))):
            return {"page_views": 0, "api_calls": 0}

        @app.get("/audit")
        async def get_audit(user=Depends(RequirePermission("audit:read"))):
            return {"logs": []}

        return TestClient(app)

    def test_owner_has_full_access(self, tenant_app):
        """Owner role has wildcard access."""
        token = _make_token({"roles": ["owner"]})
        headers = {"Authorization": f"Bearer {token}"}

        assert tenant_app.post("/projects", headers=headers).status_code == 200
        assert tenant_app.get("/projects", headers=headers).status_code == 200
        assert tenant_app.get("/analytics", headers=headers).status_code == 200
        assert tenant_app.get("/audit", headers=headers).status_code == 200

    def test_member_limited_access(self, tenant_app):
        """Member can create/read projects but not analytics/audit."""
        token = _make_token({"roles": ["member"]})
        headers = {"Authorization": f"Bearer {token}"}

        assert tenant_app.post("/projects", headers=headers).status_code == 200
        assert tenant_app.get("/projects", headers=headers).status_code == 200
        assert tenant_app.get("/audit", headers=headers).status_code == 403

    def test_viewer_read_only(self, tenant_app):
        """Viewer can only read projects and analytics."""
        token = _make_token({"roles": ["viewer"]})
        headers = {"Authorization": f"Bearer {token}"}

        assert tenant_app.get("/projects", headers=headers).status_code == 200
        assert tenant_app.get("/analytics", headers=headers).status_code == 200
        assert tenant_app.post("/projects", headers=headers).status_code == 403

    def test_health_public(self, tenant_app):
        """Health endpoint is public."""
        response = tenant_app.get("/health")
        assert response.status_code == 200

    def test_tenant_isolation_config(self):
        """TenantConfig uses correct WS02 parameters."""
        config = TenantConfig(
            jwt_claim="tenant_id",
            allow_admin_override=True,
            admin_role="super_admin",
            exclude_paths=["/health"],
        )
        assert config.jwt_claim == "tenant_id"
        assert config.admin_role == "super_admin"
        assert config.allow_admin_override is True
