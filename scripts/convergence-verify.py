#!/usr/bin/env python3
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Verify architectural convergence assertions for Kailash SDK v3.0.

Checks that the codebase satisfies the post-convergence invariants
established by SPEC-01 through SPEC-10. Run with:

    uv run python scripts/convergence-verify.py

Exit 0 if all checks pass, exit 1 with details on failure.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src" / "kailash"
PACKAGES_DIR = REPO_ROOT / "packages"

# Stale import patterns that should not exist anywhere in src/ or packages/
STALE_IMPORT_PATTERNS: list[tuple[str, str]] = [
    (
        r"from\s+kailash_trust_shim",
        "kailash-trust-shim removed in v3.0; use kailash.trust",
    ),
    (
        r"import\s+kailash_trust_shim",
        "kailash-trust-shim removed in v3.0; use kailash.trust",
    ),
]

# PACT N4/N5/N6 types that MUST be exported from kailash.trust.pact
PACT_N4_N5_N6_EXPORTS: list[tuple[str, str]] = [
    # N4 — Tiered Audit
    ("TieredAuditDispatcher", "N4 tiered audit dispatcher"),
    ("AuditChain", "N4 audit chain"),
    # N5 — Observation
    ("Observation", "N5 observation event"),
    ("ObservationSink", "N5 observation sink protocol"),
    ("InMemoryObservationSink", "N5 in-memory observation sink"),
    # N5 — EATP Emitter
    ("PactEatpEmitter", "N5 EATP emitter protocol"),
    ("InMemoryPactEmitter", "N5 in-memory EATP emitter"),
]

# Stub markers forbidden in production code (tests excluded)
STUB_MARKERS = re.compile(
    r"\b(TODO|FIXME|STUB|XXX|HACK)\b",
    re.IGNORECASE,
)

# Directories to scan for stub markers (src/ only, not tests)
STUB_SCAN_DIRS: list[Path] = [
    SRC_DIR,
    *(p / "src" for p in PACKAGES_DIR.iterdir() if p.is_dir() and (p / "src").is_dir()),
]

# Test file patterns to exclude from stub scanning
TEST_FILE_PATTERNS = re.compile(
    r"(^test_|_test\.py$|\.test\.py$|\.spec\.py$|__tests__|/tests/)"
)


class Failure(NamedTuple):
    check: str
    file: str
    line: int
    message: str


def python_files(directory: Path) -> list[Path]:
    """Yield all .py files under directory, excluding __pycache__."""
    results = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != "__pycache__" and d != ".git"]
        for f in files:
            if f.endswith(".py"):
                results.append(Path(root) / f)
    return results


def is_test_file(path: Path) -> bool:
    """Check if a file is a test file (excluded from stub checks)."""
    rel = str(path)
    return bool(TEST_FILE_PATTERNS.search(rel))


# ---------------------------------------------------------------------------
# Check 1: No stale imports
# ---------------------------------------------------------------------------


def check_stale_imports() -> list[Failure]:
    """Verify no stale imports exist in src/ or packages/."""
    failures: list[Failure] = []
    scan_dirs = [SRC_DIR] + [
        p / "src" for p in PACKAGES_DIR.iterdir() if p.is_dir() and (p / "src").is_dir()
    ]
    for scan_dir in scan_dirs:
        for py_file in python_files(scan_dir):
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(content.splitlines(), start=1):
                for pattern, msg in STALE_IMPORT_PATTERNS:
                    if re.search(pattern, line):
                        failures.append(
                            Failure(
                                check="stale-imports",
                                file=str(py_file.relative_to(REPO_ROOT)),
                                line=lineno,
                                message=msg,
                            )
                        )
    return failures


# ---------------------------------------------------------------------------
# Check 2: Consistent version patterns across packages
# ---------------------------------------------------------------------------


