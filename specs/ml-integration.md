# Kailash ML Integration Specification

Parent domain: ML Lifecycle (`kailash-ml`). Companion file: `ml-engines.md` (all 17 engine constructors, methods, configuration).

Package: `kailash-ml` v0.9.0
License: Apache-2.0
Python: >=3.11

This file is the domain truth for kailash-ml's **integration and cross-cutting concerns**: architecture principles, module layout, lazy loading, dependency model, type protocols, ONNX bridge, MLflow compatibility, agent infusion, data handling (`interop.py`), metrics registry, dashboard, reinforcement learning, GPU setup CLI, shared internals, security constraints, and global invariants.

For the 17 engines themselves (FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, ExperimentTracker, HyperparameterSearch, AutoMLEngine, EnsembleEngine, ClusteringEngine, AnomalyDetectionEngine, DimReductionEngine, PreprocessingPipeline, DataExplorer, FeatureEngineer, ModelVisualizer, ModelExplainer), see `ml-engines.md`.

---

## 1. Architecture Overview

### 1.1 Design Principles

- **Polars-native**: All data handling uses polars DataFrames internally. Conversion to numpy, pandas, Arrow, or LightGBM datasets happens at the framework boundary via the centralized `interop.py` module. No engine touches pandas directly.
- **Lazy-loaded engines**: The top-level `kailash_ml` module uses `__getattr__` to defer engine imports until first access. `from kailash_ml import FeatureStore` triggers a single `importlib.import_module` call. This keeps `import kailash_ml` fast regardless of how many optional dependencies are installed.
- **ConnectionManager-backed persistence**: Engines that persist state (FeatureStore, ModelRegistry, DriftMonitor, ExperimentTracker) use Kailash's `ConnectionManager` for all SQL. No engine uses DataFlow Express because they require DDL control, window functions, and transactions that Express cannot express.
- **Security allowlist**: Model class instantiation is gated by `ALLOWED_MODEL_PREFIXES` in `engines/_shared.py`. Only classes from `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.` are permitted. Any other prefix raises `ValueError`.
- **Quality tiers**: Each engine declares its tier: P0 (production), P1 (production with caveats), P2 (experimental). P2 engines emit `ExperimentalWarning` on first instantiation via the `@experimental` decorator.

### 1.2 Module Layout

```
kailash_ml/
  __init__.py          # Lazy-load hub; re-exports all public symbols
  _version.py          # __version__
  _decorators.py       # @experimental decorator, ExperimentalWarning
  _gpu_setup.py        # CLI: kailash-ml-gpu-setup (CUDA detection)
  types.py             # Protocols (MLToolProtocol, AgentInfusionProtocol),
                       #   schemas (FeatureField, FeatureSchema, ModelSignature, MetricSpec)
  interop.py           # Centralized polars conversion (sklearn, lgb, hf, arrow, pandas)

  engines/
    __init__.py
    _shared.py          # NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, validate_model_class,
                        #   compute_metrics_by_name
    _feature_sql.py     # Encapsulated SQL for FeatureStore (zero raw SQL in feature_store.py)
    _guardrails.py      # AgentGuardrailMixin (5 mandatory guardrails)
    _data_explorer_report.py  # Report generation for DataExplorer

    # P0 engines (production)
    feature_store.py
    model_registry.py
    training_pipeline.py
    inference_server.py
    drift_monitor.py
    experiment_tracker.py

    # P1 engines (production with caveats)
    hyperparameter_search.py
    automl_engine.py
    ensemble.py
    clustering.py
    anomaly_detection.py
    dim_reduction.py
    preprocessing.py

    # P2 engines (experimental)
    feature_engineer.py
    model_visualizer.py
    model_explainer.py
    data_explorer.py

  bridge/
    onnx_bridge.py       # ONNX export, validation, compatibility matrix

  compat/
    mlflow_format.py     # MLflow MLmodel v1 format read/write

  agents/
    __init__.py          # Lazy-load hub for agent classes
    tools.py             # Dumb data endpoint tools (LLM-first rule)
    data_scientist.py
    feature_engineer.py
    model_selector.py
    experiment_interpreter.py
    drift_analyst.py
    retraining_decision.py

  dashboard/
    __init__.py
    server.py            # Starlette ASGI app (API + embedded HTML UI)
    templates/           # HTML templates

  metrics/
    __init__.py
    _registry.py         # Registry-based metric computation

  rl/
    __init__.py
    env_registry.py      # Environment registry
    policy_registry.py   # Policy registry
    trainer.py           # RLTrainer (Stable-Baselines3 wrapper)
```

