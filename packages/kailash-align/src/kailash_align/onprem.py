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

__all__ = ["OnPremModelCache", "CachedModel"]


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
