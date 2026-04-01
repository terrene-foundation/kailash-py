# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ModelSelectorAgent -- select candidate models for an ML task.

LLM-first: Signature defines reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["ModelSelectorAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class ModelSelectorAgent:
    """Select candidate models for an ML task.

    The LLM reasons about data characteristics, constraints, and prior
    results to recommend models. Tools only fetch metadata.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class ModelSelectorSignature(Signature):
            """Select candidate models for an ML task."""

            data_characteristics: str = InputField(description="Data profile summary")
            task_type: str = InputField(
                description="classification, regression, time_series, clustering"
            )
            constraints: str = InputField(
                description="Latency, memory, interpretability requirements",
                default="",
            )
            previous_results: str = InputField(
                description="Prior experiment results", default=""
            )

            candidate_models: str = OutputField(
                description="Ranked models with rationale and hyperparameter hints"
            )
            expected_performance: str = OutputField(
                description="Expected metric ranges"
            )
            experiment_plan: str = OutputField(
                description="Order and strategy for evaluating candidates"
            )
            confidence: float = OutputField(description="Confidence (0-1)")

        class _Agent(BaseAgent):
            sig = ModelSelectorSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def select(
        self,
        data_characteristics: str,
        task_type: str,
        constraints: str = "",
        previous_results: str = "",
    ) -> dict[str, Any]:
        """Get model selection recommendations from the LLM."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            data_characteristics=data_characteristics,
            task_type=task_type,
            constraints=constraints,
            previous_results=previous_results,
        )
        return {
            "candidate_models": result.candidate_models,
            "expected_performance": result.expected_performance,
            "experiment_plan": result.experiment_plan,
            "confidence": result.confidence,
        }
