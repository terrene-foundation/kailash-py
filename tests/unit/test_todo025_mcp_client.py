"""Unit tests for TODO-025: MCP Client real protocol integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.middleware.mcp.client_integration import (
    MCPClientConfig,
    MCPServerConnection,
    MiddlewareMCPClient,
    _MCP_AVAILABLE,
)


@pytest.fixture
def mcp_client():
    """Create a MiddlewareMCPClient without event stream."""
    return MiddlewareMCPClient(config=MCPClientConfig())


class TestMCPClientConfig:
    def test_defaults(self):
        cfg = MCPClientConfig()
        assert cfg.name == "kailash-middleware-mcp-client"
        assert cfg.connection_timeout == 30
        assert cfg.max_retries == 3
        assert cfg.cache_ttl == 300

    def test_version(self):
        cfg = MCPClientConfig()
        assert cfg.version == "1.0.0"


class TestMCPServerConnection:
    def test_init_state(self, mcp_client):
        conn = MCPServerConnection("test-server", {"transport": "stdio"}, mcp_client)
        assert conn.server_name == "test-server"
        assert conn.connected is False
        assert conn.connection_attempts == 0
        assert conn.available_tools == {}
        assert conn.available_resources == {}

    @pytest.mark.asyncio
    async def test_connect_no_mcp_library(self, mcp_client):
        """When mcp library is not available, connect returns False."""
        conn = MCPServerConnection(
            "test-server", {"transport": "stdio", "command": "echo"}, mcp_client
        )

        with patch("kailash.middleware.mcp.client_integration._MCP_AVAILABLE", False):
            result = await conn.connect()
            assert result is False

    @pytest.mark.asyncio
    async def test_connect_invalid_transport(self, mcp_client):
        """Invalid transport type should fail gracefully."""
        conn = MCPServerConnection("test-server", {"transport": "unknown"}, mcp_client)
        # Even if MCP is available, unknown transport should fail
        result = await conn.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_resets_state(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        conn.connected = True
        conn._cleanup_tasks = []

        await conn.disconnect()
        assert conn.connected is False
        assert conn._session is None

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        result = await conn.call_tool("some_tool", {"arg": "val"})
        assert result["success"] is False
        assert "Not connected" in result["error"]

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        conn.connected = True
        conn._session = MagicMock()
        conn.available_tools = {"known_tool": {}}

        result = await conn.call_tool("unknown_tool", {})
        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        conn.connected = True
        conn.available_tools = {"my_tool": {"description": "test"}}

        # Mock the MCP session
        mock_content = MagicMock()
        mock_content.text = "tool output"
        mock_result = MagicMock()
        mock_result.content = [mock_content]
        mock_result.isError = False

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)
        conn._session = mock_session

        result = await conn.call_tool("my_tool", {"key": "val"})
        assert result["success"] is True
        assert result["tool_result"]["result"] == "tool output"

    @pytest.mark.asyncio
    async def test_get_resource_not_connected(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        result = await conn.get_resource("test://resource")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_resource_success(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        conn.connected = True

        mock_content = MagicMock()
        mock_content.text = "resource data"
        mock_result = MagicMock()
        mock_result.contents = [mock_content]

        mock_session = AsyncMock()
        mock_session.read_resource = AsyncMock(return_value=mock_result)
        conn._session = mock_session

        result = await conn.get_resource("test://data")
        assert result["success"] is True
        assert result["resource_data"]["content"] == "resource data"

    @pytest.mark.asyncio
    async def test_ping_no_session(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        assert await conn.ping() is False

    @pytest.mark.asyncio
    async def test_ping_success(self, mcp_client):
        conn = MCPServerConnection("test-server", {}, mcp_client)
        conn.connected = True

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        conn._session = mock_session

        assert await conn.ping() is True


class TestMiddlewareMCPClient:
    @pytest.mark.asyncio
    async def test_add_server_duplicate(self, mcp_client):
        # Pre-populate
        mcp_client.server_connections["test"] = MagicMock()
        result = await mcp_client.add_server("test", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_server_not_found(self, mcp_client):
        result = await mcp_client.remove_server("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_server_success(self, mcp_client):
        mock_conn = AsyncMock()
        mcp_client.server_connections["test"] = mock_conn

        result = await mcp_client.remove_server("test")
        assert result is True
        assert "test" not in mcp_client.server_connections
        mock_conn.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_discover_all_capabilities(self, mcp_client):
        mock_conn = MagicMock()
        mock_conn.connected = True
        mock_conn.server_capabilities = {"tools": True}
        mock_conn.available_tools = {"tool1": {}}
        mock_conn.available_resources = {}
        mcp_client.server_connections["srv"] = mock_conn

        caps = await mcp_client.discover_all_capabilities()
        assert "srv" in caps
        assert caps["srv"]["available_tools"] == {"tool1": {}}

    @pytest.mark.asyncio
    async def test_call_tool_server_not_found(self, mcp_client):
        result = await mcp_client.call_tool("nope", "tool", {})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_broadcast_tool_call(self, mcp_client):
        conn1 = AsyncMock()
        conn1.connected = True
        conn1.available_tools = {"shared_tool": {}}
        conn1.call_tool = AsyncMock(return_value={"success": True})

        conn2 = AsyncMock()
        conn2.connected = True
        conn2.available_tools = {}
        conn2.call_tool = AsyncMock()

        mcp_client.server_connections = {"s1": conn1, "s2": conn2}

        results = await mcp_client.broadcast_tool_call("shared_tool", {"x": 1})
        assert "s1" in results
        assert "s2" not in results

    @pytest.mark.asyncio
    async def test_check_health(self, mcp_client):
        conn = AsyncMock()
        conn.ping = AsyncMock(return_value=True)
        mcp_client.server_connections["srv"] = conn

        health = await mcp_client.check_health()
        assert health["srv"] is True

    @pytest.mark.asyncio
    async def test_get_client_stats(self, mcp_client):
        stats = await mcp_client.get_client_stats()
        assert stats["client_info"]["name"] == "kailash-middleware-mcp-client"
        assert stats["connections"]["total_servers"] == 0

    @pytest.mark.asyncio
    async def test_disconnect_all(self, mcp_client):
        conn = AsyncMock()
        mcp_client.server_connections["srv"] = conn

        await mcp_client.disconnect_all()
        conn.disconnect.assert_awaited_once()
