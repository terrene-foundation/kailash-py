---
priority: 10
scope: path-scoped
paths:
  - "**/.claude/hooks/lib/unlanded-work-surface.js"
  - "**/.claude/bin/worktree-reap.mjs"
  - "**/.claude/hooks/session-start.js"
  - "**/.github/workflows/**"
  - "**/.session-notes*"
  - "**/workspaces/**"
---

# Dev Integration Trunk — Landing Is Free, Promotion Is Deliberate

Lane work lands in `dev` immediately. `dev` → `main` is a separate, deliberate
promotion costing exactly one CI run. Deploy runs off a pinned `dev` commit and
is independent of `main`.

## The root cause this fixes

The gate fires on `pull_request` to `main` and on `push: branches:[main]`. So the
only route to `main` cost a CI run on a shared pool. While "landed" meant "on
`main`", **closing a branch always meant spending CI**, and every session
rationally deferred.

Measured on a sibling repo, 2026-09-10: **33 of 33 local branches UNLANDED** —
roughly a month of finished work stranded — and one fix built twice, because the
first copy was invisible on an unmerged lane.

The WIP guards were not being ignored. They gated an exit that had nowhere cheap
to go. Pointing them at a trunk reachable for free is what lets them terminate:
work becomes reapable the moment it lands, and the branch/worktree ceiling drains
itself instead of ratcheting.

## MUST Rules

### 1. Finished Lane Work Merges To `dev` The Same Session It Is Finished

A branch, worktree, or lane that is finished MUST merge into `dev` in that
session. Holding work "until the wave", "until the batch", or "until CI is worth
spending" is BLOCKED.

```bash
# DO — land it now; no PR, no gate, no wait
git checkout dev && git merge --no-ff feat/x && git push origin dev

# DO NOT — hold a finished branch for a future promotion window
```

**BLOCKED rationalizations:** "I'll batch it with the wave" / "it's not worth a CI
run" (landing in `dev` costs none) / "it's finished but unreviewed" (review is a
lane concern; `dev` is integration) / "main is the real trunk".

**Why:** Deferral is what produced 33-of-33 stranded and one fix built twice. A
branch that is invisible on an unmerged lane gets rebuilt by the next session.

### 2. No PR Is Opened Against `dev`, So No Workflow Fires

`dev` is CI-free by construction. Opening a PR against `dev`, or adding `dev` to
any workflow trigger, is BLOCKED — it reintroduces exactly the cost this model
removes.

**VERIFY BY QUERYING THE RUNS API, NEVER BY READING THE TRIGGER CONFIG.** A
trigger block is a claim about what fires; the runs API is the observation.

```bash
# DO — observe
gh run list --branch dev --limit 20 --json databaseId -q '.|length'   # expect 0
# DO NOT — infer from `on:` that nothing fired
```

**Why:** Throughput on `dev` is then bounded by coding and tests only. Measured at
adoption in this repo: pushing `dev` fired **0** workflow runs, confirmed against
a pinned pre-push run-id baseline.

### 3. "Landed" Measures Against The TRUNK, Not The Default Branch

Every landed/unlanded predicate MUST resolve its base ref to `origin/dev` when a
trunk exists. `origin/HEAD` points at the repo's DEFAULT branch — the promotion
target, not the trunk — so following it silently measures the wrong thing.

The resolution order is: `COC_LANDED_TARGET` (explicit override) → `origin/dev` →
the original `origin/HEAD` → main/master/develop chain.

**INERT WHERE THERE IS NO TRUNK.** With no `dev` and no override, behaviour is
byte-identical to before. A repo that never adopts the trunk sees no change,
which is what makes this safe to sync.

**Why:** A predicate pointed at `main` reports finished work as unlanded forever —
the permanent-backlog behaviour that trains everyone to ignore the surface.

### 4. `dev` → `main` Is ONE Deliberate Promotion, And The Gap Stays COUNTED

Promotion is one PR, one gate run, on a chosen cadence. It MUST NOT be automatic.
And because trunk-but-not-main work now reads as *landed*, the `dev..main` gap
MUST be surfaced as a live count — it is invisible to the unlanded surface by
construction.

```bash
git rev-list --count origin/main..origin/dev     # the promotion gap
```

**CADENCE: WEEKLY** (ratified 2026-09-10). One promotion PR per week,
`dev` → `main`, one gate run. Weekly is small enough that the merge stays
reviewable in a single pass; the gap counter is what shows when a week has
been missed.

**This is the model's one honest cost, stated rather than hidden:** the risk is
RELOCATED, not removed. Two things keep it honest — this counter, and a standing
promotion cadence. Without a cadence `main` rots and the first promotion after a
long gap is a large, hard-to-review merge: the same bottleneck in a new place.

