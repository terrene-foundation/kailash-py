# DataFlow Perfection — Master Fix Plan

**Target**: `packages/kailash-dataflow/` end-to-end perfection
**Release**: `kailash-dataflow 1.8.0 → 2.0.0` (major version bump; scope and breaking changes exceed a minor)
**Execution model**: autonomous, parallel agent specialization, ~21 cycles
**Constraint**: no time budget, no cost ceiling, no scope compromise

## Structure

The fix is organized into **14 PRs** that can mostly run in parallel after PR 0 (the foundation). Each PR has an owner agent, a merge gate, a regression test set, and a rollback criterion.

```
PR-0   Foundation branch + CI infrastructure + real Docker fixtures
        ↓
  ┌─────┼─────────────┬───────────────┬──────────────┬────────────┐
  ↓     ↓             ↓               ↓              ↓            ↓
PR-1  PR-2          PR-3            PR-4           PR-5         PR-6
Security  Façade    Orphan         Adapters      Cache       Fabric
fixes     managers  deletion       consolidation  tenancy    wiring
(9 C)     (7 real)  (18,400 LOC)   (3→1 dialect)  (3 layers) (6 endpoints)
  ↓     ↓             ↓               ↓              ↓            ↓
  └─────┼─────────────┼───────────────┼──────────────┼────────────┘
        ↓             ↓               ↓              ↓
      PR-7          PR-8            PR-9           PR-10
      Model         Nodes +         Auto-migrate   Observability
      registry      query           safety         overhaul
      async         security                       (logging +
                                                     metrics)
        ↓             ↓               ↓              ↓
      PR-11   ← PR-12 → PR-13 → PR-14
      Tests   Docs     Rules    Cross-SDK
      rewrite audit    exten-   parallels
              + CHG    sions
```

## PR-0 — Foundation

**Goal**: create the working branch, upgrade the CI surface, provision real-infrastructure fixtures, and break the "warnings disabled" invariant so subsequent PRs can see what they're breaking.

**Branch**: `fix/dataflow-perfection` off `main`
**Owner agent**: release-specialist + infrastructure-specialist
**Depends on**: nothing
**Blocking for**: every subsequent PR

### Deliverables

1. Delete `pytest.ini:34 --disable-warnings -p no:warnings`. Resolve every warning surfaced in the test suite before the branch compiles.
2. Delete `dataflow/utils/suppress_warnings.py` and its invocation at `dataflow/__init__.py:92`. Fix the underlying core SDK node re-registration warning at the source (`src/kailash/nodes/base.py` or `src/kailash/resources/registry.py`) — NOT a blanket logger downgrade.
3. Delete 301 `print()` calls across 37 files in production source. Replace each with a structured `logger.info(...)` / `logger.debug(...)` / `logger.error(...)` per `rules/observability.md`. Grep guard added to pre-commit: `grep -rn '^\s*print(' src/dataflow/` must return zero.
4. Add Docker-backed test fixtures for PostgreSQL, MySQL, SQLite (file mode), and Redis in `packages/kailash-dataflow/tests/conftest.py`. Fixtures must refuse to run if Docker is unavailable (no silent skip). Add corresponding `docker-compose.test.yml` with health-check probes.
5. Version bump `1.8.0 → 2.0.0-dev.1` in `pyproject.toml` and `src/dataflow/__init__.py`.
6. Add `CHANGELOG.md` entry: `[2.0.0] — unreleased — DataFlow Perfection sprint` with a placeholder summary.
7. Ensure `ruff`, `mypy`, `pytest` run green on the branch before merging anything.

### Exit criteria

- `pytest packages/kailash-dataflow/tests/ -W error` runs (fails on warnings, proves no silent suppression)
- `ruff check packages/kailash-dataflow/src/` clean
- `mypy packages/kailash-dataflow/src/` clean
- `grep -rn 'print(' packages/kailash-dataflow/src/dataflow/ | grep -v '__pycache__' | grep -v 'print_(\|pprint'` returns zero
- Docker fixtures pass on clean machine

## PR-1 — Security fixes (9 CRITICAL)

**Goal**: eliminate every vector that allows data exfiltration, RCE, or SQL injection. Must land BEFORE any non-security PR because everything downstream depends on the attack surface being closed.

**Owner agent**: security-reviewer + dataflow-specialist (pair)
**Depends on**: PR-0
**Blocking for**: PR-2, PR-3, PR-5, PR-6, PR-11

### Deliverables

