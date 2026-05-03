---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.455Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: MLEngine.evaluate() — holdout/shadow/live modes (shard-B)
phase: implement
tags:
  [
    auto-generated,
    kailash-ml,
    mlengine,
    evaluate,
    shadow,
    holdout,
    live,
    shard-b,
  ]
related_journal: []
---

# DECISION — MLEngine.evaluate() — holdout/shadow/live modes (shard-B)

## Commit

`c70fa8f8fb74` — feat(ml): implement MLEngine.evaluate() — holdout/shadow/live modes (shard-B)

## Body

Replaces the Phase 4 `NotImplementedError` stub with a production implementation per `specs/ml-engines.md` §2.2.

**Model resolution**: accepts either a `ModelVersion` directly or a URI string (`models://<name>/v<version>`); URI strings are parsed via the shared `_parse_model_uri` helper (added with `finalize()`) and loaded from the registry.

**Three modes** (scoring identical, audit/drift side-effects differ):

- `holdout`: offline evaluation. Metrics + structured log line for audit. No drift-monitor interaction.
- `shadow`: read-only compare against a live model. Emits audit with `operation="shadow_evaluate"` and explicitly skips drift-monitor updates — shadow MUST NOT poison the baseline.
- `live`: current-model evaluation. Emits `operation="evaluate"` AND refreshes the drift monitor's current window when one is wired via `self._drift_monitor`. Missing reference is an INFO log, not an error — the evaluation itself succeeded; drift is optional.

**Target resolution**: prefer `model.signature.target`, fall back to `self._setup_result.target`, raise if neither. Silent target inference is BLOCKED per `rules/zero-tolerance.md` Rule 3. `TargetNotFoundError` (typed) raised when the supplied data is missing the target column.

**Default metric set**: classification → accuracy/f1/precision/recall; regression → rmse/mae/r2; clustering → [] (callers pass explicit). This mirrors the existing `TrainingPipeline` conventions so a user who evaluates the same model via two surfaces gets the same defaults.

**Inference**: dispatches through the `InferenceServer` primitive so the pickle/ONNX load path is shared with `predict()`. `tenant_id` propagates onto `EvaluationResult` per §4.2 MUST 3.

Pre-commit bypassed (`core.hooksPath=/dev/null`): worktree has no local `.venv`. Per `rules/git.md` § Pre-Commit Hook Workarounds.

## For Discussion

1. **Counterfactual**: Shadow mode explicitly skips drift-monitor updates because "shadow MUST NOT poison the baseline." If shadow evaluations were allowed to update the drift monitor, what failure scenario would emerge — and would it be detectable before a live model was incorrectly flagged as drifted?

2. **Data-referenced**: The default metric set for clustering is `[]` (callers must pass explicit metrics). The commit states this mirrors `TrainingPipeline` conventions. If a user calls `engine.evaluate(model, data)` on a clustering model without passing metrics, they receive an `EvaluationResult` with an empty metrics dict — which looks like a successful evaluation with no findings. Is this the right UX, or should an empty metric set raise a warning?

3. **Design**: Target resolution falls back from `model.signature.target` to `self._setup_result.target`, then raises. This means `evaluate()` can be called without a prior `setup()` only if the model's signature already encodes the target. Is this documented in the spec, and what happens if `finalize()` was called with `full_fit=False` (no retrain) — does the resulting model's signature reliably carry a target?
