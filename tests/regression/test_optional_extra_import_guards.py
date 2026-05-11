# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structural invariant — module-scope imports of optional-extra packages MUST be guarded.

Per `rules/dependencies.md` § "Declared = Imported" / "BLOCKED Anti-Patterns":
every `import X` at module scope MUST resolve to a package declared in
the project's `pyproject.toml::dependencies` slim-core list. Imports of
packages declared ONLY under optional extras (`kailash[db-sqlite]`,
`kailash[server]`, etc.) MUST be wrapped in `try/except ImportError`
that raises a typed `ImportError` naming the extra.

Failure mode this test prevents: clean `pip install kailash` users get
bare `ModuleNotFoundError: No module named 'aiosqlite'` instead of an
actionable "install kailash[db-sqlite]" message.

## Two-allowlist design

1. `_FIXED_SITES` — modules where the optional-extra import is wrapped
   via `try/except ImportError`. These are the proof points. AST walks
   them and asserts the try/except wrap is present.

2. `_KNOWN_VIOLATIONS` — modules with the SAME bug class but NOT yet
   fixed (sibling-sweep finding, ~46 sites). The test does NOT fail on
   these — they are pre-existing tech debt with a tracking entry (see
   the docstring at the bottom). The test DOES fail if a NEW module
   imports an optional-extra package at module scope without a guard
   AND is not in either list — the structural defense against the bug
   class regrowing.

When a violation is fixed, MOVE its entry from `_KNOWN_VIOLATIONS` to
`_FIXED_SITES`. When the `_KNOWN_VIOLATIONS` list is empty, this test
becomes a strict allowlist (no new optional-extra module-scope imports
without a guard).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


# Optional-extra packages from pyproject.toml — every package declared
# ONLY under [project.optional-dependencies] (not in core dependencies).
# Maintained alongside pyproject.toml — when an extra is added/removed,
# this set MUST be updated in the same commit.
_OPTIONAL_PACKAGES = frozenset(
    {
        # db extras
        "aiosqlite",
        "aiomysql",
        "asyncpg",
        # server extra
        "aiohttp",
        "aiohttp_cors",
        "fastapi",
        "uvicorn",
        "starlette",  # fastapi transitively
        "aiofiles",
        "bcrypt",
        "jwt",  # PyJWT
        # http-client extra
        "httpx",
        # redis extra
        "redis",
        # auth-azure extra
        "msal",
        # scheduler extra
        "apscheduler",
        # shamir extra
        "shamir_mnemonic",
    }
)


# Modules where the optional-extra import IS wrapped in try/except ImportError
# with an actionable error message. The test verifies the wrap is present.
_FIXED_SITES = frozenset(
    {
        # First wave (PR #956): the 3 sites surfaced during #876 follow-up.
        "src/kailash/core/pool/sqlite_pool.py",
        "src/kailash/trust/migrations/eatp_human_origin.py",
        "src/kailash/api/gateway.py",
        # Second wave: sibling sweep of the 22 _KNOWN_VIOLATIONS allowlist
        # entries. Same try/except pattern as the first wave per
        # rules/dependencies.md § "Declared = Imported" / "__init__.py
        # Module-Scope Imports Honor The Manifest".
        # FastAPI / Starlette / Uvicorn — server extra
        "src/kailash/api/workflow_api.py",
        "src/kailash/api/tests/test_workflow_api_404.py",
        "src/kailash/servers/connection_metrics_router.py",
        "src/kailash/servers/durable_workflow_server.py",
        "src/kailash/servers/workflow_server.py",
        "src/kailash/gateway/api.py",
        "src/kailash/channels/api_channel.py",
        "src/kailash/middleware/auth/auth_manager.py",
        "src/kailash/middleware/communication/api_gateway.py",
        "src/kailash/middleware/communication/realtime.py",
        "src/kailash/middleware/gateway/durable_gateway.py",
        # aiohttp / aiohttp_cors — server extra
        "src/kailash/channels/mcp/sse.py",
        "src/kailash/channels/mcp/http.py",
        "src/kailash/client/enhanced_client.py",
        "src/kailash/edge/migration/edge_migrator.py",
        "src/kailash/nodes/api/http.py",
        "src/kailash/nodes/monitoring/connection_dashboard.py",
        "src/kailash/nodes/transaction/participant_transport.py",
        # bcrypt — server extra
        "src/kailash/nodes/admin/user_management.py",
        # PyJWT — server extra (also satisfied by trust extra)
        "src/kailash/trust/auth/sso/azure.py",
        "src/kailash/trust/auth/sso/google.py",
        "src/kailash/trust/auth/sso/apple.py",
    }
)


# All sites listed in _KNOWN_VIOLATIONS at PR #956 landing have been fixed
# (second-wave sweep). The empty allowlist makes
# test_no_new_unguarded_optional_extra_imports the only gate going forward —
# any new module-scope optional-extra import without a guard surfaces as a
# new violator, not silently absorbed into the allowlist.
_KNOWN_VIOLATIONS: frozenset[str] = frozenset()


