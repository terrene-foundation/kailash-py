#!/usr/bin/env python3
"""Import-execution sweep over doc + skill code fences (issue #643 / F32).

Documentation and skill examples are deliverables nobody runs: unit/integration
tests exercise the real API, but prose ``python`` fences are never imported, so a
phantom method name (``fs.ingest()``), a phantom constructor kwarg
(``FeatureSchema(entity_key=...)``), or a stale import path silently rots across
README, guides, and synced ``.claude/skills`` examples. The #643 cutover surfaced
exactly this: three artifact surfaces taught a *fictional* FeatureStore API that
matched no shipped code (see
``workspaces/issue-643-featurestore-canonical/journal/0005-DISCOVERY-...``).

This sweep is the mechanical defense the discovery journal proposed: it parses
every ``python`` fence in the target docs, statically resolves each symbol
imported from a tracked package against the *actually installed* module, and
asserts that

* every import resolves (no stale module path),
* every method called on a resolved class instance exists (``hasattr``),
* every keyword passed to a resolved class constructor is a real parameter
  (``inspect.signature``).

It uses ``ast`` (not regex) so aliased imports, parenthesised ``from X import
(a, b)`` blocks, and ``await`` expressions all resolve. It is **advisory** — wire
it into ``/redteam`` as a gate, not into ``/sync`` as a blocker (journal/0005
§"For Discussion" #3 disposition): a doc whose example calls a non-existent
method should fail review, but distribution is gated by the human at Gate-1.

Exit 0 = clean; exit 1 = at least one phantom-API finding.

Usage::

    python tools/check_doc_api_examples.py                 # default doc surface
    python tools/check_doc_api_examples.py --json          # machine-readable
    python tools/check_doc_api_examples.py path/to/file.md  # explicit targets
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Packages whose symbols are resolved against the installed code. A fence import
# from any other package (stdlib, third-party, sibling SDKs) is left untouched —
# the sweep only adjudicates the API surface it can authoritatively resolve.
TRACKED_PREFIXES = ("kailash_ml",)

# Default doc surface: every place a kailash_ml API example can rot.
DEFAULT_TARGETS = (
    ".claude/skills",
    "packages/kailash-ml/README.md",
    "packages/kailash-ml/docs",
    "packages/kailash-ml/MIGRATION.md",
)

FENCE_RE = re.compile(r"^```(?P<lang>[a-zA-Z0-9_+-]*)\s*$")

# Auditable per-fence opt-out. A fence whose body contains this literal is skipped
# — for migration "before/0.x" or "3.0 future" examples that depict deliberately
# non-current API, and intentional DO-NOT counter-examples. The marker is visible
# in the rendered doc + greppable, so /redteam can audit every opt-out + its reason.
IGNORE_MARKER = "doc-sweep: ignore"


@dataclass
class Finding:
    path: str
    line: int  # 1-based line in the source file
    kind: str  # "import" | "method" | "kwarg"
    symbol: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.kind}] {self.symbol} — {self.detail}"


@dataclass
class Fence:
    lang: str
    start_line: int  # 1-based line of the first code line inside the fence
    body: str


@dataclass
class _Resolution:
    findings: list[Finding] = field(default_factory=list)


def _iter_python_fences(text: str) -> list[Fence]:
    """Extract ``python`` (and ``py``) fenced blocks with source line numbers."""
    fences: list[Fence] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lang = m.group("lang").lower()
        body_start = i + 1
        j = body_start
        while j < len(lines) and not lines[j].startswith("```"):
            j += 1
        if lang in ("python", "py"):
            body = "\n".join(lines[body_start:j])
            if IGNORE_MARKER not in body:
                fences.append(
                    Fence(
                        lang=lang,
                        start_line=body_start + 1,  # 1-based
                        body=body,
                    )
                )
        i = j + 1
    return fences


def _parse_fence(body: str) -> ast.Module | None:
    """Parse a fence body, tolerating top-level ``await``.

    Fences routinely use ``await store.get_features(...)`` at module scope, which
    is a ``SyntaxError`` for ``ast.parse``. Wrapping the body in an ``async def``
    makes those legal while preserving line numbers via ``ast.increment_lineno``
    offset bookkeeping (handled by the caller through ``_LINE_OFFSET``).
    """
    # Try bare parse first (cheapest; keeps line numbers exact).
    try:
        return ast.parse(body)
    except SyntaxError:
        pass
    # Wrap in an async function so top-level await parses. Indent every line.
    indented = "\n".join("    " + ln for ln in body.splitlines())
    wrapped = "async def __sweep_wrapper__():\n" + (indented or "    pass")
    try:
        mod = ast.parse(wrapped)
    except SyntaxError:
        return None
    # Unwrap: the single FunctionDef's body becomes the module body, with line
    # numbers shifted by 1 (the inserted wrapper line). Caller compensates.
    fn = mod.body[0]
    assert isinstance(fn, ast.AsyncFunctionDef)
    inner = ast.Module(body=fn.body, type_ignores=[])
    # Shift line numbers back up by 1 to undo the wrapper line.
    for node in ast.walk(inner):
        lineno = getattr(node, "lineno", None)
        if lineno is not None:
            setattr(node, "lineno", lineno - 1)
    return inner


def _tracked(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in TRACKED_PREFIXES)


def _resolve_import(module: str, attr: str | None):
    """Import ``module`` and (optionally) getattr ``attr``; return obj or raise."""
    mod = importlib.import_module(module)
    if attr is None:
        return mod
    return getattr(mod, attr)


def _check_fence(
    fence: Fence,
    src_path: str,
    res: _Resolution,
    name_to_obj: dict[str, object],
    var_to_class: dict[str, type],
) -> None:
    """Validate one fence. ``name_to_obj`` / ``var_to_class`` are FILE-scoped and
    persist across fences in the same file, so a var bound in one fence (``store =
    FeatureStore(...)``) is still resolvable when a later fence calls
    ``store.get_features(...)`` — the cross-fence pattern docs routinely use."""
    tree = _parse_fence(fence.body)
    if tree is None:
        return  # placeholder-heavy fence we cannot parse; not a finding

    def srcline(node: ast.AST) -> int:
        return fence.start_line + (getattr(node, "lineno", 1) - 1)

    def _allowed_kw_params(sig: inspect.Signature) -> set[str] | None:
        """Param names acceptable as keywords, or None if **kwargs accepts any."""
        if any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            return None
        return {
            n
            for n, p in sig.parameters.items()
            if p.kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }

    def _validate_ctor_kwargs(cls: type, call: ast.Call, label: str) -> None:
        try:
            sig = inspect.signature(cls)
        except (ValueError, TypeError):
            return
        allowed = _allowed_kw_params(sig)
        if allowed is None:
            return  # **kwargs accepts anything
        for kw in call.keywords:
            if kw.arg is None:  # **expansion
                continue
            if kw.arg not in allowed:
                res.findings.append(
                    Finding(
                        src_path,
                        srcline(call),
                        "kwarg",
                        f"{label}(...{kw.arg}=...)",
                        f"not a parameter of {cls.__module__}.{cls.__qualname__}"
                        f" (real: {', '.join(sorted(allowed))})",
                    )
                )

    def _validate_method_kwargs(
        cls: type, method: str, call: ast.Call, label: str
    ) -> None:
        """Validate kwargs of a ``var.method(...)`` call against the bound method's
        real signature (``self`` excluded). Skips when the method has **kwargs."""
        fn = getattr(cls, method, None)
        if fn is None or not callable(fn):
            return
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            return
        allowed = _allowed_kw_params(sig)
        if allowed is None:
            return
        allowed.discard("self")
        for kw in call.keywords:
            if kw.arg is None:
                continue
            if kw.arg not in allowed:
                res.findings.append(
                    Finding(
                        src_path,
                        srcline(call),
                        "method-kwarg",
                        f"{label}.{method}(...{kw.arg}=...)",
                        f"not a parameter of {cls.__module__}.{cls.__qualname__}"
                        f".{method} (real: {', '.join(sorted(allowed))})",
                    )
                )

    def _validate_calls_in(node: ast.AST) -> None:
        """Validate every Call under ``node`` against the CURRENT bindings."""
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if isinstance(func, ast.Name) and func.id in name_to_obj:
                obj = name_to_obj[func.id]
                if isinstance(obj, type):
                    _validate_ctor_kwargs(obj, sub, func.id)
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                cls = var_to_class.get(func.value.id)
                if cls is None:
                    continue
                if not hasattr(cls, func.attr):
                    public = [m for m in dir(cls) if not m.startswith("_")]
                    res.findings.append(
                        Finding(
                            src_path,
                            srcline(sub),
                            "method",
                            f"{func.value.id}.{func.attr}()",
                            f"no such method on {cls.__module__}.{cls.__qualname__}"
                            f" (real: {', '.join(public)})",
                        )
                    )
                else:
                    _validate_method_kwargs(cls, func.attr, sub, func.value.id)

    def _apply_imports(node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not _tracked(module):
                return
            for alias in node.names:
                if alias.name == "*":
                    continue
                bind = alias.asname or alias.name
                try:
                    name_to_obj[bind] = _resolve_import(module, alias.name)
                except (ImportError, AttributeError) as exc:
                    res.findings.append(
                        Finding(
                            src_path,
                            srcline(node),
                            "import",
                            f"{module}.{alias.name}",
                            f"does not resolve against installed code ({exc.__class__.__name__})",
                        )
                    )
        else:  # ast.Import
            for alias in node.names:
                if not _tracked(alias.name):
                    continue
                bind = alias.asname or alias.name.split(".")[0]
                try:
                    name_to_obj[bind] = _resolve_import(alias.name, None)
                except ImportError as exc:
                    res.findings.append(
                        Finding(
                            src_path,
                            srcline(node),
                            "import",
                            alias.name,
                            f"module does not import ({exc.__class__.__name__})",
                        )
                    )

    def _bind_assign(node: ast.Assign) -> None:
        if not isinstance(node.value, ast.Call):
            return
        func = node.value.func
        bound_cls: type | None = None
        if isinstance(func, ast.Name) and isinstance(name_to_obj.get(func.id), type):
            bound_cls = name_to_obj[func.id]  # type: ignore[assignment]
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name):
                continue
            if bound_cls is not None:
                var_to_class[tgt.id] = bound_cls
            else:
                # Rebound to an unknown/non-tracked-class call → drop any stale
                # binding so a later var.method() is not checked against the wrong
                # class (cross-fence state persistence makes this matter).
                var_to_class.pop(tgt.id, None)

    def visit(stmts: list[ast.stmt]) -> None:
        """Process statements in SOURCE ORDER so within-fence rebinding (e.g. a
        migration before/after fence that imports both the legacy and canonical
        FeatureStore) resolves each use against the binding active at its line —
        not whichever import ``ast.walk`` happened to process last."""
        for stmt in stmts:
            # 1. Validate calls in this statement against bindings from PRIOR ones.
            _validate_calls_in(stmt)
            # 2. Apply this statement's binding effects for subsequent statements.
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                _apply_imports(stmt)
            elif isinstance(stmt, ast.Assign):
                _bind_assign(stmt)
            # 3. Recurse into compound-statement bodies in order.
            for fieldname in ("body", "orelse", "finalbody"):
                inner = getattr(stmt, fieldname, None)
                if isinstance(inner, list) and inner and isinstance(inner[0], ast.stmt):
                    visit(inner)  # type: ignore[arg-type]

    visit(tree.body)


def _collect_targets(raw: list[str]) -> list[Path]:
    targets = raw or list(DEFAULT_TARGETS)
    files: list[Path] = []
    for t in targets:
        p = (ROOT / t) if not Path(t).is_absolute() else Path(t)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file() and p.suffix == ".md":
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "targets", nargs="*", help="md files or dirs (default: doc surface)"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    res = _Resolution()
    files = _collect_targets(args.targets)
    for f in files:
        rel = str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f)
        # File-scoped binding state: a var bound in one fence stays resolvable in
        # later fences of the SAME file (reset per file).
        name_to_obj: dict[str, object] = {}
        var_to_class: dict[str, type] = {}
        for fence in _iter_python_fences(f.read_text(encoding="utf-8")):
            _check_fence(fence, rel, res, name_to_obj, var_to_class)

    if args.json:
        print(
            json.dumps(
                {
                    "files_scanned": len(files),
                    "findings": [f.__dict__ for f in res.findings],
                },
                indent=2,
            )
        )
    else:
        if res.findings:
            print(f"phantom-API findings ({len(res.findings)}):\n")
            for f in sorted(res.findings, key=lambda x: (x.path, x.line)):
                print("  " + f.render())
        else:
            print(f"clean — {len(files)} doc files scanned, 0 phantom-API findings")

    return 1 if res.findings else 0


if __name__ == "__main__":
    sys.exit(main())
