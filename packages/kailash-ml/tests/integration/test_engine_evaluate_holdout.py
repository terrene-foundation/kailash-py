# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: MLEngine.evaluate() scores a registered model on holdout data.

Tier 2 — real ModelRegistry, real SQLite, real artifact store. Per
``specs/ml-engines.md`` §2.2 evaluate() resolves the model URI through
the registry and scores the supplied DataFrame, returning typed
metrics. The default metric set for a classifier is
``accuracy/f1/precision/recall``.
"""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pytest

import polars as pl
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import EvaluationResult, MLEngine
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
    """Real SQLite ModelRegistry with a filesystem artifact store."""
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
def classifier_signature() -> ModelSignature:
    return ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("x1", "float64"), FeatureField("x2", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


@pytest.fixture
async def registered_classifier(
    registry: ModelRegistry,
    sample_df: pl.DataFrame,
    classifier_signature: ModelSignature,
):
    """Fit + register a sklearn classifier; return the ModelVersion."""
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    model.fit(
        sample_df.select(["x1", "x2"]).to_numpy(),
        sample_df["y"].to_numpy(),
    )
    mv = await registry.register_model(
        "clf",
        pickle.dumps(model),
        metrics=[MetricSpec("accuracy", 0.95)],
        signature=classifier_signature,
    )
    return mv


@pytest.mark.integration
async def test_evaluate_holdout_default_metrics(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
) -> None:
    """Holdout mode returns EvaluationResult with the classifier default metrics."""
    engine = MLEngine(registry=registry)
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")

    result = await engine.evaluate(registered_classifier, sample_df, mode="holdout")

    assert isinstance(result, EvaluationResult)
    assert result.mode == "holdout"
    assert result.sample_count == sample_df.height
    assert result.model_version == registered_classifier.version
    # Default classifier metric set per evaluate() contract
    for metric in ("accuracy", "f1", "precision", "recall"):
        assert (
            metric in result.metrics
        ), f"evaluate() missing default classifier metric '{metric}'"
        assert isinstance(result.metrics[metric], float)


@pytest.mark.integration
async def test_evaluate_holdout_by_uri_string(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
) -> None:
    """evaluate() accepts a URI string and resolves it through the registry."""
    engine = MLEngine(registry=registry)
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")

    uri = f"models://{registered_classifier.name}/v{registered_classifier.version}"
    result = await engine.evaluate(uri, sample_df, mode="holdout")
    assert result.model_uri == uri
    assert result.sample_count == sample_df.height


@pytest.mark.integration
async def test_evaluate_tenant_propagation(
    registry: ModelRegistry,
    registered_classifier,
    sample_df: pl.DataFrame,
) -> None:
    """evaluate() echoes engine.tenant_id on EvaluationResult."""
    engine = MLEngine(registry=registry, tenant_id="delta")
    engine._setup_result = SimpleNamespace(target="y", task_type="classification")
    result = await engine.evaluate(registered_classifier, sample_df, mode="holdout")
    assert result.tenant_id == "delta"
