# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for MLEngine.predict(channel="mcp").

After serve(channels=["mcp"]), predict(channel="mcp") MUST round-trip
through the bound MCP endpoint and return predictions.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine, PredictionResult
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def engine(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    registry = ModelRegistry(cm, artifact_store=store)

    rng = np.random.default_rng(seed=42)
    X = rng.random((40, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=4, random_state=42)
    model.fit(X, y)

    signature = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    await registry.register_model("churn_mcp", pickle.dumps(model), signature=signature)

    eng = MLEngine(registry=registry)
    yield eng, X
    await cm.close()


@pytest.mark.integration
async def test_predict_mcp_round_trip_via_active_serve(engine):
    eng, X = engine
    serve_result = await eng.serve("models://churn_mcp/v1", channels=["mcp"])
    assert "mcp" in serve_result.uris
    assert serve_result.uris["mcp"].startswith("mcp+stdio://")

    features = {"a": float(X[0, 0]), "b": float(X[0, 1])}
    result = await eng.predict("models://churn_mcp/v1", features, channel="mcp")
    assert isinstance(result, PredictionResult)
    assert result.channel == "mcp"
    assert "predictions" in result.predictions
