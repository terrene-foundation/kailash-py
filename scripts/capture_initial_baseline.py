#!/usr/bin/env python3
"""One-time capture of post-Wave-6.5 spec drift baseline (SDG-502).

Runs the spec drift gate against the full ``specs/`` corpus with
``--no-baseline`` to enumerate every pre-existing FAIL, then writes
``.spec-drift-baseline.jsonl`` with each entry tagged:

* ``origin``  — the most precise audit citation we can derive:

  - ``F-E1-NN`` for specs audited under W5-E1 (kailash-ml engines/registry/
    serving/diagnostics/tracking/autolog/rl/backends).
  - ``F-E2-NN`` for specs audited under W5-E2 (ml-automl, ml-drift,
    ml-feature-store, ml-dashboard, alignment-*, align-ml-integration,
    kailash-core-ml-integration, diagnostics-catalog).
  - ``#640-discovery`` for specs covered by W5-A/B/D/F shards or by
    no shard at all. The gate's origin regex
    (``F-E\\d+-\\d+|#\\d+(?:-...)?|gh-\\d+|PR-\\d+``) does NOT accept
    ``F-A-NN`` / ``F-B-NN`` / ``F-F-NN`` tokens, so the umbrella issue
    citation is the structural fallback. See
    ``rules/git.md`` § Issue Closure Discipline.

* ``added``   — capture date (today, ISO YYYY-MM-DD).
* ``ageout``  — added + 90 days (DEFAULT_AGEOUT_DAYS in the gate).

The script is **one-time** — re-running it would replace existing
``added`` / ``ageout`` timestamps and reset the grace window. Future
churn flows through ``--refresh-baseline`` instead, which preserves
``added`` for retained entries.

Idempotency guard: refuses to overwrite an existing
``.spec-drift-baseline.jsonl`` unless ``--force`` is passed. The CI
gate workflow (M2 / SDG-601) MUST NOT call this script.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "scripts" / "spec_drift_gate.py"
SPECS_DIR = REPO_ROOT / "specs"
BASELINE_PATH = REPO_ROOT / ".spec-drift-baseline.jsonl"
AUDIT_DIR = REPO_ROOT / "workspaces" / "portfolio-spec-audit" / "04-validate"
AGEOUT_DAYS = 90

# Per-shard prefix → first audit ID parser. The gate's origin regex only
# accepts F-E<digits>-<digits>; tokens from other shards (F-A, F-B, F-F)
# fall back to the umbrella issue citation #640-discovery.
ACCEPTED_SHARD_PREFIXES = ("E1", "E2")
FALLBACK_ORIGIN = "#640-discovery"

# `### F-{shard}-{NN} — {spec_basename} § ...` — spec name may or may not
# have a ``.md`` suffix and may or may not be wrapped in backticks. W5-E2
# uses ``\`ml-automl.md\` §``; W5-E1 uses ``ml-engines-v2 §``. The regex
# captures the bare stem; the lookup map keys both ``stem`` and ``stem.md``
# so resolution by ``Path(spec).name`` works regardless of audit style.
AUDIT_LINE_RE = re.compile(
    r"^### F-(?P<shard>[A-Z]\d?)-(?P<nn>\d+) — `?(?P<spec>[\w\-]+(?:\.md)?)`? §"
)


def _build_spec_to_origin_map() -> dict[str, str]:
    """Walk ``W5-*-findings.md`` and return ``{spec_basename: 'F-EX-NN'}``.

    Picks the LOWEST audit-ID number per spec so the citation is stable
    even when the same spec appears in multiple shards. Specs whose
    only matching shard prefix is outside ``ACCEPTED_SHARD_PREFIXES``
    are absent from the returned map; their findings fall back to
    ``FALLBACK_ORIGIN`` at lookup time.
    """
    mapping: dict[str, tuple[int, str]] = {}
    for path in sorted(AUDIT_DIR.glob("W5-*-findings.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = AUDIT_LINE_RE.match(line)
            if not match:
                continue
            shard = match["shard"]
            if shard not in ACCEPTED_SHARD_PREFIXES:
                continue
            spec = match["spec"]
            nn = int(match["nn"])
            token = f"F-{shard}-{nn:02d}"
            # Normalise both bare-stem (W5-E1: "ml-engines-v2") and
            # explicit-suffix (W5-E2: "ml-automl.md") forms to the
            # ``foo.md`` shape we look up against ``Path(spec).name``.
            key = spec if spec.endswith(".md") else f"{spec}.md"
            existing = mapping.get(key)
            if existing is None or nn < existing[0]:
                mapping[key] = (nn, token)
    return {spec: token for spec, (_, token) in mapping.items()}


def _resolve_origin(spec_path: str, spec_to_origin: dict[str, str]) -> str:
    """Map ``specs/foo.md`` → audit token, falling back to ``#640-discovery``."""
    basename = Path(spec_path).name
    return spec_to_origin.get(basename, FALLBACK_ORIGIN)