def check_version_consistency() -> list[Failure]:
    """Verify all packages have version strings in pyproject.toml."""
    failures: list[Failure] = []
    version_pattern = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)

    # Root pyproject.toml
    root_pyproject = REPO_ROOT / "pyproject.toml"
    if root_pyproject.exists():
        content = root_pyproject.read_text(encoding="utf-8")
        match = version_pattern.search(content)
        if not match:
            failures.append(
                Failure(
                    check="version-consistency",
                    file="pyproject.toml",
                    line=0,
                    message="No version found in root pyproject.toml",
                )
            )

    # Sub-packages
    for pkg_dir in sorted(PACKAGES_DIR.iterdir()):
        if not pkg_dir.is_dir():
            continue
        pyproject = pkg_dir / "pyproject.toml"
        if not pyproject.exists():
            continue
        content = pyproject.read_text(encoding="utf-8")
        match = version_pattern.search(content)
        if not match:
            failures.append(
                Failure(
                    check="version-consistency",
                    file=str(pyproject.relative_to(REPO_ROOT)),
                    line=0,
                    message=f"No version found in {pkg_dir.name}/pyproject.toml",
                )
            )
        else:
            version = match.group(1)
            # Verify it looks like a valid semver-ish pattern
            if not re.match(r"^\d+\.\d+\.\d+", version):
                failures.append(
                    Failure(
                        check="version-consistency",
                        file=str(pyproject.relative_to(REPO_ROOT)),
                        line=0,
                        message=f"Version '{version}' does not follow semver pattern",
                    )
                )

    return failures


# ---------------------------------------------------------------------------
# Check 3: PACT exports include N4/N5/N6 types
# ---------------------------------------------------------------------------


def check_pact_exports() -> list[Failure]:
    """Verify kailash.trust.pact.__init__.py exports N4/N5/N6 types."""
    failures: list[Failure] = []
    pact_init = SRC_DIR / "trust" / "pact" / "__init__.py"

    if not pact_init.exists():
        failures.append(
            Failure(
                check="pact-exports",
                file="src/kailash/trust/pact/__init__.py",
                line=0,
                message="PACT __init__.py does not exist",
            )
        )
        return failures

    content = pact_init.read_text(encoding="utf-8")

    for symbol, description in PACT_N4_N5_N6_EXPORTS:
        # Check both import and __all__
        if symbol not in content:
            failures.append(
                Failure(
                    check="pact-exports",
                    file="src/kailash/trust/pact/__init__.py",
                    line=0,
                    message=f"Missing N4/N5/N6 export: {symbol} ({description})",
                )
            )

    return failures


# ---------------------------------------------------------------------------
# Check 4: No TODO/FIXME/STUB markers in src/ (excluding tests)
# ---------------------------------------------------------------------------


def check_stub_markers() -> list[Failure]:
    """Verify no stub markers in production source (tests excluded)."""
    failures: list[Failure] = []

    for scan_dir in STUB_SCAN_DIRS:
        for py_file in python_files(scan_dir):
            if is_test_file(py_file):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for lineno, line in enumerate(content.splitlines(), start=1):
                # Skip comments that are documenting rules about stubs
                # (e.g., docstrings explaining what is blocked)
                stripped = line.strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    continue

                match = STUB_MARKERS.search(line)
                if match:
                    marker = match.group(1).upper()
                    # Distinguish real TODOs from references in strings/docs
                    # Only flag comments (lines starting with # after stripping)
                    # and inline comments
                    code_line = line.split("#", 1)
                    if len(code_line) > 1:
                        comment_part = code_line[1]
                        if STUB_MARKERS.search(comment_part):
                            failures.append(
                                Failure(
                                    check="stub-markers",
                                    file=str(py_file.relative_to(REPO_ROOT)),
                                    line=lineno,
                                    message=f"{marker} marker in comment",
                                )
                            )

    return failures


# ---------------------------------------------------------------------------
# Check 5: Absolute imports (no relative imports in src/)
# ---------------------------------------------------------------------------


def check_absolute_imports() -> list[Failure]:
    """Verify no relative imports in src/kailash/."""
    failures: list[Failure] = []
    relative_import_pattern = re.compile(r"^\s*from\s+\.\.?[\w.]*\s+import\s+")

    for py_file in python_files(SRC_DIR):
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            if relative_import_pattern.match(line):
                failures.append(
                    Failure(
                        check="absolute-imports",
                        file=str(py_file.relative_to(REPO_ROOT)),
                        line=lineno,
                        message=f"Relative import: {line.strip()!r}",
                    )
                )

    return failures


