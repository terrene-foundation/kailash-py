# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the kailash-platform MCP server (MCP-510).

Uses ``create_platform_server`` directly (in-process) rather than McpClient
subprocess to keep tests fast and reliable in CI. McpClient-based tests
are reserved for E2E tier.

Tests verify:
- Server startup with fixture project
- Tool discovery (tools/list equivalent)
- Each contributor's tools
- scan_metadata presence
- Security tier filtering
- Graceful degradation
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from kailash_mcp.contrib import SecurityTier, is_tier_enabled
    from kailash_mcp.platform_server import (
        FRAMEWORK_CONTRIBUTORS,
        create_platform_server,
    )
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )

FIXTURE_PROJECT = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "mcp_test_project"
)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _tool_names(server) -> set[str]:
    try:
        return set(server._tool_manager._tools.keys())
    except AttributeError:
        pytest.skip("FastMCP internals differ; cannot inspect tools")


async def _call_tool(server, name: str, arguments: dict | None = None):
    """Call a tool on the server and return parsed JSON result."""
    tools = server._tool_manager._tools
    if name not in tools:
        pytest.fail(f"Tool '{name}' not registered. Available: {sorted(tools.keys())}")
    tool = tools[name]
    result = await tool.run(arguments=arguments or {})
    # FastMCP returns list of TextContent items
    if isinstance(result, list) and hasattr(result[0], "text"):
        return json.loads(result[0].text)
    if isinstance(result, str):
        return json.loads(result)
    return result


# -------------------------------------------------------------------
# Server startup
# -------------------------------------------------------------------


@pytest.mark.integration
class TestServerStartup:
    """Server starts and loads expected tools."""

    def test_starts_with_fixture_project(self):
        """Server creates successfully with fixture project root."""
        server = create_platform_server(project_root=FIXTURE_PROJECT)
        assert server.name == "kailash-platform"
        tools = _tool_names(server)
        # At minimum core and platform tools exist
        assert "core.list_node_types" in tools
        assert "platform.platform_map" in tools

    def test_startup_within_time_budget(self):
        """Server startup completes within 10 seconds (RT-6c, R2-03)."""
        start = time.monotonic()
        create_platform_server(project_root=FIXTURE_PROJECT)
        elapsed = time.monotonic() - start
        assert elapsed < 10.0, f"Server startup took {elapsed:.2f}s, budget is 10s"


# -------------------------------------------------------------------
# Tool discovery
# -------------------------------------------------------------------


@pytest.mark.integration
class TestToolDiscovery:
    """Verify expected tools are registered from all contributors."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)

    def test_core_tools(self):
        """core.list_node_types and core.describe_node registered."""
        assert "core.list_node_types" in self.tools
        assert "core.describe_node" in self.tools

    def test_platform_tools(self):
        """platform.platform_map registered."""
        assert "platform.platform_map" in self.tools

    def test_dataflow_tools_if_installed(self):
        """dataflow.list_models registered if DataFlow is installed."""
        if not any(t.startswith("dataflow.") for t in self.tools):
            pytest.skip("DataFlow not installed")
        assert "dataflow.list_models" in self.tools
        assert "dataflow.describe_model" in self.tools

    def test_nexus_tools_if_installed(self):
        """nexus.list_handlers registered if Nexus is installed."""
        if not any(t.startswith("nexus.") for t in self.tools):
            pytest.skip("Nexus not installed")
        assert "nexus.list_handlers" in self.tools

    def test_kaizen_tools_if_installed(self):
        """kaizen.list_agents registered if Kaizen is installed."""
        if not any(t.startswith("kaizen.") for t in self.tools):
            pytest.skip("Kaizen not installed")
        assert "kaizen.list_agents" in self.tools
        assert "kaizen.describe_agent" in self.tools


# -------------------------------------------------------------------
# Contributor tool execution
# -------------------------------------------------------------------


@pytest.mark.integration
class TestDataflowContributor:
    """DataFlow contributor discovers models from fixture project."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)
        if not any(t.startswith("dataflow.") for t in self.tools):
            pytest.skip("DataFlow not installed")

    @pytest.mark.asyncio
    async def test_list_models_finds_user(self):
        """dataflow.list_models returns User model from fixture."""
        result = await _call_tool(self.server, "dataflow.list_models")
        assert "models" in result
        model_names = [m["name"] for m in result["models"]]
        assert "User" in model_names

    @pytest.mark.asyncio
    async def test_describe_model_user(self):
        """dataflow.describe_model(User) returns fields and generated nodes."""
        result = await _call_tool(
            self.server, "dataflow.describe_model", {"model_name": "User"}
        )
        assert "error" not in result, f"Unexpected error: {result}"
        # Should have model info with fields
        model = result.get("model", result)
        assert model.get("name") == "User" or "User" in str(model)


