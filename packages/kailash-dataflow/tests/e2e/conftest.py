"""
Configuration for end-to-end (Tier 3) tests.

NO MOCKING POLICY: All e2e tests must use real infrastructure.

This conftest enforces the policy at test collection time by scanning
every test module under ``tests/e2e/`` for imports of ``unittest.mock``
and refusing to collect the module if found. Tests that need mocks
MUST live under ``tests/unit/``.
"""

import ast
from pathlib import Path

import pytest


_E2E_DIR = Path(__file__).parent.resolve()


def _module_imports_unittest_mock(path: Path) -> bool:
    """Return True if ``path`` imports ``unittest.mock`` or names from it.

    Uses AST parsing so comments / docstrings that mention the string
    ``unittest.mock`` do not trigger false positives.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return False
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("unittest.mock"):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name and alias.name.startswith("unittest.mock"):
                    return True
    return False


def pytest_collectstart(collector):
    """Abort collection for e2e tests that import ``unittest.mock``.

    Fires before any test in an e2e module runs; ``pytest.fail`` inside
    ``pytest_collectstart`` raises a collection error that surfaces
    immediately with a clear, actionable message.
    """
    path = getattr(collector, "path", None)
    if path is None:
        return
    try:
        resolved = Path(path).resolve()
    except Exception:
        return
    if resolved.suffix != ".py":
        return
    if _E2E_DIR not in resolved.parents and resolved != _E2E_DIR:
        return
    if _module_imports_unittest_mock(resolved):
        pytest.fail(
            f"NO MOCKING POLICY VIOLATION (Tier 3): {resolved.relative_to(_E2E_DIR.parent)} "
            f"imports unittest.mock. E2E tests must use real "
            f"infrastructure. Move mock-based tests to tests/unit/ or rewrite "
            f"against real backends (see rules/testing.md § Tier 3).",
            pytrace=False,
        )


@pytest.fixture(scope="function", autouse=True)
def no_mocking_policy_e2e():
    """Autouse policy fixture for every Tier 3 e2e test.

    Complements the ``pytest_collectstart`` AST gate above — catches
    unexpected runtime unittest.mock bindings that bypass the module-
    level import check.
    """
    import sys as _sys

    mock_mod = _sys.modules.get("unittest.mock")
    if mock_mod is not None:
        _ = mock_mod.Mock  # reference to prevent tree-shaking
    yield
