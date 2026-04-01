# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""vLLM integration for online RL rollout generation.

Used by GRPO, RLOO, and Online DPO methods for fast batch generation.
vLLM is an OPTIONAL dependency ([online] extra). When not installed,
online methods fall back to HuggingFace generate() (slower but works
on any hardware including Apple Silicon).

NOTE (R2-03): vLLM requires CUDA. Not recommended for Apple Silicon.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any, Optional

from kailash_align.exceptions import AlignmentError

logger = logging.getLogger(__name__)

__all__ = [
    "VLLMBackend",
    "VLLMConfig",
    "GenerationBackend",
    "HFGenerationBackend",
]


class GenerationBackendError(AlignmentError):
    """Raised when generation backend fails."""

    pass


@dataclass(frozen=True)
class VLLMConfig:
    """Configuration for vLLM generation backend.

    Args:
        tensor_parallel_size: Number of GPUs for tensor parallelism.
        gpu_memory_utilization: Fraction of GPU memory to use (0.0-1.0).
        max_model_len: Maximum model context length.
        dtype: Data type for vLLM ('auto', 'float16', 'bfloat16').
        seed: Random seed for reproducibility.
    """

    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9
    max_model_len: Optional[int] = None
    dtype: str = "auto"
    seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.gpu_memory_utilization <= 1.0:
            raise ValueError(
                f"gpu_memory_utilization must be in (0, 1], "
                f"got {self.gpu_memory_utilization}"
            )
        if self.tensor_parallel_size < 1:
            raise ValueError(
                f"tensor_parallel_size must be >= 1, "
                f"got {self.tensor_parallel_size}"
            )


class GenerationBackend(abc.ABC):
    """Abstract base for generation backends used by online RL methods.

    Subclasses implement batch_generate() for fast rollout generation.
    The backend is passed to online trainers (GRPO, RLOO) for generating
    completions that are then scored by reward functions.
    """

    @abc.abstractmethod
    def batch_generate(
        self,
        prompts: list[str],
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        num_return_sequences: int = 1,
    ) -> list[list[str]]:
        """Generate completions for a batch of prompts.

        Args:
            prompts: List of prompts to generate from.
            max_new_tokens: Maximum new tokens per completion.
            temperature: Sampling temperature.
            top_p: Top-p (nucleus) sampling threshold.
            num_return_sequences: Number of completions per prompt.

        Returns:
            List of lists: outer = per prompt, inner = completions.
        """

    def shutdown(self) -> None:
        """Clean up resources."""
        pass


class VLLMBackend(GenerationBackend):
    """vLLM-based generation backend for fast batch generation.

    Requires [online] extra: pip install kailash-align[online]

    Args:
        model_id: HuggingFace model ID or local path.
        config: VLLMConfig with generation parameters.
    """

    def __init__(
        self,
        model_id: str,
        config: Optional[VLLMConfig] = None,
    ) -> None:
        self._model_id = model_id
        self._config = config or VLLMConfig()
        self._llm: Any = None

    def _ensure_loaded(self) -> None:
        """Lazy-load the vLLM LLM instance."""
        if self._llm is not None:
            return

        try:
            from vllm import LLM, SamplingParams  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "vLLM is required for online RL methods. "
                "Install with: pip install kailash-align[online]\n"
                "NOTE: vLLM requires CUDA. For Apple Silicon, use "
                "HFGenerationBackend instead."
            ) from exc

        logger.info("Loading vLLM model: %s", self._model_id)
        self._llm = LLM(
            model=self._model_id,
            tensor_parallel_size=self._config.tensor_parallel_size,
            gpu_memory_utilization=self._config.gpu_memory_utilization,
            max_model_len=self._config.max_model_len,
            dtype=self._config.dtype,
            seed=self._config.seed,
            trust_remote_code=False,
        )
        logger.info("vLLM model loaded: %s", self._model_id)

    def batch_generate(
        self,
        prompts: list[str],
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        num_return_sequences: int = 1,
    ) -> list[list[str]]:
        """Generate completions using vLLM's optimized inference engine."""
        self._ensure_loaded()
        from vllm import SamplingParams

        params = SamplingParams(
            max_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            n=num_return_sequences,
        )

        outputs = self._llm.generate(prompts, params)

        results: list[list[str]] = []
        for output in outputs:
            completions = [o.text for o in output.outputs]
            results.append(completions)
        return results

    def shutdown(self) -> None:
        """Release vLLM resources."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            logger.info("vLLM backend shut down")


class HFGenerationBackend(GenerationBackend):
    """HuggingFace transformers-based generation backend.

    Fallback for when vLLM is not available (e.g., Apple Silicon, CPU).
    Slower than vLLM but works everywhere transformers works.

    Args:
        model_id: HuggingFace model ID or local path.
        device: Device string ('cuda', 'mps', 'cpu'). None = auto-detect.
    """

    def __init__(
        self,
        model_id: str,
        device: Optional[str] = None,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._model: Any = None
        self._tokenizer: Any = None

    def _ensure_loaded(self) -> None:
        """Lazy-load the model and tokenizer."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = self._device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        logger.info("Loading HF model: %s (device=%s)", self._model_id, device)
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_id, trust_remote_code=False
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            torch_dtype=torch.bfloat16 if device != "cpu" else torch.float32,
            device_map=device,
            trust_remote_code=False,
        )
        self._model.eval()
        logger.info("HF model loaded: %s", self._model_id)

    def batch_generate(
        self,
        prompts: list[str],
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.95,
        num_return_sequences: int = 1,
    ) -> list[list[str]]:
        """Generate completions using HuggingFace generate()."""
        import torch

        self._ensure_loaded()

        results: list[list[str]] = []
        for prompt in prompts:
            inputs = self._tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=2048
            )
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=max(temperature, 1e-7),
                    top_p=top_p,
                    num_return_sequences=num_return_sequences,
                    do_sample=temperature > 0,
                    pad_token_id=self._tokenizer.pad_token_id,
                )

            completions: list[str] = []
            for output in outputs:
                text = self._tokenizer.decode(
                    output[inputs["input_ids"].shape[1] :],
                    skip_special_tokens=True,
                )
                completions.append(text)
            results.append(completions)

        return results

    def shutdown(self) -> None:
        """Release model resources."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        logger.info("HF generation backend shut down")
