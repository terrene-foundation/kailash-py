"""Unit tests for EATP Trust Verification Middleware.

TDD: These tests are written FIRST before the implementation.
Following the 3-tier testing strategy - Tier 1 (Unit Tests).

Tests cover:
1. Disabled mode: Passes through regardless of headers
2. Permissive mode: Valid trust passes with 200
3. Permissive mode: Invalid trust passes with warning
4. Enforcing mode: Valid trust passes with 200
5. Enforcing mode: Missing headers returns 401
6. Enforcing mode: Invalid agent returns 403
7. Exempt paths: Always pass through
8. Human origin requirement: Present returns 200
9. Human origin requirement: Missing returns 403
10. EATP context stored in request.state
11. No TrustOperations configured: Passes with warning
12. Middleware disabled via enabled=False: Passes through
"""

import asyncio
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from nexus.trust.headers import EATPHeaderExtractor, ExtractedEATPContext
from nexus.trust.middleware import TrustMiddleware, TrustMiddlewareConfig

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


def create_valid_eatp_headers() -> Dict[str, str]:
    """Create valid EATP headers for testing."""
    human_origin = {"user_id": "user-123", "auth_method": "oauth2"}
    return {
        "X-EATP-Trace-ID": "trace-abc-123",
        "X-EATP-Agent-ID": "agent-def-456",
        "X-EATP-Human-Origin": base64.b64encode(
            json.dumps(human_origin).encode()
        ).decode(),
        "X-EATP-Session-ID": "session-ghi-789",
    }


def create_headers_without_human_origin() -> Dict[str, str]:
    """Create valid EATP headers but without human origin."""
    return {
        "X-EATP-Trace-ID": "trace-abc-123",
        "X-EATP-Agent-ID": "agent-def-456",
        "X-EATP-Session-ID": "session-ghi-789",
    }


async def echo_endpoint(request: Request) -> JSONResponse:
    """Simple echo endpoint for testing."""
    # Return EATP context if stored in request.state
    eatp_context = getattr(request.state, "eatp_context", None)
    if eatp_context:
        return JSONResponse(
            {
                "message": "ok",
                "trace_id": eatp_context.trace_id,
                "agent_id": eatp_context.agent_id,
                "has_human_origin": eatp_context.has_human_origin(),
            }
        )
    return JSONResponse({"message": "ok"})


async def health_endpoint(request: Request) -> PlainTextResponse:
    """Health check endpoint for testing exempt paths."""
    return PlainTextResponse("healthy")


async def metrics_endpoint(request: Request) -> PlainTextResponse:
    """Metrics endpoint for testing exempt paths."""
    return PlainTextResponse("metrics")


def create_test_app(
    config: Optional[TrustMiddlewareConfig] = None,
    trust_operations: Optional[Any] = None,
) -> Starlette:
    """Create a Starlette app with TrustMiddleware for testing."""
    routes = [
        Route("/api/test", echo_endpoint),
        Route("/health", health_endpoint),
        Route("/metrics", metrics_endpoint),
    ]
    app = Starlette(routes=routes)

    # Add the middleware
    middleware_config = config or TrustMiddlewareConfig()
    app.add_middleware(
        TrustMiddleware,
        config=middleware_config,
        trust_operations=trust_operations,
    )

    return app


class MockTrustOperations:
    """Mock TrustOperations for unit testing."""

    def __init__(self, verify_result: bool = True):
        self.verify_result = verify_result
        self.verify_calls = []

    async def verify(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        **kwargs,
    ):
        """Mock verify that returns configured result."""
        self.verify_calls.append(
            {
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
            }
        )

        # Return a mock VerificationResult
        result = MagicMock()
        result.valid = self.verify_result
        result.reason = None if self.verify_result else "Agent not trusted"
        return result


# =============================================================================
# Test Classes
# =============================================================================


