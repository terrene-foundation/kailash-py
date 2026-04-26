"""Tier-1 unit tests for FR-4 (error class in errors module sweep).

This is the W6.5 CRIT-1 reproduction: 5 fabricated *Error classes cited
in `## Errors` MUST be detected as missing from the manifest's errors module.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from spec_drift_gate import ErrorsModule, SymbolIndex, run_sweeps, scan_sections


def _write_errors_module(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            class MLError(Exception):
                pass

            class FeatureStoreError(MLError):
                pass

            class TenantRequiredError(MLError):
                pass
            """
        )
    )


def test_fr4_error_class_present_no_finding(tmp_path: Path) -> None:
    errors_path = tmp_path / "errors.py"
    _write_errors_module(errors_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## 6. Errors\n\n" "`FeatureStoreError` is the canonical wrapper.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([], errors_modules=[ErrorsModule(errors_path)])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr4 = [f for f in findings if f.fr_code == "FR-4"]
    assert fr4 == []


def test_fr4_fabricated_error_class_produces_finding(tmp_path: Path) -> None:
    errors_path = tmp_path / "errors.py"
    _write_errors_module(errors_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 6. Errors\n\n" "`FeatureGroupNotFoundError` is raised on missing groups.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([], errors_modules=[ErrorsModule(errors_path)])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr4 = [f for f in findings if f.fr_code == "FR-4"]
    assert len(fr4) == 1
    assert fr4[0].symbol == "FeatureGroupNotFoundError"
    assert fr4[0].kind == "class"


def test_fr4_w65_crit1_replay_5_fabricated_errors(tmp_path: Path) -> None:
    """W6.5 CRIT-1: round-1 FeatureStore draft cited 5 fabricated *Error
    classes in `## Errors`. Gate produces exactly 5 FR-4 findings."""
    errors_path = tmp_path / "errors.py"
    _write_errors_module(errors_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 6. Errors\n\n"
        "The store may raise:\n\n"
        "- `FeatureGroupNotFoundError`\n"
        "- `FeatureVersionNotFoundError`\n"
        "- `FeatureEvolutionError`\n"
        "- `OnlineStoreUnavailableError`\n"
        "- `CrossTenantReadError`\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([], errors_modules=[ErrorsModule(errors_path)])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr4 = [f for f in findings if f.fr_code == "FR-4"]
    assert len(fr4) == 5
    symbols = sorted(f.symbol for f in fr4)
    assert symbols == [
        "CrossTenantReadError",
        "FeatureEvolutionError",
        "FeatureGroupNotFoundError",
        "FeatureVersionNotFoundError",
        "OnlineStoreUnavailableError",
    ]


def test_fr4_silent_outside_errors_section(tmp_path: Path) -> None:
    errors_path = tmp_path / "errors.py"
    _write_errors_module(errors_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## Deferred to M2\n\n" "`FeatureGroupNotFoundError` will land in M2.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([], errors_modules=[ErrorsModule(errors_path)])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr4 = [f for f in findings if f.fr_code == "FR-4"]
    assert fr4 == []


def test_fr4_union_scan_across_multiple_errors_modules(tmp_path: Path) -> None:
    a = tmp_path / "errors_a.py"
    b = tmp_path / "errors_b.py"
    a.write_text("class FooError(Exception):\n    pass\n")
    b.write_text("class BarError(Exception):\n    pass\n")
    spec_path = tmp_path / "spec.md"
    spec_text = "## 6. Errors\n\n" "Either `FooError` or `BarError` may be raised.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([], errors_modules=[ErrorsModule(a), ErrorsModule(b)])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr4 = [f for f in findings if f.fr_code == "FR-4"]
    assert fr4 == []
