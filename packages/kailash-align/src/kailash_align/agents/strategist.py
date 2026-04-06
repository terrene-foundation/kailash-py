# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AlignmentStrategistAgent -- reason about base model, method, and data needs.

LLM-first: the Signature defines the reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-align[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["AlignmentStrategistAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for alignment agents. "
            "Install with: pip install kailash-align[agents]"
        ) from exc


class AlignmentStrategistAgent:
    """Reason about base model selection, training method, and data requirements.

    The LLM receives model info, dataset summary, and constraints, then
    reasons about the best alignment strategy.  Tools only fetch data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class StrategistSignature(Signature):
            """Recommend an alignment strategy for a given model and dataset."""

            base_model_info: str = InputField(
                description="Base model metadata (name, size, architecture)"
            )
            dataset_summary: str = InputField(
                description="Dataset statistics (size, columns, quality metrics)"
            )
            constraints: str = InputField(
                description="Hardware, budget, time, or quality constraints",
                default="",
            )
            available_methods: str = InputField(
                description="List of supported training methods", default=""
            )

            method_recommendation: str = OutputField(
                description="Recommended training method (SFT, DPO, GRPO, etc.) with rationale"
            )
            base_model_assessment: str = OutputField(
                description="Assessment of the base model's suitability"
            )
            data_requirements: str = OutputField(
                description="Data preparation steps needed before training"
            )
            risks: str = OutputField(
                description="Risks: data quality, model capacity, training instability"
            )
            confidence: float = OutputField(
                description="Confidence in this recommendation (0-1)"
            )

        class _Agent(BaseAgent):
            signature = StrategistSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def recommend(
        self,
        base_model_info: str,
        dataset_summary: str,
        constraints: str = "",
        available_methods: str = "",
    ) -> dict[str, Any]:
        """Run the strategist and return recommendations."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            base_model_info=base_model_info,
            dataset_summary=dataset_summary,
            constraints=constraints,
            available_methods=available_methods,
        )
        return dict(result)
