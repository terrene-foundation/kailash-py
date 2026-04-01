# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DriftAnalystAgent -- analyze model drift and determine action.

LLM-first: Signature defines reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-ml[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["DriftAnalystAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for ML agents. "
            "Install with: pip install kailash-ml[agents]"
        ) from exc


class DriftAnalystAgent:
    """Analyze model drift and determine if action is needed.

    The LLM receives drift reports and performance data, then reasons
    about whether drift is actionable, seasonal, or noise. Tools
    only fetch drift history and distribution data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class DriftAnalystSignature(Signature):
            """Analyze model drift and determine if action is needed."""

            drift_report: str = InputField(description="DriftMonitor output")
            historical_drift: str = InputField(
                description="Historical drift trends", default=""
            )
            model_performance: str = InputField(
                description="Current vs training metrics", default=""
            )
            domain_context: str = InputField(description="Domain info", default="")

            assessment: str = OutputField(description="Actionable, seasonal, or noise?")
            root_cause: str = OutputField(description="Likely cause of drift")
            impact: str = OutputField(description="Expected impact on predictions")
            recommendation: str = OutputField(
                description="retrain, monitor, investigate, or ignore"
            )
            urgency: str = OutputField(description="immediate, soon, routine, none")
            confidence: float = OutputField(description="Confidence (0-1)")

        class _Agent(BaseAgent):
            sig = DriftAnalystSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def analyze(
        self,
        drift_report: str,
        historical_drift: str = "",
        model_performance: str = "",
        domain_context: str = "",
    ) -> dict[str, Any]:
        """Get drift analysis from the LLM."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            drift_report=drift_report,
            historical_drift=historical_drift,
            model_performance=model_performance,
            domain_context=domain_context,
        )
        return {
            "assessment": result.assessment,
            "root_cause": result.root_cause,
            "impact": result.impact,
            "recommendation": result.recommendation,
            "urgency": result.urgency,
            "confidence": result.confidence,
        }
