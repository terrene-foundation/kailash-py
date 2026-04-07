# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ExperimentTracker auto-logging integration.

Verifies that TrainingPipeline, HyperparameterSearch, and AutoMLEngine
automatically log params and metrics when a tracker is provided, and
that behaviour is unchanged when tracker=None (backward compatibility).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import polars as pl
import pytest

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.experiment_tracker import ExperimentTracker
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.engines.training_pipeline import (
    EvalSpec,
    ModelSpec,
    TrainingPipeline,
    TrainingResult,
)
from kailash_ml.types import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager (in-memory)."""
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
async def registry(conn: ConnectionManager, tmp_path: Path) -> ModelRegistry:
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    return ModelRegistry(conn, artifact_store=store)


@pytest.fixture
def pipeline(feature_store: FeatureStore, registry: ModelRegistry) -> TrainingPipeline:
    return TrainingPipeline(feature_store, registry)


@pytest.fixture
async def tracker(conn: ConnectionManager, tmp_path: Path) -> ExperimentTracker:
    """ExperimentTracker backed by real SQLite + tmp_path artifacts."""
    return ExperimentTracker(conn, artifact_root=str(tmp_path / "mlartifacts"))


@pytest.fixture
def sample_schema() -> FeatureSchema:
    return FeatureSchema(
        "test",
        [
            FeatureField("feature_a", "float64"),
            FeatureField("feature_b", "float64"),
        ],
        entity_id_column="entity_id",
    )


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Classification dataset with clear separation."""
    rng = np.random.RandomState(42)
    n = 200
    feature_a = np.concatenate([rng.normal(0, 1, n // 2), rng.normal(3, 1, n // 2)])
    feature_b = np.concatenate([rng.normal(0, 1, n // 2), rng.normal(3, 1, n // 2)])
    target = np.array([0] * (n // 2) + [1] * (n // 2))
    return pl.DataFrame(
        {
            "entity_id": [f"e{i}" for i in range(n)],
            "feature_a": feature_a.tolist(),
            "feature_b": feature_b.tolist(),
            "target": target.tolist(),
        }
    )


# ---------------------------------------------------------------------------
# TrainingPipeline auto-logging
# ---------------------------------------------------------------------------


class TestTrainingPipelineAutoLogging:
    """Tests for TrainingPipeline.train() with tracker parameter."""

    @pytest.mark.asyncio
    async def test_train_without_tracker_backward_compat(
        self,
        pipeline: TrainingPipeline,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Training without tracker works exactly as before."""
        result = await pipeline.train(
            sample_df,
            sample_schema,
            ModelSpec(
                "sklearn.ensemble.RandomForestClassifier",
                {"n_estimators": 5, "random_state": 42},
            ),
            EvalSpec(metrics=["accuracy"], min_threshold={"accuracy": 0.3}),
            "no_tracker_test",
        )
        assert result.registered is True
        assert result.run_id is None
        assert "accuracy" in result.metrics

    @pytest.mark.asyncio
    async def test_train_with_tracker_logs_run(
        self,
        pipeline: TrainingPipeline,
        tracker: ExperimentTracker,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Training with tracker creates a run and logs params/metrics."""
        result = await pipeline.train(
            sample_df,
            sample_schema,
            ModelSpec(
                "sklearn.ensemble.RandomForestClassifier",
                {"n_estimators": 5, "random_state": 42},
            ),
            EvalSpec(metrics=["accuracy", "f1"], min_threshold={"accuracy": 0.3}),
            "tracked_experiment",
            tracker=tracker,
        )

        # run_id should be populated
        assert result.run_id is not None
        assert isinstance(result.run_id, str)
        assert len(result.run_id) > 0

        # Verify the run exists in tracker
        run = await tracker.get_run(result.run_id)
        assert run.status == "COMPLETED"

        # Verify params were logged
        assert run.params["model_class"] == "sklearn.ensemble.RandomForestClassifier"
        assert run.params["framework"] == "sklearn"
        assert run.params["hp.n_estimators"] == "5"
        assert run.params["hp.random_state"] == "42"
        assert run.params["split_strategy"] == "holdout"
        assert run.params["n_rows"] == "200"
        assert run.params["n_cols"] == "4"

        # Verify metrics were logged
        assert "accuracy" in run.metrics
        assert "f1" in run.metrics
        assert "training_time_seconds" in run.metrics
        assert run.metrics["accuracy"] > 0.3

    @pytest.mark.asyncio
    async def test_train_with_tracker_run_name_uses_class(
        self,
        pipeline: TrainingPipeline,
        tracker: ExperimentTracker,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Run name is derived from model class short name."""
        result = await pipeline.train(
            sample_df,
            sample_schema,
            ModelSpec("sklearn.tree.DecisionTreeClassifier", {"random_state": 42}),
            EvalSpec(metrics=["accuracy"]),
            "name_test",
            tracker=tracker,
        )

        run = await tracker.get_run(result.run_id)
        assert run.name == "DecisionTreeClassifier"

    @pytest.mark.asyncio
    async def test_train_with_tracker_parent_run_id(
        self,
        pipeline: TrainingPipeline,
        tracker: ExperimentTracker,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Training with parent_run_id creates a child run."""
        # Create a parent run first
        parent = await tracker.start_run("parent_test", run_name="parent")

        result = await pipeline.train(
            sample_df,
            sample_schema,
            ModelSpec(
                "sklearn.ensemble.RandomForestClassifier",
                {"n_estimators": 5, "random_state": 42},
            ),
            EvalSpec(metrics=["accuracy"]),
            "parent_test",
            tracker=tracker,
            parent_run_id=parent.id,
        )

        # Verify child run has parent set
        child_run = await tracker.get_run(result.run_id)
        assert child_run.parent_run_id == parent.id

        # Verify parent can list child
        children = await tracker.list_child_runs(parent.id)
        assert len(children) == 1
        assert children[0].id == result.run_id

        await tracker.end_run(parent.id)

    @pytest.mark.asyncio
    async def test_training_result_run_id_serialization(self) -> None:
        """TrainingResult.run_id round-trips through to_dict/from_dict."""
        result = TrainingResult(
            model_version=None,
            metrics={"accuracy": 0.9},
            training_time_seconds=1.0,
            data_shape=(100, 5),
            registered=False,
            threshold_met=True,
            run_id="test-run-id-123",
        )
        d = result.to_dict()
        assert d["run_id"] == "test-run-id-123"

        restored = TrainingResult.from_dict(d)
        assert restored.run_id == "test-run-id-123"

    @pytest.mark.asyncio
    async def test_training_result_run_id_none_serialization(self) -> None:
        """TrainingResult with no run_id serializes correctly."""
        result = TrainingResult(
            model_version=None,
            metrics={"accuracy": 0.9},
            training_time_seconds=1.0,
            data_shape=(100, 5),
            registered=False,
            threshold_met=True,
        )
        d = result.to_dict()
        assert d["run_id"] is None

        restored = TrainingResult.from_dict(d)
        assert restored.run_id is None


# ---------------------------------------------------------------------------
# HyperparameterSearch auto-logging
# ---------------------------------------------------------------------------


class TestHyperparameterSearchAutoLogging:
    """Tests for HyperparameterSearch.search() with tracker parameter."""

    @pytest.mark.asyncio
    async def test_search_with_tracker_creates_parent_and_child_runs(
        self,
        pipeline: TrainingPipeline,
        tracker: ExperimentTracker,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Search creates a parent run, each trial creates a child run."""
        from kailash_ml.engines.hyperparameter_search import (
            HyperparameterSearch,
            ParamDistribution,
            SearchConfig,
            SearchSpace,
        )

        search = HyperparameterSearch(pipeline)
        search_space = SearchSpace(
            [ParamDistribution("n_estimators", "categorical", choices=[5, 10])]
        )
        config = SearchConfig(
            strategy="grid",
            n_trials=2,
            metric_to_optimize="accuracy",
            direction="maximize",
        )

        result = await search.search(
            sample_df,
            sample_schema,
            ModelSpec("sklearn.ensemble.RandomForestClassifier", {"random_state": 42}),
            search_space,
            config,
            EvalSpec(metrics=["accuracy"]),
            "search_tracked",
            tracker=tracker,
        )

        assert len(result.all_trials) == 2

        # Find the parent run (search run)
        runs = await tracker.list_runs("search_tracked")
        parent_runs = [r for r in runs if r.parent_run_id is None]
        assert len(parent_runs) == 1
        parent_run = parent_runs[0]
        assert parent_run.name == "search_grid"
        assert parent_run.status == "COMPLETED"

        # Verify search params on parent
        assert parent_run.params["search_strategy"] == "grid"
        assert parent_run.params["metric_to_optimize"] == "accuracy"

        # Verify best metrics logged on parent
        assert "accuracy" in parent_run.metrics

        # Verify child runs exist
        children = await tracker.list_child_runs(parent_run.id)
        assert len(children) == 2

    @pytest.mark.asyncio
    async def test_search_without_tracker_backward_compat(
        self,
        pipeline: TrainingPipeline,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """Search without tracker works exactly as before."""
        from kailash_ml.engines.hyperparameter_search import (
            HyperparameterSearch,
            ParamDistribution,
            SearchConfig,
            SearchSpace,
        )

        search = HyperparameterSearch(pipeline)
        search_space = SearchSpace(
            [ParamDistribution("n_estimators", "categorical", choices=[5])]
        )
        config = SearchConfig(
            strategy="grid",
            n_trials=1,
            metric_to_optimize="accuracy",
            direction="maximize",
        )

        result = await search.search(
            sample_df,
            sample_schema,
            ModelSpec("sklearn.ensemble.RandomForestClassifier", {"random_state": 42}),
            search_space,
            config,
            EvalSpec(metrics=["accuracy"]),
            "search_no_tracker",
        )

        assert len(result.all_trials) == 1
        assert result.best_metrics.get("accuracy", 0) > 0


# ---------------------------------------------------------------------------
# AutoMLEngine auto-logging
# ---------------------------------------------------------------------------


class TestAutoMLEngineAutoLogging:
    """Tests for AutoMLEngine.run() with tracker parameter."""

    @pytest.mark.asyncio
    async def test_automl_with_tracker_creates_parent_run(
        self,
        pipeline: TrainingPipeline,
        tracker: ExperimentTracker,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """AutoML creates a parent run and passes tracker to sub-calls."""
        from kailash_ml.engines.automl_engine import AutoMLConfig, AutoMLEngine
        from kailash_ml.engines.hyperparameter_search import HyperparameterSearch

        search = HyperparameterSearch(pipeline)
        engine = AutoMLEngine(pipeline, search)

        config = AutoMLConfig(
            task_type="classification",
            search_strategy="random",
            search_n_trials=2,
        )

        result = await engine.run(
            sample_df,
            sample_schema,
            config,
            EvalSpec(metrics=["accuracy"]),
            "automl_tracked",
            tracker=tracker,
        )

        assert result.best_metrics.get("accuracy", 0) > 0

        # Find the automl parent run
        runs = await tracker.list_runs("automl_tracked")
        # There should be an automl parent run with no parent
        automl_runs = [
            r for r in runs if r.name == "automl" and r.parent_run_id is None
        ]
        assert len(automl_runs) == 1
        automl_run = automl_runs[0]
        assert automl_run.status == "COMPLETED"

        # Verify AutoML config params
        assert automl_run.params["task_type"] == "classification"
        assert automl_run.params["search_strategy"] == "random"

        # Verify best metrics logged on parent
        assert "accuracy" in automl_run.metrics

        # Verify child runs were created (candidates + search trials)
        all_child_runs = await tracker.list_child_runs(automl_run.id)
        assert len(all_child_runs) > 0

    @pytest.mark.asyncio
    async def test_automl_without_tracker_backward_compat(
        self,
        pipeline: TrainingPipeline,
        sample_df: pl.DataFrame,
        sample_schema: FeatureSchema,
    ) -> None:
        """AutoML without tracker works exactly as before."""
        from kailash_ml.engines.automl_engine import AutoMLConfig, AutoMLEngine
        from kailash_ml.engines.hyperparameter_search import HyperparameterSearch

        search = HyperparameterSearch(pipeline)
        engine = AutoMLEngine(pipeline, search)

        config = AutoMLConfig(
            task_type="classification",
            search_strategy="random",
            search_n_trials=2,
        )

        result = await engine.run(
            sample_df,
            sample_schema,
            config,
            EvalSpec(metrics=["accuracy"]),
            "automl_no_tracker",
        )

        assert result.best_metrics.get("accuracy", 0) > 0
        assert len(result.all_candidates) > 0
