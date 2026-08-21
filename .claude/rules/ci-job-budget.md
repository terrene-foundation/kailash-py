---
priority: 10
scope: path-scoped
paths:
  - "**/.github/workflows/**"
  - "**/scripts/ci/job_budget_audit.py"
  - "**/scripts/ci/job-budget.d/**"
  - "**/.pre-commit-config.yaml"
---

# CI Job Budget — Adding A Job Is A Declared Act, Never An Unremarked One

CI jobs accrete one unremarkable job at a time. Each addition is individually
defensible; nothing says anything at the moment each is added; and the fan-out is
discovered only when the queue is full or the bill arrives. The defect is not any
one job — it is that **no surface makes the accretion visible at the moment it
happens**.

Measured in this repo on PR #2205 (2026-08-21): **25 runner-consuming jobs**
across 5 workflow runs, of which **3** gate anything. Nine of the 25 were an exact
duplicate of another nine — one workflow ran twice on the identical SHA, and the
failing copy read as a real break until both runs were compared.

The census is `scripts/ci/job_budget_audit.py`, declared by
`scripts/ci/job-budget.d/_meta.json`, and it runs as a **pre-commit** hook on
workflow edits. It is deliberately NOT a CI job: a gate about runner fan-out that
itself consumes a runner on every PR would be self-defeating.

## MUST Rules

### 1. A Workflow Triggered By BOTH `push` And `pull_request` MUST Share One Concurrency Group Across The Two Events

A workflow reachable from both events MUST declare a `concurrency.group` that
resolves to the **same value** for a push and a pull_request on the same branch.
A group interpolating `github.run_id` / `github.run_number` / `github.sha`, or
falling back off `pull_request.number` to anything that is not the branch, is
BLOCKED — it puts every push run in its own private group, so the run is never
deduplicated against the PR run for the same commit, nor against an earlier push
to the same branch.

```yaml
# DO — resolves to the branch on BOTH events, so the two runs collapse
concurrency:
  group: ${{ github.workflow }}-${{ github.head_ref || github.ref_name }}
  cancel-in-progress: true

# DO NOT — `pull_request.number` is empty on push, so this falls back to
# `run_id`, which is unique per run: the group can never match anything
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: true
```

**BLOCKED rationalizations:** "`cancel-in-progress: true` is already set, so
duplicates are handled" (the flag is armed; the key defeats it) / "the two runs
test different refs, so both are meaningful" (they ran the identical 9 jobs on the
identical SHA) / "`run_id` guarantees uniqueness, which is what a group key wants"
(a concurrency key wants COLLISION — uniqueness is the anti-goal) / "it has always
been that way and CI is green" / "only one of them is required, the other is
harmless".

**Why:** `cancel-in-progress` cannot fire on a group that never collides, so the
armed machinery reads as protection while providing none — and the duplicate is
not merely wasted spend: when the two copies disagree, the failing one is
indistinguishable from a real regression until someone compares runs by SHA.

### 2. A New PR-Reachable Job Is Declared, Gated, Or Budgeted — Never Silent

A job added to a `pull_request`-triggered workflow MUST be one of: a branch-
protection **required context**; **`paths:`-gated** so it fires only on relevant
diffs; or carry a **dated budgeted exemption** in
`scripts/ci/job-budget.d/_meta.json` naming why it runs ungated and when that is
revisited. Adding a job that is none of the three is BLOCKED.

```json
// DO — budgeted, with a reason and an expiry that will actually fire
{ "workflow": "project-automation.yml", "jobs": 5,
  "reason": "Board bookkeeping; every job is `if:`-gated and skips on ordinary PRs.",
  "declared_on": "2026-08-21", "revisit_on": "2027-02-21" }

// DO NOT — a job that runs on every PR, gates nothing, and is written down nowhere
```

**BLOCKED rationalizations:** "it is one small job" (the failure mode is
accretion, so every instance is one small job) / "we will gate it later" /
"it is fast, so it does not count" (it still occupies a runner slot) / "the
exemption list is bureaucracy" / "I will add the `paths:` filter in a follow-up".

**Why:** The per-addition cost is always defensible and the aggregate never gets
examined, so the only place accretion can be caught is the moment of addition —
which is exactly where nothing was looking.

### 3. The Ceiling Is A RATCHET, And A Breach Is Reported, Never Silently Raised

`per_pr_job_ceiling` is set just above the measured baseline so it fires on
GROWTH. Raising it to clear a breach requires a dated rationale in the
declaration; editing the number to make the gate quiet is BLOCKED. A ceiling
breach names the count and the ceiling — it never merely says "over budget".

**Why:** A ceiling silently raised to match reality measures nothing; the ratchet
only works if crossing it costs a written justification.

## MUST NOT

- Interpolate a per-run-unique value into a concurrency group key

**Why:** It guarantees the group never collides, which is the one thing a
concurrency group exists to do.

- Read a green `job_budget_audit.py` run as evidence the CI surface is healthy
  without checking the advisory notes

