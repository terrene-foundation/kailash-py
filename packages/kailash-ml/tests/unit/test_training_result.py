# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for kailash_ml._result.TrainingResult.

Specs: specs/ml-engines.md §4 (TrainingResult dataclass contract).
"""
from __future__ import annotations

import pytest
from kailash_ml import TrainingResult

REQUIRED_FIELDS = {
    "model_uri",
    "metrics",
    "device_used",
    "accelerator",
    "precision",
    "elapsed_seconds",
    "tracker_run_id",
    "tenant_id",
    "artifact_uris",
    "lightning_trainer_config",
}


def _valid_kwargs() -> dict:
    return dict(
        model_uri="registry://churn/42",
        metrics={"accuracy": 0.95, "f1": 0.90},
        device_used="cuda:0",
        accelerator="cuda",
        precision="bf16-mixed",
        elapsed_seconds=12.5,
        tracker_run_id="run-abc",
        tenant_id="acme",
        artifact_uris={"onnx": "s3://bucket/churn.onnx"},
        lightning_trainer_config={"max_epochs": 10, "devices": 1},
    )


class TestTrainingResultConstruction:
    """Basic dataclass shape + field presence."""

    def test_all_required_fields_present(self):
        """TrainingResult MUST have all 10 fields per spec §4."""
        r = TrainingResult(**_valid_kwargs())
        for field_name in REQUIRED_FIELDS:
            assert hasattr(r, field_name), f"missing field: {field_name}"

    def test_construction_with_all_fields(self):
        """Full valid construction succeeds."""
        r = TrainingResult(**_valid_kwargs())
        assert r.model_uri == "registry://churn/42"
        assert r.metrics["accuracy"] == 0.95
        assert r.device_used == "cuda:0"

    def test_frozen_dataclass_rejects_mutation(self):
        """TrainingResult MUST be frozen — post-construction mutation blocked."""
        r = TrainingResult(**_valid_kwargs())
        with pytest.raises((AttributeError, TypeError, Exception)):
            r.model_uri = "other"  # type: ignore[misc]


class TestTrainingResultSerialization:
    """to_dict / from_dict round-trip per EATP convention."""

    def test_to_dict_includes_required_fields(self):
        """to_dict output carries every required field."""
        r = TrainingResult(**_valid_kwargs())
        data = r.to_dict()
        for field_name in REQUIRED_FIELDS:
            assert field_name in data, f"to_dict missing: {field_name}"

    def test_round_trip_preserves_fields(self):
        """from_dict(to_dict(r)) returns an equivalent result."""
        r = TrainingResult(**_valid_kwargs())
        data = r.to_dict()
        r2 = TrainingResult.from_dict(data)
        assert r2.model_uri == r.model_uri
        assert r2.metrics == r.metrics
        assert r2.device_used == r.device_used
        assert r2.accelerator == r.accelerator
        assert r2.precision == r.precision

    def test_tenant_id_none_serializes(self):
        """Optional tenant_id=None serializes cleanly."""
        kwargs = _valid_kwargs()
        kwargs["tenant_id"] = None
        r = TrainingResult(**kwargs)
        data = r.to_dict()
        r2 = TrainingResult.from_dict(data)
        assert r2.tenant_id is None


class TestTrainingResultValidation:
    """__post_init__ validation."""

    def test_negative_elapsed_rejected(self):
        """elapsed_seconds must be non-negative."""
        kwargs = _valid_kwargs()
        kwargs["elapsed_seconds"] = -1.0
        with pytest.raises((ValueError, Exception)):
            TrainingResult(**kwargs)