1. **SQL injection in `core/multi_tenancy.py` (13 sites)**: migrate every f-string SQL site to parameterized queries using the canonical `quote_identifier()` helper (from PR-4) for DDL and `?` / `$1` / `%s` bindings for DML. Tenant ID validated against strict regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$` BEFORE it ever reaches a SQL-building call site. Violation raises `InvalidTenantIdError`.
2. **`eval(row["embedding"])` at `semantic/search.py:134`**: this file is in the deletion scope (PR-3). For PR-1, replace with safe msgpack/json deserialization as a stopgap until deletion.
3. **`exec(self.filter_code, ...)` in `nodes/dynamic_update.py`**: DELETE the entire 223-line file in PR-1 (security surface, zero consumers). Its tests move to `tests/regression/test_dynamic_update_rce_deleted.py`.
4. **Fake `encrypt_tenant_data` at `core/multi_tenancy.py:925-949`**: DELETE the function and its call sites. Replace with a real cryptography primitive backed by `cryptography.fernet.Fernet` with keys sourced from the environment via `rules/env-models.md` (KMS integration is out of scope for PR-1 but the abstraction point is created — a `TenantKeyProvider` interface with a default `EnvVarKeyProvider` and a documented extension point for HSM/KMS).
5. **SQL injection via f-string `table_name` across 25 DDL sites**: migrate every adapter DDL to the canonical `quote_identifier()` from `adapters/sql_dialects.py` (until PR-4 consolidates the dialect system). Adapters: `postgresql.py:279,294,363`, `mysql.py:282,298,376,386`, `sqlite.py:519,539,673`, `sqlite_enterprise.py:864,893,973,1003,1013,1023,1074,1079,1139`.
6. **SQL injection in generated `UpdateNode` via `fields` dict keys at `core/nodes.py:2192,2195,2235,2248`**: whitelist field names against `self.model_fields` in `ParameterValidator` (not just the hardcoded `created_at`/`updated_at` rejection). Unknown fields raise `UnknownFieldError`. Never interpolated; always parameterized.
7. **SQL injection in bulk nodes (`bulk_create.py`, `bulk_update.py`, `bulk_delete.py`)**: the audit recommends deleting the standalone files and using the generated `core/nodes.py:3350-3600` branch as canonical. Delete in PR-3 (orphan deletion). For PR-1, add a regression test that exercises the DELETED files' attack vectors against the CANONICAL path to prove the canonical branch is safe.
8. **`LIMIT/OFFSET` inlined in `database/query_builder.py:311-313`**: parameterize.
9. **`validate_queries=False` hardcoded in 40+ DML call sites**: flip to `True` everywhere in PR-1. Any test that breaks because it was relying on unvalidated queries is itself broken and gets fixed.
10. **Unredacted Redis URL logging at `cache/auto_detection.py:146, 152, 220`**: replace every log line that touches `redis_url` with a `mask_sensitive_values()` helper.

### Regression tests (Tier 2 — real Postgres + Redis)

- `tests/regression/test_issue_multi_tenancy_sql_injection.py` — 13 PoC payloads, one per site
- `tests/regression/test_eval_removed_from_semantic_search.py`
- `tests/regression/test_dynamic_update_node_deleted.py`
- `tests/regression/test_encrypt_tenant_data_replaced.py` — verify no `f"encrypted_` prefix, verify Fernet ciphertext verifiable, key rotation works
- `tests/regression/test_ddl_identifier_quoting.py` — injection via `table_name="x\"; DROP TABLE users;--"` against every adapter
- `tests/regression/test_update_node_field_whitelist.py` — `fields={"password_hash = 'pwned', x": 1}` must raise
- `tests/regression/test_query_builder_limit_offset_parameterized.py`
- `tests/regression/test_redis_url_masked_in_logs.py` — `caplog` verification

### Exit criteria

- Every regression test passes against real infrastructure (no mocks)
- `grep -rn 'f".*{table_name}' packages/kailash-dataflow/src/dataflow/adapters/` returns zero
- `grep -rn 'eval(' packages/kailash-dataflow/src/dataflow/` returns zero outside `numexpr`/`ast.literal_eval` justified uses
- `grep -rn 'exec(' packages/kailash-dataflow/src/dataflow/` returns zero
- `grep -rn 'encrypted_' packages/kailash-dataflow/src/dataflow/` returns zero
- `security-reviewer` agent approves the diff

## PR-2 — Façade manager real implementations (7 managers)

**Goal**: replace every stub manager class with a real one that does what the docstring promises, OR delete the manager and remove the public API if no real implementation is viable in-scope.

**Owner agent**: dataflow-specialist
**Depends on**: PR-1
**Blocking for**: PR-7, PR-10

### Deliverables

1. **`features/transactions.py::TransactionManager`** — real implementation:
   - Acquire a connection via the adapter
   - Issue `BEGIN [ISOLATION LEVEL X]`
   - Track the active transaction in a `ContextVar` (not a class attribute — async-safe)
   - Commit on clean exit, rollback on exception
   - Support savepoints via `SAVEPOINT` / `RELEASE SAVEPOINT` / `ROLLBACK TO SAVEPOINT`
   - Nested `with` yields savepoints, outer yields real transactions
   - Emit `rules/observability.md` entry/exit/error logs
   - Integration test: two concurrent transactions on the same connection pool, one rolls back, verify the other's writes are preserved and the rolled-back changes are gone
2. **`utils/connection.py::ConnectionManager`** — real implementation:
   - `initialize_pool()` delegates to the adapter's `create_connection_pool()`
   - `health_check()` runs `SELECT 1` with a bounded timeout and reports real reachability
   - `test_connection()` returns the real driver error when a connection can't be acquired
   - `close_all_connections()` delegates to the adapter's `close_connection_pool()`
   - Every method returns real state, not a hardcoded dict
3. **`features/multi_tenant.py::MultiTenantManager`** — real implementation backed by PostgreSQL/MySQL/SQLite (not a Python dict):
   - Tenants stored in a `dataflow_tenants` table (numbered migration, schema-migration.md compliant)
   - `create_tenant(tenant_id, metadata)` writes the row with parameterized SQL
   - `get_tenant(tenant_id)` reads the row
   - `list_tenants()` paginated
   - `delete_tenant(tenant_id)` soft-delete (audit trail required)
   - All operations emit audit log entries via PR-10's audit log path
   - Tenant ID validated against regex (re-uses the validator from PR-1)
4. **`TenantSecurityManager`** — delete the fake; replace with real Fernet-backed encryption per PR-1
5. **`CacheIntegration` (legacy parallel init path at `core/engine.py:941-1005`)**: DELETE the dead 886 LOC parallel init. Consumers (zero real consumers per cache audit) migrate to the live Express cache path.
6. **`FabricScheduler`**: wire into `FabricRuntime.start()`. `ProductRegistration.schedule` values are parsed into `croniter` objects at registration time and scheduled in the leader's event loop. Leader death releases the schedule; new leader re-acquires. Integration test: declare a product with `schedule="*/5 * * * * *"` (every 5s) and verify it fires 5 times in 30 seconds.
7. **`FabricServingLayer` wiring**: see PR-6 — fabric endpoints registration into Nexus.

