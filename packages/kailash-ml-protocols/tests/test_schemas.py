# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dataclass round-trip serialization tests for kailash-ml-protocols."""
from __future__ import annotations

from kailash_ml_protocols import (
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)


class TestFeatureField:
    """FeatureField serialization tests."""

    def test_round_trip_defaults(self) -> None:
        """FeatureField with defaults serializes and restores."""
        field = FeatureField(name="age", dtype="int64")
        restored = FeatureField.from_dict(field.to_dict())
        assert restored.name == "age"
        assert restored.dtype == "int64"
        assert restored.nullable is True
        assert restored.description == ""

    def test_round_trip_all_fields(self) -> None:
        """FeatureField with all fields set serializes and restores."""
        field = FeatureField(
            name="email", dtype="utf8", nullable=False, description="User email"
        )
        restored = FeatureField.from_dict(field.to_dict())
        assert restored.name == "email"
        assert restored.dtype == "utf8"
        assert restored.nullable is False
        assert restored.description == "User email"


class TestFeatureSchema:
    """FeatureSchema serialization tests."""

    def test_round_trip(self) -> None:
        """FeatureSchema serializes to dict and back without data loss."""
        schema = FeatureSchema(
            name="user_features",
            features=[
                FeatureField("age", "int64"),
                FeatureField("name", "utf8", nullable=False),
            ],
            entity_id_column="user_id",
            timestamp_column="created_at",
        )
        restored = FeatureSchema.from_dict(schema.to_dict())
        assert restored.name == schema.name
        assert len(restored.features) == 2
        assert restored.features[0].name == "age"
        assert restored.features[0].dtype == "int64"
        assert restored.features[1].nullable is False
        assert restored.entity_id_column == "user_id"
        assert restored.timestamp_column == "created_at"
        assert restored.version == 1

    def test_round_trip_no_timestamp(self) -> None:
        """FeatureSchema without timestamp_column serializes correctly."""
        schema = FeatureSchema(
            name="simple",
            features=[FeatureField("x", "float64")],
            entity_id_column="id",
        )
        restored = FeatureSchema.from_dict(schema.to_dict())
        assert restored.timestamp_column is None
        assert restored.version == 1

    def test_round_trip_custom_version(self) -> None:
        """FeatureSchema with custom version preserves it."""
        schema = FeatureSchema(
            name="v3_features",
            features=[FeatureField("a", "float64")],
            entity_id_column="id",
            version=3,
        )
        restored = FeatureSchema.from_dict(schema.to_dict())
        assert restored.version == 3


class TestModelSignature:
    """ModelSignature serialization tests."""

    def test_round_trip(self) -> None:
        """ModelSignature serializes to dict and back."""
        sig = ModelSignature(
            input_schema=FeatureSchema(
                name="input",
                features=[
                    FeatureField("feature_a", "float64"),
                    FeatureField("feature_b", "float64"),
                ],
                entity_id_column="entity_id",
            ),
            output_columns=["prediction", "probability"],
            output_dtypes=["int64", "float64"],
            model_type="classifier",
        )
        restored = ModelSignature.from_dict(sig.to_dict())
        assert restored.model_type == "classifier"
        assert restored.output_columns == ["prediction", "probability"]
        assert restored.output_dtypes == ["int64", "float64"]
        assert restored.input_schema.name == "input"
        assert len(restored.input_schema.features) == 2

    def test_round_trip_regressor(self) -> None:
        """ModelSignature with regressor type serializes correctly."""
        sig = ModelSignature(
            input_schema=FeatureSchema(
                name="reg_input",
                features=[FeatureField("x", "float64")],
                entity_id_column="id",
            ),
            output_columns=["value"],
            output_dtypes=["float64"],
            model_type="regressor",
        )
        restored = ModelSignature.from_dict(sig.to_dict())
        assert restored.model_type == "regressor"


class TestMetricSpec:
    """MetricSpec serialization tests."""

    def test_round_trip_defaults(self) -> None:
        """MetricSpec with defaults serializes and restores."""
        metric = MetricSpec(name="accuracy", value=0.95)
        restored = MetricSpec.from_dict(metric.to_dict())
        assert restored.name == "accuracy"
        assert restored.value == 0.95
        assert restored.split == "test"
        assert restored.higher_is_better is True

    def test_round_trip_all_fields(self) -> None:
        """MetricSpec with all fields set serializes and restores."""
        metric = MetricSpec(
            name="rmse", value=0.032, split="val", higher_is_better=False
        )
        restored = MetricSpec.from_dict(metric.to_dict())
        assert restored.name == "rmse"
        assert restored.value == 0.032
        assert restored.split == "val"
        assert restored.higher_is_better is False

    def test_round_trip_zero_value(self) -> None:
        """MetricSpec with zero value serializes correctly."""
        metric = MetricSpec(name="loss", value=0.0, higher_is_better=False)
        restored = MetricSpec.from_dict(metric.to_dict())
        assert restored.value == 0.0
