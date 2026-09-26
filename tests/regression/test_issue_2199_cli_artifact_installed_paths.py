"""Issue #2199 — CLI artifacts must land at their INSTALLED paths, not the
emitter's STAGING paths.

WHAT WENT WRONG
---------------
``.claude/bin/emit-cli-artifacts.mjs`` writes a deliberately DOTLESS staging
layout under ``--out <dir>``::

    <dir>/codex/prompts/<cmd>.md
    <dir>/gemini/commands/<cmd>.toml

The INSTALLED locations that the Codex and Gemini CLIs actually load are
DOTTED, at the repo root: ``.codex/**`` and ``.gemini/**``. The two forms are a
deliberate two-root distinction — ``validate-emit.mjs`` encodes both, joining
``emitDir`` with ``"codex"`` for the emit root and ``root`` with ``".codex"``
for the installed root.

The 2026-08-19 Gate-2 sync (PR #2198, commit ``d0a756ef9``) copied the staging
tree into the target worktree WITHOUT applying the staging -> installed
mapping. 950 files landed at top-level ``codex/`` and ``gemini/`` while the
live ``.codex/`` and ``.gemini/`` trees were left untouched. Of those, 912 were
byte-identical duplicates (bloat), 36 carried real updates that would have sat
at a path no CLI loads while the live artifact stayed stale, and 2 were
entirely new. Relocated by hand in ``f7783de0a``.

WHY THIS TEST EXISTS AND WHY IT IS SHAPED THIS WAY
--------------------------------------------------
The delivery reported SUCCESS and delivered nothing. That is the defect class
tracked in #2189: an absence rendered as a success. The obvious guard --
"assert ``.codex/`` is non-empty" -- does NOT discriminate, and saying so is
the whole point of #2199's acceptance criterion 2: ``.codex/`` was non-empty
BEFORE the bad sync too, which is exactly why the regression shipped green.

So the invariant asserted here has TWO halves, and both are load-bearing:

1. ZERO artifacts at top-level ``codex/`` or ``gemini/``  (catches the
   staging-layout delivery), AND
2. ``.codex/`` and ``.gemini/`` are NON-EMPTY                (catches the
   degenerate way to satisfy half 1 -- deleting the installed trees).

Half 1 alone passes on a repo with no CLI artifacts at all. Half 2 alone passes
on the exact bad sync this test exists to catch. Neither is sufficient.

The check is a pure function over a root path so that the two controls below
can fire it at KNOWN-ANSWER inputs. Per ``instrument-discipline.md`` MUST-3, an
instrument that has never been shown to produce its failing verdict HERE is not
evidence when it comes back clean -- so the controls are permanent parts of the
suite, not a one-off manual check at authoring time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

REPO_ROOT = Path(__file__).resolve().parents[2]

# The emitter's staging directory names. Dotless == staging, dotted == installed.
STAGING_DIR_NAMES = ("codex", "gemini")
INSTALLED_DIR_NAMES = (".codex", ".gemini")


def find_staging_layout_violations(root: Path) -> list[str]:
    """Return the invariant violations at ``root``; empty list means clean.

    Two independent failure modes, reported together so a run names every
    problem rather than only the first:

    * a DOTLESS ``codex/`` or ``gemini/`` directory holding files -- the
      staging layout delivered verbatim;
    * a missing or EMPTY installed ``.codex/`` or ``.gemini/`` tree -- the
      degenerate way to satisfy the first half.
    """
    violations: list[str] = []

    for name in STAGING_DIR_NAMES:
        staged = root / name
        if not staged.is_dir():
            continue
        stray = sorted(p for p in staged.rglob("*") if p.is_file())
        if stray:
            sample = ", ".join(str(p.relative_to(root)) for p in stray[:5])
            violations.append(
                f"{len(stray)} file(s) at the emitter's STAGING path {name}/ "
                f"(installed path is .{name}/); e.g. {sample}"
            )

    for name in INSTALLED_DIR_NAMES:
        installed = root / name
        if not installed.is_dir():
            violations.append(f"installed tree {name}/ is missing entirely")
            continue
        if not any(p.is_file() for p in installed.rglob("*")):
            violations.append(f"installed tree {name}/ exists but holds no files")

    return violations


def test_cli_artifacts_are_at_installed_paths_not_staging_paths():
    """#2199 AC#2 — the live repo holds no staging-layout CLI artifacts."""
    violations = find_staging_layout_violations(REPO_ROOT)
    assert not violations, (
        "CLI artifacts are not at their installed paths (#2199).\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nThe emitter's dotless layout is staging-only. A Gate-2 delivery "
        "must apply the staging -> installed mapping: codex/ -> .codex/, "
        "gemini/ -> .gemini/."
    )


def test_control_detects_the_bad_sync(tmp_path: Path):
    """CONTROL A — the instrument fires on the exact shape #2199 recorded.

    Reproduces PR #2198's layout: a populated dotless tree alongside a
    populated dotted tree. Without this control, a clean verdict from the test
    above would be indistinguishable from an instrument that cannot fail.
    """
    for name in INSTALLED_DIR_NAMES:
        d = tmp_path / name / "prompts"
        d.mkdir(parents=True)
        (d / "analyze.md").write_text("installed")
    for name in STAGING_DIR_NAMES:
        d = tmp_path / name / "prompts"
        d.mkdir(parents=True)
        (d / "analyze.md").write_text("staged")

    violations = find_staging_layout_violations(tmp_path)
    assert len(violations) == 2, violations
    assert all("STAGING path" in v for v in violations), violations


def test_control_detects_deleted_installed_trees(tmp_path: Path):
    """CONTROL B — deleting the installed trees is not a way to pass.

    Half 1 of the invariant is satisfied vacuously by a repo with no CLI
    artifacts anywhere. This control pins that half 2 refuses it.
    """
    violations = find_staging_layout_violations(tmp_path)
    assert len(violations) == 2, violations
    assert all("installed tree" in v for v in violations), violations


def test_control_accepts_a_correct_delivery(tmp_path: Path):
    """CONTROL C — the instrument is not simply 'always report a violation'.

    Without this, CONTROL A and CONTROL B would both pass against a function
    that returned a non-empty list unconditionally.
    """
    for name in INSTALLED_DIR_NAMES:
        d = tmp_path / name / "prompts"
        d.mkdir(parents=True)
        (d / "analyze.md").write_text("installed")

    assert find_staging_layout_violations(tmp_path) == []


def test_control_ignores_an_empty_staging_directory(tmp_path: Path):
    """CONTROL D — an empty dotless directory is not a delivery.

    Bounds the false-positive surface: the violation is FILES at the staging
    path, not the mere existence of a directory (a stale empty dir, or one
    created by an unrelated tool, must not red the suite).
    """
    for name in INSTALLED_DIR_NAMES:
        d = tmp_path / name / "prompts"
        d.mkdir(parents=True)
        (d / "analyze.md").write_text("installed")
    (tmp_path / "codex").mkdir()

    assert find_staging_layout_violations(tmp_path) == []
