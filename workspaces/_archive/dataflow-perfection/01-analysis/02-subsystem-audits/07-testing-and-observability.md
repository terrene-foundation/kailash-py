# Testing + Observability Audit

Scope: `packages/kailash-dataflow/tests/` (486 `.py` files), `packages/kailash-dataflow/src/dataflow/testing/` (7 modules), and every observability surface (logging, metrics, tracing, audit) across `packages/kailash-dataflow/src/dataflow/` (280 `.py` files, 28 subsystems).

Methodology: `rules/testing.md` § Audit Mode was followed. The `.test-results` file was not consulted. Coverage was re-derived from test imports via ripgrep. Every claim below is cited `file:line` or `grep <pattern>`.

Cross-SDK note: this audit is Python-only. The cross-SDK inspection (`rules/cross-sdk-inspection.md`) for the equivalent Rust tree (`kailash-rs/crates/kailash-dataflow/tests`) is deferred to `02-plans/02-followups-and-cross-sdk.md`, but every finding below should be cross-filed to `esperie-enterprise/kailash-rs` unless verified not to apply.

## Executive summary

DataFlow ships today with a test surface that looks large (486 files, 223 unit, 182 integration, 50 e2e) but is systematically falsified at the two tiers that matter. The integration tier — where `rules/testing.md` says mocking is BLOCKED — contains **118 unittest.mock usages across 30 files**. The fabric tier — where the entire `#354` class of bugs lives — never exercises Redis even once: all eleven `PipelineExecutor(...)` call sites in the fabric directory pass `dev_mode=True` with no `redis_url`, meaning the shared-state code path that the brief identifies as the root cause of multi-replica data loss has zero test coverage. The regression directory, which the rules describe as "permanent bug reproduction", has exactly one test file after two and a half years of bug fixes.

Observability is worse. Structured-field logging exists in 8 call sites across 4 files (`grep -E 'logger\.(info|warning|error|debug)\s*\(\s*"[^"]+",\s*\w+='`) against **969 f-string-interpolated log calls across 99 files** — a 121× ratio against the rule. There are zero `correlation_id`/`request_id`/`trace_id` bindings in any application code path; the only nine occurrences are in migration and trust wrappers. There is no `mode=real|cached|fake` field anywhere in the source tree (`grep 'mode=.real|mode=.cached|mode=.fake'` returns zero results). The only Prometheus metric module (`fabric/metrics.py`, 166 lines, 10 metrics) is instantiated exactly once — inside its own unit test. The entire DataFlow production code path emits zero Prometheus metrics at runtime. There is zero OpenTelemetry instrumentation (`grep 'from opentelemetry|tracer\.start|start_as_current_span'` = 0 files). There are **301 bare `print()` calls across 37 files** in production source, 73 in `platform/inspector.py` alone.

The `no_mocking_policy` fixture that conftest.py defines at `tests/conftest.py:455` to enforce the Tier 2 anti-mocking rule is referenced nowhere else in the test tree. It is dead policy. The `pytest.ini` turns warnings off globally with `-p no:warnings --disable-warnings`, meaning the entire zero-tolerance log-triage protocol (`rules/observability.md` § 5) is structurally impossible to execute against this package.

If `/redteam` certified that tests pass, it certified noise. The analysis-phase verdict is: the test suite's weight is mostly load-bearing fiction, and the observability layer that would let an operator diagnose a production failure does not exist.

## Tier compliance summary

| Tier                     | Files | `unittest.mock` imports | % violating rule  |
| ------------------------ | ----- | ----------------------- | ----------------- |
| 1 (`tests/unit/`)        | 223   | allowed                 | n/a               |
| 2 (`tests/integration/`) | 182   | **118 in 30 files**     | **16.5%**         |
| 2 (`tests/fabric/`)      | 4     | **4 in 1 file**         | **25%**           |
| 3 (`tests/e2e/`)         | 50    | **15 in 4 files**       | **8%**            |
| 3 (`tests/tier3_e2e/`)   | 1     | 0                       | 0%                |
| regression/              | 1     | 0                       | 0% (1 file total) |
| bug_reproduction/        | 1     | 0                       | 0% (1 file total) |

Verification commands:

- `grep -rln "from unittest.mock\|import mock\|MagicMock\|@patch\|Mock()\|AsyncMock" packages/kailash-dataflow/tests/integration` → 30 files
- `grep -rln "from unittest.mock\|import mock\|MagicMock\|@patch\|Mock()\|AsyncMock" packages/kailash-dataflow/tests/e2e` → 4 files
- `grep -rln "from unittest.mock\|import mock\|MagicMock\|@patch\|Mock()\|AsyncMock" packages/kailash-dataflow/tests/fabric` → 4 files (1 actually imports `unittest.mock`, 3 mention it in docstrings declaring they do NOT mock)

### Folder hygiene violations

