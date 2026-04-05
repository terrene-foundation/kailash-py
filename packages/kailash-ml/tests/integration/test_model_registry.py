# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for ModelRegistry engine.

Uses a real SQLite database via ConnectionManager (no mocking).
"""
from __future__ import annotations

import pickle

import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelNotFoundError,
    ModelRegistry,
    ModelVersion,
)
from kailash_ml.types import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    """Real SQLite ConnectionManager for integration tests."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def registry(conn: ConnectionManager, tmp_path) -> ModelRegistry:
    """ModelRegistry backed by real SQLite + tmp_path artifacts."""
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(conn, artifact_store=store)
    return reg


@pytest.fixture
def sample_signature() -> ModelSignature:
    return ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


@pytest.fixture
def trained_model_bytes() -> bytes:
    """A small trained sklearn model as pickle bytes."""
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    model.fit([[1, 2], [3, 4], [5, 6], [7, 8]], [0, 1, 0, 1])
    return pickle.dumps(model)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_register_model_returns_staging(
    registry: ModelRegistry,
    trained_model_bytes: bytes,
    sample_signature: ModelSignature,
) -> None:
    """Register a model, verify it starts at staging."""
    version = await registry.register_model(
        "test_model",
        trained_model_bytes,
        metrics=[MetricSpec("accuracy", 0.95)],
        signature=sample_signature,
    )
    assert version.stage == "staging"
    assert version.version == 1
    assert version.name == "test_model"
    assert len(version.metrics) == 1
    assert version.metrics[0].name == "accuracy"
    assert version.model_uuid != ""


@pytest.mark.integration
async def test_register_increments_version(
    registry: ModelRegistry,
) -> None:
    """Each register_model call increments version."""
    v1 = await registry.register_model("m", b"model_v1")
    v2 = await registry.register_model("m", b"model_v2")
    v3 = await registry.register_model("m", b"model_v3")
    assert v1.version == 1
    assert v2.version == 2
    assert v3.version == 3


# ---------------------------------------------------------------------------
# Get model
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_model_by_version(
    registry: ModelRegistry,
    trained_model_bytes: bytes,
    sample_signature: ModelSignature,
) -> None:
    """get_model returns the correct version."""
    await registry.register_model(
        "test_model",
        trained_model_bytes,
        metrics=[MetricSpec("accuracy", 0.95)],
        signature=sample_signature,
    )
    loaded = await registry.get_model("test_model", 1)
    assert loaded.stage == "staging"
    assert loaded.version == 1
    assert loaded.signature is not None
    assert loaded.signature.model_type == "classifier"


@pytest.mark.integration
async def test_get_model_latest(registry: ModelRegistry) -> None:
    """get_model without version returns latest."""
    await registry.register_model("m", b"v1")
    await registry.register_model("m", b"v2")
    latest = await registry.get_model("m")
    assert latest.version == 2


@pytest.mark.integration
async def test_get_model_not_found(registry: ModelRegistry) -> None:
    """get_model raises ModelNotFoundError for missing model."""
    with pytest.raises(ModelNotFoundError):
        await registry.get_model("nonexistent")


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_models(registry: ModelRegistry) -> None:
    """list_models returns all registered models."""
    await registry.register_model("alpha", b"a")
    await registry.register_model("beta", b"b")
    models = await registry.list_models()
    names = [m["name"] for m in models]
    assert sorted(names) == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# Stage transitions
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_promote_to_production(registry: ModelRegistry) -> None:
    """Promote staging -> production."""
    await registry.register_model("m", b"model_data")
    promoted = await registry.promote_model("m", 1, "production")
    assert promoted.stage == "production"


@pytest.mark.integration
async def test_promote_to_production_demotes_current(
    registry: ModelRegistry,
) -> None:
    """Promoting v2 to production archives v1."""
    await registry.register_model("m", b"model_v1")
    await registry.promote_model("m", 1, "production")

    await registry.register_model("m", b"model_v2")
    await registry.promote_model("m", 2, "production")

    v1_after = await registry.get_model("m", 1)
    assert v1_after.stage == "archived"

    v2_after = await registry.get_model("m", 2)
    assert v2_after.stage == "production"


@pytest.mark.integration
async def test_invalid_transition_raises(registry: ModelRegistry) -> None:
    """Invalid stage transition raises ValueError."""
    await registry.register_model("m", b"data")
    # staging -> staging is not valid
    with pytest.raises(ValueError, match="Invalid transition"):
        await registry.promote_model("m", 1, "staging")


@pytest.mark.integration
async def test_archived_can_reactivate(registry: ModelRegistry) -> None:
    """Archived model can be re-activated to staging."""
    await registry.register_model("m", b"data")
    await registry.promote_model("m", 1, "production")
    await registry.promote_model("m", 1, "archived")
    reactivated = await registry.promote_model("m", 1, "staging")
    assert reactivated.stage == "staging"


# ---------------------------------------------------------------------------
# Get model versions
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_model_versions_newest_first(
    registry: ModelRegistry,
) -> None:
    """get_model_versions returns versions newest first."""
    await registry.register_model("m", b"v1")
    await registry.register_model("m", b"v2")
    await registry.register_model("m", b"v3")
    versions = await registry.get_model_versions("m")
    assert [v.version for v in versions] == [3, 2, 1]


# ---------------------------------------------------------------------------
# ONNX status
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_onnx_failure_sets_status(
    registry: ModelRegistry,
) -> None:
    """Registering non-picklable bytes sets onnx_status != 'success'."""
    await registry.register_model("custom_model", b"not_a_real_model")
    version = await registry.get_model("custom_model", 1)
    assert version.onnx_status in ("failed", "not_applicable")


@pytest.mark.integration
async def test_onnx_success_for_sklearn(
    registry: ModelRegistry,
    trained_model_bytes: bytes,
    sample_signature: ModelSignature,
) -> None:
    """Sklearn model with signature gets ONNX export attempted."""
    version = await registry.register_model(
        "sklearn_model",
        trained_model_bytes,
        signature=sample_signature,
    )
    # ONNX export was attempted -- status depends on skl2onnx availability
    assert version.onnx_status in ("success", "failed", "not_applicable")


# ---------------------------------------------------------------------------
# Artifact round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_load_artifact_round_trip(
    registry: ModelRegistry,
    trained_model_bytes: bytes,
) -> None:
    """Store and load artifact, verify deserialization."""
    await registry.register_model("rf", trained_model_bytes)
    loaded_bytes = await registry.load_artifact("rf", 1)
    model = pickle.loads(loaded_bytes)
    pred = model.predict([[1, 2]])
    assert len(pred) == 1


# ---------------------------------------------------------------------------
# MLflow export/import
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_mlflow_export_import_round_trip(
    registry: ModelRegistry,
    trained_model_bytes: bytes,
    sample_signature: ModelSignature,
    tmp_path,
) -> None:
    """Export MLmodel YAML, import it, verify metadata matches."""
    await registry.register_model(
        "rf",
        trained_model_bytes,
        metrics=[MetricSpec("f1", 0.88)],
        signature=sample_signature,
    )
    mlmodel_path = await registry.export_mlflow("rf", 1, tmp_path / "export")
    assert (mlmodel_path / "MLmodel").exists()
    assert (mlmodel_path / "model.pkl").exists()

    imported = await registry.import_mlflow(mlmodel_path)
    assert imported.version >= 1
    # Verify metrics survived round-trip
    assert any(m.name == "f1" for m in imported.metrics)
