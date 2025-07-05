"""Unit tests for LLMAgent tool execution functionality."""

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from kailash.nodes.ai.llm_agent import LLMAgentNode


class TestLLMAgentToolExecution(unittest.TestCase):
    """Test tool execution in LLMAgentNode."""

    def setUp(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.node = LLMAgentNode()

    def tearDown(self):
        """Clean up test environment."""
        # Reset environment
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_tool_execution_with_mock_provider(self):
        """Test that tool calls are executed when returned by mock provider."""
        # Define a simple tool
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]

        # Call the agent with a message that triggers tool use
        result = self.node.run(
            provider="mock",
            model="test-model",
            messages=[
                {
                    "role": "user",
                    "content": "Please create a report using the test tool",
                }
            ],
            tools=tools,
            auto_execute_tools=True,
        )

        # Verify the response
        self.assertTrue(result["success"])
        self.assertIn("response", result)

        # Check that tool was executed
        self.assertIn("tool_execution_rounds", result["response"])
        self.assertGreater(result["response"]["tool_execution_rounds"], 0)

        # Verify context shows tool execution
        self.assertIn("tools_executed", result["context"])
        self.assertEqual(
            result["context"]["tools_executed"],
            result["response"]["tool_execution_rounds"],
        )

    def test_tool_execution_disabled(self):
        """Test that tools are not executed when auto_execute_tools is False."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        result = self.node.run(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Please execute the test tool"}],
            tools=tools,
            auto_execute_tools=False,
        )

        # Tool calls should be in response but not executed
        self.assertTrue(result["success"])
        response = result["response"]

        # Check that no tool execution happened
        self.assertNotIn("tool_execution_rounds", response)
        self.assertEqual(result["context"]["tools_executed"], 0)

    def test_mcp_tool_execution(self):
        """Test execution of MCP discovered tools."""
        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client_class:
            # Mock MCP client
            mock_client = MagicMock()
            mock_mcp_client_class.return_value = mock_client

            # Mock tool discovery
            mock_client.discover_tools = AsyncMock(
                return_value=[
                    {
                        "name": "mcp_search",
                        "description": "Search MCP server",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    }
                ]
            )

            # Mock tool execution
            mock_client.call_tool = AsyncMock(
                return_value={"result": "MCP search results", "status": "success"}
            )

            # Test with MCP server config
            result = self.node.run(
                provider="mock",
                model="test-model",
                messages=[{"role": "user", "content": "Execute MCP search for data"}],
                mcp_servers=[
                    {
                        "name": "test-mcp-server",
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "test_server"],
                    }
                ],
                auto_discover_tools=True,
                auto_execute_tools=True,
            )

            self.assertTrue(result["success"])
            # MCP tools should have been discovered
            self.assertGreater(result["context"]["tools_available"], 0)

    def test_multiple_tool_execution_rounds(self):
        """Test multiple rounds of tool execution."""
        # This tests the loop limiting functionality
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "iterative_tool",
                    "description": "A tool that might be called multiple times",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        result = self.node.run(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Execute iterative operations"}],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 3},
        )

        self.assertTrue(result["success"])
        # Check rounds are limited
        tool_rounds = result["response"].get("tool_execution_rounds", 0)
        self.assertLessEqual(tool_rounds, 3)

    def test_tool_execution_error_handling(self):
        """Test error handling during tool execution."""
        with patch.object(self.node, "_execute_mcp_tool_call") as mock_execute:
            # Make the tool execution fail
            mock_execute.side_effect = Exception("Tool execution failed")

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "failing_tool",
                        "description": "A tool that will fail",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

            result = self.node.run(
                provider="mock",
                model="test-model",
                messages=[{"role": "user", "content": "Execute the failing tool"}],
                tools=tools,
                auto_execute_tools=True,
            )

            # Should still succeed but with error in tool results
            self.assertTrue(result["success"])

    def test_execute_tool_calls_method(self):
        """Test the _execute_tool_calls method directly."""
        # Create tool calls
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "arguments": json.dumps({"param": "value"}),
                },
            }
        ]

        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {},
                },
            }
        ]

        # Execute tool calls
        results = self.node._execute_tool_calls(tool_calls, available_tools)

        # Verify results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tool_call_id"], "call_123")
        self.assertIn("content", results[0])

        # Parse the content to verify it's valid JSON
        content = json.loads(results[0]["content"])
        self.assertIn("status", content)

    def test_execute_regular_tool(self):
        """Test execution of regular (non-MCP) tools."""
        tool_call = {
            "id": "call_456",
            "function": {
                "name": "regular_tool",
                "arguments": json.dumps({"input": "test data"}),
            },
        }

        result = self.node._execute_regular_tool(tool_call, [])

        # Verify result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "regular_tool")
        self.assertIn("result", result)
        self.assertIn("regular_tool", result["result"])

    def test_tool_execution_with_mcp_and_regular_tools(self):
        """Test execution with both MCP and regular tools."""
        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client_class:
            mock_client = MagicMock()
            mock_mcp_client_class.return_value = mock_client

            # Mock MCP tool discovery
            mock_client.discover_tools = AsyncMock(
                return_value=[
                    {
                        "name": "mcp_tool",
                        "description": "MCP tool",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ]
            )

            # Regular tools
            regular_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "regular_tool",
                        "description": "Regular tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

            result = self.node.run(
                provider="mock",
                model="test-model",
                messages=[{"role": "user", "content": "Execute both tools"}],
                tools=regular_tools,
                mcp_servers=[{"name": "test-server", "transport": "stdio"}],
                auto_discover_tools=True,
                auto_execute_tools=True,
            )

            self.assertTrue(result["success"])
            # Should have both regular and MCP tools available
            self.assertGreaterEqual(result["context"]["tools_available"], 2)


if __name__ == "__main__":
    unittest.main()
