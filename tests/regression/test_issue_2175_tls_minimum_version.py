# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2175 -- unpinned TLS floor (CodeQL 6180).

``ssl.create_default_context()`` currently defaults to TLS 1.2 on CPython, so a
runtime assertion such as ``ctx.minimum_version == TLSVersion.TLSv1_2`` passes
whether or not the code pins anything -- it is a non-discriminating instrument
(``instrument-discipline.md`` MUST-1). The defect is precisely that the floor is
inherited from the interpreter rather than stated by the code, so the pin has to
be asserted against the SOURCE.

Measured before the fix, with a control (``instrument-discipline.md`` MUST-3):
the same scanner reported ``trust/plane/siem.py`` as already pinned while
reporting three unpinned sites, so it discriminates on this tree.

The repo-wide sweep is the important test: it fails on any NEW
``create_default_context()`` introduced without a floor, which is what the issue
asked for ("fix them in the same change rather than one at a time").
"""

from __future__ import annotations

import ast
import ssl
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every module that constructs an SSL context in shipped (non-test) source.
PINNED_SITES = [
    "src/kailash/nodes/api/security.py",
    "src/kailash/trust/plane/identity.py",
    "src/kailash/trust/plane/siem.py",
    "packages/kailash-dataflow/src/dataflow/adapters/postgresql.py",
]


def _shipped_source_files() -> list[Path]:
    """Every shipped (non-test) Python file: src/ plus packages/*/src."""
    files = list((REPO_ROOT / "src").rglob("*.py"))
    for package in sorted((REPO_ROOT / "packages").glob("*")):
        src = package / "src"
        if src.is_dir():
            files.extend(src.rglob("*.py"))
    return files


class _SSLContextVisitor(ast.NodeVisitor):
    """Collects (function, context-variable) pairs and minimum_version pins."""

    def __init__(self) -> None:
        self.constructions: list[tuple[str, int]] = []
        self.pins: set[str] = set()
        self._scope = "<module>"

    def _visit_scope(self, node):
        previous, self._scope = self._scope, node.name
        self.generic_visit(node)
        self._scope = previous

    visit_FunctionDef = _visit_scope
    visit_AsyncFunctionDef = _visit_scope

    def visit_Assign(self, node: ast.Assign) -> None:
        target = node.targets[0] if len(node.targets) == 1 else None

        # `ctx = ssl.create_default_context()` / `ssl.SSLContext(...)`
        call = node.value
        if isinstance(call, ast.Call):
            func = call.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name in {"create_default_context", "SSLContext"} and isinstance(
                target, ast.Name
            ):
                self.constructions.append((f"{self._scope}:{target.id}", node.lineno))

        # `ctx.minimum_version = ...`
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "minimum_version"
            and isinstance(target.value, ast.Name)
        ):
            self.pins.add(f"{self._scope}:{target.value.id}")

        self.generic_visit(node)


def _unpinned_contexts(path: Path) -> list[str]:
    visitor = _SSLContextVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return [
        f"{path.relative_to(REPO_ROOT)}:{line} ({key})"
        for key, line in visitor.constructions
        if key not in visitor.pins
    ]


def test_control_scanner_detects_an_unpinned_context():
    """The scanner must be able to return the OPPOSITE verdict.

    Without this control an empty finding list is indistinguishable from a
    scanner that never fires (``instrument-discipline.md`` MUST-3).
    """
    unpinned = ast.parse(
        "import ssl\ndef f():\n    ctx = ssl.create_default_context()\n"
    )
    visitor = _SSLContextVisitor()
    visitor.visit(unpinned)
    assert visitor.constructions and not visitor.pins

    pinned = ast.parse(
        "import ssl\n"
        "def f():\n"
        "    ctx = ssl.create_default_context()\n"
        "    ctx.minimum_version = ssl.TLSVersion.TLSv1_2\n"
    )
    visitor = _SSLContextVisitor()
    visitor.visit(pinned)
    assert visitor.constructions and visitor.pins


@pytest.mark.parametrize("relative_path", PINNED_SITES)
def test_known_ssl_sites_pin_a_tls_floor(relative_path):
    path = REPO_ROOT / relative_path
    assert path.exists(), f"site moved: {relative_path}"
    assert _unpinned_contexts(path) == []


@pytest.mark.parametrize("relative_path", PINNED_SITES)
def test_known_ssl_sites_pin_tls_1_2_specifically(relative_path):
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "ssl.TLSVersion.TLSv1_2" in source


def test_no_shipped_ssl_context_is_left_without_a_floor():
    """Repo-wide sweep -- the multi-site half of #2175's acceptance criteria."""
    findings: list[str] = []
    for path in _shipped_source_files():
        findings.extend(_unpinned_contexts(path))
    assert findings == [], (
        "SSL/TLS context(s) constructed without an explicit minimum_version. "
        "Set `.minimum_version = ssl.TLSVersion.TLSv1_2` at each site:\n  "
        + "\n  ".join(findings)
    )


def test_pinned_floor_is_reachable_at_runtime():
    """Complements the source pins: the attribute is settable and takes.

    This alone would NOT discriminate (the default is already TLS 1.2 here), so
    it is scoped to proving the pinned value is a valid, effective assignment.
    """
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
