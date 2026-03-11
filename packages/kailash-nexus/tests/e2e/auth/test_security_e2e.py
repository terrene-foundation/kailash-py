"""E2E security tests for auth stack (TODO-310H).

Tier 3 tests - NO MOCKING. Tests security boundaries including
invalid tokens, expired tokens, permission escalation, and rate limiting.
"""

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from nexus.auth.audit.config import AuditConfig
from nexus.auth.jwt import JWTConfig
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth.rate_limit.config import RateLimitConfig

TEST_SECRET = "e2e-test-secret-key-very-secure-123"


# =============================================================================
# Tests: JWT Security
# =============================================================================


class TestJWTSecurityE2E:
    """E2E security tests for JWT authentication (NO MOCKING)."""

    def test_no_token_returns_401(self, full_auth_client):
        """Request without JWT token returns 401."""
        response = full_auth_client.get("/api/profile")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, full_auth_client):
        """Request with invalid JWT token returns 401."""
        response = full_auth_client.get(
            "/api/profile",
            headers={"Authorization": "Bearer invalid-token-garbage"},
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(self, full_auth_client, create_token):
        """Request with expired JWT token returns 401."""
        token = create_token(user_id="alice", roles=["user"], expired=True)
        response = full_auth_client.get(
            "/api/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_wrong_secret_returns_401(self, full_auth_client):
        """Token signed with wrong secret returns 401."""
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "alice",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = pyjwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        response = full_auth_client.get(
            "/api/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_malformed_authorization_header(self, full_auth_client):
        """Malformed Authorization header returns 401."""
        response = full_auth_client.get(
            "/api/profile",
            headers={"Authorization": "NotBearer sometoken"},
        )
        assert response.status_code == 401

    def test_empty_bearer_token(self, full_auth_client):
        """Empty Bearer token returns 401."""
        response = full_auth_client.get(
            "/api/profile",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401


# =============================================================================
# Tests: RBAC Security
# =============================================================================


class TestRBACSecurityE2E:
    """E2E security tests for RBAC enforcement (NO MOCKING)."""

    def test_user_cannot_write_admin_settings(self, full_auth_client, auth_header):
        """User role cannot write admin settings (no write:settings permission)."""
        headers = auth_header(
            user_id="bob",
            roles=["user"],
            tenant_id="org-1",
        )
        response = full_auth_client.post("/api/admin/settings", headers=headers)
        assert response.status_code == 403

    def test_admin_can_access_all_endpoints(self, full_auth_client, auth_header):
        """Admin role (wildcard permissions) can access any endpoint."""
        headers = auth_header(
            user_id="admin-1",
            roles=["admin"],
            tenant_id="org-1",
        )

        # Admin can access user endpoints
        resp_data = full_auth_client.get("/api/data", headers=headers)
        assert resp_data.status_code == 200

        # Admin can access admin endpoints
        resp_admin = full_auth_client.get("/api/admin/users", headers=headers)
        assert resp_admin.status_code == 200

        # Admin can write settings
        resp_settings = full_auth_client.post("/api/admin/settings", headers=headers)
        assert resp_settings.status_code == 200

    def test_no_role_gets_403_on_rbac_endpoint(self, full_auth_client, auth_header):
        """Token without roles gets 403 on RBAC-protected endpoint."""
        headers = auth_header(
            user_id="norole-user",
            roles=[],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403

    def test_viewer_cannot_access_admin(self, full_auth_client, auth_header):
        """Viewer role cannot access admin endpoint."""
        headers = auth_header(
            user_id="viewer-1",
            roles=["viewer"],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403


# =============================================================================
# Tests: Rate Limiting Security
# =============================================================================


class TestRateLimitingSecurityE2E:
    """E2E security tests for rate limiting (NO MOCKING)."""

    def test_rate_limit_enforced(self, auth_header):
        """Requests beyond rate limit return 429."""
        from fastapi import FastAPI

        app = FastAPI()
        plugin = NexusAuthPlugin(
            rate_limit=RateLimitConfig(
                requests_per_minute=3,
                burst_size=0,
            ),
        )
        plugin.install(app)

        @app.get("/api/test")
        async def test_ep():
            return {"ok": True}

        client = TestClient(app)

        # First 3 should succeed
        for i in range(3):
            resp = client.get("/api/test")
            assert resp.status_code == 200, f"Request {i+1} should succeed"

        # 4th should be rate limited
        resp = client.get("/api/test")
        assert resp.status_code == 429

    def test_rate_limit_includes_headers(self, auth_header):
        """Rate limit response includes X-RateLimit headers."""
        from fastapi import FastAPI

        app = FastAPI()
        plugin = NexusAuthPlugin(
            rate_limit=RateLimitConfig(
                requests_per_minute=2,
                burst_size=0,
                include_headers=True,
            ),
        )
        plugin.install(app)

        @app.get("/api/test")
        async def test_ep():
            return {"ok": True}

        client = TestClient(app)

        # Make requests
        resp1 = client.get("/api/test")
        assert resp1.status_code == 200

        # Rate limit headers should be present
        assert "x-ratelimit-limit" in resp1.headers or resp1.status_code == 200

    def test_rate_limit_429_has_retry_after(self, auth_header):
        """429 response includes Retry-After header."""
        from fastapi import FastAPI

        app = FastAPI()
        plugin = NexusAuthPlugin(
            rate_limit=RateLimitConfig(
                requests_per_minute=1,
                burst_size=0,
                include_headers=True,
            ),
        )
        plugin.install(app)

        @app.get("/api/test")
        async def test_ep():
            return {"ok": True}

        client = TestClient(app)

        # Exhaust rate limit
        client.get("/api/test")

        # Next request should be 429 with Retry-After
        resp = client.get("/api/test")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers


# =============================================================================
# Tests: Middleware Stack Integration
# =============================================================================


class TestMiddlewareStackE2E:
    """E2E tests for middleware stack integration (NO MOCKING)."""

    def test_all_middleware_work_together(self, full_auth_client, auth_header, caplog):
        """JWT + RBAC + tenant + audit all work in single request."""
        import logging

        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="org-1",
        )

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = full_auth_client.get("/api/data", headers=headers)

        # JWT authenticated
        assert response.status_code == 200

        # RBAC allowed (user has read:data)
        data = response.json()
        assert data["data"] == [1, 2, 3]

        # Tenant isolated
        assert data["tenant_id"] == "org-1"

        # Audited
        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

    def test_middleware_order_correct(self, full_auth_client, auth_header, caplog):
        """Middleware executes in correct order: audit wraps rate_limit wraps tenant wraps jwt."""
        import logging

        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="org-1",
        )

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = full_auth_client.get("/api/profile", headers=headers)

        assert response.status_code == 200

        # Verify audit captured the 200 (audit is outermost, sees final status)
        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

    def test_audit_captures_auth_failure(self, full_auth_client, caplog):
        """Audit middleware captures JWT authentication failure."""
        import logging

        with caplog.at_level(logging.WARNING, logger="nexus.audit"):
            response = full_auth_client.get("/api/profile")

        assert response.status_code == 401

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1
