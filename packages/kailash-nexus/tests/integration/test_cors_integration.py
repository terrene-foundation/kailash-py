"""Integration tests for Nexus native CORS configuration (TODO-300E).

Tests CORS behavior with real HTTP requests using Starlette TestClient.
Tier 2 tests - NO MOCKING. Uses real gateway and middleware stack.
"""

import os

import pytest
from nexus import Nexus
from starlette.testclient import TestClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_nexus_env(monkeypatch):
    """Ensure NEXUS_ENV is reset between tests."""
    monkeypatch.delenv("NEXUS_ENV", raising=False)


def _make_client(app: Nexus) -> TestClient:
    """Create a TestClient from a Nexus instance."""
    return TestClient(app._gateway.app)


# =============================================================================
# Tests: CORS Preflight Requests
# =============================================================================


class TestCorsPreflight:
    """Tests for CORS preflight (OPTIONS) requests."""

    def test_preflight_returns_allow_origin(self):
        """Preflight response includes Access-Control-Allow-Origin."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_preflight_returns_allow_methods(self):
        """Preflight response includes allowed methods."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_methods=["GET", "POST"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 200
        allow_methods = response.headers["access-control-allow-methods"]
        assert "POST" in allow_methods

    def test_preflight_returns_allow_headers(self):
        """Preflight response includes allowed headers."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_headers=["Authorization", "Content-Type"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

        assert response.status_code == 200
        allow_headers = response.headers["access-control-allow-headers"]
        assert "Authorization" in allow_headers

    def test_preflight_returns_max_age(self):
        """Preflight response includes max-age."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_max_age=1800,
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-max-age"] == "1800"

    def test_preflight_returns_credentials(self):
        """Preflight includes credentials header when configured."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_credentials=True,
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.headers["access-control-allow-credentials"] == "true"


# =============================================================================
# Tests: CORS Actual Requests
# =============================================================================


class TestCorsActualRequest:
    """Tests for CORS headers on actual (non-preflight) requests."""

    def test_actual_request_has_allow_origin(self):
        """Actual request includes CORS origin header."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_actual_request_has_expose_headers(self):
        """Actual request includes expose-headers when configured."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_expose_headers=["X-Request-ID", "X-Total-Count"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        expose = response.headers.get("access-control-expose-headers", "")
        assert "X-Request-ID" in expose
        assert "X-Total-Count" in expose

    def test_actual_request_has_credentials(self):
        """Actual request includes credentials header."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_credentials=True,
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.headers["access-control-allow-credentials"] == "true"


# =============================================================================
# Tests: Origin Blocking
# =============================================================================


class TestCorsOriginBlocking:
    """Tests for blocked origins."""

    def test_non_allowed_origin_no_cors_headers(self):
        """Requests from non-allowed origins get no CORS headers."""
        app = Nexus(
            cors_origins=["http://allowed.com"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://evil.com"},
        )

        # Request still succeeds (CORS is browser-enforced)
        assert response.status_code == 200
        # But no CORS headers present
        assert "access-control-allow-origin" not in response.headers

    def test_wildcard_allows_any_origin(self):
        """Wildcard origin responds with * for any origin."""
        app = Nexus(
            cors_origins=["*"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://any-origin.example.com"},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"


# =============================================================================
# Tests: Production Environment
# =============================================================================


class TestCorsProductionIntegration:
    """Tests for production environment CORS behavior."""

    def test_production_no_cors_by_default(self, monkeypatch):
        """Production without explicit origins has no CORS middleware."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://example.com"},
        )

        # Request succeeds but no CORS headers (no middleware applied)
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_production_with_explicit_origins(self, monkeypatch):
        """Production with explicit origins works correctly."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(
            cors_origins=["https://app.example.com"],
            enable_auth=False,
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "https://app.example.com"},
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "https://app.example.com"
        )


# =============================================================================
# Tests: configure_cors() with Gateway
# =============================================================================


class TestConfigureCorsWithGateway:
    """Tests for configure_cors() applying to live gateway."""

    def test_configure_cors_adds_middleware(self):
        """configure_cors() adds CORS middleware to running gateway."""
        app = Nexus(
            cors_origins=["http://initial.com"],
            enable_durability=False,
        )
        client = _make_client(app)

        # Reconfigure with new origin
        app.configure_cors(allow_origins=["http://updated.com"])

        # The new middleware is added (Starlette stacks them)
        response = client.get(
            "/health",
            headers={"Origin": "http://updated.com"},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://updated.com"