**Why:** Freeloader jobs are reported at `note` severity and exit 0 by design;
treating exit 0 as "nothing to see" discards the rule's entire advisory tier.

- Add the census itself as a CI job

**Why:** A fan-out gate that consumes a runner on every PR pays the cost it
exists to prevent; pre-commit fires exactly when a workflow is edited, for free.

## Trust Posture Wiring

- **Severity:** `block` at the pre-commit layer for MUST-1 and MUST-3 — both are
  STRUCTURAL facts read off the workflow YAML and the declaration (a group key
  either interpolates a per-run token or it does not; a count either exceeds a
  declared integer or it does not), which is the narrow class
  `hook-output-discipline.md` MUST-2 reserves `block` for. MUST-2's freeloader
  arm is `advisory` — whether an ungated job is legitimate is a judgment, and
  adding a CI job is a legitimate act. `halt-and-report` at gate-review (reviewer
  at `/implement` + cc-architect at `/codify` confirm a new PR-reachable job was
  required, `paths:`-gated, or budgeted).
- **Grace period:** 7 days from rule landing (2026-08-21 → 2026-08-28).
- **Cumulative posture impact:** same-class violations (a shared-trigger workflow
  with a non-colliding group key; an ungated, unbudgeted PR-reachable job; a
  ceiling raised with no dated rationale) contribute to `trust-posture.md` MUST-4
  cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d →
  drop 1 posture).
- **Regression-within-grace:** routes through the GENERIC
  `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× =
  drop 1 posture) — NO dedicated per-clause key. Named deviation from the
  key-per-clause shape, recorded here per `trust-posture.md` Rule 8: the
  structural arms already fail closed at pre-commit, so a per-clause instant-drop
  key would double-count the clauses that cannot silently pass, and minting one
  would drag `trust-posture.md` — a `self-referential-codify.md` allowlist file —
  into a self-referential edit. Same disposition `burn-down-reporting.md` and
  `security.md` § Enforcement-Surface Parity took.
- **Receipt requirement:** SessionStart soft-gate `[ack: ci-job-budget]` IFF
  `posture.json::pending_verification` includes the `ci-job-budget` rule_id.
- **Detection mechanism:** structural, SHIPPED — nothing here is deferred.
  `scripts/ci/job_budget_audit.py` runs as the `ci-job-budget` pre-commit hook,
  scoped by `files:` to workflow / declaration / engine edits, so a repo touching
  none of them pays nothing. It carries `--selftest`, which drives every check
  against a NEGATIVE control that must trip it and a positive control that must
  stay quiet, plus an **anti-vacuity floor** that fails when a check ships with no
  negative control — that is what an inert gate looks like from the outside. It
  exits **2 (UNRUN, explicitly NOT a pass)** on an unreadable declaration or a
  missing workflows directory, so a silent no-op cannot read as clean.
  Discrimination was MEASURED at landing, both poles on one tree: **8 errors**
  against `origin/main`'s pre-fix workflows, **0** against the fixed tree, and the
  hook was driven red and green again through the real `pre-commit run` path.
  Re-measure rather than citing those figures. **No probe suite ships for this
  rule** — stated explicitly rather than naming a phantom path; the semantic tier
  is UNCOVERED and owed at gate-review via `/test-harness-probe`, the same
  disposition `agents.md` § Worktree-Orchestration wiring records.
- **Violation scope:** MUST-1 (non-colliding concurrency group on a shared-trigger
  workflow) + MUST-2 (PR-reachable job that is neither required, `paths:`-gated,
  nor budgeted) + MUST-3 (ceiling raised without a dated rationale). Every
  `violations.jsonl` row names the workflow and which MUST fired.
- **Origin:** See § Origin.

## Origin

2026-08-21 — incorporated from loom#1877, which proposed a `ci-job-budget`
artifact set originating in a sibling BUILD repo. Adopted here ahead of the loom
cascade at the co-owner's direction, so the eventual cascade is a merge-and-
validate rather than a first landing.

**Deliberately NOT carried over from the source proposal:** its declaration
encoded self-hosted fleet topology — runner labels, per-pool capacities, a fleet
total, a host id, internal workflow names. loom's Gate-1 refused it on exactly
that ground, and this repo is PUBLIC, so the same refusal binds harder here.
Capacity is expressed instead as a per-PR job ceiling, which is the metric that
actually bites on GitHub-hosted runners and which carries no infrastructure
detail. The source's `--verify-capacity` reader is also not carried: it needs an
`admin:org` credential no configured secret holds, and adopting an instrument
nothing can run would book teeth that cannot arrive.

The duplicate-run defect this rule's MUST-1 blocks was found here, not inherited:
12 workflows carried `${{ github.event.pull_request.number || github.run_id }}`
verbatim, all with `cancel-in-progress: true`. `docs-build.yml` already carried
the correct form, so the fix was a pattern the repo had and had not propagated.