### Exit criteria

- Zero Python-dict "managers" exposed as public APIs
- Every manager has a Tier 2 integration test that verifies real infrastructure side effects
- `db.transactions.transaction()` actually issues BEGIN/COMMIT to the database — verify via server log (pg_stat_activity or SHOW PROCESSLIST)

## PR-3 — Orphan deletion (~18,400 LOC)

**Goal**: remove dead code, dead subdirectories, and duplicate implementations. This is the largest mechanical PR in the sprint and the one that unblocks every subsequent refactor by eliminating the "two parallel implementations" problem.

**Owner agent**: dataflow-specialist + reviewer (pair for safety)
**Depends on**: PR-1 (security patches must land on the live path before the dead path is deleted)
**Blocking for**: PR-4 (dialect consolidation requires the dead dialect systems gone)

### Deliverables — files and directories to delete

| Path                                                                 | LOC   | Reason                                                                                               |
| -------------------------------------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------- |
| `dataflow/nodes/dynamic_update.py`                                   | 223   | RCE via exec() (PR-1 replaces stopgap); zero consumers                                               |
| `dataflow/nodes/bulk_create.py` (standalone)                         | ~400  | SQL injection minefield; canonical branch at `core/nodes.py:3350`                                    |
| `dataflow/nodes/bulk_update.py` (standalone)                         | ~500  | Same                                                                                                 |
| `dataflow/nodes/bulk_delete.py` (standalone)                         | ~350  | Same                                                                                                 |
| `dataflow/web/`                                                      | 1,958 | Entire `WebMigrationAPI` orphan, zero Nexus wiring                                                   |
| `dataflow/semantic/`                                                 | 1,239 | Duplicates Kaizen `SemanticMemory`; `eval()` RCE site (stopgap in PR-1 then delete)                  |
| `dataflow/compatibility/`                                            | 1,327 | `unittest.mock.Mock` in production at `legacy_support.py:75`; legacy kailash compat no longer needed |
| `dataflow/performance/`                                              | 1,700 | Duplicate `MigrationConnectionManager` class name collision                                          |
| `dataflow/migration/` (singular)                                     | ?     | Dead duplicate of `dataflow/migrations/`                                                             |
| `dataflow/validators/` (plural)                                      | ?     | Dead duplicate of `dataflow/validation/`                                                             |
| `dataflow/trust/`                                                    | 2,407 | Zero production importers (OR wire in PR-2 if salvageable)                                           |
| `dataflow/optimization/`                                             | ?     | Only consumed by a single test                                                                       |
| `dataflow/classification/`                                           | ?     | `@classify` decorator promises redaction never delivered; delete or wire in PR-8                     |
| `dataflow/core/cache_integration.py` (legacy)                        | 886   | Dead parallel init path                                                                              |
| `dataflow/adapters/sqlite_enterprise.py`                             | ?     | Divergent, less-complete SQLite adapter; default in `factory.py:37`                                  |
| `dataflow/fabric/metrics.py` (if unwired in PR-10)                   | 166   | Dead `FabricMetrics` class; OR wire in PR-10                                                         |
| `dataflow/fabric/pipeline.py::InMemoryDebouncer`                     | ~50   | Zero instantiations; follow-up issue will reimplement                                                |
| `dataflow/fabric/pipeline.py::_queue` + `change_detector.py:274-296` | ~40   | Dead pair (red team finding N1)                                                                      |
| `dataflow/sql/dialects.py` OR `adapters/sql_dialects.py`             | ?     | Pick one, delete the other                                                                           |
| `dataflow/utils/suppress_warnings.py`                                | ?     | Logger-level suppression (already deleted in PR-0; counted for tracking)                             |
| `dataflow/cli/main.py` (coming-soon stubs)                           | ?     | Every command prints "coming soon"; DELETE the file and the `pyproject.toml` entry point             |

### Deliverables — classes to delete (excerpt)

- `core/multi_tenancy.py::TenantSecurityManager` (fake encryption)
- `features/multi_tenant.py::MultiTenantManager` (replaced by PR-2 real impl)
- `utils/connection.py::ConnectionManager` (replaced by PR-2 real impl)
- `debug/DebugAgent` (LLM-first violation + hardcoded model name)
- `debug/ErrorCategorizer` (regex-based, LLM-first violation)
- `debug/PatternRecognitionEngine` (threshold-based, LLM-first violation)
- Every orphan `platform/*` class except `Inspector` and `ErrorEnhancer`

### Deliverables — duplicate consolidation

| Duplicate                      | Canonical Choice                     | Delete                     |
| ------------------------------ | ------------------------------------ | -------------------------- |
| `migration/` vs `migrations/`  | `migrations/` (plural; the live one) | `migration/`               |
| `validation/` vs `validators/` | `validation/` (live one)             | `validators/`              |
| Three dialect systems          | Pick one (PR-4 decides)              | Other two                  |
| Two SQLite adapters            | `sqlite.py` (more complete)          | `sqlite_enterprise.py`     |
| Three `CircuitBreaker`         | One in a shared `utils/` module      | Other two                  |
| Two `DataFlowError`            | One canonical                        | Other                      |
| Two `HealthStatus`             | One canonical                        | Other                      |
| Two `RetentionPolicy`          | One canonical                        | Other                      |
| Two `DebugAgent`               | Delete both                          | Both (LLM-first violation) |

### Process

