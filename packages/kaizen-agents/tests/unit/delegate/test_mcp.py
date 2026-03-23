"""Tests for kz.mcp — MCP client tool discovery and calling.

All subprocess interactions are mocked. Tests verify:
- Server config parsing from TOML structure
- Tool discovery via tools/list
- Tool calling via tools/call
- JSON-RPC message formatting
- Error handling (server not running, init failure, tool errors)
- Registration of MCP tools into the loop ToolRegistry
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen_agents.delegate.mcp import (
    McpClient,
    McpServerConfig,
    McpToolDef,
    load_mcp_server_configs,
    register_mcp_tools,
)


# ---------------------------------------------------------------------------
# McpServerConfig
# ---------------------------------------------------------------------------


class TestMcpServerConfig:
    def test_basic_config(self) -> None:
        cfg = McpServerConfig(
            name="fs",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
        assert cfg.name == "fs"
        assert cfg.command == "npx"
        assert len(cfg.args) == 3
        assert cfg.env == {}

    def test_config_with_env(self) -> None:
        cfg = McpServerConfig(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "test-token"},
        )
        assert cfg.env["GITHUB_TOKEN"] == "test-token"

    def test_config_frozen(self) -> None:
        cfg = McpServerConfig(name="x", command="y")
        with pytest.raises(AttributeError):
            cfg.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# McpToolDef
# ---------------------------------------------------------------------------


class TestMcpToolDef:
    def test_tool_def_fields(self) -> None:
        td = McpToolDef(
            name="read_file",
            description="Read a file from disk",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            server_name="fs",
        )
        assert td.name == "read_file"
        assert td.server_name == "fs"
        assert "path" in td.input_schema["properties"]


# ---------------------------------------------------------------------------
# load_mcp_server_configs
# ---------------------------------------------------------------------------


class TestLoadMcpServerConfigs:
    def test_parse_multiple_servers(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    },
                    "github": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                        "env": {"GITHUB_TOKEN": "abc"},
                    },
                }
            }
        }
        configs = load_mcp_server_configs(raw)
        assert len(configs) == 2
        names = {c.name for c in configs}
        assert "filesystem" in names
        assert "github" in names

        gh = next(c for c in configs if c.name == "github")
        assert gh.env["GITHUB_TOKEN"] == "abc"

    def test_empty_config(self) -> None:
        assert load_mcp_server_configs({}) == []

    def test_missing_mcp_section(self) -> None:
        assert load_mcp_server_configs({"other": "stuff"}) == []

    def test_skips_invalid_entries(self) -> None:
        raw = {
            "mcp": {
                "servers": {
                    "good": {"command": "echo", "args": ["hello"]},
                    "bad_no_command": {"args": ["test"]},
                    "bad_not_dict": "invalid",
                }
            }
        }
        configs = load_mcp_server_configs(raw)
        assert len(configs) == 1
        assert configs[0].name == "good"


# ---------------------------------------------------------------------------
# McpClient — unit tests with mocked subprocess
# ---------------------------------------------------------------------------


class TestMcpClient:
    def test_server_name(self) -> None:
        cfg = McpServerConfig(name="test", command="echo")
        client = McpClient(cfg)
        assert client.server_name == "test"

    def test_not_running_initially(self) -> None:
        cfg = McpServerConfig(name="test", command="echo")
        client = McpClient(cfg)
        assert not client.is_running

    @pytest.mark.asyncio
    async def test_discover_tools_before_start_raises(self) -> None:
        cfg = McpServerConfig(name="test", command="echo")
        client = McpClient(cfg)
        with pytest.raises(RuntimeError, match="not running"):
            await client.discover_tools()

    @pytest.mark.asyncio
    async def test_call_tool_before_start_raises(self) -> None:
        cfg = McpServerConfig(name="test", command="echo")
        client = McpClient(cfg)
        with pytest.raises(RuntimeError, match="not running"):
            await client.call_tool("anything", {})

    @pytest.mark.asyncio
    async def test_start_command_not_found(self) -> None:
        cfg = McpServerConfig(name="test", command="/nonexistent/binary/xyz")
        client = McpClient(cfg)
        with pytest.raises(RuntimeError, match="command not found|failed to start"):
            await client.start()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """Stopping a client that was never started should not raise."""
        cfg = McpServerConfig(name="test", command="echo")
        client = McpClient(cfg)
        await client.stop()  # Should not raise


class TestMcpClientWithMockedProcess:
    """Tests that mock the subprocess to simulate MCP server responses.

    The mock uses an asyncio.Queue to synchronize: responses are only
    delivered to the reader after a request is written to stdin. This
    mirrors how a real MCP server would behave (request in, response out).
    """

    def _make_client_with_mock(
        self,
        response_results: list[dict[str, Any]],
    ) -> tuple[McpClient, MagicMock]:
        """Create a client with a mocked process.

        Parameters
        ----------
        response_results:
            List of JSON-RPC "result" values (or full response dicts with
            "error"). Each result is returned for the matching request in
            order. The response ID is automatically set to match the
            request ID.
        """
        cfg = McpServerConfig(name="mock_server", command="mock")
        client = McpClient(cfg)

        # Queue that delivers responses after requests are sent
        response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        request_count = 0

        # Build mock process
        mock_process = MagicMock()
        mock_process.returncode = None

        # Mock stdin — intercept writes to know when requests are sent
        mock_stdin = MagicMock()
        results_iter = iter(response_results)

        def on_write(data: bytes) -> None:
            nonlocal request_count
            # Parse the request to get its ID
            try:
                req = json.loads(data.decode("utf-8").strip())
                req_id = req.get("id")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return

            if req_id is None:
                # Notification (no response expected)
                return

            # Build response with matching ID
            try:
                result_data = next(results_iter)
            except StopIteration:
                return

            if "error" in result_data:
                response = {"jsonrpc": "2.0", "id": req_id, "error": result_data["error"]}
            elif "result" in result_data:
                response = {"jsonrpc": "2.0", "id": req_id, "result": result_data["result"]}
            else:
                response = {"jsonrpc": "2.0", "id": req_id, "result": result_data}

            line = (json.dumps(response) + "\n").encode("utf-8")
            response_queue.put_nowait(line)
            request_count += 1

        mock_stdin.write = MagicMock(side_effect=on_write)
        mock_stdin.drain = AsyncMock()
        mock_process.stdin = mock_stdin

        # Mock stdout — reads from the queue, EOF after all responses delivered
        async def mock_readline() -> bytes:
            try:
                return await asyncio.wait_for(response_queue.get(), timeout=5)
            except asyncio.TimeoutError:
                return b""

        mock_stdout = AsyncMock()
        mock_stdout.readline = mock_readline
        mock_process.stdout = mock_stdout

        # Mock stderr
        mock_stderr = AsyncMock()
        mock_process.stderr = mock_stderr

        # Mock wait and signal
        mock_process.wait = AsyncMock()
        mock_process.send_signal = MagicMock()

        client._process = mock_process
        client._reader_task = asyncio.create_task(client._read_stdout())
        client._initialized = True

        return client, mock_process

    @pytest.mark.asyncio
    async def test_discover_tools(self) -> None:
        """Test tool discovery via mocked tools/list response."""
        tools_result = {
            "result": {
                "tools": [
                    {
                        "name": "read_file",
                        "description": "Read file contents",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    },
                    {
                        "name": "write_file",
                        "description": "Write file contents",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "content"],
                        },
                    },
                ]
            },
        }

        client, _ = self._make_client_with_mock([tools_result])

        tools = await client.discover_tools()

        assert len(tools) == 2
        assert tools[0].name == "read_file"
        assert tools[0].description == "Read file contents"
        assert tools[0].server_name == "mock_server"
        assert tools[1].name == "write_file"

        await client.stop()

    @pytest.mark.asyncio
    async def test_call_tool(self) -> None:
        """Test tool calling via mocked tools/call response."""
        call_result = {
            "result": {"content": [{"type": "text", "text": "file contents here"}]},
        }

        client, _ = self._make_client_with_mock([call_result])

        result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
        assert result == "file contents here"

        await client.stop()

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self) -> None:
        """Test handling of MCP tool error (isError flag)."""
        error_result = {
            "result": {
                "content": [{"type": "text", "text": "File not found"}],
                "isError": True,
            },
        }

        client, _ = self._make_client_with_mock([error_result])

        result = await client.call_tool("read_file", {"path": "/nope"})
        assert "MCP tool error" in result
        assert "File not found" in result

        await client.stop()

    @pytest.mark.asyncio
    async def test_call_tool_jsonrpc_error(self) -> None:
        """Test handling of JSON-RPC error response."""
        error_result = {
            "error": {
                "code": -32601,
                "message": "Method not found",
            },
        }

        client, _ = self._make_client_with_mock([error_result])

        with pytest.raises(RuntimeError, match="Method not found"):
            await client.call_tool("nonexistent", {})

        await client.stop()

    @pytest.mark.asyncio
    async def test_empty_tool_result(self) -> None:
        """Test handling of empty content in tool response."""
        empty_result = {
            "result": {"content": []},
        }

        client, _ = self._make_client_with_mock([empty_result])

        result = await client.call_tool("some_tool", {})
        assert result == ""

        await client.stop()

    @pytest.mark.asyncio
    async def test_multi_content_blocks(self) -> None:
        """Test handling of multiple content blocks in tool response."""
        multi_result = {
            "result": {
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"},
                    {"type": "image", "mimeType": "image/png"},
                ]
            },
        }

        client, _ = self._make_client_with_mock([multi_result])

        result = await client.call_tool("multi_tool", {})
        assert "line one" in result
        assert "line two" in result
        assert "[image: image/png]" in result

        await client.stop()


# ---------------------------------------------------------------------------
# register_mcp_tools
# ---------------------------------------------------------------------------


class TestRegisterMcpTools:
    @pytest.mark.asyncio
    async def test_registers_tools_with_prefix(self) -> None:
        """MCP tools should be registered with mcp_<server>_<tool> prefix."""
        # Create a mock client
        mock_client = AsyncMock(spec=McpClient)
        mock_client.server_name = "testserver"
        mock_client.discover_tools = AsyncMock(
            return_value=[
                McpToolDef(
                    name="read_file",
                    description="Read a file",
                    input_schema={"type": "object", "properties": {}},
                    server_name="testserver",
                ),
                McpToolDef(
                    name="list_dir",
                    description="List directory",
                    input_schema={"type": "object", "properties": {}},
                    server_name="testserver",
                ),
            ]
        )

        # Create a mock registry that records registrations
        registered: dict[str, Any] = {}

        class MockRegistry:
            def register(
                self, name: str, description: str, parameters: dict, executor: Any
            ) -> None:
                registered[name] = {
                    "description": description,
                    "parameters": parameters,
                    "executor": executor,
                }

        registry = MockRegistry()
        tools = await register_mcp_tools(mock_client, registry)

        assert len(tools) == 2
        assert "mcp_testserver_read_file" in registered
        assert "mcp_testserver_list_dir" in registered
        assert "[MCP:testserver]" in registered["mcp_testserver_read_file"]["description"]
