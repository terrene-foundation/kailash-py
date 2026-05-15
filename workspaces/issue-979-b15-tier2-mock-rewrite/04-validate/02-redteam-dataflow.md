# DataFlow Red Team — #992 Architecture Plan

## Verdict (from DataFlow lens)

REJECT — the plan ships duplicate test coverage of an existing real-PG suite and is structurally inconsistent with three load-bearing DataFlow facts the plan never surfaces. See DF-1 (parity duplication, CRIT), DF-2 (lock semantics misframed, HIGH), and DF-3 (lifespan-proxy test is structurally untenable on SQLite, HIGH). With DF-1 / DF-2 / DF-3 / DF-4 resolved, the split-shard restructure is sound and APPROVE-WITH-FIXES is reachable in one shard.

## Findings

### [DF-1 type:CRIT] — Shard 2 duplicates an EXISTING real-PG suite; current `migration/` already covers the rewrite

The plan presents Shard 2 as creating "new Tier-2 wiring" for `MigrationLockManager` against real PG. A real-PG integration suite already exists at `packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py` (singular `migration/`, not the plural `migrations/` directory where the mocked File 6 lives). That file:

- imports `IntegrationTestSuite` (lines 17-29)
- runs against real PostgreSQL via `asyncpg` (line 17, fixture lines 49-56)
- has `TestRealPostgreSQLLocking` covering all four scenarios the plan claims to add: lock table creation (lines 104-136), successful acquisition (138-156), conflict prevention via two-`MigrationLockManager`-instances-same-adapter (158-181), release + re-acquisition (183-241), check_status (243-261), expired-lock cleanup (263-298)
- contains zero `@patch` / `MagicMock` / `AsyncMock` references

The plan's value-anchor for Shard 2 — "MigrationLockManager wiring tests don't exist against real PG" — is **factually wrong**. The wiring already ships, in a sibling directory the classification audit did not enumerate. Shipping `tests/integration/migrations/test_migration_lock_manager_wiring.py` per the plan creates two parallel real-PG suites for the same manager with overlapping coverage. Per `rules/orphan-detection.md` § "Removed = Deleted, Not Deprecated" and `rules/refactor-invariants.md` (test-suite duplication = institutional drift), this is BLOCKED.

**Correct disposition**: Shard 2 splits File 6 into (a) the Tier-1 param-conversion file as planned AND (b) DELETES the mocked `tests/integration/migrations/test_migration_lock_manager_integration.py` outright — the real-PG counterpart already lives at `tests/integration/migration/test_migration_lock_manager_integration.py`. No new Tier-2 file is created; the orchestrator MUST cite the existing path in the workspace journal `DECISION-shard-classifications.md` so the next session does not re-discover the duplication.

Additionally, `tests/integration/migration/test_concurrent_migration_safety.py` (lines 51-167) already exercises advisory-lock-based concurrent acquisition through `asyncio.gather` against real PG — closing the "concurrent acquire blocks" scenario the plan's Shard 2 invariant 4 claims to introduce.

### [DF-2 type:HIGH] — Lock semantics are row-level, not PG advisory; the plan's "concurrent acquire test design" question is misframed

The plan's red-team question 1 asks whether `MigrationLockManager.migration_lock` uses "advisory PG lock" or "row-level lock". The source at `src/dataflow/migrations/concurrent_access_manager.py` makes this unambiguous:

- the table is `dataflow_migration_locks` (lines 183-202), NOT `kml_migration_locks` as the prompt's question 4 names it
- acquisition is `INSERT ... ON CONFLICT DO NOTHING` (PG, lines 256-261) / `INSERT OR IGNORE` (SQLite) / `INSERT IGNORE` (MySQL) against that row
- "ownership" is verified by a second `SELECT WHERE schema_name = $1 AND holder_process_id = $2` (lines 280-298) which confirms the insert won, not a `pg_advisory_lock`
- the lock is row-level, expressed via a UNIQUE constraint on `schema_name`, scoped by `expires_at` (lines 414-417) — NOT a PG session-bound advisory lock
- works across DataFlow instances, processes, and hosts (anything sharing the same DB), NOT scoped to one pool

