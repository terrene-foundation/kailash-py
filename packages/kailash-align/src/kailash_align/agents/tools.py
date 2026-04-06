# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dumb data endpoint tools for alignment agents.

Per the LLM-first rule: tools fetch/write data, the LLM reasons.
No decision logic in any tool function.  Tools that have existing
engine implementations MUST delegate to them (zero-tolerance Rule 4).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "get_base_model_info",
    "list_training_methods",
    "estimate_training_cost",
    "get_dataset_stats",
    "check_preference_quality",
    "get_gpu_memory",
    "estimate_lora_memory",
    "list_quantization_options",
]


# ---------------------------------------------------------------------------
# Model info (heuristic — static knowledge is acceptable)
# ---------------------------------------------------------------------------

# Approximate metadata for common base models.
_MODEL_INFO: dict[str, dict[str, Any]] = {
    "meta-llama/Llama-2-7b-hf": {
        "params_b": 6.7,
        "architecture": "llama",
        "context_length": 4096,
    },
    "meta-llama/Meta-Llama-3-8B": {
        "params_b": 8.0,
        "architecture": "llama",
        "context_length": 8192,
    },
    "mistralai/Mistral-7B-v0.1": {
        "params_b": 7.2,
        "architecture": "mistral",
        "context_length": 32768,
    },
    "microsoft/phi-2": {
        "params_b": 2.7,
        "architecture": "phi",
        "context_length": 2048,
    },
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0": {
        "params_b": 1.1,
        "architecture": "llama",
        "context_length": 2048,
    },
}


async def get_base_model_info(model_id: str) -> dict[str, Any]:
    """Fetch base model metadata. No decisions."""
    info = _MODEL_INFO.get(model_id)
    if info:
        return {"model_id": model_id, **info, "source": "known_model_db"}
    return {
        "model_id": model_id,
        "params_b": None,
        "architecture": "unknown",
        "context_length": None,
        "source": "unknown_model",
    }


# ---------------------------------------------------------------------------
# Training methods (MUST use METHOD_REGISTRY — Rule 4)
# ---------------------------------------------------------------------------


async def list_training_methods() -> dict[str, Any]:
    """List available training methods from the real registry. No decisions."""
    from kailash_align.method_registry import METHOD_REGISTRY

    methods = []
    for name, config in METHOD_REGISTRY.items():
        methods.append(
            {
                "name": name,
                "requires_preference_data": config.requires_preference_data,
                "category": config.category,
            }
        )
    return {"methods": methods, "total": len(methods)}


# ---------------------------------------------------------------------------
# Cost estimation (heuristic — formula-based, acceptable)
# ---------------------------------------------------------------------------


async def estimate_training_cost(
    model_params_b: float,
    dataset_rows: int,
    epochs: int = 3,
    gpu_cost_per_hour: float = 2.50,
) -> dict[str, Any]:
    """Estimate training cost based on model size and dataset. No decisions."""
    # Rough heuristic: tokens/sec depends on model size
    tokens_per_second = 1000 / max(model_params_b, 0.1)
    avg_tokens_per_row = 512
    total_tokens = dataset_rows * avg_tokens_per_row * epochs
    estimated_hours = total_tokens / (tokens_per_second * 3600)
    estimated_cost = estimated_hours * gpu_cost_per_hour
    return {
        "estimated_hours": round(estimated_hours, 2),
        "estimated_cost_usd": round(estimated_cost, 2),
        "gpu_cost_per_hour": gpu_cost_per_hour,
        "note": "Rough estimate — actual cost depends on hardware and batch size",
    }


# ---------------------------------------------------------------------------
# Dataset stats (MUST use real data)
# ---------------------------------------------------------------------------


