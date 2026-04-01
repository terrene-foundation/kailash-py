# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for OnPremModelCache and OnPremConfig.

Runs without torch/transformers/huggingface_hub installed.
All heavy deps are mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kailash_align.config import OnPremConfig
from kailash_align.exceptions import CacheNotFoundError
from kailash_align.onprem import CachedModel, OnPremModelCache


class TestOnPremConfigDefaults:
    def test_offline_mode_default_false(self):
        config = OnPremConfig()
        assert config.offline_mode is False

    def test_model_cache_dir_expanded(self):
        """model_cache_dir should be expanded from ~ to absolute path."""
        config = OnPremConfig()
        assert "~" not in config.model_cache_dir
        assert Path(config.model_cache_dir).is_absolute()

    def test_ollama_host_default(self):
        config = OnPremConfig()
        assert config.ollama_host == "http://localhost:11434"

    def test_vllm_endpoint_default_none(self):
        config = OnPremConfig()
        assert config.vllm_endpoint is None

    def test_custom_cache_dir(self):
        config = OnPremConfig(model_cache_dir="/tmp/my-cache")
        assert config.model_cache_dir == "/tmp/my-cache"


class TestOfflineModeField:
    """Test offline_mode propagation in config."""

    def test_offline_mode_true(self):
        config = OnPremConfig(offline_mode=True)
        assert config.offline_mode is True

    def test_offline_mode_false(self):
        config = OnPremConfig(offline_mode=False)
        assert config.offline_mode is False

    def test_offline_mode_with_custom_cache(self):
        config = OnPremConfig(offline_mode=True, model_cache_dir="/opt/models")
        assert config.offline_mode is True
        assert config.model_cache_dir == "/opt/models"


class TestCachedModelDataclass:
    def test_to_dict(self):
        model = CachedModel(
            model_id="meta-llama/Llama-3.1-8B",
            cache_path="/cache/models--meta-llama--Llama-3.1-8B/snapshots/abc12345",
            size_bytes=16_000_000_000,
            revision="abc12345",
            is_complete=True,
        )
        d = model.to_dict()
        assert d["model_id"] == "meta-llama/Llama-3.1-8B"
        assert d["size_bytes"] == 16_000_000_000
        assert d["revision"] == "abc12345"
        assert d["is_complete"] is True

    def test_to_dict_none_revision(self):
        model = CachedModel(
            model_id="test/model",
            cache_path="/cache/test",
            size_bytes=0,
            revision=None,
            is_complete=False,
        )
        d = model.to_dict()
        assert d["revision"] is None
        assert d["is_complete"] is False


class TestOnPremModelCacheInit:
    def test_creates_cache_directory(self, tmp_path):
        cache_dir = tmp_path / "new-cache"
        assert not cache_dir.exists()
        cache = OnPremModelCache(cache_dir=str(cache_dir))
        assert cache_dir.exists()

    def test_cache_dir_property(self, tmp_path):
        cache = OnPremModelCache(cache_dir=str(tmp_path))
        assert cache.cache_dir == tmp_path


class TestListCachedWithEmptyCache:
    """Test list() behavior when cache directory is empty."""

    def test_list_empty_returns_empty(self, tmp_path):
        """list() on an empty cache returns an empty list."""
        import sys

        cache = OnPremModelCache(cache_dir=str(tmp_path))

        mock_cache_info = MagicMock()
        mock_cache_info.repos = []

        mock_hf = MagicMock()
        mock_hf.scan_cache_dir.return_value = mock_cache_info

        # huggingface_hub is imported locally inside list(), so patch sys.modules
        with patch.dict(sys.modules, {"huggingface_hub": mock_hf}):
            result = cache.list()

        assert result == []

    def test_list_with_scan_exception_returns_empty(self, tmp_path):
        """list() returns empty list when scan_cache_dir raises."""
        import sys

        cache = OnPremModelCache(cache_dir=str(tmp_path))

        mock_hf = MagicMock()
        mock_hf.scan_cache_dir.side_effect = Exception("corrupt cache")
        with patch.dict(sys.modules, {"huggingface_hub": mock_hf}):
            result = cache.list()
        assert result == []


class TestCachePathNotFound:
    """Test cache_path() when model is not cached."""

    def test_cache_path_raises_for_missing_model(self, tmp_path):
        import sys as _sys

        cache = OnPremModelCache(cache_dir=str(tmp_path))

        mock_hf = MagicMock()
        mock_hf.try_to_load_from_cache.return_value = None
        with patch.dict(_sys.modules, {"huggingface_hub": mock_hf}):
            with pytest.raises(CacheNotFoundError, match="not found in cache"):
                cache.cache_path("nonexistent/model")


class TestListWithModels:
    """Test list() with mocked huggingface_hub returning models."""

    def test_list_returns_cached_models(self, tmp_path):
        import sys as _sys

        cache = OnPremModelCache(cache_dir=str(tmp_path))

        mock_revision = MagicMock()
        mock_revision.snapshot_path = "/cache/snapshots/abc"
        mock_revision.size_on_disk = 8_000_000_000
        mock_revision.commit_hash = "abc12345678"

        mock_repo = MagicMock()
        mock_repo.repo_id = "meta-llama/Llama-3.1-8B"
        mock_repo.revisions = [mock_revision]

        mock_cache_info = MagicMock()
        mock_cache_info.repos = [mock_repo]

        mock_hf = MagicMock()
        mock_hf.scan_cache_dir.return_value = mock_cache_info
        with patch.dict(_sys.modules, {"huggingface_hub": mock_hf}):
            result = cache.list()

        assert len(result) == 1
        assert result[0].model_id == "meta-llama/Llama-3.1-8B"
        assert result[0].size_bytes == 8_000_000_000
        assert result[0].revision == "abc12345"  # Truncated to 8 chars
