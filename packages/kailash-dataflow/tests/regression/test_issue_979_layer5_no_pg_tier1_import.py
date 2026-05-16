"""Regression for issue #979 Workstream-B B-5 — PR #976 failure-layer 5.

PR #976 failure-layer 5 (per
`workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:23-32`):

    5. **PostgreSQL-requiring "unit" tests** — `TestImpactReporterIntegration`
       and similar are integration-shaped but classified tier-1.

The structural defense for layer 5 in the unit tier is: no
`tests/unit/` module may eagerly import a PostgreSQL driver
(`asyncpg`, `psycopg`, `psycopg2`) at module top. A bare top-level
driver import is the loud structural signal that an "integration-shaped"
test was misfiled into tier-1 — the exact PR #976 layer-5 failure. The
Tier-1 contract (specs/testing-tiers.md) forbids PostgreSQL in the unit
tier; tests that genuinely touch a PG driver are integration tier and
belong under `tests/integration/`. A guarded import
(`pytest.importorskip` / nested-in-function / try-guard) is permitted
only as a deliberate skip mechanism.

This file walks each `tests/unit/` module's AST and flags any
TOP-LEVEL `import asyncpg` / `import psycopg` / `import psycopg2`
(plain `Import`) OR `from <driver> import ...` (`ImportFrom`). An
import nested inside a function body or a `try`/`with` guard is OK.

Same `ast`-walk technique as the layer-3 regression. Tier-1: pure
`ast` parsing of test source, no infrastructure, no driver import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
UNIT_DIR = PACKAGE_ROOT / "tests" / "unit"

# PostgreSQL drivers. A bare top-level import of any of these in a unit
# test means the test is integration-shaped (PR #976 layer-5).
FORBIDDEN_PG_MODULES = ("asyncpg", "psycopg2", "psycopg")


def _is_guarded(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """True if `node` is NOT at module top (nested in function/try/with/if)."""
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
    return any(name == m or name.startswith(m + ".") for m in FORBIDDEN_PG_MODULES)


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
    """Return violation messages for one unit-test file."""
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - surfaces a real broken test
        return [f"{path} failed to parse ({exc}); cannot verify layer-5 safety"]

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    violations: list[str] = []
    rel = _rel(path)
    for node in ast.walk(tree):
        matched_name: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_matches(alias.name):
                    matched_name = alias.name
                    break
        elif isinstance(node, ast.ImportFrom):
            if _module_matches(node.module):
                matched_name = node.module
        if matched_name is None:
            continue
        if _is_guarded(node, parents):
            continue
        violations.append(
            f"{rel}:{node.lineno} — bare top-level import of PostgreSQL "
            f"driver `{matched_name}` (PR #976 layer-5: integration-shaped "
            f"test misfiled into tier-1). Move the test to "
            f"tests/integration/, or guard the import inside a function / "
            f"`try` / `pytest.importorskip`."
        )
    return violations


@pytest.mark.regression
@pytest.mark.unit
def test_no_bare_pg_driver_import_in_unit_tests():
    """Layer 5: no unguarded top-level asyncpg/psycopg/psycopg2 in tests/unit/.

    A bare top-level PostgreSQL-driver import in a unit test is the
    structural signature of an integration-shaped test misclassified
    into tier-1 (PR #976 failure-layer 5: `TestImpactReporter
    Integration` and similar). The Tier-1 contract forbids PostgreSQL
    in the unit tier; such tests belong under tests/integration/.
    Guarded imports (importorskip / nested / try) are permitted as a
    deliberate skip mechanism.

    See workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:31-32.
    """
    assert UNIT_DIR.is_dir(), (
        f"{UNIT_DIR} does not exist — the DataFlow unit tier is the surface "
        f"PR #976 layer-5 protects; its absence is itself a regression."
    )
    all_violations: list[str] = []
    for path in sorted(UNIT_DIR.rglob("test_*.py")):
        all_violations.extend(_scan_file(path))

    assert not all_violations, (
        "Bare top-level PostgreSQL-driver imports found in tests/unit/ "
        "(PR #976 failure-layer 5 — issue #979 Workstream-B B-5):\n"
        + "\n".join(f"  - {v}" for v in all_violations)
    )