### 5. Deploy From A Pinned `dev` Commit, Never From `main`

Deploy targets a pinned `dev` SHA. Deploying from `main` couples release to the
promotion cadence, which is a scheduling artifact, not a readiness signal.

**Deploy authorisation is UNCHANGED:** a deploy to a namespace serving real client
traffic still requires an explicit human yes. Nothing here relaxes that.

## MUST NOT

- Add `dev` to any workflow trigger, or open a PR against `dev`

**Why:** It reintroduces the per-landing CI cost that caused the backlog.

- Treat a green `dev` as a promotion, or auto-promote on a timer

**Why:** Promotion is the deliberate act where the gate is spent; automating it
spends the gate on every landing again, one indirection removed.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` +
  cc-architect at `/codify` confirm finished lane work landed in `dev` the same
  session, that no workflow trigger gained `dev`, and that any landed/unlanded
  claim resolved against the trunk); `advisory` at the hook layer — whether a lane
  was "finished" is a judgment with no structural tool-call-time signal.
- **Grace period:** 7 days from rule landing (2026-09-10 → 2026-09-17).
- **Cumulative posture impact:** same-class violations (finished work held off the
  trunk; `dev` added to a workflow trigger; a landed predicate left pointed at the
  default branch; a promotion auto-fired) contribute to `trust-posture.md` MUST-4
  cumulative-window math (3× same-rule in 30d → drop 1 posture; 5× total in 30d →
  drop 1 posture).
- **Regression-within-grace:** routes through the GENERIC
  `regression_within_grace` emergency trigger per `trust-posture.md` MUST-4 (1× =
  drop 1 posture) — NO dedicated per-clause key. Named deviation from the
  key-per-clause shape per `trust-posture.md` Rule 8: these are recoverable
  workflow-discipline lapses, not corruption, and minting a key would drag
  `trust-posture.md` — a `self-referential-codify.md` allowlist file — into a
  self-referential edit. Same disposition `ci-job-budget.md` and
  `test-parsimony.md` took.
- **Receipt requirement:** SessionStart soft-gate `[ack: dev-integration-trunk]`
  IFF `posture.json::pending_verification` includes the `dev-integration-trunk`
  rule_id.
- **Detection mechanism:** structural for MUST-3/4, review for the rest.
  `unlanded-work-surface.js::resolveBaseRef` prefers `origin/dev` (override:
  `COC_LANDED_TARGET`) and `worktree-reap.mjs` uses the same order, so the reap
  classifier and the session-start surface agree on what "landed" means.
  `computePromotionGap` + `formatPromotionGapBlock` render the `dev..main` count
  at every SessionStart, fail-open (a null is "not measured", never "zero").
  MUST-1/2/5 are gate-review only, honestly: "is this lane finished" and "was this
  deploy authorised" are judgments, and MUST-2's real check is an API observation
  a hook cannot make at tool-call time. **No probe suite ships** — stated rather
  than naming a phantom path; the semantic tier is UNCOVERED and owed at
  gate-review via `/test-harness-probe`, the disposition `ci-job-budget.md`,
  `docker-no-sprawl.md` and `test-parsimony.md` also record.
- **Violation scope:** MUST-1 (work held off trunk) + MUST-2 (`dev` gains CI) +
  MUST-3 (predicate on the wrong base) + MUST-4 (uncounted gap / auto-promotion) +
  MUST-5 (deploy from `main`). Every `violations.jsonl` row names the surface.
- **Origin:** See § Origin.

## Origin

2026-09-10 — co-owner directive, verbatim: _"Lane work lands in dev immediately.
dev → main is a separate, deliberate promotion that costs exactly one CI run."_

**Adapted, not transplanted.** The directive's change table names
`.claude/bin/branch-landed-check.mjs` (`TARGET_DEFAULT`) and
`.claude/hooks/wip-closure-guard.js` (`TRUNK`). **Neither file exists in this
repo** — both are sibling-repo surfaces. Here the equivalents are
`unlanded-work-surface.js`, which resolves from `origin/HEAD` rather than a
constant and documents that as deliberate ("NO REPO-SHAPE ASSUMPTIONS"), and
`worktree-reap.mjs`. Implementing the named paths verbatim would have created two
dead files and left the live predicates pointed at `main`.

The directive's own escape clause was checked before adopting: *"any repo whose
gate does not trigger on main needs none of this."* Measured here — 16 workflows
on `pull_request`, 4 on `push: branches:[main]` including CodeQL, a required
context — so the constraint holds and the change is warranted.