# ---------------------------------------------------------------------------
# Check 6: DriftMonitor API surface
# ---------------------------------------------------------------------------


def check_drift_monitor_api() -> list[Failure]:
    """Verify DriftMonitor uses set_reference_data (not set_reference)."""
    failures: list[Failure] = []
    drift_monitor_file = (
        PACKAGES_DIR
        / "kailash-ml"
        / "src"
        / "kailash_ml"
        / "engines"
        / "drift_monitor.py"
    )

    if not drift_monitor_file.exists():
        # Package may not be present; skip
        return failures

    content = drift_monitor_file.read_text(encoding="utf-8")

    # Verify set_reference_data exists
    if (
        "def set_reference_data(" not in content
        and "async def set_reference_data(" not in content
    ):
        failures.append(
            Failure(
                check="drift-monitor-api",
                file=str(drift_monitor_file.relative_to(REPO_ROOT)),
                line=0,
                message="DriftMonitor.set_reference_data() method not found",
            )
        )

    # Verify old set_reference shim is gone (method def, not references in docs/strings)
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if re.match(r"(async\s+)?def\s+set_reference\s*\(", stripped):
            # This is the old method name as a def — should not exist
            if "set_reference_data" not in stripped:
                failures.append(
                    Failure(
                        check="drift-monitor-api",
                        file=str(drift_monitor_file.relative_to(REPO_ROOT)),
                        line=lineno,
                        message="Old set_reference() method still defined (should be set_reference_data)",
                    )
                )

    return failures


# ---------------------------------------------------------------------------
# Check 7: Runtime exports (EventLoopWatchdog, ProgressUpdate)
# ---------------------------------------------------------------------------


def check_runtime_exports() -> list[Failure]:
    """Verify EventLoopWatchdog and ProgressUpdate are exported from runtime."""
    failures: list[Failure] = []
    runtime_init = SRC_DIR / "runtime" / "__init__.py"

    if not runtime_init.exists():
        failures.append(
            Failure(
                check="runtime-exports",
                file="src/kailash/runtime/__init__.py",
                line=0,
                message="Runtime __init__.py does not exist",
            )
        )
        return failures

    content = runtime_init.read_text(encoding="utf-8")

    for symbol in [
        "EventLoopWatchdog",
        "StallReport",
        "ProgressUpdate",
        "ProgressRegistry",
        "report_progress",
    ]:
        if symbol not in content:
            failures.append(
                Failure(
                    check="runtime-exports",
                    file="src/kailash/runtime/__init__.py",
                    line=0,
                    message=f"Missing runtime export: {symbol}",
                )
            )

    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print("Kailash SDK Convergence Verification")
    print("=" * 50)
    print()

    all_failures: list[Failure] = []
    checks = [
        ("Stale imports", check_stale_imports),
        ("Version consistency", check_version_consistency),
        ("PACT N4/N5/N6 exports", check_pact_exports),
        ("Stub markers in src/", check_stub_markers),
        ("Absolute imports in src/kailash/", check_absolute_imports),
        ("DriftMonitor API surface", check_drift_monitor_api),
        ("Runtime exports (watchdog + progress)", check_runtime_exports),
    ]

    for name, check_fn in checks:
        failures = check_fn()
        status = "PASS" if not failures else "FAIL"
        count_msg = f" ({len(failures)} issues)" if failures else ""
        print(f"  [{status}] {name}{count_msg}")
        all_failures.extend(failures)

    print()

    if not all_failures:
        print("All convergence checks passed.")
        return 0

    print(f"FAILED: {len(all_failures)} issue(s) found")
    print("-" * 50)

    # Group by check
    by_check: dict[str, list[Failure]] = {}
    for f in all_failures:
        by_check.setdefault(f.check, []).append(f)

    for check_name, failures in by_check.items():
        print(f"\n  [{check_name}]")
        for f in failures[:20]:  # Cap output per check
            loc = f"{f.file}:{f.line}" if f.line else f.file
            print(f"    {loc}: {f.message}")
        if len(failures) > 20:
            print(f"    ... and {len(failures) - 20} more")

    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
