# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureEngineerAgent -- design and evaluate features for ML models.

LLM-first: Signature defines reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["FeatureEngineerAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class FeatureEngineerAgent:
    """Design and evaluate features for an ML model.

    The LLM reasons about which features to create, which to drop,
    and how to validate quality. Tools only fetch data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class FeatureEngineerSignature(Signature):
            """Design and evaluate features for an ML model."""

            data_profile: str = InputField(description="Statistical profile")
            target_description: str = InputField(description="What we are predicting")
            existing_features: str = InputField(
                description="Features already created", default=""
            )
            model_performance: str = InputField(
                description="Current model metrics", default=""
            )

            proposed_features: str = OutputField(
                description="List of proposed features with name, computation, rationale"
            )
            feature_interactions: str = OutputField(
                description="Promising interactions to explore"
            )
            features_to_drop: str = OutputField(
                description="Features to remove with rationale"
            )
            validation_plan: str = OutputField(
                description="How to validate feature quality"
            )
            confidence: float = OutputField(description="Confidence (0-1)")

        class _Agent(BaseAgent):
            sig = FeatureEngineerSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def suggest(
        self,
        data_profile: str,
        target_description: str,
        existing_features: str = "",
        model_performance: str = "",
    ) -> dict[str, Any]:
        """Get feature engineering suggestions from the LLM."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            data_profile=data_profile,
            target_description=target_description,
            existing_features=existing_features,
            model_performance=model_performance,
        )
        return {
            "proposed_features": result.proposed_features,
            "feature_interactions": result.feature_interactions,
            "features_to_drop": result.features_to_drop,
            "validation_plan": result.validation_plan,
            "confidence": result.confidence,
        }