- `tests/integration/tenancy/test_query_interceptor.py:1` — docstring reads `"""Unit tests for SQL query interceptor in multi-tenant mode."""` but file is in `integration/`. It mocks (`from unittest.mock import Mock, patch` at line 12) because its author knew it was a unit test. Misfiled by directory.
- `tests/integration/cache/test_cache_invalidation.py:14` imports `AsyncMock, Mock, patch` and at line 48 literally writes `mock_cache_manager = Mock()`. This is a pure unit test masquerading as an integration test because the file lives in `tests/integration/cache/`.
- `tests/integration/migration/test_column_removal_integration.py` has 19 mock usages — the highest mock count of any "integration" file in the package. The filename ends in `_integration` but the body is a unit test.
- `tests/integration/tenancy/test_multi_tenancy_integration.py` is flagged by grep as a matcher for the word "tenant" but the Tier 2 file imports `from dataflow.core.multi_tenancy`, **bypassing** the `dataflow/tenancy/` module which is the actual multi-tenant enforcement layer (see `tests/integration/tenancy/test_query_interceptor.py` for the contrast).

## CRITICAL findings

### C-T1. Fabric Redis code path has zero test coverage

`rules/testing.md` § Coverage Requirements: "Financial / Auth / Security-critical — 100%". The fabric pipeline's cross-replica consistency is security-critical because it determines whether multi-tenant product caches can leak between workers.

Every single fabric test constructs `PipelineExecutor` with `dev_mode=True` and no `redis_url`:

- `tests/fabric/test_fabric_cache_control.py:30` — `PipelineExecutor(dataflow=mock_df, max_concurrent=2, dev_mode=True)`
- `tests/fabric/test_fabric_critical_bugs.py:88,142,197,347,399` — five call sites, all `dev_mode=True`, all no `redis_url`
- `tests/fabric/test_fabric_integration.py:168,238,328,467,522` — five call sites, identical shape

Total: **11 fabric `PipelineExecutor(...)` constructions, 0 with Redis**. Grep verification: `grep -n "PipelineExecutor(" packages/kailash-dataflow/tests/fabric/*.py | grep -v dev_mode=True` → empty. The Redis leader-election, cross-worker cache invalidation, and webhook nonce deduplication code paths that `CHANGELOG.md:13-15` documents as features have **never been exercised by a single automated test**. This is the direct confirmation of issue #354's blast radius.

### C-T2. 30 Tier-2 files violate the no-mocking rule

`rules/testing.md` § Tier 2: "Real database, real API calls (test server). NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED)".

`grep -c "from unittest.mock\|import mock\|MagicMock\|@patch\|Mock()\|AsyncMock" packages/kailash-dataflow/tests/integration/**/*.py` → 118 total occurrences across 30 files. Worst offenders:

| File                                                                  | Mock count |
| --------------------------------------------------------------------- | ---------- |
| `tests/integration/cache/test_cache_invalidation.py`                  | 28         |
| `tests/integration/migration/test_column_removal_integration.py`      | 19         |
| `tests/integration/transactions/test_workflow_context_integration.py` | 14         |
| `tests/integration/model_registry/test_model_registry.py`             | 10         |
| `tests/integration/migration/test_fk_safe_migration_integration.py`   | 6          |
| `tests/integration/test_dataflow_bug_011_012_integration.py`          | 6          |
| `tests/integration/monitoring/test_health_monitor_integration.py`     | 4          |

Every one of these is a BLOCKING finding per `rules/testing.md` § Audit Mode.

### C-T3. The `no_mocking_policy` fixture is dead

`tests/conftest.py:455-490` defines a fixture that replaces `unittest.mock.Mock`, `MagicMock`, and `patch` with functions that raise `RuntimeError("Mocking is not allowed in integration tests! Use real infrastructure.")`. That fixture is referenced **zero** times elsewhere in the test tree (`grep -rln "no_mocking_policy" tests/` → one file: the conftest that defines it). A fixture that nothing requests is not a policy; it is performance art.

### C-T4. Regression discipline is effectively nonexistent

`rules/testing.md` § Regression Testing: "Place in `tests/regression/test_issue_*.py`. Regression tests are NEVER deleted."

`ls tests/regression/`:

```
backward_compatibility_check.py
FEATURE_DEVELOPMENT_GATES.md
full_regression_suite.sh
performance_benchmark.py
quick_validation.sh
README.md
REGRESSION_ANALYSIS_REPORT.md
REGRESSION_TESTING_PROTOCOL.md
simple_validation.py
test_redteam_r4_nonce_and_source_validation.py   ← the ONLY test_*.py
validate_core_functionality.py
```

