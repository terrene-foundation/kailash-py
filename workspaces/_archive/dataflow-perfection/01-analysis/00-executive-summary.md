# DataFlow Perfection — Consolidated Executive Summary

**Date**: 2026-04-08
**Mandate**: `workspaces/dataflow-perfection/briefs/01-mandate.md`
**Scope**: Entire `packages/kailash-dataflow/` package — 28 subsystems, ~280 source files, ~486 test files
**Auditors**: 8 specialists in parallel — core+config, adapters, fabric (second pass), cache, tenancy+security, nodes+query+migrations, testing+observability, platform+web+orphan subsystems
**Verdict**: **FOUNDATIONALLY BROKEN.** DataFlow is not a package with bugs. It is a package whose advertised features are simulated — data integrity, encryption, multi-tenant isolation, transactions, connection health, migrations, cross-worker coordination, observability, and the CLI entry point are stubs that return canned responses while presenting as real.

## Severity roll-up

| Subsystem                  | CRITICAL | HIGH     | MEDIUM   | LOW     | Orphan LOC (delete)                    |
| -------------------------- | -------- | -------- | -------- | ------- | -------------------------------------- |
| Core + config              | 7        | 18       | 22       | 12      | —                                      |
| Adapters + SQL dialect     | 5        | 12       | ~8       | ~6      | —                                      |
| Fabric (second pass)       | 4 new    | 12 new   | 12 new   | 7 new   | ~6 orphan classes                      |
| Cache (Express + query)    | 2        | 5        | ~8       | ~4      | 886 (dead parallel init path)          |
| Tenancy + security         | 9        | 13       | 14       | 9       | —                                      |
| Nodes + query + migrations | 11       | 17       | ~10      | ~5      | 223 (dynamic_update.py) + 4 bulk files |
| Testing + observability    | 5        | ~10      | ~15      | ~10     | —                                      |
| Platform + web + orphans   | 3        | ~15      | ~20      | ~15     | ~17,300                                |
| **TOTAL (approximate)**    | **~46**  | **~102** | **~109** | **~68** | **~18,400+ LOC**                       |

## The headline: DataFlow is a façade

Eight independent auditors converged on the same pattern. **DataFlow ships a series of "manager" classes that look like production infrastructure but are Python dicts returning canned responses.** The user calls `db.transactions`, `db.connection`, `db.tenants`, `db.cache_integration`, etc. and gets an object whose methods do nothing. The docstring says "transaction safety"; the method flips an in-memory dict status and yields. The docstring says "enterprise encryption"; the method returns `f"encrypted_{key}_{data}"`. The docstring says "Redis-backed production cache"; the method writes to an OrderedDict.

Every one of these façade managers is:

1. **Instantiated in `DataFlow.__init__`** (core/engine.py line range 440-530)
2. **Exposed as a public attribute** (`db.transactions`, `db.connection`, `db.tenants`, `db.cache_integration`)
3. **Documented in docstrings as production-grade**
4. **Backed by a Python dict or trivial function**
5. **Tested against itself in isolation** — the tests assert "manager.status == 'committed'" without verifying any database side-effect
6. **Consumed by upstream code that trusts the contract** (e.g., `model_registry.py` wraps every registration in the fake TransactionManager and calls it "transactional")

This pattern is the single biggest institutional-knowledge failure in the Kailash ecosystem. Every one of these façades violates `zero-tolerance.md` Rule 2 ("No stubs") AND Rule 6 ("Implement fully") AND the communication rule that says fix don't document.

## Most damning findings (cross-subsystem)

### 1. `TransactionManager` is a Python dict with `status="committed"` [CRITICAL — data integrity]

- **Location**: `features/transactions.py:30-58`
- **Wiring**: `core/engine.py:453` instantiates on every DataFlow init; `engine.py:2825` exposes as `db.transactions`
- **Behavior**: Every method yields an in-memory dict. Zero BEGIN, zero COMMIT, zero ROLLBACK, zero isolation level is ever sent to the database.
- **Consumer lie**: `model_registry.py:101` wraps model registration in this fake and calls it "transaction-safe". `rules/testing.md` state-persistence verification was MEANT to catch this class of bug.
- **Blast radius**: every DataFlow user who relied on transactional model registration is running on fiction. Any partial failure mid-registration leaves inconsistent state with no rollback.

