---
type: CONNECTION
date: 2026-05-14
created_at: 2026-05-14T23:55:00Z
author: agent
session_id: shard-2-implementation
session_turn: post-review
project: kailash-py
topic: correct base-SHA framing in journal/0006 per reviewer LOW finding
phase: implement
tags: [issue-1002, shard-2, journal-correction, localruntime-leak]
---

# 0007 CONNECTION — correct base-SHA framing in journal/0006

Per `rules/journal.md` § MUST NOT (Overwrite existing entries — immutable once
created; new entry references the original), this entry corrects a clerical
framing error in `journal/0006-DISCOVERY-dataflow-leaks-localruntime-reference.md`
flagged by the gate-level reviewer at LOW severity during Shard 2 review.

## Correction

`journal/0006:43` references commit `52b8e7f6` as "the branch's base SHA" for the
LocalRuntime leak reproduction protocol. That framing is technically incorrect:

- `52b8e7f6` IS Shard 2's first commit (`fix(dataflow): sync DataFlow.close()
closes cached AsyncSQLDatabaseNode (#1002)`) — NOT the pre-Shard-2 base.
- The actual pre-Shard-2 base SHA is `b0ba53ef` (the `main` branch HEAD at
  Shard 1 merge, before Shard 2 branched).

## Why the empirical claim still holds

The reproduction protocol journal/0006 documents — `git checkout main --
packages/kailash-dataflow/tests/unit/migrations/test_batched_migration_executor.py
packages/kailash-dataflow/tests/unit/migrations/test_migration_performance_tracker.py;
pytest ...` — restores the AFFECTED test files to their `main` state, which
is identical to their state at commit `52b8e7f6` (Shard 2's first commit
touched `engine.py` and the new regression test file, NOT the test files
named in the reproduction protocol). So the warning reproduces in BOTH:

1. `main` (HEAD `b0ba53ef`) — the true pre-Shard-2 base
2. `52b8e7f6` on the branch — Shard 2's first commit

Either witness proves pre-existing per `rules/zero-tolerance.md` Rule 1c (any
"pre-existing" disposition MUST cite a commit SHA pre-dating the session's
first tool call — `b0ba53ef` IS that SHA).

## Verified-pre-existing receipts

- Witness 1: `git show main:packages/kailash-dataflow/tests/unit/migrations/test_batched_migration_executor.py | pytest -W error::ResourceWarning ...` → 11 warnings present on `main` (verified this session).
- Witness 2: same suite re-run at branch HEAD with `git checkout main --` on those two files → same 11 warnings (verified this session per the PR's broader-sweep pytest result).

Both receipts confirm the LocalRuntime leak is pre-existing on `main` at SHA
`b0ba53ef`; Shard 2 does not introduce it.

## Disposition unchanged

The LocalRuntime leak remains:

1. Pre-existing on `main` (verified — see receipts above)
2. A Core SDK + DataFlow plumbing class distinct from Shard 2's test-fixture-leak class
3. Out of Shard 2 scope per `workspaces/issue-1002-aiosqlite-fixture-cleanup/02-plans/01-architecture-plan.md`
4. Recommended for Shard 3 or a separate workstream

This entry corrects ONLY the prose framing of "base SHA" in journal/0006:43; it
does not change the leak's verified-pre-existing status, its scope-out
disposition, or the Shard 2 review verdict (PASS — security-reviewer + reviewer
both clean).

## For Discussion

1. **Counterfactual:** If `52b8e7f6` HAD introduced the LocalRuntime leak (a
   world where Shard 2's engine `close()` fix accidentally widened the leak
   surface), would the journal/0006 reproduction protocol have caught it?
   Answer: yes — the protocol restores `test_batched_migration_executor.py`
   and `test_migration_performance_tracker.py` to their state at the commit
   under test; on a branch where Shard 2 widened the leak, the witness file's
   state at `52b8e7f6` would be identical to `main` (Shard 2 didn't touch
   those files), so the reproduction would show MORE warnings, not the same
   warnings — surfacing the regression. The reproduction is sound; only the
   prose-framing of "base SHA" is wrong.
2. **Data-grounded check:** how many post-merge sessions can read journal/0006
   without follow-up SHA confusion? The original entry's reproduction commands
   are executable and produce the same evidence regardless of the framing
   error, so the institutional cost of the original wording is bounded to "a
   reviewer raises a LOW on the next read." This correction eliminates that
   future-reader cost.
3. **Policy question:** for same-session reviewer-surfaced clerical errors in
   journal entries, is "new corrective entry" the right disposition vs an
   in-place amendment? The current journal.md MUST NOT mandates immutability
   even for same-session corrections — does this overhead make sense for
   clerical (vs substantive) errors? Disposition for now: respect the rule;
   new entries are append-only and cheap; in-place edits silently lose audit
   trail. (Could be revisited at /codify if recurrent.)

## Consequences

- The Shard 2 PR description continues to cite `52b8e7f6` (the engine fix
  commit), which is correct as the FIRST commit in the Shard 2 chain. No PR
  description edit required.
- Future readers of journal/0006 SHOULD read this entry adjacent to it for
  the corrected SHA framing.
- No code change. No test change. No further reviewer round-trip required.

## Follow-up actions

None — clerical correction only.
