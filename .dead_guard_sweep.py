"""Mechanical dead-guard sweep (issue #2013 sibling sweep).

Enumerates every string-literal attribute probe -- hasattr(x, "N") and
getattr(x, "N", ...) -- in PRODUCTION source, then asks whether "N" is
defined ANYWHERE reachable (this repo OR the installed third-party
packages the probed object could come from).

DISCRIMINATION (rules/instrument-discipline.md MUST-1): a probed name is
reported DEAD only when the definition search returns ZERO hits across
both corpora. For a live name (e.g. "health_check", defined in
src/kailash/servers/workflow_server.py) the search returns a non-empty
hit list and the name is classified LIVE. The instrument therefore
returns a DIFFERENT result depending on whether the definition exists --
which is exactly the falsifying condition. If every probed name were
defined, the DEAD table would be empty.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Probe sites: production source only. Tests probing a test double are noise.
PROD_ROOTS = [ROOT / "src" / "kailash"] + sorted(
    (ROOT / "packages").glob("*/src")
)


def collect_probes() -> dict[str, list[tuple[str, int, str]]]:
    """name -> [(relpath, lineno, probe_kind)]"""
    probes: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for root in PROD_ROOTS:
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if not isinstance(fn, ast.Name) or fn.id not in ("hasattr", "getattr"):
                    continue
                if len(node.args) < 2:
                    continue
                attr = node.args[1]
                if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                    continue
                probes[attr.value].append(
                    (str(path.relative_to(ROOT)), node.lineno, fn.id)
                )
    return probes


def definition_patterns(name: str) -> str:
    """Regex matching any plausible Python definition of attribute `name`."""
    n = re.escape(name)
    return (
        rf"(^|[^\w])def\s+{n}\s*\("          # method / function
        rf"|^\s*{n}\s*(:[^=]+)?=[^=]"        # class attr / assignment / dataclass field
        rf"|^\s*{n}\s*:\s*\w"                # annotated field
        rf"|setattr\([^,]+,\s*[\"']{n}[\"']"  # dynamic assignment
        rf"|[\"']{n}[\"']\s*:"               # dict-backed __getattr__ table
    )


def search(pattern: str, paths: list[str]) -> list[str]:
    existing = [p for p in paths if Path(p).exists()]
    if not existing:
        return []
    proc = subprocess.run(
        ["grep", "-rEn", "--include=*.py", "--include=*.pyi", pattern, *existing],
        capture_output=True,
        text=True,
    )
    return [ln for ln in proc.stdout.splitlines() if ln.strip()][:6]


def main() -> int:
    probes = collect_probes()

    repo_paths = ["src", "packages", "tests"]
    # The worktree has no venv of its own; the installed third-party corpus
    # lives in the primary checkout's venv. Passed via --deps.
    site_packages = sys.argv[1:]

    dead: list[tuple[str, list[tuple[str, int, str]]]] = []
    live = 0
    thirdparty = 0

    for name in sorted(probes):
        pat = definition_patterns(name)
        if search(pat, repo_paths):
            live += 1
            continue
        if site_packages and search(pat, site_packages):
            thirdparty += 1
            continue
        dead.append((name, probes[name]))

    print(f"probed names       : {len(probes)}")
    print(f"  defined in-repo  : {live}")
    print(f"  defined in deps  : {thirdparty}")
    print(f"  ZERO definitions : {len(dead)}")
    print()
    print("=== DEAD GUARDS (probed name has NO definition anywhere) ===")
    for name, sites in dead:
        print(f"\n{name!r}")
        for relpath, lineno, kind in sites:
            print(f"    {kind:<7} {relpath}:{lineno}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