The plan's invariant 4 phrasing ("UNIQUE violation surfaces as real PG error from `kml_migration_locks` table") is doubly wrong: (a) the table is `dataflow_migration_locks`, not `kml_migration_locks`; (b) the UNIQUE violation does not "surface as a real PG error" because `ON CONFLICT DO NOTHING` swallows it — the second acquire returns `False`, not an exception. The plan's "concurrent acquire test design" question presupposes ambiguity that does not exist in the source; the existing `test_concurrent_migration_safety.py:131-142` shows the canonical `asyncio.gather` pattern against `MigrationLockManager` instances sharing one `ConnectionManagerAdapter`. Pool size 2 suffices because each acquire is one connection one statement, no held-lock state on the connection.

**Correct disposition**: if Shard 2 ships any new test (after DF-1 resolution makes that ship-or-skip), it MUST use `dataflow_migration_locks` as the table name, MUST NOT assert on a raised PG exception for second acquire (assert `acquired_2 is False`), and MUST follow `test_concurrent_migration_safety.py`'s `asyncio.gather` shape.

### [DF-3 type:HIGH] — `test_simulated_fastapi_lifespan` against real PG is not a meaningful proxy; the fake-FastAPI scaffold is the test

The plan's Shard 3 promises to "rewrite `test_simulated_fastapi_lifespan` against real PG ... at the platform where the bug was originally reported." Reading the SUT at `src/dataflow/migrations/auto_migration_system.py:40-114`:

- the helper does NOT use `async_safe_run` anymore (docstring lines 44-57 explicitly state the v0.10.11 fix REPLACED `async_safe_run` with synchronous `SyncDDLExecutor`)
- the bug class the helper was created to fix ("Task got Future attached to a different loop") IS structurally impossible against the current implementation — there is no event loop bridging
- `_execute_workflow_safe` is now a thin dispatcher over `SyncDDLExecutor(connection_string)` using sync `psycopg2` / `sqlite3` — both work identically against PG and SQLite

Per `rules/spec-accuracy.md` MUST Rule 1 (every citation resolves against working code), the plan's claim that PG is "the platform where the bug actually manifests" is **stale**: the bug class was closed by removing event-loop bridging entirely. Running `test_original_bug_scenario` against real PG does not "prove the fix at the platform where the bug was originally reported"; it proves nothing the current SQLite-memory test does not already prove, because the current code does not bridge event loops on either backend.

Worse, the existing `test_simulated_fastapi_lifespan` (lines 662-684 of File 4) does not simulate FastAPI lifespan — it constructs a `DataFlow("sqlite:///:memory:")`, calls `await db.initialize()` inside `@pytest.mark.asyncio`, and swallows every exception (`except Exception: pass`). It is a "no-hang" smoke test, not a lifespan reproduction. Per `rules/zero-tolerance.md` Rule 3 (silent error swallowing BLOCKED), this test should be REJECTED as a Tier-2 candidate — porting it to real PG would carry the same `except Exception: pass` defect.

There is no canonical "real-ASGI-lifespan-against-real-PG" pattern in `tests/integration/` — grep confirms zero `from fastapi.testclient` / `httpx.AsyncClient` / `lifespan` matches across `packages/kailash-dataflow/tests/integration/`. Creating a precedent here is out of scope for #992's stated value-anchor (Tier-2 contract restoration of EXISTING tests, not net-new lifespan coverage).

**Correct disposition**: Shard 3's `test_async_safe_run_postgres.py` MUST ship only `test_original_bug_scenario` (which has a real-PG-meaningful read-back assertion: `assert "bug_repro" in results`), AND only if the workspace decides PG-on-the-same-no-event-loop-bridging path adds independent value. `test_simulated_fastapi_lifespan` MUST be DELETED from the file outright per `rules/orphan-detection.md` Rule 3 (Removed = Deleted, not deprecated). The plan's claim that Shard 3 "closes the platform-coverage gap" is rejected; restate the value-anchor as "removes a swallow-exception smoke test that violates zero-tolerance Rule 3."

