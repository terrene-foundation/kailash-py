---
name: kailash-ml
description: "Kailash ML — MANDATORY for ALL ML training/inference/feature work. 13 engines (FeatureStore, ModelRegistry, TrainingPipeline, DriftMonitor, AutoML, HyperparameterSearch, Ensemble, etc.), polars-native, ONNX serving, agent-augmented search. Use proactively when work touches feature stores, training pipelines, inference servers, drift detection, ensembles, or 'just a quick sklearn pipeline'. Raw sklearn, pytorch, numpy, pandas training loops BLOCKED."
---

# Kailash ML — Classical & Deep Learning Lifecycle

Production ML lifecycle framework built on Kailash Core SDK — polars-native engines, schema-driven pipelines, agent-augmented AutoML, and cross-language ONNX serving.

## Install Matrix

```
pip install kailash-ml            # Core: polars, numpy, scipy, sklearn, lightgbm, plotly, onnx
pip install kailash-ml[dl]        # + PyTorch, Lightning, transformers, timm
pip install kailash-ml[dl-gpu]    # + onnxruntime-gpu
pip install kailash-ml[rl]        # + Stable-Baselines3, Gymnasium
pip install kailash-ml[agents]    # + kailash-kaizen (agent integration)
pip install kailash-ml[xgb]       # + XGBoost
pip install kailash-ml[catboost]  # + CatBoost
pip install kailash-ml[explain]   # + SHAP (model explainability)
pip install kailash-ml[imbalance] # + imbalanced-learn (SMOTE, ADASYN)
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[full]      # Everything (CPU)
pip install kailash-ml[all-gpu]   # Everything (GPU)
```

## 13 Engines (by Priority)

| #   | Engine                | Priority | Purpose                                                            | Key Dependency                     |
| --- | --------------------- | -------- | ------------------------------------------------------------------ | ---------------------------------- |
| 1   | FeatureStore          | P0       | Polars-native feature versioning, point-in-time queries            | ConnectionManager                  |
| 2   | ModelRegistry         | P0       | Model versioning (staging/shadow/production/archived), ONNX export | ConnectionManager, ArtifactStore   |
| 3   | TrainingPipeline      | P0       | sklearn/LightGBM/Lightning training with FeatureSchema             | FeatureStore, ModelRegistry        |
| 4   | InferenceServer       | P0       | REST serving via kailash-nexus, response caching, batch            | ModelRegistry, kailash-nexus       |
| 5   | DriftMonitor          | P0       | KS/chi2/PSI/Jensen-Shannon drift detection, scheduled checks       | ConnectionManager                  |
| 6   | ExperimentTracker     | P0       | MLflow-compatible run tracking, metric comparison, audit           | ConnectionManager                  |
| 7   | HyperparameterSearch  | P1       | Grid/random/Bayesian/successive halving optimization               | TrainingPipeline                   |
| 8   | AutoMLEngine          | P1       | Multi-family model search, optional agent augmentation             | HyperparameterSearch, FeatureStore |
| 9   | EnsembleEngine        | P1       | Blend/stack/bag/boost ensemble creation                            | TrainingPipeline                   |
| 10  | PreprocessingPipeline | P1       | Auto-setup from FeatureSchema, imputation, encoding                | FeatureSchema                      |
| 11  | DataExplorer          | P2       | Statistical profiling, plotly visualization, comparison            | polars, plotly                     |
| 12  | FeatureEngineer       | P2       | Auto-generation, selection, importance ranking                     | polars                             |
| 13  | ModelExplainer        | P2       | SHAP-based global/local/dependence explanations                    | SHAP (requires [explain])          |

**Additional modules**: OnnxBridge, MlflowFormatReader/Writer, MLDashboard (all lazy-loaded).

## Quick Start

### Feature Ingestion

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore
from kailash_ml.types import FeatureSchema, FeatureField
import polars as pl

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
    ],
    target=FeatureField(name="churned", dtype="int"),
)

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()

