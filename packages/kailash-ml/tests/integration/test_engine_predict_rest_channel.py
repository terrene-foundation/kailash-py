# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for MLEngine.predict(channel="rest").

After a serve(channels=["rest"]) call, predict(channel="rest") MUST
round-trip through the bound REST endpoint and return predictions.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine, PredictionResult, ServeResult
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def engine_with_registered_model(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    registry = ModelRegistry(cm, artifact_store=store)

    rng = np.random.default_rng(seed=42)
    X = rng.random((40, 3), dtype=np.float64)
    y = (X[:, 0] + X[:, 1] > 1.0).astype(int)
    model = RandomForestClassifier(n_estimators=4, random_state=42)
    model.fit(X, y)

    signature = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [
                FeatureField("a", "float64"),
                FeatureField("b", "float64"),
                FeatureField("c", "float64"),
            ],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )

    await registry.register_model(
        "churn_rest", pickle.dumps(model), signature=signature
    )

    engine = MLEngine(registry=registry)
    yield engine, X
    await cm.close()


@pytest.mark.integration
async def test_predict_rest_round_trip_via_active_serve(engine_with_registered_model):
    engine, X = engine_with_registered_model
    serve_result = await engine.serve("models://churn_rest/v1", channels=["rest"])
    assert isinstance(serve_result, ServeResult)
    assert "rest" in serve_result.uris
    assert serve_result.uris["rest"].startswith("http://")

    features = {"a": float(X[0, 0]), "b": float(X[0, 1]), "c": float(X[0, 2])}
    result = await engine.predict("models://churn_rest/v1", features, channel="rest")
    assert isinstance(result, PredictionResult)
    assert result.channel == "rest"
    assert isinstance(result.predictions, dict)
    assert "predictions" in result.predictions


@pytest.mark.integration
async def test_predict_rest_no_endpoint_raises_model_not_found(
    engine_with_registered_model,
):
    """predict(channel='rest') without prior serve() raises ModelNotFoundError."""
    from kailash_ml.engine import ModelNotFoundError

    engine, X = engine_with_registered_model
    features = {"a": float(X[0, 0]), "b": float(X[0, 1]), "c": float(X[0, 2])}
    with pytest.raises(ModelNotFoundError):
        await engine.predict("models://churn_rest/v1", features, channel="rest")