### 1.3 Lazy Loading Mechanism

The top-level `__init__.py` defines an `_engine_map` dict mapping class names to their module paths. `__getattr__` intercepts attribute access, calls `importlib.import_module`, and returns the requested class. This means:

- `import kailash_ml` is always fast (loads only `types.py` and `_version.py` eagerly).
- `from kailash_ml import TrainingPipeline` triggers exactly one module import.
- Unknown attributes raise `AttributeError` with the attempted name.

The `metrics` sub-module is handled as a special case: `kailash_ml.metrics` returns the entire subpackage via `importlib.import_module("kailash_ml.metrics")`.

### 1.4 Dependency Model

**Core dependencies** (always installed):

- `kailash>=2.8.1`, `kailash-dataflow>=1.0`, `kailash-nexus>=1.0`
- `polars>=1.0`, `pyarrow>=14.0`, `numpy>=1.24`, `scipy>=1.11`
- `scikit-learn>=1.5`, `lightgbm>=4.0`, `plotly>=5.18`
- `skl2onnx>=1.16`, `onnxmltools>=1.12`, `onnxruntime>=1.17`

**Optional extras**:

| Extra         | Packages                                                      | Purpose                        |
| ------------- | ------------------------------------------------------------- | ------------------------------ |
| `dl`          | torch, lightning, torchvision, torchaudio, timm, transformers | Deep learning training         |
| `dl-gpu`      | Same as dl + onnxruntime-gpu                                  | GPU-accelerated DL             |
| `rl`          | dl + stable-baselines3, gymnasium                             | Reinforcement learning         |
| `agents`      | kailash-kaizen                                                | LLM agent augmentation         |
| `explain`     | shap                                                          | Model explainability           |
| `imbalance`   | imbalanced-learn                                              | Class imbalance handling       |
| `xgb`         | xgboost                                                       | XGBoost models                 |
| `catboost`    | catboost                                                      | CatBoost models                |
| `stats`       | statsmodels                                                   | Statistical models             |
| `hpo`         | optuna                                                        | Bayesian hyperparameter search |
| `mlflow`      | pyyaml                                                        | MLflow format interop          |
| `huggingface` | datasets                                                      | HuggingFace dataset conversion |
| `dashboard`   | starlette, uvicorn                                            | ML dashboard server            |
| `interop`     | pandas                                                        | Pandas interop                 |
| `all`         | Everything above                                              | Full suite (CPU)               |
| `all-gpu`     | Everything above with GPU variants                            | Full suite (GPU)               |

---

## 2. Type Contracts (`types.py`)

All types provide `to_dict()` / `from_dict()` round-trip serialization.

### 2.1 MLToolProtocol

Runtime-checkable protocol for Kaizen agent tools. Implementors: InferenceServer, ModelRegistry. Consumers: Kaizen MCP tools, Delegate agents.

**Methods:**

- `async predict(model_name: str, features: dict[str, Any], *, options: dict | None = None) -> dict[str, Any]` -- Returns `{"prediction": ..., "probabilities": [...], "model_version": ...}`.
- `async get_metrics(model_name: str, version: str | None = None, *, options: dict | None = None) -> dict[str, Any]` -- Returns `{"metrics": {"accuracy": 0.95, ...}, "version": ..., "evaluated_at": ...}`.
- `async get_model_info(model_name: str, *, options: dict | None = None) -> dict[str, Any]` -- Returns `{"name": ..., "stage": ..., "versions": [...], "signature": ...}`.

### 2.2 AgentInfusionProtocol

Runtime-checkable protocol for agent-augmented engine methods. Implementors: Kaizen Delegate agents. Consumers: AutoMLEngine, DataExplorer, FeatureEngineer, DriftMonitor.

