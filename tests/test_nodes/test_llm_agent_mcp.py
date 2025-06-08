"""Unit tests for LLMAgentNode with MCP integration."""

import pytest

from kailash.nodes.ai import LLMAgentNode


class TestLLMAgentMCPIntegration:
    """Test cases for LLMAgentNode with built-in MCP capabilities."""

    def test_mcp_context_retrieval(self):
        """Test retrieving context from MCP servers."""
        agent = LLMAgentNode(name="test_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Test message"}],
            mcp_servers=[
                {
                    "name": "test-server",
                    "transport": "stdio",
                    "command": "test-mcp-server",
                }
            ],
            mcp_context=["data://test/resource"],
        )

        assert result["success"] is True
        assert "context" in result
        assert result["context"]["mcp_resources_used"] >= 1

    def test_auto_discover_tools(self):
        """Test automatic tool discovery from MCP servers."""
        agent = LLMAgentNode(name="test_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Use available tools"}],
            mcp_servers=[
                {
                    "name": "tool-server",
                    "transport": "http",
                    "url": "http://localhost:8080",
                }
            ],
            auto_discover_tools=True,
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] > 0

    def test_multiple_mcp_servers(self):
        """Test connecting to multiple MCP servers."""
        agent = LLMAgentNode(name="test_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Aggregate data"}],
            mcp_servers=[
                {"name": "server1", "transport": "stdio", "command": "mcp-server1"},
                {
                    "name": "server2",
                    "transport": "http",
                    "url": "http://localhost:8081",
                },
            ],
            mcp_context=["data://server1/data", "data://server2/data"],
        )

        assert result["success"] is True
        assert result["context"]["mcp_resources_used"] >= 2

    def test_mcp_tool_merging(self):
        """Test merging MCP discovered tools with existing tools."""
        agent = LLMAgentNode(name="test_agent")

        existing_tools = [
            {
                "type": "function",
                "function": {
                    "name": "existing_tool",
                    "description": "An existing tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "List tools"}],
            tools=existing_tools,
            mcp_servers=[
                {"name": "tool-server", "transport": "stdio", "command": "mcp"}
            ],
            auto_discover_tools=True,
        )

        assert result["success"] is True
        # Should have at least the existing tool + discovered tools
        assert result["context"]["tools_available"] > len(existing_tools)

    def test_mcp_error_handling(self):
        """Test graceful handling of MCP connection errors."""
        agent = LLMAgentNode(name="test_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Test error handling"}],
            mcp_servers=[
                {
                    "name": "invalid-server",
                    "transport": "stdio",
                    "command": "non-existent-command",
                }
            ],
            mcp_context=["data://invalid/resource"],
        )

        # Should still succeed with fallback behavior
        assert result["success"] is True
        assert "response" in result

    def test_mcp_with_rag_integration(self):
        """Test MCP integration with RAG."""
        agent = LLMAgentNode(name="test_agent")

        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Search with context"}],
            mcp_servers=[
                {"name": "knowledge-server", "transport": "stdio", "command": "mcp-kb"}
            ],
            mcp_context=["resource://knowledge/base"],
            rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
        )

        assert result["success"] is True
        assert result["context"]["mcp_resources_used"] >= 1
        assert result["context"]["rag_documents_retrieved"] >= 0

    def test_tool_discovery_mock_fallback(self):
        """Test that tool discovery falls back to mock tools when MCP unavailable."""
        agent = LLMAgentNode(name="test_agent")

        # Test internal method directly
        mock_tools = agent._discover_mcp_tools(
            [{"name": "test-server", "transport": "stdio", "command": "test"}]
        )

        assert len(mock_tools) > 0
        # Should have mock tools with correct naming
        tool_names = [t["function"]["name"] for t in mock_tools]
        assert any("mcp_test-server" in name for name in tool_names)

    def test_tool_merging_deduplication(self):
        """Test that tool merging avoids duplicates."""
        agent = LLMAgentNode(name="test_agent")

        existing = [
            {"type": "function", "function": {"name": "tool1"}},
            {"type": "function", "function": {"name": "tool2"}},
        ]

        mcp_tools = [
            {"type": "function", "function": {"name": "tool2"}},  # Duplicate
            {"type": "function", "function": {"name": "tool3"}},  # New
        ]

        merged = agent._merge_tools(existing, mcp_tools)

        # Should have 3 tools total (tool1, tool2, tool3)
        assert len(merged) == 3
        tool_names = [t["function"]["name"] for t in merged]
        assert sorted(tool_names) == ["tool1", "tool2", "tool3"]

    def test_mcp_context_format_handling(self):
        """Test handling of different MCP content formats."""
        agent = LLMAgentNode(name="test_agent")

        # Test with different URI schemes
        result = agent.run(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Test URIs"}],
            mcp_context=[
                "data://path/to/data",
                "file://path/to/file",
                "resource://type/name",
                "prompt://template/name",
            ],
        )

        assert result["success"] is True
        assert result["context"]["mcp_resources_used"] == 4


@pytest.mark.parametrize(
    "transport,config",
    [
        ("stdio", {"command": "test-server", "args": ["--port", "8080"]}),
        ("http", {"url": "http://localhost:8080", "headers": {"Auth": "Bearer token"}}),
        ("sse", {"url": "http://localhost:8080/events"}),
    ],
)
def test_mcp_transport_types(transport, config):
    """Test different MCP transport configurations."""
    agent = LLMAgentNode(name="test_agent")

    server_config = {"name": f"{transport}-server", "transport": transport}
    server_config.update(config)

    result = agent.run(
        provider="mock",
        model="gpt-4",
        messages=[{"role": "user", "content": f"Test {transport} transport"}],
        mcp_servers=[server_config],
    )

    assert result["success"] is True
    assert "response" in result
