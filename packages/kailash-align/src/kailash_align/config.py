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
    "KTOConfig",
    "ORPOConfig",
    "GRPOConfig",
    "RLOOConfig",
    "OnlineDPOConfig",
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
class KTOConfig:
    """Kahneman-Tversky Optimization configuration (unpaired binary feedback).

    KTO works with unpaired binary feedback (prompt, completion, label) instead of
    pairwise preferences. Dramatically lowers the data barrier compared to DPO.

    Args:
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate (KTO paper recommends 5e-7).
        warmup_ratio: Fraction of steps for warmup.
        beta: KTO beta parameter controlling loss scaling.
        desirable_weight: Weight for desirable (True) examples.
        undesirable_weight: Weight for undesirable (False) examples.
        max_length: Maximum total sequence length.
        max_prompt_length: Maximum prompt length.
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
    """

    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-7
    warmup_ratio: float = 0.1
    beta: float = 0.1
    desirable_weight: float = 1.0
    undesirable_weight: float = 1.0
    max_length: int = 1024
    max_prompt_length: int = 512
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_positive(self.beta, "beta")
        _validate_positive(self.desirable_weight, "desirable_weight")
        _validate_positive(self.undesirable_weight, "undesirable_weight")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.KTOConfig."""
        from trl import KTOConfig as TRLKTOConfig

        return TRLKTOConfig(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            beta=self.beta,
            desirable_weight=self.desirable_weight,
            undesirable_weight=self.undesirable_weight,
            max_length=self.max_length,
            max_prompt_length=self.max_prompt_length,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )


@dataclass(frozen=True)
class ORPOConfig:
    """Odds Ratio Preference Optimization configuration (monolithic SFT+preference).

    ORPO combines SFT and preference alignment in a single training pass,
    eliminating the need for the sft_then_dpo two-stage pipeline.

    Args:
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate (ORPO paper recommends 8e-6).
        warmup_ratio: Fraction of steps for warmup.
        beta: Odds ratio weight parameter.
        max_length: Maximum total sequence length.
        max_prompt_length: Maximum prompt length.
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
    """

    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 8e-6
    warmup_ratio: float = 0.1
    beta: float = 0.1
    max_length: int = 1024
    max_prompt_length: int = 512
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
        """Convert to trl.ORPOConfig."""
        from trl import ORPOConfig as TRLORPOConfig

        return TRLORPOConfig(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            beta=self.beta,
            max_length=self.max_length,
            max_prompt_length=self.max_prompt_length,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )


@dataclass(frozen=True)
class GRPOConfig:
    """Group Relative Policy Optimization configuration (online RL).

    GRPO generates completions online and scores them with reward functions.
    This is the method behind DeepSeek-R1. Requires reward functions from
    RewardRegistry and optionally vLLM for fast generation.

    Args:
        num_generations: Completions per prompt (DeepSeek used 16; 4 fits single GPU).
        temperature: Sampling temperature for generation diversity.
        max_completion_length: Maximum tokens per generated completion.
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate.
        warmup_ratio: Fraction of steps for warmup.
        kl_coef: KL divergence penalty coefficient.
        use_vllm: Use vLLM for fast generation (requires CUDA).
        vllm_gpu_utilization: GPU memory fraction for vLLM (0.0-1.0).
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
    """

    num_generations: int = 4
    temperature: float = 0.7
    max_completion_length: int = 2048
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 1e-5
    warmup_ratio: float = 0.1
    kl_coef: float = 0.001
    use_vllm: bool = False
    vllm_gpu_utilization: float = 0.5
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_finite(self.kl_coef, "kl_coef")
        if self.kl_coef < 0:
            raise ValueError(f"kl_coef must be >= 0, got {self.kl_coef}")
        _validate_finite(self.temperature, "temperature")
        if self.temperature <= 0:
            raise ValueError(f"temperature must be > 0, got {self.temperature}")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if self.num_generations < 1:
            raise ValueError(
                f"num_generations must be >= 1, got {self.num_generations}"
            )
        if not 0.0 < self.vllm_gpu_utilization <= 1.0:
            raise ValueError(
                f"vllm_gpu_utilization must be in (0, 1], got {self.vllm_gpu_utilization}"
            )
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.GRPOConfig."""
        from trl import GRPOConfig as TRLGRPOConfig

        kwargs = dict(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            num_generations=self.num_generations,
            temperature=self.temperature,
            max_completion_length=self.max_completion_length,
            kl_coef=self.kl_coef,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )
        if self.use_vllm:
            kwargs["use_vllm"] = True
            kwargs["vllm_gpu_utilization"] = self.vllm_gpu_utilization
        return TRLGRPOConfig(**kwargs)


