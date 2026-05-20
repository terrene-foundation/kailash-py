# Recovery Plan Mapping — #977 / #979 → Implementation Shards

PR #977's body lists a five-step recovery plan. #979's acceptance
criteria are a near-rewrite of that plan. This file maps both to
concrete implementation shards, with gap notes where the
recovery plan needs to be extended.

## Mapping table

| PR #977 recovery step                                                 | #979 AC#       | Plan shard | Gap notes                                                                                                             |
| --------------------------------------------------------------------- | -------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| (1) Audit for Docker/Postgres/MySQL/Redis-requiring tests + mark/move | #1, #3, #4, #5 | S2, S3, S4 | #977 said "mark with `requires_*`" — we recommend MOVE for true integration-shaped tests, marker for ambiguous cases. |
| (2) Add `pytest-timeout`, `pytest-forked` to `[dev]`                  | (implicit)     | S1         | S1 covers BOTH plugins + the `timeout = 120` config + a `[dev]` install verification.                                 |
| (3) Fix or skip `test_dataflow_events.py` failures                    | #2             | S5         | Re-scoped from "fix" to "verify clean; document". Layer E shows failures aren't reproducing.                          |
| (4) Refactor `test_example_gallery.py` to use `memory_dataflow`       | #1             | S2         | Actually MOVE to integration since it exercises real AsyncLocalRuntime (the docstring's intent).                      |
| (5) Re-add unit gate to unified-ci.yml                                | #7             | S6         | Final shard; depends on all prior shards passing.                                                                     |

## Gaps PR #977 / #979 don't cover (added to plan)

1. **CLAUDE.md update.** The institutional spec at
   `tests/unit/CLAUDE.md` is the canonical authority. After the
   cleanup, it should be updated to reflect what was actually
   enforced and mention the importorskip pattern for borderline
   files. Add to S6.

2. **conftest.py imports.** Some files use `IntegrationTestSuite`
   from `tests/infrastructure/test_harness` — a Python module
   reachable from BOTH unit and integration tiers. The fact that
   it's reachable from unit/ is itself drift. Add a doc note in
   S6 about the import surface.

3. **Marker-based exclusion fallback.** If files cannot be moved
   in this session (e.g., they're transitively-imported by other
   unit fixtures), add `requires_postgres` markers and update
   `addopts` to `-m "not (requires_postgres or requires_mysql or
requires_redis or requires_docker)"` for the unit tier. This
   is the fallback per #977 step 1.

## Strategy decision: MOVE vs IMPORTORSKIP

For Layer C (fabric) and Layer D (PG):

- MOVE wins when the test's intent IS to exercise the dep
  (real-world integration shape).
- IMPORTORSKIP wins when the test happens to import the dep
  but tests something else (parsing, logic, error shape).

Per `journal/0001` brief correction #4, the plan adopts:

- **fabric/**: MOVE entire directory (intent is integration).
- **IntegrationTestSuite users**: MOVE (intent is PG).
- **Bare DB-driver imports**: IMPORTORSKIP if the test logic is
  pure-Python; MOVE if it actually exercises the driver.
- **Real PG URLs**: per-file audit — MOVE if PG-required, refactor
  URL to SQLite sentinel if mocked.

This decision is the load-bearing claim of the shard plan; the
plan in `02-plans/00-architecture-plan.md` cites this section as
the rationale.

## Verification ladder

Each shard MUST verify in this order:

1. Local fast: `pytest packages/kailash-dataflow/tests/unit/<sub> -x`
2. Clean venv full: `/tmp/dataflow-tier1/bin/pytest packages/kailash-dataflow/tests/unit -x` (no `[fabric]`, no PG)
3. (S6 only) CI: `unified-ci.yml test-dataflow` job passes
   on the PR

S1 verifies via clean venv (step 2).
S2-S5 verify via local fast (step 1) + spot-check clean venv.
S6 verifies via all three.
