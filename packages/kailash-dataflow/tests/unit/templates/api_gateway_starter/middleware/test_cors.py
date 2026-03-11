"""
Unit tests for CORS configuration middleware.
Tests origin validation, header generation, and FastAPI integration.
"""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from templates.api_gateway_starter.middleware.cors import (
    configure_cors,
    get_cors_headers,
    is_origin_allowed,
)


class TestCORSConfiguration:
    """Test CORS middleware configuration and validation."""

    def test_configure_cors_wildcard(self):
        """Test CORS configuration with wildcard origin."""
        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        configure_cors(app, allowed_origins=["*"])

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://example.com"})

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_configure_cors_specific_origins(self):
        """Test CORS configuration with specific allowed origins."""
        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        allowed = ["https://app.example.com", "https://admin.example.com"]
        configure_cors(app, allowed_origins=allowed)

        client = TestClient(app)

        # Allowed origin
        response = client.get("/test", headers={"Origin": "https://app.example.com"})
        assert response.status_code == 200

        # Disallowed origin (should still return 200 but without CORS headers)
        response = client.get("/test", headers={"Origin": "https://evil.com"})
        assert response.status_code == 200

    def test_configure_cors_credentials(self):
        """Test CORS configuration allows credentials."""
        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        configure_cors(app, allowed_origins=["https://app.example.com"])

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://app.example.com"})

        # Should allow credentials
        assert "access-control-allow-credentials" in response.headers

    def test_configure_cors_methods(self):
        """Test CORS configuration allows all HTTP methods."""
        app = FastAPI()

        @app.options("/test")
        def test_options():
            return {"status": "ok"}

        configure_cors(app, allowed_origins=["*"])

        client = TestClient(app)
        response = client.options(
            "/test",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        # Should allow method
        assert "access-control-allow-methods" in response.headers

    def test_get_cors_headers_allowed_origin(self):
        """Test CORS headers for allowed origin."""
        origin = "https://app.example.com"
        allowed_origins = ["https://app.example.com", "https://admin.example.com"]

        headers = get_cors_headers(origin, allowed_origins)

        assert "Access-Control-Allow-Origin" in headers
        assert headers["Access-Control-Allow-Origin"] == origin
        assert "Access-Control-Allow-Credentials" in headers
        assert headers["Access-Control-Allow-Credentials"] == "true"

    def test_get_cors_headers_disallowed_origin(self):
        """Test CORS headers for disallowed origin."""
        origin = "https://evil.com"
        allowed_origins = ["https://app.example.com"]

        headers = get_cors_headers(origin, allowed_origins)

        # Should return empty dict or no CORS headers
        assert headers == {} or "Access-Control-Allow-Origin" not in headers

    def test_is_origin_allowed_exact_match(self):
        """Test origin validation with exact match."""
        origin = "https://app.example.com"
        allowed_origins = ["https://app.example.com", "https://admin.example.com"]

        assert is_origin_allowed(origin, allowed_origins) is True

    def test_is_origin_allowed_wildcard(self):
        """Test origin validation with wildcard."""
        origin = "https://anything.com"
        allowed_origins = ["*"]

        assert is_origin_allowed(origin, allowed_origins) is True

    def test_is_origin_allowed_subdomain(self):
        """Test origin validation does NOT allow subdomains by default."""
        origin = "https://subdomain.example.com"
        allowed_origins = ["https://example.com"]

        # Subdomains should NOT be allowed unless explicitly listed
        assert is_origin_allowed(origin, allowed_origins) is False

    def test_is_origin_allowed_not_in_list(self):
        """Test origin validation rejects unlisted origins."""
        origin = "https://evil.com"
        allowed_origins = ["https://app.example.com", "https://admin.example.com"]

        assert is_origin_allowed(origin, allowed_origins) is False
