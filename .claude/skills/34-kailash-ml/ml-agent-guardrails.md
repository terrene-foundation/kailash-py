# ML Agent Guardrails

5 mandatory guardrails for agent-augmented ML engines, plus reference for the 6 Kaizen agents (DataScientist, FeatureEngineer, ModelSelector, ExperimentInterpreter, DriftAnalyst, RetrainingDecision).

## The 5 Mandatory Guardrails

Every agent-augmented ML engine MUST implement all 5 guardrails via `AgentGuardrailMixin`. These are non-negotiable — no agent recommendation reaches the user without passing through all 5.

### 1. Confidence Floor on Agent Trials

The agent's confidence floor is set via `AutoMLConfig.min_confidence` (0.0-1.0). Trials
the agent proposes below the floor are denied rather than blindly trusted — they surface
in `result.denied_trials`.

```python
from kailash_ml.automl import AutoMLConfig

# Trials below the confidence floor are denied (counted in result.denied_trials).
config = AutoMLConfig(agent=True, min_confidence=0.6)
```

### 2. Cost Budget Tracking

Cumulative LLM cost is tracked and capped at `max_llm_cost_usd`. Prevents runaway agent spending during exploration.

```python
from kailash_ml import AutoMLEngine, BudgetExhaustedError
from kailash_ml.automl import AutoMLConfig

config = AutoMLConfig(
    agent=True,
    max_llm_cost_usd=5.0,  # Hard cap on LLM spending
)

engine = AutoMLEngine(config=config, tenant_id="default", actor_id="ci")
result = await engine.run(space=search_space, trial_fn=trial_fn)
# result.cumulative_cost_microdollars — total LLM spend for this run

# Exceeding budget raises BudgetExhaustedError, not silent truncation
```

**Financial validation**: `math.isfinite()` on `max_llm_cost_usd` — NaN bypasses all numeric comparisons, Inf defeats upper-bound checks.

### 3. Human Approval Gate for Production Changes

Agents cannot promote models to production or trigger retraining without human approval. `auto_approve=False` is the default.

```python
# auto_approve=False (the default) means agent-proposed actions above the budget /
# cost-approval threshold are withheld rather than auto-executed.
config = AutoMLConfig(agent=True, auto_approve=False)

result = await engine.run(space=search_space, trial_fn=trial_fn)
# result.denied_trials — trials the guardrail withheld
# result.early_stopped / result.early_stopped_reason — whether a gate halted the run
```

**Opt-in override**: `auto_approve=True` removes the gate. Use only in fully automated pipelines with monitoring.

### 4. Baseline Comparison

Run the search twice — once tagged `"baseline"` (pure algorithmic) and once tagged
`"agent"` — and compare `result.best_trial` across the two runs to verify agent
intelligence adds value. The `source_tag` is recorded on every trial for audit.

```python
baseline = await engine.run(space=search_space, trial_fn=trial_fn, source_tag="baseline")
agent_run = await engine.run(space=search_space, trial_fn=trial_fn, source_tag="agent")

# Compare the best trial's metric across the two runs.
if agent_run.best_trial.metric_value <= baseline.best_trial.metric_value:
    # Agent did not beat the baseline — keep the baseline result.
    pass
```

### 5. Full Audit Trail

Every trial and its cost are recorded on the result and via the engine's
`cost_tracker`; denials and early-stop reasons are first-class result fields.

```python
result = await engine.run(space=search_space, trial_fn=trial_fn)

# Per-run audit surface (no separate query call needed):
print(result.total_trials, result.completed_trials, result.denied_trials, result.failed_trials)
print(result.cumulative_cost_microdollars)
for trial in result.all_trials:
    print(trial)  # each trial carries its params, metric_value, source, and cost_microdollars
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
