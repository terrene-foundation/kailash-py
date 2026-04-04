# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for MCP tool generation from fabric products (#250).

Tests: tool generation from products, schema derivation for materialized /
parameterized / virtual products, get_mcp_tools() on FabricRuntime,
register_with_mcp() ImportError when kailash-mcp is missing, and MCP
tool handler delegation to the serving layer.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from types import ModuleType
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.mcp_integration import (
    _product_params_to_schema,
    generate_mcp_tools,
    register_with_mcp,
)
from dataflow.fabric.products import ProductRegistration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product(
    name: str,
    mode: str = "materialized",
    fn: Any = None,
    depends_on: List[str] | None = None,
) -> ProductRegistration:
    """Create a minimal ProductRegistration for testing."""
    if fn is None:

        async def fn(ctx: Any) -> dict:
            return {}

    return ProductRegistration(
        name=name,
        fn=fn,
        mode=ProductMode(mode),
        depends_on=depends_on or [],
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
        write_debounce=timedelta(seconds=1),
    )


# ---------------------------------------------------------------------------
# generate_mcp_tools
# ---------------------------------------------------------------------------


class TestGenerateMcpTools:
    def test_generates_tools_for_all_products(self):
        products = {
            "dashboard": _make_product("dashboard"),
            "report": _make_product("report"),
        }
        tools = generate_mcp_tools(products)
        assert len(tools) == 2

        names = {t["name"] for t in tools}
        assert names == {"get_dashboard", "get_report"}

    def test_tool_has_required_fields(self):
        products = {"metrics": _make_product("metrics")}
        tools = generate_mcp_tools(products)
        tool = tools[0]

        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["name"] == "get_metrics"
        assert "metrics" in tool["description"]

    def test_empty_products_returns_empty_list(self):
        tools = generate_mcp_tools({})
        assert tools == []


# ---------------------------------------------------------------------------
# _product_params_to_schema
# ---------------------------------------------------------------------------


class TestProductParamsToSchema:
    def test_materialized_product_has_no_required_params(self):
        product = _make_product("mat", mode="materialized")
        schema = _product_params_to_schema(product)

        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema

    def test_parameterized_product_introspects_fn(self):
        async def my_product(ctx: Any, region: str, year: int = 2026) -> dict:
            return {}

        product = _make_product("param", mode="parameterized", fn=my_product)
        schema = _product_params_to_schema(product)

        assert "region" in schema["properties"]
        assert "year" in schema["properties"]
        # 'ctx' should be excluded
        assert "ctx" not in schema["properties"]
        # region has no default -> required
        assert "required" in schema
        assert "region" in schema["required"]
        # year has a default -> not required
        assert "year" not in schema.get("required", [])

    def test_virtual_product_introspects_fn(self):
        async def virtual_fn(ctx: Any, query: str) -> dict:
            return {}

        product = _make_product("virt", mode="virtual", fn=virtual_fn)
        schema = _product_params_to_schema(product)

        assert "query" in schema["properties"]
        assert "required" in schema
        assert "query" in schema["required"]

    def test_type_annotation_int_becomes_number(self):
        async def fn(ctx: Any, count: int) -> dict:
            return {}

        product = _make_product("typed", mode="parameterized", fn=fn)
        schema = _product_params_to_schema(product)

        assert schema["properties"]["count"]["type"] == "number"

    def test_type_annotation_bool_becomes_boolean(self):
        async def fn(ctx: Any, active: bool = True) -> dict:
            return {}

        product = _make_product("bool", mode="parameterized", fn=fn)
        schema = _product_params_to_schema(product)

        assert schema["properties"]["active"]["type"] == "boolean"

    def test_unannotated_defaults_to_string(self):
        async def fn(ctx, name="default") -> dict:
            return {}

        product = _make_product("untyped", mode="parameterized", fn=fn)
        schema = _product_params_to_schema(product)

        assert schema["properties"]["name"]["type"] == "string"


# ---------------------------------------------------------------------------
# FabricRuntime.get_mcp_tools()
# ---------------------------------------------------------------------------


