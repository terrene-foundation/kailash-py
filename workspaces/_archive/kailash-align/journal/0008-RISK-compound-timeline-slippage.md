---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T14:45:00+08:00
author: agent
session_turn: 3
project: kailash-align
topic: Session estimate slippage compounds with kailash-ml dependency to potentially double calendar time
phase: analyze
tags: [estimation, kailash-ml, timeline, sessions, risk, critical-path]
---

# Compound Timeline Slippage Risk

## Risk Description

Two independently-identified risks interact to create a compound timeline threat:

1. **RT1-03 (CRITICAL)**: kailash-ml does not exist yet and is a hard prerequisite for AdapterRegistry, the highest-value component.
2. **RT1-04 (HIGH)**: The 7-12 session estimate for kailash-align alone is optimistic by 2-4 sessions based on component-level decomposition.

These are not independent risks. They compound: if kailash-ml takes 5-8 sessions and kailash-align takes 10-16 sessions, and the dependency is sequential (not parallel), the total elapsed time could reach 15-24 sessions.

## The Compound Effect

### Best Case (Parallel Development)

If the ModelRegistry interface is frozen early and both packages develop in parallel:

- kailash-ml: 5-8 sessions (parallel)
- kailash-align: 8-12 sessions (agents deferred, starts after interface freeze)
- Total elapsed: max(8, 12) + 0.5 (interface freeze) = **8.5-12.5 sessions**

### Worst Case (Sequential Development)

If kailash-ml must ship ModelRegistry before kailash-align can start Phase 1:

- kailash-ml Phase 1-2 (ModelRegistry): 3-5 sessions
- kailash-align full: 10-16 sessions
- Total elapsed: 3 + 10 = **13-21 sessions**

### Most Likely Case

Some parallelism but with integration points that create waiting:

- kailash-ml ModelRegistry ships after 3-4 sessions
- kailash-align starts after ModelRegistry, takes 10-14 sessions
- Integration friction adds 1-2 sessions
- Total elapsed: **14-20 sessions**

## Why This Matters

The brief (and journal 0004) references an original estimate of 7-12 sessions for kailash-align. Presenting this estimate without the kailash-ml prerequisite context understates the actual calendar commitment by 50-100%.

The estimation gap has knock-on effects:

- Other workstreams that depend on kailash-align (e.g., kz-engage integration) schedule against the lower number
- Stakeholder expectations are set against 7-12 sessions, not 14-20
- If the estimate slips mid-development, the response may be scope cuts to training or serving -- the two areas where cutting scope removes the most value

## Likelihood and Impact

- **Likelihood**: HIGH -- both contributing risks are individually rated CRITICAL/HIGH
- **Impact**: HIGH -- timeline doubles, stakeholder expectations misaligned, downstream dependencies delayed

## Mitigations

1. **Interface-first development (from RT1-03)**: Freeze the ModelRegistry extension points as a protocol/ABC before either package starts. This enables parallel development and reduces the compound effect.
2. **Revised estimate communication**: Present the estimate as "8-12 sessions for kailash-align after ModelRegistry interface is frozen" rather than "7-12 sessions total." Include kailash-ml timeline separately.
3. **Scope control for v1**: Deferring agents to v1.1 (journal 0004) already reduces the lower bound. If further scope reduction is needed, the AlignmentEvaluator's custom evaluation feature (`evaluate_custom()`) could move to v1.1 without losing standardized benchmark evaluation.
4. **Start AlignmentServing early**: AlignmentServing (GGUF conversion, Ollama deployment) does NOT depend on kailash-ml or ModelRegistry. It can start immediately and surface the highest-risk integration issues (GGUF conversion fragility) before ModelRegistry is ready.

## For Discussion

1. The best-case scenario (8.5-12.5 sessions) requires freezing the ModelRegistry interface before implementation begins. The kailash-ml workspace is currently in its own /analyze phase. Is it realistic to extract and freeze an interface before /todos completes for kailash-ml?
2. If AlignmentServing is started early (before kailash-ml ModelRegistry exists), it must work with a temporary standalone adapter tracking mechanism. When AdapterRegistry arrives later, a migration is needed. Is this migration cost lower than the cost of waiting?
3. The compound timeline risk assumes kailash-ml and kailash-align are developed by the same autonomous agent system (sequential session allocation). If two parallel agent instances could work on both packages simultaneously, how does that change the elapsed time calculation?