df = pl.read_csv("data.csv")
await fs.ingest("user_features", schema, df)

# Point-in-time retrieval
features = await fs.get_features("user_features", entity_ids=["u1", "u2"])
```

### Training

```python
from kailash_ml import TrainingPipeline, ModelRegistry, ModelSpec, EvalSpec
from kailash_ml.engines import LocalFileArtifactStore

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)
```

### Drift Monitoring

```python
from kailash_ml import DriftMonitor

monitor = DriftMonitor(conn)
await monitor.initialize()
await monitor.set_reference("model_v1", reference_df)
report = await monitor.check_drift("model_v1", current_df)
# report.overall_drift, report.feature_results, report.recommendations
```

### Model Explainability (requires `[explain]`)

```python
from kailash_ml import ModelExplainer

explainer = ModelExplainer(model=fitted_model, X=train_df, feature_names=schema.feature_names)
global_report = explainer.explain_global(max_display=10)
local_report = explainer.explain_local(X=test_df, index=0)
fig = explainer.to_plotly("summary")  # "summary", "beeswarm", "dependence"
```

### AutoML with Agent Augmentation

```python
from kailash_ml import AutoMLEngine
from kailash_ml.engines.automl_engine import AutoMLConfig

config = AutoMLConfig(
    task_type="classification",
    metric_to_optimize="f1",
    search_strategy="bayesian",
    search_n_trials=50,
    agent=True,            # LLM augmentation (requires kailash-ml[agents])
    auto_approve=False,    # Human approval gate
    max_llm_cost_usd=5.0,
)
engine = AutoMLEngine(feature_store=fs, model_registry=registry, config=config)
result = await engine.run(schema=schema, data=df)
```

### Model Registry Lifecycle

```python
# Stage transitions: staging → shadow → production → archived
await registry.promote("model_v1", version_id, target_stage="production")

# Valid transitions:
# staging    → shadow, production, archived
# shadow     → production, archived, staging
# production → archived, shadow
# archived   → staging
```

### Preprocessing Pipeline

```python
from kailash_ml.engines import PreprocessingPipeline

pipeline = PreprocessingPipeline()
result = pipeline.setup(
    data=df, target="churned",
    normalize=True, normalize_method="zscore",       # zscore, minmax, robust, maxabs
    imputation="knn", impute_n_neighbors=5,           # knn, iterative, default
    remove_multicollinearity=True, multicollinearity_threshold=0.9,
    fix_imbalance=True, imbalance_method="smote",     # smote, adasyn ([imbalance])
)
```

### Nested Runs & Auto-Logging

```python
from kailash_ml import ExperimentTracker

tracker = ExperimentTracker(conn)
await tracker.initialize()

async with tracker.run("hyperopt-sweep") as parent:
    for params in param_grid:
        async with tracker.run("trial", parent_run_id=parent.run_id) as child:
            await child.log_params(params)
```

## Decision Tree: kailash-ml vs kailash-align vs kailash-kaizen

| You Want To...                        | Use                                                 |
| ------------------------------------- | --------------------------------------------------- |
| Train sklearn/LightGBM/XGBoost models | **kailash-ml**                                      |
| Manage feature pipelines              | **kailash-ml**                                      |
| Monitor model drift                   | **kailash-ml**                                      |
| Export models to ONNX                 | **kailash-ml**                                      |
| Fine-tune an LLM (LoRA, DPO, RLHF)    | **kailash-align**                                   |
| Serve a fine-tuned LLM via Ollama     | **kailash-align**                                   |
| Build an AI agent with tools          | **kailash-kaizen**                                  |
| Add agent intelligence to ML engines  | **kailash-ml[agents]** (uses Kaizen under the hood) |
| Train RL policies (Gymnasium)         | **kailash-ml[rl]**                                  |

## Polars-Native Rule (ABSOLUTE)

Every engine accepts and returns `polars.DataFrame`. Conversion to numpy/pandas/LightGBM Dataset happens ONLY in `interop.py` at sklearn/framework boundaries.

```python
# DO: Work in polars throughout
df = pl.read_csv("data.csv")
await fs.ingest("features", schema, df)

