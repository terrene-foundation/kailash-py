"""
Unit Tests for HTTP Tools Security Validation (Tier 1)

Tests security validations for HTTP tools:
- URL scheme validation (http/https only)
- SSRF protection (block private IPs, localhost)
- Timeout validation (1-300 seconds)
- Response size limits (10MB max)

Test Coverage:
    - URL validation: 8 tests
    - SSRF protection: 8 tests
    - Timeout validation: 4 tests
    - Response size limits: 0 tests (tested in integration)

Total: 20 tests (all should FAIL until validation is implemented)

NOTE: Following TDD - these tests are written FIRST and should FAIL.
      Implementation comes after tests are written.
"""

import pytest

# Skip all tests in this module until kaizen.tools.builtin is implemented
pytest.importorskip(
    "kaizen.tools.builtin.api",
    reason="TDD tests - kaizen.tools.builtin.api module not yet implemented. "
    "These tests will be enabled once the HTTP security validation is implemented.",
)


class TestURLSchemeValidation:
    """Test URL scheme validation (http/https only)."""

    def test_valid_https_url(self):
        """Test that https:// URLs are accepted."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("https://example.com")
        assert is_valid is True
        assert error is None

    def test_valid_http_url(self):
        """Test that http:// URLs are accepted."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://example.com")
        assert is_valid is True
        assert error is None

    def test_invalid_ftp_scheme(self):
        """Test that ftp:// URLs are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("ftp://example.com")
        assert is_valid is False
        assert "scheme must be http or https" in error.lower()

    def test_invalid_file_scheme(self):
        """Test that file:// URLs are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("file:///etc/passwd")
        assert is_valid is False
        assert "scheme must be http or https" in error.lower()

    def test_invalid_javascript_scheme(self):
        """Test that javascript: URLs are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("javascript:alert(1)")
        assert is_valid is False
        assert "scheme must be http or https" in error.lower()

    def test_invalid_data_scheme(self):
        """Test that data: URLs are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("data:text/html,<script>alert(1)</script>")
        assert is_valid is False
        assert "scheme must be http or https" in error.lower()

    def test_url_without_scheme(self):
        """Test that URLs without scheme are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("example.com")
        assert is_valid is False
        assert error is not None

    def test_empty_url(self):
        """Test that empty URLs are rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("")
        assert is_valid is False
        assert error is not None


class TestSSRFProtection:
    """Test SSRF protection (block private IPs and localhost)."""

    def test_reject_localhost_by_name(self):
        """Test that localhost is rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://localhost:8080")
        assert is_valid is False
        assert "localhost" in error.lower() or "ssrf" in error.lower()

    def test_reject_loopback_ipv4(self):
        """Test that 127.0.0.1 is rejected."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://127.0.0.1:8080")
        assert is_valid is False
        assert (
            "localhost" in error.lower()
            or "ssrf" in error.lower()
            or "private" in error.lower()
        )

    def test_reject_private_class_a(self):
        """Test that 10.x.x.x is rejected (private Class A)."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://10.0.0.1:8080")
        assert is_valid is False
        assert "private" in error.lower() or "ssrf" in error.lower()

    def test_reject_private_class_c(self):
        """Test that 192.168.x.x is rejected (private Class C)."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://192.168.1.1:8080")
        assert is_valid is False
        assert "private" in error.lower() or "ssrf" in error.lower()

    def test_reject_link_local(self):
        """Test that 169.254.x.x is rejected (link-local, AWS metadata)."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://169.254.169.254")  # AWS metadata
        assert is_valid is False
        assert "private" in error.lower() or "ssrf" in error.lower()

    def test_reject_ipv6_loopback(self):
        """Test that [::1] is rejected (IPv6 loopback)."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://[::1]:8080")
        assert is_valid is False
        assert (
            "localhost" in error.lower()
            or "ssrf" in error.lower()
            or "private" in error.lower()
        )

    def test_accept_public_domain(self):
        """Test that public domains are accepted."""
        from kaizen.tools.builtin.api import validate_url

        is_valid, error = validate_url("http://example.com")
        assert is_valid is True
        assert error is None

    def test_accept_public_ip(self):
        """Test that public IPs are accepted."""
        from kaizen.tools.builtin.api import validate_url

        # 8.8.8.8 is Google DNS (public)
        is_valid, error = validate_url("http://8.8.8.8")
        assert is_valid is True
        assert error is None


class TestTimeoutValidation:
    """Test timeout validation (1-300 seconds)."""

    def test_valid_timeout_minimum(self):
        """Test that timeout=1 is accepted."""
        from kaizen.tools.builtin.api import validate_timeout

        is_valid, error = validate_timeout(1)
        assert is_valid is True
        assert error is None

    def test_valid_timeout_maximum(self):
        """Test that timeout=300 is accepted."""
        from kaizen.tools.builtin.api import validate_timeout

        is_valid, error = validate_timeout(300)
        assert is_valid is True
        assert error is None

    def test_invalid_timeout_zero(self):
        """Test that timeout=0 is rejected."""
        from kaizen.tools.builtin.api import validate_timeout

        is_valid, error = validate_timeout(0)
        assert is_valid is False
        assert "at least 1" in error.lower()

    def test_invalid_timeout_negative(self):
        """Test that negative timeouts are rejected."""
        from kaizen.tools.builtin.api import validate_timeout

        is_valid, error = validate_timeout(-1)
        assert is_valid is False
        assert "at least 1" in error.lower()

    def test_invalid_timeout_too_large(self):
        """Test that timeout > 300 is rejected."""
        from kaizen.tools.builtin.api import validate_timeout

        is_valid, error = validate_timeout(301)
        assert is_valid is False
        assert "must not exceed" in error.lower() and "300" in error

    def test_valid_timeout_typical(self):
        """Test that typical timeout values are accepted."""
        from kaizen.tools.builtin.api import validate_timeout

        for timeout in [10, 30, 60, 120]:
            is_valid, error = validate_timeout(timeout)
            assert is_valid is True, f"timeout={timeout} should be valid"
            assert error is None
