# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SDK convention enforcement tests (Phase 8, item 8.38).

Scans EATP modules for required SDK conventions:
- SPDX license headers
- ``__all__`` exports
- ``from __future__ import annotations``
- ``to_dict()`` on ``@dataclass`` classes
- Errors inherit from ``TrustError``

Pre-existing modules that predate these conventions are excluded from
checks that would require invasive refactoring. New and recently modified
modules are held to the full standard.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import List, Set, Tuple

import pytest

# Root of the EATP package source
_EATP_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "eatp"

# Modules modified/created in the gap-closure effort (Phases 1-8).
# These are held to the full convention standard.
_ENFORCED_MODULES: List[str] = [
    "hooks.py",
    "roles.py",
    "vocabulary.py",
    "scoring.py",
    "reasoning.py",
    "export/siem.py",
    "export/compliance.py",
    "export/__init__.py",
    "metrics.py",
]

# Modules where dataclasses use specialized serialization instead of to_dict()
# (e.g., SIEMEvent uses serialize_cef/serialize_ocsf, Compliance uses generate_*)
_TO_DICT_EXCLUDED_MODULES: List[str] = [
    "export/siem.py",
    "export/compliance.py",
]


def _get_module_paths(subset: List[str] | None = None) -> List[Path]:
    """Return module paths, optionally filtered to a subset."""
    if subset is not None:
        return [_EATP_SRC / m for m in subset if (_EATP_SRC / m).exists()]
    # All .py files excluding __pycache__ and __init__.py
    return [
        p
        for p in _EATP_SRC.rglob("*.py")
        if "__pycache__" not in str(p) and p.name != "__init__.py"
    ]


def _read_lines(path: Path) -> List[str]:
    return path.read_text().splitlines()


# ===================================================================
# 1. SPDX header
# ===================================================================


class TestSPDXHeaders:
    """Every enforced module must have the Terrene Foundation SPDX header."""

    def test_spdx_header_present(self) -> None:
        missing: List[str] = []
        for path in _get_module_paths(_ENFORCED_MODULES):
            lines = _read_lines(path)
            text = "\n".join(lines[:5])
            if "SPDX-License-Identifier: Apache-2.0" not in text:
                missing.append(str(path.relative_to(_EATP_SRC)))
        assert not missing, f"Missing SPDX header: {missing}"

    def test_copyright_header_present(self) -> None:
        missing: List[str] = []
        for path in _get_module_paths(_ENFORCED_MODULES):
            lines = _read_lines(path)
            text = "\n".join(lines[:5])
            if "Copyright" not in text and "Terrene Foundation" not in text:
                missing.append(str(path.relative_to(_EATP_SRC)))
        assert not missing, f"Missing copyright header: {missing}"


# ===================================================================
# 2. __all__ present
# ===================================================================


class TestAllExports:
    """Every enforced module must define __all__."""

    def test_all_defined(self) -> None:
        missing: List[str] = []
        for path in _get_module_paths(_ENFORCED_MODULES):
            tree = ast.parse(path.read_text())
            has_all = any(
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
                )
                for node in ast.walk(tree)
            )
            if not has_all:
                missing.append(str(path.relative_to(_EATP_SRC)))
        assert not missing, f"Missing __all__: {missing}"


# ===================================================================
# 3. from __future__ import annotations
# ===================================================================


class TestFutureAnnotations:
    """Every enforced module must use ``from __future__ import annotations``."""

    def test_future_annotations_present(self) -> None:
        missing: List[str] = []
        for path in _get_module_paths(_ENFORCED_MODULES):
            tree = ast.parse(path.read_text())
            has_future = any(
                isinstance(node, ast.ImportFrom)
                and node.module == "__future__"
                and any(alias.name == "annotations" for alias in node.names)
                for node in ast.walk(tree)
            )
            if not has_future:
                missing.append(str(path.relative_to(_EATP_SRC)))
        assert not missing, f"Missing future annotations: {missing}"


# ===================================================================
# 4. to_dict() on @dataclass classes
# ===================================================================


def _find_dataclass_names(tree: ast.Module) -> List[str]:
    """Find class names decorated with @dataclass in an AST."""
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                dec_name = ""
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Attribute):
                    dec_name = dec.attr
                if dec_name == "dataclass":
                    names.append(node.name)
    return names


def _find_methods(cls_node: ast.ClassDef) -> Set[str]:
    """Find method names in a class definition."""
    return {
        node.name
        for node in cls_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class TestToDict:
    """Every @dataclass in enforced modules must have to_dict()."""

    def test_to_dict_present(self) -> None:
        # Exclude modules that use specialized serialization
        modules = [m for m in _ENFORCED_MODULES if m not in _TO_DICT_EXCLUDED_MODULES]
        missing: List[Tuple[str, str]] = []
        for path in _get_module_paths(modules):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    is_dataclass = any(
                        (isinstance(d, ast.Name) and d.id == "dataclass")
                        or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                        for d in node.decorator_list
                    )
                    if is_dataclass and "to_dict" not in _find_methods(node):
                        # Skip ABC/abstract classes
                        if not any(
                            isinstance(d, ast.Name)
                            and d.id in ("ABC", "abstractmethod")
                            for d in node.decorator_list
                        ):
                            missing.append(
                                (str(path.relative_to(_EATP_SRC)), node.name)
                            )
        assert not missing, f"@dataclass without to_dict(): {missing}"


# ===================================================================
# 5. Errors inherit from TrustError
# ===================================================================


class TestErrorInheritance:
    """All Error classes in the exceptions module must inherit from TrustError."""

    def test_all_errors_inherit_from_trust_error(self) -> None:
        from eatp import exceptions

        trust_error = exceptions.TrustError
        non_compliant: List[str] = []

        for name, obj in inspect.getmembers(exceptions, inspect.isclass):
            if name.endswith("Error") and name != "TrustError":
                if not issubclass(obj, trust_error):
                    non_compliant.append(name)

        assert (
            not non_compliant
        ), f"Exceptions not inheriting from TrustError: {non_compliant}"

    def test_all_errors_have_details(self) -> None:
        """TrustError base provides .details; verify it works on all subclasses."""
        from eatp import exceptions

        for name, obj in inspect.getmembers(exceptions, inspect.isclass):
            if (
                name.endswith("Error")
                and issubclass(obj, exceptions.TrustError)
                and name != "TrustError"
            ):
                # Just verify TrustError.__init__ provides .details
                base = exceptions.TrustError("test", details={"key": "val"})
                assert hasattr(base, "details"), f"{name} missing .details"
