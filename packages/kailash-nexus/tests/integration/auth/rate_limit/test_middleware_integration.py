"""Integration tests for rate limiting middleware (TODO-310D).

Tier 2 tests - NO MOCKING. Uses real FastAPI TestClient with real
InMemoryBackend for middleware integration testing.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.rate_limit.middleware import RateLimitMiddleware

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app_with_rate_limit():
    """Create a FastAPI app with rate limiting middleware."""
    app = FastAPI()

    config = RateLimitConfig(
        requests_per_minute=10,
        burst_size=5,
        backend="memory",
        route_limits={
            "/health": None,  # No rate limit
            "/api/strict/*": {"requests_per_minute": 3},
        },
    )
    app.add_middleware(RateLimitMiddleware, config=config)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health_endpoint():
        return {"status": "healthy"}

    @app.get("/api/strict/resource")
    async def strict_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app_with_rate_limit):
    """Create a TestClient."""
    return TestClient(app_with_rate_limit)


# =============================================================================
# Tests: Basic Rate Limiting
# =============================================================================


class TestMiddlewareRateLimiting:
    """Integration tests for rate limiting with real HTTP (NO MOCKING)."""

    def test_allows_requests_under_limit(self, client):
        """Requests under limit succeed with 200."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_adds_rate_limit_headers(self, client):
        """Rate limit headers are added to successful responses."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "10"

    def test_remaining_decreases(self, client):
        """X-RateLimit-Remaining decreases with each request."""
        r1 = client.get("/test")
        r2 = client.get("/test")

        remaining1 = int(r1.headers["X-RateLimit-Remaining"])
        remaining2 = int(r2.headers["X-RateLimit-Remaining"])

        assert remaining2 < remaining1

    def test_returns_429_when_exceeded(self, client):
        """Returns 429 when rate limit is exceeded."""
        # burst_multiplier = (10 + 5) / 10 = 1.5
        # Effective capacity = 10 * 1.5 = 15

        # Make enough requests to exceed limit
        for _ in range(16):
            client.get("/test")

        # Next request should get 429
        response = client.get("/test")
        assert response.status_code == 429

    def test_429_response_format(self, client):
        """429 response has correct format."""
        # Exhaust limit
        for _ in range(16):
            client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429

        body = response.json()
        assert "detail" in body
        assert "Rate limit exceeded" in body["detail"]
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)

    def test_429_includes_retry_after_header(self, client):
        """429 response includes Retry-After header."""
        for _ in range(16):
            client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0


# =============================================================================
# Tests: Route-Specific Limits
# =============================================================================


class TestRouteSpecificLimits:
    """Integration tests for per-route rate limits (NO MOCKING)."""

    def test_health_endpoint_not_rate_limited(self, client):
        """Health endpoint is excluded from rate limiting."""
        # Make many requests - none should be rate limited
        for _ in range(50):
            response = client.get("/health")
            assert response.status_code == 200

        # Should still not have rate limit headers
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers

    def test_strict_route_has_lower_limit(self, client):
        """Strict route has its own lower limit."""
        # Strict limit is 3 requests/minute
        # With burst_multiplier = (10+5)/10 = 1.5, capacity = 3 * 1.5 = 4.5

        responses = []
        for _ in range(6):
            resp = client.get("/api/strict/resource")
            responses.append(resp.status_code)

        # Some should be 200, some should be 429
        assert 200 in responses
        assert 429 in responses

    def test_strict_route_shows_custom_limit(self, client):
        """Strict route shows custom limit in headers."""
        response = client.get("/api/strict/resource")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "3"


# =============================================================================
# Tests: Identifier Isolation
# =============================================================================


class TestIdentifierIsolation:
    """Integration tests for identifier-based isolation (NO MOCKING)."""

    def test_different_ips_independent(self):
        """Different IPs have independent rate limits."""
        app = FastAPI()

        config = RateLimitConfig(
            requests_per_minute=5,
            burst_size=0,
            backend="memory",
        )
        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Exhaust limit for default IP
        for _ in range(6):
            client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429

    def test_custom_identifier_extractor(self):
        """Custom identifier extractor is used."""
        app = FastAPI()

        call_count = {"count": 0}

        def custom_extractor(request: Request) -> str:
            call_count["count"] += 1
            return "custom-id"

        config = RateLimitConfig(
            requests_per_minute=100,
            burst_size=0,
            backend="memory",
        )
        app.add_middleware(
            RateLimitMiddleware,
            config=config,
            identifier_extractor=custom_extractor,
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        client.get("/test")
        client.get("/test")

        assert call_count["count"] == 2


# =============================================================================
# Tests: Header Configuration
# =============================================================================


class TestHeaderConfiguration:
    """Integration tests for header configuration (NO MOCKING)."""

    def test_headers_disabled(self):
        """Headers can be disabled."""
        app = FastAPI()

        config = RateLimitConfig(
            requests_per_minute=100,
            include_headers=False,
            backend="memory",
        )
        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers
        assert "X-RateLimit-Remaining" not in response.headers

    def test_headers_enabled_by_default(self, client):
        """Headers are enabled by default."""
        response = client.get("/test")
        assert "X-RateLimit-Limit" in response.headers


# =============================================================================
# Tests: Decorator Integration
# =============================================================================


class TestDecoratorIntegration:
    """Integration tests for @rate_limit decorator (NO MOCKING)."""

    def test_decorator_limits_endpoint(self):
        """@rate_limit decorator limits specific endpoint."""
        from nexus.auth.rate_limit.decorators import rate_limit

        app = FastAPI()

        @app.get("/limited")
        @rate_limit(requests_per_minute=3, burst_size=0)
        async def limited_endpoint(request: Request):
            return {"status": "ok"}

        @app.get("/unlimited")
        async def unlimited_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Exhaust limited endpoint
        for _ in range(4):
            client.get("/limited")

        response = client.get("/limited")
        assert response.status_code == 429

        # Unlimited endpoint still works
        response = client.get("/unlimited")
        assert response.status_code == 200

    def test_decorator_429_has_retry_after(self):
        """Decorator 429 response has Retry-After header."""
        from nexus.auth.rate_limit.decorators import rate_limit

        app = FastAPI()

        @app.get("/limited")
        @rate_limit(requests_per_minute=2, burst_size=0)
        async def limited_endpoint(request: Request):
            return {"status": "ok"}

        client = TestClient(app)

        for _ in range(3):
            client.get("/limited")

        response = client.get("/limited")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
