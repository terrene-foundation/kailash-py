# ML Model Registry

ModelRegistry provides model versioning, lifecycle management, artifact storage with SHA256 integrity, and MLflow MLmodel format compatibility.

## Setup

```python
from kailash_ml import ModelRegistry
from kailash_ml.engines import LocalFileArtifactStore
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

registry = ModelRegistry(
    conn,
    artifact_store=LocalFileArtifactStore("./artifacts"),
)
await registry.initialize()
```

## Model Lifecycle

Every model progresses through 4 stages with explicit transitions:

```
staging --> shadow --> production --> archived
   |                      |
   +--- (rejected) -------+--- (rollback to shadow)
```

| Stage          | Purpose                                  | Who Transitions       |
| -------------- | ---------------------------------------- | --------------------- |
| **staging**    | Just trained, not yet validated          | TrainingPipeline      |
| **shadow**     | Running alongside production, no traffic | Human or DriftMonitor |
| **production** | Serving live traffic                     | Human approval gate   |
| **archived**   | Retired, kept for audit/reproducibility  | Automatic or manual   |

## Register a Model

```python
model_id = await registry.register(
    name="churn_predictor",
    model_class="sklearn.ensemble.RandomForestClassifier",
    artifact_path="./artifacts/rf_model.pkl",
    metrics={"accuracy": 0.92, "f1": 0.87},
    schema_name="user_churn",
    tags={"team": "data-science", "experiment": "exp_042"},
)
# Model starts in 'staging' stage
```

## Lifecycle Transitions

```python
# Promote to shadow (parallel run alongside production)
await registry.transition(model_id, stage="shadow")

# Promote to production (requires human approval in agent-augmented mode)
await registry.transition(model_id, stage="production")

# Archive when superseded
await registry.transition(model_id, stage="archived")

# Rollback: move production model back to shadow
await registry.transition(model_id, stage="shadow")
```

## Query Models

```python
# Get latest production model
model = await registry.get_latest(name="churn_predictor", stage="production")

# Get specific version
model = await registry.get(model_id="model_abc123")

# List all versions
models = await registry.list_versions(name="churn_predictor")

# Filter by stage
staging_models = await registry.list_versions(
    name="churn_predictor",
    stage="staging",
)

# Filter by metrics threshold
good_models = await registry.list_versions(
    name="churn_predictor",
    min_metrics={"accuracy": 0.90},
)
```

## SHA256 Integrity

Every registered artifact has a SHA256 hash computed at registration time and verified on load. This prevents silent model corruption.

```python
# Hash computed automatically at registration
model_id = await registry.register(
    name="churn_predictor",
    artifact_path="./artifacts/rf_model.pkl",
    ...
)

# Integrity verified automatically on load
model = await registry.load(model_id)
# Raises IntegrityError if hash mismatch

# Manual verification
is_valid = await registry.verify_integrity(model_id)
```

## Versioning

Models are versioned automatically within a name. Each registration creates a new version.

```python
# Version 1
await registry.register(name="churn_predictor", ...)  # v1

# Version 2 (same name, new registration)
await registry.register(name="churn_predictor", ...)  # v2

# Get specific version
model_v1 = await registry.get(name="churn_predictor", version=1)
model_v2 = await registry.get(name="churn_predictor", version=2)

# Get latest regardless of version
latest = await registry.get_latest(name="churn_predictor")
```

## MLflow MLmodel Format Compatibility

ModelRegistry reads and writes the MLflow MLmodel format for interoperability with existing ML tooling.

```python
from kailash_ml.compat import MlflowFormatReader, MlflowFormatWriter

# Import from MLflow artifact
reader = MlflowFormatReader()
model_info = reader.read("./mlruns/0/abc123/artifacts/model/MLmodel")
model_id = await registry.register(
    name=model_info.name,
    model_class=model_info.model_class,
    artifact_path=model_info.artifact_path,
    metrics=model_info.metrics,
)

# Export to MLflow format
writer = MlflowFormatWriter()
model = await registry.get(model_id)
writer.write(model, output_path="./mlflow_export/")
# Produces MLmodel file + artifact compatible with mlflow.pyfunc.load_model()
```

## Metadata and Tags

```python
# Add metadata at registration
model_id = await registry.register(
    name="churn_predictor",
    tags={"experiment": "exp_042", "dataset": "2025-Q1"},
    description="Random forest trained on Q1 2025 data",
    ...
)

# Update tags later
await registry.update_tags(model_id, {"deployed_by": "ci-pipeline"})

# Search by tags
models = await registry.search(tags={"experiment": "exp_042"})
```

## Integration with TrainingPipeline

TrainingPipeline automatically registers trained models in staging:

```python
from kailash_ml import TrainingPipeline

pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
result = await pipeline.train(schema=schema, model_spec=spec, eval_spec=eval_spec)
# result.model_id is already registered in 'staging'
# Metrics from eval_spec are attached to the registry entry
```

## Critical Rules

- Models always start in `staging` — no direct-to-production registration
- SHA256 integrity check on every load — no silent corruption
- Human approval required for `shadow → production` in agent-augmented mode
- Archived models are never deleted — kept for audit and reproducibility
- Model class strings validated against allowlist before any dynamic import
