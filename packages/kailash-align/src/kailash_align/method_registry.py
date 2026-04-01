# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MethodRegistry: registry-driven training method dispatch.

Replaces hard if-elif dispatch in pipeline.py with a registry architecture.
Each training method is registered with its trainer class, config class,
dataset validator, and metrics extractor. Uses lazy imports (string-based
references) to avoid loading TRL trainers at module load time (H1).
"""
from __future__ import annotations

import importlib
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kailash_align.exceptions import AlignmentError, TrainingError

logger = logging.getLogger(__name__)

__all__ = [
    "MethodConfig",
    "METHOD_REGISTRY",
    "get_method",
    "register_method",
    "validate_method_name",
]


def _validate_preference_columns(dataset: Any) -> None:
    """Validate preference dataset: requires prompt, chosen, rejected columns."""
    required = {"prompt", "chosen", "rejected"}
    actual = set(dataset.column_names)
    missing = required - actual
    if missing:
        raise TrainingError(
            f"Preference dataset missing columns: {missing}. "
            f"Expected: prompt, chosen, rejected. Got: {sorted(actual)}"
        )
    if len(dataset) == 0:
        raise TrainingError("Dataset is empty")


def _validate_sft_columns(dataset: Any) -> None:
    """Validate SFT dataset: requires a text column."""
    if len(dataset) == 0:
        raise TrainingError("Dataset is empty")


def _validate_unpaired_columns(dataset: Any) -> None:
    """Validate unpaired preference dataset: requires prompt, completion, label columns."""
    required = {"prompt", "completion", "label"}
    actual = set(dataset.column_names)
    missing = required - actual
    if missing:
        raise TrainingError(
            f"Unpaired preference dataset missing columns: {missing}. "
            f"Expected: prompt, completion, label. Got: {sorted(actual)}"
        )
    if len(dataset) == 0:
        raise TrainingError("Dataset is empty")


def _validate_prompt_only(dataset: Any) -> None:
    """Validate prompt-only dataset for online methods (GRPO, RLOO)."""
    if len(dataset) == 0:
        raise TrainingError("Dataset is empty")
    columns = set(dataset.column_names)
    if "prompt" not in columns:
        raise TrainingError(
            f"Online RL dataset requires 'prompt' column. Got: {sorted(columns)}"
        )


def _extract_standard_metrics(train_result: Any) -> dict[str, Any]:
    """Extract standard training metrics from TRL TrainOutput."""
    metrics: dict[str, Any] = {}
    if hasattr(train_result, "training_loss"):
        metrics["train_loss"] = train_result.training_loss
    if hasattr(train_result, "metrics"):
        raw = train_result.metrics
        metrics["train_runtime"] = raw.get("train_runtime")
        metrics["train_samples_per_second"] = raw.get("train_samples_per_second")
    return metrics


def _extract_dpo_metrics(train_result: Any) -> dict[str, Any]:
    """Extract DPO-specific metrics (reward margins)."""
    metrics = _extract_standard_metrics(train_result)
    if hasattr(train_result, "metrics"):
        raw = train_result.metrics
        metrics["rewards_chosen"] = raw.get("rewards/chosen")
        metrics["rewards_rejected"] = raw.get("rewards/rejected")
        metrics["rewards_margin"] = raw.get("rewards/margins")
    return metrics


def _extract_grpo_metrics(train_result: Any) -> dict[str, Any]:
    """Extract GRPO-specific metrics."""
    metrics = _extract_standard_metrics(train_result)
    if hasattr(train_result, "metrics"):
        raw = train_result.metrics
        metrics["reward_mean"] = raw.get("reward")
        metrics["kl_divergence"] = raw.get("kl")
    return metrics


@dataclass(frozen=True)
class MethodConfig:
    """Metadata for a training method.

    Uses string-based lazy references for trainer/config classes to avoid
    importing TRL at module load time. Classes resolved via _lazy_import()
    only when train() is called.

    Args:
        name: Method identifier (e.g., 'sft', 'dpo', 'grpo').
        trainer_module: Python module containing the trainer class.
        trainer_class_name: Name of the trainer class.
        config_module: Python module containing the TRL config class.
        config_class_name: Name of the TRL config class.
        dataset_validator: Callable to validate dataset format.
        dataset_required_columns: Required columns (for error messages).
        metrics_extractor: Callable to extract metrics from TrainOutput.
        requires_preference_data: Whether method needs paired preference data.
        requires_reward_func: Whether method needs a reward function (online RL).
        requires_generation_backend: Whether method needs vLLM for online rollouts.
        supports_loss_type: Whether method supports DPO loss_type variants.
        category: Method category for documentation/UI.
    """

    name: str
    trainer_module: str
    trainer_class_name: str
    config_module: str
    config_class_name: str
    dataset_validator: Callable[[Any], None]
    dataset_required_columns: frozenset[str] = field(default_factory=frozenset)
    metrics_extractor: Callable[..., dict[str, Any]] = _extract_standard_metrics
    requires_preference_data: bool = False
    requires_reward_func: bool = False
    requires_generation_backend: bool = False
    supports_loss_type: bool = False
    category: str = "offline"


def _lazy_import(module_name: str, class_name: str) -> type:
    """Import a class by module path and class name. Lazy — only called at train time."""
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except ImportError as exc:
        raise ImportError(
            f"Cannot import {class_name} from {module_name}. "
            f"Ensure the required package is installed: pip install kailash-align"
        ) from exc
    except AttributeError as exc:
        raise ImportError(
            f"{module_name} does not have attribute {class_name}. "
            f"Check that your TRL version supports this trainer."
        ) from exc


# --- Built-in Method Registry ---

METHOD_REGISTRY: dict[str, MethodConfig] = {}


def register_method(config: MethodConfig) -> None:
    """Register a training method in the global registry."""
    METHOD_REGISTRY[config.name] = config


def get_method(name: str) -> MethodConfig:
    """Look up a registered training method.

    Raises:
        AlignmentError: If method is not registered.
    """
    if name not in METHOD_REGISTRY:
        available = sorted(METHOD_REGISTRY.keys())
        raise AlignmentError(
            f"Unknown training method '{name}'. "
            f"Available methods: {available}"
        )
    return METHOD_REGISTRY[name]


def validate_method_name(name: str) -> None:
    """Validate that a method name is registered or is the special 'sft_then_dpo' combo."""
    if name == "sft_then_dpo":
        return  # Special combo method
    if name not in METHOD_REGISTRY:
        available = sorted(METHOD_REGISTRY.keys())
        raise ValueError(
            f"Unknown training method '{name}'. "
            f"Available: {available + ['sft_then_dpo']}"
        )


# Register built-in methods

register_method(MethodConfig(
    name="sft",
    trainer_module="trl",
    trainer_class_name="SFTTrainer",
    config_module="trl",
    config_class_name="SFTConfig",
    dataset_validator=_validate_sft_columns,
    dataset_required_columns=frozenset({"text"}),
    metrics_extractor=_extract_standard_metrics,
    requires_preference_data=False,
    category="offline",
))

register_method(MethodConfig(
    name="dpo",
    trainer_module="trl",
    trainer_class_name="DPOTrainer",
    config_module="trl",
    config_class_name="DPOConfig",
    dataset_validator=_validate_preference_columns,
    dataset_required_columns=frozenset({"prompt", "chosen", "rejected"}),
    metrics_extractor=_extract_dpo_metrics,
    requires_preference_data=True,
    supports_loss_type=True,
    category="offline",
))

register_method(MethodConfig(
    name="kto",
    trainer_module="trl",
    trainer_class_name="KTOTrainer",
    config_module="trl",
    config_class_name="KTOConfig",
    dataset_validator=_validate_unpaired_columns,
    dataset_required_columns=frozenset({"prompt", "completion", "label"}),
    metrics_extractor=_extract_dpo_metrics,
    requires_preference_data=False,
    category="unpaired",
))

register_method(MethodConfig(
    name="orpo",
    trainer_module="trl",
    trainer_class_name="ORPOTrainer",
    config_module="trl",
    config_class_name="ORPOConfig",
    dataset_validator=_validate_preference_columns,
    dataset_required_columns=frozenset({"prompt", "chosen", "rejected"}),
    metrics_extractor=_extract_standard_metrics,
    requires_preference_data=True,
    category="monolithic",
))

register_method(MethodConfig(
    name="grpo",
    trainer_module="trl",
    trainer_class_name="GRPOTrainer",
    config_module="trl",
    config_class_name="GRPOConfig",
    dataset_validator=_validate_prompt_only,
    dataset_required_columns=frozenset({"prompt"}),
    metrics_extractor=_extract_grpo_metrics,
    requires_reward_func=True,
    requires_generation_backend=True,
    category="online",
))

register_method(MethodConfig(
    name="rloo",
    trainer_module="trl",
    trainer_class_name="RLOOTrainer",
    config_module="trl",
    config_class_name="RLOOConfig",
    dataset_validator=_validate_prompt_only,
    dataset_required_columns=frozenset({"prompt"}),
    metrics_extractor=_extract_grpo_metrics,
    requires_reward_func=True,
    requires_generation_backend=True,
    category="online",
))

register_method(MethodConfig(
    name="online_dpo",
    trainer_module="trl",
    trainer_class_name="OnlineDPOTrainer",
    config_module="trl",
    config_class_name="OnlineDPOConfig",
    dataset_validator=_validate_prompt_only,
    dataset_required_columns=frozenset({"prompt"}),
    metrics_extractor=_extract_dpo_metrics,
    requires_generation_backend=True,
    category="online",
))
