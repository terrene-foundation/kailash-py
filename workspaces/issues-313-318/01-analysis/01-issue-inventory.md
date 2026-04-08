# Issue Inventory — #308, #313–#318

## Triage Summary

| #   | Package          | Title                                   | Priority | Complexity   | Actionable?                  |
| --- | ---------------- | --------------------------------------- | -------- | ------------ | ---------------------------- |
| 313 | kailash-ml       | PreprocessingPipeline cardinality guard | P1       | Small-Medium | Yes                          |
| 314 | kailash-ml       | ModelVisualizer EDA charts              | P1       | Medium       | Yes                          |
| 315 | kailash-ml       | training_history y_label                | Normal   | Trivial      | Yes                          |
| 316 | kaizen-agents    | Export SupervisorWorkerPattern          | Normal   | Trivial      | Yes                          |
| 317 | kailash-ml       | ExperimentTracker standalone usage      | Normal   | Low-Medium   | Yes                          |
| 318 | kailash-ml       | ParamDistribution type field docs       | Normal   | Low          | Yes                          |
| 308 | pact (cross-sdk) | Pact engine governance helpers          | Tracking | N/A          | No — Python already complete |

**6 actionable issues, 1 tracking-only.**

## Package Distribution

- **kailash-ml**: 5 issues (#313, #314, #315, #317, #318) — dominant workload
- **kaizen-agents**: 1 issue (#316)
- **kailash-pact**: 1 issue (#308, tracking only)

## Dependency Graph

No inter-issue dependencies. All 6 actionable issues can be implemented in parallel.

## Bonus Findings

1. **README fabrication** — kailash-ml README has multiple examples that don't match actual APIs:
   - ExperimentTracker example calls nonexistent `initialize()`, wrong arg types for `start_run`, wrong params for `list_runs`
   - SearchSpace/ParamDistribution example uses nonexistent fields (`model_class`, `framework`, `parameters`, `values`)
   - These should be fixed alongside #317 and #318

2. **Deprecated module past removal date** — `kaizen_agents/agents/coordination/__init__.py` re-exports pattern classes with deprecation warning claiming removal in v0.5.0, but current version is 0.6.0. Should be cleaned up alongside #316.
