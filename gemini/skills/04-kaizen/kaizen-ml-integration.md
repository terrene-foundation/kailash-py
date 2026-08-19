---
name: kaizen-ml-integration
description: "kailash-ml engine patterns -- FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, AutoML with LLM guardrails, quality tiers"
---

# kailash-ml Integration Patterns

kailash-ml provides 9 ML lifecycle engines built on Kailash Core SDK infrastructure (ConnectionManager, polars-native data). All engines are lazy-loaded on first access.

## Install

```bash
pip install kailash-ml           # Core engines (polars, numpy, scikit-learn)
pip install kailash-ml[lgb]      # + LightGBM
pip install kailash-ml[onnx]     # + ONNX export
pip install kailash-ml[explore]  # + plotly (DataExplorer)
```

## Engine Overview

| Engine                 | Tier | Purpose                                                                                | Key Dependencies          |
| ---------------------- | ---- | -------------------------------------------------------------------------------------- | ------------------------- |
| `FeatureStore`         | P0   | DataFlow-backed feature versioning, point-in-time queries                              | ConnectionManager, polars |
| `ModelRegistry`        | P0   | Model lifecycle (staging->shadow->production->archived), ONNX export, MLflow v1 compat | ConnectionManager         |
| `TrainingPipeline`     | P0   | sklearn + LightGBM training with checkpoint management                                 | scikit-learn              |
| `InferenceServer`      | P0   | Model cache, lazy Nexus endpoints, MLToolProtocol                                      | -                         |
| `DriftMonitor`         | P0   | PSI, KS-test, performance degradation detection                                        | scipy                     |
| `HyperparameterSearch` | P1   | Grid, random, Bayesian, successive halving                                             | -                         |
| `AutoMLEngine`         | P1   | Algorithmic + optional LLM augmentation with 5 guardrails                              | -                         |
| `DataExplorer`         | P2   | Polars profiling, plotly visualization                                                 | plotly (@experimental)    |
| `FeatureEngineer`      | P2   | Interaction, polynomial, binning transforms                                            | (@experimental)           |

**Quality tiers**: P0 = production-ready, P1 = stable with advanced features, P2 = @experimental (emit `ExperimentalWarning` on use).

## Quick Start

```python
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore  # legacy write surface — top-level FeatureStore is the canonical read surface (kailash-ml 2.0.0, #643)
from kailash_ml import (
    ModelRegistry, TrainingPipeline,
    InferenceServer, DriftMonitor,
)

# Shared connection (required -- see rules/dataflow-pool.md)
conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

# Initialize engines
features = FeatureStore(conn)
await features.initialize()
registry = ModelRegistry(conn)
pipeline = TrainingPipeline(feature_store=features, registry=registry)
# InferenceServer is per-model, built from the registry:
server = InferenceServer.from_registry("churn_predictor", registry=registry)
monitor = DriftMonitor(conn, tenant_id="default")
```

## Type Contracts (kailash_ml.types)

Cross-package contracts (stdlib-only types, no heavy dependencies):

```python
from kailash_ml.types import (
    MLToolProtocol,           # InferenceServer implements this for Kaizen tools
    AgentInfusionProtocol,    # AutoMLEngine's LLM interface
    FeatureSchema,            # FeatureStore schema definition
    FeatureField,             # Individual feature field spec
    ModelSignature,           # Model I/O signature (input/output schemas)
    MetricSpec,               # Metric definition for ModelRegistry
)
```

## ModelRegistry Lifecycle

```
staging -> shadow -> production -> archived
     \       |           |
      \      v           v
       +-> archived   shadow (rollback)
```

```python
# Register a model version (artifact is bytes; metrics is a list of MetricSpec)
version = await registry.register_model(
    "churn_predictor",
    model_bytes,
    metrics=[MetricSpec(name="accuracy", value=0.92), MetricSpec(name="f1", value=0.87)],
    signature=ModelSignature(
        input_schema=schema,
        output_columns=["prediction"],
        output_dtypes=["int"],
        model_type="sklearn",
    ),
)

# Promote through stages
await registry.promote_model("churn_predictor", version.version, "shadow")
await registry.promote_model("churn_predictor", version.version, "production")

# ONNX export (requires [onnx] extra)
from kailash_ml import OnnxBridge
bridge = OnnxBridge()
export = bridge.export(model, framework="sklearn", n_features=10, output_path="model.onnx")

# MLflow MLmodel format compatibility — write a registered version out
from kailash_ml import MlflowFormatReader, MlflowFormatWriter
writer = MlflowFormatWriter()
writer.write(version, output_dir="./mlflow_out")
```

## AutoMLEngine (5 LLM Guardrails)

When `AgentInfusionProtocol` is provided, AutoML uses LLM augmentation for:

1. **Model selection** -- LLM suggests algorithms based on data characteristics
2. **Feature engineering** -- LLM proposes feature transformations
3. **Hyperparameter suggestions** -- LLM narrows search space
4. **Result interpretation** -- LLM explains model performance
5. **Next-step recommendation** -- LLM suggests iteration strategy

All 5 guardrails are opt-in. Without an LLM, AutoML runs purely algorithmically.

```python
from kailash_ml import AutoMLEngine
from kailash_ml.automl import AutoMLConfig

# Pure algorithmic (no LLM): agent defaults to False on the config
automl = AutoMLEngine(
    config=AutoMLConfig(task_type="classification", metric_name="f1", max_trials=50),
    tenant_id="default",
    actor_id="ci",
)

# With LLM augmentation (5 guardrails): set agent=True + pass a governance engine
automl = AutoMLEngine(
    config=AutoMLConfig(task_type="classification", metric_name="f1", agent=True),
    tenant_id="default",
    actor_id="ci",
    governance_engine=my_governance_engine,
)

# run() drives a search space + trial function (see ml-agent-guardrails.md)
result = await automl.run(space=search_space, trial_fn=trial_fn)
```

## Interop Module (8 Converters)

Centralized polars conversion in `kailash_ml.interop`:

```python
from kailash_ml.interop import to_sklearn_input, from_sklearn_output, to_pandas

X, y, col_info = to_sklearn_input(df, feature_columns=["a", "b"], target_column="y")
result_df = from_sklearn_output(predictions, col_info)
pandas_df = to_pandas(df)  # For legacy library compat
```

See `skills/02-dataflow/dataflow-ml-integration.md` for the full converter table.

## Cross-References

- `skills/02-dataflow/dataflow-ml-integration.md` -- FeatureStore + DataFlow integration details
- `kailash_ml.engines` -- Engine implementations
- `kailash_ml.interop` -- Polars converters
- `rules/infrastructure-sql.md` -- SQL safety patterns used by FeatureStore/ModelRegistry
