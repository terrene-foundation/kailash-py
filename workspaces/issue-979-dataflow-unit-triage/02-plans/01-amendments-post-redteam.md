# Plan Amendments — Post Red-Team

Date: 2026-05-13
Supersedes the shard list in `00-architecture-plan.md` § Decomposition.
Source: `journal/0002-DISCOVERY-redteam-findings.md`.

The original 6-shard plan is preserved as the first draft. The
amended shard list below is what /todos should approve.

## Amended shard list (10 shards, dependency graph below)

### S1 — Plugin & timeout preconditions _(unchanged)_

Files: `packages/kailash-dataflow/pyproject.toml`, `pytest.ini`.

- Add `pytest-timeout>=2.3.0` + `pytest-forked>=1.6.0` to `[dev]`.
- Add `timeout = 120` + `timeout_method = thread` to `pytest.ini`.
- Add `addopts` marker exclusion: `-m "not (requires_postgres or
requires_mysql or requires_redis or requires_docker)"`.

Verification: clean venv install + deliberate-hang test +
`pytest --collect-only`.

Value-anchor: per #979 — without this floor, every subsequent
shard's failure surfaces as job-wide timeout, not per-test.

Capacity: ≤50 LOC, 3 invariants, 1 call-graph hop.

### S2a — Move `test_example_gallery.py` to integration _(was S2)_

Files: `git mv packages/kailash-dataflow/tests/unit/examples
→ packages/kailash-dataflow/tests/integration/examples`.

Invariants: tests collect post-move; integration env has the deps
they need; no orphan import path in unit tier; module-scope
`tempfile.mktemp()` deadlock no longer affects unit tier.

Capacity: ≤30 LOC, 3 invariants.

### S2b — Inspector files (4) _(NEW — red-team CRIT-2 surface)_

Files:

- `tests/unit/test_inspector_realtime_debugging.py`
- `tests/unit/test_inspector_parameter_tracing.py`
- `tests/unit/test_inspector_workflow_analysis.py`
- `tests/unit/test_inspector.py`

Per file, decide: MOVE to `tests/integration/inspector/` if test
exercises real workflow execution; OR refactor to use mocks /
`pytest.importorskip("kailash.runtime")` if logic is
pure-Python. Recommendation: move (inspector tests likely exercise
real execution).

Value-anchor: per `specs/testing-tiers.md` § Tier-1 Rule 1 —
`AsyncLocalRuntime` and `WorkflowBuilder` bare top-imports are
BLOCKED in tier-1.

Capacity: ≤200 LOC, 4 invariants (uniform pattern).

### S2c — SaaS template files (6) _(NEW)_

Files:

- `tests/unit/templates/test_saas_starter_jwt.py`
- `tests/unit/templates/test_saas_starter_auth.py`
- `tests/unit/templates/test_saas_subscriptions.py`
- `tests/unit/templates/test_saas_webhooks.py`
- `tests/unit/templates/test_saas_api_keys.py`
- `tests/unit/templates/test_saas_tenancy.py`

Per file, MOVE to `tests/integration/templates/` (templates are
end-to-end scaffolds; intent is integration).

Capacity: ≤200 LOC, 4 invariants.

### S2d — Other workflow-importing files (10) _(NEW)_

Files:

- `tests/unit/test_strict_mode_connection_validation.py`
- `tests/unit/test_strict_mode_workflow_validation.py`
- `tests/unit/test_node_id_namespace.py`
- `tests/unit/migrations/test_async_safe_run_integration.py`
- `tests/unit/core/test_async_sql_sqlite.py`
- `tests/unit/core/test_workflow_binding.py`
- `tests/unit/core/test_model_registry_runtime_injection.py`
- `tests/unit/nodes/test_count_node.py`
- `tests/unit/testing/test_tdd_performance_benchmark.py`
- (audit for any leftovers via final grep)

Per file: MOVE to integration if exercising real workflow, OR
refactor with `importorskip` + mock. Heterogeneous — each file's
disposition determined at implement-time.

Capacity: ≤300 LOC, 5 invariants. If exceeds budget, split by
sub-directory (`core/`, `migrations/`, etc.).

### S3 — fabric/ directory move _(unchanged)_

`git mv tests/unit/fabric → tests/integration/fabric`. Update
`tests/CLAUDE.md`. 21 files, 16 with top-imports.

