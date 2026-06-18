# Violations Inventory — Files vs Contract

Source: parallel agent findings + targeted grep on
`packages/kailash-dataflow/tests/unit/`. Each row cites the
canonical contract clause it violates (see `01-tier1-contract.md`).

## V1 — `IntegrationTestSuite` use inside `tests/unit/`

Violates: contract clause #1 (no external infra) — requires PG:5434.

| File                                                         | Disposition                           |
| ------------------------------------------------------------ | ------------------------------------- |
| `tests/unit/cache/test_cache_invalidation.py:35`             | MOVE → `tests/integration/cache/`     |
| `tests/unit/migration/test_impact_reporter_unit.py:50,56,67` | MOVE → `tests/integration/migration/` |

## V2 — Bare top-import of DB driver

Violates: contract clause #1 — module fails to load without driver.

| File                                     | Import (line)         | Disposition                                             |
| ---------------------------------------- | --------------------- | ------------------------------------------------------- |
| `tests/unit/testing/test_tdd_support.py` | `import asyncpg` (16) | Wrap in `pytest.importorskip("asyncpg")` at top OR MOVE |

## V3 — `tests/unit/fabric/` with `dataflow.fabric.*` top-imports

Violates: contract clause #1 — modules require `[fabric]` extra
(httpx, watchdog, msgpack, prometheus-client) absent in clean
`[dev]` install.

Files (17 of 21 in `tests/unit/fabric/`): `test_config.py`,
`test_context.py`, `test_fabric_integrity.py`,
`test_file_directory_scanning.py`, `test_health.py`,
`test_mcp_integration.py`, `test_metrics.py`,
`test_metrics_phase_5_12.py` (verify — agent flagged this as
NOT top-importing fabric; re-check), `test_products.py`,
`test_products_dag.py`, `test_serving.py`,
`test_source_registration.py`, `test_sse.py`, `test_ssrf.py`,
`test_testing.py`, `test_webhook_providers.py`,
`test_webhooks.py`.

Plus 4 files that import only `dataflow.adapters.*` or stdlib —
case-by-case keep in unit OR move with siblings for cohesion:
`test_express_pagination.py`, `test_metrics_phase_5_12.py`,
`test_resource_warning.py`, `test_source_adapter.py`.

Disposition recommendation: MOVE entire directory →
`tests/integration/fabric/` AND document `[fabric]` extra in
`tests/CLAUDE.md` integration-tier instructions. (The 4
adapter-only files migrate too for cohesion — a single test
directory is easier to reason about than per-file decisions.)

## V4 — Real-shaped PG URLs at module / test scope

Violates: contract clause #1 — even patched, the URLs encode
the test's true infra dependency.

PG:5434 (likely real connection attempts):

- `tests/unit/migrations/test_migration_test_framework.py:48,82`
- `tests/unit/test_dataflow_bug_011_012_fixes.py:230,273`
- `tests/unit/test_tdd_node_generation_integration.py:148,182,267`

PG:5432 (may be patched — verify):

- `tests/unit/test_bug_006_safety_parameters.py` (10 sites)
- `tests/unit/test_actual_api_validation.py` (10 sites)
- `tests/unit/test_real_tdd_integration.py` (5 sites)
- `tests/unit/test_count_node.py:21`
- `tests/unit/test_bulk_upsert_delegation.py:28`
- `tests/unit/test_architecture_validation.py:197`

Disposition: per-file audit at /implement time.

- If test actually requires PG: MOVE → `tests/integration/`.
- If test uses URL only for parsing / construction with mocks:
  refactor to use a SQLite URL or a `sentinel` string with no
  real connection attempt; document the parse-only intent.

## V5 — `tempfile.mktemp()` / `NamedTemporaryFile` for DB path

Violates: contract clause #2 (use fixtures).

| File                                                      | Sites                                           |
| --------------------------------------------------------- | ----------------------------------------------- |
| `tests/unit/migrations/test_sync_ddl_executor.py`         | 9                                               |
| `tests/unit/core/test_async_sql_sqlite.py:23`             | 1                                               |
| `tests/unit/testing/test_tdd_performance_benchmark.py`    | 4                                               |
| `tests/unit/testing/test_performance_regression_suite.py` | 2 (JSON files, not DB — could keep but mark)    |
| `tests/unit/examples/test_example_gallery.py:29`          | 1 (module-scope `mktemp` — the deadlock source) |
| `tests/unit/context_aware/test_performance_benchmarks.py` | 3                                               |
| `tests/unit/context_aware/test_instance_isolation.py`     | ≥1                                              |

Disposition: refactor to use `memory_dataflow` / `file_dataflow`
fixtures from `tests/unit/conftest.py`. The `test_example_gallery`
case is special (10 tests share state through real workflow
execution) — fastest path is MOVE → `tests/integration/examples/`
since the tests genuinely exercise `AsyncLocalRuntime` end-to-end.

## V6 — Ad-hoc `DataFlow(...sqlite:///...)` instantiation

Violates: contract clause #2.

Files (from grep `DataFlow(.*sqlite:///`): 15 files.
Cross-reference with V5 — most overlap. Files in this list
that are NOT already covered by V5:

- `tests/unit/test_derived_model.py`
- `tests/unit/migrations/test_async_safe_run_integration.py`
- `tests/unit/core/test_fabric_only_mode.py`
- `tests/unit/core/test_dataflow_2026_001_fixes.py`
- `tests/unit/core/test_architecture_validation.py`
- `tests/unit/core/test_pool_defaults.py`
- `tests/unit/core/test_lazy_connection.py`
- `tests/unit/features/test_read_replica.py`
- `tests/unit/fabric/test_products.py` (covered by V3)
- `tests/unit/fabric/test_source_registration.py` (covered by V3)
- `tests/unit/test_inspector_workflow_analysis.py`

Disposition: refactor to fixture pattern. These files MAY still
hang under contention if they share state — fixture isolation
fixes that class.

## Aggregate count

- V1 (IntegrationTestSuite): **2 files** (move)
- V2 (bare DB-driver import): **1 file** (gate or move)
- V3 (fabric/): **21 files** in directory (move directory)
- V4 (PG URLs): **9 files** (per-file audit)
- V5 (tempfile-based): **7 files** (refactor or move)
- V6 (ad-hoc sqlite): **15 files** total, ~8 net new after V3+V5 overlap

**Net distinct files needing change: ~30-35** (small denominator;
some files are listed across multiple violations).

This is large but mechanical — each violation has a small,
well-defined fix. The shard plan can group by violation class
(V1+V2 cheap, V3 single directory move, V4-V6 file-by-file).
