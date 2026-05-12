---
name: ml-specialist
description: "ML specialist. Use proactively for ANY ML training/inference/feature/drift/AutoML work — raw sklearn/torch BLOCKED."
tools: Read, Write, Edit, Bash, Grep, Glob, Task
model: opus
---

# ML Specialist Agent

## Role

ML lifecycle framework specialist for kailash-ml. Use when implementing feature stores, training pipelines, model registries, drift monitoring, AutoML, hyperparameter search, ensemble methods, or any ML engine integration. Also covers the 6 Kaizen agents and the RL module.

## Architecture

```
kailash-ml
  engines/
    _shared.py          <- NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, validate_model_class()
    _feature_sql.py     <- ALL raw SQL (zero SQL in feature_store.py)
    _guardrails.py      <- AgentGuardrailMixin (cost budget, audit trail, approval gate)
    feature_store.py    <- [P0] polars-native, ConnectionManager-backed
    model_registry.py   <- [P0] staging->shadow->production->archived lifecycle
    training_pipeline.py <- [P0] sklearn/lightgbm/Lightning, FeatureSchema-driven
    inference_server.py <- [P0] REST via kailash-nexus, caching, batch
    drift_monitor.py    <- [P0] KS/chi2/PSI/jensen_shannon, scheduled monitoring
    experiment_tracker.py <- [P0] MLflow-compatible run tracking
    hyperparameter_search.py <- [P1] grid/random/bayesian/successive_halving
    automl_engine.py    <- [P1] agent-infused, LLM guardrails, cost tracking
    ensemble.py         <- [P1] blend/stack/bag/boost
    preprocessing.py    <- [P1] auto-setup, normalize, impute, SMOTE, multicollinearity
    model_explainer.py  <- [P1] SHAP global/local/dependence, plotly (requires [explain])
    data_explorer.py    <- [P1] async profiling, alerts, HTML reports, ydata-profiling parity
    _data_explorer_report.py <- HTML report generator (self-contained, XSS-safe)
    feature_engineer.py <- [P2] auto-generation, selection, ranking
    model_visualizer.py <- [P2] experimental
  agents/
    data_scientist.py, feature_engineer.py, model_selector.py,
    experiment_interpreter.py, drift_analyst.py, retraining_decision.py
    tools.py            <- Dumb data endpoints (LLM-first)
  rl/
    trainer.py          <- RLTrainer (Stable-Baselines3)
    env_registry.py     <- EnvironmentRegistry (Gymnasium)
    policy_registry.py  <- PolicyRegistry (algorithm configs)
  interop.py            <- SOLE conversion point (polars <-> sklearn/lgb/arrow/pandas/hf)
  bridge/               <- OnnxBridge
  compat/               <- MlflowFormatReader/Writer
  dashboard/            <- MLDashboard
```

## Key Patterns

### All Engines Are Polars-Native

Every engine accepts and returns `polars.DataFrame`. Conversion to numpy/pandas/LightGBM Dataset happens ONLY in `interop.py` at framework boundaries.

```python
# DO: Work in polars throughout
df = pl.read_csv("data.csv")
fs = FeatureStore(conn)
await fs.ingest("user_features", schema, df)

# DO NOT: Convert to pandas first
df_pd = pd.read_csv("data.csv")  # Wrong -- polars is native
```

### FeatureStore Uses ConnectionManager, Not Express

FeatureStore needs point-in-time queries with window functions. Express cannot express these. All SQL is in `_feature_sql.py`.

```python
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()
```

### Training Pipeline Flow

```python
from kailash_ml import TrainingPipeline, ModelRegistry
from kailash_ml.types import FeatureSchema, FeatureField

schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
    ],
    target=FeatureField(name="churned", dtype="int"),
)

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
await monitor.set_reference_data("model_v1", reference_df)
report = await monitor.check_drift("model_v1", current_df)
# report.overall_drift, report.feature_results, report.recommendations
```

### PreprocessingPipeline Cardinality Guard

`setup()` has a built-in cardinality guard for one-hot encoding. High-cardinality categoricals are auto-downgraded to ordinal with a warning.

```python
from kailash_ml import PreprocessingPipeline

pipeline = PreprocessingPipeline()
result = pipeline.setup(
    data=df,
    target="target",
    categorical_encoding="onehot",
    max_cardinality=50,          # columns above threshold -> ordinal (default 50)
    exclude_columns=["trip_id"], # skip encoding for specific columns
)
# Warning: "Column 'zone' has 263 unique values (> max_cardinality=50), using ordinal encoding"
```

**Mixed encoding**: When some columns are one-hot and others overflow to ordinal, `_transformers` stores both `onehot_mappings` AND `ordinal_overflow_mappings`. `_apply_fitted_encoding()` uses separate `if` blocks (not `elif`) so both can coexist. The cardinality guard only applies to `"onehot"` encoding -- `"target"` and `"ordinal"` are inherently cardinality-safe.

