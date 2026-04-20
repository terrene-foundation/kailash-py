# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for MLEngine.predict(channel="direct").

Exercises the full direct-channel path: real sklearn training -> ONNX
export via ModelRegistry.register_model -> MLEngine.predict() -> verified
prediction output. No mocks; real onnxruntime dispatch.

Shard-C scope per workspaces/kailash-ml-gpu-stack/shards/shard-C brief.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine, PredictionResult
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml.types import (
    FeatureField,
    FeatureSchema,
    ModelSignature,
)


@pytest.fixture
async def registry(tmp_path):
    """ModelRegistry backed by real SQLite + tmp_path artifacts."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.fixture
def trained_model_artifact():
    """Pickle-encoded sklearn RandomForestClassifier fitted on a tiny dataset."""
    rng = np.random.default_rng(seed=42)
    X = rng.random((40, 3), dtype=np.float64)
    y = (X[:, 0] + X[:, 1] > 1.0).astype(int)
    model = RandomForestClassifier(n_estimators=4, random_state=42)
    model.fit(X, y)
    return pickle.dumps(model), X


@pytest.fixture
def signature():
    return ModelSignature(
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


@pytest.mark.integration
async def test_predict_direct_round_trips_onnx(
    registry, trained_model_artifact, signature
):
    """Direct channel: registered sklearn model -> engine.predict -> prediction list."""
    artifact_bytes, X_train = trained_model_artifact
    mv = await registry.register_model(
        "churn_direct", artifact_bytes, signature=signature
    )
    assert mv.version == 1

    engine = MLEngine(registry=registry)
    features = {
        "a": float(X_train[0, 0]),
        "b": float(X_train[0, 1]),
        "c": float(X_train[0, 2]),
    }
    result = await engine.predict(
        "models://churn_direct/v1", features, channel="direct"
    )

    assert isinstance(result, PredictionResult)
    assert result.channel == "direct"
    assert result.model_uri == "models://churn_direct/v1"
    assert result.model_version == 1
    assert result.elapsed_ms >= 0
    # The underlying ONNX output IS a prediction array; verify shape.
    payload = result.predictions
    assert isinstance(payload, dict)
    assert "predictions" in payload
    assert len(payload["predictions"]) == 1
