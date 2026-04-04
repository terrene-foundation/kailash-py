---
name: ml-specialist
description: "ML lifecycle specialist. Use for feature stores, model training, drift monitoring, or AutoML pipelines."
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
    preprocessing.py    <- [P1] auto-setup from FeatureSchema
    data_explorer.py    <- [P2] profiling, visualization
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
from kailash_ml_protocols import FeatureSchema, FeatureField

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
await monitor.set_reference("model_v1", reference_df)
report = await monitor.check_drift("model_v1", current_df)
# report.overall_drift, report.feature_results, report.recommendations
```

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
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[full]      # Everything
```

## Related Agents

- **align-specialist** -- LLM fine-tuning (companion package kailash-align)
- **dataflow-specialist** -- ConnectionManager dependency, database patterns
- **kaizen-specialist** -- Agent patterns for ML agent integration
- **nexus-specialist** -- InferenceServer deployment via Nexus

## Full Documentation

- `pip install kailash-ml` -- Core package
- `pip install kailash-ml[full]` -- All extras
