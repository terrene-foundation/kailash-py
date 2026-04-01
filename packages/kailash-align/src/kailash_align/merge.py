# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Adapter merge utilities for kailash-align.

Merges LoRA adapters into base models using PEFT's merge_and_unload().
After merge, the resulting model is a standard HuggingFace model
that can be loaded without PEFT. Required for GGUF export (ALN-301)
and vLLM serving.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from kailash_align.exceptions import MergeError

logger = logging.getLogger(__name__)

__all__ = ["merge_adapter", "AdapterMerger"]


class AdapterMerger:
    """Merges LoRA adapters into base models.

    After merge, the resulting model is a standard HuggingFace model
    that can be loaded without PEFT. This is required for:
    - GGUF export (ALN-301): conversion tools expect a full model
    - vLLM serving: vLLM loads HF models directly
    - Distribution: merged models are simpler to share

    Args:
        adapter_registry: AdapterRegistry for looking up adapters and updating status.
    """

    def __init__(self, adapter_registry: Any = None) -> None:
        self._registry = adapter_registry

    async def merge(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> Path:
        """Merge LoRA adapter into base model.

        Steps:
        1. Load base model
        2. Load adapter via PeftModel.from_pretrained()
        3. Call model.merge_and_unload()
        4. Save merged model + tokenizer to output_dir
        5. Update AdapterRegistry: merge_status = 'merged', merged_model_path

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            output_dir: Where to save merged model. Defaults to adapter_path/../merged/

        Returns:
            Path to merged model directory.

        Raises:
            MergeError: If merge fails.
        """
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self._registry is None:
            raise MergeError("AdapterRegistry is required for merge operations")

        adapter_version = await self._registry.get_adapter(adapter_name, version)

        # Idempotent: if already merged, return existing path
        if adapter_version.merge_status == "merged":
            logger.info(
                "Adapter %s v%s is already merged at %s",
                adapter_name,
                adapter_version.version,
                adapter_version.merged_model_path,
            )
            return Path(adapter_version.merged_model_path)

        if adapter_version.merge_status == "exported":
            raise MergeError(
                f"Adapter {adapter_name} v{adapter_version.version} has already been "
                f"exported to GGUF. Cannot re-merge an exported adapter."
            )

        # Load base model
        logger.info("Loading base model: %s", adapter_version.base_model_id)
        base_model = AutoModelForCausalLM.from_pretrained(
            adapter_version.base_model_id,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=False,
        )

        # Load adapter
        logger.info("Loading adapter from: %s", adapter_version.adapter_path)
        model = PeftModel.from_pretrained(base_model, adapter_version.adapter_path)

        # Merge
        logger.info("Merging adapter into base model...")
        try:
            model = model.merge_and_unload()
        except Exception as exc:
            raise MergeError(f"merge_and_unload() failed: {exc}") from exc

        # Save merged model
        output_path = Path(
            output_dir or Path(adapter_version.adapter_path).parent / "merged"
        )
        output_path.mkdir(parents=True, exist_ok=True)

        model.save_pretrained(str(output_path))
        tokenizer = AutoTokenizer.from_pretrained(adapter_version.adapter_path)
        tokenizer.save_pretrained(str(output_path))

        logger.info("Merged model saved to: %s", output_path)

        # Update registry
        await self._registry.update_merge_status(
            adapter_name,
            adapter_version.version,
            merge_status="merged",
            merged_model_path=str(output_path),
        )

        return output_path


async def merge_adapter(
    adapter_name: str,
    version: Optional[str] = None,
    output_dir: Optional[str] = None,
    adapter_registry: Any = None,
) -> Path:
    """Convenience function for one-shot adapter merge.

    See AdapterMerger.merge() for full documentation.
    """
    merger = AdapterMerger(adapter_registry=adapter_registry)
    return await merger.merge(adapter_name, version, output_dir)