1. For each deletion candidate, run `git grep -l '<class_or_module_name>' packages/ src/` to find every consumer.
2. Document consumer count in a tracking file at `workspaces/dataflow-perfection/02-plans/03-deletion-safety-log.md`.
3. For each candidate with zero consumers, delete in a single commit with message `chore(dataflow): delete orphan <name> (0 consumers verified)`.
4. For each candidate with NON-ZERO consumers, list the consumers, justify why they can also be deleted or migrated, then delete in a dependent commit.
5. After every batch of 10 deletions, run the full test suite. If any test fails, the test was exercising orphan code — either fix the test to exercise the canonical path, or delete the test if it was exclusively exercising the deleted orphan.
6. Final diff stats: target `~18,400 LOC deleted`.

### Exit criteria

- `wc -l` on the branch diff shows net ~18,400 LOC removed
- Full test suite passes
- `ruff check` and `mypy` clean
- Every deletion has a consumer-count log entry

## PR-4 — Adapters consolidation + dialect unification

**Goal**: collapse the three parallel dialect systems into one, fix #353 (sslmode), fix the PostgreSQL `execute_transaction` non-transaction bug, add `application_name`/`command_timeout`/`sslrootcert`/`sslcert`/`sslkey` URL parsing, consolidate identifier quoting through the canonical helper, and eliminate cross-adapter divergence.

**Owner agent**: dataflow-specialist + infrastructure-specialist
**Depends on**: PR-1 (security fixes landed), PR-3 (dead dialect systems deleted)
**Blocking for**: PR-11 (tests that use adapters)

### Deliverables

1. **Canonical dialect module**: pick one of `adapters/sql_dialects.py` or `sql/dialects.py`. Rename to `adapters/dialect.py`. Expose the full `rules/infrastructure-sql.md` helper set: `dialect.blob_type()`, `dialect.current_timestamp()`, `dialect.quote_identifier()`, `dialect.limit_clause()`, `dialect.auto_increment_clause()`, `dialect.upsert_clause()`, `dialect.returning_clause()`.
2. **Fix #353** — `adapters/postgresql.py:340-351 get_connection_parameters` returns every URL parameter: `ssl`, `application_name`, `command_timeout`, `server_settings`, plus parsed `sslrootcert`/`sslcert`/`sslkey`. Translate `sslmode=disable|prefer|require|verify-ca|verify-full` to asyncpg's SSL argument (bool for disable, SSLContext for verify-\*). Regression test at `tests/regression/test_issue_353_sslmode.py`.
3. **Fix PostgreSQL execute_transaction** — rewrite `adapters/postgresql.py:157-176` to:
   - Acquire a single connection from the pool
   - Enter asyncpg's `connection.transaction()` context manager
   - Run all queries on that connection
   - Commit on clean exit, rollback on exception
   - Match MySQL/SQLite semantics
4. **Expand URL parsing** — `connection_parser.py` must handle:
   - `redis://`, `rediss://`, `unix://` schemes
   - Passwords with every special char (`%`, `:`, `@`, `/`, `?`, `#`)
   - IPv6 hosts in brackets
   - Unix socket paths
   - Query string flags
   - Trailing slashes
   - Relative SQLite paths
   - `file:memdb_NAME?mode=memory&cache=shared` URIs
5. **Factory safety** — `adapters/factory.py:37`: remove the `SQLiteEnterpriseAdapter` default; use `SQLiteAdapter`. If `sqlite_enterprise.py` is already deleted in PR-3, this is mechanical.
6. **Bypass-pool bug** — `sqlite.py` and `sqlite_enterprise.py` (if the latter survives PR-3) MUST go through the pool for `_test_connection`, `_perform_wal_checkpoint`, `_initialize_performance_monitoring`, and `_collect_performance_metrics`. Bare `aiosqlite.connect()` is forbidden per `rules/patterns.md` § SQLite Connection Management.
7. **Fabricated telemetry deletion** — `sqlite.py:913-925` `cache_hit_ratio = 0.95 if ...` and `checkpoint_frequency=1.0`: delete. Replace with real metrics sourced from `sqlite_stat1` / `PRAGMA wal_checkpoint` or mark the metric as unavailable.
8. **Lazy driver imports** — per `rules/dependencies.md` and `rules/infrastructure-sql.md` Rule 8: every driver (`asyncpg`, `aiomysql`, `aiosqlite`) imported lazily inside methods, not at module top. Already partial; make total.
9. **Error taxonomy** — every adapter raises `AdapterError`/`ConnectionError`/`QueryError`/`TransactionError` consistently. No bare `Exception` raises.
10. **Parity table test** — new test `tests/unit/adapters/test_adapter_parity.py` that asserts every public method on `DatabaseAdapter` is implemented by all three adapters. Test fails if any gap.

### Exit criteria

- Single canonical dialect module
- `grep -rn "sslmode" packages/kailash-dataflow/src/dataflow/adapters/` confirms URL parsing AND forwarding
- Regression tests for #353, execute_transaction, parity all pass against real PostgreSQL + MySQL + SQLite
- Zero `aiosqlite.connect(` direct calls in production source

## PR-5 — Cache tenancy across three layers

**Goal**: fix the active cross-tenant data leak in the Express cache, extend tenant partitioning to fabric, and fix the three broken `invalidate_model` implementations.

**Owner agent**: dataflow-specialist + security-reviewer
**Depends on**: PR-1, PR-3
**Blocking for**: PR-6 (fabric cache builds on this)

### Deliverables

