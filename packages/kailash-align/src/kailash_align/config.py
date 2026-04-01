# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Configuration dataclasses for kailash-align."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "AlignmentConfig",
    "LoRAConfig",
    "SFTConfig",
    "DPOConfig",
    "AdapterSignature",
    "ServingConfig",
    "EvalConfig",
    "OnPremConfig",
    "QUICK_TASKS",
    "STANDARD_TASKS",
]


def _validate_finite(value: float, name: str) -> None:
    """Validate that a numeric value is finite (not NaN or Inf)."""
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")


def _validate_positive(value: float, name: str) -> None:
    """Validate that a numeric value is positive."""
    _validate_finite(value, name)
    if value is not None and value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


@dataclass(frozen=True)
class LoRAConfig:
    """LoRA adapter configuration.

    Args:
        rank: LoRA rank (r). Higher values = more parameters, more capacity.
        alpha: LoRA alpha scaling factor. Commonly 2x rank.
        target_modules: Model modules to apply LoRA to.
        dropout: Dropout probability for LoRA layers.
        bias: Bias training mode: 'none', 'all', or 'lora_only'.
        task_type: PEFT task type. Always 'CAUSAL_LM' for alignment.
    """

    rank: int = 16
    alpha: int = 32
    target_modules: tuple[str, ...] = ("q_proj", "v_proj", "k_proj", "o_proj")
    dropout: float = 0.05
    bias: str = "none"
    task_type: str = "CAUSAL_LM"

    def __post_init__(self) -> None:
        if not math.isfinite(self.rank):
            raise ValueError(f"rank must be finite, got {self.rank}")
        if self.rank < 1:
            raise ValueError(f"rank must be >= 1, got {self.rank}")
        if not math.isfinite(self.alpha):
            raise ValueError(f"alpha must be finite, got {self.alpha}")
        if self.alpha < 1:
            raise ValueError(f"alpha must be >= 1, got {self.alpha}")
        _validate_finite(self.dropout, "dropout")
        if not 0 <= self.dropout < 1:
            raise ValueError(f"dropout must be in [0, 1), got {self.dropout}")
        if not self.target_modules:
            raise ValueError("target_modules must not be empty")
        if self.bias not in ("none", "all", "lora_only"):
            raise ValueError(
                f"bias must be 'none', 'all', or 'lora_only', got {self.bias!r}"
            )

    def to_peft_config(self):
        """Convert to peft.LoraConfig. Lazy import to avoid loading peft at config time."""
        from peft import LoraConfig as PeftLoraConfig, TaskType

        return PeftLoraConfig(
            r=self.rank,
            lora_alpha=self.alpha,
            target_modules=list(self.target_modules),
            lora_dropout=self.dropout,
            bias=self.bias,
            task_type=getattr(TaskType, self.task_type),
        )


@dataclass(frozen=True)
class SFTConfig:
    """Supervised fine-tuning configuration.

    Args:
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate.
        warmup_ratio: Fraction of steps for warmup.
        max_seq_length: Maximum sequence length for tokenization.
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
        dataset_text_field: Column name in dataset containing text.
    """

    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.03
    max_seq_length: int = 2048
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
    dataset_text_field: str = "text"

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.SFTConfig. Uses SFTConfig (not deprecated TrainingArguments)."""
        from trl import SFTConfig as TRLSFTConfig

        return TRLSFTConfig(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            max_seq_length=self.max_seq_length,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
            dataset_text_field=self.dataset_text_field,
        )


@dataclass(frozen=True)
class DPOConfig:
    """Direct Preference Optimization configuration.

    Args:
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate.
        warmup_ratio: Fraction of steps for warmup.
        max_length: Maximum total sequence length.
        max_prompt_length: Maximum prompt length.
        beta: DPO beta parameter controlling deviation from reference policy.
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
    """

    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.1
    max_length: int = 2048
    max_prompt_length: int = 512
    beta: float = 0.1
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_positive(self.beta, "beta")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.DPOConfig."""
        from trl import DPOConfig as TRLDPOConfig

        return TRLDPOConfig(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            max_length=self.max_length,
            max_prompt_length=self.max_prompt_length,
            beta=self.beta,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )


@dataclass(frozen=True)
class AdapterSignature:
    """Describes a LoRA adapter's characteristics. Separate from ModelSignature (R2).

    Args:
        base_model_id: HuggingFace model ID (e.g., 'meta-llama/Llama-3.1-8B').
        adapter_type: Type of adapter -- 'lora' or 'qlora'.
        rank: LoRA rank (r).
        alpha: LoRA alpha scaling factor.
        target_modules: Model modules with LoRA applied.
        task_type: PEFT task type.
        training_method: Training method used -- 'sft', 'dpo', or 'sft_then_dpo'.
    """

    base_model_id: str
    adapter_type: str = "lora"
    rank: int = 16
    alpha: int = 32
    target_modules: tuple[str, ...] = ("q_proj", "v_proj")
    task_type: str = "CAUSAL_LM"
    training_method: str = "sft"

    def __post_init__(self) -> None:
        if not self.base_model_id:
            raise ValueError("base_model_id is required")
        if self.rank < 1:
            raise ValueError(f"rank must be >= 1, got {self.rank}")
        if self.alpha < 1:
            raise ValueError(f"alpha must be >= 1, got {self.alpha}")
        if not self.target_modules:
            raise ValueError("target_modules must not be empty")
        if self.adapter_type not in ("lora", "qlora"):
            raise ValueError(
                f"adapter_type must be 'lora' or 'qlora', got {self.adapter_type!r}"
            )
        if self.training_method not in ("sft", "dpo", "sft_then_dpo"):
            raise ValueError(
                f"training_method must be 'sft', 'dpo', or 'sft_then_dpo', "
                f"got {self.training_method!r}"
            )


