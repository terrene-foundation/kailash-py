# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for KaizenModelBridge.

Runs without torch/transformers/kaizen_agents installed.
All external deps are mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash_align.bridge import (
    BridgeConfig,
    BridgeNotReadyError,
    KaizenModelBridge,
)


class TestBridgeConfigDefaults:
    def test_default_ollama_host(self):
        config = BridgeConfig()
        assert config.ollama_host == "http://localhost:11434"

    def test_default_vllm_endpoint_is_none(self):
        config = BridgeConfig()
        assert config.vllm_endpoint is None

    def test_default_strategy_is_none(self):
        config = BridgeConfig()
        assert config.default_strategy is None

    def test_frozen(self):
        config = BridgeConfig()
        with pytest.raises(AttributeError):
            config.ollama_host = "http://other:11434"  # type: ignore[misc]

    def test_custom_values(self):
        config = BridgeConfig(
            ollama_host="http://custom:1234",
            vllm_endpoint="http://vllm:8000/v1",
            default_strategy="vllm",
        )
        assert config.ollama_host == "http://custom:1234"
        assert config.vllm_endpoint == "http://vllm:8000/v1"
        assert config.default_strategy == "vllm"


class TestDelegateConfigForOllama:
    """Test _build_delegate_config for Ollama strategy."""

    def test_ollama_config_structure(self):
        registry = MagicMock()
        bridge = KaizenModelBridge(adapter_registry=registry)

        adapter_version = MagicMock()
        adapter_version.adapter_name = "my-finetuned-model"

        config = bridge._build_delegate_config(adapter_version, "ollama")

        assert config["model"] == "my-finetuned-model"
        assert config["adapter"] == "ollama"
        assert config["adapter_kwargs"]["host"] == "http://localhost:11434"

    def test_ollama_config_custom_host(self):
        registry = MagicMock()
        bridge_config = BridgeConfig(ollama_host="http://gpu-server:11434")
        bridge = KaizenModelBridge(adapter_registry=registry, config=bridge_config)

        adapter_version = MagicMock()
        adapter_version.adapter_name = "model-x"

        config = bridge._build_delegate_config(adapter_version, "ollama")
        assert config["adapter_kwargs"]["host"] == "http://gpu-server:11434"


class TestDelegateConfigForVllm:
    """Test _build_delegate_config for vLLM strategy."""

    def test_vllm_config_structure(self):
        registry = MagicMock()
        bridge_config = BridgeConfig(vllm_endpoint="http://vllm:8000/v1")
        bridge = KaizenModelBridge(adapter_registry=registry, config=bridge_config)

        adapter_version = MagicMock()
        adapter_version.adapter_name = "my-model"

        config = bridge._build_delegate_config(adapter_version, "vllm")

        assert config["model"] == "my-model"
        assert config["adapter"] == "openai"
        assert config["adapter_kwargs"]["base_url"] == "http://vllm:8000/v1"
        assert config["adapter_kwargs"]["api_key"] == "not-needed"

    def test_unknown_strategy_raises(self):
        registry = MagicMock()
        bridge = KaizenModelBridge(adapter_registry=registry)
        adapter_version = MagicMock()

        with pytest.raises(BridgeNotReadyError, match="Unknown strategy"):
            bridge._build_delegate_config(adapter_version, "tgi")


class TestBudgetUsdDocumentation:
    """Verify the budget_usd limitation is documented in the module and class docstrings."""

    def test_module_docstring_mentions_budget_usd(self):
        import kailash_align.bridge as bridge_mod

        assert "budget_usd" in bridge_mod.__doc__

    def test_class_docstring_mentions_budget_usd(self):
        assert "budget_usd" in KaizenModelBridge.__doc__

    def test_class_docstring_mentions_max_turns_alternative(self):
        assert "max_turns" in KaizenModelBridge.__doc__


class TestResolveStrategy:
    """Test auto-detection of serving strategy."""

    @pytest.mark.asyncio
    async def test_default_strategy_overrides_detection(self):
        registry = MagicMock()
        config = BridgeConfig(default_strategy="vllm")
        bridge = KaizenModelBridge(adapter_registry=registry, config=config)

        adapter_version = MagicMock()
        result = await bridge.resolve_strategy(adapter_version)
        assert result == "vllm"

    @pytest.mark.asyncio
    async def test_no_strategy_available_raises(self):
        registry = MagicMock()
        bridge = KaizenModelBridge(adapter_registry=registry)

        adapter_version = MagicMock()
        adapter_version.gguf_path = None
        adapter_version.adapter_name = "test"

        with pytest.raises(BridgeNotReadyError, match="Cannot determine"):
            await bridge.resolve_strategy(adapter_version)

    @pytest.mark.asyncio
    async def test_ollama_selected_when_available(self):
        registry = MagicMock()
        bridge = KaizenModelBridge(adapter_registry=registry)

        adapter_version = MagicMock()
        adapter_version.gguf_path = "/path/to/model.gguf"

        with patch.object(bridge, "_is_ollama_available", return_value=True):
            result = await bridge.resolve_strategy(adapter_version)
        assert result == "ollama"


class TestGetDelegateConfig:
    """Test get_delegate_config (the inspection-only path)."""

    @pytest.mark.asyncio
    async def test_returns_dict_without_creating_delegate(self):
        registry = AsyncMock()
        adapter_version = MagicMock()
        adapter_version.adapter_name = "fine-tuned-llama"
        adapter_version.gguf_path = "/path/to.gguf"
        registry.get_adapter = AsyncMock(return_value=adapter_version)

        bridge = KaizenModelBridge(adapter_registry=registry)

        with patch.object(bridge, "resolve_strategy", return_value="ollama"):
            config = await bridge.get_delegate_config("fine-tuned-llama")

        assert isinstance(config, dict)
        assert config["model"] == "fine-tuned-llama"
        assert config["adapter"] == "ollama"
