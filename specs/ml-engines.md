# Kailash ML Engines Specification

Parent domain: ML Lifecycle (`kailash-ml`). Companion file: `ml-integration.md` (architecture, type contracts, ONNX bridge, MLflow, agent infusion, data handling, dashboard, security, RL, shared internals).

Package: `kailash-ml` v0.9.0
License: Apache-2.0
Python: >=3.11

This file is the domain truth for the **17 ML engines** in kailash-ml: P0 production engines (FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, ExperimentTracker), P1 production-with-caveats engines (HyperparameterSearch, AutoMLEngine, EnsembleEngine, ClusteringEngine, AnomalyDetectionEngine, DimReductionEngine, PreprocessingPipeline), and P2 experimental engines (DataExplorer, FeatureEngineer, ModelVisualizer, ModelExplainer). All constructors, methods, configuration, and engine-specific edge cases are authoritative here.

For architecture, type protocols (MLToolProtocol, AgentInfusionProtocol, FeatureField, FeatureSchema, ModelSignature, MetricSpec), ONNX bridge, MLflow compatibility, agent infusion, data handling via `interop.py`, metrics registry, dashboard, and shared internals, see `ml-integration.md`.

---

## 1. Engines

### 1.1 FeatureStore [P0: Production]

**Purpose**: DataFlow-backed, polars-native feature versioning with point-in-time correctness.

**Constructor**:

```python
FeatureStore(conn: ConnectionManager, *, table_prefix: str = "kml_feat_")
```

