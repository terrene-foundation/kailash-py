# kailash-ml Quick Reference

## Engine Index

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
| 13  | ModelVisualizer       | P2       | Model explanation plots (experimental)                             | plotly                             |

**Additional modules**: OnnxBridge, MlflowFormatReader/Writer, MLDashboard (all lazy-loaded).

## Internal Modules

| Module            | Purpose                                                                                   | When to Touch                          |
| ----------------- | ----------------------------------------------------------------------------------------- | -------------------------------------- |
| `_shared.py`      | NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, validate_model_class(), compute_metrics_by_name() | Adding new model frameworks or metrics |
| `_feature_sql.py` | ALL raw SQL for FeatureStore (zero SQL elsewhere)                                         | Any FeatureStore schema/query change   |
| `_guardrails.py`  | AgentGuardrailMixin (cost budget, audit trail, approval gate)                             | Adding agent integration to any engine |
| `interop.py`      | SOLE conversion point: polars <-> sklearn/lgb/arrow/pandas/hf                             | Adding new framework interop           |

## Common Patterns

### FeatureSchema Definition

```python
from kailash_ml.types import FeatureSchema, FeatureField

schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
        FeatureField(name="monthly_charges", dtype="float"),
    ],
    target=FeatureField(name="churned", dtype="int"),
)
```

### FeatureStore Setup + Ingest

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()

await fs.register_schema(schema)
await fs.ingest("user_churn", schema, polars_df)

# Point-in-time retrieval
features = await fs.get_features("user_churn", entity_ids=["u1", "u2"])
```

### Training Pipeline

```python
from kailash_ml import TrainingPipeline
from kailash_ml.engines.training_pipeline import ModelSpec, EvalSpec

pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(
        model_class="sklearn.ensemble.RandomForestClassifier",
        hyperparameters={"n_estimators": 100, "max_depth": 10},
    ),
    eval_spec=EvalSpec(metrics=["accuracy", "f1", "roc_auc"]),
)
# result.model_version, result.metrics, result.training_time
```

### Drift Monitoring Setup

```python
from kailash_ml import DriftMonitor

monitor = DriftMonitor(conn)
await monitor.initialize()

# Set reference distribution
await monitor.set_reference("model_v1", reference_df)

# Check for drift (returns DriftReport)
report = await monitor.check_drift("model_v1", current_df)
for feat in report.feature_results:
    if feat.drift_detected:
        print(f"{feat.feature_name}: PSI={feat.psi:.3f}, type={feat.drift_type}")
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
    agent=True,            # Enable LLM augmentation (requires kailash-ml[agents])
    auto_approve=False,    # Human approval gate
    max_llm_cost_usd=5.0,
)
engine = AutoMLEngine(feature_store=fs, model_registry=registry, config=config)
result = await engine.run(schema=schema, data=df)
```

### Model Registry Lifecycle

```python
from kailash_ml import ModelRegistry
from kailash_ml.engines.model_registry import LocalFileArtifactStore

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

# Stage transitions: staging -> shadow -> production -> archived
await registry.promote("model_v1", version_id, target_stage="production")

# Valid transitions:
# staging  -> shadow, production, archived
# shadow   -> production, archived, staging
# production -> archived, shadow
# archived -> staging
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

## Security Checklist

When writing or reviewing kailash-ml engine code, verify:

- [ ] **SQL identifiers**: All interpolated identifiers pass through `_validate_identifier()` (from `kailash.db.dialect`)
- [ ] **SQL types**: Column types validated via `_validate_sql_type()` allowlist (INTEGER, REAL, TEXT, BLOB, NUMERIC)
- [ ] **SQL placement**: Zero raw SQL outside `_feature_sql.py` -- all queries go through that module
- [ ] **Model classes**: Dynamic model imports validated via `validate_model_class()` against ALLOWED_MODEL_PREFIXES
- [ ] **Financial fields**: `math.isfinite()` on all cost/budget fields (NaN/Inf bypass comparisons)
- [ ] **Table prefix**: Regex-validated in constructor (`^[a-zA-Z_][a-zA-Z0-9_]*$`)
- [ ] **Bounded collections**: Audit trails, cost logs, trial history use `deque(maxlen=N)`
- [ ] **Agent guardrails**: Engines with agent integration inherit `AgentGuardrailMixin` (cost budget + approval gate)
- [ ] **Interop boundary**: Conversions happen ONLY in `interop.py`, nowhere else

## Install Matrix

```
pip install kailash-ml            # Core: polars, numpy, scipy, sklearn, lightgbm, plotly, onnx
pip install kailash-ml[dl]        # + PyTorch, Lightning, transformers, timm
pip install kailash-ml[dl-gpu]    # + onnxruntime-gpu
pip install kailash-ml[rl]        # + Stable-Baselines3, Gymnasium
pip install kailash-ml[agents]    # + kailash-kaizen
pip install kailash-ml[xgb]       # + XGBoost
pip install kailash-ml[catboost]  # + CatBoost
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[all]       # Everything (CPU)
pip install kailash-ml[all-gpu]   # Everything (GPU)
```

## Cross-References

- `.claude/agents/frameworks/ml-specialist.md` -- Full agent (architecture, patterns, security)
- `.claude/agents/frameworks/align-specialist.md` -- LLM fine-tuning (companion package)
- `.claude/agents/frameworks/dataflow-specialist.md` -- ConnectionManager, database patterns
- `packages/kailash-ml/src/kailash_ml/` -- Source code
