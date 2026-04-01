# Red Team Round 1 — kailash-ml

**Date**: 2026-04-01
**Test count**: 508 passed, 1 skipped
**Agents deployed**: deep-analyst (spec-coverage), security-reviewer, testing-specialist, intermediate-reviewer

## Findings Summary

| Severity | Found | Fixed R1 | Open |
| -------- | ----- | -------- | ---- |
| CRITICAL | 5     | 5        | 0    |
| HIGH     | 6     | 1        | 5    |
| MEDIUM   | 16    | 0        | 16   |
| LOW      | 8     | 0        | 8    |

## CRITICAL Findings (all fixed)

### C1: SQL Type Injection in `_feature_sql.py:71` [FIXED]

`sql_type` values interpolated into DDL without validation. Added `_ALLOWED_SQL_TYPES` allowlist and `_validate_sql_type()` called before interpolation.

### C2: Stub Tool Functions `trigger_retraining` and `rollback_model` [FIXED]

Tools accepted pipeline/registry objects but never called them. Rewrote to call `pipeline.retrain()` and `registry.promote_model()` when available, with fallback to "pending" status when objects not provided.

### C3: Silent `except Exception: pass` in Production Code [FIXED]

Three locations in `drift_monitor.py` (metric computation) silently swallowed errors. Added `logger.debug()` with `exc_info=True` to all three.

### C4: ExperimentTracker Missing from `__init__.py` [FIXED]

Fully implemented engine (88 tests) was unreachable via `from kailash_ml import ExperimentTracker`. Added to lazy loader and `__all__`.

### C5: `ModelRegistry.compare()` — P0 Spec Method Missing [FIXED]

Architecture spec Section 3.3 requires `compare(name, version_a, version_b)`. Implemented as metric comparison with deltas and better_version indicator.

## HIGH Findings

### H1: NaN/Inf on DriftMonitor Thresholds [FIXED]

`psi_threshold`, `ks_threshold`, `performance_threshold` had no `math.isfinite()` validation. NaN would silently disable all drift detection. Added validation in `__init__`.

### H2: Unbounded Collections [OPEN]

- `CostTracker._calls` (guardrails): grows per LLM call
- `LLMCostTracker._calls` (automl): same pattern
- `AgentGuardrailMixin._audit_buffer`: grows until flush
- `DriftMonitor._references`: holds full pl.Series per model
- `PolicyRegistry._versions`: unbounded version lists

### H3: DriftMonitor TOCTOU Race [OPEN]

`set_reference()` and `_store_baseline()` use check-then-act without transactions. Should use `dialect.upsert()` or wrap in `async with conn.transaction()`.

### H4: Code Duplication [OPEN]

- `_NUMERIC_DTYPES` defined in 3 files
- `_ALLOWED_MODEL_PREFIXES` + `_validate_model_class` in 2 files
- `_compute_metrics` in 2 files
- SB3 `_ALGO_MAP` / `_SB3_ALGORITHMS` in 2 files

### H5: `DataExplorer.compare()` Spec Method Missing [OPEN]

Architecture spec Section 3.7 defines `compare(data_a, data_b)`. Not implemented.

### H6: `interop.from_arrow()` and `dict_records_to_polars()` Missing [OPEN]

Implementation plan TSG-312 lists these converters. Not implemented.

## Spec Coverage (from deep-analyst)

**71 IMPLEMENTED, 6 PARTIAL, 10 MISSING, 1 UNWIRED**

Full report at `workspaces/kailash-ml/.spec-coverage`.

## Test Coverage (from testing-specialist)

- C1 (mlflow_format.py zero tests): **FIXED** — 16 new tests in `test_mlflow_format.py`
- C2 (\_feature_sql.py zero tests): **FIXED** — 14 new tests in `test_feature_sql.py`
- H1 (RL module minimal): acknowledged, SB3 not installed in CI
- H2 (Agent tests import-only): acknowledged, LLM required for behavioral tests
- H3 (No E2E tier): tracked

## Security (from security-reviewer)

All CRITICAL items fixed. Notable passes:

- GPU setup shell safety: PASSED
- Agent LLM-first compliance: PASSED
- SQL parameterized queries: PASSED
- Model class allowlist: PASSED
- Pickle security comments: present at all 3 sites

## Next Steps (R2)

1. Fix H2 (bounded collections) — add `deque(maxlen=10000)` where needed
2. Fix H3 (TOCTOU) — wrap in transactions
3. Fix H4 (dedup) — extract shared modules
4. Implement H5 (DataExplorer.compare) and H6 (interop converters)
5. Re-run affected tests only
