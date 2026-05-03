---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.457Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: MLEngine.finalize() — full-fit retrain on combined train+holdout set (shard-B)
phase: implement
tags: [auto-generated, kailash-ml, mlengine, finalize, full-fit, shard-b]
related_journal: []
---

# DECISION — MLEngine.finalize() — full-fit retrain (shard-B)

## Commit

`8cd1d2b0d633` — feat(ml): implement MLEngine.finalize() — full-fit retrain (shard-B)

## Body

Replaces the Phase 3 `NotImplementedError` stub with a production implementation per `specs/ml-engines.md` §2.2.

**Candidate resolution**: accepts either a `TrainingResult` directly or a model-URI string (`models://<name>/v<version>`). URI strings are parsed via the new `_parse_model_uri` helper and loaded from the registry; the result is wrapped into a read-through `TrainingResult` so callers can reach `family` + `hyperparameters` uniformly.

**Behavior**:

- `full_fit=True` (default): re-train the candidate's family on the combined train+holdout set by dispatching through `self.fit()` so the Lightning-spine invariant holds (§2.1 MUST 7). Escape-hatch `data=` and `target=` let `finalize` run without a prior `setup()` — same contract as `compare()` so sibling shard A's `setup()` landing is not a blocker.
- `full_fit=False`: re-wrap the candidate without retraining, useful when the caller wants to mark a candidate as finalized for audit without paying the retrain cost.

`tenant_id` propagates onto `FinalizeResult` AND the inner `training_result` per §4.2 MUST 3.

Adds `_ensure_registry_for_read()` — the read-side registry-loading helper. Writes (`register()`) still belong to sibling shard A; this method is a bounded read-only bootstrap that keeps `finalize()` and `evaluate()` functional against a pre-populated registry.

Pre-commit bypassed (`core.hooksPath=/dev/null`): the hook resolves `.venv/bin/python` relative to the worktree cwd and the worktree has no local venv. Per `rules/git.md` § Pre-Commit Hook Workarounds.

## For Discussion

1. **Counterfactual**: `full_fit=True` dispatches through `self.fit()` to preserve the Lightning-spine invariant. If finalize had directly instantiated the family's trainer (bypassing `self.fit()`), which invariants from §2.1 MUST 7 would be silently violated — and would those violations have been visible in the `FinalizeResult` or only at serve time?

2. **Data-referenced**: `full_fit=False` is documented as useful "when the caller wants to mark a candidate as finalized for audit without paying the retrain cost." The commit does not specify whether `FinalizeResult.model_version` is the same object as the input candidate or a new registry entry. If two calls to `finalize(candidate, full_fit=False)` produce two separate `FinalizeResult` objects pointing to the same underlying artifact, how does the audit table distinguish them?

3. **Design**: The `_ensure_registry_for_read()` helper is explicitly bounded to read-only operations. Shard A's `register()` owns write access. This split ownership was driven by parallel worktree coordination. Is read/write registry split a permanent design decision or an implementation artifact of the parallel-shard approach? Should a future consolidation phase unify registry access into a single method?
