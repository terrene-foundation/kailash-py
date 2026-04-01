# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AdapterRegistry."""
from __future__ import annotations

import pytest

from kailash_align.config import AdapterSignature
from kailash_align.exceptions import AdapterNotFoundError, AlignmentError
from kailash_align.registry import AdapterRegistry, AdapterVersion


class TestAdapterRegistryRegister:
    @pytest.mark.asyncio
    async def test_register_creates_adapter_and_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        result = await adapter_registry.register_adapter(
            name="test-adapter",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
            training_metrics={"loss": 0.42},
        )
        assert isinstance(result, AdapterVersion)
        assert result.adapter_name == "test-adapter"
        assert result.version == "1"
        assert result.stage == "staging"
        assert result.adapter_path == "/path/to/adapter"
        assert result.base_model_id == "meta-llama/Llama-3.1-8B"
        assert result.merge_status == "separate"
        assert result.training_metrics == {"loss": 0.42}
        assert result.lora_config["r"] == 16
        assert result.lora_config["alpha"] == 32
        assert result.gguf_path is None
        assert result.merged_model_path is None

    @pytest.mark.asyncio
    async def test_register_increments_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v1 = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        v2 = await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        assert v1.version == "1"
        assert v2.version == "2"
        assert v1.adapter_id == v2.adapter_id  # Same adapter, different versions

    @pytest.mark.asyncio
    async def test_register_with_tags(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        result = await adapter_registry.register_adapter(
            name="tagged",
            adapter_path="/tagged",
            signature=sample_signature,
            tags=["production", "customer-service"],
        )
        assert result.adapter_name == "tagged"

    @pytest.mark.asyncio
    async def test_register_with_training_data_ref(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        result = await adapter_registry.register_adapter(
            name="with-ref",
            adapter_path="/ref",
            signature=sample_signature,
            training_data_ref="datasets/my-sft-data",
        )
        assert result.version == "1"


class TestAdapterRegistryGet:
    @pytest.mark.asyncio
    async def test_get_latest_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        result = await adapter_registry.get_adapter("test")
        assert result.version == "2"
        assert result.adapter_path == "/v2"

    @pytest.mark.asyncio
    async def test_get_specific_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        result = await adapter_registry.get_adapter("test", version="1")
        assert result.version == "1"
        assert result.adapter_path == "/v1"

    @pytest.mark.asyncio
    async def test_get_by_stage(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        v2 = await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        await adapter_registry.promote("test", v2.version, "production")

        # Get staging version (v1)
        staging = await adapter_registry.get_adapter("test", stage="staging")
        assert staging.version == "1"

        # Get production version (v2)
        prod = await adapter_registry.get_adapter("test", stage="production")
        assert prod.version == "2"

    @pytest.mark.asyncio
    async def test_get_nonexistent_adapter(self, adapter_registry: AdapterRegistry):
        with pytest.raises(AdapterNotFoundError, match="not found"):
            await adapter_registry.get_adapter("nonexistent")

    @pytest.mark.asyncio
    async def test_get_nonexistent_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AdapterNotFoundError, match="version 99"):
            await adapter_registry.get_adapter("test", version="99")

    @pytest.mark.asyncio
    async def test_get_nonexistent_stage(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AdapterNotFoundError, match="no version in stage"):
            await adapter_registry.get_adapter("test", stage="production")


class TestAdapterRegistryList:
    @pytest.mark.asyncio
    async def test_list_empty(self, adapter_registry: AdapterRegistry):
        result = await adapter_registry.list_adapters()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="adapter-a", adapter_path="/a", signature=sample_signature
        )
        await adapter_registry.register_adapter(
            name="adapter-b", adapter_path="/b", signature=sample_signature
        )
        result = await adapter_registry.list_adapters()
        assert len(result) == 2
        names = {r.adapter_name for r in result}
        assert names == {"adapter-a", "adapter-b"}

    @pytest.mark.asyncio
    async def test_list_by_base_model(self, adapter_registry: AdapterRegistry):
        sig_llama = AdapterSignature(base_model_id="meta-llama/Llama-3.1-8B")
        sig_mistral = AdapterSignature(base_model_id="mistralai/Mistral-7B")

        await adapter_registry.register_adapter(
            name="llama-adapter", adapter_path="/llama", signature=sig_llama
        )
        await adapter_registry.register_adapter(
            name="mistral-adapter", adapter_path="/mistral", signature=sig_mistral
        )

        result = await adapter_registry.list_adapters(
            base_model_id="meta-llama/Llama-3.1-8B"
        )
        assert len(result) == 1
        assert result[0].adapter_name == "llama-adapter"

    @pytest.mark.asyncio
    async def test_list_by_tags(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="tagged",
            adapter_path="/tagged",
            signature=sample_signature,
            tags=["prod", "customer-service"],
        )
        await adapter_registry.register_adapter(
            name="untagged", adapter_path="/untagged", signature=sample_signature
        )

        result = await adapter_registry.list_adapters(tags=["prod"])
        assert len(result) == 1
        assert result[0].adapter_name == "tagged"


class TestAdapterRegistryPromote:
    @pytest.mark.asyncio
    async def test_promote_staging_to_shadow(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        result = await adapter_registry.promote("test", v.version, "shadow")
        assert result.stage == "shadow"

    @pytest.mark.asyncio
    async def test_promote_to_production(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.promote("test", v.version, "shadow")
        result = await adapter_registry.promote("test", v.version, "production")
        assert result.stage == "production"

    @pytest.mark.asyncio
    async def test_promote_backward_rejected(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.promote("test", v.version, "production")
        with pytest.raises(AlignmentError, match="only forward transitions"):
            await adapter_registry.promote("test", v.version, "staging")

    @pytest.mark.asyncio
    async def test_promote_same_stage_rejected(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AlignmentError, match="only forward transitions"):
            await adapter_registry.promote("test", v.version, "staging")

    @pytest.mark.asyncio
    async def test_promote_invalid_stage(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AlignmentError, match="Invalid stage"):
            await adapter_registry.promote("test", v.version, "invalid")

    @pytest.mark.asyncio
    async def test_promote_nonexistent_adapter(self, adapter_registry: AdapterRegistry):
        with pytest.raises(AdapterNotFoundError):
            await adapter_registry.promote("nonexistent", "1", "shadow")


class TestAdapterRegistryUpdate:
    @pytest.mark.asyncio
    async def test_update_merge_status(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        result = await adapter_registry.update_merge_status(
            "test", v.version, "merged", merged_model_path="/merged"
        )
        assert result.merge_status == "merged"
        assert result.merged_model_path == "/merged"

    @pytest.mark.asyncio
    async def test_update_merge_status_invalid(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AlignmentError, match="Invalid merge_status"):
            await adapter_registry.update_merge_status("test", v.version, "invalid")

    @pytest.mark.asyncio
    async def test_update_gguf_path(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        result = await adapter_registry.update_gguf_path(
            "test",
            v.version,
            "/model.gguf",
            quantization_config={"method": "q4_k_m"},
        )
        assert result.gguf_path == "/model.gguf"
        assert result.quantization_config == {"method": "q4_k_m"}
        assert result.merge_status == "exported"

    @pytest.mark.asyncio
    async def test_update_eval_results(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        v = await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        eval_results = {"mmlu": 0.72, "hellaswag": 0.85}
        result = await adapter_registry.update_eval_results(
            "test", v.version, eval_results
        )
        assert result.eval_results == eval_results


class TestAdapterRegistryDelete:
    @pytest.mark.asyncio
    async def test_delete_all_versions(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        await adapter_registry.delete_adapter("test")

        with pytest.raises(AdapterNotFoundError):
            await adapter_registry.get_adapter("test")

    @pytest.mark.asyncio
    async def test_delete_specific_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v2", signature=sample_signature
        )
        await adapter_registry.delete_adapter("test", version="1")

        # v2 should still exist
        result = await adapter_registry.get_adapter("test")
        assert result.version == "2"

        # v1 should be gone
        with pytest.raises(AdapterNotFoundError, match="version 1"):
            await adapter_registry.get_adapter("test", version="1")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_adapter(self, adapter_registry: AdapterRegistry):
        with pytest.raises(AdapterNotFoundError):
            await adapter_registry.delete_adapter("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_version(
        self, adapter_registry: AdapterRegistry, sample_signature: AdapterSignature
    ):
        await adapter_registry.register_adapter(
            name="test", adapter_path="/v1", signature=sample_signature
        )
        with pytest.raises(AdapterNotFoundError, match="version 99"):
            await adapter_registry.delete_adapter("test", version="99")


class TestAdapterRegistryComposition:
    def test_not_inheriting_from_model_registry(self):
        """AdapterRegistry uses composition, not inheritance."""
        # Verify AdapterRegistry does NOT inherit from any ModelRegistry
        bases = AdapterRegistry.__mro__
        base_names = [b.__name__ for b in bases]
        assert "ModelRegistry" not in base_names

    def test_accepts_optional_model_registry(self):
        """AdapterRegistry accepts an optional model_registry parameter."""
        registry = AdapterRegistry(model_registry=None)
        assert registry._model_registry is None

        fake_registry = object()
        registry2 = AdapterRegistry(model_registry=fake_registry)
        assert registry2._model_registry is fake_registry
