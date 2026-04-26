"""Tier-1 unit tests for ADR-2 override directive parsing (SDG-102).

Verifies:
- `<!-- spec-assert: <kind>:<symbol> -->` parses to (kind, symbol, action="assert").
- `<!-- spec-assert-skip: <kind>:<symbol> reason:"..." -->` parses to
  (kind, symbol, action="skip", reason).
- Missing `reason:` on skip raises `MarkerSyntaxError`.
- Malformed directives raise `MarkerSyntaxError`.
- Errors derive from `SpecDriftGateError`.
"""

from __future__ import annotations

import pytest
from spec_drift_gate import (
    MarkerSyntaxError,
    OverrideDirective,
    SpecDriftGateError,
    parse_overrides,
)


def test_parse_assert_directive() -> None:
    text = (
        "## Examples\n\n"
        "<!-- spec-assert: class:Ensemble.from_leaderboard -->\n\n"
        "The `Ensemble.from_leaderboard()` classmethod is canonical.\n"
    )
    overrides = parse_overrides(text)
    assert len(overrides) == 1
    od = overrides[0]
    assert isinstance(od, OverrideDirective)
    assert od.kind == "class"
    assert od.symbol == "Ensemble.from_leaderboard"
    assert od.action == "assert"
    assert od.reason is None


def test_parse_skip_directive_with_reason() -> None:
    text = (
        "## Examples\n\n"
        '<!-- spec-assert-skip: class:SentimentAnalysisAgent reason:"illustrative example only" -->\n\n'
        "Imagine a `SentimentAnalysisAgent` class…\n"
    )
    overrides = parse_overrides(text)
    assert len(overrides) == 1
    od = overrides[0]
    assert od.kind == "class"
    assert od.symbol == "SentimentAnalysisAgent"
    assert od.action == "skip"
    assert od.reason == "illustrative example only"


def test_parse_skip_missing_reason_raises_marker_syntax_error() -> None:
    text = "<!-- spec-assert-skip: class:Foo -->\n"
    with pytest.raises(MarkerSyntaxError) as excinfo:
        parse_overrides(text)
    assert "reason" in str(excinfo.value).lower()


def test_parse_skip_malformed_quotes_raises_marker_syntax_error() -> None:
    text = '<!-- spec-assert-skip: class:Foo reason:"unterminated -->\n'
    with pytest.raises(MarkerSyntaxError):
        parse_overrides(text)


def test_parse_assert_missing_kind_raises_marker_syntax_error() -> None:
    text = "<!-- spec-assert: Foo -->\n"
    # No `:` separator → not a valid directive shape.
    with pytest.raises(MarkerSyntaxError):
        parse_overrides(text)


def test_marker_syntax_error_is_spec_drift_gate_error_subclass() -> None:
    assert issubclass(MarkerSyntaxError, SpecDriftGateError)
    assert issubclass(MarkerSyntaxError, Exception)


def test_parse_multiple_directives_sorted_by_line() -> None:
    text = (
        "## Examples\n\n"
        "<!-- spec-assert: class:Foo -->\n"
        "body line\n"
        '<!-- spec-assert-skip: class:Bar reason:"illustrative" -->\n'
    )
    overrides = parse_overrides(text)
    assert len(overrides) == 2
    assert [o.symbol for o in overrides] == ["Foo", "Bar"]
    assert overrides[0].line_no < overrides[1].line_no


def test_parse_no_directives_returns_empty_list() -> None:
    text = "## 1. Scope\n\nNo overrides here.\n"
    assert parse_overrides(text) == []


def test_parse_directive_records_line_number() -> None:
    text = "line1\nline2\n<!-- spec-assert: class:Foo -->\nline4\n"
    overrides = parse_overrides(text)
    assert len(overrides) == 1
    # 1-based line number
    assert overrides[0].line_no == 3


def test_parse_directive_with_dotted_symbol() -> None:
    text = "<!-- spec-assert: method:MyClass.my_method -->\n"
    overrides = parse_overrides(text)
    assert len(overrides) == 1
    assert overrides[0].kind == "method"
    assert overrides[0].symbol == "MyClass.my_method"


def test_parse_skip_directive_with_dotted_symbol_and_reason() -> None:
    text = '<!-- spec-assert-skip: method:Foo.bar reason:"deferred to M2" -->\n'
    overrides = parse_overrides(text)
    assert len(overrides) == 1
    assert overrides[0].symbol == "Foo.bar"
    assert overrides[0].reason == "deferred to M2"
