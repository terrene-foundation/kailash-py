"""End-to-end CLI regression for `tools/sweep-redteam.py` (#1129).

Per `.claude/rules/testing.md` § "End-to-End Pipeline Regression Above Unit
+ Integration": the unit tests exercise the tool's verification primitives
in isolation; this regression test executes the literal CLI invocation the
operator (and Sweep 5 in `.claude/commands/sweep.md`) runs, and asserts the
sentinel byte-equality of its output. Lifts the manual walk receipt from
PR #1175's body into a permanent CI gate.

Per `.claude/rules/user-flow-validation.md` MUST-2: the receipt is the
literal command output. This test re-runs that command on every CI build,
so the walk receipt cannot decay.

Tier-2 placement: invokes a subprocess against the real tool + real repo
state. NO mocking (per testing.md § 3-Tier Testing).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOL = REPO_ROOT / "tools" / "sweep-redteam.py"
SENTINEL_PATTERN = re.compile(
    r"^<!-- sweep-redteam:v1:(OK|N/A) "
    r"(specs=\d+ symbols=\d+ orphans=\d+ coverage_gaps=\d+ stubs=\d+|"
    r"reason=orchestration-mode no_specs=(true|false) no_tool=(true|false))"
    r" -->$",
    re.MULTILINE,
)


@pytest.mark.regression
def test_sweep_redteam_cli_all_against_this_repo() -> None:
    """Walk receipt: `python tools/sweep-redteam.py --json --all` against this repo.

    Asserts the sentinel byte-shape matches the documented contract in
    `.claude/commands/sweep.md:83`. Exit code 0 when no findings; the tool
    MAY emit findings (exit 1) without failing this test — the assertion
    is on the sentinel shape, not on a green-only state.
    """
    assert TOOL.is_file(), f"tool missing: {TOOL}"
    result = subprocess.run(
        [sys.executable, str(TOOL), "--json", "--all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode in (0, 1), (
        f"unexpected exit {result.returncode}\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    match = SENTINEL_PATTERN.search(result.stdout)
    assert match is not None, (
        "sentinel not found in stdout; documented shape is "
        "`<!-- sweep-redteam:v1:OK specs=N symbols=M orphans=O coverage_gaps=C stubs=S -->`"
        f"\nstdout:\n{result.stdout}"
    )


@pytest.mark.regression
def test_sweep_redteam_cli_rejects_path_outside_root(tmp_path: Path) -> None:
    """Defense-in-depth: --json arg pointing outside the repo MUST refuse.

    Per R1 security review (#1175 R1-security-01): the tool runs against
    operator workspaces; an argv-influenced invocation passing
    `--json /tmp/foo.md` MUST refuse with a typed error rather than
    silently reading a path outside the repo root.
    """
    # Create a file outside REPO_ROOT (tmp_path is in $TMPDIR, not under repo).
    outside_spec = tmp_path / "foo.md"
    outside_spec.write_text("MUST `Some.Symbol` exists\n", encoding="utf-8")
    assert not str(outside_spec).startswith(
        str(REPO_ROOT)
    ), "tmp_path unexpectedly under REPO_ROOT; the test premise is invalid"
    result = subprocess.run(
        [sys.executable, str(TOOL), "--json", str(outside_spec)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, (
        f"expected parser.error exit 2; got {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    assert (
        "escapes repo root" in result.stderr
    ), f"expected 'escapes repo root' guard message; got:\n{result.stderr}"