### 2. `ConnectionManager` (db.connection) — every method returns canned responses [CRITICAL — observability fiction]

- **Location**: `utils/connection.py::ConnectionManager`, wired at `core/engine.py:454`
- **Behavior**: `initialize_pool()`, `health_check()`, `test_connection()`, `close_all_connections()` all return hardcoded dicts with `# In real implementation, would...` comments. `db.connection.health_check()` ALWAYS reports `database_reachable=True` regardless of state.
- **Consequence**: operators who built monitoring dashboards against `db.connection.health_check()` are watching a constant-true signal while their database is on fire.

### 3. `MultiTenantManager` + `encrypt_tenant_data` are fakes [CRITICAL — security theater]

- **`features/multi_tenant.py`**: Python dict with hardcoded `"created_at": "2024-01-01T00:00:00Z"`. Wired at `engine.py:531` for every `multi_tenant=True` deployment.
- **`core/multi_tenancy.py:925-949`**: `encrypt_tenant_data` is literal string concatenation `f"encrypted_{key}_{data}"`; `_get_tenant_encryption_key` returns the constant string `"tenant_specific_key"`.
- **Consequence**: any user who trusted "enterprise encryption" is storing plaintext with a fixed prefix. Any data exfiltration by a reader with DB access is direct plaintext recovery.
- **Aggravator**: `except: pass` inside the fake encryption function (`multi_tenancy.py:930`) per `rules/zero-tolerance.md` Rule 3.

### 4. 13 SQL injection sites in the multi-tenant isolation layer [CRITICAL — direct RCE]

- **Location**: `core/multi_tenancy.py:415, 420, 424, 427, 429, 452, 456, 477, 482, 490, 494` (RLS policies) + `:334, :367` (schema DDL)
- **Pattern**: `tenant_id` f-string-interpolated into SQL literals and DDL. `TenantConfig.__post_init__` only rejects spaces in `tenant_id`.
- **PoCs**:
  - `tenant_id = "a' OR '1'='1"` → bypass row-level isolation, read any tenant's data
  - `tenant_id = 'x"; DROP TABLE users; --'` → arbitrary DDL execution
  - `tenant_id = "'; INSERT INTO users VALUES (...); --"` → arbitrary DML
- **Consequence**: **the layer designed to enforce isolation is the attack surface.** A hostile tenant provisioning another tenant's ID achieves cross-tenant compromise AND arbitrary code execution on the database.

### 5. `eval()` on a database column in semantic search [CRITICAL — RCE via vector column]

- **Location**: `semantic/search.py:134` — `eval(row["embedding"])` on a fetched row
- **Attack**: any actor who can write to a vector column gets Python RCE on the worker the next time `find_similar_examples` runs. In a multi-tenant setup, tenant A writing to its own vectors achieves RCE during tenant B's query execution.
- **Surrounding context**: `semantic/` is 1,239 LOC duplicating Kaizen's `SemanticMemory`. The entire directory is a candidate for deletion, BUT the `eval()` site is reachable today if the subsystem is used anywhere.

### 6. `exec()` on workflow parameter in `DynamicUpdateNode` [CRITICAL — generic RCE]

- **Location**: `nodes/dynamic_update.py:172, 182` — `exec(self.filter_code, {}, namespace)` and `exec(self.prepare_code, ...)`
- **Reach**: any caller that can build a workflow (e.g., a Nexus HTTP channel) has full RCE. `workflow.add_node("DynamicUpdateNode", ...)` is the attack vector.
- **Consumers**: grep across the repo returns zero legitimate consumers outside the file itself. It is a covert `PythonCodeNode` reimplementation shipped as an attack surface.
- **Fix**: delete the entire 223-line file.

### 7. SQL injection in generated `UpdateNode` via `fields` dict keys [CRITICAL]

- **Location**: `core/nodes.py:2192, 2195, 2235, 2248`
- **Pattern**: `field_names = list(updates.keys())` with zero whitelist against `self.model_fields`. Keys interpolated into the SET clause.
- **PoC**: `fields={"password_hash = 'pwned', x": 1}` — the caller controls the SQL.
- **Bonus bug**: this is ALSO the silent-parameter-drop pattern `rules/testing.md` warns about — unknown keys pass through validation.

