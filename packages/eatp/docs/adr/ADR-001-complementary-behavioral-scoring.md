# ADR-001: Complementary Behavioral Scoring

**Status**: Accepted
**Date**: 2026-03-14

## Context

EATP's structural trust score (chain completeness, delegation depth, constraint coverage, posture, recency) evaluates the _configuration_ of an agent's trust chain. It does not reflect the agent's _runtime behavior_ — an agent with a perfect chain can still behave poorly.

## Decision

Behavioral scoring is complementary, not a replacement. The combined score blends structural (60%) and behavioral (40%) by default. Behavioral data is caller-provided — the SDK does not collect it automatically.

## Rationale

- **60/40 weighting**: Structural represents the governance foundation; behavioral represents runtime evidence. Governance should outweigh runtime to prevent gaming (an agent can inflate approval rates).
- **Gaming resistance**: `interaction_volume` factor (log-scaled, weight 10) penalizes low-volume agents that might cherry-pick easy approvals.
- **Fail-safe**: Zero behavioral data = score 0, grade F. Unknown agents are not trusted.
- **Backward compatible**: No behavioral data means combined = structural score. Existing code is unaffected.

## Consequences

- Callers must maintain `BehavioralData` counters in their enforcement pipeline.
- `BehavioralData` persistence is in-memory only for v0.1. A `BehavioralStore` protocol may be added in v0.2.
