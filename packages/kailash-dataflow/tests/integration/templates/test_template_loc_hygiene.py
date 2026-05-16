"""Round-5 redteam F1 regression: structural sweep over template
sources asserting every LocalRuntime() construction is paired with a
`with` context manager.

Origin: round-5 redteam surfaced FOUR call sites in
``saas_starter/tenancy/isolation.py`` AND one sibling in
``api_gateway_starter/example_app/routes/users.py`` where
``runtime = LocalRuntime()`` was constructed bare (no ``with`` block),
leaking connections + background tasks until garbage collection AND
triggering the kailash v0.12 hard-removal deprecation warning on every
call. The fix wraps each in ``with LocalRuntime() as runtime:`` so the
runtime's __exit__ closes the pool deterministically.

This is the LOCK on the fix per ``rules/refactor-invariants.md`` MUST
Rule 1 — without a regression test, the next session's edit could
re-introduce the bare construction with no signal. Per
``rules/probe-driven-verification.md`` Rule 3 (structural sweeps are
the canonical no-LLM verification form), this is a grep-based AST-level
structural sweep — not a semantic probe.

Scope: the SaaS Starter + api_gateway_starter template trees ONLY.
Production SDK code (src/kailash/, src/dataflow/) is out of scope
because it does NOT teach bare-LocalRuntime patterns through
documented helpers — the templates DO (they are the canonical
"copy this to your project" surface), so the regression risk is
higher there.

Per ``rules/testing.md`` § Audit Mode and ``rules/orphan-detection.md``
Rule 1a, structural sweeps over source belong in the test suite when
the sweep verifies an absolute state that is not reachable through
function calls.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# Repo root, derived from the location of THIS test file. Resolves the
# worktree path correctly even when invoked from a different cwd (per
# ``rules/worktree-isolation.md`` § 3a — tool roots bound to __file__
# resolve to whichever checkout owns the test binary, which is exactly
# the behavior we want for this sweep).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_TEMPLATE_ROOTS = [
    _REPO_ROOT / "packages/kailash-dataflow/templates/saas_starter",
    _REPO_ROOT / "packages/kailash-dataflow/templates/api_gateway_starter",
]

# Regex matches ``LocalRuntime()`` (and ``LocalRuntime(...)`` with args)
# only when the line is NOT inside a ``with`` statement. The two-phase
# check below is AST-based, not pure-regex, but we use this pattern for
# a fast pre-filter.
_LOCAL_RUNTIME_CALL = re.compile(r"\bLocalRuntime\s*\(")


def _find_bare_localruntime_constructions(source: str, filepath: Path) -> list[str]:
    """Walk the AST and return a list of "filepath:line — context"
    strings for every ``LocalRuntime()`` construction that is NOT
    inside a ``with`` statement context manager.

    The AST walk is the canonical structural form per
    ``rules/testing.md`` § "__all__ / Re-export Symbol Counts Use
    Structural Enumeration, Not Grep" — text grep cannot distinguish
    ``LocalRuntime()`` inside a ``with`` block from a bare assignment;
    AST node parents make the distinction.
    """
    bare_sites: list[str] = []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as exc:
        pytest.fail(f"Cannot parse {filepath}: {exc}")

    # Build a parent map so we can ask: is this ast.Call node inside a
    # ``with`` block via its parent chain? Python's ast module does not
    # set parent pointers by default.
    parent_of: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_of[child] = parent

    def _is_inside_with(node: ast.AST) -> bool:
        """Walk up the parent chain; if any ancestor is an ast.With
        AND this node is in its ``items`` (the context-manager
        expressions, not the body), then this is a ``with
        LocalRuntime()`` call."""
        current = node
        while current in parent_of:
            parent = parent_of[current]
            if isinstance(parent, ast.withitem):
                # withitem nodes hold the context-manager expression
                return True
            # Allow walking up at most a few levels — we don't want
            # ``with X: LocalRuntime()`` in the body to count as inside.
            # Specifically: stop at function/class/module boundaries.
            if isinstance(
                parent,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module),
            ):
                return False
            current = parent
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match both `LocalRuntime(...)` (Name) and `runtime.LocalRuntime(...)`
        # (Attribute). The templates only use the bare-Name form, but
        # check both for completeness.
        called_name: str | None = None
        if isinstance(func, ast.Name):
            called_name = func.id
        elif isinstance(func, ast.Attribute):
            called_name = func.attr
        if called_name != "LocalRuntime":
            continue
        if _is_inside_with(node):
            continue
        # Bare construction found.
        try:
            rel = filepath.relative_to(_REPO_ROOT)
        except ValueError:
            rel = filepath
        bare_sites.append(f"{rel}:{node.lineno}")

    return bare_sites


@pytest.mark.integration
def test_template_files_use_context_managed_localruntime():
    """Round-5 F1 regression: every ``LocalRuntime()`` construction in
    the saas_starter + api_gateway_starter template trees MUST live
    inside a ``with`` context manager.

    A bare ``runtime = LocalRuntime()`` leaks the runtime's connection
    pool and triggers the kailash v0.12 hard-removal warning. This
    test fails loudly if a future edit re-introduces the bare pattern.
    """
    violations: list[str] = []

    for root in _TEMPLATE_ROOTS:
        assert root.exists(), f"Template root not found: {root}"
        for py_file in root.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            # Fast pre-filter — skip files that don't mention LocalRuntime
            # at all so we don't AST-parse the whole template tree.
            if not _LOCAL_RUNTIME_CALL.search(source):
                continue
            violations.extend(_find_bare_localruntime_constructions(source, py_file))

    assert not violations, (
        "Round-5 F1 regression: bare LocalRuntime() construction found in "
        "template tree (expected ALL inside `with` context manager):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
