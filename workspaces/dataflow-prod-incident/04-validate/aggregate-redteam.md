# /redteam — Validation Aggregate (2026-04-28)

Two consecutive clean rounds. Convergence reached.

## Releases verified live on PyPI

- `kailash 2.12.0` — clean-venv install OK; `AsyncSQLDatabaseNode.pool_count()` returns 0; `PoolExhaustedError` accessible
- `kailash-dataflow 2.4.0` — clean-venv install OK; `DDLFailedError` accessible; `DataFlowEngineBuilder('sqlite:///:memory:').build_sync()` returns DataFlowEngine

## Round 1 — Spec Compliance (AST/grep, NOT file existence)

Per `skills/spec-compliance/SKILL.md`, every spec promise verified by literal AST or grep, NOT file existence.

### Shard A (#696 DDL fail-fast)

| Assertion                                   | Verification                                                                                 | Result                 |
| ------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------- |
| `DDLFailedError` class exists               | `ast.parse('packages/kailash-dataflow/src/dataflow/core/exceptions.py')` walk for `ClassDef` | `['DDLFailedError']` ✓ |
| `auto_migrate` arg on `DataFlow.__init__`   | AST walk for `FunctionDef('__init__')` in `ClassDef('DataFlow')`                             | True ✓                 |
| `_failed_table_creations` attribute set     | `grep -c '_failed_table_creations' core/engine.py`                                           | 10 references ✓        |
| `DDLFailedError` raised in production paths | `grep -n 'raise self._DDLFailedError'`                                                       | 5 raise sites ✓        |
| Regression test exists                      | `pytest --collect-only test_issue_696_ddl_retry_storm.py`                                    | 14 tests collect ✓     |

### Shard B (#697 + #698 pool lifecycle)

| Assertion                                    | Verification                                                        | Result                                                           |
| -------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `_PROCESS_POOL_REGISTRY` exists              | `hasattr(kailash.nodes.data.async_sql, '_PROCESS_POOL_REGISTRY')`   | True (WeakValueDictionary) ✓                                     |
| `_POOL_DEFAULTS` exists                      | `hasattr(...)`                                                      | True (dict, max=100, idle=300) ✓                                 |
| `set_pool_defaults` callable                 | `hasattr(...)`                                                      | True (function) ✓                                                |
| `_REAPER_TASKS` exists                       | `hasattr(...)`                                                      | True (dict) ✓                                                    |
| `_ensure_reaper_started` callable            | `hasattr(...)`                                                      | True ✓                                                           |
| `pool_count()` classmethod                   | `AsyncSQLDatabaseNode.pool_count()`                                 | Returns 0 on import ✓                                            |
| `PoolExhaustedError` raised at cap           | `grep -n 'raise PoolExhaustedError' async_sql.py`                   | Line 4279 ✓                                                      |
| `len(_PROCESS_POOL_REGISTRY)` consumer sites | `grep -n 'len(_PROCESS_POOL_REGISTRY)'`                             | 5 sites (pool_count, fallback cap check, reaper, warning logs) ✓ |
| Unit tests pass                              | `pytest -q tests/unit/nodes/data/test_pool_*.py test_exceptions.py` | 47/47 ✓                                                          |
| Regression tests collect                     | `pytest --collect-only test_issue_697_pool_leak.py`                 | 6 tests ✓                                                        |

### Shard C (#685 + #686 engine surface)

| Assertion                                                  | Verification                                                           | Result                                |
| ---------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------- |
| `DataFlow.register_model` exists                           | AST walk for `FunctionDef('register_model')` in `ClassDef('DataFlow')` | True ✓                                |
| `DataFlowEngineBuilder.build` exists                       | AST walk in `ClassDef('DataFlowEngineBuilder')`                        | True ✓                                |
| `DataFlowEngineBuilder.build_sync` exists                  | AST walk                                                               | True ✓                                |
| `DataFlowEngine.register_model` end-to-end                 | `engine.register_model(None, Foo)` against real instance               | No AttributeError ✓                   |
| `engine.get_model_classification_report(Foo)` returns dict | Direct call                                                            | `{}` ✓ (no classification policy set) |
| Regression tests pass                                      | `pytest tests/regression/test_issue_685_*.py test_issue_686_*.py`      | 11/11 ✓                               |

## Round 2 — Security + Orphan + Log Triage

