# DataFlow Specialist Review — Issue #979 Triage

Date: 2026-05-13
Phase: /analyze (expert pass 04, parallel with testing / pentest / release experts)
Source: amendments plan `02-plans/01-amendments-post-redteam.md`
Reading order: brief → tier1-contract → failure-layers → amendments → this file.

Mission: scrutinize the S2a/S2b/S2c/S2d + S3 + S4 + S5a/S5b moves for **DataFlow-specific contract risk** the testing/pentest/release lenses cannot surface. Extends `02-failure-layers.md`, does not repeat it.

Findings are classified per the prompt's four buckets:

- **API-CONTRACT-RISK** — a DataFlow API contract loses tier-1 coverage after the move.
- **FIXTURE-COMPATIBILITY** — a moved test will not run on `memory_dataflow` (in-memory SQLite).
- **PORTABILITY-GAP** — test uses a PG-only feature SQLite cannot fake.
- **NEUTRAL** — no DataFlow-specific concern.

All findings cite `path:line` verified by grep on current `main` (`21ba8e6a`).

---

## Finding 1 — API-CONTRACT-RISK — `DataFlowEngine.builder()` has ZERO tier-1 coverage

Per `framework-first.md` § Four-Layer Hierarchy, `DataFlowEngine` (Engine layer) is the DEFAULT for production DataFlow use; `db.express` is the primitive convenience. `framework-first.md` table lists `DataFlowEngine.builder()` with validation / classification / query-tracking as the recommended path.

`rg 'DataFlowEngine\.builder|DataFlowEngine\(' packages/kailash-dataflow/tests/unit/` returns **zero** matches across the entire unit tier. The recommended-default Engine API is exercised ONLY in integration tier — no smoke test, no parameter validation, no builder-chain assertion runs at tier-1.

**Impact:** Today AND after every S-shard moves. The PR #968 gate, once re-applied via S6, gates DataFlow PRs on a tier-1 surface that excludes the Engine layer entirely. A `DataFlowEngine.builder().slow_query_threshold(...)` API breakage ships green through `/redteam` until the integration tier runs.

**Disposition:** Add a single tier-1 smoke test for `DataFlowEngine.builder()` construction + `.build()` return-shape against `memory_dataflow` fixture, in S5b (already touches the fixture surface). Stays sub-1s; covers the Engine entrypoint.

---

## Finding 2 — API-CONTRACT-RISK — `auto_migrate=True` (engine.py:151 default) regression-test depth thins after S5a

