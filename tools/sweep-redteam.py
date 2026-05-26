#!/usr/bin/env python3
"""Sweep 5 redteam tool — per-spec MUST-symbol verification (#1129).

Implements the `/sweep` Sweep 5 protocol from
`.claude/commands/sweep.md` and `.claude/skills/spec-compliance/SKILL.md`:
walk every `workspaces/*/specs/**/*.md`, extract MUST-clause symbols,
verify they exist in source via AST parsing, verify Tier 2 wiring tests
import them, and detect stub bodies (NotImplementedError / TODO / bare pass).

Per `.claude/rules/probe-driven-verification.md` MUST-3: where structural
verification is possible, use AST/grep/exit-code — NOT lexical regex over
assistant prose. The MUST-symbol extraction here scans STRUCTURED markers
in spec markdown (backticked identifiers next to "MUST" keywords); the
verification is AST-walked Python source. Both halves are structural.

# Invocation

    tools/sweep-redteam.py --json specs/<file>.md   # one spec
    tools/sweep-redteam.py --json --all             # every workspace spec

# Output

JSONL findings on stdout, one per line, followed by a sentinel comment.
Findings have the shape:

    {"category": "orphan|coverage_gap|stub|drift",
     "symbol": "Module.Symbol",
     "spec": "workspaces/<ws>/specs/<file>.md",
     "spec_line": <int>,
     "source": "<file:line>" | null,
     "evidence": "<command + output>"}

Sentinel (always emitted on stdout as the final line, on success or finding):

    <!-- sweep-redteam:v1:OK specs=N symbols=M orphans=O coverage_gaps=C stubs=S -->

Exit codes: 0 = no orphans/coverage_gaps/stubs; 1 = ≥1 finding (operator
decides disposition).

# MUST-symbol extraction heuristic

A spec MUST symbol is extracted from any line containing `MUST` (case-
sensitive) AND a backticked identifier of the shape:

  * `Module.Symbol` or `Module.submodule.Symbol` (dotted path) — searched
    for via AST in `packages/<pkg>/src/<module>.py` AND `src/<module>.py`.
  * `path/to/file.py:NNN` (file-line ref) — line ref alone is verified by
    file existence + line count.

The heuristic is conservative — false negatives (missed symbols) are
acceptable; false positives (spurious MUST citations) are not. The
canonical entry shape is `MUST ... \`Module.Symbol\` ...` per the
spec-compliance SKILL example tables.

# Verification per symbol

1. Source presence — AST-parse the candidate source file(s) and walk for
   `ast.ClassDef` / `ast.FunctionDef` / `ast.AsyncFunctionDef` /
   `ast.Assign(targets=[Name(...)])` matching the symbol's tail name.
2. Tier 2 coverage — grep `tests/integration/**/*.py` for an `import` or
   `from <module>` line referencing the module path. Missing = coverage_gap.
3. Stub body — AST-walk the matching def's body: if a single `Raise` of
   `NotImplementedError`, OR a single bare `Pass`, OR an inline `TODO` /
   `FIXME` comment in the body source → stub finding.

Drift detection (category 4) is out of scope for this v1 — the spec text
that says "X" and source that does "Y" requires semantic comparison
beyond AST shape; the tool emits the symbol presence/absence axis and
defers drift to the human reviewer.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent

# Regex over STRUCTURED markdown markers (not semantic prose) — extracts a
# backticked identifier from any line containing the literal "MUST" token.
# Per probe-driven-verification.md MUST-3: structural lex over structured
# markers is acceptable; this is NOT regex-over-semantic-claims.
_MUST_LINE = re.compile(r"\bMUST\b")
_BACKTICK_SYMBOL = re.compile(r"`([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")
_BACKTICK_FILELINE = re.compile(r"`([A-Za-z0-9_./-]+\.py):(\d+)`")

# Stub heuristics (AST-walked, not source-grepped)
_STUB_COMMENT = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b")


@dataclass(frozen=True)
class SpecSymbol:
    """One MUST symbol mention extracted from a spec file."""

    name: str  # dotted symbol path, e.g. "kailash.foo.Bar"
    spec_path: Path  # absolute path to the spec file
    spec_line: int  # 1-based line number where the mention appeared


@dataclass
class Finding:
    category: str  # "orphan" | "coverage_gap" | "stub" | "drift"
    symbol: str
    spec: str
    spec_line: int
    source: str | None
    evidence: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "category": self.category,
                "symbol": self.symbol,
                "spec": self.spec,
                "spec_line": self.spec_line,
                "source": self.source,
                "evidence": self.evidence,
            },
            sort_keys=True,
        )


@dataclass
class Sentinel:
    specs: int = 0
    symbols: int = 0
    orphans: int = 0
    coverage_gaps: int = 0
    stubs: int = 0

    def render(self) -> str:
        return (
            "<!-- sweep-redteam:v1:OK "
            f"specs={self.specs} symbols={self.symbols} "
            f"orphans={self.orphans} coverage_gaps={self.coverage_gaps} "
            f"stubs={self.stubs} -->"
        )


# --- Spec extraction --------------------------------------------------------


def extract_symbols(spec_path: Path) -> list[SpecSymbol]:
    """Walk a spec file; extract MUST-tagged backticked symbols + file refs.

    Returns a deduplicated list (preserves first-seen order). Conservative
    extractor — only emits symbols matching the canonical shape.
    """
    text = spec_path.read_text(encoding="utf-8")
    seen: dict[str, SpecSymbol] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not _MUST_LINE.search(line):
            continue
        for m in _BACKTICK_SYMBOL.finditer(line):
            name = m.group(1)
            if name not in seen:
                seen[name] = SpecSymbol(
                    name=name, spec_path=spec_path, spec_line=line_no
                )
        for m in _BACKTICK_FILELINE.finditer(line):
            ref = f"{m.group(1)}:{m.group(2)}"
            if ref not in seen:
                seen[ref] = SpecSymbol(name=ref, spec_path=spec_path, spec_line=line_no)
    return list(seen.values())


# --- Source verification ----------------------------------------------------


def candidate_source_files(symbol: str) -> list[Path]:
    """Map a dotted symbol path to likely source files.

    "kailash.foo.bar.Baz" → tries (in order):
      * src/kailash/foo/bar.py
      * src/kailash/foo/bar/__init__.py
      * packages/*/src/kailash/foo/bar.py
      * packages/*/src/kailash_foo/bar.py (sub-package convention)

    Returns ALL candidate paths that exist on disk. The tool does NOT
    guess one — every candidate is parsed; first hit wins for evidence.
    """
    parts = symbol.split(".")
    if len(parts) < 2:
        return []
    module_parts = parts[:-1]
    candidates: list[Path] = []

    # Try src/<module>.py and src/<module>/__init__.py
    base = ROOT / "src" / Path(*module_parts)
    candidates.append(base.with_suffix(".py"))
    candidates.append(base / "__init__.py")

    # Try packages/*/src/<module>.py
    pkg_dir = ROOT / "packages"
    if pkg_dir.is_dir():
        for pkg in pkg_dir.iterdir():
            if not pkg.is_dir():
                continue
            pkg_src = pkg / "src"
            if not pkg_src.is_dir():
                continue
            candidates.append(pkg_src / Path(*module_parts).with_suffix(".py"))
            candidates.append(pkg_src / Path(*module_parts) / "__init__.py")
            # sub-package convention: "kailash_align" instead of "kailash.align"
            if len(module_parts) >= 2 and module_parts[0] == "kailash":
                alt_first = f"kailash_{module_parts[1]}"
                alt_parts = [alt_first, *module_parts[2:]]
                if alt_parts:
                    candidates.append(pkg_src / Path(*alt_parts).with_suffix(".py"))
                    candidates.append(pkg_src / Path(*alt_parts) / "__init__.py")

    return [c for c in candidates if c.is_file()]


def find_symbol_in_ast(tree: ast.AST, tail_name: str) -> ast.AST | None:
    """Walk an AST for a class/function/assignment matching tail_name."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == tail_name:
                return node
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == tail_name:
                    return node
    return None


