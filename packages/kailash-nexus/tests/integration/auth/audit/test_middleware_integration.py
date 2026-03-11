"""Integration tests for AuditMiddleware (TODO-310F).

Tier 2 tests - NO MOCKING. Uses real FastAPI TestClient with real
middleware for audit logging testing.
"""

import json
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nexus.auth.audit.config import AuditConfig
from nexus.auth.audit.middleware import AuditMiddleware
from nexus.auth.audit.record import AuditRecord

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_app():
    """Create a FastAPI app with audit middleware."""
    app = FastAPI()

    config = AuditConfig(
        backend="logging",
        exclude_paths=["/health"],
        include_query_params=True,
    )
    app.add_middleware(AuditMiddleware, config=config)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/data")
    async def get_data():
        return {"items": [1, 2, 3]}

    @app.post("/api/users")
    async def create_user():
        return JSONResponse(
            status_code=201,
            content={"id": "user-1", "name": "Alice"},
        )

    @app.get("/api/error")
    async def error_endpoint():
        return JSONResponse(
            status_code=500,
            content={"error": "Something went wrong"},
        )

    @app.get("/api/not-found")
    async def not_found():
        return JSONResponse(
            status_code=404,
            content={"error": "Not found"},
        )

    return app


@pytest.fixture
def client(audit_app):
    """Create TestClient."""
    return TestClient(audit_app)


# =============================================================================
# Tests: Basic Audit Logging
# =============================================================================


class TestBasicAuditLogging:
    """Integration tests for basic audit logging (NO MOCKING)."""

    def test_get_request_logged(self, client, caplog):
        """GET request is logged."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.get("/api/data")

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1

        log_data = json.loads(audit_logs[0].message)
        assert log_data["method"] == "GET"
        assert log_data["path"] == "/api/data"
        assert log_data["status_code"] == 200

    def test_post_request_logged(self, client, caplog):
        """POST request is logged."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.post("/api/users")

        assert response.status_code == 201

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1

        log_data = json.loads(audit_logs[0].message)
        assert log_data["method"] == "POST"
        assert log_data["status_code"] == 201

    def test_duration_recorded(self, client, caplog):
        """Duration is recorded in milliseconds."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        log_data = json.loads(audit_logs[0].message)
        assert "duration_ms" in log_data
        assert log_data["duration_ms"] >= 0

    def test_request_id_generated(self, client, caplog):
        """Request ID is auto-generated UUID."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        log_data = json.loads(audit_logs[0].message)
        assert "request_id" in log_data
        assert len(log_data["request_id"]) > 0

    def test_timestamp_recorded(self, client, caplog):
        """Timestamp is recorded."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        log_data = json.loads(audit_logs[0].message)
        assert "timestamp" in log_data


# =============================================================================
# Tests: Path Exclusion
# =============================================================================


class TestAuditPathExclusion:
    """Integration tests for path exclusion (NO MOCKING)."""

    def test_health_not_logged(self, client, caplog):
        """Health endpoint is not logged."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.get("/health")

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 0

    def test_api_endpoint_logged(self, client, caplog):
        """Non-excluded API endpoint is logged."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1


# =============================================================================
# Tests: Error Response Logging
# =============================================================================


class TestAuditErrorLogging:
    """Integration tests for error response logging (NO MOCKING)."""

    def test_5xx_logged_at_error(self, client, caplog):
        """5xx responses logged at ERROR level."""
        with caplog.at_level(logging.ERROR, logger="nexus.audit"):
            response = client.get("/api/error")

        assert response.status_code == 500

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1
        assert audit_logs[0].levelno == logging.ERROR

        log_data = json.loads(audit_logs[0].message)
        assert log_data["error"] == "HTTP 500"

    def test_4xx_logged_at_warning(self, client, caplog):
        """4xx responses logged at WARNING level."""
        with caplog.at_level(logging.WARNING, logger="nexus.audit"):
            response = client.get("/api/not-found")

        assert response.status_code == 404

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1
        assert audit_logs[0].levelno == logging.WARNING


# =============================================================================
# Tests: Query Parameter Redaction
# =============================================================================


class TestAuditQueryParamRedaction:
    """Integration tests for PII redaction in query params (NO MOCKING)."""

    def test_password_param_redacted(self, client, caplog):
        """Password query param is redacted."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data?password=secret123&name=alice")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        log_data = json.loads(audit_logs[0].message)

        # Check query params in metadata
        query_params = log_data.get("metadata", {}).get("query_params", {})
        assert query_params.get("password") == "[REDACTED]"
        assert query_params.get("name") == "alice"

    def test_token_param_redacted(self, client, caplog):
        """Token query param is redacted."""
        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            client.get("/api/data?token=secret-token&page=1")

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        log_data = json.loads(audit_logs[0].message)

        query_params = log_data.get("metadata", {}).get("query_params", {})
        assert query_params.get("token") == "[REDACTED]"
        assert query_params.get("page") == "1"


# =============================================================================
# Tests: Custom Backend
# =============================================================================


class TestAuditCustomBackend:
    """Integration tests for custom backend (NO MOCKING)."""

    def test_custom_callable_backend(self):
        """Custom callable backend receives records."""
        stored_records = []

        async def my_store(record):
            stored_records.append(record)

        app = FastAPI()
        config = AuditConfig(backend=my_store)
        app.add_middleware(AuditMiddleware, config=config)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/api/test")
        assert response.status_code == 200

        assert len(stored_records) == 1
        assert stored_records[0].method == "GET"
        assert stored_records[0].path == "/api/test"
        assert stored_records[0].status_code == 200

    def test_sync_callable_backend(self):
        """Sync callable backend receives records."""
        stored_records = []

        def my_store(record):
            stored_records.append(record)

        app = FastAPI()
        config = AuditConfig(backend=my_store)
        app.add_middleware(AuditMiddleware, config=config)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        client.get("/api/test")

        assert len(stored_records) == 1


# =============================================================================
# Tests: Disabled Audit
# =============================================================================


class TestAuditDisabled:
    """Integration tests for disabled audit (NO MOCKING)."""

    def test_disabled_audit_no_logging(self, caplog):
        """Disabled audit does not log."""
        app = FastAPI()
        config = AuditConfig(enabled=False)
        app.add_middleware(AuditMiddleware, config=config)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.get("/api/test")

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 0


# =============================================================================
# Tests: Failure Isolation
# =============================================================================


class TestAuditFailureIsolation:
    """Integration tests for failure isolation (NO MOCKING)."""

    def test_backend_failure_doesnt_break_request(self):
        """Backend failure does not affect request response."""

        async def failing_store(record):
            raise RuntimeError("Storage failed!")

        app = FastAPI()
        config = AuditConfig(backend=failing_store)
        app.add_middleware(AuditMiddleware, config=config)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/api/test")

        # Request should succeed despite backend failure
        assert response.status_code == 200
        assert response.json() == {"ok": True}
