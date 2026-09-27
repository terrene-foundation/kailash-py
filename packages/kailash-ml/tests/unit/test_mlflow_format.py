# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for MLflow format reader and writer."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


@dataclass
class _FakeMetric:
    name: str
    value: float


@dataclass
class _FakeSignature:
    input_schema: Any
    output_columns: list[str] = field(default_factory=lambda: ["prediction"])
    output_dtypes: list[str] = field(default_factory=lambda: ["float64"])
    model_type: str = "classifier"


@dataclass
class _FakeFeatureSchema:
    features: list[Any] = field(default_factory=list)


@dataclass
class _FakeFeature:
    name: str
    dtype: str


@dataclass
class _FakeModelVersion:
    name: str = "test-model"
    version: int = 1
    model_uuid: str = "uuid-123"
    metrics: list[_FakeMetric] = field(default_factory=list)
    signature: _FakeSignature | None = None
    created_at: str = "2026-04-01T00:00:00"
    onnx_status: str = "success"


class TestMlflowFormatWriter:
    def test_write_creates_directory(self, tmp_path):
        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        writer = MlflowFormatWriter()
        out = tmp_path / "model_out"
        mv = _FakeModelVersion()
        writer.write(mv, out)
        assert out.exists()
        assert (out / "MLmodel").exists()
        assert (out / "requirements.txt").exists()

    def test_write_mlmodel_yaml(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        writer = MlflowFormatWriter()
        mv = _FakeModelVersion(
            name="my-model",
            model_uuid="abc-123",
            metrics=[_FakeMetric("accuracy", 0.95), _FakeMetric("f1", 0.92)],
            created_at="2026-04-01T12:00:00",
        )
        out = tmp_path / "model_out"
        writer.write(mv, out)

        with open(out / "MLmodel") as f:
            mlmodel = yaml.safe_load(f)

        assert mlmodel["model_uuid"] == "abc-123"
        assert mlmodel["run_id"] == "my-model"
        assert "flavors" in mlmodel
        assert "python_function" in mlmodel["flavors"]
        assert len(mlmodel["metrics"]) == 2
        assert mlmodel["metrics"][0]["name"] == "accuracy"
        assert mlmodel["utc_time_created"] == "2026-04-01T12:00:00"

    def test_write_with_artifact(self, tmp_path):
        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        writer = MlflowFormatWriter()
        mv = _FakeModelVersion()
        out = tmp_path / "model_out"
        artifact = b"fake-model-bytes"
        writer.write(mv, out, artifact_data=artifact)
        assert (out / "model.pkl").read_bytes() == artifact

    def test_write_with_signature(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        schema = _FakeFeatureSchema(
            features=[
                _FakeFeature("age", "float64"),
                _FakeFeature("income", "int64"),
            ]
        )
        sig = _FakeSignature(input_schema=schema)
        mv = _FakeModelVersion(signature=sig)
        out = tmp_path / "model_out"

        writer = MlflowFormatWriter()
        writer.write(mv, out)

        with open(out / "MLmodel") as f:
            mlmodel = yaml.safe_load(f)

        assert "signature" in mlmodel
        inputs = json.loads(mlmodel["signature"]["inputs"])
        assert len(inputs) == 2
        assert inputs[0]["name"] == "age"
        assert inputs[0]["type"] == "double"  # float64 -> double
        assert inputs[1]["type"] == "long"  # int64 -> long

    def test_requirements_txt(self, tmp_path):
        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        writer = MlflowFormatWriter()
        out = tmp_path / "model_out"
        writer.write(_FakeModelVersion(), out)
        reqs = (out / "requirements.txt").read_text()
        assert "kailash-ml" in reqs

    def test_write_idempotent(self, tmp_path):
        from kailash_ml.compat.mlflow_format import MlflowFormatWriter

        writer = MlflowFormatWriter()
        out = tmp_path / "model_out"
        mv = _FakeModelVersion()
        writer.write(mv, out)
        writer.write(mv, out)  # should not raise
        assert (out / "MLmodel").exists()


class TestMlflowFormatReader:
    def _write_mlmodel(self, path: Path, content: dict) -> None:
        import yaml

        path.mkdir(parents=True, exist_ok=True)
        with open(path / "MLmodel") as f:
            pass  # ensure dir exists
        with open(path / "MLmodel", "w") as f:
            yaml.dump(content, f)

    def test_read_basic(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        mlmodel = {
            "artifact_path": "model",
            "flavors": {
                "sklearn": {"sklearn_version": "1.4.0", "pickled_model": "model.pkl"}
            },
            "run_id": "imported-model",
            "model_uuid": "uuid-abc",
        }
        with open(model_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f)

        reader = MlflowFormatReader()
        result = reader.read(model_dir)
        assert result["framework"] == "sklearn"
        assert result["experiment_name"] == "imported-model"
        assert result["mlflow_model_uuid"] == "uuid-abc"

    def test_read_missing_mlmodel(self, tmp_path):
        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        reader = MlflowFormatReader()
        with pytest.raises(FileNotFoundError, match="No MLmodel"):
            reader.read(tmp_path)

    def test_read_with_signature(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        inputs = [{"name": "age", "type": "double"}, {"name": "city", "type": "string"}]
        mlmodel = {
            "artifact_path": "model",
            "flavors": {"python_function": {}},
            "signature": {
                "inputs": json.dumps(inputs),
                "outputs": json.dumps([{"name": "label", "type": "long"}]),
            },
        }
        with open(model_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f)

        reader = MlflowFormatReader()
        result = reader.read(model_dir)
        sig = result["signature"]
        assert sig is not None
        assert len(sig["inputs"]) == 2
        assert sig["inputs"][0]["name"] == "age"
        assert sig["inputs"][0]["dtype"] == "float64"  # double -> float64

    def test_read_with_metrics(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        mlmodel = {
            "artifact_path": "model",
            "flavors": {"python_function": {}},
            "metrics": [
                {"name": "accuracy", "value": 0.95},
                {"name": "f1", "value": 0.88},
            ],
        }
        with open(model_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f)

        reader = MlflowFormatReader()
        result = reader.read(model_dir)
        assert len(result["metrics"]) == 2
        assert result["metrics"][0]["name"] == "accuracy"

    def test_detect_lightgbm_framework(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        mlmodel = {
            "artifact_path": "model",
            "flavors": {"lightgbm": {"lgb_version": "4.3.0"}},
        }
        with open(model_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f)

        reader = MlflowFormatReader()
        result = reader.read(model_dir)
        assert result["framework"] == "lightgbm"

    def test_malformed_signature_handled(self, tmp_path):
        import yaml

        from kailash_ml.compat.mlflow_format import MlflowFormatReader

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        mlmodel = {
            "artifact_path": "model",
            "flavors": {"python_function": {}},
            "signature": {"inputs": "not valid json{{{"},
        }
        with open(model_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f)

        reader = MlflowFormatReader()
        result = reader.read(model_dir)
        # Should not raise, should return None or empty signature
        assert result["signature"] is None or result["signature"] == {}


class TestRoundTrip:
    """Test write -> read roundtrip preserves metadata."""

    def test_write_then_read(self, tmp_path):
        from kailash_ml.compat.mlflow_format import (
            MlflowFormatReader,
            MlflowFormatWriter,
        )

        schema = _FakeFeatureSchema(
            features=[_FakeFeature("temp", "float64"), _FakeFeature("hour", "int32")]
        )
        sig = _FakeSignature(input_schema=schema)
        mv = _FakeModelVersion(
            name="roundtrip-model",
            model_uuid="rt-uuid",
            metrics=[_FakeMetric("rmse", 12.5)],
            signature=sig,
            created_at="2026-04-01T10:00:00",
        )

        out = tmp_path / "model_out"
        MlflowFormatWriter().write(mv, out, artifact_data=b"model-bytes")

        result = MlflowFormatReader().read(out)
        assert result["experiment_name"] == "roundtrip-model"
        assert result["mlflow_model_uuid"] == "rt-uuid"
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["value"] == 12.5
        assert result["signature"] is not None
        assert len(result["signature"]["inputs"]) == 2