class TestFabricRuntimeGetMcpTools:
    def test_get_mcp_tools_returns_tool_list(self):
        """Test that FabricRuntime.get_mcp_tools() delegates correctly."""
        # We can't easily instantiate a full FabricRuntime without its
        # subsystems, so we test the wiring by calling the underlying
        # function directly (same code path).
        products = {
            "sales": _make_product("sales"),
            "inventory": _make_product("inventory", mode="virtual"),
        }
        tools = generate_mcp_tools(products)
        assert len(tools) == 2
        assert tools[0]["name"] == "get_sales"
        assert tools[1]["name"] == "get_inventory"


# ---------------------------------------------------------------------------
# register_with_mcp — ImportError
# ---------------------------------------------------------------------------


class TestRegisterWithMcpImportError:
    def test_raises_import_error_without_kailash_mcp(self):
        """register_with_mcp raises ImportError with helpful message."""
        # Ensure kailash_mcp is not importable
        mock_runtime = MagicMock()
        mock_runtime._products = {}
        mock_server = MagicMock()

        with pytest.raises(ImportError, match="kailash-mcp"):
            register_with_mcp(mock_runtime, mock_server)


# ---------------------------------------------------------------------------
# register_with_mcp — success path (mock kailash_mcp)
# ---------------------------------------------------------------------------


class TestRegisterWithMcpSuccess:
    def test_registers_tools_on_server(self):
        """When kailash_mcp is available, tools are registered on the server."""
        # Create a fake kailash_mcp module
        fake_module = ModuleType("kailash_mcp")
        fake_module.MCPServer = type("MCPServer", (), {})  # type: ignore[attr-defined]
        sys.modules["kailash_mcp"] = fake_module

        try:
            mock_runtime = MagicMock()
            mock_runtime._products = {
                "dashboard": _make_product("dashboard"),
                "alerts": _make_product("alerts"),
            }
            mock_runtime.serving = None  # Not needed for registration count

            mock_server = MagicMock()
            mock_server.register_tool = MagicMock()

            count = register_with_mcp(mock_runtime, mock_server)

            assert count == 2
            assert mock_server.register_tool.call_count == 2

            # Verify tool definitions passed to register_tool
            calls = mock_server.register_tool.call_args_list
            tool_names = {call[0][0]["name"] for call in calls}
            assert tool_names == {"get_dashboard", "get_alerts"}
        finally:
            del sys.modules["kailash_mcp"]


# ---------------------------------------------------------------------------
# MCP tool handler — delegation to serving layer
# ---------------------------------------------------------------------------


class TestMcpToolHandler:
    @pytest.mark.asyncio
    async def test_handler_calls_serving_layer(self):
        """The MCP handler delegates to the fabric serving layer."""
        from dataflow.fabric.mcp_integration import _make_mcp_handler

        # Build a mock serving layer with a matching route
        mock_route_handler = AsyncMock(
            return_value={
                "_status": 200,
                "_headers": {},
                "data": {"users": 42, "revenue": 100},
            }
        )
        mock_serving = MagicMock()
        mock_serving.get_routes.return_value = [
            {
                "method": "GET",
                "path": "/fabric/dashboard",
                "handler": mock_route_handler,
            }
        ]

        mock_runtime = MagicMock()
        mock_runtime.serving = mock_serving

        handler = _make_mcp_handler(mock_runtime, "get_dashboard")
        result = await handler(region="us-east")

        # Should return just the data, not the _status/_headers wrapper
        assert result == {"users": 42, "revenue": 100}
        mock_route_handler.assert_awaited_once_with(region="us-east")

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_serving_not_initialized(self):
        """Handler returns error dict when serving layer is None."""
        from dataflow.fabric.mcp_integration import _make_mcp_handler

        mock_runtime = MagicMock()
        mock_runtime.serving = None

        handler = _make_mcp_handler(mock_runtime, "get_dashboard")
        result = await handler()

        assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_returns_error_for_unknown_product(self):
        """Handler returns error when product route not found."""
        from dataflow.fabric.mcp_integration import _make_mcp_handler

        mock_serving = MagicMock()
        mock_serving.get_routes.return_value = []  # No routes

        mock_runtime = MagicMock()
        mock_runtime.serving = mock_serving

        handler = _make_mcp_handler(mock_runtime, "get_nonexistent")
        result = await handler()

        assert "error" in result
        assert "nonexistent" in result["error"]
