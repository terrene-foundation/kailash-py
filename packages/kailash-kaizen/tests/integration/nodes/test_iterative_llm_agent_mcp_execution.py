"""Test MCP tool execution in IterativeLLMAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode


class TestIterativeLLMAgentMCPExecution:
    """Test MCP tool execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.agent = IterativeLLMAgentNode()

    def test_no_mock_parameters_exist(self):
        """Test that mock-related parameters have been removed."""
        params = self.agent.get_parameters()
        assert "use_real_mcp" not in params
        assert "mock_mode" not in params

    def test_real_execution_functionality(self):
        """Test that the node executes with real LLM fallback when no MCP tools."""
        # Test basic functionality - the node should work with real LLM fallback
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
                        {"step": 1, "action": "direct_llm_response", "tools": []}
                    ],
                    "planning_mode": "direct_llm",
                },
            ):
                with patch.object(
                    self.agent,
                    "_phase_reflection",
                    return_value={"confidence_score": 0.8},
                ):
                    with patch.object(
                        self.agent,
                        "_phase_convergence",
                        return_value={"should_stop": True, "reason": "goal_achieved"},
                    ):
                        with patch.object(
                            self.agent,
                            "_calculate_resource_usage",
                            return_value={"total_api_calls": 1},
                        ):
                            # Mock the parent LLM call
                            with patch(
                                "kailash.nodes.ai.llm_agent.LLMAgentNode.run"
                            ) as mock_llm:
                                mock_llm.return_value = {
                                    "success": True,
                                    "response": {"content": "Test response from LLM"},
                                }

                                # Test execution - simplified API
                                result = self.agent.run(
                                    provider="openai",
                                    model="gpt-3.5-turbo",
                                    api_key="test-key",
                                    messages=[
                                        {"role": "user", "content": "Test query"}
                                    ],
                                    max_iterations=1,
                                )

                                # Verify real execution occurred
                                assert result["success"] is True
                                assert "iterations" in result
                                assert len(result["iterations"]) == 1

                                # Verify LLM was called for direct response
                                mock_llm.assert_called()

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

    def test_execution_with_tools_available(self):
        """Test execution path when MCP tools are available."""
        # Mock tool discovery and execution
        with patch.object(
            self.agent,
            "_execute_tools_with_mcp",
            return_value={
                "step": 1,
                "action": "test_action",
                "tools_used": ["test_tool"],
                "output": "Real tool execution result",
                "success": True,
                "duration": 2.5,
            },
        ):
            # Test planning with tools
            plan = {
                "execution_steps": [
                    {"step": 1, "action": "test_action", "tools": ["test_tool"]}
                ]
            }
            discoveries = {"new_tools": [{"name": "test_tool"}]}

            # Execute the execution phase
            result = self.agent._phase_execution({}, plan, discoveries)

            # Verify real tool execution was called
            assert result["success"] is True
            assert len(result["steps_completed"]) == 1
            assert (
                "Real tool execution result" in result["steps_completed"][0]["output"]
            )

    def test_execution_without_tools_fallback(self):
        """Test execution falls back to LLM when no tools available."""
        with patch("kailash.nodes.ai.llm_agent.LLMAgentNode.run") as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "response": {"content": "LLM fallback response"},
            }

            # Test planning without tools (direct LLM mode)
            plan = {
                "execution_steps": [
                    {"step": 1, "action": "direct_llm_response", "tools": []}
                ],
                "planning_mode": "direct_llm",
            }
            discoveries = {"new_tools": []}

            # Execute the execution phase
            result = self.agent._phase_execution(
                {"provider": "openai", "model": "gpt-3.5-turbo"}, plan, discoveries
            )

            # Verify LLM fallback was used
            assert result["success"] is True
            assert mock_llm.called
            assert "LLM fallback response" in result["tool_outputs"]["llm_response"]
