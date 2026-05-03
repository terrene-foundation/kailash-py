---
type: GAP
date: 2026-04-01
created_at: 2026-04-01T16:35:00Z
author: agent
session_turn: 3
project: kailash-ml
topic: kailash-ml-protocols method signatures are undefined despite being a permanent interface
phase: analyze
tags: [ml, protocols, kaizen, circular-dependency, api-design, gap]
---

# Gap: kailash-ml-protocols Method Signatures Are Not Defined

## Context

kailash-ml-protocols is the thin interface package (~50KB) that breaks the circular dependency between kailash-ml and kailash-kaizen. The brief defines two protocols at a high level: `MLToolProtocol` (with methods `predict`, `get_metrics`, `trigger_retrain`) and `AgentInfusionProtocol` (with methods `suggest_features`, `select_model`, `interpret_results`). The dependency analysis (`05-dependency-analysis.md`) confirms the package is the right solution.

## The Gap

The actual method signatures -- parameter names, types, return types, async vs sync, error behavior -- are not defined anywhere in the research files, the brief, or the value proposition analysis. The only specification is a list of method names.

This matters because protocol interfaces are effectively permanent. Per the dependency analysis: "Protocol methods cannot be removed without breaking implementations. Only additive changes are safe." And: "Breaking protocol changes require a major version bump of ALL three packages." A poorly designed protocol locks three packages into a bad interface.

## Specific Unanswered Questions

### MLToolProtocol

1. `predict()` -- Does it accept a single record (`dict`) or a batch (`list[dict]` / `pl.DataFrame`)? Or both via overloading?
2. `predict()` -- Does it return raw predictions (`list[float]`) or structured results (`dict` with predictions, probabilities, metadata)?
3. `get_metrics()` -- Does it return all metrics for a model, or accept a filter (metric name, time range)?
4. `get_metrics()` -- What is the return type? A flat dict (`{"accuracy": 0.95}`) or a structured object (`list[MetricSpec]`)?
5. `trigger_retrain()` -- Is this synchronous (blocks until training completes) or asynchronous (returns a training_id for polling)?
6. `trigger_retrain()` -- Does it accept training configuration (data source, model spec) or use the model's existing config?

### AgentInfusionProtocol

7. `suggest_features()` -- What input does it receive? Raw data profile? Column names? The agent context?
8. `select_model()` -- Does it return a single model recommendation or a ranked list?
9. `interpret_results()` -- What "results" does it interpret? Training metrics? Drift reports? Both?

### Shared Types

10. `FeatureSchema`, `ModelSignature`, `MetricSpec` -- These are listed but not defined. Their field sets determine what information flows between kailash-ml and kailash-kaizen.

## Why This Cannot Be Deferred to Implementation

If protocol design happens during /implement, the risk is:

- Developer A implements `MLToolProtocol.predict(features: dict) -> list[float]` in kailash-ml
- Developer B implements the Kaizen consumer expecting `predict(features: pl.DataFrame) -> PredictionResult`
- The mismatch is discovered late, requiring a protocol change that cascades to both packages

Protocol design must be finalized in /todos so that both kailash-ml and kailash-kaizen implementation can proceed in parallel against a stable contract.

## Recommended Action

Before implementation begins, write the complete Protocol classes:

```python
# Example (to be validated against actual call sites)
@runtime_checkable
class MLToolProtocol(Protocol):
    async def predict(self, model_name: str, features: dict[str, Any]) -> PredictionResult: ...
    async def predict_batch(self, model_name: str, records: list[dict[str, Any]]) -> list[PredictionResult]: ...
    async def get_metrics(self, model_name: str, version: str | None = None) -> dict[str, float]: ...
    async def trigger_retrain(self, model_name: str, config: RetrainConfig | None = None) -> str: ...  # returns training_id
```

Then validate each method against:

- Every call site in kailash-ml agents (the DataScientistAgent tools, the ModelSelectorAgent tools)
- Every call site in kailash-kaizen ML tool registration
- The Nexus handler interface for prediction endpoints

## For Discussion

1. The protocol defines `predict()` accepting `dict[str, Any]` as features. But kailash-ml's internal API is polars-only. Should the protocol use polars types (coupling both packages to polars) or dict types (requiring conversion at every call site)? This is a fundamental design tension between type safety and dependency minimization.
2. `trigger_retrain()` is async by nature (training takes minutes to hours). But Kaizen agents call tools synchronously via the Delegate pattern. How does an async retrain operation fit into a synchronous tool invocation? Should the tool return a training_id immediately and the agent poll for completion?
3. If the protocol package had been designed with only `predict()` and `get_metrics()` (the two most certain methods) and `trigger_retrain()` was added in v1.1, would this conservative approach reduce the risk of locking in a wrong interface? What is the cost of not having `trigger_retrain()` in v1?
