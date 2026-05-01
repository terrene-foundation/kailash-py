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
from kailash_ml import (
    FeatureStore, ModelRegistry, TrainingPipeline,
    InferenceServer, DriftMonitor,
)

# Shared connection (required -- see rules/dataflow-pool.md)
conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

# Initialize engines
features = FeatureStore(conn)
registry = ModelRegistry(conn)
pipeline = TrainingPipeline(registry)
server = InferenceServer(registry)
monitor = DriftMonitor(conn)
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
# Register a model version
version = await registry.register_version(
    name="churn_predictor",
    artifact=model_bytes,
    signature=ModelSignature(input_schema=[...], output_schema=[...]),
    metrics={"accuracy": 0.92, "f1": 0.87},
)

# Promote through stages
await registry.transition_stage(name, version.version, "shadow")
await registry.transition_stage(name, version.version, "production")

# ONNX export (requires [onnx] extra)
from kailash_ml import OnnxBridge
bridge = OnnxBridge()
onnx_bytes = bridge.export(model, input_schema)

# MLflow v1 format compatibility
from kailash_ml import MlflowFormatReader, MlflowFormatWriter
writer = MlflowFormatWriter()
writer.save(model_dir, flavor="sklearn", model=model)
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

# Pure algorithmic (no LLM)
automl = AutoMLEngine(registry=registry, pipeline=pipeline)

# With LLM augmentation (5 guardrails)
automl = AutoMLEngine(
    registry=registry,
    pipeline=pipeline,
    agent_infusion=my_agent_infusion,  # AgentInfusionProtocol
)
result = await automl.run(data=df, target="churn", task="classification")
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
