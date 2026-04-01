# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AlignmentPipeline: SFT + DPO training orchestration.

Thin wrappers around TRL's SFTTrainer and DPOTrainer. The framework value is
AdapterRegistry integration, checkpoint management, and reproducibility -- not
training innovation.
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
        method: Training method used ('sft', 'dpo', or 'sft_then_dpo').
    """

    adapter_name: str
    adapter_path: str
    adapter_version: Any  # Optional[AdapterVersion] -- avoids circular import
    training_metrics: dict
    experiment_dir: str
    method: str  # "sft" | "dpo" | "sft_then_dpo"


class AlignmentPipeline:
    """Orchestrates SFT + DPO training pipeline.

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
    ) -> AlignmentResult:
        """Run training based on config.method.

        Args:
            dataset: HuggingFace Dataset for SFT (instruction data).
            adapter_name: Name for the adapter in AdapterRegistry.
            preference_dataset: HuggingFace Dataset for DPO (prompt/chosen/rejected).

        Returns:
            AlignmentResult with adapter version, metrics, and paths.

        Raises:
            TrainingError: If training fails or required datasets are missing.
        """
        if self._config.method == "sft":
            return await self._run_sft(dataset, adapter_name)
        elif self._config.method == "dpo":
            if preference_dataset is None:
                raise TrainingError("DPO requires preference_dataset")
            return await self._run_dpo(preference_dataset, adapter_name)
        elif self._config.method == "sft_then_dpo":
            if preference_dataset is None:
                raise TrainingError("sft_then_dpo requires preference_dataset")
            sft_result = await self._run_sft(dataset, adapter_name + "-sft")
            return await self._run_dpo(
                preference_dataset,
                adapter_name,
                base_adapter_path=sft_result.adapter_path,
            )
        else:
            raise TrainingError(f"Unknown training method: {self._config.method!r}")

    async def _run_sft(self, dataset: Any, adapter_name: str) -> AlignmentResult:
        """Run supervised fine-tuning via TRL SFTTrainer.

        Steps:
        1. Load base model (with QLoRA quantization if configured)
        2. Apply LoRA adapter via PEFT
        3. Create TRL SFTConfig (not deprecated TrainingArguments)
        4. Train with SFTTrainer
        5. Save adapter weights
        6. Register in AdapterRegistry
        7. Return AlignmentResult
        """
        import torch
        from peft import get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTTrainer

        experiment_dir = Path(self._config.experiment_dir) / adapter_name / "sft"
        experiment_dir.mkdir(parents=True, exist_ok=True)

        # 1. Load base model
        model_kwargs = self._base_model_kwargs()
        model_kwargs["torch_dtype"] = self._resolve_dtype(self._config.sft)

        if self._config.use_qlora:
            model_kwargs["quantization_config"] = self._qlora_config()
            model_kwargs["torch_dtype"] = torch.bfloat16

        logger.info("Loading base model %s for SFT", self._config.base_model_id)
        model = AutoModelForCausalLM.from_pretrained(**model_kwargs)
        tokenizer = AutoTokenizer.from_pretrained(
            self._config.base_model_id,
            local_files_only=self._config.local_files_only,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 2. Apply LoRA
        peft_config = self._config.lora.to_peft_config()
        model = get_peft_model(model, peft_config)
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in model.parameters())
        logger.info(
            "LoRA applied: %d trainable / %d total params (%.2f%%)",
            trainable_params,
            total_params,
            100 * trainable_params / total_params,
        )

        # 3. Create TRL SFTConfig
        sft_config = self._config.sft.to_trl_config(str(experiment_dir))

        # 4. Train
        trainer = SFTTrainer(
            model=model,
            args=sft_config,
            train_dataset=dataset,
            processing_class=tokenizer,
            peft_config=peft_config,
        )

        try:
            logger.info("Starting SFT training for %s", adapter_name)
            train_result = trainer.train(
                resume_from_checkpoint=self._find_checkpoint(experiment_dir),
            )
        except Exception as exc:
            raise TrainingError(f"SFT training failed: {exc}") from exc

        # 5. Save adapter
        adapter_path = experiment_dir / "adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        logger.info("SFT adapter saved to %s", adapter_path)

        # 6. Register in AdapterRegistry
        adapter_version = None
        if self._registry is not None:
            signature = AdapterSignature(
                base_model_id=self._config.base_model_id,
                adapter_type="qlora" if self._config.use_qlora else "lora",
                rank=self._config.lora.rank,
                alpha=self._config.lora.alpha,
                target_modules=self._config.lora.target_modules,
                training_method="sft",
            )
            adapter_version = await self._registry.register_adapter(
                name=adapter_name,
                adapter_path=str(adapter_path),
                signature=signature,
                training_metrics={
                    "train_loss": train_result.training_loss,
                    "train_runtime": train_result.metrics.get("train_runtime"),
                    "train_samples_per_second": train_result.metrics.get(
                        "train_samples_per_second"
                    ),
                },
            )

        # 7. Return result
        return AlignmentResult(
            adapter_name=adapter_name,
            adapter_path=str(adapter_path),
            adapter_version=adapter_version,
            training_metrics=train_result.metrics,
            experiment_dir=str(experiment_dir),
            method="sft",
        )

    async def _run_dpo(
        self,
        preference_dataset: Any,
        adapter_name: str,
        base_adapter_path: Optional[str] = None,
    ) -> AlignmentResult:
        """Run Direct Preference Optimization via TRL DPOTrainer.

        Steps:
        1. Validate preference dataset format (prompt, chosen, rejected)
        2. Load base model (or load SFT adapter if chaining sft_then_dpo)
        3. Apply LoRA adapter via PEFT (or load existing adapter)
        4. Create TRL DPOConfig
        5. Train with DPOTrainer (reference model is implicit in TRL >=0.25)
        6. Save adapter weights
        7. Register in AdapterRegistry
        8. Return AlignmentResult
        """
        import torch
        from peft import PeftModel, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import DPOTrainer

        experiment_dir = Path(self._config.experiment_dir) / adapter_name / "dpo"
        experiment_dir.mkdir(parents=True, exist_ok=True)

        # 1. Validate preference dataset
        self._validate_preference_dataset(preference_dataset)

        # 2. Load model
        model_kwargs = self._base_model_kwargs()
        model_kwargs["torch_dtype"] = self._resolve_dtype(self._config.dpo)

        if self._config.use_qlora:
            model_kwargs["quantization_config"] = self._qlora_config()
            model_kwargs["torch_dtype"] = torch.bfloat16

        logger.info("Loading base model %s for DPO", self._config.base_model_id)
        model = AutoModelForCausalLM.from_pretrained(**model_kwargs)
        tokenizer = AutoTokenizer.from_pretrained(
            self._config.base_model_id,
            local_files_only=self._config.local_files_only,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 3. Apply LoRA (or load existing SFT adapter)
        peft_config = self._config.lora.to_peft_config()
        if base_adapter_path is not None:
            # Chaining from SFT: load the SFT adapter, merge, apply fresh LoRA for DPO
            model = PeftModel.from_pretrained(model, base_adapter_path)
            model = model.merge_and_unload()
            model = get_peft_model(model, peft_config)
            logger.info(
                "Loaded SFT adapter from %s, applying fresh LoRA for DPO",
                base_adapter_path,
            )
        else:
            model = get_peft_model(model, peft_config)

        # 4. Create TRL DPOConfig
        dpo_config = self._config.dpo.to_trl_config(str(experiment_dir))

        # 5. Train (reference model is implicit in TRL >=0.25)
        trainer = DPOTrainer(
            model=model,
            args=dpo_config,
            train_dataset=preference_dataset,
            processing_class=tokenizer,
            peft_config=peft_config,
        )

        try:
            logger.info("Starting DPO training for %s", adapter_name)
            train_result = trainer.train(
                resume_from_checkpoint=self._find_checkpoint(experiment_dir),
            )
        except Exception as exc:
            raise TrainingError(f"DPO training failed: {exc}") from exc

        # 6. Save adapter
        adapter_path = experiment_dir / "adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        logger.info("DPO adapter saved to %s", adapter_path)

        # 7. Register in AdapterRegistry
        adapter_version = None
        if self._registry is not None:
            training_method = "dpo" if base_adapter_path is None else "sft_then_dpo"
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
                training_metrics={
                    "train_loss": train_result.training_loss,
                    "train_runtime": train_result.metrics.get("train_runtime"),
                    "dpo_rewards_chosen": train_result.metrics.get("rewards/chosen"),
                    "dpo_rewards_rejected": train_result.metrics.get(
                        "rewards/rejected"
                    ),
                    "dpo_rewards_margin": train_result.metrics.get("rewards/margins"),
                },
            )

        # 8. Return result
        return AlignmentResult(
            adapter_name=adapter_name,
            adapter_path=str(adapter_path),
            adapter_version=adapter_version,
            training_metrics=train_result.metrics,
            experiment_dir=str(experiment_dir),
            method="dpo" if base_adapter_path is None else "sft_then_dpo",
        )

    # --- Internal helpers ---

    def _base_model_kwargs(self) -> dict[str, Any]:
        """Build base model loading kwargs."""
        kwargs: dict[str, Any] = {
            "pretrained_model_name_or_path": self._config.base_model_id,
            "local_files_only": self._config.local_files_only,
            "trust_remote_code": False,
        }
        if self._config.base_model_revision:
            kwargs["revision"] = self._config.base_model_revision
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

    def _validate_preference_dataset(self, dataset: Any) -> None:
        """Validate that dataset has the required columns for DPO training.

        Required columns: 'prompt', 'chosen', 'rejected'.
        Each row must have non-empty strings in all three columns.

        Args:
            dataset: HuggingFace Dataset to validate.

        Raises:
            TrainingError: If dataset format is invalid.
        """
        required_columns = {"prompt", "chosen", "rejected"}
        actual_columns = set(dataset.column_names)
        missing = required_columns - actual_columns
        if missing:
            raise TrainingError(
                f"Preference dataset missing required columns: {missing}. "
                f"Expected columns: prompt, chosen, rejected. "
                f"Got columns: {sorted(actual_columns)}"
            )

        # Spot-check first row for non-empty strings
        if len(dataset) == 0:
            raise TrainingError("Preference dataset is empty")

        first_row = dataset[0]
        for col in required_columns:
            if not isinstance(first_row[col], str) or not first_row[col].strip():
                raise TrainingError(
                    f"Preference dataset column '{col}' must contain non-empty strings. "
                    f"First row has: {type(first_row[col]).__name__} = {first_row[col]!r}"
                )
