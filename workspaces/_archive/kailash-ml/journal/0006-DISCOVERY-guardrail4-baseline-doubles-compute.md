---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T16:33:00Z
author: agent
session_turn: 3
project: kailash-ml
topic: Agent Guardrail 4 (baseline comparison) doubles compute cost silently
phase: analyze
tags: [ml, agents, guardrails, performance, automl, red-team]
---

# Discovery: Guardrail 4 Baseline Comparison Doubles Compute Cost for Agent-Augmented Engines

## Context

During red team analysis of the 5 mandatory agent guardrails specified in the kailash-ml brief, cross-referencing the guardrail definitions against the AutoML engine's execution model revealed that Guardrail 4 ("Pure algorithmic recommendation shown alongside agent recommendation") has an unaddressed compute cost that could make agent-augmented engines impractical for large datasets.

## The Finding

Guardrail 4 requires that every agent-augmented engine call produces BOTH an algorithmic baseline AND the agent's recommendation, so the user can compare them. For AutoMLEngine, this means:

1. Run full hyperparameter search algorithmically (the baseline path)
2. Run agent-augmented hyperparameter search (the agent path)
3. Present both results to the user for comparison

If AutoML takes 30 minutes on a dataset, Guardrail 4 doubles that to 60 minutes. The user pays the full algorithmic baseline cost even when using agents. This cost scales with dataset size and model complexity -- for large production datasets, the overhead could be hours.

No research file, the brief, or the value proposition analysis quantifies this cost. The guardrail is presented as a safety mechanism without acknowledging its performance implications.

## The Fix

The baseline should compare **recommendations**, not **results**. The algorithmic baseline is "what the default algorithm would select" (e.g., LightGBM with default hyperparameters, computed in seconds), not "what the full algorithmic AutoML pipeline produces after exhaustive search." The user sees: "The agent recommends XGBoost with these hyperparameters (confidence: 0.82). The algorithmic default would be LightGBM with default settings." This is a meaningful comparison that costs near-zero compute.

Additionally, Guardrail 1 (confidence scores) suffers from an epistemic weakness: LLM self-assessed confidence is not a calibrated probability. Renaming from `confidence` to `self_assessed_confidence` and documenting the limitation prevents users from treating it as statistical certainty.

## Implications

- The guardrail specification must be refined before implementation, not during
- All 5 guardrails need a performance analysis pass, not just a correctness analysis
- The audit trail guardrail (Guardrail 5) should batch writes rather than write per-decision to avoid database pressure during high-trial AutoML runs

## For Discussion

1. If Guardrail 4 compares recommendations rather than full training results, is it still a meaningful safety check? A user could argue that recommending LightGBM vs XGBoost is less informative than showing actual performance differences on their data.
2. If Guardrail 4 had been designed from the start as "compare recommendations, not results," would the original red team rounds (RT1-RT3 in the brief) have caught this compute cost issue, or was the issue only visible when the AutoML execution model was analyzed in detail?
3. The 5 guardrails were designed as a unit. Weakening Guardrail 4 (from full baseline to recommendation comparison) changes the safety profile. Should the guardrail set be re-evaluated holistically, or is this a local fix?
