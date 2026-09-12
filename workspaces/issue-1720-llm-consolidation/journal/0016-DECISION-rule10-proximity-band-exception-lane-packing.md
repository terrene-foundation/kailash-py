# 0016 — DECISION: Rule-10 proximity-band exceptions for the lane-packing codify

Date: 2026-09-12
Covers: `d94f597ff` (codify: WIP ceilings bind LANES, never agents)

## Why this receipt exists — a self-caught Rule-10 miss

`d94f597ff` added load-bearing content to TWO `priority: 0` / `scope: baseline` rules
(`agents.md` § Triad, `autonomous-execution.md` Rule 1) while the lane sat at 11.1%
headroom — inside Rule 10's 15% proximity band. The commit claimed compliance via
**path (a) paired extraction**: the § Root-Cause Fix 12-phrase BLOCKED corpus moved from
`autonomous-execution.md` to `guides/rule-extracts/autonomous-execution.md`, 665 B of
source out, 224 B pointer in.

**That extraction recovered ZERO emitted bytes, so path (a) was never satisfied.**

Measured after a lane's forensics established how to measure at all
(`emit.mjs` pipes each rule through `composeRule → stripRuleFrontmatter → abridgeV6 →
stripSlotMarkers`, and `abridgeV6` strips whole H2 sections — `Trust Posture Wiring`,
`Examples`, `Origin:` — plus the BLOCKED corpora):

```
source   pointer-form : 16014          ABRIDGED pointer-form: 7672
source   full-corpus  : 16455 (+441)   ABRIDGED full-corpus : 7672 (delta 0)
pointer survives abridgement: false
CONTROL (a preserved MUST phrase survives): true
```

The control fires, so the instrument can return the other answer. The extraction moved
441 B of source that `abridgeV6` was ALREADY discarding. The additions, by contrast,
landed in preserved regions and are genuinely emitted.

**Method note for the next session — this is the reusable part.** Measure Rule-10
headroom by editing INSIDE a preserved MUST / `**Why:**` region, NEVER by appending to
EOF. Most baseline rules end in a stripped `Trust Posture Wiring` / `Origin` / `Examples`
section, so an EOF append is guaranteed to read as zero delta and will look like the
emitter is blind. It is not: a 5000 B insert into a preserved MUST body moved the lane
from 58263 B / 11.1% to 63263 B / 3.47% — a floor breach the gate reported correctly.
**Rule 10's gate is LIVE in this repo and discriminates.** The earlier in-session claim
that it might be inert is WITHDRAWN; the probe was placed in dead space, not the gate.

Disposition: path (a) is unavailable without trimming another baseline rule's LIVE
emitted text to fund this one, so both rules take **path (b)**, below, per rule as
Rule 10 § "Composite + new-rule additions" requires.

---

Rule-10-exception: agents.md

(i) **Bytes added on lane-of-concern:** +354 B emitted, measured as
`abridgeV6(stripRuleFrontmatter(...))` length at `d94f597ff^` → `d94f597ff`
(10213 → 10567). Aggregate lane figure from `emit.mjs --all --dry-run`: 57801 B → 58263 B.

(ii) **Lane-of-concern headroom_pct:** 11.8% → 11.1% (codex and gemini identical; band
15%, floor 10%, cap 65536 B). Above the floor — this is a band exception, not a breach.

(iii) **Calendar/horizon constraint:** no further baseline-MUST additions are planned in
this repo within 14 days. The remaining queued work (#2230, #2231, #1971) is SDK code and
touches no `scope: baseline` rule. The lane-packing contract is complete as landed; its
depth already lives path-scoped and needs no follow-on baseline addition.

(iv) **F23b escalation surface:** if `agents.md` on this lane needs another Rule-10
invocation within 30 days, `rule-authoring.md` MUST Rule 11 fires and escalates to
corpus-level pruning review — split, demote to path-scoped, or extract-to-skill+pointer —
rather than another addition-local exception. Recorded here so the 30-day clock has a
citable anchor.

(v) **Absence-of-skill-extension-host:** the addition IS ALREADY the extracted form. The
full contract (MUST-1 lane-keyed ledger, MUST-6 packing, the three bounds, DO/DO-NOT, the
BLOCKED corpus, the Wiring) lives in `orchestration-launch-ledger.md` — `priority: 10`,
`scope: path-scoped`, which pays ZERO baseline emission. What landed in `agents.md` is a
single always-on POINTER sentence. Candidate hosts considered and rejected:
`skills/30-claude-code-patterns/parallel-dispatch-default.md` (already the § Triad depth
host — moving the pointer there reproduces the exact reachability gap, since a dispatch
decision touches no file that loads a skill); `orchestration-launch-ledger.md` itself
(it IS the host for the depth — but its `paths:` are `workspaces/**`, `.session-notes*`,
`journal/**`, and an orchestrator CHOOSING a wave shape may touch none of them, which is
the `issue-triage-routing.md` reachability class); a new baseline rule (strictly worse —
a whole new baseline rule costs more than 354 B). The residual 354 B is the irreducible
always-on pointer; removing it silently restores the serial-worker default at exactly the
moment the decision is made.

---

Rule-10-exception: autonomous-execution.md

(i) **Bytes added on lane-of-concern:** +102 B emitted, measured the same way
(7570 → 7672 abridged, `d94f597ff^` → `d94f597ff`).

(ii) **Lane-of-concern headroom_pct:** 11.8% → 11.1% (the same lane movement; the two
rules' deltas are components of the one aggregate, not separate lane movements).

(iii) **Calendar/horizon constraint:** as above — no further baseline-MUST additions
planned within 14 days.

(iv) **F23b escalation surface:** as above; a second Rule-10 invocation against
`autonomous-execution.md` on this lane within 30 days fires MUST Rule 11 and escalates to
corpus-level review rather than another exception.

(v) **Absence-of-skill-extension-host:** structurally non-decomposable — it is a
CORRECTION to an existing sentence, not new prose. Rule 1 read "A single shard (one
session, one worktree, one implementation pass)"; the parenthetical binding the shard
budget to a WORKTREE is precisely what forbids packing many agents into one lane, so the
lane-packing contract is unenforceable while that sentence stands. A correction cannot be
extracted to a skill: the wrong text would remain in the emitted baseline and the skill
would contradict it. Candidate hosts considered and rejected:
`guides/rule-extracts/autonomous-execution.md` (holds this rule's depth, but a rule-body
sentence cannot be corrected from a non-emitted extract); deleting the parenthetical
outright rather than replacing it (loses the ≤500-LOC-per-pass binding entirely, which is
a real loss, not a saving). The 102 B is the minimum edit that makes the existing clause
true under the new contract.

---

## What is NOT claimed here

- No claim that path (a) was satisfied. It was not, and the commit body that implied it is
  corrected by this receipt rather than amended (`git.md` § Discipline: push a follow-up,
  never amend a pushed claim).
- No claim that the aggregate `emit.mjs` figure decomposes exactly into the two per-rule
  deltas: +354 and +102 sum to 456 against an aggregate movement of 462. The 6 B gap is
  unexplained — most likely per-rule joiners in `emitBaseline` — and is recorded rather
  than rounded away. It does not change either verdict.
- `.claude/bin/check-baseline-delta.mjs`, which consumes the `Rule-10-exception:` binding
  token, is NOT present in this repo (it is loom-side). The token is written in canonical
  form for the cc-architect sweep and for portability, not because a local checker reads
  it. Stated so no reader infers a mechanical gate that does not exist here.