1. **Express cache tenant dimension** — `cache/key_generator.py:97-135 generate_express_key` gains a required `tenant_id: Optional[str]` argument. For `multi_tenant=True` models, `tenant_id` is REQUIRED and absence raises `FabricTenantRequiredError`. Keys become `dataflow:v1:<tenant_id>:<model>:<op>:<params_hash>`.
2. **Express call-site migration** — every `generate_express_key` / `express.cache_*` call site in `features/express.py:140, 954-996` passes `tenant_id` from the tenant context. If no context, raise (unless the model is not `multi_tenant`).
3. **`invalidate_model` consolidation** — the three parallel implementations (`features/express.py:991-996`, `cache/memory_cache.py:180-203`, `cache/async_redis_adapter.py:343-357`) become ONE. Wrong prefix in `AsyncRedisCacheAdapter` (`dataflow:{model}:*` should be `dataflow:v1:<tenant>:<model>:*`) fixed. Substring `in` match in `InMemoryCache` replaced with exact key pattern match.
4. **Cache version tag** — every cached entry gets a `schema_version: 2` field. Entries with an old version are evicted on read (safe migration).
5. **Cache metrics** — register `express_cache_hits_total{model, op, tenant}`, `express_cache_misses_total{model, op, tenant}`, `express_cache_errors_total{backend}`, `express_cache_backend_info{backend}` gauges. Tenant label cardinality is a Prometheus footgun — cap at 1000 distinct tenants and collapse the rest into `tenant="other"`.
6. **Structured logging** — every cache `get`/`set`/`invalidate` emits `logger.info("express.cache.get", model=..., tenant_id=..., cache_hit=..., source=redis|memory, mode=real|cached, latency_ms=...)`.
7. **Redis URL parser fix** — `cache/auto_detection.py:68-78` — DELETE the hand-rolled parser, use `urllib.parse.urlparse` or `redis.asyncio.from_url` directly.
8. **Circuit breaker** — flip the default from `circuit_breaker_enabled=False` to `True`. Implement the `failover_mode="degraded"` path (currently a stub).
9. **Rust cross-SDK** — file `esperie-enterprise/kailash-rs#<new>` with the same bug in `crates/kailash-dataflow/src/query_cache.rs` (zero tenant dimension, 953 LOC).

### Regression tests (Tier 2 — real Postgres + Redis)

- `tests/regression/test_express_cache_tenant_isolation.py` — two tenants, same model, same query, verify distinct cache entries AND no cross-tenant hits
- `tests/regression/test_express_cache_invalidate_exact_match.py` — verify `invalidate_model("User")` does NOT nuke `UserAudit`
- `tests/regression/test_express_cache_invalidate_redis_prefix.py` — verify Redis prefix matches real key pattern
- `tests/regression/test_express_cache_schema_version_migration.py` — write entry with old version, verify eviction on read
- `tests/regression/test_redis_url_parser_edge_cases.py` — password-special-chars, IPv6, unix sockets, rediss://, trailing slashes

### Exit criteria

- Zero cache-key construction sites without `tenant_id`
- `grep -rn "dataflow:{model}" packages/kailash-dataflow/src/dataflow/cache/` returns zero (wrong prefix)
- All regression tests pass against real Redis

## PR-6 — Fabric: Redis cache + endpoint wiring + scheduler + webhooks (integrates `workspaces/issue-354/` plan)

**Goal**: honor `workspaces/issue-354/02-plans/01-fix-plan.md` AND wire the 1,555 LOC of orphan fabric endpoint code. This is the biggest single PR in the sprint.

**Owner agent**: dataflow-specialist (primary) + nexus-specialist (endpoint registration)
**Depends on**: PR-1, PR-2, PR-5 (cache tenant partitioning must land first)
**Blocking for**: PR-10 (observability) for fabric metrics

### Deliverables (integrates issue-354 plan + new second-pass findings)

1. **`fabric/cache.py`** — `FabricCacheBackend(ABC)` + `InMemoryFabricCacheBackend` + `RedisFabricCacheBackend` (per `workspaces/issue-354/02-plans/01-fix-plan.md`)
2. **Tenant-partitioned cache keys** — red-team Amendment A: tenant plumbing through `FabricServingLayer`, `serving.py:276,393`, `runtime.py:479,566`, `health.py:85`, `_get_products_cache`, `products.py`
3. **Write CAS by `run_started_at`** — Amendment C
4. **Redis-outage fallback** — Amendment D
5. **`get_metadata(key)` fast path** — Amendment A (metadata-only HGET)
6. **Leader-side warm-cache on election** — Amendment B (NOT follower lazy prewarm)
7. **DataFlow `self._redis_url` assignment** — fix the deepest wiring
8. **Webhook `_get_or_create_redis_client`** — shared Redis client for cache, webhook nonce, leader, debouncer
9. **Paired deletion**: `pipeline.py:173 _queue` + `change_detector.py:274-296`
10. **NEW — Endpoint wiring into Nexus**: `FabricRuntime.start()` accepts a `nexus: Nexus` parameter (not `Optional[Any]`). When provided, registers:
    - `serving.get_routes()` into `nexus.register_routes(...)`
    - `health.get_health_handler()` into `nexus.register_route("/fabric/health", ...)`
    - `sse.get_sse_handler()` into `nexus.register_route("/fabric/sse/:product", ...)`
    - `webhooks.handle_webhook` into `nexus.register_route("/fabric/webhook/:source", POST)`
    - `mcp_integration` into `nexus.register_mcp_tools(...)`
    - `metrics.get_prometheus_handler()` into `nexus.register_route("/fabric/metrics", ...)`
      When no `nexus` provided, fabric starts in "background only" mode (change detector + scheduler + leader) with NO endpoints — loud log warning.
11. **NEW — Multi-webhook-source support**: `WebhookReceiver` gains adapters for GitHub (`x-hub-signature-256`), GitLab (`x-gitlab-token`), Stripe (`stripe-signature`), Slack (`x-slack-signature`), and generic HMAC. Config per product.
12. **NEW — `FabricScheduler` wiring**: instantiated in `FabricRuntime.start()`, receives the `ProductRegistration.schedule` cron expressions, runs on the leader's event loop. Leader death releases, new leader re-acquires.
13. **NEW — `tenant_extractor` actually invoked**: currently stored but never called. Every webhook request and serving request must extract tenant_id via the callable.
14. **NEW — `FabricMetrics` wiring**: PR-10 adds the metric definitions; this PR instantiates `FabricMetrics()` in `FabricRuntime.start()` and updates counters from pipeline execution, cache operations, leader election, webhook dispatch.
15. **CHANGELOG breaking change note** — `FabricRuntime.product_info`/`invalidate`/`invalidate_all` become async; fabric endpoints now require a Nexus instance

