#!/usr/bin/env python3
"""Enforce kailash.delegate architectural fences (#1035).

Two fences:

* **Fence A (Apache-2.0 substrate purity):** No module under
  ``src/kailash/delegate/**`` may import ``kailash_rs``,
  ``kailash.commercial``, ``kailash.proprietary``, or any name starting
  with ``_rs_``. Per #1035 acceptance criterion: the package MUST stand
  alone in the OSS SDK with zero proprietary dependency.

* **Fence B (conformance zero-engine-deps):** Modules under
  ``src/kailash/delegate/conformance/**`` may not import any of the
  delegate engine modules (``runtime``, ``dispatch``, ``trust``,
  ``audit``, ``posture``). Conformance loads vectors from JSON via
  dataclasses + stdlib only so it can co-execute with kailash-rs.

Uses ``ast.parse`` rather than regex so import aliases, parenthesized
``from X import (a, b)`` blocks, and multi-line imports all resolve
correctly. Exit 0 = clean; exit 1 = at least one fence violation.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = ROOT / "src" / "kailash" / "delegate"
CONFORMANCE_ROOT = PKG_ROOT / "conformance"

# Fence A — modules NO file under src/kailash/delegate/ may import.
PROPRIETARY_PREFIXES = (
    "kailash_rs",
    "kailash.commercial",
    "kailash.proprietary",
)
PROPRIETARY_LEAF_PREFIX = "_rs_"

# Fence B — engine modules conformance/ may NOT import.
ENGINE_MODULES = frozenset(
    {
        "kailash.delegate.runtime",
        "kailash.delegate.dispatch",
        "kailash.delegate.trust",
        "kailash.delegate.audit",
        "kailash.delegate.posture",
    }
)


def _is_proprietary(module: str) -> bool:
    """True if ``module`` matches a Fence A forbidden prefix."""
    if module.startswith(PROPRIETARY_PREFIXES):
        return True
    # _rs_-prefixed leaf segment (e.g. ``kailash._rs_bridge``).
    return any(part.startswith(PROPRIETARY_LEAF_PREFIX) for part in module.split("."))


def _collect_imports(tree: ast.AST) -> list[tuple[str, int]]:
    """Return ``(module_name, lineno)`` for every import in ``tree``."""
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append((node.module, node.lineno))
    return imports


def _check_file(path: Path) -> list[str]:
    """Return list of violation messages for ``path`` (empty = clean)."""
    rel = path.relative_to(ROOT)
    in_conformance = CONFORMANCE_ROOT in path.parents or path == CONFORMANCE_ROOT
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # surface as fence violation; do not silently skip.
        return [f"{rel}:{exc.lineno}: SyntaxError parsing for fence check: {exc.msg}"]
    violations: list[str] = []
    for module, lineno in _collect_imports(tree):
        if _is_proprietary(module):
            violations.append(
                f"{rel}:{lineno}: Fence A violation — import of proprietary "
                f"module '{module}' (kailash.delegate must stay Apache-2.0 pure)"
            )
        if in_conformance and module in ENGINE_MODULES:
            violations.append(
                f"{rel}:{lineno}: Fence B violation — conformance/ imported engine "
                f"module '{module}' (conformance must remain zero-engine-deps)"
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--check", action="store_true", default=True, help="Default; kept for parity."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="List each scanned file."
    )
    args = parser.parse_args(argv)

    if not PKG_ROOT.is_dir():
        print(
            f"lint-delegate-fences: package root not found: {PKG_ROOT}", file=sys.stderr
        )
        return 1

    files = sorted(PKG_ROOT.rglob("*.py"))
    all_violations: list[str] = []
    for path in files:
        if args.verbose:
            print(f"  scanning {path.relative_to(ROOT)}", file=sys.stderr)
        all_violations.extend(_check_file(path))

    if all_violations:
        print("kailash.delegate fence violations:", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        print(
            f"\n{len(all_violations)} violation(s) across {len(files)} file(s). "
            "See #1035 + tools/lint-delegate-fences.py docstring.",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        print(
            f"lint-delegate-fences: clean ({len(files)} files scanned)", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
