# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RetrainingDecisionAgent -- decide whether to retrain based on drift.

LLM-first: Signature defines reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["RetrainingDecisionAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class RetrainingDecisionAgent:
    """Decide whether to retrain based on drift and performance.

    The LLM weighs drift severity, current performance, training cost,
    and business impact to make a retraining decision. Tools only
    fetch model versions and trigger retraining.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class RetrainingDecisionSignature(Signature):
            """Decide whether to retrain based on drift and performance."""

            drift_assessment: str = InputField(description="From DriftAnalystAgent")
            current_performance: str = InputField(
                description="Current accuracy metrics"
            )
            training_cost: str = InputField(
                description="Estimated time and compute", default=""
            )
            business_impact: str = InputField(
                description="Cost of prediction errors", default=""
            )

            decision: str = OutputField(
                description="retrain_now, schedule_retrain, continue_monitoring, or no_action"
            )
            rationale: str = OutputField(description="Why this decision")
            retrain_spec: str = OutputField(
                description="Data window, features, hyperparameter changes"
            )
            fallback_plan: str = OutputField(
                description="What to do if retraining fails"
            )
            confidence: float = OutputField(description="Confidence (0-1)")

        class _Agent(BaseAgent):
            sig = RetrainingDecisionSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def decide(
        self,
        drift_assessment: str,
        current_performance: str,
        training_cost: str = "",
        business_impact: str = "",
    ) -> dict[str, Any]:
        """Get retraining decision from the LLM."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            drift_assessment=drift_assessment,
            current_performance=current_performance,
            training_cost=training_cost,
            business_impact=business_impact,
        )
        return {
            "decision": result.decision,
            "rationale": result.rationale,
            "retrain_spec": result.retrain_spec,
            "fallback_plan": result.fallback_plan,
            "confidence": result.confidence,
        }
