---
priority: 10
scope: path-scoped
paths:
  - "**/tests/**"
  - "**/*test*.py"
  - "**/conftest.py"
  - "**/.pre-commit-config.yaml"
  - "**/.github/workflows/**"
  - "**/pyproject.toml"
---

# Test Parsimony — Run The Smallest Suite That Could Fail, Then Widen At Junctures

Verification cost is paid on EVERY iteration; verification VALUE is concentrated
at a few junctures. Running the broad suite on every change inverts that: it taxes
the fast loop where the tests cannot observe the diff, and it trains everyone to
skip the gate entirely — which is how a broad gate ends up protecting nothing.

Measured in this repo, 2026-09-01:

| surface | before | after |
| --- | --- | --- |
| pre-commit on a DOCS-ONLY change | **82s** (4891 unit tests, `always_run: true`) | **3s** (hook skipped) |
| PR-time CI jobs (all paths matching) | **53** | **35** |
| of which Windows jobs at 2× minute cost | 8 | **0** |

Neither number came from removing a test. Both came from not running tests that
could not have observed the change.

## The two lanes

**ITERATION** — a PR, a push to a feature branch, a local commit. Optimised for
SPEED. Floor Python version only, ubuntu only, path-scoped, fast markers.

**CRITICAL JUNCTURE** — `schedule` (nightly), `workflow_dispatch`, `merge_group`,
push to `main`, and a release. Optimised for COVERAGE. Full version matrix, every
OS, broad suites.

The juncture set is deliberately closed. "This change feels risky" is not a
juncture; if it genuinely is, dispatch the full matrix explicitly
(`workflow_dispatch`) and say why.

## MUST Rules

### 1. Scope A Test Invocation To What Could Observe The Change

An agent-initiated test run MUST target the narrowest scope that could plausibly
fail because of the diff — the changed module's tests, the package's suite, or a
`-k` selection. Running the whole tree, or adding `--cov` over the whole source
root, on a scoped change is BLOCKED.

```bash
# DO — the smallest suite that could fail
pytest tests/unit/nodes/data/ -q                     # the area the diff touched
pytest tests/unit -k "pool or reaper" -q             # a selection across areas
pytest packages/kailash-ml/tests/unit -q             # that package's own suite

# DO NOT — the whole tree, or whole-root coverage, for a scoped change
pytest tests/unit tests/regression tests/deployment tests/security --cov=src/kailash
```

**BLOCKED rationalizations:** "the full suite is the safe option" (it is the SLOW
option; the narrow suite plus a juncture run is the safe one) / "coverage numbers
need the whole root" (they need it at a juncture, not per iteration) / "I do not
know which tests cover this" (find out — that is one `grep`, and not knowing is
itself worth surfacing) / "it only takes a few minutes" (multiplied by every
iteration in every lane) / "the lane has budget".

**Why:** A test that cannot observe the diff cannot fail because of it, so running
it buys nothing and is paid every iteration. Whole-root `--cov` is the worst case:
it forces full collection AND instrumentation to answer a question nobody asked at
that moment.

### 2. A Local Gate Fires Only On Files That Could Change Its Verdict

A pre-commit hook MUST be scoped by `files:` to the paths whose change can alter
its outcome. `always_run: true` on a hook that executes tests is BLOCKED — it
fires the suite on docs, workflow, and `.claude/**` commits where not one test can
observe the diff.

```yaml
# DO — the suite runs when Python or the dependency/pytest config changes
files: '\.(py)$|^(pyproject\.toml|uv\.lock|conftest\.py|pytest\.ini)$'

# DO NOT — fires 4891 tests on a README typo
always_run: true
pass_filenames: false
```

**BLOCKED rationalizations:** "always_run is safer" / "a docs change could break an
import" (name the test that would catch it, or the claim is decoration) / "the
hook is fast enough" (82s measured, on every commit) / "scoping it risks missing
something" — the juncture lane is what catches that, by design.

**Why:** A gate that fires when it cannot discriminate is pure tax, and the tax is
what makes people reach for `--no-verify`, which disables the gate for the changes
that DO matter.

### 3. Breadth Is Keyed On The EVENT, Never Left Literal

A PR-reachable workflow MUST NOT declare a literal multi-entry `python-version` or
`os` matrix. Breadth MUST be keyed on the closed juncture set so the PR lane
collapses to the floor and expands only where coverage is the goal.

```yaml
# DO — floor for iteration, full at a juncture
python-version: >-
  ${{ fromJSON((github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
  || github.event_name == 'merge_group' || github.ref == 'refs/heads/main')
  && '["3.11","3.12","3.13","3.14"]' || '["3.11"]') }}

# DO NOT — every entry on every PR
python-version: ["3.11", "3.12", "3.13", "3.14"]
```

**Key on the EVENT, not on `event_name == 'pull_request'`.** The negated form
looks equivalent and is not: a push to a feature branch is not a `pull_request`,
so it would silently earn the FULL matrix — the opposite of the intent. That
inversion was written and caught during this rule's own implementation.

**Why:** A version-specific break is real but rare, and the nightly/main lane
catches it within a day; paying the full matrix on every iteration to shorten that
window is the trade this rule declines.

### 4. Narrowing A Lane MUST Relocate The Coverage, Never Drop It

Before narrowing any lane, the wider coverage MUST already run at a juncture —
verify the workflow actually has a `schedule:`, a `push:` to `main`, or a
`merge_group:` arm. Narrowing a workflow that has none silently DELETES that
coverage.

```bash
# DO — verify the juncture exists before narrowing
awk '/^on:/,/^jobs:/' .github/workflows/W.yml | grep -E 'schedule:|branches: \[main\]|merge_group:'
# DO NOT — narrow and assume something else covers it
```

