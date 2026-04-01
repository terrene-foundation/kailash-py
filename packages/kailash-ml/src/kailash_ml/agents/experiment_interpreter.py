# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ExperimentInterpreterAgent -- interpret ML experiment results.

LLM-first: Signature defines reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["ExperimentInterpreterAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class ExperimentInterpreterAgent:
    """Interpret ML experiment results and recommend next steps.

    The LLM analyzes trial results, finds patterns, explains failures,
    and recommends next steps. Tools only fetch trial data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class ExperimentInterpreterSignature(Signature):
            """Interpret ML experiment results and recommend next steps."""

            experiment_results: str = InputField(
                description="All trial results: model, params, metrics"
            )
            experiment_goal: str = InputField(description="What success looks like")
            data_context: str = InputField(
                description="Brief data description", default=""
            )

            interpretation: str = OutputField(description="What the results tell us")
            patterns: str = OutputField(description="Patterns across trials")
            failure_analysis: str = OutputField(description="Why poor configs failed")
            recommendations: str = OutputField(description="Specific next steps")
            confidence_assessment: str = OutputField(
                description="Confidence in best result"
            )
            confidence: float = OutputField(description="Confidence (0-1)")

        class _Agent(BaseAgent):
            sig = ExperimentInterpreterSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def interpret(
        self,
        experiment_results: str,
        experiment_goal: str,
        data_context: str = "",
    ) -> dict[str, Any]:
        """Get experiment interpretation from the LLM."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            experiment_results=experiment_results,
            experiment_goal=experiment_goal,
            data_context=data_context,
        )
        return {
            "interpretation": result.interpretation,
            "patterns": result.patterns,
            "failure_analysis": result.failure_analysis,
            "recommendations": result.recommendations,
            "confidence_assessment": result.confidence_assessment,
            "confidence": result.confidence,
        }