### 8. SQL injection via f-string `table_name` across 25 DDL sites [CRITICAL]

- **Locations**: `adapters/postgresql.py:279,294,363`, `adapters/mysql.py:282,298,376,386`, `adapters/sqlite.py:519,539,673`, `adapters/sqlite_enterprise.py:864,893,973,1003,1013,1023,1074,1079,1139`
- **Pattern**: `f"CREATE TABLE {table_name} ..."` with no identifier validation or quoting.
- **Defense in depth**: `adapters/sql_dialects.py` already has `quote_identifier()`. Zero adapters import it.
- **Aggravator**: `database/query_builder.py:311-313` inlines `LIMIT` and `OFFSET` as raw string literals — no parameter binding. `validate_queries=False` hardcoded in 40+ DML call sites, disabling the core SDK's query validation layer PACKAGE-WIDE.

### 9. Express cache leaks across tenants RIGHT NOW [CRITICAL — active data leak]

- **Location**: `cache/key_generator.py:97-135` → `generate_express_key("User", "list", {...})` produces identical keys for tenant A and tenant B
- **Wiring**: `features/express.py:140, 954-996` — Redis adapter is WIRED via `CacheBackend.auto_detect(redis_url=...)`. Unlike fabric (where Redis was never wired), the Express cache Redis path is live in production.
- **Scope**: every `db.express.list`, `db.express.read`, `db.express.count` with `multi_tenant=True` is actively leaking cross-tenant.
- **Aggravator #1**: `_invalidate_model_cache` at `features/express.py:991-996` has three parallel implementations in three files, none tenant-scoped. `AsyncRedisCacheAdapter.invalidate_model` uses `dataflow:{model}:*` which DOES NOT match real keys (which are `dataflow:v1:{model}:...`) — the method matches nothing. Cache invalidation is broken AND leaks across tenants.
- **Aggravator #2**: `InMemoryCache.invalidate_model` uses substring `in` match, so invalidating `User` also nukes `UserAudit`.
- **Cross-SDK**: Rust `crates/kailash-dataflow/src/query_cache.rs` has the same bug (0 tenant mentions in 953 LOC).

### 10. #352 (model_registry sync-in-async) is worse than the issue described [CRITICAL]

- **Not one site — 13 sites** in `core/model_registry.py` call sync `self.runtime.execute()`. When `DataFlow` is constructed under FastAPI lifespan, `engine.py:441-444` assigns `AsyncLocalRuntime()`, which at `async_local.py:599-603` explicitly raises `RuntimeError` on any sync `.execute()` from an async context. The existing "detect async context" branch does NOT fix the 13 sites — it creates the async-aware runtime and then lets 13 calls hit the guard.
- **Fix scope**: all 13 sites must be converted, or `_create_model_registry_table` becomes async and the caller chain cascades.

### 11. #354 (fabric cache Redis stub) + the ENTIRE fabric endpoint stack is unwired [CRITICAL]

- **First pass finding**: `PipelineExecutor(redis_url=...)` accepts and silently discards the URL. Eight stubs/lies in one file.
- **Second pass finding (NEW)**: `FabricRuntime.start()` instantiates `FabricServingLayer`, `WebhookReceiver`, and `FabricHealthManager`, but **no code in the dataflow package ever registers the routes returned by `serving.get_routes()`, `health.get_health_handler()`, `sse.get_sse_handler()`, `webhooks.handle_webhook`, or `mcp_integration` with any HTTP server.** The `nexus: Optional[Any]` parameter at `runtime.py:74` is accepted, stored, and never read.
- **Scope of orphan code in fabric alone**: 6 endpoint classes collectively dead. 512 LOC `FabricServingLayer` + 236 LOC `FabricHealthManager` + 147 LOC `FabricSSE` + 300 LOC `WebhookReceiver` + 194 LOC `FabricMCPIntegration` + 166 LOC `FabricMetrics` = 1,555 LOC of dead endpoint code.
- **Consequence**: a user who calls `db.start()` then hits `GET /fabric/dashboard` gets a 404. All documented fabric endpoints are 404.
- **Additional**: `WebhookReceiver` hardcodes a bespoke `x-webhook-signature` header and supports NONE of GitHub/GitLab/Stripe/Slack signature formats. Even after wiring, every real webhook producer is rejected.
- **Additional**: `FabricScheduler` (257 LOC with cron + croniter + supervised tasks + clock-drift cap) is never instantiated. `ProductRegistration.schedule` is validated at registration then silently ignored. Every `@db.product("hourly", schedule="0 * * * *")` is a broken promise.
- **Additional**: `tenant_extractor` is stored at `runtime.py:85` but never invoked. Every `PipelineContext(tenant_id=None)` in fabric.