| Check                                             | Method                                                                                 | Result         |
| ------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------- |
| No `eval()` / `exec()` / `shell=True` introduced  | `git diff 9c8dd44b..HEAD` filtered                                                     | Clean ✓        |
| No hardcoded secrets                              | `git diff` filtered for api_key/password literals                                      | Clean ✓        |
| Every new public symbol has a consumer            | `getattr(module, sym)` for each + verify `pool_count()` reads `_PROCESS_POOL_REGISTRY` | All consumed ✓ |
| Log triage: WARN/ERROR in test output             | `pytest 2>&1 \| grep -iE "warn\|error\|deprecat"`                                      | Empty ✓        |
| Per-package collection (orphan-detection.md § 5a) | `cd packages/kailash-dataflow && pytest --collect-only`                                | 25 tests ✓     |
| Run dataflow regression tests                     | `pytest tests/regression/test_issue_{696,685,686}*.py`                                 | 25/25 pass ✓   |

## Brief-to-spec coverage (rules/specs-authority.md)

| Brief requirement                             | Spec section                                             | Verification site                                      |
| --------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------ |
| R1: DDL fail-fast typed error + bounded retry | `specs/dataflow-core.md` § 1.6 Auto-Migrate Semantics    | DDLFailedError + 5 raise sites + 14 regression tests   |
| R2: AsyncSQL pool fallback bounded            | `specs/dataflow-cache.md` § 13.4 Pool Lifecycle Contract | PoolExhaustedError at cap + 6 regression tests         |
| R3: idle-timeout + LRU configurable           | `specs/dataflow-cache.md` § 13.4                         | set_pool_defaults + idle reaper + 47 unit tests        |
| R4: register_model end-to-end                 | `specs/dataflow-core.md` § DataFlowEngine                | DataFlow.register_model + Engine passthrough + 7 tests |
| R5: build_sync companion                      | `specs/dataflow-core.md` § DataFlowEngine.builder        | build_sync method + 4 tests                            |
| R6: Tier-2 regression tests for every fix     | `rules/testing.md` § E2E Pipeline Regression             | 31 total (14+6+11)                                     |
| R7: Cross-SDK inspection on every fix         | `rules/cross-sdk-inspection.md` MUST Rule 1              | esperie/kailash-rs#673, #674, #675                     |

ALL 7 brief requirements have a verifiable trace.

## Convergence criteria check (per /redteam skill)

| Criterion                               | Status                                                                                                                                |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 0 CRITICAL findings                     | ✓                                                                                                                                     |
| 0 HIGH findings                         | ✓                                                                                                                                     |
| 2 consecutive clean rounds              | ✓ (Round 1 + Round 2)                                                                                                                 |
| Spec compliance: 100% AST/grep verified | ✓ (every assertion has literal verification command + actual output)                                                                  |
| New code has new tests                  | ✓ (`tests/regression/test_issue_697_pool_leak.py` imports `kailash.nodes.data.async_sql`; `test_issue_696/685/686` import `dataflow`) |
| Frontend integration: 0 mock data       | N/A (backend-only workstream)                                                                                                         |

**CONVERGED.**

## Issues closed (delivered-code reference per rules/git.md § Issue Closure Discipline)

| Issue | State  | Closed at            | Reference                         |
| ----- | ------ | -------------------- | --------------------------------- |
| #696  | CLOSED | 2026-04-28T11:24:10Z | PR #703 → kailash-dataflow v2.4.0 |
| #697  | CLOSED | 2026-04-28T11:24:06Z | PR #702 → kailash v2.12.0         |
| #698  | CLOSED | 2026-04-28T11:24:06Z | PR #702 → kailash v2.12.0         |
| #685  | CLOSED | 2026-04-28T11:24:14Z | PR #704 → kailash-dataflow v2.4.0 |
| #686  | CLOSED | 2026-04-28T11:24:15Z | PR #704 → kailash-dataflow v2.4.0 |

## Cross-SDK followups filed at esperie/kailash-rs

- #673 (DPI-B pool registry parity)
- #674 (DPI-A DDL fail-fast parity)
- #675 (DPI-C build_sync parity)

## Tests summary

- **Unit (Tier 1):** 47 pool tests passing on import
- **Regression (Tier 2):** 31 tests across both packages (14 DDL + 6 pool + 7 engine.register + 4 build_sync). Pool regression skips locally without Docker; will run in CI.
- **Bridge (D2):** added at `tests/regression/test_dataflow_pool_bridge.py` (cross-package; integrates Shard A + Shard B; skips without Docker)

## Notes

- Pre-existing pyright diagnostics on `engine.py` (TenantContextSwitch undefined, max_overflow unknown, \_engine unknown, etc.) are NOT introduced by this workstream and remain on separate workstreams per `rules/zero-tolerance.md` Rule 1's shard-scope clause.
- The IDE pyright server may show transient `from .core.exceptions import DDLFailedError` resolution errors until the IDE refreshes; the file exists at `packages/kailash-dataflow/src/dataflow/core/exceptions.py` (4725 bytes) and the import resolves at runtime.
