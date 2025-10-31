"""Integration tests for IterativeLLMAgent with REAL services only (NO MOCKING)."""

import os
import time

import pytest
import requests

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
@pytest.mark.requires_docker
class TestIterativeLLMAgentRealServices:
    """Test IterativeLLMAgent with real containerized services - NO MOCKING."""

    @pytest.fixture(autouse=True)
    def check_test_infrastructure(self):
        """Ensure test infrastructure is running."""
        # Check if test-env services are available
        try:
            # Check Ollama
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code != 200:
                pytest.skip(
                    "Ollama service not running. Run: ./tests/utils/test-env up"
                )
        except:
            pytest.skip(
                "Test infrastructure not available. Run: ./tests/utils/test-env up"
            )

    def test_real_execution_with_ollama(self):
        """Test real execution using local Ollama model."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "IterativeLLMAgentNode",
            "ollama_agent",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {"role": "user", "content": "What is 2+2? Answer in one sentence."}
                ],
                "max_iterations": 1,
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Verify real execution occurred
        assert results["ollama_agent"]["success"] is True
        assert execution_time > 0.5  # Real LLM calls take time
        assert len(results["ollama_agent"]["final_response"]) > 10

    def test_real_mcp_server_integration(self):
        """Test with real MCP server from test infrastructure."""
        # Check if test MCP server is available
        try:
            response = requests.get("http://localhost:8090/health", timeout=2)
            if response.status_code != 200:
                pytest.skip("Test MCP server not running")
        except:
            pytest.skip("Test MCP server not available")

        workflow = WorkflowBuilder()

        workflow.add_node(
            "IterativeLLMAgentNode",
            "mcp_agent",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {
                        "role": "user",
                        "content": "List available tools from the MCP server",
                    }
                ],
                "mcp_servers": [
                    {"url": "http://localhost:8090", "name": "test_mcp_server"}
                ],
                "max_iterations": 2,
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Should discover real tools from MCP server
        assert results["mcp_agent"]["success"] is True
        assert "discoveries" in results["mcp_agent"]
        # Tool discovery depends on what the real server provides

    def test_network_resilience_with_real_services(self):
        """Test behavior with intermittent real service issues."""
        workflow = WorkflowBuilder()

        # Use a non-existent MCP server to test fallback
        workflow.add_node(
            "IterativeLLMAgentNode",
            "resilient_agent",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {"role": "user", "content": "Analyze data even if tools fail"}
                ],
                "mcp_servers": [
                    {
                        "url": "http://localhost:9999",  # Non-existent
                        "name": "unavailable_server",
                    }
                ],
                "max_iterations": 2,
                "discovery_budget": {"max_servers": 1, "max_tools": 5},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Should succeed with LLM fallback despite MCP failure
        assert results["resilient_agent"]["success"] is True
        assert len(results["resilient_agent"]["final_response"]) > 20

    def test_multi_iteration_convergence_real(self):
        """Test real convergence behavior over multiple iterations."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "IterativeLLMAgentNode",
            "convergence_agent",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {"role": "user", "content": "Write a haiku about testing"}
                ],
                "max_iterations": 3,
                "convergence_criteria": {
                    "goal_satisfaction": {"threshold": 0.8},
                    "early_satisfaction": {"enabled": True, "threshold": 0.85},
                },
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        total_time = time.time() - start_time

        # Verify real iterative execution
        assert results["convergence_agent"]["success"] is True
        iterations = results["convergence_agent"]["iterations"]
        assert len(iterations) >= 1  # At least one iteration
        assert total_time > 1.0  # Real execution takes time

        # Check convergence occurred
        assert "convergence_reason" in results["convergence_agent"]

    @pytest.mark.slow
    def test_performance_with_real_workload(self):
        """Test performance characteristics with real LLM workload."""
        workflow = WorkflowBuilder()

        # Create a more complex query requiring analysis
        workflow.add_node(
            "IterativeLLMAgentNode",
            "performance_agent",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze the pros and cons of iterative AI processing",
                    }
                ],
                "max_iterations": 2,
                "discovery_budget": {"max_tools": 10},
                "iteration_timeout": 30,
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Verify performance bounds
        assert results["performance_agent"]["success"] is True
        assert execution_time < 60  # Should complete within timeout
        assert execution_time > 2  # Real processing takes time

        # Check resource usage tracking
        resource_usage = results["performance_agent"]["resource_usage"]
        assert resource_usage["total_iterations"] <= 2
        assert resource_usage["total_duration_seconds"] > 0

    def test_real_mcp_tool_execution(self):
        """Test actual MCP tool execution if available."""
        # This test requires a real MCP server with actual tools
        # Skip if not available in test environment
        try:
            # Try to check for MCP server with tools
            response = requests.get("http://localhost:8090/tools", timeout=2)
            if response.status_code != 200 or not response.json():
                pytest.skip("No MCP tools available for testing")
        except:
            pytest.skip("MCP tool server not available")

        workflow = WorkflowBuilder()

        workflow.add_node(
            "IterativeLLMAgentNode",
            "tool_executor",
            {
                "provider": "ollama",
                "model": "llama2",
                "base_url": "http://localhost:11434",
                "messages": [
                    {
                        "role": "user",
                        "content": "Use available tools to get system information",
                    }
                ],
                "mcp_servers": [
                    {"url": "http://localhost:8090", "name": "tool_server"}
                ],
                "max_iterations": 2,
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify tool execution
        assert results["tool_executor"]["success"] is True

        # Check if tools were actually used
        tool_outputs = {}
        for iteration in results["tool_executor"]["iterations"]:
            if "execution_results" in iteration:
                tool_outputs.update(
                    iteration["execution_results"].get("tool_outputs", {})
                )

        # If tools were available, they should have been executed
        if results["tool_executor"]["discoveries"]["tools"]:
            assert len(tool_outputs) > 0  # Some tools should have been used
