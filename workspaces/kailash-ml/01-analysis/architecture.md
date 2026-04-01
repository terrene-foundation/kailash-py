# kailash-ml Architecture

## 1. Package Structure

### 1.1 Directory Layout

```
packages/
  kailash-ml-protocols/              # Thin interface package (~50KB, no ML deps)
    src/kailash_ml_protocols/
      __init__.py
      protocols.py                   # MLToolProtocol, AgentInfusionProtocol
      schemas.py                     # FeatureSchema, ModelSignature, MetricSpec
    pyproject.toml

  kailash-ml/
    src/kailash_ml/
      __init__.py                    # Lazy imports for all engines
      interop.py                     # polars conversion utilities (benchmarked)
      serialization.py               # ModelSerializer (native + ONNX)
      engines/
        __init__.py
        feature_store.py             # FeatureStore
        model_registry.py            # ModelRegistry
        training_pipeline.py         # TrainingPipeline
        inference_server.py          # InferenceServer
        drift_monitor.py             # DriftMonitor
        automl.py                    # AutoMLEngine
        data_explorer.py             # DataExplorer
        hyperparameter_search.py     # HyperparameterSearch
        feature_engineer.py          # FeatureEngineer
      agents/
        __init__.py
        data_scientist.py
        feature_engineer.py
        model_selector.py
        experiment_interpreter.py
        drift_analyst.py
        retraining_decision.py
        tools.py                     # All agent tools (dumb data endpoints)
      rl/                            # [rl] optional extra
        __init__.py
        trainer.py                   # RLTrainer (SB3 wrapper)
        env_registry.py              # EnvironmentRegistry
        policy_registry.py           # PolicyRegistry
    tests/
      test_interop.py
      test_protocols.py
      test_serialization.py
      bench/
        test_interop_bench.py        # Benchmark harness
    pyproject.toml
    README.md
```

### 1.2 pyproject.toml

```toml
[project]
name = "kailash-ml"
version = "1.0.0"
description = "Classical and deep learning lifecycle for the Kailash ecosystem"
requires-python = ">=3.10"
license = {text = "Apache-2.0"}
dependencies = [
    "kailash>=1.0",
    "kailash-dataflow>=1.0",
    "kailash-nexus>=1.0",
    "kailash-ml-protocols>=1.0",
    "polars>=1.0",
    "numpy>=1.26",
    "scipy>=1.12",
    "plotly>=5.18",
    "scikit-learn>=1.4",
    "lightgbm>=4.3",
    "skl2onnx>=1.16",
    "onnxmltools>=1.12",
]

[project.optional-dependencies]
xgb = ["xgboost>=2.0"]
catboost = ["catboost>=1.2"]
stats = ["statsmodels>=0.14"]
dl = [
    "torch>=2.2",
    "lightning>=2.2",
    "torchvision>=0.17",
    "torchaudio>=2.2",
    "timm>=1.0",
    "transformers>=4.40",
    "onnxruntime>=1.17",
]
dl-gpu = [
    "torch>=2.2",
    "lightning>=2.2",
    "torchvision>=0.17",
    "torchaudio>=2.2",
    "timm>=1.0",
    "transformers>=4.40",
    "onnxruntime-gpu>=1.17",
]
rl = [
    "kailash-ml[dl]",
    "stable-baselines3>=2.3",
    "gymnasium>=0.29",
]
agents = ["kailash-kaizen>=1.0"]
full = ["kailash-ml[dl,xgb,catboost,stats,rl,agents]"]
full-gpu = ["kailash-ml[dl-gpu,xgb,catboost,stats,rl,agents]"]

[project.scripts]
kailash-ml-gpu-setup = "kailash_ml.cli:gpu_setup"
```

### 1.3 Install Size Tiers

| Tier | Command | Size | Contents |
|------|---------|------|----------|
| Base (Classical ML) | `pip install kailash-ml` | ~195MB | polars, numpy, scipy, plotly, sklearn, lightgbm, skl2onnx, onnxmltools |
| Deep Learning (CPU) | `pip install kailash-ml[dl]` | ~480MB | + torch (CPU), lightning, torchvision, torchaudio, timm, transformers, onnxruntime |
| Deep Learning (GPU) | `pip install kailash-ml[dl-gpu]` | ~2.5GB | + torch (CUDA), lightning, torchvision (CUDA), torchaudio (CUDA), timm, transformers, onnxruntime-gpu |
| Classical RL | `pip install kailash-ml[rl]` | ~505MB | + stable-baselines3, gymnasium (requires [dl]) |
| Everything (CPU) | `pip install kailash-ml[full]` | ~530MB | Union of all above |
| Everything (GPU) | `pip install kailash-ml[full-gpu]` | ~2.8GB | Union of all above with CUDA |

