# Model Registry

Version, track, and manage ML models through their lifecycle.

## Register a Model

```python
from kailash_ml.engines.model_registry import ModelRegistry

registry = ModelRegistry()

# Register with metrics
version = await registry.register(
    name="churn-predictor",
    model=trained_model,
    metrics={"accuracy": 0.92, "f1": 0.88, "auc": 0.95},
    tags={"team": "data-science", "dataset": "q4-2025"},
)
```

## Version Management

```python
# List all versions
versions = await registry.list_versions("churn-predictor")
for v in versions:
    print(f"v{v.version}: {v.stage} — accuracy={v.metrics.get('accuracy')}")

# Load a specific version
model = await registry.load("churn-predictor", version=2)

# Load latest
model = await registry.load("churn-predictor")
```

## Stage Transitions

Models progress through stages: `staging` -> `shadow` -> `production` -> `archived`.

```python
# Promote to production
await registry.transition("churn-predictor", version=3, stage="production")

# Archive old version
await registry.transition("churn-predictor", version=1, stage="archived")
```

## MLflow Compatibility

ModelRegistry uses a compatible artifact format. Export for MLflow:

```python
artifact_path = await registry.export_artifact("churn-predictor", version=3)
# Returns path to model artifacts (model.pkl, metadata.json)
```

## Common Errors

**`ModelNotFoundError: no versions registered`** -- Register at least one version before loading.

**`StageTransitionError: cannot skip stages`** -- Models must progress through stages in order. You cannot jump from `staging` to `archived`.