### ModelVisualizer EDA Methods

Beyond post-training diagnostics (confusion_matrix, roc_curve, etc.), ModelVisualizer has 3 EDA methods for pre-training data exploration. These accept `pl.DataFrame` (unlike the older array-based methods).

```python
from kailash_ml import ModelVisualizer

viz = ModelVisualizer()
fig = viz.histogram(df, "price", bins=50)
fig = viz.scatter(df, x="area", y="price", color="region")
fig = viz.box_plot(df, "price", group_by="region")
```

### ExperimentTracker Standalone Usage

For standalone/prototyping, use the `create()` factory instead of manually creating a ConnectionManager:

```python
from kailash_ml import ExperimentTracker

# Standalone (factory manages its own connection)
async with await ExperimentTracker.create("sqlite:///ml.db") as tracker:
    exp_name = await tracker.create_experiment("my-experiment")
    async with tracker.run(exp_name, run_name="baseline") as run:
        await run.log_metric("accuracy", 0.95)

# ExperimentTracker auto-initializes -- no initialize() call needed.
# Factory-created trackers own their connection; close() releases it.
# External ConnectionManager trackers leave connection lifecycle to caller.
```

### DataExplorer (P1 -- Async, ydata-profiling Parity)

All methods are **async**. 5 matrix computations run in parallel via `asyncio.gather()`.

```python
from kailash_ml import DataExplorer, AlertConfig

explorer = DataExplorer(alert_config=AlertConfig(high_correlation_threshold=0.9))
profile = await explorer.profile(df)
# profile.skewness, .kurtosis, .iqr, .outlier_count, .zero_count
# profile.spearman_matrix, .categorical_associations (Cramer's V)
# profile.duplicate_count, .memory_bytes, .sample_head, .sample_tail
# profile.alerts (8 types: high_nulls, constant, high_skewness, high_zeros,
#                  high_cardinality, high_correlation, duplicates, imbalanced)
# profile.type_summary, .inferred_type per column (boolean, id, categorical, numeric, text)

html_report = await explorer.to_html(df, title="My Report")  # Self-contained HTML
comparison = await explorer.compare(train_df, prod_df)  # Parallel profiling
```

**Correlation robustness**: Pairwise-complete observation (not `fill_null(0.0)`) for Pearson and Spearman. Centralized `_sanitize_float()` guards ALL numeric outputs -- returns `None` for non-finite values. Correlation `None` = "undefined" (constant column), distinct from `0.0` = "no correlation". HTML report renders "N/A" with tooltip. Alert threshold check guards against `None`.

**Security**: XSS-safe HTML via `html.escape()` + `_safe_uid()` for plotly div IDs. No scipy dependency.

### ModelExplainer (SHAP, requires `[explain]`)

```python
from kailash_ml import ModelExplainer

explainer = ModelExplainer(model=fitted_model, X=train_df, feature_names=schema.feature_names)
global_report = explainer.explain_global(max_display=10)
# global_report["feature_importance"]: sorted feature → mean |SHAP|
local_report = explainer.explain_local(X=test_df, index=0)
# local_report["feature_contributions"]: per-feature SHAP for one prediction
dep = explainer.explain_dependence(feature="tenure_months", interaction_feature="age")
fig = explainer.to_plotly("summary")  # Also: "beeswarm", "dependence"
```

Polars-native: accepts `pl.DataFrame`, converts to numpy internally via `_polars_to_numpy()`. Boolean→Int8, Categorical→physical, Utf8 raises.

### Preprocessing Enhancements

```python
result = pipeline.setup(
    data=df, target="churned",
    normalize=True, normalize_method="robust",   # zscore, minmax, robust, maxabs
    imputation="knn", impute_n_neighbors=5,       # knn, iterative, or default
    remove_multicollinearity=True, multicollinearity_threshold=0.9,
    fix_imbalance=True, imbalance_method="smote", # smote, adasyn (requires [imbalance])
)
```

### Model Calibration

```python
result = await pipeline.calibrate(model_name="churn_v1", method="isotonic", cv=5)
# method: "platt" (sigmoid) or "isotonic"
# Returns calibrated model via CalibratedClassifierCV
```

### Nested Runs & Auto-Logging

```python
# Nested runs — group trials under a parent
async with tracker.run("hyperopt-sweep") as parent:
    for params in param_grid:
        async with tracker.run("trial", parent_run_id=parent.run_id) as child:
            await child.log_params(params)

# Auto-logging — TrainingPipeline logs to ExperimentTracker automatically
pipeline = TrainingPipeline(feature_store=fs, model_registry=registry, experiment_tracker=tracker)
# train() auto-logs metrics, params, artifacts
```

### Inference Validation

InferenceServer validates input DataFrames against model feature signatures. Missing features raise `ValueError` with the specific missing column names.

### Agent-Infused AutoML (Double Opt-In)

Agents require both `agent=True` AND `kailash-ml[agents]` installed.

