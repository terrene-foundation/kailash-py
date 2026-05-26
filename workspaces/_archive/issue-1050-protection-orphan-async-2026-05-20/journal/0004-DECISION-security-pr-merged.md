# DECISION — #1050 security PR merged; gates + CI receipts

**Date:** 2026-05-17
**Phase:** /implement → merge

## Outcome

PR #1057 merged to `main` at commit `344400235`. Issue #1050
auto-closed via `Fixes #1050`. Branch deleted.

## Durable receipts (verify-resource-existence MUST-4)

- **reviewer gate:** APPROVE (agentId aab794a9e60bdaf24). Round 1
  CHANGES-REQUIRED (1 HIGH: spec §4 stale, cited deleted `:367`,
  batched-deferral framing). Fixed in `0ce4c597f`. Round 2 (focused
  spec-delta re-review): APPROVE — all 5 checks pass, all citations
  grep-resolved on branch, spec-accuracy Rule 2 grep empty.
- **security-reviewer gate:** APPROVE (agentId ae900e8e84a9f8292).
  Zero CRITICAL/HIGH; all 7 audit dimensions PASS. 1 MEDIUM (M1) + 1
  LOW (L1), both scoped out-of-shard → follow-up.
- **CI:** PR-gate matrix 12/12 pass, 0 fail (Python 3.11-3.14,
  DataFlow Tier-1, PACT, infra, CodeQL, spec-drift). Watcher exit 0,
  manually re-verified `gh pr checks 1057` (0 fail count).
- **Local:** pyright 0/0/0 production source; Ruff clean; pre-commit
  all hooks; protection suites 38/38.

## Commits (4)

- `e876700d7` 1a — ProtectionViolation(NodeExecutionError) re-base
- `c27528938` 1b — async_run wiring + delete dead sync override +
  restore 2 gap-tests + I7 count→READ same-bug-class fix
- `97d198d4f` — pyright suppression-code correction (caught in verify)
- `0ce4c597f` — spec §4 present-tense conformance (reviewer HIGH)

## Carry-forward (value-anchored)

- **Shards 2/3/4** — now unblocked (Shard 1 merged). Value-anchors in
  `02-plans/01-shard-plan.md` (issue #1050 AC#1-3,6). Launch parallel.
- **Follow-up issue** — dead `AsyncSQLProtectionWrapper` removal +
  security-reviewer M1 (validation-before-protection ordering on
  Express path, defense-in-depth, I2 still holds) + L1 (`upsert`→
  CUSTOM_QUERY pre-existing enum gap, correctly blocked today).
  Distinct bug class, references merge `344400235`.
- **/release** — BUILD repo: `kailash-dataflow` ships to PyPI
  (build-repo-release-discipline; feedback_build_repo_release memory).
