#!/usr/bin/env python3
"""Census PR-reachable CI jobs and make unremarked fan-out loud.

loom#1877 — "CI jobs accrete one unremarkable job at a time, and nothing says
anything at the moment each is added."

Measured in this repo on PR #2205 (2026-08-21): **25 runner-consuming jobs**
across 5 workflow runs, of which **3** gate anything (the branch-protection
required contexts). Nine of those 25 were an exact duplicate of another nine —
the same workflow ran twice on the identical SHA.

That duplicate had a single root cause, and this tool's first check is its
regression guard:

    concurrency:
      group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}

On a ``pull_request`` event that resolves to the PR number. On a ``push`` event
``pull_request.number`` is empty, so it falls back to ``github.run_id`` — which
is **unique per run**. Every push run therefore lands in its own private
concurrency group and can never be deduplicated: not against the PR run for the
same commit, and not even against an earlier push to the same branch. Twelve
workflows carried that expression verbatim, all with ``cancel-in-progress: true``
— the cancellation machinery was armed and the group key defeated it.

The fix is a key that resolves identically for both events::

    group: ${{ github.workflow }}-${{ github.head_ref || github.ref_name }}

``head_ref`` is set only on pull_request events (the source branch); ``ref_name``
is the branch on push. Both resolve to the same branch name, so the two runs
collapse into one group and the later cancels the earlier.

What is an ERROR (exit 1)
-------------------------
1. **Dedup defect** — a workflow triggered by BOTH ``push`` and ``pull_request``
   whose concurrency group cannot resolve identically for the two events (it
   interpolates ``run_id``, or ``pull_request.number`` as the *fallback*), or
   which declares no ``concurrency:`` block at all. This is the #2205 duplicate.
2. **Ceiling breach** — declared PR-reachable job count above
   ``per_pr_job_ceiling``, after subtracting budgeted exemptions.
3. **Stale exemption** — a budgeted exemption past its ``revisit_on`` date, or
   naming a workflow that no longer exists.

What is ADVISORY (exit 0, still printed)
----------------------------------------
* **Freeloaders** — PR-reachable jobs that are neither a required context nor
  ``paths:``-gated. Adding a CI job is legitimate; the goal is that it becomes a
  *declared* act, not that it is refused. Matching ``ci-job-budget.md``'s
  contract and ``hook-output-discipline.md`` MUST-2, this never blocks.

Exit codes: 0 = no errors; 1 = >=1 error; 2 = the tool could not run (unreadable
declaration, unparseable workflow). Exit 2 is UNRUN, explicitly NOT a pass — a
silent no-op must never read as clean.

Run ``--selftest`` to prove the gate can still go red: it drives every check
against a NEGATIVE control that must trip it and a positive control that must
stay quiet. A check with no negative control is itself reported as an error
(anti-vacuity floor) — that is what an inert gate looks like from the outside.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
DECLARATION = ROOT / "scripts" / "ci" / "job-budget.d" / "_meta.json"

# A group key that resolves identically on push and pull_request. `head_ref` is
# empty off a PR, so the fallback carries the push case.
_SAFE_FALLBACKS = (
    "github.ref_name",
    "github.ref",
    "github.event.pull_request.head.ref",
)
# Interpolations that make a group unique per run, defeating dedup entirely.
_UNIQUE_TOKENS = ("github.run_id", "github.run_number", "github.sha")


class Finding:
    def __init__(self, severity: str, check: str, workflow: str, message: str):
        self.severity = severity
        self.check = check
        self.workflow = workflow
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "check": self.check,
            "workflow": self.workflow,
            "message": self.message,
        }

    def __str__(self) -> str:
        tag = "ERROR " if self.severity == "error" else "note  "
        return f"{tag} [{self.check}] {self.workflow}: {self.message}"


def load_declaration(path: Path = DECLARATION) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _on_block(text: str) -> str:
    """The workflow's `on:` block, as raw text.

    Deliberately textual rather than YAML-parsed: `on` is the YAML 1.1 boolean
    `True` after a safe_load, which silently renames the key and is exactly the
    kind of quiet mis-read this tool exists to prevent.
    """
    m = re.search(
        r"^on:(.*?)^(?:jobs|permissions|env|concurrency|defaults):", text, re.S | re.M
    )
    return m.group(1) if m else text


def _concurrency_group(text: str) -> str | None:
    m = re.search(r"^concurrency:\s*$(.*?)(?=^\S)", text, re.S | re.M)
    if not m:
        m = re.search(r"^concurrency:(.*?)(?=^\S)", text, re.S | re.M)
        if not m:
            return None
    g = re.search(r"group:\s*(.+)$", m.group(1), re.M)
    return g.group(1).strip() if g else None


def _job_names(text: str) -> list[str]:
    if "jobs:" not in text:
        return []
    body = text.split("jobs:", 1)[1]
    return re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", body, re.M)


def group_dedups_push_and_pr(group: str | None) -> tuple[bool, str]:
    """Does this concurrency group collapse a push run and a PR run for one branch?

    Returns (ok, reason). The reason is the falsifying detail, so a caller can
    print WHY rather than just that something failed.
    """
    if group is None:
        return (
            False,
            "no `concurrency:` group declared — push and PR runs cannot collapse",
        )
    for tok in _UNIQUE_TOKENS:
        if tok in group:
            return False, (
                f"group interpolates `{tok}`, which is unique per run — the push run "
                f"lands in its own group and is never deduplicated"
            )
    if "pull_request.number" in group and "||" in group:
        head, _, tail = group.partition("||")
        if "pull_request.number" in head and not any(
            f in tail for f in _SAFE_FALLBACKS
        ):
            return False, (
                "group falls back off `pull_request.number` to something that does not "
                "resolve to the branch on a push event"
            )
    if any(f in group for f in _SAFE_FALLBACKS) or "head_ref" in group:
        return True, "resolves to the branch on both push and pull_request"
    return (
        False,
        f"group `{group}` does not demonstrably resolve identically for push and pull_request",
    )


_JUNCTURE_TOKENS = ("github.event_name ==", "github.ref ==")


def matrix_breadth_findings(name, text):
    """Flag a literal multi-entry matrix on a PR-reachable workflow.

    Such a matrix runs EVERY entry on EVERY PR. The juncture-keyed form collapses
    to one entry for iteration and expands only at a critical juncture (schedule /
    workflow_dispatch / merge_group / push to main). Measured 2026-09-01: literal
    matrices accounted for 18 of 53 PR-time jobs, 8 of them Windows at 2x cost.
    """
    out = []
    for key in ("python-version", "os"):
        expr = re.search(key + r": >-\s*\n\s*\$\{\{ fromJSON\((.*?)\) \}\}", text, re.S)
        if expr:
            if not any(tok in expr.group(1) for tok in _JUNCTURE_TOKENS):
                out.append(
                    Finding(
                        "error",
                        "matrix-breadth",
                        name,
                        "`"
                        + key
                        + "` uses a fromJSON expression not keyed on a critical "
                        "juncture, so it cannot collapse for the PR lane",
                    )
                )
            continue
        lit = re.search(key + r": *\[([^\]]*)\]", text)
        if not lit:
            continue
        entries = [e for e in lit.group(1).split(",") if e.strip()]
        if len(entries) > 1:
            out.append(
                Finding(
                    "error",
                    "matrix-breadth",
                    name,
                    "`"
                    + key
                    + "` is a literal "
                    + str(len(entries))
                    + "-entry matrix on a PR-reachable workflow, so all of them run on "
                    "every PR. Key it on a critical juncture so the PR lane collapses "
                    "to the floor version.",
                )
            )
    return out


def audit(
    decl: dict[str, Any], workflows_dir: Path = WORKFLOWS, today: _dt.date | None = None
) -> list[Finding]:
    today = today or _dt.date.today()
    findings: list[Finding] = []

    exempt_dedup = {e["workflow"] for e in decl.get("dedup_exempt_workflows", [])}
    budgeted = {e["workflow"]: e for e in decl.get("budgeted_exemptions", [])}
    required = set(decl.get("required_contexts", []))

    pr_job_total = 0
    present: set[str] = set()

    for f in sorted(workflows_dir.iterdir()):
        if f.suffix not in (".yml", ".yaml"):
            continue
        present.add(f.name)
        text = f.read_text(encoding="utf-8", errors="replace")
        on = _on_block(text)
        on_pr = "pull_request" in on
        on_push = re.search(r"^\s+push:", on, re.M) is not None
        if not on_pr:
            continue

        jobs = _job_names(text)
        if f.name in budgeted:
            pass  # declared, does not count toward the ceiling
        else:
            pr_job_total += len(jobs)

        # Check 1 — dedup defect. Only bites when BOTH triggers are present:
        # a pull_request-only workflow cannot produce the duplicate.
        if on_push and f.name not in exempt_dedup:
            ok, why = group_dedups_push_and_pr(_concurrency_group(text))
            if not ok:
                findings.append(Finding("error", "dedup", f.name, why))

        findings.extend(matrix_breadth_findings(f.name, text))

        # Advisory — freeloaders: neither required nor paths-gated.
        if (
            not any(j in required for j in jobs)
            and "paths:" not in on
            and f.name not in budgeted
        ):
            findings.append(
                Finding(
                    "note",
                    "freeloader",
                    f.name,
                    f"{len(jobs)} job(s) run on every PR but gate nothing and are not `paths:`-gated",
                )
            )

    # Check 3 — stale / dangling exemptions.
    for name, e in budgeted.items():
        if name not in present:
            findings.append(
                Finding(
                    "error",
                    "exemption",
                    name,
                    "budgeted exemption names a workflow that no longer exists",
                )
            )
            continue
        rv = e.get("revisit_on")
        if rv and _dt.date.fromisoformat(rv) < today:
            findings.append(
                Finding(
                    "error",
                    "exemption",
                    name,
                    f"budgeted exemption passed its revisit_on date ({rv})",
                )
            )

    # Check 2 — ceiling.
    ceiling = decl.get("per_pr_job_ceiling")
    if isinstance(ceiling, int) and pr_job_total > ceiling:
        findings.append(
            Finding(
                "error",
                "ceiling",
                "(repo)",
                f"{pr_job_total} PR-reachable jobs declared, ceiling is {ceiling}",
            )
        )

    return findings


# --------------------------------------------------------------------------
# Selftest — every check gets a NEGATIVE control that must trip it and a
# positive control that must stay quiet. A check with no negative control is
# reported as an error: that is precisely what an inert gate looks like.
# --------------------------------------------------------------------------

_NEG = {
    "dedup-run_id": (
        "on:\n  push:\n    branches: [x]\n  pull_request:\n    branches: [main]\n"
        "concurrency:\n  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}\n"
        "  cancel-in-progress: true\njobs:\n  a:\n    runs-on: x\n"
    ),
    "dedup-missing": (
        "on:\n  push:\n    branches: [x]\n  pull_request:\n    branches: [main]\n"
        "jobs:\n  a:\n    runs-on: x\n"
    ),
}
_POS = {
    "dedup-ok": (
        "on:\n  push:\n    branches: [x]\n  pull_request:\n    branches: [main]\n"
        "concurrency:\n  group: ${{ github.workflow }}-${{ github.head_ref || github.ref_name }}\n"
        "  cancel-in-progress: true\njobs:\n  a:\n    runs-on: x\n"
    ),
    "dedup-pr-only": (  # pull_request only: cannot duplicate, must not be flagged
        "on:\n  pull_request:\n    branches: [main]\n" "jobs:\n  a:\n    runs-on: x\n"
    ),
}


def selftest() -> int:
    cases = 0
    failures: list[str] = []

    for name, text in _NEG.items():
        cases += 1
        ok, why = group_dedups_push_and_pr(_concurrency_group(text))
        if ok:
            failures.append(f"NEGATIVE control '{name}' did NOT trip the dedup check")

    for name, text in _POS.items():
        cases += 1
        if name == "dedup-pr-only":
            on = _on_block(text)
            if re.search(r"^\s+push:", on, re.M):
                failures.append(f"POSITIVE control '{name}' misread as push-triggered")
            continue
        ok, why = group_dedups_push_and_pr(_concurrency_group(text))
        if not ok:
            failures.append(f"POSITIVE control '{name}' was flagged: {why}")

    # Ceiling: negative control must breach, positive must not.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "w.yml").write_text(
            "on:\n  pull_request:\n    branches: [main]\n"
            "jobs:\n" + "".join(f"  j{i}:\n    runs-on: x\n" for i in range(9)),
            encoding="utf-8",
        )
        cases += 1
        breached = audit({"per_pr_job_ceiling": 5, "required_contexts": []}, d)
        if not any(f.check == "ceiling" for f in breached):
            failures.append(
                "NEGATIVE control 'ceiling' did NOT trip (9 jobs vs ceiling 5)"
            )
        cases += 1
        quiet = audit({"per_pr_job_ceiling": 50, "required_contexts": []}, d)
        if any(f.check == "ceiling" for f in quiet):
            failures.append(
                "POSITIVE control 'ceiling' tripped at ceiling 50 with 9 jobs"
            )

    # Exemption expiry: negative control must trip.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "w.yml").write_text(
            "on:\n  pull_request:\njobs:\n  a:\n    runs-on: x\n", encoding="utf-8"
        )
        cases += 1
        stale = audit(
            {
                "per_pr_job_ceiling": 99,
                "required_contexts": [],
                "budgeted_exemptions": [
                    {"workflow": "w.yml", "revisit_on": "2020-01-01"}
                ],
            },
            d,
            today=_dt.date(2026, 1, 1),
        )
        if not any(f.check == "exemption" for f in stale):
            failures.append("NEGATIVE control 'stale exemption' did NOT trip")

    # Matrix breadth: a literal multi-entry matrix must trip; a juncture-keyed
    # expression and a single-entry literal must not.
    cases += 1
    if not matrix_breadth_findings(
        "w.yml", '        python-version: ["3.11", "3.12"]\n'
    ):
        failures.append("NEGATIVE control 'matrix-breadth literal' did NOT trip")
    cases += 1
    if not matrix_breadth_findings(
        "w.yml", "        os: [ubuntu-latest, windows-latest]\n"
    ):
        failures.append("NEGATIVE control 'matrix-breadth os' did NOT trip")
    cases += 1
    keyed = (
        "        python-version: >-\n"
        "          ${{ fromJSON((github.event_name == 'schedule') && '[\"3.11\",\"3.12\"]'"
        " || '[\"3.11\"]') }}\n"
    )
    if matrix_breadth_findings("w.yml", keyed):
        failures.append("POSITIVE control 'juncture-keyed matrix' was flagged")
    cases += 1
    if matrix_breadth_findings("w.yml", '        python-version: ["3.11"]\n'):
        failures.append("POSITIVE control 'single-entry literal' was flagged")
    cases += 1
    unkeyed = (
        "        python-version: >-\n"
        '          ${{ fromJSON(true && \'["3.11","3.12"]\' || \'["3.11"]\') }}\n'
    )
    if not matrix_breadth_findings("w.yml", unkeyed):
        failures.append("NEGATIVE control 'fromJSON not juncture-keyed' did NOT trip")

    # Anti-vacuity floor: every check this tool can emit must own a negative control.
    checks_with_negative = {"dedup", "ceiling", "exemption", "matrix-breadth"}
    emitted_checks = {"dedup", "ceiling", "exemption", "freeloader", "matrix-breadth"}
    advisory_only = {"freeloader"}
    uncovered = emitted_checks - checks_with_negative - advisory_only
    if uncovered:
        failures.append(
            f"anti-vacuity: check(s) with no negative control: {sorted(uncovered)}"
        )

    for f in failures:
        print(f"SELFTEST FAIL: {f}", file=sys.stderr)
    print(f"selftest: {cases} case(s), {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true", help="emit findings as JSON")
    p.add_argument("--selftest", action="store_true", help="prove the gate can go red")
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()

    try:
        decl = load_declaration()
    except (OSError, json.JSONDecodeError) as e:
        print(f"UNRUN: cannot read declaration {DECLARATION}: {e}", file=sys.stderr)
        return 2
    if not WORKFLOWS.is_dir():
        print(f"UNRUN: no workflows directory at {WORKFLOWS}", file=sys.stderr)
        return 2

    findings = audit(decl)
    errors = [f for f in findings if f.severity == "error"]

    if args.json:
        print(
            json.dumps(
                {
                    "errors": len(errors),
                    "notes": len(findings) - len(errors),
                    "findings": [f.as_dict() for f in findings],
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            print(f)
        print(
            f"\njob-budget-audit: {len(errors)} error(s), "
            f"{len(findings) - len(errors)} advisory note(s)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
