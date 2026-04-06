# kailash-ml

Machine learning lifecycle for the Kailash ecosystem. Train models, store features, serve predictions, monitor drift, and optionally augment decisions with AI agents -- all built on polars DataFrames and backed by a single database.

Part of the [Kailash Python SDK](https://github.com/terrene-foundation/kailash-py) by the Terrene Foundation.

**Version**: 0.2.0 | **License**: Apache-2.0 | **Python**: 3.10+

---

## Why kailash-ml

**Polars-native from the ground up.** Every engine accepts and returns `polars.DataFrame`. Conversion to numpy, pandas, or framework-specific formats happens at the boundary, never inside your pipeline logic. This means you work with a single, fast, memory-efficient data format throughout.

**Zero-config persistence.** All engines store their state -- features, model metadata, drift reports, experiment logs -- through the same database your application already uses. No separate tracking server, no object store to configure, no infrastructure to maintain.

**Agent-augmented, not agent-dependent.** Six Kaizen agents can augment your ML workflow with LLM-powered recommendations. They require double opt-in (install the extras AND pass `agent=True`), enforce cost budgets, and always run alongside a pure algorithmic baseline. You never need agents -- they are a power-user option.

**Production lifecycle built in.** Models move through a governed lifecycle (staging, shadow, production, archived). Drift monitoring runs on a schedule. ONNX export happens automatically. The inference server caches models in memory and exposes predictions via Nexus.

**Security by default.** Model class imports are restricted to an allowlist. All SQL is encapsulated in a single auditable file. Financial fields are validated against NaN and Infinity. Agent cost budgets are hard-capped.

---

## Installation

```bash
# Base install (~195MB): polars, sklearn, LightGBM, scipy, plotly, ONNX
pip install kailash-ml

# Optional extras
pip install kailash-ml[dl]        # + PyTorch, Lightning, transformers
pip install kailash-ml[dl-gpu]    # + onnxruntime-gpu (CUDA inference)
pip install kailash-ml[rl]        # + Stable-Baselines3, Gymnasium
pip install kailash-ml[agents]    # + Kaizen (LLM-augmented ML)
pip install kailash-ml[xgb]       # + XGBoost
pip install kailash-ml[catboost]  # + CatBoost
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[full]      # Everything above
pip install kailash-ml[full-gpu]  # Everything + GPU runtime
```

### Development

```bash
pip install kailash-ml[dev]       # pytest, hypothesis, mypy, ruff
```

---

## Quick Start

```python
import polars as pl
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
from kailash_ml.engines.training_pipeline import TrainingPipeline, ModelSpec, EvalSpec
from kailash_ml.engines.inference_server import InferenceServer
from kailash_ml.types import FeatureSchema, FeatureField


async def main():
    # 1. Connect to a database
    conn = ConnectionManager("sqlite:///ml.db")
    await conn.initialize()

    # 2. Set up engines
    feature_store = FeatureStore(conn)
    await feature_store.initialize()

    registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
    await registry.initialize()

    pipeline = TrainingPipeline(feature_store=feature_store, model_registry=registry)

    # 3. Define your feature schema
    schema = FeatureSchema(
        name="customer_churn",
        features=[
            FeatureField(name="age", dtype="float64"),
            FeatureField(name="tenure_months", dtype="float64"),
            FeatureField(name="monthly_spend", dtype="float64"),
        ],
        entity_id_column="customer_id",
    )

    # 4. Prepare data as a polars DataFrame
    data = pl.DataFrame({
        "customer_id": ["c1", "c2", "c3", "c4", "c5"],
        "age": [25.0, 35.0, 45.0, 55.0, 30.0],
        "tenure_months": [12.0, 24.0, 36.0, 48.0, 6.0],
        "monthly_spend": [50.0, 75.0, 100.0, 125.0, 40.0],
        "churned": [0, 1, 0, 0, 1],
    })

    # 5. Train a model
    result = await pipeline.train(
        data=data,
        schema=schema,
        model_spec=ModelSpec(
            model_class="sklearn.ensemble.RandomForestClassifier",
            hyperparameters={"n_estimators": 100, "max_depth": 5},
            framework="sklearn",
        ),
        eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
        model_name="churn_predictor",
    )
    print(f"Accuracy: {result.metrics['accuracy']:.2f}")
    print(f"Model version: {result.model_version}")

    # 6. Serve predictions
    server = InferenceServer(model_registry=registry)
    predictions = await server.predict("churn_predictor", data)
    print(predictions.predictions)
```

---

## Architecture Overview

```
                              kailash-ml
    +---------------------------------------------------------+
    |                                                         |
    |   types.py (FeatureSchema, ModelSignature, Protocols)   |
    |                          |                              |
    |   +-------- engines/ --------+                          |
    |   |                          |                          |
    |   |  FeatureStore            |  interop.py              |
    |   |  TrainingPipeline  <---->|  (polars <-> sklearn     |
    |   |  ModelRegistry           |   polars <-> lightgbm    |
    |   |  InferenceServer         |   polars <-> pandas      |
    |   |  DriftMonitor            |   polars <-> arrow       |
    |   |  ExperimentTracker       |   polars <-> HuggingFace)|
    |   |  HyperparameterSearch    |                          |
    |   |  AutoMLEngine            |                          |
    |   |  EnsembleEngine          |                          |
    |   |  PreprocessingPipeline   |                          |
    |   |  DataExplorer            |                          |
    |   |  FeatureEngineer         |                          |
    |   |  ModelVisualizer         |                          |
    |   +------------|-------------+                          |
    |                |                                        |
    |   bridge/      |     compat/       dashboard/           |
    |   OnnxBridge   |     MlflowFormat  MLDashboard          |
    |                |                                        |
    |   agents/ (optional, double opt-in)                     |
    |   DataScientist, FeatureEngineer, ModelSelector,        |
    |   ExperimentInterpreter, DriftAnalyst, RetrainingDecision|
    |                |                                        |
    |   rl/ (optional)                                        |
    |   RLTrainer, EnvironmentRegistry, PolicyRegistry        |
    |                |                                        |
    +----------------|----------------------------------------+
                     |
           ConnectionManager (kailash.db)
                     |
               SQLite / PostgreSQL
```

All engines persist through `ConnectionManager` from the core Kailash SDK. The `interop.py` module is the sole conversion point between polars and external frameworks -- no engine file contains direct pandas or numpy conversion logic.

---

## Engines Reference

kailash-ml provides 13 engines plus a bridge and compatibility layer, organized by purpose and stability.

### Core Engines (P0 -- stable API, full test coverage)

#### FeatureStore

```python
from kailash_ml.engines.feature_store import FeatureStore
```

Computes, versions, and serves features with point-in-time correct retrieval. Uses `ConnectionManager` for temporal window queries that require SQL beyond what Express can express. All raw SQL is encapsulated in `_feature_sql.py` -- the engine itself contains zero raw SQL.

Key operations: `ingest()`, `get_features()`, `get_features_at_time()`, `list_feature_sets()`.

#### ModelRegistry

```python
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
```

Manages the complete model lifecycle through four stages: **staging** (newly trained), **shadow** (running alongside production), **production** (serving traffic), and **archived** (retired). Stores artifacts on the local filesystem with optional ONNX export. Reads and writes MLflow MLmodel format v1 for interoperability.

Key operations: `register_model()`, `promote()`, `get_model()`, `list_models()`, `get_production_model()`.

#### TrainingPipeline

```python
from kailash_ml.engines.training_pipeline import TrainingPipeline, ModelSpec, EvalSpec
```

Orchestrates the full training lifecycle: load features, train a model, evaluate metrics, and register the result. Supports scikit-learn and LightGBM model classes out of the box. Model class imports are restricted to a security allowlist (`sklearn.*`, `lightgbm.*`, `xgboost.*`, `catboost.*`, `torch.*`, `lightning.*`, `kailash_ml.*`) to prevent arbitrary code execution.

Key operations: `train()`.

#### InferenceServer

```python
from kailash_ml.engines.inference_server import InferenceServer
```

Loads models from ModelRegistry, caches them in an LRU memory cache, and serves predictions. Supports single-record and batch prediction. Nexus integration is lazy-loaded -- if kailash-nexus is installed, predictions can be auto-exposed as REST endpoints.

Key operations: `predict()`, `predict_batch()`, `load_model()`, `evict()`.

#### DriftMonitor

```python
from kailash_ml.engines.drift_monitor import DriftMonitor, DriftSpec
```

Detects distribution shifts in production data using PSI (Population Stability Index) and the Kolmogorov-Smirnov test. Stores reference distributions and drift reports in the database. Reports classify drift as `none`, `moderate`, or `severe` per feature and overall. Optionally augments reports with agent-powered interpretation (double opt-in).

Key operations: `set_reference()`, `check_drift()`, `get_drift_history()`, `check_performance_degradation()`.

#### ExperimentTracker

```python
from kailash_ml.engines.experiment_tracker import ExperimentTracker
```

Provides MLflow-compatible experiment tracking: experiments, runs, parameters, step-based metrics (for training curves), and artifact metadata. Artifacts are stored on the local filesystem; the database holds metadata only -- no binary blobs in SQL.

Key operations: `create_experiment()`, `run()` (context manager), `log_param()`, `log_metric()`, `log_artifact()`, `get_run()`, `list_runs()`. Standalone usage: `await ExperimentTracker.create("sqlite:///ml.db")`.

### Search and Optimization Engines (P1 -- tested, API may evolve)

#### HyperparameterSearch

```python
from kailash_ml.engines.hyperparameter_search import HyperparameterSearch, SearchSpace, SearchConfig
```

Supports four search strategies for hyperparameter optimization: **grid** (exhaustive), **random** (sampling), **bayesian** (surrogate-model guided), and **successive halving** (early stopping of poor candidates). Integrates with TrainingPipeline for execution and ModelRegistry for result tracking.

Key operations: `search()`.

#### AutoMLEngine

```python
from kailash_ml.engines.automl_engine import AutoMLEngine, AutoMLConfig
```

Orchestrates HyperparameterSearch across multiple model families, ranks results, and optionally augments decisions with Kaizen agents. Requires double opt-in for agent augmentation: set `agent=True` in `AutoMLConfig` AND have `kailash-ml[agents]` installed. Cost budgets cap LLM spending via `max_llm_cost_usd`.

Key operations: `run()`.

#### EnsembleEngine

```python
from kailash_ml.engines.ensemble import EnsembleEngine
```

Creates ensemble models through four strategies: **blending** (weighted average of predictions), **stacking** (meta-learner on base model outputs), **bagging** (bootstrap aggregation), and **boosting** (sequential error correction). All data handling uses polars internally; conversion to sklearn happens at the boundary via `interop.py`.

Key operations: `blend()`, `stack()`, `bag()`, `boost()`.

#### PreprocessingPipeline

```python
from kailash_ml.engines.preprocessing import PreprocessingPipeline
```

Automatic data preprocessing for ML workflows. Auto-detects task type, encodes categoricals, scales numerics, imputes missing values, and splits train/test. Returns a `SetupResult` with transformed data ready for training.

Key operations: `setup()`.

### Experimental Engines (P2 -- functional, API may change)

#### DataExplorer

```python
from kailash_ml.engines.data_explorer import DataExplorer
```

Computes summary statistics, distributions, correlations, and missing value analysis using polars. Generates interactive plotly visualizations. Optionally augments profiling output with agent-generated narrative (double opt-in).

Key operations: `profile()`, `visualize()`, `correlation_matrix()`.

#### FeatureEngineer

```python
from kailash_ml.engines.feature_engineer import FeatureEngineer
```

Generates candidate features (interactions, polynomial, binning, temporal) from source data, evaluates their predictive power, and selects the best subset. Returns ranked features with importance scores.

Key operations: `generate()`, `select()`, `rank()`.

#### ModelVisualizer

```python
from kailash_ml.engines.model_visualizer import ModelVisualizer
```

Produces interactive plotly visualizations for ML model analysis: confusion matrix, ROC curve, precision-recall curve, feature importance, learning curves, residual plots, calibration curves, metric comparison, and training history. All methods return plotly `Figure` objects.

Key operations: `confusion_matrix()`, `roc_curve()`, `precision_recall()`, `feature_importance()`, `learning_curve()`.

### Bridge and Compatibility

#### OnnxBridge

```python
from kailash_ml.bridge.onnx_bridge import OnnxBridge
```

Exports trained models to ONNX format for cross-runtime serving ("train in Python, serve in Rust"). Performs a pre-flight compatibility check, exports the model, and validates the ONNX artifact. Export failure is never fatal -- the model falls back to native Python inference. Approximate success rates: sklearn ~90%, LightGBM ~95%, PyTorch feedforward ~70-85%.

Key operations: `check_compatibility()`, `export()`, `validate()`.

#### MlflowFormatReader / MlflowFormatWriter

```python
from kailash_ml.compat.mlflow_format import MlflowFormatReader, MlflowFormatWriter
```

Reads and writes the MLflow MLmodel YAML format v1. This is format interoperability -- metadata round-trips through MLflow without data loss. kailash-ml does not run an MLflow tracking server, replace experiment tracking, or integrate with the MLflow UI.

Key operations: `MlflowFormatReader.read()`, `MlflowFormatWriter.write()`.

### Quality Tier Promotion

- **P2 to P1**: 3 integration tests, 2 real-world user validations, no open bugs above LOW
- **P1 to P0**: No API changes for 3+ minor releases, complete documentation, performance benchmarks

---

## Type Contracts (`kailash_ml.types`)

All cross-engine and cross-framework type contracts live in `kailash_ml.types`. This module replaced the former `kailash-ml-protocols` package. Every type supports `to_dict()` / `from_dict()` round-trip serialization.

### FeatureField

Defines a single feature column.

```python
from kailash_ml.types import FeatureField

field = FeatureField(
    name="age",
    dtype="float64",     # "int64", "float64", "utf8", "bool", "datetime", "categorical"
    nullable=True,
    description="Customer age in years",
)
```

### FeatureSchema

Defines a complete feature set with entity identification and optional timestamps.

```python
from kailash_ml.types import FeatureSchema, FeatureField

schema = FeatureSchema(
    name="customer_features",
    features=[
        FeatureField(name="age", dtype="float64"),
        FeatureField(name="tenure_months", dtype="float64"),
        FeatureField(name="plan_type", dtype="categorical"),
    ],
    entity_id_column="customer_id",
    timestamp_column="event_time",   # optional, enables point-in-time queries
    version=1,
)

# Round-trip serialization
d = schema.to_dict()
restored = FeatureSchema.from_dict(d)
```

### ModelSignature

Captures the input/output schema of a trained model.

```python
from kailash_ml.types import ModelSignature, FeatureSchema, FeatureField

signature = ModelSignature(
    input_schema=FeatureSchema(
        name="churn_input",
        features=[FeatureField(name="age", dtype="float64")],
        entity_id_column="customer_id",
    ),
    output_columns=["prediction", "probability"],
    output_dtypes=["int64", "float64"],
    model_type="classifier",   # "classifier", "regressor", "ranker"
)
```

### MetricSpec

Records a single evaluation metric with its value and context.

```python
from kailash_ml.types import MetricSpec

metric = MetricSpec(
    name="f1",
    value=0.87,
    split="test",              # "train", "val", "test"
    higher_is_better=True,
)
```

### MLToolProtocol

A `typing.Protocol` that defines the interface for ML tools accessible to Kaizen agents via MCP. Implementors include `InferenceServer` and `ModelRegistry`. The protocol requires three methods:

- `predict(model_name, features)` -- single-record prediction
- `get_metrics(model_name)` -- model evaluation metrics
- `get_model_info(model_name)` -- model metadata and stage

### AgentInfusionProtocol

A `typing.Protocol` that defines the interface for agent-augmented engine methods. Implementors are Kaizen Delegate agents (installed via `kailash-ml[agents]`). Consumers are engines that accept optional agent augmentation. The protocol requires four methods:

- `suggest_model(data_profile, task_type)` -- model family recommendations
- `suggest_features(data_profile, existing_features)` -- feature engineering guidance
- `interpret_results(experiment_results)` -- trial result analysis
- `interpret_drift(drift_report)` -- drift report interpretation

---

## Interop Module

The `kailash_ml.interop` module is the sole conversion point between polars and external frameworks. No engine file contains direct conversion logic.

```python
from kailash_ml.interop import (
    to_sklearn_input,       # polars -> (numpy X, numpy y) for sklearn
    from_sklearn_output,    # numpy predictions -> polars DataFrame
    to_lgb_dataset,         # polars -> LightGBM Dataset
    to_hf_dataset,          # polars -> HuggingFace Dataset
    polars_to_arrow,        # polars -> PyArrow Table
    from_arrow,             # PyArrow Table -> polars DataFrame
    to_pandas,              # polars -> pandas DataFrame
    from_pandas,            # pandas DataFrame -> polars DataFrame
    polars_to_dict_records, # polars -> list of dicts
    dict_records_to_polars, # list of dicts -> polars DataFrame
)

# Example: prepare data for sklearn
X, y = to_sklearn_input(polars_df, label_col="target")

# Example: convert to pandas for libraries that require it
pandas_df = to_pandas(polars_df)
polars_df = from_pandas(pandas_df)
```

Optional dependencies (`lightgbm`, `datasets`, `pyarrow`, `pandas`) are imported lazily so that `import kailash_ml` never fails due to missing extras.

---

## Agent Integration

Six Kaizen agents provide LLM-augmented ML workflows. They follow the LLM-first rule: the LLM does all reasoning, tools are dumb data endpoints.

### Double Opt-In Pattern

Agent augmentation requires two explicit steps:

1. **Install the agents extra**: `pip install kailash-ml[agents]`
2. **Enable in configuration**: pass `agent=True` to the engine config

Without both steps, engines run in pure algorithmic mode.

### Five Mandatory Guardrails

Every agent-augmented operation enforces:

1. **Confidence scores** -- every recommendation includes a self-assessed confidence value (0.0 to 1.0)
2. **Cost budget** -- cumulative LLM cost is capped at `max_llm_cost_usd` (raises `GuardrailBudgetExceededError` if exceeded)
3. **Human approval gate** -- `auto_approve=False` by default; the engine pauses for human confirmation before applying agent recommendations
4. **Baseline comparison** -- a pure algorithmic baseline runs alongside the agent, so you can compare agent-augmented results against non-augmented results
5. **Audit trail** -- all agent decisions are logged to `_kml_agent_audit_log` in the database

### Agent Catalog

| Agent                      | Purpose                                 | Tier |
| -------------------------- | --------------------------------------- | ---- |
| DataScientistAgent         | Data profiling and ML strategy guidance | P0   |
| RetrainingDecisionAgent    | Retrain, monitor, or rollback decisions | P0   |
| ModelSelectorAgent         | Model family and config recommendations | P1   |
| ExperimentInterpreterAgent | Trial result analysis and next steps    | P1   |
| FeatureEngineerAgent       | Feature design, generation, and pruning | P2   |
| DriftAnalystAgent          | Drift interpretation and action plans   | P2   |

### Example: Agent-Augmented AutoML

```python
from kailash_ml.engines.automl_engine import AutoMLEngine, AutoMLConfig

config = AutoMLConfig(
    task_type="classification",
    agent=True,              # Opt-in 1: enable agent augmentation
    auto_approve=False,      # Human approval gate (default)
    max_llm_cost_usd=5.0,   # Cost budget cap
)
engine = AutoMLEngine(
    feature_store=feature_store,
    model_registry=registry,
    config=config,
)
result = await engine.run(schema=schema, data=df)

# result includes both agent recommendations and algorithmic baseline
print(result.best_model)
print(result.agent_recommendations)
```

### Agent Tools

The `kailash_ml.agents.tools` module provides dumb data endpoints that agents call. These tools fetch data, compute statistics, and return raw results -- they contain zero decision logic. Available tools include:

- `profile_data`, `get_column_stats`, `sample_rows` (DataScientistAgent)
- `compute_feature`, `check_target_correlation` (FeatureEngineerAgent)
- `list_available_trainers`, `get_model_metadata` (ModelSelectorAgent)
- `get_trial_details`, `compare_trials` (ExperimentInterpreterAgent)
- `get_drift_history`, `get_feature_distribution` (DriftAnalystAgent)
- `get_prediction_accuracy`, `trigger_retraining` (RetrainingDecisionAgent)

---

## Reinforcement Learning Module

Requires `pip install kailash-ml[rl]` (Stable-Baselines3, Gymnasium, PyTorch).

```python
from kailash_ml.rl import RLTrainer, EnvironmentRegistry, PolicyRegistry
from kailash_ml.rl.trainer import RLTrainingConfig

# Register environment
env_reg = EnvironmentRegistry()
env_reg.register("CartPole-v1")

# Configure policy
policy_reg = PolicyRegistry()
policy_config = policy_reg.get("PPO")

# Train
trainer = RLTrainer(env_registry=env_reg, policy_registry=policy_reg)
config = RLTrainingConfig(
    algorithm="PPO",           # PPO, SAC, DQN, A2C, TD3, DDPG
    policy_type="MlpPolicy",
    total_timesteps=100_000,
    n_eval_episodes=10,
    eval_freq=10_000,
    seed=42,
)
result = await trainer.train(env_id="CartPole-v1", config=config)
print(f"Mean reward: {result.mean_reward:.1f}")
```

---

## ONNX Bridge

Models registered in ModelRegistry are automatically eligible for ONNX export. The OnnxBridge handles the full pipeline: compatibility check, export, and validation.

```python
from kailash_ml.bridge.onnx_bridge import OnnxBridge

bridge = OnnxBridge()

# Check if a model can be exported
compat = bridge.check_compatibility(trained_model)
print(f"ONNX compatible: {compat.is_compatible}")

# Export
if compat.is_compatible:
    export_result = bridge.export(trained_model, output_path="model.onnx")
    print(f"Export success: {export_result.success}")

    # Validate the exported artifact
    validation = bridge.validate("model.onnx", sample_input)
    print(f"Max deviation: {validation.max_deviation:.6f}")
```

ONNX export failure is non-fatal. The model falls back to native Python inference. Check `model.onnx_status` to determine export status.

| Framework | Approximate Success Rate | Notes                                         |
| --------- | ------------------------ | --------------------------------------------- |
| sklearn   | ~90%                     | All standard estimators                       |
| LightGBM  | ~95%                     | Full support                                  |
| PyTorch   | 70-85%                   | Feedforward networks; dynamic graphs may fail |

---

## Dashboard

kailash-ml includes a web dashboard for viewing experiments, runs, metrics, and models.

### Launch

```bash
# CLI entry point
kailash-ml-dashboard

# Or from Python
from kailash_ml.dashboard import MLDashboard

dashboard = MLDashboard(db_url="sqlite:///ml.db")
dashboard.serve(host="0.0.0.0", port=5000)
```

The dashboard is backed by ExperimentTracker and ModelRegistry engines, served via Starlette and uvicorn. It provides a read-only view of your ML experiments -- no state mutation from the UI.

---

## Drift Monitoring

```python
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor, DriftSpec

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

monitor = DriftMonitor(conn)
await monitor.initialize()

# Set a reference distribution (e.g., from your training data)
await monitor.set_reference("churn_model_v1", reference_df)

# Check drift against new production data
report = await monitor.check_drift(
    "churn_model_v1",
    current_df,
    spec=DriftSpec(
        psi_threshold=0.2,         # PSI > 0.2 = severe drift
        ks_alpha=0.05,             # KS test significance level
    ),
)

print(f"Overall drift: {report.overall_drift}")     # "none", "moderate", "severe"
print(f"Features drifted: {report.drifted_features}")

for feature_result in report.feature_results:
    print(f"  {feature_result.feature_name}: PSI={feature_result.psi:.4f}, "
          f"KS={feature_result.ks_statistic:.4f}, drift={feature_result.drift_type}")
```

---

## Experiment Tracking

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import ExperimentTracker

# Option 1: Standalone (factory -- manages its own connection)
async with await ExperimentTracker.create("sqlite:///ml.db") as tracker:
    exp_name = await tracker.create_experiment("my-experiment")
    async with tracker.run(exp_name, run_name="baseline") as run:
        await run.log_metric("accuracy", 0.95)
        await run.log_param("n_estimators", "100")

# Option 2: Shared connection (caller manages ConnectionManager lifecycle)
conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
tracker = ExperimentTracker(conn, artifact_root="./artifacts")

exp_name = await tracker.create_experiment("churn_classification")

async with tracker.run("churn_classification", run_name="rf_baseline") as run:
    # Log parameters
    await run.log_param("n_estimators", "100")
    await run.log_param("max_depth", "5")

    # Log metrics (supports step-based logging for training curves)
    await run.log_metric("accuracy", 0.92)
    await run.log_metric("f1", 0.87)

# Query results
runs = await tracker.list_runs("churn_classification")
best_run = runs[0]
print(f"Best accuracy: {best_run.metrics['accuracy']}")

await conn.close()
```

---

## Hyperparameter Search

```python
from kailash_ml.engines.hyperparameter_search import (
    HyperparameterSearch,
    SearchSpace,
    SearchConfig,
    ParamDistribution,
)

# Define search space
space = SearchSpace(params=[
    ParamDistribution("n_estimators", "int_uniform", low=50, high=500),
    ParamDistribution("max_depth", "int_uniform", low=3, high=15),
    ParamDistribution("learning_rate", "log_uniform", low=0.001, high=0.3),
    ParamDistribution("subsample", "uniform", low=0.6, high=1.0),
])

config = SearchConfig(
    strategy="bayesian",        # "grid", "random", "bayesian", "successive_halving"
    n_trials=50,
    metric_to_optimize="f1",
    direction="maximize",
)

searcher = HyperparameterSearch(pipeline)
result = await searcher.search(
    data=data,
    schema=schema,
    base_model_spec=base_model_spec,
    search_space=space,
    config=config,
    eval_spec=eval_spec,
    experiment_name="my-search",
)

print(f"Best params: {result.best_params}")
print(f"Best metrics: {result.best_metrics}")
print(f"Best trial: #{result.best_trial_number}")
```

---

## Ensemble Methods

```python
from kailash_ml.engines.ensemble import EnsembleEngine

ensemble = EnsembleEngine()

# Blend: weighted average of predictions from multiple models
blend_result = ensemble.blend(
    models=[model_a, model_b, model_c],
    X_val=X_val,
    y_val=y_val,
    weights=[0.5, 0.3, 0.2],
)

# Stack: train a meta-learner on base model outputs
stack_result = ensemble.stack(
    models=[model_a, model_b, model_c],
    X_train=X_train,
    y_train=y_train,
    meta_learner_class="sklearn.linear_model.LogisticRegression",
)

# Bag: bootstrap aggregation
bag_result = ensemble.bag(
    model_class="sklearn.tree.DecisionTreeClassifier",
    X_train=X_train,
    y_train=y_train,
    n_estimators=10,
)
```

---

## Configuration

### Database Setup

kailash-ml uses `ConnectionManager` from the core Kailash SDK. All engines share the same connection.

```python
from kailash.db.connection import ConnectionManager

# SQLite (default, zero config)
conn = ConnectionManager("sqlite:///ml.db")

# In-memory SQLite (for testing)
conn = ConnectionManager("sqlite:///:memory:")

# PostgreSQL
conn = ConnectionManager("postgresql://user:pass@localhost:5432/mldb")

await conn.initialize()
```

### Engine Initialization

Every engine that persists state requires initialization to create its database tables.

```python
feature_store = FeatureStore(conn)
await feature_store.initialize()

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

tracker = ExperimentTracker(conn, artifact_root="./experiment_artifacts")
# ExperimentTracker auto-initializes on first use (no initialize() needed)

monitor = DriftMonitor(conn)
await monitor.initialize()
```

### Model Class Allowlist

For security, `TrainingPipeline` and `EnsembleEngine` restrict model class imports to these prefixes:

- `sklearn.*`
- `lightgbm.*`
- `xgboost.*`
- `catboost.*`
- `torch.*`
- `lightning.*`
- `kailash_ml.*`

Attempting to load a model class outside this allowlist raises a `ValueError`. This prevents arbitrary code execution via model class strings.

### CLI Entry Points

```bash
# Launch the experiment dashboard
kailash-ml-dashboard

# Configure GPU runtime (CUDA/ROCm detection)
kailash-ml-gpu-setup
```

---

## Troubleshooting

### "Module kailash_ml has no attribute ..."

Engines are lazy-loaded. Make sure you are importing from the correct path:

```python
# Direct import (always works)
from kailash_ml.engines.feature_store import FeatureStore

# Lazy import from top-level (also works)
from kailash_ml import FeatureStore
```

### "kailash-ml-protocols not found"

Type contracts have been merged into `kailash_ml.types`. Update your imports:

```python
# Old (deprecated)
from kailash_ml_protocols import FeatureSchema, FeatureField

# New
from kailash_ml.types import FeatureSchema, FeatureField
```

### ONNX export fails silently

ONNX export failure is by design non-fatal. Check the export status:

```python
version = await registry.get_model("my_model")
print(version.onnx_status)  # "success", "failed", "not_attempted"
```

Common causes: unsupported model type, dynamic computation graph (PyTorch), custom sklearn estimators.

### Agent features not available

Agent augmentation requires both installation and configuration:

```bash
pip install kailash-ml[agents]
```

```python
config = AutoMLConfig(agent=True)  # Must explicitly opt in
```

If `kailash-kaizen` is not installed, setting `agent=True` will raise an `ImportError` with a helpful message.

### "Database is locked" errors

Use `ConnectionManager` (not bare `aiosqlite.connect()`). ConnectionManager configures WAL mode, busy timeouts, and connection pooling automatically.

### LLM cost budget exceeded

Agent-augmented engines track cumulative LLM cost. If you hit the limit:

```python
config = AutoMLConfig(
    agent=True,
    max_llm_cost_usd=10.0,  # Increase the budget (default varies by engine)
)
```

---

## Contributing

kailash-ml is part of the [Kailash Python SDK monorepo](https://github.com/terrene-foundation/kailash-py).

```bash
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-py/packages/kailash-ml
uv venv && uv sync
uv run pytest tests/ -x
```

See the monorepo CONTRIBUTING.md for guidelines on pull requests, testing, and code style.

---

## License

Apache-2.0. Copyright 2026 Terrene Foundation.
