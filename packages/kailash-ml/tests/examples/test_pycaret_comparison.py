# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Side-by-side comparison: kailash-ml covers the full ML lifecycle
that would otherwise require PyCaret + MLflow.

Every section shows the kailash-ml API alongside a comment indicating
the PyCaret or MLflow equivalent.  The test exercises real models,
real SQLite, and real data -- nothing is mocked.

Run with:
    uv run pytest packages/kailash-ml/tests/examples/test_pycaret_comparison.py -v
"""
from __future__ import annotations

import pickle
import warnings

import numpy as np
import polars as pl
import pytest
from kailash_ml.engines.automl_engine import AutoMLConfig, AutoMLEngine, AutoMLResult
from kailash_ml.engines.data_explorer import DataExplorer, DataProfile
from kailash_ml.engines.drift_monitor import DriftMonitor, DriftReport
from kailash_ml.engines.ensemble import BlendResult, EnsembleEngine, StackResult
from kailash_ml.engines.experiment_tracker import ExperimentTracker
from kailash_ml.engines.feature_engineer import FeatureEngineer, GeneratedFeatures
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.hyperparameter_search import (
    HyperparameterSearch,
    ParamDistribution,
    SearchConfig,
    SearchResult,
    SearchSpace,
)
from kailash_ml.engines.inference_server import InferenceServer, PredictionResult
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.engines.preprocessing import PreprocessingPipeline, SetupResult
from kailash_ml.engines.training_pipeline import (
    EvalSpec,
    ModelSpec,
    TrainingPipeline,
    TrainingResult,
)
from kailash_ml.interop import to_sklearn_input
from kailash_ml.types import FeatureField, FeatureSchema, MetricSpec, ModelSignature
from sklearn.datasets import make_classification
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from kailash.db.connection import ConnectionManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager -- no mocking."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def feature_store(conn: ConnectionManager) -> FeatureStore:
    fs = FeatureStore(conn)
    await fs.initialize()
    return fs


@pytest.fixture
async def registry(conn: ConnectionManager, tmp_path) -> ModelRegistry:
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    return ModelRegistry(conn, artifact_store=store)


@pytest.fixture
def pipeline(feature_store: FeatureStore, registry: ModelRegistry) -> TrainingPipeline:
    return TrainingPipeline(feature_store, registry)


@pytest.fixture
async def tracker(conn: ConnectionManager, tmp_path) -> ExperimentTracker:
    return ExperimentTracker(conn, artifact_root=str(tmp_path / "mlartifacts"))


@pytest.fixture
async def drift_monitor(conn: ConnectionManager) -> DriftMonitor:
    return DriftMonitor(conn, tenant_id="test")


@pytest.fixture
def schema() -> FeatureSchema:
    """FeatureSchema matching the synthetic dataset."""
    return FeatureSchema(
        name="binary_classification",
        features=[
            FeatureField("feat_0", "float64"),
            FeatureField("feat_1", "float64"),
            FeatureField("feat_2", "float64"),
            FeatureField("feat_3", "float64"),
            FeatureField("feat_4", "float64"),
            FeatureField("feat_5", "float64"),
            FeatureField("feat_6", "float64"),
            FeatureField("feat_7", "float64"),
            FeatureField("feat_8", "float64"),
            FeatureField("feat_9", "float64"),
        ],
        entity_id_column="entity_id",
    )


@pytest.fixture
def data() -> pl.DataFrame:
    """Synthetic binary classification dataset via sklearn.datasets.

    500 samples, 10 features, 5 informative, reproducible seed.
    """
    X, y = make_classification(
        n_samples=500,
        n_features=10,
        n_informative=5,
        n_redundant=2,
        n_clusters_per_class=1,
        random_state=42,
    )
    columns = {f"feat_{i}": X[:, i].tolist() for i in range(10)}
    columns["entity_id"] = [f"e{i}" for i in range(500)]
    columns["target"] = y.tolist()
    return pl.DataFrame(columns)


# ---------------------------------------------------------------------------
# 1. Data Exploration -- PyCaret: pycaret.eda()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_01_data_exploration(data: pl.DataFrame) -> None:
    """Profile the dataset before training.

    PyCaret equivalent:
        from pycaret.classification import setup
        setup(data, target='target')  # prints profiling info
        # or: from pycaret.eda import dashboard
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        explorer = DataExplorer()
    feature_cols = [f"feat_{i}" for i in range(10)]
    profile: DataProfile = await explorer.profile(
        data, columns=feature_cols + ["target"]
    )

    # Verify profiling outputs
    assert profile.n_rows == 500
    assert profile.n_columns == 11
    assert len(profile.columns) == 11

    # Check numeric stats exist
    for col_profile in profile.columns:
        if col_profile.dtype.startswith("Float") or col_profile.dtype.startswith("Int"):
            assert col_profile.mean is not None
            assert col_profile.std is not None
            assert col_profile.null_count == 0

    # Correlation matrix covers all numeric features
    assert profile.correlation_matrix is not None
    assert "feat_0" in profile.correlation_matrix
    assert "feat_9" in profile.correlation_matrix


