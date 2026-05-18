---
type: DECISION
date: 2026-05-06
created_at: 2026-05-06T04:46:00Z
author: agent
session_id: 568d8b2e-d820-4272-a450-5f4ed5fe8209
project: issue-835-dataflow-transaction-eventloop
topic: Reject brief candidates A/B/C; adopt Candidate D (per-loop pool registry)
phase: analyze
tags: [dataflow, transactions, asyncpg, root-cause-fix, candidate-selection]
---

# DECISION — Reject brief candidates A/B/C; adopt Candidate D

## Decision

For issue #835, reject all three fix candidates proposed in the issue body. Adopt **Candidate D**: route `TransactionManager._get_adapter()` through the existing `_PROCESS_POOL_REGISTRY` (loop-id keyed), preserving the fail-fast `SELECT 1` reachability check via a transient connection. Remove the long-lived `_connection_manager._adapter` field. Full plan in `02-plans/01-architecture.md`.

## Why each brief candidate is rejected

**Candidate A** (re-order `_get_adapter()` to prefer the AsyncSQLNode pool): NO-OP. Cluster 3 verification confirmed `self.dataflow._cached_async_node` (the "AsyncSQLNode pool" branch) has ZERO production setters. The branch is dead code; reordering dead code is no-op.

**Candidate B** (lazy bind in `initialize_pool`): BLOCKED by `rules/dataflow-pool.md` Rule 2. The proposal is identical to `lazy_connect=True`, which is explicitly BLOCKED — `DataFlow.__init__` MUST verify reachability via `SELECT 1` before accepting traffic. Skipping reachability turns a config error into a user-facing outage.

**Candidate C** (gate `DataFlowExpressSync` behind `enable_sync_api=True`): WRONG TARGET. `SyncExpress` and `SyncTransactionManager` are already lazy (constructed on first property access). They are NOT involved in the failure mode — in the bug repro, the daemon thread is never spawned because user code never accesses those properties. Gating documented public surfaces (`db.express_sync`, `db.transactions_sync`) behind a new kwarg also triggers `rules/zero-tolerance.md` Rule 6a deprecation cycle, multiplying scope without fixing the bug.

## Why Candidate D

**Root cause vs. symptom (`/autonomize` Rule 2):** the brief's three fixes all patch surfaces. The actual root cause is that DataFlow's async transaction surface retains a single asyncpg pool object across multiple event loops — structurally incompatible with asyncpg's loop-binding contract. Candidate D adopts the per-loop pool model that `db.express.*` already uses. After the fix, no pool is reused across loop boundaries anywhere in DataFlow.

**Reuses tested infrastructure:** `_PROCESS_POOL_REGISTRY`, `_generate_pool_key`, `_idle_pool_reaper_loop`, DPI-B2 max-pool cap, DPI-B3 reaper. All have institutional history (issues #697, #698) and live test coverage. Candidate D adds ~120 LOC of dispatch logic without inventing new mechanisms.

**Closes the institutional gap:** the architecture flattens to a single rule — "asyncpg pools are loop-bound; every consumer of asyncpg in DataFlow looks pools up via `_PROCESS_POOL_REGISTRY`." Today the rule has an exception (the async transaction surface). After the fix, it has none.

**Captures regression coverage:** Phase 3 of the plan adds 5 Tier-2 tests covering the cross-loop scenarios the bug exhibits — closing the test-coverage gap that let this bug ship undetected (`test_issue_707_*` and `test_issue_711_*` happen to run in the same loop that constructs the DataFlow, so the bug is invisible to them).

## Alternatives considered (beyond brief candidates)

- **Reinitialize-on-loop-mismatch at `acquire()` time:** detect when `pool._loop != asyncio.get_running_loop()`, drop the pool, recreate. Considered and rejected — the same outcome (per-loop pool) achieved more directly by keying on `id(loop)` from the start. Recreate-on-mismatch also leaves a window where the old pool's connections leak.
- **Run all DataFlow on a singleton daemon-thread loop:** considered and rejected — fights against asyncio's "the running loop is the application's loop" model. Mainstream Python async code uses `asyncio.run`, pytest-asyncio per-test loops, FastAPI's loop, etc. A singleton daemon would force every consumer onto a non-native loop and break ergonomics.
- **Defer pool creation entirely:** the plan does this for the long-lived pool (no retained `_adapter` after Phase 2), but reachability checking still needs a connection at init. Hence "transient connection at init, lazy pool at first use, per-loop after that."

## Consequences

**Immediate (this PR):**

- `db.transactions.begin()` works across loop boundaries (the bug is fixed).
- `db.express.*` behavior unchanged (already loop-aware).
- `db.transactions_sync.begin()` behavior unchanged (already loop-aware via fresh-connection-per-begin).
- Internal `_connection_manager._adapter` field removed; 4 internal callers migrated.

**Forward (institutional):**

- All asyncpg consumers in DataFlow now go through one registry. Future async features that need a pool MUST use `_PROCESS_POOL_REGISTRY` (or be rejected at code review). The architecture is uniform.
- `specs/dataflow-cache.md §12.1` will document loop-affinity for async transactions, mirroring §12.7's documentation for the sync surface.
- Cross-SDK companion question recorded for kailash-rs (Tokio runtime — does the analogous pool binding hold? Likely yes by Tokio construction but worth verifying in a kailash-rs session, gated by user approval per `rules/upstream-issue-hygiene.md` Rule 1).

## Follow-up actions

1. `/todos` phase: shard the plan into 4 phases (rewrite `_get_adapter`, transient health check, Tier-2 tests, spec updates), all in one PR per shard-budget calculation.
2. `/implement` phase: execute under the standard mechanical-sweep reviewer prompts (`rules/agents.md` MUST: AST/grep mechanical sweeps).
3. Post-merge `/codify`: capture the "third pool surface migrated to per-loop registry" pattern as an addition to `specs/dataflow-cache.md §13.4`. The pattern itself doesn't need a new rule — it's an instance of `dataflow-pool.md` Rule 2 — but the narrative is worth recording.
4. User-gated cross-SDK filing for kailash-rs.

## For Discussion

1. **Counterfactual**: would Candidate D have been the obvious pick if the architecture plan had been written without first running cluster 3 (which proved candidates A/B/C unworkable)? The brief's candidates are seductive precisely because they sound like surface-level reorderings — "switch which pool we prefer", "defer init", "make sync optional". Only the cluster-3 verification proved each candidate's structural blocker. The lesson: brief-stated fix candidates require the same verification rigor as brief-stated symptoms.
2. **Specific data**: the `_PROCESS_POOL_REGISTRY` size cap is currently 100 (`_POOL_DEFAULTS["max_pool_count_per_process"]`). Production DataFlow workloads typically have 1-2 active loops. Test workloads (pytest-asyncio function-scope) churn loops faster. Will Candidate D's transaction pools push real test suites past 100? The DPI-B3 reaper closes idle pools after 300s by default; tests that run >100 loops in <300s would hit `PoolExhaustedError`. Mitigation: tests can call `set_pool_defaults(idle_timeout=2)` to aggressive-reap; document this in the spec section that opts async transactions into the registry.
3. **Reversibility check**: if Candidate D ships and a downstream consumer surprises us by needing the legacy `_adapter` retention behavior, what's the back-out plan? The plan removes `_adapter` assignment entirely. Reverting requires restoring the field AND the original `_get_adapter` resolution order. Cost: one PR, ~80 LOC. Acceptable.
