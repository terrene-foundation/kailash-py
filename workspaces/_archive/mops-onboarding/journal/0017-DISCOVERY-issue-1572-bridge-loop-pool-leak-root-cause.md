# 0017 — DISCOVERY: #1572 real root cause is bridge-loop adapter-pool lifecycle (not close_async)

**Date:** 2026-07-05
**Type:** DISCOVERY (+ DECISION: Option A approved)
**Issue:** kailash-py #1572 (MySQL adapter pool not drained on close_async / Event loop is closed at GC)

## Symptom (reproduced, real MySQL:3307 + PG:5434)

`await db.close_async()` after an express/node CRUD cycle emits ~10 GC-time
`RuntimeError: Event loop is closed` + `ResourceWarning: Unclosed connection`
from `aiomysql/connection.py:1131 Connection.__del__` (aiomysql 0.3.2 — latest;
`__del__` unconditionally calls `self.close()` → `transport.close()` on the loop).
MEDIUM / cosmetic: connections reclaimed at process exit, no data/runtime impact.
Reproduces on BOTH sync-node path AND pure-async `db.express` path.

## Two hypotheses PROVEN WRONG (both no-ops)

1. **Issue's hypothesis** — `close_async()` never calls
   `MySQLAdapter.close_connection_pool()`. Wrong layer.
2. **My initial hypothesis** — `close_async()` never drains
   `AsyncSQLDatabaseNode._shared_pools`. True that close_async does not call
   `clear_shared_pools`, but IRRELEVANT: the express pool's cached node in
   `_async_sql_node_cache` has a byte-identical `_pool_key`, so the existing
   node-cache teardown (`engine.py:10695-10708` → `cleanup():6646`
   `del _shared_pools[key]; await adapter.disconnect()`) already drains it.
   `_shared_pools` is size 0 after `close_async`. dataflow-specialist prototyped
   the `_shared_pools`-drain fix: warning count stayed 10/10.

## Verified root cause (specialist instrumented `aiomysql.Connection.__init__`; I verified the mechanism)

~6 of ~12 connections are created on **transient bridge event loops**, NOT in
`_shared_pools`, and are never drained before their loop closes:

- `async_utils.py:223-248 run_coro_in_new_loop` (the `async_safe_run` bridge)
  creates a new loop in a thread pool, runs the coro, then `_cancel_all_tasks` +
  `new_loop.close()` — **without disconnecting adapter pools created on it**.
- Origins: `DataFlow.__init__` reachability probe (`adapters/mysql.py:76→94
create_connection_pool`, 1 conn) + `initialize()`/auto-migrate DDL
  (`async_sql.py:611 EnterpriseConnectionPool.initialize`, min_size=5 → 5 conns).
- `initialize_pool()` bridges to sync via `async_safe_run` at `engine.py:1840`;
  `engine.py:6436` documents "binds each to a fresh, short-lived loop".
  An aiomysql pool bound to an already-closed loop cannot be drained (transports
  belong to the dead loop) — same reason `cleanup()` early-returns on a closed loop
  (`async_sql.py:6608-6615`). Only correct drain point = while the bridge loop lives.

## DECISION — Option A approved (user, 2026-07-05)

Fix at the bridge-loop boundary: in `run_coro_in_new_loop`, BEFORE
`new_loop.close()`, drain adapter pools created on that loop (via a per-loop
adapter registry populated on adapter `connect()`). Best-effort/guarded so
teardown never raises; log ONLY counts + loop id (pool keys carry creds —
`security.md`; use `redact_pool_key`). General (catches all origins present +
future). Rejected: Option B (fix the 2 originating paths — brittle);
close-method drain (proven no-op).

## Not started. Cross-SDK: the Rust SDK MySQL binding may share the gap (issue note).
