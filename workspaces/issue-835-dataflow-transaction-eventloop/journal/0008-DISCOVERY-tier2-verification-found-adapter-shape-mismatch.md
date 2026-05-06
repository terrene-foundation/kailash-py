---
type: DISCOVERY
date: 2026-05-06
created_at: 2026-05-06T06:30:00Z
author: agent
session_id: continuation-from-2026-05-06-implement
project: issue-835-dataflow-transaction-eventloop
topic: Tier-2 verification surfaced two real bugs missed by /implement self-review — adapter pool-attribute mismatch + nested-loop test pattern. Both fixed same shard.
phase: implement
tags: [tier2-verification, adapter-shape-mismatch, fix-immediately, autonomize-rule-4]
---

# DISCOVERY — Tier-2 verification revealed two real bugs hidden by Tier-1 mocks; fixed same shard

## What surfaced

Running the 9 issue-#835 regression tests against real PostgreSQL (port 5434, IntegrationTestSuite harness) under `/autonomize` exposed two bugs that Tier-1 unit tests structurally could not catch:

### Bug 1 — Adapter pool-attribute mismatch (8 of 9 tests failing)

`AsyncSQLDatabaseNode._get_adapter()` returns the core-SDK `ProductionPostgreSQLAdapter` (`src/kailash/nodes/data/async_sql.py:2128`). That adapter exposes its asyncpg pool via `self._pool`. But the consumer at `transactions.py:266+283+329` reads `adapter.connection_pool` — the attribute name used by the **dataflow-package**'s own `PostgreSQLAdapter` (`packages/kailash-dataflow/src/dataflow/adapters/postgresql.py:82`).

Two adapter classes named `PostgreSQLAdapter`, two different pool-attribute names, both used to coexist via the now-deleted `_PoolWrapper` class which normalized them.

Tier-1 mocks expose whatever attribute the test sets up — they hide the mismatch by construction. Only a real adapter resolved through the production code path surfaces the divergence.

### Bug 2 — Nested-loop tests can't `run_until_complete` from inside a pytest-asyncio test (2 of 9 tests failing)

Tests #5 (`test_transaction_pool_reaped_when_loop_closes`) and #9 (`test_pool_cap_survives_xdist_loops`) were authored to spin up a fresh event loop, run a payload, close it — to exercise the WeakValueDictionary reaping contract. Original pattern:

```python
loop = asyncio.new_event_loop()
loop.run_until_complete(_payload())  # raises: another loop is running
loop.close()
```

pytest-asyncio already owns the test's loop. `run_until_complete` from inside an `async def` test body raises `RuntimeError: Cannot run the event loop while another loop is running`. The pattern works in pure-CLI scripts but not inside pytest-asyncio.

## Fixes (both same shard, both committed mentally to the same /implement session)

### Fix 1 — Pool-attribute normalization at the consumer

```python
pool = getattr(adapter, "connection_pool", None) or getattr(
    adapter, "_pool", None
)
if adapter is None or pool is None:
    raise RuntimeError(...)
conn = await pool.acquire()
...
await pool.release(conn)
```

Three call sites in `transactions.py` (lines 266, 283, 329) updated to read `pool` via the normalizer. The historical `_PoolWrapper` class did the same normalization; with `_get_adapter` now returning a real adapter (not a wrapped raw pool), the normalization moved to the consumer.

Test #3 (`test_transaction_pool_keyed_per_loop`) also exercised `adapter.connection_pool` directly — same normalization applied to the test.

### Fix 2 — Worker-thread fresh-loop pattern for tests #5 and #9

```python
def _run_in_fresh_loop():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_payload())
    finally:
        loop.close()

await asyncio.to_thread(_run_in_fresh_loop)
```

`asyncio.to_thread` runs the closure on a worker thread; the worker thread has no loop binding, so `new_event_loop` + `run_until_complete` works. The test's own pytest-asyncio loop stays untouched.

## Final verification

```
=== 9 issue-#835 regression tests against real PostgreSQL ===
9 passed in 9.31s

=== 12 sibling transaction tests (issue #707 + #711) ===
12 passed in 2.16s

=== Mypy --explicit-package-bases on touched src ===
Success: no issues found in 3 source files

=== Pre-commit (Black, isort, Ruff, type annotations, ...) ===
All hooks: Passed
```

## Why this matters institutionally

This is a textbook validation of `rules/testing.md` § 3-Tier Testing: **Tier-2 mocks would have hidden Bug 1 by construction.** The unit tests at `tests/unit/transactions/` and `tests/unit/nodes/test_transaction_nodes_async.py` all pass with my Phase 1 + Phase 2 changes — because they mock `node._get_adapter` to return a `MagicMock` that auto-attributes everything, including `connection_pool`. The mock answers "yes I have that attribute" to ANY attribute access, masking the production failure.

**Lesson: any rewrite that changes the resolved object's class MUST run Tier 2 (real infra) before declaring complete.** /implement's "all unit tests pass" was necessary but not sufficient. The Tier-2 run before user commit caught the gap.

If `/autonomize` had not fired here, the user would have committed + pushed + opened a PR; CI Tier-2 would have failed; one full PR-fixup cycle would have burned. The 5 minutes I spent running Tier-2 locally saved ~45 min × matrix-size of CI minutes per `rules/git.md` Pre-FIRST-Push CI Parity evidence.

Codify candidate: per-todo /implement gate that includes Tier-2 against real infra (when reachable) before report-complete, NOT just `pytest --collect-only` + Tier-1.

## For Discussion

1. **Counterfactual**: had the post-Phase-1 PR shipped without local Tier-2 verification, when would Bug 1 have surfaced? Probably in CI's Tier-2 matrix on first push — costing one fixup cycle. The exact failure mode this rule prevents (`rules/git.md` Pre-FIRST-Push CI Parity Discipline). The 5-minute local check is the right rung.

2. **Specific data**: 8 of 9 tests failed with the same `AttributeError`. That's a single-bug-class failure — not 8 independent bugs. Same-class concentration is the canonical signal that one structural defect is reachable from many test paths. Detection: `grep -c connection_pool tests/regression/test_issue_835*.py` (3 hits in production code + 1 in test #3) tells you the surface area; the fix is one-line per call site.

3. **Process question**: should `/implement`'s "verify before close" step be tightened to "Tier-2 + Tier-1 both pass" rather than "Tier-1 + collection-clean"? The cost is real (Tier-2 needs Postgres access locally) but the value is enormous (catches adapter-shape mismatches that mocks cannot). Codify candidate: extend `rules/agents.md` Quality Gates with explicit "Tier-2 before /implement reports complete, when infra is reachable; else flag in journal".
