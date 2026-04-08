# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for FabricServingLayer (TODO-14, TODO-15, TODO-24).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.products import ProductRegistration
from dataflow.fabric.serving import FabricServingLayer, validate_filter


def _make_product(
    name: str = "dashboard",
    mode: str = "materialized",
    depends_on: list = None,
) -> ProductRegistration:
    async def _fn(ctx):
        return {}

    return ProductRegistration(
        name=name,
        fn=_fn,
        mode=ProductMode(mode),
        depends_on=depends_on or ["User"],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
    )


class _MockExpress:
    """Stub express to make write targets detectable."""

    pass


class _MockPipeline:
    """Mock pipeline that mirrors the real ``PipelineExecutor.get_cached``
    signature so the serving layer's calls in production code path
    (cache fast read with optional ``params`` and ``tenant_id``) work
    against the test stub without TypeError.
    """

    def __init__(self, cache: dict = None):
        self._cache = cache or {}

    async def get_cached(self, name, params=None, tenant_id=None):
        return self._cache.get(name)


class TestFabricServingLayer:
    def test_generates_routes_for_products(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)
        routes = serving.get_routes()

        paths = [r["path"] for r in routes]
        assert "/fabric/dashboard" in paths
        assert "/fabric/_batch" in paths

    def test_generates_write_routes_when_enabled(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(
            products=products,
            pipeline_executor=pipeline,
            express=_MockExpress(),  # Provide express so products become writable
            enable_writes=True,
        )
        routes = serving.get_routes()
        write_routes = [r for r in routes if r["method"] == "POST"]
        assert len(write_routes) >= 1

    @pytest.mark.asyncio
    async def test_product_handler_returns_cached_data(self):
        try:
            import msgpack

            data = {"total": 42}
            cached_bytes = msgpack.packb(data)
        except ImportError:
            import json

            data = {"total": 42}
            cached_bytes = json.dumps(data).encode("utf-8")

        metadata = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_ms": 150,
        }

        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline(cache={"dashboard": (cached_bytes, metadata)})
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)

        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/dashboard")
        result = await handler()

        assert result["_status"] == 200
        assert result["data"]["total"] == 42
        assert result["_headers"]["X-Fabric-Freshness"] == "fresh"
        assert result["_headers"]["X-Fabric-Mode"] == "materialized"

    @pytest.mark.asyncio
    async def test_cold_product_returns_202(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)

        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/dashboard")
        result = await handler()

        assert result["_status"] == 202
        assert result["_headers"]["X-Fabric-Freshness"] == "cold"

    @pytest.mark.asyncio
    async def test_batch_handler(self):
        try:
            import msgpack

            data_a = msgpack.packb({"a": 1})
            data_b = msgpack.packb({"b": 2})
        except ImportError:
            import json

            data_a = json.dumps({"a": 1}).encode("utf-8")
            data_b = json.dumps({"b": 2}).encode("utf-8")

        meta = {"cached_at": datetime.now(timezone.utc).isoformat()}

        products = {
            "a": _make_product("a"),
            "b": _make_product("b"),
        }
        pipeline = _MockPipeline(cache={"a": (data_a, meta), "b": (data_b, meta)})
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)

        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/_batch")
        result = await handler(products="a,b")

        assert result["_status"] == 200
        assert "a" in result["data"]
        assert "b" in result["data"]


class TestFilterValidation:
    def test_allowed_operators_pass(self):
        f = {"age": {"$gt": 18, "$lt": 65}}
        assert validate_filter(f) == f

    def test_disallowed_operator_raises(self):
        with pytest.raises(ValueError, match="Disallowed filter operator"):
            validate_filter({"name": {"$regex": ".*admin.*"}})

    def test_where_operator_in_nested_dict_blocked(self):
        """$where inside a nested value dict is blocked."""
        with pytest.raises(ValueError, match="Disallowed"):
            validate_filter({"field": {"$where": "this.admin === true"}})

    def test_non_operator_keys_pass(self):
        f = {"name": "Alice", "active": True}
        assert validate_filter(f) == f


# ---------------------------------------------------------------------------
# Parameter Validation Tests (security HIGH from red team)
# ---------------------------------------------------------------------------


class TestParameterValidation:
    """Validates consumer and refresh query parameters."""

    def test_valid_consumer_accepted(self):
        from dataflow.fabric.serving import _validate_consumer_param

        assert _validate_consumer_param("my-consumer_01") is None

    def test_consumer_too_long_rejected(self):
        from dataflow.fabric.serving import _validate_consumer_param

        err = _validate_consumer_param("a" * 256)
        assert err is not None
        assert "maximum length" in err

    def test_consumer_empty_string_rejected(self):
        from dataflow.fabric.serving import _validate_consumer_param

        err = _validate_consumer_param("")
        assert err is not None
        assert "empty" in err

    def test_consumer_special_chars_rejected(self):
        from dataflow.fabric.serving import _validate_consumer_param

        err = _validate_consumer_param("../../etc/passwd")
        assert err is not None
        assert "alphanumeric" in err

    def test_consumer_spaces_rejected(self):
        from dataflow.fabric.serving import _validate_consumer_param

        err = _validate_consumer_param("my consumer")
        assert err is not None

    def test_consumer_non_string_rejected(self):
        from dataflow.fabric.serving import _validate_consumer_param

        err = _validate_consumer_param(["list"])
        assert err is not None
        assert "string" in err

    def test_valid_refresh_true(self):
        from dataflow.fabric.serving import _validate_refresh_param

        assert _validate_refresh_param("true") is None

    def test_valid_refresh_false(self):
        from dataflow.fabric.serving import _validate_refresh_param

        assert _validate_refresh_param("false") is None

    def test_refresh_invalid_value_rejected(self):
        from dataflow.fabric.serving import _validate_refresh_param

        err = _validate_refresh_param("yes")
        assert err is not None
        assert "'true' or 'false'" in err

    def test_refresh_non_string_rejected(self):
        from dataflow.fabric.serving import _validate_refresh_param

        err = _validate_refresh_param(123)
        assert err is not None
        assert "string" in err

    @pytest.mark.asyncio
    async def test_handler_rejects_invalid_refresh(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)
        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/dashboard")

        result = await handler(refresh="yes")
        assert result["_status"] == 400
        assert "'true' or 'false'" in result["error"]

    @pytest.mark.asyncio
    async def test_handler_rejects_special_char_consumer(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)
        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/dashboard")

        result = await handler(consumer="../../hack")
        assert result["_status"] == 400
        assert "alphanumeric" in result["error"]

    @pytest.mark.asyncio
    async def test_handler_does_not_leak_consumer_list(self):
        products = {"dashboard": _make_product("dashboard")}
        pipeline = _MockPipeline()
        serving = FabricServingLayer(products=products, pipeline_executor=pipeline)
        routes = serving.get_routes()
        handler = next(r["handler"] for r in routes if r["path"] == "/fabric/dashboard")

        result = await handler(consumer="nonexistent")
        assert result["_status"] == 400
        # Error should NOT contain "Available consumers:" list
        assert "Available consumers" not in result.get("error", "")
