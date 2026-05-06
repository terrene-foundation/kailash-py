---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T05:00:00Z
author: agent
session_id: 568d8b2e-d820-4272-a450-5f4ed5fe8209
project: issue-835-dataflow-transaction-eventloop
topic: Revise plan after red-team — reuse existing AsyncSQLDatabaseNode._get_adapter() rather than invent a new path
phase: analyze
tags: [red-team, plan-revision, code-reuse, three-pool-registries]
---

# DECISION — Revise plan after red-team: reuse existing `AsyncSQLDatabaseNode._get_adapter()`

## Decision

The red-team round (analyst + dataflow-specialist, run in parallel) surfaced enough material findings that the architecture plan was BLOCKED at "REVISE BEFORE /todos." Revisions applied in-session under the autonomize directive. Net effect: the fix's substance is unchanged (per-loop pool keying for async transactions) but the implementation path is now reuse-of-existing rather than build-new.

## Findings that drove the revision

| ID                                 | Severity | Finding                                                                                                                                                                                                 | Disposition                                                                                                                                                     |
| ---------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------- | --------------- | ------------------------------------------------- |
| C1 (analyst + dataflow-specialist) | CRITICAL | Plan invented a phantom `_build_pool_key_for_dataflow` helper that does not exist. Three pool registries exist, not one.                                                                                | Replaced with reuse of `AsyncSQLDatabaseNode._get_adapter()` via the existing `_get_cached_db_node(db_type)` accessor (pattern from `transaction_nodes.py:59`). |
| C2 (analyst)                       | CRITICAL | All `engine.py:NNNN` citations ambiguous between two distinct files (`packages/kailash-dataflow/src/dataflow/engine.py` 560 LOC and `packages/kailash-dataflow/src/dataflow/core/engine.py` 10443 LOC). | Global `s/engine.py/core/engine.py/` across all analysis docs and journals.                                                                                     |
| C3 (analyst)                       | CRITICAL | Pool key shape mismatch: plan said `(connection_string, id(loop))`; actual `_generate_pool_key` is `loop_id                                                                                             | db_type                                                                                                                                                         | connection | pool_size | max_pool_size`. | Resolved by reuse — the node owns key generation. |
| H2 (analyst)                       | HIGH     | Plan claimed `initialize_pool` runs `SELECT 1` today; verification shows it does NOT. The reachability proof is `await adapter.connect()` succeeding.                                                   | Phase 2 preserves the existing `connect()`-based gate; does NOT add a new `SELECT 1`.                                                                           |
| H3 (dataflow-specialist)           | HIGH     | Concurrent `begin()` calls on a fresh loop both miss the registry and create racing pools.                                                                                                              | Closed automatically by reusing `AsyncSQLDatabaseNode._get_adapter()`'s existing `_pool_locks` per-key lock.                                                    |
| H4 (analyst)                       | HIGH     | No test for "first DB touch IS the transaction" path.                                                                                                                                                   | Added test #6.                                                                                                                                                  |
| H5 (analyst)                       | HIGH     | No test for `execute_raw` outside `async with` body after the migration.                                                                                                                                | Added test #7.                                                                                                                                                  |
| H6 (analyst)                       | HIGH     | Pool-cap exhaustion under pytest-xdist multi-loop unmitigated.                                                                                                                                          | Added autouse `set_pool_defaults(idle_timeout=2)` fixture + test #9 stress check.                                                                               |
| M2 (analyst)                       | MEDIUM   | Phase 4 spec text would have been spec-first design-doc work (violates `spec-accuracy.md` Rule 5).                                                                                                      | Spec edits land same PR but commit order is code-then-spec, prose written in present tense describing post-merge behavior.                                      |
| M3 (analyst)                       | MEDIUM   | Cross-SDK inspection not run.                                                                                                                                                                           | Explicitly out-of-scope this PR; user-gated follow-up; `repo-scope-discipline.md` cited.                                                                        |
| H2 (dataflow-specialist)           | HIGH     | `_PoolWrapper` becomes orphan code after fix.                                                                                                                                                           | Explicitly deleted in Phase 1 same PR per `rules/orphan-detection.md`.                                                                                          |