### [DF-4 type:HIGH] — `pool_size=2, max_overflow=2` is sized for an unrelated workload class; cite the harness reason explicitly OR drop the pin

The harness reference doc (§ 4.4) cites `pool_size=2, max_overflow=2` as the mitigation for "9 independent `DataFlow` instances saturating PG `max_connections`." That sizing comes from `test_classification_mutation_return.py:81-86` where 9 DataFlow instances run in one test. Shard 2's tests do NOT construct 9 DataFlow instances — they construct one `ConnectionManagerAdapter` (which wraps zero pools, see `MockDataFlowForTesting` at `test_migration_lock_manager_integration.py:42-46`) and two `MigrationLockManager` instances sharing it. Pinning `pool_size=2` on a `DataFlow` instance that the lock-manager test path never uses is cargo-cult: the existing real-PG test (which DF-1 cites) constructs no `DataFlow` at all — it uses `ConnectionManagerAdapter(MockDataFlowForTesting(url))` directly. The plan's invariant 1 sub-bullet "Real `DataFlow(test_suite.config.url, pool_size=2, max_overflow=2)` per harness contract" prescribes a pattern that does not match the SUT and adds connection overhead the test does not need.

**Correct disposition**: if Shard 2 ships any new tests (post-DF-1), follow the EXISTING pattern in `tests/integration/migration/test_migration_lock_manager_integration.py:42-97` (mock-DataFlow-config + real-PG ConnectionManagerAdapter), NOT the plan's `DataFlow(url, pool_size=2)` invocation. If the plan's authors believe a full `DataFlow` instance is required, they MUST cite the SUT call site that proves the manager needs an initialized DataFlow pool — none exists.

### [DF-5 type:MED] — Schema-setup question 4 references the wrong table name (`kml_migration_locks` does not exist)

The prompt's question 4 asks whether `kml_migration_locks` exists by default in `IntegrationTestSuite`-provisioned DBs. No such table exists in `packages/kailash-dataflow/src/dataflow/migrations/`. The actual table is `dataflow_migration_locks` (see DF-2). The `_kml_*` table-name prefix belongs to `kailash-ml` (per `journal/0004-DISCOVERY-three-way-schema-drift-mandates-migration-0005.md` cited in `rules/schema-migration.md` Rule 1a), not to DataFlow migrations. The harness does NOT pre-create the migration-lock table; `MigrationLockManager._ensure_lock_table()` (lines 179-210) creates it lazily on first `acquire`. The existing test at `test_migration_lock_manager_integration.py:104-115` verifies this lazy-create behavior directly; the plan does not need to re-derive it.

**Correct disposition**: any new test (post-DF-1) MUST NOT call `setup_dataflow_schema()` (no such helper exists in `IntegrationTestSuite` — the harness exposes `TableFactory.create_*` for application tables, not migration-control tables) and MUST NOT pre-create `dataflow_migration_locks` in fixtures; the lock manager owns its own creation.

### [DF-6 type:MED] — Shard 3 invariant 2 over-claims; the SUT no longer carries event-loop-bridging bug class

Per DF-3, the helper does not bridge event loops in v0.10.11+. Shard 3 invariant 2 says the new file will "prove the fix at the platform where the bug was originally reported." The fix landed by REMOVING the bridging entirely; there is no platform-specific behavior left to prove. Restating the invariant to a fact-anchored form ("`test_original_bug_scenario` runs against real PG without hang or exception, demonstrating the v0.10.11 sync-DDL path works against the production database backend") is acceptable; the current phrasing implies an event-loop bug class that no longer exists, which `rules/spec-accuracy.md` Rule 1 BLOCKS.

