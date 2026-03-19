from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Self-contained tests for the Catalog MCP Server.

Run with:
    python -m pytest packages/kailash-kaizen/tests/unit/mcp/test_catalog_server.py -v --noconftest

This test file pre-loads a stub ``kaizen`` package into ``sys.modules`` so
that ``from kaizen.mcp.catalog_server...`` does NOT trigger the real
``kaizen/__init__.py`` (which has a broken import chain to
``kailash.nodes.base.Node``).  The same approach is used by the
composition test conftest.
"""

import json
import os
import sys
import types
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Stub kaizen package to bypass the broken __init__.py import chain
# ---------------------------------------------------------------------------
_need_stub = False
try:
    from kailash.nodes.base import Node  # noqa: F401
except (ImportError, AttributeError):
    _need_stub = True

if _need_stub and "kaizen" not in sys.modules:
    _src_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "src")
    )
    _kaizen_dir = os.path.join(_src_dir, "kaizen")

    _stub = types.ModuleType("kaizen")
    _stub.__path__ = [_kaizen_dir]
    _stub.__package__ = "kaizen"
    _stub.__file__ = os.path.join(_kaizen_dir, "__init__.py")
    sys.modules["kaizen"] = _stub

    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    method: str,
    params: Dict[str, Any] | None = None,
    req_id: int = 1,
) -> Dict[str, Any]:
    """Build a JSON-RPC request dict."""
    req: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    return req


def _tool_call(
    tool_name: str, arguments: Dict[str, Any], req_id: int = 1
) -> Dict[str, Any]:
    """Build a tools/call JSON-RPC request."""
    return _make_request(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        req_id=req_id,
    )


def _get_tool_result(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the parsed tool result from a tools/call response."""
    content = response["result"]["content"]
    assert len(content) == 1
    return json.loads(content[0]["text"])


def _is_error_response(response: Dict[str, Any]) -> bool:
    """Return True if the response indicates an error."""
    return response.get("result", {}).get("isError", False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server():
    """Create a fresh CatalogMCPServer with builtin agents pre-seeded."""
    from kaizen.mcp.catalog_server.server import CatalogMCPServer

    return CatalogMCPServer()


@pytest.fixture
def initialized_server(server):
    """Create a server that has already been initialized."""
    server.handle_request(_make_request("initialize"))
    return server


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestProtocol:
    """MCP protocol-level tests."""

    def test_server_initialize(self, server):
        """Handle initialize request and return capabilities."""
        resp = server.handle_request(_make_request("initialize"))

        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "kaizen-catalog"
        assert result["serverInfo"]["version"] == "1.0.0"

    def test_tools_list_returns_11_tools(self, initialized_server):
        """tools/list must return exactly 11 tool definitions."""
        resp = initialized_server.handle_request(_make_request("tools/list"))

        tools = resp["result"]["tools"]
        assert len(tools) == 11

        tool_names = {t["name"] for t in tools}
        expected = {
            "catalog_search",
            "catalog_describe",
            "catalog_schema",
            "catalog_deps",
            "deploy_agent",
            "deploy_status",
            "catalog_deregister",
            "app_register",
            "app_status",
            "validate_composition",
            "budget_status",
        }
        assert tool_names == expected

        # Every tool must have inputSchema
        for tool in tools:
            assert "inputSchema" in tool, f"Tool {tool['name']} missing inputSchema"
            assert tool["inputSchema"]["type"] == "object"

    def test_notifications_initialized_returns_empty(self, server):
        """notifications/initialized is a notification -- returns empty dict."""
        resp = server.handle_request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert resp == {}

    def test_unknown_method_error(self, initialized_server):
        """Unknown methods return method-not-found error."""
        resp = initialized_server.handle_request(_make_request("resources/list"))
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_tools_list_before_initialize_returns_error(self, server):
        """tools/list before initialize must return an error."""
        resp = server.handle_request(_make_request("tools/list"))
        assert "error" in resp
        assert resp["error"]["code"] == -32600
        assert "not initialized" in resp["error"]["message"].lower()

    def test_tools_call_before_initialize_returns_error(self, server):
        """tools/call before initialize must return an error."""
        resp = server.handle_request(_tool_call("catalog_search", {"query": "react"}))
        assert "error" in resp
        assert resp["error"]["code"] == -32600
        assert "not initialized" in resp["error"]["message"].lower()

    def test_unknown_tool_error(self, initialized_server):
        """Calling a non-existent tool returns an error."""
        resp = initialized_server.handle_request(_tool_call("nonexistent_tool", {}))
        assert "error" in resp
        assert resp["error"]["code"] == -32602
        assert "nonexistent_tool" in resp["error"]["message"]

    def test_parse_error(self, initialized_server):
        """Malformed JSON is handled at the stdio level.

        The server.handle_request expects a parsed dict, so parse errors
        are handled at the serve_stdio level.  Here we test that the
        _error helper produces correct structure.
        """
        error_resp = initialized_server._error(None, -32700, "Parse error")
        assert error_resp["jsonrpc"] == "2.0"
        assert error_resp["id"] is None
        assert error_resp["error"]["code"] == -32700
        assert error_resp["error"]["message"] == "Parse error"


# ---------------------------------------------------------------------------
# Discovery tools
# ---------------------------------------------------------------------------


class TestCatalogSearch:
    """Tests for catalog_search tool."""

    def test_catalog_search_finds_agents(self, initialized_server):
        """Search by query string finds matching agents."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_search", {"query": "react"})
        )
        result = _get_tool_result(resp)
        assert result["count"] >= 1
        names = [a["name"] for a in result["agents"]]
        assert "react-agent" in names

    def test_catalog_search_by_capability(self, initialized_server):
        """Search by capability filter finds agents with that capability."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_search", {"capabilities": ["reasoning"]})
        )
        result = _get_tool_result(resp)
        assert result["count"] >= 1
        for agent in result["agents"]:
            assert "reasoning" in agent["capabilities"]

    def test_catalog_search_empty_result(self, initialized_server):
        """Search with no matches returns empty list."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_search", {"query": "zzz_nonexistent_agent_xyz"})
        )
        result = _get_tool_result(resp)
        assert result["count"] == 0
        assert result["agents"] == []

    def test_catalog_search_no_filters(self, initialized_server):
        """Search with no filters returns all agents."""
        resp = initialized_server.handle_request(_tool_call("catalog_search", {}))
        result = _get_tool_result(resp)
        # Should have all 10 builtin agents
        assert result["count"] >= 10

    def test_catalog_search_by_status(self, initialized_server):
        """Search by status filter."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_search", {"status": "registered"})
        )
        result = _get_tool_result(resp)
        assert result["count"] >= 1
        for agent in result["agents"]:
            assert agent["status"] == "registered"


