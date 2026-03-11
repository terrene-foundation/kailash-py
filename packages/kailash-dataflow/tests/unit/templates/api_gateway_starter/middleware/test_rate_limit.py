"""
Unit tests for Rate Limiting middleware.
Tests token bucket algorithm, middleware integration, and concurrent requests.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request
from templates.api_gateway_starter.middleware.rate_limit import (
    InMemoryRateLimiter,
    rate_limit,
    rate_limit_middleware,
)


class TestInMemoryRateLimiter:
    """Test token bucket rate limiter implementation."""

    def test_in_memory_rate_limiter_under_limit(self):
        """Test that requests under rate limit are allowed."""
        limiter = InMemoryRateLimiter(rate=100, window=3600)

        # Make 50 requests (under limit of 100)
        for i in range(50):
            allowed, info = limiter.check_rate_limit("user-123")
            assert allowed is True
            assert "remaining" in info
            assert info["remaining"] == 100 - i - 1

    def test_in_memory_rate_limiter_exceeds_limit(self):
        """Test that requests exceeding rate limit are blocked."""
        limiter = InMemoryRateLimiter(rate=10, window=3600)

        # Make 10 requests (at limit)
        for i in range(10):
            allowed, info = limiter.check_rate_limit("user-123")
            assert allowed is True

        # 11th request should be blocked
        allowed, info = limiter.check_rate_limit("user-123")
        assert allowed is False
        assert "retry_after" in info
        assert info["retry_after"] > 0

    def test_in_memory_rate_limiter_refill(self):
        """Test that rate limit refills after window expires."""
        limiter = InMemoryRateLimiter(rate=10, window=1)  # 1 second window

        # Exhaust limit
        for i in range(10):
            allowed, info = limiter.check_rate_limit("user-123")
            assert allowed is True

        # Should be blocked
        allowed, info = limiter.check_rate_limit("user-123")
        assert allowed is False

        # Wait for window to expire
        import time

        time.sleep(1.1)

        # Should be allowed again
        allowed, info = limiter.check_rate_limit("user-123")
        assert allowed is True

    async def test_rate_limit_middleware_under_limit(self):
        """Test middleware allows requests under limit."""
        limiter = InMemoryRateLimiter(rate=100, window=3600)
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user_id = "user-123"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await rate_limit_middleware(request, call_next, limiter)
        assert response.status_code == 200

    async def test_rate_limit_middleware_exceeds_limit(self):
        """Test middleware blocks requests exceeding limit."""
        limiter = InMemoryRateLimiter(rate=5, window=3600)
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user_id = "user-123"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        # Exhaust limit
        for i in range(5):
            response = await rate_limit_middleware(request, call_next, limiter)
            assert response.status_code == 200

        # 6th request should raise exception
        with pytest.raises(HTTPException) as exc_info:
            await rate_limit_middleware(request, call_next, limiter)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value.detail)

    async def test_rate_limit_middleware_headers(self):
        """Test middleware adds rate limit headers to response."""
        limiter = InMemoryRateLimiter(rate=100, window=3600)
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user_id = "user-123"

        mock_response = Mock()
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await rate_limit_middleware(request, call_next, limiter)

        # Check headers were added
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_decorator_valid(self):
        """Test rate_limit decorator allows valid requests."""
        limiter = InMemoryRateLimiter(rate=100, window=3600)

        @rate_limit(rate=100, window=3600)
        async def test_endpoint(request: Request):
            return {"status": "success"}

        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user_id = "user-123"

        # Should not raise exception
        result = asyncio.run(test_endpoint(request))
        assert result == {"status": "success"}

    def test_rate_limit_decorator_exceeded(self):
        """Test rate_limit decorator blocks exceeded requests."""

        @rate_limit(rate=2, window=3600)
        async def test_endpoint(request: Request):
            return {"status": "success"}

        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user_id = "user-123"

        # First 2 requests should succeed
        asyncio.run(test_endpoint(request))
        asyncio.run(test_endpoint(request))

        # 3rd request should raise exception
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(test_endpoint(request))

        assert exc_info.value.status_code == 429

    def test_reset_rate_limit(self):
        """Test admin can reset rate limit for a user."""
        limiter = InMemoryRateLimiter(rate=5, window=3600)

        # Exhaust limit
        for i in range(5):
            allowed, info = limiter.check_rate_limit("user-123")
            assert allowed is True

        # Should be blocked
        allowed, info = limiter.check_rate_limit("user-123")
        assert allowed is False

        # Admin resets limit
        limiter.reset_rate_limit("user-123")

        # Should be allowed again
        allowed, info = limiter.check_rate_limit("user-123")
        assert allowed is True

    async def test_rate_limit_concurrent_requests(self):
        """Test rate limiter handles concurrent requests correctly."""
        limiter = InMemoryRateLimiter(rate=50, window=3600)

        async def make_request(user_id: str):
            return limiter.check_rate_limit(user_id)

        # Make 100 concurrent requests (50 should succeed, 50 should fail)
        tasks = [make_request("user-123") for _ in range(100)]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for allowed, _ in results if allowed)
        blocked_count = sum(1 for allowed, _ in results if not allowed)

        assert allowed_count == 50
        assert blocked_count == 50
