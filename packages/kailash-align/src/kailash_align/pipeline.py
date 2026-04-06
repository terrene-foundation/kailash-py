# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AlignmentPipeline: registry-driven training orchestration.

Supports all methods registered in MethodRegistry (SFT, DPO, KTO, ORPO,
GRPO, RLOO, Online DPO, and experimental trainers). The framework value is
AdapterRegistry integration, checkpoint management, and reproducibility --
not training innovation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from kailash_align.config import AdapterSignature, AlignmentConfig
from kailash_align.exceptions import TrainingError

logger = logging.getLogger(__name__)

__all__ = ["AlignmentPipeline", "AlignmentResult"]


@dataclass
class AlignmentResult:
    """Returned by AlignmentPipeline.train().

    Args:
        adapter_name: Human-readable adapter name.
        adapter_path: Path to saved LoRA adapter weights.
        adapter_version: AdapterVersion from registry (None if no registry).
        training_metrics: Training metrics dict from TRL trainer.
        experiment_dir: Directory containing checkpoints and output.
        method: Training method used.
    """

    adapter_name: str
    adapter_path: str
    adapter_version: Any  # Optional[AdapterVersion] -- avoids circular import
    training_metrics: dict
    experiment_dir: str
    method: str


class AlignmentPipeline:
    """Orchestrates training pipeline for all alignment methods.

    Uses MethodRegistry for method dispatch instead of hardcoded if-elif.
    Supports offline methods (SFT, DPO, KTO, ORPO, CPO), online methods
    (GRPO, RLOO, Online DPO), and the special sft_then_dpo combo.

    Args:
        config: AlignmentConfig with training parameters.
        adapter_registry: Optional AdapterRegistry for tracking trained adapters.
    """

    def __init__(
        self,
        config: AlignmentConfig,
        adapter_registry: Any = None,
    ) -> None:
        self._config = config
        self._registry = adapter_registry

    async def train(
        self,
        dataset: Any,
        adapter_name: str,
        preference_dataset: Any = None,
        reward_funcs: Optional[list[str]] = None,
    ) -> AlignmentResult:
        """Run training based on config.method.

        Args:
            dataset: HuggingFace Dataset for SFT (instruction data) or online
                     methods (prompt-only data).
            adapter_name: Name for the adapter in AdapterRegistry.
            preference_dataset: HuggingFace Dataset for preference methods
                                (prompt/chosen/rejected).
            reward_funcs: Reward function names from RewardRegistry. Overrides
                          config.reward_funcs if provided.

        Returns:
            AlignmentResult with adapter version, metrics, and paths.

        Raises:
            TrainingError: If training fails or required datasets/functions are missing.
        """
        method = self._config.method

        # Special combo: SFT then DPO
        if method == "sft_then_dpo":
            if preference_dataset is None:
                raise TrainingError("sft_then_dpo requires preference_dataset")
            sft_result = await self._run_training("sft", dataset, adapter_name + "-sft")
            return await self._run_training(
                "dpo",
                preference_dataset,
                adapter_name,
                base_adapter_path=sft_result.adapter_path,
            )

        # All other methods: use registry
        from kailash_align.method_registry import get_method

        method_config = get_method(method)

        # Determine which dataset to use
        if method_config.requires_preference_data:
            if preference_dataset is None:
                raise TrainingError(
                    f"{method} requires preference_dataset "
                    f"(columns: {sorted(method_config.dataset_required_columns)})"
                )
            train_dataset = preference_dataset
        else:
            train_dataset = dataset

        # Resolve reward functions for online methods
        resolved_rewards = None
        if method_config.requires_reward_func:
            func_names = reward_funcs or self._config.reward_funcs
            if not func_names:
                raise TrainingError(
                    f"Method '{method}' requires reward functions. "
                    f"Pass reward_funcs=['name'] or set config.reward_funcs."
                )
            from kailash_align.rewards import reward_registry

            resolved_rewards = [reward_registry.get(name) for name in func_names]

        return await self._run_training(
            method,
            train_dataset,
            adapter_name,
            reward_funcs=resolved_rewards,
        )

    async def _run_training(
        self,
        method_name: str,
        dataset: Any,
        adapter_name: str,
        *,
        base_adapter_path: Optional[str] = None,
        reward_funcs: Optional[list[Any]] = None,
    ) -> AlignmentResult:
        """Generic training method using MethodRegistry.

        Handles all methods: loads model, applies LoRA, creates TRL trainer,
        trains, saves adapter, registers in AdapterRegistry.

        Args:
            method_name: Registry key (e.g., 'sft', 'dpo', 'grpo').
            dataset: Validated HuggingFace Dataset.
            adapter_name: Name for the adapter.
            base_adapter_path: Path to base adapter for chaining (sft_then_dpo).
            reward_funcs: Resolved reward functions for online methods.
        """
        import torch
        from peft import PeftModel, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer

        from kailash_align.method_registry import _lazy_import, get_method

        method = get_method(method_name)

        # Validate dataset
        method.dataset_validator(dataset)

        # Setup experiment directory
        experiment_dir = Path(self._config.experiment_dir) / adapter_name / method_name
        experiment_dir.mkdir(parents=True, exist_ok=True)

        # 1. Load base model
        model_kwargs = self._base_model_kwargs()
        stage_config = self._config.get_method_config(method_name)
        model_kwargs["torch_dtype"] = self._resolve_dtype(stage_config)

        if self._config.use_qlora:
            model_kwargs["quantization_config"] = self._qlora_config()
            model_kwargs["torch_dtype"] = torch.bfloat16

        logger.info(
            "Loading base model %s for %s", self._config.base_model_id, method_name
        )
        model = AutoModelForCausalLM.from_pretrained(**model_kwargs)
        tokenizer_kwargs = {
            "pretrained_model_name_or_path": self._config.base_model_id,
            "local_files_only": model_kwargs["local_files_only"],
            "trust_remote_code": False,
        }
        if "cache_dir" in model_kwargs:
            tokenizer_kwargs["cache_dir"] = model_kwargs["cache_dir"]
        tokenizer = AutoTokenizer.from_pretrained(**tokenizer_kwargs)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 2. Apply LoRA (or chain from base adapter)
        peft_config = self._config.lora.to_peft_config()
        if base_adapter_path is not None:
            model = PeftModel.from_pretrained(model, base_adapter_path)
            model = model.merge_and_unload()
            model = get_peft_model(model, peft_config)
            logger.info(
                "Chained from %s, applying fresh LoRA for %s",
                base_adapter_path,
                method_name,
            )
        else:
            model = get_peft_model(model, peft_config)

        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in model.parameters())
        logger.info(
            "LoRA applied: %d trainable / %d total params (%.2f%%)",
            trainable_params,
            total_params,
            100 * trainable_params / max(1, total_params),
        )

        # 3. Create TRL config
        trl_config = stage_config.to_trl_config(str(experiment_dir))

        # Apply loss_type for DPO variants
        if method.supports_loss_type and self._config.loss_type:
            trl_config.loss_type = self._config.loss_type

        # 4. Create trainer
        TrainerClass = _lazy_import(method.trainer_module, method.trainer_class_name)

        trainer_kwargs: dict[str, Any] = {
            "model": model,
            "args": trl_config,
            "train_dataset": dataset,
            "processing_class": tokenizer,
        }

        # Add peft_config for offline/unpaired methods
        if not method.requires_generation_backend:
            trainer_kwargs["peft_config"] = peft_config

        # Add reward functions for online methods
        if method.requires_reward_func and reward_funcs:
            trainer_kwargs["reward_funcs"] = reward_funcs

        trainer = TrainerClass(**trainer_kwargs)

        # 5. Train
        try:
            logger.info("Starting %s training for %s", method_name, adapter_name)
            train_result = trainer.train(
                resume_from_checkpoint=self._find_checkpoint(experiment_dir),
            )
        except Exception as exc:
            raise TrainingError(
                f"{method_name.upper()} training failed: {exc}"
            ) from exc

        # 6. Save adapter
        adapter_path = experiment_dir / "adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        logger.info("%s adapter saved to %s", method_name.upper(), adapter_path)

        # 7. Register in AdapterRegistry
        adapter_version = None
        if self._registry is not None:
            training_method = (
                method_name if base_adapter_path is None else "sft_then_dpo"
            )
            signature = AdapterSignature(
                base_model_id=self._config.base_model_id,
                adapter_type="qlora" if self._config.use_qlora else "lora",
                rank=self._config.lora.rank,
                alpha=self._config.lora.alpha,
                target_modules=self._config.lora.target_modules,
                training_method=training_method,
            )
            adapter_version = await self._registry.register_adapter(
                name=adapter_name,
                adapter_path=str(adapter_path),
                signature=signature,
                training_metrics=method.metrics_extractor(train_result),
            )

        # 8. Return result
        return AlignmentResult(
            adapter_name=adapter_name,
            adapter_path=str(adapter_path),
            adapter_version=adapter_version,
            training_metrics=train_result.metrics,
            experiment_dir=str(experiment_dir),
            method=method_name if base_adapter_path is None else "sft_then_dpo",
        )

    # --- Internal helpers ---

    def _base_model_kwargs(self) -> dict[str, Any]:
        """Build base model loading kwargs.

        Respects both ``config.local_files_only`` and nested
        ``config.onprem.offline_mode``.  When either is True,
        ``local_files_only=True`` is set so no HuggingFace Hub
        requests escape.
        """
        onprem = self._config.onprem
        offline = self._config.local_files_only or (
            onprem is not None and onprem.offline_mode
        )
        kwargs: dict[str, Any] = {
            "pretrained_model_name_or_path": self._config.base_model_id,
            "local_files_only": offline,
            "trust_remote_code": False,
        }
        if self._config.base_model_revision:
            kwargs["revision"] = self._config.base_model_revision
        if onprem is not None and onprem.model_cache_dir:
            kwargs["cache_dir"] = onprem.model_cache_dir
        return kwargs

    def _resolve_dtype(self, stage_config: Any) -> Any:
        """Resolve torch dtype from stage config bf16/fp16 flags."""
        import torch

        if stage_config.bf16:
            return torch.bfloat16
        elif stage_config.fp16:
            return torch.float16
        return torch.float32

    def _qlora_config(self) -> Any:
        """Create BitsAndBytesConfig for QLoRA 4-bit loading."""
        import torch
        from transformers import BitsAndBytesConfig

        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    def _find_checkpoint(self, experiment_dir: Path) -> Optional[str]:
        """Find latest checkpoint in experiment_dir for resume."""
        checkpoints = list(experiment_dir.glob("checkpoint-*"))
        if checkpoints:

            def _ckpt_number(p: Path) -> int:
                try:
                    return int(p.name.split("-", 1)[1])
                except (IndexError, ValueError):
                    return -1

            latest = max(checkpoints, key=_ckpt_number)
            return str(latest)
        return None
