"""Tier-1 tests for the kailash.delegate package shell (S1, #1035).

Covers:

* package + conformance subpackage import cleanly with empty public surface,
* the fence lint exits 0 against the committed tree,
* the fence lint detects a Fence A violation introduced via a temp file.

Subsequent shards (S2..S8) will populate the public surface; these tests
remain stable because they assert the Apache-2.0 substrate + lint contract,
not specific symbols.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_SCRIPT = REPO_ROOT / "tools" / "lint-delegate-fences.py"
DELEGATE_PKG = REPO_ROOT / "src" / "kailash" / "delegate"


def test_kailash_delegate_imports_cleanly() -> None:
    """Public surface count is the structural defense per orphan-detection.md
    Rule 6a (Merge-Time ``__all__`` Reconciliation). When S3+ shards land new
    symbols this count MUST move in lockstep -- a silent drop is the failure
    mode this assertion catches."""
    import kailash.delegate as pkg

    assert len(pkg.__all__) == 66, (
        "kailash.delegate.__all__ count drifted; #1143 + #1035 + redteam + #1532 ship 66 "
        "symbols (S2: 12 [+PrincipalKind] + S3 trust cascade: 5 + S4 audit chain: 7 "
        "+ S5 dispatch: 7 + #1532 connector-authoring surface: 10 + S6 runtime spine: 10 "
        "+ S7 conformance schema: 7 + #1035 acceptance-gate aliases: 5 "
        "+ Shard Y verifier exports: 3). "
        "If a later shard added a symbol, update this count in the same commit "
        f"per orphan-detection.md Rule 6a. Got: {pkg.__all__!r}"
    )
    # Every entry MUST resolve to a real attribute on the package (eager-
    # import contract from orphan-detection.md Rule 6).
    for name in pkg.__all__:
        assert hasattr(pkg, name), f"__all__ entry {name!r} not on package"


def test_kailash_delegate_conformance_imports_cleanly() -> None:
    """S7 (#1035) populates the conformance subpackage with the 15-symbol
    behavioural-only schema vendored from rs kailash-delegate-conformance
    per cross-sdk-inspection.md Rule 4a. Empty was the S1 baseline; this
    assertion locks the S7+ public surface count + eager-import contract."""
    import kailash.delegate.conformance as conformance

    assert len(conformance.__all__) == 15, (
        "kailash.delegate.conformance.__all__ count drifted; S7 ships 15 "
        f"symbols. Got {len(conformance.__all__)}: {conformance.__all__!r}"
    )
    # Every entry MUST resolve to a real attribute on the subpackage
    # (eager-import contract from orphan-detection.md Rule 6).
    for name in conformance.__all__:
        assert hasattr(
            conformance, name
        ), f"conformance.__all__ entry {name!r} not on subpackage"


def test_lint_script_exists_and_is_executable() -> None:
    assert LINT_SCRIPT.is_file(), f"lint script missing at {LINT_SCRIPT}"


def test_lint_script_exit_zero_on_clean_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"lint-delegate-fences.py failed on the committed tree.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_lint_script_detects_proprietary_import() -> None:
    """Plant a temp file with a forbidden import; lint MUST exit 1."""
    forbidden = DELEGATE_PKG / "_s1_fence_probe.py"
    assert not forbidden.exists(), (
        "Probe path already exists — refusing to overwrite. "
        "Delete the file and rerun."
    )
    forbidden.write_text(
        '"""Temporary fence-violation probe (S1 test). Auto-deleted."""\n'
        "from kailash_rs import foo  # noqa: F401  -- Fence A probe\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(LINT_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 1, (
            "lint-delegate-fences.py should exit 1 on a proprietary import; "
            f"got exit={result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert (
            "Fence A violation" in result.stderr
        ), f"expected 'Fence A violation' in stderr; got: {result.stderr}"
        assert "kailash_rs" in result.stderr
    finally:
        forbidden.unlink(missing_ok=True)


def test_lint_script_detects_conformance_engine_import() -> None:
    """Plant a temp file in conformance/ that imports an engine module.

    Fence B says conformance/ may not import kailash.delegate.{runtime,
    dispatch,trust,audit,posture}. Probe with a stub import — does not
    require the engine module to exist; the lint reads via AST.
    """
    forbidden = DELEGATE_PKG / "conformance" / "_s1_fence_probe.py"
    assert not forbidden.exists()
    forbidden.write_text(
        '"""Temporary Fence B probe. Auto-deleted."""\n'
        "from kailash.delegate.runtime import Engine  # noqa: F401\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(LINT_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 1
        assert (
            "Fence B violation" in result.stderr
        ), f"expected 'Fence B violation' in stderr; got: {result.stderr}"
    finally:
        forbidden.unlink(missing_ok=True)