# DO NOT: Convert to pandas first
df_pd = pd.read_csv("data.csv")  # WRONG — polars is the native format
```

## Interop Conversion Table

All conversions live in `interop.py`. Import from there only.

| Function                   | From             | To                                   | Use When                    |
| -------------------------- | ---------------- | ------------------------------------ | --------------------------- |
| `to_sklearn_input()`       | polars DataFrame | (X: ndarray, y: ndarray, info: dict) | Training with sklearn       |
| `from_sklearn_output()`    | ndarray          | polars DataFrame                     | Converting predictions back |
| `to_lgb_dataset()`         | polars DataFrame | lightgbm.Dataset                     | Training with LightGBM      |
| `to_hf_dataset()`          | polars DataFrame | datasets.Dataset                     | HuggingFace integration     |
| `polars_to_arrow()`        | polars DataFrame | pyarrow.Table                        | Arrow IPC / Parquet         |
| `from_arrow()`             | pyarrow.Table    | polars DataFrame                     | Ingesting Arrow data        |
| `to_pandas()`              | polars DataFrame | pandas.DataFrame                     | Legacy pandas interop       |
| `from_pandas()`            | pandas.DataFrame | polars DataFrame                     | Ingesting pandas data       |
| `polars_to_dict_records()` | polars DataFrame | list[dict]                           | JSON serialization          |
| `dict_records_to_polars()` | list[dict]       | polars DataFrame                     | JSON deserialization        |

## Architecture

```
kailash-ml/
  engines/
    _shared.py              ← Numeric dtypes, model class validation
    _feature_sql.py         ← ALL raw SQL (zero SQL in engine files)
    _guardrails.py          ← AgentGuardrailMixin (5 mandatory guardrails)
    feature_store.py        ← FeatureStore (ConnectionManager, polars-native)
    model_registry.py       ← ModelRegistry (lifecycle, SHA256 integrity)
    training_pipeline.py    ← TrainingPipeline (schema-driven)
    inference_server.py     ← InferenceServer (Nexus, ONNX, caching)
    drift_monitor.py        ← DriftMonitor (KS/chi2/PSI/JS)
    model_explainer.py      ← ModelExplainer (SHAP, [explain])
    experiment_tracker.py   ← MLflow-compatible tracking (nested runs)
    hyperparameter_search.py ← Grid/random/bayesian/successive halving
    automl_engine.py        ← Agent-infused AutoML
    ensemble.py             ← Blend/stack/bag/boost
    preprocessing.py        ← Auto-setup from FeatureSchema
  agents/                   ← 6 Kaizen agents ([agents])
    tools.py                ← Dumb data endpoints (LLM-first)
  rl/                       ← RLTrainer, EnvironmentRegistry, PolicyRegistry
  interop.py                ← SOLE conversion point
  bridge/                   ← OnnxBridge (export + verification)
```

### Internal Module Guide

| Module            | Purpose                                                                                   | When to Touch                          |
| ----------------- | ----------------------------------------------------------------------------------------- | -------------------------------------- |
| `_shared.py`      | NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, validate_model_class(), compute_metrics_by_name() | Adding new model frameworks or metrics |
| `_feature_sql.py` | ALL raw SQL for FeatureStore (zero SQL elsewhere)                                         | Any FeatureStore schema/query change   |
| `_guardrails.py`  | AgentGuardrailMixin (cost budget, audit trail, approval gate)                             | Adding agent integration to any engine |
| `interop.py`      | SOLE conversion point: polars ↔ sklearn/lgb/arrow/pandas/hf                               | Adding new framework interop           |

## 6 ML Agents (kailash-ml[agents])

Agents require both `agent=True` AND the agents extra installed. All follow LLM-first rule.

| Agent                      | Purpose                        |
| -------------------------- | ------------------------------ |
| DataScientistAgent         | Data profiling recommendations |
| FeatureEngineerAgent       | Feature generation guidance    |
| ModelSelectorAgent         | Model selection reasoning      |
| ExperimentInterpreterAgent | Trial result analysis          |
| DriftAnalystAgent          | Drift report interpretation    |
| RetrainingDecisionAgent    | Retrain/rollback decisions     |

See [ml-agent-guardrails](ml-agent-guardrails.md) for the 5 mandatory guardrails.

## RL Module (kailash-ml[rl])

```python
from kailash_ml.rl import RLTrainer, EnvironmentRegistry, PolicyRegistry

