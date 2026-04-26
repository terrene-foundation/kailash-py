"""Tier-1 unit tests for FR-1 (class existence sweep)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from spec_drift_gate import Finding, SymbolIndex, run_sweeps, scan_sections


@pytest.fixture
def tmp_source_root(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (src / "models.py").write_text(
        textwrap.dedent(
            """\
            class FooEngine:
                pass

            class BarStore:
                pass
            """
        )
    )
    return tmp_path


def test_fr1_class_exists_no_finding(tmp_source_root: Path) -> None:
    spec_path = tmp_source_root / "spec.md"
    spec_text = (
        "## 2. Construction\n\n" "The `FooEngine` is the canonical entry point.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([tmp_source_root / "src" / "pkg"])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert fr1 == []


def test_fr1_class_missing_produces_finding(tmp_source_root: Path) -> None:
    spec_path = tmp_source_root / "spec.md"
    spec_text = "## 2. Construction\n\n" "The `MissingEngine` does important things.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([tmp_source_root / "src" / "pkg"])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert len(fr1) == 1
    f = fr1[0]
    assert isinstance(f, Finding)
    assert f.symbol == "MissingEngine"
    assert f.kind == "class"


def test_fr1_finds_class_across_multiple_source_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "pkg_a"
    root_b = tmp_path / "pkg_b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "x.py").write_text("class Alpha:\n    pass\n")
    (root_b / "y.py").write_text("class Beta:\n    pass\n")

    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 2. Construction\n\n" "The `Alpha` and `Beta` classes are canonical.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root_a, root_b])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert fr1 == []


def test_fr1_silent_outside_allowlisted_section(tmp_source_root: Path) -> None:
    spec_path = tmp_source_root / "spec.md"
    spec_text = "## Out of Scope\n\n" "We don't implement `MissingEngine` here.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([tmp_source_root / "src" / "pkg"])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert fr1 == []  # excluded section → no finding


def test_fr1_skip_directive_suppresses_finding(tmp_source_root: Path) -> None:
    spec_path = tmp_source_root / "spec.md"
    spec_text = (
        "## 2. Construction\n\n"
        '<!-- spec-assert-skip: class:MissingEngine reason:"illustrative only" -->\n\n'
        "Imagine a `MissingEngine` class…\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    from spec_drift_gate import parse_overrides

    overrides = parse_overrides(spec_text)
    cache = SymbolIndex.build([tmp_source_root / "src" / "pkg"])
    findings = run_sweeps(spec_path, spec_text, sections, overrides, cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert fr1 == []


def test_fr1_lowercase_words_not_treated_as_class_names(tmp_source_root: Path) -> None:
    """Backticked lowercase identifiers (`x`, `foo`, etc.) MUST NOT be
    treated as class-citations — only single capitalized identifiers."""
    spec_path = tmp_source_root / "spec.md"
    spec_text = "## 2. Construction\n\n" "Pass `tenant_id` and `actor_id` as kwargs.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([tmp_source_root / "src" / "pkg"])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr1 = [f for f in findings if f.fr_code == "FR-1"]
    assert fr1 == []
