"""Tier-1 unit tests for FR-6 ``__all__`` membership sweep (SDG-202).

The sweep fires when an allowlisted section line literally contains
``in `__all__``` AND a backticked Python-identifier symbol. Backticked
symbols on lines that merely DISCUSS ``__all__`` as a concept (e.g.,
"CodeQL resolves every ``__all__`` entry") stay silent.

Q9.2 v1.0 conservative scope: broader prose detection (``exported``,
``exports``) is deferred to v1.1 once a tighter symbol-proximity check
lands.
"""

from __future__ import annotations

from pathlib import Path

from spec_drift_gate import (
    SymbolIndex,
    parse_overrides,
    run_sweeps,
    scan_sections,
)


def _idx(*, all_exports: set[str]) -> SymbolIndex:
    idx = SymbolIndex()
    idx.all_exports.update(all_exports)
    return idx


def test_symbol_in_all_passes() -> None:
    spec_text = (
        "## Public API\n\n"
        "The `MLEngine` symbol is in `__all__` per the package contract.\n"
    )
    cache = _idx(all_exports={"MLEngine"})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-6"] == []


def test_symbol_missing_from_all_emits_finding() -> None:
    spec_text = (
        "## Public API\n\n" "`MLEngine` and `Ghost` are in `__all__` per spec.\n"
    )
    cache = _idx(all_exports={"MLEngine"})
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    fr6 = [f for f in findings if f.fr_code == "FR-6"]
    assert len(fr6) == 1
    assert fr6[0].symbol == "Ghost"
    assert fr6[0].kind == "export"


def test_descriptive_all_mention_silent() -> None:
    """Lines that talk about ``__all__`` but do not assert membership for
    the cited symbols (e.g., "CodeQL resolves every ``__all__`` entry")
    must not fire."""

    spec_text = (
        "## Public API\n\n"
        "All names are eagerly imported (`agent_diagnostics`, `trace_exporter`)"
        " — CodeQL resolves every `__all__` entry at module scope.\n"
    )
    cache = _idx(all_exports=set())  # neither symbol is in __all__
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-6"] == []


def test_dunder_symbols_excluded() -> None:
    """``__getattr__`` / ``__init__`` are language hooks, not exports."""

    spec_text = "## Public API\n\n" "`__getattr__` and `__init__` are in `__all__`?\n"
    cache = _idx(all_exports=set())
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-6"] == []


def test_skip_directive_suppresses_fr6() -> None:
    spec_text = (
        "## Public API\n\n"
        '<!-- spec-assert-skip: export:Ghost reason:"forward declaration" -->\n\n'
        "`Ghost` is in `__all__`.\n"
    )
    cache = _idx(all_exports=set())
    sections = scan_sections(spec_text)
    overrides = parse_overrides(spec_text)
    findings = run_sweeps(
        spec_path=Path("specs/foo.md"),
        spec_text=spec_text,
        sections=sections,
        overrides=overrides,
        cache=cache,
    )
    assert [f for f in findings if f.fr_code == "FR-6"] == []
