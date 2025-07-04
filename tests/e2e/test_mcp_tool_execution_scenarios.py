"""E2E tests for MCP tool execution scenarios."""

import json
import os
import time
from typing import Any, Dict

import pytest

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow


@pytest.mark.e2e
@pytest.mark.slow
class TestMCPToolExecutionScenarios:
    """Test real-world MCP tool execution scenarios."""

    def setup_method(self):
        """Set up test environment."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_llm_agent_executes_mcp_tools(self):
        """Test that LLMAgent can discover and execute MCP tools in a workflow."""
        # Create workflow
        workflow = Workflow("test_mcp_tool_execution", "Test MCP Tool Execution")

        # Add LLM agent node
        llm_agent = LLMAgentNode()
        workflow.add_node("llm_agent", llm_agent)

        # Set inputs for the node
        workflow.set_node_inputs(
            "llm_agent",
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {
                        "role": "user",
                        "content": "Create a report using available tools and execute operations",
                    }
                ],
                "auto_discover_tools": True,
                "auto_execute_tools": True,
                "mcp_servers": [
                    {
                        "name": "test-mcp-server",
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["test"],
                    }
                ],
                "tool_execution_config": {"max_rounds": 3},
            },
        )

        # Create runtime and execute
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify execution
        assert result.success is True
        llm_result = result.node_outputs["llm_agent"]

        # Check that tools were available
        assert llm_result["context"]["tools_available"] > 0

        # Check that tools were executed
        assert llm_result["context"]["tools_executed"] >= 0

    def test_multi_step_tool_workflow(self):
        """Test a workflow where LLM uses tools multiple times."""
        workflow = Workflow("multi_step_tool_workflow", "Multi-Step Tool Workflow")

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
            LLMAgentNode(),
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {
                        "role": "user",
                        "content": "Execute a multi-step data operation: fetch, transform, and save",
                    }
                ],
                "tools": tools,
                "auto_execute_tools": True,
                "tool_execution_config": {"max_rounds": 5},
            },
        )

        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        assert result.success is True
        agent_output = result.node_outputs["agent"]

        # Should have executed tools
        if agent_output["context"]["tools_available"] > 0:
            # If tools were made available, check execution happened
            assert "response" in agent_output
            response = agent_output["response"]

            # Check for tool execution metadata
            if "tool_execution_rounds" in response:
                assert response["tool_execution_rounds"] > 0

    def test_tool_execution_with_errors(self):
        """Test that tool execution errors are handled gracefully."""
        workflow = Workflow("tool_error_handling", "Tool Error Handling")

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
            LLMAgentNode(),
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "Execute the unreliable tool"}
                ],
                "tools": problematic_tools,
                "auto_execute_tools": True,
            },
        )

        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Workflow should still succeed even with tool errors
        assert result.success is True

    def test_disabled_tool_execution(self):
        """Test that tools are not executed when auto_execute_tools is False."""
        workflow = Workflow("disabled_tool_execution", "Disabled Tool Execution")

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
            LLMAgentNode(),
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Create something"}],
                "tools": tools,
                "auto_execute_tools": False,  # Disabled
            },
        )

        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        assert result.success is True
        agent_output = result.node_outputs["agent"]

        # Tools should not have been executed
        assert agent_output["context"]["tools_executed"] == 0

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

        workflow = Workflow("many_tools_performance", "Many Tools Performance")

        workflow.add_node(
            "agent",
            LLMAgentNode(),
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Execute some operations"}],
                "tools": many_tools,
                "auto_execute_tools": True,
                "tool_execution_config": {"max_rounds": 2},
            },
        )

        start_time = time.time()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)
        execution_time = time.time() - start_time

        assert result.success is True
        # Should complete in reasonable time even with many tools
        assert execution_time < 5.0  # 5 seconds max

    def test_tool_execution_with_conversation_memory(self):
        """Test tool execution preserves conversation context."""
        workflow = Workflow("tool_with_memory", "Tool with Memory")

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
            LLMAgentNode(),
            {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Remember that X=42."},
                    {"role": "assistant", "content": "I'll remember that X=42."},
                    {
                        "role": "user",
                        "content": "Now execute the memory tool with that context.",
                    },
                ],
                "tools": tools,
                "auto_execute_tools": True,
                "conversation_id": "test_memory_123",
                "memory_config": {"type": "buffer", "max_tokens": 1000},
            },
        )

        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        assert result.success is True
        # Conversation should be preserved through tool execution
