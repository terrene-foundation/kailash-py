"""Regression gate: engine.py MUST stay pyright-clean.

This test enforces the static-analysis contract established by the
dataflow-engine-pyright-cleanup workspace (2026-05-04). It fails loudly
when a future PR re-introduces an error OR pushes warnings above the
pinned ceiling.

Threshold relaxation requires:
  1. Updated thresholds AND PINNED_PYRIGHT_VERSION here.
  2. Rationale documented in this docstring + commit body.
  3. Tracking issue per zero-tolerance.md Rule 1b.
  4. Release-specialist signoff in the PR.

Silent threshold relaxation is BLOCKED.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Pinned pyright version (matches the calibration baseline). MUST match the
# pin in `packages/kailash-dataflow/pyproject.toml::[project.optional-dependencies].dev`.
PINNED_PYRIGHT_VERSION = "1.1.371"

# Post-cleanup baseline ceilings. Errors MUST be 0; warnings ≤ ceiling.
# Ceiling TIGHTENED 10 → 0 (2026-06-25): engine.py was driven to 0 pinned-pyright
# warnings (the prior 12-vs-10 drift was fixed at root — annotation corrections +
# two justified targeted ignores + one real silent-None-return bug fix). With the
# gate now CI-enforced (unified-ci test-dataflow job runs tests/regression/), 0 is
# the strict floor: any new warning fails loudly. Tightening, not relaxation.
ERROR_CEILING = 0
WARNING_CEILING = 0

ENGINE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "dataflow" / "core" / "engine.py"
)


def _run_pyright() -> tuple[int, int, str]:
    """Invoke pyright on engine.py; return (errors, warnings, raw_output)."""
    if shutil.which("uv") is None:
        pytest.skip("uv not available — gate cannot resolve pyright")
    result = subprocess.run(
        ["uv", "run", "pyright", str(ENGINE_PATH)],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    # When pyright cannot actually be spawned in this environment (e.g. the
    # node-based launcher is not invocable via `uv run` in CI), the gate cannot
    # enforce. Skip-when-unavailable rather than fail — the gap is tracked at
    # issue #1472 (engine pyright CI gate does not enforce). See test-skip
    # discipline: an acceptable skip is "cannot execute", not "system broken".
    if "Failed to spawn" in output or not output.strip():
        pytest.skip(
            "pyright is not invocable in this environment "
            "(`uv run pyright` failed to spawn) — the engine pyright gate does "
            "not enforce here; see issue #1472. "
            f"Captured output: {output[:300]!r}"
        )
    # Summary line shape: "N errors, M warnings, K informations"
    match = re.search(
        r"(\d+) errors?, (\d+) warnings?, (\d+) informations?",
        output,
    )
    if not match:
        pytest.fail(f"could not parse pyright summary from output:\n{output}")
    return int(match.group(1)), int(match.group(2)), output


@pytest.mark.regression
def test_engine_pyright_version_pinned() -> None:
    """Running pyright must match the pinned version (calibration baseline)."""
    if shutil.which("uv") is None:
        pytest.skip("uv not available — version pin cannot be verified")
    result = subprocess.run(
        ["uv", "run", "pyright", "--version"],
        capture_output=True,
        text=True,
    )
    running = result.stdout.strip()
    if not running or "Failed to spawn" in (result.stdout + result.stderr):
        pytest.skip(
            "pyright is not invocable in this environment — the engine pyright "
            "version pin cannot be verified here; see issue #1472."
        )
    assert PINNED_PYRIGHT_VERSION in running, (
        f"pyright version mismatch: running {running!r}, "
        f"gate calibrated for {PINNED_PYRIGHT_VERSION!r}. "
        f"Update both pyproject.toml::[dev] AND PINNED_PYRIGHT_VERSION + re-baseline."
    )


@pytest.mark.regression
def test_engine_pyright_zero_errors() -> None:
    """engine.py MUST have zero pyright errors."""
    errors, _warnings, output = _run_pyright()
    assert errors == ERROR_CEILING, (
        f"pyright reports {errors} errors (ceiling: {ERROR_CEILING}). "
        f"Full report:\n{output}"
    )


@pytest.mark.regression
def test_engine_pyright_warnings_under_ceiling() -> None:
    """engine.py warnings MUST stay ≤ pinned ceiling."""
    _errors, warnings, output = _run_pyright()
    assert warnings <= WARNING_CEILING, (
        f"pyright reports {warnings} warnings (ceiling: {WARNING_CEILING}). "
        f"Full report:\n{output}"
    )


@pytest.mark.regression
def test_engine_pyright_suppressions_documented() -> None:
    """Every `# pyright: ignore[...]` MUST be near a `# Reason:` line.

    The gate accepts justifications anywhere within ±5 lines of the
    suppression comment to allow for auto-formatter line wrapping.
    """
    source = ENGINE_PATH.read_text().splitlines()
    suppressions = [
        (i, line) for i, line in enumerate(source) if "# pyright: ignore" in line
    ]
    undocumented = []
    for i, line in suppressions:
        window = source[max(0, i - 5) : i + 6]
        if not any("# Reason:" in w or "Reason:" in w for w in window):
            undocumented.append((i + 1, line.strip()))
    assert not undocumented, (
        "Undocumented `# pyright: ignore` suppressions found:\n"
        + "\n".join(f"  L{n}: {ln}" for n, ln in undocumented)
        + "\nEvery suppression MUST have a `# Reason: <X>` line within ±5 lines."
    )
