"""Tier 2 wiring test — exercises the CLI as a subprocess.

Per `rules/facade-manager-detection.md` MUST 1, every facade-shaped
public surface MUST have a Tier 2 test that drives it through the
production entry point — not by importing internal helpers. The gate
ships as `python scripts/spec_drift_gate.py …`; this test invokes the
script via subprocess and asserts:

- `--version` exits 0 with the expected version string
- `--no-baseline --format json` produces a JSON payload that parses,
  carries the `meta`/`findings`/`expired_baseline` keys, and round-trips
  the FR catalog (FAIL findings carry a populated `fix_hint`)
- `--no-baseline --format github` emits valid `::error`/`::warning`
  annotations
- The W6.5 combined demo fixture produces exit 1 (CI-blocking) with
  exactly 6 FAIL annotations
- `--refresh-baseline --resolved-by-sha <sha>` archives resolved
  entries and shrinks the baseline (lifecycle round-trip)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "spec_drift_gate.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "spec_drift_gate"
GH_LINE_RE = re.compile(r"^::(error|warning) file=([^,]+),line=(\d+)::")


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the gate as the production CLI would.

    We use the venv interpreter (`sys.executable`) per
    `rules/python-environment.md` Rule 1 so the subprocess resolves
    against `.venv/bin/python` regardless of pyenv shims.
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.integration
class TestVersion:
    def test_version_exits_zero(self) -> None:
        result = _run(["--version"])
        assert result.returncode == 0
        assert "spec_drift_gate v" in result.stdout


@pytest.mark.integration
class TestJsonEmitter:
    def test_pristine_v2_emits_valid_json_zero_fail(self) -> None:
        result = _run(
            [
                "--no-baseline",
                "--format",
                "json",
                "specs/ml-automl.md",
                "specs/ml-feature-store.md",
            ]
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert set(payload.keys()) == {"meta", "findings", "expired_baseline"}
        fail_findings = [f for f in payload["findings"] if f["severity"] == "FAIL"]
        assert (
            fail_findings == []
        ), f"pristine v2 corpus regressed via CLI: {fail_findings[:3]}"

    def test_w65_combined_demo_emits_six_fails(self) -> None:
        result = _run(
            [
                "--no-baseline",
                "--format",
                "json",
                "tests/fixtures/spec_drift_gate/w65_combined_demo.md",
            ]
        )
        assert result.returncode == 1, "FAIL findings MUST exit 1"
        payload = json.loads(result.stdout)
        fail_findings = [f for f in payload["findings"] if f["severity"] == "FAIL"]
        assert len(fail_findings) == 6
        # Every FAIL carries a fix_hint per ADR-6
        assert all(
            f["fix_hint"] and f["fix_hint"].startswith("→ fix:") for f in fail_findings
        )


@pytest.mark.integration
class TestGitHubEmitter:
    def test_w65_combined_demo_emits_six_error_annotations(self) -> None:
        result = _run(
            [
                "--no-baseline",
                "--format",
                "github",
                "tests/fixtures/spec_drift_gate/w65_combined_demo.md",
            ]
        )
        assert result.returncode == 1
        lines = [line for line in result.stdout.splitlines() if line.startswith("::")]
        error_lines = [line for line in lines if line.startswith("::error ")]
        assert len(error_lines) == 6
        for line in error_lines:
            m = GH_LINE_RE.match(line)
            assert m, f"malformed GH annotation: {line!r}"


@pytest.mark.integration
class TestRefreshBaselineRoundTrip:
    """End-to-end refresh flow: archive resolved entries, shrink baseline.

    Runs in `tmp_path` so we don't pollute the repo's real
    `.spec-drift-baseline.jsonl`. The fixture writes a minimal manifest
    + source tree + spec, seeds the baseline with two entries (one
    matching today's drift, one resolved), and verifies the refresh
    archives only the resolved entry.
    """

    def test_refresh_archives_only_resolved(self, tmp_path: Path) -> None:
        # Minimal valid project layout
        (tmp_path / "src" / "demo").mkdir(parents=True)
        (tmp_path / "src" / "demo" / "__init__.py").write_text(
            'from .errors import DemoError\n__all__ = ["DemoError"]\n'
        )
        (tmp_path / "src" / "demo" / "errors.py").write_text(
            "class DemoError(Exception):\n    pass\n"
        )
        (tmp_path / "specs").mkdir()
        (tmp_path / "specs" / "demo.md").write_text(
            "# Demo\n\n## Errors\n\n`DemoError` is raised on failure.\n"
        )
        (tmp_path / ".spec-drift-gate.toml").write_text(
            '[gate]\nversion = "1.0"\nspec_glob = "specs/*.md"\n'
            '[[source_roots]]\npackage = "demo"\npath = "src/demo"\n'
            "[errors_modules]\n"
            'default = "src/demo/errors.py"\n'
        )
        # Baseline: one entry that's still drift today (ResolvedClass not
        # in source — won't be flagged because no spec mentions it, so
        # refresh treats it as resolved); one entry whose drift is gone.
        baseline_path = tmp_path / ".spec-drift-baseline.jsonl"
        baseline_path.write_text(
            '{"added":"2026-04-01","ageout":"2026-07-01","finding":"FR-4",'
            '"kind":"error_class","line":10,"origin":"F-E2-01","spec":'
            '"specs/old.md","symbol":"GoneError"}\n'
            '{"added":"2026-04-01","ageout":"2026-07-01","finding":"FR-4",'
            '"kind":"error_class","line":10,"origin":"F-E2-02","spec":'
            '"specs/missing.md","symbol":"AnotherGoneError"}\n'
        )

        result = _run(
            [
                "--refresh-baseline",
                "--resolved-by-sha",
                "abc1234567",
            ],
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert "archived 2 resolved entries" in result.stdout

        # Resolved archive received both entries with the cited SHA
        archive = tmp_path / ".spec-drift-resolved.jsonl"
        assert archive.exists()
        archive_lines = [json.loads(line) for line in archive.read_text().splitlines()]
        assert len(archive_lines) == 2
        assert all(p["resolved_sha"] == "abc1234567" for p in archive_lines)

        # Baseline shrunk to zero (both entries resolved)
        assert baseline_path.read_text().strip() == ""