**Why:** Measured during this rule's implementation: two workflows had neither a
nightly nor a push-to-main arm, so narrowing them alone would have dropped four
Python versions outright. Both got a nightly in the same change.

## MUST NOT

- Add `--cov` to a routine or agent-initiated run

**Why:** Coverage instrumentation forces full collection and slows every test; it
answers a juncture question, so it belongs on the juncture lane.

- Treat "the suite is green" from a narrow run as evidence the broad suite is green

**Why:** It is evidence about the scope that ran and nothing else; the juncture run
is what supports the wider claim.

## Trust Posture Wiring

- **Severity:** `block` at the pre-commit layer for MUST-3 — a literal multi-entry
  matrix on a PR-reachable workflow is a STRUCTURAL fact read straight off the YAML,
  which is the narrow class `hook-output-discipline.md` MUST-2 reserves `block` for,
  and it is caught before the workflow can land. `halt-and-report` at gate-review for
  MUST-1/2/4 (reviewer at `/implement` confirms agent-initiated runs were scoped, that
  no test-executing hook carries `always_run`, and that any narrowing relocated its
  coverage). MUST-1 has **no hook layer at all** and is honest about it: whether a
  given invocation was the narrowest that could fail is a judgment over the diff, with
  no structural tool-call-time signal.
- **Grace period:** 7 days from rule landing (2026-09-01 → 2026-09-08).
- **Cumulative posture impact:** same-class violations (a whole-tree or `--cov` run on
  a scoped change; a test-executing hook with `always_run`; a literal PR-reachable
  matrix; a lane narrowed without its coverage relocated) contribute to
  `trust-posture.md` MUST-4 cumulative-window math (3× same-rule in 30d → drop 1
  posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** routes through the GENERIC `regression_within_grace`
  emergency trigger per `trust-posture.md` MUST-4 (1× = drop 1 posture) — NO dedicated
  per-clause key. Named deviation from the key-per-clause shape, recorded here per
  `trust-posture.md` Rule 8: these violations cost time rather than correctness and are
  reversible by re-scoping, so they do not warrant an instant-drop key, and minting one
  would drag `trust-posture.md` — a `self-referential-codify.md` allowlist file — into a
  self-referential edit. Same disposition `ci-job-budget.md` and `docker-no-sprawl.md`
  took.
- **Receipt requirement:** SessionStart soft-gate `[ack: test-parsimony]` IFF
  `posture.json::pending_verification` includes the `test-parsimony` rule_id.
- **Detection mechanism:** structural for MUST-3, review for the rest.
  `scripts/ci/job_budget_audit.py::matrix_breadth_findings` flags a literal
  multi-entry `python-version`/`os` matrix on a PR-reachable workflow, and a
  `fromJSON` expression not keyed on the juncture set; it runs as the `ci-job-budget`
  pre-commit hook, scoped by `files:` to workflow edits. Discrimination MEASURED at
  landing, both poles on one tree: **5 errors** against `origin/main`'s workflows,
  **0** against this branch. `--selftest` carries a negative control per check plus an
  anti-vacuity floor that fails when a check ships with no control (12 cases at
  landing; re-measure rather than citing). MUST-1/2/4 are gate-review only —
  deliberately, since each is a judgment over a diff. **No probe suite ships** —
  stated rather than naming a phantom path; the semantic tier is UNCOVERED and owed at
  gate-review via `/test-harness-probe`, the disposition `ci-job-budget.md` and
  `docker-no-sprawl.md` also record.
- **Violation scope:** MUST-1 (over-broad invocation) + MUST-2 (`always_run` test
  hook) + MUST-3 (literal PR-reachable matrix) + MUST-4 (narrowing without
  relocation). Every `violations.jsonl` row names the surface and which MUST fired.
- **Origin:** See § Origin.

## Origin

2026-09-01 — co-owner-directed, verbatim: _"PARSIMONY IS THE CORE DIRECTIVE"_, with
the instruction to speed up the bug/feature/issue loop and activate the heavy lanes
"sparingly at critical junctures ONLY".

The measurement corrected the premise in a way worth recording: the committed
pre-commit gate was **29s**, not the tens-of-minutes reported. The 82s figure on a
docs-only commit was real, and the waste was not suite SIZE but suite TRIGGERING —
`always_run: true` firing 4891 tests where none could observe the diff. The broad
`tests/unit tests/regression tests/deployment tests/security --cov` invocation was
never in the pre-commit config at all; it is what AGENT artifacts prescribe, which
is why MUST-1 targets agent-initiated runs rather than the config alone.

Two defects were caught during implementation and are pinned by MUST-3's warning
and MUST-4: keying breadth on `event_name == 'pull_request'` silently gave a
feature-branch push the FULL matrix, and two workflows had no juncture arm at all,
so narrowing them would have deleted four Python versions rather than relocating
them.

**Length rationale (per `rule-authoring.md` MUST NOT § "Rules longer than 200
lines").** 218 lines. Named rationale: **two-lane contract with a mandated 8-field
Wiring** — the rule defines the iteration/juncture split once and then binds it at
four surfaces (agent invocation, local hook, CI matrix, and the relocation
precondition), each carrying the DO/DO-NOT + BLOCKED corpus + `**Why:**` the
meta-rule requires. Splitting it would put the lane definition in one file and its
enforcement in another, which is how the convention decays. `priority: 10` +
`scope: path-scoped`, so it pays NO baseline-emission cost and Rule 10's
proximity-band gate does not fire. Sibling precedent: `ci-job-budget.md`.
