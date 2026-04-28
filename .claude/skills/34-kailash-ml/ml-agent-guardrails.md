# ML Agent Guardrails

5 mandatory guardrails for agent-augmented ML engines, plus reference for the 6 Kaizen agents (DataScientist, FeatureEngineer, ModelSelector, ExperimentInterpreter, DriftAnalyst, RetrainingDecision).

## The 5 Mandatory Guardrails

Every agent-augmented ML engine MUST implement all 5 guardrails via `AgentGuardrailMixin`. These are non-negotiable — no agent recommendation reaches the user without passing through all 5.

### 1. Confidence Scores on Every Recommendation

Every agent recommendation includes a confidence score (0.0-1.0). Low-confidence recommendations are flagged to prevent blind trust in agent outputs.

```python
# Agent output always includes confidence
result = await automl.run(schema=schema, data=df)
# result.recommendation.confidence = 0.85
# result.recommendation.reasoning = "High F1 correlation with ensemble approach"

# Low confidence triggers explicit warning
if result.recommendation.confidence < 0.6:
    # Agent adds: "Low confidence — consider manual review"
    pass
```

### 2. Cost Budget Tracking

Cumulative LLM cost is tracked and capped at `max_llm_cost_usd`. Prevents runaway agent spending during exploration.

```python
from kailash_ml.engines.automl_engine import AutoMLConfig

config = AutoMLConfig(
    agent=True,
    max_llm_cost_usd=5.0,  # Hard cap on LLM spending
)

engine = AutoMLEngine(feature_store=fs, model_registry=registry, config=config)
result = await engine.run(schema=schema, data=df)
# result.agent_cost_usd = 2.37  (total LLM cost for this run)

# Exceeding budget raises BudgetExhaustedError, not silent truncation
```

**Financial validation**: `math.isfinite()` on `max_llm_cost_usd` — NaN bypasses all numeric comparisons, Inf defeats upper-bound checks.

### 3. Human Approval Gate for Production Changes

Agents cannot promote models to production or trigger retraining without human approval. `auto_approve=False` is the default.

```python
config = AutoMLConfig(
    agent=True,
    auto_approve=False,  # DEFAULT — human must approve production changes
)

# Agent recommends but does not execute:
result = await engine.run(schema=schema, data=df)
# result.pending_actions = [
#     {"action": "promote_to_production", "model_id": "abc123", "awaiting_approval": True},
#     {"action": "retrain", "reason": "drift detected", "awaiting_approval": True},
# ]

# Human approves explicitly
await engine.approve_action(result.pending_actions[0])
```

**Opt-in override**: `auto_approve=True` removes the gate. Use only in fully automated pipelines with monitoring.

### 4. Baseline Comparison

Agent must beat a non-agent baseline. A pure algorithmic baseline (no LLM) runs alongside the agent to verify that agent intelligence adds value.

```python
result = await engine.run(schema=schema, data=df)

# Both results always available
# result.agent_result     — agent-augmented outcome
# result.baseline_result  — pure algorithmic baseline (no LLM)

# Agent recommendation rejected if it doesn't beat baseline
if result.agent_result.f1 <= result.baseline_result.f1:
    # Falls back to baseline automatically
    # Logs: "Agent recommendation did not beat baseline (agent: 0.82, baseline: 0.84)"
    pass
```

### 5. Full Audit Trail

All agent decisions logged to `_kml_agent_audit_log` table with bounded storage (`deque(maxlen=N)`).

```python
# Every agent action is logged
# Columns: timestamp, agent_name, action, input_summary, output_summary,
#           confidence, cost_usd, approved_by, baseline_comparison

# Query audit trail
audit = await engine.get_audit_trail(limit=100)
for entry in audit:
    print(f"{entry.timestamp} | {entry.agent_name} | {entry.action} | "
          f"confidence={entry.confidence} | cost=${entry.cost_usd}")
```

## AgentGuardrailMixin

All 5 guardrails are implemented in `_guardrails.py` as a mixin that agent-augmented engines inherit.

```python
from kailash_ml.engines._guardrails import AgentGuardrailMixin

class AutoMLEngine(AgentGuardrailMixin, BaseEngine):
    # Mixin provides:
    # - _check_confidence(recommendation) -> warns if low
    # - _track_cost(llm_call) -> raises BudgetExhaustedError if exceeded
    # - _require_approval(action) -> blocks until human approves
    # - _compare_baseline(agent_result, baseline_result) -> falls back if worse
    # - _log_audit(action, details) -> writes to audit trail
    pass
```

## The 6 ML Agents

All agents require `kailash-ml[agents]` (which installs kailash-kaizen). All follow the LLM-first rule — `tools.py` provides dumb data endpoints, the LLM does ALL reasoning via Signatures.

### DataScientistAgent

Profiles data and recommends preprocessing strategies.

```python
# Tools: profile_data, get_column_stats, sample_rows
# Signature outputs: data_quality_report, preprocessing_recommendations, confidence
```

### FeatureEngineerAgent

Generates and ranks candidate features.

```python
# Tools: compute_feature, check_target_correlation
# Signature outputs: candidate_features, rankings, expected_lift, confidence
```

### ModelSelectorAgent

Reasons about which model family fits the data characteristics.

```python
# Tools: list_available_trainers, get_model_metadata
# Signature outputs: recommended_model, alternatives, reasoning, confidence
```

### ExperimentInterpreterAgent

Analyzes trial results and explains outcomes.

```python
# Tools: get_trial_details, compare_trials
# Signature outputs: interpretation, key_findings, next_steps, confidence
```

### DriftAnalystAgent

Interprets drift reports and recommends actions.

```python
# Tools: get_drift_history, get_feature_distribution
# Signature outputs: drift_analysis, affected_features, severity, recommended_action, confidence
```

### RetrainingDecisionAgent

Decides whether to retrain, rollback, or continue serving.

```python
# Tools: get_prediction_accuracy, trigger_retraining
# Signature outputs: decision, reasoning, urgency, confidence
```

## Double Opt-In

Agent augmentation requires both conditions:

1. **Code opt-in**: `agent=True` in engine config
2. **Package opt-in**: `pip install kailash-ml[agents]`

Without both, engines run in pure algorithmic mode with no LLM calls.

```python
# Pure algorithmic (no agents)
config = AutoMLConfig(task_type="classification")

# Agent-augmented (both opt-ins)
config = AutoMLConfig(
    task_type="classification",
    agent=True,              # Code opt-in
    max_llm_cost_usd=5.0,
)
# Also requires: pip install kailash-ml[agents]
```

## Critical Rules

- All 5 guardrails are mandatory — no agent runs without them
- `auto_approve=False` is the default — human approval for production changes
- Agent must beat non-agent baseline or falls back automatically
- `math.isfinite()` validation on all cost/budget fields
- Audit trail uses bounded storage (`deque(maxlen=N)`) to prevent OOM
- Tools are dumb data endpoints — LLM does ALL reasoning (see `rules/agent-reasoning.md`)
