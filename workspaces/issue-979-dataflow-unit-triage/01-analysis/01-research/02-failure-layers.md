# Failure Layers — Verified State (Current Main `21ba8e6a`)

Each layer below maps to one of PR #977's revert citations and one
of #979's acceptance criteria. Receipts cite the parallel
verification agents' findings recorded in `journal/0001`.

## Layer A — Plugin / config preconditions

| Concern                          | State on main                                                    |
| -------------------------------- | ---------------------------------------------------------------- |
| `pytest-timeout>=2.3.0`          | Pinned at root `pyproject.toml:166`. NOT in dataflow `[dev]`.    |
| `pytest-forked`                  | NOT pinned in root nor in dataflow. Transitive in dev venv only. |
| `timeout = 120` in pytest config | ABSENT from `pytest.ini` and `pyproject.toml`.                   |
| AST assertion rewriting          | ENABLED (no `--assert=plain`). 3849 tests collected.             |
| unified-ci.yml dataflow job      | NOT PRESENT (fully reverted with #968).                          |

Implication: any subsequent shard's failure surfaces as a 6-hour
job-wide timeout instead of a single-test failure with traceback.
This layer MUST land first.

## Layer B — `test_example_gallery.py` deadlock

| Concern                                                | State on main                                                             |
| ------------------------------------------------------ | ------------------------------------------------------------------------- |
| File exists / line count                               | YES / 1094 LOC                                                            |
| `from kailash.runtime import AsyncLocalRuntime`        | line 22                                                                   |
| `from kailash.workflow.builder import WorkflowBuilder` | line 23                                                                   |
| `_DB_FILE = tempfile.mktemp(...)` module-scoped        | line 28-30                                                                |
| `DB_URL` shared across all 10 tests                    | YES                                                                       |
| `DataFlow(DB_URL)` without kwargs                      | 10 instantiations (lines 58, 129, 241, 324, 420, 506, 608, 703, 836, 969) |
| `_fresh_db_url()` helper (PR #976)                     | ABSENT                                                                    |
| `auto_migrate=True` default fires per-test             | YES (engine.py:151 default)                                               |

This is the originating hang: every test triggers DDL on a shared
SQLite file, hitting `dataflow_migration_locks` contention,
producing the 15-minute CI timeout cited in PR #976. The
`memory_dataflow` fixture in `tests/unit/conftest.py:75` was
authored specifically to fix this class of bug. The file does
not use it.

## Layer C — `tests/unit/fabric/` import-time fails

| Concern                                | State on main                                                       |
| -------------------------------------- | ------------------------------------------------------------------- |
| `tests/unit/fabric/` exists            | YES (21 test files + `__init__.py`)                                 |
| Top-imports `from dataflow.fabric.*`   | 17 of 21 files                                                      |
| `dataflow.fabric` location             | In-tree at `src/dataflow/fabric/`                                   |
| Runtime deps for fabric                | `httpx>=0.27, watchdog>=4.0, msgpack>=1.0, prometheus-client>=0.20` |
| `[fabric]` extra declared              | YES at `packages/kailash-dataflow/pyproject.toml:95-100`            |
| `importorskip` gating in unit/fabric/  | ZERO                                                                |
| `tests/integration/fabric/` target dir | DOES NOT EXIST                                                      |

Implication: a clean `[dev]`-only install fails at import time on
17 files. The 4 fabric files that import only `dataflow.adapters.*`
or stdlib (`test_express_pagination.py`,
`test_metrics_phase_5_12.py`, `test_resource_warning.py`,
`test_source_adapter.py`) MAY belong in unit-tier but need a
case-by-case check.

## Layer D — PostgreSQL-requiring "unit" tests

| Concern                                                                                       | State on main                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `TestImpactReporterIntegration` in `tests/unit/`                                              | `tests/unit/migration/test_impact_reporter_unit.py:67` uses `IntegrationTestSuite` (PG:5434)                                                                                                                       |
| `IntegrationTestSuite` usage from unit                                                        | 2 files: `cache/test_cache_invalidation.py:35`, `migration/test_impact_reporter_unit.py:56`                                                                                                                        |
| Bare top-import `import asyncpg`                                                              | `tests/unit/testing/test_tdd_support.py:16`                                                                                                                                                                        |
| PG:5434 URLs (likely real)                                                                    | 3 files: `test_migration_test_framework.py:48,82`; `test_dataflow_bug_011_012_fixes.py:230,273`; `test_tdd_node_generation_integration.py:148,182,267`                                                             |
| PG:5432 URLs (may be patched)                                                                 | 7 files: `test_bug_006_safety_parameters.py`, `test_actual_api_validation.py`, `test_real_tdd_integration.py`, `test_count_node.py:21`, `test_bulk_upsert_delegation.py:28`, `test_architecture_validation.py:197` |
| `requires_postgres / requires_mysql / requires_redis / requires_docker` markers used in unit/ | ZERO                                                                                                                                                                                                               |
| `addopts` excludes `requires_*` for unit tier                                                 | NO                                                                                                                                                                                                                 |

Implication: broader than #979 listed. A correct fix audits ALL
files carrying real-shaped DB URLs and either gates them or
moves them. `migration/` (singular) and `migrations/` (plural)
are DIFFERENT directories — both exist.

## Layer E — Suite-level memory / `test_dataflow_events.py`

| Concern                                       | State on main                                                            |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| Total `tests/unit/` count                     | 3849 collected in 1.60s (local dev venv with `[fabric]`)                 |
| Collection errors                             | ZERO (dev venv has fabric deps; CI tier-1 venv would NOT)                |
| `tests/unit/features/test_dataflow_events.py` | 182 LOC, 11 tests, pure-Python (no DB, no asyncpg, no AsyncLocalRuntime) |
| `dataflow.core.events` module imports         | line 16-20                                                               |
| Test setup pattern                            | `class FakeDataFlow(DataFlowEventMixin)` at line 49-52                   |
| PR #976's "4+ failures"                       | NOT REPRODUCING locally on main                                          |

Implication: the events file's "4+ failures" framing from
PR #976 either was transient (env / ordering) or has been
addressed by other commits. Acceptance criterion #2 in #979
needs re-scoping to **"verify clean in `[dev]`-only env;
document as already-resolved if green"**.

## Pre-existing direct contract violations (tier-1 CLAUDE.md)

Beyond the 5 PR #977 layers, the suite has institutional contract
drift recorded in `03-violations-inventory.md`:

- `tempfile.NamedTemporaryFile` / `tempfile.mktemp()` in 8 files
  (instead of `memory_dataflow` / `file_dataflow` fixtures).
- 15+ files instantiate `DataFlow(...sqlite:///...)` ad hoc
  (instead of fixture).
- 2 files import `IntegrationTestSuite` (the PG infra harness)
  inside `tests/unit/`.

Per CLAUDE.md: every one of these is a contract violation. The
fix is structural (use the fixtures) AND classification
(integration-shaped tests move to `tests/integration/`).