**GPU users must supply `--extra-index-url https://download.pytorch.org/whl/cu121`** (or cu118/cu124) when installing `[dl-gpu]`. The extra cannot enforce the CUDA index URL. A `kailash-ml-gpu-setup` CLI detects CUDA version and prints the correct install command.

---

## 2. Circular Dependency Resolution

### 2.1 The Problem

```
kailash-ml ---depends-on---> kailash-kaizen  (for AutoML agent infusion)
kailash-kaizen ---depends-on---> kailash-ml  (for ML-aware tools)
```

This is a hard import cycle. `pip install kailash-ml` would require kailash-kaizen, which would require kailash-ml.

### 2.2 The Solution: Interface Package + Runtime Injection

```
kailash-ml-protocols   (NEW, ~50KB)
    - MLToolProtocol         (predict, get_metrics, trigger_retrain)
    - AgentInfusionProtocol  (suggest_features, select_model, interpret_results)
    - FeatureSchema, ModelSignature, MetricSpec  (shared data contracts)

kailash-ml
    +-- kailash-ml-protocols  (import the contracts)
    # Implements MLToolProtocol
    # OPTIONALLY consumes AgentInfusionProtocol at runtime

kailash-kaizen
    +-- kailash-ml-protocols  (import the contracts)
    # OPTIONALLY implements AgentInfusionProtocol
    # OPTIONALLY consumes MLToolProtocol via MCP tools
```

### 2.3 Runtime Discovery Pattern

```python
# kailash_ml/engines/automl.py
from kailash_ml_protocols import AgentInfusionProtocol

class AutoMLEngine:
    def __init__(self, pipeline: TrainingPipeline,
                 agent: AgentInfusionProtocol | None = None):
        self._agent = agent  # injected, not imported

    async def select_model(self, X, y, spec: ExperimentSpec):
        if self._agent:
            suggestion = await self._agent.suggest_model(X.describe(), spec)
            candidates = self._expand_candidates(suggestion)
        else:
            candidates = self._default_candidates(spec)
        return await self._evaluate_candidates(candidates, X, y, spec)
```

### 2.4 Protocol Definitions

```python
# kailash_ml_protocols/protocols.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class AgentInfusionProtocol(Protocol):
    async def suggest_model(self, data_profile: str, spec: dict) -> dict: ...
    async def suggest_features(self, data_profile: str, target: str) -> list[dict]: ...
    async def interpret_results(self, results: str, context: str) -> dict: ...

@runtime_checkable
class MLToolProtocol(Protocol):
    async def predict(self, model_name: str, features: dict) -> dict: ...
    async def get_metrics(self, model_name: str, version: str) -> dict: ...
    async def trigger_retrain(self, model_name: str, spec: dict) -> str: ...
```

### 2.5 Why Not extras_require Only?

Using `pip install kailash-ml[agents]` to pull in kailash-kaizen would still create a circular chain if kailash-kaizen also had `[ml]` extras pulling kailash-ml. The protocol package cleanly breaks the cycle at the type level.

### 2.6 Dependency DAG (Final)

```
                    kailash (core SDK)
                   /        |         \
        kailash-dataflow  kailash-nexus  kailash-kaizen
              |              |              |
              +--------------+--------------+
              |                             |
         kailash-ml-protocols    kailash-ml-protocols
              |                             |
         kailash-ml                    kailash-kaizen
         (implements MLToolProtocol)   (implements AgentInfusionProtocol)
              |                             |
              +---- runtime discovery ------+
```

---

## 3. Engine Specifications

### 3.1 TrainingPipeline

**Purpose**: Orchestrates the full training lifecycle: data loading, feature computation, model training, evaluation, and model registration.

**Depends on**: FeatureStore, ModelRegistry, Core SDK (WorkflowBuilder for pipeline DAG)

**Key Methods**:
```python
class TrainingPipeline:
    def __init__(self, feature_store: FeatureStore, registry: ModelRegistry):
        ...

    async def train(self, data, feature_schema, model_spec, eval_spec,
                    experiment_name) -> TrainingResult:
        """Full pipeline: features -> train -> evaluate -> register."""

    async def evaluate(self, model, data, eval_spec) -> EvalResult:
        """Evaluate only (for shadow mode comparison)."""

    async def retrain(self, model_name: str, new_data: pl.DataFrame) -> TrainingResult:
        """Retrain existing model with new data. Uses registered feature_schema."""
```