class TestCatalogDescribe:
    """Tests for catalog_describe tool."""

    def test_catalog_describe_existing(self, initialized_server):
        """Describe an existing agent returns full detail."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_describe", {"name": "react-agent"})
        )
        result = _get_tool_result(resp)
        agent = result["agent"]
        assert agent["name"] == "react-agent"
        assert "reasoning" in agent["capabilities"]
        assert agent["module"] == "kaizen.agents.specialized.react"
        assert agent["class_name"] == "ReActAgent"

    def test_catalog_describe_unknown(self, initialized_server):
        """Describe an unknown agent returns error."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_describe", {"name": "nonexistent-agent"})
        )
        assert _is_error_response(resp)
        result = _get_tool_result(resp)
        assert "error" in result
        assert "not found" in result["error"]


class TestCatalogSchema:
    """Tests for catalog_schema tool."""

    def test_catalog_schema_existing(self, initialized_server):
        """Schema for an existing agent returns input/output schemas."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_schema", {"name": "simple-qa"})
        )
        result = _get_tool_result(resp)
        assert result["name"] == "simple-qa"
        # Builtin agents don't have declared schemas, so they're empty
        assert "input_schema" in result
        assert "output_schema" in result

    def test_catalog_schema_with_declared_schemas(self, initialized_server):
        """Agent with declared schemas returns them."""
        # First register an agent with schemas
        initialized_server._registry.deregister("simple-qa")  # Make room for test
        initialized_server._registry.register(
            {
                "name": "schema-test-agent",
                "module": "test.module",
                "class_name": "TestAgent",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
            }
        )

        resp = initialized_server.handle_request(
            _tool_call("catalog_schema", {"name": "schema-test-agent"})
        )
        result = _get_tool_result(resp)
        assert result["input_schema"]["properties"]["query"]["type"] == "string"
        assert result["output_schema"]["properties"]["answer"]["type"] == "string"


class TestCatalogDeps:
    """Tests for catalog_deps tool."""

    def test_catalog_deps_valid_dag(self, initialized_server):
        """Valid DAG returns topological order."""
        agents = [
            {"name": "fetcher", "inputs_from": []},
            {"name": "parser", "inputs_from": ["fetcher"]},
            {"name": "analyzer", "inputs_from": ["parser"]},
        ]
        resp = initialized_server.handle_request(
            _tool_call("catalog_deps", {"agents": agents})
        )
        result = _get_tool_result(resp)
        assert result["is_valid"] is True
        assert len(result["cycles"]) == 0
        # Topological order: fetcher must come before parser, parser before analyzer
        order = result["topological_order"]
        assert order.index("fetcher") < order.index("parser")
        assert order.index("parser") < order.index("analyzer")

    def test_catalog_deps_cycle(self, initialized_server):
        """Cycle in DAG is detected."""
        agents = [
            {"name": "a", "inputs_from": ["c"]},
            {"name": "b", "inputs_from": ["a"]},
            {"name": "c", "inputs_from": ["b"]},
        ]
        resp = initialized_server.handle_request(
            _tool_call("catalog_deps", {"agents": agents})
        )
        result = _get_tool_result(resp)
        assert result["is_valid"] is False
        assert len(result["cycles"]) >= 1

    def test_catalog_deps_empty(self, initialized_server):
        """Empty agent list is valid."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_deps", {"agents": []})
        )
        result = _get_tool_result(resp)
        assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# Deployment tools
