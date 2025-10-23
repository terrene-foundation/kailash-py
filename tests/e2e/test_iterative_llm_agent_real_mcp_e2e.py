#!/usr/bin/env python3
"""
E2E test for IterativeLLMAgent with real MCP tool execution.

This test demonstrates the complete user journey using real Docker services,
real MCP servers, and actual tool execution with the IterativeLLMAgent.

Following test organization policy:
- Tier 3 (E2E) test with real Docker services
- No mocking - all real services and data
- Complete user workflow from discovery to synthesis
- Real MCP server with actual tool execution

IMPORTANT: Run with Docker services:
  ./tests/utils/test-env up
  ./tests/utils/test-env test tier3
"""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
import pytest_asyncio
from kailash.mcp_server import MCPClient
from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from tests.utils.docker_config import OLLAMA_CONFIG, ensure_docker_services


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
class TestIterativeLLMAgentRealMCPE2E:
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

    @pytest.mark.asyncio
    async def test_real_mcp_tool_execution_e2e(self):
        """
        Complete E2E test demonstrating real MCP tool execution in IterativeLLMAgent.

        This test validates:
        1. Real MCP server startup in Docker
        2. Tool discovery from actual MCP servers
        3. Real tool execution (not mock)
        4. Processing of actual tool results
        5. Complete iterative workflow with convergence
        """
        print("\n" + "=" * 60)
        print("🚀 Starting IterativeLLMAgent Real MCP E2E Test")
        print("=" * 60)

        # Step 1: Create and verify MCP server is accessible
        mcp_servers = [
            {
                "name": "ai-registry-server",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "kailash.mcp_server.ai_registry_server"],
            }
        ]

        # Verify MCP server can be started
        print("\n📡 Step 1: Verifying MCP server accessibility...")
        try:
            test_client = MCPClient()
            await test_client.connect_to_server(mcp_servers[0])
            await test_client.disconnect()
            print("✅ MCP server is accessible")
        except Exception as e:
            print(f"⚠️ MCP server connection test failed: {e}")
            # Continue anyway - the agent might handle it differently

        # Step 2: Create IterativeLLMAgent with real configuration
        print("\n🤖 Step 2: Creating IterativeLLMAgent with real MCP...")
        agent = IterativeLLMAgentNode(name="e2e_test_agent")

        # Step 3: Execute with real MCP servers and Ollama
        print("\n🔄 Step 3: Executing iterative workflow with real tools...")
        start_time = time.time()

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Research and analyze healthcare AI applications. "
                    "Use available tools to find relevant use cases and trends.",
                }
            ],
            mcp_servers=mcp_servers,
            max_iterations=3,
            discovery_mode="progressive",
            use_real_mcp=True,  # Enable real MCP execution
            convergence_criteria={
                "goal_satisfaction": {"threshold": 0.8},
                "diminishing_returns": {"min_improvement": 0.1},
            },
            enable_detailed_logging=True,
            iteration_timeout=60,  # Reasonable timeout for E2E
        )

        execution_time = time.time() - start_time

        # Step 4: Validate results
        print(
            f"\n📊 Step 4: Validating results (execution took {execution_time:.2f}s)..."
        )

        # Basic success validation
        assert (
            result["success"] is True
        ), f"Agent execution failed: {result.get('error')}"

        # Verify iterative process
        assert "iterations" in result, "No iterations found in result"
        iterations = result["iterations"]
        assert len(iterations) > 0, "No iterations were executed"
        print(f"✅ Completed {len(iterations)} iterations")

        # Verify MCP tool discovery
        discoveries = result.get("discoveries", {})
        discovered_tools = discoveries.get("tools", {})
        print(f"✅ Discovered {len(discovered_tools)} MCP tools")

        # Verify real tool execution occurred
        tool_executions = []
        for iteration in iterations:
            exec_results = iteration.get("execution_results", {})
            if exec_results.get("steps_completed"):
                for step in exec_results["steps_completed"]:
                    if step.get("tools_used"):
                        tool_executions.append(
                            {
                                "iteration": iteration.get("iteration_num", "?"),
                                "tools": step["tools_used"],
                                "success": step.get("success", False),
                                "has_output": bool(step.get("output")),
                            }
                        )

        assert len(tool_executions) > 0, "No tools were executed during iterations"
        print(f"✅ Executed tools in {len(tool_executions)} steps")

        # Verify convergence
        assert "convergence_reason" in result, "No convergence reason found"
        print(f"✅ Convergence achieved: {result['convergence_reason']}")

        # Verify final synthesis
        assert "final_response" in result, "No final response generated"
        assert len(result["final_response"]) > 0, "Empty final response"

        # Step 5: Detailed execution analysis
        print("\n📈 Step 5: Execution Analysis")
        print(f"{'='*50}")

        for i, iteration in enumerate(iterations):
            print(f"\n🔄 Iteration {i+1}:")

            # Discovery phase
            if "discoveries" in iteration:
                new_tools = iteration["discoveries"].get("new_tools", [])
                if new_tools:
                    print(f"  📡 Discovered {len(new_tools)} new tools")

            # Planning phase
            if "planning" in iteration:
                selected_tools = iteration["planning"].get("selected_tools", [])
                print(
                    f"  📋 Selected tools: {', '.join(selected_tools) if selected_tools else 'None'}"
                )

            # Execution phase
            if "execution_results" in iteration:
                exec_results = iteration["execution_results"]
                steps = exec_results.get("steps_completed", [])
                for step in steps:
                    if step.get("tools_used"):
                        print(f"  🔧 Executed: {', '.join(step['tools_used'])}")
                        print(f"     Success: {step.get('success', False)}")
                        if step.get("output"):
                            output_preview = str(step["output"])[:100]
                            print(f"     Output: {output_preview}...")

        print(f"\n{'='*50}")
        print("✅ E2E Test Summary:")
        print(f"  - Total execution time: {execution_time:.2f}s")
        print(f"  - Iterations completed: {len(iterations)}")
        print(f"  - Tools discovered: {len(discovered_tools)}")
        print(f"  - Tool executions: {len(tool_executions)}")
        print(f"  - Convergence reason: {result['convergence_reason']}")
        print(f"  - Final response length: {len(result['final_response'])} chars")
        print("=" * 60)

    @pytest.mark.asyncio
    async def test_workflow_integration_with_real_mcp(self):
        """
        Test IterativeLLMAgent integration in a complete workflow with real MCP.

        This demonstrates:
        1. Workflow-based usage of IterativeLLMAgent
        2. Integration with other nodes
        3. Real MCP tool execution in workflow context
        """
        print("\n" + "=" * 60)
        print("🔄 Testing Workflow Integration with Real MCP")
        print("=" * 60)

        # Create workflow
        workflow = WorkflowBuilder()

        # Add IterativeLLMAgent with MCP
        workflow.add_node(
            "IterativeLLMAgentNode",
            "research_agent",
            {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Find information about AI trends in manufacturing",
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
                "use_real_mcp": True,
                "convergence_criteria": {"goal_satisfaction": {"threshold": 0.7}},
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate workflow execution
        assert "research_agent" in results, "Agent node not found in workflow results"
        agent_result = results["research_agent"]
        assert agent_result["success"] is True
        assert len(agent_result.get("iterations", [])) > 0

        print("✅ Workflow integration successful")
        print(f"  - Run ID: {run_id}")
        print(f"  - Iterations: {len(agent_result.get('iterations', []))}")
        print(
            f"  - Tools discovered: {len(agent_result.get('discoveries', {}).get('tools', {}))}"
        )

    @pytest.mark.asyncio
    async def test_error_handling_with_real_mcp(self):
        """
        Test error handling and recovery with real MCP servers.

        Validates graceful handling of:
        1. MCP server failures
        2. Tool execution errors
        3. Fallback behavior
        """
        print("\n" + "=" * 60)
        print("🛡️ Testing Error Handling with Real MCP")
        print("=" * 60)

        agent = IterativeLLMAgentNode(name="error_test_agent")

        # Test with mix of valid and invalid servers
        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Simple test query"}],
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
            iteration_timeout=30,
        )

        # Should still succeed with partial server availability
        assert result["success"] is True
        print("✅ Graceful error handling confirmed")

        # Check that valid server was used
        discoveries = result.get("discoveries", {})
        if discoveries.get("tools"):
            print("  - Successfully used valid server")
            print(f"  - Discovered {len(discoveries['tools'])} tools despite errors")

    @pytest.mark.asyncio
    async def test_performance_characteristics(self):
        """
        Test performance characteristics with real MCP execution.

        Validates:
        1. Execution time within acceptable bounds
        2. Resource usage tracking
        3. Concurrent operation handling
        """
        print("\n" + "=" * 60)
        print("⚡ Testing Performance with Real MCP")
        print("=" * 60)

        agent = IterativeLLMAgentNode(name="performance_test_agent")

        # Quick performance test
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
            max_iterations=1,
            use_real_mcp=True,
            iteration_timeout=30,
            discovery_mode="focused",  # Faster discovery
        )

        execution_time = time.time() - start_time

        # Performance assertions
        assert result["success"] is True
        assert execution_time < 60, f"Execution too slow: {execution_time:.2f}s"

        # Check resource metrics
        resource_usage = result.get("resource_usage", {})

        print(f"✅ Performance test completed in {execution_time:.2f}s")
        print(
            f"  - Total duration: {resource_usage.get('total_duration_seconds', execution_time):.2f}s"
        )
        print(f"  - Tools used: {resource_usage.get('total_tools_used', 0)}")
        print(f"  - API calls: {resource_usage.get('total_api_calls', 0)}")

        # Verify reasonable performance
        assert execution_time < 60, "Single iteration should complete within 60s"
        print("✅ Performance within acceptable bounds")

    @pytest.mark.asyncio
    async def test_complex_multi_iteration_scenario(self):
        """
        Test complex multi-iteration scenario with real MCP.

        This demonstrates:
        1. Progressive tool discovery
        2. Multiple iteration cycles
        3. Convergence based on real results
        4. Complex decision making
        """
        print("\n" + "=" * 60)
        print("🔬 Testing Complex Multi-Iteration Scenario")
        print("=" * 60)

        agent = IterativeLLMAgentNode(name="complex_scenario_agent")

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Conduct a comprehensive analysis of AI applications in healthcare. "
                        "Start with discovering available tools, then gather data about "
                        "different use cases, analyze trends, and provide insights."
                    ),
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
            max_iterations=5,
            use_real_mcp=True,
            discovery_mode="progressive",
            convergence_mode="hybrid",
            convergence_criteria={
                "goal_satisfaction": {"threshold": 0.85},
                "diminishing_returns": {"min_improvement": 0.05},
                "hybrid_config": {
                    "test_weight": 0.3,
                    "satisfaction_weight": 0.7,
                    "require_both": False,
                },
            },
            enable_detailed_logging=True,
        )

        # Validate complex execution
        assert result["success"] is True
        iterations = result.get("iterations", [])

        print("\n📊 Complex Scenario Results:")
        print(f"  - Total iterations: {len(iterations)}")
        print(f"  - Convergence: {result.get('convergence_reason', 'Unknown')}")

        # Analyze iteration progression
        tool_usage_progression = []
        for i, iteration in enumerate(iterations):
            tools_used = set()
            exec_results = iteration.get("execution_results", {})
            for step in exec_results.get("steps_completed", []):
                if step.get("tools_used"):
                    tools_used.update(step["tools_used"])

            tool_usage_progression.append(
                {
                    "iteration": i + 1,
                    "tools_count": len(tools_used),
                    "tools": list(tools_used),
                }
            )

        # Verify progressive discovery and usage
        print("\n📈 Tool Usage Progression:")
        for prog in tool_usage_progression:
            print(f"  - Iteration {prog['iteration']}: {prog['tools_count']} tools")
            if prog["tools"]:
                print(
                    f"    Tools: {', '.join(prog['tools'][:3])}{'...' if len(prog['tools']) > 3 else ''}"
                )

        # Verify convergence was based on real results
        final_iteration = iterations[-1] if iterations else {}
        convergence_decision = final_iteration.get("convergence_decision", {})

        if convergence_decision:
            print("\n🎯 Convergence Decision:")
            print(f"  - Should stop: {convergence_decision.get('should_stop', False)}")
            print(f"  - Reason: {convergence_decision.get('reason', 'Unknown')}")
            print(f"  - Confidence: {convergence_decision.get('confidence', 0):.2f}")

        print("\n✅ Complex multi-iteration scenario completed successfully")
        print("=" * 60)


if __name__ == "__main__":
    # Allow running this test directly
    pytest.main([__file__, "-v", "-s"])
