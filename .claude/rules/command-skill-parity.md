---
priority: 10
scope: path-scoped
paths:
  - ".claude/commands/**"
  - ".claude/skills/**"
---

# Command↔Skill Parity — The Split-Artifact Pair Stays In Sync

The `cc-artifacts.md` Rule 3 split (command = entry point ≤150 lines; skill = procedure
depth) makes a command and its backing skill **two artifacts describing ONE procedure**.
Wherever both surfaces state the same step — a `Print:`/hand-off string, a STOP/gate
predicate, a precondition, a step ordering, a cited field/branch/lockfile/helper name, or a
guard's create→teardown lifecycle — they are two copies of ONE contract, and an edit to one
copy that does not move the other drifts the pair: whoever follows the skill (the
procedure-of-record) diverges from what the command (the entry point) promises. When the
drifted step is a **security guard's lifecycle**, the drift is a security regression that
diff-level, single-file review cannot see — each surface is individually coherent, only the
pair is wrong. This rule governs the SHARED-STEP CONTENT the pair holds in common — not the
split itself (`cc-artifacts.md` Rule 3) nor reference resolution (that rule's § "No Dangling
Cross-References").

## MUST Rules

### 1. A Shared-Step Edit Updates The Command↔Skill Mirror In The Same Shard

When a command (`.claude/commands/X.md`) and its backing skill (`.claude/skills/NN-X/SKILL.md`)
both describe the same procedure step — a `Print:`/hand-off string, a STOP/gate predicate, a
precondition, a step ordering, a cited field/branch/lockfile/helper name, or a guard's
create→teardown lifecycle — an edit to that step in EITHER surface MUST update the mirror in
the SAME change. Editing the command's shared step and deferring the skill (or vice versa) is
BLOCKED. This is `security.md` § "Multi-Site Kwarg Plumbing" one abstraction up: the command
and skill are two call sites of one contract; both move in the same PR.

```text
# DO — edit the shared step in BOTH surfaces in one shard
command C5 print: "Each TEAMMATE now runs /enroll…"   +   skill C5 print: "Each TEAMMATE now runs /enroll…"
(the print strings are byte-aligned; a `diff` of the two Print: lines is empty)

# DO NOT — edit the command's shared step, leave the skill's mirror stale
command B3: "Enrollment PR opened. Once it merges to main, run /onboard"
skill   B3: "Enrolled. Run /onboard"   ← an orchestrator following the skill diverges
```

**BLOCKED rationalizations:**

- "The command is authoritative; the skill will be reconciled later"
- "The skill is just detail; the command's version is what matters"
- "They're close enough — the reader will infer the intent"
- "It's a one-line print string, not worth touching two files"
- "/redteam will catch the drift" (it does — as a finding this rule exists to prevent at authoring time)

**Why:** The command and skill are the same contract stored twice; a reader follows exactly
one of them and never sees the other. A shared-step edit to one is a silent divergence for
every reader of the other. Moving both in the same shard is the only point the pair is
guaranteed consistent — a deferred mirror is a divergence that ships. Evidence: the
re-convergence #5 enroll B3 + ecosystem C5 print strings each drifted when the command was
edited but the skill was not (one pair introduced by fixing the command alone).

### 2. `/redteam` Runs A Command↔Skill Parity Sweep

A `/redteam` round over a repo carrying command+skill pairs MUST include a mechanical
command↔skill parity sweep: for EACH pair, compare the shared-step axes — (a) literal
`Print:`/hand-off strings (`diff` the lines; byte-identical or a stated consistent
depth-difference), (b) step ordering, (c) STOP/gate predicates, (d) cited
field/branch/lockfile/helper names, (e) guard lifecycle. A same-step CONTRADICTION between a
command and its skill is a finding: **MED**, escalating to **HIGH** when the drift sends an
operator to a wrong/redundant command OR drops a security guard. A command-terse /
skill-detailed asymmetry (the Rule-3 split working as intended) is NOT a finding — only
same-step contradictions are. Scoping the redteam to single files without the cross-pair
sweep is BLOCKED (the divergence is invisible at single-file granularity).

```text
# DO — per-pair sweep across the 5 axes
for (cmd, skill) in pairs: diff Print: lines; compare STOP predicates; compare cited names…
  → contradiction on a shared step = finding (MED/HIGH)

# DO NOT — review each command and each skill in isolation
# (each file is internally coherent; the pair contradiction never surfaces)
```

**BLOCKED rationalizations:**

- "I reviewed every command and every skill; the pair is implied"
- "The parity sweep is redundant with the per-file review"
- "Command↔skill drift is an authoring concern, not a redteam concern"

**Why:** Single-file review reads each surface as internally consistent; the contradiction
lives in the DELTA between the two files, which only a cross-pair comparison surfaces. The
re-convergence #5 certify security divergence (below) was invisible to five prior review
lenses and surfaced ONLY when the command↔skill parity sweep ran.

### 3. A Cited Guard's Lifecycle Is Verified To Span The ENTIRE Protected Window

When a command↔skill pair cites a security / enforcement guard (a lockfile-gated hook, a
posture gate, a state-mutation tripwire) that protects an activity, the guard's lifecycle —
its create AND its teardown — MUST be verified to span the ENTIRE protected activity,
including retry loops, re-entry, and abandon paths, in BOTH the command and the skill. "The
guard is registered / wired" is NOT "the guard covers the whole window": a teardown placed
before a retry loop leaves that loop unguarded even though the hook is correctly registered.
A guard whose teardown precedes any part of the activity it protects is BLOCKED.

```text
# DO — the guard spans the whole protected window in both surfaces
certify no-assist lockfile: created at Phase B (probe), removed at Phase C EXIT
(pass OR abandon) — so the Phase C gate RETRY LOOP that re-asks failed questions stays guarded

# DO NOT — teardown before the retry loop the guard exists to protect
skill removes the lockfile "before Phase C begins" while Phase C re-runs the probe on
failed questions → the retries run with the no-assist guard already gone (hook was registered,
but inert on the skill-followed path)
```

**BLOCKED rationalizations:**

- "The hook is registered in settings.json, so the gate has teeth" (registered ≠ covers the window)
- "Phase C doesn't need the guard — it doesn't do retrieval" (the retry loop re-runs the guarded activity)
- "The prose refusal covers the gap" (prose is belt; the structural guard is the suspenders — the lesson is that the suspenders were removed)

**Why:** A security guard's value is the window it covers, not the fact of its registration.
A lifecycle that opens the guard but tears it down mid-activity ships a protected surface
with an un-guarded hole — and because the hole is on ONE execution path (the skill's), the
diff-level review of the wiring says "guard present" while the runtime says "guard absent
during the retries." Evidence: the `/certify` `probe-phase-guard` lockfile (a prior security
closure, wired into committed settings in kailash-py #1623) was removed before the Phase C
gate retry loop in the skill; an orchestrator following it could be coached through the
retries with no structural guard.

## MUST NOT

- Ship a command↔skill pair where a shared step (print / gate / precondition / ordering /
  cited name / guard lifecycle) contradicts between the two surfaces

**Why:** The reader follows one surface; a contradiction is a silent divergence for every
reader of the other.

- Treat "the hook is registered" as proof the guard covers the whole protected activity

**Why:** Registration is necessary, not sufficient; a teardown mid-activity leaves an
un-guarded window on the path that tears down early.

- Scope a `/redteam` of command+skill artifacts to single files without the cross-pair sweep

**Why:** The divergence is in the delta between the paired files, invisible at single-file
granularity.

## Trust Posture Wiring

- **Severity:** `halt-and-report` at gate-review (reviewer at `/implement` + cc-architect at
  `/codify` run the per-pair parity sweep; security-reviewer runs the MUST-3 guard-lifecycle
  check when a cited guard is security/enforcement). `advisory` at the hook layer — a
  command↔skill shared-step contradiction is a cross-file semantic-judgment property, not a
  single tool-call structural signal, so per `hook-output-discipline.md` MUST-2 a lexical
  detector MUST NOT carry `block`.
- **Grace period:** 7 days from rule landing (2026-07-08 → 2026-07-15).
- **Cumulative posture impact:** same-class violations (a shared-step command↔skill divergence
  shipped; a guard teardown preceding its protected window; a `/redteam` scoped without the
  parity sweep) contribute to `trust-posture.md` MUST Rule 4 cumulative-window math (3× same-rule
  in 30d → drop 1 posture; 5× total in 30d → drop 1 posture).
- **Regression-within-grace:** any same-class violation within 7 days routes through the GENERIC
  `regression_within_grace` emergency trigger per `trust-posture.md` MUST Rule 4 (1× = drop 1
  posture) — no dedicated trigger key (a cross-file semantic-judgment property does not warrant an
  instant-drop key, and minting one would append load-bearing content to the self-referential
  `trust-posture.md`; the same disposition `journal.md` + `symbol-anchored-citations.md` took).
- **Receipt requirement:** SessionStart soft-gate `[ack: command-skill-parity]` IFF
  `posture.json::pending_verification` includes this rule_id (set at land-time, cleared after grace).
- **Detection mechanism:** Phase 1 — review-layer mechanical sweep. cc-architect / reviewer at
  `/codify` + `/implement`, and the `/redteam` command↔skill parity sweep (MUST-2), enumerate every
  `.claude/commands/X.md` ↔ `.claude/skills/NN-X/SKILL.md` pair and `diff`/compare the 5 shared-step
  axes; security-reviewer runs MUST-3 for any cited security/enforcement guard. Phase 2 (deferred per
  `trust-posture.md` § Two-Phase Rollout, after ≥3 real sessions exercise Phase 1) — an advisory
  `.claude/hooks/lib/violation-patterns.js` detector flagging a `Print:` line present in a command but
  absent/divergent in its paired skill (lexical, advisory; paired with the Phase-1 reviewer per
  `probe-driven-verification.md` MUST-4). Audit fixtures land WITH the Phase-2 detector at
  `.claude/audit-fixtures/command-skill-parity/` per `cc-artifacts.md` Rule 9.
- **Violation scope:** MUST 1 (same-shard mirror edit), MUST 2 (redteam parity sweep), MUST 3
  (guard-lifecycle spans the window). Every `violations.jsonl` row records which MUST clause fired.
- **Origin:** See § Origin.

## Distinct From / Cross-References

- **Extends** `cc-artifacts.md` Rule 3 (creates the pair) — this rule keeps the pair's shared-step
  content in sync; **distinct from** that rule's § "No Dangling Cross-References" (reference
  resolution, not content parity).
- **Artifact-prose analogue of** `security.md` § "Multi-Site Kwarg Plumbing" — command + skill are
  two call sites of one contract.
- **Pairs with** `user-flow-validation.md` MUST-4 (the walk surfaces the operator consequence; this
  rule blocks the drift at authoring + adds the sweep). **Composed by** `commands/redteam.md`
  § 1 "Spec compliance audit" via MUST-2 (`redteam.md` invokes the parity sweep for command+skill repos).

## Origin

2026-07-08 — a kailash-py onboarding-suite independent re-convergence (`journal/0032`). The
`/certify` no-assist gate (`probe-phase-guard.js`, a prior security-HIGH closure; wired into
kailash-py committed `settings.json` in PR #1623) was inert on one execution path: the command
(`certify.md`) kept the lockfile through the Phase C gate retry loop; the backing skill
(`42-certify`) removed it before Phase C, whose loop re-runs the probe on failed questions. An
orchestrator following the skill tore the guard down during the retries it protects. The
divergence was invisible to five OTHER review lenses in the same convergence (registration
parity, symbol existence, distributable invariant, lifecycle walk, cross-reference) and surfaced
ONLY when a command↔skill parity sweep ran; two sibling print-string divergences (enroll B3,
ecosystem C5) were also introduced by editing a command without its skill. Landed BUILD-side
(kailash-py) with the multi-agent redteam-with-tests that IS the `self-referential-codify.md`
Rule 1 gate; routed to loom via the BUILD→loom proposal for cross-SDK + downstream distribution
(the same skill/hook pair exists wherever the onboarding suite was synced).

**Length rationale (per `rule-authoring.md` MUST NOT § "Rules longer than 200 lines").** ~214
lines, over the 200 guidance. Named rationale: the residual is irreducible — three MUST clauses each carrying the
mandatory DO/DO-NOT + BLOCKED-corpus + `**Why:**` (`rule-authoring.md` Rules 2/3/4) plus the
canonical 8-field Trust Posture Wiring (`trust-posture.md` MUST-8, ~30 non-decomposable lines). The
intro, Origin, and Distinct-From were already trimmed; collapsing a MUST's example or BLOCKED
corpus would weaken the structural defense. `priority: 10` + `scope: path-scoped` → pays no baseline
budget. Sibling precedent: `user-flow-validation.md` + `recommendation-quality.md` length rationales.
