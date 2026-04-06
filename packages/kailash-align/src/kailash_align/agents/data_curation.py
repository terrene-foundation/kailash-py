# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataCurationAgent -- evaluate dataset quality and recommend curation.

LLM-first: the Signature defines the reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-align[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["DataCurationAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for alignment agents. "
            "Install with: pip install kailash-align[agents]"
        ) from exc


class DataCurationAgent:
    """Evaluate dataset quality and recommend curation strategies.

    The LLM receives dataset stats and preference quality metrics, then
    reasons about gaps and improvements.  Tools only fetch data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class DataCurationSignature(Signature):
            """Evaluate dataset quality and recommend curation strategies."""

            dataset_stats: str = InputField(
                description="Dataset statistics (row count, column types, distributions)"
            )
            preference_quality: str = InputField(
                description="Preference pair quality metrics (length ratio, diversity, consistency)",
                default="",
            )
            training_method: str = InputField(
                description="Target training method (SFT, DPO, etc.)", default=""
            )

            curation_strategy: str = OutputField(
                description="Recommended data curation steps"
            )
            quality_assessment: str = OutputField(
                description="Overall dataset quality assessment"
            )
            gaps: list = OutputField(
                description="Identified data gaps or quality issues"
            )
            augmentation_suggestions: str = OutputField(
                description="Data augmentation or synthetic data suggestions"
            )
            confidence: float = OutputField(
                description="Confidence in this assessment (0-1)"
            )

        class _Agent(BaseAgent):
            signature = DataCurationSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def evaluate(
        self,
        dataset_stats: str,
        preference_quality: str = "",
        training_method: str = "",
    ) -> dict[str, Any]:
        """Run the curator and return quality assessment."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            dataset_stats=dataset_stats,
            preference_quality=preference_quality,
            training_method=training_method,
        )
        return dict(result)
