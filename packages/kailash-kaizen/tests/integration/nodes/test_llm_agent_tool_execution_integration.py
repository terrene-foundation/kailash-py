"""Integration tests for LLMAgent tool execution with real scenarios."""

import asyncio
import json
import os

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode


@pytest.mark.integration
class TestLLMAgentToolExecutionIntegration:
    """Test tool execution in real-world scenarios."""

    def setup_method(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.node = LLMAgentNode(name="test_tool_agent")

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_complete_tool_execution_flow(self):
        """Test complete flow: discovery -> execution -> response."""
        # Define tools that would be used
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_sum",
                    "description": "Calculate the sum of two numbers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "format_result",
                    "description": "Format a calculation result",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {
                                "type": "number",
                                "description": "Value to format",
                            },
                            "prefix": {"type": "string", "description": "Prefix text"},
                        },
                        "required": ["value"],
                    },
                },
            },
        ]

        # Run the agent
        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Create a calculation: add 5 and 3, then format the result nicely",
                }
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 3},
        )

        # Verify success
        assert result["success"] is True
        assert "response" in result

        # Check that tools were executed
        assert result["context"]["tools_executed"] > 0

        # Verify the response contains tool execution info
        response = result["response"]
        assert "tool_execution_rounds" in response
        assert response["tool_execution_rounds"] > 0

    def test_tool_execution_with_errors(self):
        """Test tool execution handles errors gracefully."""
        # Tool that will cause issues
        problematic_tools = [
            {
                "type": "function",
                "function": {
                    "name": "problematic_tool",
                    "description": "A tool that might fail",
                    "parameters": {
                        "type": "object",
                        "properties": {"fail": {"type": "boolean"}},
                    },
                },
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Execute the problematic tool"}],
            tools=problematic_tools,
            auto_execute_tools=True,
        )

        # Should still succeed even if tool execution has issues
        assert result["success"] is True

    def test_mixed_mcp_and_regular_tools(self):
        """Test execution with both MCP and regular tools in same conversation."""
        # Regular tools
        regular_tools = [
            {
                "type": "function",
                "function": {
                    "name": "local_search",
                    "description": "Search local data",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]

        # Mock MCP server config (would fail but that's ok for this test)
        mcp_servers = [
            {
                "name": "test-knowledge-base",
                "transport": "stdio",
                "command": "echo",
                "args": ["mcp-test"],
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Search for information and execute tools"}
            ],
            tools=regular_tools,
            mcp_servers=mcp_servers,
            auto_discover_tools=True,
            auto_execute_tools=True,
            mcp_config={"fallback_on_failure": True},
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] >= 1  # At least regular tools

    def test_tool_execution_respects_max_rounds(self):
        """Test that tool execution respects max_rounds configuration."""
        # Tool that could be called repeatedly
        recursive_tool = [
            {
                "type": "function",
                "function": {
                    "name": "recursive_operation",
                    "description": "An operation that might trigger more operations",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Execute recursive operations"}],
            tools=recursive_tool,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 2},  # Limit to 2 rounds
        )

        assert result["success"] is True

        # Check rounds are limited
        if "tool_execution_rounds" in result["response"]:
            assert result["response"]["tool_execution_rounds"] <= 2

    @pytest.mark.asyncio
    async def test_async_tool_execution(self):
        """Test tool execution in async context."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "async_tool",
                    "description": "Tool for async testing",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        # Run in async context
        loop = asyncio.get_event_loop()

        def run_agent():
            return self.node.execute(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": "Execute async tool"}],
                tools=tools,
                auto_execute_tools=True,
            )

        # Execute in thread pool to avoid event loop issues
        result = await loop.run_in_executor(None, run_agent)

        assert result["success"] is True

    def test_tool_execution_disabled_returns_tool_calls(self):
        """Test that disabling auto_execute_tools returns tool_calls without execution."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "unexecuted_tool",
                    "description": "This tool should not be executed",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Create something with tools"}],
            tools=tools,
            auto_execute_tools=False,  # Disable execution
        )

        assert result["success"] is True

        # Tools should not have been executed
        assert result["context"]["tools_executed"] == 0

        # But tool_calls might be in the response
        response = result["response"]
        if "tool_calls" in response and response["tool_calls"]:
            # If there are tool calls, they weren't executed
            assert "tool_execution_rounds" not in response
