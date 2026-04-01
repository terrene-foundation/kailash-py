# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AdapterRegistry: structured tracking for LoRA/QLoRA adapters.

Uses composition (HAS-A ModelRegistry, not inheritance) per ALN-001 contract.
AlignAdapter and AlignAdapterVersion are standalone records, not inheriting
from MLModel/MLModelVersion.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from kailash_align.config import AdapterSignature
from kailash_align.exceptions import AdapterNotFoundError, AlignmentError

logger = logging.getLogger(__name__)

__all__ = ["AdapterRegistry", "AdapterVersion"]

# Valid stage transitions (monotonic: can only move forward)
_STAGE_ORDER = {"staging": 0, "shadow": 1, "production": 2, "archived": 3}


@dataclass
class AdapterVersion:
    """Returned by AdapterRegistry CRUD methods. Rich view of a stored adapter version."""

    adapter_id: str
    adapter_name: str
    version: str
    stage: str
    adapter_path: str
    base_model_id: str
    base_model_revision: Optional[str]
    lora_config: dict
    training_metrics: dict
    merge_status: str  # "separate" | "merged" | "exported"
    merged_model_path: Optional[str]
    gguf_path: Optional[str]
    quantization_config: Optional[dict]
    eval_results: Optional[dict]
    created_at: str


