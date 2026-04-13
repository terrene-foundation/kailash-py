# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the expanded Platform contributor (MCP-506)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from kailash_mcp.platform_server import create_platform_server
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )

from kailash_mcp.contrib.platform import (
    _build_platform_map,
    _detect_agent_tool_connections,
    _detect_model_agent_connections,
    _detect_model_handler_connections,
    _get_framework_versions,
    _get_project_info,
    _get_trust_summary,
)

# -------------------------------------------------------------------
# Cross-framework connection detection
# -------------------------------------------------------------------


class TestModelHandlerConnections:
    """Test model-to-handler connection detection via generated node names."""

    def test_detects_create_node_reference(self, tmp_path: Path):
        """Handler source containing CreateUser is detected."""
        handler_file = tmp_path / "handler.py"
        handler_file.write_text(
            'workflow.add_node("CreateUser", "create", {"name": "test"})',
            encoding="utf-8",
        )

        models = [{"name": "User", "file": "models.py"}]
        handlers = [{"name": "user_handler", "file": "handler.py"}]

        connections = _detect_model_handler_connections(models, handlers, tmp_path)

        assert len(connections) == 1
        assert connections[0]["from"] == "User"
        assert connections[0]["to"] == "user_handler"
        assert connections[0]["type"] == "model_to_handler"
        assert connections[0]["via"] == "CreateUser"

    def test_no_match_returns_empty(self, tmp_path: Path):
        """When no generated names are found, return empty list."""
        handler_file = tmp_path / "handler.py"
        handler_file.write_text("# no model references", encoding="utf-8")

        models = [{"name": "Product", "file": "models.py"}]
        handlers = [{"name": "other_handler", "file": "handler.py"}]

        connections = _detect_model_handler_connections(models, handlers, tmp_path)
        assert connections == []

    def test_multiple_models_single_handler(self, tmp_path: Path):
        """Multiple models referenced in a single handler file."""
        handler_file = tmp_path / "handler.py"
        handler_file.write_text(
            "CreateUser(...)\nReadProduct(...)\n",
            encoding="utf-8",
        )

        models = [
            {"name": "User", "file": "m.py"},
            {"name": "Product", "file": "m.py"},
        ]
        handlers = [{"name": "combo_handler", "file": "handler.py"}]

        connections = _detect_model_handler_connections(models, handlers, tmp_path)
        assert len(connections) == 2

    def test_missing_handler_file(self, tmp_path: Path):
        """Handler file that does not exist is skipped."""
        models = [{"name": "User", "file": "m.py"}]
        handlers = [{"name": "gone", "file": "nonexistent.py"}]

        connections = _detect_model_handler_connections(models, handlers, tmp_path)
        assert connections == []


class TestAgentToolConnections:
    """Test agent-to-tool connection extraction."""

    def test_extracts_tool_connections(self):
        agents = [
            {"name": "ResearchAgent", "tools": ["web_search", "read_file"]},
            {"name": "SimpleAgent", "tools": []},
        ]
        connections = _detect_agent_tool_connections(agents)
        assert len(connections) == 2
        assert connections[0]["from"] == "ResearchAgent"
        assert connections[0]["to"] == "web_search"
        assert connections[0]["type"] == "agent_to_tool"

    def test_empty_agents(self):
        assert _detect_agent_tool_connections([]) == []


class TestModelAgentConnections:
    """Test model-to-agent connection detection."""

    def test_detects_model_reference_in_agent(self, tmp_path: Path):
        agent_file = tmp_path / "agent.py"
        agent_file.write_text(
            "result = runtime.execute(CreateOrder(...))",
            encoding="utf-8",
        )
        models = [{"name": "Order", "file": "m.py"}]
        agents = [{"name": "OrderAgent", "file": "agent.py", "tools": []}]

        connections = _detect_model_agent_connections(models, agents, tmp_path)
        assert len(connections) == 1
        assert connections[0]["type"] == "model_to_agent"


# -------------------------------------------------------------------
# Framework version detection
# -------------------------------------------------------------------


class TestFrameworkVersions:
    """Test framework version detection."""

    def test_returns_dict_for_all_frameworks(self):
        versions = _get_framework_versions()
        assert "core" in versions
        assert "dataflow" in versions
        assert "nexus" in versions
        assert "kaizen" in versions
        assert "pact" in versions
        assert "trust" in versions

    def test_installed_framework_has_version(self):
        """Core (kailash) should be installed in test environment."""
        versions = _get_framework_versions()
        core = versions["core"]
        assert core["installed"] is True
        assert "version" in core


# -------------------------------------------------------------------
# Project info
# -------------------------------------------------------------------


class TestProjectInfo:
    """Test project info extraction."""

    def test_with_pyproject(self, tmp_path: Path):
        """Read project name from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        info = _get_project_info(tmp_path)
        assert info["name"] == "my-app"
        assert info["root"] == str(tmp_path)

    def test_fallback_to_dir_name(self, tmp_path: Path):
        """When no pyproject.toml, use directory name."""
        info = _get_project_info(tmp_path)
        assert info["name"] == tmp_path.name


# -------------------------------------------------------------------
# Trust summary
# -------------------------------------------------------------------


class TestTrustSummary:
    """Test lightweight trust summary."""

    def test_no_trust_dir(self, tmp_path: Path):
        result = _get_trust_summary(tmp_path)
        assert result["installed"] is False
        assert result["trust_dir_exists"] is False

    def test_with_trust_dir(self, tmp_path: Path):
        (tmp_path / "trust-plane").mkdir()
        result = _get_trust_summary(tmp_path)
        assert result["installed"] is True
        assert result["trust_dir_exists"] is True


# -------------------------------------------------------------------
# Platform map aggregation
# -------------------------------------------------------------------


class TestBuildPlatformMap:
    """Test the full platform map builder."""

    def test_returns_valid_structure(self, tmp_path: Path):
        """Platform map has all required top-level keys."""
        result = _build_platform_map(tmp_path)

        assert "project" in result
        assert "frameworks" in result
        assert "models" in result
        assert "handlers" in result
        assert "agents" in result
        assert "channels" in result
        assert "connections" in result
        assert "trust" in result
        assert "scan_metadata" in result

    def test_scan_metadata_has_limitations(self, tmp_path: Path):
        result = _build_platform_map(tmp_path)
        meta = result["scan_metadata"]
        assert meta["method"] == "ast_static"
        assert "limitations" in meta
        assert len(meta["limitations"]) > 0

    def test_empty_project(self, tmp_path: Path):
        """Empty project returns empty arrays, not errors."""
        result = _build_platform_map(tmp_path)
        assert result["models"] == []
        assert result["handlers"] == []
        assert result["agents"] == []
        assert result["connections"] == []


# -------------------------------------------------------------------
# Tool and resource registration
# -------------------------------------------------------------------


class TestPlatformToolRegistration:
    """Test platform tools are registered."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        with patch(
            "kailash_mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [("kailash_mcp.contrib.platform", "platform")],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_platform_map_registered(self, server):
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.platform_map" in tool_names
        assert "platform.project_info" in tool_names

    def test_resources_registered(self, server):
        """MCP resources should be registered with kailash:// URIs."""
        try:
            resource_names = set(server._resource_manager._resources.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect resources")
        expected = {
            "kailash://models",
            "kailash://handlers",
            "kailash://agents",
            "kailash://platform-map",
            "kailash://node-types",
        }
        for uri in expected:
            assert uri in resource_names, f"Resource {uri} not registered"
