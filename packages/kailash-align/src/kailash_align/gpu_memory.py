# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""GPU memory estimation and management for alignment training.

Estimates VRAM requirements for training configurations to prevent
OOM errors. Supports multi-GPU setups via device_map estimation.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

from kailash_align.exceptions import AlignmentError

logger = logging.getLogger(__name__)

__all__ = [
    "GPUMemoryEstimate",
    "estimate_training_memory",
    "get_gpu_info",
    "GPUInfo",
]


class InsufficientMemoryError(AlignmentError):
    """Raised when estimated memory exceeds available GPU memory."""

    pass


@dataclass(frozen=True)
class GPUInfo:
    """Information about a single GPU device.

    Args:
        device_index: CUDA device index.
        name: GPU name (e.g., 'NVIDIA A100-SXM4-80GB').
        total_memory_gb: Total VRAM in GB.
        free_memory_gb: Free VRAM in GB.
    """

    device_index: int
    name: str
    total_memory_gb: float
    free_memory_gb: float


@dataclass(frozen=True)
class GPUMemoryEstimate:
    """Memory estimate for a training configuration.

    Args:
        model_memory_gb: Base model weights memory.
        adapter_memory_gb: LoRA adapter parameters memory.
        optimizer_memory_gb: Optimizer state memory.
        gradient_memory_gb: Gradient tensors memory.
        activation_memory_gb: Activation memory (batch-dependent).
        total_estimate_gb: Total estimated VRAM.
        recommended_batch_size: Recommended batch size for available memory.
        fits_in_memory: Whether the config fits in available GPU memory.
        notes: Any warnings or recommendations.
    """

    model_memory_gb: float
    adapter_memory_gb: float
    optimizer_memory_gb: float
    gradient_memory_gb: float
    activation_memory_gb: float
    total_estimate_gb: float
    recommended_batch_size: int
    fits_in_memory: bool
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "model_memory_gb": round(self.model_memory_gb, 2),
            "adapter_memory_gb": round(self.adapter_memory_gb, 2),
            "optimizer_memory_gb": round(self.optimizer_memory_gb, 2),
            "gradient_memory_gb": round(self.gradient_memory_gb, 2),
            "activation_memory_gb": round(self.activation_memory_gb, 2),
            "total_estimate_gb": round(self.total_estimate_gb, 2),
            "recommended_batch_size": self.recommended_batch_size,
            "fits_in_memory": self.fits_in_memory,
            "notes": self.notes,
        }


# Approximate parameter counts for common model sizes
_MODEL_PARAM_ESTIMATES: dict[str, int] = {
    "1b": 1_000_000_000,
    "3b": 3_000_000_000,
    "7b": 7_000_000_000,
    "8b": 8_000_000_000,
    "13b": 13_000_000_000,
    "14b": 14_000_000_000,
    "30b": 30_000_000_000,
    "34b": 34_000_000_000,
    "70b": 70_000_000_000,
}


def _estimate_params_from_model_id(model_id: str) -> int:
    """Estimate parameter count from model ID string."""
    model_id_lower = model_id.lower()
    for size_str, param_count in sorted(
        _MODEL_PARAM_ESTIMATES.items(), key=lambda x: -x[1]
    ):
        if size_str in model_id_lower:
            return param_count
    # Default to 7B if size unknown
    logger.warning(
        "Cannot determine model size from '%s', assuming 7B parameters", model_id
    )
    return 7_000_000_000


def _bytes_per_param(dtype: str, use_qlora: bool) -> float:
    """Bytes per parameter for a given dtype."""
    if use_qlora:
        return 0.5  # 4-bit quantization
    dtype_map = {"float32": 4.0, "float16": 2.0, "bfloat16": 2.0}
    return dtype_map.get(dtype, 2.0)


