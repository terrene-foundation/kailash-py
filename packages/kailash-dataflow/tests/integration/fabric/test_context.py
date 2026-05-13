# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for FabricContext, PipelineContext, PipelineScopedExpress (TODO-10).
"""

from __future__ import annotations

import pytest

from dataflow.fabric.context import (
    FabricContext,
    PipelineContext,
    PipelineScopedExpress,
    SourceHandle,
)


class TestFabricContextForTesting:
    def test_create_test_context(self):
        ctx = FabricContext.for_testing(
            express_data={"User": [{"id": "1", "name": "Alice"}]},
            source_data={"crm": {"deals": [1, 2, 3]}},
            products_cache={"dashboard": {"count": 42}},
        )
        assert ctx.tenant_id is None

    @pytest.mark.asyncio
    async def test_express_list(self):
        ctx = FabricContext.for_testing(
            express_data={
                "User": [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
            }
        )
        users = await ctx.express.list("User")
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_express_read(self):
        ctx = FabricContext.for_testing(
            express_data={"User": [{"id": "1", "name": "Alice"}]}
        )
        user = await ctx.express.read("User", "1")
        assert user["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_express_count(self):
        ctx = FabricContext.for_testing(
            express_data={"User": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
        )
        count = await ctx.express.count("User")
        assert count == 3

    @pytest.mark.asyncio
    async def test_source_handle(self):
        # Source data keyed by path — use "" as default path
        ctx = FabricContext.for_testing(source_data={"crm": {"": {"deals": [1, 2, 3]}}})
        handle = ctx.source("crm")
        assert isinstance(handle, SourceHandle)
        assert handle.name == "crm"
        data = await handle.fetch()
        assert data == {"deals": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_source_handle_with_path(self):
        ctx = FabricContext.for_testing(
            source_data={"crm": {"deals": [1, 2, 3], "contacts": [4, 5]}}
        )
        handle = ctx.source("crm")
        deals = await handle.fetch("deals")
        assert deals == [1, 2, 3]

    def test_source_not_found_raises(self):
        ctx = FabricContext.for_testing()
        with pytest.raises(KeyError, match="not registered"):
            ctx.source("nonexistent")

    def test_product_cache_access(self):
        ctx = FabricContext.for_testing(products_cache={"dashboard": {"count": 42}})
        assert ctx.product("dashboard") == {"count": 42}

    def test_product_not_found_raises(self):
        ctx = FabricContext.for_testing()
        with pytest.raises(KeyError, match="no cached result"):
            ctx.product("nonexistent")

    def test_tenant_id(self):
        ctx = FabricContext.for_testing(tenant_id="tenant-1")
        assert ctx.tenant_id == "tenant-1"


class TestPipelineScopedExpress:
    @pytest.mark.asyncio
    async def test_read_deduplication(self):
        """Two identical list() calls should hit cache on second call."""
        call_count = 0

        class CountingExpress:
            async def list(self, model, **kwargs):
                nonlocal call_count
                call_count += 1
                return [{"id": "1"}]

        scoped = PipelineScopedExpress(CountingExpress())
        result1 = await scoped.list("User")
        result2 = await scoped.list("User")
        assert result1 == result2
        assert call_count == 1  # Only one actual call

    @pytest.mark.asyncio
    async def test_different_filters_not_deduplicated(self):
        call_count = 0

        class CountingExpress:
            async def list(self, model, filter=None, **kwargs):
                nonlocal call_count
                call_count += 1
                return [{"id": "1"}]

        scoped = PipelineScopedExpress(CountingExpress())
        await scoped.list("User", filter={"active": True})
        await scoped.list("User", filter={"active": False})
        assert call_count == 2  # Different filters = different calls

    @pytest.mark.asyncio
    async def test_writes_not_cached(self):
        create_count = 0

        class CountingExpress:
            async def create(self, model, data, **kwargs):
                nonlocal create_count
                create_count += 1
                return data

        scoped = PipelineScopedExpress(CountingExpress())
        await scoped.create("User", {"name": "Alice"})
        await scoped.create("User", {"name": "Bob"})
        assert create_count == 2  # Both pass through

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        call_count = 0

        class CountingExpress:
            async def list(self, model, **kwargs):
                nonlocal call_count
                call_count += 1
                return [{"id": "1"}]

        scoped = PipelineScopedExpress(CountingExpress())
        await scoped.list("User")
        scoped.clear_cache()
        await scoped.list("User")
        assert call_count == 2  # Cache was cleared


class TestPipelineContext:
    @pytest.mark.asyncio
    async def test_pipeline_context_uses_scoped_express(self):
        ctx = PipelineContext(
            express=_StubExpress(),
            sources={},
            products_cache={},
        )
        assert isinstance(ctx.express, PipelineScopedExpress)

    @pytest.mark.asyncio
    async def test_pipeline_context_clears_cache(self):
        call_count = 0

        class CountingExpress:
            async def list(self, model, **kwargs):
                nonlocal call_count
                call_count += 1
                return []

        ctx = PipelineContext(
            express=CountingExpress(),
            sources={},
            products_cache={},
        )
        await ctx.express.list("User")
        await ctx.express.list("User")
        assert call_count == 1  # Cached
        ctx.clear_read_cache()
        await ctx.express.list("User")
        assert call_count == 2  # Cache cleared, fresh call


class _StubExpress:
    async def list(self, model, **kwargs):
        return []

    async def read(self, model, record_id, **kwargs):
        return None

    async def count(self, model, **kwargs):
        return 0