env_reg = EnvironmentRegistry()
env_reg.register("CartPole-v1")

trainer = RLTrainer(env_registry=env_reg, policy_registry=PolicyRegistry())
result = await trainer.train(env_id="CartPole-v1", algorithm="PPO", total_timesteps=100_000)
```

## Security Checklist

When writing or reviewing kailash-ml engine code, verify:

- [ ] **SQL identifiers**: All interpolated identifiers pass through `_validate_identifier()` (from `kailash.db.dialect`)
- [ ] **SQL types**: Column types validated via `_validate_sql_type()` allowlist (INTEGER, REAL, TEXT, BLOB, NUMERIC)
- [ ] **SQL placement**: Zero raw SQL outside `_feature_sql.py` — all queries go through that module
- [ ] **Model classes**: Dynamic model imports validated via `validate_model_class()` against ALLOWED_MODEL_PREFIXES (`sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.`)
- [ ] **Financial fields**: `math.isfinite()` on all cost/budget fields (NaN/Inf bypass comparisons)
- [ ] **Table prefix**: Regex-validated in constructor (`^[a-zA-Z_][a-zA-Z0-9_]*$`)
- [ ] **Bounded collections**: Audit trails, cost logs, trial history use `deque(maxlen=N)`
- [ ] **Agent guardrails**: Engines with agent integration inherit `AgentGuardrailMixin` (cost budget + approval gate)
- [ ] **Interop boundary**: Conversions happen ONLY in `interop.py`, nowhere else

## Skill Files

- [ml-feature-pipelines](ml-feature-pipelines.md) — FeatureStore, polars-only engineering, schema-driven ingestion
- [ml-model-registry](ml-model-registry.md) — ModelRegistry CRUD, lifecycle stages, MLflow compatibility
- [ml-training-pipeline](ml-training-pipeline.md) — TrainingPipeline, hyperparameter search, experiment tracking
- [ml-inference-server](ml-inference-server.md) — InferenceServer, Nexus exposure, ONNX serving, batch inference
- [ml-agent-guardrails](ml-agent-guardrails.md) — 5 mandatory guardrails, AutoML, agent integration
- [ml-onnx-export](ml-onnx-export.md) — PyTorch/sklearn to ONNX, verification, cross-language serving
- [ml-drift-monitoring](ml-drift-monitoring.md) — DriftMonitor, statistical tests, alert thresholds, retraining triggers

## Critical Rules

- All engines are polars-native — no pandas/numpy in pipeline code
- sklearn interop only at boundary via `interop.py`
- FeatureStore uses ConnectionManager, not Express (needs window functions)
- Zero raw SQL outside `_feature_sql.py`
- Agent-augmented engines require double opt-in (`agent=True` + extras installed)
- All agents follow LLM-first rule — tools are dumb data endpoints

## Related Skills

- [01-core-sdk](../01-core-sdk/SKILL.md) — Core workflow patterns
- [02-dataflow](../02-dataflow/SKILL.md) — Database integration (ConnectionManager)
- [03-nexus](../03-nexus/SKILL.md) — Multi-channel deployment (InferenceServer)
- [04-kaizen](../04-kaizen/SKILL.md) — AI agent framework (ML agents)
- [35-kailash-align](../35-kailash-align/SKILL.md) — LLM fine-tuning and alignment
</content>
</invoke>