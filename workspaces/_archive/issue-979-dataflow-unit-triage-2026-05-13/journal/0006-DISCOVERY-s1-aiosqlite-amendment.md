# 0006 — DISCOVERY: S1 amended at launch with `aiosqlite` Tier-1 dev-dep

**Date:** 2026-05-14
**Phase:** `/implement` (Workstream-A S1)
**Author:** Claude Opus 4.7 (1M context)

## What happened

While running S1's clean-venv verification command
(`/tmp/s1-verify/bin/pytest packages/kailash-dataflow/tests/unit
--collect-only -q`), conftest loading failed with
`ModuleNotFoundError: No module named 'aiosqlite'`. Bare module-scope
`import aiosqlite` lives at
`packages/kailash-dataflow/tests/fixtures/unit_test_harness.py:26`
(consumed by `tests/unit/conftest.py:18`) and backs every Tier-1
canonical fixture (`memory_dataflow`, `file_dataflow`, etc.).

S1's approved scope (OPTION-C′, journal/0005) covered `pytest-timeout`
only. Discovery surfaced a SAME-CLASS gap — another Tier-1-required
dev dep was missing from `[project.optional-dependencies].dev`.

## Why the launch-time amendment is in scope (not a follow-up issue)

Per `rules/autonomous-execution.md` MUST Rule 4 ("Fix-Immediately When
Review Surfaces A Same-Class Gap Within Shard Budget"):

- **Same bug class.** "Tier-1 dev-dep pin missing → clean-venv install
  cannot collect" applies identically to `pytest-timeout` (S1 scope) and
  `aiosqlite` (this finding).
- **Fits remaining shard budget.** S1 cap is ≤80 LOC + 5 invariants. The
  fix is 1 line in `pyproject.toml`, 1 assertion in the regression test,
  and ~10 lines of spec amendment. Total ~12 LOC; remaining ≤5
  invariants stay at 5 (the existing invariant 1 absorbed aiosqlite as
  a co-required pin).
- **Filing a follow-up issue is BLOCKED** for the rationalizations
  enumerated in MUST-4: "separate PR is cleaner for review" /
  "follow-up issue captures it" — both produce a 2× context-reload
  cost the next session must pay.

## What landed

1. `packages/kailash-dataflow/pyproject.toml::[project.optional-dependencies].dev`
   now includes `aiosqlite>=0.19.0` with an explanatory comment citing
   the Tier-1 fixture surface.
2. `specs/testing-tiers.md` § Tier-1 Contract Rule 6 was amended to
   state "each package MUST pin every Tier-1 infra driver its canonical
   fixtures import at module scope," and to mark `pytest-forked` as
   OPTIONAL (R1 redteam round had already falsified the "archived"
   claim AND verified zero consumer in DataFlow — see journal/0002).
3. Regression test
   `test_issue_979_s1_preconditions::test_dev_extras_carry_tier1_required_pins`
   asserts BOTH `pytest-timeout>=2.3.x` AND `aiosqlite>=0.x.x` are in
   `[dev]`. The single test covers both pins because they share the
   same failure class (Tier-1 dev-dep missing → conftest fails).

## What did NOT change

- S1's other 4 invariants are unmodified.
- No test file was touched (per S1 § "Out of scope": no per-file
  marker application — that lands organically in S2-S5).
- The remaining 14 collection errors against `tests/unit/` (psutil,
  polars, fastapi, cryptography) are explicit S2a / S3 / S4 / S5a
  scope per the workstream plan and remain untouched.

## Spec sibling re-derivation (per `rules/specs-authority.md` MUST-5b)

`specs/testing-tiers.md` is the only file in the testing-tier domain
under `specs/`. No sibling files exist to re-derive. The edit's
downstream impact:

- `briefs/00-brief.md` § "Brief traceability" — Layer A → § Tier-1
  Contract Rule 6 still maps; the rule's wording broadened but its
  identity is preserved.
- `02-plans/02-amendments-v2-post-redteam-r1r2.md` — S1's scope grew
  by one pin; no plan field references "exact dev-dep list" so no
  edit required.

## Brief-corrections impact

None — the brief's failure-layer 1 ("pytest-timeout missing") accurately
described the surface that triggered debugging; aiosqlite is the
SAME-LAYER family failure that S1's verification command surfaced
during execution, not a brief inaccuracy.