### 12. Two divergent SQLite adapters, the less-complete one is default [CRITICAL]

- **Location**: `factory.py:37` makes `SQLiteEnterpriseAdapter` the default. That class duplicates every dataclass from `sqlite.py`, is MISSING `execute_insert`, `execute_bulk_insert`, `get_server_version`, `get_database_size`, `get_connection_parameters`, and its `disconnect()` has no leaked-transaction check (unlike `sqlite.py:261-271`).
- **Both adapters bypass the pool** in `_test_connection`, `_perform_wal_checkpoint`, `_initialize_performance_monitoring`, and `_collect_performance_metrics` with bare `aiosqlite.connect()` — direct `rules/patterns.md` § SQLite Connection Management violation.
- **Fabricated telemetry**: `sqlite.py:913-925` returns `cache_hit_ratio = 0.95 if self._query_count > 10 else 0.0` and `checkpoint_frequency=1.0` — literal zero-tolerance Rule 2 simulated data in production metrics path.

### 13. Three parallel dialect systems, none providing the mandated portability helpers [HIGH]

- **Location 1**: `adapters/sql_dialects.py` defines `SQLDialect`/`PostgreSQLDialect`/`MySQLDialect`/`SQLiteDialect` with one method set
- **Location 2**: `sql/dialects.py` defines the same class NAMES with completely different methods (`build_upsert_query`)
- **Location 3**: Each adapter implements its own `format_query`/`get_dialect`/`supports_feature`/DDL locally
- **Consequence**: three parallel implementations + one missing contract = guaranteed divergence. None of them expose `blob_type()`, `current_timestamp()`, `quote_identifier()`, or `limit_clause()` helpers as mandated by `rules/infrastructure-sql.md`.
- **Fix**: pick one, delete the other two, migrate every adapter to the canonical helper layer.

### 14. `execute_transaction` is not a transaction on PostgreSQL [CRITICAL — data integrity]

- **Location**: `adapters/postgresql.py:157-176`
- **Pattern**: loops `await self.execute_query(query, params)`; each `execute_query` acquires a NEW pool connection — no shared connection, no BEGIN, no COMMIT, no atomicity.
- **Failure mode**: failure on query 3 of 5 leaves 1-2 queries committed. The docstring promises "multiple queries in a transaction".
- **Aggravator**: MySQL and SQLite equivalents actually implement real transactions. Cross-dialect code silently gets atomicity on two dialects and loses it on the third.

### 15. Auto-migrate runs DDL on first boot without confirmation AND has been emitting broken SQL [CRITICAL]

- **Location**: `core/engine.py:5191-5196` calls `auto_migrate(interactive=False, auto_confirm=True)` on every SQLite model registration
- **Aggravator**: swallows failures at 5209-5212 with comment "Don't fail model registration"
- **Historical evidence**: `migrations/performance_data/migration_history.jsonl` contains 44 historical runs, **every single one showing `success: false` with "syntax error at or near WHERE"** — runtime telemetry committed to source showing the auto-migrate generator itself has been emitting broken SQL.
- **Violation**: `rules/schema-migration.md` — DDL in application code without review, no downgrade path, no numbered migration files, non-reversible.

### 16. Dead parallel subsystems: 4 duplicate module trees [HIGH]

- **`migration/` (singular)** is dead code with zero importers — delete.
- **`validators/` (plural)** is dead code — delete.
- **`optimization/`** only consumed by `testing/production_deployment_tester.py` — delete or wire.
- **`classification/`** documented and declared, NEVER called from any CRUD node — the `@classify("email", PII, ..., REDACT)` contract promises redaction that never happens. Either wire into the query path or delete.