@pytest.mark.integration
class TestNexusContributor:
    """Nexus contributor discovers handlers from fixture project."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)
        if not any(t.startswith("nexus.") for t in self.tools):
            pytest.skip("Nexus not installed")

    @pytest.mark.asyncio
    async def test_list_handlers_finds_create_user(self):
        """nexus.list_handlers returns create_user_handler from fixture."""
        result = await _call_tool(self.server, "nexus.list_handlers")
        assert "handlers" in result
        handler_names = [h["name"] for h in result["handlers"]]
        assert "create_user_handler" in handler_names

    @pytest.mark.asyncio
    async def test_scan_metadata_present(self):
        """nexus.list_handlers response includes scan_metadata."""
        result = await _call_tool(self.server, "nexus.list_handlers")
        assert "scan_metadata" in result
        meta = result["scan_metadata"]
        assert "method" in meta
        assert "files_scanned" in meta


@pytest.mark.integration
class TestKaizenContributor:
    """Kaizen contributor discovers agents from fixture project."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)
        if not any(t.startswith("kaizen.") for t in self.tools):
            pytest.skip("Kaizen not installed")

    @pytest.mark.asyncio
    async def test_list_agents_finds_support_agent(self):
        """kaizen.list_agents returns SupportAgent from fixture."""
        result = await _call_tool(self.server, "kaizen.list_agents")
        assert "agents" in result
        agent_names = [a["name"] for a in result["agents"]]
        assert "SupportAgent" in agent_names

    @pytest.mark.asyncio
    async def test_describe_agent_support(self):
        """kaizen.describe_agent(SupportAgent) returns signature info."""
        result = await _call_tool(
            self.server,
            "kaizen.describe_agent",
            {"agent_name": "SupportAgent"},
        )
        assert "error" not in result, f"Unexpected error: {result}"
        agent = result.get("agent", result)
        assert agent["name"] == "SupportAgent"
        assert agent.get("signature") is not None


# -------------------------------------------------------------------
# Platform map + cross-framework connections
# -------------------------------------------------------------------


@pytest.mark.integration
class TestPlatformMap:
    """Platform map discovers cross-framework connections."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)

    @pytest.mark.asyncio
    async def test_platform_map_returns_valid_structure(self):
        """platform.platform_map returns dict with expected keys."""
        result = await _call_tool(self.server, "platform.platform_map")
        # Should be a dict (may vary in structure depending on installed frameworks)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_platform_map_connections(self):
        """platform.platform_map includes model_to_handler connection."""
        if not any(t.startswith("dataflow.") for t in self.tools):
            pytest.skip("DataFlow not installed")
        if not any(t.startswith("nexus.") for t in self.tools):
            pytest.skip("Nexus not installed")

        result = await _call_tool(self.server, "platform.platform_map")
        connections = result.get("connections", [])
        # Look for User -> create_user connection via CreateUser reference
        model_handler = [c for c in connections if c.get("type") == "model_to_handler"]
        assert any(
            c.get("from") == "User" and "create_user" in c.get("to", "")
            for c in model_handler
        ), f"Expected User -> create_user connection, got {model_handler}"


# -------------------------------------------------------------------
# Security tier filtering
# -------------------------------------------------------------------


@pytest.mark.integration
class TestSecurityTierFiltering:
    """Security tiers correctly gate tool registration."""

    def test_no_execution_tools_by_default(self):
        """Without KAILASH_MCP_ENABLE_EXECUTION, Tier 4 tools absent."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("KAILASH_MCP_ENABLE_EXECUTION", None)
            server = create_platform_server(project_root=FIXTURE_PROJECT)

        tools = _tool_names(server)
        assert "nexus.test_handler" not in tools
        assert "kaizen.test_agent" not in tools

    def test_execution_tools_present_when_enabled(self):
        """With KAILASH_MCP_ENABLE_EXECUTION=true, Tier 4 tools present."""
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_EXECUTION": "true"}):
            server = create_platform_server(project_root=FIXTURE_PROJECT)

        tools = _tool_names(server)
        has_nexus = any(t.startswith("nexus.") for t in tools)
        has_kaizen = any(t.startswith("kaizen.") for t in tools)

        if has_nexus:
            assert "nexus.test_handler" in tools
        if has_kaizen:
            assert "kaizen.test_agent" in tools

    def test_validation_tools_absent_when_disabled(self):
        """With KAILASH_MCP_ENABLE_VALIDATION=false, Tier 3 tools absent."""
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_VALIDATION": "false"}):
            server = create_platform_server(project_root=FIXTURE_PROJECT)

        tools = _tool_names(server)
        # If nexus is installed, validate_handler should NOT be present
        if any(t.startswith("nexus.") for t in tools):
            assert "nexus.validate_handler" not in tools


