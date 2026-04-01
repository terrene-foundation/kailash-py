---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T10:45:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: Defer all 4 alignment agents to v1.1
phase: analyze
tags: [agents, kaizen, scope, agent-reasoning, decision]
---

# Decision: Defer All 4 Alignment Agents to v1.1

## Decision

All 4 alignment-specific Kaizen agents (AlignmentStrategistAgent, DataCurationAgent, TrainingConfigAgent, EvalInterpreterAgent) are deferred from v1.0 to v1.1.

## Alternatives Considered

### A: All 4 agents in v1.0 (original plan)

- **Pros**: Complete Kaizen integration from day 1. Consistent with kailash-ml's 6 agents.
- **Cons**: 1 additional implementation session. 2 of the 4 agents encode deterministic logic (agent-reasoning rule concern). None are required for the core train->evaluate->deploy->integrate workflow.

### B: 2 agents in v1.0 (DataCuration + EvalInterpreter only)

- **Pros**: Keeps the genuinely useful agents. Drops the deterministic ones.
- **Cons**: Still 0.5 session overhead. Partial agent coverage may confuse users who expect the full set.

### C: All 4 agents deferred to v1.1 (chosen)

- **Pros**: Saves 1 full session. Focuses v1.0 on the core lifecycle (registry, training, evaluation, serving, bridge). Avoids agent-reasoning rule violations.
- **Cons**: No AI-guided workflow in v1.0. Users must make all alignment decisions themselves.

## Rationale

### AlignmentStrategistAgent: Deterministic Logic

The SFT-vs-DPO recommendation is a 4-row lookup table, not a reasoning task. Having instruction data -> SFT. Having preference data -> DPO. Having both -> SFT then DPO. Having neither -> "collect data." An LLM call to make this recommendation adds latency, cost, and no intelligence. This risks violating the agent-reasoning rule: "If you're writing conditionals to route, classify, extract, or decide -- you're building a script, not an agent."

### TrainingConfigAgent: Also Deterministic

Given model size + GPU memory, the config is largely formulaic: r=16 for 7B, gradient_checkpointing=True always, bf16 if A100/H100. A documentation page with recommended configs provides the same value with zero latency.

### DataCurationAgent and EvalInterpreterAgent: Genuine But Optional

These provide real value (data quality analysis, evaluation interpretation) but the core workflow functions without them. Users who train and evaluate models can interpret their own results for v1.0.

### Session Savings

Deferring saves 1 implementation session (TSG-405) from the critical path, reducing the estimate from 7-11 to 6-10 sessions.

## Consequences

- v1.0 has no AI-guided alignment workflow. Users make all decisions (method, config, deploy/retrain) themselves.
- v1.1 can introduce agents with better understanding of real user patterns (learned from v1.0 usage).
- The `agents/` directory in the package structure is created but empty in v1.0.

## For Discussion

1. The kailash-ml brief includes 6 agents in v1.0 scope (DataScientist, FeatureEngineer, ModelSelector, ExperimentInterpreter, DriftAnalyst, RetrainingDecision). If kailash-align defers its agents to v1.1, should kailash-ml also reconsider agent scope for consistency?
2. If AlignmentStrategistAgent were redesigned to recommend _hyperparameters_ (learning rate, LoRA rank, number of epochs) rather than _method_ (SFT vs DPO), would it pass the agent-reasoning rule? Hyperparameter recommendation genuinely benefits from LLM reasoning about trade-offs.
3. How will users who expected AI-guided workflow (per the brief's "4 agents" promise) react to v1.0 without agents? Is this a messaging risk?