### 17. `dataflow/trust/` is 2,407 LOC of pure orphan [HIGH]

- **Location**: `trust/__init__.py` advertises `TrustAwareQueryExecutor`, `ConstraintEnvelopeWrapper`, `DataFlowAuditStore`, `SignedAuditRecord`, `TenantTrustManager`, `CrossTenantDelegation`
- **Referrers**: zero production importers anywhere in the package. Only test files reference them.
- **Docstring lie**: "trust-aware query execution for DataFlow" — nothing in the query path, audit path, or tenant path calls them.
- **Fix**: wire into `core/audit_integration.py` + `core/nodes.py` query interception OR delete in full.

### 18. `dataflow/cli/main.py` prints "coming soon" for every command [HIGH — user-facing silent-success lie]

- **Location**: `pyproject.toml:88` binds `dataflow = dataflow.cli:main`. `init`, `schema`, `migrate create/apply/rollback/status` all print `"coming soon..."` or `"Placeholder for actual implementation"` while exiting 0.
- **Aggravator**: the `init` handler has the comment `# Mock the DataFlow instantiation for testing` in production code.
- **User experience**: `dataflow init` → prints "coming soon", exit 0. The CLI is a lie with zero functionality.

### 19. Structured logging is 99.2% broken, zero correlation IDs, 301 `print()` calls in production [HIGH]

- **969 f-string `logger.*(f"...")` calls** across 99 files vs **8 structured-field calls** across 4 files. Direct `rules/observability.md` MUST Rule § Structured logging violation at scale.
- **Zero `logger.bind` / `structlog.bind`** / correlation-ID propagation anywhere in application code
- **Zero `mode=real|cached|fake` field** anywhere
- **Zero OpenTelemetry spans**
- **301 `print()` calls in production source** across 37 files — `rules/observability.md` § Rule 1 ("Never `print`") violated 301 times
- **`pytest.ini:34`** ships `--disable-warnings -p no:warnings`, structurally disabling the log-triage gate mandated by `rules/zero-tolerance.md` Rule 1 and `rules/observability.md` MUST 5. Warnings are suppressed package-wide so the log-triage protocol literally cannot function.
- **`suppress_warnings.py::suppress_core_sdk_warnings()`** runs automatically at `dataflow/__init__.py:92` and permanently downgrades `kailash.nodes.base` and `kailash.resources.registry` from WARNING to ERROR for every process that imports DataFlow. Direct `observability.md` violation ("No silent log-level downgrades"). The root cause is DataFlow re-registering nodes during `@db.model`; per `zero-tolerance.md` Rule 4, the fix belongs in the core SDK node registry, not a blanket logger mute.

### 20. 118 mock violations in Tier 2 across 30 integration test files [CRITICAL — test-tier compliance]

- **Rule**: `rules/testing.md` forbids `unittest.mock` in `tests/integration/`, `tests/e2e/`, `tests/fabric/`
- **Violations**: 118 across 30 files. Worst offenders: `test_cache_invalidation.py` (28), `test_column_removal_integration.py` (19), `test_workflow_context_integration.py` (14)
- **The enforcer itself is dead**: the `no_mocking_policy` fixture at `tests/conftest.py:455` is referenced NOWHERE. The policy enforcement mechanism is dead policy code.

### 21. Every CRITICAL security finding has zero regression coverage [CRITICAL — test discipline collapse]

- SQL injection in `multi_tenancy.py` — zero regression tests
- `eval()` at `semantic/search.py:134` — zero regression tests
- `exec()` at `nodes/dynamic_update.py:172,182` — zero regression tests
- Fake `encrypt_tenant_data` — zero regression tests
- Express cache tenant leak — zero regression tests
- Fabric cache multi-tenant — zero regression tests
- `tests/regression/` contains ONE test file total

### 22. `FabricMetrics` is dead; no metric anywhere is incremented in production [HIGH]

- **Location**: `src/dataflow/fabric/metrics.py` declares 10 Prometheus metrics
- **Instantiations**: exactly once — in its own unit test
- **Consequence**: operators have no visibility into fabric pipeline execution, cache hits, prewarm duration, leader state, or anything else.
- **Module header**: contains literal `TODO-21` — another tracked TODO never delivered.

