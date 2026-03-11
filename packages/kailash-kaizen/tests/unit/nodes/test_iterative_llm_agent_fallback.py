"""Test fallback scenarios for IterativeLLMAgent without mock mode."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode


class TestIterativeLLMAgentFallback:
    """Test graceful degradation and fallback scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.agent = IterativeLLMAgentNode()

    def test_fallback_to_llm_when_no_mcp_servers(self):
        """Test that node falls back to LLM when no MCP servers configured."""
        with patch("kaizen.nodes.ai.llm_agent.LLMAgentNode.run") as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "response": {"content": "Direct LLM response without tools"},
            }

            # Execute without MCP servers
            result = self.agent.execute(
                provider="openai",
                model="gpt-3.5-turbo",
                api_key="test-key",
                messages=[{"role": "user", "content": "Analyze data"}],
                max_iterations=1,
                # No mcp_servers parameter
            )

            # Should use LLM fallback
            assert result["success"] is True
            mock_llm.assert_called()

    def test_fallback_when_mcp_discovery_fails(self):
        """Test graceful fallback when MCP discovery fails."""
        with patch.object(
            self.agent,
            "_discover_server_tools",
            side_effect=Exception("Connection failed"),
        ):
            with patch("kaizen.nodes.ai.llm_agent.LLMAgentNode.run") as mock_llm:
                mock_llm.return_value = {
                    "success": True,
                    "response": {"content": "LLM response after discovery failure"},
                }

                result = self.agent.execute(
                    provider="openai",
                    model="gpt-3.5-turbo",
                    api_key="test-key",
                    messages=[{"role": "user", "content": "Test query"}],
                    mcp_servers=[{"url": "http://failing-server:8080"}],
                    max_iterations=1,
                )

                # Should still succeed with LLM fallback
                assert result["success"] is True

    def test_partial_mcp_failure_continues_execution(self):
        """Test that partial MCP failures don't stop execution."""
        # Mock one tool succeeding, one failing
        with patch.object(self.agent, "_execute_tools_with_mcp") as mock_exec:
            mock_exec.return_value = {
                "step": 1,
                "action": "multi_tool_action",
                "tools_used": ["tool1", "tool2"],
                "output": "Tool 1: Success\nTool 2: Failed but continued",
                "success": True,
                "tool_outputs": {
                    "tool1": "Success data",
                    "tool2": "Error: Connection timeout",
                },
            }

            # Test execution with mixed results
            plan = {
                "execution_steps": [
                    {
                        "step": 1,
                        "action": "multi_tool_action",
                        "tools": ["tool1", "tool2"],
                    }
                ]
            }
            discoveries = {"new_tools": [{"name": "tool1"}, {"name": "tool2"}]}

            result = self.agent._phase_execution({}, plan, discoveries)

            # Should complete with partial success
            assert result["success"] is True
            assert "tool1" in result["tool_outputs"]
            assert "tool2" in result["tool_outputs"]

    @patch("kailash.mcp_server.MCPClient")
    def test_mcp_timeout_fallback(self, mock_mcp_client):
        """Test handling of MCP timeouts with fallback."""
        # Setup mock that times out
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(
            side_effect=TimeoutError("MCP call timed out")
        )
        mock_mcp_client.return_value = mock_client

        # Mock LLM fallback
        with patch("kaizen.nodes.ai.llm_agent.LLMAgentNode.run") as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "response": {"content": "LLM handled after timeout"},
            }

            # Execute with timeout scenario
            discoveries = {
                "new_tools": [
                    {"name": "slow_tool", "mcp_server_config": {"url": "http://test"}}
                ]
            }
            kwargs = {"messages": [{"role": "user", "content": "Test"}]}

            result = self.agent._execute_tools_with_mcp(
                1, "test_action", ["slow_tool"], discoveries, kwargs
            )

            # Should handle timeout gracefully
            assert (
                "error" in result["output"].lower()
                or "failed" in result["output"].lower()
            )

    def test_convergence_without_tools(self):
        """Test that convergence works when no tools are available."""
        with patch.object(
            self.agent, "_phase_discovery", return_value={"new_tools": []}
        ):
            with patch("kaizen.nodes.ai.llm_agent.LLMAgentNode.run") as mock_llm:
                # Mock improving responses over iterations
                mock_llm.side_effect = [
                    {"success": True, "response": {"content": "Initial analysis"}},
                    {
                        "success": True,
                        "response": {"content": "Refined analysis with more detail"},
                    },
                    {
                        "success": True,
                        "response": {"content": "Final comprehensive analysis"},
                    },
                ]

                result = self.agent.execute(
                    provider="openai",
                    model="gpt-4",
                    api_key="test-key",
                    messages=[{"role": "user", "content": "Analyze market trends"}],
                    max_iterations=3,
                    convergence_criteria={"goal_satisfaction": {"threshold": 0.8}},
                )

                # Should iterate and converge
                assert result["success"] is True
                assert result["total_iterations"] >= 1
                assert "convergence_reason" in result
