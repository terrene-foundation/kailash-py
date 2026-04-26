"""Tier-1 acceptance test: pristine v2 specs MUST produce ZERO findings.

ADR-2 verification command (per workspaces/spec-drift-gate plan): the v2
specs `specs/ml-automl.md` + `specs/ml-feature-store.md` are the calibration
prototypes. They are re-derived directly from the canonical surface, so every
"is implemented" claim is grounded in a file:line range.

If this test produces findings, the gate's calibration (regex / sweep logic)
is wrong — fix the gate, do NOT silence the test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _gate_script(repo_root: Path) -> Path:
    return repo_root / "scripts" / "spec_drift_gate.py"


def test_pristine_ml_automl_zero_findings(repo_root: Path) -> None:
    spec = repo_root / "specs" / "ml-automl.md"
    assert spec.exists(), f"missing reference spec: {spec}"
    result = subprocess.run(
        [sys.executable, str(_gate_script(repo_root)), str(spec)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"gate FAILED for {spec}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}\n"
    )
    assert (
        "FAIL" not in result.stdout
    ), f"unexpected FAIL line(s) in gate output:\n{result.stdout}"


def test_pristine_ml_feature_store_zero_findings(repo_root: Path) -> None:
    spec = repo_root / "specs" / "ml-feature-store.md"
    assert spec.exists(), f"missing reference spec: {spec}"
    result = subprocess.run(
        [sys.executable, str(_gate_script(repo_root)), str(spec)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"gate FAILED for {spec}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}\n"
    )
    assert (
        "FAIL" not in result.stdout
    ), f"unexpected FAIL line(s) in gate output:\n{result.stdout}"


def test_version_flag_returns_0(repo_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_gate_script(repo_root)), "--version"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result.returncode == 0
    assert "spec_drift_gate" in result.stdout