`packages/kailash-dataflow/src/dataflow/core/engine.py:151` declares `auto_migrate: Union[bool, str] = True` (the fail-fast post-#696 default). Tier-1 coverage of THIS default firing under a real event loop (the originating `__del__` deadlock from PR #968) lives in TWO places:

1. `packages/kailash-dataflow/tests/unit/conftest.py:104` — `auto_migrate_dataflow` fixture sets `auto_migrate=True` and yields/closes correctly.
2. `packages/kailash-dataflow/tests/unit/migrations/test_sync_ddl_executor.py:103-128` — `test_ddl_works_inside_async_function` exercises sync-DDL-inside-`asyncio.get_running_loop()` against a `tempfile.NamedTemporaryFile(suffix=".db")` (line 113-114) — this is on the S5a tempfile-removal list (per amendments doc:147-154).

**The risk:** S5a refactors the tempfile path to `memory_dataflow`. The `memory_dataflow` fixture's docstring at `tests/unit/conftest.py:75-89` documents that it specifically fixes the `__del__` deadlock — BUT the test's intent (`# We're inside an async function - event loop is running` line 117-118) is to simulate **module-import-time DDL under uvicorn's running loop**. If S5a refactors to `memory_dataflow`, the fixture wraps the cleanup correctly but the **test setup no longer reflects the FastAPI module-import scenario** the test was written for (line 108-111 docstring).

**Impact:** After S5a, the only tier-1 protection for "engine.py:151's `True` default does not deadlock under uvicorn module-import" is the _fixture's_ implicit yield+close discipline. The original explicit assertion (sync DDL succeeds inside `asyncio.get_running_loop()`) collapses into "the fixture ran cleanly", which is weaker — a regression that breaks the import-time path but happens to clean up correctly via the fixture's `close_async()` will pass tier-1.

**Disposition:** Keep the test's explicit `asyncio.get_running_loop()` assertion (line 118) when refactoring to `memory_dataflow`. Add a regression test in S5a that imports a `@db.model` decorator inside a running `asyncio` event loop and confirms `auto_migrate=True` fires without hanging — preserves the original intent.

---

## Finding 3 — API-CONTRACT-RISK — `db.express` async surface loses tier-1 entirely after S3

Per `framework-first.md` and `specs/dataflow-express.md`, `db.express.{read,list,count,create,update,delete,upsert,find_one,bulk_create,bulk_upsert,bulk_delete}` is the primitive convenience layer (~23x faster than `WorkflowBuilder`). It is the DEFAULT user-facing API per `rules/patterns.md` § DataFlow Express.

Tier-1 coverage of the **async** `db.express.*` surface:

| Test                                                                        | What it covers                                                                                                   |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `tests/unit/fabric/test_context.py:35,43,51` (S3 → integration)             | `ctx.express.list/read/count` — but via `FabricContext.for_testing` (stub, not real)                             |
| `tests/unit/fabric/test_express_pagination.py:65,90,117` (S3 → integration) | `Express.list` order_by — mocks `DataFlowExpress.__new__(DataFlowExpress)` with `db = MagicMock()` (lines 29-43) |

After S3 moves `tests/unit/fabric/` to integration:

- **Zero tier-1 tests exercise `db.express.<method>` against a real `memory_dataflow` fixture.**
- The only surviving tier-1 Express coverage is `db.express_sync.create/list` in `tests/unit/test_derived_model.py:696-863` (3 invocations across 3 derived-model integration tests).

The PR #968 gate (re-applied at S6) gates DataFlow PRs on a tier-1 surface where the Engine default (Finding 1) AND the Express primitive default both have effectively zero coverage. Per `specs/dataflow-express.md` § 3.2 (`read`), § 3.5 (`list`), § 3.7 (`count`) — the spec contracts are unverified at tier-1 once S3 lands.

**Impact:** Compound with Finding 1: after S3 + S2a/b/c/d + S6, the tier-1 gate verifies type-mapping, fixture lifecycle, and node-binding — but NOT the two APIs the docstrings and `framework-first.md` table teach users to use.

**Disposition:** Add a `tests/unit/express/test_express_smoke.py` in S6 (the spec/CLAUDE.md-alignment shard already touches the canonical fixture table per amendments doc:201-204). 6 tests, ~30 LOC, against `memory_dataflow`:

- `await db.express.create("Model", {...})`
- `await db.express.read("Model", id)`
- `await db.express.list("Model", filter={...})`
- `await db.express.count("Model", filter={...})`
- `await db.express.update("Model", id, {...})`
- `await db.express.delete("Model", id)`

Each <1s on in-memory SQLite. Closes the gap without exceeding S6's ≤300 LOC / 5 invariants budget.

---

## Finding 4 — API-CONTRACT-RISK — String-based node API stays tier-1 via `test_workflow_binding.py` ONLY if S2d preserves it

`tests/unit/core/test_workflow_binding.py:109-115` is the **only** tier-1 test that grep-verifies the string-form node-name contract for all 11 auto-generated nodes per model (`UserCreateNode`, `UserReadNode`, `UserListNode`, `UserUpdateNode`, `UserDeleteNode`, `UserListNode`, `UserUpsertNode`, `UserCountNode` + bulk variants). Uses `memory_dataflow` fixture (73 references — `grep -c 'memory_dataflow' tests/unit/core/test_workflow_binding.py` = 73), imports `WorkflowBuilder` at line 35.

This file is in S2d's "Other workflow-importing files (10)" list (amendments doc:81-91) with disposition "MOVE to integration if exercising real workflow, OR refactor with importorskip + mock — heterogeneous, each file's disposition determined at implement-time."

**The risk:** S2d's "MOVE to integration" is the wrong disposition for `test_workflow_binding.py`. The file does NOT exercise real workflow execution — `LocalRuntime` is imported at line 34 but used only inside a `MagicMock` in test 8 (`execute()` delegates to runtime). The actual tested surface is:

- `db._workflow_binder` initialization (43 tests)
- `binder._resolve_node_type("Model", "Op") → "ModelOpNode"` for all 11 operations (test 17, lines 590-624)
- `db.add_node(workflow, model, op, node_id, params)` delegation (tests 12-15)
- `WorkflowBuilder.add_node("ModelOpNode", "node_id", {params})` backward compat (test 16, line 536-555)

All four properties are tier-1-shaped (no I/O, no real workflow exec). Moving this file to integration removes the **only** tier-1 grep on the 11-node-per-model contract documented in `framework-first.md` (DataFlow row, "11 nodes per model (v0.8.0+): CRUD (4) + Query (2) + Upsert + Bulk (4)" per the specialist agent file).

**Impact:** A future refactor that renames `UserCreateNode` → `UserCreateOpNode` ships green through tier-1 until integration runs. Same failure mode as Finding 3 (compounded).

**Disposition:** S2d MUST explicitly classify `test_workflow_binding.py` as STAY-IN-TIER-1 with refactor: remove the unused `LocalRuntime` import (line 34, currently unused outside mocked test 8), gate the one test that touches real runtime under `pytest.importorskip("kailash.runtime")`. The other 19 tests stay tier-1. Same disposition for `tests/unit/core/test_async_sql_sqlite.py` — needs per-file inspection at /implement, NOT blanket move.

Recommend amending S2d's prompt: "Per-file audit — files that import `AsyncLocalRuntime`/`WorkflowBuilder` but use them only for _type assertions_ or _mocked construction_ STAY in tier-1 with `importorskip` gating. Files that actually call `runtime.execute(workflow.build())` MOVE to integration." The amended plan (amendments doc:92-98) hints at this but does not enumerate the binder-vs-runtime distinction the disposition requires.

---

## Finding 5 — FIXTURE-COMPATIBILITY — `BulkUpsertNode` PG-postgresql connection_string in tier-1 is parse-only

`tests/unit/nodes/test_bulk_upsert_conflict_on.py:17-26` constructs `BulkUpsertNode(table_name="test_table", connection_string="postgresql://localhost/test")` and calls `node.get_parameters()`. This is **parse-only** — no `aiosqlite.connect()` / `asyncpg.connect()` fires. The `BulkUpsertNode` constructor stores the connection_string for later use; the test never reaches the use site.

This file is NOT in S4 (PG-audit list) per amendments doc:107-138 — correctly excluded.

**Impact:** None today. But noting it because the pattern (`connection_string="postgresql://..."` in `tests/unit/`) **looks** like a Layer D violation under the grep `specs/testing-tiers.md:188` audits (`grep -rn 'DataFlow(.*postgresql://' tests/unit/`). The PG URL is on `BulkUpsertNode`, not `DataFlow`, so the grep doesn't match — but `/redteam` mechanical sweeps that broaden to any `postgresql://` string will false-positive.

**Disposition:** None required for S4. Document in S6's CLAUDE.md update (`tests/unit/CLAUDE.md`) that PG URLs inside `*Node(connection_string=...)` constructors that NEVER call `.execute()` are tier-1-acceptable — same exemption shape SQLite uses already. Prevents next-cycle false-positive triage.

---

## Finding 6 — PORTABILITY-GAP — PostgreSQL array / JSONB type-mapping tests are PARSE-ONLY (no real PG)

`tests/unit/core/test_postgresql_array_types.py:147-447` and `tests/unit/core/test_dataflow_2026_001_fixes.py:29-82` test `dataflow._python_type_to_sql_type(List[str], "postgresql") == "JSONB"` — pure function calls on a `DataFlow("sqlite:///:memory:", auto_migrate=False)` instance (test_dataflow_2026_001_fixes.py:25-27). No PG connection, no JSONB execution; just dialect string-mapping verification.

These files are NOT on any S-shard move list (correctly). They are tier-1-clean.

**Impact:** Verifies the spec'd type-mapping contract per `specs/dataflow-cache.md` (dialect system) at tier-1 without real PG. Survives all moves.

**Disposition:** NEUTRAL — no action.

---

## Finding 7 — API-CONTRACT-RISK — Multi-tenant invariant tests stay tier-1, but classification-redaction does NOT

Per `specs/dataflow-models.md:260-291` and `rules/tenant-isolation.md`, multi-tenant invariants on `DataFlow(..., multi_tenant=True)` and the classification redaction helpers are load-bearing security promises. Tier-1 coverage:

| Concern                                                                     | Tier-1 file                                                                                                                                         | Disposition under S-shards     |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `TenantContextSwitch` API                                                   | `tests/unit/core/test_tenant_context.py` (20 tests, line 34)                                                                                        | STAYS (not on any move list)   |
| `TenantRequiredError` alias                                                 | `tests/unit/test_tenant_required_error_alias.py`                                                                                                    | STAYS                          |
| Cache-key v2 keyspace + tenant                                              | `tests/unit/cache/test_redis_invalidate_v2_keyspace.py:50-88`                                                                                       | STAYS                          |
| `apply_read_classification`                                                 | `tests/unit/test_apply_read_classification.py`                                                                                                      | STAYS                          |
| Express mutation-return redaction (per `dataflow-classification.md` MUST-1) | **No tier-1 file** — only in `tests/integration/security/test_event_payload_classification.py` (per `rules/event-payload-classification.md` Origin) | N/A — already integration-only |

**Impact:** The dataflow-classification rule mandates Tier-2 tests per mutation (Rule 3) — this is structurally correct. BUT: `tests/unit/cache/test_cache_invalidation.py:35-37` has a fixture importing `IntegrationTestSuite` AND tests marked `@pytest.mark.integration` (line 46) inside `tests/unit/` (amendments doc line 113 catches this — S4 moves the file). The mismatch is more severe than amendments doc claims: the file imports `IntegrationTestSuite` at line 35 but the symbol isn't even imported at the top of the file — likely a botched copy-paste that suggests collection failure on clean install. Verify at /implement.

**Disposition:** S4 must verify `tests/unit/cache/test_cache_invalidation.py` is the file referenced — the path matches but the harness fixture begins at line 32, not the file `cache_invalidation_bug.py` (which is a different file). Cross-reference: amendments doc line 113 reads `tests/unit/cache/test_cache_invalidation.py (uses IntegrationTestSuite)` — verified file:line 35.

---

## Finding 8 — FIXTURE-COMPATIBILITY — `test_lazy_connection.py` deliberate PG URLs are tier-1-correct

`tests/unit/core/test_lazy_connection.py:24,43,73,136,156,171,189` uses `"postgresql://nonexistent:password@192.0.2.1:5432/fake_db"` to **prove no connection fires** at `DataFlow.__init__()` (issue #171). The IP `192.0.2.1` is RFC 5737 documentation space — guaranteed unreachable, so any successful test confirms the lazy-connection contract.

This file is on S4's per-file-audit list (amendments doc:133-138) tagged "(new from inventory red-team)".

**Impact:** This is a TIER-1-LEGITIMATE PG URL — the test's purpose IS that no real PG connection happens. Moving to integration would invert the test's contract (integration tier runs against real PG at :5434, so the test would actually connect).

**Disposition:** S4 MUST classify `test_lazy_connection.py` as STAY-IN-TIER-1. Add an inline pytest comment or marker (`@pytest.mark.unit` + comment "documentation IP — no real connection") to prevent future-cycle re-triage. Per `rules/dataflow-pool.md` Rule 2 ("Validate Pool Config AND Reachability at Startup"), `enable_connection_pooling=False` kwarg at line 27 is the load-bearing signal that bypasses startup validation — the test deliberately exercises this branch. Preserving it at tier-1 protects the issue #171 regression.

Same shape for `test_logging_config.py` / `test_logging_levels.py` (also on S4's audit list, lines 134-135) — need per-file audit at /implement to distinguish "deliberate unreachable URL" from "real PG attempt."

---

## Finding 9 — API-CONTRACT-RISK — Bulk ops (`bulk_create`, `bulk_upsert`) tier-1 thin

Per `specs/dataflow-express.md` § "Bulk Operations" and `framework-first.md` DataFlow row, bulk ops are first-class.

Tier-1 coverage today:

- `tests/unit/nodes/test_bulk_upsert_conflict_on.py:41-60` — deduplicate-batch-data logic only (no real DB).
- `tests/unit/core/test_auto_generated_bulk_parameter_mapping.py:27-209` — parameter-shape only (data/records/rows/documents aliases per node).
- `tests/unit/core/test_type_processor.py:516,537,666` — TypeProcessor's bulk_create operation (in-memory list transforms).

ZERO tier-1 tests exercise `db.express.bulk_create("Model", [rows])` or `db.express.bulk_upsert("Model", [rows], conflict_on=[...])` against `memory_dataflow`. The WARN-on-partial-failure contract (`rules/observability.md` Rule 7 + `specs/dataflow-express.md` § 3.10 line 350 "Returns list of created records. Logs WARN on partial failure") has no tier-1 grep.

**Impact:** Same compound risk as Finding 3 — after S-shards, bulk ops are tier-1-tested only at the parameter-shape layer. A regression in the partial-failure WARN emission (per `observability.md` MUST Rule 7) ships green through tier-1.

**Disposition:** Add to the express-smoke shard recommended in Finding 3:

- `await db.express.bulk_create("Model", [{...}, {...}])` — assert returned list length matches input
- Inject a deliberate duplicate-PK row; capture `caplog.records`; assert one record has level WARN with `bulk_create.partial_failure` event (per `observability.md` Rule 7 DO example).

~10 LOC. Stays sub-1s.

---

## Finding 10 — NEUTRAL — `query/conftest.py:5-10` stale workaround correctly folded into S5b

Amendments doc:163-181 documents the `tests/unit/query/conftest.py:5-10` stale `Node`-import workaround. Independent verification (journal/0002 line 134-141): `python -c "from kailash.nodes.base import Node; print('OK')"` exits 0 on current main. The workaround is stale.

Per `rules/zero-tolerance.md` Rule 4, this is a workaround for an SDK issue that no longer exists — BLOCKED disposition is to delete.

**Impact:** S5b's "while-here cleanup" framing is correct AND well-bounded.

**Disposition:** NEUTRAL — accept S5b's disposition.

---

## Summary table

| #   | Finding                                                               | Classification        | Affected shard(s)     | Suggested fix                                                   |
| --- | --------------------------------------------------------------------- | --------------------- | --------------------- | --------------------------------------------------------------- |
| 1   | `DataFlowEngine.builder()` zero tier-1 coverage                       | API-CONTRACT-RISK     | S5b or new mini-shard | Add Engine smoke test in S5b                                    |
| 2   | `auto_migrate=True` event-loop scenario thins after S5a               | API-CONTRACT-RISK     | S5a                   | Preserve `asyncio.get_running_loop()` assertion in refactor     |
| 3   | `db.express` async surface zero tier-1 after S3                       | API-CONTRACT-RISK     | S3 + S6               | Add `tests/unit/express/test_express_smoke.py` in S6            |
| 4   | String-based node API tier-1 coverage at risk in S2d                  | API-CONTRACT-RISK     | S2d                   | Classify `test_workflow_binding.py` STAY-IN-TIER-1              |
| 5   | `BulkUpsertNode(connection_string=PG)` parse-only false-positive risk | FIXTURE-COMPATIBILITY | S6 (CLAUDE.md update) | Document exemption for parse-only constructors                  |
| 6   | PG type-mapping tests are PARSE-ONLY                                  | NEUTRAL               | none                  | No action                                                       |
| 7   | Multi-tenant invariants stay tier-1 correctly                         | NEUTRAL (mostly)      | S4 verify file:line   | Verify `test_cache_invalidation.py` is the intended move-target |
| 8   | `test_lazy_connection.py` deliberate PG URLs are correct              | FIXTURE-COMPATIBILITY | S4                    | Classify STAY-IN-TIER-1 with inline-marker                      |
| 9   | Bulk ops + WARN-on-partial-failure zero tier-1                        | API-CONTRACT-RISK     | S6 (or S3 follow-up)  | Extend express-smoke shard with bulk_create + caplog WARN       |
| 10  | `query/conftest.py` stale workaround                                  | NEUTRAL               | S5b                   | Accept disposition                                              |

## Net recommendation for /todos human gate

Three amendments to the existing plan, none expanding shard count past 10:

1. **S2d disposition matrix** — per-file STAY-vs-MOVE classification at /implement time, with `test_workflow_binding.py`, `test_async_sql_sqlite.py`, `test_strict_mode_*.py` as known STAY-IN-TIER-1 (refactor with `importorskip`, remove unused runtime imports, leave the 11-node mapping grep). Same approach for `test_lazy_connection.py` / `test_logging_config.py` / `test_logging_levels.py` in S4.

2. **S6 express-smoke addition** — single new file `tests/unit/express/test_express_smoke.py` with 7 tests against `memory_dataflow`: create, read, list, count, update, delete, bulk_create (with caplog WARN assertion). ~50 LOC, ~3s total. Closes Findings 1+3+9 in one delivery.

3. **S5a `__del__`-deadlock preservation** — when refactoring `test_sync_ddl_executor.py:103-128` to `memory_dataflow`, KEEP the explicit `asyncio.get_running_loop()` assertion and add a regression test that imports `@db.model` inside a running event loop. Preserves the originating regression-test intent.

Total scope addition: ~70 LOC, ~5 invariants, single shard budget — fits S6 cleanly. The three amendments lift the tier-1 gate from "fixture lifecycle + node-name grep" to "fixture lifecycle + node-name grep + Engine smoke + Express smoke + bulk smoke + auto_migrate event-loop regression" — covering the four DataFlow APIs the spec teaches users to use.
