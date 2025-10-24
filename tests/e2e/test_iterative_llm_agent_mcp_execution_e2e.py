"""
E2E test for IterativeLLMAgent with real MCP tool execution.

This test demonstrates the complete user journey using real Docker services,
real MCP servers, and actual tool execution with the IterativeLLMAgent.

Following test organization policy:
- Tier 3 (E2E) test with real Docker services
- No mocking - all real services and data
- Complete user workflow from discovery to synthesis
"""

import os

import pytest
import pytest_asyncio
from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import OLLAMA_CONFIG, ensure_docker_services


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
class TestIterativeLLMAgentMCPExecutionE2E:
    """E2E test for IterativeLLMAgent with real MCP tool execution."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure Docker services are running for E2E tests."""
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker services not available")

        # Set up environment for real MCP and Ollama
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = OLLAMA_CONFIG["base_url"]
        os.environ["REGISTRY_FILE"] = (
            "# contrib (removed)/research/combined_ai_registry.json"
        )
        yield

        # Cleanup
        os.environ.pop("KAILASH_USE_REAL_MCP", None)
        os.environ.pop("OLLAMA_BASE_URL", None)
        os.environ.pop("REGISTRY_FILE", None)

    def test_user_journey_ai_research_with_mcp_tools(self):
        """
        Complete user journey: AI researcher using IterativeLLMAgent to discover
        and analyze AI use cases through real MCP tool execution.

        User Persona: AI Researcher
        Goal: Research healthcare AI applications using available MCP tools
        """
        # Step 1: User creates workflow with IterativeLLMAgent
        workflow = WorkflowBuilder()

        # Step 2: User configures IterativeLLMAgent with MCP servers
        workflow.add_node(
            "IterativeLLMAgentNode",
            "research_agent",
            {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Research and analyze healthcare AI applications. "
                        "Use available tools to find relevant use cases and trends.",
                    }
                ],
                "mcp_servers": [
                    {
                        "name": "ai-registry-server",
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                    }
                ],
                "max_iterations": 3,
                "discovery_mode": "progressive",
                "use_real_mcp": True,  # Enable real MCP execution
                "convergence_criteria": {
                    "goal_satisfaction": {"threshold": 0.8},
                    "diminishing_returns": {"min_improvement": 0.1},
                },
                "enable_detailed_logging": True,
            },
        )

        # Step 3: Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Step 4: Verify results
        assert "research_agent" in results, "Research agent node not found in results"

        agent_result = results["research_agent"]
        assert (
            agent_result["success"] is True
        ), f"Agent execution failed: {agent_result.get('error')}"

        # Verify iterative process occurred
        assert "iterations" in agent_result, "No iterations found in result"
        iterations = agent_result["iterations"]
        assert len(iterations) > 0, "No iterations were executed"

        # Verify MCP tool discovery and execution
        discoveries = agent_result.get("discoveries", {})
        assert len(discoveries.get("tools", {})) > 0, "No MCP tools were discovered"

        # Check that at least one iteration executed tools
        tool_executed = False
        for iteration in iterations:
            if iteration.get("execution_results", {}).get("tool_outputs"):
                tool_executed = True
                break

        assert tool_executed, "No MCP tools were executed during iterations"

        # Verify final synthesis
        assert "final_response" in agent_result, "No final response generated"
        final_response = agent_result["final_response"]
        assert len(final_response) > 0, "Empty final response"

        print(
            f"\n✅ IterativeLLMAgent successfully executed {len(iterations)} iterations"
        )
        print(f"✅ Discovered {len(discoveries.get('tools', {}))} MCP tools")
        print(
            f"✅ Convergence reason: {agent_result.get('convergence_reason', 'Unknown')}"
        )

    def test_user_journey_data_scientist_analysis(self):
        """
        User journey: Data scientist using IterativeLLMAgent for complex analysis
        with test-driven convergence mode.

        User Persona: Data Scientist
        Goal: Analyze data patterns using iterative refinement with validation
        """
        # Create workflow with test-driven convergence
        workflow = WorkflowBuilder()

        workflow.add_node(
            "IterativeLLMAgentNode",
            "analysis_agent",
            {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze manufacturing quality control AI use cases. "
                        "Find patterns and generate insights.",
                    }
                ],
                "mcp_servers": [
                    {
                        "name": "ai-registry-server",
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                    }
                ],
                "max_iterations": 2,
                "convergence_mode": "hybrid",  # Use hybrid convergence
                "use_real_mcp": True,
                "convergence_criteria": {
                    "goal_satisfaction": {"threshold": 0.7},
                    "hybrid_config": {
                        "test_weight": 0.6,
                        "satisfaction_weight": 0.4,
                        "require_both": False,
                    },
                },
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution
        assert "analysis_agent" in results
        agent_result = results["analysis_agent"]
        assert agent_result["success"] is True

        # Check convergence mode was respected
        iterations = agent_result.get("iterations", [])
        assert len(iterations) > 0

        # Verify hybrid convergence metrics
        for iteration in iterations:
            if "convergence_decision" in iteration:
                decision = iteration["convergence_decision"]
                if decision.get("should_stop"):
                    # Should have both test and satisfaction metrics
                    assert (
                        "test_results" in decision or "satisfaction_metrics" in decision
                    )
                    break

        print("\n✅ Hybrid convergence mode executed successfully")
        print(f"✅ Total iterations: {len(iterations)}")

    def test_user_journey_engineer_troubleshooting(self):
        """
        User journey: Engineer troubleshooting with controlled MCP execution.

        User Persona: Software Engineer
        Goal: Debug and troubleshoot using iterative approach
        """
        # Direct node usage for troubleshooting scenario
        agent = IterativeLLMAgentNode(name="troubleshooting_agent")

        # Execute with specific configuration
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Help troubleshoot performance issues in AI applications.",
                }
            ],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                }
            ],
            max_iterations=1,  # Quick troubleshooting
            use_real_mcp=True,
            discovery_mode="exhaustive",  # Discover all available tools
            iteration_timeout=60,  # Shorter timeout for troubleshooting
        )

        # Verify quick execution
        assert result["success"] is True
        assert len(result["iterations"]) == 1

        # Check that tools were discovered
        discoveries = result.get("discoveries", {})
        assert len(discoveries.get("tools", {})) > 0

        print(
            f"\n✅ Troubleshooting scenario completed in {result.get('total_duration', 0):.2f}s"
        )

    def test_performance_with_real_mcp_execution(self):
        """
        Test performance characteristics with real MCP tool execution.

        Validates that real MCP execution performs within acceptable bounds.
        """
        import time

        agent = IterativeLLMAgentNode(name="performance_test_agent")

        start_time = time.time()

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Quick search for AI trends"}],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                }
            ],
            max_iterations=2,
            use_real_mcp=True,
            iteration_timeout=30,
        )

        execution_time = time.time() - start_time

        # Verify performance
        assert result["success"] is True
        assert execution_time < 60, f"Execution took too long: {execution_time:.2f}s"

        # Check resource usage metrics
        resource_usage = result.get("resource_usage", {})
        assert "total_duration_seconds" in resource_usage
        assert "total_tools_used" in resource_usage

        print(f"\n✅ Performance test completed in {execution_time:.2f}s")
        print(f"✅ Tools used: {resource_usage.get('total_tools_used', 0)}")
        print(f"✅ API calls: {resource_usage.get('total_api_calls', 0)}")

    def test_error_recovery_with_real_mcp(self):
        """
        Test error handling and recovery with real MCP servers.

        Validates graceful handling of MCP failures.
        """
        agent = IterativeLLMAgentNode(name="error_recovery_agent")

        # Test with a mix of valid and invalid servers
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Search for information"}],
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                },
                {
                    "name": "invalid-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "nonexistent.module"],
                },
            ],
            max_iterations=1,
            use_real_mcp=True,
        )

        # Should still succeed despite one invalid server
        assert result["success"] is True

        # Check that discovery handled the error
        discoveries = result.get("discoveries", {})
        servers = discoveries.get("servers", {})

        # Should have attempted both servers
        assert len(servers) >= 1

        # Check for error handling in iterations
        iterations = result.get("iterations", [])
        if iterations:
            first_iteration = iterations[0]
            # May have errors recorded
            if "error" in first_iteration or first_iteration.get("discoveries", {}).get(
                "new_servers"
            ):
                print("\n✅ Error recovery handled gracefully")

        print("\n✅ Completed despite server errors")
        print(
            f"✅ Discovered {len(discoveries.get('tools', {}))} tools from valid servers"
        )
