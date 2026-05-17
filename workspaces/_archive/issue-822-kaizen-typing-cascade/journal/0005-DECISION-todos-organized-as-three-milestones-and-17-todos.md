---
type: DECISION
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: co-authored
session_id: issue-822-kaizen-typing-cascade
session_turn: /todos
project: kailash-py / issue-822-kaizen-typing-cascade
topic: 17-todo / 3-milestone organization for #822 typing cascade
phase: todos
tags:
  [
    issue-822,
    kailash-kaizen,
    todos-organization,
    shard-budget,
    autonomous-execution,
  ]
---

# DECISION — /todos organized as 3 milestones / 17 todos

**Date:** 2026-05-05
**Phase:** /todos
**Trigger:** human approved architecture plan; comprehensive todos required per `/todos` workflow Step 3

## Decision

Organize the issue #822 work as 17 todos across 3 milestones:

- **Milestone 1 — Shard 1 (Type Safety + Real Bug Fix)**: 7 todos (1.1–1.7)
- **Milestone 2 — Shard 2 (Orphan-Import Deletion)**: 5 todos (2.1–2.5)
- **Milestone 3 — Release + Cross-SDK Coordination**: 5 todos (3.1–3.5)

Each todo carries:

- Implements ref (architecture plan section)
- Spec target (post-merge spec edit, per `specs-authority.md` Rule 5)
- LOC estimate
- Invariant count (tracked against `autonomous-execution.md` Rule 1 budget)
- Call-graph hops
- Feedback-loop command

## Trade-offs evaluated

### Granularity: 17 vs ~30 vs ~6

- **30 micro-todos** (1 per source-edit site): too fine; tracking overhead exceeds shard budget; loses the conceptual unit.
- **6 mega-todos** (one per shard ÷ ship-step): violates "describable in 3 sentences" — each would mix typing fixes with regression tests with PR plumbing.
- **17 todos** (chosen): each is one conceptual change with one acceptance gate. Closing PR todos (1.7, 2.5) are intentionally separate so the structural gate (admin-merge) is its own checkpoint.

### Shard 2 disposition: delete vs NotImplementedError

Architecture plan § Open Question #1 surfaces both options. User approved (the
plan recommends delete + CHANGELOG entry). Todos 2.1–2.5 implement that path.
The NotImplementedError fallback path is preserved in journal/architecture for
audit trail; not implemented as todos.

### Release surface: 2.18.3 patch vs 2.19.0 minor

Architecture plan § Open Question #2 + reviewer Round 1 M4 confirm 2.19.0 minor
(existing `[Unreleased]` already accumulates 5+ minor-bump-shaped entries; Shard 2
adds BREAKING removals that mandate a minor bump per `rules/zero-tolerance.md`
Rule 6a). Todo 3.1 implements 2.19.0.

### Follow-ups (HUMAN-GATED)

Two follow-up issues identified during /analyze:

- Cross-SDK orphan-pattern audit against `esperie/kailash-rs` (`cross-sdk-inspection.md` Rule 1)
- LLM-first rewrite of `_generate_role_based_traits` (`agent-reasoning.md` Rule 1)

Both filed as HUMAN-GATED todos (3.3, 3.4) per `rules/upstream-issue-hygiene.md`
Rule 1 — drafting body is permitted, submission requires explicit user approval
IN THE SAME SESSION.

## Why this matters

The 12-todo structure provides:

1. **Shard-budget enforcement** — every todo carries an explicit invariant count
   and LOC estimate, audit-able against `autonomous-execution.md` Rule 1.
2. **Spec-update discipline** — todos 1.6 + 2.4 carry the spec edits at
   first-instance per `specs-authority.md` Rule 5; spec lag is impossible.
3. **Release discipline** — todo 3.1 invokes the full
   `build-repo-release-discipline.md` protocol (enumerate scope, release kaizen,
   sweep stale siblings, verify installability from clean venv).
4. **Closure traceability** — todo 3.5's closing comment cites both PR SHAs +
   PyPI version + cross-SDK + LLM-first follow-ups, making `git log --grep`
   audit-able.

## Action

- 17 todo files written to `todos/active/` (1.1–1.7, 2.1–2.5, 3.1–3.5).
- /todos workflow Step 4 (red-team) covered by Round 1 (analyst + reviewer)
  already applied to architecture plan; todos derive directly from the revised
  plan with no new structural decisions.
- /todos workflow Step 5 — STOP for human approval — pending.

## For Discussion

1. **Counterfactual:** would a 6-mega-todo organization (one todo per ship-step,
   collapsing build + test + spec + PR into one file) be cheaper at /implement
   time? The 17-todo split costs ~3× more file-management overhead but produces
   independent acceptance gates per conceptual change. Worth it?
2. **Specific data:** Shard 2's LOC estimate is ~440 (375 source + ~65 test
   sweep). The architecture plan claims this fits Rule 1 because "deletion-heavy
   boilerplate; single conceptual change." But Rule 1 §2 says boilerplate
   scales 5× the base 500-LOC budget — so deletion-heavy COULD be ~2500 LOC
   before sharding triggers. Is 440 conservative or are we leaving multi-shard
   parallelism on the table?
3. **Alternative:** todos 3.3 and 3.4 are both HUMAN-GATED follow-up issue
   filings. Could they be deferred entirely (filed by the user OUTSIDE the
   workspace) rather than tracked as workspace todos? The current shape keeps
   them visible; the alternative reduces todo count but loses the audit trail.

## References

- `02-plans/01-architecture.md` (revised) — source of truth
- `04-validate/03-revisions-round-1.md` — applied revisions
- `rules/autonomous-execution.md` Rule 1 — shard budget per todo
- `rules/specs-authority.md` Rule 5 + `rules/spec-accuracy.md` Rule 5 — spec-edit timing
- `rules/build-repo-release-discipline.md` Rules 1–4 — release scope