**Data types**:
- `ModelSpec`: `model_type` (str), `hyperparams` (dict), `trainer_class` (optional)
- `EvalSpec`: `cv_strategy` (str: "kfold_5", "walk_forward_5"), `metrics` (list[str]), `success_thresholds` (dict[str, float])
- `TrainingResult`: `model`, `metrics` (dict), `feature_importance` (pl.DataFrame|None), `experiment_id`, `model_version` (ModelVersion)

**Classical path**: calls `kailash_ml.interop.to_sklearn_input()` or `.to_lgb_dataset()` at training boundary. All other data handling is polars.

**DL path** (conditional on `[dl]` extra): uses `lightning.Trainer`. Lazily imported. Raises `ImportError` with install instructions if missing.

**Agent infusion**: `AgentInfusionProtocol` injection accepted at construction. When provided, `train()` uses agent model selection instead of grid/random search. Double opt-in required.

**On success**: model auto-registered in ModelRegistry at STAGING stage if metrics meet `success_thresholds`.

**Nexus**: `POST /api/pipelines/{name}/train` triggers training; `GET /api/pipelines/{name}/status` returns progress.

### 3.2 FeatureStore

**Purpose**: Compute, version, store, and serve features. Point-in-time correct retrieval.

**Depends on**: DataFlow (storage), polars (computation)

**Key Methods**:
```python
class FeatureStore:
    def __init__(self, db: DataFlow):
        ...

    async def register_features(self, schema: FeatureSchema) -> None:
        """Register feature definitions. Creates DataFlow tables. Idempotent."""

    async def compute(self, raw_data: pl.DataFrame, schema: FeatureSchema) -> pl.DataFrame:
        """Compute features from raw data per schema."""

    async def get_features(self, entity_ids: list[str], feature_names: list[str],
                           as_of: datetime | None = None) -> pl.DataFrame:
        """Retrieve features, optionally point-in-time correct."""

    async def get_training_set(self, schema: FeatureSchema,
                                start: datetime, end: datetime) -> pl.DataFrame:
        """Retrieve materialized features for a training window."""

    def get_features_lazy(self, entity_ids, feature_names) -> pl.LazyFrame:
        """Returns LazyFrame for memory-bounded streaming."""
```

**DataFlow integration**: `register_features()` creates DataFlow model tables. Feature metadata stored in `_feature_metadata` DataFlow model.

**Point-in-time correctness**: `as_of` parameter filters to latest feature values before the given timestamp. Prevents future data leakage in training.

**Bulk write path**: Arrow-native path for >10K rows (avoids O(n*m) Python dict allocation from `to_dicts()`). Falls back to chunked `to_dicts()` only when DataFlow lacks Arrow bulk insert.

**Feature computation**: Schema defines feature functions as callables that accept a LazyFrame and return a LazyFrame:
```python
@dataclass
class FeatureDefinition:
    name: str
    polars_dtype: pl.DataType
    nullable: bool
    compute_fn: Callable[[pl.LazyFrame], pl.LazyFrame]
```

### 3.3 ModelRegistry

**Purpose**: Track model lifecycle -- staging, shadow, production, archived. Store metadata, metrics, artifact references.

**Depends on**: DataFlow (metadata), pluggable ArtifactStore (local filesystem in v1)

**Key Methods**:
```python
class ModelRegistry:
    def __init__(self, db: DataFlow, artifact_store: ArtifactStore | None = None):
        ...

    async def register(self, name: str, artifact: ModelArtifact,
                       metrics: dict, feature_schema: FeatureSchema) -> ModelVersion:
        """Register a new model version."""

    async def promote(self, name: str, version: str, stage: Stage) -> None:
        """Promote to staging/shadow/production."""

    async def load(self, name: str, version: str | None = None,
                   stage: Stage | None = None) -> Any:
        """Load model artifact. Default: latest production version."""

    async def compare(self, name: str, version_a: str, version_b: str) -> ComparisonResult:
        """Compare two model versions on metrics."""

    async def export_mlflow(self, name: str, version: str, path: Path):
        """Write MLflow MLmodel YAML (no mlflow import -- writes format directly)."""

    async def import_mlflow(self, mlflow_path: Path) -> ModelVersion:
        """Import from MLflow MLmodel YAML."""
```

