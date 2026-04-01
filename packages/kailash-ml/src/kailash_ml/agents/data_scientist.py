# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataScientistAgent -- analyze datasets and formulate ML strategy.

LLM-first: the Signature defines the reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["DataScientistAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class DataScientistAgent:
    """Analyze a dataset and formulate an ML strategy.

    The LLM receives the data profile and reasons about the best approach.
    Tools only fetch data -- all reasoning happens in the Signature.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class DataScientistSignature(Signature):
            """Analyze a dataset and formulate an ML strategy."""

            data_profile: str = InputField(
                description="Statistical profile from DataExplorer"
            )
            business_context: str = InputField(
                description="What problem is being solved", default=""
            )
            constraints: str = InputField(
                description="Time, compute, or accuracy constraints", default=""
            )

            data_assessment: str = OutputField(
                description="Data quality, volume, suitability assessment"
            )
            recommended_approach: str = OutputField(
                description="Recommended ML approach with rationale"
            )
            risks: str = OutputField(
                description="Data risks: leakage, bias, insufficient volume, class imbalance"
            )
            feature_hypotheses: list = OutputField(
                description="Hypotheses about useful features"
            )
            preprocessing_plan: str = OutputField(
                description="Recommended preprocessing steps"
            )
            confidence: float = OutputField(
                description="Confidence in this recommendation (0-1)"
            )

        class _Agent(BaseAgent):
            sig = DataScientistSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def analyze(
        self,
        data_profile: str,
        business_context: str = "",
        constraints: str = "",
    ) -> dict[str, Any]:
        """Run the DataScientist analysis.

        Returns the LLM's assessment, approach, risks, feature hypotheses,
        preprocessing plan, and confidence score.
        """
        agent = self._ensure_agent()
        result = await agent.run_async(
            data_profile=data_profile,
            business_context=business_context,
            constraints=constraints,
        )
        return {
            "data_assessment": result.data_assessment,
            "recommended_approach": result.recommended_approach,
            "risks": result.risks,
            "feature_hypotheses": result.feature_hypotheses,
            "preprocessing_plan": result.preprocessing_plan,
            "confidence": result.confidence,
        }
