"""Tier-1 unit tests for FR-3 decorator-application count sweep (SDG-202).

The sweep fires when an allowlisted section line carries BOTH:
- A backticked ``@<name>`` decorator token, AND
- A count phrase like ``5 functions`` / ``12 sites`` / ``7 callers``.

Mismatches against the source-tree decorator count produce findings. Lines
without both signals stay silent (conservative v1.0 scope per Q9.2).
"""

from __future__ import annotations

from pathlib import Path

from spec_drift_gate import (
    Finding,
    SymbolIndex,
    _sweep_fr3_decorator_count,
)


def _idx(decorator_counts: dict[str, int]) -> SymbolIndex:
    idx = SymbolIndex()
    idx.decorator_counts.update(decorator_counts)
    return idx


def test_decorator_count_match_silent() -> None:
    findings: list[Finding] = []
    _sweep_fr3_decorator_count(
        line="The `@dataclass` decorator is applied to 12 classes in core/",
        line_no=42,
        spec_path=Path("specs/foo.md"),
        cache=_idx({"dataclass": 12}),
        findings=findings,
    )
    assert findings == []


def test_decorator_count_mismatch_emits_finding() -> None:
    findings: list[Finding] = []
    _sweep_fr3_decorator_count(
        line="The `@dataclass` decorator is applied to 12 classes",
        line_no=10,
        spec_path=Path("specs/foo.md"),
        cache=_idx({"dataclass": 7}),
        findings=findings,
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.fr_code == "FR-3"
    assert f.symbol == "@dataclass"
    assert f.kind == "decorator"
    assert "spec claims 12" in f.message
    assert "source tree has 7" in f.message


def test_decorator_with_no_count_phrase_silent() -> None:
    findings: list[Finding] = []
    _sweep_fr3_decorator_count(
        line="See the `@dataclass` decorator below.",
        line_no=1,
        spec_path=Path("specs/foo.md"),
        cache=_idx({"dataclass": 99}),
        findings=findings,
    )
    assert findings == []


def test_count_phrase_with_no_decorator_silent() -> None:
    findings: list[Finding] = []
    _sweep_fr3_decorator_count(
        line="There are 5 callers in production.",
        line_no=1,
        spec_path=Path("specs/foo.md"),
        cache=_idx({"dataclass": 99}),
        findings=findings,
    )
    assert findings == []


def test_count_phrase_variants() -> None:
    """The phrase regex covers functions / methods / sites / callers / etc."""

    cache = _idx({"register": 3})
    for phrase in (
        "the `@register` decorator is applied to 5 functions",
        "5 methods marked with `@register`",
        "5 callers of `@register`",
        "5 sites use `@register`",
        "5 call sites for `@register`",
        "5 definitions tagged `@register`",
        "`@register` shows up at 5 nodes",
    ):
        findings: list[Finding] = []
        _sweep_fr3_decorator_count(
            line=phrase,
            line_no=1,
            spec_path=Path("specs/foo.md"),
            cache=cache,
            findings=findings,
        )
        assert len(findings) == 1, f"phrase failed to fire: {phrase}"
        assert findings[0].symbol == "@register"


def test_decorator_with_zero_actual_emits_finding() -> None:
    findings: list[Finding] = []
    _sweep_fr3_decorator_count(
        line="`@feature` decorator is applied to 3 sites",
        line_no=5,
        spec_path=Path("specs/foo.md"),
        cache=_idx({}),
        findings=findings,
    )
    assert len(findings) == 1
    assert "source tree has 0" in findings[0].message
