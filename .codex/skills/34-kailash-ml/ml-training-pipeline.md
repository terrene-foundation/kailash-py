# ML Training Pipeline

`TrainingPipeline` orchestrates schema-driven model training with FeatureStore +
ModelRegistry, polars-native data, hyperparameter search, and experiment tracking.

## Basic Training

```python
from kailash_ml import TrainingPipeline
from kailash_ml.engines.training_pipeline import ModelSpec, EvalSpec
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
from kailash_ml.engines.feature_store import FeatureStore  # legacy write surface
from kailash_ml.types import FeatureSchema, FeatureField
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()

# ModelRegistry is ready on construction (no initialize()).
registry = ModelRegistry(conn, LocalFileArtifactStore("./artifacts"))

pipeline = TrainingPipeline(feature_store=fs, registry=registry)
```

## Schema-Driven Training

`FeatureSchema` declares inputs, entity key, and timestamp. The training target is
an ordinary feature column named in the data — the schema has no `target` field.

```python
schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
        FeatureField(name="monthly_spend", dtype="float"),
        FeatureField(name="churned", dtype="int"),  # the target column
    ],
    entity_id_column="user_id",
)

# train(data, schema, model_spec, eval_spec, experiment_name)
result = await pipeline.train(
    training_df,
    schema,
    ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    EvalSpec(metrics=["accuracy", "f1", "precision", "recall"]),
    experiment_name="user_churn",
)

# result.metrics — {"accuracy": 0.92, "f1": 0.87, ...}
# result.device  — resolved backend/device report
```

## Model Spec Options

`ModelSpec(model_class, hyperparameters={}, framework="sklearn")` — pass tuned
values via `hyperparameters=`.

```python
ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier")
ModelSpec(model_class="sklearn.linear_model.LogisticRegression")
ModelSpec(model_class="lightgbm.LGBMClassifier")
ModelSpec(model_class="xgboost.XGBClassifier")
ModelSpec(model_class="catboost.CatBoostClassifier")

# With hyperparameters
ModelSpec(
    model_class="sklearn.ensemble.RandomForestClassifier",
    hyperparameters={"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 5},
)
```

**Model class allowlist**: Only `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`,
`kailash_ml.`, `torch.`, `lightning.` prefixes are permitted — preventing arbitrary
code execution via model class strings.

## Hyperparameter Search

One engine, `HyperparameterSearch`, runs every strategy — selected via
`SearchConfig(strategy=...)`. The space is a `SearchSpace` of `ParamDistribution`s.

```python
from kailash_ml.engines.hyperparameter_search import (
    HyperparameterSearch,
    SearchConfig,
    SearchSpace,
    ParamDistribution,
)

space = SearchSpace(params=[
    ParamDistribution(name="n_estimators", type="int_uniform", low=100, high=1000),
    ParamDistribution(name="max_depth", type="int_uniform", low=3, high=30),
    ParamDistribution(name="learning_rate", type="log_uniform", low=0.001, high=0.3),
])

search = HyperparameterSearch(pipeline)

# strategy selects grid / random / bayesian / successive-halving behaviour.
result = await search.search(
    training_df,
    schema,
    ModelSpec(model_class="sklearn.ensemble.GradientBoostingClassifier"),
    space,
    SearchConfig(strategy="bayesian", n_trials=100, metric_to_optimize="f1", direction="maximize"),
    EvalSpec(metrics=["accuracy", "f1"]),
    experiment_name="user_churn_hpo",
)
# result.best_params / result.best_metrics / result.all_trials / result.model_version
```

For a grid sweep use `SearchConfig(strategy="grid")`; for random,
`SearchConfig(strategy="random", n_trials=50)`. Categorical axes use
`ParamDistribution(name=..., type="categorical", choices=[...])`.

## Experiment Tracking

Pass an `ExperimentTracker` into `train(tracker=...)`; every run is recorded.

```python
from kailash_ml.engines.experiment_tracker import ExperimentTracker

tracker = ExperimentTracker(conn, artifact_root="./artifacts")

result = await pipeline.train(
    training_df, schema,
    ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    EvalSpec(metrics=["accuracy", "f1"]),
    experiment_name="user_churn",
    tracker=tracker,
)

# Query runs
runs = await tracker.list_runs("user_churn")

# Best run by a metric (order_by on search_runs; there is no get_best_run helper)
best = await tracker.search_runs("user_churn", order_by="metrics.f1 DESC", max_results=1)

# Compare specific runs
comparison = await tracker.compare_runs([r.run_id for r in runs[:3]])
```

## Storage Backend

Artifacts (models, metrics, schemas) persist via `ConnectionManager`, dialect-portable
across SQLite, PostgreSQL, and MySQL.

```python
conn = ConnectionManager("sqlite:///ml.db")                   # development
conn = ConnectionManager("postgresql://user:pass@host/mldb")  # production
# Same pipeline code — ConnectionManager handles dialect differences.
```

## Evaluation Spec

`EvalSpec(metrics, split_strategy="holdout", n_splits=5, test_size=0.2, min_threshold={})`.

```python
# Classification metrics
EvalSpec(metrics=["accuracy", "f1", "precision", "recall", "roc_auc"])

# Regression metrics
EvalSpec(metrics=["rmse", "mae", "r2", "mape"])

# Cross-validation (k-fold)
EvalSpec(metrics=["accuracy", "f1"], split_strategy="cv", n_splits=5)

# Custom holdout split
EvalSpec(metrics=["accuracy"], split_strategy="holdout", test_size=0.2)

# Gate registration on a metric floor
EvalSpec(metrics=["accuracy", "f1"], min_threshold={"f1": 0.8})
```

## Critical Rules

- Schema drives inputs; the target is a feature column, not a schema field
- `train(data, schema, model_spec, eval_spec, experiment_name)` — data is required
- Model class strings validated against the allowlist before import
- All data in polars — conversion at the sklearn boundary via `interop.py`
- One `HyperparameterSearch` engine; `SearchConfig(strategy=...)` selects the method
- Pass the tracker via `train(tracker=...)`, not the pipeline constructor
