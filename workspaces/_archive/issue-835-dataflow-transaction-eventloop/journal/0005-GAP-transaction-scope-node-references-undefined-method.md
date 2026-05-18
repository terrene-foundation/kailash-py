---
type: GAP
date: 2026-05-06
created_at: 2026-05-06T05:10:00Z
author: agent
session_id: 568d8b2e-d820-4272-a450-5f4ed5fe8209
project: issue-835-dataflow-transaction-eventloop
topic: TransactionScopeNode workflow path references undefined `_get_cached_db_node` method
phase: analyze
tags: [latent-bug, transaction-scope-node, follow-up]
---

# GAP — `TransactionScopeNode` references undefined `_get_cached_db_node`

## What's missing / broken

`packages/kailash-dataflow/src/dataflow/nodes/transaction_nodes.py:59` calls `dataflow_instance._get_cached_db_node(db_type)` to resolve the database adapter for workflow-context transactions. **`_get_cached_db_node` is not defined anywhere in the source tree.**

Verified via:

```bash
grep -rn "def _get_cached_db_node\|def get_cached_db_node" packages/kailash-dataflow/src/ src/kailash/
# (zero results)
```

`TransactionScopeNode` is registered into the `NodeRegistry` at `core/engine.py:8581` and added to `self._nodes["TransactionScopeNode"]` at `core/engine.py:8590`. So the node IS present in the public surface, but invoking it through any workflow that hits `_get_adapter_from_context` will raise `AttributeError`.

## Why it matters

This is a SEPARATE latent bug from issue #835. It does not cause #835's symptom because:

- `db.transactions.begin()` does NOT go through `TransactionScopeNode`. It goes through `TransactionManager.begin()` (`features/transactions.py:242`), which uses its own `_get_adapter()` — currently returning the broken `_connection_manager._adapter`.
- The two paths are unrelated. `TransactionScopeNode` is for workflow-graph composition (a node that wraps a transaction); `TransactionManager.begin()` is for direct API use.

The bug surfaced during the issue #835 architecture-plan revision because the FIRST revision suggested reusing `_get_cached_db_node` as the resolution mechanism for `TransactionManager._get_adapter()`. Verification proved the reference broken — both for the issue #835 fix AND for the existing `TransactionScopeNode` flow.

## Severity assessment

`TransactionScopeNode` is documented and registered. Any workflow that uses it WILL fail at runtime. This deserves:

- A separate GitHub issue, scoped to the SDK API surface only (per `rules/upstream-issue-hygiene.md`).
- Tier-2 regression coverage of `TransactionScopeNode` end-to-end through a workflow runtime — search the test directory: empty? Add it.
- Either define `_get_cached_db_node` on DataFlow OR rewrite `_get_adapter_from_context` to use a different resolution path.

The fix scope for that follow-up issue likely overlaps with issue #835's fix — both want a "resolve the cached AsyncSQLDatabaseNode" entry point. Coordinating the two:

- Land issue #835's fix first (Phase 1 caches a dedicated node on `TransactionManager`).
- The follow-up for `TransactionScopeNode` can then either define a public `_get_cached_db_node` on DataFlow OR have `_get_adapter_from_context` follow the same "construct a dedicated cached node" pattern.

## Disposition for THIS workspace

- Out of scope for issue #835's fix (different code path, different failure mode).
- Recorded here so a future session picks it up.
- Per `rules/upstream-issue-hygiene.md` MUST Rule 1, NOT auto-filed against the SDK repo. User-gated.
- Recommended title: "bug: TransactionScopeNode raises AttributeError because `_get_cached_db_node` is not defined".

## For Discussion

1. **Counterfactual**: would a `pytest --collect-only -q packages/kailash-dataflow/tests/` followed by a search for `TransactionScopeNode` in test files have caught this? Per `rules/agents.md` reviewer mechanical sweeps, "for every NEW module, grep test directory for import — empty = HIGH." The class isn't new but the rule logic generalizes — public-surface symbols without behavioral coverage rot silently. Would a periodic sweep across all `__all__` symbols catch this?
2. **Specific data**: this is the second latent bug surfaced by tracing references during plan revision (the first being `_PoolWrapper`'s dead-code branch). Suggests architecture-plan red teams catch latent bugs at a non-trivial rate. Worth recording.
3. **Process question**: should `/analyze` always run a "every cited helper resolves" sweep on the architecture plan before reporting complete? `rules/spec-accuracy.md` Rule 1 mandates this for specs; the same discipline applied to plans would have caught the `_build_pool_key_for_dataflow` AND `_get_cached_db_node` references in one sweep.

## Source

- Broken reference: `packages/kailash-dataflow/src/dataflow/nodes/transaction_nodes.py:59`
- Registration sites: `packages/kailash-dataflow/src/dataflow/core/engine.py:8581, 8590`
- `__all__` export: `packages/kailash-dataflow/src/dataflow/nodes/__init__.py:23, 36`
- Verification command (zero results, confirming undefined): `grep -rn "def _get_cached_db_node\|def get_cached_db_node" packages/kailash-dataflow/src/ src/kailash/`
