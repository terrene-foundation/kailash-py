# Model Registry

Version, track, and manage ML models through their lifecycle.

## Register a Model

```python
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
from kailash_ml.types import MetricSpec
import pickle

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
registry = ModelRegistry(conn, LocalFileArtifactStore("./artifacts"))

# Register a serialized model artifact with metrics
artifact = pickle.dumps(trained_model)
mv = await registry.register_model(
    "churn-predictor",
    artifact,
    metrics=[
        MetricSpec(name="accuracy", value=0.92),
        MetricSpec(name="f1", value=0.88),
        MetricSpec(name="auc", value=0.95),
    ],
)
print(f"Registered churn-predictor v{mv.version}")
```

## Version Management

```python
# List all versions
versions = await registry.get_model_versions("churn-predictor")
for v in versions:
    print(f"v{v.version}: {v.stage}")

# Inspect a specific version's metadata
model_v2 = await registry.get_model("churn-predictor", version=2)

# Load a version's raw artifact bytes
artifact_bytes = await registry.load_artifact("churn-predictor", version=2)
```

## Stage Transitions

Models progress through stages: `staging` -> `shadow` -> `production` -> `archived`.

```python
# Promote to production
await registry.promote_model("churn-predictor", version=3, target_stage="production")

# Archive an old version
await registry.promote_model("churn-predictor", version=1, target_stage="archived")
```

## MLflow Compatibility

ModelRegistry exports versions in the MLflow `MLmodel` layout:

```python
mlflow_dir = await registry.export_mlflow("churn-predictor", version=3, output_dir="./mlflow-out")
# Returns the path to the exported MLflow model directory
```

## Common Errors

**`ModelNotFoundError: no versions registered`** -- Register at least one version before loading.

**`StageTransitionError: cannot skip stages`** -- Models must progress through stages in order. You cannot jump from `staging` to `archived`.