Capacity: ≤50 LOC, 3 invariants.

### S4 — Layer D: PG-requiring tests _(amended scope)_

Now covers (verified via independent grep):

**MOVE to `tests/integration/...`:**

- `tests/unit/cache/test_cache_invalidation.py` (uses IntegrationTestSuite)
- `tests/unit/migration/test_impact_reporter_unit.py` (uses IntegrationTestSuite + PG:5434)
- `tests/unit/migrations/test_bug_006_safety_parameters.py` (12 PG sites)
- `tests/unit/core/test_actual_api_validation.py` (multiple PG sites)
- `tests/unit/package/test_package_installation_unit.py` (12 PG sites — **previously missing**)
- `tests/unit/migrations/test_migration_test_framework.py` (PG:5434 sites)
- `tests/unit/test_dataflow_bug_011_012_fixes.py` (PG:5434 sites)
- `tests/unit/test_tdd_node_generation_integration.py` (PG:5434 sites)
- `tests/unit/test_real_tdd_integration.py`
- `tests/unit/test_dataflow_bug_011_012_unit.py` (**new from inventory red-team**)
- `tests/unit/adapters/test_postgresql_adapter.py` (**new — 16 PG-URL sites**)
- `tests/unit/performance/test_simple_coverage_boost.py` (**new — 9 sites**)

**GATE with `importorskip("asyncpg")`:**

- `tests/unit/testing/test_tdd_support.py` (line 16 bare `import asyncpg`)

**PER-FILE AUDIT (parse-only URL vs real connection):**

- `tests/unit/nodes/test_count_node.py:21` (also matches CRIT-2)
- `tests/unit/features/test_bulk_upsert_delegation.py:28`
- `tests/unit/core/test_architecture_validation.py:197`
- `tests/unit/core/test_lazy_connection.py` (**new from inventory red-team**)
- `tests/unit/core/test_logging_config.py` (**new**)
- `tests/unit/core/test_logging_levels.py` (**new**)
- `tests/unit/test_protection_system_critical_gaps.py` (**new**)
- `tests/unit/test_write_protection_comprehensive.py` (**new**)

Capacity: bulk-move shard ≤300 LOC + audit shard ≤200 LOC =
two sub-shards (S4a moves, S4b audits). Or single shard if
each file's disposition is mechanical.

### S5a — V5 tempfile removal _(was S5, split)_

Files (verified):

- `tests/unit/migrations/test_sync_ddl_executor.py` (9 sites)
- `tests/unit/core/test_async_sql_sqlite.py`
- `tests/unit/testing/test_tdd_performance_benchmark.py`
- `tests/unit/context_aware/test_performance_benchmarks.py`
- `tests/unit/context_aware/test_instance_isolation.py`
- (`tests/unit/testing/test_performance_regression_suite.py` —
  uses `.json` tempfile, NOT `.db` — EXCLUDE from V5 scope)

Refactor pattern: `tempfile.NamedTemporaryFile(suffix=".db", ...)`

- `DataFlow(f"sqlite:///{tmp.name}")` → `memory_dataflow` or
  `file_dataflow` fixture from `tests/unit/conftest.py`.

Capacity: ≤250 LOC, 5 invariants (uniform refactor).

### S5b — V6 ad-hoc sqlite refactor + stale-conftest cleanup _(NEW from S5 split)_

Files (V6 net-new — verified via earlier grep):

- `tests/unit/test_derived_model.py`
- `tests/unit/test_inspector_workflow_analysis.py` (overlaps S2b)
- `tests/unit/core/test_fabric_only_mode.py`
- `tests/unit/core/test_dataflow_2026_001_fixes.py`
- `tests/unit/core/test_architecture_validation.py` (overlaps S4)
- `tests/unit/core/test_pool_defaults.py`
- `tests/unit/core/test_lazy_connection.py` (overlaps S4)
- `tests/unit/features/test_read_replica.py`

Plus: clean up the stale workaround at
`tests/unit/query/conftest.py:5-10` — the documented "pre-existing
import error in dataflow.**init**.py (cannot import 'Node' from
'kailash.nodes.base')" no longer reproduces on main; the conftest
is itself a `rules/zero-tolerance.md` Rule 4 violation
(workaround for SDK issue that no longer exists).

Capacity: ≤300 LOC, 5 invariants.

