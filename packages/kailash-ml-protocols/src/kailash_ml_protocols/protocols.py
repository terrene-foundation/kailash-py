# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Frozen protocol definitions for kailash-ml / kailash-kaizen interop.

These signatures are permanent -- methods cannot be removed in v1.x
without breaking all consumers. Additive changes (new methods) are safe.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


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