- `conn`: An initialized ConnectionManager. The caller owns the lifecycle.
- `table_prefix`: Prefix for generated feature tables. Validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` (optional trailing underscore). Invalid prefix raises `ValueError`.

**Lifecycle**:

- `async initialize() -> None` -- Creates internal metadata table `_kml_feature_schemas`. Idempotent.
- Auto-initializes on first call to any data method.

**Key Methods**:

| Method              | Signature                                                                                                                                                                           | Description                                                                                                                                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `register_features` | `async (schema: FeatureSchema) -> None`                                                                                                                                             | Register schema, create backing table. Idempotent (re-registration with same hash is no-op). Different hash raises `ValueError` to prevent silent schema drift.                                                           |
| `compute`           | `(raw_data: pl.DataFrame \| pl.LazyFrame, schema: FeatureSchema) -> pl.DataFrame`                                                                                                   | Validate DataFrame against schema (missing columns, nullable constraints), project to schema columns. LazyFrame collected eagerly.                                                                                        |
| `store`             | `async (features: pl.DataFrame, schema: FeatureSchema) -> int`                                                                                                                      | Materialize features to DB. Returns row count. Uses chunked inserts (1000 rows/chunk). Dict path for <10K rows, bulk path for larger. Adds `created_at` timestamp.                                                        |
| `get_features`      | `async (entity_ids: list[str], feature_names: list[str], *, schema_name: str \| None = None, schema: FeatureSchema \| None = None, as_of: datetime \| None = None) -> pl.DataFrame` | Retrieve features. When `as_of` is set, returns point-in-time correct values (latest before cutoff). Exactly one of `schema_name` or `schema` required. Returns empty DataFrame with expected columns when no rows match. |
| `get_training_set`  | `async (schema: FeatureSchema, *, start: datetime, end: datetime) -> pl.DataFrame`                                                                                                  | Retrieve all features within a time window for training.                                                                                                                                                                  |
| `get_features_lazy` | Same as `get_features` but returns `pl.LazyFrame`                                                                                                                                   | Data fetched eagerly from DB, wrapped in LazyFrame for deferred downstream ops.                                                                                                                                           |
| `list_schemas`      | `async () -> list[dict]`                                                                                                                                                            | List all registered feature schemas with metadata.                                                                                                                                                                        |

**Edge Cases**:

- Schema hash computed from `schema.to_dict()` -- any field change produces a different hash.
- All raw SQL is encapsulated in `_feature_sql.py`; `feature_store.py` contains zero raw SQL.
- `_BULK_THRESHOLD = 10_000` rows.

---

### 1.2 ModelRegistry [P0: Production]

**Purpose**: Model lifecycle management with versioned stages, artifact storage, and ONNX export.

**Constructor**:

```python
ModelRegistry(conn: ConnectionManager, artifact_store: ArtifactStore | None = None, *, auto_migrate: bool = True)
```

- `artifact_store`: Defaults to `LocalFileArtifactStore(root_dir=".kailash_ml/artifacts")`.
- `auto_migrate`: When True, creates tables on first use.

**Stage Lifecycle**:

```
staging -> shadow | production | archived
shadow  -> production | archived | staging
production -> archived | shadow
archived -> staging
```

When promoting to `production`, the current production version is automatically demoted to `archived`.

**Key Methods**:

| Method               | Signature                                                                                                                                   | Description                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `register_model`     | `async (name: str, artifact: bytes, *, metrics: list[MetricSpec] \| None = None, signature: ModelSignature \| None = None) -> ModelVersion` | Register new version at STAGING. Auto-increments version. Attempts ONNX export (non-fatal on failure). Saves pickle, ONNX, and metadata JSON to artifact store. Uses transaction to prevent TOCTOU race on version increment. |
| `get_model`          | `async (name: str, version: int \| None = None, *, stage: str \| None = None) -> ModelVersion`                                              | Retrieve by version, stage, or latest. Raises `ModelNotFoundError`.                                                                                                                                                           |
| `list_models`        | `async () -> list[dict]`                                                                                                                    | List all model entries with latest_version.                                                                                                                                                                                   |
| `promote_model`      | `async (name: str, version: int, target_stage: str, *, reason: str = "") -> ModelVersion`                                                   | Transition between stages. Validates against `VALID_TRANSITIONS`. Records transition in audit table.                                                                                                                          |
| `get_model_versions` | `async (name: str) -> list[ModelVersion]`                                                                                                   | All versions, newest first.                                                                                                                                                                                                   |
| `compare`            | `async (name: str, version_a: int, version_b: int) -> dict`                                                                                 | Compare stored metrics between two versions. Returns `{"deltas": {...}, "better_version": ...}`.                                                                                                                              |
| `load_artifact`      | `async (name: str, version: int, filename: str = "model.pkl") -> bytes`                                                                     | Load raw artifact bytes.                                                                                                                                                                                                      |
| `export_mlflow`      | `async (name: str, version: int, output_dir: Path) -> Path`                                                                                 | Export to MLflow MLmodel format v1 directory.                                                                                                                                                                                 |
| `import_mlflow`      | `async (mlmodel_dir: Path) -> ModelVersion`                                                                                                 | Import from MLflow format, register as new version.                                                                                                                                                                           |

**ModelVersion dataclass fields**: `name`, `version`, `stage`, `metrics: list[MetricSpec]`, `signature: ModelSignature | None`, `onnx_status` ("pending" | "success" | "failed" | "not_applicable"), `onnx_error`, `artifact_path`, `model_uuid`, `created_at`.

**ArtifactStore protocol**: `save`, `load`, `exists`, `delete`. LocalFileArtifactStore validates against path traversal attacks.

**Tables**: `_kml_models`, `_kml_model_versions`, `_kml_model_transitions`.

---

### 1.3 TrainingPipeline [P0: Production]

**Purpose**: Full training lifecycle: features -> train -> evaluate -> register.

**Constructor**:

```python
TrainingPipeline(feature_store: Any, registry: ModelRegistry)
```

**Key Types**:

**ModelSpec**:

- `model_class: str` -- Fully qualified class name, e.g. `"sklearn.ensemble.RandomForestClassifier"`. Validated against security allowlist.
- `hyperparameters: dict` -- Passed to model constructor.
- `framework: str` -- `"sklearn"`, `"lightgbm"`, or `"lightning"`.
- `instantiate() -> Any` -- Creates model instance via `importlib.import_module` + `getattr`.

**EvalSpec**:

- `metrics: list[str]` -- Default `["accuracy"]`.
- `split_strategy: str` -- `"holdout"`, `"kfold"`, `"stratified_kfold"`, `"walk_forward"`.
- `n_splits: int` -- Default 5.
- `test_size: float` -- Default 0.2.
- `min_threshold: dict[str, float]` -- Minimum metric values for registration.

**Key Methods**:

| Method      | Signature                                                                                                                                                                                                                                               | Description                                                                                                                                                      |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `train`     | `async (data: pl.DataFrame, schema: FeatureSchema, model_spec: ModelSpec, eval_spec: EvalSpec, experiment_name: str, *, agent: AgentInfusionProtocol \| None = None, tracker: Any \| None = None, parent_run_id: str \| None = None) -> TrainingResult` | Full pipeline: validate, split, convert via interop, fit, evaluate, register if threshold met, optionally log to ExperimentTracker.                              |
| `calibrate` | `async (model, X_val: pl.DataFrame, y_val: pl.Series, *, method: str = "sigmoid") -> Any`                                                                                                                                                               | Calibrate classifier probabilities. `"sigmoid"` (Platt scaling) or `"isotonic"`. Returns `CalibratedClassifierCV`. Uses `FrozenEstimator` to prevent re-fitting. |
| `evaluate`  | `async (model_name: str, version: int, data: pl.DataFrame, schema: FeatureSchema, eval_spec: EvalSpec) -> dict[str, float]`                                                                                                                             | Evaluate a registered model on new data (shadow mode).                                                                                                           |
| `retrain`   | `async (model_name: str, schema, model_spec, eval_spec, data, *, tracker: Any \| None = None) -> TrainingResult`                                                                                                                                        | Retrain using new data, register as next version.                                                                                                                |

**Splitting strategies**:

- `holdout`: Deterministic shuffle (seed=42), split at `(1 - test_size)`.
- `kfold`: sklearn KFold, returns first fold.
- `stratified_kfold`: sklearn StratifiedKFold, returns first fold.
- `walk_forward`: No shuffle, tail is test (time-series aware).

**TrainingResult fields**: `model_version`, `metrics`, `training_time_seconds`, `data_shape`, `registered`, `threshold_met`, `run_id`.

**Target detection**: Automatically detects the target column as any column not in the feature schema or entity/timestamp columns.

**Frameworks supported**:

- `sklearn`: Standard `model.fit(X, y)`.
- `lightgbm`: Uses sklearn API (`LGBMClassifier.fit`). Requires `pip install lightgbm`.
- `lightning`: PyTorch Lightning. Separates `trainer_` prefixed hyperparameters for `L.Trainer` kwargs from module kwargs. Requires `pip install kailash-ml[dl]`.

---

### 1.4 InferenceServer [P0: Production]

**Purpose**: Load, cache, and serve predictions with Nexus and MCP integration.

**Constructor**:

```python
InferenceServer(registry: ModelRegistry, *, cache_size: int = 10)
```

**LRU Cache**: `_ModelCache` uses `OrderedDict` with `max_size`. Evicts least-recently-used on capacity. Cache key: `"{model_name}:v{version}"`.

**Key Methods**:

| Method               | Signature                                                                                                                                                  | Description                                                                                                                         |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `predict`            | `async (model_name: str, features: dict[str, Any], *, version: int \| None = None, options: dict \| None = None, strict: bool = True) -> PredictionResult` | Single-record prediction. Tries ONNX first when available, falls back to native.                                                    |
| `predict_batch`      | `async (model_name: str, records: list[dict], *, version: int \| None = None, strict: bool = True) -> list[PredictionResult]`                              | Batch prediction. Converts list[dict] -> polars -> numpy in one shot.                                                               |
| `warm_cache`         | `async (model_names: list[str]) -> None`                                                                                                                   | Pre-load models into cache.                                                                                                         |
| `register_endpoints` | `(nexus: Any) -> None`                                                                                                                                     | Register HTTP endpoints with Nexus: `POST /api/predict/{model_name}`, `POST /api/predict_batch/{model_name}`, `GET /api/ml/health`. |
| `register_mcp_tools` | `(server: Any, namespace: str = "ml") -> None`                                                                                                             | Register MCP tools: `ml.predict`, `ml.predict_batch`, `ml.model_info`.                                                              |
| `get_metrics`        | `async (model_name, version, *, options) -> dict`                                                                                                          | MLToolProtocol: return model metrics.                                                                                               |
| `get_model_info`     | `async (model_name, *, options) -> dict`                                                                                                                   | MLToolProtocol: return model metadata.                                                                                              |

**Feature validation** (`strict` mode):

- Missing features: raises `ValueError` in strict mode, logs warning and substitutes `0.0` in non-strict.
- Non-numeric values: same behavior. Checks via `isinstance(val, (int, float))` or numpy scalar or `float()` conversion.

**Inference paths**:

- **ONNX**: When `onnx_status == "success"` and `onnxruntime` is available. Input dtype: `float32`.
- **Native**: Standard `model.predict()`. Input dtype: `float64`.
- ONNX probability outputs handled for both dict format `[{class: prob}]` and array format.

**PredictionResult fields**: `prediction`, `probabilities`, `model_name`, `model_version`, `inference_time_ms`, `inference_path` ("onnx" | "native").

---

### 1.5 DriftMonitor [P0: Production]

**Purpose**: Distribution shift detection using PSI and KS-test, with performance degradation monitoring and scheduled checks.

**Constructor**:

```python
DriftMonitor(conn: ConnectionManager, *, psi_threshold: float = 0.2, ks_threshold: float = 0.05, performance_threshold: float = 0.1)
```

All thresholds validated as finite in `__init__`.

**Drift Detection Methods**:

| Metric                           | Threshold             | Interpretation                                              |
| -------------------------------- | --------------------- | ----------------------------------------------------------- |
| PSI (Population Stability Index) | >0.2 = drift          | <0.1 none, 0.1-0.2 moderate, >0.2 significant, >0.25 severe |
| KS-test (Kolmogorov-Smirnov)     | p-value <0.05 = drift | Two-sample test, numeric features only                      |

Drift is detected when PSI exceeds threshold OR KS p-value is below threshold (for numeric features).

**Categorical PSI**: Computes PSI over category frequency distributions instead of histogram bins.

**Key Methods**:

| Method                | Signature                                                                                                                                             | Description                                                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `set_reference_data`  | `async (model_name: str, reference_data: pl.DataFrame, feature_columns: list[str]) -> None`                                                           | Store per-feature reference distribution. Persists to DB and caches in memory. Memory cache bounded to 100 references (evicts oldest).                        |
| `check_drift`         | `async (model_name: str, current_data: pl.DataFrame, *, agent: AgentInfusionProtocol \| None = None) -> DriftReport`                                  | Check feature drift against stored reference. Stores report to DB. Optionally invokes agent interpretation on drift. Raises `ValueError` if no reference set. |
| `check_performance`   | `async (model_name: str, predictions: pl.DataFrame, actuals: pl.DataFrame, *, baseline_metrics: dict \| None = None) -> PerformanceDegradationReport` | Compare current performance against baseline. Auto-stores first metrics as baseline.                                                                          |
| `get_drift_history`   | `async (model_name: str, limit: int = 20) -> list[dict]`                                                                                              | Retrieve stored drift reports.                                                                                                                                |
| `schedule_monitoring` | `async (model_name: str, interval: timedelta, data_fn: Callable, spec: DriftSpec \| None = None) -> None`                                             | Schedule periodic drift checks as asyncio background task. Minimum interval 1 second. Calls `DriftSpec.on_drift_detected` callback on drift.                  |
| `cancel_monitoring`   | `async (model_name: str) -> bool`                                                                                                                     | Cancel scheduled monitoring.                                                                                                                                  |
| `shutdown`            | `async () -> None`                                                                                                                                    | Cancel all scheduled tasks.                                                                                                                                   |

**DriftCallback type**: `Callable[[DriftReport], Awaitable[None]]` -- async callback invoked when drift is detected.

**DriftReport fields**: `model_name`, `feature_results: list[FeatureDriftResult]`, `overall_drift_detected`, `overall_severity` ("none" | "moderate" | "severe"), `checked_at`, `reference_set_at`, `sample_size_reference`, `sample_size_current`.

**Tables**: `_kml_drift_references`, `_kml_drift_reports`, `_kml_performance_baselines`.

---

### 1.6 ExperimentTracker [P0: Production]

**Purpose**: Experiment lifecycle, run logging, step-based metrics (training curves), and artifact metadata. MLflow-compatible concepts.

**Constructor**:

```python
ExperimentTracker(conn: ConnectionManager, *, artifact_root: str | Path = ".kailash_ml/experiments")
```

**Hierarchy**: Experiment -> Run (optional parent_run_id for nesting) -> Params + Metrics + Artifacts.

**Key Types**:

- `Experiment(id, name, description, created_at, tags)`
- `Run(id, experiment_id, name, status, start_time, end_time, parent_run_id, tags)`
- `MetricEntry(name, value, step, timestamp)` -- supports step-based logging for training curves.
- `RunContext` -- async context manager for auto-starting/ending runs.

**Valid run statuses**: `RUNNING`, `COMPLETED`, `FAILED`, `KILLED`.

**Key Methods**:

| Method                                                      | Description                                                            |
| ----------------------------------------------------------- | ---------------------------------------------------------------------- |
| `create_experiment(name, description, tags)`                | Create experiment. Idempotent by name.                                 |
| `start_run(experiment_name, run_name, parent_run_id, tags)` | Start a new run. Returns `Run`.                                        |
| `end_run(run_id, status)`                                   | End a run with status.                                                 |
| `log_params(run_id, params)`                                | Log parameter dict.                                                    |
| `log_metric(run_id, name, value, step)`                     | Log single metric (optional step for curves).                          |
| `log_metrics(run_id, metrics)`                              | Log multiple metrics.                                                  |
| `run(experiment_name, run_name, parent_run_id)`             | Async context manager (`RunContext`). Auto-ends with COMPLETED/FAILED. |
| `get_metric_history(run_id, metric_name)`                   | Get step-by-step metric values.                                        |
| `compare_runs(run_ids)`                                     | Compare metrics across runs.                                           |
| `list_experiments()`                                        | List all experiments.                                                  |
| `search_runs(experiment_name, filter_params, order_by)`     | Search runs with filtering.                                            |

**Integration with TrainingPipeline**: When a `tracker` is passed to `train()`, it auto-creates a run, logs `model_class`, `framework`, `split_strategy`, `test_size`, `n_rows`, `n_cols`, all hyperparameters (prefixed with `hp.`), all metrics, and `training_time_seconds`.

**Integration with HyperparameterSearch and AutoML**: Creates parent runs for the search/AutoML session, with child runs for each trial.

---

### 1.7 HyperparameterSearch [P1: Production with Caveats]

**Purpose**: Grid, random, Bayesian (optuna), and successive halving hyperparameter optimization.

**Known limitation**: Bayesian search with >50 parameters may not converge within default trial budget.

**Constructor**:

```python
HyperparameterSearch(pipeline: TrainingPipeline)
```

**Configuration Types**:

**ParamDistribution**: `name`, `type` ("uniform" | "log_uniform" | "int_uniform" | "categorical"), `low`, `high`, `choices`.

**SearchSpace**: Contains `list[ParamDistribution]`. Methods:

- `sample_grid()` -- Exhaustive grid. Continuous params sampled at 5 linspace points.
- `sample_random(n, rng)` -- Random samples. Default seed 42.

**SearchConfig**: `strategy` (default "bayesian"), `n_trials` (50), `timeout_seconds`, `metric_to_optimize` ("accuracy"), `direction` ("maximize" | "minimize"), `early_stopping_patience`, `n_jobs` (1), `register_best` (True).

**Key Method**:

```python
async search(data, schema, base_model_spec, search_space, config, eval_spec, experiment_name, *, tracker=None, parent_run_id=None) -> SearchResult
```

**Strategies**:

- **Grid**: Exhaustive enumeration of all parameter combinations.
- **Random**: N random samples from parameter distributions.
- **Bayesian**: Uses `optuna.create_study` with TPE sampler. Runs objective in executor thread, uses `asyncio.run_coroutine_threadsafe` to call async train from sync objective.
- **Successive halving**: Uses Optuna's `SuccessiveHalvingPruner`. Trains on increasing data fractions (12.5%, 25%, 50%, 100%). Prunes poor performers early. Reports intermediate values to trial.

**SearchResult fields**: `best_params`, `best_metrics`, `best_trial_number`, `all_trials: list[TrialResult]`, `total_time_seconds`, `strategy`, `model_version`.

**TrialResult fields**: `trial_number`, `params`, `metrics`, `training_time_seconds`, `pruned: bool`.

---

### 1.8 AutoMLEngine [P1: Production with Caveats]

**Purpose**: Automated model selection + hyperparameter optimization across multiple model families.

**Constructor**:

```python
AutoMLEngine(pipeline: TrainingPipeline, search: HyperparameterSearch, *, registry: ModelRegistry | None = None)
```

**AutoMLConfig fields**: `task_type` ("classification" | "regression"), `metric_to_optimize`, `direction`, `candidate_families`, `search_strategy`, `search_n_trials` (30), `register_best`, `agent` (False), `auto_approve` (False), `max_llm_cost_usd` (1.0), `approval_timeout_seconds` (600.0), `audit_batch_size` (10), `audit_flush_interval_seconds` (30.0).

**Default candidate families**:

Classification:

- `sklearn.ensemble.RandomForestClassifier`
- `sklearn.ensemble.GradientBoostingClassifier`
- `sklearn.linear_model.LogisticRegression`

Regression:

- `sklearn.ensemble.RandomForestRegressor`
- `sklearn.ensemble.GradientBoostingRegressor`
- `sklearn.linear_model.Ridge`

**Pipeline**:

1. Profile data.
2. Compute baseline recommendation (rank families by dataset size + feature count).
3. Quick-train each candidate with default hyperparameters.
4. Rank candidates by optimization metric.
5. Run HyperparameterSearch on top candidate.
6. Return best model with all results.

**LLMCostTracker**: Tracks cumulative LLM token costs across Delegate runs. Per-model pricing from `KAILASH_ML_LLM_COST_INPUT_PER_1K` and `KAILASH_ML_LLM_COST_OUTPUT_PER_1K` env vars (defaults: $0.003 and $0.015). Raises `LLMBudgetExceededError` when budget exceeded.

**Agent augmentation**: Double opt-in required: `pip install kailash-ml[agents]` AND `agent=True`. Not yet fully implemented in v1.

---

### 1.9 EnsembleEngine [P1: Production with Caveats]

**Purpose**: Ensemble model creation via blending, stacking, bagging, and boosting.

**Constructor**: No arguments. Stateless engine.

**Methods**:

| Method                                                                                               | Description                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `blend(models, data, target, *, weights, method, test_size, seed) -> BlendResult`                    | Weighted averaging ("soft") or majority voting ("hard"). Uses `VotingClassifier`/`VotingRegressor`. Soft voting requires `predict_proba` on all models. Reports per-component contributions. |
| `stack(models, data, target, *, meta_model_class, fold, test_size, seed) -> StackResult`             | Cross-validated stacking with meta-learner. `meta_model_class` validated against security allowlist. Uses `StackingClassifier`/`StackingRegressor`.                                          |
| `bag(model, data, target, *, n_estimators, max_samples, max_features, test_size, seed) -> BagResult` | Bootstrap aggregating. Uses `BaggingClassifier`/`BaggingRegressor`.                                                                                                                          |
| `boost(model, data, target, *, n_estimators, learning_rate, test_size, seed) -> BoostResult`         | AdaBoost. Requires base model to support `sample_weight`. Uses `AdaBoostClassifier`/`AdaBoostRegressor`.                                                                                     |

**Task type auto-detection**: `<=20 unique target values` -> classification, else regression.

---

### 1.10 ClusteringEngine [P1: Production with Caveats]

**Purpose**: Unsupervised clustering via KMeans, DBSCAN, GMM, and Spectral Clustering.

**Constructor**: No arguments. Stateless engine.

**Supported algorithms**: `kmeans`, `dbscan`, `gmm`, `spectral`.

**Methods**:

| Method                                                                   | Description                                                                                                                                      |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `fit(data, algorithm, n_clusters, **kwargs) -> ClusterResult`            | Fit clustering algorithm. Non-numeric columns silently excluded. DBSCAN ignores `n_clusters`. Extra kwargs passed to sklearn.                    |
| `sweep_k(data, k_range, algorithm, criterion, **kwargs) -> KSweepResult` | Sweep across k values. DBSCAN not supported (no `n_clusters` param). Criterion: `"silhouette"` or `"calinski_harabasz"` (both higher is better). |

**ClusterResult fields**: `labels`, `n_clusters`, `algorithm`, `silhouette_score`, `calinski_harabasz_score`, `inertia` (KMeans only), `metrics` dict.

**GMM-specific metrics**: BIC and AIC.
**DBSCAN-specific metrics**: `n_noise_points`.

**Edge cases**:

- Empty DataFrame raises `ValueError`.
- Metrics require >=2 clusters and more samples than clusters; returns `None` otherwise.
- Non-finite values sanitized to `None`.

---

### 1.11 AnomalyDetectionEngine [P1: Production with Caveats]

**Purpose**: Unsupervised anomaly detection via Isolation Forest, LOF, and One-Class SVM.

**Constructor**: No arguments. Stateless engine.

**Supported algorithms**: `isolation_forest`, `lof`, `one_class_svm`.

**Score normalization**: All anomaly scores normalized to [0, 1] regardless of algorithm, where higher = more anomalous. Uses min-max normalization with sklearn convention inversion (sklearn: lower = more anomalous).

**Methods**:

| Method                                                                                                                  | Description                                                                                                                                                                          |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `detect(data, *, algorithm, contamination, feature_columns, seed, **kwargs) -> AnomalyResult`                           | Single algorithm detection. `contamination` must be in (0, 0.5). Auto-selects numeric columns if `feature_columns` is None.                                                          |
| `ensemble_detect(data, *, algorithms, contamination, voting, feature_columns, seed, **kwargs) -> EnsembleAnomalyResult` | Run multiple algorithms and combine. `voting="majority"`: majority voting on labels. `voting="score_average"`: average normalized scores, threshold at 0.5. Requires >=2 algorithms. |

**AnomalyResult fields**: `labels` (1=normal, -1=anomaly), `scores` (0-1), `n_anomalies`, `contamination`, `algorithm`, `metrics` (n_samples, anomaly_ratio, score_separation, etc.).

---

### 1.12 DimReductionEngine [P1: Production with Caveats]

**Purpose**: Dimensionality reduction via PCA, NMF, t-SNE, and UMAP.

**Constructor**: No arguments. Stateless engine.

**Supported algorithms**: `pca`, `nmf`, `tsne`, `umap` (requires `umap-learn` package).

**Methods**:

| Method                                                                                    | Description                                                                                                                                                                   |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reduce(data, *, algorithm, n_components, columns, seed, **kwargs) -> DimReductionResult` | Reduce dimensionality. NMF requires non-negative input. t-SNE auto-adjusts perplexity based on sample count.                                                                  |
| `variance_analysis(data, *, columns) -> dict`                                             | PCA variance analysis without reducing. Returns `explained_variance_ratio`, `cumulative_variance`, `elbow_component` (via max-distance-to-line heuristic), `n_components_95`. |

