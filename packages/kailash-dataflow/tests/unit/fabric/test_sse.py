# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for SSEManager (TODO-23)."""

from __future__ import annotations

import asyncio

import pytest

from dataflow.fabric.sse import SSEManager


class TestSSEManager:
    @pytest.mark.asyncio
    async def test_add_and_remove_client(self):
        mgr = SSEManager()
        queue = await mgr.add_client()
        assert mgr.client_count == 1
        await mgr.remove_client(queue)
        assert mgr.client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_clients(self):
        mgr = SSEManager()
        q1 = await mgr.add_client()
        q2 = await mgr.add_client()

        await mgr.broadcast("test_event", {"key": "value"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert "test_event" in msg1
        assert '"key": "value"' in msg1
        assert msg1 == msg2

    @pytest.mark.asyncio
    async def test_broadcast_product_updated(self):
        mgr = SSEManager()
        queue = await mgr.add_client()

        await mgr.broadcast_product_updated("dashboard", "2026-04-03T10:00:00Z")

        msg = queue.get_nowait()
        assert "product_updated" in msg
        assert "dashboard" in msg

    @pytest.mark.asyncio
    async def test_broadcast_source_health(self):
        mgr = SSEManager()
        queue = await mgr.add_client()

        await mgr.broadcast_source_health("crm", False, "error")

        msg = queue.get_nowait()
        assert "source_health" in msg
        assert "crm" in msg

    @pytest.mark.asyncio
    async def test_full_queue_drops_gracefully(self):
        mgr = SSEManager()
        queue = await mgr.add_client()

        # Fill the queue (maxsize=100)
        for i in range(100):
            queue.put_nowait(f"filler_{i}")

        # This should not raise — it drops the overflowed client
        await mgr.broadcast("overflow", {"test": True})
        # Client was removed due to full queue
        assert mgr.client_count == 0

    @pytest.mark.asyncio
    async def test_sse_handler_route(self):
        mgr = SSEManager()
        route = mgr.get_sse_handler()
        assert route["method"] == "GET"
        assert route["path"] == "/fabric/_events"
        assert route["metadata"]["type"] == "sse"
