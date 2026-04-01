# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for AlignmentServing (ALN-301).

These tests run without torch/transformers/llama_cpp installed.
All heavy dependencies are mocked.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash_align.config import ServingConfig
from kailash_align.exceptions import ServingError
from kailash_align.serving import (
    QUANTIZATION_TYPES,
    SUPPORTED_ARCHITECTURES,
    AlignmentServing,
)


class TestSupportedArchitectures:
    """Test the SUPPORTED_ARCHITECTURES constant."""

    def test_llama_fully_supported(self):
        assert SUPPORTED_ARCHITECTURES["LlamaForCausalLM"] == "fully_supported"

    def test_mistral_fully_supported(self):
        assert SUPPORTED_ARCHITECTURES["MistralForCausalLM"] == "fully_supported"

    def test_phi3_supported(self):
        assert SUPPORTED_ARCHITECTURES["Phi3ForCausalLM"] == "supported"

    def test_qwen2_supported(self):
        assert SUPPORTED_ARCHITECTURES["Qwen2ForCausalLM"] == "supported"

    def test_unsupported_arch_not_in_dict(self):
        assert "GPT2LMHeadModel" not in SUPPORTED_ARCHITECTURES

    def test_architecture_count(self):
        """Exactly 4 architectures are supported."""
        assert len(SUPPORTED_ARCHITECTURES) == 4


class TestQuantizationTypes:
    def test_f16_maps_to_none(self):
        assert QUANTIZATION_TYPES["f16"] is None

    def test_q4_k_m_maps_to_string(self):
        assert QUANTIZATION_TYPES["q4_k_m"] == "q4_k_m"

    def test_q8_0_maps_to_string(self):
        assert QUANTIZATION_TYPES["q8_0"] == "q8_0"


class TestModelNameValidation:
    """Test the model_name validation regex used in _ollama_create."""

    PATTERN = re.compile(r"^[a-zA-Z0-9_:.-]+$")

    def test_simple_name_valid(self):
        assert self.PATTERN.match("my-model")

    def test_name_with_tag_valid(self):
        assert self.PATTERN.match("my-model:latest")

    def test_name_with_dots_valid(self):
        assert self.PATTERN.match("org.model.v1")

    def test_name_with_underscore_valid(self):
        assert self.PATTERN.match("my_model_v2")

    def test_empty_name_invalid(self):
        assert not self.PATTERN.match("")

    def test_name_with_spaces_invalid(self):
        assert not self.PATTERN.match("my model")

    def test_name_with_semicolon_invalid(self):
        assert not self.PATTERN.match("model;rm -rf")

    def test_name_with_slash_invalid(self):
        assert not self.PATTERN.match("model/name")


class TestModelfileGeneration:
    """Test _write_modelfile output structure."""

    def test_modelfile_basic(self, tmp_path):
        config = ServingConfig(system_prompt=None)
        serving = AlignmentServing(config=config)

        gguf_path = tmp_path / "test.gguf"
        modelfile_path = tmp_path / "Modelfile"
        serving._write_modelfile(modelfile_path, gguf_path)

        content = modelfile_path.read_text()
        assert content.startswith(f"FROM {gguf_path}")
        assert "SYSTEM" not in content

    def test_modelfile_with_system_prompt(self, tmp_path):
        config = ServingConfig(system_prompt="You are a helpful assistant.")
        serving = AlignmentServing(config=config)

        gguf_path = tmp_path / "test.gguf"
        modelfile_path = tmp_path / "Modelfile"
        serving._write_modelfile(modelfile_path, gguf_path)

        content = modelfile_path.read_text()
        assert f"FROM {gguf_path}" in content
        assert 'SYSTEM """You are a helpful assistant."""' in content


