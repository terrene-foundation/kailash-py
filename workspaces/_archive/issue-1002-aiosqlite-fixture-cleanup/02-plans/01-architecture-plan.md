# Architecture plan — #1002 aiosqlite/connection fixture cleanup

Date: 2026-05-14
Phase: /analyze

Brief: `briefs/00-brief.md` (verbatim from `gh issue view 1002` body; value-anchor source b — workspace brief).

## Brief corrections (gate before /todos)

Per `rules/agents.md` § "Parallel Brief-Claim Verification" — these corrections MUST be acknowledged before /todos. Full evidence in `journal/0001-DISCOVERY-hang-reproduces-and-brief-corrections.md` and `journal/0002-CONNECTION-redteam-findings.md`.

1. **`async with DataFlow(...) as db:` is NOT supported.** DataFlow exposes `__enter__` / `__exit__` (sync), `close()`, `close_async()`. No `__aenter__` / `__aexit__`. Canonical migration template is the existing `packages/kailash-dataflow/tests/unit/conftest.py:80-108` pattern: `try: yield / finally: await dataflow.close_async()`.
2. **Scope is test-body inline constructions, not conftest fixtures.** Root conftest is already canonical. The cleanup is ~270 inline `DataFlow(...)` calls across ~50+ test files.
3. **`__del__` no longer deadlocks.** Post-PR #1001 it emits `ResourceWarning` only. The hang root cause is aiosqlite background threads kept alive by un-closed connections at `_Py_Finalize` time — distinct from #1000's logging-lock deadlock.
4. **Spec contract already lives at `specs/testing-tiers.md` §2 (lines 42-86, amended 2026-05-14).** The work here is to make the test code converge with the existing spec — NOT to write a new `specs/dataflow-test-fixtures.md`. Per `rules/spec-accuracy.md` Rule 5, specs describe shipped behavior; the spec already mandates fixture-managed cleanup, the issue is enforcement on inline constructions.
5. **Surface includes Redis / MySQL / Mongo async adapters, not just `DataFlow(`.** Brief Shard 1 explicitly mentions `AsyncRedisCacheAdapter`. Grep finds 8 unit-test files importing `redis.asyncio` / `aiomysql` / `motor`. Any inline construction of these without `await close()` reproduces the same `_Py_Finalize` thread-leak class — Shard surface MUST cover all three.

## Failure surface

Empirically reproduced: pytest test phase completes in ~93s, then process hangs ~10 min in state `S` (sleeping/blocked) before SIGKILL. The CI `setsid` wrapper at `.github/workflows/unified-ci.yml:251-289` masks this by killing the process group after the success summary line appears.

## Approach — fixture / inline-construction migration

Each test that constructs `DataFlow(...)` inline must either:

- **A. Adopt an existing fixture** (`memory_dataflow`, `file_dataflow`, `auto_migrate_dataflow`) when the URL pattern matches; OR
- **B. Add a local fixture** to the file's conftest using the canonical `try/finally: await close_async()` shape; OR
- **C. Wrap in `with DataFlow(...) as db:`** (sync context manager) inside sync test bodies where adding a fixture is overkill.

Option A is preferred. Option C is acceptable for small test bodies; option B is the bridge case for parameterized inline URLs.

Async tests that need cleanup but cannot adopt a fixture (e.g., they construct multiple DataFlow instances within one test) MUST use explicit `try / finally: await db.close_async()` inside the test.

## Sharded plan (per `autonomous-execution.md` § Per-Session Capacity Budget)

Each shard stays within ≤500 LOC load-bearing, ≤5-10 invariants, ≤3-4 call-graph hops, describable in 3 sentences. Each shard carries a value-anchor citing `briefs/00-brief.md:38-42` verbatim per `value-prioritization.md` MUST-6.

### Shard-0 entry decision — conftest-stub pattern REJECTED with rationale

