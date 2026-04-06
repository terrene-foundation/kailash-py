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
from kailash_ml.engines.automl_engine import AutoMLEngine

automl = AutoMLEngine()
result = await automl.run(
    data=df,
    target_column="target",
    task="classification",
    time_budget_seconds=300,
)
print(f"Best model: {result.best_model_name}")
print(f"Best score: {result.best_score:.4f}")
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
