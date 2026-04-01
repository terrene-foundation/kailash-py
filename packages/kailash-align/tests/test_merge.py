# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AdapterMerger (ALN-302)."""
from __future__ import annotations

import pytest

from kailash_align.exceptions import MergeError
from kailash_align.merge import AdapterMerger, merge_adapter


class TestAdapterMerger:
    @pytest.mark.asyncio
    async def test_merge_requires_registry(self):
        """Merge requires AdapterRegistry."""
        merger = AdapterMerger(adapter_registry=None)
        with pytest.raises(MergeError, match="AdapterRegistry is required"):
            await merger.merge("test")

    @pytest.mark.asyncio
    async def test_merge_idempotent_already_merged(
        self, adapter_registry, sample_signature
    ):
        """If adapter is already merged, return existing path without re-merging."""
        v = await adapter_registry.register_adapter(
            name="test-merged",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
        )
        await adapter_registry.update_merge_status(
            "test-merged", v.version, "merged", merged_model_path="/merged/path"
        )

        merger = AdapterMerger(adapter_registry=adapter_registry)
        result = await merger.merge("test-merged")
        from pathlib import Path

        assert result == Path("/merged/path")

    @pytest.mark.asyncio
    async def test_merge_rejects_exported_adapter(
        self, adapter_registry, sample_signature
    ):
        """Cannot re-merge an adapter that has been exported to GGUF."""
        v = await adapter_registry.register_adapter(
            name="test-exported",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
        )
        await adapter_registry.update_gguf_path(
            "test-exported", v.version, "/path/to/gguf"
        )

        merger = AdapterMerger(adapter_registry=adapter_registry)
        with pytest.raises(MergeError, match="already been exported"):
            await merger.merge("test-exported")


class TestMergeAdapterConvenience:
    @pytest.mark.asyncio
    async def test_merge_adapter_requires_registry(self):
        """Convenience function also requires registry."""
        with pytest.raises(MergeError, match="AdapterRegistry is required"):
            await merge_adapter("test", adapter_registry=None)

    @pytest.mark.asyncio
    async def test_merge_adapter_idempotent(self, adapter_registry, sample_signature):
        """Convenience function also handles idempotent merge."""
        v = await adapter_registry.register_adapter(
            name="test-conv",
            adapter_path="/path/to/adapter",
            signature=sample_signature,
        )
        await adapter_registry.update_merge_status(
            "test-conv", v.version, "merged", merged_model_path="/merged"
        )

        from pathlib import Path

        result = await merge_adapter("test-conv", adapter_registry=adapter_registry)
        assert result == Path("/merged")
