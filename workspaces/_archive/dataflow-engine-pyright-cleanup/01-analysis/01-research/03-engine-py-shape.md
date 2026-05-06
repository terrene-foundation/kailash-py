# engine.py Shape Reference

**File:** `packages/kailash-dataflow/src/dataflow/core/engine.py`
**Total LOC:** 10,393 (verified `wc -l`)
**Top-level definitions:** 2 (1 class, 1 helper) — most logic lives in methods on the main class
**Branch:** `main @ a28caf0d` (2026-05-04)

## Why the size matters

10,393 LOC exceeds the per-shard load-bearing-logic budget mandated by `rules/autonomous-execution.md` MUST Rule 1 (≤500 LOC of load-bearing logic per shard). The /todos phase MUST partition the cleanup into shards along independent failure-class boundaries, NOT touch all 5 errors + 56 warnings in one PR.

This file documents the natural seams along which the work can be sharded.

## Verified consumers (`MockConnectionPool` shim @ L3430-3450)

```bash
grep -rn "MockConnectionPool" packages/ src/ tests/ | grep -v "engine.py:3437"
```

Hits (5 outside the shim):

- `packages/kailash-dataflow/tests/fixtures/engine_testing_mocks.py:7,22,410` — test fixture (separate definition + use)
- `packages/kailash-dataflow/tests/fixtures/mock_helpers.py:11,42,76,84` — the canonical test fixture this shim re-exports
- `packages/kailash-dataflow/build/lib/dataflow/core/engine_production.py:8,35,408` — stale build artifact (`build/` is `dataflow-pool.md`-irrelevant; not source of truth)

**Conclusion:** the shim has ZERO non-test consumers in production. Class A (Error 1, L3437) disposition is **delete the shim entirely** — the symbol is dead code. The docstring at L3431-3433 advising callers to "consider real connection pooling" anticipated this; the consumers already migrated.

## Verified `import asyncio` redundancy

```bash
grep -n "^import asyncio\|^    import asyncio\|^        import asyncio" engine.py
# 7:import asyncio       — module-level
# 6073:        import asyncio  — local, redundant
# 7783:        import asyncio  — local, redundant
# 9823:        import asyncio  — local, redundant
```

The L4455 `import asyncio` referenced in Class C is INSIDE `discover_schema()`'s try block. It's redundant with the module-level import at L7. Same for L6073, L7783, L9823 — verified the module-level import is in scope at each location (no `del asyncio` between them).

**Conclusion:** All 4 local `import asyncio` statements (L4455, L6073, L7783, L9823) can be deleted in one shard. This unblocks Class C errors (L4496, L4504 are direct beneficiaries) AND removes 4 lines of dead code.

## Natural shard seams

| Shard | Scope                                                                                                    | LOC touched (est.)           | Errors closed | Warnings closed | Risk               |
| ----- | -------------------------------------------------------------------------------------------------------- | ---------------------------- | ------------- | --------------- | ------------------ |
| S1    | Delete MockConnectionPool shim (L3430-3450)                                                              | ~25 deletion                 | 1             | 0               | LOW                |
| S2    | TYPE_CHECKING import for `TenantContextSwitch`                                                           | ~5 addition                  | 1             | 0               | LOW                |
| S3    | Hoist `import asyncio` + init `discovered_schema = None` + typed guard                                   | ~30 modification             | 3             | 0               | MEDIUM             |
| S4    | Add typed `_require_*` helpers + retrofit call sites for Class W2                                        | ~150 modification            | 0             | 13              | MEDIUM             |
| S5    | Fix Class W1 + W3 (22 Optional-arg call sites)                                                           | ~80 modification             | 0             | 22              | LOW                |
| S6    | Add ClassVar declarations on `Node` / `DataFlowConfig` / `_Proxy` (cross-package edit to `kailash` core) | ~30 modification, 2 packages | 0             | 9               | MEDIUM (cross-pkg) |
| S7    | Fix Class W6 (`with cursor:` → `async with cursor:`)                                                     | ~5 modification              | 0             | 2               | LOW (real bug)     |
| S8    | Add regression-gate test (`tests/regression/test_engine_pyright_invariant.py`)                           | ~30 addition                 | — (gate)      | — (gate)        | LOW                |

Shards S1, S2, S3, S5, S7, S8 are independent (no overlap, no ordering dependency between them). S4 + S6 require the `_require_*` helpers and ClassVar declarations to be in place before the warnings clear.

## Sharding strategy

**Wave 1 (parallel — 4 shards):** S1, S2, S5, S7. All independent file edits in `engine.py` only, plus the trivial deletion shim. None touches the same line range as another. Per `rules/worktree-isolation.md` MUST Rule 4, batch size ≤3 simultaneous worktree agents — so split: wave 1A = (S1, S2, S5), wave 1B = (S7).

**Wave 2 (sequential):** S3 (depends on no other prior change but rewrites the discover_schema method — rebases cleanly after Wave 1).

**Wave 3 (sequential, cross-package):** S6 (modifies `src/kailash/nodes/base.py` + propagates), then S4 (Optional member access — depends on S6 only inasmuch as both add typed declarations).

**Wave 4 (gate):** S8 — regression test lands LAST, after all error/warning fixes are merged. Gate test asserts `pyright` exit 0 + warning count ≤10.

Total: 8 shards, ~360 LOC modified, 5 errors + 46 warnings closed (10 documented exemptions).

## Out of scope (per brief)

- Refactoring `engine.py` to reduce its LOC count.
- Other DataFlow files with pyright drift.
- Pushing warning count to 0 (acceptance criterion #4 floors at ≤10 with justified exemptions).