**DataFlow models (auto-created)**:
- `MLModel`: id, name, description, owner, created_at
- `MLModelVersion`: id, model_id, version, stage, metrics_json, feature_schema_ref, artifact_path, onnx_path, onnx_status ("pending"/"success"/"failed"/"not_applicable"), created_at
- `MLModelTransition`: id, version_id, from_stage, to_stage, timestamp, reason

**MLflow format**: v1 writes/reads MLflow MLmodel YAML directly (no `import mlflow`). Metadata round-trips without data loss. W&B/Neptune in v1.1.

**ONNX status tracking**: When ONNX export fails, status is `"failed"` with error message. NOT a hard failure. Native Python inference still works.

### 3.4 InferenceServer

**Purpose**: Load models from registry, serve predictions, cache hot models, auto-expose via Nexus.

**Key Methods**:
```python
class InferenceServer:
    def __init__(self, registry: ModelRegistry, nexus: Nexus | None = None,
                 cache_size: int = 10):
        ...

    async def predict(self, model_name: str, features: dict | pl.DataFrame,
                      version: str | None = None) -> PredictionResult:
        """Predict. Default: latest production version."""

    async def predict_batch(self, model_name: str, features: pl.DataFrame) -> pl.DataFrame:
        """Batch prediction with predictions column appended."""

    async def warm_cache(self, model_names: list[str]) -> None:
        """Pre-load models into LRU cache."""

    def register_endpoints(self, nexus: Nexus) -> None:
        """Auto-register: POST /api/predict/{model_name}, GET .../health"""
```

**Model caching**: LRU cache of deserialized models. Configurable size. Eviction logged.

**ONNX path**: When a model has `onnx_status="success"`, uses `onnxruntime.InferenceSession`. When failed or unavailable, falls back to native Python. `PredictionResult.inference_mode` tells caller which path was used ("onnx" or "native").

**Input validation**: Features validated against `model_metadata.json` input_schema. Type mismatches return clear errors.

### 3.5 DriftMonitor

**Purpose**: Detect feature drift and model performance degradation.

**Key Methods**:
```python
class DriftMonitor:
    def __init__(self, inference_server: InferenceServer,
                 feature_store: FeatureStore, db: DataFlow):
        ...

    async def set_reference(self, model_name: str, reference_data: pl.DataFrame) -> None:
    async def check_drift(self, model_name: str, window=None) -> DriftReport:
    async def check_performance(self, model_name: str, actuals: pl.DataFrame) -> PerformanceReport:
    async def schedule_monitoring(self, model_name: str, interval: timedelta, drift_spec: DriftSpec) -> None:
```

**Statistical methods**:
- **PSI** (Population Stability Index): > 0.2 = significant drift (alert=True); 0.1-0.2 = moderate
- **KS test** (Kolmogorov-Smirnov): per-feature p-value; p < 0.05 = statistically significant shift

**DataFlow**: Drift reports stored in `MLDriftReport` model. Reference statistics in `MLDriftReference`.

**Scheduling**: v1 uses asyncio background task. v2 integrates with Nexus BackgroundService.

### 3.6 AutoMLEngine

**Purpose**: Automated model selection + hyperparameter optimization, optionally agent-augmented.

**Key Methods**:
```python
class AutoMLEngine:
    def __init__(self, pipeline: TrainingPipeline,
                 agent: AgentInfusionProtocol | None = None):
        ...

    async def run(self, data: pl.DataFrame, target: str,
                  task: TaskType, spec: ExperimentSpec) -> AutoMLResult:
    async def suggest_next(self, results: list[TrialResult]) -> list[TrialConfig]:
```

**ExperimentSpec**: `time_budget_sec`, `max_trials`, `search_strategy` ("bayesian"/"random"/"grid"), `success_criteria`, `max_llm_cost_usd` (default $1.00), `auto_approve` (default False), `require_baseline` (default True), `audit_trail` (default True).

**Pure algorithmic mode** (default): Profile data -> generate candidates -> cross-validation -> Bayesian optimization -> return best.

**Agent-augmented mode** (requires injection AND `auto_approve=False`): DataScientistAgent profiles, ModelSelectorAgent suggests, ExperimentInterpreterAgent interprets.

**5 guardrails implemented**: confidence scores, cost budget, human approval gate, baseline comparison, audit trail. See TSG-306 for full implementation details.

### 3.7 DataExplorer

**Purpose**: Statistical profiling, visualizations, optional natural-language narrative.

