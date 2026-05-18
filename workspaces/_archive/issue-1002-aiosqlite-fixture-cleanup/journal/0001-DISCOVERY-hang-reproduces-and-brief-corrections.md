# 0001 DISCOVERY — hang reproduces empirically + three brief corrections

Date: 2026-05-14
Phase: /analyze

## Hang reproduces (direct evidence)

Local run (`.venv/bin/python -m pytest packages/kailash-dataflow/tests/unit/ --maxfail=10 -q --timeout=120 -p no:cacheprovider`):

- Pytest summary line: `=========== 3274 passed, 87 skipped, 59 warnings in 93.60s (0:01:33) ===========`
- Total wall clock to SIGKILL: `11:44.13`
- Post-summary hang: **~10 min 11 s** in process state `S` (sleeping/blocked) — consistent with `__psynch_cvwait` thread block claimed by #1002 brief.

Conclusion: brief's hang attribution is reproduced. Without the CI `setsid` wrapper at `.github/workflows/unified-ci.yml:255-289`, every dataflow Tier-1 CI run would hang indefinitely after the success summary.

## Three brief corrections (gate before /todos)

Per `agents.md` § "Parallel Brief-Claim Verification When Issue Count ≥ 3" these are recorded here AND in the architecture plan as the gate before `/todos`.

### Correction 1 — DataFlow does NOT support `async with`

Brief Shard 2 (`gh issue view 1002`) says:

> "convert per-test patterns to `async with DataFlow(...) as db:` or explicit `await db.close_async()` in fixture teardown."

Live source check (`packages/kailash-dataflow/src/dataflow/core/engine.py`):

- Line 3374: `def __enter__(self):` (sync context manager)
- Line 3425: `def __exit__(self, exc_type, exc_val, exc_tb):` (sync)
- Line 3484: `def __del__(self, _warnings=warnings):` (post-PR #1001 — `ResourceWarning` only)
- Line 9948: `def close(self):` (sync)
- Line 10051: `async def close_async(self):`

No `__aenter__` / `__aexit__`. `async with DataFlow(...) as db:` raises `AttributeError` at runtime. The canonical pattern is the one already in `packages/kailash-dataflow/tests/unit/conftest.py:80-108`:

```python
@pytest.fixture
async def memory_dataflow(memory_test_suite):
    dataflow = memory_test_suite.dataflow_harness.create_dataflow()
    try:
        yield dataflow
    finally:
        await dataflow.close_async()
```

### Correction 2 — Scope is test-body inline constructions, not fixture conftest

Brief Shard 1 says "every fixture pattern in `tests/unit/` that constructs `DataFlow`...". The actual surface (verified by grep):

- Root conftest at `packages/kailash-dataflow/tests/unit/conftest.py` — already canonical (8 dataflow fixtures, all `try / finally: await close_async()`).
- `tests/unit/trust/conftest.py` — only mocks + data fixtures (no resources).
- `tests/unit/query/conftest.py` — module-loading stub.
- **Test bodies**: ~270 inline `DataFlow(...)` constructions across ~50+ test files. None of these go through the canonical fixtures.

The cleanup scope is **test-body inline constructions**, not conftest fixtures. Heaviest hot-spots:

| File                                 | Inline calls (approx) |
| ------------------------------------ | --------------------: |
| `test_derived_model.py`              |                   ~20 |
| `test_dataflow_bug_011_012_fixes.py` |                    ~7 |
| `test_engine_migration_errors.py`    |                    ~7 |
| `core/test_dataflow_test_mode.py`    |                    ~9 |
| `test_cache_invalidation_bug.py`     |                    ~4 |

Mid- and low-concentration files cover the remaining ~220 calls.

### Correction 3 — `__del__` no longer participates in deadlock chain

Brief implies `__del__` may still call `close()`. Verified live in `engine.py:3484-3514`:

```python
def __del__(self, _warnings=warnings):
    try:
        if not getattr(self, "_closed", True):
            _warnings.warn(
                f"Unclosed DataFlow instance {getattr(self, '_instance_id', '?')}. "
                "Use 'with DataFlow(...) as db:' or call db.close() "
                "(or `await db.close_async()` in async contexts).",
                ResourceWarning,
                source=self,
            )
    except Exception:
        ...
```

Post-PR #1001 (commit `5cae13c0`), `__del__` emits `ResourceWarning` only — never calls `close()`, never spawns a new event loop, never touches logging. The hang root cause is therefore NOT `__del__`-triggered logging deadlock (which #1000 addressed). It is upstream: the test fixtures leave aiosqlite background threads running because they never call `close_async()`. Those non-daemon background threads block `_Py_Finalize → wait_for_thread_shutdown` at interpreter shutdown.

## Pre-existing WARN entries (zero-tolerance.md Rule 1 disposition)

Two unique WARN classes in the test output:

1. **`DeprecationWarning: MLTenantRequiredError is deprecated; use TenantRequiredError. Alias will be removed in kailash-dataflow v3.0.`** — pre-existing deprecation alias, on a documented removal path (v3.0). Disposition: deferred to v3.0 removal cycle; no action this workstream.

2. **`PytestWarning: The test <Function test_async_regression_testing> is marked with '@pytest.mark.asyncio' but it is not an async function.`** at `tests/unit/testing/test_performance_regression_suite.py:717`. Disposition: file as todo for inclusion in this workstream's hygiene shard (cheap; same area).

## Source references

- DataFlow lifecycle surface: `packages/kailash-dataflow/src/dataflow/core/engine.py:3374,3425,3484,9948,10051`
- Canonical fixture pattern: `packages/kailash-dataflow/tests/unit/conftest.py:80-108`
- CI wrapper to remove: `.github/workflows/unified-ci.yml:251-289`
- Rule binding: `rules/patterns.md` § "Async Resource Cleanup"
