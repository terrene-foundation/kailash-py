#!/usr/bin/env python
"""Resolve every `from X import Y` in shard-authored test files against real source.

Catches the "test asserts against an imagined API" defect class: a regression test
that names a class/function which does not exist passes review as coverage while
exercising nothing. Surfaced in Wave 5 when a shard wrote
`from kaizen.nodes.rag.advanced import SelfCorrectiveRAGNode` — real name is
`SelfCorrectingRAGNode`, and the `_execute_rag` method it called exists nowhere.

Uses AST (no test execution) + importlib (ground truth, not grep).
Run:  .venv/bin/python workspaces/.../verify-shard-symbols.py <file-or-glob>...
Exit: 0 = every symbol resolved; 1 = at least one unresolved.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

# Only these roots are checked; third-party/stdlib imports are out of scope.
IN_SCOPE_ROOTS = (
    "kaizen",
    "dataflow",
    "nexus",
    "kailash",
    "kailash_ml",
    "kailash_align",
)


def module_in_scope(mod: str) -> bool:
    return mod.split(".")[0] in IN_SCOPE_ROOTS


def collect_imports(path: Path) -> list[tuple[int, str, str]]:
    """Return (lineno, module, symbol) for every in-scope `from mod import sym`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if not module_in_scope(node.module):
                continue
            for alias in node.names:
                if alias.name != "*":
                    out.append((node.lineno, node.module, alias.name))
    return out


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv if Path(a).is_file()]
    if not files:
        print("no input files", file=sys.stderr)
        return 2

    failures: list[str] = []
    checked = 0
    for f in files:
        try:
            imports = collect_imports(f)
        except SyntaxError as exc:
            failures.append(f"{f}: SYNTAX ERROR — {exc}")
            continue
        for lineno, mod, sym in imports:
            checked += 1
            try:
                m = importlib.import_module(mod)
            except (
                Exception
            ) as exc:  # ImportError, and anything a module raises at import
                failures.append(
                    f"{f}:{lineno}: MODULE UNRESOLVED `{mod}` — {type(exc).__name__}: {exc}"
                )
                continue
            if not hasattr(m, sym):
                failures.append(
                    f"{f}:{lineno}: SYMBOL UNRESOLVED `{sym}` not in `{mod}`"
                )

    print(f"checked {checked} in-scope symbol import(s) across {len(files)} file(s)")
    if failures:
        print(f"\n{len(failures)} UNRESOLVED:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("all in-scope symbols resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
