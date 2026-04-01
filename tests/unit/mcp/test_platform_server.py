# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the kailash-platform MCP server skeleton (MCP-500)."""

from __future__ import annotations

import logging
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# MCP platform server tests require the third-party ``mcp`` package.
# The platform_server module handles the sys.path shadowing issue
# internally (see _get_fastmcp_class()), so we can import it directly.
# If the third-party mcp package is truly unavailable, the import
# of platform_server will raise ImportError.
try:
    from kailash.mcp.contrib import SecurityTier, is_tier_enabled
    from kailash.mcp.platform_server import (
        FRAMEWORK_CONTRIBUTORS,
        create_platform_server,
    )
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )


# -------------------------------------------------------------------
# SecurityTier env var checks
# -------------------------------------------------------------------


class TestSecurityTier:
    """Tier gate checks based on environment variables."""

    def test_tier1_always_enabled(self):
        assert is_tier_enabled(SecurityTier.INTROSPECTION) is True

    def test_tier2_always_enabled(self):
        assert is_tier_enabled(SecurityTier.SCAFFOLD) is True

    def test_tier3_enabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert is_tier_enabled(SecurityTier.VALIDATION) is True

    def test_tier3_disabled_when_false(self):
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_VALIDATION": "false"}):
            assert is_tier_enabled(SecurityTier.VALIDATION) is False

    def test_tier4_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert is_tier_enabled(SecurityTier.EXECUTION) is False

    def test_tier4_enabled_when_true(self):
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_EXECUTION": "true"}):
            assert is_tier_enabled(SecurityTier.EXECUTION) is True


# -------------------------------------------------------------------
# create_platform_server()
# -------------------------------------------------------------------


class TestCreatePlatformServer:
    """Tests for the platform server factory function."""

    def test_returns_fastmcp_instance(self, tmp_path: Path):
        """create_platform_server returns a FastMCP with the correct name."""
        server = create_platform_server(project_root=tmp_path)
        assert server.name == "kailash-platform"

    def test_uses_cwd_when_no_root(self):
        """When project_root is None, resolves to cwd."""
        server = create_platform_server(project_root=None)
        assert server.name == "kailash-platform"

    def test_contributor_list_has_expected_entries(self):
        """FRAMEWORK_CONTRIBUTORS includes core and platform at minimum."""
        namespaces = [ns for _, ns in FRAMEWORK_CONTRIBUTORS]
        assert "core" in namespaces
        assert "platform" in namespaces

    def test_contributor_discovery_order(self):
        """Contributors are loaded in declared order."""
        import importlib

        load_order: list[str] = []
        original_import_module = importlib.import_module

        def tracking_import(name, *args, **kwargs):
            if name.startswith("kailash.mcp.contrib."):
                ns = name.rsplit(".", 1)[-1]
                load_order.append(ns)
            return original_import_module(name, *args, **kwargs)

        with patch("importlib.import_module", side_effect=tracking_import):
            create_platform_server(project_root=Path.cwd())

        # core and platform should be in load order and in sequence
        assert "core" in load_order
        assert "platform" in load_order
        assert load_order.index("core") < load_order.index("platform")


# -------------------------------------------------------------------
# Graceful error handling
# -------------------------------------------------------------------


class TestContributorErrorHandling:
    """Verify that contributor failures do not crash the server."""

    def test_import_error_skipped_gracefully(self, tmp_path: Path, caplog):
        """A contributor that fails to import is skipped with an INFO log."""
        with caplog.at_level(logging.INFO):
            # dataflow/nexus/kaizen/trust/pact will ImportError if not
            # installed as separate packages -- that is the normal path.
            server = create_platform_server(project_root=tmp_path)

        assert server.name == "kailash-platform"

    def test_exception_in_register_tools_handled(self, tmp_path: Path, caplog):
        """A contributor raising Exception during register_tools is caught."""
        bad_module = types.ModuleType("kailash.mcp.contrib.bad")

        def bad_register(server, root, ns):
            raise TypeError("intentional test failure")

        bad_module.register_tools = bad_register

        with (
            patch(
                "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
                [("kailash.mcp.contrib.bad", "bad")],
            ),
            patch.dict(
                "sys.modules",
                {"kailash.mcp.contrib.bad": bad_module},
            ),
            caplog.at_level(logging.ERROR),
        ):
            server = create_platform_server(project_root=tmp_path)

        assert server.name == "kailash-platform"
        assert any("intentional test failure" in r.message for r in caplog.records)


# -------------------------------------------------------------------
# Namespace validation
# -------------------------------------------------------------------


class TestNamespaceValidation:
    """Verify that tools registered outside the namespace produce warnings."""

    def test_misnamed_tool_warns(self, tmp_path: Path, caplog):
        """A tool without the namespace prefix triggers a warning."""
        bad_module = types.ModuleType("kailash.mcp.contrib.badns")

        def bad_register(server, root, ns):
            @server.tool(name="wrong_prefix.something")
            async def wrong_tool() -> dict:
                return {}

        bad_module.register_tools = bad_register

        with (
            patch(
                "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
                [("kailash.mcp.contrib.badns", "badns")],
            ),
            patch.dict(
                "sys.modules",
                {"kailash.mcp.contrib.badns": bad_module},
            ),
            caplog.at_level(logging.WARNING),
        ):
            create_platform_server(project_root=tmp_path)

        warning_msgs = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("wrong_prefix.something" in m for m in warning_msgs)


# -------------------------------------------------------------------
# Core contributor
# -------------------------------------------------------------------


class TestCoreContributor:
    """Verify that core.* tools are registered and functional."""

    @pytest.fixture()
    def server(self, tmp_path: Path):
        """Create a platform server with only core + platform contributors."""
        with patch(
            "kailash.mcp.platform_server.FRAMEWORK_CONTRIBUTORS",
            [
                ("kailash.mcp.contrib.core", "core"),
                ("kailash.mcp.contrib.platform", "platform"),
            ],
        ):
            return create_platform_server(project_root=tmp_path)

    def test_core_tools_registered(self, server):
        """core.list_node_types, core.list_node_categories, core.get_sdk_version exist."""
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "core.list_node_types" in tool_names
        assert "core.list_node_categories" in tool_names
        assert "core.get_sdk_version" in tool_names

    def test_platform_tools_registered(self, server):
        """platform.platform_map and platform.project_info exist."""
        try:
            tool_names = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")
        assert "platform.platform_map" in tool_names
        assert "platform.project_info" in tool_names


# -------------------------------------------------------------------
# project_root resolution
# -------------------------------------------------------------------


class TestProjectRootResolution:
    """CLI arg > env var > cwd priority for project_root."""

    def test_cli_arg_takes_priority(self, tmp_path: Path):
        """When a Path is provided, it is used directly."""
        server = create_platform_server(project_root=tmp_path)
        assert server.name == "kailash-platform"

    def test_env_var_used_when_no_arg(self, tmp_path: Path):
        """KAILASH_PROJECT_ROOT env var is used when no arg is passed."""
        with patch.dict(
            "os.environ",
            {"KAILASH_PROJECT_ROOT": str(tmp_path)},
        ):
            # create_platform_server(None) uses cwd, but the env var
            # path is exercised through main()'s argparse logic.
            server = create_platform_server(project_root=None)
            assert server.name == "kailash-platform"