`rules/testing.md` § "Tier-1 Conftest Stub for Newly-Side-Effecting Internal Methods" defines an autouse-fixture pattern that monkeypatches a method to collapse N call sites into 1. **Not applicable here.** That pattern targets methods whose side effects are stubbed for Tier-1 isolation (LLM/DB/network calls); we want the OPPOSITE — real DataFlow construction with proper cleanup. Monkeypatching `DataFlow.__init__` to register cleanup automatically would (a) hide the cleanup contract from test authors, (b) break tests that assert on real init-time behavior, and (c) create a global side-effect class that survives across the conftest scope. Decision: per-test fixture adoption is the correct migration; record this rejection here so a future `/codify` does not re-propose the pattern.

### Do-not-touch list (applies to all shards)

These files intentionally exercise the un-closed-DataFlow / `__del__` warning path. Migration agents MUST NOT modify them:

- `packages/kailash-dataflow/tests/unit/test_del_no_close.py`
- `packages/kailash-dataflow/tests/unit/features/test_resource_warning.py`
- Any other test whose name contains `_resource_warning`, `_del_no_close`, `_del_warning`, or that wraps `DataFlow(...)` inside `with pytest.warns(ResourceWarning)`.

### Shard 1 — High-concentration files (~300 LOC, 1 session)

Files: `test_derived_model.py`, `test_dataflow_bug_011_012_fixes.py`, `test_engine_migration_errors.py`, `core/test_dataflow_test_mode.py`, `test_cache_invalidation_bug.py`.

**Tempfile cross-listing**: 3 files in `tests/unit/` use `tempfile.*` (`migrations/test_migration_performance_tracker.py`, `testing/test_performance_regression_suite.py`, `context_aware/test_instance_isolation.py`). None overlap Shard-1's hot-spot list, but Shard-1 sites that introduce a tempfile MUST close DataFlow BEFORE `os.unlink()` / tempfile context exit.

Value-anchor (verbatim from `briefs/00-brief.md:38-39`): "Test fixtures explicitly close `DataFlow`/connection instances" and "Local pytest exits cleanly (no `_Py_Finalize` hang) within 2 min". This shard converts the heaviest leak sites, where ~45 of the ~270 inline calls live.

Invariants: (1) every replaced site closes via fixture or explicit `close_async()`; (2) no test in scope changes behavior; (3) sync-vs-async test signature preserved; (4) per-test isolation preserved (no shared state introduced); (5) regression assertion in same commit; (6) do-not-touch list respected; (7) tempfile-using sites close DataFlow before unlink.

Deliverables: file edits + commit. No CI wrapper changes yet.

### Shard 2 — Mid-concentration DataFlow + Redis/MySQL/Mongo adapters (~250 LOC, 1 session)

Files: subdirectories with 2–5 inline constructions per file — `cache/`, `migrations/`, `security/`, `query/`, `ml/`, `model_registry/`, `nodes/`, `features/`. **Plus** the 8 files with non-DataFlow async-resource constructions: `cache/test_async_redis_adapter.py`, `cache/test_redis_invalidate_v2_keyspace.py`, `cache/test_auto_detection.py`, `core/test_pool_utils.py`, `test_cache_invalidation_bug.py`, `adapters/test_mysql_adapter.py`, `adapters/test_mongodb_adapter.py`, `adapters/test_mysql_transaction_hardening.py`.

Value-anchor (verbatim from `briefs/00-brief.md:38`): "Test fixtures explicitly close `DataFlow`/connection instances". For non-DataFlow adapters, the closure is `await adapter.close()` / `await client.aclose()` per each adapter's documented contract.

Invariants: same seven as Shard 1, plus (8) Redis/MySQL/Mongo adapter constructions either use a fixture with teardown OR call `await close()` in a `finally` block.

### Shard 3 — Low-concentration files + tail + asyncio-mark hygiene (~150 LOC, 1 session)

All remaining files with ≤2 inline constructions each. Also addresses the `PytestWarning` at `tests/unit/testing/test_performance_regression_suite.py:717` (mismatched `@pytest.mark.asyncio` on sync function) per `zero-tolerance.md` Rule 1.

Value-anchor (verbatim from `briefs/00-brief.md:39`): "Local pytest exits cleanly (no `_Py_Finalize` hang) within 2 min" — verifiable at end of this shard via the local-repro gate (no setsid wrapper) before Shard 4 entry.

