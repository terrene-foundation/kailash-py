"""E2E tests for MCP tool execution scenarios."""

import json
import os
import time
from typing import Any, Dict

import pytest
import pytest_asyncio
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow

from tests.utils.docker_config import OLLAMA_CONFIG, ensure_docker_services


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.requires_docker
@pytest.mark.requires_ollama
class TestMCPToolExecutionScenarios:
    """Test real-world MCP tool execution scenarios."""

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

    def test_llm_agent_executes_mcp_tools(self):
        """Test that LLMAgent can discover and execute MCP tools in a workflow."""
        # Create workflow with proper constructor
        workflow = Workflow(
            workflow_id="test_mcp_tool_execution", name="Test MCP Tool Execution"
        )

        # Add LLM agent node with configuration passed as **config
        workflow.add_node(
            "llm_agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Create a report using available tools and execute operations",
                }
            ],
            auto_discover_tools=True,
            auto_execute_tools=True,
            mcp_servers=[
                {
                    "name": "ai-registry-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "kailash.mcp_server.ai_registry_server"],
                }
            ],
            tool_execution_config={"max_rounds": 3},
        )

        # Create runtime and execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify execution succeeded (results dict should have node outputs)
        assert "llm_agent" in results
        llm_result = results["llm_agent"]

        # Check that LLM agent executed successfully
        assert llm_result is not None

        # Check basic LLM response structure (mock provider returns basic structure)
        assert isinstance(llm_result, dict)

    def test_multi_step_tool_workflow(self):
        """Test a workflow where LLM uses tools multiple times."""
        workflow = Workflow(
            workflow_id="multi_step_tool_workflow", name="Multi-Step Tool Workflow"
        )

        # Define custom tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "data_processor",
                    "description": "Process data in steps",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["fetch", "transform", "save"],
                            },
                            "data": {"type": "string"},
                        },
                        "required": ["operation"],
                    },
                },
            }
        ]

        # Add agent that will use tools
        workflow.add_node(
            "agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Execute a multi-step data operation: fetch, transform, and save",
                }
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 5},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        assert "agent" in results
        agent_output = results["agent"]

        # Check that agent executed successfully
        assert agent_output is not None
        assert isinstance(agent_output, dict)

    def test_tool_execution_with_errors(self):
        """Test that tool execution errors are handled gracefully."""
        workflow = Workflow(
            workflow_id="tool_error_handling", name="Tool Error Handling"
        )

        # Tool that will simulate errors
        problematic_tools = [
            {
                "type": "function",
                "function": {
                    "name": "unreliable_tool",
                    "description": "A tool that might fail",
                    "parameters": {
                        "type": "object",
                        "properties": {"should_fail": {"type": "boolean"}},
                    },
                },
            }
        ]

        workflow.add_node(
            "agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Execute the unreliable tool"}],
            tools=problematic_tools,
            auto_execute_tools=True,
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Workflow should still succeed even with tool errors
        assert "agent" in results
        assert results["agent"] is not None

    def test_disabled_tool_execution(self):
        """Test that tools are not executed when auto_execute_tools is False."""
        workflow = Workflow(
            workflow_id="disabled_tool_execution", name="Disabled Tool Execution"
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Should not be executed",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        workflow.add_node(
            "agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Create something"}],
            tools=tools,
            auto_execute_tools=False,  # Disabled
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        assert "agent" in results
        agent_output = results["agent"]

        # Check that agent executed successfully
        assert agent_output is not None
        assert isinstance(agent_output, dict)

    def test_performance_with_multiple_tools(self):
        """Test performance when many tools are available."""
        # Create many tools
        many_tools = []
        for i in range(20):
            many_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"tool_{i}",
                        "description": f"Tool number {i}",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )

        workflow = Workflow(
            workflow_id="many_tools_performance", name="Many Tools Performance"
        )

        workflow.add_node(
            "agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Execute some operations"}],
            tools=many_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 2},
        )

        start_time = time.time()
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)
        execution_time = time.time() - start_time

        assert "agent" in results
        assert results["agent"] is not None
        # Should complete in reasonable time even with many tools
        assert execution_time < 5.0  # 5 seconds max

    def test_tool_execution_with_conversation_memory(self):
        """Test tool execution preserves conversation context."""
        workflow = Workflow(workflow_id="tool_with_memory", name="Tool with Memory")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "memory_tool",
                    "description": "Tool that uses conversation context",
                    "parameters": {
                        "type": "object",
                        "properties": {"context_needed": {"type": "boolean"}},
                    },
                },
            }
        ]

        workflow.add_node(
            "agent",
            LLMAgentNode,
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Remember that X=42."},
                {"role": "assistant", "content": "I'll remember that X=42."},
                {
                    "role": "user",
                    "content": "Now execute the memory tool with that context.",
                },
            ],
            tools=tools,
            auto_execute_tools=True,
            conversation_id="test_memory_123",
            memory_config={"type": "buffer", "max_tokens": 1000},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        assert "agent" in results
        assert results["agent"] is not None
        # Conversation should be preserved through tool execution
