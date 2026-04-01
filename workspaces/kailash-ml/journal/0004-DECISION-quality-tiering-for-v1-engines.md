---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T10:45:00Z
author: agent
session_turn: 1
project: kailash-ml
topic: Quality tiering strategy for 9 engines in v1
phase: analyze
tags: [ml, scope, engines, quality, release-strategy]
---

# Decision: Tier Quality Guarantees Across 9 Engines

## Context

Red team analysis (RT-R1-07) identified that shipping 9 engines + 6 agents in v1 carries a 61% probability that at least one engine ships below production quality. Two options were evaluated: (A) ship all 9 with tiered quality guarantees, or (B) ship 5 core engines in v1.0, remainder in v1.1.

## Decision

**Option A: Ship all 9 engines with explicit quality tiering.**

| Tier                         | Engines                                                                      | Guarantee                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| P0 (production)              | TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor | Full test coverage, integration tested, documented, production-ready                   |
| P1 (production with caveats) | HyperparameterSearch, AutoMLEngine                                           | Full test coverage, may have edge cases documented                                     |
| P2 (experimental)            | DataExplorer, FeatureEngineer                                                | Core functionality tested, advanced features may be incomplete, marked `@experimental` |

## Rationale

1. The implementation plan is well-phased. P0 engines (Phases 1-3) are built first and most thoroughly tested. P2 engines (Phase 4, later sessions) get less soak time but are self-contained.
2. Cutting to 5 engines saves 4-6 sessions but delays features that differentiate kailash-ml from raw sklearn. AutoML and DataExplorer are selling points.
3. The `@experimental` decorator is honest with users and sets expectations without hiding functionality.
4. kailash-align depends on kailash-ml's ModelRegistry (P0) and possibly FeatureStore (P0). These are guaranteed regardless of tiering.

## Alternatives Considered

**Option B (5 engines, v1.0/v1.1 split)**: Lower risk, higher confidence in shipped quality. Rejected because the phased implementation plan already handles complexity sequencing, and the P2 engines (DataExplorer, FeatureEngineer) are low-risk (stateless/simple).

**Option C (ship all 9 with uniform quality)**: Aspirational but statistically unlikely given the session budget. Would require extending the timeline.

## Consequences

- P2 engines must have documentation clearly marking them as experimental
- The implementation plan should allocate extra sessions for P0 engine hardening if P2 engines fall behind
- Release notes must explicitly state which engines are P0/P1/P2

## For Discussion

1. The P2 engines (DataExplorer, FeatureEngineer) are the most agent-dependent. If agent guardrails (RT-R1-04) are harder to implement than expected, should these engines ship without agent augmentation in v1?
2. How long should `@experimental` status last? Is there a session/release target for promoting P2 engines to production?
3. kailash-align's dependency is on P0 engines. But if a user builds a workflow that chains FeatureEngineer (P2) -> TrainingPipeline (P0) -> InferenceServer (P0), the experimental engine becomes a critical path. Should we document this risk?
