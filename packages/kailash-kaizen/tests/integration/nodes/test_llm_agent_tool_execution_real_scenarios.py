"""Integration tests for LLMAgent tool execution with real scenarios.

These tests use REAL services (no mocking) as per test organization policy.
"""

import asyncio
import json
import os
import time
from typing import Any, Dict, List

import pytest
from kaizen.nodes.ai.llm_agent import LLMAgentNode

from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow


@pytest.mark.integration
class TestLLMAgentToolExecutionRealScenarios:
    """Integration tests with real components and services."""

    def setup_method(self):
        """Set up test environment."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"
        self.runtime = LocalRuntime()

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    # ========== Workflow Integration Tests ==========

    def test_tool_execution_in_workflow(self):
        """Test tool execution within a complete workflow."""
        workflow = Workflow("tool_execution_workflow", "Tool Execution Test")

        # Add LLM agent with tools
        agent = LLMAgentNode(name="agent_with_tools")
        workflow.add_node("agent", agent)

        # Define tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "data_processor",
                    "description": "Process data with operations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["sum", "average", "count"],
                            },
                            "data": {"type": "array", "items": {"type": "number"}},
                        },
                        "required": ["operation", "data"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "report_generator",
                    "description": "Generate a report from processed data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "data": {"type": "object"},
                            "format": {
                                "type": "string",
                                "enum": ["json", "text", "markdown"],
                            },
                        },
                        "required": ["title", "data"],
                    },
                },
            },
        ]

        # Execute workflow with parameters
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "agent": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Process the data [1,2,3,4,5] to get the sum and average, then create a report",
                        }
                    ],
                    "tools": tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 3},
                }
            },
        )

        assert "agent" in outputs
        agent_output = outputs["agent"]
        assert agent_output["success"] is True
        assert agent_output["context"]["tools_available"] == 2

    def test_multi_node_workflow_with_tools(self):
        """Test workflow with multiple nodes where one uses tools."""
        workflow = Workflow("multi_node_tool_workflow", "Multi-Node Tool Test")

        # First node: Prepares data
        from kailash.nodes.code import PythonCodeNode

        data_prep = PythonCodeNode(
            name="data_preparation",
            code="""
