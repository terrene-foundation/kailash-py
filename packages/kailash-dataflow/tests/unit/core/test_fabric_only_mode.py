# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for DataFlow fabric-only mode (#251).

When a DataFlow instance has sources/products but no @db.model classes
and no explicit database_url, it should skip database initialization
entirely — no connection pool, no migrations, no SQLite file creation.
"""

from __future__ import annotations

import pytest

from dataflow.core.engine import DataFlow


class TestFabricOnlyDetection:
    """DataFlow._fabric_only property detection."""

    def test_no_sources_no_models_is_not_fabric_only(self):
        db = DataFlow()
        assert not db._fabric_only

    def test_sources_no_models_no_url_is_fabric_only(self):
        db = DataFlow()
        db._sources["loans"] = {"adapter": None}
        assert db._fabric_only

    def test_sources_with_models_is_not_fabric_only(self):
        db = DataFlow()
        db._sources["loans"] = {"adapter": None}
        db._models["Loan"] = object()
        assert not db._fabric_only

    def test_explicit_database_url_is_not_fabric_only(self):
        db = DataFlow(database_url="sqlite:///:memory:")
        db._sources["loans"] = {"adapter": None}
        assert not db._fabric_only

    def test_products_without_models_is_fabric_only(self):
        db = DataFlow()
        db._products["dashboard"] = object()
        assert db._fabric_only


class TestFabricOnlyInitialize:
    """initialize() skips DB when fabric-only."""

    @pytest.mark.asyncio
    async def test_initialize_returns_true_without_db(self):
        db = DataFlow()
        db._sources["loans"] = {"adapter": None}
        result = await db.initialize()
        assert result is True

    def test_ensure_connected_skips_db(self):
        db = DataFlow()
        db._sources["loans"] = {"adapter": None}
        db._ensure_connected()
        assert db._connected is True