One test file. Meanwhile closed-bug telemetry from `gh issue list --repo terrene-foundation/kailash-py --state closed --label bug` shows at least 20 recent dataflow-class fixes (#296 `bulk_upsert` event emission, #281 `ConnectionManager.close()` swallows exceptions, #268 `ProductInvokeNode.execute()` missing method, etc.) with zero `tests/regression/test_issue_*.py` counterparts. The existing bug-fix tests are scattered:

- `tests/integration/migration/test_bug_006_validation.py`
- `tests/unit/test_dataflow_bug_fixes_validation.py`
- `tests/unit/test_dataflow_bug_011_012_unit.py`
- `tests/unit/test_dataflow_bug_011_012_fixes.py`
- `tests/integration/test_dataflow_bug_011_012_integration.py`
- `tests/e2e/migrations/test_migration_bug_006_e2e.py`

Not one is in `tests/regression/`. There is no `@pytest.mark.regression` discipline that maps a test to an issue number, so the "never delete" guarantee is purely verbal.

### C-T5. Every CRITICAL security finding from the tenancy audit has zero regression coverage

Per the tenancy/security sub-audit's nine CRITICAL findings, I greped each for a regression test:

- **SQL injection in `multi_tenancy.py`**: `grep -rln "test.*sql.*injection.*multi.*tenant" tests/` → 0. Closest is `tests/integration/security/test_sql_injection_prevention.py` which does NOT import `dataflow.core.multi_tenancy`.
- **`eval()` on row embeddings in `semantic/search.py:134`** (`else eval(row["embedding"])`): `grep -rln "test.*eval\|semantic.*search\|test.*embedding.*injection" tests/` → 0 tests for the `eval` path. `tests/unit/core/test_semantic_memory.py` exists but does not exercise the arbitrary-code-execution surface.
- **`exec()` in `nodes/dynamic_update.py:172,182`** (`exec(self.filter_code, {}, namespace)`, `exec(self.prepare_code, ...)`): `grep -rln "dynamic_update.*exec\|filter_code.*injection\|test.*exec.*injection" tests/` → 0.
- **Fake `encrypt_tenant_data`**: no test exists named or asserting against the real-vs-fake behavior.
- **Express cache tenant leak**: `tests/unit/test_express_cache_wiring.py` exists but the 2 `redis_url` references there are in a fixture helper signature, not a multi-tenant-leak test.
- **Fabric cache multi-tenant leak**: no fabric test ever passes `tenant_id`. `grep -n "tenant" packages/kailash-dataflow/tests/fabric/*.py` → 0 hits.

`rules/testing.md` § Audit Mode: "For every § Security Threats subsection in any spec, grep for a corresponding `test_<threat>` function. Missing = HIGH." Six out of six of the escalated security threats have no test. I classify this as CRITICAL because the cost of a production tenant leak exceeds the cost of the missing tests by several orders of magnitude.

### C-O1. Structured logging is 99.2% broken

`rules/observability.md` § MUST NOT: "No unstructured `f\"...\"` log messages. Pass fields as keyword arguments."

- `grep -rc 'logger\.(info|warning|error|debug|critical)\s*\(\s*f["'"'"']' packages/kailash-dataflow/src/dataflow/` → **969 occurrences across 99 files**
- `grep -rc 'logger\.(info|warning|error|debug)\s*\(\s*"[^"]+",\s*\w+=' packages/kailash-dataflow/src/dataflow/` → **8 occurrences across 4 files**

That is a 121:1 ratio in favor of unstructured f-string logs. Top offenders by raw count:

| File                                                        | f-string log calls |
| ----------------------------------------------------------- | ------------------ |
| `src/dataflow/core/engine.py`                               | 90                 |
| `src/dataflow/migrations/auto_migration_system.py`          | 41                 |
| `src/dataflow/core/multi_tenancy.py`                        | 39                 |
| `src/dataflow/adapters/mongodb.py`                          | 36                 |
| `src/dataflow/migrations/fk_aware_system_demo.py`           | 33                 |
| `src/dataflow/migrations/fk_aware_workflow_orchestrator.py` | 28                 |
| `src/dataflow/migrations/postgresql_test_manager.py`        | 26                 |

Every one of these files is BLOCKED by `rules/observability.md`.

### C-O2. Zero correlation-ID propagation

`rules/observability.md` § 2: "Every log line in a request/handler/agent execution MUST carry a correlation ID (request_id, trace_id, run_id) bound for the entire scope of that execution."

- `grep -rc 'correlation_id|request_id|trace_id' packages/kailash-dataflow/src/dataflow/` → 9 occurrences in 2 files (`migrations/concurrent_access_manager.py`, `trust/query_wrapper.py`). Both use the tokens as local variable names, not as `logger.bind(...)` calls.
- `grep -rc 'logger\.bind\|structlog\.bind\|contextvars' packages/kailash-dataflow/src/dataflow/` → 0 file hits for `logger.bind` or `structlog.bind`.

The gateway integration layer (`src/dataflow/gateway_integration.py`), Nexus adapter surface, and all fabric endpoints emit logs with no correlation ID. Multi-step requests will interleave in any aggregator.

### C-O3. FabricMetrics is dead code

`src/dataflow/fabric/metrics.py` declares 10 Prometheus metrics (lines 58-109 — `Gauge`, `Histogram`, `Counter` for `source_health`, `source_check_duration`, `source_consecutive_failures`, `pipeline_duration`, `pipeline_runs_total`, `cache_hit_total`, `cache_miss_total`, `product_age_seconds`, `request_duration`, `request_total`).

- `grep -rn "FabricMetrics(" packages/kailash-dataflow/` → exactly one hit: `tests/unit/fabric/test_metrics.py:17: cls._metrics = FabricMetrics()`.
- `grep -rn "from dataflow.fabric.metrics\|from dataflow.fabric import metrics\|from \.metrics import" packages/kailash-dataflow/src/dataflow/fabric/` → **zero hits**. No sibling module in `fabric/` imports this file.

The module header literally says "TODO-21" at line 4, a violation of `rules/zero-tolerance.md` Rule 2 (TODO markers BLOCKED). The entire metrics module is a 166-line stub that was written, tested in isolation, and never wired into production. This is the metrics counterpart to the `no_mocking_policy` fixture: infrastructure built to look like infrastructure.

### C-O4. `pytest.ini` globally suppresses warnings

`packages/kailash-dataflow/pytest.ini:34`:

```
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings
    -p no:warnings
```

`rules/zero-tolerance.md` Rule 1 + `rules/observability.md` MUST Rule 5 require that WARN+ entries are diagnosed and either fixed or acknowledged before any gate. With `--disable-warnings` and `-p no:warnings`, the package has structurally disabled the log-triage gate. Every `DeprecationWarning`, `ResourceWarning`, `RuntimeWarning` from 486 test files is silently swallowed. This is a deeper violation than any individual test mock because it's a global opt-out from the observability discipline.

### C-O5. 301 `print()` calls in production source

`rules/observability.md` § MUST Rule 1: "`print()`, `console.log()`, `eprintln!`, `puts` are BLOCKED in production code."

- `grep -rc 'print\s*\(' packages/kailash-dataflow/src/dataflow/` → 301 across 37 files.
- Top: `platform/inspector.py:73`, `cli/inspector_cli.py:75`, `migrations/auto_migration_system.py:44`, `debug/solution_generator.py`, `debug/debug_agent.py`.

The CLI files (`cli/inspector_cli.py`, `debug/cli.py`) are partially defensible — CLI output is stdout — but `platform/inspector.py` is an application module, `migrations/auto_migration_system.py` is runtime migration code, and `debug/solution_generator.py` ships in production imports. All 301 calls MUST become structured logger invocations.

## HIGH findings

### H-T1. Zero OpenTelemetry / distributed tracing

- `grep -rc 'from opentelemetry|import opentelemetry|otel|tracer\.start|start_as_current_span' packages/kailash-dataflow/src/dataflow/` → **0**.
- No spans, no trace exporters, no context propagation. For a package that the Terrene Foundation brief describes as "the database fabric the rest of the Kailash ecosystem depends on", the absence of distributed tracing is a production observability gap.

### H-T2. Missing `mode=real|cached|fake` field on every data call

`rules/observability.md` § 3: "Every data fetch MUST log the source mode in the log line itself. This is non-negotiable."

- `grep -rc 'mode=.real|mode=.cached|mode=.fake|source="postgres"' packages/kailash-dataflow/src/dataflow/` → **0**.

The Express cache (`features/express.py`), the fabric product cache (`fabric/pipeline.py`), the read-replica router, and the adapter layer all fetch data without a `mode` field. `grep mode=fake` — the grep that operators are supposed to run — returns nothing because the pattern was never emitted.

### H-T3. Unit tests performing real I/O (Tier 1 < 1s violation)

`rules/testing.md` § Tier 1: "<1s per test, no external dependencies."

`find tests/unit -name "*.py" | xargs grep -l "asyncpg\|psycopg2\|aiomysql\|requests\.get\|httpx\.get"` → **16 unit-tier files do real network/DB I/O**. A Tier 1 unit test that opens an asyncpg connection is not a unit test — it is a misfiled integration test whose timeout budget (Tier 1 <1s) cannot be met without flakiness.

### H-T4. 68 `random.*` calls with zero `random.seed()`

`rules/testing.md` § Rules: "Tests MUST be deterministic (no random data without seeds, no time-dependent assertions)."

- `grep -rc 'random\.\w+\(' packages/kailash-dataflow/tests/` → 68 across 18 files.
- `grep -rc 'random\.seed\(' packages/kailash-dataflow/tests/` → **0**.

Worst offender: `tests/conftest.py:248` — the `sqlite_file` entry in `DATABASE_CONFIGS` literally uses `int(time.time())` and `random.randint(1000, 9999)` to construct the file name, meaning the Tier-2 test DB path changes every run. This is useful for isolation but it also means: (a) stale files accumulate in `/tmp`, (b) any test that opens the same file across pytest workers hits different DBs, (c) the resulting database's state is non-reproducible.

### H-T5. `time.sleep(N)` waits in 59 test files

`grep -rc 'time\.sleep\(' packages/kailash-dataflow/tests/` → 59 files. `time.sleep` is the canonical flaky-test primitive. In Tier 2/3 where the test is supposed to validate real async behavior, `time.sleep()` either slows the suite (if N is large enough to win the race) or creates intermittent failures (if N is too small). The correct patterns are `asyncio.wait_for`, explicit event fences, or `asyncio.Event`. None of that discipline is visible.

### H-T6. Conftest silently swallows cleanup errors

`tests/conftest.py:52,101,134,143,407` — all `except Exception: pass`. Per `rules/zero-tolerance.md` Rule 3, bare `except: pass` is BLOCKED unless it is a hook or cleanup path. Cleanup paths are explicitly carved out in the rule, so this is borderline — but the cleanup fixture at line 130 is swallowing failures during setup (line 134), not teardown. Setup swallow is disguised as teardown; that is not an allowed exception.

### H-T7. State-persistence verification missing in e2e writes

`rules/testing.md` § State Persistence: "every write MUST be verified with a read-back".

- `grep -c 'db\.express\.create\|api\.create_\|\.create(' packages/kailash-dataflow/tests/e2e/**/*.py` → 14 in 1 file (`tests/e2e/web/test_web_migration_api_e2e.py`).

Only ONE e2e file runs direct writes with read-backs. The rest of `tests/e2e/` touches DataFlow through `standard_dataflow` fixtures and relies on the node return value being "successful", which `rules/testing.md` explicitly calls out as insufficient ("DataFlow `UpdateNode` silently ignores unknown parameter names. The API returns success but zero bytes are written."). So the documented state-persistence failure mode is precisely what the e2e suite cannot catch.

### H-T8. Docker service availability is not a hard gate

`tests/conftest.py:669-679` — the TDD infrastructure fixture checks if localhost:5434 is reachable with a 1-second `socket.create_connection` probe, and if it's not, it yields and returns. Tests that need PostgreSQL silently skip. `rules/testing.md` § Tier 2: real infrastructure required; the default should be **fail loudly** when Docker isn't running, not silently skip. A test suite that silently skips 90% of itself when Docker is down will pass any PR check and certify nothing.

### H-O1. Audit logging is incomplete despite a dedicated module

`src/dataflow/core/audit_events.py`, `src/dataflow/core/audit_integration.py`, and `src/dataflow/core/audit_trail_manager.py` all exist, but:

- `grep -rn 'audit_trail\|emit_audit\|AuditEvent' packages/kailash-dataflow/src/dataflow/tenancy/` → 0 (tenant create/update is not audit-logged).
- `grep -rn 'emit_audit\|AuditEvent' packages/kailash-dataflow/src/dataflow/migrations/auto_migration_system.py` → 0 (schema DDL is not audit-logged).
- `grep -rn 'emit_audit\|AuditEvent' packages/kailash-dataflow/src/dataflow/fabric/` → 0.

The audit infrastructure exists; almost nothing calls it. Privileged operations (tenant create, DDL application, config load, secret rotation) emit no audit event.

### H-O2. Log levels are not differentiated

`src/dataflow/core/engine.py` alone has 90 f-string log calls, essentially all at `info` or `debug`. There is no grep'able pattern for `logger.error|logger.exception` on failure paths. `rules/observability.md` § 3 requires ERROR for user-facing failure, WARN for fallback, INFO for state transition — because there is no audit, the level distinction is collapsed.

### H-O3. CHANGELOG does not reference issues

`packages/kailash-dataflow/CHANGELOG.md` 1.6.0 (2026-04-03) lists "Data Fabric Engine" with no issue reference. 1.5.1 references #212 (good). 1.5.0 references zero issues for 7 feature additions. 1.4.0, 1.1.0 mix referenced and unreferenced. `rules/deployment.md` § Before Any Release doesn't mandate issue references directly, but `rules/git.md` § PR Description says "always include a `## Related issues` section" — the CHANGELOG is downstream of PR descriptions, and the discipline collapsed.

### H-O4. Release test gate is not declared

`packages/kailash-dataflow/` has no `deploy/deployment-config.md`. `rules/deployment.md` § Release Config: "Every SDK MUST have `deploy/deployment-config.md`." The package ships to PyPI without a declared pre-release gate that says "run Tier 2 integration tests".

## MEDIUM findings

### M-T1. `pytest.ini` markers drift from docstring convention

`pytest.ini` declares `tier1`, `tier2`, `tier3`, `postgresql`, `sqlite`, `bug_reproduction`, `bug_investigation`, `regression`, `tdd`. `grep -c '@pytest.mark.tier1' packages/kailash-dataflow/tests/` returns 0. The tier markers are declared but not used.

### M-T2. `test_*.py` naming convention is inconsistent

`rules/testing.md` § Rules: "Naming: `test_[feature]_[scenario]_[expected_result].py`". Actual files:

- Compliant: `test_query_builder_postgresql.py`, `test_fk_safe_migration_integration.py`.
- Non-compliant: `test_v0106_features.py` (version-number in name), `test_dataflow_bug_011_012_integration.py` (issue numbers, not features), `test_redteam_r4_nonce_and_source_validation.py` (session artifact leaked into filename).

These are cosmetic but they indicate that test authorship is reactive (named after the session) rather than proactive (named after the scenario).

### M-T3. `integration_refactor_report.txt` and `refactor_integration_tests.py` sitting in `tests/`

`tests/integration_refactor_report.txt` and `tests/refactor_integration_tests.py` are not test files — they are working artifacts from a prior refactor that were committed to `tests/`. These pollute `pytest --collect-only` and cause discovery warnings.

### M-T4. `tests/manual/` exists and has no CI enforcement

`ls tests/` shows a `manual/` directory. Manual tests are by definition un-automatable; their presence in the test tree means some regression paths are gated on a human running them, which is a `rules/autonomous-execution.md` violation. Either automate or delete.

### M-T5. `conftest.py` `sys.path` manipulation

`tests/conftest.py:16-22` hand-inserts three paths (kailash-dataflow/src, packages/kailash-dataflow, project root, kailash-nexus/src) into `sys.path`. This tells me the package is not importable as a proper installable. `rules/python-environment.md` mandates `uv` and a `.venv`; hand-patching sys.path is a workaround for a broken `pyproject.toml`. Confirm that `pip install -e .` (or `uv pip install -e .`) makes the package importable without the sys.path hack.

### M-O1. `logging_config.py` exists but is not globally applied

`src/dataflow/core/logging_config.py` exists. `grep -rn "from dataflow.core.logging_config\|from \.logging_config" packages/kailash-dataflow/src/dataflow/` → one hit (its own import line). It's loaded lazily, which means most modules get Python's default logging configuration, which means NOTE the f-string logging pattern will render as plain text with no JSON wrapper.

### M-O2. Prometheus metrics outside `fabric/` do not exist

`grep -rn 'from prometheus_client\|Counter\|Gauge\|Histogram' packages/kailash-dataflow/src/dataflow/` → only `fabric/metrics.py`. Core engine, migrations, tenancy, cache — no metrics. The cache auditor's claim ("no Prometheus metric for the Express cache") is correct: `grep -rn "express_cache_hit\|express_cache_miss" packages/kailash-dataflow/src/` → 0.

### M-O3. Health check does not emit metrics

`src/dataflow/platform/health.py` — 5 f-string log calls. No prometheus metric for health status, latency, or failure count. Health is observable only via logs, and the logs are unstructured.

## LOW findings

### L-T1. `tests/CLAUDE.md` gives correct guidance but isn't enforced

`tests/CLAUDE.md` (the file loaded into this session) explicitly says "NO MOCKING in Integration/E2E Tests" and gives correct `IntegrationTestSuite` examples. The document is right; the tree ignores it. This is a governance LOW because fixing the tree fixes this LOW automatically.

### L-T2. `tests/e2e/test_documentation_examples.py` exists

Good practice — but `grep -n "md\|.rst\|CHANGELOG" packages/kailash-dataflow/tests/e2e/test_documentation_examples.py` shows it only checks one example file. If it's a test for CHANGELOG examples, it should enumerate all `CHANGELOG.md` code fences.

### L-T3. `CONTRIBUTING.md` and test discovery

Test contributors need a 3-sentence section on "which tier does my test belong in" with a decision tree. Absent today.

### L-O1. `__del__` warnings use `f""` style

Several async resource `__del__` methods log `ResourceWarning` with f-strings — same rule, but `__del__` is the cleanup carve-out, so this is LOW not HIGH.

## Modules with zero importing tests

Methodology: `grep -rln "from dataflow\.<module>\|import dataflow\.<module>" packages/kailash-dataflow/tests/`. A module is "zero-covered" if nothing in `tests/` imports it.

| Module                                                 | Importing tests | Verdict                                                      |
| ------------------------------------------------------ | --------------- | ------------------------------------------------------------ |
| `src/dataflow/cli.py` (root CLI)                       | 0               | Shadowed by `cli/` package; dead re-export?                  |
| `src/dataflow/core/database_registry.py`               | 0 direct        | Imported only transitively via `engine.py`                   |
| `src/dataflow/core/provenance.py`                      | 0               | No test exercises provenance                                 |
| `src/dataflow/core/tenant_context.py`                  | 0 direct        | Grep returns only source-internal imports                    |
| `src/dataflow/core/tenant_migration.py`                | 0               | No tenant migration tests                                    |
| `src/dataflow/core/tenant_security.py`                 | 0 direct        | Security-critical, zero coverage                             |
| `src/dataflow/configuration/progressive_disclosure.py` | 0               | Configuration DX feature with no tests                       |
| `src/dataflow/compatibility/legacy_support.py`         | 0               | Compatibility shim with no tests                             |
| `src/dataflow/compatibility/migration_path.py`         | 0               | Migration path advisor, no tests                             |
| `src/dataflow/classification/policy.py`                | 0 direct        | Classification policy engine, no direct test imports         |
| `src/dataflow/classification/types.py`                 | 0 direct        | Type definitions, used transitively only                     |
| `src/dataflow/platform/resilience.py`                  | 0               | Platform resilience module with no dedicated tests           |
| `src/dataflow/performance/sqlite_monitor.py`           | 0               | SQLite monitor with no coverage                              |
| `src/dataflow/optimization/query_plan_analyzer.py`     | 0               | Query optimizer, no tests (only workflow_analyzer has tests) |
| `src/dataflow/fabric/metrics.py`                       | 1 (own test)    | Covered only by its own unit test                            |
| `src/dataflow/fabric/leader.py`                        | 0               | Leader election critical, zero tests                         |
| `src/dataflow/fabric/runtime.py`                       | 0 direct        | Fabric runtime module                                        |
| `src/dataflow/migration/orchestration_engine.py`       | 0 direct        | Orchestration layer                                          |
| `src/dataflow/migration/type_converter.py`             | 0 direct        | Type conversion across dialects                              |
| `src/dataflow/migration/data_validation_engine.py`     | 0 direct        | Data validation                                              |
| `src/dataflow/trust/audit.py`                          | 0 direct        | Audit emission helper                                        |
| `src/dataflow/web/migration_api.py`                    | 0 direct        | Web migration API (only e2e test touches it)                 |
| `src/dataflow/validators/*`                            | 0 direct        | Validator modules lack direct imports in tests               |
| `src/dataflow/utils/connection_adapter.py`             | 0 direct        | Connection adapter utility                                   |
| `src/dataflow/gateway_integration.py`                  | 0               | Nexus gateway integration has no dedicated test              |

Note: "0 direct" means no test file imports the module explicitly. Some of these are exercised transitively (engine imports tenant_context, etc.), but transitive coverage is not the same as intentional testing. Every one of these modules should have at least one test file under `tests/unit/` or `tests/integration/` with a grep-visible import.

## Observability gap matrix

Per `rules/observability.md` § Mandatory Log Points, each boundary needs entry/exit/error/state/auth log lines. I audited the major subsystems:

| Subsystem                               | HTTP/RPC endpoint  | Integration point (outbound) | Data call (source + mode) | State transition   | Auth event     | Verdict |
| --------------------------------------- | ------------------ | ---------------------------- | ------------------------- | ------------------ | -------------- | ------- |
| `fabric/serving.py` (REST endpoints)    | partial (f-string) | no `source`/`mode`           | no                        | no                 | no             | FAIL    |
| `fabric/webhooks.py`                    | partial            | no                           | no                        | no                 | no             | FAIL    |
| `fabric/pipeline.py` (PipelineExecutor) | n/a                | no                           | no                        | partial            | no             | FAIL    |
| `fabric/leader.py`                      | n/a                | no                           | no                        | no (state change!) | no             | FAIL    |
| `core/engine.py`                        | n/a                | 90 f-string logs             | no `mode`                 | partial            | no             | FAIL    |
| `core/multi_tenancy.py`                 | n/a                | no                           | no                        | no                 | **no (auth!)** | FAIL    |
| `cache/redis_manager.py`                | n/a                | no `source=redis`            | no `mode=cached`          | no                 | no             | FAIL    |
| `cache/invalidation.py`                 | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `cache/async_redis_adapter.py`          | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `features/express.py`                   | n/a                | no                           | **no `mode=real/cached`** | no                 | no             | FAIL    |
| `adapters/postgresql.py`                | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `adapters/mysql.py`                     | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `adapters/sqlite.py`                    | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `migrations/auto_migration_system.py`   | n/a                | no                           | no                        | partial (DDL)      | no             | PARTIAL |
| `gateway_integration.py`                | n/a                | no                           | no                        | no                 | no             | FAIL    |
| `trust/audit.py`                        | n/a                | audit exists but unused      | no                        | no                 | no             | FAIL    |
| `web/migration_api.py`                  | **no entry/exit**  | no                           | no                        | no                 | no             | FAIL    |
| `platform/inspector.py`                 | n/a                | 73 print calls               | no                        | no                 | no             | FAIL    |
| `cli/*.py`                              | n/a                | print allowed                | n/a                       | n/a                | n/a            | OK      |

Every non-CLI subsystem is FAIL at multiple columns. The cells that say "partial" mean the function logs _something_ but not in the structured shape the rule requires.

## Metrics inventory

| Metric name                          | Type      | Labels               | Defined in              | Ever incremented outside fabric/metrics.py? | Registered at startup?         |
| ------------------------------------ | --------- | -------------------- | ----------------------- | ------------------------------------------- | ------------------------------ |
| `fabric_source_health`               | Gauge     | `source`             | `fabric/metrics.py:58`  | **No** (grep confirms)                      | No (module never instantiated) |
| `fabric_source_check_duration`       | Histogram | `source`             | `fabric/metrics.py:63`  | No                                          | No                             |
| `fabric_source_consecutive_failures` | Gauge     | `source`             | `fabric/metrics.py:68`  | No                                          | No                             |
| `fabric_pipeline_duration`           | Histogram | `product`            | `fabric/metrics.py:75`  | No                                          | No                             |
| `fabric_pipeline_runs_total`         | Counter   | `product`, `status`  | `fabric/metrics.py:80`  | No                                          | No                             |
| `fabric_cache_hit_total`             | Counter   | `product`            | `fabric/metrics.py:87`  | No                                          | No                             |
| `fabric_cache_miss_total`            | Counter   | `product`            | `fabric/metrics.py:92`  | No                                          | No                             |
| `fabric_product_age_seconds`         | Gauge     | `product`            | `fabric/metrics.py:97`  | No                                          | No                             |
| `fabric_request_duration`            | Histogram | `endpoint`           | `fabric/metrics.py:104` | No                                          | No                             |
| `fabric_request_total`               | Counter   | `endpoint`, `status` | `fabric/metrics.py:109` | No                                          | No                             |

Missing metrics per other audits:

| Missing metric                               | Expected location                     | Required by                      |
| -------------------------------------------- | ------------------------------------- | -------------------------------- |
| `express_cache_hit_total` (with `tenant_id`) | `features/express.py`                 | Cache auditor, multi-tenant rule |
| `express_cache_miss_total`                   | `features/express.py`                 | Cache auditor                    |
| `express_cache_error_total`                  | `features/express.py`                 | Cache auditor                    |
| `dataflow_connection_pool_size`              | `core/pool_monitor.py`                | `rules/dataflow-pool.md` Rule 2  |
| `dataflow_connection_pool_active`            | `core/pool_monitor.py`                | Pool exhaustion postmortem       |
| `dataflow_connection_pool_waiters`           | `core/pool_monitor.py`                | Pool exhaustion postmortem       |
| `dataflow_query_duration_seconds`            | `core/engine.py`                      | Slow query detection             |
| `dataflow_migration_duration_seconds`        | `migrations/auto_migration_system.py` | Migration SLO                    |
| `dataflow_tenant_isolation_violations`       | `tenancy/interceptor.py`              | Tenant leak detection            |
| `dataflow_audit_events_total`                | `trust/audit.py`                      | Audit completeness               |

### Cardinality concerns

All current fabric metrics label by `product`, `source`, or `endpoint`. These are bounded sets — safe. The _missing_ express-cache metrics MUST NOT label by `tenant_id` directly (unbounded), but MAY label by `tenant_tier` or `tenant_segment` if the latter is a bounded enum. The plan-master-fix-plan should call this out explicitly so the implementation doesn't add `tenant_id=...` as a Prometheus label footgun.

## Rule gaps

Rules that the package violates today and the concrete gap:

1. **`rules/testing.md` § Tier 2 (no mocking)** — 30 files, 118 occurrences. Enforce via a pytest collection hook that fails if `unittest.mock` is imported in any file under `tests/integration/`, `tests/e2e/`, `tests/fabric/`, `tests/tier3_e2e/`.
2. **`rules/testing.md` § State Persistence** — e2e writes missing read-backs. Introduce a `verify_persisted()` helper that every e2e write MUST call, with a lint rule rejecting `.create(` without a subsequent `.read(` in the same test function.
3. **`rules/testing.md` § Audit Mode** — `.test-results` discipline. The audit rule exists; it is not enforced. The `redteam` command must re-derive `pytest --collect-only` every round.
4. **`rules/testing.md` § Regression** — `tests/regression/` is effectively empty. Every closed bug issue from 2025-10-01 forward must have a `tests/regression/test_issue_<N>_<slug>.py` file. A pre-commit hook could enforce "new commit with `fix(dataflow): ` prefix requires a regression test" at push time.
5. **`rules/observability.md` § MUST 1 (framework logger, no print)** — 301 print calls. A `ruff` rule (`T201` and `T203`) can enforce this globally in CI.
6. **`rules/observability.md` § MUST NOT (no f-string logs)** — 969 occurrences. A `ruff` rule `G004` enforces this. Turn it on.
7. **`rules/observability.md` § 3 (data calls log mode)** — zero occurrences. Add a linter / grep check in CI: every file that imports `features/express.py` or `cache/redis_manager.py` must have at least one `mode=` field in a log call.
8. **`rules/observability.md` § 2 (correlation IDs)** — zero binds. Introduce a mandatory `context_var` module (`core/observability_context.py`) that binds `request_id` at every entry point and audits against bind-count on every gate.
9. **`rules/dataflow-pool.md` § 2 (startup validation)** — pool validation exists but emits no metric. Add `dataflow_pool_validation_result{result="ok|warning|error"}` on startup.
10. **`rules/zero-tolerance.md` Rule 1 (log triage)** — `pytest.ini` globally disables warnings. Remove `--disable-warnings` and `-p no:warnings`, fix the fallout, gate on clean.
11. **`rules/zero-tolerance.md` Rule 2 (no TODO markers)** — `src/dataflow/fabric/metrics.py:4` literally has `TODO-21`. Remove.
12. **`rules/deployment.md` § Release Config** — no `deploy/deployment-config.md` for dataflow. Create one.
13. **`rules/cross-sdk-inspection.md`** — every finding above should be cross-filed against kailash-rs.
14. **`rules/autonomous-execution.md`** — `tests/manual/` directory exists; incompatible with autonomous execution model. Delete or automate.

## Top-level conclusion

The dataflow package test tree passes the "do lots of tests exist" eyeball test and fails almost every qualitative rule in `rules/testing.md` and `rules/observability.md`. The mocks in Tier 2, the Redis-never-tested fabric, the dead `FabricMetrics`, the dead `no_mocking_policy` fixture, the 969 f-string logs, the zero correlation IDs, and the globally disabled pytest warnings collectively mean that the package has neither test-derived confidence in its own behavior nor runtime observability into its own failures. This is the testing-and-observability counterpart to the other subsystem audits' stubs and docstring lies: the same pattern of "infrastructure that was built to look like infrastructure". Every CRITICAL and HIGH finding above is a BLOCKING item for the "dataflow MUST be perfect" mandate. None are optional, none are deferrable.