**Methods:**

- `async suggest_model(data_profile: dict, task_type: str, *, options: dict | None = None) -> dict` -- Returns `{"candidates": [...], "reasoning": ..., "self_assessed_confidence": ...}`.
- `async suggest_features(data_profile: dict, existing_features: list[str], *, options: dict | None = None) -> dict` -- Returns `{"proposed_features": [...], "interactions": [...], "drops": [...]}`.
- `async interpret_results(experiment_results: dict, *, options: dict | None = None) -> dict` -- Returns `{"interpretation": ..., "patterns": [...], "recommendations": [...]}`.
- `async interpret_drift(drift_report: dict, *, options: dict | None = None) -> dict` -- Returns `{"assessment": ..., "root_cause": ..., "urgency": ..., "recommendation": ...}`.

### 2.3 FeatureField

Dataclass for a single feature column definition.

| Field         | Type   | Default  | Constraint                                                                        |
| ------------- | ------ | -------- | --------------------------------------------------------------------------------- |
| `name`        | `str`  | required |                                                                                   |
| `dtype`       | `str`  | required | One of: `"int64"`, `"float64"`, `"utf8"`, `"bool"`, `"datetime"`, `"categorical"` |
| `nullable`    | `bool` | `True`   |                                                                                   |
| `description` | `str`  | `""`     |                                                                                   |

### 2.4 FeatureSchema

Dataclass for a feature set schema.

| Field              | Type                 | Default  | Constraint                               |
| ------------------ | -------------------- | -------- | ---------------------------------------- |
| `name`             | `str`                | required |                                          |
| `features`         | `list[FeatureField]` | required |                                          |
| `entity_id_column` | `str`                | required |                                          |
| `timestamp_column` | `str \| None`        | `None`   | Enables point-in-time retrieval when set |
| `version`          | `int`                | `1`      |                                          |

### 2.5 ModelSignature

Input/output schema for a trained model.

| Field            | Type            | Default                                                  |
| ---------------- | --------------- | -------------------------------------------------------- |
| `input_schema`   | `FeatureSchema` | required                                                 |
| `output_columns` | `list[str]`     | required                                                 |
| `output_dtypes`  | `list[str]`     | required                                                 |
| `model_type`     | `str`           | required -- `"classifier"`, `"regressor"`, or `"ranker"` |

### 2.6 MetricSpec

A single evaluation metric with its value.

| Field              | Type    | Default  | Constraint                                   |
| ------------------ | ------- | -------- | -------------------------------------------- |
| `name`             | `str`   | required | e.g. `"accuracy"`, `"f1"`, `"rmse"`, `"auc"` |
| `value`            | `float` | required | Must be finite (`__post_init__` validates)   |
| `split`            | `str`   | `"test"` | `"train"`, `"val"`, `"test"`                 |
| `higher_is_better` | `bool`  | `True`   |                                              |

---

## 3. ONNX Bridge (`bridge/onnx_bridge.py`)

### 3.1 Purpose

Enables "train in Python, serve in Rust." Every compatible model gets ONNX export artifacts. ONNX export failure is NOT fatal -- falls back to native Python inference.

### 3.2 OnnxBridge Class [P1]

**Methods**:

| Method                                                                                | Description                                                                                                                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `check_compatibility(model, framework) -> OnnxCompatibility`                          | Pre-flight compatibility check against the compatibility matrix. Runs in <1 second.                                                           |
| `export(model, framework, schema, *, output_path, n_features) -> OnnxExportResult`    | Export to ONNX. Returns result with `success=False` on failure (not an exception). Infers `n_features` from schema or `model.n_features_in_`. |
| `validate(model, onnx_path, sample_input, *, tolerance=1e-4) -> OnnxValidationResult` | Compare native vs ONNX predictions. Reports `max_diff` and `mean_diff`. Valid when max_diff <= tolerance.                                     |

### 3.3 Compatibility Matrix

