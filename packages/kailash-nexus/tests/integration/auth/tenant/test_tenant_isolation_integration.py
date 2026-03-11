"""Integration tests for tenant isolation middleware (TODO-310E).

Tier 2 tests - NO MOCKING. Uses real FastAPI TestClient with real
middleware for tenant isolation testing.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import get_current_tenant, get_current_tenant_id
from nexus.auth.tenant.middleware import TenantMiddleware

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app_with_tenant_isolation():
    """Create a FastAPI app with tenant middleware."""
    app = FastAPI()

    config = TenantConfig(
        jwt_claim="org_id",
        validate_tenant_exists=False,
        exclude_paths=["/health", "/metrics"],
    )
    app.add_middleware(TenantMiddleware, config=config)

    @app.get("/health")
    async def health_endpoint():
        return {"status": "healthy"}

    @app.get("/api/data")
    async def get_data(request: Request):
        tenant = get_current_tenant()
        if tenant:
            return {"tenant_id": tenant.tenant_id}
        return {"tenant_id": None}

    @app.get("/api/tenant-id")
    async def get_tenant_id(request: Request):
        return {"tenant_id": get_current_tenant_id()}

    return app


@pytest.fixture
def client(app_with_tenant_isolation):
    """Create a TestClient."""
    return TestClient(app_with_tenant_isolation)


# =============================================================================
# Helper: Simulate auth middleware setting request state
# =============================================================================


def make_app_with_state_setup(config=None):
    """Create app where we can control request.state values."""
    app = FastAPI()

    if config is None:
        config = TenantConfig(
            jwt_claim="org_id",
            validate_tenant_exists=False,
            exclude_paths=["/health"],
        )

    # Use a simple middleware to set state before TenantMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware

    class FakeAuthMiddleware(BaseHTTPMiddleware):
        """Simulates auth middleware by setting state from custom headers."""

        async def dispatch(self, request, call_next):
            from nexus.auth.models import AuthenticatedUser

            # Read custom test headers to set state
            user_id = request.headers.get("X-Test-User-ID")
            roles = (
                request.headers.get("X-Test-Roles", "").split(",")
                if "X-Test-Roles" in request.headers
                else []
            )
            if user_id:
                request.state.user = AuthenticatedUser(
                    user_id=user_id,
                    roles=roles,
                )
            if "X-Test-Claims" in request.headers:
                import json

                request.state.token_payload = json.loads(
                    request.headers["X-Test-Claims"]
                )
            return await call_next(request)

    # Order matters: TenantMiddleware runs after FakeAuthMiddleware
    app.add_middleware(TenantMiddleware, config=config)
    app.add_middleware(FakeAuthMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/data")
    async def get_data(request: Request):
        tenant = get_current_tenant()
        return {"tenant_id": tenant.tenant_id if tenant else None}

    return app


# =============================================================================
# Tests: JWT Claim Resolution
# =============================================================================


class TestTenantFromJWTClaim:
    """Integration tests for tenant resolution from JWT claims (NO MOCKING)."""

    def test_tenant_from_jwt_claim(self):
        """Tenant resolved from JWT org_id claim."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        claims = json.dumps({"org_id": "tenant-123"})
        response = client.get(
            "/api/data",
            headers={"X-Test-Claims": claims},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "tenant-123"

    def test_tenant_header_in_response(self):
        """Response includes X-Tenant-ID header."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        claims = json.dumps({"org_id": "tenant-456"})
        response = client.get(
            "/api/data",
            headers={"X-Test-Claims": claims},
        )
        assert response.headers.get("X-Tenant-ID") == "tenant-456"

    def test_no_tenant_when_no_claims(self):
        """No tenant when no JWT claims."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        response = client.get("/api/data")
        assert response.status_code == 200
        assert response.json()["tenant_id"] is None


# =============================================================================
# Tests: Admin Override
# =============================================================================


class TestAdminOverride:
    """Integration tests for admin override via header (NO MOCKING)."""

    def test_admin_can_override_tenant(self):
        """Admin can use X-Tenant-ID header."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        claims = json.dumps({"org_id": "original-tenant"})
        response = client.get(
            "/api/data",
            headers={
                "X-Test-User-ID": "admin-user",
                "X-Test-Roles": "super_admin",
                "X-Test-Claims": claims,
                "X-Tenant-ID": "override-tenant",
            },
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "override-tenant"

    def test_non_admin_cannot_override(self):
        """Non-admin cannot use X-Tenant-ID header (fail-closed)."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        claims = json.dumps({"org_id": "my-tenant"})
        response = client.get(
            "/api/data",
            headers={
                "X-Test-User-ID": "regular-user",
                "X-Test-Roles": "user",
                "X-Test-Claims": claims,
                "X-Tenant-ID": "other-tenant",
            },
        )
        # Should get 403, not silently use the header
        assert response.status_code == 403
        assert response.json()["error_code"] == "TENANT_ACCESS_DENIED"

    def test_admin_override_disabled(self):
        """When admin override disabled, header always fails."""
        config = TenantConfig(
            jwt_claim="org_id",
            allow_admin_override=False,
            validate_tenant_exists=False,
            exclude_paths=["/health"],
        )
        app = make_app_with_state_setup(config=config)
        client = TestClient(app)

        import json

        claims = json.dumps({"org_id": "my-tenant"})
        response = client.get(
            "/api/data",
            headers={
                "X-Test-User-ID": "admin-user",
                "X-Test-Roles": "super_admin",
                "X-Test-Claims": claims,
                "X-Tenant-ID": "other-tenant",
            },
        )
        assert response.status_code == 403


# =============================================================================
# Tests: Path Exclusion
# =============================================================================


class TestPathExclusion:
    """Integration tests for path exclusion (NO MOCKING)."""

    def test_health_excluded(self):
        """Health endpoint excluded from tenant isolation."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert "X-Tenant-ID" not in response.headers

    def test_disabled_config(self):
        """Disabled config skips all tenant isolation."""
        config = TenantConfig(
            enabled=False,
            jwt_claim="org_id",
            validate_tenant_exists=False,
        )
        app = make_app_with_state_setup(config=config)
        client = TestClient(app)

        response = client.get("/api/data")
        assert response.status_code == 200
        assert response.json()["tenant_id"] is None


# =============================================================================
# Tests: Context Isolation
# =============================================================================


class TestContextIsolation:
    """Integration tests for context isolation between requests (NO MOCKING)."""

    def test_context_cleared_between_requests(self):
        """Tenant context cleared between requests."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        # First request with tenant
        claims = json.dumps({"org_id": "tenant-a"})
        r1 = client.get("/api/data", headers={"X-Test-Claims": claims})
        assert r1.json()["tenant_id"] == "tenant-a"

        # Second request without tenant
        r2 = client.get("/api/data")
        assert r2.json()["tenant_id"] is None

    def test_different_tenants_per_request(self):
        """Different requests can have different tenants."""
        app = make_app_with_state_setup()
        client = TestClient(app)

        import json

        claims_a = json.dumps({"org_id": "tenant-a"})
        claims_b = json.dumps({"org_id": "tenant-b"})

        r1 = client.get("/api/data", headers={"X-Test-Claims": claims_a})
        r2 = client.get("/api/data", headers={"X-Test-Claims": claims_b})

        assert r1.json()["tenant_id"] == "tenant-a"
        assert r2.json()["tenant_id"] == "tenant-b"
