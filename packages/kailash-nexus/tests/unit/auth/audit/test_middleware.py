"""Unit tests for AuditMiddleware (TODO-310F).

Tier 1 tests - mocking allowed.
Tests middleware initialization, exclusion logic, and IP extraction.
"""

from unittest.mock import MagicMock

import pytest
from nexus.auth.audit.config import AuditConfig
from nexus.auth.audit.middleware import AuditMiddleware

# =============================================================================
# Tests: Exclusion Logic
# =============================================================================


class TestAuditMiddlewareExclusion:
    """Test middleware exclusion logic."""

    def _make_middleware(self, config=None):
        """Create middleware with mock app."""
        if config is None:
            config = AuditConfig()
        app = MagicMock()
        return AuditMiddleware(app, config=config)

    def _make_request(
        self, path="/test", method="GET", headers=None, client_host="127.0.0.1"
    ):
        """Create a mock request."""
        request = MagicMock()
        request.url.path = path
        request.method = method
        request.headers = headers or {}
        request.client = MagicMock()
        request.client.host = client_host
        return request

    def test_health_excluded(self):
        """Health endpoint is excluded."""
        mw = self._make_middleware()
        request = self._make_request(path="/health")
        assert mw._is_excluded(request) is True

    def test_metrics_excluded(self):
        """Metrics endpoint is excluded."""
        mw = self._make_middleware()
        request = self._make_request(path="/metrics")
        assert mw._is_excluded(request) is True

    def test_docs_excluded(self):
        """Docs endpoint is excluded."""
        mw = self._make_middleware()
        request = self._make_request(path="/docs")
        assert mw._is_excluded(request) is True

    def test_options_excluded(self):
        """OPTIONS method is excluded."""
        mw = self._make_middleware()
        request = self._make_request(path="/api/data", method="OPTIONS")
        assert mw._is_excluded(request) is True

    def test_api_not_excluded(self):
        """Normal API endpoints not excluded."""
        mw = self._make_middleware()
        request = self._make_request(path="/api/data")
        assert mw._is_excluded(request) is False

    def test_custom_exclusion(self):
        """Custom exclude paths work."""
        config = AuditConfig(exclude_paths=["/internal/*"])
        mw = self._make_middleware(config=config)
        request = self._make_request(path="/internal/status")
        assert mw._is_excluded(request) is True


# =============================================================================
# Tests: IP Extraction
# =============================================================================


class TestAuditMiddlewareIPExtraction:
    """Test client IP address extraction."""

    def _make_middleware(self, trust_proxy=False):
        app = MagicMock()
        config = AuditConfig(trust_proxy_headers=trust_proxy)
        return AuditMiddleware(app, config=config)

    def _make_request(self, headers=None, client_host="127.0.0.1"):
        request = MagicMock()
        request.headers = headers or {}
        request.client = MagicMock()
        request.client.host = client_host
        return request

    def test_direct_connection(self):
        """Direct connection uses client.host."""
        mw = self._make_middleware()
        request = self._make_request(client_host="192.168.1.100")
        assert mw._get_client_ip(request) == "192.168.1.100"

    def test_x_forwarded_for(self):
        """X-Forwarded-For extracts first IP when proxy headers trusted."""
        mw = self._make_middleware(trust_proxy=True)
        request = self._make_request(
            headers={"X-Forwarded-For": "203.0.113.50, 70.41.3.18"},
        )
        assert mw._get_client_ip(request) == "203.0.113.50"

    def test_x_real_ip(self):
        """X-Real-IP used when no X-Forwarded-For and proxy headers trusted."""
        mw = self._make_middleware(trust_proxy=True)
        request = self._make_request(
            headers={"X-Real-IP": "10.0.0.1"},
        )
        assert mw._get_client_ip(request) == "10.0.0.1"

    def test_x_forwarded_for_takes_precedence(self):
        """X-Forwarded-For takes precedence over X-Real-IP when trusted."""
        mw = self._make_middleware(trust_proxy=True)
        request = self._make_request(
            headers={
                "X-Forwarded-For": "203.0.113.50",
                "X-Real-IP": "10.0.0.1",
            },
        )
        assert mw._get_client_ip(request) == "203.0.113.50"

    def test_proxy_headers_ignored_by_default(self):
        """Proxy headers are ignored when trust_proxy_headers=False (default)."""
        mw = self._make_middleware(trust_proxy=False)
        request = self._make_request(
            headers={"X-Forwarded-For": "203.0.113.50"},
            client_host="10.0.0.1",
        )
        assert mw._get_client_ip(request) == "10.0.0.1"

    def test_no_client(self):
        """Returns 'unknown' when no client info."""
        mw = self._make_middleware()
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert mw._get_client_ip(request) == "unknown"


# =============================================================================
# Tests: Backend Initialization
# =============================================================================


class TestAuditMiddlewareInit:
    """Test middleware initialization."""

    def test_default_config(self):
        """Middleware initializes with default config."""
        app = MagicMock()
        config = AuditConfig()
        mw = AuditMiddleware(app, config=config)
        assert mw.config is config
        assert mw._backend is None
        assert mw._initialized is False

    def test_pii_filter_created(self):
        """PII filter created from config."""
        app = MagicMock()
        config = AuditConfig(
            redact_fields=["password"],
            redact_headers=["Authorization"],
        )
        mw = AuditMiddleware(app, config=config)
        assert mw._pii_filter is not None
