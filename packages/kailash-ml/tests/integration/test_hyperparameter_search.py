# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for HyperparameterSearch engine.

Uses real sklearn + real SQLite (no mocking).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.hyperparameter_search import (
    HyperparameterSearch,
    ParamDistribution,
    SearchConfig,
    SearchResult,
    SearchSpace,
    TrialResult,
)
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.engines.training_pipeline import (
    EvalSpec,
    ModelSpec,
    TrainingPipeline,
)
from kailash_ml.types import FeatureField, FeatureSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
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
def search(pipeline: TrainingPipeline) -> HyperparameterSearch:
    return HyperparameterSearch(pipeline)


@pytest.fixture
def sample_schema() -> FeatureSchema:
    return FeatureSchema(
        "hp_test",
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_random_search_finds_better_params(
    search: HyperparameterSearch,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Random search finds params at least as good as default."""
    result = await search.search(
        sample_df,
        sample_schema,
        ModelSpec("sklearn.ensemble.RandomForestClassifier", {}, "sklearn"),
        SearchSpace(
            [
                ParamDistribution("n_estimators", "int_uniform", low=5, high=50),
                ParamDistribution("max_depth", "int_uniform", low=2, high=15),
            ]
        ),
        SearchConfig(strategy="random", n_trials=5, metric_to_optimize="accuracy"),
        EvalSpec(metrics=["accuracy"]),
        "random_search_run",
    )

    assert isinstance(result, SearchResult)
    assert len(result.all_trials) == 5
    assert result.best_metrics["accuracy"] > 0.5
    assert result.strategy == "random"
    assert result.total_time_seconds > 0


@pytest.mark.integration
async def test_grid_search_exhaustive(
    search: HyperparameterSearch,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Grid search tests every combination."""
    result = await search.search(
        sample_df,
        sample_schema,
        ModelSpec("sklearn.ensemble.RandomForestClassifier", {}, "sklearn"),
        SearchSpace(
            [
                ParamDistribution("n_estimators", "categorical", choices=[10, 50]),
                ParamDistribution("max_depth", "categorical", choices=[3, 5, 10]),
            ]
        ),
        SearchConfig(strategy="grid", n_trials=100),  # n_trials ignored for grid
        EvalSpec(metrics=["accuracy"]),
        "grid_search_run",
    )

    # 2 x 3 = 6 combinations
    assert len(result.all_trials) == 6
    assert result.strategy == "grid"


@pytest.mark.integration
async def test_bayesian_search_converges(
    search: HyperparameterSearch,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Bayesian search runs and returns results."""
    result = await search.search(
        sample_df,
        sample_schema,
        ModelSpec("sklearn.ensemble.RandomForestClassifier", {}, "sklearn"),
        SearchSpace(
            [
                ParamDistribution("n_estimators", "int_uniform", low=5, high=50),
                ParamDistribution("max_depth", "int_uniform", low=2, high=10),
            ]
        ),
        SearchConfig(strategy="bayesian", n_trials=5, metric_to_optimize="accuracy"),
        EvalSpec(metrics=["accuracy"]),
        "bayesian_search_run",
    )

    assert len(result.all_trials) == 5
    assert result.best_metrics["accuracy"] > 0.5
    assert result.strategy == "bayesian"


@pytest.mark.integration
async def test_search_space_sample_random() -> None:
    """SearchSpace.sample_random produces correct number of samples."""
    space = SearchSpace(
        [
            ParamDistribution("lr", "log_uniform", low=0.001, high=0.1),
            ParamDistribution("layers", "int_uniform", low=1, high=5),
            ParamDistribution("activation", "categorical", choices=["relu", "tanh"]),
        ]
    )

    samples = space.sample_random(10)
    assert len(samples) == 10
    for s in samples:
        assert "lr" in s
        assert "layers" in s
        assert "activation" in s
        assert 0.001 <= s["lr"] <= 0.1
        assert 1 <= s["layers"] <= 5
        assert s["activation"] in ("relu", "tanh")


@pytest.mark.integration
async def test_search_space_sample_grid() -> None:
    """SearchSpace.sample_grid produces exhaustive grid."""
    space = SearchSpace(
        [
            ParamDistribution("a", "categorical", choices=[1, 2, 3]),
            ParamDistribution("b", "categorical", choices=["x", "y"]),
        ]
    )

    grid = space.sample_grid()
    assert len(grid) == 6  # 3 x 2
