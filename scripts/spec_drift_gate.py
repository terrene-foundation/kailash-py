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
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

VERSION = "1.0.0-s3"

DEFAULT_MANIFEST_PATH = Path(".spec-drift-gate.toml")

# ---------------------------------------------------------------------------
# Source-root and errors-module configuration is manifest-driven from
# ``.spec-drift-gate.toml`` (per spec § 2.4). The S1 in-line defaults were
# replaced by ``Manifest.load()`` in S2; missing manifest raises
# ``ManifestNotFoundError`` rather than falling back implicitly.
# ---------------------------------------------------------------------------

CACHE_PATH = Path(".spec-drift-gate-cache.json")
CACHE_FORMAT_VERSION = "2"


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


class ManifestNotFoundError(SpecDriftGateError):
    """``.spec-drift-gate.toml`` not present at the expected path."""


class ManifestSchemaError(SpecDriftGateError):
    """Manifest fails schema validation. The message names the bad field."""


class BaselineParseError(SpecDriftGateError):
    """``.spec-drift-baseline.jsonl`` is malformed JSON or missing required fields."""


# ---------------------------------------------------------------------------
# Manifest (SDG-201). Spec § 2.4 is canonical (supersedes the divergent ADR-5
# example in ``02-requirements-and-adrs.md`` per redteam REQ-HIGH-2). The
# parser refuses to run without the file (no implicit defaults) and validates
# every path at parse time so typos surface before any sweep fires.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRoot:
    package: str
    path: Path


@dataclass(frozen=True)
class ErrorsOverride:
    package: str
    path: Path


