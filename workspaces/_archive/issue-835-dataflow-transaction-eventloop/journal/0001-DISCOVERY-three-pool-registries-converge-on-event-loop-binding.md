---
type: DISCOVERY
date: 2026-05-06
created_at: 2026-05-06T04:45:29Z
author: agent
session_id: 568d8b2e-d820-4272-a450-5f4ed5fe8209
project: issue-835-dataflow-transaction-eventloop
topic: Three pool registries in DataFlow converge on event-loop binding constraint
phase: analyze
tags: [dataflow, transactions, asyncpg, event-loop, pool-registry]
---

# DISCOVERY — Three pool registries converge on event-loop binding constraint

## What was discovered

DataFlow has **three distinct pool ownership patterns**, all dealing with asyncpg's loop-binding constraint, but only TWO of them respect it. The third (`_connection_manager._adapter`) is the source of issue #835.

| Owner                                          | Loop-keyed                                              | Reaper                                  | Used by                                |
| ---------------------------------------------- | ------------------------------------------------------- | --------------------------------------- | -------------------------------------- |
| `_PROCESS_POOL_REGISTRY` (`async_sql.py:2655`) | YES — `id(running_loop)` keyed via `_generate_pool_key` | YES — per-loop `_idle_pool_reaper_loop` | `db.express.*`, `AsyncSQLDatabaseNode` |
| `SyncTransactionManager` per-`begin()`         | N/A — fresh `asyncpg.connect()` per begin               | not needed (one connection per scope)   | `db.transactions_sync.begin()`         |
| `_connection_manager._adapter.connection_pool` | NO — single pool, bound at first `_ensure_connected`    | NO                                      | `db.transactions.begin()` (broken)     |

The first two are the structural responses to "asyncpg pools are loop-bound". The third silently violates the constraint and the violation surfaced as issue #835.

## Why it matters

The bug isn't a one-off coding error in `TransactionManager._get_adapter()`. It's the third surface in DataFlow inheriting from a pre-loop-aware design (single-pool retention) that the other two surfaces have already migrated past. The Express path migrated to per-loop pools at `_PROCESS_POOL_REGISTRY` (DPI-B / issue #697 + #698). The sync transaction path migrated to per-`begin()` connections to avoid pool reuse altogether. The async transaction path is left holding the legacy pattern alone — and the legacy pattern is structurally incompatible with multi-loop usage (pytest-asyncio function-scope, repeated `asyncio.run`, sync-bridge calling async).

The ergonomic gap is real: a user creating `db = DataFlow(...)` and using it across event loops experiences:

- `db.express.*` → "just works"
- `db.express_sync.*` → "just works"
- `db.transactions_sync.*` → "just works"
- `db.transactions.*` → "RuntimeError: Event loop is closed"

The fix (`02-plans/01-architecture.md` Candidate D) brings the third surface into the same registry as the first.

## Connection to existing institutional knowledge

`specs/dataflow-cache.md §12.7` already documents the loop-binding constraint as the rationale for the sync-transaction design ("asyncpg connections are loop-bound; sharing the DataFlow pool across the host loop and the BG loop produces `RuntimeError: Future ... attached to a different loop`"). The async transaction surface was simply never migrated to participate.

`specs/dataflow-cache.md §13.4 Pool Lifecycle Contract (DPI-B / issue #697 + #698)` enumerates the per-loop registry's invariants but does not require async transactions to opt in. The fix amends this implicit exemption.

## For Discussion

1. **Counterfactual**: if the original `TransactionManager` author had used `_PROCESS_POOL_REGISTRY` from day one, would the bug have ever surfaced? Probably not — it would have surfaced as a different bug (registry-cap exhaustion under multi-loop test loads, easier to detect in CI). What does this say about the cost of greenfield-pattern adoption vs migration?
2. **Specific data**: the `_PROCESS_POOL_REGISTRY` cap is `max_pool_count_per_process=100` (`async_sql.py:_POOL_DEFAULTS`). Today the cap is set against Express pools only. After Candidate D lands, transaction pools share the cap. Is 100 the right number for a workload that creates one DataFlow with five distinct event loops? Should the default be raised, or should the new code share keys with Express to avoid double-counting?
3. **Scope question**: should the fix close the door on `_connection_manager._adapter` entirely (Phase 2 in the plan), or keep it as an injectable for some advanced users? Removing it makes the architecture more uniform; keeping it preserves hypothetical extensibility no caller currently exercises. The data argues for removal — cluster 3 found ZERO production setters for the alternate `_adapter` paths in `_get_adapter()`.

## Source citations (verified)

- `_PROCESS_POOL_REGISTRY` definition: `src/kailash/nodes/data/async_sql.py:2655-2658`
- `_generate_pool_key`: `src/kailash/nodes/data/async_sql.py:4130-4172`
- `_idle_pool_reaper_loop`: `src/kailash/nodes/data/async_sql.py:2764-2841`
- `_ensure_connected`: `packages/kailash-dataflow/src/dataflow/core/engine.py:1094-1280`
- `_initialize_database`: `packages/kailash-dataflow/src/dataflow/core/engine.py:1719-1724`
- `async_safe_run` thread-pool branch: `packages/kailash-dataflow/src/dataflow/core/async_utils.py:195-248`
- `TransactionManager._get_adapter`: `packages/kailash-dataflow/src/dataflow/features/transactions.py:387-411`
- `SyncTransactionManager._open_connection_for_url`: `packages/kailash-dataflow/src/dataflow/features/transactions.py:467-491`
- `dataflow-cache.md §12.7` loop-binding documentation
- `dataflow-cache.md §13.4` pool lifecycle contract
