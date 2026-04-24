# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W18 — Registry alias + query Tier 1 unit tests.

Pure-Python coverage of the validation surfaces introduced in W18:
alias regex, reserved aliases, filter DSL grammar. Exercises zero
storage backend — every database interaction lives in the W18
integration tests (``test_w18_registry_alias_wiring.py``).
"""
from __future__ import annotations

import pytest
from kailash_ml.tracking.registry import (
    ALIAS_REGEX,
    RESERVED_ALIASES,
    SEARCH_ALLOWED_COLUMNS,
    SEARCH_ALLOWED_OPS,
    FilterParseError,
    InvalidAliasError,
    ModelRegistry,
)


# --- ALIAS_REGEX --------------------------------------------------------


@pytest.mark.parametrize(
    "alias",
    [
        "@production",
        "@staging",
        "@shadow",
        "@archived",
        "@champion",
        "@challenger",
        "@friday-release",
        "@iberia-region",
        "@v2-canary",
        "@a",
    ],
)
def test_alias_regex_accepts_valid(alias: str) -> None:
    assert ALIAS_REGEX.match(alias) is not None


@pytest.mark.parametrize(
    "alias",
    [
        "production",  # missing @
        "@",  # empty suffix
        "@1production",  # starts with digit after @
        "@-prod",  # starts with dash
        "@prod_with/slash",  # illegal char
        "@" + "a" * 65,  # too long
        "@prod release",  # space
        "@prod;drop",  # punctuation outside allowlist
    ],
)
def test_alias_regex_rejects_invalid(alias: str) -> None:
    assert ALIAS_REGEX.match(alias) is None


def test_validate_alias_rejects_non_string() -> None:
    with pytest.raises(InvalidAliasError, match="must be a string"):
        ModelRegistry._validate_alias(123)  # type: ignore[arg-type]


def test_validate_alias_fingerprint_does_not_echo_raw() -> None:
    # log-poisoning defense — the error message MUST NOT contain the
    # raw alias; it only cites the regex contract.
    with pytest.raises(InvalidAliasError) as excinfo:
        ModelRegistry._validate_alias("@bad/alias!!!")
    assert "@bad/alias" not in str(excinfo.value)
    assert "^@[a-zA-Z][a-zA-Z0-9_-]{0,63}$" in str(excinfo.value)


# --- RESERVED_ALIASES constant -----------------------------------------


def test_reserved_aliases_constant_shape() -> None:
    # Spec §4.1 MUST 2 lists the exact six strings.
    assert RESERVED_ALIASES == (
        "@production",
        "@staging",
        "@champion",
        "@challenger",
        "@shadow",
        "@archived",
    )


# --- Filter DSL --------------------------------------------------------


def test_parse_search_filter_none_returns_empty() -> None:
    where, params = ModelRegistry._parse_search_filter(None)
    assert where == ""
    assert params == []


def test_parse_search_filter_empty_string_returns_empty() -> None:
    where, params = ModelRegistry._parse_search_filter("")
    assert where == ""
    assert params == []


def test_parse_search_filter_single_clause_int_literal() -> None:
    where, params = ModelRegistry._parse_search_filter("version > 3")
    assert where == "version > ?"
    assert params == [3]


def test_parse_search_filter_single_clause_string_literal() -> None:
    where, params = ModelRegistry._parse_search_filter("name = 'fraud'")
    assert where == "name = ?"
    assert params == ["fraud"]


def test_parse_search_filter_compound_and() -> None:
    where, params = ModelRegistry._parse_search_filter("name = 'fraud' AND version > 3")
    assert where == "name = ? AND version > ?"
    assert params == ["fraud", 3]


def test_parse_search_filter_rejects_unknown_column() -> None:
    with pytest.raises(FilterParseError, match="allowlist"):
        ModelRegistry._parse_search_filter("unsafe_col = 'x'")


def test_parse_search_filter_rejects_bad_operator() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_filter("name LIKE 'fraud%'")


def test_parse_search_filter_rejects_raw_sql_injection() -> None:
    # Classic "'; DROP TABLE; --" — grammar rejects it at the
    # literal parser stage (single-quote matcher).
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_filter(
            "name = 'fraud'; DROP TABLE experiment_registry_versions; --"
        )


def test_parse_search_filter_rejects_subquery() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_filter(
            "name = (SELECT name FROM experiment_registry_versions)"
        )


def test_parse_search_filter_rejects_function_call() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_filter("name = UPPER('fraud')")


def test_parse_search_filter_error_does_not_echo_raw() -> None:
    # Same fingerprint discipline as the alias validator.
    with pytest.raises(FilterParseError) as excinfo:
        ModelRegistry._parse_search_filter("evil_col = 'attack'")
    assert "evil_col" not in str(excinfo.value)
    assert "attack" not in str(excinfo.value)


# --- order_by parser ---------------------------------------------------


def test_parse_search_order_by_none_empty() -> None:
    assert ModelRegistry._parse_search_order_by(None) == ""
    assert ModelRegistry._parse_search_order_by([]) == ""


def test_parse_search_order_by_default_asc() -> None:
    assert ModelRegistry._parse_search_order_by(["version"]) == "version ASC"


def test_parse_search_order_by_explicit_direction() -> None:
    assert ModelRegistry._parse_search_order_by(["version DESC"]) == "version DESC"


def test_parse_search_order_by_multi() -> None:
    assert (
        ModelRegistry._parse_search_order_by(["name ASC", "version DESC"])
        == "name ASC, version DESC"
    )


def test_parse_search_order_by_rejects_unknown_column() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_order_by(["evil_col"])


def test_parse_search_order_by_rejects_bad_direction() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_order_by(["version SIDEWAYS"])


def test_parse_search_order_by_rejects_extra_tokens() -> None:
    with pytest.raises(FilterParseError):
        ModelRegistry._parse_search_order_by(["version DESC EXTRA"])


# --- Allowlist constants ----------------------------------------------


def test_search_allowed_ops_no_like_or_in() -> None:
    # Defense-in-depth — if a future refactor widens the grammar,
    # this test surfaces the change at review time.
    assert "LIKE" not in SEARCH_ALLOWED_OPS
    assert "IN" not in SEARCH_ALLOWED_OPS
    assert "=" in SEARCH_ALLOWED_OPS


def test_search_allowed_columns_no_injection_surface() -> None:
    # Every name MUST match the dialect identifier regex (no quote /
    # semicolon / whitespace). Uses the same pattern the dialect
    # helper enforces on DDL identifiers.
    import re

    safe_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    for col in SEARCH_ALLOWED_COLUMNS:
        assert safe_re.match(col) is not None, (
            f"search-allowed column {col!r} would fail identifier "
            "regex — this widens the injection surface"
        )
