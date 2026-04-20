# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.evaluate() raises TargetNotFoundError on missing target.

Tier 2 — per the typed-error contract in ``specs/ml-engines.md`` §2.3
a data frame missing the target column MUST raise the typed
:class:`TargetNotFoundError`, not a generic ``KeyError`` deep in
metric computation.
"""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pytest

import polars as pl
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engine import TargetNotFoundError
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.types import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)


@pytest.fixture
async def registry(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(40)),
            "x2": [i * 2 for i in range(40)],
            "y": [i % 2 for i in range(40)],
        }
    )


@pytest.fixture
async def registered_classifier(registry: ModelRegistry, sample_df: pl.DataFrame):
    sig = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("x1", "float64"), FeatureField("x2", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    model.fit(sample_df.select(["x1", "x2"]).to_numpy(), sample_df["y"].to_numpy())
    return await registry.register_model(
        "clf_missing_target",
        pickle.dumps(model),
        metrics=[MetricSpec("accuracy", 0.95)],
        signature=sig,
    )


@pytest.mark.integration
async def test_evaluate_raises_target_not_found_when_column_absent(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
) -> None:
    """evaluate(data=...) with missing target column raises TargetNotFoundError."""
    engine = MLEngine(registry=registry)
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")

    # Drop the target column — features still present
    features_only = sample_df.drop("y")
    assert "y" not in features_only.columns

    with pytest.raises(TargetNotFoundError) as exc_info:
        await engine.evaluate(registered_classifier, features_only, mode="holdout")

    # Typed exception carries the column + available columns (§2.3)
    assert exc_info.value.column == "y"
    assert "x1" in exc_info.value.columns
    assert "x2" in exc_info.value.columns