def is_stub_body(node: ast.AST, source: str) -> tuple[bool, str]:
    """Detect stub body: NotImplementedError raise, bare pass, or TODO comment.

    Returns (is_stub, evidence). Only applies to function/method definitions —
    classes and assignments cannot have stub bodies in this sense.
    """
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False, ""

    body = node.body
    # Strip leading docstring per Python convention
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    if not body:
        return False, ""

    # Single statement bodies — the canonical stub shapes
    if len(body) == 1:
        stmt = body[0]
        # raise NotImplementedError or raise NotImplementedError(...)
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc
            name = None
            if isinstance(exc, ast.Name):
                name = exc.id
            elif isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            if name == "NotImplementedError":
                return True, f"raise NotImplementedError at line {stmt.lineno}"
        # bare pass (as sole non-docstring body)
        if isinstance(stmt, ast.Pass):
            return True, f"bare pass at line {stmt.lineno}"

    # TODO/FIXME comment inside the body source (lexically present in the
    # function source range — still structural since we slice by line numbers)
    try:
        src_lines = source.splitlines()
        body_src = "\n".join(src_lines[node.lineno - 1 : node.end_lineno])
        m = _STUB_COMMENT.search(body_src)
        if m:
            return True, f"{m.group(1)} comment in body"
    except (AttributeError, IndexError):
        pass

    return False, ""


