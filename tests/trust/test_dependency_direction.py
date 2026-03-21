# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Dependency direction enforcement test (TODO-21).

Verifies that the trust module tree respects its layering:

- Protocol layer (kailash.trust.*, excluding plane/) MUST NOT import from plane/
- Plane layer (kailash.trust.plane.*) MAY import from protocol layer
- No module in kailash.trust MUST import from old paths (eatp, trustplane)
- No module in kailash.trust MUST import from kailash.runtime (prevents circular)
"""

import ast
from pathlib import Path
from typing import List, Tuple

import pytest

_TRUST_SRC = Path(__file__).resolve().parent.parent / "src" / "kailash" / "trust"


def _scan_imports(file_path: Path) -> List[str]:
    """Extract all import module names from a Python file."""
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _get_protocol_files() -> List[Path]:
    """Get all .py files in the protocol layer (trust/, excluding plane/)."""
    return [
        p
        for p in _TRUST_SRC.rglob("*.py")
        if "__pycache__" not in str(p)
        and "plane" not in p.relative_to(_TRUST_SRC).parts
    ]


def _get_all_trust_files() -> List[Path]:
    """Get all .py files in the trust module tree."""
    return [p for p in _TRUST_SRC.rglob("*.py") if "__pycache__" not in str(p)]


class TestDependencyDirection:
    """Verify the trust module tree respects its layering constraints."""

    def test_protocol_layer_does_not_import_from_plane(self):
        """No module in trust/ (excluding plane/) should import from kailash.trust.plane."""
        violations: List[Tuple[str, str]] = []

        for file_path in _get_protocol_files():
            rel = str(file_path.relative_to(_TRUST_SRC))
            for imp in _scan_imports(file_path):
                if "kailash.trust.plane" in imp:
                    violations.append((rel, imp))

        assert not violations, (
            "Protocol layer imports from plane layer (dependency direction violation):\n"
            + "\n".join(f"  - {f}: {imp}" for f, imp in violations)
        )

    def test_no_old_eatp_imports(self):
        """No module should import from the old 'eatp' package."""
        violations: List[Tuple[str, str]] = []

        for file_path in _get_all_trust_files():
            rel = str(file_path.relative_to(_TRUST_SRC))
            for imp in _scan_imports(file_path):
                if imp == "eatp" or imp.startswith("eatp."):
                    violations.append((rel, imp))

        assert not violations, "Old 'eatp' imports found:\n" + "\n".join(
            f"  - {f}: {imp}" for f, imp in violations
        )

    def test_no_old_trustplane_imports(self):
        """No module should import from the old 'trustplane' package."""
        violations: List[Tuple[str, str]] = []

        for file_path in _get_all_trust_files():
            rel = str(file_path.relative_to(_TRUST_SRC))
            for imp in _scan_imports(file_path):
                if imp == "trustplane" or imp.startswith("trustplane."):
                    violations.append((rel, imp))

        assert not violations, "Old 'trustplane' imports found:\n" + "\n".join(
            f"  - {f}: {imp}" for f, imp in violations
        )

    def test_no_runtime_imports(self):
        """Trust modules must not import from kailash.runtime (prevents circular)."""
        violations: List[Tuple[str, str]] = []

        for file_path in _get_all_trust_files():
            rel = str(file_path.relative_to(_TRUST_SRC))
            for imp in _scan_imports(file_path):
                if imp.startswith("kailash.runtime"):
                    violations.append((rel, imp))

        assert not violations, (
            "Trust modules import from kailash.runtime (circular dependency risk):\n"
            + "\n".join(f"  - {f}: {imp}" for f, imp in violations)
        )