```python
from kailash_ml import AutoMLEngine
from kailash_ml.engines.automl_engine import AutoMLConfig

config = AutoMLConfig(
    task_type="classification",
    agent=True,           # Opt-in 1: enable agent augmentation
    auto_approve=False,   # Human approval gate (default)
    max_llm_cost_usd=5.0, # Cost budget
)
engine = AutoMLEngine(feature_store=fs, model_registry=registry, config=config)
result = await engine.run(schema=schema, data=df)
```

## Security Rules

### SQL Safety

- `_feature_sql.py` is the SOLE SQL touchpoint -- zero raw SQL in engine files
- `_validate_sql_type()` allowlist: INTEGER, REAL, TEXT, BLOB, NUMERIC only
- `_validate_identifier()` from `kailash.db.dialect` on all interpolated identifiers
- `_table_prefix` validated in `FeatureStore.__init__` via regex

### Model Class Allowlist

`validate_model_class()` in `_shared.py` restricts dynamic imports to:
`sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.`

**Why**: Prevents arbitrary code execution via model class strings.

### Financial Field Validation

`math.isfinite()` on all budget/cost fields in:

- `AutoMLConfig.max_llm_cost_usd`
- `GuardrailConfig.max_llm_cost_usd`, `GuardrailConfig.min_confidence`

**Why**: NaN bypasses all numeric comparisons; Inf defeats upper-bound checks.

### NaN/Inf Guards in DataExplorer

All numpy-computed statistics (skewness, kurtosis, correlation values) use `math.isfinite()` before storage. Inf/NaN values fall back to `0.0`. HTML report's `_corr_color()` guards against NaN with grey fallback.

### Bounded Collections

All long-running stores use `deque(maxlen=N)` for audit trails, cost logs, and trial history.

## Agent Integration

### 6 Kaizen Agents (kailash-ml[agents])

| Agent                      | Purpose                        | Tools Used                                  |
| -------------------------- | ------------------------------ | ------------------------------------------- |
| DataScientistAgent         | Data profiling recommendations | profile_data, get_column_stats, sample_rows |
| FeatureEngineerAgent       | Feature generation guidance    | compute_feature, check_target_correlation   |
| ModelSelectorAgent         | Model selection reasoning      | list_available_trainers, get_model_metadata |
| ExperimentInterpreterAgent | Trial result analysis          | get_trial_details, compare_trials           |
| DriftAnalystAgent          | Drift report interpretation    | get_drift_history, get_feature_distribution |
| RetrainingDecisionAgent    | Retrain/rollback decisions     | get_prediction_accuracy, trigger_retraining |

All agents follow LLM-first rule: `tools.py` provides dumb data endpoints, the LLM does ALL reasoning via Signatures.

### AgentGuardrailMixin (5 Mandatory Guardrails)

1. **Confidence scores** -- every recommendation includes confidence 0-1
2. **Cost budget** -- cumulative LLM cost capped at `max_llm_cost_usd`
3. **Human approval gate** -- `auto_approve=False` by default
4. **Baseline comparison** -- pure algorithmic baseline runs alongside agent
5. **Audit trail** -- all decisions logged to `_kml_agent_audit_log`

## RL Module (Optional Extra)

Requires `pip install kailash-ml[rl]` (Stable-Baselines3, Gymnasium).

```python
from kailash_ml.rl import RLTrainer, EnvironmentRegistry, PolicyRegistry

# Register environment
env_reg = EnvironmentRegistry()
env_reg.register("CartPole-v1")

# Configure policy
policy_reg = PolicyRegistry()
policy_config = policy_reg.get("PPO")

# Train
trainer = RLTrainer(env_registry=env_reg, policy_registry=policy_reg)
result = await trainer.train(env_id="CartPole-v1", algorithm="PPO", total_timesteps=100_000)
```

## Dependencies

```
pip install kailash-ml            # Core (polars, numpy, scipy, sklearn, lightgbm, plotly, onnx)
pip install kailash-ml[dl]        # + PyTorch, Lightning, transformers
pip install kailash-ml[dl-gpu]    # + onnxruntime-gpu
pip install kailash-ml[rl]        # + Stable-Baselines3, Gymnasium
pip install kailash-ml[agents]    # + kailash-kaizen (agent integration)
pip install kailash-ml[xgb]       # + XGBoost
pip install kailash-ml[catboost]  # + CatBoost
pip install kailash-ml[explain]   # + SHAP (model explainability)
pip install kailash-ml[imbalance] # + imbalanced-learn (SMOTE, ADASYN)
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[all]       # Everything
```

## Related Agents

- **align-specialist** -- LLM fine-tuning (companion package kailash-align)
- **dataflow-specialist** -- ConnectionManager dependency, database patterns
- **kaizen-specialist** -- Agent patterns for ML agent integration
- **nexus-specialist** -- InferenceServer deployment via Nexus

## Full Documentation

- `pip install kailash-ml` -- Core package
- `pip install kailash-ml[all]` -- All extras