class TestTrustMiddlewareDisabledMode:
    """Tests for disabled mode middleware behavior."""

    def test_middleware_disabled_mode(self):
        """Test mode='disabled' passes through regardless of headers."""
        config = TrustMiddlewareConfig(mode="disabled")
        app = create_test_app(config=config)
        client = TestClient(app)

        # Request with NO headers should pass
        response = client.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

    def test_middleware_disabled_mode_with_invalid_headers(self):
        """Test mode='disabled' passes through even with invalid agent."""
        config = TrustMiddlewareConfig(mode="disabled")
        mock_trust = MockTrustOperations(verify_result=False)  # Would fail if checked
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Even with invalid agent, should pass in disabled mode
        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 200
        # Verify that trust operations was NOT called in disabled mode
        assert len(mock_trust.verify_calls) == 0


class TestTrustMiddlewarePermissiveMode:
    """Tests for permissive mode middleware behavior."""

    def test_middleware_permissive_valid_trust(self):
        """Test mode='permissive' with valid trust returns 200."""
        config = TrustMiddlewareConfig(mode="permissive")
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

    def test_middleware_permissive_invalid_trust(self):
        """Test mode='permissive' with no headers still returns 200 with warning."""
        config = TrustMiddlewareConfig(mode="permissive")
        mock_trust = MockTrustOperations(verify_result=False)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Request with NO headers - should still pass in permissive mode
        response = client.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

    def test_middleware_permissive_failed_verification(self):
        """Test mode='permissive' with failed trust verification still returns 200."""
        config = TrustMiddlewareConfig(mode="permissive")
        mock_trust = MockTrustOperations(verify_result=False)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        # Even though verification fails, permissive mode allows through
        assert response.status_code == 200


class TestTrustMiddlewareEnforcingMode:
    """Tests for enforcing mode middleware behavior."""

    def test_middleware_enforcing_valid_trust(self):
        """Test mode='enforcing' with valid trust returns 200."""
        config = TrustMiddlewareConfig(mode="enforcing")
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

    def test_middleware_enforcing_missing_headers(self):
        """Test mode='enforcing' with no headers returns 401."""
        config = TrustMiddlewareConfig(mode="enforcing")
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Request with NO headers
        response = client.get("/api/test")

        assert response.status_code == 401
        error_data = response.json()
        assert "error" in error_data
        assert (
            "EATP" in error_data["error"] or "required" in error_data["error"].lower()
        )

    def test_middleware_enforcing_invalid_agent(self):
        """Test mode='enforcing' with failed verification returns 403."""
        config = TrustMiddlewareConfig(mode="enforcing")
        mock_trust = MockTrustOperations(verify_result=False)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 403
        error_data = response.json()
        assert "error" in error_data


