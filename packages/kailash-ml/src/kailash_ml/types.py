# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML type contracts — schemas and protocols for kailash-ml engines.

All types provide to_dict() / from_dict() round-trip serialization.
Protocols define interfaces for cross-framework interop (e.g., Kaizen agents
calling ML tools).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


@dataclass
class FeatureField:
    """Single feature column definition."""

    name: str
    dtype: str  # "int64", "float64", "utf8", "bool", "datetime", "categorical"
    nullable: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureField:
        return cls(**data)


@dataclass
class FeatureSchema:
    """Schema for a feature set."""

    name: str
    features: list[FeatureField]
    entity_id_column: str
    timestamp_column: str | None = None
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "features": [f.to_dict() for f in self.features],
            "entity_id_column": self.entity_id_column,
            "timestamp_column": self.timestamp_column,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureSchema:
        return cls(
            name=data["name"],
            features=[FeatureField.from_dict(f) for f in data["features"]],
            entity_id_column=data["entity_id_column"],
            timestamp_column=data.get("timestamp_column"),
            version=data.get("version", 1),
        )


@dataclass
class ModelSignature:
    """Input/output schema for a trained model."""

    input_schema: FeatureSchema
    output_columns: list[str]
    output_dtypes: list[str]
    model_type: str  # "classifier", "regressor", "ranker"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_schema": self.input_schema.to_dict(),
            "output_columns": self.output_columns,
            "output_dtypes": self.output_dtypes,
            "model_type": self.model_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelSignature:
        return cls(
            input_schema=FeatureSchema.from_dict(data["input_schema"]),
            output_columns=data["output_columns"],
            output_dtypes=data["output_dtypes"],
            model_type=data["model_type"],
        )


@dataclass
class MetricSpec:
    """A single evaluation metric with its value."""

    name: str  # "accuracy", "f1", "rmse", "auc", etc.
    value: float
    split: str = "test"  # "train", "val", "test"
    higher_is_better: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "split": self.split,
            "higher_is_better": self.higher_is_better,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricSpec:
        return cls(**data)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MLToolProtocol(Protocol):
    """Tools that Kaizen agents call to access ML capabilities.

    Implementors: kailash-ml InferenceServer, ModelRegistry.
    Consumers: Kaizen MCP tools, Delegate agents.
    """

    async def predict(
        self,
        model_name: str,
        features: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...

    async def get_metrics(
        self,
        model_name: str,
        version: str | None = None,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...

    async def get_model_info(
        self,
        model_name: str,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class AgentInfusionProtocol(Protocol):
    """Protocol for agent-augmented engine methods.

    Implementors: Kaizen Delegate agents (via kailash-ml[agents]).
    Consumers: kailash-ml engines (AutoMLEngine, DataExplorer, etc.).
    """

    async def suggest_model(
        self,
        data_profile: dict[str, Any],
        task_type: str,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...

    async def suggest_features(
        self,
        data_profile: dict[str, Any],
        existing_features: list[str],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...

    async def interpret_results(
        self,
        experiment_results: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...

    async def interpret_drift(
        self,
        drift_report: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]: ...


__all__ = [
    "FeatureField",
    "FeatureSchema",
    "ModelSignature",
    "MetricSpec",
    "MLToolProtocol",
    "AgentInfusionProtocol",
]