# ---------------------------------------------------------------------------


class TestDeployAgent:
    """Tests for deploy_agent tool."""

    def test_deploy_agent_inline_toml(self, initialized_server):
        """Deploy from valid inline TOML registers the agent."""
        toml_content = """\
[agent]
manifest_version = "1.0"
name = "test-deploy-agent"
module = "myapp.agents.test"
class_name = "TestDeployAgent"
description = "A test agent for deployment"
capabilities = ["testing"]
"""
        resp = initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": toml_content})
        )
        result = _get_tool_result(resp)
        assert not _is_error_response(resp)
        assert result["action"] == "deployed"
        assert result["agent"]["name"] == "test-deploy-agent"
        assert result["agent"]["status"] == "deployed"

    def test_deploy_agent_rejects_file_path(self, initialized_server):
        """RT-06: File paths are rejected."""
        resp = initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": "/etc/agent.toml"})
        )
        assert _is_error_response(resp)
        result = _get_tool_result(resp)
        assert "File paths are not accepted" in result["error"]

    def test_deploy_agent_rejects_relative_path(self, initialized_server):
        """RT-06: Relative file paths are also rejected."""
        resp = initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": "config/agent.toml"})
        )
        assert _is_error_response(resp)
        result = _get_tool_result(resp)
        assert "File paths are not accepted" in result["error"]

    def test_deploy_agent_rejects_windows_path(self, initialized_server):
        """RT-06: Windows-style paths are rejected."""
        resp = initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": "C:\\agents\\test.toml"})
        )
        assert _is_error_response(resp)
        result = _get_tool_result(resp)
        assert "File paths are not accepted" in result["error"]

    def test_deploy_agent_with_governance(self, initialized_server):
        """Deploy agent with governance section."""
        toml_content = """\
[agent]
manifest_version = "1.0"
name = "governed-agent"
module = "myapp.agents.governed"
class_name = "GovernedAgent"
description = "Agent with governance"
capabilities = ["pii-detection"]

[governance]
purpose = "PII detection in documents"
risk_level = "high"
data_access_needed = ["customer_data"]
suggested_posture = "supervised"
max_budget_microdollars = 500000
"""
        resp = initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": toml_content})
        )
        result = _get_tool_result(resp)
        assert not _is_error_response(resp)
        assert result["agent"]["name"] == "governed-agent"
        gov = result["agent"].get("governance")
        assert gov is not None
        assert gov["risk_level"] == "high"
        assert gov["max_budget_microdollars"] == 500000


