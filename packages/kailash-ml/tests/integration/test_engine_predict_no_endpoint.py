# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test: predict(channel='rest'/'mcp') without prior serve() raises.

Per specs/ml-engines.md §2.2, calling predict() through a non-direct
channel before the model has been bound via serve() MUST raise
ModelNotFoundError with an actionable message that names serve() as the
remediation.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engine import ModelNotFoundError
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def engine_and_features(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    registry = ModelRegistry(cm, artifact_store=store)

    rng = np.random.default_rng(seed=99)
    X = rng.random((20, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=2, random_state=0)
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
    await registry.register_model(
        "solo_model", pickle.dumps(model), signature=signature
    )

    engine = MLEngine(registry=registry)
    yield engine, {"a": float(X[0, 0]), "b": float(X[0, 1])}
    await cm.close()


@pytest.mark.integration
async def test_predict_rest_without_serve_raises_model_not_found(
    engine_and_features,
):
    engine, features = engine_and_features
    with pytest.raises(ModelNotFoundError):
        await engine.predict("models://solo_model/v1", features, channel="rest")


@pytest.mark.integration
async def test_predict_mcp_without_serve_raises_model_not_found(
    engine_and_features,
):
    engine, features = engine_and_features
    with pytest.raises(ModelNotFoundError):
        await engine.predict("models://solo_model/v1", features, channel="mcp")


@pytest.mark.integration
async def test_predict_direct_without_serve_works_normally(engine_and_features):
    """direct channel does NOT require serve(); sanity check the fixture."""
    engine, features = engine_and_features
    result = await engine.predict("models://solo_model/v1", features, channel="direct")
    assert result.channel == "direct"
