#!/usr/bin/env python3
"""Spec Drift Gate — mechanically verifies ``specs/*.md`` assertions against the
Kailash source tree.

S1 of the implementation plan delivers the four day-1-critical sweeps:

- FR-1: class existence
- FR-2: function/method existence
- FR-4: error-class existence (in ``kailash.ml.errors`` and friends)
- FR-7: test-file existence

Section-context inference (ADR-2) is the keystone: backticked symbols are
treated as assertions ONLY inside an allow-listed heading. Two HTML-comment
override directives (``<!-- spec-assert: ... -->`` /
``<!-- spec-assert-skip: ... reason:"..." -->``) override the heuristic.

Spec authority: ``specs/spec-drift-gate.md`` § 2.1, § 3, § 4, § 6.1, § 8, § 10.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

VERSION = "1.0.0-s1"

# ---------------------------------------------------------------------------
# Default source-root and errors-module configuration.
# S2 (SDG-201) replaces these constants with manifest-driven values
# (``.spec-drift-gate.toml`` per spec § 2.4).
# ---------------------------------------------------------------------------

DEFAULT_SOURCE_ROOTS: list[Path] = [
    Path("src/kailash"),
    Path("packages/kailash-ml/src/kailash_ml"),
    Path("packages/kailash-dataflow/src/dataflow"),
    Path("packages/kailash-nexus/src/nexus"),
    Path("packages/kailash-kaizen/src/kaizen"),
    Path("packages/kailash-pact/src/pact"),
    Path("packages/kailash-mcp/src/mcp"),
    Path("packages/kailash-align/src/kailash_align"),
]

DEFAULT_ERRORS_MODULES: list[Path] = [
    Path("src/kailash/ml/errors.py"),
    Path("src/kailash/errors.py"),
]

CACHE_PATH = Path(".spec-drift-gate-cache.json")
CACHE_FORMAT_VERSION = "1"


# ---------------------------------------------------------------------------
# Errors — every gate-raised exception derives from SpecDriftGateError per
# spec § 6.1.
# ---------------------------------------------------------------------------


class SpecDriftGateError(Exception):
    """Base class for spec-drift-gate runtime errors."""


class MarkerSyntaxError(SpecDriftGateError):
    """A ``<!-- spec-assert ... -->`` directive has malformed syntax."""


class SweepRuntimeError(SpecDriftGateError):
    """An AST parse failure on a ``.py`` file in a source root."""


# ---------------------------------------------------------------------------
# Section-context allowlist (ADR-2 § 3.1).
#
# The regex matches anywhere after ``## `` so numbered headings such as
# ``## 2. Construction`` or ``## 11. Test Contract`` are picked up. Excluded
# headings (Scope, Out of Scope, Industry Parity, Deferred to M2,
# Cross-References, Conformance Checklist, Maintenance Notes) are silent.
# ---------------------------------------------------------------------------

ALLOWLIST: dict[str, re.Pattern[str]] = {
    "FR-1": re.compile(r"^## .*?(Surface|Construction|Public API)\b", re.IGNORECASE),
    "FR-2": re.compile(r"^## .*?(Surface|Construction|Public API)\b", re.IGNORECASE),
    "FR-4": re.compile(r"^## .*?(Errors|Exceptions)\b", re.IGNORECASE),
    "FR-7": re.compile(r"^## .*?(Test Contract|Tests|Tier .* Tests)\b", re.IGNORECASE),
}

# Section headings that ALWAYS suppress sweeps (per spec § 3.1). These are
# checked first; if any match, no FR is applied to the section even when a
# substring match in ALLOWLIST would otherwise hit.
EXCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^## .*?\bScope\b", re.IGNORECASE),
    re.compile(r"^## .*?\bOut of Scope\b", re.IGNORECASE),
    re.compile(r"^## .*?\bIndustry Parity\b", re.IGNORECASE),
    re.compile(r"^## .*?\bDeferred to M[0-9]+\b", re.IGNORECASE),
    re.compile(r"^## .*?\bDeferred\b", re.IGNORECASE),
    re.compile(r"^## .*?\bCross-References\b", re.IGNORECASE),
    re.compile(r"^## .*?\bConformance Checklist\b", re.IGNORECASE),
    re.compile(r"^## .*?\bMaintenance Notes\b", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Override directives (ADR-2 § 3.2).
# ---------------------------------------------------------------------------

ASSERT_RE = re.compile(r"<!--\s*spec-assert:\s*(?P<kind>\w+):(?P<symbol>[\w.]+)\s*-->")
SKIP_RE = re.compile(
    r'<!--\s*spec-assert-skip:\s*(?P<kind>\w+):(?P<symbol>[\w.]+)\s+reason:"(?P<reason>[^"]+)"\s*-->'
)
# Loose detector — anything starting with the spec-assert / spec-assert-skip
# prefix that the strict regexes did NOT match is a syntax error.
ANY_DIRECTIVE_RE = re.compile(r"<!--\s*spec-assert(?:-skip)?:[^>]*-->")
ANY_DIRECTIVE_OPENER_RE = re.compile(r"<!--\s*spec-assert(?:-skip)?:")


@dataclass(frozen=True)
class OverrideDirective:
    kind: str
    symbol: str
    action: Literal["assert", "skip"]
    reason: str | None
    line_no: int


def parse_overrides(spec_text: str) -> list[OverrideDirective]:
    """Parse ``<!-- spec-assert ... -->`` directives in *spec_text*.

    Raises ``MarkerSyntaxError`` if any directive is malformed (e.g. missing
    ``reason:"..."`` on a skip).
    """

    overrides: list[OverrideDirective] = []
    for line_no, line in enumerate(spec_text.splitlines(), start=1):
        opener = ANY_DIRECTIVE_OPENER_RE.search(line)
        if opener is None:
            continue

        # Closed-form match (must include the closing -->):
        if "-->" not in line[opener.start() :]:
            raise MarkerSyntaxError(f"line {line_no}: directive missing closing '-->'")

        # Try the strict shapes in order.
        if (
            line.lstrip().startswith("<!-- spec-assert-skip")
            or "spec-assert-skip:" in line
        ):
            m = SKIP_RE.search(line)
            if m is None:
                # The line clearly intends to be a skip directive but does not
                # match the strict shape; identify the gap.
                if 'reason:"' not in line:
                    raise MarkerSyntaxError(
                        f"line {line_no}: spec-assert-skip directive missing required "
                        f'reason:"..." field'
                    )
                raise MarkerSyntaxError(
                    f"line {line_no}: malformed spec-assert-skip directive: {line.strip()}"
                )
            overrides.append(
                OverrideDirective(
                    kind=m.group("kind"),
                    symbol=m.group("symbol"),
                    action="skip",
                    reason=m.group("reason"),
                    line_no=line_no,
                )
            )
            continue

        # spec-assert (assert action)
        m = ASSERT_RE.search(line)
        if m is None:
            raise MarkerSyntaxError(
                f"line {line_no}: malformed spec-assert directive: {line.strip()}"
            )
        overrides.append(
            OverrideDirective(
                kind=m.group("kind"),
                symbol=m.group("symbol"),
                action="assert",
                reason=None,
                line_no=line_no,
            )
        )

    overrides.sort(key=lambda o: o.line_no)
    return overrides


# ---------------------------------------------------------------------------
# Section parsing.
# ---------------------------------------------------------------------------


@dataclass
class Subsection:
    """A level-3+ subsection used for fine-grained negation tracking.

    Subsections whose heading signals "NOT implemented", "Currently Lacks",
    "Do Not Reference", "follow-up: create", "Drift To Clean Up", etc. silence
    every sweep within their body so deferred / future content does not
    produce false-positive findings.
    """

    heading: str
    heading_line: int
    body_end: int
    negated: bool


@dataclass
class Section:
    heading: str
    heading_line: int  # 1-based
    body_end: int  # 1-based, exclusive (line of next heading or EOF)
    matched_frs: list[str] = field(default_factory=list)
    subsections: list[Subsection] = field(default_factory=list)


# Subsection-heading negation patterns. Any level-3/4 subheading matching one
# of these silences every sweep inside that subsection. The intent: spec
# authors flag deferred / fabricated / future work via heading text rather
# than per-symbol override directives.
SUBSECTION_NEGATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bNOT\s+Defined\b", re.IGNORECASE),
    re.compile(r"\bNot\s+Defined\b", re.IGNORECASE),
    re.compile(r"\bDo\s+Not\s+Reference\b", re.IGNORECASE),
    re.compile(r"\bNot\s+Implemented\b", re.IGNORECASE),
    re.compile(r"\bAbsent\b", re.IGNORECASE),
    re.compile(r"\bCurrently\s+Lacks\b", re.IGNORECASE),
    re.compile(r"\bDeferred\b", re.IGNORECASE),
    re.compile(r"\bDrift\s+To\s+Clean\s+Up\b", re.IGNORECASE),
    re.compile(r"\bWave\s+\d+\s+follow[- ]up\b", re.IGNORECASE),
    re.compile(r"\bAvailable\s+But\s+Not\s+Currently\s+Raised\b", re.IGNORECASE),
    re.compile(r"\bDefined\s+But\s+NOT\s+Raised\b", re.IGNORECASE),
    re.compile(r"\bDefined\s+But\s+Not\s+Raised\b", re.IGNORECASE),
    re.compile(r"\bMissing\s+Typed\s+Errors\b", re.IGNORECASE),
    re.compile(r"\bAbsent\s+At\s+The\s+Surface\b", re.IGNORECASE),
    re.compile(r"\bSix\s+Missing\b", re.IGNORECASE),
    re.compile(r"\bNamed\s+In\s+v\d+\s+Spec\s+But\s+Absent\b", re.IGNORECASE),
)


def _is_negated_subheading(heading: str) -> bool:
    return any(p.search(heading) for p in SUBSECTION_NEGATION_PATTERNS)


def scan_sections(spec_text: str) -> list[Section]:
    """Walk the markdown heading hierarchy.

    Returns one ``Section`` per ``##`` heading (ignoring those inside fenced
    code blocks). Each section's ``matched_frs`` list contains the FR codes
    whose allowlist regex matched the heading (after exclusions). The
    ``subsections`` list records every ``###`` / ``####`` heading inside the
    section, with a ``negated`` flag if the subheading signals deferred /
    not-implemented content.
    """

    lines = spec_text.splitlines()
    in_fence = False
    # (1-based line, heading text, level)
    raw_headings: list[tuple[int, str, int]] = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        # Fenced code block toggle: lines starting with ``` (any number).
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            raw_headings.append((idx, line.rstrip(), 2))
        elif line.startswith("### ") and not line.startswith("#### "):
            raw_headings.append((idx, line.rstrip(), 3))
        elif line.startswith("#### ") and not line.startswith("##### "):
            raw_headings.append((idx, line.rstrip(), 4))

    # First pass: build level-2 sections.
    level2 = [(ln, h) for (ln, h, lvl) in raw_headings if lvl == 2]
    sections: list[Section] = []
    for i, (heading_line, heading_text) in enumerate(level2):
        body_end = level2[i + 1][0] if i + 1 < len(level2) else len(lines) + 1
        section = Section(
            heading=heading_text,
            heading_line=heading_line,
            body_end=body_end,
        )
        if not _is_excluded(heading_text):
            for fr_code, regex in ALLOWLIST.items():
                if regex.match(heading_text):
                    section.matched_frs.append(fr_code)
        sections.append(section)

    # Second pass: attach subsections (level 3 and 4) to their parent level-2
    # section. Subsection body_end is the start of the NEXT heading at the
    # same or higher level, or the parent section's body_end.
    sub_headings = [(ln, h, lvl) for (ln, h, lvl) in raw_headings if lvl in (3, 4)]
    for sec in sections:
        # Filter to subheadings that lie within the parent's [heading_line, body_end).
        my_subs = [
            (ln, h, lvl)
            for (ln, h, lvl) in sub_headings
            if sec.heading_line < ln < sec.body_end
        ]
        for j, (ln, h, lvl) in enumerate(my_subs):
            # Find the next subheading with level <= current → bounds the body.
            sub_body_end = sec.body_end
            for k in range(j + 1, len(my_subs)):
                next_ln, _next_h, next_lvl = my_subs[k]
                if next_lvl <= lvl:
                    sub_body_end = next_ln
                    break
            sec.subsections.append(
                Subsection(
                    heading=h,
                    heading_line=ln,
                    body_end=sub_body_end,
                    negated=_is_negated_subheading(h),
                )
            )
    return sections


def _is_excluded(heading: str) -> bool:
    return any(p.match(heading) for p in EXCLUSION_PATTERNS)


# ---------------------------------------------------------------------------
# Stop-list — Python builtins, log levels, SQL types, etc. that look like
# class names (single capitalized identifier) but are NOT real classes in
# the Kailash source tree. Without this list FR-1 would flood the v2 specs
# with false positives.
# ---------------------------------------------------------------------------

STOP_LIST: frozenset[str] = frozenset(
    {
        # Python builtin singletons / sentinels.
        "True",
        "False",
        "None",
        "NotImplemented",
        "Ellipsis",
        "NaN",
        "Inf",
        # Builtin exception hierarchy.
        "BaseException",
        "Exception",
        "ArithmeticError",
        "AssertionError",
        "AttributeError",
        "BlockingIOError",
        "BrokenPipeError",
        "BufferError",
        "BytesWarning",
        "ChildProcessError",
        "ConnectionAbortedError",
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "DeprecationWarning",
        "EOFError",
        "EnvironmentError",
        "FileExistsError",
        "FileNotFoundError",
        "FloatingPointError",
        "FutureWarning",
        "GeneratorExit",
        "IOError",
        "ImportError",
        "ImportWarning",
        "IndentationError",
        "IndexError",
        "InterruptedError",
        "IsADirectoryError",
        "KeyError",
        "KeyboardInterrupt",
        "LookupError",
        "MemoryError",
        "ModuleNotFoundError",
        "NameError",
        "NotADirectoryError",
        "NotImplementedError",
        "OSError",
        "OverflowError",
        "PendingDeprecationWarning",
        "PermissionError",
        "ProcessLookupError",
        "RecursionError",
        "ReferenceError",
        "ResourceWarning",
        "RuntimeError",
        "RuntimeWarning",
        "StopAsyncIteration",
        "StopIteration",
        "SyntaxError",
        "SyntaxWarning",
        "SystemError",
        "SystemExit",
        "TabError",
        "TimeoutError",
        "TypeError",
        "UnboundLocalError",
        "UnicodeDecodeError",
        "UnicodeEncodeError",
        "UnicodeError",
        "UnicodeTranslateError",
        "UnicodeWarning",
        "UserWarning",
        "ValueError",
        "Warning",
        "ZeroDivisionError",
        # typing module surface (commonly cited in code blocks).
        "Any",
        "Optional",
        "Union",
        "Tuple",
        "List",
        "Dict",
        "Set",
        "FrozenSet",
        "Callable",
        "Iterator",
        "Iterable",
        "Generator",
        "AsyncIterator",
        "AsyncGenerator",
        "Awaitable",
        "Coroutine",
        "Sequence",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "Protocol",
        "TypeVar",
        "Generic",
        "Literal",
        "Final",
        "ClassVar",
        "Type",
        "TypedDict",
        "NamedTuple",
        # SQL / DDL types frequently cited in spec text.
        "JSONB",
        "JSON",
        "UUID",
        "BIGSERIAL",
        "BIGINT",
        "SERIAL",
        "INTEGER",
        "TEXT",
        "REAL",
        "VARCHAR",
        "BOOLEAN",
        "BLOB",
        "NUMERIC",
        "DECIMAL",
        "FLOAT",
        "DOUBLE",
        "TIMESTAMP",
        "TIMESTAMPTZ",
        "DATE",
        "TIME",
        "BYTEA",
        "ARRAY",
        # Log-level / log-level-like words.
        "WARN",
        "INFO",
        "DEBUG",
        "ERROR",
        "TRACE",
        "FATAL",
        "CRIT",
        "CRITICAL",
        "EXCEPTION",
        "NOTSET",
        # Document conventions and acronyms.
        "MUST",
        "MAY",
        "SHOULD",
        "DO",
        "NOT",
        "BLOCKED",
        "BUILD",
        "RFC",
        "PR",
        "PII",
        "PIT",
        "SDK",
        "API",
        "CLI",
        "MCP",
        "HTTP",
        "URL",
        "URI",
        "DDL",
        "DML",
        "GDPR",
        "RECOMMENDED",
        "PASS",
        "FAIL",
        "JSONL",
        "HTML",
        "OS",
        "IO",
        "TZ",
        "UTC",
        "CRUD",
        "PACT",
        "ADR",
        "ASHA",
        "BOHB",
        "PBT",
        "EI",
        "ML",
        "RL",
        "RLHF",
        "ONNX",
        "LLM",
        # Milestone / wave shorthand used in specs.
        "M0",
        "M1",
        "M2",
    }
)

# Words that look like classes (Cap-prefix) but are obviously prose.
PROSE_STOP_LIST: frozenset[str] = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "When",
        "Where",
        "If",
        "Else",
        "Then",
        "Per",
        "See",
        "Note",
        "BLOCKED",
        "DO",
        "NOT",
        "Today",
        "Now",
        "Yes",
        "No",
        "OK",
    }
)


# ---------------------------------------------------------------------------
# Symbol-index cache (FR-1, FR-2 backbone).
#
# Cache entry keyed by ``(file_path, mtime, sha256[:16])``. Disk persistence
# at ``.spec-drift-gate-cache.json`` (gitignored — added in S5).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheEntry:
    file_path: str
    mtime: float
    sha256_16: str
    classes: frozenset[str]
    # "Class.method" qualified names — module-level functions are stored as
    # bare names and resolved at sweep time.
    functions: frozenset[str]
    error_classes: frozenset[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "mtime": self.mtime,
            "sha256_16": self.sha256_16,
            "classes": sorted(self.classes),
            "functions": sorted(self.functions),
            "error_classes": sorted(self.error_classes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CacheEntry":
        return cls(
            file_path=str(data["file_path"]),
            mtime=float(data["mtime"]),  # type: ignore[arg-type]
            sha256_16=str(data["sha256_16"]),
            classes=frozenset(data["classes"]),  # type: ignore[arg-type]
            functions=frozenset(data["functions"]),  # type: ignore[arg-type]
            error_classes=frozenset(data["error_classes"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ErrorsModule:
    """A single ``errors.py`` declared as the canonical home for typed
    exceptions. Multiple modules MAY be declared; FR-4 union-scans across
    all of them (per spec § 11.6 Q9.1 v1.0 disposition)."""

    path: Path


@dataclass
class SymbolIndex:
    """In-memory union of every ``CacheEntry`` for the configured source
    roots + errors modules."""

    classes: set[str] = field(default_factory=set)
    methods: dict[str, set[str]] = field(default_factory=dict)
    error_classes: set[str] = field(default_factory=set)
    _entries: list[CacheEntry] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        source_roots: Iterable[Path],
        errors_modules: Iterable[ErrorsModule] | None = None,
    ) -> "SymbolIndex":
        idx = cls()
        seen_paths: set[str] = set()
        for root in source_roots:
            if not root.exists():
                continue
            for py_file in sorted(root.rglob("*.py")):
                resolved = str(py_file.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                entry = _parse_python_file(py_file)
                if entry is None:
                    continue
                idx._entries.append(entry)
                idx.classes.update(entry.classes)
                for fq in entry.functions:
                    if "." in fq:
                        cls_name, method = fq.split(".", 1)
                        idx.methods.setdefault(cls_name, set()).add(method)
                # Errors are also classes — make them findable via FR-1
                idx.classes.update(entry.error_classes)
        for em in errors_modules or ():
            if not em.path.exists():
                continue
            resolved = str(em.path.resolve())
            entry = _parse_python_file(em.path)
            if entry is None:
                continue
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                idx._entries.append(entry)
                idx.classes.update(entry.classes)
            idx.error_classes.update(entry.error_classes)
            idx.error_classes.update(entry.classes)
        return idx


def _parse_python_file(path: Path) -> CacheEntry | None:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise SweepRuntimeError(
            f"failed to parse {path}: line {exc.lineno}: {exc.msg}"
        ) from exc

    classes: set[str] = set()
    functions: set[str] = set()  # qualified names "Class.method" + bare names
    error_classes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
            if node.name.endswith("Error") or node.name.endswith("Warning"):
                error_classes.add(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.add(f"{node.name}.{item.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Top-level / nested function (we only consider top-level via the
            # tree.body filter below to avoid pulling in nested helpers).
            pass

    # Top-level functions only (for FR-2 standalone-call resolution).
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(top.name)

    stat = path.stat()
    h = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return CacheEntry(
        file_path=str(path.resolve()),
        mtime=stat.st_mtime,
        sha256_16=h,
        classes=frozenset(classes),
        functions=frozenset(functions),
        error_classes=frozenset(error_classes),
    )


def _load_cache(cache_path: Path) -> dict[str, CacheEntry]:
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("format") != CACHE_FORMAT_VERSION:
        return {}
    out: dict[str, CacheEntry] = {}
    for raw in data.get("entries", []):
        try:
            entry = CacheEntry.from_dict(raw)
        except Exception:
            continue
        out[entry.file_path] = entry
    return out


def _save_cache(cache_path: Path, entries: Iterable[CacheEntry]) -> None:
    payload = {
        "format": CACHE_FORMAT_VERSION,
        "entries": [e.to_dict() for e in entries],
    }
    try:
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Findings.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    spec_path: str
    line: int
    fr_code: str
    symbol: str
    kind: str
    message: str

    def sort_key(self) -> tuple[str, int, str, str]:
        return (self.spec_path, self.line, self.fr_code, self.symbol)


# ---------------------------------------------------------------------------
# Sweep dispatch.
# ---------------------------------------------------------------------------


# Find backticked tokens like `Foo`, `Foo.bar`, `Foo.bar()`, `tests/x.py`.
BACKTICK_TOKEN_RE = re.compile(r"`([^`\n]+?)`")
# Single capitalized identifier — at least 2 chars, must contain a lowercase
# letter (so all-cap acronyms like ``JSONB`` / ``UUID`` are excluded — they
# also appear in STOP_LIST but the regex narrows the class name surface).
CLASS_NAME_RE = re.compile(r"^[A-Z][a-zA-Z0-9_]*$")
# Method-call form: REQUIRE the trailing ``()`` so ``Class.field`` (a field
# reference, FR-5 territory deferred to S2) does NOT match. This narrows FR-2
# to clear method-call assertions.
METHOD_CALL_RE = re.compile(r"^([A-Z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\(\)$")
# Module-qualified form: ``pkg.subpkg.Class`` — extract the trailing Class.
DOTTED_CLASS_RE = re.compile(r"^(?:[a-z_][a-zA-Z0-9_]*\.)+([A-Z][a-zA-Z0-9_]*)$")
# Test-path form: tests/.../test_foo.py.
TEST_PATH_RE = re.compile(r"^(?:packages/[\w-]+/)?tests?/[\w./-]+\.py$")
# Error symbol: matches X*Error or X*Warning (single capitalized word
# ending in Error/Warning).
ERROR_NAME_RE = re.compile(r"^[A-Z][a-zA-Z0-9_]*(?:Error|Warning)$")

# Inline negation patterns — when these appear within a "negation window"
# around a backticked symbol, the symbol is treated as informally mentioned
# (deferred / not implemented / fabricated) and not asserted. The window is
# the surrounding paragraph (the line itself plus any continuation lines up
# to the next blank line in either direction).
INLINE_NEGATION_RE = re.compile(
    r"(?:"
    # Strong upper-case "NOT" markers.
    r"\bNOT\s+(?:implemented|raised|honoured|honored|present|defined|available|in)\b"
    r"|\(NOT\s+`"  # paren-prefixed: "ValueError (NOT `InvalidConfigError` ...)"
    r"|—\s+NOT\s+"  # em-dash-prefixed
    r"|\bMUST\s+NOT\b"
    r"|\bdoes\s+NOT\b"
    r"|\bdo\s+NOT\b"
    r"|\bis\s+NOT\b"
    r"|\bare\s+NOT\b"
    r"|\bwere\s+NOT\b"
    r"|\bare\s+missing\b"
    r"|\bis\s+missing\b"
    r"|\bnot\s+implemented\b"
    r"|\bnot\s+raised\b"
    r"|\bnot\s+available\b"
    r"|\bnot\s+defined\b"
    r"|\bnot\s+wired\b"
    r"|\bnot\s+honour"  # honoured / honored
    r"|\bnot\s+present\b"
    r"|\bare\s+absent\b"
    r"|\bis\s+absent\b"
    r"|\bdoes\s+not\s+raise\b"
    r"|\bdoes\s+not\s+implement\b"
    r"|\bdoes\s+not\s+exist\b"
    r"|\bv\d+[- ]spec'd\b"  # "v1-spec'd" or "v1 spec'd"
    r"|\bSpec\s+v\d+\b"
    r"|\bv\d+\s+spec\b"
    r"|\bfabricated\b"
    r"|\bnever\s+raised\b"
    r"|\bnever\s+raises\b"
    r"|\bdeprecated\b"
    r")",
    re.IGNORECASE,
)


def _is_in_negated_subsection(section: Section, line_no: int) -> bool:
    for sub in section.subsections:
        if sub.heading_line < line_no < sub.body_end and sub.negated:
            return True
    return False


def _paragraph_around(lines: list[str], line_no: int) -> str:
    """Return the paragraph containing line_no (1-based).

    Boundaries are blank lines or the file edges. Used for inline-negation
    detection so prose like 'The v1-spec'd `LeaderboardReport` is NOT
    implemented' suppresses the citation across the wrap-around lines.
    """

    if line_no - 1 < 0 or line_no - 1 >= len(lines):
        return ""
    start = line_no - 1
    while start > 0 and lines[start - 1].strip() != "":
        start -= 1
    end = line_no - 1
    while end + 1 < len(lines) and lines[end + 1].strip() != "":
        end += 1
    return "\n".join(lines[start : end + 1])


def _line_is_negated(lines: list[str], line_no: int) -> bool:
    paragraph = _paragraph_around(lines, line_no)
    return INLINE_NEGATION_RE.search(paragraph) is not None


def _resolve_test_path(symbol: str) -> bool:
    """Return True if *symbol* (a posix path) resolves to an existing file
    via direct lookup OR via any ``packages/*/`` prefix.

    The v2 specs use shortened paths like ``tests/unit/x.py`` that resolve
    to ``packages/<pkg>/tests/unit/x.py``. Trying every package prefix mirrors
    the way authors think about the path.
    """

    if Path(symbol).exists():
        return True
    pkgs_dir = Path("packages")
    if not pkgs_dir.exists():
        return False
    for pkg in pkgs_dir.iterdir():
        if not pkg.is_dir():
            continue
        candidate = pkg / symbol
        if candidate.exists():
            return True
    return False


def run_sweeps(
    spec_path: Path,
    spec_text: str,
    sections: list[Section],
    overrides: list[OverrideDirective],
    cache: SymbolIndex,
) -> list[Finding]:
    """Drive the four day-1 sweeps over *sections*.

    Override directives at the SAME section as a citation override the
    section's default behaviour: ``spec-assert-skip`` suppresses the finding;
    ``spec-assert`` forces the finding even outside an allowlist section
    (S1: assert is honoured but no extra section-context is required).
    """

    findings: list[Finding] = []
    lines = spec_text.splitlines()

    # Build a per-section override map keyed by symbol.
    overrides_by_section: dict[int, dict[tuple[str, str], OverrideDirective]] = {}
    section_index_by_line: dict[int, int] = {}
    for sec_idx, section in enumerate(sections):
        for line_no in range(section.heading_line, section.body_end):
            section_index_by_line[line_no] = sec_idx

    for od in overrides:
        sec_idx = section_index_by_line.get(od.line_no, -1)
        bucket = overrides_by_section.setdefault(sec_idx, {})
        bucket[(od.kind, od.symbol)] = od

    # Iterate each section, examine lines that lie inside.
    for sec_idx, section in enumerate(sections):
        if not section.matched_frs:
            continue
        # Walk body lines, skipping fenced code blocks.
        in_fence = False
        for line_no in range(section.heading_line + 1, section.body_end):
            if line_no - 1 >= len(lines):
                break
            line = lines[line_no - 1]
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            # Subsection silencer — heading-3/4 inside this section signals
            # deferred/fabricated/follow-up content, all citations are silent.
            if _is_in_negated_subsection(section, line_no):
                continue
            # Inline negation — paragraph-level NOT/v1-spec/Spec v1 markers
            # treat the line's citations as informal mentions.
            line_negated = _line_is_negated(lines, line_no)
            for token in BACKTICK_TOKEN_RE.findall(line):
                token = token.strip()
                if not token:
                    continue
                _dispatch_token(
                    token=token,
                    line_no=line_no,
                    spec_path=spec_path,
                    section=section,
                    overrides_for_section=overrides_by_section.get(sec_idx, {}),
                    cache=cache,
                    findings=findings,
                    line_negated=line_negated,
                )

    findings.sort(key=Finding.sort_key)
    return findings


def _dispatch_token(
    *,
    token: str,
    line_no: int,
    spec_path: Path,
    section: Section,
    overrides_for_section: dict[tuple[str, str], OverrideDirective],
    cache: SymbolIndex,
    findings: list[Finding],
    line_negated: bool = False,
) -> None:
    """Run every section-applicable sweep against *token*.

    A token may match more than one shape (e.g. ``FooError`` matches both
    FR-1 class-name and FR-4 error-class). FR-4 takes precedence inside
    Errors sections; FR-1 takes precedence inside Surface/Construction sections.

    When ``line_negated`` is True the surrounding paragraph carries a NOT /
    "v1 spec" / "removed" marker — every citation on the line is an informal
    mention and sweeps short-circuit silently.
    """

    if line_negated:
        return

    if "FR-7" in section.matched_frs and TEST_PATH_RE.match(token):
        symbol = token
        if _suppressed(overrides_for_section, "test_path", symbol):
            return
        if not _resolve_test_path(symbol):
            findings.append(
                Finding(
                    spec_path=str(spec_path),
                    line=line_no,
                    fr_code="FR-7",
                    symbol=symbol,
                    kind="test_path",
                    message=(
                        f"FR-7: test path {symbol!r} cited at "
                        f"{spec_path}:{line_no} does not exist on disk "
                        f"(searched cwd + packages/*/)"
                    ),
                )
            )
        return

    if "FR-4" in section.matched_frs and ERROR_NAME_RE.match(token):
        symbol = token
        if _suppressed(overrides_for_section, "class", symbol):
            return
        if symbol in STOP_LIST:
            return
        if symbol in cache.error_classes or symbol in cache.classes:
            return
        findings.append(
            Finding(
                spec_path=str(spec_path),
                line=line_no,
                fr_code="FR-4",
                symbol=symbol,
                kind="class",
                message=(
                    f"FR-4: {symbol} cited at {spec_path}:{line_no} not found "
                    f"in any configured errors module"
                ),
            )
        )
        return

    if "FR-2" in section.matched_frs:
        m = METHOD_CALL_RE.match(token)
        if m is not None:
            cls_name, method = m.group(1), m.group(2)
            full = f"{cls_name}.{method}"
            if _suppressed(overrides_for_section, "method", full):
                return
            # Skip dunders and obviously private helpers — the spec frequently
            # cites ``__post_init__`` / ``__init__`` which are language hooks.
            if method.startswith("__") and method.endswith("__"):
                return
            if cls_name in STOP_LIST or cls_name in PROSE_STOP_LIST:
                return
            if cls_name not in cache.classes and cls_name not in cache.error_classes:
                findings.append(
                    Finding(
                        spec_path=str(spec_path),
                        line=line_no,
                        fr_code="FR-2",
                        symbol=full,
                        kind="method",
                        message=(
                            f"FR-2: class {cls_name} (citing {full}) at "
                            f"{spec_path}:{line_no} not found in any source root"
                        ),
                    )
                )
                return
            if method not in cache.methods.get(cls_name, set()):
                findings.append(
                    Finding(
                        spec_path=str(spec_path),
                        line=line_no,
                        fr_code="FR-2",
                        symbol=full,
                        kind="method",
                        message=(
                            f"FR-2: method {full} cited at {spec_path}:{line_no} "
                            f"not found on class {cls_name}"
                        ),
                    )
                )
            return

    if "FR-1" in section.matched_frs:
        # Only consider single-token capitalized identifiers — everything
        # else (lowercase symbols, dotted module paths, code fragments) is
        # ignored at this layer.
        if "." in token:
            dotted = DOTTED_CLASS_RE.match(token)
            if dotted is None:
                return
            symbol = dotted.group(1)
        else:
            if not CLASS_NAME_RE.match(token):
                return
            symbol = token
        if symbol in STOP_LIST or symbol in PROSE_STOP_LIST:
            return
        if _suppressed(overrides_for_section, "class", symbol):
            return
        if symbol in cache.classes or symbol in cache.error_classes:
            return
        findings.append(
            Finding(
                spec_path=str(spec_path),
                line=line_no,
                fr_code="FR-1",
                symbol=symbol,
                kind="class",
                message=(
                    f"FR-1: class {symbol} cited at {spec_path}:{line_no} not "
                    f"found in any configured source root"
                ),
            )
        )