@dataclass(frozen=True)
class RLOOConfig:
    """REINFORCE Leave-One-Out configuration (online RL).

    RLOO generates multiple completions per prompt and uses a leave-one-out
    baseline for variance reduction. Same infrastructure as GRPO (reward
    functions + optional vLLM) but different optimization technique.

    Args:
        num_generations: Completions per prompt for LOO baseline.
        temperature: Sampling temperature for generation diversity.
        max_completion_length: Maximum tokens per generated completion.
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate.
        warmup_ratio: Fraction of steps for warmup.
        kl_coef: KL divergence penalty coefficient.
        use_vllm: Use vLLM for fast generation (requires CUDA).
        vllm_gpu_utilization: GPU memory fraction for vLLM (0.0-1.0).
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
    """

    num_generations: int = 4
    temperature: float = 0.7
    max_completion_length: int = 2048
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 1e-5
    warmup_ratio: float = 0.1
    kl_coef: float = 0.001
    use_vllm: bool = False
    vllm_gpu_utilization: float = 0.5
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_finite(self.kl_coef, "kl_coef")
        if self.kl_coef < 0:
            raise ValueError(f"kl_coef must be >= 0, got {self.kl_coef}")
        _validate_finite(self.temperature, "temperature")
        if self.temperature <= 0:
            raise ValueError(f"temperature must be > 0, got {self.temperature}")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if self.num_generations < 1:
            raise ValueError(
                f"num_generations must be >= 1, got {self.num_generations}"
            )
        if not 0.0 < self.vllm_gpu_utilization <= 1.0:
            raise ValueError(
                f"vllm_gpu_utilization must be in (0, 1], got {self.vllm_gpu_utilization}"
            )
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.RLOOConfig."""
        from trl import RLOOConfig as TRLRLOOConfig

        kwargs = dict(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            num_generations=self.num_generations,
            temperature=self.temperature,
            max_completion_length=self.max_completion_length,
            kl_coef=self.kl_coef,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )
        if self.use_vllm:
            kwargs["use_vllm"] = True
            kwargs["vllm_gpu_utilization"] = self.vllm_gpu_utilization
        return TRLRLOOConfig(**kwargs)


@dataclass(frozen=True)
class OnlineDPOConfig:
    """Online DPO configuration (DPO with online generation).

    Online DPO generates completions online and uses a reward model to score
    pairs, then applies DPO loss. Requires generation backend.

    Args:
        num_train_epochs: Number of training epochs.
        per_device_train_batch_size: Batch size per device.
        gradient_accumulation_steps: Steps before gradient update.
        learning_rate: Peak learning rate.
        warmup_ratio: Fraction of steps for warmup.
        beta: DPO beta parameter.
        max_length: Maximum total sequence length.
        max_prompt_length: Maximum prompt length.
        max_completion_length: Maximum completion length for generation.
        logging_steps: Log metrics every N steps.
        save_steps: Save checkpoint every N steps.
        gradient_checkpointing: Trade compute for memory.
        bf16: Use bfloat16 mixed precision.
        fp16: Use float16 mixed precision.
        use_vllm: Use vLLM for fast generation (requires CUDA).
        vllm_gpu_utilization: GPU memory fraction for vLLM (0.0-1.0).
    """

    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.1
    beta: float = 0.1
    max_length: int = 2048
    max_prompt_length: int = 512
    max_completion_length: int = 512
    logging_steps: int = 10
    save_steps: int = 100
    gradient_checkpointing: bool = True
    bf16: bool = True
    fp16: bool = False
    use_vllm: bool = False
    vllm_gpu_utilization: float = 0.5

    def __post_init__(self) -> None:
        _validate_positive(self.learning_rate, "learning_rate")
        _validate_positive(self.beta, "beta")
        _validate_finite(self.warmup_ratio, "warmup_ratio")
        if self.warmup_ratio < 0 or self.warmup_ratio >= 1:
            raise ValueError(f"warmup_ratio must be in [0, 1), got {self.warmup_ratio}")
        if not 0.0 < self.vllm_gpu_utilization <= 1.0:
            raise ValueError(
                f"vllm_gpu_utilization must be in (0, 1], got {self.vllm_gpu_utilization}"
            )
        if self.bf16 and self.fp16:
            raise ValueError("Cannot enable both bf16 and fp16")

    def to_trl_config(self, output_dir: str):
        """Convert to trl.OnlineDPOConfig."""
        from trl import OnlineDPOConfig as TRLOnlineDPOConfig

        kwargs = dict(
            output_dir=output_dir,
            num_train_epochs=self.num_train_epochs,
            per_device_train_batch_size=self.per_device_train_batch_size,
            gradient_accumulation_steps=self.gradient_accumulation_steps,
            learning_rate=self.learning_rate,
            warmup_ratio=self.warmup_ratio,
            beta=self.beta,
            max_length=self.max_length,
            max_prompt_length=self.max_prompt_length,
            max_completion_length=self.max_completion_length,
            logging_steps=self.logging_steps,
            save_steps=self.save_steps,
            gradient_checkpointing=self.gradient_checkpointing,
            bf16=self.bf16,
            fp16=self.fp16,
        )
        if self.use_vllm:
            kwargs["use_vllm"] = True
            kwargs["vllm_gpu_utilization"] = self.vllm_gpu_utilization
        return TRLOnlineDPOConfig(**kwargs)


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
        training_method: Any method in METHOD_REGISTRY or 'sft_then_dpo'.
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
        from kailash_align.method_registry import validate_method_name

        validate_method_name(self.training_method)


@dataclass
class AlignmentConfig:
    """Top-level configuration for AlignmentPipeline.

    Supports all training methods registered in MethodRegistry:
    - Offline: sft, dpo, sft_then_dpo, orpo, cpo
    - Unpaired: kto, bco
    - Online: grpo, rloo, online_dpo, xpo, nash_md

    Args:
        method: Training method -- any key in METHOD_REGISTRY or 'sft_then_dpo'.
        base_model_id: HuggingFace model ID (e.g., 'meta-llama/Llama-3.1-8B').
        lora: LoRA configuration.
        sft: SFT-specific configuration.
        dpo: DPO-specific configuration.
        kto: KTO-specific configuration (unpaired binary feedback).
        orpo: ORPO-specific configuration (monolithic SFT+preference).
        grpo: GRPO-specific configuration (online RL with reward functions).
        rloo: RLOO-specific configuration (online RL with LOO baseline).
        online_dpo: Online DPO-specific configuration.
        loss_type: DPO loss variant (e.g., 'ipo', 'simpo'). Only for DPO-family methods.
        reward_funcs: Reward function names from RewardRegistry (for online methods).
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
    kto: Optional[KTOConfig] = None
    orpo: Optional[ORPOConfig] = None
    grpo: Optional[GRPOConfig] = None
    rloo: Optional[RLOOConfig] = None
    online_dpo: Optional[OnlineDPOConfig] = None
    loss_type: Optional[str] = None
    reward_funcs: list[str] = field(default_factory=list)
    use_qlora: bool = False
    experiment_dir: str = "./align-experiments"
    local_files_only: bool = False
    base_model_revision: Optional[str] = None

    def __post_init__(self) -> None:
        from kailash_align.method_registry import validate_method_name

        validate_method_name(self.method)
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
        # Auto-create method-specific configs with defaults if not provided
        if self.method == "kto" and self.kto is None:
            self.kto = KTOConfig()
        if self.method == "orpo" and self.orpo is None:
            self.orpo = ORPOConfig()
        if self.method == "grpo" and self.grpo is None:
            self.grpo = GRPOConfig()
        if self.method == "rloo" and self.rloo is None:
            self.rloo = RLOOConfig()
        if self.method == "online_dpo" and self.online_dpo is None:
            self.online_dpo = OnlineDPOConfig()

    def get_method_config(self, method_name: str):
        """Get the method-specific config for TRL config generation.

        Returns the dedicated config if set, or falls back to SFT config
        for experimental methods without dedicated configs.
        """
        config_map = {
            "sft": self.sft,
            "dpo": self.dpo,
            "kto": self.kto,
            "orpo": self.orpo,
            "grpo": self.grpo,
            "rloo": self.rloo,
            "online_dpo": self.online_dpo,
        }
        config = config_map.get(method_name)
        if config is not None:
            return config
        # For experimental methods (cpo, bco, xpo, nash_md) without dedicated config,
        # fall back to sft config as base training arguments
        return self.sft

    def validate(self) -> list[str]:
        """Run full validation, return list of warnings (empty = valid)."""
        warnings: list[str] = []
        if self.method in ("sft", "sft_then_dpo") and not self.sft:
            warnings.append("SFT config missing for SFT-based method")
        if self.method in ("dpo", "sft_then_dpo") and not self.dpo:
            warnings.append("DPO config missing for DPO-based method")
        # Check online methods have reward functions configured
        from kailash_align.method_registry import METHOD_REGISTRY

        if self.method in METHOD_REGISTRY:
            method_meta = METHOD_REGISTRY[self.method]
            if method_meta.requires_reward_func and not self.reward_funcs:
                warnings.append(
                    f"Method '{self.method}' requires reward_funcs but none configured"
                )
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