| Framework         | Confidence  | Notes                                 |
| ----------------- | ----------- | ------------------------------------- |
| sklearn (default) | guaranteed  | skl2onnx handles most estimators      |
| sklearn Pipeline  | best_effort | Custom transformers may fail          |
| lightgbm          | guaranteed  | onnxmltools handles all models        |
| xgboost           | guaranteed  | onnxmltools handles all models        |
| pytorch (default) | best_effort | Dynamic control flow may fail         |
| pytorch RNN       | best_effort | Variable sequence lengths need config |

### 3.4 Export Implementations

- **sklearn**: Uses `skl2onnx.convert_sklearn` with `FloatTensorType([None, n_features])`.
- **lightgbm**: Uses `onnxmltools.convert_lightgbm` with `FloatTensorType([None, n_features])`.

### 3.5 OnnxExportResult Fields

`success`, `onnx_path`, `onnx_status` ("success" | "failed" | "skipped"), `error_message`, `model_size_bytes`, `export_time_seconds`.

---

## 4. MLflow Compatibility (`compat/mlflow_format.py`)

### 4.1 Scope

Format interoperability only. kailash-ml can read and write MLflow MLmodel YAML format v1. This is NOT behavioral equivalence -- kailash-ml does NOT run an MLflow tracking server.

### 4.2 MlflowFormatWriter

Writes model to MLflow-compatible directory structure:

```
output_dir/
  MLmodel           # YAML metadata
  model.pkl         # serialized model artifact
  requirements.txt  # pip requirements
```

Generates flavors (python_function + sklearn), signature (input/output column-based), metrics, and model_uuid.

### 4.3 MlflowFormatReader

Reads MLmodel YAML and returns kailash-ml compatible dict with: `experiment_name`, `framework`, `signature`, `metrics`, `artifact_path`, `mlflow_model_uuid`, `utc_time_created`.

Detects framework from flavors: sklearn, lightgbm, pytorch, xgboost, or python_function.

### 4.4 Dtype Mapping

| kailash-ml | MLflow  |
| ---------- | ------- |
| float64    | double  |
| float32    | float   |
| int64      | long    |
| int32      | integer |
| string     | string  |
| bool       | boolean |

---

## 5. Agent Infusion

### 5.1 Architecture

Agent augmentation follows the LLM-first rule: the LLM does ALL reasoning, tools are dumb data endpoints. Agents require double opt-in: install `kailash-ml[agents]` AND set `agent=True` at call site.

### 5.2 Available Agents

| Agent                      | Module                             | Purpose                            |
| -------------------------- | ---------------------------------- | ---------------------------------- |
| DataScientistAgent         | `agents/data_scientist.py`         | General ML guidance                |
| FeatureEngineerAgent       | `agents/feature_engineer.py`       | Feature generation recommendations |
| ModelSelectorAgent         | `agents/model_selector.py`         | Model family selection             |
| ExperimentInterpreterAgent | `agents/experiment_interpreter.py` | Experiment result interpretation   |
| DriftAnalystAgent          | `agents/drift_analyst.py`          | Drift analysis and root cause      |
| RetrainingDecisionAgent    | `agents/retraining_decision.py`    | Retraining decision support        |

All agents lazy-loaded via `__getattr__` in `agents/__init__.py`.

### 5.3 Tool Functions (`agents/tools.py`)

All tools are dumb data endpoints with zero decision logic:

`profile_data`, `get_column_stats`, `check_correlation`, `sample_rows`, `compute_feature`, `check_target_correlation`, `get_feature_importance`, `list_available_trainers`, `get_model_metadata`, `get_trial_details`, `compare_trials`, `get_drift_history`, `get_feature_distribution`, `get_prediction_accuracy`, `trigger_retraining`, `get_model_versions`, `rollback_model`.

### 5.4 Guardrails (`engines/_guardrails.py`)

Five mandatory guardrails for agent-augmented engines:

1. **Confidence scores**: Every agent recommendation includes confidence (0-1).
2. **Cost budget**: Cumulative LLM cost capped at `max_llm_cost_usd`.
3. **Human approval gate**: `auto_approve=False` by default.
4. **Baseline comparison**: Pure algorithmic baseline runs alongside agent.
5. **Audit trail**: All agent decisions logged to `_kml_agent_audit_log`.