### 23. Hand-rolled Redis URL parser crashes on realistic URLs [HIGH]

- **Location**: `cache/auto_detection.py:68-78, 156-161`
- **Pattern**: `redis_url.replace("redis://", "").split("/").split(":")` — crashes on `redis://user:pass@host/0`, silently ignores `rediss://` TLS, `unix://` sockets, and query params.
- **Aggravator**: `circuit_breaker_enabled=False` default means a Redis outage makes every request pay the full 5s socket timeout. The unbounded `ThreadPoolExecutor` (up to ~32 workers per instance) saturates within seconds under load. `failover_mode="degraded"` is declared but has zero consumers — another stub.
- **Aggravator**: unredacted Redis URL logging at `cache/auto_detection.py:146, 152, 220` (passwords in logs).

### 24. Debug agents violate LLM-first rules + hardcode model name [HIGH]

- **Location**: `debug/` — `ErrorCategorizer` uses regex, `PatternRecognitionEngine` uses thresholds, neither consults an LLM
- **Violation**: `rules/agent-reasoning.md` — "LLM does ALL reasoning. Tools are dumb data endpoints." Regex-based categorization is deterministic logic that `rules/agent-reasoning.md` BLOCKS.
- **Aggravator**: `DebugAgent` hardcodes `model="gpt-4o-mini"` — `rules/env-models.md` violation.

### 25. `compatibility/` uses `unittest.mock.Mock` IN PRODUCTION [MEDIUM — code hygiene collapse]

- **Location**: `compatibility/legacy_support.py:75` imports and instantiates `Mock()` from production source
- **Rule violation**: test-only symbols have zero place in production code

## Cross-subsystem patterns

### Pattern A: Façade-manager anti-pattern

The dominant bug shape. Seven different "manager" classes are all Python dicts pretending to be infrastructure: TransactionManager, ConnectionManager, MultiTenantManager, TenantSecurityManager (with fake encryption), CacheIntegration (dead path), FabricScheduler (registered but not wired), FabricServingLayer (orphan). A SPEC for "managers must be backed by integration tests that verify the underlying system" would have caught every one of these.

### Pattern B: Stored-but-never-read parameters

`self._redis_url = redis_url`, `self._dev_mode = dev_mode`, `self._queue = ...`, `self._tenant_extractor = ...`, `nexus: Optional[Any]` on `FabricRuntime`, and dozens more. Every one of these is `rules/dataflow-pool.md` Rule 3 ("No Deceptive Configuration") at scale. The rule exists; the enforcement does not.

### Pattern C: Advertised endpoints that 404

Fabric has 6 endpoint implementations totaling 1,555 LOC none of which are registered with any HTTP server. CLI has 5 commands all of which print "coming soon". Every documented surface either returns 404 or prints a promise.

### Pattern D: Cross-tenant key collision across every cache layer

Express cache (`cache/key_generator.py`), fabric cache (`fabric/pipeline.py:119`), query cache (Rust mirror), classification cache — not a single one partitions by tenant. The security auditor confirmed this is an ACTIVE data-leak primitive in Express today (Redis wired), not just a latent risk.

### Pattern E: Three parallel implementations of everything

Three dialect systems (`adapters/sql_dialects.py`, `sql/dialects.py`, inline in adapters). Three cache invalidation implementations (`features/express.py`, `cache/memory_cache.py`, `cache/async_redis_adapter.py`). Two SQLite adapters (the default is the less-complete one). Two migration directories (`migrations/`, `migration/`). Two validation directories (`validation/`, `validators/`). Framework-first violated inside the framework package itself.

### Pattern F: Simulated telemetry in production code paths

`cache_hit_ratio = 0.95 if self._query_count > 10 else 0.0` is production code. `db.connection.health_check()` always returns `database_reachable=True`. The "encryption" is `f"encrypted_{key}_{data}"`. Operators running monitoring against DataFlow's own health signals are watching fiction.

### Pattern G: The observability gate is structurally disabled

`pytest.ini:34` disables warnings. `suppress_warnings.py` runs at import time and downgrades core SDK log levels. 969 f-string log calls. Zero correlation IDs. 301 `print()` calls. The log-triage gate mandated by `rules/zero-tolerance.md` Rule 1 and `rules/observability.md` MUST 5 literally cannot function.