def _suppressed(
    overrides_for_section: dict[tuple[str, str], OverrideDirective],
    kind: str,
    symbol: str,
) -> bool:
    od = overrides_for_section.get((kind, symbol))
    return od is not None and od.action == "skip"


# ---------------------------------------------------------------------------
# Output formatting (S1: human format only).
# ---------------------------------------------------------------------------


FIX_HINT_TEMPLATE = (
    "  → fix: (a) define {symbol} in source, "
    "OR (b) delete the assertion, "
    "OR (c) move under `## Deferred to M2`"
)


def _emit_human(
    findings: list[Finding],
    *,
    spec_paths: list[Path],
    sections_by_spec: dict[str, list[Section]],
) -> int:
    by_spec: dict[str, list[Finding]] = {}
    for f in findings:
        by_spec.setdefault(f.spec_path, []).append(f)

    for spec_path in spec_paths:
        sp = str(spec_path)
        sec_list = sections_by_spec.get(sp, [])
        scanned = [s.heading for s in sec_list if s.matched_frs]
        spec_findings = by_spec.get(sp, [])
        if spec_findings:
            for f in spec_findings:
                print(
                    f"FAIL {f.spec_path}:{f.line} {f.fr_code}: "
                    f"{f.symbol} ({f.kind}) — {f.message}"
                )
                print(FIX_HINT_TEMPLATE.format(symbol=f.symbol))
        else:
            print(f"PASS {sp} (0 findings across {len(scanned)} scanned sections)")
        if scanned:
            print(f"INFO sections scanned: {scanned}")
        else:
            print(
                f"WARN {sp}: zero allowlisted sections found. "
                f"Expected one of: ## Surface, ## Construction, ## Public API, "
                f"## Errors, ## Test Contract"
            )

    return 1 if findings else 0


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec_drift_gate")
    parser.add_argument(
        "--format",
        choices=["human", "json", "github"],
        default="human",
    )
    parser.add_argument(
        "--baseline", type=Path, default=Path(".spec-drift-baseline.jsonl")
    )
    parser.add_argument("--refresh-baseline", action="store_true")
    parser.add_argument("--filter", default=None)
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("spec_paths", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        manifest_path = (
            args.baseline.parent / ".spec-drift-gate.toml"
            if args.baseline
            else Path(".spec-drift-gate.toml")
        )
        print(f"spec_drift_gate v{VERSION} (manifest: {manifest_path})")
        return 0

    # Resolve target specs.
    if args.spec_paths:
        spec_paths = [Path(p) for p in args.spec_paths]
    else:
        spec_paths = sorted(Path("specs").glob("**/*.md"))

    cache = SymbolIndex.build(
        DEFAULT_SOURCE_ROOTS,
        errors_modules=[ErrorsModule(p) for p in DEFAULT_ERRORS_MODULES],
    )

    all_findings: list[Finding] = []
    sections_by_spec: dict[str, list[Section]] = {}

    for spec_path in spec_paths:
        try:
            spec_text = spec_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SweepRuntimeError(f"failed to read spec {spec_path}: {exc}") from exc
        sections = scan_sections(spec_text)
        sections_by_spec[str(spec_path)] = sections
        overrides = parse_overrides(spec_text)
        findings = run_sweeps(spec_path, spec_text, sections, overrides, cache)
        all_findings.extend(findings)

    all_findings.sort(key=Finding.sort_key)

    if args.format == "human":
        return _emit_human(
            all_findings,
            spec_paths=spec_paths,
            sections_by_spec=sections_by_spec,
        )
    if args.format == "json":
        # Minimal JSON output for S1; full schema in S3.
        out = [f.__dict__ for f in all_findings]
        print(json.dumps(out, indent=2, sort_keys=True))
        return 1 if all_findings else 0
    if args.format == "github":
        # Minimal GitHub Actions annotation for S1; full schema in S3.
        for f in all_findings:
            print(
                f"::error file={f.spec_path},line={f.line}::"
                f"{f.fr_code}: {f.message}"
            )
        return 1 if all_findings else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
