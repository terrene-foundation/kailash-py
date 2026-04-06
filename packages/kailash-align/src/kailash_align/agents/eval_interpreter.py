# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EvalInterpreterAgent -- interpret evaluation results and recommend next steps.

LLM-first: the Signature defines the reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-align[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["EvalInterpreterAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for alignment agents. "
            "Install with: pip install kailash-align[agents]"
        ) from exc


class EvalInterpreterAgent:
    """Interpret evaluation results and recommend next steps.

    The LLM receives eval metrics, training config used, and optional
    baseline comparison, then reasons about quality and improvement paths.
    Tools only fetch data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class EvalInterpreterSignature(Signature):
            """Interpret alignment evaluation results and recommend improvements."""

            eval_results: str = InputField(
                description="Evaluation metrics (per-task scores, aggregates)"
            )
            training_config: str = InputField(
                description="Training configuration used (method, hyperparameters, LoRA)"
            )
            baseline: str = InputField(
                description="Baseline model scores for comparison", default=""
            )

            interpretation: str = OutputField(
                description="What the results mean — strengths and weaknesses"
            )
            quality_verdict: str = OutputField(
                description="Overall quality verdict: deploy, iterate, or retrain"
            )
            next_steps: list = OutputField(
                description="Recommended next steps ranked by expected impact"
            )
            risks: str = OutputField(
                description="Deployment risks identified from eval results"
            )
            confidence: float = OutputField(
                description="Confidence in this interpretation (0-1)"
            )

        class _Agent(BaseAgent):
            signature = EvalInterpreterSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def interpret(
        self,
        eval_results: str,
        training_config: str,
        baseline: str = "",
    ) -> dict[str, Any]:
        """Run the interpreter and return analysis."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            eval_results=eval_results,
            training_config=training_config,
            baseline=baseline,
        )
        return dict(result)