## Cross-SDK (kailash-rs) parallels

- **Fabric Redis cache**: Rust has the same absence (no `redis_url` field at all in `executor.rs`). File cross-SDK issue after Python fix.
- **Express query cache tenant leak**: Rust `query_cache.rs` has zero tenant mentions in 953 LOC. Same bug.
- **Multi-tenant RLS SQL injection**: verify whether the Rust `dataflow/src/multi_tenancy.rs` (if it exists) has the same f-string interpolation.
- **Transaction manager stub**: verify Rust `transactions.rs` is a real transaction wrapper.

## Institutional-knowledge fault lines

### Context amnesia (primary)

Every manager stub has a docstring promising production behavior and an implementation delivering a dict. The authors knew they were stubbing and shipped anyway. `classification/` has decorators that promise redaction that never happens. `trust/` has 2,407 LOC nobody imports. The `TODO-11`, `TODO-21`, `TODO-38`, `TODO-155` markers are evidence that work was planned, scoped, partially built, and left to "later" that never arrived.

### Security blindness (critical severity amplification)

Nine CRITICAL security findings — SQL injection, eval, exec, fake encryption, cross-tenant leak — in a package whose docstrings advertise "enterprise multi-tenant security controls". Reviewers approved PRs with `f"encrypted_{key}_{data}"` as the literal body of an encryption function. Reviewers approved PRs calling `eval(row["embedding"])`. Reviewers approved PRs with `exec(self.filter_code, ...)` exposed as a workflow node. There is no review gate for CRITICAL-class patterns.

### Convention drift (enabling mechanism)

`rules/dataflow-pool.md` Rule 3 ("No Deceptive Configuration") exists and is exactly the right guard; nobody enforced it. `rules/zero-tolerance.md` Rule 2 ("No Stubs") exists; the façade managers are the exact pattern forbidden. `rules/observability.md` § Data Calls mandates `source=`/`mode=` fields on every data-call log; 969 f-string violations say otherwise. `rules/testing.md` forbids mocking in Tier 2/3; 118 violations across 30 files. Every rule that should have caught the bugs exists. None of them were applied.

## Severity of the package state

**DataFlow cannot ship as-is.** With the active Express cross-tenant data leak, the 13 SQL injection sites in the isolation layer, the eval/exec RCE sites, the fake encryption, and the façade managers presenting as production infrastructure, any user running `DataFlow(multi_tenant=True, redis_url=...)` in production is exposed to:

1. Data exfiltration across tenants through the Express cache (active, today)
2. Arbitrary database compromise through tenant_id injection
3. Remote code execution through vector-column writes
4. Remote code execution through workflow construction
5. Plaintext storage of "encrypted" tenant data
6. False-positive health signals hiding real database failures
7. Silent loss of transactional guarantees
8. Silent auto-migration failures logging success
9. Cross-tenant cache invalidation cascade

This is not a fixable bug list. **This is a package that needs a sprint of foundational repair before it can honestly claim any of its advertised features.**

## What the master fix plan must accomplish