async def get_dataset_stats(dataset: Any) -> dict[str, Any]:
    """Compute dataset statistics from a real dataset object. No decisions."""
    try:
        info = dataset.info if hasattr(dataset, "info") else {}
        num_rows = len(dataset) if hasattr(dataset, "__len__") else 0
        columns = list(dataset.column_names) if hasattr(dataset, "column_names") else []
        return {
            "num_rows": num_rows,
            "columns": columns,
            "description": getattr(info, "description", ""),
            "size_bytes": getattr(info, "size_in_bytes", None),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def check_preference_quality(dataset: Any) -> dict[str, Any]:
    """Compute preference pair quality metrics from real data. No decisions."""
    try:
        columns = list(dataset.column_names) if hasattr(dataset, "column_names") else []
        has_chosen = "chosen" in columns
        has_rejected = "rejected" in columns
        has_prompt = "prompt" in columns
        num_rows = len(dataset) if hasattr(dataset, "__len__") else 0

        result: dict[str, Any] = {
            "num_pairs": num_rows,
            "has_prompt": has_prompt,
            "has_chosen": has_chosen,
            "has_rejected": has_rejected,
            "columns": columns,
        }

        if has_chosen and has_rejected and num_rows > 0:
            # Sample length stats
            sample_size = min(100, num_rows)
            chosen_lens = [len(str(dataset[i]["chosen"])) for i in range(sample_size)]
            rejected_lens = [
                len(str(dataset[i]["rejected"])) for i in range(sample_size)
            ]
            avg_chosen = sum(chosen_lens) / len(chosen_lens) if chosen_lens else 0
            avg_rejected = (
                sum(rejected_lens) / len(rejected_lens) if rejected_lens else 0
            )
            result["avg_chosen_length"] = round(avg_chosen, 1)
            result["avg_rejected_length"] = round(avg_rejected, 1)
            result["length_ratio"] = (
                round(avg_chosen / avg_rejected, 2) if avg_rejected > 0 else None
            )

        return result
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# GPU memory (MUST use existing gpu_memory.py — Rule 4)
# ---------------------------------------------------------------------------


async def get_gpu_memory() -> dict[str, Any]:
    """Fetch GPU information from real hardware. No decisions."""
    from kailash_align.gpu_memory import get_gpu_info

    gpus = get_gpu_info()
    return {
        "gpus": [
            {
                "name": g.name,
                "total_gb": g.total_memory_gb,
                "free_gb": g.free_memory_gb,
            }
            for g in gpus
        ],
        "total_count": len(gpus),
    }


async def estimate_lora_memory(
    model_id: str,
    lora_rank: int = 16,
    batch_size: int = 4,
    sequence_length: int = 512,
    use_qlora: bool = False,
) -> dict[str, Any]:
    """Estimate LoRA training memory using existing engine. No decisions."""
    from kailash_align.gpu_memory import estimate_training_memory

    estimate = estimate_training_memory(
        model_id=model_id,
        lora_rank=lora_rank,
        batch_size=batch_size,
        seq_length=sequence_length,
        use_qlora=use_qlora,
    )
    return {
        "model_memory_gb": estimate.model_memory_gb,
        "optimizer_memory_gb": estimate.optimizer_memory_gb,
        "activation_memory_gb": estimate.activation_memory_gb,
        "total_estimate_gb": estimate.total_estimate_gb,
        "recommended_batch_size": estimate.recommended_batch_size,
        "fits_in_memory": estimate.fits_in_memory,
    }


# ---------------------------------------------------------------------------
# Quantization (static — options from ServingConfig, acceptable)
# ---------------------------------------------------------------------------


async def list_quantization_options() -> dict[str, Any]:
    """List available quantization options. No decisions."""
    return {
        "options": [
            {
                "name": "f16",
                "bits": 16,
                "description": "Full float16 — maximum quality",
            },
            {
                "name": "q8_0",
                "bits": 8,
                "description": "8-bit quantization — good quality/size balance",
            },
            {
                "name": "q4_k_m",
                "bits": 4,
                "description": "4-bit medium — best size/quality trade-off",
            },
            {
                "name": "q4_k_s",
                "bits": 4,
                "description": "4-bit small — smallest with acceptable quality",
            },
            {
                "name": "q2_k",
                "bits": 2,
                "description": "2-bit — experimental, significant quality loss",
            },
        ],
    }
