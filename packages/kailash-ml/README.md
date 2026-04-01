# kailash-ml

Classical and deep learning lifecycle for the Kailash ecosystem. Train models, store features, serve predictions, monitor drift, and optionally augment with AI agents.

Part of the [Kailash Python SDK](https://github.com/terrene-foundation/kailash-py) by the Terrene Foundation.

## Installation

```bash
pip install kailash-ml            # Base (~195MB): sklearn, LightGBM, polars
pip install kailash-ml[dl]        # + PyTorch, Lightning
pip install kailash-ml[rl]        # + Stable Baselines3, Gymnasium
pip install kailash-ml[agents]    # + Kaizen (LLM-augmented ML)
pip install kailash-ml[full]      # Everything
```

## Quick Start

```python
import polars as pl
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.model_registry import ModelRegistry
from kailash_ml.engines.training_pipeline import TrainingPipeline, ModelSpec, EvalSpec
from kailash_ml.engines.inference_server import InferenceServer
from kailash_ml._types import FeatureSchema, FeatureField
from dataflow import DataFlow

# Initialize
db = DataFlow("sqlite:///ml.db")
await db.initialize()

feature_store = FeatureStore(db)
registry = ModelRegistry(db)
pipeline = TrainingPipeline(feature_store, registry)

# Define schema
schema = FeatureSchema("customers", [
    FeatureField("age", "float64"),
    FeatureField("income", "float64"),
], entity_id_column="customer_id")

# Train
data = pl.DataFrame({"customer_id": ["c1","c2","c3"], "age": [25.0,35.0,45.0], "income": [50000.0,75000.0,90000.0], "churn": [0,1,0]})
result = await pipeline.train(
    data, schema,
    ModelSpec("sklearn.ensemble.RandomForestClassifier", {"n_estimators": 100}, "sklearn"),
    EvalSpec(metrics=["accuracy", "f1"]),
    "churn_predictor",
)
print(f"Accuracy: {result.metrics['accuracy']:.2f}")

# Serve predictions
server = InferenceServer(registry)
predictions = await server.predict("churn_predictor", data)
```

## Engines

kailash-ml provides 9 engines organized in 3 quality tiers:

### P0: Production (stable API, full test coverage)

| Engine               | Purpose                                                                   |
| -------------------- | ------------------------------------------------------------------------- |
| **FeatureStore**     | Compute, version, and serve features with point-in-time correct retrieval |
| **ModelRegistry**    | Model lifecycle management (staging -> shadow -> production -> archived)  |
| **TrainingPipeline** | Full training lifecycle: data prep -> train -> evaluate -> register       |
| **InferenceServer**  | Load, cache, and serve predictions; auto-expose via Nexus                 |
| **DriftMonitor**     | Feature drift (PSI, KS-test) and performance degradation detection        |

### P1: Production with Caveats (tested, API may evolve)

| Engine                   | Purpose                                                  |
| ------------------------ | -------------------------------------------------------- |
| **HyperparameterSearch** | Grid, random, Bayesian (optuna), successive halving      |
| **AutoMLEngine**         | Automated model selection with optional LLM augmentation |

### P2: Experimental (functional, API may change)

| Engine              | Purpose                                                  |
| ------------------- | -------------------------------------------------------- |
| **DataExplorer**    | Statistical profiling with polars, plotly visualizations |
| **FeatureEngineer** | Automated feature generation and selection               |

### Quality Tier Promotion

- **P2 -> P1**: 3 integration tests, 2 real-world user validations, no open bugs above LOW
- **P1 -> P0**: No API changes for 3+ minor releases, complete documentation, performance benchmarks

## Agents (Optional)

6 Kaizen agents provide LLM-augmented ML workflows. Double opt-in: install `kailash-ml[agents]` AND pass `agent=True`.

| Agent                      | Purpose                                | Tier |
| -------------------------- | -------------------------------------- | ---- |
| DataScientistAgent         | Data analysis + ML strategy            | P0   |
| RetrainingDecisionAgent    | Retrain/monitor/rollback decision      | P0   |
| ModelSelectorAgent         | Model family + config recommendation   | P1   |
| ExperimentInterpreterAgent | Trial result analysis + next steps     | P1   |
| FeatureEngineerAgent       | Feature design and pruning             | P2   |
| DriftAnalystAgent          | Drift interpretation + action decision | P2   |

All agents emit `self_assessed_confidence` (0-1), enforce cost budgets, require human approval by default, show baseline comparison, and log decisions to DataFlow.

## ONNX Bridge

Models registered in ModelRegistry are automatically exported to ONNX format when supported:

- **sklearn**: ~90% success rate (all standard estimators)
- **LightGBM**: ~95% success rate
- **PyTorch**: 70-85% (feedforward networks)

Failed ONNX exports are non-fatal -- the model falls back to native Python inference. Use `model.onnx_status` to check export status.

## polars-native

All data operations use polars DataFrames internally. The `kailash_ml.interop` module provides converters for ecosystem integration:

```python
from kailash_ml.interop import to_sklearn_input, to_pandas, from_pandas

X, y = to_sklearn_input(polars_df, label_col="target")
pandas_df = to_pandas(polars_df)
polars_df = from_pandas(pandas_df)
```

## DataFlow Integration

All engines persist data through DataFlow -- no additional infrastructure needed. Features, model metadata, drift reports, and audit logs use the same database as your application.

## License

Apache-2.0
