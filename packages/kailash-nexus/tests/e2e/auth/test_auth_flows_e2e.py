"""E2E tests for complete auth flows (TODO-310H).

Tier 3 tests - NO MOCKING. Real FastAPI app with full auth stack.
Tests complete authentication and authorization flows end-to-end.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

# =============================================================================
# Tests: Complete Auth Flows
# =============================================================================


class TestCompleteAuthFlowE2E:
    """E2E tests for complete authentication flows (NO MOCKING)."""

    def test_jwt_to_profile(self, full_auth_client, auth_header):
        """JWT token grants access to profile endpoint."""
        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/profile", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["tenant_id"] == "org-1"

    def test_jwt_plus_rbac_user_access(self, full_auth_client, auth_header):
        """User role can access data endpoint via RBAC permission check."""
        headers = auth_header(
            user_id="bob",
            roles=["user"],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/data", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "bob"
        assert data["tenant_id"] == "org-1"
        assert data["data"] == [1, 2, 3]

    def test_jwt_plus_rbac_admin_access(self, full_auth_client, auth_header):
        """Admin role can access admin endpoint."""
        headers = auth_header(
            user_id="admin-1",
            roles=["admin"],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/admin/users", headers=headers)

        assert response.status_code == 200
        assert response.json()["admin_id"] == "admin-1"

    def test_user_cannot_access_admin_endpoint(self, full_auth_client, auth_header):
        """User role cannot access admin-only endpoint."""
        headers = auth_header(
            user_id="bob",
            roles=["user"],
            tenant_id="org-1",
        )
        response = full_auth_client.get("/api/admin/users", headers=headers)

        assert response.status_code == 403

    def test_viewer_can_read_data(self, full_auth_client, auth_header):
        """Viewer role can read data (has read:data permission)."""
        headers = auth_header(
            user_id="viewer-1",
            roles=["viewer"],
            tenant_id="org-2",
        )
        response = full_auth_client.get("/api/data", headers=headers)

        assert response.status_code == 200
        assert response.json()["tenant_id"] == "org-2"

    def test_viewer_cannot_access_admin(self, full_auth_client, auth_header):
        """Viewer role cannot access admin endpoint."""
        headers = auth_header(
            user_id="viewer-1",
            roles=["viewer"],
            tenant_id="org-2",
        )
        response = full_auth_client.get("/api/admin/users", headers=headers)

        assert response.status_code == 403

    def test_public_endpoint_no_auth_required(self, full_auth_client):
        """Public endpoint accessible without JWT."""
        response = full_auth_client.get("/api/public")

        assert response.status_code == 200
        assert response.json()["message"] == "public data"

    def test_health_endpoint_no_auth_required(self, full_auth_client):
        """Health endpoint accessible without JWT."""
        response = full_auth_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# =============================================================================
# Tests: Audit Logging E2E
# =============================================================================


class TestAuditLoggingE2E:
    """E2E tests for audit logging in full auth stack (NO MOCKING)."""

    def test_successful_request_audited(self, full_auth_client, auth_header, caplog):
        """Successful authenticated request generates audit log."""
        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="org-1",
        )

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = full_auth_client.get("/api/profile", headers=headers)

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

        log_data = json.loads(audit_logs[0].message)
        assert log_data["method"] == "GET"
        assert log_data["path"] == "/api/profile"
        assert log_data["status_code"] == 200

    def test_rejected_request_audited(self, full_auth_client, caplog):
        """Unauthenticated request (401) is audited."""
        with caplog.at_level(logging.WARNING, logger="nexus.audit"):
            response = full_auth_client.get("/api/profile")

        assert response.status_code == 401

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

        log_data = json.loads(audit_logs[0].message)
        assert log_data["status_code"] == 401

    def test_forbidden_request_audited(self, full_auth_client, auth_header, caplog):
        """Forbidden request (403) is audited."""
        headers = auth_header(
            user_id="bob",
            roles=["user"],
            tenant_id="org-1",
        )

        with caplog.at_level(logging.WARNING, logger="nexus.audit"):
            response = full_auth_client.get("/api/admin/users", headers=headers)

        assert response.status_code == 403

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

        log_data = json.loads(audit_logs[0].message)
        assert log_data["status_code"] == 403

    def test_health_not_audited(self, full_auth_client, caplog):
        """Health endpoint excluded from audit logging."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = full_auth_client.get("/health")

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 0

    def test_error_response_audited_at_error_level(
        self, full_auth_client, auth_header, caplog
    ):
        """5xx response audited at ERROR level."""
        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="org-1",
        )

        with caplog.at_level(logging.ERROR, logger="nexus.audit"):
            response = full_auth_client.get("/api/error", headers=headers)

        assert response.status_code == 500

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1
        assert audit_logs[0].levelno == logging.ERROR


# =============================================================================
# Tests: Tenant Isolation E2E
# =============================================================================


class TestTenantIsolationE2E:
    """E2E tests for tenant isolation in full auth stack (NO MOCKING)."""

    def test_tenant_context_set_from_jwt(self, full_auth_client, auth_header):
        """Tenant ID extracted from JWT claim and available in endpoint."""
        headers = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="tenant-abc",
        )
        response = full_auth_client.get("/api/profile", headers=headers)

        assert response.status_code == 200
        assert response.json()["tenant_id"] == "tenant-abc"

    def test_different_tenants_isolated(self, full_auth_client, auth_header):
        """Different users in different tenants get their own context."""
        headers_a = auth_header(
            user_id="alice",
            roles=["user"],
            tenant_id="tenant-a",
        )
        headers_b = auth_header(
            user_id="bob",
            roles=["user"],
            tenant_id="tenant-b",
        )

        resp_a = full_auth_client.get("/api/data", headers=headers_a)
        resp_b = full_auth_client.get("/api/data", headers=headers_b)

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["tenant_id"] == "tenant-a"
        assert resp_b.json()["tenant_id"] == "tenant-b"

    def test_tenant_propagates_through_request(self, full_auth_client, auth_header):
        """Tenant ID propagates from JWT through middleware to endpoint."""
        headers = auth_header(
            user_id="charlie",
            roles=["user"],
            tenant_id="org-xyz",
        )
        response = full_auth_client.get("/api/data", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "charlie"
        assert data["tenant_id"] == "org-xyz"
