"""Unit tests for PIIFilter (TODO-310F).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.audit.pii_filter import PIIFilter

# =============================================================================
# Tests: Header Redaction
# =============================================================================


class TestPIIFilterHeaders:
    """Test header redaction."""

    def test_redact_authorization(self):
        """Authorization header is redacted."""
        pii = PIIFilter(
            redact_fields=[],
            redact_headers=["Authorization"],
        )

        headers = {
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
        }

        result = pii.redact_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["Content-Type"] == "application/json"

    def test_redact_multiple_headers(self):
        """Multiple headers redacted."""
        pii = PIIFilter(
            redact_fields=[],
            redact_headers=["Authorization", "Cookie", "X-API-Key"],
        )

        headers = {
            "Authorization": "Bearer xyz",
            "Cookie": "session=abc123",
            "X-API-Key": "key-456",
            "Accept": "application/json",
        }

        result = pii.redact_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["Cookie"] == "[REDACTED]"
        assert result["X-API-Key"] == "[REDACTED]"
        assert result["Accept"] == "application/json"

    def test_case_insensitive_header_match(self):
        """Header matching is case-insensitive."""
        pii = PIIFilter(
            redact_fields=[],
            redact_headers=["Authorization"],
        )

        headers = {"authorization": "Bearer xyz"}
        result = pii.redact_headers(headers)
        assert result["authorization"] == "[REDACTED]"

    def test_no_redaction_when_no_match(self):
        """Non-sensitive headers preserved."""
        pii = PIIFilter(
            redact_fields=[],
            redact_headers=["Authorization"],
        )

        headers = {"Content-Type": "text/html", "Accept": "application/json"}
        result = pii.redact_headers(headers)
        assert result == headers

    def test_empty_headers(self):
        """Empty headers dict returns empty dict."""
        pii = PIIFilter(redact_fields=[], redact_headers=["Authorization"])
        assert pii.redact_headers({}) == {}

    def test_custom_replacement(self):
        """Custom replacement string used."""
        pii = PIIFilter(
            redact_fields=[],
            redact_headers=["Authorization"],
            replacement="***",
        )

        result = pii.redact_headers({"Authorization": "Bearer xyz"})
        assert result["Authorization"] == "***"


# =============================================================================
# Tests: Body Redaction
# =============================================================================


class TestPIIFilterBody:
    """Test body field redaction."""

    def test_redact_password_field(self):
        """Password field is redacted."""
        pii = PIIFilter(
            redact_fields=["password"],
            redact_headers=[],
        )

        body = {"username": "alice", "password": "super-secret"}
        result = pii.redact_body(body)
        assert result["username"] == "alice"
        assert result["password"] == "[REDACTED]"

    def test_redact_nested_fields(self):
        """Nested sensitive fields are redacted."""
        pii = PIIFilter(
            redact_fields=["password", "secret"],
            redact_headers=[],
        )

        body = {
            "username": "alice",
            "password": "secret123",
            "nested": {
                "secret": "also-secret",
                "public": "visible",
            },
        }

        result = pii.redact_body(body)
        assert result["username"] == "alice"
        assert result["password"] == "[REDACTED]"
        assert result["nested"]["secret"] == "[REDACTED]"
        assert result["nested"]["public"] == "visible"

    def test_redact_in_list(self):
        """Fields in list items are redacted."""
        pii = PIIFilter(
            redact_fields=["token"],
            redact_headers=[],
        )

        body = [
            {"name": "item1", "token": "abc"},
            {"name": "item2", "token": "def"},
        ]

        result = pii.redact_body(body)
        assert result[0]["name"] == "item1"
        assert result[0]["token"] == "[REDACTED]"
        assert result[1]["token"] == "[REDACTED]"

    def test_case_insensitive_field_match(self):
        """Field matching is case-insensitive."""
        pii = PIIFilter(
            redact_fields=["password"],
            redact_headers=[],
        )

        body = {"Password": "xyz", "PASSWORD": "abc"}
        result = pii.redact_body(body)
        assert result["Password"] == "[REDACTED]"
        assert result["PASSWORD"] == "[REDACTED]"

    def test_primitive_values_unchanged(self):
        """Primitive values (int, bool, None) pass through."""
        pii = PIIFilter(redact_fields=["password"], redact_headers=[])

        assert pii.redact_body(42) == 42
        assert pii.redact_body(True) is True
        assert pii.redact_body(None) is None

    def test_empty_body(self):
        """Empty dict returns empty dict."""
        pii = PIIFilter(redact_fields=["password"], redact_headers=[])
        assert pii.redact_body({}) == {}


# =============================================================================
# Tests: Pattern-Based PII Detection
# =============================================================================


class TestPIIFilterPatterns:
    """Test pattern-based PII detection."""

    def test_redact_email(self):
        """Email addresses in strings are redacted."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        text = "Contact user@example.com for details"
        result = pii._redact_patterns(text)
        assert "user@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_redact_ssn(self):
        """SSN patterns are redacted."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        text = "SSN: 123-45-6789"
        result = pii._redact_patterns(text)
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_redact_credit_card(self):
        """Credit card patterns are redacted."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        text = "Card: 4111-1111-1111-1111"
        result = pii._redact_patterns(text)
        assert "4111-1111-1111-1111" not in result
        assert "[CARD_REDACTED]" in result

    def test_redact_credit_card_no_dashes(self):
        """Credit card without dashes are redacted."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        text = "Card: 4111111111111111"
        result = pii._redact_patterns(text)
        assert "4111111111111111" not in result

    def test_string_in_body_patterns_applied(self):
        """Patterns applied to string values in body dict."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        body = {"message": "Contact user@example.com for details"}
        result = pii.redact_body(body)
        assert "user@example.com" not in result["message"]
        assert "[EMAIL_REDACTED]" in result["message"]

    def test_no_patterns_in_normal_text(self):
        """Normal text without PII passes through."""
        pii = PIIFilter(redact_fields=[], redact_headers=[])

        text = "Hello world, no PII here"
        result = pii._redact_patterns(text)
        assert result == text


# =============================================================================
# Tests: Query Parameter Redaction
# =============================================================================


class TestPIIFilterQueryParams:
    """Test query parameter redaction."""

    def test_redact_sensitive_params(self):
        """Sensitive query params are redacted."""
        pii = PIIFilter(
            redact_fields=["password", "token"],
            redact_headers=[],
        )

        params = {"name": "alice", "password": "secret", "token": "abc123"}
        result = pii.redact_query_params(params)
        assert result["name"] == "alice"
        assert result["password"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_no_redaction_when_no_match(self):
        """Non-sensitive params preserved."""
        pii = PIIFilter(
            redact_fields=["password"],
            redact_headers=[],
        )

        params = {"page": "1", "limit": "10"}
        result = pii.redact_query_params(params)
        assert result == params

    def test_empty_params(self):
        """Empty params dict returns empty dict."""
        pii = PIIFilter(redact_fields=["password"], redact_headers=[])
        assert pii.redact_query_params({}) == {}
