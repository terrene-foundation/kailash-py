# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: quote_identifier() and _validate_json_path() must not echo
raw attacker-controlled input in error messages.

Echoing raw input enables log poisoning (injecting arbitrary log entries
via crafted identifiers) and stored XSS if the error message reaches a
web interface. The fix replaces verbatim input with a fingerprint hash:
``(fingerprint=XXXX)`` where XXXX is ``hash(name) & 0xFFFF`` in hex.

This test covers both the core SDK dialect (kailash.db.dialect) and the
DataFlow dialect (dataflow.adapters.dialect).
"""

from __future__ import annotations

import re

import pytest

# ---------------------------------------------------------------------------
# Injection payloads — none of these should appear verbatim in error messages
# ---------------------------------------------------------------------------
_PAYLOADS = [
    'users"; DROP TABLE customers; --',
    "name WITH DATA",
    "123_starts_with_digit",
    '<script>alert("xss")</script>',
    "a" * 200,  # exceeds length limits
    "",
]

_FINGERPRINT_RE = re.compile(r"fingerprint=[0-9a-f]{4}")


# ======================================================================
# Core SDK: kailash.db.dialect._validate_identifier
# ======================================================================
class TestCoreSDKValidateIdentifierNoRawEcho:
    """Verify _validate_identifier() uses fingerprint, not raw input."""

    def test_injection_payload_not_echoed(self):
        from kailash.db.dialect import _validate_identifier

        payload = 'users"; DROP TABLE customers; --'
        with pytest.raises(ValueError) as exc_info:
            _validate_identifier(payload)
        error_msg = str(exc_info.value)
        assert payload not in error_msg, (
            f"Error message must NOT contain the raw payload. Got: {error_msg}"
        )
        assert _FINGERPRINT_RE.search(error_msg), (
            f"Error message must contain a hex fingerprint. Got: {error_msg}"
        )

    @pytest.mark.parametrize("payload", _PAYLOADS)
    def test_no_payload_echoed_parametrized(self, payload: str):
        from kailash.db.dialect import _validate_identifier

        with pytest.raises(ValueError) as exc_info:
            _validate_identifier(payload)
        error_msg = str(exc_info.value)
        # For empty string, skip the "not in" check (empty is substring of everything)
        if payload:
            assert payload not in error_msg
        assert _FINGERPRINT_RE.search(error_msg)


# ======================================================================
# Core SDK: kailash.db.dialect._validate_json_path
# ======================================================================
class TestCoreSDKValidateJsonPathNoRawEcho:
    """Verify _validate_json_path() uses fingerprint, not raw input."""

    def test_injection_payload_not_echoed(self):
        from kailash.db.dialect import _validate_json_path

        payload = "data'; DROP TABLE users; --"
        with pytest.raises(ValueError) as exc_info:
            _validate_json_path(payload)
        error_msg = str(exc_info.value)
        assert payload not in error_msg, (
            f"Error message must NOT contain the raw payload. Got: {error_msg}"
        )
        assert _FINGERPRINT_RE.search(error_msg), (
            f"Error message must contain a hex fingerprint. Got: {error_msg}"
        )

    @pytest.mark.parametrize(
        "payload",
        [
            "data'; DROP TABLE users; --",
            '<script>alert("xss")</script>',
            "path with spaces",
        ],
    )
    def test_no_payload_echoed_parametrized(self, payload: str):
        from kailash.db.dialect import _validate_json_path

        with pytest.raises(ValueError) as exc_info:
            _validate_json_path(payload)
        error_msg = str(exc_info.value)
        assert payload not in error_msg
        assert _FINGERPRINT_RE.search(error_msg)


# ======================================================================
# DataFlow: dataflow.adapters.dialect — all 3 dialect classes
# ======================================================================
class TestDataFlowQuoteIdentifierNoRawEcho:
    """Verify all DataFlow dialect quote_identifier() methods use fingerprint."""

    @pytest.fixture(
        params=["postgresql", "mysql", "sqlite"],
        ids=["PostgreSQL", "MySQL", "SQLite"],
    )
    def dialect(self, request):
        from dataflow.adapters.dialect import DialectManager

        return DialectManager.get_dialect(request.param)

    def test_injection_payload_not_echoed(self, dialect):
        from dataflow.adapters.exceptions import InvalidIdentifierError

        payload = 'users"; DROP TABLE customers; --'
        with pytest.raises(InvalidIdentifierError) as exc_info:
            dialect.quote_identifier(payload)
        error_msg = str(exc_info.value)
        assert payload not in error_msg, (
            f"Error message must NOT contain the raw payload. Got: {error_msg}"
        )
        assert _FINGERPRINT_RE.search(error_msg), (
            f"Error message must contain a hex fingerprint. Got: {error_msg}"
        )

    @pytest.mark.parametrize("payload", _PAYLOADS)
    def test_no_payload_echoed_parametrized(self, dialect, payload: str):
        from dataflow.adapters.exceptions import InvalidIdentifierError

        with pytest.raises(InvalidIdentifierError) as exc_info:
            dialect.quote_identifier(payload)
        error_msg = str(exc_info.value)
        if payload:
            assert payload not in error_msg
        assert _FINGERPRINT_RE.search(error_msg)

    def test_valid_identifier_still_works(self, dialect):
        """Sanity check: valid identifiers are accepted and quoted."""
        result = dialect.quote_identifier("users")
        assert "users" in result

    def test_error_message_contains_regex_hint(self, dialect):
        """Error message should tell the caller what pattern is required."""
        from dataflow.adapters.exceptions import InvalidIdentifierError

        with pytest.raises(InvalidIdentifierError) as exc_info:
            dialect.quote_identifier("bad identifier!")
        error_msg = str(exc_info.value)
        assert "must match" in error_msg.lower() or "pattern" in error_msg.lower()
