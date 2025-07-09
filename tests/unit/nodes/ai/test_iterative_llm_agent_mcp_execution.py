"""Test MCP tool execution in IterativeLLMAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode


class TestIterativeLLMAgentMCPExecution:
    """Test MCP tool execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.agent = IterativeLLMAgentNode()

    def test_use_real_mcp_parameter_exists(self):
        """Test that use_real_mcp parameter is available."""
        params = self.agent.get_parameters()
        assert "use_real_mcp" in params
        assert params["use_real_mcp"].default is True
        assert params["use_real_mcp"].type is bool

    def test_mock_execution_when_disabled(self):
        """Test that mock execution is used when use_real_mcp is False."""
        # Mock the necessary methods
        with patch.object(
            self.agent,
            "_phase_discovery",
            return_value={"new_tools": [], "new_servers": []},
        ):
            with patch.object(
                self.agent,
                "_phase_planning",
                return_value={
                    "execution_steps": [
                        {"step": 1, "action": "test", "tools": ["test_tool"]}
                    ]
                },
            ):
                with patch.object(
                    self.agent,
                    "_phase_reflection",
                    return_value={"confidence_score": 0.5},
                ):
                    with patch.object(
                        self.agent,
                        "_phase_convergence",
                        return_value={"should_stop": True, "reason": "test"},
                    ):
                        with patch.object(
                            self.agent, "_phase_synthesis", return_value="Test response"
                        ):

                            # Test with use_real_mcp=False
                            result = self.agent.run(
                                provider="test",
                                model="test-model",
                                messages=[{"role": "user", "content": "Test query"}],
                                use_real_mcp=False,
                                max_iterations=1,
                            )

                            assert result["success"] is True
                            assert len(result["iterations"]) == 1

                            # Check that execution used mock
                            iteration = result["iterations"][0]
                            assert "execution_results" in iteration
                            exec_results = iteration["execution_results"]
                            assert any(
                                "Mock execution result" in str(step.get("output", ""))
                                for step in exec_results.get("steps_completed", [])
                            )

    @patch("kailash.mcp_server.MCPClient")
    def test_real_mcp_execution_initialization(self, mock_mcp_client):
        """Test that MCP client is initialized when using real execution."""
        # Setup mock MCP client
        mock_client_instance = MagicMock()
        mock_client_instance.call_tool = AsyncMock(
            return_value={
                "success": True,
                "content": "Test tool output",
                "tool_name": "test_tool",
            }
        )
        mock_mcp_client.return_value = mock_client_instance

        # Create mock discoveries and plan
        discoveries = {
            "new_tools": [
                {"name": "test_tool", "mcp_server_config": {"url": "http://test.com"}}
            ],
            "new_servers": [],
        }

        kwargs = {
            "mcp_servers": [{"url": "http://test.com"}],
            "messages": [{"role": "user", "content": "Test query"}],
        }

        # Test the MCP tool execution method
        result = self.agent._execute_tools_with_mcp(
            1, "test_action", ["test_tool"], discoveries, kwargs
        )

        # Verify MCP client was initialized
        mock_mcp_client.assert_called_once()
        assert hasattr(self.agent, "_mcp_client")

        # Verify result structure
        assert result["success"] is True
        assert result["step"] == 1
        assert result["action"] == "test_action"
        assert result["tools_used"] == ["test_tool"]
        assert "tool_outputs" in result

    def test_build_tool_server_mapping(self):
        """Test tool to server mapping functionality."""
        discoveries = {
            "new_tools": [
                {"name": "tool1", "mcp_server_config": {"url": "http://server1.com"}},
                {
                    "function": {
                        "name": "tool2",
                        "mcp_server_config": {"url": "http://server2.com"},
                    }
                },
            ]
        }

        kwargs = {"mcp_servers": [{"url": "http://fallback.com"}]}

        mapping = self.agent._build_tool_server_mapping(discoveries, kwargs)

        assert mapping["tool1"] == {"url": "http://server1.com"}
        assert mapping["tool2"] == {"url": "http://server2.com"}

    def test_extract_tool_arguments(self):
        """Test tool argument extraction."""
        kwargs = {"messages": [{"role": "user", "content": "Analyze the sales data"}]}

        # Test different actions
        args = self.agent._extract_tool_arguments("test_tool", "gather_data", kwargs)
        assert args["query"] == "Analyze the sales data"
        assert args["action"] == "search"

        args = self.agent._extract_tool_arguments(
            "test_tool", "perform_analysis", kwargs
        )
        assert args["data"] == "Analyze the sales data"
        assert args["action"] == "analyze"

        args = self.agent._extract_tool_arguments(
            "test_tool", "generate_insights", kwargs
        )
        assert args["input"] == "Analyze the sales data"
        assert args["action"] == "generate"

    def test_async_in_sync_context(self):
        """Test async execution in sync context."""

        async def test_coro():
            return "test_result"

        result = self.agent._run_async_in_sync_context(test_coro())
        assert result == "test_result"

    @patch("kailash.mcp_server.MCPClient")
    def test_tool_execution_error_handling(self, mock_mcp_client):
        """Test error handling in tool execution."""
        # Setup mock MCP client that raises an error
        mock_client_instance = MagicMock()
        mock_client_instance.call_tool = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        mock_mcp_client.return_value = mock_client_instance

        discoveries = {
            "new_tools": [
                {"name": "test_tool", "mcp_server_config": {"url": "http://test.com"}}
            ]
        }

        kwargs = {
            "mcp_servers": [{"url": "http://test.com"}],
            "messages": [{"role": "user", "content": "Test query"}],
        }

        # Test error handling
        result = self.agent._execute_tools_with_mcp(
            1, "test_action", ["test_tool"], discoveries, kwargs
        )

        # Verify error was handled gracefully
        assert result["success"] is False
        assert "test_tool" in result["tool_outputs"]
        assert "Error: Connection failed" in result["tool_outputs"]["test_tool"]
        assert "failed" in result["output"]

    def test_no_server_config_handling(self):
        """Test handling when no server config is found for a tool."""
        discoveries = {"new_tools": []}  # No tools discovered

        kwargs = {
            "mcp_servers": [],
            "messages": [{"role": "user", "content": "Test query"}],
        }

        result = self.agent._execute_tools_with_mcp(
            1, "test_action", ["unknown_tool"], discoveries, kwargs
        )

        # Should handle gracefully with no server config
        assert result["success"] is False
        assert "No tools executed" in result["output"]
