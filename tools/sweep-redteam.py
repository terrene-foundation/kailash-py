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
canonical entry shape is "MUST ... Module.Symbol ..." (the symbol
wrapped in backticks) per the spec-compliance SKILL example tables.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent

# Regex over STRUCTURED markdown markers (not semantic prose) — extracts a
# backticked identifier from any line containing the literal "MUST" token.
# Per probe-driven-verification.md MUST-3: structural lex over structured
# markers is acceptable; this is NOT regex-over-semantic-claims.
_MUST_LINE = re.compile(r"\bMUST\b")
_BACKTICK_SYMBOL = re.compile(
    r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`"
)
_BACKTICK_FILELINE = re.compile(r"`([A-Za-z0-9_./-]+\.py):(\d+)`")

# Stub heuristics (AST-walked, not source-grepped)
_STUB_COMMENT = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b")


# --- Allowlist: false-positive symbol classes -------------------------------
#
# The MUST-symbol extraction (a backticked dotted token near "MUST") greedily
# matches many dotted strings that are NOT verifiable kailash source symbols.
# Each class below is a documented FALSE-POSITIVE family the extractor MUST
# skip so the residual surfaces genuine "declared in spec but absent in
# source" drift instead of burying it under external-lib / filename / example-
# variable noise.
#
# CONSERVATISM GUARD: none of these classes can match a genuine kailash package
# symbol. Real kailash roots (kailash*, kaizen, dataflow, nexus) resolve to a
# source file and are verified via AST; a genuinely-missing kailash-family
# module (real drift) is explicitly protected in class (d) below.

# (a) stdlib module roots — a stdlib name is never a kailash source symbol
# (`hmac.compare_digest`, `secrets.compare_digest`, `asyncio.run`, `sys.modules`).
_STDLIB_ROOTS = frozenset(sys.stdlib_module_names)

# (a) third-party package roots (+ common import aliases). Documented external
# deps referenced in spec prose (`torch.distributed`, `polars.DataFrame`,
# `pytorch_lightning.Trainer`, `L.Trainer`); none is a kailash symbol.
_THIRD_PARTY_ROOTS = frozenset(
    {
        "torch",
        "polars",
        "pl",
        "pandas",
        "pd",
        "numpy",
        "np",
        "scipy",
        "sklearn",
        "transformers",
        "pytorch_lightning",
        "lightning",
        "L",
        "stable_baselines3",
        "sb3",
        "sb3_contrib",
        "pettingzoo",
        "gymnasium",
        "gym",
        "accelerate",
        "jax",
        "tensorflow",
        "tf",
        "xgboost",
        "lightgbm",
        "catboost",
        "mlflow",
        "ray",
        "onnx",
        "onnxruntime",
        "ort",
        "datasets",
        "trl",
        "peft",
        "PIL",
        "plotly",
        "matplotlib",
        "seaborn",
        "pydantic",
        "fastapi",
        "starlette",
        "uvicorn",
        "aiohttp",
        "httpx",
        "sqlalchemy",
        "psycopg2",
        "aiosqlite",
        "redis",
        "boto3",
        "click",
        "yaml",
        "jsonschema",
        "structlog",
        "opentelemetry",
        "prometheus_client",
        "websockets",
        "cryptography",
        "jwt",
        "com",
        "param",
    }
)

# (b) file/config references — a dotted token whose tail is a file suffix is a
# filename (`pytest.ini`, `conftest.py`, `pyproject.toml`, `observability.md`,
# `last.ckpt`, `plotly.min.js`), NOT a `Module.Symbol`.
_FILE_SUFFIXES = frozenset(
    {
        "py",
        "pyi",
        "md",
        "ini",
        "toml",
        "cfg",
        "js",
        "mjs",
        "cjs",
        "json",
        "yaml",
        "yml",
        "txt",
        "ckpt",
        "sh",
        "lock",
        "rs",
        "rb",
    }
)

# (c) instance-attribute roots — `self.x` / `cls.x` in a code fence is an
# attribute access on an instance, never an importable module path.
_INSTANCE_ROOTS = frozenset({"self", "cls"})

# (d) genuine kailash top-level package prefixes — a symbol whose ROOT starts
# with one of these is NEVER treated as an illustrative local-var (class (d) in
# verify_symbol), even when it fails to resolve, so a genuinely-missing
# kailash-family module stays flagged as real drift.
_KAILASH_FAMILY_PREFIXES = ("kailash", "kaizen", "dataflow", "nexus")


def _lexical_allowlist_class(name: str) -> str | None:
    """Return the false-positive class label for a symbol skippable by lexical
    shape alone (classes a/b/c), or None if it must be verified.

    Class (d) — illustrative lowercase local-vars / event-keys — needs source
    resolution and is handled in `verify_symbol` (only fires when no candidate
    source module exists).
    """
    parts = name.split(".")
    root = parts[0]
    tail = parts[-1]
    if root in _INSTANCE_ROOTS:
        return "instance-attr(self/cls)"
    if tail in _FILE_SUFFIXES:
        return "file-reference"
    if root in _STDLIB_ROOTS:
        return "stdlib-module"
    if root in _THIRD_PARTY_ROOTS:
        return "third-party-module"
    return None


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
            # Skip lexical false-positive classes (a/b/c) — stdlib / third-party
            # module refs, filename references, and self./cls. instance-attribute
            # accesses are never verifiable kailash source symbols.
            if _lexical_allowlist_class(name) is not None:
                continue
            if name not in seen:
                seen[name] = SpecSymbol(
                    name=name, spec_path=spec_path, spec_line=line_no
                )
        for m in _BACKTICK_FILELINE.finditer(line):
            path = m.group(1)
            # Bare-basename line citations (`errors.py:722`) are illustrative —
            # the canonical resolvable shape is `path/to/file.py:NNN` (a path
            # with a directory component that resolves against the repo root).
            # A basename alone cannot be resolved and is prose, not drift.
            if "/" not in path:
                continue
            ref = f"{path}:{m.group(2)}"
            if ref not in seen:
                seen[ref] = SpecSymbol(name=ref, spec_path=spec_path, spec_line=line_no)
    return list(seen.values())


# --- Source verification ----------------------------------------------------


def _source_roots() -> list[Path]:
    """Every import root: `src/` plus each `packages/*/src/`."""
    roots: list[Path] = []
    src = ROOT / "src"
    if src.is_dir():
        roots.append(src)
    pkg_dir = ROOT / "packages"
    if pkg_dir.is_dir():
        for pkg in sorted(pkg_dir.iterdir()):
            if pkg.is_dir() and (pkg / "src").is_dir():
                roots.append(pkg / "src")
    return roots


def _dotted_path_is_module(symbol: str) -> bool:
    """True if the FULL dotted path names an importable module or package on disk.

    A spec reference whose tail is itself a submodule / subpackage
    (`kailash_ml.features`, `kaizen.judges`, `kailash.trust.envelope`,
    `dataflow.adapters.dialect`) resolves to a directory or `.py` file, NOT to a
    class/func/assign inside a parent module. The tail-symbol AST walk looks for
    a symbol NAMED after the directory and falsely reports the module absent.
    This check recognizes the module/package as present. It resolves ONLY real
    on-disk paths — a genuinely-missing module returns False and stays flagged as
    drift, so it never masks true drift. Also matches the sub-package rename
    convention (`kailash.align` module dir living at `src/kailash_align/`).
    """
    parts = symbol.split(".")
    rel = Path(*parts)
    variants = [rel]
    # sub-package convention: `kailash.<sub>....` may live at `kailash_<sub>/...`
    if len(parts) >= 2 and parts[0] == "kailash":
        variants.append(Path(f"kailash_{parts[1]}", *parts[2:]))
    for root in _source_roots():
        for v in variants:
            if (root / v).is_dir() and (root / v / "__init__.py").is_file():
                return True
            if (root / v.with_suffix(".py")).is_file():
                return True
    return False


def candidate_source_files(symbol: str) -> list[Path]:
    """Map a dotted symbol path to likely source files.

    "kailash.foo.bar.Baz" → tries (in order), every progressively-shorter
    module-prefix because the symbol's last 1-N parts may be a
    class.method.nested chain inside a single module file:

      * src/kailash/foo/bar.py       (module = kailash.foo.bar, tail = Baz)
      * src/kailash/foo/bar/__init__.py
      * src/kailash/foo.py           (module = kailash.foo, tail = bar.Baz)
      * src/kailash/foo/__init__.py
      * packages/*/src/<module>.py   (mirrored for every prefix)
      * packages/*/src/kailash_<sub>/<rest>.py (sub-package convention)

    The tail-symbol AST walk in `find_symbol_in_ast` uses `parts[-1]`
    only — so every candidate file is parsed and walked for the tail.
    Returns ALL candidate paths that exist on disk in priority order
    (longest module prefix first, shortest last). Deduplicated.
    """
    parts = symbol.split(".")
    if len(parts) < 2:
        return []

    candidates: list[Path] = []
    pkg_dir = ROOT / "packages"
    pkg_srcs: list[Path] = []
    if pkg_dir.is_dir():
        for pkg in sorted(pkg_dir.iterdir()):
            if pkg.is_dir() and (pkg / "src").is_dir():
                pkg_srcs.append(pkg / "src")

    # Iterate module-prefix lengths from longest (parts[:-1]) down to 1,
    # so the most-specific file is tried first. AST walk is cheap and
    # first-hit semantics protect against name shadowing per
    # find_symbol_in_ast's documented contract.
    for prefix_len in range(len(parts) - 1, 0, -1):
        module_parts = parts[:prefix_len]
        # src/<module>.py and src/<module>/__init__.py
        base = ROOT / "src" / Path(*module_parts)
        candidates.append(base.with_suffix(".py"))
        candidates.append(base / "__init__.py")
        # packages/*/src/<module>.py
        for pkg_src in pkg_srcs:
            candidates.append(pkg_src / Path(*module_parts).with_suffix(".py"))
            candidates.append(pkg_src / Path(*module_parts) / "__init__.py")
            # sub-package convention: "kailash_align" instead of "kailash.align"
            if len(module_parts) >= 2 and module_parts[0] == "kailash":
                alt_first = f"kailash_{module_parts[1]}"
                alt_parts = [alt_first, *module_parts[2:]]
                if alt_parts:
                    candidates.append(pkg_src / Path(*alt_parts).with_suffix(".py"))
                    candidates.append(pkg_src / Path(*alt_parts) / "__init__.py")

    # Deduplicate while preserving priority order
    seen: set[Path] = set()
    deduped: list[Path] = []
    for c in candidates:
        if c not in seen and c.is_file():
            seen.add(c)
            deduped.append(c)
    return deduped


def find_symbol_in_ast(tree: ast.AST, tail_name: str) -> ast.stmt | None:
    """Walk an AST for a class/function/assignment matching tail_name.

    Returns the matching statement node (ast.stmt) so callers can rely
    on .lineno / .end_lineno being present.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == tail_name:
                return node
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == tail_name:
                    return node
        # Re-export: `from .submodule import Name [as Alias]`. Facade / package
        # __init__.py modules expose public symbols by RE-EXPORT, not local def;
        # matching only ClassDef/FunctionDef/Assign misses every re-exported
        # symbol and reports a present-but-re-exported public API (e.g.
        # `kailash_ml.errors.ParamValueError`) as a false orphan. The bound name
        # is `asname or name`. A genuinely-absent symbol has no such binding, so
        # this only recognizes real presence — it never masks true drift.
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == tail_name:
                    return node
        # Annotated assignment: `NAME: T = value` / `NAME: T` (module-level
        # constants like `__version__: str = "..."`, dataclass fields). ast.Assign
        # does NOT cover ast.AnnAssign, so annotated definitions were falsely
        # reported absent.
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == tail_name:
                return node
    return None


def is_stub_body(node: ast.stmt, source: str) -> tuple[bool, str]:
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
        path_str, _line_str = symbol.name.rsplit(":", 1)
        target = (ROOT / path_str).resolve()
        # Defense-in-depth: refuse path-collapse escapes even though the
        # backtick-filerule regex bounds path chars. Per R1 security review
        # LOW finding (R1-security-09).
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            return [
                Finding(
                    category="orphan",
                    symbol=symbol.name,
                    spec=str(symbol.spec_path.relative_to(ROOT)),
                    spec_line=symbol.spec_line,
                    source=None,
                    evidence=f"file-line ref escapes repo root: {path_str}",
                )
            ]
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

    # Module / package reference — the full dotted path names an importable
    # module or package on disk (`kailash_ml.features`, `kaizen.judges`,
    # `kailash.trust.envelope`). The tail is a directory / file, not an in-file
    # symbol; existence of the module IS the answer. Checked before the
    # tail-symbol AST walk, which would otherwise search the PARENT module for a
    # symbol named after the directory and falsely report the module absent.
    if _dotted_path_is_module(symbol.name):
        return []

    findings: list[Finding] = []
    tail = symbol.name.split(".")[-1]
    candidates = candidate_source_files(symbol.name)

    if not candidates:
        # (d) Illustrative local-variable / event-key / prose-alias reference.
        # A LOWERCASE root that resolves to NO source module — and is not a
        # kailash-family package — is an attribute access on an example instance
        # (`device.family`, `result.device`, `engine.tenant_id`), a dotted
        # event/metric/log key (`server.signature.changed`,
        # `rl.policy.kl_from_ref`, `feature_store.erase_tenant.ok`), or a prose
        # API-alias mention (`km.register`, `ml.runs.get`) — never a verifiable
        # kailash source symbol. Kailash-family roots (`kailash*`, `kaizen`,
        # `dataflow`, `nexus`) are PROTECTED: a genuinely-missing kailash-family
        # module falls through to the orphan finding below (real drift). A
        # Capitalized root (`RegisterResult.artifact_uris`) is a ClassName.member
        # reference — kept as an orphan (the tool cannot resolve a class as a
        # module, but the contract is genuine, not illustrative). Likewise a
        # Capitalized TAIL (`myapp.missing.Vanished`, `pkg.mod.SomeClass`) names a
        # class/type CONTRACT the spec promises — kept as an orphan; every
        # illustrative false-positive above has a lowercase tail (`.family`,
        # `.register`, `.changed`), so the CapWords-tail carve-out preserves the
        # false-positive suppression while restoring genuine missing-symbol drift.
        root = symbol.name.split(".")[0]
        if (
            root[:1].islower()
            and not root.startswith(_KAILASH_FAMILY_PREFIXES)
            and not tail[:1].isupper()
        ):
            return []
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

    found_at: tuple[Path, ast.stmt, str] | None = None
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
        # Defense-in-depth: refuse paths outside ROOT even when the operator
        # supplied an absolute path. Bounds the blast radius of an attacker
        # who can influence argv (CI invocation with attacker-influenced
        # parameters). Per R1 security review LOW finding (R1-security-01).
        resolved = scope.resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            parser.error(f"spec path escapes repo root: {scope}")
        if not resolved.exists():
            parser.error(f"spec path does not exist: {scope}")
        specs = list(iter_spec_files(resolved))

    return run(specs, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
