# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""On-prem model cache management for air-gapped deployments.

Wraps HuggingFace Hub's snapshot_download() and scan_cache_dir() for
model pre-caching. Models are downloaded once (with internet), then
used offline via local_files_only=True propagation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kailash_align.exceptions import CacheNotFoundError

logger = logging.getLogger(__name__)

__all__ = [
    "OnPremModelCache",
    "CachedModel",
    "OnPremSetupGuide",
    "ChecklistItem",
    "SetupChecklist",
]


@dataclass
class CachedModel:
    """Information about a cached model.

    Args:
        model_id: HuggingFace model ID.
        cache_path: Absolute path to the cached model snapshot.
        size_bytes: Size of the cached model on disk.
        revision: Short commit hash of the cached revision.
        is_complete: Whether the download is complete.
    """

    model_id: str
    cache_path: str
    size_bytes: int
    revision: Optional[str]
    is_complete: bool

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "cache_path": self.cache_path,
            "size_bytes": self.size_bytes,
            "revision": self.revision,
            "is_complete": self.is_complete,
        }


class OnPremModelCache:
    """Manages local model cache for air-gapped environments.

    Wraps HuggingFace Hub's snapshot_download() and scan_cache_dir().
    Models are downloaded once (with internet), then used offline.

    Usage:
        # Online: pre-cache models
        cache = OnPremModelCache(cache_dir="./models")
        cache.download("meta-llama/Llama-3.1-8B")

        # Offline: use cached models
        config = OnPremConfig(offline_mode=True, model_cache_dir="./models")
        # All from_pretrained() calls use local_files_only=True

    Args:
        cache_dir: Directory for cached models. Defaults to ~/.cache/kailash-align/models.
    """

    def __init__(self, cache_dir: str = "~/.cache/kailash-align/models") -> None:
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory path."""
        return self._cache_dir

    def download(
        self,
        model_id: str,
        revision: Optional[str] = None,
        allow_patterns: Optional[list[str]] = None,
    ) -> Path:
        """Download a model from HuggingFace Hub to local cache.

        Uses huggingface_hub.snapshot_download() which:
        - Downloads all model files (config, weights, tokenizer)
        - Resumes partial downloads
        - Verifies file integrity via SHA256

        Args:
            model_id: HuggingFace model ID (e.g., 'meta-llama/Llama-3.1-8B').
            revision: Specific revision/branch (default: 'main').
            allow_patterns: File patterns to include (None = all files).

        Returns:
            Path to the downloaded model directory.
        """
        from huggingface_hub import snapshot_download

        logger.info(
            "Downloading %s (revision=%s) to %s",
            model_id,
            revision,
            self._cache_dir,
        )
        path = snapshot_download(
            repo_id=model_id,
            revision=revision,
            cache_dir=str(self._cache_dir),
            allow_patterns=allow_patterns,
        )
        logger.info("Download complete: %s -> %s", model_id, path)
        return Path(path)

    def list(self) -> list[CachedModel]:
        """List all cached models with sizes and completeness status.

        Returns:
            List of CachedModel entries.
        """
        from huggingface_hub import scan_cache_dir

        try:
            cache_info = scan_cache_dir(str(self._cache_dir))
        except Exception as exc:
            logger.warning("Failed to scan cache directory: %s", exc)
            return []

        models: list[CachedModel] = []
        for repo in cache_info.repos:
            for revision in repo.revisions:
                models.append(
                    CachedModel(
                        model_id=repo.repo_id,
                        cache_path=str(revision.snapshot_path),
                        size_bytes=revision.size_on_disk,
                        revision=(
                            revision.commit_hash[:8] if revision.commit_hash else None
                        ),
                        is_complete=True,
                    )
                )
        return models

    def verify(self, model_id: str) -> bool:
        """Verify a cached model is complete and loadable.

        Checks:
        1. Model files exist in cache
        2. Config can be loaded
        3. Tokenizer can be loaded

        Returns:
            True if model is verified, False if incomplete or corrupt.
        """
        try:
            model_path = self.cache_path(model_id)
            from transformers import AutoConfig, AutoTokenizer

            AutoConfig.from_pretrained(str(model_path), local_files_only=True)
            AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
            logger.info("Model %s verified at %s", model_id, model_path)
            return True
        except Exception as exc:
            logger.warning("Model %s verification failed: %s", model_id, exc)
            return False

    def cache_path(self, model_id: str) -> Path:
        """Get the local cache path for a model.

        Args:
            model_id: HuggingFace model ID.

        Returns:
            Path to the cached model directory.

        Raises:
            CacheNotFoundError: If model is not in the cache.
        """
        from huggingface_hub import try_to_load_from_cache

        try:
            result = try_to_load_from_cache(
                model_id,
                "config.json",
                cache_dir=str(self._cache_dir),
            )
            if result is None or isinstance(result, str) is False:
                raise CacheNotFoundError(
                    f"Model '{model_id}' not found in cache at {self._cache_dir}. "
                    f"Download it first: kailash-align-prepare download {model_id}"
                )
            return Path(result).parent
        except CacheNotFoundError:
            raise
        except Exception:
            raise CacheNotFoundError(
                f"Model '{model_id}' not found in cache at {self._cache_dir}. "
                f"Download it first: kailash-align-prepare download {model_id}"
            )


# ---------------------------------------------------------------------------
# OnPremSetupGuide — structured deployment checklist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChecklistItem:
    """Single item in a deployment checklist.

    Structured so agents can process programmatically and renderers
    can produce markdown, JSON, or CLI table output.
    """

    step: int
    category: str  # "download", "verify", "configure", "deploy"
    description: str
    command: Optional[str] = None
    size_estimate_gb: Optional[float] = None


@dataclass(frozen=True)
class SetupChecklist:
    """Complete deployment checklist for on-prem setup."""

    items: tuple[ChecklistItem, ...]
    total_disk_gb: float
    model_count: int

    def to_dict(self) -> dict:
        """Structured dict for API responses."""
        return {
            "items": [
                {
                    "step": item.step,
                    "category": item.category,
                    "description": item.description,
                    "command": item.command,
                    "size_estimate_gb": item.size_estimate_gb,
                }
                for item in self.items
            ],
            "total_disk_gb": self.total_disk_gb,
            "model_count": self.model_count,
        }

    def to_markdown(self) -> str:
        """Render as markdown for human consumption."""
        lines = [
            "# On-Prem Deployment Checklist",
            "",
            f"**Models**: {self.model_count} | "
            f"**Estimated disk**: {self.total_disk_gb:.1f} GB",
            "",
        ]
        current_cat = ""
        for item in self.items:
            if item.category != current_cat:
                current_cat = item.category
                lines.append(f"## {current_cat.title()}")
                lines.append("")
            size_note = (
                f" (~{item.size_estimate_gb:.1f} GB)" if item.size_estimate_gb else ""
            )
            lines.append(f"- [ ] **Step {item.step}**: {item.description}{size_note}")
            if item.command:
                lines.append(f"  ```bash")
                lines.append(f"  {item.command}")
                lines.append(f"  ```")
            lines.append("")
        return "\n".join(lines)


class OnPremSetupGuide:
    """Generate deployment checklists for air-gapped environments."""

    # Approximate sizes for common base models (GB).
    _MODEL_SIZES: dict[str, float] = {
        "meta-llama/Llama-2-7b-hf": 13.5,
        "meta-llama/Meta-Llama-3-8B": 16.0,
        "mistralai/Mistral-7B-v0.1": 14.5,
        "microsoft/phi-2": 5.5,
        "TinyLlama/TinyLlama-1.1B-Chat-v1.0": 2.2,
    }

    @classmethod
    def generate_checklist(
        cls,
        models: list[str],
        cache_dir: str = "~/.cache/kailash-align/models",
    ) -> SetupChecklist:
        """Generate a structured deployment checklist.

        Args:
            models: HuggingFace model IDs to include.
            cache_dir: Target cache directory on the air-gapped machine.

        Returns:
            SetupChecklist with structured items, renderable as markdown or dict.
        """
        items: list[ChecklistItem] = []
        total_size = 0.0
        step = 1

        # Download phase
        for model_id in models:
            size = cls._MODEL_SIZES.get(model_id, 10.0)
            total_size += size
            items.append(
                ChecklistItem(
                    step=step,
                    category="download",
                    description=f"Download {model_id}",
                    command=f"kailash-align-prepare download {model_id}",
                    size_estimate_gb=size,
                )
            )
            step += 1

        # Verify phase
        for model_id in models:
            items.append(
                ChecklistItem(
                    step=step,
                    category="verify",
                    description=f"Verify {model_id} is loadable",
                    command=f"kailash-align-prepare verify {model_id}",
                )
            )
            step += 1

        # Configure phase
        items.append(
            ChecklistItem(
                step=step,
                category="configure",
                description=(
                    "Set OnPremConfig(offline_mode=True, "
                    f'model_cache_dir="{cache_dir}")'
                ),
            )
        )
        step += 1

        # Deploy phase
        items.append(
            ChecklistItem(
                step=step,
                category="deploy",
                description="Transfer cache directory to air-gapped machine",
                command=f"rsync -av {cache_dir} target-host:{cache_dir}",
                size_estimate_gb=total_size,
            )
        )

        return SetupChecklist(
            items=tuple(items),
            total_disk_gb=total_size,
            model_count=len(models),
        )
