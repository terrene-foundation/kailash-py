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
import sys
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


def _resolve_pyright() -> list[str] | None:
    """Resolve an invocable pyright command, or None if none is installed.

    Issue #1472: the gate previously invoked ``uv run pyright``, which resolves
    uv's *project* environment — NOT the ``.venv`` the CI job installs into. In
    the ``test-dataflow`` job that env has no pyright, so ``uv run pyright``
    failed to spawn and the gate silently skipped (enforcing nothing).

    Resolution order:
      1. pyright installed alongside the running interpreter. CI runs pytest
         under ``.venv/bin/python`` and ``kailash-dataflow[dev]`` installs
         pyright==1.1.371 into that same ``.venv/bin`` — so the gate ENFORCES
         there.
      2. pyright on PATH (local dev outside a venv-adjacent install).
      3. ``uv run pyright`` (resolves a synced uv project env, e.g. plain
         ``uv run pytest`` locally where pyright is a project dep).
    """
    venv_pyright = Path(sys.executable).parent / "pyright"
    if venv_pyright.exists():
        return [str(venv_pyright)]
    on_path = shutil.which("pyright")
    if on_path is not None:
        return [on_path]
    if shutil.which("uv") is not None:
        return ["uv", "run", "pyright"]
    return None


def _run_pyright() -> tuple[int, int, str]:
    """Invoke pyright on engine.py; return (errors, warnings, raw_output)."""
    cmd = _resolve_pyright()
    if cmd is None:
        # GENUINELY cannot execute (no pyright installed anywhere) — an
        # acceptable "cannot execute" skip per test-skip-discipline. CI installs
        # pyright via kailash-dataflow[dev], so this branch is local-only.
        pytest.skip(
            "pyright is not installed in this environment — the engine pyright "
            "gate cannot execute here. CI installs it via kailash-dataflow[dev]."
        )
    result = subprocess.run(
        [*cmd, str(ENGINE_PATH)],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    # A resolved pyright that still fails to spawn (or emits nothing) is a BROKEN
    # gate, not an absent one — fail loudly rather than skip. Silent-skip here
    # was the exact #1472 failure mode (the gate enforced nothing while green).
    if "Failed to spawn" in output or not output.strip():
        pytest.fail(
            f"pyright resolved to {cmd!r} but failed to spawn or emitted no "
            f"output — the engine pyright gate could not execute. "
            f"Captured output: {output[:500]!r}"
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
    cmd = _resolve_pyright()
    if cmd is None:
        pytest.skip(
            "pyright is not installed in this environment — the version pin "
            "cannot be verified here. CI installs it via kailash-dataflow[dev]."
        )
    result = subprocess.run(
        [*cmd, "--version"],
        capture_output=True,
        text=True,
    )
    running = result.stdout.strip()
    if not running or "Failed to spawn" in (result.stdout + result.stderr):
        pytest.fail(
            f"pyright resolved to {cmd!r} but failed to report a version — the "
            f"engine pyright version pin could not be verified. "
            f"Captured: {(result.stdout + result.stderr)[:500]!r}"
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