### Regression tests (Tier 2 — real Redis + real Nexus)

(All from `workspaces/issue-354/02-plans/01-fix-plan.md` Tier 2 list, PLUS:)

- `tests/regression/test_fabric_endpoints_registered_with_nexus.py` — verify GET `/fabric/dashboard` returns 200 (not 404)
- `tests/regression/test_fabric_github_webhook_signature.py` — send a GitHub webhook with `x-hub-signature-256`, verify HMAC validated and event dispatched
- `tests/regression/test_fabric_gitlab_webhook.py`
- `tests/regression/test_fabric_stripe_webhook.py`
- `tests/regression/test_fabric_slack_webhook.py`
- `tests/regression/test_fabric_scheduler_cron_executes.py` — declare a product with `schedule="*/5 * * * * *"`, verify 5-6 executions in 30 seconds
- `tests/regression/test_fabric_tenant_extractor_invoked_on_request.py`
- `tests/regression/test_fabric_metrics_populated_on_pipeline_run.py`

### Exit criteria

- Every issue-354 red-team amendment landed
- Every fabric endpoint reachable via Nexus
- GitHub/GitLab/Stripe/Slack webhook signatures validated
- Scheduler executes cron expressions on the leader
- Every Tier 2 fabric regression test passes

## PR-7 — Model registry async migration + full transaction wrapping

**Goal**: fix #352 (13 sites, not 1). Every model registry operation runs in a real transaction via PR-2's TransactionManager.

**Owner agent**: dataflow-specialist
**Depends on**: PR-2 (TransactionManager real impl)
**Blocking for**: nothing downstream

### Deliverables

1. **Convert `ModelRegistry._create_model_registry_table` and all 12 other `self.runtime.execute(...)` sites** to async. The caller chain cascades through `initialize()` → `DataFlow.start()`. Verify every caller is already async.
2. **Wrap every model-registry mutation in a real transaction** via `async with db.transactions.transaction():`. Partial failure rolls back.
3. **Tests** — `tests/regression/test_issue_352_fastapi_startup.py` — instantiate DataFlow under an async FastAPI lifespan, verify table creation succeeds AND the table actually exists.
4. **Sync-context back-compat** — when `_is_async=False`, fall through to the existing sync `runtime.execute()` path.

### Exit criteria

- `tests/regression/test_issue_352_fastapi_startup.py` passes
- No sync `runtime.execute()` calls inside async contexts (grep guard)

## PR-8 — Nodes, query builder, migrations safety

**Goal**: fix every non-security node/query/migration finding from audit 06. Includes auto-migrate safety, `UpdateNode` field whitelist (if not fully landed in PR-1), manual timestamp management removal, LIMIT/OFFSET parameterization, `validate_queries=True` flip, classification wiring or deletion.

**Owner agent**: dataflow-specialist
**Depends on**: PR-1, PR-3, PR-4
**Blocking for**: PR-11

### Deliverables

