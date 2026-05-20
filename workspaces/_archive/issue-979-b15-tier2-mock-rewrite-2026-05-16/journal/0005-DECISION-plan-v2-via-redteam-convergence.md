# DECISION — Architecture plan v2 lands after Round-1 REJECT → Round-2 APPROVE-WITH-FIXES

**Date**: 2026-05-15
**Phase**: /analyze convergence

## Decision

Adopt `02-plans/01-architecture-plan-v2.md` + `02-amendments-post-round2.md`
as the authoritative architecture for #992. Proceed to `/todos` (structural
human gate).

## Round history

| Round | Verdict                                                         | Findings                          | Pivots                  |
| ----- | --------------------------------------------------------------- | --------------------------------- | ----------------------- |
| 1     | REJECT (DataFlow) + APPROVE-WITH-FIXES (architecture + testing) | 1 CRIT + 13 HIGH across 3 reports | 3 load-bearing          |
| 2     | APPROVE-WITH-FIXES × 3 (post v2 rewrite)                        | 5 HIGH + 6 MED + 2 LOW            | 12 localized amendments |

Receipts (per `rules/verify-resource-existence.md` MUST-4):

- Round 1 reports: `04-validate/{01-redteam-architecture,02-redteam-dataflow,03-redteam-testing}.md`
- Round 2 reports: `04-validate/{04-redteam-round2-architecture,05-redteam-round2-dataflow,06-redteam-round2-testing}.md`

## Three load-bearing pivots from Round 1

1. **Drop v1 Cluster B (new tier-2 wiring file)** — real-PG coverage already
   exists at the singular-dir path (see `0001-DISCOVERY-duplicate-coverage-at-singular-dir.md`).
2. **Drop v1 Cluster C (File 4 PG-regression split)** — `_execute_workflow_safe`
   is now sync; the event-loop bug class is closed (see
   `0002-DISCOVERY-execute-workflow-safe-now-sync.md`). Regression test moves
   to `tests/regression/`; smoke test deleted.
3. **Use verified mock counts (128) not issue body claim (74)** — see
   `0003-DISCOVERY-mock-counts-stale-in-issue-body.md`.

## Twelve localized amendments from Round 2

Captured in `02-plans/02-amendments-post-round2.md` (A1–A12). Span:
filename convention, invariant math, commit-body rationale, pre-flight
bash, AST scan range, marker registration confirmation, follow-up gap
disposition, line-range re-verification at move time, assertion
simplification, tier-1-vs-tier-2 coexistence clarification, invariant
count, cluster description.

## Why v2 not v3

Round 2's 5 HIGH findings are localized text edits, not structural plan
changes. Per `rules/spec-accuracy.md` Rule 6 (historical change logs
permitted append-only) and the precedent of
`workspaces/issue-979-dataflow-unit-triage/02-plans/{01,02}-amendments-*.md`,
the amendments file is the legitimate pattern. No v3 file needed unless
Round 3 surfaces new structural issues.

## Pivots NOT taken (and why)

- **Not** added: a third shard for "new tier-2 lock-manager wiring test"
  — already exists at singular-dir path.
- **Not** added: a "file body update to #992 with corrected mock counts"
  task — out of scope per `rules/upstream-issue-hygiene.md` MUST-1 (no
  per-issue gate from user for editing). Verified counts captured in
  workspace journals + plan; sufficient.
- **Not** added: cross-SDK kailash-rs sibling sweep — out of scope per
  `rules/repo-scope-discipline.md`.

## Convergence verdict

Both Round 2 testing-specialist and dataflow-specialist explicitly noted
that all CRIT/HIGH findings from Round 1 are closed in v2. Round 2 new
findings are amendable in-place. No Round 3 needed.

Plan ready for `/todos` (structural human gate).
