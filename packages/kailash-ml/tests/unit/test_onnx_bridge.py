# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for ONNX export/validation in ModelRegistry."""
from __future__ import annotations

import pickle
from unittest.mock import MagicMock, patch

import pytest
from kailash_ml.engines.model_registry import (
    ModelVersion,
    _attempt_onnx_export,
    _validate_artifact_name,
    _write_mlmodel_yaml,
    _read_mlmodel_yaml,
    VALID_TRANSITIONS,
    ALL_STAGES,
)
from kailash_ml.types import FeatureField, FeatureSchema, MetricSpec, ModelSignature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature(n_features: int = 3) -> ModelSignature:
    """Build a minimal ModelSignature for testing."""
    features = [FeatureField(name=f"f{i}", dtype="float64") for i in range(n_features)]
    schema = FeatureSchema(
        name="test_schema",
        features=features,
        entity_id_column="f0",
    )
    return ModelSignature(
        input_schema=schema,
        output_columns=["prediction"],
        output_dtypes=["float64"],
        model_type="classifier",
    )


def _pickle_obj(obj: object) -> bytes:
    return pickle.dumps(obj)


# ---------------------------------------------------------------------------
# _attempt_onnx_export
# ---------------------------------------------------------------------------


class TestAttemptOnnxExport:
    """Tests for the _attempt_onnx_export helper."""

    def test_unpicklable_bytes_returns_not_applicable(self) -> None:
        status, error, data = _attempt_onnx_export(b"not-a-pickle", None)
        assert status == "not_applicable"
        assert error is not None
        assert "Cannot unpickle" in error
        assert data is None

    def test_no_signature_returns_not_applicable(self) -> None:
        model_bytes = _pickle_obj({"dummy": True})
        status, error, data = _attempt_onnx_export(model_bytes, None)
        assert status == "not_applicable"
        assert "No signature" in (error or "")
        assert data is None

    def test_unsupported_model_type_returns_not_applicable(self) -> None:
        """A plain dict is not an sklearn/lightgbm model."""
        model_bytes = _pickle_obj({"some": "dict"})
        sig = _make_signature(2)
        status, error, data = _attempt_onnx_export(model_bytes, sig)
        assert status == "not_applicable"
        assert "not supported" in (error or "")
        assert data is None

    def test_skl2onnx_not_installed_returns_not_applicable(self) -> None:
        """When skl2onnx is missing, should gracefully degrade."""
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(max_iter=10)
        # Fit on trivial data so it's a valid model
        import numpy as np

        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        y = np.array([0, 1])
        model.fit(X, y)
        model_bytes = _pickle_obj(model)
        sig = _make_signature(3)

        with patch.dict("sys.modules", {"skl2onnx": None}):
            status, error, data = _attempt_onnx_export(model_bytes, sig)
        assert status == "not_applicable"
        assert "skl2onnx not installed" in (error or "")
        assert data is None

    def test_onnx_export_failure_returns_failed_status(self) -> None:
        """When skl2onnx raises during conversion, status should be 'failed'."""
        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier(n_estimators=2, random_state=42)
        import numpy as np

        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        y = np.array([0, 1])
        model.fit(X, y)
        model_bytes = _pickle_obj(model)
        sig = _make_signature(3)

        fake_skl2onnx = MagicMock()
        fake_skl2onnx.convert_sklearn.side_effect = RuntimeError("conversion boom")
        fake_float_type = MagicMock()
        fake_data_types = MagicMock()
        fake_data_types.FloatTensorType = fake_float_type

        with patch.dict(
            "sys.modules",
            {
                "skl2onnx": fake_skl2onnx,
                "skl2onnx.common": MagicMock(),
                "skl2onnx.common.data_types": fake_data_types,
            },
        ):
            status, error, data = _attempt_onnx_export(model_bytes, sig)

        assert status == "failed"
        assert "conversion boom" in (error or "")
        assert data is None


# ---------------------------------------------------------------------------
# ModelVersion dataclass
# ---------------------------------------------------------------------------


class TestModelVersion:
    """Tests for ModelVersion to_dict / from_dict round-trip."""

    def test_onnx_status_defaults_to_pending(self) -> None:
        mv = ModelVersion(name="m", version=1, stage="staging")
        assert mv.onnx_status == "pending"
        assert mv.onnx_error is None

    def test_to_dict_includes_onnx_fields(self) -> None:
        mv = ModelVersion(
            name="m",
            version=2,
            stage="staging",
            onnx_status="success",
            onnx_error=None,
        )
        d = mv.to_dict()
        assert d["onnx_status"] == "success"
        assert d["onnx_error"] is None

    def test_round_trip_with_metrics_and_signature(self) -> None:
        sig = _make_signature(2)
        metrics = [MetricSpec(name="accuracy", value=0.95)]
        mv = ModelVersion(
            name="test_model",
            version=3,
            stage="production",
            metrics=metrics,
            signature=sig,
            onnx_status="failed",
            onnx_error="some error",
            artifact_path="/tmp/art",
            model_uuid="uuid-123",
            created_at="2026-01-01T00:00:00Z",
        )
        d = mv.to_dict()
        restored = ModelVersion.from_dict(d)

        assert restored.name == mv.name
        assert restored.version == mv.version
        assert restored.stage == mv.stage
        assert restored.onnx_status == "failed"
        assert restored.onnx_error == "some error"
        assert len(restored.metrics) == 1
        assert restored.metrics[0].name == "accuracy"
        assert restored.signature is not None
        assert len(restored.signature.input_schema.features) == 2


# ---------------------------------------------------------------------------
# Stage transitions
# ---------------------------------------------------------------------------


class TestStageTransitions:
    """Tests for valid stage transition rules."""

    def test_all_stages_is_complete(self) -> None:
        assert ALL_STAGES == {"staging", "shadow", "production", "archived"}

    def test_staging_can_transition_to_shadow(self) -> None:
        assert "shadow" in VALID_TRANSITIONS["staging"]

    def test_production_cannot_transition_to_staging(self) -> None:
        assert "staging" not in VALID_TRANSITIONS["production"]

    def test_archived_can_only_go_to_staging(self) -> None:
        assert VALID_TRANSITIONS["archived"] == {"staging"}


# ---------------------------------------------------------------------------
# Artifact name validation
# ---------------------------------------------------------------------------


class TestValidateArtifactName:
    """Tests for _validate_artifact_name path traversal prevention."""

    def test_valid_name_passes(self) -> None:
        _validate_artifact_name("my_model")  # should not raise

    def test_path_separator_raises(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            _validate_artifact_name("../evil")

    def test_backslash_raises(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            _validate_artifact_name("a\\b")

    def test_forward_slash_raises(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            _validate_artifact_name("a/b")


# ---------------------------------------------------------------------------
# MLflow YAML helpers
# ---------------------------------------------------------------------------


class TestMLflowYaml:
    """Tests for _write_mlmodel_yaml and _read_mlmodel_yaml."""

    def test_write_mlmodel_yaml_contains_artifact_path(self) -> None:
        info = {"artifact_path": "model.pkl", "model_uuid": "abc"}
        yaml_str = _write_mlmodel_yaml(info)
        assert "model.pkl" in yaml_str
        assert "abc" in yaml_str

    def test_read_mlmodel_yaml_from_file(self, tmp_path) -> None:
        content = "artifact_path: model.pkl\nmodel_uuid: xyz\n"
        mlmodel_file = tmp_path / "MLmodel"
        mlmodel_file.write_text(content)
        result = _read_mlmodel_yaml(tmp_path)
        assert result.get("artifact_path") == "model.pkl"
