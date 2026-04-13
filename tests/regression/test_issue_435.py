# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #435 — kailash-mcp bin script references wrong module path.

The root kailash package defined a conflicting ``kailash-mcp`` console script
entry point that pointed at the deprecated ``kailash.mcp.platform_server``
shim path. When both packages were installed, the root package's entry point
overwrote the correct one from the kailash-mcp sub-package, making the CLI
unusable with ``ModuleNotFoundError``.

Fixed by removing the conflicting entry point from the root pyproject.toml
and deleting the deprecated ``kailash.mcp`` shim entirely.
"""

from __future__ import annotations

import pytest


@pytest.mark.regression
class TestIssue435:
    """kailash-mcp entry point must resolve to kailash_mcp, not kailash.mcp."""

    def test_platform_server_importable_from_canonical_path(self) -> None:
        """The canonical kailash_mcp.platform_server module is importable."""
        from kailash_mcp.platform_server import main

        assert callable(main)

    def test_no_kailash_dot_mcp_module(self) -> None:
        """The deprecated kailash.mcp shim must not exist as a package."""
        import importlib.util

        spec = importlib.util.find_spec("kailash.mcp")
        assert spec is None, (
            "kailash.mcp still exists as a module — the deprecated shim "
            "was not removed. This causes the bin/kailash-mcp script to "
            "reference the wrong import path."
        )

    def test_root_pyproject_no_kailash_mcp_script(self) -> None:
        """Root pyproject.toml must NOT define a kailash-mcp console script."""
        from pathlib import Path

        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        scripts = data.get("project", {}).get("scripts", {})
        assert "kailash-mcp" not in scripts, (
            "Root pyproject.toml still defines a kailash-mcp script entry "
            "point. This conflicts with the entry point in the kailash-mcp "
            "sub-package and causes the wrong module path in bin/kailash-mcp."
        )