### [DF-7 type:LOW] — Shard 2/3 invariant counts use grep, not AST; counts of param-conversion tests should use `pytest --collect-only`

Per `rules/testing.md` § "MUST: `__all__` / Re-export Symbol Counts Use Structural Enumeration, Not Grep" applied to test enumeration, the invariants "Param-conversion test count in new Tier-1 file equals original count in File 6's two extracted classes" should specify the verification command: `pytest --collect-only -q tests/unit/migrations/test_connection_adapter_param_conversion.py | grep -c '::test_'` AND `pytest --collect-only -q tests/integration/migrations/test_migration_lock_manager_integration.py::TestConnectionManagerAdapter tests/integration/migrations/test_migration_lock_manager_integration.py::TestParameterConversionEdgeCases | grep -c '::test_'`. Without an explicit invariant verification command, count drift is invisible at PR review.

### [DF-8 type:LOW] — Shard 4 collect-only sweep does not cover the new Tier-1 destination

Shard 4 invariant 2 runs `pytest --collect-only tests/integration --collect-only -q`. The new Tier-1 files land at `tests/unit/migrations/` (Shard 2) and `tests/unit/migrations/` (Shard 3, with name `test_async_safe_run.py`). Per `rules/orphan-detection.md` Rule 5 (Collect-Only Is A Merge Gate), the gate MUST also collect `tests/unit/` to confirm the new files collect cleanly. Add `pytest --collect-only -q packages/kailash-dataflow/tests/unit/migrations/`.

### [DF-9 type:LOW] — No mention of `tests/integration/migrations/__init__.py` deletion impact

Per `find` enumeration, `tests/integration/migrations/` contains 5 files; Shard 2 and Shard 3 each delete one. There is no `__init__.py` in `tests/integration/migrations/` (the find listing confirms). The plan does not need to handle init-file deletion, but this MUST be confirmed in the Shard 4 verification gate to close the prompt's question 7 — and the prompt's question 7 phrasing about "fixture-discovery logic" should be answered: pytest does NOT require `__init__.py` for test discovery in this layout; there is no impact.

### [DF-10 type:LOW] — `db.express` / no raw-SQL audit

Per `rules/framework-first.md` § Specialist Consultation table and `rules/dataflow-identifier-safety.md` Rule 1, the plan does NOT introduce any raw SQL, ORM workaround, or `@db.workflow` bypass. The new test files (if they ship per DF-1/DF-3 resolution) construct `ConnectionManagerAdapter` directly — that adapter IS the framework's connection abstraction for migrations and is the canonical surface for `MigrationLockManager`. No anti-pattern detected.

## Summary of REQUIRED fixes before Shard plan can proceed

1. **DF-1 (CRIT)**: drop Shard 2's "new Tier-2 wiring file" sub-task; cite `tests/integration/migration/test_migration_lock_manager_integration.py` and `tests/integration/migration/test_concurrent_migration_safety.py` as the existing coverage; Shard 2 becomes (a) extract Tier-1 param-conversion to `tests/unit/migrations/`, (b) delete `tests/integration/migrations/test_migration_lock_manager_integration.py`.
2. **DF-2 (HIGH)**: if any new test ships, use `dataflow_migration_locks` (not `kml_migration_locks`); assert `False` on second acquire (not raised exception).
3. **DF-3 (HIGH)**: Shard 3 MUST delete `test_simulated_fastapi_lifespan` outright; ship only `test_original_bug_scenario` against real PG if there is independent value, with a fact-anchored value-anchor (NOT "the platform the bug manifests"); update the value-anchor citation per `rules/spec-accuracy.md` Rule 1.
4. **DF-4 (HIGH)**: any new test MUST follow the existing `ConnectionManagerAdapter(MockDataFlowForTesting)` pattern, NOT `DataFlow(url, pool_size=2)` cargo-cult sizing.

With those four fixes the plan re-converges to APPROVE-WITH-FIXES and is one-shard implementable.
