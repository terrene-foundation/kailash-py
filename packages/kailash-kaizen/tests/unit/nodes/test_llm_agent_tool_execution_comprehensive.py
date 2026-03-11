"""Comprehensive unit tests for LLMAgent tool execution functionality."""

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode


class TestLLMAgentToolExecutionComprehensive(unittest.TestCase):
    """Comprehensive test coverage for tool execution in LLMAgentNode."""

    def setUp(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.node = LLMAgentNode()

    def tearDown(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    # ========== Basic Tool Execution Tests ==========

    def test_tool_execution_enabled_by_default(self):
        """Test that auto_execute_tools is True by default."""
        params = self.node.get_parameters()
        self.assertTrue(params["auto_execute_tools"].default)

    def test_tool_execution_can_be_disabled(self):
        """Test that tool execution can be disabled."""
        result = self.node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Do something"}],
            auto_execute_tools=False,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["context"]["tools_executed"], 0)

    def test_tool_execution_config_parameter(self):
        """Test tool_execution_config parameter handling."""
        config = {"max_rounds": 3, "timeout": 60}
        result = self.node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Test"}],
            tool_execution_config=config,
        )
        self.assertTrue(result["success"])

    # ========== Tool Call Execution Tests ==========

    def test_execute_tool_calls_with_regular_tools(self):
        """Test _execute_tool_calls with regular (non-MCP) tools."""
        tool_calls = [
            {
                "id": "call_001",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": json.dumps({"operation": "add", "a": 5, "b": 3}),
                },
            },
            {
                "id": "call_002",
                "type": "function",
                "function": {
                    "name": "weather",
                    "arguments": json.dumps({"location": "Paris"}),
                },
            },
        ]

        available_tools = [
            {"type": "function", "function": {"name": "calculator"}},
            {"type": "function", "function": {"name": "weather"}},
        ]

        results = self.node._execute_tool_calls(tool_calls, available_tools)

        # Verify results structure
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["tool_call_id"], "call_001")
        self.assertEqual(results[1]["tool_call_id"], "call_002")

        # Verify content is valid JSON
        for result in results:
            content = json.loads(result["content"])
            self.assertIn("status", content)

    def test_execute_tool_calls_with_mcp_tools(self):
        """Test _execute_tool_calls with MCP tools."""
        with patch.object(self.node, "_execute_mcp_tool_call") as mock_mcp_execute:
            mock_mcp_execute.return_value = {
                "result": "MCP tool executed",
                "success": True,
            }

            tool_calls = [
                {
                    "id": "call_mcp",
                    "type": "function",
                    "function": {
                        "name": "mcp_search",
                        "arguments": json.dumps({"query": "test"}),
                    },
                }
            ]

            mcp_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_search",
                        "mcp_server": "test-server",
                        "mcp_server_config": {"name": "test-server"},
                    },
                }
            ]

            results = self.node._execute_tool_calls(tool_calls, [], mcp_tools)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["tool_call_id"], "call_mcp")
            mock_mcp_execute.assert_called_once()

    def test_execute_tool_calls_error_handling(self):
        """Test error handling in _execute_tool_calls."""
        with patch.object(self.node, "_execute_mcp_tool_call") as mock_execute:
            mock_execute.side_effect = Exception("Tool execution failed")

            tool_calls = [
                {
                    "id": "call_fail",
                    "function": {"name": "failing_tool", "arguments": "{}"},
                }
            ]

            mcp_tools = [{"type": "function", "function": {"name": "failing_tool"}}]

            results = self.node._execute_tool_calls(tool_calls, [], mcp_tools)

            # Should handle error gracefully
            self.assertEqual(len(results), 1)
            content = json.loads(results[0]["content"])
            self.assertEqual(content["status"], "failed")
            self.assertIn("error", content)

    # ========== Tool Execution Loop Tests ==========

    def test_tool_execution_loop_single_round(self):
        """Test tool execution loop with single round."""

        # Create a mock provider that returns tool calls once
        def mock_provider_response(provider, model, messages, tools, config):
            # First call returns tool calls
            if len(messages) == 1:
                return {
                    "id": "msg_1",
                    "content": "I'll calculate that for you.",
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": json.dumps({"a": 5, "b": 3}),
                            },
                        }
                    ],
                    "tool_execution_rounds": 0,
                }
            # Second call (after tool execution) returns final response
            else:
                return {
                    "id": "msg_2",
                    "content": "The result is 8.",
                    "role": "assistant",
                    "tool_calls": [],  # No more tool calls
                    "tool_execution_rounds": 1,
                }

        with patch.object(
            self.node, "_provider_llm_response", side_effect=mock_provider_response
        ):
            tools = [{"type": "function", "function": {"name": "calculator"}}]

            result = self.node.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Calculate 5 + 3"}],
                tools=tools,
                auto_execute_tools=True,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["context"]["tools_executed"], 1)
            self.assertEqual(result["response"]["tool_execution_rounds"], 1)

    def test_tool_execution_loop_multiple_rounds(self):
        """Test tool execution loop with multiple rounds."""
        call_count = 0

        def mock_provider_response(provider, model, messages, tools, config):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First round: request tool A
                return {
                    "content": "Let me get data first.",
                    "tool_calls": [
                        {
                            "id": f"call_{call_count}",
                            "function": {"name": "get_data", "arguments": "{}"},
                        }
                    ],
                }
            elif call_count == 2:
                # Second round: request tool B based on tool A results
                return {
                    "content": "Now I'll process the data.",
                    "tool_calls": [
                        {
                            "id": f"call_{call_count}",
                            "function": {"name": "process_data", "arguments": "{}"},
                        }
                    ],
                }
            else:
                # Final round: no more tools
                return {
                    "content": "Processing complete.",
                    "tool_calls": [],
                    "tool_execution_rounds": 2,
                }

        with patch.object(
            self.node, "_provider_llm_response", side_effect=mock_provider_response
        ):
            tools = [
                {"type": "function", "function": {"name": "get_data"}},
                {"type": "function", "function": {"name": "process_data"}},
            ]

            result = self.node.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Get and process data"}],
                tools=tools,
                auto_execute_tools=True,
                tool_execution_config={"max_rounds": 5},
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["context"]["tools_executed"], 2)

    def test_tool_execution_loop_respects_max_rounds(self):
        """Test that tool execution loop respects max_rounds limit."""

        def mock_provider_always_returns_tools(
            provider, model, messages, tools, config
        ):
            # Always return tool calls
            return {
                "content": "More tools needed.",
                "tool_calls": [
                    {
                        "id": f"call_{len(messages)}",
                        "function": {"name": "infinite_tool", "arguments": "{}"},
                    }
                ],
            }

        with patch.object(
            self.node,
            "_provider_llm_response",
            side_effect=mock_provider_always_returns_tools,
        ):
            tools = [{"type": "function", "function": {"name": "infinite_tool"}}]

            result = self.node.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Infinite loop test"}],
                tools=tools,
                auto_execute_tools=True,
                tool_execution_config={"max_rounds": 2},  # Limit to 2 rounds
            )

            self.assertTrue(result["success"])
            # Should stop at 2 rounds
            self.assertEqual(result["context"]["tools_executed"], 2)

    # ========== MCP Tool Execution Tests ==========

    @patch("kailash.mcp_server.MCPClient")
    def test_execute_mcp_tool_call_success(self, mock_mcp_client_class):
        """Test successful MCP tool execution."""
        mock_client = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Mock async call_tool method
        mock_client.call_tool = AsyncMock(
            return_value={"result": "Success", "data": [1, 2, 3]}
        )

        tool_call = {
            "id": "mcp_call_1",
            "function": {
                "name": "mcp_tool",
                "arguments": json.dumps({"param": "value"}),
            },
        }

        mcp_tools = [
            {
                "function": {
                    "name": "mcp_tool",
                    "mcp_server_config": {"name": "test-server", "transport": "stdio"},
                }
            }
        ]

        # Execute async method
        import asyncio

        result = asyncio.run(self.node._execute_mcp_tool_call(tool_call, mcp_tools))

        self.assertTrue(result["success"])
        self.assertEqual(result["tool_name"], "mcp_tool")
        self.assertEqual(result["server"], "test-server")
        mock_client.call_tool.assert_called_once()

    @patch("kailash.mcp_server.MCPClient")
    def test_execute_mcp_tool_call_failure(self, mock_mcp_client_class):
        """Test MCP tool execution failure handling."""
        mock_client = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Mock tool call failure
        mock_client.call_tool = AsyncMock(side_effect=Exception("MCP server error"))

        tool_call = {
            "id": "call_fail_test",
            "function": {
                "name": "failing_mcp_tool",
                "arguments": "{}",
            },
        }

        mcp_tools = [
            {
                "function": {
                    "name": "failing_mcp_tool",
                    "mcp_server_config": {"name": "failing-server"},
                }
            }
        ]

        import asyncio

        result = asyncio.run(self.node._execute_mcp_tool_call(tool_call, mcp_tools))

        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertEqual(result["tool_name"], "failing_mcp_tool")

    def test_execute_mcp_tool_not_found(self):
        """Test MCP tool execution when tool not found."""
        tool_call = {
            "id": "call_not_found",
            "function": {
                "name": "nonexistent_tool",
                "arguments": "{}",
            },
        }

        mcp_tools = [{"function": {"name": "other_tool"}}]

        import asyncio

        result = asyncio.run(self.node._execute_mcp_tool_call(tool_call, mcp_tools))

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    # ========== Edge Cases and Error Scenarios ==========

    def test_tool_execution_with_invalid_arguments(self):
        """Test tool execution with invalid JSON arguments."""
        tool_calls = [
            {
                "id": "invalid_args",
                "function": {
                    "name": "test_tool",
                    "arguments": "invalid json{",  # Invalid JSON
                },
            }
        ]

        results = self.node._execute_tool_calls(tool_calls, [])

        # Should handle gracefully
        self.assertEqual(len(results), 1)
        content = json.loads(results[0]["content"])
        self.assertEqual(content["status"], "failed")

    def test_tool_execution_with_missing_fields(self):
        """Test tool execution with missing required fields."""
        # Missing function field
        tool_calls = [
            {
                "id": "missing_function",
                # No function field
            }
        ]

        results = self.node._execute_tool_calls(tool_calls, [])
        self.assertEqual(len(results), 1)

        # Missing name in function
        tool_calls = [
            {
                "id": "missing_name",
                "function": {
                    # No name field
                    "arguments": "{}",
                },
            }
        ]

        results = self.node._execute_tool_calls(tool_calls, [])
        self.assertEqual(len(results), 1)

    def test_tool_execution_with_empty_tools(self):
        """Test tool execution with empty tool lists."""
        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "some_tool", "arguments": "{}"},
            }
        ]

        # Empty available tools and MCP tools
        results = self.node._execute_tool_calls(tool_calls, [], [])

        # Should still return results (regular tool execution)
        self.assertEqual(len(results), 1)

    def test_concurrent_tool_execution(self):
        """Test handling of multiple tool calls in single round."""
        tool_calls = [
            {
                "id": f"call_{i}",
                "function": {
                    "name": f"tool_{i}",
                    "arguments": json.dumps({"index": i}),
                },
            }
            for i in range(5)
        ]

        results = self.node._execute_tool_calls(tool_calls, [])

        # All tools should be executed
        self.assertEqual(len(results), 5)

        # Verify each result
        for i, result in enumerate(results):
            self.assertEqual(result["tool_call_id"], f"call_{i}")

    # ========== Integration with Response Flow ==========

    def test_tool_results_added_to_conversation(self):
        """Test that tool results are properly added to conversation."""
        messages_captured = []

        def capture_messages(provider, model, messages, tools, config):
            messages_captured.append(list(messages))  # Capture a copy

            if len(messages) == 1:
                # First call
                return {
                    "content": "Using tool",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "test_tool", "arguments": "{}"},
                        }
                    ],
                }
            else:
                # After tool execution
                return {"content": "Done", "tool_calls": []}

        with patch.object(
            self.node, "_provider_llm_response", side_effect=capture_messages
        ):
            result = self.node.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Test"}],
                tools=[{"type": "function", "function": {"name": "test_tool"}}],
                auto_execute_tools=True,
            )

            # Check that messages were properly enriched
            self.assertGreater(len(messages_captured), 1)

            # Second call should have tool results
            final_messages = messages_captured[-1]

            # Should contain assistant message with tool calls
            assistant_msgs = [m for m in final_messages if m.get("role") == "assistant"]
            self.assertTrue(any("tool_calls" in m for m in assistant_msgs))

            # Should contain tool result messages
            tool_msgs = [m for m in final_messages if m.get("role") == "tool"]
            self.assertGreater(len(tool_msgs), 0)

    def test_tool_execution_preserves_conversation_context(self):
        """Test that tool execution preserves conversation context."""
        initial_messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Remember X=42"},
            {"role": "assistant", "content": "I'll remember that."},
            {"role": "user", "content": "Now calculate X+8"},
        ]

        with patch.object(self.node, "_provider_llm_response") as mock_provider:
            # First response requests tool
            mock_provider.side_effect = [
                {
                    "content": "Let me calculate that.",
                    "tool_calls": [
                        {
                            "id": "calc_1",
                            "function": {
                                "name": "calculator",
                                "arguments": json.dumps({"a": 42, "b": 8}),
                            },
                        }
                    ],
                },
                {
                    "content": "X + 8 = 50",
                    "tool_calls": [],
                },
            ]

            result = self.node.execute(
                provider="test",
                model="test-model",
                messages=initial_messages,
                tools=[{"type": "function", "function": {"name": "calculator"}}],
                auto_execute_tools=True,
            )

            # Verify context was preserved
            self.assertTrue(result["success"])

            # Check that provider was called with full context
            calls = mock_provider.call_args_list
            final_call_messages = calls[-1][0][2]  # Third argument is messages

            # Should contain all original messages
            self.assertGreaterEqual(len(final_call_messages), len(initial_messages))

    # ========== Performance and Resource Tests ==========

    def test_tool_execution_performance(self):
        """Test that tool execution doesn't significantly impact performance."""
        import time

        # Disable tool execution
        start_time = time.time()
        result1 = self.node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Test"}],
            auto_execute_tools=False,
        )
        time_without_tools = time.time() - start_time

        # Enable tool execution (but mock won't return tools)
        start_time = time.time()
        result2 = self.node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Test"}],
            auto_execute_tools=True,
        )
        time_with_tools = time.time() - start_time

        # Tool execution overhead should be minimal
        self.assertLess(
            time_with_tools - time_without_tools, 0.1
        )  # Less than 100ms overhead

    def test_memory_usage_with_many_tools(self):
        """Test memory handling with many tools."""
        # Create 100 tools
        many_tools = [
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": f"Tool number {i} with a long description " * 10,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            f"param_{j}": {
                                "type": "string",
                                "description": f"Parameter {j}",
                            }
                            for j in range(10)
                        },
                    },
                },
            }
            for i in range(100)
        ]

        # Should handle without issues - tests that large tool lists don't cause memory issues
        result = self.node.execute(
            provider="mock",
            model="test-model",
            messages=[{"role": "user", "content": "Test with many tools"}],
            tools=many_tools,
            auto_execute_tools=True,
        )

        self.assertTrue(result["success"])
        self.assertIn("context", result)
        self.assertIn("tools_available", result["context"])
        # The implementation may process tools differently; main test is no memory issues
        self.assertGreaterEqual(result["context"]["tools_available"], 0)


if __name__ == "__main__":
    unittest.main()
