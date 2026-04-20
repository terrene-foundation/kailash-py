# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test: serve(channels=["rest", "mcp"]) binds BOTH from one call.

Per specs/ml-engines.md §2.1 MUST 10, a single serve() call with a
channels subset MUST bring up every requested channel. This is the key
value proposition the spec enumerates in §7 ("MLflow-better") — the test
guards against any future refactor that splits serve() into per-channel
methods.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine, ServeResult
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def engine(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    registry = ModelRegistry(cm, artifact_store=store)

    rng = np.random.default_rng(seed=3)
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
        "multi_channel", pickle.dumps(model), signature=signature
    )

    eng = MLEngine(registry=registry)
    yield eng
    await cm.close()


@pytest.mark.integration
async def test_serve_rest_and_mcp_in_one_call(engine):
    """serve(channels=['rest', 'mcp']) → both URIs populated, both respond."""
    result = await engine.serve("models://multi_channel/v1", channels=["rest", "mcp"])
    assert isinstance(result, ServeResult)
    assert set(result.uris.keys()) == {"rest", "mcp"}
    assert result.uris["rest"].startswith("http://")
    assert result.uris["mcp"].startswith("mcp+stdio://")
    assert result.channels == ("rest", "mcp")

    # Both endpoints respond.
    features = {"a": 0.5, "b": 0.5}
    rest_pred = await engine.predict(
        "models://multi_channel/v1", features, channel="rest"
    )
    mcp_pred = await engine.predict(
        "models://multi_channel/v1", features, channel="mcp"
    )
    assert "predictions" in rest_pred.predictions
    assert "predictions" in mcp_pred.predictions


@pytest.mark.integration
async def test_serve_single_channel_also_works(engine):
    """Backwards-compatible path: channels=['rest'] alone."""
    result = await engine.serve("models://multi_channel/v1", channels=["rest"])
    assert set(result.uris.keys()) == {"rest"}


@pytest.mark.integration
async def test_serve_rejects_empty_channels(engine):
    with pytest.raises(ValueError):
        await engine.serve("models://multi_channel/v1", channels=[])