**Key Methods**:
```python
class DataExplorer:
    def __init__(self, agent: AgentInfusionProtocol | None = None):
        ...

    async def profile(self, data: pl.DataFrame, spec: ExplorerSpec | None = None) -> DataProfile:
    async def compare(self, data_a: pl.DataFrame, data_b: pl.DataFrame) -> ComparisonProfile:
```

**Depth modes**: "quick" (column stats only, <1s), "standard" (+ distribution plots, <5s), "deep" (+ anomaly detection + correlation pairs).

**DataProfile includes**: row/column count, per-column stats (dtype, null_pct, unique_count, mean/std/percentiles), correlation matrix (pl.DataFrame), anomaly flags, plotly Figures, narrative (empty without agent).

### 3.8 HyperparameterSearch

**Purpose**: Systematic hyperparameter optimization. Used by AutoML and standalone.

**Key Methods**:
```python
class HyperparameterSearch:
    def __init__(self, pipeline: TrainingPipeline):
        ...

    async def search(self, model_spec, search_space, data, eval_spec,
                     strategy="bayesian", budget=50) -> SearchResult:
```

**4 strategies**: "grid" (exhaustive), "random" (sampling), "bayesian" (GP surrogate + Expected Improvement, scipy-based), "halving" (successive halving -- eliminate bottom 50% each round).

**SearchSpace**: maps parameter names to `IntRange`, `FloatRange`, `Categorical`, `LogUniform`.

**SearchResult**: `best_params`, `best_score`, `all_trials`, `convergence_curve` (pl.DataFrame), `search_time_sec`.

### 3.9 FeatureEngineer

**Purpose**: Automated feature generation + selection, optionally agent-augmented.

**Key Methods**:
```python
class FeatureEngineer:
    def __init__(self, feature_store: FeatureStore,
                 agent: AgentInfusionProtocol | None = None):
        ...

    async def generate(self, data, target, spec) -> FeatureEngineeringResult:
    async def select(self, data, target, features, method="importance") -> list[str]:
```

**Algorithmic transforms**: `rolling_mean(window)`, `rolling_std(window)`, `lag(n)`, `diff(n)`, `poly(degree)`, `log`, `sqrt`, `interaction(col_a, col_b)`, `datetime_parts`.

**Selection methods**: "importance" (LightGBM feature_importances_), "mutual_info" (sklearn mutual_info_regression/classif), "correlation".

**5 guardrails**: identical pattern to AutoMLEngine via shared `AgentGuardrailMixin`.

---

## 4. Kaizen Agent Designs

All agents follow the LLM-first rule: reasoning via Signatures, tools are dumb data endpoints. Every agent emits `confidence: float` (Guardrail 1).

### 4.1 DataScientistAgent

```python
class DataScientistSignature(Signature):
    """Analyze a dataset and formulate an ML strategy."""
    data_profile: str = InputField(description="Statistical profile from DataExplorer")
    business_context: str = InputField(description="What problem is being solved", default="")
    constraints: str = InputField(description="Time, compute, or accuracy constraints", default="")

    data_assessment: str = OutputField(description="Data quality, volume, suitability assessment")
    recommended_approach: str = OutputField(description="Recommended ML approach with rationale")
    risks: str = OutputField(description="Data risks: leakage, bias, insufficient volume, class imbalance")
    feature_hypotheses: list[str] = OutputField(description="Hypotheses about useful features")
    preprocessing_plan: str = OutputField(description="Recommended preprocessing steps")
    confidence: float = OutputField(description="Confidence in this recommendation (0-1)")
```

**Tools**: `profile_data(dataset_ref)`, `get_column_stats(dataset_ref, column)`, `check_correlation(dataset_ref, col_a, col_b)`, `sample_rows(dataset_ref, n)`

### 4.2 FeatureEngineerAgent

```python
class FeatureEngineerSignature(Signature):
    """Design and evaluate features for an ML model."""
    data_profile: str = InputField(description="Statistical profile")
    target_description: str = InputField(description="What we are predicting")
    existing_features: list[str] = InputField(description="Features already created")
    model_performance: str = InputField(description="Current model metrics", default="")

    proposed_features: list[dict] = OutputField(description="List of {name, computation, rationale}")
    feature_interactions: list[str] = OutputField(description="Promising interactions to explore")
    features_to_drop: list[str] = OutputField(description="Features to remove with rationale")
    validation_plan: str = OutputField(description="How to validate feature quality")
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Tools**: `compute_feature(dataset_ref, expression)`, `check_target_correlation(dataset_ref, feature, target)`, `check_feature_drift(feature_name, reference, current)`, `get_feature_importance(model_ref)`

### 4.3 ModelSelectorAgent

```python
class ModelSelectorSignature(Signature):
    """Select candidate models for an ML task."""
    data_characteristics: str = InputField(description="Data profile summary")
    task_type: str = InputField(description="classification, regression, time_series, clustering")
    constraints: str = InputField(description="Latency, memory, interpretability requirements")
    previous_results: str = InputField(description="Prior experiment results", default="")

    candidate_models: list[dict] = OutputField(description="Ranked {model_type, rationale, hyperparameter_hints}")
    expected_performance: str = OutputField(description="Expected metric ranges")
    experiment_plan: str = OutputField(description="Order and strategy for evaluating candidates")
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Tools**: `list_available_trainers()`, `get_model_metadata(model_type)`, `estimate_training_time(model_type, data_size)`

