"""Tier-1 unit tests for FR-2 (function/method existence sweep)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from spec_drift_gate import SymbolIndex, run_sweeps, scan_sections


def _build_pkg(tmp_path: Path) -> Path:
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "engine.py").write_text(
        textwrap.dedent(
            """\
            class MLEngine:
                def fit(self, data):
                    return None

                async def deploy(self, model, *, channels):
                    return None

            def standalone():
                return 1
            """
        )
    )
    return root


def test_fr2_class_method_exists(tmp_path: Path) -> None:
    root = _build_pkg(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## 3. Public API\n\n" "Use `MLEngine.fit()` to train.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr2 = [f for f in findings if f.fr_code == "FR-2"]
    assert fr2 == []


def test_fr2_async_method_exists(tmp_path: Path) -> None:
    root = _build_pkg(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## 3. Public API\n\n" "`MLEngine.deploy()` deploys the model.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr2 = [f for f in findings if f.fr_code == "FR-2"]
    assert fr2 == []


def test_fr2_missing_method_produces_finding(tmp_path: Path) -> None:
    root = _build_pkg(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## 3. Public API\n\n" "Use `MLEngine.fit_auto()` to auto-train.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr2 = [f for f in findings if f.fr_code == "FR-2"]
    assert len(fr2) == 1
    assert fr2[0].symbol == "MLEngine.fit_auto"
    assert fr2[0].kind == "method"


def test_fr2_missing_class_produces_method_finding(tmp_path: Path) -> None:
    """`MissingClass.foo()` cited but MissingClass doesn't exist → FR-2 finding."""
    root = _build_pkg(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 3. Public API\n\n" "Use `MissingClass.foo()` for the missing flow.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr2 = [f for f in findings if f.fr_code == "FR-2"]
    assert len(fr2) == 1
    assert fr2[0].symbol == "MissingClass.foo"


def test_fr2_silent_outside_allowlisted_section(tmp_path: Path) -> None:
    root = _build_pkg(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## Deferred to M2\n\n" "`MLEngine.fit_auto()` is deferred.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([root])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr2 = [f for f in findings if f.fr_code == "FR-2"]
    assert fr2 == []
