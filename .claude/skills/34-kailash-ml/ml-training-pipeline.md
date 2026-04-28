# ML Training Pipeline

TrainingPipeline orchestrates schema-driven model training with FeatureStore integration, DataFlow storage backend, hyperparameter search, and experiment tracking.

## Basic Training

```python
from kailash_ml import TrainingPipeline, ModelRegistry, ModelSpec, EvalSpec
from kailash_ml.engines import LocalFileArtifactStore
from kailash_ml.types import FeatureSchema, FeatureField
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
```

## Schema-Driven Training

The pipeline uses FeatureSchema to determine inputs, target, and data types. No manual column selection.

```python
schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
        FeatureField(name="monthly_spend", dtype="float"),
    ],
    target=FeatureField(name="churned", dtype="int"),
)

result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1", "precision", "recall"]),
)

# result.model_id      — registered in ModelRegistry (staging)
# result.metrics        — {"accuracy": 0.92, "f1": 0.87, ...}
# result.training_time  — duration in seconds
# result.experiment_id  — linked to ExperimentTracker
```

## Model Spec Options

```python
# sklearn models
ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier")
ModelSpec(model_class="sklearn.linear_model.LogisticRegression")
ModelSpec(model_class="sklearn.ensemble.GradientBoostingClassifier")

# LightGBM
ModelSpec(model_class="lightgbm.LGBMClassifier")

# XGBoost (requires kailash-ml[xgb])
ModelSpec(model_class="xgboost.XGBClassifier")

# CatBoost (requires kailash-ml[catboost])
ModelSpec(model_class="catboost.CatBoostClassifier")

# With hyperparameters
ModelSpec(
    model_class="sklearn.ensemble.RandomForestClassifier",
    params={"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 5},
)
```

**Model class allowlist**: Only `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.` prefixes are permitted. This prevents arbitrary code execution via model class strings.

## FeatureStore Integration

TrainingPipeline pulls data directly from FeatureStore, preserving point-in-time correctness.

```python
# Train from FeatureStore (recommended)
result = await pipeline.train(
    schema=schema,
    feature_set="user_features",    # Pull from FeatureStore
    as_of="2025-01-01T00:00:00",   # Point-in-time correctness
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)

# Train from DataFrame (when data is already prepared)
result = await pipeline.train(
    schema=schema,
    data=training_df,               # polars DataFrame
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)
```

## Hyperparameter Search

Four search strategies, all integrated with ExperimentTracker.

### Grid Search

```python
from kailash_ml.engines.hyperparameter_search import GridSearch

search = GridSearch(
    param_grid={
        "n_estimators": [100, 200, 500],
        "max_depth": [5, 10, 20],
        "min_samples_leaf": [1, 5, 10],
    },
)

result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"], optimize="f1"),
    search=search,
)
# Trains 27 combinations, registers best model
```

### Random Search

```python
from kailash_ml.engines.hyperparameter_search import RandomSearch

search = RandomSearch(
    param_distributions={
        "n_estimators": (100, 1000),       # Uniform int range
        "max_depth": (3, 30),
        "learning_rate": (0.001, 0.3),     # Uniform float range
    },
    n_trials=50,
)
```

### Bayesian Search

```python
from kailash_ml.engines.hyperparameter_search import BayesianSearch

search = BayesianSearch(
    param_space={
        "n_estimators": (100, 1000),
        "max_depth": (3, 30),
        "learning_rate": (0.001, 0.3),
    },
    n_trials=100,
    acquisition_function="expected_improvement",
)
```

### Successive Halving

Early-stops poorly performing configurations to focus budget on promising ones.

```python
from kailash_ml.engines.hyperparameter_search import SuccessiveHalving

search = SuccessiveHalving(
    param_distributions={
        "n_estimators": (100, 1000),
        "max_depth": (3, 30),
    },
    n_candidates=81,    # Start with 81 candidates
    reduction_factor=3, # Keep top 1/3 each round
)
```

## Experiment Tracking

Every training run is logged to ExperimentTracker, which is MLflow-compatible.

```python
from kailash_ml.engines import ExperimentTracker

tracker = ExperimentTracker(conn)
await tracker.initialize()

# Automatic tracking via pipeline (default)
pipeline = TrainingPipeline(
    feature_store=fs,
    model_registry=registry,
    experiment_tracker=tracker,
)

# Query experiments
runs = await tracker.list_runs(experiment_name="user_churn")
best_run = await tracker.get_best_run(
    experiment_name="user_churn",
    metric="f1",
    direction="maximize",
)

# Compare runs
comparison = await tracker.compare_runs(
    run_ids=["run_001", "run_002", "run_003"],
    metrics=["accuracy", "f1", "training_time"],
)
```

## DataFlow Storage Backend

Training artifacts (models, metrics, schemas) are stored via DataFlow's ConnectionManager. This provides dialect-portable storage across SQLite, PostgreSQL, and MySQL.

```python
# SQLite for development
conn = ConnectionManager("sqlite:///ml.db")

# PostgreSQL for production
conn = ConnectionManager("postgresql://user:pass@host/mldb")

# Same pipeline code works with both — DataFlow handles dialect differences
pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
```

## Evaluation Spec

```python
# Classification metrics
EvalSpec(metrics=["accuracy", "f1", "precision", "recall", "roc_auc"])

# Regression metrics
EvalSpec(metrics=["rmse", "mae", "r2", "mape"])

# Cross-validation
EvalSpec(metrics=["accuracy", "f1"], cv_folds=5)

# Optimize specific metric (for hyperparameter search)
EvalSpec(metrics=["accuracy", "f1"], optimize="f1")

# Custom train/test split ratio
EvalSpec(metrics=["accuracy"], test_size=0.2, random_state=42)
```

## Critical Rules

- Schema drives everything — no manual column selection
- Model class strings validated against allowlist before import
- All data in polars — conversion at sklearn boundary via `interop.py`
- Every training run tracked in ExperimentTracker
- Trained models auto-registered in ModelRegistry at `staging` stage
- Point-in-time correctness when pulling from FeatureStore
