# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for MockSource (TODO-27)."""

from __future__ import annotations

import pytest

from dataflow.fabric.testing import MockSource


class TestMockSource:
    @pytest.mark.asyncio
    async def test_fetch_returns_configured_data(self):
        source = MockSource("test", data={"": {"key": "value"}, "items": [1, 2, 3]})
        await source.connect()
        result = await source.fetch("")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_fetch_path(self):
        source = MockSource("test", data={"items": [1, 2, 3]})
        await source.connect()
        result = await source.fetch("items")
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_detect_change_default_false(self):
        source = MockSource("test")
        await source.connect()
        assert await source.detect_change() is False

    @pytest.mark.asyncio
    async def test_trigger_change(self):
        source = MockSource("test")
        await source.connect()
        source.trigger_change()
        assert await source.detect_change() is True
        # Should reset after detection
        assert await source.detect_change() is False

    @pytest.mark.asyncio
    async def test_write_stores_data(self):
        source = MockSource("test")
        await source.connect()
        await source.write("items", [1, 2, 3])
        result = await source.fetch("items")
        assert result == [1, 2, 3]

    def test_source_type(self):
        source = MockSource("test")
        assert source.source_type == "mock"

    @pytest.mark.asyncio
    async def test_set_data(self):
        source = MockSource("test")
        source.set_data("path", {"updated": True})
        await source.connect()
        result = await source.fetch("path")
        assert result == {"updated": True}
