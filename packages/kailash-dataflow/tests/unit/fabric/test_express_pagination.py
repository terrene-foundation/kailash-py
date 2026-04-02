# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for Express list() order_by parameter (GH #228 cross-SDK alignment).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExpressListOrderBy:
    """Verify order_by parameter on async Express.list() and sync express_sync.list()."""

    def _make_express(self):
        """Create a minimal DataFlowExpress instance with a mocked DataFlow db."""
        from dataflow.features.express import DataFlowExpress

        db = MagicMock()
        db._nodes = {}
        db._cache = None
        express = DataFlowExpress.__new__(DataFlowExpress)
        express._db = db
        express._default_cache_ttl = None
        express._timings = {}
        return express

    @pytest.mark.asyncio
    async def test_list_accepts_order_by_parameter(self):
        """order_by is accepted without raising TypeError."""
        express = self._make_express()

        node = MagicMock()
        node.async_run = AsyncMock(return_value=[{"id": 1, "name": "Alice"}])
        express._create_node = MagicMock(return_value=node)
        express._cache_get = AsyncMock(return_value=None)
        express._cache_set = AsyncMock()
        express._execute_with_timing = AsyncMock(
            return_value=[{"id": 1, "name": "Alice"}]
        )

        # Should not raise
        result = await express.list("User", order_by="name")
        assert result == [{"id": 1, "name": "Alice"}]

    @pytest.mark.asyncio
    async def test_list_passes_order_by_in_params(self):
        """order_by is included in the params passed to the node."""
        express = self._make_express()

        captured_params = {}
        records = [{"id": 1}]

        async def fake_execute(operation, coro):
            return await coro

        async def fake_async_run(**kwargs):
            captured_params.update(kwargs)
            return records

        node = MagicMock()
        node.async_run = fake_async_run
        express._create_node = MagicMock(return_value=node)
        express._cache_get = AsyncMock(return_value=None)
        express._cache_set = AsyncMock()
        express._execute_with_timing = fake_execute

        await express.list("User", order_by="created_at")

        assert "order_by" in captured_params
        assert captured_params["order_by"] == "created_at"

    @pytest.mark.asyncio
    async def test_list_omits_order_by_when_none(self):
        """order_by is NOT included in params when not provided (backwards compatibility)."""
        express = self._make_express()

        captured_params = {}
        records = [{"id": 1}]

        async def fake_execute(operation, coro):
            return await coro

        async def fake_async_run(**kwargs):
            captured_params.update(kwargs)
            return records

        node = MagicMock()
        node.async_run = fake_async_run
        express._create_node = MagicMock(return_value=node)
        express._cache_get = AsyncMock(return_value=None)
        express._cache_set = AsyncMock()
        express._execute_with_timing = fake_execute

        await express.list("User")

        assert "order_by" not in captured_params

    def test_sync_list_accepts_order_by_parameter(self):
        """SyncExpress.list() accepts order_by without raising TypeError."""
        from dataflow.features.express import SyncExpress

        async_express = MagicMock()
        async_express.list = AsyncMock(return_value=[{"id": 1}])

        sync = SyncExpress.__new__(SyncExpress)
        sync._express = async_express
        sync._run_sync = lambda coro: [{"id": 1}]

        # Should not raise
        result = sync.list("User", order_by="name")
        assert result == [{"id": 1}]

    def test_sync_list_passes_order_by_to_async(self):
        """SyncExpress.list() forwards order_by to the async Express.list()."""
        from dataflow.features.express import SyncExpress

        captured = {}

        async def fake_list(
            model,
            filter=None,
            limit=100,
            offset=0,
            order_by=None,
            cache_ttl=None,
            use_primary=False,
        ):
            captured["order_by"] = order_by
            return []

        async_express = MagicMock()
        async_express.list = fake_list

        sync = SyncExpress.__new__(SyncExpress)
        sync._express = async_express

        import asyncio

        sync._run_sync = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

        sync.list("User", order_by="updated_at")

        assert captured.get("order_by") == "updated_at"
