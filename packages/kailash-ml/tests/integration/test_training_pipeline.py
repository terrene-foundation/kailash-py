# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for TrainingPipeline engine.

Uses real sklearn/LightGBM + real SQLite (no mocking).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash.db.connection import ConnectionManager

try:
    import lightgbm  # noqa: F401

    _HAS_LIGHTGBM = True
except (ImportError, OSError):
    _HAS_LIGHTGBM = False
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.training_pipeline import (
    EvalSpec,
    ModelSpec,
    TrainingPipeline,
    TrainingResult,
)
from kailash_ml_protocols import FeatureField, FeatureSchema


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
# Full training cycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_full_sklearn_train_register_cycle(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Train sklearn RandomForest, register, verify model version exists."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 10, "random_state": 42},
            "sklearn",
        ),
        EvalSpec(metrics=["accuracy"], min_threshold={"accuracy": 0.3}),
        "test_experiment",
    )

    assert result.registered is True
    assert result.threshold_met is True
    assert result.metrics["accuracy"] > 0.3
    assert result.model_version is not None
    assert result.data_shape == (200, 4)
    assert result.training_time_seconds > 0

    # Verify in registry
    loaded = await registry.get_model("test_experiment", result.model_version.version)
    assert loaded.stage == "staging"


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_LIGHTGBM, reason="LightGBM native lib not available")
async def test_full_lightgbm_train_register_cycle(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Train LightGBM, register, verify model version exists."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec(
            "lightgbm.LGBMClassifier",
            {"n_estimators": 10, "verbose": -1},
            "lightgbm",
        ),
        EvalSpec(metrics=["accuracy"], min_threshold={"accuracy": 0.3}),
        "lgbm_experiment",
    )

    assert result.registered is True
    assert result.metrics["accuracy"] > 0.3
    assert result.model_version is not None

    loaded = await registry.get_model("lgbm_experiment", result.model_version.version)
    assert loaded.stage == "staging"


# ---------------------------------------------------------------------------
# Threshold failure
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_threshold_failure_skips_registration(
    pipeline: TrainingPipeline,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Model below threshold is NOT registered."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 5, "random_state": 42},
            "sklearn",
        ),
        EvalSpec(
            metrics=["accuracy"],
            min_threshold={"accuracy": 0.9999},  # impossibly high
        ),
        "threshold_test",
    )
    assert result.registered is False
    assert result.threshold_met is False
    assert result.model_version is None


# ---------------------------------------------------------------------------
# Retrain
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_retrain_creates_new_version(
    pipeline: TrainingPipeline,
    registry: ModelRegistry,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Retrain creates version 2 of the same model."""
    # Train v1
    r1 = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 5, "random_state": 42},
        ),
        EvalSpec(metrics=["accuracy"], min_threshold={"accuracy": 0.3}),
        "retrain_model",
    )
    assert r1.registered is True
    assert r1.model_version is not None
    assert r1.model_version.version == 1

    # Retrain (creates v2)
    r2 = await pipeline.retrain(
        "retrain_model",
        sample_schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 10, "random_state": 42},
        ),
        EvalSpec(metrics=["accuracy"], min_threshold={"accuracy": 0.3}),
        sample_df,
    )
    assert r2.registered is True
    assert r2.model_version is not None
    assert r2.model_version.version == 2


# ---------------------------------------------------------------------------
# Multiple metrics
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_multiple_metrics(
    pipeline: TrainingPipeline,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Pipeline can compute multiple metrics."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec(
            "sklearn.ensemble.RandomForestClassifier",
            {"n_estimators": 10, "random_state": 42},
        ),
        EvalSpec(metrics=["accuracy", "f1", "precision", "recall"]),
        "multi_metric",
    )
    assert "accuracy" in result.metrics
    assert "f1" in result.metrics
    assert "precision" in result.metrics
    assert "recall" in result.metrics


# ---------------------------------------------------------------------------
# Split strategies
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_walk_forward_split(
    pipeline: TrainingPipeline,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """Walk-forward split strategy works."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec("sklearn.tree.DecisionTreeClassifier", {"random_state": 42}),
        EvalSpec(
            metrics=["accuracy"],
            split_strategy="walk_forward",
            min_threshold={"accuracy": 0.1},
        ),
        "walk_forward_test",
    )
    assert result.registered is True


@pytest.mark.integration
async def test_kfold_split(
    pipeline: TrainingPipeline,
    sample_df: pl.DataFrame,
    sample_schema: FeatureSchema,
) -> None:
    """K-fold split strategy works."""
    result = await pipeline.train(
        sample_df,
        sample_schema,
        ModelSpec("sklearn.tree.DecisionTreeClassifier", {"random_state": 42}),
        EvalSpec(
            metrics=["accuracy"],
            split_strategy="kfold",
            n_splits=5,
            min_threshold={"accuracy": 0.1},
        ),
        "kfold_test",
    )
    assert result.registered is True


# ---------------------------------------------------------------------------
# Data validation
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_missing_feature_raises(
    pipeline: TrainingPipeline,
) -> None:
    """Missing feature column raises ValueError."""
    schema = FeatureSchema(
        "strict",
        [FeatureField("nonexistent_col", "float64")],
        entity_id_column="id",
    )
    df = pl.DataFrame({"id": ["e1"], "other": [1.0], "target": [0]})
    with pytest.raises(ValueError, match="missing columns"):
        await pipeline.train(
            df,
            schema,
            ModelSpec("sklearn.tree.DecisionTreeClassifier"),
            EvalSpec(),
            "should_fail",
        )
