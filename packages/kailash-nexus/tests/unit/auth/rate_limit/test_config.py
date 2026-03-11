"""Unit tests for RateLimitConfig (TODO-310D).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.rate_limit.config import RateLimitConfig

# =============================================================================
# Tests: Default Values
# =============================================================================


class TestRateLimitConfigDefaults:
    """Test default configuration values."""

    def test_config_defaults(self):
        """Test all default values are correct."""
        config = RateLimitConfig()
        assert config.requests_per_minute == 100
        assert config.burst_size == 20
        assert config.backend == "memory"
        assert config.redis_url is None
        assert config.redis_key_prefix == "nexus:rl:"
        assert config.redis_connection_pool_size == 50
        assert config.redis_timeout_seconds == 5.0
        assert config.route_limits == {}
        assert config.include_headers is True
        assert config.fail_open is True

    def test_config_custom_values(self):
        """Test setting custom values."""
        config = RateLimitConfig(
            requests_per_minute=50,
            burst_size=10,
            backend="memory",
            include_headers=False,
            fail_open=False,
        )
        assert config.requests_per_minute == 50
        assert config.burst_size == 10
        assert config.include_headers is False
        assert config.fail_open is False

    def test_config_redis_values(self):
        """Test Redis-specific configuration."""
        config = RateLimitConfig(
            backend="redis",
            redis_url="redis://localhost:6379/0",
            redis_key_prefix="myapp:rl:",
            redis_connection_pool_size=25,
            redis_timeout_seconds=3.0,
        )
        assert config.backend == "redis"
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.redis_key_prefix == "myapp:rl:"
        assert config.redis_connection_pool_size == 25
        assert config.redis_timeout_seconds == 3.0

    def test_config_route_limits(self):
        """Test route_limits configuration."""
        config = RateLimitConfig(
            route_limits={
                "/api/chat/*": {"requests_per_minute": 30},
                "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
                "/health": None,  # No rate limit
            }
        )
        assert config.route_limits["/api/chat/*"] == {"requests_per_minute": 30}
        assert config.route_limits["/health"] is None


# =============================================================================
# Tests: Validation
# =============================================================================


class TestRateLimitConfigValidation:
    """Test configuration validation."""

    def test_rejects_negative_requests_per_minute(self):
        """Test validation rejects negative requests_per_minute."""
        with pytest.raises(ValueError, match="must be positive"):
            RateLimitConfig(requests_per_minute=-1)

    def test_rejects_zero_requests_per_minute(self):
        """Test validation rejects zero requests_per_minute."""
        with pytest.raises(ValueError, match="must be positive"):
            RateLimitConfig(requests_per_minute=0)

    def test_rejects_negative_burst_size(self):
        """Test validation rejects negative burst_size."""
        with pytest.raises(ValueError, match="cannot be negative"):
            RateLimitConfig(burst_size=-1)

    def test_allows_zero_burst_size(self):
        """Test zero burst_size is allowed."""
        config = RateLimitConfig(burst_size=0)
        assert config.burst_size == 0

    def test_requires_redis_url_for_redis_backend(self):
        """Test Redis backend requires URL."""
        with pytest.raises(ValueError, match="redis_url required"):
            RateLimitConfig(backend="redis")

    def test_redis_url_accepted_for_redis_backend(self):
        """Test Redis backend works with URL."""
        config = RateLimitConfig(
            backend="redis",
            redis_url="redis://localhost:6379/0",
        )
        assert config.redis_url == "redis://localhost:6379/0"

    def test_redis_url_ignored_for_memory_backend(self):
        """Test redis_url ignored for memory backend."""
        config = RateLimitConfig(
            backend="memory",
            redis_url="redis://localhost:6379/0",
        )
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.backend == "memory"


# =============================================================================
# Tests: Package Exports
# =============================================================================


class TestRateLimitPackageExports:
    """Test package exports from rate_limit."""

    def test_config_exported_from_package(self):
        """RateLimitConfig accessible from rate_limit package."""
        from nexus.auth.rate_limit import RateLimitConfig as RC

        assert RC is RateLimitConfig

    def test_backend_exported_from_package(self):
        """RateLimitBackend accessible from rate_limit package."""
        from nexus.auth.rate_limit import RateLimitBackend

        assert RateLimitBackend is not None

    def test_memory_backend_exported(self):
        """InMemoryBackend accessible from rate_limit package."""
        from nexus.auth.rate_limit import InMemoryBackend

        assert InMemoryBackend is not None

    def test_middleware_exported(self):
        """RateLimitMiddleware accessible from rate_limit package."""
        from nexus.auth.rate_limit import RateLimitMiddleware

        assert RateLimitMiddleware is not None

    def test_result_exported(self):
        """RateLimitResult accessible from rate_limit package."""
        from nexus.auth.rate_limit import RateLimitResult

        assert RateLimitResult is not None

    def test_decorator_exported(self):
        """rate_limit decorator accessible from rate_limit package."""
        from nexus.auth.rate_limit import rate_limit

        assert callable(rate_limit)

    def test_exports_from_auth_package(self):
        """Rate limit components accessible from nexus.auth."""
        from nexus.auth import RateLimitConfig, RateLimitMiddleware, rate_limit

        assert RateLimitConfig is not None
        assert RateLimitMiddleware is not None
        assert callable(rate_limit)
