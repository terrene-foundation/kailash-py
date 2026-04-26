"""Tier-1 unit tests for FR-7 (test file existence sweep).

This is the W6.5 CRIT-2 reproduction: a fabricated test path cited in
`## Test Contract` MUST be detected as missing.
"""

from __future__ import annotations

import os
from pathlib import Path

from spec_drift_gate import SymbolIndex, run_sweeps, scan_sections


def test_fr7_test_file_exists_no_finding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    test_dir = tmp_path / "tests" / "unit"
    test_dir.mkdir(parents=True)
    (test_dir / "test_real.py").write_text("# real test file")

    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 7. Test Contract\n\n" "See `tests/unit/test_real.py` for unit coverage.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr7 = [f for f in findings if f.fr_code == "FR-7"]
    assert fr7 == []


def test_fr7_missing_test_file_produces_finding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 7. Test Contract\n\n"
        "See `tests/integration/test_feature_store_wiring.py` for wiring.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr7 = [f for f in findings if f.fr_code == "FR-7"]
    assert len(fr7) == 1
    assert fr7[0].symbol == "tests/integration/test_feature_store_wiring.py"
    assert fr7[0].kind == "test_path"


def test_fr7_silent_outside_test_contract_section(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## Deferred to M2\n\n" "Future: `tests/integration/test_does_not_exist.py`.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr7 = [f for f in findings if f.fr_code == "FR-7"]
    assert fr7 == []


def test_fr7_w65_crit2_replay_one_fabricated_test(tmp_path: Path, monkeypatch) -> None:
    """W6.5 CRIT-2: round-1 FeatureStore draft fabricated a wiring test path."""
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = (
        "## 7. Test Contract\n\n"
        "Wiring test: `packages/kailash-ml/tests/integration/test_feature_store_wiring.py`.\n"
    )
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr7 = [f for f in findings if f.fr_code == "FR-7"]
    assert len(fr7) == 1
    assert "test_feature_store_wiring.py" in fr7[0].symbol


def test_fr7_with_tier_2_tests_section_heading(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "spec.md"
    spec_text = "## Tier 2 Tests\n\n" "See `tests/integration/test_missing.py`.\n"
    spec_path.write_text(spec_text)
    sections = scan_sections(spec_text)
    cache = SymbolIndex.build([])
    findings = run_sweeps(spec_path, spec_text, sections, [], cache)
    fr7 = [f for f in findings if f.fr_code == "FR-7"]
    assert len(fr7) == 1
