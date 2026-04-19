# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: core SDK ``dialect.quote_identifier()`` contract.

Mirrors the DataFlow-side contract (`packages/kailash-dataflow/tests/unit/
adapters/test_safe_identifier.py` and
`tests/regression/test_identifier_error_no_raw_echo.py`) for the core
SDK port at ``kailash.db.dialect``. Per ``rules/dataflow-identifier-safety.md``
MUST Rule 2, every dialect's ``quote_identifier`` MUST:

1. Validate against the allowlist regex ``^[a-zA-Z_][a-zA-Z0-9_]*$``.
2. Reject with a typed ``IdentifierError`` whose message does NOT echo
   the raw input verbatim — only a fingerprint hash is emitted.
3. Check length against the dialect limit (PG 63 / MySQL 64 / SQLite 128).
4. Quote with the dialect's quote char (``"`` for PG/SQLite, ``\u0060`` for MySQL).
5. Not attempt to escape embedded quote characters.

Closes #550 (cross-SDK parity with kailash-dataflow's canonical
``quote_identifier`` helper).
"""

from __future__ import annotations

import re

import pytest

from kailash.db.dialect import (
    IdentifierError,
    MySQLDialect,
    PostgresDialect,
    SQLiteDialect,
)

_FINGERPRINT_RE = re.compile(r"fingerprint=[0-9a-f]{4}")


# ======================================================================
# Validation — the regex allowlist rejects injection payloads
# ======================================================================
class TestQuoteIdentifierRejectsSQLInjection:
    """Every dialect MUST reject standard injection payloads via IdentifierError."""

    @pytest.fixture(params=[PostgresDialect(), MySQLDialect(), SQLiteDialect()])
    def dialect(self, request):
        return request.param

    @pytest.mark.regression
    def test_drop_table_injection(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier('users"; DROP TABLE customers; --')

    @pytest.mark.regression
    def test_name_with_spaces(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("name WITH DATA")

    @pytest.mark.regression
    def test_starts_with_digit(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("123_starts_with_digit")

    @pytest.mark.regression
    def test_empty_string(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("")

    @pytest.mark.regression
    def test_whitespace_only(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("   ")

    @pytest.mark.regression
    def test_null_byte(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("table\x00drop")

    @pytest.mark.regression
    def test_backtick(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("`injected`")

    @pytest.mark.regression
    def test_double_quote(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier('"injected"')

    @pytest.mark.regression
    def test_dot(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("schema.table")

    @pytest.mark.regression
    def test_hyphen(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("table-name")

    @pytest.mark.regression
    def test_semicolon(self, dialect):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier("table;drop")

    @pytest.mark.regression
    def test_non_string_raises_identifier_error(self, dialect):
        # The contract says IdentifierError (ValueError subclass), not TypeError.
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(None)  # type: ignore[arg-type]
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(42)  # type: ignore[arg-type]


# ======================================================================
# Length limits — PG 63, MySQL 64, SQLite 128
# ======================================================================
class TestQuoteIdentifierEnforcesDialectLengthLimit:
    @pytest.mark.regression
    def test_postgres_rejects_64_chars(self):
        dialect = PostgresDialect()
        # 63 allowed, 64 rejected
        ok = "a" * 63
        bad = "a" * 64
        assert dialect.quote_identifier(ok) == f'"{ok}"'
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(bad)

    @pytest.mark.regression
    def test_mysql_rejects_65_chars(self):
        dialect = MySQLDialect()
        ok = "a" * 64
        bad = "a" * 65
        assert dialect.quote_identifier(ok) == f"`{ok}`"
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(bad)

    @pytest.mark.regression
    def test_sqlite_rejects_129_chars(self):
        dialect = SQLiteDialect()
        ok = "a" * 128
        bad = "a" * 129
        assert dialect.quote_identifier(ok) == f'"{ok}"'
        with pytest.raises(IdentifierError):
            dialect.quote_identifier(bad)


# ======================================================================
# Dialect-appropriate quoting — PG/SQLite use `"`, MySQL uses backtick
# ======================================================================
class TestQuoteIdentifierProducesDialectQuoting:
    @pytest.mark.regression
    def test_postgres_uses_double_quotes(self):
        assert PostgresDialect().quote_identifier("users") == '"users"'

    @pytest.mark.regression
    def test_mysql_uses_backticks(self):
        assert MySQLDialect().quote_identifier("users") == "`users`"

    @pytest.mark.regression
    def test_sqlite_uses_double_quotes(self):
        assert SQLiteDialect().quote_identifier("users") == '"users"'

    @pytest.mark.regression
    def test_valid_identifiers_round_trip(self):
        # Common valid forms accepted across every dialect.
        names = [
            "users",
            "user_profiles",
            "_private",
            "UserProfiles",
            "a",
            "_",
            "table123",
        ]
        for d in (PostgresDialect(), MySQLDialect(), SQLiteDialect()):
            for n in names:
                out = d.quote_identifier(n)
                assert n in out  # wrapped but not mangled


# ======================================================================
# Error-message hygiene — fingerprint ONLY, never the raw payload
# ======================================================================
class TestQuoteIdentifierErrorFingerprintNoEcho:
    """The raw (possibly malicious) input MUST NOT appear in the error message.

    Per ``rules/dataflow-identifier-safety.md`` MUST Rule 2: the error
    message uses a fingerprint hash to prevent log-poisoning / stored
    XSS. This is the exact same contract the DataFlow helper already
    enforces; tests mirror that parity.
    """

    @pytest.fixture(params=[PostgresDialect(), MySQLDialect(), SQLiteDialect()])
    def dialect(self, request):
        return request.param

    @pytest.mark.regression
    def test_sql_injection_not_echoed(self, dialect):
        payload = 'users"; DROP TABLE customers; --'
        with pytest.raises(IdentifierError) as exc_info:
            dialect.quote_identifier(payload)
        msg = str(exc_info.value)
        assert (
            payload not in msg
        ), f"Error message MUST NOT echo the raw payload. Got: {msg}"
        assert _FINGERPRINT_RE.search(
            msg
        ), f"Error message must include a hex fingerprint. Got: {msg}"

    @pytest.mark.regression
    def test_xss_payload_not_echoed(self, dialect):
        payload = '<script>alert("xss")</script>'
        with pytest.raises(IdentifierError) as exc_info:
            dialect.quote_identifier(payload)
        msg = str(exc_info.value)
        assert payload not in msg
        assert _FINGERPRINT_RE.search(msg)

    @pytest.mark.regression
    def test_long_payload_not_echoed(self, dialect):
        # Exceed every dialect's length limit.
        payload = "bad_ident_" + ("a" * 500)
        with pytest.raises(IdentifierError) as exc_info:
            dialect.quote_identifier(payload)
        msg = str(exc_info.value)
        assert payload not in msg
        assert _FINGERPRINT_RE.search(msg)


# ======================================================================
# IdentifierError IS a ValueError — backward-compat with pre-existing
# callers that catch ValueError on invalid identifiers.
# ======================================================================
class TestIdentifierErrorIsValueError:
    @pytest.mark.regression
    def test_identifier_error_subclasses_value_error(self):
        assert issubclass(IdentifierError, ValueError)

    @pytest.mark.regression
    def test_existing_value_error_callers_still_work(self):
        """Callers that wrote ``except ValueError`` continue to catch
        the new typed ``IdentifierError`` without modification."""
        dialect = PostgresDialect()
        try:
            dialect.quote_identifier('" OR 1=1 --')
        except ValueError:
            return  # Caught correctly.
        pytest.fail("Expected ValueError (IdentifierError) to be raised")
