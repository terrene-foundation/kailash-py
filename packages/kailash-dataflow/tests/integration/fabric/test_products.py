# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for product registration (TODO-09).
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow
from dataflow.fabric.config import RestSourceConfig
from dataflow.fabric.products import ProductRegistration, register_product


class TestProductRegistration:
    @pytest.fixture
    def db(self):
        db = DataFlow("sqlite:///:memory:", auto_migrate=False)

        @db.model
        class User:
            name: str

        db.source("crm", RestSourceConfig(url="https://api.example.com"))
        return db

    def test_register_product_via_decorator(self, db):
        @db.product("dashboard", depends_on=["User", "crm"])
        async def dashboard(ctx):
            return {"count": 1}

        assert "dashboard" in db.get_products()

    def test_product_registration_stores_metadata(self, db):
        @db.product("dashboard", depends_on=["User", "crm"], mode="materialized")
        async def dashboard(ctx):
            return {"count": 1}

        reg = db._products["dashboard"]
        assert isinstance(reg, ProductRegistration)
        assert reg.name == "dashboard"
        assert reg.depends_on == ["User", "crm"]
        assert reg.mode.value == "materialized"

    def test_duplicate_product_name_raises(self, db):
        @db.product("dashboard", depends_on=["User"])
        async def dashboard(ctx):
            return {}

        with pytest.raises(ValueError, match="already registered"):

            @db.product("dashboard", depends_on=["User"])
            async def dashboard2(ctx):
                return {}

    def test_invalid_mode_raises(self, db):
        with pytest.raises(ValueError, match="Invalid product mode"):

            @db.product("bad", depends_on=["User"], mode="realtime")
            async def bad(ctx):
                return {}

    def test_depends_on_unknown_name_raises(self, db):
        with pytest.raises(ValueError, match="not a registered model"):

            @db.product("bad", depends_on=["NonExistent"])
            async def bad(ctx):
                return {}

    def test_materialized_requires_depends_on(self, db):
        with pytest.raises(ValueError, match="requires at least one"):

            @db.product("bad", depends_on=[], mode="materialized")
            async def bad(ctx):
                return {}

    def test_virtual_mode_allows_empty_depends_on(self, db):
        @db.product("status", depends_on=[], mode="virtual")
        async def status(ctx):
            return {"ok": True}

        assert "status" in db.get_products()

    def test_invalid_cache_miss_raises(self, db):
        with pytest.raises(ValueError, match="Invalid cache_miss"):

            @db.product("bad", depends_on=["User"], cache_miss="never")
            async def bad(ctx):
                return {}

    def test_parameterized_mode(self, db):
        @db.product("users", depends_on=["User"], mode="parameterized")
        async def users(ctx, filter=None, page=1, limit=50):
            return []

        reg = db._products["users"]
        assert reg.mode.value == "parameterized"

    def test_product_depends_on_other_product(self, db):
        @db.product("base", depends_on=["User"])
        async def base(ctx):
            return {"total": 100}

        @db.product("summary", depends_on=["base"])
        async def summary(ctx):
            return {"base_total": ctx.product("base")["total"]}

        assert "summary" in db.get_products()
        assert db._products["summary"].depends_on == ["base"]


class TestRegisterProductDirect:
    def test_register_product_function(self):
        products = {}
        models = {"User": {"class": object, "fields": {}}}
        sources = {}

        async def my_product(ctx):
            return {"data": 1}

        register_product(
            products=products,
            models=models,
            sources=sources,
            name="test",
            fn=my_product,
            mode="materialized",
            depends_on=["User"],
        )

        assert "test" in products
        assert products["test"].fn is my_product
