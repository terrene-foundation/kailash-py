# Research — fixture surface for #1002

Date: 2026-05-14
Phase: /analyze
Source: parallel deep-dive agent + targeted grep verification (paths/lines cited from live source).

## Existing canonical pattern (DO use as migration template)

File: `packages/kailash-dataflow/tests/unit/conftest.py`

| Lines   | Fixture                    | Scope    | Constructs                                                              | Teardown                         |
| ------- | -------------------------- | -------- | ----------------------------------------------------------------------- | -------------------------------- |
| 29–33   | `unit_test_suite`          | function | `StandardUnitFixtures.memory_test_suite()` + `suite.session()`          | async ctx mgr                    |
| 37–42   | `memory_test_suite`        | function | `UnitTestSuite(memory_config)` + session                                | async ctx mgr                    |
| 46–51   | `file_test_suite`          | function | `UnitTestSuite(file_config)` + session                                  | async ctx mgr                    |
| 58–61   | `sqlite_memory_connection` | function | `memory_test_suite.get_connection()`                                    | async ctx mgr                    |
| 65–68   | `sqlite_file_connection`   | function | `file_test_suite.get_connection()`                                      | async ctx mgr                    |
| 75–88   | `memory_dataflow`          | function | `memory_test_suite.dataflow_harness.create_dataflow()`                  | `await close_async()` in finally |
| 92–98   | `file_dataflow`            | function | `file_test_suite.dataflow_harness.create_dataflow()`                    | `await close_async()` in finally |
| 102–108 | `auto_migrate_dataflow`    | function | `memory_test_suite.dataflow_harness.create_dataflow(auto_migrate=True)` | `await close_async()` in finally |

All eight already close cleanly. Trust + query conftests carry only mocks/data — no resource fixtures.

## DataFlow lifecycle API (verified live)

Source: `packages/kailash-dataflow/src/dataflow/core/engine.py`

- Line 3374 — `def __enter__(self):` (sync)
- Line 3425 — `def __exit__(self, exc_type, exc_val, exc_tb):` (sync)
- Line 3484 — `def __del__(self, _warnings=warnings):` (ResourceWarning only post-PR #1001 commit `5cae13c0`)
- Line 9948 — `def close(self):`
- Line 10051 — `async def close_async(self):`

No `__aenter__` / `__aexit__`. `async with DataFlow(...)` is unsupported.

## Inline-construction hot-spots (`grep -rn 'DataFlow(' packages/kailash-dataflow/tests/unit`)

Approximate counts; verified via grep of `DataFlow(` literal:

| File                                 |      Inline calls (approx) |
| ------------------------------------ | -------------------------: |
| `test_derived_model.py`              |                        ~20 |
| `core/test_dataflow_test_mode.py`    |                         ~9 |
| `test_dataflow_bug_011_012_fixes.py` |                         ~7 |
| `test_engine_migration_errors.py`    |                         ~7 |
| `test_cache_invalidation_bug.py`     |                         ~4 |
| Mid-concentration (per-file 2–5)     |      ~150 across ~30 files |
| Low-concentration (per-file ≤2)      |       ~70 across ~20 files |
| **Total**                            | **~270 across ~50+ files** |

## Hang reproduction (direct)

Command: `time .venv/bin/python -m pytest packages/kailash-dataflow/tests/unit/ --maxfail=10 -q --timeout=120 -p no:cacheprovider`

- Test summary line: `3274 passed, 87 skipped, 59 warnings in 93.60s`
- Wall clock to SIGKILL: `11:44.13`
- Post-summary state: process in `S` (sleep / blocked on condvar)
- Process behavior matches brief: `_Py_Finalize → wait_for_thread_shutdown` indefinite block

This is the direct empirical evidence that the CI `setsid` wrapper is load-bearing in main today.

## Migration template (the only one needed)

```python
# Option A — adopt existing fixture
async def test_something(memory_dataflow):
    await memory_dataflow.express.create("User", {...})

# Option B — local fixture in same file's conftest
@pytest.fixture
async def custom_dataflow():
    db = DataFlow(":memory:", migration_enabled=False)
    try:
        yield db
    finally:
        await db.close_async()

# Option C — sync context manager inside sync test body
def test_something_sync():
    with DataFlow(":memory:") as db:
        result = db.express_sync.create("User", {...})
        assert result["id"]
```

## Risks surfaced during enumeration

- Tests asserting `__del__`-emitted `ResourceWarning` semantics must remain un-migrated (they are testing the warning, not the cleanup pattern).
- Tests that construct DataFlow with `tempfile.NamedTemporaryFile` need ordered cleanup (close DataFlow before unlinking file).
- A small number of tests use `@patch("aiosqlite.connect", ...)` — those bypass real connections and need no migration.
