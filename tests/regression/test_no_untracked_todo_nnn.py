"""Regression — no untracked TODO-NNN markers in production source (issue #781).

Belt-and-suspenders gate against pre-commit/CI drift. Asserts the same
canonical condition the .pre-commit-config.yaml::no-untracked-todo-nnn
hook enforces, so a regression slips through only if BOTH the hook AND
this test fall over together. Per .claude/rules/zero-tolerance.md
Rule 2 + Rule 6.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_REGEX = r"TODO-[0-9]+"
EXCLUDE_PATTERNS = [
    r":\s*///",  # Rust doc-comments (out of Python source)
    r":\s*//!",  # Rust inner doc-comments
    r"/build/",  # transient build artifacts
    r"tracked:",  # explicit tracker link — Class 2 exception per zero-tolerance Rule 6
    r"\.egg-info/",  # setuptools-generated SOURCES.txt — references filenames, not code comments
]


def _list_production_source_dirs() -> list[Path]:
    """Return src/ + every packages/<pkg>/src/ that exists at REPO_ROOT."""
    roots: list[Path] = []
    if (REPO_ROOT / "src").is_dir():
        roots.append(REPO_ROOT / "src")
    for pkg_src in (REPO_ROOT / "packages").glob("*/src"):
        if pkg_src.is_dir():
            roots.append(pkg_src)
    return roots


@pytest.mark.regression
def test_no_untracked_todo_nnn_in_production_source() -> None:
    """No TODO-NNN markers in production source without (tracked: ...) links.

    Mirrors .pre-commit-config.yaml::no-untracked-todo-nnn so a regression
    requires breaking both layers. Closing #781.
    """
    roots = _list_production_source_dirs()
    assert roots, "No production source roots found — check REPO_ROOT resolution"

    # `-I` skips binary files (transient *.pyc under __pycache__).
    result = subprocess.run(
        ["grep", "-rInE", CANONICAL_REGEX, *(str(r) for r in roots)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    survivors = [
        line
        for line in result.stdout.splitlines()
        if line and not any(re.search(p, line) for p in EXCLUDE_PATTERNS)
    ]

    if survivors:
        sample = "\n".join(survivors[:20])
        suffix = f"\n... ({len(survivors) - 20} more)" if len(survivors) > 20 else ""
        pytest.fail(
            f"Found {len(survivors)} untracked TODO-NNN marker(s) in production source:\n"
            f"{sample}{suffix}\n\n"
            "Each must either (1) carry a same-line (tracked: gh#NNN) or "
            "(tracked: workspaces/<project>/todos/active/<file>.md) link, "
            "or (2) be deleted.\n"
            "See .claude/rules/zero-tolerance.md Rule 2 + Rule 6, and the "
            "issue #781 cleanup workstream."
        )