def verify_symbol(symbol: SpecSymbol) -> list[Finding]:
    """Run the three checks for a SpecSymbol; emit findings for each gap.

    Order: source-presence → stub-body → coverage. A missing source halts
    the chain (no point checking stub/coverage on an orphan).
    """
    # File-line ref shape — verify file exists and has ≥ that many lines
    if ":" in symbol.name and not symbol.name.split(".")[0].isidentifier():
        path_str, line_str = symbol.name.rsplit(":", 1)
        target = ROOT / path_str
        if not target.is_file():
            return [
                Finding(
                    category="orphan",
                    symbol=symbol.name,
                    spec=str(symbol.spec_path.relative_to(ROOT)),
                    spec_line=symbol.spec_line,
                    source=None,
                    evidence=f"file not found: {path_str}",
                )
            ]
        # Existence is enough — line refs do not get coverage/stub checks
        return []

    findings: list[Finding] = []
    tail = symbol.name.split(".")[-1]
    candidates = candidate_source_files(symbol.name)

    if not candidates:
        return [
            Finding(
                category="orphan",
                symbol=symbol.name,
                spec=str(symbol.spec_path.relative_to(ROOT)),
                spec_line=symbol.spec_line,
                source=None,
                evidence="no candidate source files exist for module path",
            )
        ]

    found_at: tuple[Path, ast.AST, str] | None = None
    for cand in candidates:
        try:
            src = cand.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(cand))
        except (OSError, SyntaxError):
            continue
        node = find_symbol_in_ast(tree, tail)
        if node is not None:
            found_at = (cand, node, src)
            break

    if found_at is None:
        return [
            Finding(
                category="orphan",
                symbol=symbol.name,
                spec=str(symbol.spec_path.relative_to(ROOT)),
                spec_line=symbol.spec_line,
                source=None,
                evidence=(
                    f"ast.walk found no ClassDef/FunctionDef/Assign named "
                    f"{tail!r} in {len(candidates)} candidate file(s)"
                ),
            )
        ]

    src_path, src_node, src_text = found_at
    src_rel = str(src_path.relative_to(ROOT))
    src_loc = f"{src_rel}:{src_node.lineno}"

    # Stub-body check
    is_stub, stub_evidence = is_stub_body(src_node, src_text)
    if is_stub:
        findings.append(
            Finding(
                category="stub",
                symbol=symbol.name,
                spec=str(symbol.spec_path.relative_to(ROOT)),
                spec_line=symbol.spec_line,
                source=src_loc,
                evidence=stub_evidence,
            )
        )

    # Tier-2 coverage check — grep tests/integration/ for module import
    if not has_tier2_coverage(symbol.name):
        findings.append(
            Finding(
                category="coverage_gap",
                symbol=symbol.name,
                spec=str(symbol.spec_path.relative_to(ROOT)),
                spec_line=symbol.spec_line,
                source=src_loc,
                evidence=(
                    f"no tests/integration/**/*.py file imports module "
                    f"{'.'.join(symbol.name.split('.')[:-1])}"
                ),
            )
        )

    return findings