# ---------------------------------------------------------------------------
# 2. Preprocessing -- PyCaret: setup()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_02_preprocessing_setup(data: pl.DataFrame) -> None:
    """Auto-detect task type, scale numerics, split train/test.

    PyCaret equivalent:
        from pycaret.classification import setup
        s = setup(data, target='target', normalize=True, train_size=0.8)
    """
    pipeline = PreprocessingPipeline()
    result: SetupResult = pipeline.setup(
        data,
        target="target",
        train_size=0.8,
        normalize=True,
        imputation_strategy="mean",
        seed=42,
    )

    assert result.task_type == "classification"
    assert result.original_shape == (500, 12)
    assert result.train_data.height > 0
    assert result.test_data.height > 0
    assert result.train_data.height + result.test_data.height == 500
    assert len(result.numeric_columns) > 0
    assert "target" == result.target_column

    # Transformers were fitted
    assert result.transformers is not None

    # Transform new data using the fitted pipeline (inference time)
    new_row = pl.DataFrame(
        {
            "entity_id": ["new_1"],
            **{f"feat_{i}": [0.5] for i in range(10)},
            "target": [0],
        }
    )
    transformed = pipeline.transform(new_row)
    assert transformed.height == 1


# ---------------------------------------------------------------------------
# 3. Feature Engineering -- PyCaret: create_feature() / feature interactions
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_03_feature_engineering(data: pl.DataFrame, schema: FeatureSchema) -> None:
    """Generate and select features automatically.

    PyCaret equivalent:
        setup(data, feature_interaction=True, polynomial_features=True)
        # PyCaret handles this inside setup(); kailash-ml gives explicit control.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        engineer = FeatureEngineer(max_features=20)

    # Generate candidate features: interactions + polynomial
    generated: GeneratedFeatures = engineer.generate(
        data,
        schema,
        strategies=["interactions", "polynomial"],
    )

    assert len(generated.generated_columns) > 0
    assert generated.total_candidates > len(schema.features)
    assert generated.data.width > data.width

    # Select best features using tree-based importance
    selected = engineer.select(
        generated.data,
        generated,
        target="target",
        method="importance",
        top_k=10,
    )

    assert len(selected.selected_columns) == 10
    assert len(selected.rankings) > 0
    assert selected.rankings[0].rank == 1
    assert selected.n_selected == 10


# ---------------------------------------------------------------------------
# 4. Model Training (manual multi-model) -- PyCaret: compare_models()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_04_multi_model_training(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    data: pl.DataFrame,
    schema: FeatureSchema,
) -> None:
    """Train multiple model families and compare.

    PyCaret equivalent:
        from pycaret.classification import compare_models
        best = compare_models(n_select=3)
    """
    eval_spec = EvalSpec(
        metrics=["accuracy", "f1"],
        min_threshold={"accuracy": 0.5},
    )

    model_specs = [
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 20, "random_state": 42},
        ),
        ModelSpec(
            "sklearn.ensemble.GradientBoostingClassifier",
            {"n_estimators": 20, "random_state": 42},
        ),
        ModelSpec(
            "sklearn.linear_model.LogisticRegression",
            {"max_iter": 200, "random_state": 42},
        ),
    ]

    results: list[TrainingResult] = []
    for i, spec in enumerate(model_specs):
        result = await pipeline.train(
            data,
            schema,
            spec,
            eval_spec,
            f"compare_models_{i}",
        )
        results.append(result)

    # All models should have trained successfully
    assert all(r.registered for r in results)
    assert all(r.threshold_met for r in results)
    assert all(r.metrics["accuracy"] > 0.5 for r in results)

    # Rank by accuracy (PyCaret: compare_models returns sorted leaderboard)
    ranked = sorted(results, key=lambda r: r.metrics["accuracy"], reverse=True)
    assert ranked[0].metrics["accuracy"] >= ranked[-1].metrics["accuracy"]


# ---------------------------------------------------------------------------
# 5. AutoML Model Comparison -- PyCaret: compare_models() full automation
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_05_automl_comparison(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    data: pl.DataFrame,
    schema: FeatureSchema,
) -> None:
    """Fully automated model selection via AutoMLEngine.

    PyCaret equivalent:
        from pycaret.classification import compare_models, tune_model
        best = compare_models()  # trains all families, returns best
    """
    hp_search = HyperparameterSearch(pipeline)
    automl = AutoMLEngine(pipeline, hp_search, registry=registry)

    config = AutoMLConfig(
        task_type="classification",
        metric_to_optimize="accuracy",
        direction="maximize",
        search_strategy="random",
        search_n_trials=3,  # Small for test speed
        register_best=False,
    )

    eval_spec = EvalSpec(
        metrics=["accuracy", "f1"],
        min_threshold={"accuracy": 0.3},
    )

    result: AutoMLResult = await automl.run(
        data,
        schema,
        config,
        eval_spec,
        "automl_experiment",
    )

    # AutoML evaluated multiple candidates
    assert len(result.all_candidates) >= 2
    assert result.best_model is not None
    assert result.best_model.rank == 1
    assert result.best_metrics.get("accuracy", 0) > 0.3

    # Baseline recommendation was computed (Guardrail 4)
    assert len(result.baseline_recommendation) > 0


# ---------------------------------------------------------------------------
# 6. Hyperparameter Tuning -- PyCaret: tune_model()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_06_hyperparameter_tuning(
    pipeline: TrainingPipeline,
    data: pl.DataFrame,
    schema: FeatureSchema,
) -> None:
    """Hyperparameter search with random strategy.

    PyCaret equivalent:
        from pycaret.classification import tune_model
        tuned_rf = tune_model(rf, n_iter=10, optimize='accuracy')
    """
    hp_search = HyperparameterSearch(pipeline)

    base_spec = ModelSpec(
        "sklearn.ensemble.RandomForestClassifier",
        {"random_state": 42},
    )

    search_space = SearchSpace(
        [
            ParamDistribution("n_estimators", "int_uniform", low=5, high=50),
            ParamDistribution("max_depth", "int_uniform", low=2, high=10),
        ]
    )

    search_config = SearchConfig(
        strategy="random",
        n_trials=5,
        metric_to_optimize="accuracy",
        direction="maximize",
        register_best=False,
    )

    eval_spec = EvalSpec(
        metrics=["accuracy", "f1"],
        min_threshold={"accuracy": 0.3},
    )

    result: SearchResult = await hp_search.search(
        data,
        schema,
        base_spec,
        search_space,
        search_config,
        eval_spec,
        "hp_search_rf",
    )

    assert len(result.all_trials) == 5
    assert result.best_params is not None
    assert "n_estimators" in result.best_params
    assert result.best_metrics["accuracy"] > 0.3
    assert result.strategy == "random"
    assert result.total_time_seconds > 0


# ---------------------------------------------------------------------------
# 7. Ensemble Methods -- PyCaret: blend_models(), stack_models()
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_07_ensemble_blend(data: pl.DataFrame) -> None:
    """Blend multiple fitted models via soft voting.

    PyCaret equivalent:
        from pycaret.classification import blend_models
        blended = blend_models([rf, gb, lr], method='soft')
    """
    feature_cols = [f"feat_{i}" for i in range(10)]
    X, y, _ = to_sklearn_input(
        data, feature_columns=feature_cols, target_column="target"
    )

    # Fit individual models
    rf = RandomForestClassifier(n_estimators=20, random_state=42)
    gb = GradientBoostingClassifier(n_estimators=20, random_state=42)
    lr = LogisticRegression(max_iter=200, random_state=42)
    rf.fit(X, y)
    gb.fit(X, y)
    lr.fit(X, y)

    # Drop non-numeric columns before passing to ensemble (entity_id is String)
    numeric_data = data.drop("entity_id")

    engine = EnsembleEngine()
    result: BlendResult = engine.blend(
        [rf, gb, lr],
        numeric_data,
        target="target",
        method="soft",
        seed=42,
    )

    assert result.n_models == 3
    assert result.method == "soft"
    assert result.metrics["accuracy"] > 0.5
    assert len(result.weights) == 3
    assert len(result.component_contributions) == 3
    assert result.ensemble_model is not None


@pytest.mark.integration
def test_07_ensemble_stack(data: pl.DataFrame) -> None:
    """Stack models with a meta-learner.

    PyCaret equivalent:
        from pycaret.classification import stack_models
        stacked = stack_models([rf, gb], meta_model=lr)
    """
    feature_cols = [f"feat_{i}" for i in range(10)]
    X, y, _ = to_sklearn_input(
        data, feature_columns=feature_cols, target_column="target"
    )

    rf = RandomForestClassifier(n_estimators=20, random_state=42)
    gb = GradientBoostingClassifier(n_estimators=20, random_state=42)
    rf.fit(X, y)
    gb.fit(X, y)

    # Drop non-numeric columns before passing to ensemble (entity_id is String)
    numeric_data = data.drop("entity_id")

    engine = EnsembleEngine()
    result: StackResult = engine.stack(
        [rf, gb],
        numeric_data,
        target="target",
        meta_model_class="sklearn.linear_model.LogisticRegression",
        fold=3,
        seed=42,
    )

    assert result.n_base_models == 2
    assert result.meta_model_class == "sklearn.linear_model.LogisticRegression"
    assert result.metrics["accuracy"] > 0.5
    assert result.fold == 3
    assert result.ensemble_model is not None


# ---------------------------------------------------------------------------
# 8. Experiment Tracking -- MLflow: mlflow.start_run(), log_param, log_metric
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_08_experiment_tracking(
    tracker: ExperimentTracker,
) -> None:
    """Full experiment tracking lifecycle.

    MLflow equivalent:
        import mlflow
        mlflow.set_experiment("churn_prediction")
        with mlflow.start_run(run_name="rf_baseline") as run:
            mlflow.log_params({"n_estimators": "100", "max_depth": "10"})
            mlflow.log_metrics({"accuracy": 0.92, "f1": 0.89})
            mlflow.log_metric("loss", 0.3, step=0)
            mlflow.log_metric("loss", 0.1, step=1)
    """
    # Create experiment (MLflow: mlflow.set_experiment)
    exp_id = await tracker.create_experiment(
        "churn_prediction",
        description="Binary classification for customer churn",
        tags={"team": "data-science", "version": "v1"},
    )
    assert exp_id is not None

    # Start a run (MLflow: mlflow.start_run)
    async with tracker.run("churn_prediction", run_name="rf_baseline") as ctx:
        # Log parameters (MLflow: mlflow.log_params)
        await ctx.log_params(
            {
                "model_class": "RandomForestClassifier",
                "n_estimators": "100",
                "max_depth": "10",
            }
        )

        # Log metrics (MLflow: mlflow.log_metrics)
        await ctx.log_metrics({"accuracy": 0.92, "f1": 0.89}, step=0)

        # Log step-based metrics for training curves (MLflow: mlflow.log_metric)
        await ctx.log_metric("loss", 0.5, step=0)
        await ctx.log_metric("loss", 0.3, step=1)
        await ctx.log_metric("loss", 0.1, step=2)

        run_id = ctx.run_id

    # Verify run completed
    run = await tracker.get_run(run_id)
    assert run.status == "COMPLETED"
    assert run.params["n_estimators"] == "100"
    assert run.metrics["accuracy"] == 0.92
    assert run.metrics["f1"] == 0.89

    # Get metric history (MLflow: mlflow.tracking.MlflowClient().get_metric_history)
    loss_history = await tracker.get_metric_history(run_id, "loss")
    assert len(loss_history) == 3
    assert loss_history[0].value == 0.5
    assert loss_history[2].value == 0.1

    # Start a second run for comparison
    async with tracker.run("churn_prediction", run_name="gb_tuned") as ctx2:
        await ctx2.log_params(
            {
                "model_class": "GradientBoostingClassifier",
                "n_estimators": "200",
                "learning_rate": "0.05",
            }
        )
        await ctx2.log_metrics({"accuracy": 0.94, "f1": 0.91})
        run_id_2 = ctx2.run_id

    # Compare runs (MLflow: mlflow.search_runs or MlflowClient)
    comparison = await tracker.compare_runs([run_id, run_id_2])
    assert len(comparison.run_ids) == 2
    assert "accuracy" in comparison.metrics
    assert comparison.metrics["accuracy"][0] == 0.92
    assert comparison.metrics["accuracy"][1] == 0.94

    # List all runs (MLflow: mlflow.search_runs)
    all_runs = await tracker.list_runs("churn_prediction")
    assert len(all_runs) == 2

    # Search runs by params (MLflow: mlflow.search_runs with filter_string)
    filtered = await tracker.search_runs(
        "churn_prediction",
        filter_params={"model_class": "GradientBoostingClassifier"},
    )
    assert len(filtered) == 1
    assert filtered[0].params["model_class"] == "GradientBoostingClassifier"


# ---------------------------------------------------------------------------
# 9. Model Registry -- PyCaret: save_model/load_model, MLflow Model Registry
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_09_model_registry(
    registry: ModelRegistry,
    schema: FeatureSchema,
    tmp_path,
) -> None:
    """Model versioning and lifecycle management.

    PyCaret equivalent:
        from pycaret.classification import save_model, load_model
        save_model(best_model, 'my_model')
        loaded = load_model('my_model')

    MLflow equivalent:
        mlflow.sklearn.log_model(model, "model")
        client.transition_model_version_stage("my_model", 1, "Production")
    """
    # Train and serialize a model
    rf = RandomForestClassifier(n_estimators=20, random_state=42)
    rf.fit([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]] * 50, [0, 1] * 25)
    artifact_bytes = pickle.dumps(rf)

    signature = ModelSignature(
        input_schema=schema,
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )

    # Register v1 (MLflow: mlflow.register_model)
    v1 = await registry.register_model(
        "churn_model",
        artifact_bytes,
        metrics=[MetricSpec("accuracy", 0.92), MetricSpec("f1", 0.89)],
        signature=signature,
    )
    assert v1.version == 1
    assert v1.stage == "staging"

    # Register v2 with improved metrics
    v2 = await registry.register_model(
        "churn_model",
        artifact_bytes,
        metrics=[MetricSpec("accuracy", 0.95), MetricSpec("f1", 0.93)],
        signature=signature,
    )
    assert v2.version == 2

    # Compare versions
    comparison = await registry.compare("churn_model", 1, 2)
    assert comparison["better_version"] == 2
    assert comparison["deltas"]["accuracy"] > 0

    # Promote v2: staging -> production
    # (MLflow: client.transition_model_version_stage)
    promoted = await registry.promote_model(
        "churn_model", 2, "production", reason="Better accuracy"
    )
    assert promoted.stage == "production"

    # Load production model (PyCaret: load_model)
    prod_model = await registry.get_model("churn_model", stage="production")
    assert prod_model.version == 2
    assert prod_model.stage == "production"

    # Load artifact and deserialize
    loaded_bytes = await registry.load_artifact("churn_model", 2)
    model = pickle.loads(loaded_bytes)
    preds = model.predict([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])
    assert len(preds) == 1

    # List all versions (MLflow: client.search_model_versions)
    versions = await registry.get_model_versions("churn_model")
    assert len(versions) == 2
    assert versions[0].version == 2  # newest first

    # MLflow format export/import round-trip
    export_path = await registry.export_mlflow(
        "churn_model", 2, tmp_path / "mlflow_out"
    )
    assert (export_path / "MLmodel").exists()
    assert (export_path / "model.pkl").exists()


# ---------------------------------------------------------------------------
# 10. Inference Server -- PyCaret: predict_model()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_10_inference_server(
    registry: ModelRegistry,
    schema: FeatureSchema,
) -> None:
    """Single and batch prediction via InferenceServer.

    PyCaret equivalent:
        from pycaret.classification import predict_model
        predictions = predict_model(best_model, data=new_data)
    """
    # Register a trained model
    rf = RandomForestClassifier(n_estimators=20, random_state=42)
    X_train = np.random.RandomState(42).randn(200, 10)
    y_train = (X_train[:, 0] > 0).astype(int)
    rf.fit(X_train, y_train)

    signature = ModelSignature(
        input_schema=schema,
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )

    await registry.register_model(
        "inference_model",
        pickle.dumps(rf),
        metrics=[MetricSpec("accuracy", 0.90)],
        signature=signature,
    )

    server = InferenceServer(registry, cache_size=5)

    # Single prediction (PyCaret: predict_model with single row)
    features = {f"feat_{i}": float(i) for i in range(10)}
    result: PredictionResult = await server.predict("inference_model", features)

    assert result.prediction is not None
    assert result.model_name == "inference_model"
    assert result.model_version == 1
    assert result.inference_time_ms >= 0
    assert result.inference_path in ("native", "onnx")

    # Batch prediction (PyCaret: predict_model with DataFrame)
    batch_records = [
        {f"feat_{i}": float(np.random.RandomState(row).randn()) for i in range(10)}
        for row in range(50)
    ]
    batch_results: list[PredictionResult] = await server.predict_batch(
        "inference_model",
        batch_records,
    )

    assert len(batch_results) == 50
    assert all(r.model_name == "inference_model" for r in batch_results)
    assert all(r.prediction is not None for r in batch_results)

    # MLToolProtocol: get_metrics (for Kaizen agent integration)
    metrics_info = await server.get_metrics("inference_model")
    assert "metrics" in metrics_info
    assert metrics_info["metrics"]["accuracy"] == 0.90

    # MLToolProtocol: get_model_info
    model_info = await server.get_model_info("inference_model")
    assert model_info["name"] == "inference_model"
    assert 1 in model_info["versions"]


# ---------------------------------------------------------------------------
# 11. Drift Monitoring -- No PyCaret equivalent (requires separate tool)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_11_drift_monitoring(
    drift_monitor: DriftMonitor,
    data: pl.DataFrame,
) -> None:
    """Detect feature distribution drift using PSI and KS tests.

    PyCaret has no built-in drift detection. Typically requires:
        - Evidently AI
        - NannyML
        - whylogs
    kailash-ml provides this natively via DriftMonitor.
    """
    feature_cols = [f"feat_{i}" for i in range(10)]

    # Set reference distribution (production baseline)
    await drift_monitor.set_reference_data("churn_v1", data, feature_cols)

    # Check drift against the same data -- should detect no drift
    report_no_drift: DriftReport = await drift_monitor.check_drift("churn_v1", data)
    assert report_no_drift.model_name == "churn_v1"
    assert report_no_drift.overall_severity == "none"
    assert len(report_no_drift.feature_results) == 10

    # Simulate distribution shift: shift mean of feat_0 by 3 std devs
    shifted_data = data.clone()
    original_feat_0 = shifted_data["feat_0"].to_numpy()
    shifted_feat_0 = original_feat_0 + 3.0 * original_feat_0.std()
    shifted_data = shifted_data.with_columns(
        pl.Series("feat_0", shifted_feat_0.tolist())
    )

    # Check drift against shifted data
    report_drift: DriftReport = await drift_monitor.check_drift(
        "churn_v1", shifted_data
    )
    assert report_drift.overall_drift_detected is True
    assert "feat_0" in report_drift.drifted_features

    # Verify individual feature results have PSI/KS values
    feat_0_result = next(
        f for f in report_drift.feature_results if f.feature_name == "feat_0"
    )
    assert feat_0_result.psi > 0.1  # PSI indicates shift
    assert feat_0_result.drift_detected is True

    # Drift history persisted to database
    history = await drift_monitor.get_drift_history("churn_v1")
    assert len(history) == 2  # Two checks: no-drift + drift


# ---------------------------------------------------------------------------
# 12. Full Lifecycle Integration (end-to-end)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_12_full_lifecycle(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    tracker: ExperimentTracker,
    drift_monitor: DriftMonitor,
    data: pl.DataFrame,
    schema: FeatureSchema,
) -> None:
    """End-to-end ML lifecycle exercising all engines together.

    This demonstrates the complete workflow that would require
    PyCaret + MLflow + Evidently working together.

    kailash-ml covers it all natively, polars-native, with one
    ConnectionManager and one set of types.
    """
    # ---- Step 1: Profile data (PyCaret: setup) ----
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        explorer = DataExplorer()
    profile = await explorer.profile(data)
    assert profile.n_rows == 500

    # ---- Step 2: Preprocess (PyCaret: setup) ----
    preprocessor = PreprocessingPipeline()
    setup_result = preprocessor.setup(data, target="target", seed=42)
    assert setup_result.task_type == "classification"

    # ---- Step 3: Train with experiment tracking (PyCaret + MLflow) ----
    async with tracker.run("lifecycle_experiment", run_name="rf_v1") as ctx:
        train_result = await pipeline.train(
            data,
            schema,
            ModelSpec(
                "sklearn.ensemble.RandomForestClassifier",
                {"n_estimators": 20, "random_state": 42},
            ),
            EvalSpec(
                metrics=["accuracy", "f1"],
                min_threshold={"accuracy": 0.5},
            ),
            "lifecycle_model",
        )

        # Log training params and metrics to experiment tracker
        await ctx.log_params(
            {
                "model_class": "RandomForestClassifier",
                "n_estimators": "20",
            }
        )
        await ctx.log_metrics(train_result.metrics)

    assert train_result.registered is True
    assert train_result.metrics["accuracy"] > 0.5

    # ---- Step 4: Promote to production (MLflow: stage transition) ----
    mv = train_result.model_version
    assert mv is not None
    promoted = await registry.promote_model(
        "lifecycle_model", mv.version, "production", reason="Initial deployment"
    )
    assert promoted.stage == "production"

    # ---- Step 5: Serve predictions (PyCaret: predict_model) ----
    server = InferenceServer(registry, cache_size=5)
    pred = await server.predict(
        "lifecycle_model",
        {f"feat_{i}": float(i * 0.1) for i in range(10)},
    )
    assert pred.prediction is not None

    # ---- Step 6: Monitor drift ----
    feature_cols = [f"feat_{i}" for i in range(10)]
    await drift_monitor.set_reference_data("lifecycle_model", data, feature_cols)
    report = await drift_monitor.check_drift("lifecycle_model", data)
    assert report.overall_drift_detected is False

    # ---- Step 7: Retrain when drift detected ----
    retrain_result = await pipeline.retrain(
        "lifecycle_model",
        schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 30, "random_state": 42},
        ),
        EvalSpec(
            metrics=["accuracy", "f1"],
            min_threshold={"accuracy": 0.5},
        ),
        data,
    )
    assert retrain_result.registered is True
    assert retrain_result.model_version is not None
    assert retrain_result.model_version.version == 2

    # Promote new version, old one auto-archived
    await registry.promote_model(
        "lifecycle_model", 2, "production", reason="Drift-triggered retrain"
    )
    v1_after = await registry.get_model("lifecycle_model", 1)
    assert v1_after.stage == "archived"

    v2_prod = await registry.get_model("lifecycle_model", stage="production")
    assert v2_prod.version == 2
