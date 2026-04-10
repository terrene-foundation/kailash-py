#!/usr/bin/env python3
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Extract public API surface of a Python package via ast.

Emits one symbol per line: module_path::symbol_type::qualified_name(signature)
Types: class, enum, enum_variant, function, method, constant, protocol, class_const
Skips private symbols (_prefix), __pycache__, _internal/, test files.
Usage: python3 scripts/extract-api-surface.py src/kailash/
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Optional

_EXCLUDED_DIRS = {"__pycache__", "_internal", ".git", ".venv", "node_modules"}


def _is_test_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.py")
        or name.endswith(".spec.py")
        or "/__tests__/" in str(path)
        or "/tests/" in str(path)
    )


def _has_parity_skip(node: ast.AST) -> Optional[str]:
    doc = ast.get_docstring(node, clean=False)
    if not doc:
        return None
    for line in doc.splitlines():
        s = line.strip()
        if s.startswith("# parity-skip:") or s.startswith("parity-skip:"):
            return s.split(":", 1)[1].strip() if ":" in s else ""
    return None


def _fmt_ann(node: Optional[ast.expr]) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        v = _fmt_ann(node.value)
        return f"{v}.{node.attr}" if v else node.attr
    if isinstance(node, ast.Subscript):
        return f"{_fmt_ann(node.value)}[{_fmt_ann(node.slice)}]"
    if isinstance(node, ast.Tuple):
        return ", ".join(_fmt_ann(e) for e in node.elts)
    if isinstance(node, ast.List):
        return f"[{', '.join(_fmt_ann(e) for e in node.elts)}]"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{_fmt_ann(node.left)} | {_fmt_ann(node.right)}"
    if isinstance(node, ast.Starred):
        return f"*{_fmt_ann(node.value)}"
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return "..."


def _fmt_param(arg: ast.arg) -> str:
    ann = _fmt_ann(arg.annotation)
    return f"{arg.arg}: {ann}" if ann else arg.arg


def _fmt_sig(
    func: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool = False
) -> str:
    params: list[str] = []
    a = func.args
    posonlyargs = getattr(a, "posonlyargs", [])
    all_pos = list(posonlyargs) + list(a.args)
    start = 0
    if is_method and all_pos and all_pos[0].arg in ("self", "cls"):
        start = 1
    n_args, n_defs = len(all_pos), len(a.defaults)
    def_off = n_args - n_defs

    for i, arg in enumerate(all_pos):
        if i < start:
            continue
        p = _fmt_param(arg)
        di = i - def_off
        if 0 <= di < n_defs:
            try:
                p += f" = {ast.unparse(a.defaults[di])}"
            except (AttributeError, ValueError):
                p += " = ..."
        params.append(p)

    if posonlyargs and start < len(posonlyargs):
        pos = len(posonlyargs) - start
        if 0 < pos <= len(params):
            params.insert(pos, "/")

    if a.vararg:
        params.append(f"*{_fmt_param(a.vararg)}")
    elif a.kwonlyargs:
        params.append("*")

    for i, kw in enumerate(a.kwonlyargs):
        p = _fmt_param(kw)
        if i < len(a.kw_defaults) and a.kw_defaults[i] is not None:
            try:
                p += f" = {ast.unparse(a.kw_defaults[i])}"
            except (AttributeError, ValueError):
                p += " = ..."
        params.append(p)

    if a.kwarg:
        params.append(f"**{_fmt_param(a.kwarg)}")

    sig = ", ".join(params)
    ret = _fmt_ann(func.returns)
    return f"({sig}) -> {ret}" if ret else f"({sig})"