### S6 — Re-apply gate + CLAUDE.md / pytest.ini alignment _(amended)_

Files:

- `.github/workflows/unified-ci.yml` — re-add the
  `test-dataflow` job (rebuilt from scratch using PR #968 as
  reference, NOT cherry-pick). Choose ONE location for marker
  exclusion: pytest.ini (set by S1) is canonical; workflow `-m`
  becomes additive only.
- `packages/kailash-dataflow/tests/unit/CLAUDE.md` — mirror the
  `specs/testing-tiers.md` stricter contract (drift-1 fix:
  add `AsyncLocalRuntime` and `WorkflowBuilder` to the
  no-top-import list).
- `packages/kailash-dataflow/tests/CLAUDE.md` — document
  `[fabric]` requirement for the integration tier's
  `fabric/` subdir.
- `packages/kailash-dataflow/pytest.ini` — declare
  `sqlite_memory`, `sqlite_file`, `mocking` markers if keeping
  them as the auto-applied markers per CLAUDE.md (drift-3 fix).
- `specs/testing-tiers.md` — add `unit_test_suite` to canonical
  fixture table (drift-2 fix).

Invariants:

- Gate fires on this PR, passes.
- Gate ALSO fires on a deliberate `feat/canary` PR with a planted
  tier-1 violation (e.g., a new `tempfile.mktemp` or bare
  `import asyncpg`) AND CORRECTLY fails.
- Job-level `timeout-minutes` ≠ per-test `timeout` (S1 set per-test
  in pytest.ini; S6 sets job-level in workflow).

Capacity: ≤300 LOC, 5 invariants.

## Amended dependency graph

```
S1 (preconditions) ──┐
                     │
                     ├──→ S2a/S2b/S2c/S2d (Layer B fan-out) ──┐
                     ├──→ S3 (fabric move)                   ──┤
                     ├──→ S4 (Layer D PG audit + move)       ──┼──→ S6 (gate + spec/CLAUDE.md alignment)
                     ├──→ S5a (V5 tempfile)                  ──┤
                     └──→ S5b (V6 ad-hoc + conftest cleanup) ──┘
```

Parallel-wave strategy: launch S2a-S5b as 2-3 parallel worktree
agents at a time per `rules/worktree-isolation.md` Rule 4. Each
shard's worktree gets its own `tests/unit/` working copy; conflicts
on `pyproject.toml` and `pytest.ini` are avoided since only S1 and
S6 touch those.

## Brief-to-spec-to-shard traceability (final)

| Brief layer           | Spec clause                 | Shards covering         |
| --------------------- | --------------------------- | ----------------------- |
| Layer A               | Tier-1 Rule 6               | S1                      |
| Layer B               | Tier-1 Rule 1, 2            | S2a, S2b, S2c, S2d, S5b |
| Layer C               | Tier-1 Rule 1               | S3                      |
| Layer D               | Tier-1 Rule 1, 3            | S4                      |
| Layer E               | Tier-1 Rule 5, 6            | S1, S5a, S5b            |
| AC#6 (≤2 min runtime) | Tier-1 § Performance budget | S6 (verifies)           |
| AC#7 (re-apply gate)  | § CI Gate Strategy          | S6                      |

## Out of scope (unchanged)

- Refactoring `tests/integration/` (separate issue)
- Adding new tests
- Changing production code outside `packages/kailash-dataflow/`
  unless a failing test reveals a real bug
- Sibling packages

## What still needs human gate at /todos

Three decisions for the user:

1. **S4 + S2 overlap**: a few files (`nodes/test_count_node.py`,
   `core/test_architecture_validation.py`, `core/test_lazy_connection.py`)
   match BOTH Layer B (AsyncLocalRuntime import) and Layer D
   (PG URL). Cleanest: handle in S4 (PG-audit) per the file's
   primary classification; document in shard prompt.

2. **S2b inspector files disposition**: MOVE all to integration vs
   gate with importorskip — depends on whether `tests/unit/test_inspector*.py`
   tests truly exercise real workflow execution or just construct
   `WorkflowBuilder` for static inspection. Recommend MOVE
   (consistent with S2a + S2c).

3. **S6 spec-update scope**: include CLAUDE.md drift fixes 1-3
   in S6 (recommended for cohesion) OR split into a final spec-only
   shard? Recommend INCLUDE — S6 is already the
   spec-touching shard.
