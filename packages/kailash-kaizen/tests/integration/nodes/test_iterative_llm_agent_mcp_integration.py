"""Integration test for IterativeLLMAgent MCP tool execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode


class TestIterativeLLMAgentMCPIntegration:
    """Integration test for MCP tool execution in IterativeLLMAgent."""

    def setup_method(self):
        """Set up test fixtures."""
        self.agent = IterativeLLMAgentNode()

    @patch("kailash.mcp_server.MCPClient")
    def test_end_to_end_with_real_mcp_execution(self, mock_mcp_client):
        """Test end-to-end execution with real MCP tool calls."""
        # Setup mock MCP client that returns realistic responses
        mock_client_instance = MagicMock()
        mock_client_instance.call_tool = AsyncMock(
            return_value={
                "success": True,
                "content": "Tool execution successful: Found 5 relevant documents about AI trends",
                "tool_name": "search_tool",
            }
        )
        mock_mcp_client.return_value = mock_client_instance

        # Setup mock for tool discovery
        mock_client_instance.discover_tools = AsyncMock(
            return_value=[
                {
                    "name": "search_tool",
                    "description": "Search for information",
                    "parameters": {"query": {"type": "string"}},
                }
            ]
        )

        # Mock the parent's _discover_mcp_tools method to return discovered tools
        with patch.object(
            self.agent,
            "_discover_mcp_tools",
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "search_tool",
                        "description": "Search for information",
                        "parameters": {"query": {"type": "string"}},
                        "mcp_server_config": {"url": "http://test-server.com"},
                    },
                }
            ],
        ):
            # Mock the parent's run method to avoid actual LLM calls
            with patch(
                "kailash.nodes.ai.llm_agent.LLMAgentNode.run",
                return_value={
                    "success": True,
                    "response": {"content": "Test response"},
                    "usage": {"total_tokens": 100},
                },
            ):
                # Execute the agent with real MCP enabled
                result = self.agent.run(
                    provider="test",
                    model="test-model",
                    messages=[{"role": "user", "content": "Search for AI trends"}],
                    mcp_servers=[{"url": "http://test-server.com"}],
                    use_real_mcp=True,
                    max_iterations=1,
                )

                # Verify the result
                assert result["success"] is True
                assert len(result["iterations"]) == 1

                # Verify that real MCP tool was called
                iteration = result["iterations"][0]
                assert "execution_results" in iteration
                exec_results = iteration["execution_results"]

                # Check that real tool execution occurred
                assert len(exec_results["steps_completed"]) > 0
                step_result = exec_results["steps_completed"][0]
                assert step_result["success"] is True
                assert "Tool execution successful" in step_result["output"]

                # Verify MCP client was called
                mock_client_instance.call_tool.assert_called()

                # Verify the call was made with correct parameters
                call_args = mock_client_instance.call_tool.call_args
                assert call_args[0][0] == {
                    "url": "http://test-server.com"
                }  # server_config
                assert call_args[0][1] == "search_tool"  # tool_name
                assert "query" in call_args[0][2]  # arguments

    def test_fallback_to_mock_when_mcp_disabled(self):
        """Test that agent falls back to mock execution when MCP is disabled."""
        # Mock the parent's _discover_mcp_tools method
        with patch.object(self.agent, "_discover_mcp_tools", return_value=[]):
            # Mock the parent's run method
            with patch(
                "kailash.nodes.ai.llm_agent.LLMAgentNode.run",
                return_value={
                    "success": True,
                    "response": {"content": "Test response"},
                    "usage": {"total_tokens": 100},
                },
            ):
                # Execute with MCP disabled
                result = self.agent.run(
                    provider="test",
                    model="test-model",
                    messages=[{"role": "user", "content": "Search for AI trends"}],
                    mcp_servers=[],
                    max_iterations=1,
                )

                # Verify the result
                assert result["success"] is True
                assert len(result["iterations"]) == 1

                # Verify that mock execution was used
                iteration = result["iterations"][0]
                exec_results = iteration["execution_results"]

                if exec_results["steps_completed"]:
                    step_result = exec_results["steps_completed"][0]
                    assert "Mock execution result" in step_result["output"]

    @patch("kailash.mcp_server.MCPClient")
    def test_error_handling_in_mcp_execution(self, mock_mcp_client):
        """Test error handling when MCP tool execution fails."""
        # Setup mock MCP client that fails
        mock_client_instance = MagicMock()
        mock_client_instance.call_tool = AsyncMock(
            side_effect=Exception("MCP server unreachable")
        )
        mock_mcp_client.return_value = mock_client_instance

        # Mock the parent's _discover_mcp_tools method
        with patch.object(
            self.agent,
            "_discover_mcp_tools",
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "failing_tool",
                        "description": "Tool that fails",
                        "parameters": {"query": {"type": "string"}},
                        "mcp_server_config": {"url": "http://failing-server.com"},
                    },
                }
            ],
        ):
            # Mock the parent's run method
            with patch(
                "kailash.nodes.ai.llm_agent.LLMAgentNode.run",
                return_value={
                    "success": True,
                    "response": {"content": "Test response"},
                    "usage": {"total_tokens": 100},
                },
            ):
                # Execute with real MCP enabled
                result = self.agent.run(
                    provider="test",
                    model="test-model",
                    messages=[{"role": "user", "content": "Use failing tool"}],
                    mcp_servers=[{"url": "http://failing-server.com"}],
                    use_real_mcp=True,
                    max_iterations=1,
                )

                # Verify the result - should still succeed but with error handling
                assert result["success"] is True
                assert len(result["iterations"]) == 1

                # Verify that error was handled gracefully
                iteration = result["iterations"][0]
                exec_results = iteration["execution_results"]

                if exec_results["steps_completed"]:
                    step_result = exec_results["steps_completed"][0]
                    # Error should be captured but execution should continue
                    assert (
                        "failed" in step_result["output"]
                        or "Error" in step_result["output"]
                    )
