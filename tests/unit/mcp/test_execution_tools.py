# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Tier 4 execution tools (MCP-509).

Tests verify:
- Execution tools are NOT registered when KAILASH_MCP_ENABLE_EXECUTION is unset
- Execution tools ARE registered when KAILASH_MCP_ENABLE_EXECUTION=true
- Subprocess timeout handling
- Structured error output for missing handler/agent
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from kailash.mcp.contrib import SecurityTier, is_tier_enabled
    from kailash.mcp.platform_server import create_platform_server
    from kailash.mcp.contrib.nexus import (
        _execute_in_subprocess as nexus_execute,
    )
    from kailash.mcp.contrib.kaizen import (
        _execute_in_subprocess as kaizen_execute,
    )
except ImportError:
    pytest.skip(
        "Third-party 'mcp' package not available",
        allow_module_level=True,
    )


# -------------------------------------------------------------------
# Tier 4 registration gating
# -------------------------------------------------------------------


class TestTier4Registration:
    """Execution tools must only appear when env var is set."""

    def _tool_names(self, server) -> set[str]:
        try:
            return set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ; cannot inspect tools")

    def test_tier4_tools_absent_by_default(self, tmp_path: Path):
        """Without KAILASH_MCP_ENABLE_EXECUTION, no Tier 4 tools."""
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the env var is not set
            import os

            os.environ.pop("KAILASH_MCP_ENABLE_EXECUTION", None)
            server = create_platform_server(project_root=tmp_path)

        tools = self._tool_names(server)
        assert "nexus.test_handler" not in tools
        assert "kaizen.test_agent" not in tools

    def test_tier4_tools_present_when_enabled(self, tmp_path: Path):
        """With KAILASH_MCP_ENABLE_EXECUTION=true, Tier 4 tools registered."""
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_EXECUTION": "true"}):
            server = create_platform_server(project_root=tmp_path)

        tools = self._tool_names(server)
        # Only check if the frameworks are installed
        # nexus and kaizen may not be installed, so we check
        # that IF they are installed, their tier 4 tools appear
        has_nexus = any(t.startswith("nexus.") for t in tools)
        has_kaizen = any(t.startswith("kaizen.") for t in tools)

        if has_nexus:
            assert "nexus.test_handler" in tools
        if has_kaizen:
            assert "kaizen.test_agent" in tools


# -------------------------------------------------------------------
# Subprocess execution
# -------------------------------------------------------------------


class TestSubprocessExecution:
    """Subprocess helper handles output, errors, and timeouts."""

    def test_successful_execution(self, tmp_path: Path):
        """Subprocess returns parsed JSON output."""
        script = 'import json; print(json.dumps({"status": "ok"}))'
        result = nexus_execute(script, tmp_path, timeout=10)
        assert result["status"] == "ok"
        assert "duration_ms" in result

    def test_nonzero_exit_code(self, tmp_path: Path):
        """Non-zero exit code produces structured error."""
        script = "import sys; sys.exit(1)"
        result = nexus_execute(script, tmp_path, timeout=10)
        assert "errors" in result
        assert "duration_ms" in result

    def test_stderr_captured(self, tmp_path: Path):
        """Stderr output appears in errors list."""
        script = 'import sys; sys.stderr.write("boom"); sys.exit(1)'
        result = nexus_execute(script, tmp_path, timeout=10)
        assert "errors" in result
        assert any("boom" in e for e in result["errors"])

    def test_timeout_handling(self, tmp_path: Path):
        """Timeout produces structured error with elapsed time."""
        script = "import time; time.sleep(60)"
        result = nexus_execute(script, tmp_path, timeout=1)
        assert "errors" in result
        assert any("timed out" in e for e in result["errors"])
        assert "duration_ms" in result

    def test_non_json_output(self, tmp_path: Path):
        """Non-JSON stdout is captured as raw_output."""
        script = 'print("not json")'
        result = nexus_execute(script, tmp_path, timeout=10)
        assert result.get("raw_output") == "not json"

    def test_pythonpath_set(self, tmp_path: Path):
        """Subprocess receives project_root in PYTHONPATH."""
        script = (
            "import os, json; "
            'print(json.dumps({"pythonpath": os.environ.get("PYTHONPATH", "")}))'
        )
        result = nexus_execute(script, tmp_path, timeout=10)
        assert str(tmp_path) in result.get("pythonpath", "")


# -------------------------------------------------------------------
# Handler not found
# -------------------------------------------------------------------


class TestHandlerNotFound:
    """Missing handler/agent returns structured error with available list."""

    @pytest.mark.asyncio
    async def test_nexus_handler_not_found(self, tmp_path: Path):
        """nexus.test_handler with unknown name returns error + available list."""
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_EXECUTION": "true"}):
            server = create_platform_server(project_root=tmp_path)

        tools = set()
        try:
            tools = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ")

        if "nexus.test_handler" not in tools:
            pytest.skip("nexus not installed")

        tool = server._tool_manager._tools["nexus.test_handler"]
        result = await tool.run({"handler_name": "nonexistent_handler"})
        # FastMCP tool.run() may return a dict or a list of content items
        if isinstance(result, dict):
            parsed = result
        elif isinstance(result, list) and result and hasattr(result[0], "text"):
            parsed = json.loads(result[0].text)
        else:
            parsed = result
        assert "errors" in parsed or "error" in str(parsed)

    @pytest.mark.asyncio
    async def test_kaizen_agent_not_found(self, tmp_path: Path):
        """kaizen.test_agent with unknown name returns error + available list."""
        with patch.dict("os.environ", {"KAILASH_MCP_ENABLE_EXECUTION": "true"}):
            server = create_platform_server(project_root=tmp_path)

        tools = set()
        try:
            tools = set(server._tool_manager._tools.keys())
        except AttributeError:
            pytest.skip("FastMCP internals differ")

        if "kaizen.test_agent" not in tools:
            pytest.skip("kaizen not installed")

        tool = server._tool_manager._tools["kaizen.test_agent"]
        result = await tool.run(
            {"agent_name": "nonexistent_agent", "task": "hello"}
        )
        # FastMCP tool.run() may return a dict or a list of content items
        if isinstance(result, dict):
            parsed = result
        elif isinstance(result, list) and result and hasattr(result[0], "text"):
            parsed = json.loads(result[0].text)
        else:
            parsed = result
        assert "errors" in parsed or "error" in str(parsed)