### 4.4 ExperimentInterpreterAgent

```python
class ExperimentInterpreterSignature(Signature):
    """Interpret ML experiment results and recommend next steps."""
    experiment_results: str = InputField(description="All trial results: model, params, metrics")
    experiment_goal: str = InputField(description="What success looks like")
    data_context: str = InputField(description="Brief data description")

    interpretation: str = OutputField(description="What the results tell us")
    patterns: list[str] = OutputField(description="Patterns across trials")
    failure_analysis: str = OutputField(description="Why poor configs failed")
    recommendations: list[str] = OutputField(description="Specific next steps")
    confidence_assessment: str = OutputField(description="Confidence in best result")
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Tools**: `get_trial_details(trial_id)`, `compare_trials(trial_ids)`, `get_learning_curves(trial_id)`, `get_feature_importance(trial_id)`

### 4.5 DriftAnalystAgent

```python
class DriftAnalystSignature(Signature):
    """Analyze model drift and determine if action is needed."""
    drift_report: str = InputField(description="DriftMonitor output")
    historical_drift: str = InputField(description="Historical drift trends")
    model_performance: str = InputField(description="Current vs training metrics")
    domain_context: str = InputField(description="Domain info", default="")

    assessment: str = OutputField(description="Actionable, seasonal, or noise?")
    root_cause: str = OutputField(description="Likely cause of drift")
    impact: str = OutputField(description="Expected impact on predictions")
    recommendation: str = OutputField(description="retrain, monitor, investigate, or ignore")
    urgency: str = OutputField(description="immediate, soon, routine, none")
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Tools**: `get_drift_history(model_name, window)`, `get_feature_distribution(feature_name, period)`, `get_prediction_accuracy(model_name, window)`, `get_external_events(date_range)`

### 4.6 RetrainingDecisionAgent

```python
class RetrainingDecisionSignature(Signature):
    """Decide whether to retrain based on drift and performance."""
    drift_assessment: str = InputField(description="From DriftAnalystAgent")
    current_performance: str = InputField(description="Current accuracy metrics")
    training_cost: str = InputField(description="Estimated time and compute")
    business_impact: str = InputField(description="Cost of prediction errors", default="")

    decision: str = OutputField(description="retrain_now, schedule_retrain, continue_monitoring, or no_action")
    rationale: str = OutputField(description="Why this decision")
    retrain_spec: str = OutputField(description="Data window, features, hyperparameter changes")
    fallback_plan: str = OutputField(description="What to do if retraining fails")
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Tools**: `trigger_retraining(model_name, spec)`, `get_model_versions(model_name)`, `estimate_retrain_time(model_name, data_window)`, `rollback_model(model_name, version)`

---

## 5. polars Integration Patterns

### 5.1 Design Principle

kailash-ml NEVER converts to/from pandas internally. All engines accept and return `pl.DataFrame` or `pl.LazyFrame`.

```python
# Internal pattern: polars -> numpy at sklearn boundary
def _train_sklearn(self, model, features: pl.DataFrame, target: pl.Series):
    X = features.to_numpy()  # Conversion at the outermost boundary only
    y = target.to_numpy()
    model.fit(X, y)
    return model
