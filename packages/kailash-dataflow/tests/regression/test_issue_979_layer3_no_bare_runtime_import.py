"""Regression for issue #979 Workstream-B B-5 — PR #976 failure-layer 3.

PR #976 failure-layer 3 (per
`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-32`):

    3. **fork + asyncio incompatibility** — child processes inherited an
       event loop they couldn't cleanly use.

The structural defense for layer 3 in the unit tier is: no `tests/unit/`
module may eagerly import the heavy real-runtime entrypoints
(`kailash.runtime.AsyncLocalRuntime`, `kailash.workflow.builder.
WorkflowBuilder`) at module top. A bare top-level import drags the real
async runtime into collection — exactly the fork+asyncio surface PR #976
layer 3 names — for every worker the #898 CI gate spawns. The Tier-1
contract (specs/testing-tiers.md) forbids these top-imports outright:
the runtime is a tier-2/3 dependency. Tests that genuinely need it must
guard the import (`pytest.importorskip` / nested-in-function /
try-guard) so collection stays cheap and fork-safe.

This file walks each `tests/unit/` module's AST and flags any
TOP-LEVEL `ImportFrom` of those modules. An import nested inside a
function body or a `try`/`with` guard is OK (it is not paid at
collection time and does not pollute the forked worker).

Tier-1: pure `ast` parsing of test source, no infrastructure, no
imports of the scanned modules themselves.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
UNIT_DIR = PACKAGE_ROOT / "tests" / "unit"

# Modules whose eager top-level import in a unit test re-opens the PR #976
# layer-3 fork+asyncio surface. Matched as module-prefix: a top-level
# `from kailash.runtime import X` or `from kailash.runtime.foo import Y`
# both count.
FORBIDDEN_TOP_IMPORT_MODULES = (
    "kailash.runtime",
    "kailash.workflow.builder",
)


def _is_guarded(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """True if `node` is NOT at module top — i.e. nested in a function/try/with.

    A module-top ImportFrom has only `ast.Module` ancestors. Any
    FunctionDef / AsyncFunctionDef / Try / With / If ancestor means the
    import is deferred (paid only when that code path runs), which is the
    importorskip / try-guard / nested pattern the Tier-1 contract allows.
    """
    cur = parents.get(node)
    while cur is not None:
        if isinstance(
            cur,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Try,
                ast.With,
                ast.AsyncWith,
                ast.If,
            ),
        ):
            return True
        cur = parents.get(cur)
    return False


def _module_matches(name: str | None) -> bool:
    if not name:
        return False
    return any(
        name == m or name.startswith(m + ".") for m in FORBIDDEN_TOP_IMPORT_MODULES
    )


def _rel(path: Path) -> str:
    """Path relative to the package root, falling back to the raw path.

    `Path.relative_to` raises `ValueError` for a path outside
    PACKAGE_ROOT. In the real test every scanned file lives under
    UNIT_DIR (always inside PACKAGE_ROOT), but the helper stays robust
    so a caller passing an out-of-tree path gets a readable message
    instead of a `ValueError`.
    """
    try:
        return str(path.relative_to(PACKAGE_ROOT))
    except ValueError:
        return str(path)


def _scan_file(path: Path) -> list[str]:
    """Return a list of violation messages for one unit-test file."""
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - surfaces a real broken test
        return [f"{path} failed to parse ({exc}); cannot verify layer-3 safety"]

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not _module_matches(node.module):
            continue
        if _is_guarded(node, parents):
            continue
        rel = _rel(path)
        names = ", ".join(alias.name for alias in node.names)
        violations.append(
            f"{rel}:{node.lineno} — bare top-level "
            f"`from {node.module} import {names}` (PR #976 layer-3: drags the "
            f"real async runtime into collection / forked workers). Move it "
            f"inside a function, a `try`/`with` guard, or use "
            f"`pytest.importorskip`."
        )
    return violations


@pytest.mark.regression
@pytest.mark.unit
def test_no_bare_runtime_import_in_unit_tests():
    """Layer 3: no unguarded top-level runtime/builder import in tests/unit/.

    A bare `from kailash.runtime import AsyncLocalRuntime` (or
    `from kailash.workflow.builder import WorkflowBuilder`) at module
    top is paid at collection time and inherited by every forked
    pytest worker — the exact fork+asyncio incompatibility PR #976
    failure-layer 3 names. Guarded imports (importorskip / nested /
    try) are fine and explicitly allowed by the Tier-1 contract.

    See workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:28-30.
    """
    assert UNIT_DIR.is_dir(), (
        f"{UNIT_DIR} does not exist — the DataFlow unit tier is the surface "
        f"PR #976 layer-3 protects; its absence is itself a regression."
    )
    all_violations: list[str] = []
    for path in sorted(UNIT_DIR.rglob("test_*.py")):
        all_violations.extend(_scan_file(path))

    assert not all_violations, (
        "Bare top-level runtime/builder imports found in tests/unit/ "
        "(PR #976 failure-layer 3 — issue #979 Workstream-B B-5):\n"
        + "\n".join(f"  - {v}" for v in all_violations)
    )
