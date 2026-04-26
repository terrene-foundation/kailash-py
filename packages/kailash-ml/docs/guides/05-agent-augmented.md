# Agent-Augmented ML

Use Kaizen agents to augment the ML workflow with LLM-powered analysis.

Requires: `pip install kailash-ml[agents]`

## DataScientist Agent

Analyze a dataset and formulate an ML strategy:

```python
from kailash_ml.agents import DataScientistAgent
from kailash_ml.engines.data_explorer import DataExplorer

# Profile data first
explorer = DataExplorer()
profile = await explorer.profile(df)

# Agent reasons about the data
agent = DataScientistAgent()
result = await agent.recommend(
    data_profile=str(profile.to_dict()),
    business_context="Predict customer churn for telecom",
    constraints="Must train in under 1 hour on a single GPU",
)
print(result["recommended_approach"])
print(f"Confidence: {result['confidence']}")
```

## AutoML Engine

Automated model selection and hyperparameter tuning:

```python
from kailash_ml.automl import AutoMLConfig, AutoMLEngine
# Equivalent: from kailash_ml import AutoMLEngine

config = AutoMLConfig(
    task_type="classification",
    time_budget_seconds=300,
)
automl = AutoMLEngine(
    config=config,
    tenant_id="acme",
    actor_id="alice@acme",
    connection=conn_mgr,
)
result = await automl.run(space=param_specs, trial_fn=user_trial_fn)
print(f"Best trial: {result.best_trial}")
print(f"Cumulative cost (microdollars): {result.cumulative_cost_microdollars}")
```

## Five Guardrails

Agent-augmented features enforce five guardrails:

1. **Time budget** -- AutoML stops within the specified time
2. **Memory budget** -- Models that exceed available memory are skipped
3. **Validation** -- All results validated against holdout set
4. **Reproducibility** -- Random seeds are fixed and logged
5. **Explainability** -- Feature importance computed for all models

## Common Errors

**`ImportError: kailash-kaizen required`** -- Install with `pip install kailash-ml[agents]`.

**`TimeoutError: AutoML exceeded budget`** -- Increase `time_budget_seconds` or reduce the search space.