```

### 5.2 Interop Module Functions

| Function | Input | Output | Notes |
|----------|-------|--------|-------|
| `to_sklearn_input(df)` | `pl.DataFrame` | `(np.ndarray, list[str], dict)` | Categorical -> integer codes; returns column_info for restoration |
| `from_sklearn_output(arr, cols)` | `np.ndarray, list[str]` | `pl.DataFrame` | Preserves column names |
| `to_lgb_dataset(df, label_col)` | `pl.DataFrame, str` | `lgb.Dataset` | Preserves categorical via `categorical_feature` param. ONE place where pandas is touched (LightGBM requires pandas for native categorical) |
| `to_hf_dataset(df)` | `pl.DataFrame` | `datasets.Dataset` | Via Arrow (zero-copy). Conditional import. |
| `polars_to_arrow(df)` | `pl.DataFrame` | `pa.Table` | With optional schema validation |
| `from_arrow(table)` | `pa.Table` | `pl.DataFrame` | Wraps `pl.from_arrow()` |

### 5.3 Benchmark Requirement

Before shipping, a benchmark must verify: `to_sklearn_input()` overhead < 15% of a 100K-row LightGBM train time. Results documented in `interop_benchmark.md`.

### 5.4 FeatureStore Write Path

For large feature tables (>10K rows), the write path must NOT use `to_dicts()` (which creates O(n*m) Python objects). Preferred: DataFlow Arrow bulk insert. Fallback: chunked writes (max 5000 rows per chunk).

---

## 6. ONNX Bridge Protocol

### 6.1 Flow

```
Python (kailash-ml)                    Rust (kailash-rs)
====================                    =================
Train model (sklearn/LightGBM/PyTorch)
    |
Export to ONNX
    |
Register in ModelRegistry
  (artifact_path, onnx_path,
   model_metadata.json)
    |                                   Read model_metadata.json
    +---- artifact store (S3/local) --> Load ONNX via ort crate
                                        |
                                    Serve predictions
                                    (sub-ms latency)
```

### 6.2 model_metadata.json Schema

```json
{
    "schema_version": "1.0.0",
    "model_name": "energy_price_predictor",
    "model_version": "2.3.1",
    "model_type": "LightGBMRegressor",
    "task_type": "regression",
    "framework": "lightgbm",
    "framework_version": "4.3.0",
    "input_schema": {
        "features": [
            {"name": "temperature", "dtype": "float64", "nullable": false},
            {"name": "hour_of_day", "dtype": "int32", "nullable": false}
        ],
        "arrow_schema_b64": "...(serialized Arrow schema for polars-rs zero-copy)"
    },
    "output_schema": {
        "predictions": [
            {"name": "price_prediction", "dtype": "float64"}
        ]
    },
    "artifacts": {
        "native": "model.lgb",
        "onnx": "model.onnx",
        "onnx_opset": 17,
        "onnx_ir_version": 9
    },
    "training_metrics": {
        "rmse": 12.45,
        "mae": 8.21,
        "r2": 0.89
    },
    "feature_schema_ref": "energy_features_v3",
    "lineage": {
        "training_data_hash": "sha256:abc123...",
        "feature_store_version": "3",
        "pipeline_version": "1.2.0"
    }
}
```

### 6.3 ONNX Export by Framework

| Framework | Export Method | v1 Guaranteed |
|-----------|-------------|---------------|
| scikit-learn | `skl2onnx.convert_sklearn()` | Yes (all estimators) |
| LightGBM | `onnxmltools.convert_lightgbm()` | Yes |
| XGBoost | `onnxmltools.convert_xgboost()` | Yes |
| PyTorch feedforward | `torch.onnx.export()` | Yes |
| PyTorch dynamic control flow | `torch.onnx.export()` | Best effort |
| CatBoost | `model.save_model(format="onnx")` | Yes |
| HuggingFace transformers | `optimum.exporters.onnx` | Best effort (requires [dl] + optimum) |

### 6.4 ONNX Fallback

When ONNX export fails:
1. Store native artifact only (Python inference works)
2. Mark model as `onnx_status: "failed"` with error message
3. InferenceServer serves via native Python path
4. Rust consumers get clear error: "Model X is not ONNX-compatible. Serve from Python."

### 6.5 ModelSerializer

```python
class ModelSerializer:
    async def save(self, model, path, formats=["native", "onnx"]) -> dict:
        """Save model in native + ONNX formats. Returns artifact paths."""

    async def load(self, path, format="native") -> Any:
        """Load model from artifact path."""

    async def validate_onnx(self, native_model, onnx_path,
                             test_data, tolerance=1e-5) -> bool:
        """Validate ONNX output matches native model within tolerance."""
```

### 6.6 Rust-Side Consumption

```rust
// kailash-rs/crates/kailash-ml/src/inference.rs
pub struct OnnxPredictor {
    session: Session,
    metadata: ModelMetadata,
}