**DimReductionResult fields**: `transformed` (N x n_components list), `n_components`, `algorithm`, `explained_variance_ratio` (PCA only), `reconstruction_error` (PCA/NMF), `metrics` dict.

**Elbow detection**: Maximum perpendicular distance from each point to the line connecting first and last cumulative variance points. Falls back to first component crossing 95% cumulative variance.

---

### 1.13 PreprocessingPipeline [P1: Production with Caveats]

**Purpose**: Automatic data preprocessing for ML workflows. PyCaret `setup()` equivalent.

**Constructor**: No arguments. Stateless engine.

**Method**: `setup(data, target, *, test_size, seed, ...) -> SetupResult`

Auto-detects task type, identifies numeric vs categorical columns, encodes categoricals, scales numerics, imputes missing values, and splits train/test.

**SetupResult fields**: `train_data`, `test_data`, `target_column`, `task_type`, `numeric_columns`, `categorical_columns`, `transformers` (fitted sklearn transformers), `original_shape`, `transformed_shape`, `summary`.

**Task type detection**: Boolean/Categorical/String -> classification. Numeric with <=20 unique values -> classification. Otherwise regression.

---

### 1.14 DataExplorer [P2: Experimental]

**Purpose**: Async statistical profiling with plotly visualizations.

Computes summary statistics, distributions, correlations, and missing value analysis using polars. Generates interactive plotly visualizations. Async-first with parallel matrix computations via `asyncio.gather()`.

