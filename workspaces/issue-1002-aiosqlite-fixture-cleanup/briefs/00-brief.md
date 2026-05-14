# Brief — issue #1002 — aiosqlite/connection fixture cleanup (AC#3 of #1000)

Source: `gh issue view 1002` (filed 2026-05-14 as deferred AC#3 of #1000).

## Value-anchor (verbatim from #1000 brief AC#3)

> "Verify on CI: remove the setsid wrapper from `.github/workflows/unified-ci.yml::test-dataflow` and confirm pytest exits cleanly"

## Context

#1000 (PR #1001) closed the structural `__del__` rule violations per `rules/patterns.md` § Async Resource Cleanup. The CI `setsid` wrapper in `unified-ci.yml::test-dataflow` (lines 255-289) remains — protecting against a DIFFERENT root cause than the `__del__` deadlock #1000 addressed.

## Repro

```bash
cd packages/kailash-dataflow
time ../../.venv/bin/python -m pytest tests/unit/ --maxfail=10 -q --timeout=120
# Test phase: 3274 passed in ~93s
# Process: hangs in _Py_Finalize → wait_for_thread_shutdown indefinitely
```

## Root cause (sample evidence)

Post-pytest-summary, ~18 unnamed `threading.Thread` instances stuck in `_PyMutex_LockTimed` → `_PyParkingLot_Park` → `__psynch_cvwait`. These are aiosqlite background threads (one per open `Connection`) held alive because test fixtures create `DataFlow` / aiosqlite connections and never close them.

Polars rayon (16) + tokio (16) + polars-stream async-executor (16) threads are Rust pthreads — they don't block `_Py_Finalize`, but contribute to the process not exiting cleanly post-SIGKILL.

## Scope (multi-shard per `autonomous-execution.md` MUST Rule 1)

**Shard 1**: enumerate every fixture pattern in `tests/unit/` that constructs `DataFlow` / aiosqlite / `AsyncRedisCacheAdapter` without explicit `close()`. Estimate fixture-count and call-site-count.

**Shard 2**: convert per-test patterns to `async with DataFlow(...) as db:` or explicit `await db.close_async()` in fixture teardown.

**Shard 3**: verify pytest exits cleanly without setsid wrapper, then remove the wrapper from `.github/workflows/unified-ci.yml::test-dataflow`.

## Acceptance criteria

- [ ] Test fixtures explicitly close `DataFlow`/connection instances
- [ ] Local pytest exits cleanly (no `_Py_Finalize` hang) within 2 min
- [ ] Remove the `setsid` + 150s polling wrapper from `unified-ci.yml::test-dataflow`; restore plain pytest invocation
- [ ] Same-PR regression: `tests/regression/test_pytest_exits_clean.py` asserts pytest completes within timeout
- [ ] CHANGELOG entry on the release that lands the fix

## Related

- #1000 (closes AC#1/#2/#4; this issue picks up AC#3)
- #979 (Workstream-B item B-Δ — original umbrella, CLOSED 2026-05-14 via S6 + 2.9.6)
- PR #1001 (structural `__del__` fix, merged 2026-05-14)