Invariants: same eight as Shard 2.

### Shard 4 — Remove `setsid` wrapper + regression test + CHANGELOG (~50 LOC, 1 session)

**Entry gate**: BEFORE editing `unified-ci.yml`, run `time .venv/bin/python -m pytest packages/kailash-dataflow/tests/unit/ -q --timeout=120` locally and verify total wall-clock ≤120s with exit 0. If the post-summary hang reproduces, return to Shard 1-3 to find the missed leak. Skipping this gate ships a CI hang on Shard 4's PR.

File 1: `.github/workflows/unified-ci.yml:251-289` — restore plain pytest invocation.

File 2: `packages/kailash-dataflow/tests/regression/test_pytest_exits_clean.py` — invokes `subprocess.run(["python", "-m", "pytest", "tests/unit/cache/", "-q", "--timeout=60"], timeout=300)` on a representative subset (`tests/unit/cache/` chosen as it covers the Redis/SQLite cleanup paths surfaced as highest-risk in Shard 2; small enough to run in <60s; large enough to expose regression). Asserts `proc.returncode == 0` AND `proc total wall-clock ≤90s`. `@pytest.mark.regression`. Lives in the dataflow sub-package's `tests/regression/` directory (not root).

Value-anchor (verbatim from `briefs/00-brief.md:40-42`): "Remove the `setsid` + 150s polling wrapper from `unified-ci.yml::test-dataflow`; restore plain pytest invocation"; "Same-PR regression: `tests/regression/test_pytest_exits_clean.py` asserts pytest completes within timeout"; "CHANGELOG entry on the release that lands the fix".

Invariants: (1) entry-gate local repro passes pre-edit; (2) CI passes without setsid; (3) regression test prevents future regression; (4) CHANGELOG entry references this issue; (5) `release/v*` branch convention per `rules/git.md`.

## Acceptance criteria (verbatim from #1002 brief)

- [ ] Test fixtures explicitly close `DataFlow`/connection instances (Shards 1–3).
- [ ] Local pytest exits cleanly (no `_Py_Finalize` hang) within 2 min (verified end of Shard 3).
- [ ] Remove the `setsid` + 150s polling wrapper from `unified-ci.yml::test-dataflow`; restore plain pytest invocation (Shard 4).
- [ ] Same-PR regression: `tests/regression/test_pytest_exits_clean.py` asserts pytest completes within timeout (Shard 4).
- [ ] CHANGELOG entry on the release that lands the fix (Shard 4 release-prep PR).

## Cross-SDK note (per `rules/cross-sdk-inspection.md` MUST-1)

This is a Python-specific aiosqlite cleanup. The Rust SDK uses tokio + sqlx and has different fixture lifecycle. Per `rules/repo-scope-discipline.md`, this note is informational only — the user (not this session) decides whether to open a parallel investigation in a `kailash-rs` session.

## Specs update — already landed

`specs/testing-tiers.md` §2 (lines 42-86) already mandates the canonical fixture contract. This session amended that section in-place (commit pending) to (a) cite `packages/kailash-dataflow/tests/unit/conftest.py:80-108` as the canonical shape, (b) document that DataFlow has no `__aenter__`, (c) explain the `_Py_Finalize` hang root cause and reference issue #1002 + `rules/patterns.md` § "Async Resource Cleanup". Per `rules/spec-accuracy.md` Rule 5, the spec describes what ships today; Shards 1-4 bring code into compliance with the existing spec. NO new spec file.

## Risks

- **Risk 1**: Test bodies that construct multiple DataFlow with non-uniform URLs may resist fixture adoption. Mitigation: option C (sync `with`) covers most; option B (local conftest fixture with parameter) covers the rest.
- **Risk 2**: Some inline tests assert `__del__`-emitted `ResourceWarning` semantics. Mitigation: those tests stay un-migrated — they are testing the warning, not the fixture pattern.
- **Risk 3**: Removing setsid wrapper in Shard 4 before Shard 3 lands re-opens the hang. Mitigation: strict shard sequencing; Shard 4 depends on Shards 1–3 all merged.
