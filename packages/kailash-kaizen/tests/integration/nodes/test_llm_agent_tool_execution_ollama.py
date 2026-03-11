"""Integration tests for LLMAgent tool execution with real Ollama models.

These tests use REAL Ollama models (no mocking) to verify full MCP tool execution.
"""

import asyncio
import json
import os
import time
from typing import Any, Dict

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode

from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestLLMAgentToolExecutionOllama:
    """Test tool execution with real Ollama models."""

    def setup_method(self):
        """Set up test environment."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"
        self.runtime = LocalRuntime()

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_ollama_basic_tool_execution(self):
        """Test basic tool execution with Ollama."""
        agent = LLMAgentNode(name="ollama_agent")

        # Simple calculator tool
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",  # Fast model for testing
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. When asked to perform calculations, use the available tools.",
                },
                {
                    "role": "user",
                    "content": "Please add 15 and 27 using the add_numbers tool.",
                },
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 2},
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 1
        # Ollama should have tried to use the tool

    def test_ollama_multi_tool_scenario(self):
        """Test multiple tool usage with Ollama."""
        agent = LLMAgentNode(name="multi_tool_agent")

        # Multiple tools for a data processing scenario
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_data",
                    "description": "Read data from a source",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Data source name",
                            }
                        },
                        "required": ["source"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "process_data",
                    "description": "Process data with a specific operation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "string",
                                "description": "Data to process",
                            },
                            "operation": {
                                "type": "string",
                                "enum": ["filter", "transform", "aggregate"],
                            },
                        },
                        "required": ["data", "operation"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_results",
                    "description": "Save processed results",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "string",
                                "description": "Results to save",
                            },
                            "destination": {
                                "type": "string",
                                "description": "Where to save",
                            },
                        },
                        "required": ["results", "destination"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "system",
                    "content": "You are a data processing assistant. Use the available tools to complete tasks.",
                },
                {
                    "role": "user",
                    "content": "Read data from 'sales_db', filter it, and save to 'reports'. Use the appropriate tools.",
                },
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 4,  # Allow multiple tool calls
                "timeout": 30,
            },
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 3

    def test_ollama_tool_execution_with_mcp_tools(self):
        """Test Ollama with MCP-provided tools."""
        agent = LLMAgentNode(name="mcp_ollama_agent")

        # Simulate MCP tools with proper metadata
        mcp_tools = [
            {
                "type": "function",
                "function": {
                    "name": "mcp_search",
                    "description": "Search using MCP server",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                    "mcp_server": "search_server",
                    "mcp_server_config": {
                        "name": "search_server",
                        "transport": "stdio",
                    },
                },
            }
        ]

        # Also test with regular tools mixed in
        regular_tools = [
            {
                "type": "function",
                "function": {
                    "name": "format_results",
                    "description": "Format search results",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "results": {"type": "array"},
                            "format": {
                                "type": "string",
                                "enum": ["json", "text", "table"],
                            },
                        },
                        "required": ["results"],
                    },
                },
            }
        ]

        all_tools = mcp_tools + regular_tools

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "Search for 'python async' and format the results as a table",
                }
            ],
            tools=all_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 3},
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 2
        # Should have both MCP and regular tools available

    def test_ollama_tool_error_handling(self):
        """Test how Ollama handles tool execution errors."""
        agent = LLMAgentNode(name="error_handling_agent")

        # Tool that might fail
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "risky_operation",
                    "description": "An operation that might fail",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "risk_level": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                            "data": {"type": "string"},
                        },
                        "required": ["risk_level", "data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "safe_fallback",
                    "description": "A safe fallback operation",
                    "parameters": {
                        "type": "object",
                        "properties": {"data": {"type": "string"}},
                        "required": ["data"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "system",
                    "content": "If an operation fails, try using a fallback method.",
                },
                {
                    "role": "user",
                    "content": "Process this data with high risk level: 'important_data'. If it fails, use the safe fallback.",
                },
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 3,
                "continue_on_error": True,  # Should continue even if tool fails
            },
        )

        assert result["success"] is True
        # Even with potential errors, the agent should complete successfully

    def test_ollama_workflow_integration(self):
        """Test Ollama tool execution within a workflow."""
        workflow = Workflow("ollama_tool_workflow", "Ollama Tool Test")

        # Add Ollama agent node
        agent = LLMAgentNode(name="ollama_workflow_agent")
        workflow.add_node("agent", agent)

        # Tools for workflow operations
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_workflow_status",
                    "description": "Get current workflow status",
                    "parameters": {
                        "type": "object",
                        "properties": {"workflow_id": {"type": "string"}},
                        "required": ["workflow_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_workflow",
                    "description": "Update workflow state",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "workflow_id": {"type": "string"},
                            "status": {"type": "string"},
                            "data": {"type": "object"},
                        },
                        "required": ["workflow_id", "status"],
                    },
                },
            },
        ]

        # Execute workflow
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "agent": {
                    "provider": "ollama",
                    "model": "llama3.2:1b",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Check the status of workflow '{workflow.workflow_id}' and update it to 'processing'",
                        }
                    ],
                    "tools": tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 2},
                }
            },
        )

        assert "agent" in outputs
        assert outputs["agent"]["success"] is True

    @pytest.mark.slow
    def test_ollama_complex_multi_round_scenario(self):
        """Test complex scenario with multiple rounds of tool execution."""
        agent = LLMAgentNode(name="complex_scenario_agent")

        # Complex set of tools for a multi-step process
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "analyze_requirements",
                    "description": "Analyze project requirements",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirements": {"type": "string"},
                            "complexity": {
                                "type": "string",
                                "enum": ["simple", "moderate", "complex"],
                            },
                        },
                        "required": ["requirements"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_plan",
                    "description": "Generate implementation plan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "analysis": {"type": "object"},
                            "timeline": {"type": "string"},
                        },
                        "required": ["analysis"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "estimate_resources",
                    "description": "Estimate required resources",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "plan": {"type": "object"},
                            "team_size": {"type": "integer"},
                        },
                        "required": ["plan"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_report",
                    "description": "Create final report",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "analysis": {"type": "object"},
                            "plan": {"type": "object"},
                            "resources": {"type": "object"},
                            "format": {
                                "type": "string",
                                "enum": ["executive", "detailed", "technical"],
                            },
                        },
                        "required": ["analysis", "plan", "resources"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "system",
                    "content": "You are a project planning assistant. Use the available tools to analyze requirements and create a comprehensive plan.",
                },
                {
                    "role": "user",
                    "content": "Analyze these requirements: 'Build a real-time chat application with AI integration'. Create a complete project plan with resource estimates and an executive report.",
                },
            ],
            tools=tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 5,  # Allow multiple rounds for complex workflow
                "timeout": 60,
            },
            temperature=0.7,  # Some creativity for planning
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 4
        # Should have executed multiple tools in sequence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
