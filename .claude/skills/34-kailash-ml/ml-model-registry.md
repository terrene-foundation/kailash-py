# ML Model Registry

`ModelRegistry` provides model versioning, stage lifecycle management, artifact
storage with SHA256 integrity, ONNX export, and MLflow `MLmodel` format
interoperability. Models are keyed by `(name, version)` and scoped per `tenant_id`.

## Setup

```python
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

# No initialize() — the registry is ready on construction (auto_migrate=True default).
registry = ModelRegistry(conn, LocalFileArtifactStore("./artifacts"))
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

`register_model` takes the serialized model as `bytes` plus a list of `MetricSpec`.
Each registration creates a new version, starting in `staging`.

```python
from kailash_ml.types import MetricSpec
import pickle

artifact = pickle.dumps(trained_model)
mv = await registry.register_model(
    "churn_predictor",
    artifact,
    metrics=[
        MetricSpec(name="accuracy", value=0.92),
        MetricSpec(name="f1", value=0.87),
    ],
)
print(f"Registered {mv.name} v{mv.version} (stage={mv.stage})")  # stage == "staging"
```

## Lifecycle Transitions

`promote_model(name, version, target_stage)` moves a version between stages.

```python
# Promote to shadow (parallel run alongside production)
await registry.promote_model("churn_predictor", version=mv.version, target_stage="shadow")

# Promote to production (gate this behind human approval in agent-augmented mode)
await registry.promote_model("churn_predictor", version=mv.version, target_stage="production")

# Archive when superseded
await registry.promote_model("churn_predictor", version=mv.version, target_stage="archived")

# Rollback: move a production model back to shadow
await registry.promote_model("churn_predictor", version=mv.version, target_stage="shadow")
```

## Query Models

```python
# Latest production version
prod = await registry.get_model("churn_predictor", stage="production")

# Specific version's metadata
model_v2 = await registry.get_model("churn_predictor", version=2)

# All versions of a name
versions = await registry.get_model_versions("churn_predictor")
for v in versions:
    print(f"v{v.version}: {v.stage}")

# All registered model names
names = await registry.list_models()

# Compare two versions' metrics
diff = await registry.compare("churn_predictor", version_a=1, version_b=2)
```

## SHA256 Integrity

Every registered artifact is SHA256-hashed at registration and verified on load,
preventing silent model corruption. `load_artifact` returns the raw bytes; a hash
mismatch raises.

```python
# Hash is computed automatically at register_model time.
artifact_bytes = await registry.load_artifact("churn_predictor", version=2)
model = pickle.loads(artifact_bytes)  # integrity already verified by load_artifact
```

## Versioning

Versions are assigned automatically within a name — each `register_model` call
creates the next version.

```python
await registry.register_model("churn_predictor", pickle.dumps(model_a), metrics=[...])  # v1
await registry.register_model("churn_predictor", pickle.dumps(model_b), metrics=[...])  # v2

model_v1 = await registry.get_model("churn_predictor", version=1)
model_v2 = await registry.get_model("churn_predictor", version=2)
latest = await registry.get_model("churn_predictor")  # highest version
```

## MLflow MLmodel Format Compatibility

The registry reads and writes the MLflow `MLmodel` layout natively for
interoperability with existing ML tooling.

```python
# Import a model from an MLflow artifact directory
imported = await registry.import_mlflow("./mlruns/0/abc123/artifacts/model")
print(f"Imported {imported.name} v{imported.version}")

# Export a registered version to the MLflow MLmodel layout
mlflow_dir = await registry.export_mlflow("churn_predictor", version=2, output_dir="./mlflow_export")
# mlflow_dir is loadable via mlflow.pyfunc.load_model()
```

## Lineage

```python
# Record training lineage for a version (links to the tracker run + inputs)
await registry.record_lineage(
    name="churn_predictor",
    version=mv.version,
    tenant_id="_single",
    tracker_run_id="run-abc123",
    training_data_uri="feature_store://user_churn@v2",
)

# Walk the lineage graph for a model reference
graph = await registry.build_lineage_graph(ref="churn_predictor", tenant_id="_single")
```

## Integration with TrainingPipeline

`TrainingPipeline(feature_store, registry)` registers trained models in `staging`
as part of `train(...)`.

```python
from kailash_ml import TrainingPipeline

pipeline = TrainingPipeline(feature_store=fs, registry=registry)
result = await pipeline.train(
    data=df,
    schema=schema,
    model_spec=spec,
    eval_spec=eval_spec,
    experiment_name="churn-2025q1",
)
# The trained model is registered in 'staging'; eval metrics are attached.
```

## Critical Rules

- Models always start in `staging` — no direct-to-production registration
- `register_model` takes `bytes`, not a live model object — serialize first
- SHA256 integrity is verified on every `load_artifact` — no silent corruption
- Human approval gates `shadow → production` in agent-augmented mode
- Archived models are never deleted — kept for audit and reproducibility
