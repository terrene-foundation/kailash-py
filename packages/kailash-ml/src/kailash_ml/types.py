# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML type contracts — protocols and schemas for cross-framework interop.

This module is the single source of truth for ML interface contracts
shared between kailash-ml and kailash-kaizen. It replaces the former
kailash-ml-protocols package.

All types provide to_dict() / from_dict() round-trip serialization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MLToolProtocol(Protocol):
    """Tools that Kaizen agents call via MCP to access ML capabilities.

    Implementors: kailash-ml InferenceServer, ModelRegistry.
    Consumers: kailash-kaizen MCP tools, Delegate agents.
    """

    async def predict(
        self,
        model_name: str,
        features: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Single-record prediction.

        Returns {"prediction": ..., "probabilities": [...], "model_version": ...}.
        """
        ...

    async def get_metrics(
        self,
        model_name: str,
        version: str | None = None,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Model metrics.

        Returns {"metrics": {"accuracy": 0.95, ...}, "version": ..., "evaluated_at": ...}.
        """
        ...

    async def get_model_info(
        self,
        model_name: str,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Model metadata.

        Returns {"name": ..., "stage": ..., "versions": [...], "signature": ...}.
        """
        ...


@runtime_checkable
class AgentInfusionProtocol(Protocol):
    """Protocol for agent-augmented engine methods.

    Implementors: kailash-kaizen Delegate agents (via kailash-ml[agents]).
    Consumers: kailash-ml engines (AutoMLEngine, DataExplorer, FeatureEngineer, DriftMonitor).
    """

    async def suggest_model(
        self,
        data_profile: dict[str, Any],
        task_type: str,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Suggest model families.

        Returns {"candidates": [...], "reasoning": ..., "self_assessed_confidence": ...}.
        """
        ...

    async def suggest_features(
        self,
        data_profile: dict[str, Any],
        existing_features: list[str],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Suggest feature engineering.

        Returns {"proposed_features": [...], "interactions": [...], "drops": [...]}.
        """
        ...

    async def interpret_results(
        self,
        experiment_results: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Interpret experiment results.

        Returns {"interpretation": ..., "patterns": [...], "recommendations": [...]}.
        """
        ...

    async def interpret_drift(
        self,
        drift_report: dict[str, Any],
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """Interpret drift report.

        Returns {"assessment": ..., "root_cause": ..., "urgency": ..., "recommendation": ...}.
        """
        ...


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

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError(f"MetricSpec.value must be finite, got {self.value!r}")

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


__all__ = [
    "MLToolProtocol",
    "AgentInfusionProtocol",
    "FeatureField",
    "FeatureSchema",
    "ModelSignature",
    "MetricSpec",
]