**Key Types**: `ColumnProfile`, `DataProfile`, `VisualizationReport`, `AlertConfig`.

---

### 1.15 FeatureEngineer [P2: Experimental]

**Purpose**: Automated feature generation and selection.

Generates candidate features (interactions, polynomial, binning, temporal) from source data, evaluates them, and selects the best subset.

**Strategies**: `"interaction"`, `"polynomial"`, `"binning"`, `"temporal"`.

**Key Types**: `GeneratedColumn`, `GeneratedFeatures`, `FeatureRank`, `SelectedFeatures`.

---

### 1.16 ModelVisualizer [P2: Experimental]

**Purpose**: Interactive plotly visualizations for model diagnostics. PyCaret `plot_model()` equivalent.

Generates: confusion matrix, ROC curve, precision-recall curve, feature importance, learning curves, residual plots, calibration curves, metric comparison, training history. All methods return `plotly.graph_objects.Figure`.

---

### 1.17 ModelExplainer [P2: Experimental]

**Purpose**: SHAP-based model explainability. Requires `pip install kailash-ml[explain]`.

Provides global and local explanations for fitted sklearn-compatible models. Accepts polars DataFrames and converts to numpy at the boundary.

---

## 2. Engine Edge Cases

### 2.1 Empty DataFrames