class AdapterRegistry:
    """Registry for LoRA/QLoRA adapters. Tracks adapters through their lifecycle:
    training -> evaluation -> merge -> GGUF export -> deployment.

    Uses an in-memory dict store for adapter and version records. Each adapter has
    versions with independent stage progression (staging -> shadow -> production -> archived).

    This registry uses composition: it HAS-A optional ModelRegistry reference,
    rather than inheriting from it.

    Args:
        model_registry: Optional ModelRegistry instance for cross-registry lookups.
    """

    def __init__(self, model_registry: Any = None) -> None:
        self._model_registry = model_registry
        self._adapters: dict[str, dict[str, Any]] = {}  # name -> adapter record
        self._versions: dict[str, list[dict[str, Any]]] = (
            {}
        )  # adapter_id -> [version records]
        logger.info("AdapterRegistry initialized")

    async def register_adapter(
        self,
        name: str,
        adapter_path: str,
        signature: AdapterSignature,
        training_metrics: Optional[dict] = None,
        training_data_ref: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> AdapterVersion:
        """Register a new adapter version.

        If adapter ``name`` does not exist, creates it. Always creates a new version.
        The new version starts in STAGING stage with merge_status="separate".

        Args:
            name: Human-readable adapter name.
            adapter_path: Path to saved LoRA adapter weights directory.
            signature: AdapterSignature describing the adapter.
            training_metrics: Training metrics dict (loss, eval_loss, etc.).
            training_data_ref: Reference to training dataset.
            tags: Optional tags for categorization.

        Returns:
            AdapterVersion with all metadata populated.
        """
        adapter = self._ensure_adapter(name, signature, training_data_ref, tags)
        adapter_id = adapter["id"]

        # Compute next version number
        existing_versions = self._versions.get(adapter_id, [])
        if existing_versions:
            max_ver = max(int(v["version"]) for v in existing_versions)
            next_version = str(max_ver + 1)
        else:
            next_version = "1"

        lora_config = {
            "r": signature.rank,
            "alpha": signature.alpha,
            "target_modules": list(signature.target_modules),
            "adapter_type": signature.adapter_type,
            "task_type": signature.task_type,
        }

        version_record: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "adapter_id": adapter_id,
            "version": next_version,
            "stage": "staging",
            "adapter_path": adapter_path,
            "base_model_id": signature.base_model_id,
            "lora_config_json": json.dumps(lora_config),
            "training_metrics_json": json.dumps(training_metrics or {}),
            "merge_status": "separate",
            "merged_model_path": None,
            "gguf_path": None,
            "quantization_config_json": None,
            "eval_results_json": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if adapter_id not in self._versions:
            self._versions[adapter_id] = []
        self._versions[adapter_id].append(version_record)

        logger.info("Registered adapter %s version %s", name, next_version)
        return self._to_adapter_version(adapter, version_record)

    async def get_adapter(
        self,
        name: str,
        version: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> AdapterVersion:
        """Get a specific adapter version.

        If version is None, returns the latest version.
        If stage is specified, returns the latest version in that stage.

        Args:
            name: Adapter name.
            version: Specific version number. If None, returns latest.
            stage: Filter by stage. If specified, returns latest in that stage.

        Returns:
            AdapterVersion with all metadata populated.

        Raises:
            AdapterNotFoundError: If adapter or version not found.
        """
        adapter = self._adapters.get(name)
        if adapter is None:
            raise AdapterNotFoundError(f"Adapter '{name}' not found")

        adapter_id = adapter["id"]
        versions = self._versions.get(adapter_id, [])
        if not versions:
            raise AdapterNotFoundError(f"Adapter '{name}' has no versions")

        if version is not None:
            matching = [v for v in versions if v["version"] == version]
            if not matching:
                raise AdapterNotFoundError(
                    f"Adapter '{name}' version {version} not found"
                )
            return self._to_adapter_version(adapter, matching[0])

        if stage is not None:
            matching = [v for v in versions if v["stage"] == stage]
            if not matching:
                raise AdapterNotFoundError(
                    f"Adapter '{name}' has no version in stage '{stage}'"
                )
            # Return latest version in that stage
            latest = max(matching, key=lambda v: int(v["version"]))
            return self._to_adapter_version(adapter, latest)

        # Return latest version overall
        latest = max(versions, key=lambda v: int(v["version"]))
        return self._to_adapter_version(adapter, latest)

    async def list_adapters(
        self,
        base_model_id: Optional[str] = None,
        stage: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[AdapterVersion]:
        """List adapters, optionally filtered by base model, stage, or tags.

        Returns the latest version of each matching adapter.

        Args:
            base_model_id: Filter by base model HuggingFace ID.
            stage: Filter by stage (returns adapters with at least one version in that stage).
            tags: Filter by tags (adapter must have all specified tags).

        Returns:
            List of AdapterVersion objects.
        """
        results: list[AdapterVersion] = []
        for name, adapter in self._adapters.items():
            # Tag filter
            if tags is not None:
                adapter_tags = json.loads(adapter.get("tags_json", "[]"))
                if not all(t in adapter_tags for t in tags):
                    continue

            # Base model filter
            if base_model_id is not None and adapter["base_model_id"] != base_model_id:
                continue

            adapter_id = adapter["id"]
            versions = self._versions.get(adapter_id, [])
            if not versions:
                continue

            # Stage filter
            if stage is not None:
                versions = [v for v in versions if v["stage"] == stage]
                if not versions:
                    continue

            latest = max(versions, key=lambda v: int(v["version"]))
            results.append(self._to_adapter_version(adapter, latest))

        return results

    async def promote(self, name: str, version: str, stage: str) -> AdapterVersion:
        """Promote an adapter version to a new stage.

        Stage transitions are monotonic: staging -> shadow -> production -> archived.
        Only forward transitions allowed.

        Args:
            name: Adapter name.
            version: Version number to promote.
            stage: Target stage.

        Returns:
            Updated AdapterVersion.

        Raises:
            AdapterNotFoundError: If adapter or version not found.
            AlignmentError: If stage transition is invalid (backward).
        """
        if stage not in _STAGE_ORDER:
            raise AlignmentError(
                f"Invalid stage '{stage}'. Must be one of: {list(_STAGE_ORDER.keys())}"
            )

        adapter = self._adapters.get(name)
        if adapter is None:
            raise AdapterNotFoundError(f"Adapter '{name}' not found")

        adapter_id = adapter["id"]
        versions = self._versions.get(adapter_id, [])
        matching = [v for v in versions if v["version"] == version]
        if not matching:
            raise AdapterNotFoundError(f"Adapter '{name}' version {version} not found")

        version_record = matching[0]
        current_stage = version_record["stage"]
        if _STAGE_ORDER[stage] <= _STAGE_ORDER[current_stage]:
            raise AlignmentError(
                f"Cannot promote from '{current_stage}' to '{stage}' "
                f"(only forward transitions allowed)"
            )

        version_record["stage"] = stage
        logger.info("Promoted adapter %s v%s to %s", name, version, stage)
        return self._to_adapter_version(adapter, version_record)

    async def update_merge_status(
        self,
        name: str,
        version: str,
        merge_status: str,
        merged_model_path: Optional[str] = None,
    ) -> AdapterVersion:
        """Update merge status after adapter merge (ALN-302).

        Args:
            name: Adapter name.
            version: Version number.
            merge_status: New merge status ('separate', 'merged', 'exported').
            merged_model_path: Path to merged model (required if merge_status='merged').

        Returns:
            Updated AdapterVersion.
        """
        if merge_status not in ("separate", "merged", "exported"):
            raise AlignmentError(
                f"Invalid merge_status '{merge_status}'. "
                f"Must be 'separate', 'merged', or 'exported'"
            )

        version_record = await self._get_version_record(name, version)
        version_record["merge_status"] = merge_status
        if merged_model_path is not None:
            version_record["merged_model_path"] = merged_model_path

        adapter = self._adapters[name]
        return self._to_adapter_version(adapter, version_record)

    async def update_gguf_path(
        self,
        name: str,
        version: str,
        gguf_path: str,
        quantization_config: Optional[dict] = None,
    ) -> AdapterVersion:
        """Update GGUF path after export (ALN-301).

        Args:
            name: Adapter name.
            version: Version number.
            gguf_path: Path to GGUF file.
            quantization_config: Quantization parameters used.

        Returns:
            Updated AdapterVersion.
        """
        version_record = await self._get_version_record(name, version)
        version_record["gguf_path"] = gguf_path
        if quantization_config is not None:
            version_record["quantization_config_json"] = json.dumps(quantization_config)
        version_record["merge_status"] = "exported"

        adapter = self._adapters[name]
        return self._to_adapter_version(adapter, version_record)

    async def update_eval_results(
        self,
        name: str,
        version: str,
        eval_results: dict,
    ) -> AdapterVersion:
        """Update evaluation results after evaluation (ALN-300).

        Args:
            name: Adapter name.
            version: Version number.
            eval_results: Evaluation scores dict.

        Returns:
            Updated AdapterVersion.
        """
        version_record = await self._get_version_record(name, version)
        version_record["eval_results_json"] = json.dumps(eval_results)

        adapter = self._adapters[name]
        return self._to_adapter_version(adapter, version_record)

    async def delete_adapter(self, name: str, version: Optional[str] = None) -> None:
        """Delete an adapter or a specific version.

        If version is None, deletes the adapter and all its versions.
        If version is specified, deletes only that version.

        Args:
            name: Adapter name.
            version: Specific version to delete. If None, deletes all.

        Raises:
            AdapterNotFoundError: If adapter or version not found.
        """
        adapter = self._adapters.get(name)
        if adapter is None:
            raise AdapterNotFoundError(f"Adapter '{name}' not found")

        adapter_id = adapter["id"]

        if version is None:
            # Delete entire adapter and all versions
            del self._adapters[name]
            self._versions.pop(adapter_id, None)
            logger.info("Deleted adapter %s and all versions", name)
        else:
            versions = self._versions.get(adapter_id, [])
            matching = [v for v in versions if v["version"] == version]
            if not matching:
                raise AdapterNotFoundError(
                    f"Adapter '{name}' version {version} not found"
                )
            versions.remove(matching[0])
            logger.info("Deleted adapter %s version %s", name, version)

    # --- Internal helpers ---

    def _ensure_adapter(
        self,
        name: str,
        signature: AdapterSignature,
        training_data_ref: Optional[str],
        tags: Optional[list[str]],
    ) -> dict[str, Any]:
        """Get or create the AlignAdapter record."""
        if name in self._adapters:
            return self._adapters[name]

        lora_config = {
            "r": signature.rank,
            "alpha": signature.alpha,
            "target_modules": list(signature.target_modules),
            "adapter_type": signature.adapter_type,
            "task_type": signature.task_type,
        }

        adapter: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "name": name,
            "model_type": "alignment",
            "base_model_id": signature.base_model_id,
            "base_model_revision": None,
            "lora_config_json": json.dumps(lora_config),
            "training_data_ref": training_data_ref,
            "tags_json": json.dumps(tags or []),
            "onnx_status": "not_applicable",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._adapters[name] = adapter
        return adapter

    async def _get_version_record(self, name: str, version: str) -> dict[str, Any]:
        """Get a version record, raising AdapterNotFoundError if missing."""
        adapter = self._adapters.get(name)
        if adapter is None:
            raise AdapterNotFoundError(f"Adapter '{name}' not found")

        adapter_id = adapter["id"]
        versions = self._versions.get(adapter_id, [])
        matching = [v for v in versions if v["version"] == version]
        if not matching:
            raise AdapterNotFoundError(f"Adapter '{name}' version {version} not found")
        return matching[0]

    def _to_adapter_version(
        self, adapter_record: dict[str, Any], version_record: dict[str, Any]
    ) -> AdapterVersion:
        """Convert internal records to AdapterVersion dataclass."""
        quant_json = version_record.get("quantization_config_json")
        eval_json = version_record.get("eval_results_json")

        return AdapterVersion(
            adapter_id=adapter_record["id"],
            adapter_name=adapter_record["name"],
            version=version_record["version"],
            stage=version_record["stage"],
            adapter_path=version_record["adapter_path"],
            base_model_id=version_record["base_model_id"],
            base_model_revision=adapter_record.get("base_model_revision"),
            lora_config=json.loads(version_record["lora_config_json"]),
            training_metrics=json.loads(version_record["training_metrics_json"]),
            merge_status=version_record["merge_status"],
            merged_model_path=version_record.get("merged_model_path"),
            gguf_path=version_record.get("gguf_path"),
            quantization_config=json.loads(quant_json) if quant_json else None,
            eval_results=json.loads(eval_json) if eval_json else None,
            created_at=version_record["created_at"],
        )