class TestVllmConfigGeneration:
    """Test vLLM config generation."""

    @pytest.mark.asyncio
    async def test_generate_vllm_config_structure(self, tmp_path):
        """vLLM config produces correct JSON and launch script."""
        mock_registry = AsyncMock()
        mock_version = MagicMock()
        mock_version.merge_status = "merged"
        mock_version.merged_model_path = "/models/merged"
        mock_version.version = "1"
        mock_registry.get_adapter = AsyncMock(return_value=mock_version)

        serving = AlignmentServing(adapter_registry=mock_registry)
        output_dir = str(tmp_path / "vllm-out")
        result = await serving.generate_vllm_config(
            "test-adapter", output_path=output_dir
        )

        assert "config_path" in result
        assert "launch_script_path" in result
        assert "config" in result
        assert result["config"]["model"] == "/models/merged"
        assert result["config"]["dtype"] == "bfloat16"
        assert result["config"]["port"] == 8000

        # Verify launch script is executable
        launch = Path(result["launch_script_path"])
        assert launch.exists()
        assert launch.stat().st_mode & 0o100  # executable bit

    @pytest.mark.asyncio
    async def test_vllm_rejects_unmerged(self):
        """vLLM config rejects adapters that are not merged."""
        mock_registry = AsyncMock()
        mock_version = MagicMock()
        mock_version.merge_status = "separate"
        mock_version.version = "1"
        mock_version.adapter_name = "test"
        mock_registry.get_adapter = AsyncMock(return_value=mock_version)

        serving = AlignmentServing(adapter_registry=mock_registry)
        with pytest.raises(ServingError, match="not merged"):
            await serving.generate_vllm_config("test")


class TestByogPath:
    """Test the 'Bring Your Own GGUF' escape hatch."""

    @pytest.mark.asyncio
    async def test_byog_missing_file_raises(self):
        """BYOG with non-existent file raises ServingError."""
        mock_registry = AsyncMock()
        serving = AlignmentServing(adapter_registry=mock_registry)

        with patch.object(serving, "_check_ollama_available"):
            with pytest.raises(ServingError, match="GGUF file not found"):
                await serving.deploy_ollama("test", gguf_path="/nonexistent/model.gguf")

    @pytest.mark.asyncio
    async def test_byog_existing_file_proceeds(self, tmp_path):
        """BYOG with existing file skips export_gguf and proceeds to deploy."""
        gguf_file = tmp_path / "my-model.gguf"
        gguf_file.write_bytes(b"fake gguf data")

        mock_registry = AsyncMock()
        serving = AlignmentServing(adapter_registry=mock_registry)

        with patch.object(serving, "_check_ollama_available"):
            with patch.object(serving, "_write_modelfile") as mock_write:
                with patch.object(serving, "_ollama_create") as mock_create:
                    with patch.object(serving, "_ollama_verify") as mock_verify:
                        result = await serving.deploy_ollama(
                            "test-adapter",
                            gguf_path=str(gguf_file),
                            model_name="my-model",
                        )

        assert result["status"] == "deployed"
        assert result["model_name"] == "my-model"
        assert result["gguf_path"] == str(gguf_file)
        mock_write.assert_called_once()
        mock_create.assert_called_once()
        mock_verify.assert_called_once()


class TestDeployDispatch:
    """Test the unified deploy() dispatch method."""

    @pytest.mark.asyncio
    async def test_deploy_unknown_target(self):
        """deploy() raises ServingError for unknown targets."""
        config = ServingConfig.__new__(ServingConfig)
        object.__setattr__(config, "target", "unknown_target")
        object.__setattr__(config, "quantization", "q4_k_m")
        object.__setattr__(config, "system_prompt", None)
        object.__setattr__(config, "ollama_host", "http://localhost:11434")
        object.__setattr__(config, "validate_gguf", True)
        object.__setattr__(config, "validation_timeout", 120)

        serving = AlignmentServing(config=config)
        with pytest.raises(ServingError, match="Unknown deployment target"):
            await serving.deploy("test-adapter")

    @pytest.mark.asyncio
    async def test_deploy_requires_registry(self):
        """Serving operations require an AdapterRegistry."""
        serving = AlignmentServing(adapter_registry=None)
        with pytest.raises(ServingError, match="AdapterRegistry is required"):
            await serving.generate_vllm_config("test-adapter")