## Why reuse-of-existing is the better fix

The original plan's "extract a helper" approach assumed the priority-chain logic in `AsyncSQLDatabaseNode._get_adapter()` should be exposed for non-node callers. The red-team showed why that's wrong:

1. The priority chain is ~150 LOC. Re-implementing in dataflow would mean two places to maintain.
2. The locks and cap enforcement are coupled to the node's instance state. Extracting them as free functions would require either passing state explicitly (verbose) or making the helper a free function that takes the node as input (just call the node's method directly).
3. There is already a precedent (`transaction_nodes.py:59`). `TransactionManager` consuming the same path is a small uniformity win.

This is the optimal disposition under `/autonomize` Rule 4 (completeness): the smallest change that closes the bug AND aligns DataFlow's three pool surfaces under one registry path.

## Cost of the red team

3 parallel verification agents (cluster 1+2+3) + 2 parallel red-team agents (analyst + dataflow-specialist) + orchestrator reconciliation = ~5 agent-runs in this `/analyze`. Without the red team, the plan would have shipped:

- a phantom-helper Phase 1 that fails import on first PR-CI run
- a wrong pool-key shape that bypasses the cap defense
- a spec-first violation
- 4 missing tests
- `_PoolWrapper` orphan code surviving merge

Each finding is a downstream cycle the red team converted into an in-session edit.

## Consequences

- Plan now grounded — every cited path resolves via grep against `main`.
- `/todos` phase has a clean target: 4 shards, 9 tests, one PR.
- The "reuse-of-existing" disposition is itself an institutional pattern worth recording (see `rules/agents.md` MUST Rule 4 on same-class fix-immediately). The pattern: when a bug surfaces a missing call to an EXISTING tested helper, reuse beats invention.

## For Discussion

1. **Counterfactual**: if the plan had skipped the red-team round (under time pressure) and gone straight to /todos, when would the C1+C3 issues have surfaced? Probably at /implement Phase 1 — the agent would attempt `from kailash.nodes.data.async_sql import _build_pool_key_for_dataflow`, get an ImportError, then have to redesign the resolution under shard pressure. The cost of that reset (one wasted shard's context) > the cost of the red-team round.
2. **Specific data**: 3 CRITICAL + 5 HIGH findings on a single architecture plan. Is this normal for /analyze output? The kailash-ml audits had similar density. The pattern: first-pass plans are seductive precisely because the high-level direction sounds right; the structural defects hide in the implementation details. Hence the red-team-after-plan ritual.
3. **Process question**: should `/analyze` ALWAYS spawn a red-team round before signaling complete? Today the convention is "red team scrutinizes" but the gate is informal. Codify candidate: a hard gate "no /analyze report unless ≥2 red-team agents have run and findings are reconciled" — applies when the workstream's complexity exceeds a threshold (e.g., touches load-bearing logic, ≥3 source files). This issue would have triggered.

## Source citations (verified post-revision)

- Reuse pattern reference: `packages/kailash-dataflow/src/dataflow/nodes/transaction_nodes.py:26-69`
- `_get_cached_db_node`: search via grep — present on DataFlow per the reuse pattern
- `AsyncSQLDatabaseNode._get_adapter`: `src/kailash/nodes/data/async_sql.py:4173-4318`
- `_generate_pool_key`: `src/kailash/nodes/data/async_sql.py:4130-4172` (5-component key shape verified)
- `_PROCESS_POOL_REGISTRY`: `src/kailash/nodes/data/async_sql.py:2655-2670`
- `_pool_locks`: per-key lock via `dpi_b_pool_lock` in `_get_adapter` priority chain
- `_PoolWrapper` (to be deleted): `packages/kailash-dataflow/src/dataflow/features/transactions.py:441`
- `set_pool_defaults`: `src/kailash/nodes/data/async_sql.py:2684`