impl OnnxPredictor {
    pub fn load(model_dir: &Path) -> Result<Self> { ... }
    pub fn predict(&self, features: &DataFrame) -> Result<DataFrame> {
        // polars DataFrame -> Arrow arrays -> ONNX inputs (zero-copy)
    }
}
```

---

## 7. Agent Guardrails (5 Mandatory)

All agent-augmented engines must implement these. Extracted into shared `AgentGuardrailMixin`.

### Guardrail 1: Confidence Scores
Every agent recommendation includes `confidence: float` (0-1). Logged to audit trail. Recommendations with confidence < 0.5 flagged.

### Guardrail 2: Cost Budget
`max_llm_cost_usd` parameter (default $1.00). When cumulative LLM API cost reaches limit, engine falls back to pure algorithmic mode. Cost tracked via token counts.

### Guardrail 3: Human Approval Gate
`auto_approve=False` default. Agent proposes, human confirms. `approve(suggestion_id)` or `reject(suggestion_id)` API.

### Guardrail 4: Baseline Comparison
Every agent-augmented run also executes pure algorithmic baseline (LightGBM default settings). Result shows both for comparison.

### Guardrail 5: Audit Trail
All agent decisions logged to DataFlow `MLAgentAuditLog`: timestamp, agent_name, input_summary, output_summary, confidence, llm_cost_usd, approved_by.

---

## 8. Testing Strategy

### 8.1 Test Tier Model

| Tier | Focus | Infrastructure | Speed | When |
|------|-------|---------------|-------|------|
| Tier 0: Regression | Bug reproduction | In-memory | <1s | Every commit |
| Tier 1: Unit | Engine logic, schema validation, serialization | Mocked models, in-memory DataFlow | <5s | Every commit |
| Tier 2: Integration | Engine-to-engine flows, DataFlow storage, Nexus endpoints | Real DataFlow (SQLite), real models (tiny) | <30s | Every PR |
| Tier 3: ML Validation | Model quality, convergence, ONNX fidelity | Real models, real data subsets | <5min | Nightly/release |
| Tier 4: GPU | CUDA training, mixed precision, distributed | Real GPU | <10min | Weekly/pre-release |

### 8.2 Determinism Strategy

Seed everything for Tier 0-2:
```python
@pytest.fixture
def deterministic():
    import random, numpy as np, torch
    seed = 42
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
    pl.set_random_seed(seed)
```

For Tier 3-4 where exact reproducibility is impossible, use statistical assertions:
```python
def assert_model_quality(metrics, thresholds, tolerance=0.05):
    for metric, threshold in thresholds.items():
        assert metrics[metric] >= threshold - tolerance
```

### 8.3 Tiny Models for Fast Tests

```python
TINY_LIGHTGBM = {"n_estimators": 5, "max_depth": 3, "num_leaves": 8}
TINY_MLP = {"hidden_sizes": [8, 4], "epochs": 2, "batch_size": 32}
```

---

## 9. Failure Mode Catalog

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| FM-01 | GPU OOM during training | Critical | Auto-detect VRAM, adjust batch size, Lightning gradient accumulation |
| FM-02 | Model divergence (NaN/Inf loss) | Critical | Monitor loss per epoch, auto-stop on NaN, gradient clipping default on |
| FM-03 | Feature drift undetected | Critical | DriftMonitor scheduled by default, PSI + KS dual metric |
| FM-04 | Schema evolution breaks inference | Critical | FeatureSchema versioned, input validation against model_metadata.json |
| FM-05 | PyTorch/CUDA version conflict | Major | Document compatibility matrix, provide gpu-setup CLI |
| FM-06 | ONNX export fidelity loss | Major | Mandatory validate_onnx(), configurable tolerance, graceful fallback |
| FM-07 | FeatureStore point-in-time error | Major | Unit tests with known temporal data, explicit as_of parameter |
| FM-08 | DataFlow table bloat | Significant | TTL-based cleanup, configurable retention |
| FM-09 | Circular import | Critical | Protocol package breaks cycle, runtime discovery |
| FM-10 | polars blocks pandas users | Significant | `kailash_ml.interop.from_pandas()` one-liner |
| FM-11 | AutoML runaway compute | Significant | Mandatory time_budget_seconds + max_trials, hard limits |
| FM-12 | Registry metadata inconsistency | Major | DataFlow transactions, atomic version+stage transitions |
| FM-13 | Stale model after promotion | Major | Registry event subscription, cache invalidation |
| FM-14 | ONNX opset incompatibility | Major | model_metadata.json specifies opset, Rust loader validates |
| FM-15 | Agent hallucination in AutoML | Significant | Agents suggest, engines verify. All evaluated by actual training+CV |
