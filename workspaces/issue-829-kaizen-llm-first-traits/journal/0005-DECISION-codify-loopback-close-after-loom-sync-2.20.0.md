---
type: DECISION
date: 2026-05-06
session: codify-loopback-after-loom-sync
---

# Codify loop-back close after loom 2.17.0 → 2.20.0 sync

## Context

Loom completed `/sync-to-build py` mid-session. Working tree now carries the
2.20.0 distribution, including:

- **3 NEW rules**: `coc-sync-landing.md`, `hook-output-discipline.md`, `sync-completeness.md`
- **1 NEW hook**: `coc-drift-warn.js` (wired into `settings.json` SessionStart)
- **1 NEW guide-extract**: `guides/rule-extracts/coc-sync-landing.md`
- **1 NEW audit-fixtures dir**: `.claude/audit-fixtures/violation-patterns/detectRepoScopeDriftBash/`
- **AMENDED rules**: `autonomous-execution.md` (Rule 4 trigger broadened — our proposal),
  `testing.md` (Tier-1 Conftest Stub subsection — our proposal),
  `worktree-isolation.md` (priority demoted 0→10, scope path-scoped per loom 2.19.0 cap-headroom)
- **MODIFIED hook lib**: `.claude/hooks/lib/violation-patterns.js` — `detectRepoScopeDriftBash`
  shell-variable false-positive fix
- **VERSION bump**: 1.0.6 → 1.0.7 (loom 2.17.0 → 2.20.0; canonical sync-completeness MUST-3
  schema migration with `upstream.build_version` retained one cycle for back-compat)
- **Proposal status**: `pending_review` → `reviewed` → `distributed` (loom Gate 1+2 complete)

## Decision

This /codify cycle is a **loop-back close**, not a fresh extraction.

**Rationale:**

- Learning digest hash unchanged (`sha256:e0f13`) since prior cycle (last_codified 2026-05-06T18:30Z).
- Journals 0001-0004 already capture the substantive work of issue #829.
- The proposal lifecycle reached terminal state `distributed`. No new patterns from THIS
  loop-back warrant new rules / agents / skills:
  - The "sync arrives as working-tree drift" pattern is exactly what `coc-sync-landing.md`
    was authored to handle (loom-side codification of this same surface, Origin 2026-05-02).
  - The polling-cadence-while-waiting (5 polls × ~30 min over ~105 min) is generic /loop
    usage, not novel enough for codification.
  - The artifact-flow lifecycle (`pending_review` → `reviewed` → `distributed`) worked as
    designed.

**Step 6b (Trust Posture Wiring) is N/A** — no new rules authored in this cycle. The 3 new
synced rules came in via loom Gate 2 distribution, not via local /codify authorship.

## Findings (surface-only, no autonomous filing)

### F1: `coc-sync-landing.md` shipped without Trust Posture Wiring section

```bash
grep -n "Trust Posture Wiring" .claude/rules/coc-sync-landing.md   # → empty
grep -n "Trust Posture Wiring" .claude/rules/hook-output-discipline.md  # → 198
grep -n "Trust Posture Wiring" .claude/rules/sync-completeness.md       # → 192
```

Per `commands/codify.md` Step 6b ENFORCEMENT: "cc-architect MUST grep each new rule file
for the literal `## Trust Posture Wiring` header AND verify all 7 fields present in the
section body (severity / grace / cumulative / regression-within-grace / receipt /
detection / first-violation / origin). Missing or incomplete → audit FAIL → /codify halts."

This is a **loom-side enforcement gap** — the rule was authored at loom and synced down.
The two sibling new rules (`hook-output-discipline.md`, `sync-completeness.md`) DO carry
the wiring. Per `repo-scope-discipline.md`, this finding is surfaced for user review only
— no autonomous file/edit upstream.

**Disposition:** user decides whether to surface to loom for next codify cycle there.

### F2: 3 `.pending/` stub journals discarded

`SessionEnd` hook auto-generated commit-message reflection stubs after 2026-05-05 commits
(`8f0950af`, `ba476b88`, `86334ec4`). Content was already covered by promoted journals
0001-0004. Per the stubs' own instructions ("Discard: rm this file"), removed.

### F3: Sync drift requires PR-landing per `coc-sync-landing.md` Rule 1

Working tree currently carries the loom 2.20.0 distribution as uncommitted drift on `main`.
Per the just-synced `coc-sync-landing.md` Rule 1: "COC Drift Lands as PR #1. Land it FIRST.
Non-COC-PR workarounds BLOCKED. Cross-session carry BLOCKED."

Per BUILD-repo standing feedback, agent does NOT autonomously commit/push in kailash-py —
this is the user's gate. Surfaced to user for staging + admin-merge per Rule 2 (stage
explicit paths) + Rule 3 (admin-merge per owner workflow).

### F4: Pre-existing 107 `<Mock name=...>.md` files in `docs/`

Created 2026-04-15 (well pre-dating session start, gitignored, not tracked). Symptom of
a doc-build test that didn't mock `test_workflow.name` properly. Pre-existing per
zero-tolerance Rule 1c (SHA-grounded: file mtimes 21 days before session start, not
tracked). **Out of scope for this codify cycle** — surface only. Separate workspace can
address if user prioritizes.

## What unlocks for the next session

- Loop-back proposal status is recorded (`distributed`, learning-codified.json updated).
- Issue #829 workspace is closeable: todos all in `completed/`, journal complete (0001-0005),
  redteam Round 1 clean, codify loop-back closed. Workspace can be archived or referenced
  by future kaizen sessions.
- Synced 2.20.0 rules + hook are in working tree, awaiting user-gated PR #1 landing per
  `coc-sync-landing.md`.

## Alternatives considered

- **Author a new rule for the polling-cadence pattern** — rejected. Pattern is generic
  /loop usage; not specific enough to deserve a rule. The /loop skill already documents
  this.
- **File upstream issue against loom for F1 (coc-sync-landing.md missing wiring)** —
  deferred per `upstream-issue-hygiene.md` MUST Rule 1 (human gate before filing).
  User decides whether to surface.
- **Promote one of the .pending stubs to a real journal** — rejected. Content was
  already in 0001-0004; promoting would be duplication.
