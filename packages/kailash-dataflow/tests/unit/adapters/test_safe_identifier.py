"""Tests for quote_identifier / _safe_identifier SQL injection prevention."""

import pytest

from dataflow.adapters.dialect import PostgreSQLDialect
from dataflow.adapters.exceptions import InvalidIdentifierError

# Use the PostgreSQL dialect's quote_identifier as the canonical test target
_dialect = PostgreSQLDialect()


def _safe_identifier(name: str) -> str:
    """Wrapper for backward compatibility in tests."""
    return _dialect.quote_identifier(name)


class TestSafeIdentifierValid:
    """Test that valid identifiers pass validation and are quoted."""

    def test_simple_name(self):
        assert _safe_identifier("users") == '"users"'

    def test_name_with_underscore(self):
        assert _safe_identifier("user_profiles") == '"user_profiles"'

    def test_leading_underscore(self):
        assert _safe_identifier("_private") == '"_private"'

    def test_mixed_case(self):
        assert _safe_identifier("UserProfiles") == '"UserProfiles"'

    def test_single_char(self):
        assert _safe_identifier("a") == '"a"'

    def test_underscore_only(self):
        assert _safe_identifier("_") == '"_"'

    def test_alphanumeric(self):
        assert _safe_identifier("table123") == '"table123"'


class TestSafeIdentifierRejectsInjection:
    """Test that SQL injection attempts are rejected."""

    def test_drop_table_injection(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier('x"; DROP TABLE users;--')

    def test_or_injection(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("a' OR '1'='1")

    def test_spaces(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table name with spaces")

    def test_empty_string(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("")

    def test_starts_with_number(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("123starts_with_number")

    def test_semicolon(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table;drop")

    def test_hyphen(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table-name")

    def test_dot(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("schema.table")

    def test_backtick(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("`injected`")

    def test_double_quote(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier('"injected"')

    def test_newline(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table\nname")

    def test_null_byte(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table\x00name")

    def test_parentheses(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("func()")

    def test_comment_injection(self):
        with pytest.raises(InvalidIdentifierError):
            _safe_identifier("table--comment")


class TestSafeIdentifierIsInvalidIdentifierError:
    """Verify InvalidIdentifierError is an AdapterError subclass."""

    def test_is_adapter_error_subclass(self):
        from dataflow.adapters.exceptions import AdapterError

        assert issubclass(InvalidIdentifierError, AdapterError)

    def test_error_message_contains_name(self):
        with pytest.raises(InvalidIdentifierError, match="bad;name"):
            _safe_identifier("bad;name")
