# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: core-SDK dialect.quote_identifier() rejects SQL injection payloads.

Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, every DDL path that
interpolates a dynamic identifier MUST route that identifier through
``dialect.quote_identifier()``. Rule 2 pins the contract: validate against
``^[a-zA-Z_][a-zA-Z0-9_]*$``, length-check per dialect (PG 63 / MySQL 64 /
SQLite 128), quote with dialect char (``"`` / `` ` `` / ``"``), reject (do
NOT escape) embedded quotes.

This regression test exercises the contract end-to-end behaviorally per
``rules/testing.md`` § MUST Behavioral Regression Tests Over Source-Grep —
calls the real helper against the real dialect, asserts the real raise.

The sibling test ``test_identifier_error_no_raw_echo.py`` covers
fingerprint-vs-raw-echo error-message hygiene; THIS file covers the
allowlist / length / dialect-char / happy-path contract.
"""

from __future__ import annotations

import pytest

from kailash.db.dialect import (
    IdentifierError,
    MySQLDialect,
    PostgresDialect,
    SQLiteDialect,
)

# ---------------------------------------------------------------------------
# Dialect fixtures
# ---------------------------------------------------------------------------
_DIALECTS = [
    pytest.param(PostgresDialect(), 63, '"', id="postgresql"),
    pytest.param(MySQLDialect(), 64, "`", id="mysql"),
    pytest.param(SQLiteDialect(), 128, '"', id="sqlite"),
]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize("dialect,max_length,quote_char", _DIALECTS)
class TestQuoteIdentifierHappyPath:
    """Valid identifiers round-trip through quoting."""

    def test_simple_identifier_wrapped_in_dialect_quote(
        self, dialect, max_length, quote_char
    ):
        result = dialect.quote_identifier("users")
        assert result == f"{quote_char}users{quote_char}"

    def test_underscore_prefix_identifier_accepted(
        self, dialect, max_length, quote_char
    ):
        result = dialect.quote_identifier("_private_table")
        assert result == f"{quote_char}_private_table{quote_char}"

    def test_digits_after_letter_accepted(self, dialect, max_length, quote_char):
        result = dialect.quote_identifier("table_123")
        assert result == f"{quote_char}table_123{quote_char}"

    def test_at_max_length_accepted(self, dialect, max_length, quote_char):
        name = "a" + "b" * (max_length - 1)
        assert len(name) == max_length
        result = dialect.quote_identifier(name)
        assert result == f"{quote_char}{name}{quote_char}"


# ---------------------------------------------------------------------------
# Rejection: SQL injection payloads
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize("dialect,max_length,quote_char", _DIALECTS)
class TestQuoteIdentifierRejectsInjection:
    """Per ``rules/dataflow-identifier-safety.md`` MUST Rule 2 — reject, not escape."""

    def test_rejects_embedded_double_quote_injection(
        self, dialect, max_length, quote_char
    ):
        """The canonical SQL identifier injection payload."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier('users"; DROP TABLE customers; --')

    def test_rejects_embedded_backtick_injection(self, dialect, max_length, quote_char):
        """MySQL-style backtick injection attempt."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("users`; DROP TABLE customers; --")

    def test_rejects_space_in_name(self, dialect, max_length, quote_char):
        """Spaces are the simplest bypass attempt; MUST be rejected."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("name WITH DATA")

    def test_rejects_leading_digit(self, dialect, max_length, quote_char):
        """Allowlist regex requires leading letter or underscore."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("123_starts_with_digit")

    def test_rejects_sql_keyword_payload(self, dialect, max_length, quote_char):
        """SQL keyword sequences embedded as identifier text."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("users UNION SELECT password FROM admin")

    def test_rejects_null_byte(self, dialect, max_length, quote_char):
        """Null byte MUST be rejected — some drivers truncate at \\x00."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("users\x00extra")

    def test_rejects_hyphen(self, dialect, max_length, quote_char):
        """Hyphens are not in the allowlist ``[a-zA-Z0-9_]``."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("my-table")

    def test_rejects_empty_string(self, dialect, max_length, quote_char):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("")

    def test_rejects_non_string_input(self, dialect, max_length, quote_char):
        """Per the contract: non-string inputs raise IdentifierError."""
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(123)  # type: ignore[arg-type]
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rejection: length overflow (per-dialect limits)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize("dialect,max_length,quote_char", _DIALECTS)
class TestQuoteIdentifierLengthLimit:
    """Per ``rules/dataflow-identifier-safety.md`` MUST Rule 2 — dialect length limits."""

    def test_exceeding_length_limit_rejected(self, dialect, max_length, quote_char):
        name = "a" * (max_length + 1)
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(name)

    def test_far_exceeding_length_limit_rejected(self, dialect, max_length, quote_char):
        name = "a" * 1000
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(name)


# ---------------------------------------------------------------------------
# IdentifierError is a ValueError subclass (backward compat)
# ---------------------------------------------------------------------------
@pytest.mark.regression
class TestIdentifierErrorIsValueError:
    """Backward compat: callers catching ``ValueError`` MUST still see raises."""

    def test_identifier_error_caught_by_value_error(self):
        dialect = PostgresDialect()
        with pytest.raises(ValueError):
            dialect.quote_identifier('"; DROP TABLE users; --')
