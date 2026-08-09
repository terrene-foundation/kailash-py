#!/usr/bin/env python
"""AST sweep: exception handlers that surface a raw exception on a provider path.

Closes the H4 gap from the round-2 redteam: the #1970 sweep was verified by SEVEN
HAND-PICKED test shapes, so its true coverage was unknown and each review round
kept finding another missed site (a2a.py, kaizen-agents, rag/similarity.py). A
hand-audited sweep cannot answer "is it complete?" — only an enumeration can.

Detects, per `except ... as <v>:` handler:
  * <v> rendered via str(<v>) / f-string / .format / repr(<v>) / bare arg, AND
  * that value reaching a logger.* call OR a dict literal value OR a raise, AND
  * NOT already routed through sanitize_provider_error in the same handler.

Provider-adjacency is reported, not assumed: a handler is flagged HIGH only when
the enclosing try-body calls something provider-shaped (run/execute/complete/
embed/generate/chat/post/get/request/invoke/...). Everything else is LOW — a
local error whose raw text is legitimate diagnostic value that MUST NOT be
blanket-sanitized (over-sanitizing is its own defect, zero-tolerance Rule 3).

Usage:  .venv/bin/python <this> <pkg-src-dir> [more dirs...]
Exit 0 always — this is an enumerator, not a gate. The gate is the pinned
baseline test that consumes it.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

PROVIDER_CALL_HINTS = (
    "run",
    "run_async",
    "execute",
    "execute_async",
    "complete",
    "completion",
    "embed",
    "embeddings",
    "generate",
    "chat",
    "invoke",
    "predict",
    "post",
    "get",
    "put",
    "request",
    "send",
    "call",
    "acall",
    "stream",
)
# The scrubber VOCABULARY, not a single name.
#
# This was `SANITIZER = "sanitize_provider_error"` — one name — while the branch
# standardised most call sites onto `scrub_remote_error` (342 vs 257 repo-wide).
# The scanner therefore flagged handlers that ARE scrubbed, including sites
# `689f9ebd8` itself fixed (`a2a.py:2309/2318/...`, `approval_manager.py:148/160`).
#
# That mattered more than the false-positive rate suggests. Combined with the
# already-known false NEGATIVES (it cannot see a value that is not the bound
# exception name), the scanner was wrong in BOTH directions: green on defective
# sites, red on fixed ones. `high_count` could not reach zero by fixing code, so
# anyone driving it to zero either never converges or learns to dismiss the
# instrument — which is worse than having no instrument.
#
# INCLUSION RULE: a name belongs here only if it takes an error VALUE/MESSAGE and
# returns a scrubbed STRING. Adding a name that does not scrub would create a
# false NEGATIVE, and a false "swept" is the exact defect this scanner exists to
# catch. Omitting a real scrubber only costs a false positive, which is the safe
# direction — so when unsure, leave it out.
#
# Deliberately EXCLUDED, with reasons (do not add without re-deriving):
#   scrub_provider_secrets    — (environ: dict) -> list[str]; strips env vars,
#                               never touches error text. Wrong shape entirely.
#   sanitize_validation_error — (policy, model_name, ...); policy-driven
#                               validation redaction, not a general error scrub.
#                               Excluded on the safe side; revisit with evidence.
SANITIZERS = frozenset(
    {
        "sanitize_provider_error",
        "scrub_remote_error",
        "scrub_local_error",
        "scrub_credentials",
        "sanitize_db_error",
    }
)


def _renders_exc(node: ast.AST, name: str) -> bool:
    """Does this subtree render the exception variable into text?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == name:
            return True
    return False


def _is_sanitized(handler: ast.ExceptHandler) -> bool:
    for sub in ast.walk(handler):
        if isinstance(sub, ast.Call):
            fn = sub.func
            nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if nm in SANITIZERS:
                return True
    return False


def _surfaces(handler: ast.ExceptHandler, name: str) -> list[str]:
    """Which user-visible surfaces the raw exception reaches."""
    out: set[str] = set()
    for sub in ast.walk(handler):
        # logger.<level>(...) with the exc rendered anywhere in the args
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if fn.value.id in ("logger", "log", "logging", "audit_logger"):
                    if any(_renders_exc(a, name) for a in sub.args) or any(
                        _renders_exc(k.value, name) for k in sub.keywords
                    ):
                        out.add(f"log.{fn.attr}")
        # dict literal value carrying the exc
        if isinstance(sub, ast.Dict):
            for k, v in zip(sub.keys, sub.values):
                if v is not None and _renders_exc(v, name):
                    key = getattr(k, "value", None) if k is not None else None
                    out.add(f"dict[{key!r}]" if isinstance(key, str) else "dict")
        # raise X(... exc ...)
        if isinstance(sub, ast.Raise) and sub.exc is not None:
            if _renders_exc(sub.exc, name):
                out.add("raise")
    return sorted(out)


def _try_body_is_provider_shaped(try_node: ast.Try) -> str | None:
    for sub in ast.walk(ast.Module(body=try_node.body, type_ignores=[])):
        if isinstance(sub, ast.Call):
            fn = sub.func
            nm = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if nm in PROVIDER_CALL_HINTS:
                return nm
    return None


def scan(root: Path) -> list[dict]:
    findings: list[dict] = []
    for path in sorted(root.rglob("*.py")):
        if "build/lib" in str(path) or "/tests/" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            hint = _try_body_is_provider_shaped(node)
            for handler in node.handlers:
                if handler.name is None or _is_sanitized(handler):
                    continue
                surfaces = _surfaces(handler, handler.name)
                if not surfaces:
                    continue
                findings.append(
                    {
                        "file": str(path),
                        "line": handler.lineno,
                        "surfaces": surfaces,
                        "provider_call": hint,
                        "severity": "HIGH" if hint else "LOW",
                    }
                )
    return findings


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv]
    all_f: list[dict] = []
    for r in roots:
        all_f.extend(scan(r))
    high = [f for f in all_f if f["severity"] == "HIGH"]
    print(
        json.dumps(
            {
                "high": high,
                "high_count": len(high),
                "low_count": len(all_f) - len(high),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