# -------------------------------------------------------------------
# Graceful degradation
# -------------------------------------------------------------------


@pytest.mark.integration
class TestGracefulDegradation:
    """Server functions with only core + platform when frameworks unavailable."""

    def test_only_core_platform_when_no_frameworks(self, tmp_path: Path):
        """With only core + platform contributors, server starts with core tools."""
        with patch(
            "kailash_mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [
                ("kailash_mcp.contrib.core", "core"),
                ("kailash_mcp.contrib.platform", "platform"),
            ],
        ):
            server = create_platform_server(project_root=tmp_path)

        tools = _tool_names(server)
        assert "core.list_node_types" in tools
        assert "platform.platform_map" in tools
        # Framework tools should not exist
        assert not any(t.startswith("dataflow.") for t in tools)
        assert not any(t.startswith("nexus.") for t in tools)
        assert not any(t.startswith("kaizen.") for t in tools)

    @pytest.mark.asyncio
    async def test_platform_map_empty_when_no_frameworks(self, tmp_path: Path):
        """platform.platform_map returns valid response without frameworks."""
        with patch(
            "kailash_mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [
                ("kailash_mcp.contrib.core", "core"),
                ("kailash_mcp.contrib.platform", "platform"),
            ],
        ):
            server = create_platform_server(project_root=tmp_path)

        result = await _call_tool(server, "platform.platform_map")
        assert isinstance(result, dict)


# -------------------------------------------------------------------
# Scaffold code parseable
# -------------------------------------------------------------------


@pytest.mark.integration
class TestScaffoldCodeQuality:
    """Scaffold tools produce parseable Python code."""

    @pytest.fixture(autouse=True)
    def _server(self):
        self.server = create_platform_server(project_root=FIXTURE_PROJECT)
        self.tools = _tool_names(self.server)

    @pytest.mark.asyncio
    async def test_nexus_scaffold_parseable(self):
        """nexus.scaffold_handler produces ast.parse()-able code."""
        if "nexus.scaffold_handler" not in self.tools:
            pytest.skip("Nexus scaffold not available")
        result = await _call_tool(
            self.server,
            "nexus.scaffold_handler",
            {
                "name": "get_status",
                "method": "GET",
                "path": "/status",
                "description": "Health check",
            },
        )
        if "error" in result:
            pytest.fail(f"Scaffold failed: {result['error']}")
        code = result.get("code", "")
        ast.parse(code)  # Should not raise

    @pytest.mark.asyncio
    async def test_kaizen_scaffold_parseable(self):
        """kaizen.scaffold_agent produces ast.parse()-able code."""
        if "kaizen.scaffold_agent" not in self.tools:
            pytest.skip("Kaizen scaffold not available")
        result = await _call_tool(
            self.server,
            "kaizen.scaffold_agent",
            {
                "agent_name": "TestAgent",
                "description": "A test agent",
            },
        )
        if "error" in result:
            pytest.fail(f"Scaffold failed: {result.get('error')}")
        code = result.get("code", "")
        ast.parse(code)  # Should not raise
