---
type: RISK
date: 2026-04-18
author: agent
project: kailash-py
topic: BulkUpsertNode pool branch silently falls back, masking misconfiguration
phase: redteam
tags: [zero-tolerance, dataflow-pool, orphan, silent-fallback]
---

# BulkUpsertNode.\_execute_query pool branch silently swallows ValueError

**File**: `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py:614-630`

**Finding**: When a caller passed `use_pooled_connection=True` with a
configured `connection_pool_id` and `_pool_manager`, the code called
`self._pool_manager.execute(operation="execute", query=query, params=params)`.
But `DataFlowConnectionManager.execute()` at
`workflow_connection_manager.py:156-171` has a closed operation allowlist:
`initialize / get_connection / release_connection / stats /
configure_smart_nodes`. `"execute"` is NOT in the list. Every attempt
raised `ValueError("Unknown operation: execute")`, was caught by a bare
`except Exception`, produced a generic
`logging.warning(f"Failed to execute via pool: {e}, falling back to
direct connection")`, and silently fell through to direct
`AsyncSQLDatabaseNode` execution.

**Why this is HIGH**:

- Operators who set `use_pooled_connection=True` believed they were
  routing through the connection pool. They weren't. Every bulk-upsert
  call bypassed the pool's connection limits, tenant accounting, and
  audit trail.
- The WARN log was generic (`Failed to execute via pool`) — it named
  no operation, no dialect, no fix. Log triage could not distinguish
  "pool is actually broken" from "this is the expected fallback."
- Two rules violated simultaneously: `zero-tolerance.md` Rule 3
  (silent fallback) and `dataflow-pool.md` Rule 3 (deceptive
  configuration — the `use_pooled_connection` kwarg existed with no
  backing impl).

**Fix**: Deleted the dead branch entirely (bulk_upsert.py:614-630). The
path now raises `NodeValidationError` when `use_pooled_connection=True`
is passed, naming `BulkCreatePoolNode` as the correct pool-routed
alternative. Docstring updated to document the constraint and link to
both rule files.

**Cross-SDK**: kailash-rs likely has the same `BulkUpsert` pool path. File
a ticket referencing this fix commit.

**Test gap**: The 18 SQLi regression tests in
`test_bulk_upsert_sql_injection.py` all use the direct path. There was
no Tier 2 test exercising the pool branch, so the orphan-with-silent-
fallback shipped undetected. Consider a negative test: "pool path on
bulk_upsert raises NodeValidationError, not silent fallthrough."

## For Discussion

- Should `DataFlowConnectionManager.execute()` grow an
  `operation="execute"` case that actually routes SQL through the
  pool? That would be a new feature. The current state is: pool exists
  for connection lifecycle (`get_connection` / `release_connection`)
  but not for query execution. Adding `execute` makes the pool a
  general execution path.
- Counterfactual: If we had simply added `"execute"` to the allowlist
  without backing impl, this HIGH would have stayed HIGH (still a
  deceptive stub). The fix required deleting the caller, not extending
  the callee.
- Are there other nodes with the same pattern? `bulk_create.py` has
  its own pool branch at `BulkCreatePoolNode` which uses
  `get_pool_instance()` (a real operation). The bug is specific to
  bulk_upsert mistakenly calling a phantom `execute` operation.
