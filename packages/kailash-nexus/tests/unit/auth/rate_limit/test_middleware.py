"""Unit tests for RateLimitMiddleware (TODO-310D).

Tier 1 tests - tests middleware configuration and route matching.
"""

from unittest.mock import MagicMock

import pytest
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.rate_limit.middleware import RateLimitMiddleware

# =============================================================================
# Tests: Middleware Initialization
# =============================================================================


class TestRateLimitMiddlewareInit:
    """Test middleware initialization and configuration."""

    def test_stores_config(self):
        """Middleware stores config."""
        config = RateLimitConfig(requests_per_minute=50)
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        assert mw.config.requests_per_minute == 50

    def test_default_identifier_extractor(self):
        """Middleware uses default identifier extractor."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        assert mw._identifier_extractor is not None

    def test_custom_identifier_extractor(self):
        """Middleware accepts custom identifier extractor."""

        def custom_extractor(r):
            return "custom-id"

        config = RateLimitConfig()
        mw = RateLimitMiddleware(
            app=MagicMock(),
            config=config,
            identifier_extractor=custom_extractor,
        )
        assert mw._identifier_extractor is custom_extractor

    def test_not_initialized_initially(self):
        """Backend not initialized until first request."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        assert mw._initialized is False
        assert mw._backend is None


# =============================================================================
# Tests: Route Matching
# =============================================================================


class TestRouteMatching:
    """Test route pattern matching for per-route limits."""

    def test_no_routes_returns_empty_dict(self):
        """No route_limits returns empty dict (use defaults)."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        result = mw._get_route_limit("/api/test")
        assert result == {}

    def test_exact_match(self):
        """Exact path match returns route config."""
        config = RateLimitConfig(
            route_limits={"/api/auth/login": {"requests_per_minute": 10}}
        )
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        result = mw._get_route_limit("/api/auth/login")
        assert result == {"requests_per_minute": 10}

    def test_glob_match(self):
        """Glob pattern match returns route config."""
        config = RateLimitConfig(
            route_limits={"/api/chat/*": {"requests_per_minute": 30}}
        )
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        result = mw._get_route_limit("/api/chat/messages")
        assert result == {"requests_per_minute": 30}

    def test_none_disables_rate_limiting(self):
        """None value disables rate limiting for route."""
        config = RateLimitConfig(route_limits={"/health": None})
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        result = mw._get_route_limit("/health")
        assert result is None

    def test_no_match_returns_defaults(self):
        """Unmatched path returns empty dict (use defaults)."""
        config = RateLimitConfig(
            route_limits={"/api/auth/login": {"requests_per_minute": 10}}
        )
        mw = RateLimitMiddleware(app=MagicMock(), config=config)
        result = mw._get_route_limit("/api/users")
        assert result == {}


# =============================================================================
# Tests: Identifier Extraction
# =============================================================================


class TestIdentifierExtraction:
    """Test default identifier extraction from requests."""

    def test_extracts_user_id_from_state(self):
        """Extracts user_id from request.state.user (AuthenticatedUser)."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)

        request = MagicMock()
        request.state.user = MagicMock(user_id="user-123")

        identifier = mw._default_identifier_extractor(request)
        assert identifier == "user:user-123"

    def test_extracts_api_key_from_header(self):
        """Extracts API key from X-API-Key header."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)

        request = MagicMock()
        request.state = MagicMock(spec=[])  # No user_id attribute
        request.headers.get.return_value = "sk-test1234567890"

        identifier = mw._default_identifier_extractor(request)
        assert identifier == "apikey:sk-test1"  # Truncated to 8 chars

    def test_falls_back_to_ip(self):
        """Falls back to client IP address."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)

        request = MagicMock()
        request.state = MagicMock(spec=[])  # No user_id
        request.headers.get.return_value = None  # No API key
        request.client.host = "192.168.1.1"

        identifier = mw._default_identifier_extractor(request)
        assert identifier == "ip:192.168.1.1"

    def test_unknown_when_no_client(self):
        """Returns 'unknown' when no client info."""
        config = RateLimitConfig()
        mw = RateLimitMiddleware(app=MagicMock(), config=config)

        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.headers.get.return_value = None
        request.client = None

        identifier = mw._default_identifier_extractor(request)
        assert identifier == "ip:unknown"
