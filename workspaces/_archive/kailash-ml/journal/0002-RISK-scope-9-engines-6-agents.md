---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T10:15:00Z
author: agent
session_turn: 1
project: kailash-ml
topic: Scope risk from 9 engines + 6 agents in v1
phase: analyze
tags: [ml, scope, risk, engines, agents]
---

# Risk: 9 Engines + 6 Agents May Exceed Quality Threshold for v1

## Context

The kailash-ml architecture specifies 9 engines and 6 Kaizen agents for v1. The implementation plan estimates 11-18 sessions. Red team analysis (RT-R1-07) quantified the quality risk.

## The Risk

If each engine has a 90% probability of shipping production-quality, the probability of ALL 9 being production-quality is 0.9^9 = 39%. There is a 61% chance that at least one engine ships below quality expectations.

The 6 agents add further surface area: each requires Signature validation, tool testing, guardrail testing, and integration with engines. The agents depend on the engines being stable, creating a dependency chain where engine quality issues cascade into agent reliability problems.

## Evidence

- Implementation plan shows 1-2 sessions per engine. Complex engines (AutoMLEngine, TrainingPipeline) may need more.
- The protocol package, interop module, ONNX bridge, and RL extra are additional deliverables beyond the 9 engines.
- Integration testing across engines (e.g., TrainingPipeline -> FeatureStore -> ModelRegistry -> InferenceServer) is non-trivial.

## Proposed Mitigation: Quality Tiering

**P0 (guaranteed production)**: TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor -- the core lifecycle
**P1 (production with caveats)**: HyperparameterSearch, AutoMLEngine -- useful but less critical
**P2 (experimental/beta)**: DataExplorer, FeatureEngineer -- nice-to-have, mark as experimental if quality lags

Ship all 9, but set explicit quality expectations. P2 engines get an `@experimental` decorator and documentation warning.

## Alternative: MVP (5 engines in v1.0, 4 in v1.1)

This saves 4-6 sessions and guarantees quality of the core lifecycle. The trade-off is delayed availability of productivity engines.

## For Discussion

1. The 39% all-engines-production-quality probability assumes independence. In reality, later engines benefit from patterns established by earlier ones. Does this correlation increase or decrease the risk?
2. If kailash-align (the 8th framework) depends on kailash-ml's ModelRegistry, and ModelRegistry ships in v1 but FeatureEngineer ships as experimental, does this affect kailash-align's v1 plans?
3. What is the reputational cost of shipping "experimental" engines? Would users interpret `@experimental` as "this will break" or as "this is new and improving"?
