"""
Integration test for IterativeLLMAgent with MCP using Docker test infrastructure.

This test demonstrates MCP tool execution with minimal Docker dependencies.
Requires only Ollama to be running for the LLM part.
"""

import os
import subprocess
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.utils.docker_config import OLLAMA_CONFIG

from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode


@pytest.mark.integration
@pytest.mark.requires_docker
class TestIterativeLLMAgentMCPDockerIntegration:
    """Integration tests for IterativeLLMAgent with Docker services."""

    def test_mcp_execution_with_mock_server(self):
        """
        Test MCP execution with a mock MCP server.
        This demonstrates the real execution path without requiring full Docker setup.
        """
        # Create agent
        agent = IterativeLLMAgentNode(name="integration_test_agent")

        # Mock the MCP client to simulate a working MCP server
        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client:
            mock_client = MagicMock()

            # Simulate tool discovery
            mock_client.discover_tools = AsyncMock(
                return_value=[
                    {
                        "name": "calculate_sum",
                        "description": "Calculate the sum of numbers",
                        "parameters": {
                            "numbers": {"type": "array", "items": {"type": "number"}}
                        },
                    },
                    {
                        "name": "get_system_info",
                        "description": "Get system information",
                        "parameters": {},
                    },
                ]
            )

            # Simulate tool execution
            mock_client.call_tool = AsyncMock(
                side_effect=[
                    {
                        "success": True,
                        "content": "Sum of [1, 2, 3, 4, 5] = 15",
                        "tool_name": "calculate_sum",
                    },
                    {
                        "success": True,
                        "content": "System: Linux, Memory: 16GB, CPU: 8 cores",
                        "tool_name": "get_system_info",
                    },
                ]
            )

            mock_mcp_client.return_value = mock_client

            # Execute with real MCP enabled
            result = agent.execute(
                provider="test",
                model="test-model",
                messages=[
                    {"role": "user", "content": "Calculate sum and get system info"}
                ],
                mcp_servers=[{"url": "http://mock-server.com"}],
                max_iterations=2,
                use_real_mcp=True,  # Enable real MCP execution
            )

            # Verify results
            assert result["success"] is True
            assert len(result.get("iterations", [])) > 0

            # Verify MCP client was used
            assert mock_client.call_tool.called
            assert mock_client.call_tool.call_count >= 1

            # Check that we got real tool results (not mock strings)
            iterations = result.get("iterations", [])
            tool_outputs = []
            for iteration in iterations:
                exec_results = iteration.get("execution_results", {})
                for step in exec_results.get("steps_completed", []):
                    if step.get("output"):
                        tool_outputs.append(step["output"])

            # Verify we got actual tool results
            assert any(
                "Sum of" in str(output) or "System:" in str(output)
                for output in tool_outputs
            )
            assert not any(
                "Mock execution result" in str(output) for output in tool_outputs
            )

            print("\n✅ Integration test passed: Real MCP execution path confirmed")

    @pytest.mark.skipif(
        not os.path.exists("/.dockerenv")
        and subprocess.run(["docker", "ps"], capture_output=True).returncode != 0,
        reason="Docker not available",
    )
    def test_mcp_with_ollama_integration(self):
        """
        Test MCP execution with Ollama integration (if available).
        This test will use real Ollama if Docker services are running.
        """
        # Check if Ollama is available
        try:
            import httpx

            response = httpx.get(f"{OLLAMA_CONFIG['base_url']}/api/tags", timeout=2.0)
            if response.status_code != 200:
                pytest.skip("Ollama service not available")
        except:
            pytest.skip("Ollama service not available")

        agent = IterativeLLMAgentNode(name="ollama_integration_agent")

        # Simple test with Ollama
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",  # Small, fast model
            messages=[{"role": "user", "content": "Hello, this is a test"}],
            max_iterations=1,
            use_real_mcp=True,
            mcp_servers=[],  # No MCP servers, just testing LLM integration
        )

        assert result["success"] is True
        assert result.get("final_response") is not None

        print("\n✅ Ollama integration test passed")

    def test_mcp_execution_comparison(self):
        """
        Compare mock vs real MCP execution to demonstrate the fix.
        """
        agent = IterativeLLMAgentNode(name="comparison_agent")

        # Test 1: With mock execution (old behavior)
        result_mock = agent.execute(
            provider="test",
            model="test-model",
            messages=[{"role": "user", "content": "Test"}],
            max_iterations=1,
            use_real_mcp=False,  # Force mock execution
        )

        # Test 2: With real execution (new behavior)
        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client:
            mock_client = MagicMock()
            mock_client.call_tool = AsyncMock(
                return_value={
                    "success": True,
                    "content": "Real MCP tool execution result",
                    "tool_name": "test_tool",
                }
            )
            mock_mcp_client.return_value = mock_client

            result_real = agent.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Test"}],
                mcp_servers=[{"url": "test"}],
                max_iterations=1,
                use_real_mcp=True,  # Force real execution
            )

        # Extract outputs
        mock_output = ""
        real_output = ""

        if result_mock.get("iterations"):
            steps = (
                result_mock["iterations"][0]
                .get("execution_results", {})
                .get("steps_completed", [])
            )
            if steps:
                mock_output = steps[0].get("output", "")

        if result_real.get("iterations"):
            steps = (
                result_real["iterations"][0]
                .get("execution_results", {})
                .get("steps_completed", [])
            )
            if steps:
                real_output = steps[0].get("output", "")

        # Verify the difference
        assert "Mock execution result" in mock_output
        assert "Real MCP tool execution result" in real_output
        assert mock_output != real_output

        print("\n✅ Comparison test passed:")
        print(f"  - Mock output: {mock_output[:50]}...")
        print(f"  - Real output: {real_output[:50]}...")

    def test_mcp_server_startup_simulation(self):
        """
        Simulate MCP server startup and tool discovery process.
        """
        # This simulates what happens when a real MCP server starts
        mcp_server_config = {
            "name": "test-mcp-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "kailash.mcp_server.test_server"],
        }

        agent = IterativeLLMAgentNode(name="server_startup_agent")

        with patch("kailash.mcp_server.MCPClient") as mock_mcp_client:
            mock_client = MagicMock()

            # Simulate server initialization
            mock_client.connect_to_server = AsyncMock()
            mock_client.initialize = AsyncMock()

            # Simulate tool discovery
            mock_client.discover_tools = AsyncMock(
                return_value=[
                    {
                        "name": "data_processor",
                        "description": "Process data with various operations",
                        "parameters": {
                            "operation": {
                                "type": "string",
                                "enum": ["sum", "mean", "max", "min"],
                            },
                            "data": {"type": "array", "items": {"type": "number"}},
                        },
                    }
                ]
            )

            # Simulate tool execution
            mock_client.call_tool = AsyncMock(
                return_value={
                    "success": True,
                    "content": "Processed data: mean = 3.5",
                    "tool_name": "data_processor",
                }
            )

            mock_mcp_client.return_value = mock_client

            # Execute with MCP server
            result = agent.execute(
                provider="test",
                model="test-model",
                messages=[{"role": "user", "content": "Process some data"}],
                mcp_servers=[mcp_server_config],
                max_iterations=1,
                use_real_mcp=True,
            )

            # Verify MCP integration is working
            assert result["success"] is True
            assert mock_client.discover_tools.called
            assert mock_client.call_tool.called

            print("\n✅ MCP server startup simulation passed")
            print("  - Tools discovered: 1")
            print(f"  - Tool executions: {mock_client.call_tool.call_count}")


if __name__ == "__main__":
    # Run integration tests
    test = TestIterativeLLMAgentMCPDockerIntegration()

    print("Running MCP Integration Tests...")
    print("=" * 60)

    test.test_mcp_execution_with_mock_server()
    test.test_mcp_execution_comparison()
    test.test_mcp_server_startup_simulation()

    # Try Ollama test if available
    try:
        test.test_mcp_with_ollama_integration()
    except pytest.skip.Exception as e:
        print(f"\n⚠️ Skipped Ollama test: {e}")

    print("\n" + "=" * 60)
    print("All integration tests completed!")