@dataclass(frozen=True)
class Exclusions:
    test_specs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    """Typed view of ``.spec-drift-gate.toml`` per spec § 2.4."""

    version: str
    spec_glob: str
    source_roots: tuple[SourceRoot, ...]
    errors_default: Path
    errors_overrides: tuple[ErrorsOverride, ...]
    exclusions: Exclusions

    @classmethod
    def load(cls, path: Path = DEFAULT_MANIFEST_PATH) -> "Manifest":
        if not path.exists():
            raise ManifestNotFoundError(
                f"manifest not found at {path}; create one per "
                f"specs/spec-drift-gate.md § 2.4"
            )
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ManifestSchemaError(f"{path}: malformed TOML: {exc}") from exc
        return cls._from_raw(raw, path)

    @classmethod
    def _from_raw(cls, raw: dict[str, object], manifest_path: Path) -> "Manifest":
        gate = raw.get("gate")
        if not isinstance(gate, dict):
            raise ManifestSchemaError(f"{manifest_path}: missing required [gate] table")
        for required in ("version", "spec_glob"):
            if required not in gate:
                raise ManifestSchemaError(
                    f"{manifest_path}: [gate].{required} is required"
                )

        sr_raw = raw.get("source_roots")
        if not isinstance(sr_raw, list) or not sr_raw:
            raise ManifestSchemaError(
                f"{manifest_path}: [[source_roots]] required (at least one entry)"
            )
        source_roots: list[SourceRoot] = []
        for i, item in enumerate(sr_raw):
            if not isinstance(item, dict):
                raise ManifestSchemaError(
                    f"{manifest_path}: [[source_roots]][{i}] not a table"
                )
            if "package" not in item:
                raise ManifestSchemaError(
                    f"{manifest_path}: [[source_roots]][{i}] missing 'package'"
                )
            if "path" not in item:
                raise ManifestSchemaError(
                    f"{manifest_path}: [[source_roots]][{i}] missing 'path'"
                )
            p = Path(str(item["path"]))
            if not p.exists():
                raise ManifestSchemaError(
                    f"{manifest_path}: [[source_roots]][{i}] path does not "
                    f"exist on disk: {p}"
                )
            source_roots.append(SourceRoot(package=str(item["package"]), path=p))

        em_raw = raw.get("errors_modules")
        if not isinstance(em_raw, dict) or "default" not in em_raw:
            raise ManifestSchemaError(
                f"{manifest_path}: [errors_modules].default is required"
            )
        errors_default = Path(str(em_raw["default"]))
        if not errors_default.exists():
            raise ManifestSchemaError(
                f"{manifest_path}: [errors_modules].default path does not "
                f"exist on disk: {errors_default}"
            )
        overrides_raw = em_raw.get("overrides") or []
        if not isinstance(overrides_raw, list):
            raise ManifestSchemaError(
                f"{manifest_path}: [errors_modules].overrides must be an array"
            )
        overrides: list[ErrorsOverride] = []
        for i, item in enumerate(overrides_raw):
            if not isinstance(item, dict):
                raise ManifestSchemaError(
                    f"{manifest_path}: [errors_modules].overrides[{i}] " f"not a table"
                )
            if "package" not in item:
                raise ManifestSchemaError(
                    f"{manifest_path}: [errors_modules].overrides[{i}] "
                    f"missing 'package'"
                )
            if "path" not in item:
                raise ManifestSchemaError(
                    f"{manifest_path}: [errors_modules].overrides[{i}] "
                    f"missing 'path'"
                )
            p = Path(str(item["path"]))
            if not p.exists():
                raise ManifestSchemaError(
                    f"{manifest_path}: [errors_modules].overrides[{i}] path "
                    f"does not exist on disk: {p}"
                )
            overrides.append(ErrorsOverride(package=str(item["package"]), path=p))

        exclusions_raw = raw.get("exclusions") or {}
        if not isinstance(exclusions_raw, dict):
            raise ManifestSchemaError(f"{manifest_path}: [exclusions] must be a table")
        test_specs = tuple(str(x) for x in (exclusions_raw.get("test_specs") or []))

        return cls(
            version=str(gate["version"]),
            spec_glob=str(gate["spec_glob"]),
            source_roots=tuple(source_roots),
            errors_default=errors_default,
            errors_overrides=tuple(overrides),
            exclusions=Exclusions(test_specs=test_specs),
        )


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
    # SDG-202 sweeps share the Surface/Construction/Public API allowlist.
    "FR-3": re.compile(r"^## .*?(Surface|Construction|Public API)\b", re.IGNORECASE),
    "FR-4": re.compile(r"^## .*?(Errors|Exceptions)\b", re.IGNORECASE),
    "FR-5": re.compile(r"^## .*?(Surface|Construction|Public API)\b", re.IGNORECASE),
    "FR-6": re.compile(r"^## .*?(Surface|Construction|Public API)\b", re.IGNORECASE),
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

        # Documentation-form mention: when the directive shape is wrapped in
        # backticks (``\`<!-- spec-assert ... -->\```), the line is illustrating
        # the syntax, not declaring it. specs/spec-drift-gate.md § 3.2 quotes
        # its own directives this way. Real directives sit on their own line
        # (possibly indented), so require the stripped line to actually open
        # with ``<!--`` before treating the match as a directive.
        if not line.lstrip().startswith("<!--"):
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
    # Parenthetical deferral marker — ``(Yet)`` / ``(yet)`` in a subheading
    # signals "documented future work" and silences sweeps inside the body.
    re.compile(r"\(Yet\)", re.IGNORECASE),
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
    # SDG-202 additions:
    # - ``class_fields`` records ``AnnAssign`` field names per class (FR-5).
    # - ``decorator_uses`` records the count of each decorator name applied
    #   inside this file (FR-3). Decorator names are the last dotted segment
    #   so ``@dataclass`` and ``@dataclasses.dataclass`` both bucket as
    #   ``dataclass``.
    # - ``all_exports`` records the ``__all__`` entries declared at module
    #   scope (FR-6). Empty when ``__all__`` is absent or unparseable.
    class_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    decorator_uses: tuple[tuple[str, int], ...] = ()
    all_exports: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "mtime": self.mtime,
            "sha256_16": self.sha256_16,
            "classes": sorted(self.classes),
            "functions": sorted(self.functions),
            "error_classes": sorted(self.error_classes),
            "class_fields": [
                [name, list(fields)] for name, fields in self.class_fields
            ],
            "decorator_uses": [[name, count] for name, count in self.decorator_uses],
            "all_exports": sorted(self.all_exports),
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
            class_fields=tuple(
                (str(name), tuple(str(f) for f in fields))
                for name, fields in (data.get("class_fields") or [])  # type: ignore[union-attr]
            ),
            decorator_uses=tuple(
                (str(name), int(count))
                for name, count in (data.get("decorator_uses") or [])  # type: ignore[union-attr]
            ),
            all_exports=frozenset(
                str(s) for s in (data.get("all_exports") or [])  # type: ignore[union-attr]
            ),
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
    # SDG-202: class_name → set of dataclass field names (FR-5). When the
    # same class name appears in multiple files (e.g. test fixtures) the
    # union is what FR-5 consults.
    class_fields: dict[str, set[str]] = field(default_factory=dict)
    # decorator-name → total occurrences across every parsed source file
    # (FR-3). Names are last-dotted-segment so ``dataclass`` covers both
    # ``@dataclass`` and ``@dataclasses.dataclass``.
    decorator_counts: dict[str, int] = field(default_factory=dict)
    # Union of every ``__all__`` entry declared at module scope (FR-6).
    all_exports: set[str] = field(default_factory=set)
    # SDG-203: package-qualified-name → {symbol: target_module} extracted
    # from the package's ``__init__.py::__getattr__`` lazy-import map. The
    # B1 sweep consults this to flag spec / source resolution divergence.
    getattr_resolution: dict[str, dict[str, str]] = field(default_factory=dict)
    _entries: list[CacheEntry] = field(default_factory=list)

    def _absorb(self, entry: CacheEntry) -> None:
        self._entries.append(entry)
        self.classes.update(entry.classes)
        self.classes.update(entry.error_classes)
        for fq in entry.functions:
            if "." in fq:
                cls_name, method = fq.split(".", 1)
                self.methods.setdefault(cls_name, set()).add(method)
        for class_name, fields_ in entry.class_fields:
            self.class_fields.setdefault(class_name, set()).update(fields_)
        for dec_name, count in entry.decorator_uses:
            self.decorator_counts[dec_name] = (
                self.decorator_counts.get(dec_name, 0) + count
            )
        self.all_exports.update(entry.all_exports)

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
            # SDG-203: per-root ``__getattr__`` resolution map. ``root``
            # like ``packages/kailash-ml/src/kailash_ml`` resolves to
            # package qualname ``kailash_ml`` (the directory name).
            pkg_qualname = root.name
            init_py = root / "__init__.py"
            if init_py.exists():
                map_entries = _parse_getattr_map(init_py)
                if map_entries:
                    idx.getattr_resolution[pkg_qualname] = map_entries
            for py_file in sorted(root.rglob("*.py")):
                resolved = str(py_file.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                entry = _parse_python_file(py_file)
                if entry is None:
                    continue
                idx._absorb(entry)
        for em in errors_modules or ():
            if not em.path.exists():
                continue
            resolved = str(em.path.resolve())
            entry = _parse_python_file(em.path)
            if entry is None:
                continue
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                idx._absorb(entry)
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
    # SDG-202: class_name → set of AnnAssign field names (FR-5)
    class_fields: dict[str, set[str]] = {}
    # bare decorator name → count of applications in this file (FR-3)
    decorator_uses: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.add(node.name)
            if node.name.endswith("Error") or node.name.endswith("Warning"):
                error_classes.add(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.add(f"{node.name}.{item.name}")
                    for dec in item.decorator_list:
                        dec_name = _decorator_name(dec)
                        if dec_name:
                            decorator_uses[dec_name] = (
                                decorator_uses.get(dec_name, 0) + 1
                            )
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    class_fields.setdefault(node.name, set()).add(item.target.id)
            for dec in node.decorator_list:
                dec_name = _decorator_name(dec)
                if dec_name:
                    decorator_uses[dec_name] = decorator_uses.get(dec_name, 0) + 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Top-level / nested function (we only consider top-level via the
            # tree.body filter below to avoid pulling in nested helpers).
            pass

    # Top-level functions only (for FR-2 standalone-call resolution AND
    # decorator counts on module-level callables).
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(top.name)
            for dec in top.decorator_list:
                dec_name = _decorator_name(dec)
                if dec_name:
                    decorator_uses[dec_name] = decorator_uses.get(dec_name, 0) + 1

    # __all__ extraction — FR-6 backbone.
    all_exports: set[str] = _extract_all_exports(tree)

    stat = path.stat()
    h = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return CacheEntry(
        file_path=str(path.resolve()),
        mtime=stat.st_mtime,
        sha256_16=h,
        classes=frozenset(classes),
        functions=frozenset(functions),
        error_classes=frozenset(error_classes),
        class_fields=tuple(
            (cls_name, tuple(sorted(fields)))
            for cls_name, fields in sorted(class_fields.items())
        ),
        decorator_uses=tuple(sorted(decorator_uses.items())),
        all_exports=frozenset(all_exports),
    )


def _decorator_name(node: ast.expr) -> str | None:
    """Return the bare last-segment name of a decorator expression.

    ``@dataclass`` → ``"dataclass"``;
    ``@dataclasses.dataclass`` → ``"dataclass"``;
    ``@register("foo")`` → ``"register"``;
    ``@module.cls.bind()`` → ``"bind"``.

    Returns ``None`` for shapes that cannot be resolved to a single name
    (e.g. lambda decorators, subscript expressions).
    """

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _extract_all_exports(tree: ast.Module) -> set[str]:
    """Read module-scope ``__all__ = [...]`` assignments.

    Supports list, tuple, and set literals of string constants. Adds /
    extends operations (``__all__ += [...]``) are recognised too. Anything
    else (e.g. dynamic ``__all__`` construction) is ignored — FR-6's v1.0
    contract is "if it's a literal, we check it" per Q9.2 disposition.
    """

    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    out.update(_strings_in_literal(node.value))
        elif isinstance(node, ast.AugAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
                and isinstance(node.op, ast.Add)
            ):
                out.update(_strings_in_literal(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "__all__" and node.value is not None:
                out.update(_strings_in_literal(node.value))
    return out


def _strings_in_literal(node: ast.expr) -> set[str]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {
            elt.value
            for elt in node.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
    return set()


def _parse_getattr_map(init_py: Path) -> dict[str, str]:
    """Extract a ``{symbol: target_module}`` map from a package's
    ``__init__.py::__getattr__`` body (SDG-203).

    Recognised shapes:

    1. Inline dict literal assigned to a local name (the ``kailash_ml``
       form: ``_engine_map = {"AutoMLEngine": "kailash_ml.engines.automl_engine", ...}``)
       followed by ``importlib.import_module(_engine_map[name])``.
    2. Module-scope ``_LAZY_IMPORT_MAP = {...}`` or ``_LAZY = {...}``
       constant referenced from inside ``__getattr__``.
    3. Inline ``if name == "X": ... importlib.import_module("pkg.subpkg")``
       chains — each branch contributes one ``X → pkg.subpkg`` entry.

    Returns ``{}`` when no ``__getattr__`` exists or the body shape is
    unrecognised — full traversal is M2 per spec § 11.1; v1.0 ships shallow
    detection that catches the W6.5 motivating pattern (the kailash_ml
    legacy-vs-canonical AutoMLEngine map).
    """

    try:
        source = init_py.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        tree = ast.parse(source, filename=str(init_py))
    except SyntaxError:
        return {}

    # Pre-scan module-scope dict assignments so __getattr__ can reference
    # them by name (pattern #2).
    module_dicts: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                d = _string_dict_literal(node.value)
                if d:
                    module_dicts[target.id] = d

    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "__getattr__"):
            continue
        # Pattern #1: inline dict literal assigned within the function.
        local_dicts: dict[str, dict[str, str]] = {}
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and len(sub.targets) == 1:
                target = sub.targets[0]
                if isinstance(target, ast.Name):
                    d = _string_dict_literal(sub.value)
                    if d:
                        local_dicts[target.id] = d
        for d in local_dicts.values():
            out.update(d)
        # Pattern #2: __getattr__ references a module-scope dict.
        for sub in ast.walk(node):
            if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name):
                d = module_dicts.get(sub.value.id)
                if d:
                    out.update(d)
            if isinstance(sub, ast.Compare) and isinstance(sub.left, ast.Name):
                # ``if name in _LAZY_IMPORT_MAP``
                for op, comparator in zip(sub.ops, sub.comparators):
                    if isinstance(op, ast.In) and isinstance(comparator, ast.Name):
                        d = module_dicts.get(comparator.id)
                        if d:
                            out.update(d)
        # Pattern #3: inline ``if name == "X": ... importlib.import_module("pkg")``
        out.update(_walk_inline_if_chain(node))

    return out


def _string_dict_literal(node: ast.expr) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    out: dict[str, str] = {}
    for key, value in zip(node.keys, node.values):
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            out[key.value] = value.value
    return out


def _walk_inline_if_chain(node: ast.FunctionDef) -> dict[str, str]:
    """Pattern #3: walk ``if name == "X": ... importlib.import_module("Y")``.

    Captures the (X, Y) pair. Multi-line branches and nested ifs are
    supported shallowly — full traversal is M2.
    """

    out: dict[str, str] = {}

    def _visit(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                symbol = _name_eq_string_test(stmt.test)
                target_module = _find_import_module_call(stmt.body)
                if symbol is not None and target_module is not None:
                    out[symbol] = target_module
                _visit(stmt.body)
                _visit(stmt.orelse)

    _visit(list(node.body))
    return out


def _name_eq_string_test(test: ast.expr) -> str | None:
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "name"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and isinstance(test.comparators[0].value, str)
    ):
        return test.comparators[0].value
    return None


def _find_import_module_call(stmts: list[ast.stmt]) -> str | None:
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "import_module"
                and len(sub.args) == 1
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[0].value, str)
            ):
                return sub.args[0].value
    return None


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
# Baseline (SDG-301). Spec § 5.1 entry schema; § 5.2 lifecycle states.
#
# JSONL-on-disk, one entry per line, sorted by ``(spec, line, finding,
# symbol)`` so PR diffs are minimal. Identity for diff classification is
# ``(spec, finding, symbol, kind)`` — line is informational only and may
# shift across spec edits without invalidating the entry.
#
# ``origin`` field is REQUIRED to refuse untracked drift (§ 5.4 D4
# mitigation). ``ageout`` defaults to ``added + DEFAULT_AGEOUT_DAYS``.
# ---------------------------------------------------------------------------

from datetime import date, datetime, timedelta

DEFAULT_AGEOUT_DAYS = 90
DEFAULT_BASELINE_PATH = Path(".spec-drift-baseline.jsonl")
DEFAULT_RESOLVED_PATH = Path(".spec-drift-resolved.jsonl")
ORIGIN_TOKEN_RE = re.compile(r"^(F-E\d+-\d+|#\d+(?:-[\w-]+)?|gh-\d+|PR-\d+)$")


@dataclass(frozen=True)
class BaselineEntry:
    spec: str
    line: int
    finding: str
    symbol: str
    kind: str
    origin: str
    added: date
    ageout: date

    def identity(self) -> tuple[str, str, str, str]:
        """Stable identity for diff classification (line is excluded)."""
        return (self.spec, self.finding, self.symbol, self.kind)

    def sort_key(self) -> tuple[str, int, str, str]:
        return (self.spec, self.line, self.finding, self.symbol)

    def to_json(self) -> str:
        return json.dumps(
            {
                "spec": self.spec,
                "line": self.line,
                "finding": self.finding,
                "symbol": self.symbol,
                "kind": self.kind,
                "origin": self.origin,
                "added": self.added.isoformat(),
                "ageout": self.ageout.isoformat(),
            },
            sort_keys=True,
        )

    @classmethod
    def from_finding(
        cls,
        finding: Finding,
        *,
        origin: str,
        added: date | None = None,
        ageout_days: int = DEFAULT_AGEOUT_DAYS,
    ) -> BaselineEntry:
        d_added = added or date.today()
        d_ageout = d_added + timedelta(days=ageout_days)
        return cls(
            spec=finding.spec_path,
            line=finding.line,
            finding=finding.fr_code,
            symbol=finding.symbol,
            kind=finding.kind,
            origin=origin,
            added=d_added,
            ageout=d_ageout,
        )


REQUIRED_BASELINE_FIELDS: tuple[str, ...] = (
    "spec",
    "line",
    "finding",
    "symbol",
    "kind",
    "origin",
    "added",
    "ageout",
)


def _parse_iso_date(value: str, field: str, lineno: int) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise BaselineParseError(
            f"line {lineno}: field {field!r} not ISO YYYY-MM-DD: {value!r}"
        ) from exc


def _validate_origin(value: str, lineno: int) -> str:
    """Origin MUST be a recognised citation token (§ 5.1 + § 5.4 D4).

    Free-form text is BLOCKED so the baseline cannot accumulate untracked
    entries. Recognised forms: ``F-E2-NN`` (audit finding ID), ``#NNN`` /
    ``#NNN-discovery`` (PR or issue with optional discovery suffix),
    ``gh-NNN`` (GitHub issue), ``PR-NNN`` (cross-repo PR).
    """
    if not isinstance(value, str) or not ORIGIN_TOKEN_RE.match(value):
        raise BaselineParseError(
            f"line {lineno}: origin must match /F-E\\d+-\\d+|#\\d+(?:-...)?|gh-\\d+|"
            f"PR-\\d+/, got {value!r}"
        )
    return value


def read_baseline(path: Path) -> list[BaselineEntry]:
    """Parse ``.spec-drift-baseline.jsonl`` into a sorted list of entries.

    Raises BaselineParseError on malformed JSON or missing required fields
    (spec § 6.1). Empty file ⇒ empty list. Missing file ⇒ empty list (caller
    decides whether to treat absence as error).
    """
    if not path.exists():
        return []
    entries: list[BaselineEntry] = []
    text = path.read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaselineParseError(f"line {lineno}: invalid JSON: {exc.msg}") from exc
        if not isinstance(obj, dict):
            raise BaselineParseError(
                f"line {lineno}: expected object, got {type(obj).__name__}"
            )
        missing = [f for f in REQUIRED_BASELINE_FIELDS if f not in obj]
        if missing:
            raise BaselineParseError(
                f"line {lineno}: missing required fields {missing}"
            )
        try:
            line_no = int(obj["line"])
        except (TypeError, ValueError) as exc:
            raise BaselineParseError(
                f"line {lineno}: field 'line' not int: {obj['line']!r}"
            ) from exc
        entries.append(
            BaselineEntry(
                spec=str(obj["spec"]),
                line=line_no,
                finding=str(obj["finding"]),
                symbol=str(obj["symbol"]),
                kind=str(obj["kind"]),
                origin=_validate_origin(obj["origin"], lineno),
                added=_parse_iso_date(obj["added"], "added", lineno),
                ageout=_parse_iso_date(obj["ageout"], "ageout", lineno),
            )
        )
    entries.sort(key=BaselineEntry.sort_key)
    return entries


def write_baseline(entries: Iterable[BaselineEntry], path: Path) -> None:
    """Write entries to JSONL, sorted, trailing newline.

    Sort is deterministic across runs so PR diffs are minimal — the
    invariant the spec § 5.1 calls out.
    """
    rows = sorted(entries, key=BaselineEntry.sort_key)
    body = "\n".join(e.to_json() for e in rows)
    path.write_text(body + "\n" if rows else "", encoding="utf-8")


@dataclass(frozen=True)
class DiffResult:
    """Total classification of today's findings + baseline entries.

    Every today-finding lands in exactly one of ``new`` / ``pre_existing``;
    every baseline entry lands in exactly one of ``pre_existing`` / ``resolved``
    / ``expired`` / ``expired_2x`` (the WARN/FAIL ageout buckets).

    Note: ``pre_existing`` is reported on BOTH sides — the today-finding (so
    it can be silenced) AND the baseline entry (so the entry's age can be
    inspected).
    """

    new: list[Finding]
    pre_existing: list[Finding]
    resolved: list[BaselineEntry]
    expired: list[BaselineEntry]
    expired_2x: list[BaselineEntry]


def diff_findings(
    today: Iterable[Finding],
    baseline: Iterable[BaselineEntry],
    *,
    today_date: date | None = None,
    ageout_days: int = DEFAULT_AGEOUT_DAYS,
) -> DiffResult:
    """Classify today's findings vs baseline entries (spec § 5.2).

    Identity match is ``(spec, finding, symbol, kind)`` — line excluded so
    spec-edit line shifts don't invalidate baseline entries.
    """
    today_list = list(today)
    baseline_list = list(baseline)
    base_index: dict[tuple[str, str, str, str], BaselineEntry] = {
        b.identity(): b for b in baseline_list
    }
    today_keys = {(f.spec_path, f.fr_code, f.symbol, f.kind) for f in today_list}

    new_findings: list[Finding] = []
    pre_existing: list[Finding] = []
    for f in today_list:
        key = (f.spec_path, f.fr_code, f.symbol, f.kind)
        if key in base_index:
            pre_existing.append(f)
        else:
            new_findings.append(f)

    today_iso = today_date or date.today()
    resolved: list[BaselineEntry] = []
    expired: list[BaselineEntry] = []
    expired_2x: list[BaselineEntry] = []
    for b in baseline_list:
        if b.identity() not in today_keys:
            resolved.append(b)
            continue
        age_days = (today_iso - b.added).days
        if age_days >= 2 * ageout_days:
            expired_2x.append(b)
        elif age_days >= ageout_days:
            expired.append(b)

    return DiffResult(
        new=sorted(new_findings, key=Finding.sort_key),
        pre_existing=sorted(pre_existing, key=Finding.sort_key),
        resolved=sorted(resolved, key=BaselineEntry.sort_key),
        expired=sorted(expired, key=BaselineEntry.sort_key),
        expired_2x=sorted(expired_2x, key=BaselineEntry.sort_key),
    )


def ageout_state(
    entry: BaselineEntry,
    *,
    today: date | None = None,
    ageout_days: int = DEFAULT_AGEOUT_DAYS,
) -> Literal["fresh", "expired", "expired_2x"]:
    """Classify a baseline entry by age (spec § 5.4)."""
    today_iso = today or date.today()
    age = (today_iso - entry.added).days
    if age >= 2 * ageout_days:
        return "expired_2x"
    if age >= ageout_days:
        return "expired"
    return "fresh"


def parse_filter(filter_expr: str | None) -> dict[str, str]:
    """Parse ``--filter origin:F-E2-NN`` / ``spec:foo`` / ``finding:FR-4`` ...

    Returns a dict of allowed predicates. Empty filter ⇒ empty dict
    (matches everything). Multiple predicates can be ``,``-separated.
    """
    if not filter_expr:
        return {}
    out: dict[str, str] = {}
    for part in filter_expr.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise SpecDriftGateError(
                f"--filter: malformed predicate {part!r}; "
                f"expected key:value (e.g., origin:F-E2-12)"
            )
        key, _, value = part.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in {"origin", "spec", "finding", "symbol"}:
            raise SpecDriftGateError(
                f"--filter: unknown key {key!r}; "
                f"allowed: origin / spec / finding / symbol"
            )
        out[key] = value
    return out


def apply_filter(
    entries: Iterable[BaselineEntry], predicates: dict[str, str]
) -> list[BaselineEntry]:
    if not predicates:
        return list(entries)
    matched: list[BaselineEntry] = []
    for b in entries:
        if predicates.get("origin") and b.origin != predicates["origin"]:
            continue
        if predicates.get("spec") and b.spec != predicates["spec"]:
            continue
        if predicates.get("finding") and b.finding != predicates["finding"]:
            continue
        if predicates.get("symbol") and b.symbol != predicates["symbol"]:
            continue
        matched.append(b)
    return matched


def archive_resolved(
    entries: Iterable[BaselineEntry],
    archive_path: Path,
    *,
    resolved_sha: str,
    resolved_at: date | None = None,
) -> int:
    """Append resolved baseline entries to the audit-trail JSONL.

    Each archive line carries the original baseline-entry fields PLUS
    ``resolved_sha`` + ``resolved_at`` (spec § 5.3 invariant 3 — every
    archived entry cites the resolving commit). Append-only — entries
    already in the archive are kept; resolved-side entries are appended.
    """
    resolved_iso = (resolved_at or date.today()).isoformat()
    rows = list(entries)
    if not rows:
        return 0
    with archive_path.open("a", encoding="utf-8") as fh:
        for b in sorted(rows, key=BaselineEntry.sort_key):
            payload = {
                "spec": b.spec,
                "line": b.line,
                "finding": b.finding,
                "symbol": b.symbol,
                "kind": b.kind,
                "origin": b.origin,
                "added": b.added.isoformat(),
                "ageout": b.ageout.isoformat(),
                "resolved_sha": resolved_sha,
                "resolved_at": resolved_iso,
            }
            fh.write(json.dumps(payload, sort_keys=True) + "\n")
    return len(rows)


def _git_head_sha() -> str:
    """Read the current commit SHA via ``git rev-parse HEAD``.

    Used when ``--refresh-baseline`` is invoked without an explicit
    ``--resolved-by-sha``. Returns ``"unknown"`` if git is unavailable
    or the working tree is not a git repo — the caller's error path
    surfaces a clear message before that fallback ships into the
    archive.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


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
    # SDG-203: B1 / `__getattr__` resolution mismatches ship as
    # ``level="WARN"`` in v1.0 — they highlight a known divergence but do
    # NOT cause exit-code failure. Hard-fail integration is v1.1 per Q9.3
    # disposition (journal 0005).
    level: Literal["FAIL", "WARN"] = "FAIL"

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

# SDG-202 ----------------------------------------------------------------
# FR-5 dataclass-field reference: ``Class.field`` (no parens — the parens
# variant is FR-2's responsibility). Trailing token must start with a lower
# letter or underscore so ``Class.NestedClass`` is NOT treated as a field.
CLASS_FIELD_RE = re.compile(r"^([A-Z][a-zA-Z0-9_]*)\.([a-z_][a-zA-Z0-9_]*)$")

# FR-3 decorator-mention: an inline ``@<name>`` reference. Picked out of a
# backtick'd token like ``@dataclass`` so we know the spec author intended
# a decorator citation rather than prose like "@joe handed me the spec".
DECORATOR_TOKEN_RE = re.compile(r"^@([a-zA-Z_][a-zA-Z0-9_]*)$")
# FR-3 count phrase — ``applied to N functions``, ``decorated 12 methods``,
# ``... 7 sites``. The match group captures the integer count.
DECORATOR_COUNT_PHRASE_RE = re.compile(
    r"\b(\d+)\s+(?:functions?|methods?|callers?|sites?|call\s+sites?|definitions?|"
    r"classes?|usages?|applications?|nodes?)\b",
    re.IGNORECASE,
)

# FR-6 export-claim trigger — strict literal ``in `__all__``` form only.
# Other "export" phrasings (W&B export, CSV export, etc.) are widespread
# in prose and would over-fire; v1.1 will add a tighter symbol-proximity
# check before broadening the trigger. Q9.2 v1.0 conservative scope.
EXPORT_PHRASE_RE = re.compile(r"in\s+`__all__`")

# FR-8 workspace-leak patterns. ``W31 31b`` style shorthands are leaks
# regardless of context. ``workspaces/<dir>/`` paths are leaks UNLESS the
# line carries a legitimate citation prefix (``Origin:``, ``Citation:``,
# ``Source:``, ``Per <path>``, ``See <path>``) or sits inside an excluded
# section (``## Cross-References`` etc., handled by EXCLUSION_PATTERNS).
WORKSPACE_LEAK_RE = re.compile(r"\bW\d+\s+\d+[a-z]?\b")
WORKSPACE_PATH_RE = re.compile(r"workspaces/[\w./-]+")
# SDG-203 fully-qualified-class form: ``pkg.subpkg.module.Symbol``. The
# trailing ``Symbol`` MUST be capitalized (single class), the prefix MUST
# be a chain of lowercase/underscore module segments. ``kailash_ml.AutoMLEngine``
# (2-segment form) is captured too so packages that expose a symbol
# directly at the top level are checked.
FQ_CLASS_RE = re.compile(
    r"^([a-z_][a-zA-Z0-9_]*)((?:\.[a-z_][a-zA-Z0-9_]*)*)\.([A-Z][a-zA-Z0-9_]*)$"
)

LEGITIMATE_CITATION_PREFIXES: tuple[str, ...] = (
    "Origin:",
    "Citation:",
    "Source:",
    "Cross-Reference:",
    "Per ",
    "See ",
    "see ",
    "see also:",
    "From:",
    "Authority:",
    # v2 spec meta-header convention — used by every realigned spec to
    # record "DRAFT at workspaces/<draft-path>" before promotion.
    "Status:",
    "Supersedes:",
)

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
    """Drive every sweep over *sections*.

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
            if line_negated:
                continue
            # FR-3: decorator application + count claim. Operates on the
            # full line because it requires correlating a decorator token
            # with a count phrase that may sit either side of the @-token.
            if "FR-3" in section.matched_frs:
                _sweep_fr3_decorator_count(
                    line=line,
                    line_no=line_no,
                    spec_path=spec_path,
                    cache=cache,
                    findings=findings,
                )
            # FR-6: __all__ membership. Trigger requires the literal
            # ``__all__`` mention so prose like "exported under …" does
            # not over-fire (per Q9.2 v1.0 conservative scope).
            if "FR-6" in section.matched_frs:
                _sweep_fr6_all_membership(
                    line=line,
                    line_no=line_no,
                    spec_path=spec_path,
                    overrides_for_section=overrides_by_section.get(sec_idx, {}),
                    cache=cache,
                    findings=findings,
                )

    # FR-8: workspace-artifact leak detection. Walks the WHOLE document
    # because a leaked workspace ID is wrong everywhere — section
    # allowlist does not gate it. Excluded sections (Cross-References,
    # Origin, Conformance Checklist) and fenced code blocks are silent.
    _sweep_fr8_workspace_leaks(
        spec_path=spec_path,
        spec_text=spec_text,
        sections=sections,
        findings=findings,
    )

    # SDG-203: B1 ``__getattr__``-resolution sweep. WARN-only in v1.0.
    _sweep_b1_getattr_resolution(
        spec_path=spec_path,
        spec_text=spec_text,
        sections=sections,
        cache=cache,
        findings=findings,
    )

    findings.sort(key=Finding.sort_key)
    return findings


# ---------------------------------------------------------------------------
# Line-level sweeps (SDG-202).
# ---------------------------------------------------------------------------


def _sweep_fr3_decorator_count(
    *,
    line: str,
    line_no: int,
    spec_path: Path,
    cache: SymbolIndex,
    findings: list[Finding],
) -> None:
    """Verify ``@decorator applied to N functions`` style claims.

    Fires only when the line carries BOTH a backticked ``@<name>`` token
    AND a count phrase like ``5 functions`` / ``12 sites``. Conservative on
    purpose: prose mentions of decorators without counts (and vice versa)
    are silent.
    """

    count_match = DECORATOR_COUNT_PHRASE_RE.search(line)
    if count_match is None:
        return
    expected = int(count_match.group(1))

    decorator_names: list[str] = []
    for token in BACKTICK_TOKEN_RE.findall(line):
        m = DECORATOR_TOKEN_RE.match(token.strip())
        if m is not None:
            decorator_names.append(m.group(1))
    if not decorator_names:
        return

    for dec_name in decorator_names:
        actual = cache.decorator_counts.get(dec_name, 0)
        if actual != expected:
            findings.append(
                Finding(
                    spec_path=str(spec_path),
                    line=line_no,
                    fr_code="FR-3",
                    symbol=f"@{dec_name}",
                    kind="decorator",
                    message=(
                        f"FR-3: spec claims {expected} application(s) of "
                        f"@{dec_name} at {spec_path}:{line_no} but the "
                        f"source tree has {actual} (counted across all "
                        f"manifest source roots)"
                    ),
                )
            )


def _sweep_fr6_all_membership(
    *,
    line: str,
    line_no: int,
    spec_path: Path,
    overrides_for_section: dict[tuple[str, str], OverrideDirective],
    cache: SymbolIndex,
    findings: list[Finding],
) -> None:
    """Verify ``in `__all__` `` claims against the union of declared exports.

    Only fires when the line literally references ``__all__`` (the strongest
    trigger). The line's backticked Class-shaped symbols are checked for
    membership in the union of every package's ``__all__``.
    """

    if EXPORT_PHRASE_RE.search(line) is None:
        return

    for token in BACKTICK_TOKEN_RE.findall(line):
        token = token.strip()
        if not token:
            continue
        # __all__ entries are typically class names (Capitalized) but may
        # also be lowercase function names. Accept either shape, exclude
        # the literal ``__all__`` token itself, and skip stop-list noise.
        if token == "__all__":
            continue
        if token in STOP_LIST or token in PROSE_STOP_LIST:
            continue
        # Restrict to "looks-like-a-symbol" tokens: a Python identifier.
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
            continue
        # Dunder names are language hooks, never canonical exports.
        if token.startswith("__") and token.endswith("__"):
            continue
        if _suppressed(overrides_for_section, "export", token):
            continue
        if token in cache.all_exports:
            continue
        findings.append(
            Finding(
                spec_path=str(spec_path),
                line=line_no,
                fr_code="FR-6",
                symbol=token,
                kind="export",
                message=(
                    f"FR-6: {token} cited at {spec_path}:{line_no} as "
                    f"exported but not present in any package's "
                    f"__all__ list (union scan across manifest source roots)"
                ),
            )
        )


def _sweep_fr8_workspace_leaks(
    *,
    spec_path: Path,
    spec_text: str,
    sections: list[Section],
    findings: list[Finding],
) -> None:
    """Catch leaked workspace artefact references in shipped specs.

    ``W31 31b`` shorthand IDs are unconditional leaks — there is no
    legitimate prose context for them. ``workspaces/<dir>/`` paths are
    leaks UNLESS the line carries a citation prefix (``Origin:``,
    ``Citation:``, ``Per <path>``, ``See <path>``) OR sits inside an
    excluded section heading (``## Cross-References`` and friends, set in
    EXCLUSION_PATTERNS) OR inside a fenced code block.
    """

    excluded_ranges: list[tuple[int, int]] = []
    for section in sections:
        if _is_excluded(section.heading):
            excluded_ranges.append((section.heading_line, section.body_end))

    def _is_excluded_line(line_no: int) -> bool:
        return any(start <= line_no < end for start, end in excluded_ranges)

    def _section_for_line(line_no: int) -> Section | None:
        for section in sections:
            if section.heading_line <= line_no < section.body_end:
                return section
        return None

    lines = spec_text.splitlines()
    in_fence = False
    for line_no, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _is_excluded_line(line_no):
            continue
        # Mirror FR-1/2/4/5/7 negation handling so ``### 7.3 Source-Comment
        # Drift To Clean Up`` and ``### 9.3 No Cross-Process Cost Tracker
        # (Yet)`` style subsections — and paragraph-level "Until then" /
        # "v1-spec'd" / "fabricated" markers — silence FR-8 too.
        section = _section_for_line(line_no)
        if section is not None and _is_in_negated_subsection(section, line_no):
            continue
        if _line_is_negated(lines, line_no):
            continue
        # Skip the spec's own provenance footer (lines beginning with
        # "Origin:" / "Citation:" / "Source:" etc.).
        if any(stripped.startswith(prefix) for prefix in LEGITIMATE_CITATION_PREFIXES):
            continue
        # Inline-cited paths are common in body prose: "see also
        # workspaces/x/y" — silence when the line carries a prose-level
        # citation marker.
        has_citation_marker = any(
            marker in line
            for marker in (
                "Origin:",
                "Citation:",
                "Source:",
                "Cross-Reference:",
                "see also:",
                "Authority:",
            )
        )

        leak_match = WORKSPACE_LEAK_RE.search(line)
        if leak_match is not None:
            leaked = leak_match.group(0)
            findings.append(
                Finding(
                    spec_path=str(spec_path),
                    line=line_no,
                    fr_code="FR-8",
                    symbol=leaked,
                    kind="workspace_leak",
                    message=(
                        f"FR-8: workspace shorthand ID {leaked!r} leaked "
                        f"into shipped spec at {spec_path}:{line_no} — "
                        f"either rewrite the prose without the wave/shard "
                        f"reference or move the line under an excluded "
                        f"section like ## Cross-References"
                    ),
                )
            )

        if has_citation_marker:
            continue
        path_match = WORKSPACE_PATH_RE.search(line)
        if path_match is not None:
            leaked = path_match.group(0)
            findings.append(
                Finding(
                    spec_path=str(spec_path),
                    line=line_no,
                    fr_code="FR-8",
                    symbol=leaked,
                    kind="workspace_path",
                    message=(
                        f"FR-8: workspaces/ path {leaked!r} cited at "
                        f"{spec_path}:{line_no} without an Origin: / "
                        f"Citation: / Per <path> prefix — promote to an "
                        f"explicit citation or move under "
                        f"## Cross-References"
                    ),
                )
            )


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

    if "FR-5" in section.matched_frs:
        m = CLASS_FIELD_RE.match(token)
        if m is not None:
            cls_name, field_name = m.group(1), m.group(2)
            full = f"{cls_name}.{field_name}"
            if _suppressed(overrides_for_section, "field", full):
                return
            # Skip dunder fields (language-mandated) and stop-list classes.
            if field_name.startswith("__") and field_name.endswith("__"):
                return
            if cls_name in STOP_LIST or cls_name in PROSE_STOP_LIST:
                return
            # Class must exist; if missing, defer to FR-1's surface so we do
            # not double-emit (FR-1 already flags missing classes).
            if cls_name not in cache.classes and cls_name not in cache.error_classes:
                return
            # Field present on the class? AnnAssign-only per Q9.2 v1.0 scope
            # (Pydantic / attrs detection is v1.1). FR-5 stays silent if the
            # class has zero declared AnnAssign fields — the class is likely
            # not a dataclass-style record at all.
            fields_on_class = cache.class_fields.get(cls_name, set())
            if not fields_on_class:
                return
            if field_name not in fields_on_class:
                findings.append(
                    Finding(
                        spec_path=str(spec_path),
                        line=line_no,
                        fr_code="FR-5",
                        symbol=full,
                        kind="field",
                        message=(
                            f"FR-5: field {full} cited at "
                            f"{spec_path}:{line_no} not declared as AnnAssign "
                            f"on class {cls_name} (v1.0 scope = AnnAssign-only "
                            f"per spec § 11.5; Pydantic / attrs detection v1.1)"
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
# SDG-203: B1 ``__getattr__`` resolution sweep.
#
# Day-1 CRIT mitigation per redteam REQ-HIGH-1 + journal 0005 disposition.
# When a spec asserts a fully-qualified path like ``kailash_ml.automl.engine.AutoMLEngine``
# AND the symbol resolves through a different module via the package's
# ``__getattr__`` lazy-import map (e.g. legacy ``kailash_ml.engines.automl_engine``),
# emit a B1-class WARN. WARN-only in v1.0 — exit code stays 0 unless other
# FAIL findings exist. Dual-emit coherence with FR-6 per redteam HIGH-2:
# when the symbol is also in ``__all__``, the WARN message cross-references
# that signal so operators see both attached to one symbol.
# ---------------------------------------------------------------------------


def _sweep_b1_getattr_resolution(
    *,
    spec_path: Path,
    spec_text: str,
    sections: list[Section],
    cache: SymbolIndex,
    findings: list[Finding],
) -> None:
    if not cache.getattr_resolution:
        return

    excluded_ranges: list[tuple[int, int]] = []
    for section in sections:
        if _is_excluded(section.heading):
            excluded_ranges.append((section.heading_line, section.body_end))

    def _is_excluded_line(line_no: int) -> bool:
        return any(start <= line_no < end for start, end in excluded_ranges)

    def _section_for_line(line_no: int) -> Section | None:
        for section in sections:
            if section.heading_line <= line_no < section.body_end:
                return section
        return None

    lines = spec_text.splitlines()
    in_fence = False
    # Dedupe per (pkg, symbol). Earliest cite wins so the WARN points at
    # the first place the spec author asserted the canonical FQ path.
    seen: set[tuple[str, str]] = set()

    for line_no, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _is_excluded_line(line_no):
            continue
        section = _section_for_line(line_no)
        if section is not None and _is_in_negated_subsection(section, line_no):
            continue
        if _line_is_negated(lines, line_no):
            continue

        for token in BACKTICK_TOKEN_RE.findall(line):
            token = token.strip()
            if not token:
                continue
            m = FQ_CLASS_RE.match(token)
            if m is None:
                continue
            pkg_root, middle, symbol = m.group(1), m.group(2), m.group(3)

            getattr_map = cache.getattr_resolution.get(pkg_root)
            if getattr_map is None:
                continue
            actual = getattr_map.get(symbol)
            if actual is None:
                continue

            # Build the spec's expected module: ``pkg_root`` plus the
            # middle dotted path (which carries a leading dot if non-empty).
            expected = f"{pkg_root}{middle}" if middle else pkg_root
            if expected == actual:
                continue
            if (pkg_root, symbol) in seen:
                continue
            seen.add((pkg_root, symbol))

            # FR-6 dual-emit coherence per redteam HIGH-2.
            in_all = symbol in cache.all_exports
            fr6_note = f" (FR-6 PASS — {symbol} is in __all__)" if in_all else ""
            findings.append(
                Finding(
                    spec_path=str(spec_path),
                    line=line_no,
                    fr_code="B1",
                    symbol=f"{pkg_root}.{symbol}",
                    kind="getattr_resolution",
                    level="WARN",
                    message=(
                        f"B1: {pkg_root}.{symbol} resolves via "
                        f"{pkg_root}.__getattr__ to '{actual}' but the spec "
                        f"asserts '{expected}'{fr6_note} — flip the "
                        f"__getattr__ map entry to '{expected}' or update "
                        f"the spec to match the actual resolution"
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Output formatting (SDG-302). ADR-6 fix-hint format: every FAIL finding
# carries a one-line ``→ fix: (a) ..., OR (b) ..., OR (c) ...`` triad
# (parallel structure, no truncation — invariant 1). The per-FR catalog
# below is the single source of fix-hint text; emitters dispatch through
# ``fix_hint_for(finding)`` so JSON / GitHub / human variants stay aligned.
# ---------------------------------------------------------------------------


FIX_HINT_CATALOG: dict[str, str] = {
    "FR-1": (
        "→ fix: (a) define {symbol} class in the source tree, "
        "OR (b) correct the cite, "
        "OR (c) move under `## Deferred to M2` per `rules/specs-authority.md` § 6"
    ),
    "FR-2": (
        "→ fix: (a) implement {symbol} method, "
        "OR (b) correct the cite, "
        "OR (c) move under `## Deferred to M2`"
    ),
    "FR-3": (
        "→ fix: (a) apply @{symbol} to the asserted call sites, "
        "OR (b) correct the count phrase, "
        "OR (c) move under `## Deferred to M2`"
    ),
    "FR-4": (
        "→ fix: (a) define {symbol} class in the errors module + add eager "
        "re-export per `rules/orphan-detection.md` MUST 6, "
        "OR (b) delete the assertion, "
        "OR (c) move under `## Deferred to M2`"
    ),
    "FR-5": (
        "→ fix: (a) declare {symbol} as an AnnAssign field on the dataclass, "
        "OR (b) correct the cite, "
        "OR (c) move under `## Deferred to M2`"
    ),
    "FR-6": (
        '→ fix: (a) add `"{symbol}"` to the package\'s `__all__`, '
        "OR (b) drop the `in __all__` claim, "
        "OR (c) move under `## Deferred to M2`"
    ),
    "FR-7": (
        "→ fix: (a) create file at {symbol} per `rules/facade-manager-detection.md` "
        "MUST 1, "
        "OR (b) correct the path, "
        "OR (c) mark as Wave 6 follow-up under `## Deferred to M2`"
    ),
    "FR-8": (
        "→ fix: (a) drop the `{symbol}` workspace reference (specs are "
        "pristine), "
        "OR (b) prefix with a legitimate citation marker (`Origin:` / `See` / "
        "`Per`), "
        "OR (c) move under `## Cross-References`"
    ),
    "B1": (
        "→ fix: (a) align the spec assertion with the actual `__getattr__` "
        "resolution for {symbol}, "
        "OR (b) flip the source-side `__getattr__` map, "
        "OR (c) update the spec to the canonical module path"
    ),
}

FIX_HINT_FALLBACK = (
    "→ fix: (a) implement {symbol} in source, "
    "OR (b) correct the cite, "
    "OR (c) move under `## Deferred to M2`"
)


def fix_hint_for(finding: Finding) -> str:
    """Return the ADR-6 fix-hint string for a finding (no leading indent)."""
    template = FIX_HINT_CATALOG.get(finding.fr_code, FIX_HINT_FALLBACK)
    return template.format(symbol=finding.symbol)


def _emit_human(
    findings: list[Finding],
    *,
    spec_paths: list[Path],
    sections_by_spec: dict[str, list[Section]],
    suppressed_count: int = 0,
    expired_warns: list[BaselineEntry] | None = None,
) -> int:
    by_spec: dict[str, list[Finding]] = {}
    for f in findings:
        by_spec.setdefault(f.spec_path, []).append(f)

    for spec_path in spec_paths:
        sp = str(spec_path)
        sec_list = sections_by_spec.get(sp, [])
        scanned = [s.heading for s in sec_list if s.matched_frs]
        spec_findings = by_spec.get(sp, [])
        fail_findings = [f for f in spec_findings if f.level == "FAIL"]
        if spec_findings:
            for f in spec_findings:
                prefix = f.level
                print(
                    f"{prefix} {f.spec_path}:{f.line} {f.fr_code}: "
                    f"{f.symbol} ({f.kind}) — {f.message}"
                )
                if f.level == "FAIL":
                    print(f"  {fix_hint_for(f)}")
        else:
            print(f"PASS {sp} (0 findings across {len(scanned)} scanned sections)")
        if scanned:
            print(f"INFO sections scanned: {scanned}")
        elif not fail_findings:
            print(
                f"WARN {sp}: zero allowlisted sections found. "
                f"Expected one of: ## Surface, ## Construction, ## Public API, "
                f"## Errors, ## Test Contract"
            )

    if suppressed_count:
        print(
            f"INFO baseline grace: {suppressed_count} pre-existing finding(s) "
            f"silenced (run with --no-baseline to surface)"
        )
    if expired_warns:
        for b in expired_warns:
            print(
                f"WARN baseline expired: {b.spec}:{b.line} {b.finding} "
                f"{b.symbol} ({b.kind}) past ageout {b.ageout.isoformat()} "
                f"(origin {b.origin}); resolve or extend justification"
            )

    # Exit 1 only when at least one FAIL-level finding is present. WARN-only
    # output (e.g., B1 ``__getattr__`` divergences, baseline ageout WARNs)
    # returns 0 per Q9.3.
    return 1 if any(f.level == "FAIL" for f in findings) else 0


def _emit_json(
    findings: list[Finding],
    *,
    suppressed_count: int = 0,
    expired_warns: list[BaselineEntry] | None = None,
) -> int:
    """ADR-6 JSON emitter: array of finding objects + meta block.

    Each finding object carries ``{spec, line, finding, symbol, kind,
    severity, message, fix_hint}``. ``severity`` mirrors ``level`` (FAIL /
    WARN). The top-level shape is ``{"meta": {...}, "findings": [...]}``
    so JSON consumers can read both at once.
    """
    findings_out: list[dict] = []
    for f in findings:
        findings_out.append(
            {
                "spec": f.spec_path,
                "line": f.line,
                "finding": f.fr_code,
                "symbol": f.symbol,
                "kind": f.kind,
                "severity": f.level,
                "message": f.message,
                "fix_hint": fix_hint_for(f) if f.level == "FAIL" else None,
            }
        )
    expired_out = []
    for b in expired_warns or []:
        expired_out.append(
            {
                "spec": b.spec,
                "line": b.line,
                "finding": b.finding,
                "symbol": b.symbol,
                "kind": b.kind,
                "origin": b.origin,
                "added": b.added.isoformat(),
                "ageout": b.ageout.isoformat(),
            }
        )
    payload = {
        "meta": {
            "version": VERSION,
            "suppressed_baseline_count": suppressed_count,
            "expired_baseline_count": len(expired_out),
        },
        "findings": findings_out,
        "expired_baseline": expired_out,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if any(f.level == "FAIL" for f in findings) else 0


def _emit_github(
    findings: list[Finding],
    *,
    expired_warns: list[BaselineEntry] | None = None,
) -> int:
    """GitHub Actions annotation format (``::error`` / ``::warning``)."""
    for f in findings:
        severity = "error" if f.level == "FAIL" else "warning"
        # GitHub annotations cannot contain newlines; the fix-hint is appended
        # to the message via " — " so it stays on one line.
        msg = f"{f.fr_code}: {f.symbol} ({f.kind}) — {f.message}"
        if f.level == "FAIL":
            msg = f"{msg} | {fix_hint_for(f)}"
        # GitHub annotation strings escape commas / newlines — replace ``\n``
        # with ``%0A`` so multi-line messages still render.
        msg = msg.replace("\n", "%0A").replace(",", "%2C")
        print(f"::{severity} file={f.spec_path},line={f.line}::{msg}")
    for b in expired_warns or []:
        msg = (
            f"baseline-expired: {b.finding} {b.symbol} ({b.kind}) past "
            f"ageout {b.ageout.isoformat()} (origin {b.origin})"
        )
        msg = msg.replace("\n", "%0A").replace(",", "%2C")
        print(f"::warning file={b.spec},line={b.line}::{msg}")
    return 1 if any(f.level == "FAIL" for f in findings) else 0


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
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument(
        "--resolved-archive",
        type=Path,
        default=DEFAULT_RESOLVED_PATH,
        help="Append-only audit trail of resolved baseline entries.",
    )
    parser.add_argument(
        "--refresh-baseline",
        action="store_true",
        help=(
            "Diff today's findings vs baseline, archive resolved entries to "
            "--resolved-archive, rewrite the baseline without them. Does NOT "
            "auto-add new findings."
        ),
    )
    parser.add_argument(
        "--resolved-by-sha",
        default=None,
        help=(
            "Commit SHA citing the resolution; defaults to `git rev-parse "
            "HEAD`. Used as `resolved_sha` in --resolved-archive entries."
        ),
    )
    parser.add_argument(
        "--filter",
        default=None,
        help=(
            "Scope baseline operations to entries matching origin / spec / "
            "finding (e.g., `--filter origin:F-E2-12`, `--filter spec:specs/"
            "ml-automl.md`, `--filter finding:FR-4`)."
        ),
    )
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("spec_paths", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"spec_drift_gate v{VERSION} (manifest: {DEFAULT_MANIFEST_PATH})")
        return 0

    # Manifest is the single source of source-root + errors-module config
    # (spec § 2.4). Missing or malformed manifest is a typed setup error —
    # propagated to the caller as exit 2 (distinct from exit 1 = findings).
    try:
        manifest = Manifest.load()
    except (ManifestNotFoundError, ManifestSchemaError) as exc:
        print(f"spec_drift_gate: {exc}", file=sys.stderr)
        return 2

    # Resolve target specs from manifest.spec_glob unless overridden by CLI.
    if args.spec_paths:
        spec_paths = [Path(p) for p in args.spec_paths]
    else:
        spec_paths = sorted(Path().glob(manifest.spec_glob))

    cache = SymbolIndex.build(
        [sr.path for sr in manifest.source_roots],
        errors_modules=[ErrorsModule(manifest.errors_default)]
        + [ErrorsModule(o.path) for o in manifest.errors_overrides],
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

    # Filter predicates affect both --refresh-baseline scoping AND the
    # in-progress baseline diff. Parse early so a malformed --filter aborts
    # before any I/O.
    try:
        filter_predicates = parse_filter(args.filter)
    except SpecDriftGateError as exc:
        print(f"spec_drift_gate: {exc}", file=sys.stderr)
        return 2

    # --refresh-baseline (SDG-303). Run sweeps with grace bypassed, diff
    # against baseline, archive resolved entries to --resolved-archive,
    # rewrite baseline without them. NEW findings are NOT auto-added —
    # operator runs sweep without --refresh-baseline + git-add to bless.
    if args.refresh_baseline:
        try:
            baseline = read_baseline(args.baseline)
        except BaselineParseError as exc:
            print(f"spec_drift_gate: baseline: {exc}", file=sys.stderr)
            return 2
        if filter_predicates:
            scoped_baseline = apply_filter(baseline, filter_predicates)
            scoped_keys = {b.identity() for b in scoped_baseline}
            untouched = [b for b in baseline if b.identity() not in scoped_keys]
        else:
            scoped_baseline = baseline
            untouched = []
        fail_findings = [f for f in all_findings if f.level == "FAIL"]
        diff = diff_findings(fail_findings, scoped_baseline)
        resolved_sha = args.resolved_by_sha or _git_head_sha()
        archived = archive_resolved(
            diff.resolved,
            args.resolved_archive,
            resolved_sha=resolved_sha,
        )
        # Keep the entries that are still present today, plus any untouched
        # entries (when --filter narrows scope).
        kept = [
            b
            for b in scoped_baseline
            if b.identity() not in {r.identity() for r in diff.resolved}
        ]
        write_baseline(kept + untouched, args.baseline)
        print(
            f"refresh-baseline: archived {archived} resolved entries to "
            f"{args.resolved_archive} (resolved_sha={resolved_sha}); baseline "
            f"now has {len(kept) + len(untouched)} entries."
        )
        if diff.new:
            print(
                f"refresh-baseline: {len(diff.new)} NEW finding(s) NOT "
                f"auto-added — review with `python scripts/spec_drift_gate.py "
                f"--no-baseline` and `git add {args.baseline}` to bless."
            )
        return 0

    # Baseline grace (FR-11). Pre-existing FAIL findings registered in the
    # baseline are silenced; only NEW findings reach the emitters as FAIL.
    # ``--no-baseline`` bypasses the diff entirely. WARN-level findings are
    # never silenced (they are advisory, never gate exit code).
    suppressed_count = 0
    expired_warns: list[BaselineEntry] = []
    if not args.no_baseline:
        try:
            baseline = read_baseline(args.baseline)
        except BaselineParseError as exc:
            print(f"spec_drift_gate: baseline: {exc}", file=sys.stderr)
            return 2
        if baseline:
            fail_findings = [f for f in all_findings if f.level == "FAIL"]
            other_findings = [f for f in all_findings if f.level != "FAIL"]
            diff = diff_findings(fail_findings, baseline)
            suppressed_count = len(diff.pre_existing)
            expired_warns = list(diff.expired)
            # 2× ageout entries are surfaced as fresh FAIL findings (force
            # resolution per spec § 5.2). Reuse the baseline entry's metadata.
            forced_fails: list[Finding] = []
            for b in diff.expired_2x:
                forced_fails.append(
                    Finding(
                        spec_path=b.spec,
                        line=b.line,
                        fr_code=b.finding,
                        symbol=b.symbol,
                        kind=b.kind,
                        message=(
                            f"baseline entry past 2× ageout "
                            f"({b.ageout.isoformat()}) — force resolution"
                        ),
                        level="FAIL",
                    )
                )
            all_findings = sorted(
                diff.new + forced_fails + other_findings,
                key=Finding.sort_key,
            )

    if args.format == "human":
        return _emit_human(
            all_findings,
            spec_paths=spec_paths,
            sections_by_spec=sections_by_spec,
            suppressed_count=suppressed_count,
            expired_warns=expired_warns,
        )
    if args.format == "json":
        return _emit_json(
            all_findings,
            suppressed_count=suppressed_count,
            expired_warns=expired_warns,
        )
    if args.format == "github":
        return _emit_github(all_findings, expired_warns=expired_warns)

    return 0


if __name__ == "__main__":
    sys.exit(main())