1. **Auto-migrate safety** — `core/engine.py:5191-5196` — flip `auto_confirm=True` to `auto_confirm=False` in production mode; add `DATAFLOW_AUTO_MIGRATE=true` environment variable to opt in explicitly. Production deployments that rely on auto-migrate must set the env var.
2. **Auto-migrate failure handling** — `engine.py:5209-5212` — remove the swallow. Migration failure raises; model registration fails loudly. Operators see the broken SQL.
3. **Fix the broken SQL in the auto-migrate generator** — `migrations/performance_data/migration_history.jsonl` shows 44 consecutive "syntax error at or near WHERE" failures. Trace, fix, add regression test.
4. **Numbered migration files** — per `rules/schema-migration.md` Rule 1, model schema changes go through numbered migrations. Auto-migrate is the exception ONLY for the bootstrap; any subsequent schema change requires a numbered file.
5. **Downgrade paths** — every migration gets a `downgrade()`. Non-reversible migrations require explicit human acknowledgement.
6. **Delete `migrations/performance_data/migration_history.jsonl`** from source. This is runtime telemetry, not source. Add to `.gitignore`.
7. **`classification/` decision** — either wire `@classify("email", PII, ..., REDACT)` into the query path (read / write interceptor that applies redaction based on the classification) OR delete the whole subsystem. User's "perfect" mandate suggests wiring; allocate a cycle.
8. **Query filter whitelist** — `query/filter.py` operator whitelist. Unknown operators raise.
9. **LIKE / ILIKE escaping** — `%`, `_`, `\` in user input properly escaped.
10. **`order_by` whitelist** — user-supplied ordering values validated against model fields.
11. **Pagination cap** — `limit` default capped at 10,000 per model; override via model config.

### Exit criteria

- `tests/regression/test_auto_migrate_opt_in.py`
- `tests/regression/test_auto_migrate_failure_raises.py`
- `tests/regression/test_auto_migrate_generator_where_clause.py`
- Classification wired or deleted (no partial)

## PR-9 — Auto-migrate safety (split from PR-8 if scope overflows)

If PR-8's scope gets unwieldy, this is the auto-migrate-only spin-off. Merge if PR-8 fits.

## PR-10 — Observability overhaul

**Goal**: replace 969 f-string log calls with structured logging, add correlation IDs, wire Prometheus metrics, remove the 301 `print()` calls (already done in PR-0), implement entry/exit/error logs on every endpoint.

**Owner agent**: infrastructure-specialist + dataflow-specialist
**Depends on**: PR-0 (warning suppression removed), PR-2 (managers have real paths to log)
**Blocking for**: PR-11 (test expectations for log output)

### Deliverables

1. **Structured logging migration** — 969 f-string log calls across 99 files rewritten to `logger.info("event.name", field1=value1, field2=value2)`. Use `structlog` if not already the logger, else the standard library's `logging.Logger.info(msg, extra={...})`.
2. **Correlation IDs** — every DataFlow entry point (express CRUD, fabric pipeline execution, migration run, transaction scope) binds a `correlation_id` via `contextvars.ContextVar` that propagates through async calls.
3. **Entry/exit/error logs** — every public method on DataFlow's Express API, every fabric endpoint, every adapter operation emits three log lines per invocation: start, success/error, latency.
4. **`mode=real|cached|fake` field** — every data-call log line includes `mode`. In production there should never be `mode=fake` anywhere.
5. **Prometheus metrics** — register and populate:
   - `dataflow_express_operations_total{model, op, tenant, result}`
   - `dataflow_express_duration_seconds{model, op, tenant}`
   - `dataflow_fabric_pipeline_duration_seconds{product, tenant}`
   - `dataflow_fabric_cache_hits_total{backend, product, tenant}`
   - `dataflow_fabric_cache_misses_total{backend, product, tenant}`
   - `dataflow_fabric_cache_errors_total{backend, error_class}`
   - `dataflow_fabric_cache_backend_info{backend}` (gauge)
   - `dataflow_fabric_cache_degraded{backend}` (gauge for outage)
   - `dataflow_fabric_prewarm_duration_seconds{replica_role}`
   - `dataflow_fabric_leader_state{replica_id}` (gauge)
   - `dataflow_adapter_connection_pool_size{dialect}`
   - `dataflow_adapter_connection_pool_used{dialect}`
   - `dataflow_adapter_query_duration_seconds{dialect, op}`
   - `dataflow_adapter_errors_total{dialect, error_class}`
   - `dataflow_migration_runs_total{result}`
   - `dataflow_transaction_duration_seconds{isolation_level, result}`
6. **OpenTelemetry spans** — optional but recommended. Span around every public entry point.
7. **Audit logs** — every privileged operation (tenant create, migration run, secret rotation) emits an `audit.<event>` log line with full context.
8. **Redis URL masking** — `mask_sensitive_values()` helper applied to every log line touching a connection string.

### Exit criteria

- `grep -rn 'logger\.\(info\|error\|warning\|debug\)(f"' packages/kailash-dataflow/src/dataflow/ | wc -l` shows 0
- Every Prometheus metric increments in the integration test suite
- `tests/observability/test_correlation_id_propagation.py` passes
- `tests/observability/test_structured_log_schema.py` — every expected log event is emitted with expected fields

## PR-11 — Test rewrite

**Goal**: fix 118 mock violations in Tier 2/3, add regression tests for every CRITICAL security finding (if not already added in PR-1), migrate Tier 1/2/3 folders to match `rules/testing.md`, enable `pytest -W error`.

**Owner agent**: testing-specialist
**Depends on**: PR-0 (infrastructure), PR-1 (regression tests from security), every other PR (tests for each fix)
**Blocking for**: release

### Deliverables

1. **118 mock violations** — every `from unittest.mock import` / `@patch` / `MagicMock` in `tests/integration/`, `tests/e2e/`, `tests/fabric/` rewritten to use real infrastructure fixtures.
2. **`no_mocking_policy` fixture enforcement** — wire `tests/conftest.py:455` into an autouse fixture that fails on mock import in Tier 2/3.
3. **State-persistence verification** — every `api.create_*` / `db.express.create` in Tier 2/3 followed by a read-back assertion.
4. **New modules from PR-1 through PR-10** — every new file has an importing test.
5. **Regression tests from security audit** — the full list from the tenancy/security audit Appendix B, if not already landed in PR-1.
6. **Tier 1 speed guard** — `pytest tests/unit/ --timeout-unit 1` fails if any Tier 1 test takes >1s.
7. **Coverage gate** — per `rules/testing.md`, 80% general, 100% financial/auth/security. Enforce in CI.

### Exit criteria

- `pytest tests/integration/ tests/e2e/ tests/fabric/ -x` passes against real infrastructure
- Mock import grep returns zero in Tier 2/3
- Coverage report meets thresholds

## PR-12 — Documentation + CHANGELOG audit

**Goal**: every docstring that lied is corrected; README claims match reality; deployment doc corrected; CHANGELOG for 2.0.0 written.

**Owner agent**: reviewer + release-specialist
**Depends on**: every preceding PR
**Blocking for**: release

### Deliverables

1. **Docstring audit** — for every parameter in every public class in `dataflow/`, verify the class body implements the documented behavior. Rewrite every lie. Grep for "production", "Redis", "distributed", "cross-worker", "shared", "encrypted", "tenant-isolated", "atomic" and verify each hit.
2. **README corrections** — `packages/kailash-dataflow/README.md`: lines that promised features delivered in 2.0.0 are clarified; lines that promised features deleted are removed.
3. **Deployment doc** — `packages/kailash-dataflow/docs/production/deployment.md` rewritten to reflect actual production behavior.
4. **CHANGELOG 2.0.0 entry** — comprehensive, per-PR breakdown, breaking-change section, migration snippets.
5. **Migration guide** — `docs/migration/1.x-to-2.0.md` — step-by-step for downstream consumers.

## PR-13 — Rule extensions

**Goal**: encode the patterns uncovered by this audit into `.claude/rules/` so the next round catches the next instance.

**Owner agent**: claude-code-architect
**Depends on**: nothing (can land in parallel)
**Blocking for**: nothing

### Deliverables

1. **Extend `rules/dataflow-pool.md` Rule 3** — explicit list of config field patterns (`*_url`, `*_backend`, `*_client`, `*_enabled`, `*_mode`) that MUST have a consumer check.
2. **New rule `rules/facade-manager-detection.md`** — any class named `*Manager` exposed as a DataFlow public attribute MUST have a Tier 2 integration test that verifies real side effects.
3. **Extend `rules/zero-tolerance.md` Rule 2** — explicit examples from the audit: fake encryption, fake transaction manager, fake health check.
4. **Extend `rules/testing.md`** — enforce `no_mocking_policy` fixture on Tier 2/3.
5. **Extend `rules/observability.md`** — explicit ban on `logger.*(f"...")`; grep guard in pre-commit.
6. **New rule `rules/orphan-detection.md`** — every new class in the codebase must have at least one non-test consumer within N commits of landing, or be deleted.
7. **New rule `rules/tenant-isolation.md`** — every cache key, every query filter, every log line, every metric label that handles tenant data MUST have a tenant dimension or explicitly document why not.
8. **New rule `rules/dataflow-identifier-safety.md`** — every DDL / DML that touches a user-influenced identifier must go through `dialect.quote_identifier()`.

## PR-14 — Cross-SDK parallels

**Goal**: file every kailash-rs issue that has a parallel to a Python finding. Per `rules/cross-sdk-inspection.md`, this is mandatory before closing the Python issues.

**Owner agent**: repo-admin (cross-repo specialist)
**Depends on**: every PR (to know what to file)
**Blocking for**: nothing

### Deliverables

1. File `esperie-enterprise/kailash-rs#<A>` — fabric `CacheBackend` trait (from `workspaces/issue-354/02-plans/02-followup-issues.md`)
2. File `esperie-enterprise/kailash-rs#<B>` — query cache tenant isolation (`crates/kailash-dataflow/src/query_cache.rs` 0 tenant mentions, 953 LOC)
3. File `esperie-enterprise/kailash-rs#<C>` — verify `multi_tenancy.rs` has or does not have the f-string SQL injection pattern
4. File `esperie-enterprise/kailash-rs#<D>` — verify `transactions.rs` is a real transaction wrapper (not a stub like Python)
5. File `esperie-enterprise/kailash-rs#<E>` — verify all adapters forward `sslmode` correctly
6. File `esperie-enterprise/kailash-rs#<F>` — verify `CreateTable` DDL uses parameterized identifiers
7. File `esperie-enterprise/kailash-rs#<G>` — verify classification decorator wiring
8. File `esperie-enterprise/kailash-rs#<H>` — verify no orphan manager classes exposed as public API

