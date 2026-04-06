# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""TrainingConfigAgent -- select hyperparameters, LoRA config, hardware.

LLM-first: the Signature defines the reasoning; tools are dumb data endpoints.
Requires ``pip install kailash-align[agents]``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["TrainingConfigAgent"]


def _import_kaizen():
    try:
        from kaizen.core import BaseAgent, InputField, OutputField, Signature

        return BaseAgent, Signature, InputField, OutputField
    except ImportError as exc:
        raise ImportError(
            "kailash-kaizen is required for alignment agents. "
            "Install with: pip install kailash-align[agents]"
        ) from exc


class TrainingConfigAgent:
    """Select hyperparameters, LoRA configuration, and hardware requirements.

    The LLM receives method, model info, GPU memory, and dataset size,
    then reasons about optimal training configuration.  Tools only fetch data.
    """

    def __init__(self, *, model: str | None = None) -> None:
        import os

        self._model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        self._agent: Any = None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent

        BaseAgent, Signature, InputField, OutputField = _import_kaizen()

        class TrainingConfigSignature(Signature):
            """Select optimal training hyperparameters and LoRA configuration."""

            training_method: str = InputField(
                description="Training method (SFT, DPO, GRPO, etc.)"
            )
            model_info: str = InputField(
                description="Base model metadata (name, parameter count, architecture)"
            )
            gpu_memory: str = InputField(
                description="Available GPU memory and hardware details"
            )
            dataset_size: str = InputField(
                description="Dataset size (rows, tokens, memory estimate)"
            )
            memory_estimate: str = InputField(
                description="Estimated training memory from estimate_training_memory()",
                default="",
            )

            hyperparameters: str = OutputField(
                description="Recommended hyperparameters (learning rate, batch size, epochs, warmup)"
            )
            lora_config: str = OutputField(
                description="LoRA configuration (rank, alpha, target modules, dropout)"
            )
            hardware_recommendation: str = OutputField(
                description="Hardware recommendation (GPU count, precision, gradient checkpointing)"
            )
            warnings: list = OutputField(
                description="Potential issues (OOM risk, slow convergence, instability)"
            )
            confidence: float = OutputField(
                description="Confidence in this configuration (0-1)"
            )

        class _Agent(BaseAgent):
            signature = TrainingConfigSignature

        self._agent = _Agent(model=self._model)
        return self._agent

    async def configure(
        self,
        training_method: str,
        model_info: str,
        gpu_memory: str,
        dataset_size: str,
        memory_estimate: str = "",
    ) -> dict[str, Any]:
        """Run the configurator and return training config."""
        agent = self._ensure_agent()
        result = await agent.run_async(
            training_method=training_method,
            model_info=model_info,
            gpu_memory=gpu_memory,
            dataset_size=dataset_size,
            memory_estimate=memory_estimate,
        )
        return dict(result)
