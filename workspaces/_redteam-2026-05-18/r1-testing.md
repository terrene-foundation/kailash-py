# Redteam Round 1 — Testing Axis

**Scope:** PR #1059 + #1060 (#1083), PR #1020 + #1021 (#1084), 7-shard OPTION-C′ (#1085).
**Mode:** Audit per `rules/testing.md` § Audit Mode. Coverage re-derived from scratch; `.test-results` ignored.

---

## Sweep 1 — Collection-time verification

```
PYTHONPATH=src:packages/kailash-dataflow/src python -m pytest \
    packages/kailash-dataflow/tests/integration/ --collect-only -q
→ 1919/2059 tests collected (140 deselected) in 2.25s   EXIT=0

PYTHONPATH=src:packages/kailash-dataflow/src python -m pytest \
    packages/kailash-dataflow/tests/unit/ --collect-only -q
→ 3445 tests collected in 1.09s                          EXIT=0
```

Both tiers collect clean. Per `orphan-detection.md` MUST-5 collect-gate: PASS.

---

## Sweep 2 — 3-tier mock compliance scan on integration tier

Filtered command (excluding the gate's own conftest.py + its meta-test fixtures):

```
grep -rEn 'from unittest\.mock import|^from mock import' \
    packages/kailash-dataflow/tests/integration/ --include='*.py' \
  | grep -v conftest.py | grep -v test_conftest_no_mocking_hook.py
→ packages/kailash-dataflow/tests/integration/fabric/test_fabric_integrity.py:22: from unittest.mock import ANY
```

Three additional file matches (`saas_starter/test_api_keys.py:24`, `saas_starter/test_jwt.py:10`,
`test_dataflow_ml_feature_source_wiring.py:20`) were **docstring mentions only** — no
actual `from unittest.mock import …` statements (verified via line-specific grep).

Baseline matches the #1084 closure decision: only `fabric/test_fabric_integrity.py:22 ANY`
allowed. No NEW primitive imports. **PASS.**

---

## Sweep 3 — Test-per-new-module coverage

All four spec-targeted new files exist and collect:

```
pytest packages/kailash-dataflow/tests/unit/security/test_sanitizer_public_api.py
       packages/kailash-dataflow/tests/unit/security/test_fabric_smoke_invariants.py
       packages/kailash-dataflow/tests/integration/test_issue_1050_workflow_runtime_protection.py
       packages/kailash-dataflow/tests/integration/test_issue_1050_protection_mutation_matrix.py
       --collect-only -q
→ 37 tests collected   EXIT=0
```

All 10 moved Tier-1 destinations (PR #1020 + #1021) collect:

```
pytest <10 files from `gh pr view 1020 --json files` + `gh pr view 1021 --json files`>
       --collect-only -q
→ 128 tests collected   EXIT=0
```

Includes:

- `tests/unit/cache/test_cache_invalidation.py`
- `tests/unit/core/test_dataflow_engine_lock_integration.py`
- `tests/unit/core/test_tdd_mode_propagates_to_node_generator.py`
- `tests/unit/migrations/test_async_safe_run.py`
- `tests/unit/migrations/test_auto_migration_system_lock_integration.py`
- `tests/unit/migrations/test_impact_reporter_unit.py`
- `tests/unit/migrations/test_migration_test_framework.py`
- `tests/unit/migrations/test_postgresql_test_manager_concurrent_unit.py`
- `tests/unit/package/test_package_installation_unit.py`
- `tests/unit/migrations/test_connection_adapter_param_conversion.py`
- (+ `tests/integration/migrations/test_migration_lock_manager_integration.py` from #1020)
- (+ `tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py` from #1021)

**PASS.**

---

## Sweep 4 — Regression-test coverage for closed bug classes

```
ls packages/kailash-dataflow/tests/regression/
→ test_issue_1045_protected_runtime_close.py
  test_issue_1045_protection_runtime_cm_deprecation.py
  test_issue_1058_bulk_update_propagates_not_swallowed.py
  test_issue_1058_shard2_protection_before_validation.py
  test_issue_1058_shards_3_4_upsert_enum_and_seed_swallow.py
  test_issue_1070_transaction_abort_state_reset.py
  ... (+ 14 unrelated test_issue_*.py)
```

| Closed class                                                                   | Regression coverage                                                                                                                                                 |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1050 `check_operation` orphan / sync override / `ProtectionViolation` re-wrap | `tests/integration/test_issue_1050_workflow_runtime_protection.py` (behavioral; imports `ProtectionViolation` at :79; exercises plain `LocalRuntime` per docstring) |
| #1058 S2 protection-before-validation                                          | `tests/regression/test_issue_1058_shard2_protection_before_validation.py`                                                                                           |
| #1058 S3/S4 UPSERT-enum + import_file swallow                                  | `tests/regression/test_issue_1058_shards_3_4_upsert_enum_and_seed_swallow.py`                                                                                       |
| #1058 bulk_update swallow                                                      | `tests/regression/test_issue_1058_bulk_update_propagates_not_swallowed.py`                                                                                          |

**PASS** — all closed bug classes have regression files. Tests are behavioral (call the
function and assert) per `rules/testing.md` § Behavioral Regression Tests.

_Note:_ #1050 regression file lives under `tests/integration/` rather than `tests/regression/`.
Per `rules/testing.md` "in `tests/regression/test_issue_*.py` … OR a clearly-anchored
one elsewhere" this satisfies the rule — the filename `test_issue_1050_*` is anchored
and behavioral. **LOW** observation only, not a blocking finding.

---

## Sweep 5 — Mutation-class matrix completeness

```
grep -nE '_BLOCKED_MUTATIONS|"create"|"update"|"delete"|"upsert"|"bulk_' \
    packages/kailash-dataflow/tests/integration/test_issue_1050_protection_mutation_matrix.py
→ 132: _BLOCKED_MUTATIONS = [
   133:    "create", 134: "update", 135: "delete", 136: "upsert",
   137:    "bulk_create", 138: "bulk_update", 139: "bulk_delete", 140: "bulk_upsert",
```

All 8 declared surfaces present. Cross-check against actual express surfaces:

```
grep -nE '^\s*(async\s+)?def\s+(create|update|delete|upsert|bulk_)' \
    packages/kailash-dataflow/src/dataflow/features/express.py
→ Async class: create/read/update/delete/list/count/upsert/bulk_create/bulk_update/
              bulk_delete/bulk_upsert (8 mutations + 3 reads)
→ Sync class:  identical 8 mutations + 3 reads
```

Mutation surfaces in source = `{create, update, delete, upsert, bulk_create, bulk_update,
bulk_delete, bulk_upsert}` = exactly the 8 in `_BLOCKED_MUTATIONS`. No missing surface.

Read surfaces (`read`, `list`, `count`) are correctly tested as "not blocked under
read-only" in the same matrix (verified via collection output). **PASS.**

---

## Sweep 6 — Tier-1 invariant compliance (3 random moved files)

AST import scan for `asyncpg|psycopg|aiopg|redis|motor|aioredis|aiohttp|requests|socket|urllib3`:

```
test_cache_invalidation.py                        → network/db imports: []
test_dataflow_engine_lock_integration.py          → network/db imports: []
test_connection_adapter_param_conversion.py       → network/db imports: []
```

No top-level forbidden imports. Tier-1 contract upheld for the sample.

_Caveat:_ `test_issue_1050_protection_mutation_matrix.py` (integration tier, correctly
placed) uses `socket.create_connection` at line 77 — this is the Postgres-gate check,
NOT a Tier-1 violation (file lives in `tests/integration/`).

**PASS.**

---

## Sweep 7 — CI gate sanity (#1085 S6, `.github/workflows/unified-ci.yml`)

```
Line 200-201: "Paths cover BOTH the package and the core SDK
              (per ci-runners.md Rule 6 — filter MUST follow transitive dep graph)"
Line 10-26:   paths: ["src/**", "packages/**", "tests/**", "pyproject.toml",
                      "uv.lock", ".github/workflows/unified-ci.yml"]
Line 231-232: uv pip install -e "." --python .venv/bin/python   ← ROOT FIRST
              uv pip install -e "packages/kailash-dataflow[dev]" --python .venv/bin/python
Line 236-237: "ZERO `-m` flag here: pytest.ini::addopts is the SOLE marker filter"
Line 257-258: ../../.venv/bin/python -m pytest tests/unit/ --maxfail=10 -q --timeout=120
              (no -m flag confirmed)
```

`packages/kailash-dataflow/pytest.ini:44-48` confirms `addopts` carries the sole `-m`:

```
addopts =
    -v --strict-markers --tb=short
    -m "not (requires_postgres or requires_mysql or requires_redis or requires_docker)"
```

All 4 sub-checks satisfied:

- `src/kailash/**` covered via `src/**` (line 11, 21) — per `deployment.md` MUST: editable root install order.
- Root install precedes sub-package install (lines 231→232).
- Zero `-m` flag on the pytest command (line 257-258 reproduced; the comment block 236-237 explicitly documents the CRIT-B fix).
- `pytest.ini::addopts` (line 44-48) is the sole `-m` location.

**PASS.**

---

## Verdict

```
SEV | finding                                                  | file:line                                                  | evidence                                          | fix
LOW | #1050 regression test placed under tests/integration/    | tests/integration/test_issue_1050_workflow_runtime_protection.py | sweep 4 — file naming `test_issue_1050_*` is anchored + behavioral; testing.md allows "anchored elsewhere" | observation only — consider mirroring to tests/regression/ at next codify pass
```

No CRIT, no HIGH, no MEDIUM.

```
Round 1 testing verdict: 0 CRIT / 0 HIGH / 0 MED / 1 LOW
Convergence: YES (zero CRIT/HIGH)
```