## Gating and sequencing

| PR  | Depends on            | Blocks         | Parallelizable with |
| --- | --------------------- | -------------- | ------------------- |
| 0   | —                     | all            | —                   |
| 1   | 0                     | 2, 3, 5, 6, 11 | —                   |
| 2   | 1                     | 7, 10          | 3, 4                |
| 3   | 1                     | 4              | 2, 5, 8             |
| 4   | 1, 3                  | 11             | 5, 6                |
| 5   | 1, 3                  | 6              | 4, 6, 8             |
| 6   | 1, 2, 5               | 10             | 7, 8                |
| 7   | 2                     | —              | 6, 8                |
| 8   | 1, 3, 4               | 11             | 6, 7                |
| 10  | 0, 2                  | 11             | 11, 12              |
| 11  | 0, 1, 10, each fix PR | release        | 12                  |
| 12  | all preceding         | release        | 11, 13              |
| 13  | none                  | —              | all                 |
| 14  | all                   | —              | 12                  |

Critical path: **PR-0 → PR-1 → PR-3 → PR-4 → PR-6 → PR-10 → PR-11 → release**. Other PRs pipeline behind the critical path.

## Release gate

DataFlow 2.0.0 can release when:

1. Every PR has merged to `fix/dataflow-perfection`
2. `ruff check`, `mypy`, `pytest -W error` all green
3. Test coverage thresholds met (80% general, 100% security-critical)
4. Zero findings remaining from the audit (CRITICAL, HIGH, MEDIUM, LOW)
5. Red team pass finds no gaps
6. CHANGELOG 2.0.0 entry written, migration guide published
7. Cross-SDK Rust issues filed and tracked
8. Impact-verse deployment owner has been notified and a cutover plan agreed

## Rollback criterion

If any PR introduces a regression that cannot be resolved within the PR scope:

1. Revert the PR
2. File a dedicated issue with a minimum reproduction
3. Do NOT block subsequent PRs if their scope is independent
4. Re-attempt the failed PR after dependencies clarify

## Impact on downstream consumers

- **impact-verse** — relies on `DataFlow(multi_tenant=True, redis_url=...)`; will need to explicitly set tenant_id on every Express operation. Breaking change documented in CHANGELOG.
- **Any consumer using `db.transactions`** — will now get real transactions. Code that relied on the stub "succeeding" will now surface real DB errors. This is a feature.
- **Any consumer using `db.connection.health_check`** — will now get real health signals. Monitoring dashboards that were watching a constant-true signal will flip. This is a feature.
- **Any consumer using `dataflow init`** — CLI is deleted. Migration: use Python API directly.
- **Any consumer using `DynamicUpdateNode`** — node is deleted. Migration: use `PythonCodeNode` with explicit allow-list.
- **Any consumer using `@classify`** — either wired (PR-8 redaction in query path) or deleted. Migration: explicit field-level encryption via PR-2's Fernet helper.

## Cost / cycle estimate

Per `rules/autonomous-execution.md`: ~21 cycles end-to-end, most PRs parallelizable. Critical path: 7-8 cycles sequential. Cross-SDK Rust follow-ups add 3-5 cycles to the total but not to the Python critical path.

User's constraint: "regardless of time and costs". Plan honors the constraint. The plan is complete; ready for `/todos` human approval gate.
