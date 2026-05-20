# DISCOVERY — File 10 (`performance/test_postgresql_test_manager_concurrent.py`) recovered at /todos red team

**Date**: 2026-05-15
**Phase**: /todos red team
**Source**: analyst red-team finding N-5 (`04-validate/07-redteam-todos.md` — returned inline; not written to file) + manual verification

## What we found

The issue body table at `gh issue view 992` lists **10 files**, but the body's prose claim says "Total: ~74 mock sites across 9 files." The /analyze phase's classification audit took the prose count (9) and silently dropped one file from the table: `performance/test_postgresql_test_manager_concurrent.py` (11 mocks per issue body — verified `grep -cE` confirms 11).

Read the file directly: docstring (lines 1-5) self-declares **Tier-1** intent:

> "Unit tests for PostgreSQL Test Manager concurrent access functionality.
> Tests isolated concurrent access components and logic.
> Tier 1 tests (<1 second timeout) with mocking allowed."

Class decorator: `@pytest.mark.unit`, `@pytest.mark.timeout(1)`. Pure Cluster-A pattern — mechanical Tier-1 move.

## Why this matters

Without this discovery, S1 would have shipped, the issue would have stayed "open until we figure out the 10th file," and the next session would inherit a workspace with an unstated scope drift. Classic value-prioritization MUST-3 failure mode (deferral as forgetting).

## Disposition

Add File 10 to S1's scope:

- Source: `packages/kailash-dataflow/tests/integration/performance/test_postgresql_test_manager_concurrent.py`
- Destination: `packages/kailash-dataflow/tests/unit/migrations/test_postgresql_test_manager_concurrent_unit.py` (rename — `performance/` directory implies performance-tier intent which the file is NOT; new path matches the `_unit.py` suffix convention).

Updated:

- `todos/active/01-S1-cluster-a-tier1-moves.md` § Scope table + Invariant 1 + verification commands.
- `todos/active/00-INDEX.md` § Verified scope correction (new section above Forest anchor) + § Open questions (#6 added).
- `todos/active/03-S3-verification-gate.md` § Scope step 1 (10 paths, not 9) + § Scope step 1b (Tier-1 sanity check with File 10's expected count).

Recorded for /implement: the verified scope is **10 files / 139 mock sites**, NOT 9 files / 74 sites.

## Verification

```bash
ls packages/kailash-dataflow/tests/integration/performance/test_postgresql_test_manager_concurrent.py
# → exists
grep -cE "@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)" packages/kailash-dataflow/tests/integration/performance/test_postgresql_test_manager_concurrent.py
# → 11
```

## Cross-rule relevance

- `rules/spec-accuracy.md` Rule 1: every citation grep-resolves. The issue body's "9 files" prose was a phantom citation against its own table of 10.
- `rules/testing.md` § MUST: Verified Numerical Claims. Counts must be produced by a verifying command; "9 files" was hand-typed.
- `rules/value-prioritization.md` MUST-1 (forest-vs-trees): a silent scope drop is the streetlight failure mode.

## Lesson for future audits

When the brief / issue body has BOTH a prose count AND a tabular enumeration, the table is authoritative — count rows mechanically, never trust the prose. The /analyze classification audit should have produced `pytest --collect-only -q` against EVERY file in the table, including ones the prose count omits.
