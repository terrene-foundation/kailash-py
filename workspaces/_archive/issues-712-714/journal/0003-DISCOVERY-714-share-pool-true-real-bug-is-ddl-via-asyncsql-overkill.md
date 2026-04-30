---
type: DISCOVERY
created: 2026-04-29
issue: 714
phase: 01-analyze
relates_to: brief 01-product-brief.md
---

# #714 brief misframes the bug — `share_pool=True` already reuses pool; real failure is DDL-via-AsyncSQL overkill

## Brief claim under scrutiny

> `DataFlow.create_tables()` (sync path) opens a separate `AsyncSQLDatabaseNode` connection pool per registered model.

## Verification result (deep-dive Round 1, 2026-04-29)

The claim is **TRUE in letter, FALSE in spirit**.

`AsyncSQLDatabaseNode` defaults `share_pool=True` (`async_sql.py:2897, 3684`)
and uses a class-level `_shared_pools` dict keyed by configuration. Each
DDL iteration in `_execute_ddl` (`engine.py:7531-7627`) and
`_execute_ddl_async` (`:7629-7722`) does construct a fresh
`AsyncSQLDatabaseNode`, BUT the pool lookup hits `_shared_pools` cache
on every iteration after the first. The actual asyncpg pool is allocated
ONCE and reused — there is not "one pool per model."

## What's actually wrong

Three real failure modes (in priority order):

1. **DDL via `AsyncSQLDatabaseNode` is overkill.** DDL is single-connection
   work. Routing it through `AsyncSQLDatabaseNode` (designed for parameterized
   queries with pool/transaction-mode/fetch-mode plumbing) means the operator
   must size a connection pool for DDL bursts. With `pool_size=10`, that's 10
   client connections held against pgbouncer in session mode. If the cap is
   below `pool_size`, the cap is hit. The fix is to bypass
   `AsyncSQLDatabaseNode` entirely for DDL and use a single connection from
   `self._connection_manager`.

2. **Per-statement node + WorkflowBuilder construction overhead.** Every DDL
   iteration constructs a fresh node + workflow builder, then tears them down.
   The pool reuse via cache hit saves the connection cost but not the node
   construction cost. Ideal fix is reuse the node OR bypass it.

3. **Failure mode if `share_pool` is somehow disabled** (test fixtures,
   dynamic configs, future refactor that flips the default): collapses
   into N pools, exactly the failure the brief describes. The current
   pattern depends on a default that could silently change. Robust fix
   removes the dependency.

## Why Mediscribe specifically hit `MaxClientsInSessionMode`

Most likely (one or more of):

1. `share_pool` was disabled by config (rare but possible)
2. `pool_size` was configured > pgbouncer cap (likely — Supabase pgbouncer
   defaults are tight, and DataFlow defaults can exceed them)
3. A sibling DataFlow code path concurrently allocated against the same cap
   (likely — once `db.create_tables_async()` gets past #713's AttributeError,
   it acquires asyncpg's pool, and then `db.express` operations contend)

## Implication for the fix

The brief recommends "reuse db.runtime pool." But CLAIM C of the deep-dive
verified that **`db.runtime` (an `AsyncLocalRuntime` workflow runtime) does
NOT expose a connection pool**. There is NO existing "runtime pool" for DDL
to borrow from. The brief's recommendation is incorrect on architecture.

The correct fix is: **acquire ONE connection from `self._connection_manager`
once per `_execute_ddl*` call, run all DDL statements on it, release.**
Bypass `AsyncSQLDatabaseNode` entirely for DDL.

## Cost / blast radius

- `_execute_ddl` and `_execute_ddl_async` are internal underscore-prefix
  methods. Public API (`create_tables`, `create_tables_async`) signatures
  unchanged.
- The refactor is ~80-100 LOC across the two methods, plus a Tier-3 test.
- No breaking change for consumers; observability stays identical
  (DDL log lines and metrics emitted by hand inside the new path).

## Cross-references

- Brief: `briefs/01-product-brief.md` § Issue #714
- Deep-dive citations: `engine.py:7531-7627` `_execute_ddl`,
  `:7629-7722` `_execute_ddl_async`, `:7541` `self._connection_manager`,
  `async_sql.py:2897, 3684` `share_pool` default
- Related #696: pool-exhaustion failure-mode class via DDL retry storm,
  documented in `specs/dataflow-core.md` §1.6
- Architecture: `01-analysis/01-architecture.md` § #714 fix surface