`GuardrailConfig` fields: `max_llm_cost_usd` (1.0), `auto_approve` (False), `require_baseline` (True), `audit_trail` (True), `min_confidence` (0.5).

### 5.5 Integration Points

- **TrainingPipeline.train()**: Optionally calls `agent.suggest_model()` before training and `agent.interpret_results()` after evaluation.
- **DriftMonitor.check_drift()**: Optionally calls `agent.interpret_drift()` when drift detected.
- **AutoMLEngine.run()**: Uses agent for model family recommendation (planned).

---

## 6. Data Handling (`interop.py`)

Centralized conversion module. The ONLY place in kailash-ml where polars data is converted to/from external formats.

### 6.1 Converters

| Function                                                                     | From -> To                                                | Notes                                                                                                                                                          |
| ---------------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `to_sklearn_input(df, feature_columns, target_column)`                       | polars -> `(X: ndarray, y: ndarray \| None, column_info)` | Handles categoricals (integer codes), booleans (cast to Int8), nulls (NaN). Raises on `pl.Utf8` not cast to `pl.Categorical`. Raises on entirely-null columns. |
| `from_sklearn_output(predictions, column_info, output_columns)`              | ndarray -> polars                                         | Restores column names from column_info.                                                                                                                        |
| `to_lgb_dataset(df, feature_columns, target_column, *, categorical_columns)` | polars -> `lgb.Dataset`                                   | Uses pandas ONLY for categorical columns (LightGBM requires `pd.Categorical`). Pure numpy path for non-categorical data.                                       |
| `to_hf_dataset(df)`                                                          | polars -> `datasets.Dataset`                              | Arrow zero-copy path.                                                                                                                                          |
| `polars_to_arrow(df, *, validate_schema, expected_schema)`                   | polars -> `pyarrow.Table`                                 | Near zero-copy (polars is Arrow-native). Optional schema validation.                                                                                           |
| `to_pandas(df)`                                                              | polars -> pandas                                          | Preserves categoricals, dates, nulls.                                                                                                                          |
| `from_pandas(pdf)`                                                           | pandas -> polars                                          | Inverse of `to_pandas`.                                                                                                                                        |
| `polars_to_dict_records(df, *, max_rows=5000)`                               | polars -> `list[dict]`                                    | For DataFlow Express API. Raises if >max_rows.                                                                                                                 |
| `from_arrow(table)`                                                          | pyarrow.Table -> polars                                   |                                                                                                                                                                |
| `dict_records_to_polars(records)`                                            | list[dict] -> polars                                      |                                                                                                                                                                |

### 6.2 Categorical Handling

Categoricals are encoded as integer codes via `col.to_physical()`. The category mapping is stored in `column_info["cat_mappings"]` for round-trip decode. Nulls become -1.

---

## 7. Metrics Registry (`metrics/_registry.py`)

### 7.1 Architecture

Registry-based metric computation wrapping sklearn metrics. Every metric is a registered callable with a standard signature. The registry is the single source of truth.

### 7.2 Built-in Metrics

**Classification**: `accuracy`, `f1`, `precision`, `recall`, `auc`.
**Regression**: `mse`, `rmse`, `mae`, `r2`.
**Probability**: `log_loss`, `brier_score_loss`, `average_precision`.

### 7.3 API

- `register_metric(name, fn, *, requires_prob=False)` -- Register a custom metric.
- `compute_metric(name, y_true, y_pred, **kwargs) -> float` -- Compute a single metric.
- `compute_metrics(y_true, y_pred, metric_names, *, y_prob, model, X_test) -> dict[str, float]` -- Compute multiple metrics. Probability metrics use `y_prob` when available.

Metrics accept polars Series or numpy arrays. Polars inputs converted to numpy at the boundary.

---

## 8. Dashboard

### 8.1 Architecture

Starlette ASGI app serving JSON API + embedded single-page HTML UI. Requires `pip install kailash-ml[dashboard]`.

**Dependencies**: `starlette`, `uvicorn` (lazy-imported).

### 8.2 API Endpoints

