"""
Tier 1 Unit Tests for BaseAgent MCP Session Integration

Tests the wired-up MCP session methods in BaseAgent that use
MCPClient session-based helpers (list_resources, read_resource,
list_prompts, get_prompt) via the _with_mcp_session bridge.

Coverage:
- discover_mcp_resources() -- delegates to MCPClient.list_resources
- read_mcp_resource()      -- delegates to MCPClient.read_resource
- discover_mcp_prompts()   -- delegates to MCPClient.list_prompts
- get_mcp_prompt()         -- delegates to MCPClient.get_prompt
- _with_mcp_session()      -- transport routing and session lifecycle
- Caching behaviour for resources and prompts
- Error propagation from MCPClient
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

# ============================================
# Fixtures
# ============================================


@pytest.fixture
def simple_signature():
    class TestSig(Signature):
        question: str = InputField(description="Q")
        answer: str = OutputField(description="A")

    return TestSig()


@pytest.fixture
def base_config():
    return BaseAgentConfig(
        llm_provider="mock",
        model="test-model",
        temperature=0.7,
        logging_enabled=False,
    )


@pytest.fixture
def mcp_servers():
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
        },
    ]


@pytest.fixture
def agent_with_servers(base_config, simple_signature, mcp_servers):
    return BaseAgent(
        config=base_config,
        signature=simple_signature,
        mcp_servers=mcp_servers,
    )


# ============================================
# discover_mcp_resources tests
# ============================================


@pytest.mark.asyncio
async def test_discover_mcp_resources_delegates_to_list_resources(agent_with_servers):
    """discover_mcp_resources should call _with_mcp_session with list_resources."""
    expected = [
        {
            "uri": "file:///data/readme.txt",
            "name": "readme",
            "description": "A readme",
            "mimeType": "text/plain",
        },
    ]
    agent_with_servers._with_mcp_session = AsyncMock(return_value=expected)

    result = await agent_with_servers.discover_mcp_resources("filesystem")

    assert result == expected
    agent_with_servers._with_mcp_session.assert_awaited_once()
    call_args = agent_with_servers._with_mcp_session.call_args
    # First positional arg is server_config, second is the method
    assert call_args[0][0]["name"] == "filesystem"


@pytest.mark.asyncio
async def test_discover_mcp_resources_uses_cache(agent_with_servers):
    """Second call should return cached resources without calling _with_mcp_session again."""
    cached = [{"uri": "file:///cached", "name": "cached"}]
    agent_with_servers._discovered_mcp_resources["filesystem"] = cached

    result = await agent_with_servers.discover_mcp_resources("filesystem")

    assert result == cached


@pytest.mark.asyncio
async def test_discover_mcp_resources_force_refresh_bypasses_cache(agent_with_servers):
    """force_refresh=True should bypass the cache and call the session helper."""
    cached = [{"uri": "file:///old"}]
    fresh = [{"uri": "file:///new"}]
    agent_with_servers._discovered_mcp_resources["filesystem"] = cached
    agent_with_servers._with_mcp_session = AsyncMock(return_value=fresh)

    result = await agent_with_servers.discover_mcp_resources(
        "filesystem", force_refresh=True
    )

    assert result == fresh
    agent_with_servers._with_mcp_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_discover_mcp_resources_not_configured(base_config, simple_signature):
    """Should raise RuntimeError when MCP servers not configured."""
    agent = BaseAgent(config=base_config, signature=simple_signature, mcp_servers=[])
    agent._mcp_servers = None

    with pytest.raises(RuntimeError, match="MCP not configured"):
        await agent.discover_mcp_resources("filesystem")


@pytest.mark.asyncio
async def test_discover_mcp_resources_server_not_found(agent_with_servers):
    """Should raise ValueError for unknown server name."""
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent_with_servers.discover_mcp_resources("nonexistent")


# ============================================
# read_mcp_resource tests
# ============================================


@pytest.mark.asyncio
async def test_read_mcp_resource_delegates_to_read_resource(agent_with_servers):
    """read_mcp_resource should call _with_mcp_session with read_resource and uri."""
    expected = [{"type": "text", "text": "Hello, world!"}]
    agent_with_servers._with_mcp_session = AsyncMock(return_value=expected)

    result = await agent_with_servers.read_mcp_resource(
        "filesystem", "file:///data/hello.txt"
    )

    assert result == expected
    call_args = agent_with_servers._with_mcp_session.call_args
    assert call_args[0][0]["name"] == "filesystem"
    # Third positional arg should be the URI
    assert call_args[0][2] == "file:///data/hello.txt"


@pytest.mark.asyncio
async def test_read_mcp_resource_not_configured(base_config, simple_signature):
    """Should raise RuntimeError when MCP not configured."""
    agent = BaseAgent(config=base_config, signature=simple_signature, mcp_servers=[])
    agent._mcp_servers = None

    with pytest.raises(RuntimeError, match="MCP not configured"):
        await agent.read_mcp_resource("filesystem", "file:///x")


@pytest.mark.asyncio
async def test_read_mcp_resource_server_not_found(agent_with_servers):
    """Should raise ValueError for unknown server name."""
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent_with_servers.read_mcp_resource("unknown", "file:///x")


# ============================================
# discover_mcp_prompts tests
# ============================================


@pytest.mark.asyncio
async def test_discover_mcp_prompts_delegates_to_list_prompts(agent_with_servers):
    """discover_mcp_prompts should call _with_mcp_session with list_prompts."""
    expected = [
        {
            "name": "greeting",
            "description": "Greet user",
            "arguments": [{"name": "name", "required": True}],
        },
    ]
    agent_with_servers._with_mcp_session = AsyncMock(return_value=expected)

    result = await agent_with_servers.discover_mcp_prompts("api-tools")

    assert result == expected
    call_args = agent_with_servers._with_mcp_session.call_args
    assert call_args[0][0]["name"] == "api-tools"


@pytest.mark.asyncio
async def test_discover_mcp_prompts_uses_cache(agent_with_servers):
    """Second call should return cached prompts."""
    cached = [{"name": "cached_prompt"}]
    agent_with_servers._discovered_mcp_prompts["api-tools"] = cached

    result = await agent_with_servers.discover_mcp_prompts("api-tools")

    assert result == cached


@pytest.mark.asyncio
async def test_discover_mcp_prompts_force_refresh(agent_with_servers):
    """force_refresh=True should bypass cache."""
    cached = [{"name": "old"}]
    fresh = [{"name": "new"}]
    agent_with_servers._discovered_mcp_prompts["api-tools"] = cached
    agent_with_servers._with_mcp_session = AsyncMock(return_value=fresh)

    result = await agent_with_servers.discover_mcp_prompts(
        "api-tools", force_refresh=True
    )

    assert result == fresh


@pytest.mark.asyncio
async def test_discover_mcp_prompts_not_configured(base_config, simple_signature):
    """Should raise RuntimeError when MCP not configured."""
    agent = BaseAgent(config=base_config, signature=simple_signature, mcp_servers=[])
    agent._mcp_servers = None

    with pytest.raises(RuntimeError, match="MCP not configured"):
        await agent.discover_mcp_prompts("api-tools")


@pytest.mark.asyncio
async def test_discover_mcp_prompts_server_not_found(agent_with_servers):
    """Should raise ValueError for unknown server."""
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent_with_servers.discover_mcp_prompts("nonexistent")


# ============================================
# get_mcp_prompt tests
# ============================================


@pytest.mark.asyncio
async def test_get_mcp_prompt_delegates_to_get_prompt(agent_with_servers):
    """get_mcp_prompt should call _with_mcp_session with get_prompt, name, and arguments."""
    expected = {
        "name": "greeting",
        "messages": [{"role": "user", "content": "Hello, Alice!"}],
        "arguments": {"name": "Alice"},
    }
    agent_with_servers._with_mcp_session = AsyncMock(return_value=expected)

    result = await agent_with_servers.get_mcp_prompt(
        "api-tools", "greeting", {"name": "Alice"}
    )

    assert result == expected
    call_args = agent_with_servers._with_mcp_session.call_args
    assert call_args[0][0]["name"] == "api-tools"
    assert call_args[0][2] == "greeting"
    assert call_args[0][3] == {"name": "Alice"}


@pytest.mark.asyncio
async def test_get_mcp_prompt_not_configured(base_config, simple_signature):
    """Should raise RuntimeError when MCP not configured."""
    agent = BaseAgent(config=base_config, signature=simple_signature, mcp_servers=[])
    agent._mcp_servers = None

    with pytest.raises(RuntimeError, match="MCP not configured"):
        await agent.get_mcp_prompt("api-tools", "greeting", {"name": "Alice"})


@pytest.mark.asyncio
async def test_get_mcp_prompt_server_not_found(agent_with_servers):
    """Should raise ValueError for unknown server."""
    with pytest.raises(ValueError, match="MCP server.*not found"):
        await agent_with_servers.get_mcp_prompt(
            "unknown", "greeting", {"name": "Alice"}
        )


# ============================================
# _with_mcp_session transport routing tests
# ============================================


@pytest.mark.asyncio
async def test_with_mcp_session_unsupported_transport(agent_with_servers):
    """Should raise ValueError for unsupported transport type."""
    bad_config = {"name": "bad", "transport": "carrier_pigeon"}

    with pytest.raises(ValueError, match="Unsupported transport type"):
        await agent_with_servers._with_mcp_session(bad_config, AsyncMock())


@pytest.mark.asyncio
async def test_with_mcp_session_websocket_missing_url(agent_with_servers):
    """Should raise ValueError when WebSocket config has no url."""
    bad_config = {"name": "bad", "transport": "websocket"}

    with pytest.raises(ValueError, match="must include 'url'"):
        await agent_with_servers._with_mcp_session(bad_config, AsyncMock())
