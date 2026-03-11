"""Edge case and error scenario tests for LLMAgent tool execution.

Tests various failure modes, edge conditions, and error recovery.
"""

import asyncio
import json
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode

from kailash.sdk_exceptions import NodeExecutionError


class TestLLMAgentToolExecutionEdgeCases:
    """Test edge cases and error scenarios for tool execution."""

    def setup_method(self):
        """Set up test environment."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.node = LLMAgentNode()

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    # ========== Malformed Tool Definitions ==========

    def test_malformed_tool_definition_missing_type(self):
        """Test handling of tool without type field."""
        malformed_tools = [
            {
                # Missing "type" field
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}},
                }
            }
        ]

        # Should handle gracefully
        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Test"}],
            tools=malformed_tools,
            auto_execute_tools=True,
        )

        assert result["success"] is True
        # Tool might be ignored or handled specially

    def test_malformed_tool_definition_invalid_parameters(self):
        """Test handling of tool with invalid parameter schema."""
        malformed_tools = [
            {
                "type": "function",
                "function": {
                    "name": "bad_params_tool",
                    "description": "Tool with bad params",
                    "parameters": "not a dict",  # Should be dict
                },
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Test"}],
            tools=malformed_tools,
            auto_execute_tools=True,
        )

        assert result["success"] is True

    def test_circular_tool_dependencies(self):
        """Test handling of tools that might create circular dependencies."""
        circular_tools = [
            {
                "type": "function",
                "function": {
                    "name": "tool_a",
                    "description": "Calls tool B",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "tool_b",
                    "description": "Calls tool A",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Use the tools"}],
            tools=circular_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 3},  # Limit to prevent infinite loop
        )

        assert result["success"] is True
        # Should respect max_rounds limit

    # ========== Tool Execution Failures ==========

    def test_tool_execution_timeout(self):
        """Test timeout handling during tool execution."""
        with patch.object(self.node, "_execute_mcp_tool_call") as mock_execute:
            # Simulate a hanging tool
            async def slow_tool(*args, **kwargs):
                await asyncio.sleep(0.2)  # Just slightly longer than most timeouts
                return {"result": "too late"}

            mock_execute.side_effect = slow_tool

            timeout_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "slow_tool",
                        "description": "Tool that times out",
                        "parameters": {"type": "object", "properties": {}},
                        "mcp_server": "test",
                    },
                }
            ]

            result = self.node.execute(
                provider="mock",
                model="test",
                messages=[{"role": "user", "content": "Run slow tool"}],
                tools=timeout_tools,
                auto_execute_tools=True,
                tool_execution_config={"timeout": 1},  # 1 second timeout
            )

            # Should complete despite timeout
            assert result["success"] is True

    def test_tool_execution_exception(self):
        """Test exception handling during tool execution."""
        with patch.object(self.node, "_execute_regular_tool") as mock_execute:
            mock_execute.side_effect = Exception("Tool crashed!")

            crash_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "crashing_tool",
                        "description": "Tool that crashes",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

            # Mock provider to return tool call
            with patch.object(self.node, "_provider_llm_response") as mock_provider:
                mock_provider.return_value = {
                    "content": "Using tool",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "crashing_tool", "arguments": "{}"},
                        }
                    ],
                }

                result = self.node.execute(
                    provider="test",
                    model="test",
                    messages=[{"role": "user", "content": "Use crashing tool"}],
                    tools=crash_tools,
                    auto_execute_tools=True,
                    tool_execution_config={"continue_on_error": True},
                )

                assert result["success"] is True
                # Should continue despite tool crash

    # ========== Invalid Tool Calls from LLM ==========

    def test_llm_calls_nonexistent_tool(self):
        """Test when LLM calls a tool that doesn't exist."""
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": "real_tool",
                    "description": "A real tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        # Mock LLM to call non-existent tool
        with patch.object(self.node, "_provider_llm_response") as mock_provider:
            mock_provider.side_effect = [
                {
                    "content": "I'll use a tool",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "nonexistent_tool", "arguments": "{}"},
                        }
                    ],
                },
                {"content": "Tool not found, proceeding without it", "tool_calls": []},
            ]

            result = self.node.execute(
                provider="test",
                model="test",
                messages=[{"role": "user", "content": "Do something"}],
                tools=available_tools,
                auto_execute_tools=True,
            )

            assert result["success"] is True

    def test_llm_provides_invalid_json_arguments(self):
        """Test when LLM provides malformed JSON in tool arguments."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "json_tool",
                    "description": "Tool expecting JSON",
                    "parameters": {
                        "type": "object",
                        "properties": {"data": {"type": "object"}},
                        "required": ["data"],
                    },
                },
            }
        ]

        with patch.object(self.node, "_provider_llm_response") as mock_provider:
            mock_provider.side_effect = [
                {
                    "content": "Using tool with bad JSON",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "json_tool",
                                "arguments": "{invalid json: true",  # Malformed JSON
                            },
                        }
                    ],
                },
                {"content": "Handled the error", "tool_calls": []},
            ]

            result = self.node.execute(
                provider="test",
                model="test",
                messages=[{"role": "user", "content": "Use the tool"}],
                tools=tools,
                auto_execute_tools=True,
            )

            assert result["success"] is True

    # ========== Extreme Scale Tests ==========

    def test_massive_tool_catalog(self):
        """Test with extremely large number of tools."""
        # Generate 1000 tools
        massive_tools = []
        for i in range(1000):
            massive_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"tool_{i}",
                        "description": f"Tool number {i} - "
                        + "x" * 100,  # Long description
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
            )

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Find and use tool_500"}],
            tools=massive_tools,
            auto_execute_tools=True,
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 1000

    def test_deeply_nested_tool_arguments(self):
        """Test tools with deeply nested parameter structures."""
        nested_tool = {
            "type": "function",
            "function": {
                "name": "nested_tool",
                "description": "Tool with nested params",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level1": {
                            "type": "object",
                            "properties": {
                                "level2": {
                                    "type": "object",
                                    "properties": {
                                        "level3": {
                                            "type": "object",
                                            "properties": {
                                                "level4": {
                                                    "type": "object",
                                                    "properties": {
                                                        "value": {"type": "string"}
                                                    },
                                                }
                                            },
                                        }
                                    },
                                }
                            },
                        }
                    },
                },
            },
        }

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Use nested tool"}],
            tools=[nested_tool],
            auto_execute_tools=True,
        )

        assert result["success"] is True

    # ========== Concurrent Execution Edge Cases ==========

    def test_concurrent_tool_calls_with_failures(self):
        """Test multiple tool calls where some fail."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": f"Tool {i}",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for i in range(5)
        ]

        # Mock some tools to fail
        with patch.object(self.node, "_execute_regular_tool") as mock_execute:

            def execute_with_failures(tool_name, args):
                if "2" in tool_name or "4" in tool_name:
                    raise Exception(f"{tool_name} failed")
                return {"result": f"{tool_name} succeeded"}

            mock_execute.side_effect = execute_with_failures

            # Mock LLM to call all tools
            with patch.object(self.node, "_provider_llm_response") as mock_provider:
                mock_provider.side_effect = [
                    {
                        "content": "Calling all tools",
                        "tool_calls": [
                            {
                                "id": f"call_{i}",
                                "function": {"name": f"tool_{i}", "arguments": "{}"},
                            }
                            for i in range(5)
                        ],
                    },
                    {"content": "Processed results", "tool_calls": []},
                ]

                result = self.node.execute(
                    provider="test",
                    model="test",
                    messages=[{"role": "user", "content": "Use all tools"}],
                    tools=tools,
                    auto_execute_tools=True,
                    tool_execution_config={"continue_on_error": True},
                )

                assert result["success"] is True
                # Should handle partial failures

    # ========== Memory and Resource Tests ==========

    def test_tool_execution_memory_limits(self):
        """Test memory limit handling during tool execution."""
        memory_intensive_tool = {
            "type": "function",
            "function": {
                "name": "memory_hog",
                "description": "Tool using lots of memory",
                "parameters": {
                    "type": "object",
                    "properties": {"size_mb": {"type": "integer"}},
                },
            },
        }

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[{"role": "user", "content": "Use memory tool with 1000 MB"}],
            tools=[memory_intensive_tool],
            auto_execute_tools=True,
            tool_execution_config={"memory_limit": 500},  # 500 MB limit
        )

        assert result["success"] is True

    # ========== Special Characters and Encoding ==========

    def test_tools_with_unicode_and_special_chars(self):
        """Test tools with unicode and special characters."""
        unicode_tools = [
            {
                "type": "function",
                "function": {
                    "name": "unicode_tool_😀",
                    "description": "Tool with émojis and spëcial chàracters 中文",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Ünïcödé input"}
                        },
                    },
                },
            }
        ]

        result = self.node.execute(
            provider="mock",
            model="test",
            messages=[
                {
                    "role": "user",
                    "content": "Use the unicode tool with text: 你好世界 🌍",
                }
            ],
            tools=unicode_tools,
            auto_execute_tools=True,
        )

        assert result["success"] is True

    # ========== State Management Edge Cases ==========

    def test_tool_execution_state_corruption(self):
        """Test recovery from state corruption during execution."""
        with patch.object(self.node, "_execute_tool_calls") as mock_execute:
            # First call corrupts state
            def corrupt_state(*args, **kwargs):
                # Simulate state corruption
                self.node._some_internal_state = None
                return [
                    {"tool_call_id": "1", "content": '{"error": "state corrupted"}'}
                ]

            mock_execute.side_effect = [corrupt_state, []]

            result = self.node.execute(
                provider="mock",
                model="test",
                messages=[{"role": "user", "content": "Test"}],
                tools=[
                    {"type": "function", "function": {"name": "test", "parameters": {}}}
                ],
                auto_execute_tools=True,
            )

            # Should handle state issues gracefully
            assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
