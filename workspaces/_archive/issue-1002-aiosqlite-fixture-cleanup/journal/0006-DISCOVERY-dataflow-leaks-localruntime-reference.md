# DISCOVERY — DataFlow Leaks LocalRuntime Reference (Pre-existing)

Date: 2026-05-14
Phase: /implement (Shard 2)

## Context

While running the Shard 2 acceptance pytest invocation with
`-W error::ResourceWarning`, two `LocalRuntime` ResourceWarnings
surfaced:

```
ResourceWarning: Unclosed LocalRuntime (ref_count=1).
Use 'with LocalRuntime() as runtime:' or call runtime.close().
  at src/kailash/runtime/local.py:2029 in LocalRuntime.__del__
```

The warnings are attributed by pytest's `unraisableexception` machinery
to the next test after the leaky GC (test_auto_migrate_false_prevents_migration
and test_existing_schema_mode_validates_compatibility in
test_bug_006_safety_parameters.py) BUT the origin is upstream:
`DataFlow(...)` internally constructs a `LocalRuntime` whose ref-count
is never released even when `DataFlow.close()` is called.

## Evidence — pre-existing on main

Reproduction protocol:

```bash
git show 52b8e7f6:packages/kailash-dataflow/tests/unit/features/test_read_replica.py \
    > /tmp/test_read_replica_main.py
cp /tmp/test_read_replica_main.py \
    packages/kailash-dataflow/tests/unit/features/test_read_replica.py
cd packages/kailash-dataflow
../../.venv/bin/python -m pytest \
    tests/unit/features/test_read_replica.py \
    tests/unit/migrations/test_bug_006_safety_parameters.py \
    -q --timeout=60 -W error::ResourceWarning
```

Result: `28 passed, 2 warnings` — same `LocalRuntime` ResourceWarning
surfaces. The warning IS NOT introduced by the Shard 2 migration; it
pre-dates the session's first tool call (verified at commit `52b8e7f6`,
the branch's base SHA).

## Root cause hypothesis

`DataFlow.__init__` (or one of the lazy-init paths it triggers, e.g.
`db.health_check()` or auto-discovery) constructs a `LocalRuntime`
that is held as an instance attribute but never has its `close()` /
ref-count-decrement called from `DataFlow.close()` or `DataFlow.close_async()`.

The engine sync `close()` fix from commit `52b8e7f6` closes the cached
`AsyncSQLDatabaseNode` but does NOT touch the internal `LocalRuntime`
ref-count. That's a distinct cleanup path.

## Disposition — Shard 2 scope-bounded

Per `rules/zero-tolerance.md` Rule 1c, the warning is **pre-existing on main**
(verified via commit-SHA reproduction). Per the architecture plan, Shard 2
covers test-fixture-level inline constructions of `DataFlow(...)` and
`AsyncRedisCacheAdapter(...)`; the `LocalRuntime` leak is at a different
surface (Core SDK runtime ref-counting in DataFlow's internal plumbing)
and is out of Shard 2 scope.

## Forward-loop

Recommended candidate for Shard 3 (which addresses low-concentration files

- tail asyncio-mark hygiene) OR a separate workstream addressing
  "DataFlow.close() does not release its internal LocalRuntime ref-count" as
  a Core-SDK + DataFlow plumbing bug. The fix lives in
  `packages/kailash-dataflow/src/dataflow/core/engine.py` (the engine that
  constructs the internal LocalRuntime) — `close()` / `close_async()` need
  to call the LocalRuntime's `close()` or decrement its ref-count.

NOT a Shard 2 commit. This journal entry is the audit trail.

## Acceptance criteria status — Shard 2

- [x] All 4 in-scope files migrated (test_read_replica, test_bug_006_safety_parameters, test_count_node, test_async_redis_adapter).
- [x] Targeted pytest run exits 0 with all 80 tests passing.
- [x] Zero new ResourceWarnings introduced by Shard 2 (the 2 LocalRuntime warnings are pre-existing per the reproduction above).
- [ ] Reviewer + security-reviewer parallel review — to be triggered by the orchestrator at next gate.

Commits:

- f0e4a74f — test_count_node.py (6 sites)
- e161cd91 — test_read_replica.py (11 sites)
- cb1279f6 — test_bug_006_safety_parameters.py (10 sites)
- fef2311a — test_async_redis_adapter.py (18 of 23 sites; 5 in do-not-touch class)