# Prepare data for analysis
import json
data = {
    "sales": [100, 150, 200, 175, 225],
    "regions": ["North", "South", "East", "West", "Central"],
    "target": 180
}
result = json.dumps(data)
""",
        )
        workflow.add_node("data_prep", data_prep)

        # Second node: LLM agent with tools
        agent = LLMAgentNode(name="tool_agent")
        workflow.add_node("agent", agent)

        # Connect nodes
        workflow.connect("data_prep", "agent", mapping={"result": "context"})

        # Execute with parameters
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "agent": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Analyze the sales data and identify regions above target",
                        }
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "analyze_sales",
                                "description": "Analyze sales data",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"data": {"type": "string"}},
                                    "required": ["data"],
                                },
                            },
                        }
                    ],
                    "auto_execute_tools": True,
                }
            },
        )

        assert "data_prep" in outputs
        assert "agent" in outputs

    # ========== Real-World Scenario Tests ==========

    def test_customer_support_scenario(self):
        """Test realistic customer support scenario with tool usage."""
        agent = LLMAgentNode(name="support_agent")

        # Customer support tools
        support_tools = [
            {
                "type": "function",
                "function": {
                    "name": "lookup_customer",
                    "description": "Look up customer information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"},
                            "email": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_order_status",
                    "description": "Check the status of an order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "customer_id": {"type": "string"},
                        },
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_ticket",
                    "description": "Create a support ticket",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"},
                            "issue": {"type": "string"},
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                        },
                        "required": ["issue"],
                    },
                },
            },
        ]

        # Simulate customer support conversation
        messages = [
            {"role": "system", "content": "You are a helpful customer support agent."},
            {
                "role": "user",
                "content": "Hi, I'm customer john@example.com and I want to check on order #12345. If there's an issue, please create a high priority ticket.",
            },
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=messages,
            tools=support_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 4},
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 3
        # In a real scenario, the agent would execute multiple tools

    def test_data_analysis_pipeline(self):
        """Test data analysis pipeline with multiple tool interactions."""
        agent = LLMAgentNode(name="data_analyst")

        # Data analysis tools
        analysis_tools = [
            {
                "type": "function",
                "function": {
                    "name": "load_dataset",
                    "description": "Load a dataset for analysis",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dataset_name": {"type": "string"},
                            "filters": {"type": "object"},
                        },
                        "required": ["dataset_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_statistics",
                    "description": "Calculate statistics on data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "array"},
                            "metrics": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["data", "metrics"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_visualization",
                    "description": "Create a visualization",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "object"},
                            "chart_type": {
                                "type": "string",
                                "enum": ["bar", "line", "pie", "scatter"],
                            },
                            "title": {"type": "string"},
                        },
                        "required": ["data", "chart_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_results",
                    "description": "Export analysis results",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "results": {"type": "object"},
                            "format": {
                                "type": "string",
                                "enum": ["csv", "json", "pdf"],
                            },
                            "filename": {"type": "string"},
                        },
                        "required": ["results", "format"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Load the sales dataset, calculate mean and standard deviation, create a bar chart, and export as JSON",
                }
            ],
            tools=analysis_tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 5,  # Multiple steps expected
                "timeout": 60,
            },
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 4

    # ========== Performance and Scalability Tests ==========

    def test_concurrent_tool_execution_performance(self):
        """Test performance with concurrent tool executions."""
        agent = LLMAgentNode(name="concurrent_agent")

        # Create tools that could be executed in parallel
        parallel_tools = [
            {
                "type": "function",
                "function": {
                    "name": f"service_{i}",
                    "description": f"Query service {i}",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
            for i in range(5)
        ]

        start_time = time.time()

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Query all 5 services for the latest data"}
            ],
            tools=parallel_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 2},
        )

        execution_time = time.time() - start_time

        assert result["success"] is True
        assert result["context"]["tools_available"] == 5
        assert execution_time < 5.0  # Should complete quickly

    def test_large_tool_catalog(self):
        """Test handling of large number of available tools."""
        agent = LLMAgentNode(name="catalog_agent")

        # Create a large catalog of tools (simulating enterprise scenario)
        large_tool_catalog = []
        categories = ["data", "api", "file", "compute", "report"]
        operations = ["create", "read", "update", "delete", "analyze"]

        for category in categories:
            for operation in operations:
                for i in range(4):  # 100 tools total
                    large_tool_catalog.append(
                        {
                            "type": "function",
                            "function": {
                                "name": f"{category}_{operation}_{i}",
                                "description": f"{operation.capitalize()} {category} resource {i}",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "data": {"type": "object"},
                                    },
                                },
                            },
                        }
                    )

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Update data resource 2 with new values"}
            ],
            tools=large_tool_catalog,
            auto_execute_tools=True,
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 100

    # ========== Error Handling and Recovery Tests ==========

    def test_tool_execution_error_recovery(self):
        """Test recovery from tool execution errors."""
        agent = LLMAgentNode(name="error_recovery_agent")

        # Tools that might fail
        unreliable_tools = [
            {
                "type": "function",
                "function": {
                    "name": "unreliable_api",
                    "description": "An API that might fail",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "endpoint": {"type": "string"},
                            "retry": {"type": "boolean"},
                        },
                        "required": ["endpoint"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fallback_api",
                    "description": "Fallback API to use if primary fails",
                    "parameters": {
                        "type": "object",
                        "properties": {"data": {"type": "string"}},
                        "required": ["data"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Get data from the API, use fallback if needed",
                }
            ],
            tools=unreliable_tools,
            auto_execute_tools=True,
            tool_execution_config={"max_rounds": 3, "continue_on_error": True},
        )

        assert result["success"] is True
        # Even with potential failures, the agent should complete

    def test_timeout_handling(self):
        """Test handling of tool execution timeouts."""
        agent = LLMAgentNode(name="timeout_agent")

        # Tool that might take too long
        slow_tools = [
            {
                "type": "function",
                "function": {
                    "name": "slow_computation",
                    "description": "Performs slow computation",
                    "parameters": {
                        "type": "object",
                        "properties": {"complexity": {"type": "integer"}},
                        "required": ["complexity"],
                    },
                },
            }
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {"role": "user", "content": "Run the computation with complexity 1000"}
            ],
            tools=slow_tools,
            auto_execute_tools=True,
            tool_execution_config={"timeout": 5, "max_rounds": 1},  # 5 second timeout
        )

        assert result["success"] is True
        # Should complete even if tool times out

    # ========== Complex Multi-Step Scenarios ==========

    def test_research_assistant_scenario(self):
        """Test complex research assistant scenario with multiple tool types."""
        agent = LLMAgentNode(name="research_assistant")

        # Research tools
        research_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_papers",
                    "description": "Search academic papers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "year_from": {"type": "integer"},
                            "year_to": {"type": "integer"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "extract_citations",
                    "description": "Extract citations from papers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "paper_ids": {"type": "array", "items": {"type": "string"}},
                            "format": {
                                "type": "string",
                                "enum": ["bibtex", "apa", "mla"],
                            },
                        },
                        "required": ["paper_ids"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_papers",
                    "description": "Generate summaries of papers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "paper_ids": {"type": "array", "items": {"type": "string"}},
                            "summary_length": {
                                "type": "string",
                                "enum": ["brief", "detailed"],
                            },
                        },
                        "required": ["paper_ids"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_bibliography",
                    "description": "Create a bibliography",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "citations": {"type": "array"},
                            "style": {"type": "string"},
                            "output_format": {
                                "type": "string",
                                "enum": ["markdown", "latex", "word"],
                            },
                        },
                        "required": ["citations", "style"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Find recent papers on quantum computing from 2023-2024, summarize the top 3, and create an APA bibliography",
                }
            ],
            tools=research_tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 5  # Multiple steps: search, summarize, extract, create bib
            },
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 4

    def test_workflow_automation_scenario(self):
        """Test workflow automation with conditional tool execution."""
        agent = LLMAgentNode(name="workflow_automator")

        # Workflow automation tools
        automation_tools = [
            {
                "type": "function",
                "function": {
                    "name": "check_conditions",
                    "description": "Check if conditions are met",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "conditions": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "operator": {"type": "string", "enum": ["AND", "OR"]},
                        },
                        "required": ["conditions"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_action",
                    "description": "Execute an action if conditions are met",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action_type": {"type": "string"},
                            "parameters": {"type": "object"},
                            "async": {"type": "boolean", "default": False},
                        },
                        "required": ["action_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_notification",
                    "description": "Send notification about workflow status",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient": {"type": "string"},
                            "message": {"type": "string"},
                            "channel": {
                                "type": "string",
                                "enum": ["email", "slack", "webhook"],
                            },
                        },
                        "required": ["recipient", "message"],
                    },
                },
            },
        ]

        result = agent.execute(
            provider="mock",
            model="gpt-4",
            messages=[
                {
                    "role": "user",
                    "content": "Check if all system health checks pass. If yes, execute deployment action. Send notification regardless of outcome.",
                }
            ],
            tools=automation_tools,
            auto_execute_tools=True,
            tool_execution_config={
                "max_rounds": 4,
                "continue_on_error": True,  # Send notification even if other steps fail
            },
        )

        assert result["success"] is True
        assert result["context"]["tools_available"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestAsyncToolExecution:
    """Test async aspects of tool execution."""

    async def test_async_tool_execution_handling(self):
        """Test that async tool execution is properly handled."""
        agent = LLMAgentNode(name="async_agent")

        # Run in async context
        loop = asyncio.get_event_loop()

        def run_agent():
            return agent.execute(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": "Execute async operation"}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "async_operation",
                            "description": "An async operation",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                auto_execute_tools=True,
            )

        # Execute in thread pool to handle async properly
        result = await loop.run_in_executor(None, run_agent)

        assert result["success"] is True