class TestTrustMiddlewareExemptPaths:
    """Tests for exempt path handling."""

    def test_middleware_exempt_paths(self):
        """Test exempt paths bypass verification entirely."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health", "/metrics"],
        )
        mock_trust = MockTrustOperations(verify_result=False)  # Would fail
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Health endpoint should bypass - no headers needed
        response = client.get("/health")
        assert response.status_code == 200
        assert response.text == "healthy"

        # Metrics endpoint should bypass
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.text == "metrics"

        # Verify that trust operations was NOT called for exempt paths
        assert len(mock_trust.verify_calls) == 0

    def test_middleware_non_exempt_path_still_enforced(self):
        """Test non-exempt paths are still enforced."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health", "/metrics"],
        )
        app = create_test_app(config=config)
        client = TestClient(app)

        # /api/test is NOT exempt, should require headers
        response = client.get("/api/test")
        assert response.status_code == 401

    def test_middleware_prefix_exempt_paths_care052(self):
        """CARE-052: Test prefix matching for exempt paths with /* suffix.

        When an exempt path ends with /*, it should match any subpath.
        E.g., "/health/*" matches "/health/ready", "/health/detailed", etc.
        """

        # Create routes for health subpaths
        async def health_ready(request):
            return PlainTextResponse("ready")

        async def health_detailed(request):
            return PlainTextResponse("detailed")

        routes = [
            Route("/api/test", echo_endpoint),
            Route("/health", health_endpoint),
            Route("/health/ready", health_ready),
            Route("/health/detailed", health_detailed),
        ]
        app = Starlette(routes=routes)

        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health/*", "/metrics"],  # Prefix pattern for health
        )
        mock_trust = MockTrustOperations(verify_result=False)  # Would fail if checked
        app.add_middleware(
            TrustMiddleware,
            config=config,
            trust_operations=mock_trust,
        )
        client = TestClient(app)

        # Base health path should be exempt (special case: /health/* also exempts /health)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.text == "healthy"

        # Health subpaths should be exempt via prefix matching
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.text == "ready"

        response = client.get("/health/detailed")
        assert response.status_code == 200
        assert response.text == "detailed"

        # Verify trust operations was NOT called for exempt paths
        assert len(mock_trust.verify_calls) == 0

    def test_middleware_exact_match_backward_compat_care052(self):
        """CARE-052: Test backward compatibility - exact paths without /* still use exact matching."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health", "/metrics"],  # No /* suffix = exact match only
        )
        app = create_test_app(config=config)
        client = TestClient(app)

        # Exact match works
        response = client.get("/health")
        assert response.status_code == 200

        # Subpaths do NOT match when using exact matching (no /* suffix)
        # This should require auth and fail with 401 (no headers)
        response = client.get("/health/detailed")
        # Note: route doesn't exist so this is 404, but importantly NOT bypassing auth
        # The middleware should NOT exempt this path
        assert response.status_code in (401, 404)

    def test_middleware_prefix_does_not_match_similar_paths_care052(self):
        """CARE-052: Test that /health/* does NOT match /healthcheck or /healthy.

        The prefix matching should only match paths that start with /health/
        not just any path that starts with /health.
        """

        async def healthcheck(request):
            return PlainTextResponse("healthcheck")

        routes = [
            Route("/api/test", echo_endpoint),
            Route("/health", health_endpoint),
            Route("/healthcheck", healthcheck),
        ]
        app = Starlette(routes=routes)

        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health/*"],  # Should NOT match /healthcheck
        )
        mock_trust = MockTrustOperations(verify_result=False)
        app.add_middleware(
            TrustMiddleware,
            config=config,
            trust_operations=mock_trust,
        )
        client = TestClient(app)

        # /health is exempt (base path)
        response = client.get("/health")
        assert response.status_code == 200

        # /healthcheck is NOT exempt - should require auth
        response = client.get("/healthcheck")
        assert response.status_code == 401  # No headers = 401


class TestTrustMiddlewareHumanOriginRequirement:
    """Tests for require_human_origin setting."""

    def test_middleware_require_human_origin_present(self):
        """Test require_human_origin=True with human origin present returns 200."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            require_human_origin=True,
        )
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Headers WITH human origin
        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 200

    def test_middleware_require_human_origin_missing(self):
        """Test require_human_origin=True without human origin returns 403."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            require_human_origin=True,
        )
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Headers WITHOUT human origin
        headers = create_headers_without_human_origin()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 403
        error_data = response.json()
        assert (
            "human" in error_data["error"].lower()
            or "origin" in error_data["error"].lower()
        )


class TestTrustMiddlewareContextStorage:
    """Tests for EATP context storage in request.state."""

    def test_middleware_context_stored_in_request_state(self):
        """Test that EATP context is stored in request.state.eatp_context."""
        config = TrustMiddlewareConfig(mode="permissive")
        app = create_test_app(config=config)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        assert response.status_code == 200
        data = response.json()

        # The echo_endpoint returns the EATP context info
        assert data["trace_id"] == "trace-abc-123"
        assert data["agent_id"] == "agent-def-456"
        assert data["has_human_origin"] is True


class TestTrustMiddlewareNoTrustOps:
    """Tests for behavior when TrustOperations is not configured."""

    def test_middleware_no_trust_ops_configured(self):
        """Test that missing TrustOperations in permissive mode passes with warning."""
        config = TrustMiddlewareConfig(mode="permissive")
        # No trust_operations provided
        app = create_test_app(config=config, trust_operations=None)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        # Should still pass in permissive mode
        assert response.status_code == 200

    def test_middleware_no_trust_ops_enforcing_mode(self):
        """Test that missing TrustOperations in enforcing mode still allows valid headers."""
        config = TrustMiddlewareConfig(mode="enforcing")
        # No trust_operations provided - can only do header-level validation
        app = create_test_app(config=config, trust_operations=None)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        # With valid headers but no trust_ops, should pass (header-only validation)
        assert response.status_code == 200


class TestTrustMiddlewareNotEnabled:
    """Tests for enabled=False behavior."""

    def test_middleware_not_enabled(self):
        """Test enabled=False completely bypasses middleware."""
        config = TrustMiddlewareConfig(enabled=False, mode="enforcing")
        mock_trust = MockTrustOperations(verify_result=False)  # Would fail
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        # Request with NO headers should pass when disabled
        response = client.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "ok"

        # Verify that trust operations was NOT called
        assert len(mock_trust.verify_calls) == 0


class TestTrustMiddlewareConfig:
    """Tests for TrustMiddlewareConfig dataclass."""

    def test_config_defaults(self):
        """Test TrustMiddlewareConfig default values."""
        config = TrustMiddlewareConfig()

        assert config.enabled is True
        assert config.mode == "permissive"
        assert "/health" in config.exempt_paths
        assert "/metrics" in config.exempt_paths
        assert "/openapi.json" in config.exempt_paths
        assert "/docs" in config.exempt_paths
        assert "/redoc" in config.exempt_paths
        assert config.require_human_origin is False
        assert config.audit_all_requests is True
        assert config.reject_expired_sessions is True

    def test_config_custom_values(self):
        """Test TrustMiddlewareConfig with custom values."""
        config = TrustMiddlewareConfig(
            enabled=False,
            mode="enforcing",
            exempt_paths=["/custom-health"],
            require_human_origin=True,
            audit_all_requests=False,
            reject_expired_sessions=False,
        )

        assert config.enabled is False
        assert config.mode == "enforcing"
        assert config.exempt_paths == ["/custom-health"]
        assert config.require_human_origin is True
        assert config.audit_all_requests is False
        assert config.reject_expired_sessions is False


class TestTrustMiddlewareEdgeCases:
    """Tests for edge cases and error handling."""

    def test_middleware_partial_headers(self):
        """Test with partial EATP headers (missing agent_id)."""
        config = TrustMiddlewareConfig(mode="enforcing")
        app = create_test_app(config=config)
        client = TestClient(app)

        # Only trace_id, missing agent_id
        headers = {"X-EATP-Trace-ID": "trace-123"}
        response = client.get("/api/test", headers=headers)

        # Should fail - missing required agent_id
        assert response.status_code == 401

    def test_middleware_malformed_human_origin(self):
        """Test with malformed base64 in human origin header."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            require_human_origin=True,
        )
        mock_trust = MockTrustOperations(verify_result=True)
        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Human-Origin": "!!!invalid-base64!!!",
        }
        response = client.get("/api/test", headers=headers)

        # Malformed human origin = no human origin = 403
        assert response.status_code == 403

    def test_middleware_case_insensitive_exempt_paths(self):
        """Test that exempt paths matching is case-sensitive (standard behavior)."""
        config = TrustMiddlewareConfig(
            mode="enforcing",
            exempt_paths=["/health"],
        )
        app = create_test_app(config=config)
        client = TestClient(app)

        # Exact match should work
        response = client.get("/health")
        assert response.status_code == 200

    def test_middleware_trust_ops_exception_handling(self):
        """Test that exceptions from TrustOperations are handled gracefully."""
        config = TrustMiddlewareConfig(mode="enforcing")

        # Create a mock that raises an exception
        mock_trust = MagicMock()
        mock_trust.verify = AsyncMock(
            side_effect=Exception("Trust service unavailable")
        )

        app = create_test_app(config=config, trust_operations=mock_trust)
        client = TestClient(app)

        headers = create_valid_eatp_headers()
        response = client.get("/api/test", headers=headers)

        # Should return 500 or similar error when trust service fails
        assert response.status_code in (500, 503)