@dataclass
class AlignmentConfig:
    """Top-level configuration for AlignmentPipeline.

    Args:
        method: Training method -- 'sft', 'dpo', or 'sft_then_dpo'.
        base_model_id: HuggingFace model ID (e.g., 'meta-llama/Llama-3.1-8B').
        lora: LoRA configuration.
        sft: SFT-specific configuration (used when method is 'sft' or 'sft_then_dpo').
        dpo: DPO-specific configuration (used when method is 'dpo' or 'sft_then_dpo').
        use_qlora: Enable 4-bit QLoRA via bitsandbytes. Requires [rlhf] extra.
        experiment_dir: Directory for checkpoints and output.
        local_files_only: If True, do not download from HuggingFace Hub. For air-gap.
        base_model_revision: Specific model revision/commit hash for reproducibility.
    """

    method: str = "sft_then_dpo"
    base_model_id: str = ""
    lora: LoRAConfig = field(default_factory=LoRAConfig)
    sft: SFTConfig = field(default_factory=SFTConfig)
    dpo: DPOConfig = field(default_factory=DPOConfig)
    use_qlora: bool = False
    experiment_dir: str = "./align-experiments"
    local_files_only: bool = False
    base_model_revision: Optional[str] = None

    def __post_init__(self) -> None:
        if self.method not in ("sft", "dpo", "sft_then_dpo"):
            raise ValueError(
                f"method must be 'sft', 'dpo', or 'sft_then_dpo', got {self.method!r}"
            )
        if not self.base_model_id:
            raise ValueError("base_model_id is required")
        if self.use_qlora:
            try:
                import bitsandbytes  # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "QLoRA requires bitsandbytes. "
                    "Install with: pip install kailash-align[rlhf]"
                ) from exc

    def validate(self) -> list[str]:
        """Run full validation, return list of warnings (empty = valid)."""
        warnings: list[str] = []
        if self.method in ("sft", "sft_then_dpo") and not self.sft:
            warnings.append("SFT config missing for SFT-based method")
        if self.method in ("dpo", "sft_then_dpo") and not self.dpo:
            warnings.append("DPO config missing for DPO-based method")
        return warnings


@dataclass(frozen=True)
class ServingConfig:
    """Configuration for model serving (ALN-301).

    Args:
        target: Deployment target -- 'ollama' or 'vllm'.
        quantization: GGUF quantization type -- 'f16', 'q4_k_m', or 'q8_0'.
        system_prompt: Optional system prompt for Ollama Modelfile.
        ollama_host: Ollama server URL.
        validate_gguf: Whether to validate GGUF after conversion (R1-02 MANDATORY).
        validation_timeout: Timeout in seconds for GGUF validation (R2 detail 2).
    """

    target: str = "ollama"
    quantization: str = "q4_k_m"
    system_prompt: Optional[str] = None
    ollama_host: str = "http://localhost:11434"
    validate_gguf: bool = True
    validation_timeout: int = 120

    def __post_init__(self) -> None:
        if self.target not in ("ollama", "vllm"):
            raise ValueError(f"target must be 'ollama' or 'vllm', got {self.target!r}")
        valid_quant = ("f16", "q4_k_m", "q8_0")
        if self.quantization not in valid_quant:
            raise ValueError(
                f"quantization must be one of {valid_quant}, got {self.quantization!r}"
            )
        _validate_positive(float(self.validation_timeout), "validation_timeout")


# Quick preset: runs in ~5 minutes on a single GPU with limit=100
QUICK_TASKS = ["arc_easy", "hellaswag", "truthfulqa_mc1"]

# Standard preset: common benchmarks, ~30-60 min on A100 with limit=100
STANDARD_TASKS = [
    "arc_easy",
    "arc_challenge",
    "hellaswag",
    "truthfulqa_mc1",
    "winogrande",
    "mmlu",
]


@dataclass(frozen=True)
class EvalConfig:
    """Configuration for evaluation runs (ALN-300).

    Args:
        tasks: List of lm-eval task names, or ['quick'] / ['standard'] presets.
        limit: Maximum samples per task. Default 100 for interactive use (R1-06).
        batch_size: Batch size for evaluation. 'auto' lets lm-eval decide.
        num_fewshot: Number of few-shot examples. None uses task default.
        device: Device string ('cuda', 'cpu', etc.). None = auto-detect.
        local_files_only: If True, do not download from HuggingFace Hub.
        use_adapter: If True, load adapter on base model. If False, eval base only.
    """

    tasks: tuple[str, ...] = ("arc_easy", "hellaswag", "truthfulqa_mc1")
    limit: int = 100
    batch_size: str = "auto"
    num_fewshot: Optional[int] = None
    device: Optional[str] = None
    local_files_only: bool = False
    use_adapter: bool = True

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 1:
            raise ValueError(f"limit must be >= 1, got {self.limit}")


@dataclass
class OnPremConfig:
    """Configuration for on-prem / air-gapped deployment (ALN-401).

    When offline_mode=True, all HuggingFace Hub downloads are disabled.
    Models must be pre-cached using kailash-align-prepare CLI.

    Args:
        offline_mode: If True, disable all HuggingFace Hub downloads.
        model_cache_dir: Directory for cached models.
        ollama_host: Ollama server URL.
        vllm_endpoint: vLLM OpenAI-compatible API endpoint.
    """

    offline_mode: bool = False
    model_cache_dir: str = "~/.cache/kailash-align/models"
    ollama_host: str = "http://localhost:11434"
    vllm_endpoint: Optional[str] = None

    def __post_init__(self) -> None:
        from pathlib import Path

        object.__setattr__(
            self, "model_cache_dir", str(Path(self.model_cache_dir).expanduser())
        )