| Endpoint                                                      | Description                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------------------- |
| `GET /`                                                       | Dashboard HTML page                                                 |
| `GET /api/overview`                                           | Aggregate stats (experiments, runs, models, features, drift alerts) |
| Plus endpoints for experiments, runs, models, features, drift |                                                                     |

### 8.3 State Injection

Dashboard app receives `tracker`, `registry`, `feature_store`, `drift_monitor` via `app.state`.

### 8.4 CLI Entry Point

`kailash-ml-dashboard` (registered in pyproject.toml as script entry point).

---

## 9. Reinforcement Learning (`rl/`)

### 9.1 RLTrainer

Stable-Baselines3 wrapper for RL training lifecycle. Requires `pip install kailash-ml[rl]`.

**RLTrainingConfig**: `algorithm` ("PPO", "SAC", "DQN", "A2C", "TD3", "DDPG"), `policy_type` ("MlpPolicy"), `total_timesteps` (100_000), `hyperparameters`, `n_eval_episodes` (10), `eval_freq` (10_000), `seed` (42), `verbose` (0), `save_path`.

**RLTrainingResult**: `policy_name`, `algorithm`, `total_timesteps`, `mean_reward`, `std_reward`, `training_time_seconds`, `artifact_path`, `eval_history`.

### 9.2 Supporting Modules

- `env_registry.py` -- Environment registry for gymnasium environments.
- `policy_registry.py` -- Policy registry for SB3 policies.

---

## 10. GPU Setup CLI

Entry point: `kailash-ml-gpu-setup`.

Detects CUDA version via (in priority order):

1. `CUDA_VERSION` env var
2. `nvidia-smi`
3. `nvcc --version`
4. `/usr/local/cuda/version.txt`

Maps CUDA version to PyTorch index URL (`cu118`, `cu121`, `cu124`, `cu126`) and prints the install command.

---

## 11. Shared Internals

### 11.1 `_shared.py`

- `NUMERIC_DTYPES`: Tuple of all polars numeric types (Float64, Float32, Int64, Int32, Int16, Int8, UInt64, UInt32, UInt16, UInt8).
- `ALLOWED_MODEL_PREFIXES`: Frozenset of `{"sklearn.", "lightgbm.", "xgboost.", "catboost.", "kailash_ml.", "torch.", "lightning."}`.
- `validate_model_class(model_class: str)`: Raises `ValueError` if class doesn't match any prefix.
- `compute_metrics_by_name(y_true, y_pred, metric_names, model, X_test, y_prob)`: Delegates to `metrics._registry.compute_metrics`.

### 11.2 `_decorators.py`

- `@experimental` decorator: Marks P2 engines. Emits `ExperimentalWarning` on first instantiation per class per interpreter session. Sets `cls._quality_tier = "P2"`.
- `ExperimentalWarning(UserWarning)`: Custom warning class.

### 11.3 `_feature_sql.py`

Encapsulated SQL for FeatureStore. The single auditable SQL touchpoint. FeatureStore itself contains zero raw SQL.

Functions: `create_metadata_table`, `compute_schema_hash`, `read_metadata`, `create_feature_table`, `upsert_metadata`, `upsert_batch`, `get_features_as_of`, `get_features_latest`, `get_features_range`, `list_all_schemas`, `dtype_to_sql`.

---

## 12. Security Constraints

### 12.1 Model Class Allowlist

Every `model_class` string is validated against `ALLOWED_MODEL_PREFIXES` before `importlib.import_module`. This prevents arbitrary code execution via model instantiation. Enforced in `ModelSpec.instantiate()`, `EnsembleEngine.stack()`, and `TrainingPipeline._train_lightning()`.

### 12.2 Pickle Deserialization

Pickle deserialization (`pickle.loads`) is used in ModelRegistry and InferenceServer. Each call site carries the security comment: "SECURITY: pickle deserialization executes arbitrary code. Only load artifacts from TRUSTED sources."

### 12.3 Artifact Path Traversal

`LocalFileArtifactStore` validates artifact names against path separators and `..` sequences. Resolved paths are checked against the root directory to prevent traversal.

### 12.4 Identifier Validation

ExperimentTracker uses `kailash.db.dialect._validate_identifier` for experiment and run names that appear in SQL.
