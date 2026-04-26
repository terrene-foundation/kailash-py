"""Tier-1 unit tests for FR-5 dataclass-field existence sweep (SDG-202).

The sweep fires when a backticked ``Class.field`` token appears inside an
allowlisted section. ``AnnAssign`` is the v1.0 detection scope per Q9.2 —
Pydantic v2 / attrs decorator-style classes deferred to v1.1.

These tests drive the dispatch via ``run_sweeps`` to exercise the full
section-context + override-directive + cache-lookup chain end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from spec_drift_gate import (
    SymbolIndex,
    parse_overrides,
    run_sweeps,
    scan_sections,
)


def _idx(*, classes: set[str], class_fields: dict[str, set[str]]) -> SymbolIndex:
    idx = SymbolIndex()
    idx.classes.update(classes)
    for cls, fields in class_fields.items():
        idx.class_fields[cls] = set(fields)
    return idx


def test_field_present_passes() -> None:
    spec_text = (
        "## Construction\n\n" "The `User.email` field carries the contact address.\n"
    )
    cache = _idx(classes={"User"}, class_fields={"User": {"email"}})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert findings == []


def test_field_missing_emits_fr5_finding() -> None:
    spec_text = (
        "## Construction\n\n" "The `User.zero_stage` field captures something.\n"
    )
    cache = _idx(classes={"User"}, class_fields={"User": {"email", "name"}})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    fr5 = [f for f in findings if f.fr_code == "FR-5"]
    assert len(fr5) == 1
    assert fr5[0].symbol == "User.zero_stage"
    assert fr5[0].kind == "field"
    assert "AnnAssign-only" in fr5[0].message


def test_class_with_zero_fields_does_not_fire_fr5() -> None:
    """If the class has no AnnAssign fields at all (not a dataclass-shape),
    FR-5 stays silent — the spec might be citing a method or property rather
    than a dataclass field, and FR-1/FR-2 own those surfaces."""

    spec_text = "## Construction\n\n" "The `Plain.something` reference appears here.\n"
    cache = _idx(classes={"Plain"}, class_fields={})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-5"] == []


def test_field_outside_allowlisted_section_silent() -> None:
    """A `Class.field` reference inside ``## Out of Scope`` must not fire."""

    spec_text = (
        "## Out of Scope\n\n" "Nothing about `User.zero_stage` is implemented yet.\n"
    )
    cache = _idx(classes={"User"}, class_fields={"User": {"email"}})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert findings == []


def test_class_unknown_does_not_double_emit_fr5() -> None:
    """If the class itself is missing from the source tree, FR-5 stays
    silent — FR-1 owns the missing-class surface. The token shape
    ``Ghost.field`` is not picked up by FR-1's CLASS_NAME_RE (which
    requires a single identifier), so the bare ``Ghost`` mention on the
    same line is what FR-1 catches."""

    spec_text = (
        "## Construction\n\n"
        "The `Ghost.field` reference here, plus a `Ghost` bare mention.\n"
    )
    cache = _idx(classes=set(), class_fields={})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-5"] == []
    assert any(f.fr_code == "FR-1" and f.symbol == "Ghost" for f in findings)


def test_skip_directive_suppresses_fr5() -> None:
    spec_text = (
        "## Construction\n\n"
        '<!-- spec-assert-skip: field:User.zero_stage reason:"v1.1 forward decl" -->\n\n'
        "The `User.zero_stage` field is documented for v1.1.\n"
    )
    cache = _idx(classes={"User"}, class_fields={"User": {"email"}})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-5"] == []