- FeatureStore.get_features: Returns empty DataFrame with expected column schema.
- ClusteringEngine.fit: Raises `ValueError`.
- DimReductionEngine.reduce: Raises `ValueError`.
- AnomalyDetectionEngine.detect: Raises `ValueError`.
- InferenceServer.predict_batch: Returns empty list for empty records.

### 2.2 Non-Finite Values

- `MetricSpec.__post_init__` validates value is finite.
- `DriftMonitor.__init__` validates all thresholds are finite.
- `AutoMLConfig.__post_init__` validates `max_llm_cost_usd` and `approval_timeout_seconds`.
- `LLMCostTracker.__init__` validates `max_budget_usd`.
- Clustering/DimReduction engines sanitize non-finite metric values to `None`.

### 2.3 Concurrent Access

- ModelRegistry.register_model: Wraps version increment in a transaction to prevent TOCTOU race.
- DriftMonitor.set_reference_data: Uses transaction for upsert.
- DriftMonitor.\_store_performance_baseline: Uses transaction for upsert.

### 2.4 Memory Bounds

- DriftMonitor.\_references: Bounded to 100 entries (evicts oldest).
- InferenceServer.\_cache: LRU with configurable max_size (default 10).
- LLMCostTracker.\_calls: `deque(maxlen=10000)`.

### 2.5 Schema Drift Prevention

FeatureStore.register_features computes a hash of the schema dict. Re-registration with the same hash is a no-op. Re-registration with a different hash raises `ValueError`. Version bumping or a new name is required.

### 2.6 Deterministic Reproducibility

All stochastic operations use `seed=42` by default (holdout split, k-fold, random search, clustering). This ensures reproducible results across runs.