def _enumerate_module_scope_optional_imports(file_path: Path) -> list[tuple[str, int]]:
    """Return (root_package, lineno) for every module-scope optional-extra import.

    Module-scope = top-level statements only. Imports inside functions,
    classes, conditional blocks (if TYPE_CHECKING, try/except) are
    excluded — they're already guarded or evaluated lazily.
    """
    try:
        tree = ast.parse(file_path.read_text(), filename=str(file_path))
    except SyntaxError:
        return []

    hits: list[tuple[str, int]] = []
    for node in tree.body:  # body = top-level only
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _OPTIONAL_PACKAGES:
                    hits.append((root, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _OPTIONAL_PACKAGES:
                    hits.append((root, node.lineno))
    return hits


def _has_module_scope_try_except_import(file_path: Path, package: str) -> bool:
    """True if the file has a module-scope `try: import <package>` block.

    Walks top-level `Try` nodes and looks for an `Import` / `ImportFrom`
    of `package` (or `from package` / `from package.X`) inside the try
    body. The except branch must raise ImportError (verified by message).
    """
    try:
        tree = ast.parse(file_path.read_text(), filename=str(file_path))
    except SyntaxError:
        return False

    for node in tree.body:
        if not isinstance(node, ast.Try):
            continue
        # Inspect the try body for the import
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name.split(".")[0] == package:
                        return True
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module and stmt.module.split(".")[0] == package:
                    return True
    return False


def _all_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]


@pytest.mark.regression
def test_fixed_sites_have_try_except_import_guard():
    """Every module in _FIXED_SITES has its optional-extra import inside a try/except."""
    root = _project_root()
    failures: list[str] = []
    for rel in sorted(_FIXED_SITES):
        path = root / rel
        if not path.exists():
            failures.append(
                f"{rel}: file missing (refactor moved it? update _FIXED_SITES)"
            )
            continue
        hits = _enumerate_module_scope_optional_imports(path)
        for package, lineno in hits:
            if not _has_module_scope_try_except_import(path, package):
                failures.append(
                    f"{rel}:{lineno} imports '{package}' at module scope "
                    f"WITHOUT a try/except ImportError guard"
                )
    if failures:
        pytest.fail(
            "FIXED_SITES regression — optional-extra import lacks guard:\n  "
            + "\n  ".join(failures)
            + "\n\nPer rules/dependencies.md § Declared = Imported: wrap with "
            "try/except ImportError raising actionable error naming the extra."
        )


@pytest.mark.regression
def test_no_new_unguarded_optional_extra_imports():
    """No file outside (_FIXED_SITES ∪ _KNOWN_VIOLATIONS) may have an unguarded import.

    Catches the regression class: someone adds a new module that imports
    fastapi / aiohttp / aiosqlite at module scope without the try/except
    wrap. The test fails with a clean error pointing to the new violator.
    """
    root = _project_root()
    src = root / "src" / "kailash"
    new_violators: list[str] = []
    for path in _all_python_files(src):
        hits = _enumerate_module_scope_optional_imports(path)
        if not hits:
            continue
        rel = str(path.relative_to(root))
        if rel in _FIXED_SITES or rel in _KNOWN_VIOLATIONS:
            continue
        for package, lineno in hits:
            if _has_module_scope_try_except_import(path, package):
                continue
            new_violators.append(
                f"{rel}:{lineno} imports '{package}' at module scope "
                f"WITHOUT a try/except ImportError guard"
            )
    if new_violators:
        pytest.fail(
            "NEW unguarded optional-extra module-scope import detected:\n  "
            + "\n  ".join(new_violators)
            + "\n\nFix options (per rules/dependencies.md § Declared = Imported):\n"
            "  1. Wrap the import in try/except ImportError raising an "
            "actionable error naming the extra (preferred; see "
            "src/kailash/core/pool/sqlite_pool.py:18-29 as canonical example).\n"
            "  2. Move the import to lazy (inside a function/method) with the "
            "same try/except pattern at the call site.\n"
            "  3. If this is a legitimate new same-class violation you cannot "
            "fix now, add the path to _KNOWN_VIOLATIONS in this test file "
            "AND open a follow-up tracking issue."
        )


@pytest.mark.regression
def test_known_violations_actually_have_violations():
    """Sanity check: every _KNOWN_VIOLATIONS entry has an actual violation.

    If a file in _KNOWN_VIOLATIONS no longer has an unguarded module-scope
    optional-extra import (because it was fixed, refactored, or deleted),
    the entry MUST be removed. Stale allowlist entries hide regressions.
    """
    root = _project_root()
    stale: list[str] = []
    for rel in sorted(_KNOWN_VIOLATIONS):
        path = root / rel
        if not path.exists():
            stale.append(
                f"{rel}: file no longer exists (delete from _KNOWN_VIOLATIONS)"
            )
            continue
        hits = _enumerate_module_scope_optional_imports(path)
        unguarded = [
            (pkg, ln)
            for pkg, ln in hits
            if not _has_module_scope_try_except_import(path, pkg)
        ]
        if not unguarded:
            stale.append(
                f"{rel}: no unguarded optional-extra imports remain "
                f"(MOVE to _FIXED_SITES — fix landed)"
            )
    if stale:
        pytest.fail(
            "Stale _KNOWN_VIOLATIONS entries:\n  "
            + "\n  ".join(stale)
            + "\n\nKnown violations are an allowlist of pre-existing tech "
            "debt — when a violation is fixed, MOVE the entry to "
            "_FIXED_SITES (don't leave it in _KNOWN_VIOLATIONS)."
        )
