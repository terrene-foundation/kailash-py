# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for InferenceServer engine.

Uses real sklearn models + real SQLite (no mocking).
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.inference_server import InferenceServer, PredictionResult
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
)
from kailash_ml_protocols import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    MLToolProtocol,
    ModelSignature,
)


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
async def registry(conn: ConnectionManager, tmp_path) -> ModelRegistry:
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    return ModelRegistry(conn, artifact_store=store)


@pytest.fixture
def sample_signature() -> ModelSignature:
    return ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [
                FeatureField("feature_a", "float64"),
                FeatureField("feature_b", "float64"),
            ],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


@pytest.fixture
async def registered_registry(
    registry: ModelRegistry, sample_signature: ModelSignature
) -> ModelRegistry:
    """Registry with a pre-registered sklearn model."""
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    X = np.array([[1, 2], [3, 4], [5, 6], [7, 8], [1, 3], [4, 5], [6, 7], [8, 9]])
    y = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    model.fit(X, y)

    await registry.register_model(
        "rf",
        pickle.dumps(model),
        signature=sample_signature,
        metrics=[MetricSpec("accuracy", 0.85)],
    )
    return registry


@pytest.fixture
def server(registered_registry: ModelRegistry) -> InferenceServer:
    return InferenceServer(registered_registry, cache_size=5)


# ---------------------------------------------------------------------------
# Single prediction
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_predict_single_record(server: InferenceServer) -> None:
    """Single-record prediction returns valid result."""
    result = await server.predict("rf", {"feature_a": 1.0, "feature_b": 2.0})
    assert isinstance(result, PredictionResult)
    assert result.prediction in (0, 1)
    assert result.model_name == "rf"
    assert result.model_version == 1
    assert result.inference_time_ms >= 0
    assert result.inference_path in ("native", "onnx")


@pytest.mark.integration
async def test_predict_with_probabilities(server: InferenceServer) -> None:
    """Prediction includes class probabilities for classifiers."""
    result = await server.predict("rf", {"feature_a": 1.0, "feature_b": 2.0})
    assert result.probabilities is not None
    assert len(result.probabilities) == 2
    assert abs(sum(result.probabilities) - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Batch prediction
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_predict_batch(server: InferenceServer) -> None:
    """Batch prediction processes multiple records."""
    records = [
        {"feature_a": 1.0, "feature_b": 2.0},
        {"feature_a": 3.0, "feature_b": 4.0},
        {"feature_a": 5.0, "feature_b": 6.0},
    ]
    results = await server.predict_batch("rf", records)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, PredictionResult)
        assert r.prediction in (0, 1)
        assert r.model_name == "rf"


@pytest.mark.integration
async def test_predict_batch_empty(server: InferenceServer) -> None:
    """Empty batch returns empty list."""
    results = await server.predict_batch("rf", [])
    assert results == []


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_warm_cache(server: InferenceServer) -> None:
    """Warming cache loads model."""
    await server.warm_cache(["rf"])
    # Second predict should be from cache (faster)
    result = await server.predict("rf", {"feature_a": 1.0, "feature_b": 2.0})
    assert result.prediction in (0, 1)


@pytest.mark.integration
async def test_cache_stats(server: InferenceServer) -> None:
    """Cache stats reflect loaded models."""
    await server.warm_cache(["rf"])
    stats = server._cache.stats()
    assert stats["size"] == 1
    assert "rf:v1" in stats["models"]


# ---------------------------------------------------------------------------
# MLToolProtocol
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_ml_tool_protocol_conformance(
    registered_registry: ModelRegistry,
) -> None:
    """InferenceServer satisfies MLToolProtocol."""
    server = InferenceServer(registered_registry)
    assert isinstance(server, MLToolProtocol)


@pytest.mark.integration
async def test_get_metrics(server: InferenceServer) -> None:
    """get_metrics returns model metrics from registry."""
    result = await server.get_metrics("rf")
    assert "metrics" in result
    assert result["metrics"]["accuracy"] == 0.85
    assert result["version"] == 1


@pytest.mark.integration
async def test_get_model_info(server: InferenceServer) -> None:
    """get_model_info returns model metadata."""
    result = await server.get_model_info("rf")
    assert result["name"] == "rf"
    assert result["stage"] == "staging"
    assert 1 in result["versions"]
    assert result["signature"] is not None