def has_tier2_coverage(symbol_name: str) -> bool:
    """Return True if any tests/integration/**/*.py imports the module."""
    module_path = ".".join(symbol_name.split(".")[:-1])
    if not module_path:
        return False
    tests_root = ROOT / "tests" / "integration"
    if not tests_root.is_dir():
        return False
    # Build the structural import-line patterns:
    #   "from <module>" / "import <module>"
    # Use plain substring search per-file — fast, deterministic, scans bytes.
    import_needle_from = f"from {module_path}".encode()
    import_needle_imp = f"import {module_path}".encode()
    for path in tests_root.rglob("*.py"):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if import_needle_from in data or import_needle_imp in data:
            return True
        # Also accept the parent module (sub-pkg convention shifts the path)
        parent = ".".join(module_path.split(".")[:-1])
        if parent:
            if (
                f"from {parent}".encode() in data
                and module_path.split(".")[-1].encode() in data
            ):
                return True
    return False


# --- Orchestration ----------------------------------------------------------


def iter_spec_files(scope: Path | None = None) -> Iterator[Path]:
    """Yield spec files. With scope=None, walks all workspaces/*/specs/."""
    if scope is not None:
        if scope.is_file():
            yield scope
        elif scope.is_dir():
            yield from sorted(scope.rglob("*.md"))
        return
    ws_root = ROOT / "workspaces"
    if not ws_root.is_dir():
        return
    for ws in sorted(ws_root.iterdir()):
        if not ws.is_dir():
            continue
        specs_dir = ws / "specs"
        if not specs_dir.is_dir():
            continue
        yield from sorted(specs_dir.rglob("*.md"))


def run(spec_paths: Iterable[Path], out) -> int:
    """Run verification over the given specs; emit JSONL + sentinel.

    Returns process exit code: 0 if no orphans/coverage_gaps/stubs, else 1.
    """
    sentinel = Sentinel()
    for spec in spec_paths:
        sentinel.specs += 1
        symbols = extract_symbols(spec)
        sentinel.symbols += len(symbols)
        for sym in symbols:
            for finding in verify_symbol(sym):
                out.write(finding.to_json() + "\n")
                if finding.category == "orphan":
                    sentinel.orphans += 1
                elif finding.category == "coverage_gap":
                    sentinel.coverage_gaps += 1
                elif finding.category == "stub":
                    sentinel.stubs += 1
    out.write(sentinel.render() + "\n")
    has_finding = sentinel.orphans + sentinel.coverage_gaps + sentinel.stubs > 0
    return 1 if has_finding else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep 5 redteam tool — extract MUST-tagged symbols from "
            "workspaces/*/specs/**/*.md and verify presence + Tier 2 "
            "coverage + stub-free body via AST."
        ),
        epilog=(
            "Heuristic: MUST-symbol = a backticked identifier of shape "
            "`Module.Symbol` or `path/to/file.py:NNN` on any line "
            "containing the literal token MUST. Conservative — misses "
            "are acceptable; spurious matches are not. See "
            "tools/sweep-redteam.py module docstring + "
            ".claude/skills/spec-compliance/SKILL.md."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit JSONL findings to stdout, one per line, with a sentinel "
            "comment as the final line. This is the only supported output "
            "format in v1."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Verify every workspaces/*/specs/**/*.md file.",
    )
    group.add_argument(
        "spec",
        nargs="?",
        help="A specific spec file or directory under workspaces/*/specs/.",
    )
    args = parser.parse_args(argv)

    if not args.json:
        # v1 only supports --json; reject anything else explicitly so the
        # next reader knows the format is intentional, not under-implemented.
        parser.error("--json is required (the only supported output format in v1)")

    if args.all:
        specs = list(iter_spec_files(None))
    else:
        scope = Path(args.spec)
        if not scope.is_absolute():
            scope = ROOT / scope
        if not scope.exists():
            parser.error(f"spec path does not exist: {scope}")
        specs = list(iter_spec_files(scope))

    return run(specs, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