class TestDeployStatus:
    """Tests for deploy_status tool."""

    def test_deploy_status_existing(self, initialized_server):
        """Query status of a registered agent."""
        resp = initialized_server.handle_request(
            _tool_call("deploy_status", {"name": "react-agent"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is True
        assert result["name"] == "react-agent"
        assert result["status"] == "registered"

    def test_deploy_status_not_found(self, initialized_server):
        """Query status of non-existent agent."""
        resp = initialized_server.handle_request(
            _tool_call("deploy_status", {"name": "no-such-agent"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is False
        assert result["status"] == "not_found"


class TestCatalogDeregister:
    """Tests for catalog_deregister tool."""

    def test_catalog_deregister(self, initialized_server):
        """Deregister an existing agent."""
        # First verify it exists
        resp = initialized_server.handle_request(
            _tool_call("deploy_status", {"name": "simple-qa"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is True

        # Deregister
        resp = initialized_server.handle_request(
            _tool_call("catalog_deregister", {"name": "simple-qa"})
        )
        result = _get_tool_result(resp)
        assert result["removed"] is True

        # Verify gone
        resp = initialized_server.handle_request(
            _tool_call("deploy_status", {"name": "simple-qa"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is False

    def test_catalog_deregister_nonexistent(self, initialized_server):
        """Deregister a non-existent agent returns removed=False."""
        resp = initialized_server.handle_request(
            _tool_call("catalog_deregister", {"name": "ghost-agent"})
        )
        result = _get_tool_result(resp)
        assert result["removed"] is False


# ---------------------------------------------------------------------------
# Application tools
# ---------------------------------------------------------------------------


class TestAppRegister:
    """Tests for app_register tool."""

    def test_app_register(self, initialized_server):
        """Register an application."""
        resp = initialized_server.handle_request(
            _tool_call(
                "app_register",
                {
                    "name": "test-app",
                    "description": "Test application",
                    "owner": "team@example.com",
                    "agents_requested": ["react-agent", "simple-qa"],
                    "budget_monthly_microdollars": 10_000_000,
                    "justification": "Need agents for research pipeline",
                },
            )
        )
        result = _get_tool_result(resp)
        assert not _is_error_response(resp)
        assert result["action"] == "registered"
        app = result["application"]
        assert app["name"] == "test-app"
        assert app["owner"] == "team@example.com"
        assert "react-agent" in app["agents_requested"]

    def test_app_register_with_unknown_agents(self, initialized_server):
        """Registration with unknown agents produces warnings."""
        resp = initialized_server.handle_request(
            _tool_call(
                "app_register",
                {
                    "name": "test-app-warnings",
                    "agents_requested": ["react-agent", "nonexistent-agent-xyz"],
                },
            )
        )
        result = _get_tool_result(resp)
        assert result["action"] == "registered"
        assert "warnings" in result
        assert any("nonexistent-agent-xyz" in w for w in result["warnings"])


class TestAppStatus:
    """Tests for app_status tool."""

    def test_app_status(self, initialized_server):
        """Query status of a registered application."""
        # Register first
        initialized_server.handle_request(
            _tool_call(
                "app_register",
                {
                    "name": "status-test-app",
                    "description": "App for status test",
                    "owner": "qa@example.com",
                },
            )
        )

        # Query status
        resp = initialized_server.handle_request(
            _tool_call("app_status", {"name": "status-test-app"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is True
        assert result["application"]["name"] == "status-test-app"
        assert result["application"]["owner"] == "qa@example.com"

    def test_app_status_not_found(self, initialized_server):
        """Query status of non-existent application."""
        resp = initialized_server.handle_request(
            _tool_call("app_status", {"name": "no-such-app"})
        )
        result = _get_tool_result(resp)
        assert result["found"] is False


# ---------------------------------------------------------------------------
# Governance tools
# ---------------------------------------------------------------------------


class TestValidateComposition:
    """Tests for validate_composition tool."""

    def test_validate_composition_valid_dag(self, initialized_server):
        """Valid composition DAG passes validation."""
        agents = [
            {"name": "fetcher", "inputs_from": []},
            {"name": "parser", "inputs_from": ["fetcher"]},
            {"name": "summarizer", "inputs_from": ["parser"]},
        ]
        resp = initialized_server.handle_request(
            _tool_call("validate_composition", {"agents": agents})
        )
        result = _get_tool_result(resp)
        assert result["dag_valid"] is True
        assert len(result["cycles"]) == 0
        assert len(result["schema_issues"]) == 0

    def test_validate_composition_cycle(self, initialized_server):
        """Cycle in composition is detected."""
        agents = [
            {"name": "a", "inputs_from": ["b"]},
            {"name": "b", "inputs_from": ["a"]},
        ]
        resp = initialized_server.handle_request(
            _tool_call("validate_composition", {"agents": agents})
        )
        result = _get_tool_result(resp)
        assert result["dag_valid"] is False
        assert len(result["cycles"]) >= 1

    def test_validate_composition_schema_check(self, initialized_server):
        """Schema incompatibility between agents is reported."""
        agents = [
            {
                "name": "producer",
                "inputs_from": [],
                "output_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                },
            },
            {
                "name": "consumer",
                "inputs_from": ["producer"],
                "input_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "string"}},
                    "required": ["count"],
                },
            },
        ]
        resp = initialized_server.handle_request(
            _tool_call("validate_composition", {"agents": agents})
        )
        result = _get_tool_result(resp)
        assert result["dag_valid"] is True  # DAG is valid
        assert len(result["schema_issues"]) >= 1  # But schemas are incompatible
        issue = result["schema_issues"][0]
        assert issue["upstream"] == "producer"
        assert issue["downstream"] == "consumer"

    def test_validate_composition_empty(self, initialized_server):
        """Empty composition is valid."""
        resp = initialized_server.handle_request(
            _tool_call("validate_composition", {"agents": []})
        )
        result = _get_tool_result(resp)
        assert result["dag_valid"] is True


class TestBudgetStatus:
    """Tests for budget_status tool."""

    def test_budget_status(self, initialized_server):
        """Budget status returns computed fields."""
        resp = initialized_server.handle_request(
            _tool_call(
                "budget_status",
                {
                    "scope": "research-app",
                    "budget_microdollars": 10_000_000,
                    "spent_microdollars": 3_000_000,
                },
            )
        )
        result = _get_tool_result(resp)
        assert result["scope"] == "research-app"
        assert result["budget_microdollars"] == 10_000_000
        assert result["spent_microdollars"] == 3_000_000
        assert result["remaining_microdollars"] == 7_000_000
        assert result["utilization_percent"] == 30.0
        assert result["status"] == "healthy"

    def test_budget_status_exceeded(self, initialized_server):
        """Budget exceeded is flagged."""
        resp = initialized_server.handle_request(
            _tool_call(
                "budget_status",
                {
                    "scope": "overbudget-app",
                    "budget_microdollars": 1_000_000,
                    "spent_microdollars": 1_500_000,
                },
            )
        )
        result = _get_tool_result(resp)
        assert result["status"] == "exceeded"
        assert result["remaining_microdollars"] == 0

    def test_budget_status_warning(self, initialized_server):
        """Budget at 80%+ utilization triggers warning."""
        resp = initialized_server.handle_request(
            _tool_call(
                "budget_status",
                {
                    "scope": "near-limit-app",
                    "budget_microdollars": 10_000_000,
                    "spent_microdollars": 8_500_000,
                },
            )
        )
        result = _get_tool_result(resp)
        assert result["status"] == "warning"

    def test_budget_status_no_budget(self, initialized_server):
        """No budget set returns appropriate status."""
        resp = initialized_server.handle_request(
            _tool_call(
                "budget_status",
                {
                    "scope": "unbudgeted-app",
                },
            )
        )
        result = _get_tool_result(resp)
        assert result["status"] == "no_budget_set"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge case tests."""

    def test_request_log_bounded(self, initialized_server):
        """Request log does not grow unbounded."""
        for i in range(15_000):
            initialized_server.handle_request(_make_request("tools/list", req_id=i))
        assert len(initialized_server._request_log) == 10_000

    def test_builtin_agents_pre_seeded(self, server):
        """Server starts with 10 builtin agents."""
        agents = server._registry.list_agents()
        assert len(agents) == 10
        names = {a["name"] for a in agents}
        assert "react-agent" in names
        assert "simple-qa" in names
        assert "vision-agent" in names

    def test_redeploy_overwrites(self, initialized_server):
        """Redeploying an agent overwrites the previous registration."""
        toml_v1 = """\
[agent]
manifest_version = "1.0"
name = "evolving-agent"
module = "myapp.v1"
class_name = "EvolvingAgent"
description = "Version 1"
"""
        toml_v2 = """\
[agent]
manifest_version = "1.0"
name = "evolving-agent"
module = "myapp.v2"
class_name = "EvolvingAgent"
description = "Version 2"
"""
        initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": toml_v1})
        )
        initialized_server.handle_request(
            _tool_call("deploy_agent", {"manifest_toml": toml_v2})
        )

        resp = initialized_server.handle_request(
            _tool_call("catalog_describe", {"name": "evolving-agent"})
        )
        result = _get_tool_result(resp)
        assert result["agent"]["module"] == "myapp.v2"
        assert result["agent"]["description"] == "Version 2"
