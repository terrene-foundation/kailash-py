"""Unit tests for RateLimitResult (TODO-310D).

Tier 1 tests - mocking allowed.
"""

from datetime import datetime, timezone

import pytest
from nexus.auth.rate_limit.result import RateLimitResult

# =============================================================================
# Tests: Basic Creation
# =============================================================================


class TestRateLimitResultCreation:
    """Test RateLimitResult creation."""

    def test_allowed_result(self):
        """Create an allowed result."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=45,
            reset_at=reset_at,
        )
        assert result.allowed is True
        assert result.limit == 100
        assert result.remaining == 45
        assert result.reset_at == reset_at
        assert result.retry_after_seconds is None
        assert result.identifier is None

    def test_blocked_result(self):
        """Create a blocked result."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=reset_at,
            retry_after_seconds=45,
            identifier="user:123",
        )
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after_seconds == 45
        assert result.identifier == "user:123"


# =============================================================================
# Tests: to_headers() Method
# =============================================================================


class TestRateLimitResultHeaders:
    """Test header generation."""

    def test_allowed_headers(self):
        """Allowed result generates standard headers."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=45,
            reset_at=reset_at,
        )

        headers = result.to_headers()
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "45"
        assert "2024-01-15" in headers["X-RateLimit-Reset"]
        assert "Retry-After" not in headers

    def test_blocked_headers_include_retry_after(self):
        """Blocked result includes Retry-After header."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=reset_at,
            retry_after_seconds=45,
        )

        headers = result.to_headers()
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert headers["Retry-After"] == "45"

    def test_blocked_without_retry_after(self):
        """Blocked result without retry_after_seconds omits Retry-After."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_at=reset_at,
        )

        headers = result.to_headers()
        assert "Retry-After" not in headers

    def test_headers_are_strings(self):
        """All header values are strings."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=45,
            reset_at=reset_at,
        )

        headers = result.to_headers()
        for key, value in headers.items():
            assert isinstance(key, str), f"Key {key} is not a string"
            assert isinstance(value, str), f"Value for {key} is not a string"

    def test_reset_at_iso_format(self):
        """reset_at is formatted as ISO 8601."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=45,
            reset_at=reset_at,
        )

        headers = result.to_headers()
        assert headers["X-RateLimit-Reset"] == "2024-01-15T10:30:00+00:00"

    def test_zero_remaining(self):
        """Zero remaining is formatted correctly."""
        reset_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=0,
            reset_at=reset_at,
        )

        headers = result.to_headers()
        assert headers["X-RateLimit-Remaining"] == "0"


# =============================================================================
# Tests: Decorator Export
# =============================================================================


class TestRateLimitDecorator:
    """Test rate_limit decorator creation."""

    def test_decorator_returns_callable(self):
        """rate_limit() returns a decorator."""
        from nexus.auth.rate_limit.decorators import rate_limit

        decorator = rate_limit(requests_per_minute=10)
        assert callable(decorator)

    def test_decorator_with_custom_params(self):
        """rate_limit() accepts custom parameters."""
        from nexus.auth.rate_limit.decorators import rate_limit

        decorator = rate_limit(
            requests_per_minute=50,
            burst_size=10,
        )
        assert callable(decorator)
