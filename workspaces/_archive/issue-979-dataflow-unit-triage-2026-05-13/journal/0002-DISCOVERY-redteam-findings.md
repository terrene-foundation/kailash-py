# 0002 DISCOVERY — Red-Team Findings + Plan Amendments

Date: 2026-05-13
Phase: /analyze (red-team gate per step 6)
Issue: #979

## Summary

Two parallel general-purpose red-team agents scrutinized the
architecture plan + spec + violations inventory. Combined findings:
plan needs **3 amendments** before /todos approval. Spec is
clean (zero phantom citations after independent verification).
Inventory has **4 corrected counts + 5 missing file entries**.

## Verified plan blockers (require amendment before /todos)

### A. CRIT-2 — Layer B blast radius is ~20 files, not 1

S2 in the plan covers only `tests/unit/examples/test_example_gallery.py`.
Independent grep for `AsyncLocalRuntime|WorkflowBuilder` across
`tests/unit/` returns 20+ matches including:

- `test_inspector_realtime_debugging.py`
- `test_inspector_parameter_tracing.py`
- `test_inspector_workflow_analysis.py`
- `test_inspector.py`
- `test_strict_mode_connection_validation.py`
- `test_strict_mode_workflow_validation.py`
- `test_node_id_namespace.py`
- `migrations/test_async_safe_run_integration.py`
- `core/test_async_sql_sqlite.py`
- `core/test_workflow_binding.py`
- `core/test_model_registry_runtime_injection.py`
- `nodes/test_count_node.py`
- `testing/test_tdd_performance_benchmark.py`
- `examples/test_example_gallery.py` (S2's only listed target)
- `templates/test_saas_subscriptions.py`
- `templates/test_saas_webhooks.py`
- `templates/test_saas_api_keys.py`
- `templates/test_saas_starter_jwt.py`
- `templates/test_saas_tenancy.py`
- `templates/test_saas_starter_auth.py`

Per `specs/testing-tiers.md` § Tier-1 Rule 1, these bare top-imports
are BLOCKED unless gated by `importorskip`. Plan amendment required:
S2 must either expand to cover the full surface OR a new shard owns it.

**Amendment**: Split S2 into:

- **S2a**: Move `tests/unit/examples/test_example_gallery.py` →
  `tests/integration/examples/` (real workflows; intent IS
  integration).
- **S2b**: Audit the 19 other files — per file, determine whether
  the test logic exercises the real runtime (MOVE to
  `tests/integration/`) or just imports for type hints / stub
  construction (gate with `pytest.importorskip("kailash.runtime")`
  at module top OR refactor to use a mock).
- **S2c**: `templates/test_saas_*.py` (6 files) — likely a single
  cohesive sub-shard since they share the SaaS scaffold pattern.
- **S2d**: `test_inspector_*.py` (4 files) — similar grouping.

Capacity: each sub-shard ≤300 LOC; sub-shards land sequentially
or as a parallel worktree wave per worktree-isolation Rule 4.

### B. HIGH-1 — V4 (PG DataFlow) missing `package/` + miscounted

Verified independent grep:

- `migrations/test_bug_006_safety_parameters.py` — 12 PG sites
- `core/test_actual_api_validation.py` — multiple sites
- `package/test_package_installation_unit.py` — 12 PG sites
  (MISSING from S4's enumerated targets)

Total: 3 distinct files with `DataFlow(...postgresql://...)`
patterns, NOT 9 as inventory claimed. Inventory red-team agent
also surfaced subdir-prefix corrections — the original V4 listed
paths like `tests/unit/test_bug_006_safety_parameters.py` (does
NOT exist) when actual path is
`tests/unit/migrations/test_bug_006_safety_parameters.py`.

**Amendment**: S4 expands to include `package/test_package_installation_unit.py`.
The V4 inventory itself is updated below.

### C. HIGH-2 — S5 invariant count exceeds budget

Plan self-flagged S5 as ≤300 LOC across 15 files with "5 invariants
per file" = 75 simultaneous invariants. Per autonomous-execution.md
§ Per-Session Capacity Budget MUST Rule 1, the cap is 5-10
invariants. The plan's "pre-authorized split into V5-only + V6-only"
is BLOCKED-rationalization shape ("decompose at /implement").

**Amendment**: S5 split at /todos:

- **S5a**: V5 only — `tempfile.NamedTemporaryFile` / `mktemp`
  removals across 7 files (uniform pattern; refactor to
  `memory_dataflow` / `file_dataflow` fixture).
- **S5b**: V6 only — ad-hoc `DataFlow(...sqlite:///...)` in 8 net
  new files (uniform pattern; refactor to fixture).

Each ≤5 invariants per sub-shard (same fixture surface; same
yield+close discipline; same marker behavior; one isolation
class; no cross-file state).

### D. HIGH-3 — S6 marker/timeout conflict with PR #968

PR #968's reverted workflow used `--maxfail=10 -q --timeout=60`
AND excluded markers in the workflow's `-m` flag. S1 adds the
same marker exclusion to `pytest.ini::addopts`. Double-filter
risk:

- If markers in BOTH the workflow `-m` and `pytest.ini::addopts`,
  the filters compose (intersection). Safe but redundant.
- If `pytest.ini::addopts` adds the exclusion AND the workflow
  passes `-m requires_postgres` (an integration job runs that
  way), addopts overrides per pytest precedence → integration
  tests would not run.

**Amendment**: S6 explicitly chooses ONE location for the marker
exclusion. Recommendation: pytest.ini (so local-run reproduces CI
behavior). Workflow `-m` becomes additive only, not duplicative.
Also: S1's `timeout = 120` (per-test) lives in pytest.ini;
S6's workflow timeout is `timeout-minutes` (job-level), not per-test.
These are different layers; document the distinction in S6.

## Downgraded / cleared findings

### CRIT-1 (claimed): pre-existing dataflow import error

`packages/kailash-dataflow/tests/unit/query/conftest.py:5-10`
documents: "pre-existing import error in dataflow.**init**.py
(cannot import 'Node' from 'kailash.nodes.base')". Independent
verification on current main:

```
$ python -c "from kailash.nodes.base import Node; print('OK')"
OK
$ python -c "from kailash.db.dialect import _validate_identifier; print('OK')"
OK
$ python -c "import dataflow"   # exits 0, no error
```

**Status**: the underlying import is fixed. The `query/conftest.py`
workaround is STALE — itself a contract violation per
`rules/zero-tolerance.md` Rule 4 (workaround for SDK issue that no
longer exists).

**Amendment**: NOT a new shard; fold cleanup of the stale conftest
into S5b (ad-hoc fixture work) or document for a separate cleanup.
Recommendation: include in S5b as "while-here" cleanup since it's
the same class (fixture/conftest hygiene).

### LOW-2 (claimed): mock_dataflow_engine phantom in spec

Independent grep:

```
packages/kailash-dataflow/tests/unit/conftest.py:148:def mock_dataflow_engine():
```

**Status**: NOT a phantom. Citation in `specs/testing-tiers.md` is
correct. The agent's truncated read missed line 148.

### MED-1 — Sequencing pre-flight

Plan dependency graph already enforces S1 → S2-S5. Adding the
"merge-base check before launching parallel wave" per
worktree-isolation Rule 5 is a process refinement; the plan
implicitly does this but should call it out.

**Amendment**: S1 marked "land + merge to main" as gate; S2-S5
shards include "verify S1 commit in main's history before starting"
as launch precondition.

## Verified violations-inventory corrections

Re-derived from independent agent sweep:

| Class | Plan claim | Actual                                                                                               | Correction                                                                 |
| ----- | ---------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V1    | 2 files    | 2                                                                                                    | CONFIRMED                                                                  |
| V2    | 1 file     | 1                                                                                                    | CONFIRMED                                                                  |
| V3    | 17 of 21   | 16 of 21                                                                                             | Inventory's footnote was correct; rolled-up "17" off by 1                  |
| V4    | 9 files    | 3 distinct files w/ PG DataFlow + 14 other PG-URL files                                              | Inventory had 5 phantom paths (missing subdir prefix); under-counted by ~8 |
| V5    | 7 files    | 7 (one of them — `test_performance_regression_suite.py` — is JSON not DB; should be removed from V5) | Headline OK; one entry misclassified                                       |
| V6    | 15 files   | 14 production                                                                                        | Inventory counted `tests/unit/CLAUDE.md` DO-NOT example as production      |

**Missing-from-inventory files** (verified production violators):

- `core/test_lazy_connection.py`
- `core/test_logging_config.py`
- `core/test_logging_levels.py`
- `adapters/test_postgresql_adapter.py` (16 PG-URL sites)
- `performance/test_simple_coverage_boost.py` (9 sites)
- `test_dataflow_bug_011_012_unit.py`
- `test_protection_system_critical_gaps.py`
- `test_write_protection_comprehensive.py`
- `package/test_package_installation_unit.py` (12 PG sites — surfaced by plan-scrutiny agent, also a Layer D match)

## Spec drift findings (non-blocking)

`specs/testing-tiers.md` vs `tests/unit/CLAUDE.md`:

- **DRIFT-1**: Spec bans `AsyncLocalRuntime` / `WorkflowBuilder`
  top-imports; CLAUDE.md is silent. Spec is stricter (newer
  authority); supersedes per specs-authority.md Rule 5. Update
  CLAUDE.md in S6 to mirror.
- **DRIFT-2**: CLAUDE.md lists `unit_test_suite` fixture; spec
  omitted it from canonical table. Add to spec.
- **DRIFT-3**: Auto-applied markers (`sqlite_memory`, `sqlite_file`,
  `mocking`) named in CLAUDE.md but not declared in pytest.ini.
  Decision: declare them in pytest.ini OR remove from CLAUDE.md
  — pick at S6.

## Net plan disposition

**Plan needs the 4 amendments above (A/B/C/D) before /todos.**
Shard count rises from 6 to ~10:

- S1 (preconditions) — unchanged
- S2a/S2b/S2c/S2d (Layer B fan-out) — new from S2
- S3 (fabric move) — unchanged
- S4 (PG audit + move, expanded scope) — amended
- S5a/S5b (fixture refactor split) — split from S5
- S6 (gate re-apply + CLAUDE.md / pytest.ini alignment) — amended

Capacity: each shard still ≤500 LOC load-bearing, ≤5-10
invariants. Plan now decomposes by violation class AND scope, not
by violation class alone.

## Action before /todos

1. Update `02-plans/00-architecture-plan.md` with amendments (next
   step in this session).
2. Surface to user at the /todos human gate with: plan-as-amended
   - journal/0001 + journal/0002 + spec + research notes — five
     reading targets, sized so the user can approve in 5-10 minutes.