def _run_gate() -> list[dict]:
    """Run the gate with ``--no-baseline --format json`` against ``specs/``."""
    spec_files = sorted(str(p.relative_to(REPO_ROOT)) for p in SPECS_DIR.rglob("*.md"))
    if not spec_files:
        raise SystemExit("no spec files under specs/ — aborting")
    cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "python"),
        str(GATE_SCRIPT),
        "--no-baseline",
        "--format",
        "json",
        *spec_files,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    # The gate exits non-zero when there are FAIL findings; that's exactly
    # what we want at capture time. We only fail on stdout-empty / parse-error.
    if not result.stdout.strip():
        sys.stderr.write(
            f"gate produced no stdout (exit {result.returncode}); stderr:\n"
            f"{result.stderr}\n"
        )
        raise SystemExit(1)
    payload = json.loads(result.stdout)
    return payload.get("findings", [])


def _baseline_entry(finding: dict, origin: str, today: date) -> dict:
    """Build the JSONL line; field order matches BaselineEntry.to_json."""
    return {
        "added": today.isoformat(),
        "ageout": (today + timedelta(days=AGEOUT_DAYS)).isoformat(),
        "finding": finding["finding"],
        "kind": finding["kind"],
        "line": finding["line"],
        "origin": origin,
        "spec": finding["spec"],
        "symbol": finding["symbol"],
    }


def _sort_key(entry: dict) -> tuple:
    """Match BaselineEntry.sort_key (spec, line, finding, symbol)."""
    return (entry["spec"], entry["line"], entry["finding"], entry["symbol"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "overwrite existing .spec-drift-baseline.jsonl. The script is "
            "one-time by design; --force is for re-running during the same "
            "capture session if the prior write was incomplete."
        ),
    )
    parser.add_argument(
        "--today",
        help="ISO date used for added/ageout (default: today). For testing.",
    )
    args = parser.parse_args()

    if BASELINE_PATH.exists() and not args.force:
        sys.stderr.write(
            f"{BASELINE_PATH.relative_to(REPO_ROOT)} already exists; "
            f"refusing to overwrite. Pass --force to re-capture.\n"
        )
        return 2

    today = date.fromisoformat(args.today) if args.today else date.today()

    spec_to_origin = _build_spec_to_origin_map()
    findings = _run_gate()

    # FAIL only — WARNs (B1 __getattr__ divergences) are not blocking and
    # MUST NOT join the baseline; future B1 sources resolve in #640
    # follow-ups (see workspaces/spec-drift-gate/.session-notes).
    fail_findings = [f for f in findings if f["severity"] == "FAIL"]

    entries = [
        _baseline_entry(f, _resolve_origin(f["spec"], spec_to_origin), today)
        for f in fail_findings
    ]
    entries.sort(key=_sort_key)

    with BASELINE_PATH.open("w", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps(entry, sort_keys=True) + "\n")

    # Summary for the operator (not parsed by anything).
    by_origin: dict[str, int] = {}
    for e in entries:
        by_origin[e["origin"]] = by_origin.get(e["origin"], 0) + 1

    sys.stderr.write(
        f"wrote {len(entries)} entries to {BASELINE_PATH.relative_to(REPO_ROOT)}\n"
        f"  added:  {today.isoformat()}\n"
        f"  ageout: {(today + timedelta(days=AGEOUT_DAYS)).isoformat()}\n"
        f"  by origin:\n"
    )
    for origin, count in sorted(by_origin.items()):
        sys.stderr.write(f"    {origin:<20} {count}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