1. **Delete ~18,400+ LOC of orphan, duplicate, and stub code** — most of `web/`, `semantic/`, `compatibility/`, `performance/`, `platform/` (except Inspector + ErrorEnhancer), `migration/`, `validators/`, `trust/` (or wire it), `nodes/dynamic_update.py`, the 4 bulk files, the dead parallel init path in `cache/`, the dead SQLiteEnterpriseAdapter
2. **Implement the 7 façade managers for real** — TransactionManager, ConnectionManager, MultiTenantManager, TenantSecurityManager (real encryption or delete the promise), CacheIntegration, FabricScheduler wiring, FabricServingLayer registration
3. **Fix all 9 CRITICAL security findings** — SQL injection at 13 sites, eval, exec, fake encryption, cache tenant leaks in Express AND fabric, identifier quoting across 25 DDL sites
4. **Wire the fabric endpoint stack into Nexus** — 6 endpoint classes totaling 1,555 LOC must actually serve traffic
5. **Migrate all 13 model_registry sync-in-async sites** (#352) — plus every similar pattern elsewhere
6. **Fix the fabric Redis cache** (#354) per the existing workspace plan — now with the additional context that Express cache has the same bug at a larger blast radius
7. **Fix the adapters sslmode + application_name + command_timeout bugs** (#353 expanded)
8. **Consolidate the three dialect systems into one** and migrate every adapter to it
9. **Replace 118 mock violations in Tier 2/3** with real-infrastructure tests
10. **Add regression tests for every CRITICAL security finding**
11. **Rewrite 969 f-string logger calls to structured form**
12. **Delete 301 `print()` calls** in production source
13. **Implement correlation ID propagation** across every async boundary
14. **Implement real Prometheus metrics** and wire them into the request path
15. **Remove `suppress_warnings.py`** and fix the underlying core SDK node re-registration warning at the source
16. **Remove `pytest.ini --disable-warnings`** and resolve the warnings it was hiding
17. **Implement tenant-aware cache keys** in every cache layer with blocking failure on `multi_tenant=True` without `tenant_id`
18. **Correct every docstring that lies** — atomic with the code changes
19. **Extend `rules/` to catch the next instance** — façade-manager detection, orphan-class detection, f-string-logger detection, dead-parameter detection
20. **File cross-SDK issues** for every pattern that has a Rust parallel
21. **Cascade all API changes through a 1.9.0 → 2.0.0 bump** — the scope exceeds a minor version

## Scope estimate (autonomous cycles)

Per `rules/autonomous-execution.md` (10x multiplier, parallel agent specialization, no human-day framing):

| Work block                                                                 | Cycles         |
| -------------------------------------------------------------------------- | -------------- |
| Delete orphan code (18,400 LOC)                                            | 1              |
| Security fixes (9 CRITICAL: SQL injection, eval, exec, encryption, cache)  | 2              |
| Façade manager real implementations (7 managers)                           | 3              |
| Fabric endpoint Nexus wiring + Redis cache + scheduler + 26 sub-findings   | 3              |
| Adapters consolidation + dialect unification + SQLite adapter merge        | 2              |
| Model registry async migration + transaction manager real implementation   | 2              |
| Cache tenant partitioning across 3 layers + invalidation fix               | 1              |
| Tests: 118 mock removals + real-infra fixtures + CRITICAL regression tests | 2              |
| Observability: structured logging + correlation IDs + metrics              | 2              |
| Documentation: docstring audit + CHANGELOG + README corrections            | 1              |
| Rule extensions + cross-SDK issue filing                                   | 1              |
| Red team pass + gap closure                                                | 1              |
| **Total**                                                                  | **~21 cycles** |

This is a multi-week autonomous campaign, not a patch. The user said "regardless of time and costs" — this plan honors that.

## Next files to produce

1. `02-plans/01-master-fix-plan.md` — atomic, sequenced fix plan mapping all ~46 CRITICAL findings to concrete PRs
2. `02-plans/02-deletion-manifest.md` — exhaustive list of files and classes to delete with justification and rollback
3. `02-plans/03-rule-extensions.md` — new rules and rule extensions that would have caught each finding class
4. `02-plans/04-cross-sdk-parallels.md` — every finding with a kailash-rs parallel, filed as issues
5. `04-validate/01-red-team-findings.md` — red team of this analysis, after the master plan is written
6. `03-user-flows/` — flow diagrams for each rewired subsystem

## Related research

- `01-analysis/02-subsystem-audits/01-core-and-config.md` — 7 C + 18 H + 22 M + 12 L
- `01-analysis/02-subsystem-audits/02-adapters.md` — 5 C + 12 H
- `01-analysis/02-subsystem-audits/03-fabric-deep-dive.md` — 4 new C + 12 new H
- `01-analysis/02-subsystem-audits/04-cache.md` — 2 C + 5 H
- `01-analysis/02-subsystem-audits/05-tenancy-and-security.md` — 9 C + 13 H + 14 M + 9 L
- `01-analysis/02-subsystem-audits/06-nodes-query-migrations.md` — 11 C + 17 H
- `01-analysis/02-subsystem-audits/07-testing-and-observability.md` — 5 C + ~10 H
- `01-analysis/02-subsystem-audits/08-platform-web-orphans.md` — 3 C + ~15 H
- `workspaces/issue-354/` — first-pass fabric analysis (integrate)
