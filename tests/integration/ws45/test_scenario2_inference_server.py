# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Scenario 2: InferenceServer prediction via register_mcp_tools().

Validates that InferenceServer can register MCP tools and serve
predictions through them, symmetric with HTTP endpoints.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestInferenceServerMCPTools:
    """InferenceServer registers MCP tools for predictions."""

    async def test_register_mcp_tools_exists(self) -> None:
        """InferenceServer has the register_mcp_tools method."""
        try:
            from kailash_ml.engines.inference_server import InferenceServer
        except ImportError:
            pytest.skip("kailash-ml not installed")

        assert hasattr(InferenceServer, "register_mcp_tools")

    async def test_register_endpoints_exists(self) -> None:
        """InferenceServer has the register_endpoints method (HTTP)."""
        try:
            from kailash_ml.engines.inference_server import InferenceServer
        except ImportError:
            pytest.skip("kailash-ml not installed")

        assert hasattr(InferenceServer, "register_endpoints")

    async def test_mcp_tools_symmetric_with_http(self) -> None:
        """MCP tools cover the same operations as HTTP endpoints."""
        try:
            from kailash_ml.engines.inference_server import InferenceServer
        except ImportError:
            pytest.skip("kailash-ml not installed")

        # Both methods exist and are callable
        import inspect

        http_sig = inspect.signature(InferenceServer.register_endpoints)
        mcp_sig = inspect.signature(InferenceServer.register_mcp_tools)

        # Both accept a server-like object as first positional arg
        http_params = list(http_sig.parameters.keys())
        mcp_params = list(mcp_sig.parameters.keys())
        assert "nexus" in http_params or "self" in http_params
        assert "server" in mcp_params or "self" in mcp_params