def _is_enum(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = _fmt_ann(base)
        if name in ("Enum", "str, Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"):
            return True
        if "Enum" in name:
            return True
    return False


def _is_protocol(node: ast.ClassDef) -> bool:
    return any("Protocol" in _fmt_ann(b) for b in node.bases)


def _enum_variants(node: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for item in node.body:
        if isinstance(item, ast.Assign):
            for t in item.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    out.append(t.id)
        elif isinstance(item, ast.AnnAssign) and item.value is not None:
            if isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
                out.append(item.target.id)
    return out


def _const_info(node: ast.AST) -> Optional[tuple[str, str]]:
    if isinstance(node, ast.Assign):
        t = node.targets[0] if node.targets else None
        if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_"):
            return (t.id, "")
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if node.target.id.isupper() and not node.target.id.startswith("_"):
            return (node.target.id, _fmt_ann(node.annotation))
    return None


def _extract_all(tree: ast.Module) -> Optional[set[str]]:
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (
                isinstance(t, ast.Name)
                and t.id == "__all__"
                and isinstance(node.value, ast.List)
            ):
                return {
                    e.value
                    for e in node.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
    return None


def _extract_module(
    tree: ast.Module, mod: str, all_names: Optional[set[str]]
) -> list[str]:
    symbols: list[str] = []

    def ok(name: str) -> bool:
        if name.startswith("_"):
            return False
        return name in all_names if all_names is not None else True

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cn = node.name
            if not ok(cn):
                continue
            skip = _has_parity_skip(node)
            sfx = f"  # parity-skip: {skip}" if skip else ""
            enum = _is_enum(node)

            if enum:
                symbols.append(f"{mod}::enum::{cn}{sfx}")
                for v in _enum_variants(node):
                    symbols.append(f"{mod}::enum_variant::{cn}.{v}{sfx}")
            elif _is_protocol(node):
                symbols.append(f"{mod}::protocol::{cn}{sfx}")
            else:
                symbols.append(f"{mod}::class::{cn}{sfx}")

            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mn = item.name
                    if mn.startswith("_"):
                        continue
                    if mn.startswith("__") and mn.endswith("__"):
                        continue
                    ms = _has_parity_skip(item)
                    msfx = f"  # parity-skip: {ms}" if ms else sfx
                    pre = "async " if isinstance(item, ast.AsyncFunctionDef) else ""
                    symbols.append(
                        f"{mod}::method::{cn}.{pre}{mn}{_fmt_sig(item, True)}{msfx}"
                    )
                elif not enum and isinstance(item, ast.Assign):
                    for t in item.targets:
                        if (
                            isinstance(t, ast.Name)
                            and t.id.isupper()
                            and not t.id.startswith("_")
                        ):
                            symbols.append(f"{mod}::class_const::{cn}.{t.id}{sfx}")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
            if not ok(fn):
                continue
            skip = _has_parity_skip(node)
            sfx = f"  # parity-skip: {skip}" if skip else ""
            pre = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            symbols.append(f"{mod}::function::{pre}{fn}{_fmt_sig(node)}{sfx}")

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            info = _const_info(node)
            if info and ok(info[0]):
                name, ann = info
                t = f": {ann}" if ann else ""
                symbols.append(f"{mod}::constant::{name}{t}")

    return symbols


def _path_to_module(fp: Path, base: Path) -> str:
    parts = list(fp.relative_to(base).parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def extract_api_surface(src_root: str) -> list[str]:
    root = Path(src_root).resolve()
    module_base = root.parent if (root / "__init__.py").exists() else root
    all_symbols: list[str] = []

    for dirpath_str, dirnames, filenames in os.walk(str(root)):
        dirpath = Path(dirpath_str)
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDED_DIRS and not d.startswith(".")
        ]

        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            if fn.startswith("_") and fn != "__init__.py":
                continue
            fp = dirpath / fn
            if any(p in _EXCLUDED_DIRS for p in fp.parts):
                continue
            if _is_test_file(fp):
                continue
            mod = _path_to_module(fp, module_base)
            if not mod:
                continue
            try:
                src = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                print(f"# WARNING: could not read {fp}", file=sys.stderr)
                continue
            try:
                tree = ast.parse(src, filename=str(fp))
            except SyntaxError as e:
                print(f"# WARNING: syntax error in {fp}: {e}", file=sys.stderr)
                continue
            all_symbols.extend(_extract_module(tree, mod, _extract_all(tree)))

    all_symbols.sort()
    return all_symbols


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <src_root>", file=sys.stderr)
        sys.exit(1)
    src_root = sys.argv[1]
    if not Path(src_root).is_dir():
        print(f"Error: {src_root} is not a directory", file=sys.stderr)
        sys.exit(1)
    symbols = extract_api_surface(src_root)
    for s in symbols:
        print(s)
    print(f"# Total public symbols: {len(symbols)}", file=sys.stderr)


if __name__ == "__main__":
    main()
