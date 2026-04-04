# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
MCP tool generation from Data Fabric products.

Generates MCP-compatible tool definitions from registered data products,
enabling AI agents to query fabric products via the Model Context Protocol.

``generate_mcp_tools`` produces tool definition dicts that conform to the
MCP tool specification.  ``register_with_mcp`` performs optional
auto-registration with a kailash-mcp server instance (lazy import).
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List

from dataflow.fabric.products import ProductRegistration

logger = logging.getLogger(__name__)

__all__ = [
    "generate_mcp_tools",
    "register_with_mcp",
]


def _product_params_to_schema(product: ProductRegistration) -> Dict[str, Any]:
    """Derive a JSON Schema ``inputSchema`` from a product's function signature.

    For *materialized* products the schema has no required properties (the
    cached result is returned as-is).  For *parameterized* products the
    function's keyword arguments (excluding ``ctx`` / ``context``) are
    mapped to string properties.  For *virtual* products the same
    introspection applies.

    Returns:
        A JSON Schema dict suitable for the MCP ``inputSchema`` field.
    """
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
    }

    if product.mode.value == "materialized":
        # Materialized products take no user parameters
        return schema

    # Introspect the product function for parameters
    try:
        sig = inspect.signature(product.fn)
    except (ValueError, TypeError):
        return schema

    skip_params = {"ctx", "context", "self", "cls"}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in skip_params:
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        prop: Dict[str, Any] = {"type": "string", "description": param_name}

        # Attempt to infer type from annotation
        if param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
            if ann is int or ann is float:
                prop["type"] = "number"
            elif ann is bool:
                prop["type"] = "boolean"
            # Default remains "string" for str and unrecognised types

        schema["properties"][param_name] = prop

        # Parameters without defaults are required
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    if required:
        schema["required"] = required

    return schema


def generate_mcp_tools(
    products: Dict[str, ProductRegistration],
) -> List[Dict[str, Any]]:
    """Generate MCP tool definitions from product registrations.

    Each product becomes one MCP tool with:

    - ``name``: ``get_{product_name}``
    - ``description``: Human-readable description
    - ``inputSchema``: JSON Schema derived from the product function

    Args:
        products: Registered products (typically ``FabricRuntime._products``).

    Returns:
        List of MCP tool definition dicts.
    """
    tools: List[Dict[str, Any]] = []

    for name, product in products.items():
        tool: Dict[str, Any] = {
            "name": f"get_{name}",
            "description": (
                f"Read the '{name}' data product " f"(mode: {product.mode.value})"
            ),
            "inputSchema": _product_params_to_schema(product),
        }
        tools.append(tool)

    return tools


def _make_mcp_handler(fabric_runtime: Any, tool_name: str) -> Callable[..., Any]:
    """Create an async handler that bridges an MCP tool call to the serving layer.

    The handler calls the fabric serving layer's product handler, passing
    MCP tool arguments as keyword parameters.

    Args:
        fabric_runtime: The ``FabricRuntime`` instance.
        tool_name: The MCP tool name (e.g. ``get_dashboard``).

    Returns:
        An async callable suitable for MCP tool registration.
    """
    # Strip the "get_" prefix to recover the product name
    product_name = tool_name[4:] if tool_name.startswith("get_") else tool_name

    async def handler(**kwargs: Any) -> Any:
        """MCP tool handler — delegates to the fabric serving layer."""
        serving = fabric_runtime.serving
        if serving is None:
            return {"error": "Fabric serving layer not initialised"}

        # Use the serving layer's product handler
        routes = serving.get_routes()
        for route in routes:
            if route["path"] == f"/fabric/{product_name}" and route["method"] == "GET":
                result = await route["handler"](**kwargs)
                # Strip internal status/header metadata — return data only
                if isinstance(result, dict) and "data" in result:
                    return result["data"]
                return result

        return {"error": f"Product '{product_name}' not found"}

    handler.__name__ = f"mcp_{tool_name}"
    return handler


def register_with_mcp(fabric_runtime: Any, mcp_server: Any) -> int:
    """Register all fabric products as MCP tools on the given server.

    Requires ``kailash-mcp`` to be installed. Raises ``ImportError`` with
    a helpful message if it is not available.

    Args:
        fabric_runtime: The ``FabricRuntime`` instance.
        mcp_server: A kailash-mcp ``MCPServer`` instance.

    Returns:
        Number of tools registered.

    Raises:
        ImportError: If ``kailash-mcp`` is not installed.
    """
    try:
        from kailash_mcp import MCPServer  # noqa: F401 — existence check
    except ImportError:
        raise ImportError(
            "kailash-mcp is required for MCP integration. "
            "Install it with: pip install kailash-mcp"
        )

    tools = generate_mcp_tools(fabric_runtime._products)

    for tool in tools:
        handler = _make_mcp_handler(fabric_runtime, tool["name"])
        mcp_server.register_tool(tool, handler)

    logger.info("Registered %d fabric products as MCP tools", len(tools))
    return len(tools)
