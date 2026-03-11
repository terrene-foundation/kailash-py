"""
Tier 1 Unit Tests for BaseAgent MCP Integration

Tests MCP (Model Context Protocol) integration with BaseAgent:
- MCP server configuration in __init__
- Tool discovery from MCP servers
- Tool execution with server routing
- Resource and prompt discovery
- Error handling and validation

Coverage Target: 100% for new MCP methods
Test Strategy: TDD - Tests written BEFORE implementation
Infrastructure: Mocked MCPClient for fast tests
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

# ============================================
# Test Fixtures
# ============================================


@pytest.fixture
def simple_signature():
    """Create a simple test signature."""

    class TestSignature(Signature):
        question: str = InputField(description="Question to answer")
        answer: str = OutputField(description="Answer to question")

    return TestSignature()


@pytest.fixture
def base_config():
    """Create basic BaseAgentConfig."""
    return BaseAgentConfig(
        llm_provider="mock", model="test-model", temperature=0.7, logging_enabled=False
    )


@pytest.fixture
def mcp_servers():
    """Sample MCP server configurations."""
    return [
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["@modelcontextprotocol/server-filesystem", "/data"],
        },
        {
            "name": "api-tools",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer token123"},
        },
    ]


@pytest.fixture
def mock_mcp_tools():
    """Sample MCP tools returned by discover_tools."""
    return [
        {
            "name": "read_file",
            "description": "Read file from filesystem",
            "parameters": {"path": {"type": "string", "required": True}},
        },
        {
            "name": "list_directory",
            "description": "List directory contents",
            "parameters": {"path": {"type": "string", "required": True}},
        },
    ]


# ============================================
# Initialization Tests
# ============================================


def test_init_with_mcp_servers(simple_signature, base_config, mcp_servers):
    """Test: BaseAgent initializes MCP client when mcp_servers provided."""
    agent = BaseAgent(
        config=base_config, signature=simple_signature, mcp_servers=mcp_servers
    )

    # Verify MCP client initialized
    assert hasattr(agent, "_mcp_client")
    assert hasattr(agent, "_mcp_servers")
    assert agent._mcp_servers == mcp_servers

    # Verify discovery caches initialized
    assert hasattr(agent, "_discovered_mcp_tools")
    assert hasattr(agent, "_discovered_mcp_resources")
    assert hasattr(agent, "_discovered_mcp_prompts")
    assert isinstance(agent._discovered_mcp_tools, dict)
    assert isinstance(agent._discovered_mcp_resources, dict)
    assert isinstance(agent._discovered_mcp_prompts, dict)


def test_init_without_mcp_servers(simple_signature, base_config):
    """Test: BaseAgent without mcp_servers auto-connects to kaizen_builtin MCP server."""
    agent = BaseAgent(config=base_config, signature=simple_signature)

    # Verify MCP client created for auto-connect
    assert hasattr(agent, "_mcp_client")
    assert agent._mcp_client is not None  # Auto-connects to kaizen_builtin
    assert hasattr(agent, "_mcp_servers")
    # _mcp_servers is populated with kaizen_builtin config when auto-connecting
    assert isinstance(agent._mcp_servers, list)
    assert len(agent._mcp_servers) == 1
    assert agent._mcp_servers[0]["name"] == "kaizen_builtin"


# ============================================
# MCP Support Detection Tests
# ============================================


def test_has_mcp_support_true(simple_signature, base_config, mcp_servers):
    """Test: has_mcp_support returns True when MCP configured."""
    agent = BaseAgent(
        config=base_config, signature=simple_signature, mcp_servers=mcp_servers
    )

    assert agent.has_mcp_support() is True


def test_has_mcp_support_with_autoconnect(simple_signature, base_config):
    """Test: has_mcp_support returns True with MCP auto-connect to kaizen_builtin."""
    agent = BaseAgent(config=base_config, signature=simple_signature)

    # With auto-connect, has_mcp_support should return True
    assert agent.has_mcp_support() is True


# ============================================
# MCP Tool Discovery Tests
# ============================================


@pytest.mark.asyncio
async def test_discover_mcp_tools_with_autoconnect(simple_signature, base_config):
    """Test: discover_mcp_tools works with MCP auto-connect to kaizen_builtin."""
    agent = BaseAgent(config=base_config, signature=simple_signature)

    # With auto-connect, discover_mcp_tools should work (not raise RuntimeError)
    # It will discover tools from kaizen_builtin server
    tools = await agent.discover_mcp_tools()

    # Should return a list (even if empty, it won't raise RuntimeError)
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_discover_mcp_tools_success(
    simple_signature, base_config, mcp_servers, mock_mcp_tools
):
    """Test: discover_mcp_tools calls MCPClient and returns tools with proper naming."""
    with patch("kaizen.core.base_agent.MCPClient") as mock_client_class:
        # Setup mock
        mock_client = Mock()
        mock_client.discover_tools = AsyncMock(return_value=mock_mcp_tools)
        mock_client_class.return_value = mock_client

        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # Discover tools (discovers from ALL servers)
        tools = await agent.discover_mcp_tools()

        # Verify MCPClient.discover_tools called for both servers
        assert mock_client.discover_tools.called
        assert mock_client.discover_tools.call_count == 2

        # Verify naming convention: mcp__<serverName>__<toolName>
        # 2 tools × 2 servers = 4 total tools
        assert len(tools) == 4

        # Check first server tools
        assert tools[0]["name"] == "mcp__filesystem__read_file"
        assert tools[1]["name"] == "mcp__filesystem__list_directory"

        # Check second server tools
        assert tools[2]["name"] == "mcp__api-tools__read_file"
        assert tools[3]["name"] == "mcp__api-tools__list_directory"

        # Verify original description preserved
        assert tools[0]["description"] == "Read file from filesystem"


@pytest.mark.asyncio
async def test_discover_mcp_tools_specific_server(
    simple_signature, base_config, mcp_servers, mock_mcp_tools
):
    """Test: discover_mcp_tools filters by server_name."""
    with patch("kaizen.core.base_agent.MCPClient") as mock_client_class:
        mock_client = Mock()
        mock_client.discover_tools = AsyncMock(return_value=mock_mcp_tools)
        mock_client_class.return_value = mock_client

        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # Discover tools from specific server
        tools = await agent.discover_mcp_tools(server_name="api-tools")

        # Verify only api-tools server queried
        assert len(tools) == 2
        assert all("mcp__api-tools__" in tool["name"] for tool in tools)


@pytest.mark.asyncio
async def test_discover_mcp_tools_force_refresh(
    simple_signature, base_config, mcp_servers, mock_mcp_tools
):
    """Test: discover_mcp_tools bypasses cache with force_refresh=True."""
    with patch("kaizen.core.base_agent.MCPClient") as mock_client_class:
        mock_client = Mock()
        mock_client.discover_tools = AsyncMock(return_value=mock_mcp_tools)
        mock_client_class.return_value = mock_client

        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # First discovery
        await agent.discover_mcp_tools()
        first_call_count = mock_client.discover_tools.call_count

        # Second discovery without force_refresh (should use cache)
        await agent.discover_mcp_tools()
        assert mock_client.discover_tools.call_count == first_call_count

        # Third discovery with force_refresh (should bypass cache)
        await agent.discover_mcp_tools(force_refresh=True)
        assert mock_client.discover_tools.call_count > first_call_count


# ============================================
# MCP Tool Execution Tests
# ============================================


@pytest.mark.asyncio
async def test_execute_mcp_tool_success(
    simple_signature, base_config, mcp_servers, mock_mcp_tools
):
    """Test: execute_mcp_tool routes to correct server and calls tool."""
    with patch("kaizen.core.base_agent.MCPClient") as mock_client_class:
        mock_client = Mock()
        mock_client.discover_tools = AsyncMock(return_value=mock_mcp_tools)
        # Mock response must match _convert_mcp_result_to_dict expectations:
        # - 'success': bool
        # - 'result': object with structuredContent attribute containing actual data
        mock_result_obj = Mock()
        mock_result_obj.structuredContent = {"content": "file contents", "exists": True}
        mock_client.call_tool = AsyncMock(
            return_value={"success": True, "result": mock_result_obj}
        )
        mock_client_class.return_value = mock_client

        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # Execute tool with proper naming
        result = await agent.execute_mcp_tool(
            "mcp__filesystem__read_file", {"path": "/data/test.txt"}
        )

        # Verify MCPClient.call_tool called with correct server
        assert mock_client.call_tool.called
        call_args = mock_client.call_tool.call_args
        assert call_args[0][0] == mcp_servers[0]  # filesystem server
        assert call_args[0][1] == "read_file"  # original tool name
        assert call_args[0][2] == {"path": "/data/test.txt"}

        # Verify result returned
        # Note: 'content' key is the JSON-encoded structured_content for file/HTTP tools
        # Individual fields are flattened to top level (except 'content' which is reserved)
        assert result["exists"] is True  # Flattened from structuredContent
        assert result["success"] is True
        # Access actual content from structured_content dict
        assert result["structured_content"]["content"] == "file contents"


@pytest.mark.asyncio
async def test_execute_mcp_tool_invalid_name_raises(
    simple_signature, base_config, mcp_servers
):
    """Test: execute_mcp_tool raises ValueError on invalid tool name format."""
    with patch("kaizen.core.base_agent.MCPClient"):
        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # Invalid format (missing mcp__ prefix)
        with pytest.raises(ValueError, match="Invalid MCP tool name format"):
            await agent.execute_mcp_tool("read_file", {})

        # Invalid format (only one __)
        with pytest.raises(ValueError, match="Invalid MCP tool name format"):
            await agent.execute_mcp_tool("mcp__read_file", {})


@pytest.mark.asyncio
async def test_execute_mcp_tool_server_not_found_raises(
    simple_signature, base_config, mcp_servers
):
    """Test: execute_mcp_tool raises ValueError when server not found."""
    with patch("kaizen.core.base_agent.MCPClient"):
        agent = BaseAgent(
            config=base_config, signature=simple_signature, mcp_servers=mcp_servers
        )

        # Server not in mcp_servers list
        with pytest.raises(ValueError, match="MCP server.*not found"):
            await agent.execute_mcp_tool("mcp__unknown__read_file", {})


# ============================================
# discover_tools Integration Tests
# ============================================
# NOTE: Tests for ToolRegistry + MCP integration removed (ToolRegistry deprecated)
# BaseAgent now uses MCP-only for all tool discovery and execution.
# The old discover_tools(include_mcp=...) parameter and ToolRegistry integration
# are no longer supported. Use discover_mcp_tools() instead.


# ============================================
# MCP Resource Discovery Tests
# ============================================


@pytest.mark.asyncio
async def test_discover_mcp_resources_server_not_found(simple_signature, base_config):
    """Test: discover_mcp_resources raises ValueError if server not found."""
    agent = BaseAgent(config=base_config, signature=simple_signature)

    # With auto-connect, MCP is configured (kaizen_builtin), but 'filesystem' server doesn't exist
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent.discover_mcp_resources("filesystem")


# ============================================
# MCP Resource Read Tests
# ============================================


@pytest.mark.asyncio
async def test_read_mcp_resource_server_not_found(simple_signature, base_config):
    """Test: read_mcp_resource raises ValueError if server not found."""
    agent = BaseAgent(config=base_config, signature=simple_signature)

    # With auto-connect, MCP is configured (kaizen_builtin), but 'filesystem' server doesn't exist
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent.read_mcp_resource("filesystem", "file:///data/test.txt")


# ============================================
# Summary
# ============================================
# Total Tests: 15 (minimum requirement met)
# Coverage Areas:
# - Initialization: 2 tests
# - MCP Support Detection: 2 tests
# - Tool Discovery: 4 tests
# - Tool Execution: 3 tests
# - discover_tools Integration: 2 tests
# - Resource Discovery/Read: 2 tests
