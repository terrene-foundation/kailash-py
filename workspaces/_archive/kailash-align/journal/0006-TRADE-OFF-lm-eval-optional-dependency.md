---
type: TRADE-OFF
date: 2026-04-01
created_at: 2026-04-01T11:15:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: Making lm-eval an optional dependency trades install simplicity for evaluation UX
phase: analyze
tags: [lm-eval, dependencies, evaluation, trade-off]
---

# Trade-Off: lm-eval as Optional Dependency

## What Was Gained

By moving lm-eval from base dependencies to an `[eval]` optional extra:

1. **Reduced base install size**: lm-eval + transitive deps save ~30-50 MB. Small but non-zero.
2. **Cleaner dependency tree**: lm-eval has its own transitive dependencies that may conflict with other packages. Making it optional isolates these conflicts.
3. **Faster install**: Fewer packages to resolve and download for users who only need training + deployment.
4. **Modularity**: Users who bring their own evaluation (custom scripts, W&B, MLflow) skip the lm-eval overhead entirely.

## What Was Sacrificed

1. **Out-of-box experience**: `pip install kailash-align` no longer includes evaluation. Users must install `kailash-align[eval]` or `kailash-align[full]` to use `AlignmentEvaluator.evaluate()`.
2. **Documentation complexity**: Must explain the extra system. "Install kailash-align" becomes "install kailash-align[eval] if you want benchmarks."
3. **Import-time error**: Users who call `AlignmentEvaluator()` without the extra get an ImportError. Clear message, but still a friction point.

## The Deciding Factor

lm-eval-harness runs on evaluation-only machines. Training machines (with GPUs, VRAM constraints) may not need the evaluation harness. Evaluation machines may run benchmarks without needing training infrastructure. The extra system allows these different deployment profiles.

Additionally, lm-eval v0.4+ underwent a significant dependency restructuring (late 2025) where the base package no longer requires torch/transformers. This means lm-eval's own dependency profile is in flux. Making it optional insulates kailash-align from lm-eval's dependency churn.

## Mitigation: "quick" Preset

To offset the UX cost, adding a "quick" evaluation preset (`evaluate(tasks=["quick"])`) that runs a curated, fast benchmark suite (arc_easy + hellaswag + truthfulqa, limit=100, ~5 minutes total). This gives users a one-call evaluation experience once they have the `[eval]` extra installed.

## For Discussion

1. kailash-ml includes scikit-learn and LightGBM in its BASE install specifically so that `pip install kailash-ml` can train and serve a model out of the box. Should the same philosophy apply here -- lm-eval in base so `pip install kailash-align` can train AND evaluate?
2. If lm-eval's dependency restructuring (late 2025) makes it lighter, does the size argument for making it optional weaken enough to reverse this decision?
3. Custom evaluation via `evaluate_custom(scoring_fn=...)` does NOT require lm-eval (it uses transformers.pipeline directly). Should this be more prominently documented as the "no extra needed" evaluation path?