def estimate_training_memory(
    model_id: str,
    lora_rank: int = 16,
    lora_target_modules: int = 4,
    batch_size: int = 4,
    seq_length: int = 2048,
    gradient_accumulation_steps: int = 4,
    use_qlora: bool = False,
    gradient_checkpointing: bool = True,
    dtype: str = "bfloat16",
    available_gpu_memory_gb: Optional[float] = None,
    is_online_method: bool = False,
) -> GPUMemoryEstimate:
    """Estimate GPU memory requirements for a training configuration.

    Uses heuristics based on model size, LoRA config, batch size, and
    sequence length. Estimates are conservative (overestimate by ~20%).

    Args:
        model_id: HuggingFace model ID (used to estimate parameter count).
        lora_rank: LoRA rank (r).
        lora_target_modules: Number of modules with LoRA applied.
        batch_size: Per-device training batch size.
        seq_length: Maximum sequence length.
        gradient_accumulation_steps: Gradient accumulation steps.
        use_qlora: Whether QLoRA 4-bit quantization is used.
        gradient_checkpointing: Whether gradient checkpointing is enabled.
        dtype: Training dtype ('float32', 'float16', 'bfloat16').
        available_gpu_memory_gb: Available GPU memory (None = auto-detect).
        is_online_method: Whether this is an online RL method (adds generation overhead).

    Returns:
        GPUMemoryEstimate with detailed breakdown.
    """
    notes: list[str] = []
    num_params = _estimate_params_from_model_id(model_id)
    bpp = _bytes_per_param(dtype, use_qlora)

    # 1. Model memory (frozen weights)
    model_memory_gb = (num_params * bpp) / (1024**3)
    if use_qlora:
        notes.append("QLoRA 4-bit: model weights use ~0.5 bytes/param")

    # 2. LoRA adapter memory
    # Each LoRA module adds 2 * hidden_dim * rank parameters
    hidden_dim_estimate = max(1, int(math.sqrt(num_params / 12)))  # rough estimate
    lora_params = 2 * hidden_dim_estimate * lora_rank * lora_target_modules
    adapter_memory_gb = (lora_params * 2.0) / (1024**3)  # Always fp16 for LoRA

    # 3. Optimizer memory (AdamW: 2 states per param)
    optimizer_memory_gb = (lora_params * 2 * 4.0) / (1024**3)  # fp32 states

    # 4. Gradient memory
    gradient_memory_gb = (lora_params * 2.0) / (1024**3)  # fp16 gradients

    # 5. Activation memory (batch * seq_len * hidden_dim * layers)
    num_layers_estimate = max(1, int(num_params / (hidden_dim_estimate**2 * 12)))
    if gradient_checkpointing:
        # Checkpointing reduces activation memory to ~sqrt(layers)
        activation_factor = math.sqrt(num_layers_estimate)
    else:
        activation_factor = num_layers_estimate

    activation_memory_gb = (
        batch_size * seq_length * hidden_dim_estimate * activation_factor * 2.0
    ) / (1024**3)

    # Online methods need extra memory for generation
    if is_online_method:
        generation_overhead = model_memory_gb * 0.15  # ~15% overhead for KV cache
        activation_memory_gb += generation_overhead
        notes.append("Online RL: added ~15% overhead for generation KV cache")

    # Total with 20% safety margin
    raw_total = (
        model_memory_gb
        + adapter_memory_gb
        + optimizer_memory_gb
        + gradient_memory_gb
        + activation_memory_gb
    )
    total_estimate_gb = raw_total * 1.2

    # Determine if it fits
    if available_gpu_memory_gb is None:
        available_gpu_memory_gb = _detect_gpu_memory()

    fits = (
        total_estimate_gb <= available_gpu_memory_gb
        if available_gpu_memory_gb
        else True
    )

    # Recommend batch size
    if available_gpu_memory_gb and not fits:
        # Try to find a batch size that fits
        for bs in [batch_size // 2, 2, 1]:
            if bs < 1:
                break
            test_activation = (
                bs * seq_length * hidden_dim_estimate * activation_factor * 2.0
            ) / (1024**3)
            if is_online_method:
                test_activation += model_memory_gb * 0.15
            test_total = (
                model_memory_gb
                + adapter_memory_gb
                + optimizer_memory_gb
                + gradient_memory_gb
                + test_activation
            ) * 1.2
            if test_total <= available_gpu_memory_gb:
                notes.append(
                    f"Reduce batch_size to {bs} to fit in {available_gpu_memory_gb:.1f}GB"
                )
                break
        recommended_batch_size = max(1, bs) if not fits else batch_size
    else:
        recommended_batch_size = batch_size

    if not fits:
        notes.append(
            f"Estimated {total_estimate_gb:.1f}GB exceeds "
            f"available {available_gpu_memory_gb:.1f}GB. "
            f"Consider QLoRA, smaller batch size, or gradient checkpointing."
        )

    return GPUMemoryEstimate(
        model_memory_gb=model_memory_gb,
        adapter_memory_gb=adapter_memory_gb,
        optimizer_memory_gb=optimizer_memory_gb,
        gradient_memory_gb=gradient_memory_gb,
        activation_memory_gb=activation_memory_gb,
        total_estimate_gb=total_estimate_gb,
        recommended_batch_size=recommended_batch_size,
        fits_in_memory=fits,
        notes=notes,
    )


def _detect_gpu_memory() -> Optional[float]:
    """Auto-detect available GPU memory. Returns None if no GPU found."""
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            total = torch.cuda.get_device_properties(device).total_mem
            return total / (1024**3)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # Apple Silicon: estimate from system memory (shared GPU/CPU)
            import os

            # macOS reports total physical memory
            try:
                import subprocess

                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                total_bytes = int(result.stdout.strip())
                # MPS can use ~75% of system memory for GPU
                return (total_bytes / (1024**3)) * 0.75
            except Exception:
                return None
    except ImportError:
        pass
    return None


def get_gpu_info() -> list[GPUInfo]:
    """Get information about all available GPUs.

    Returns:
        List of GPUInfo objects, one per GPU. Empty list if no GPU found.
    """
    gpus: list[GPUInfo] = []
    try:
        import torch

        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                free, total = torch.cuda.mem_get_info(i)
                gpus.append(
                    GPUInfo(
                        device_index=i,
                        name=props.name,
                        total_memory_gb=total / (1024**3),
                        free_memory_gb=free / (1024**3),
                    )
                )
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            estimated = _detect_gpu_memory()
            if estimated:
                gpus.append(
                    GPUInfo(
                        device_index=0,
                        name="Apple Silicon (MPS)",
                        total_memory_gb=estimated,
                        free_memory_gb=estimated * 0.8,  # Rough estimate
                    )
                )
    except ImportError:
        pass
    return gpus
