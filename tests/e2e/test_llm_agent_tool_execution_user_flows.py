"""End-to-end tests for LLMAgent tool execution user flows.

These tests validate complete user journeys with Docker services.
"""

import json
import os
import time
from typing import Any, Dict, List

import pytest
from kailash.middleware import create_gateway
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestLLMAgentToolExecutionUserFlows:
    """E2E tests for common user flows with tool execution."""

    def setup_method(self):
        """Set up test environment."""
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"
        self.runtime = LocalRuntime()

    def teardown_method(self):
        """Clean up test environment."""
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_user_flow_data_analysis_assistant(self):
        """Test complete flow: User asks AI to analyze data from database."""
        # Create workflow
        workflow = Workflow("data_analysis_flow", "AI-powered data analysis")

        # Add database node
        db_node = SQLDatabaseNode(
            name="sales_db",
            connection_string="sqlite:///:memory:",
            query="SELECT 1 as placeholder",  # Default query, overridden at runtime
        )
        workflow.add_node("database", db_node)

        # Add AI agent with analysis tools
        agent = LLMAgentNode(name="analyst")
        workflow.add_node("agent", agent)

        # Connect database results to agent context
        workflow.connect("database", "agent", mapping={"data": "data_context"})

        # Define analysis tools
        analysis_tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_metrics",
                    "description": "Calculate business metrics from data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "array", "description": "Sales data"},
                            "metrics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Metrics to calculate",
                            },
                        },
                        "required": ["data", "metrics"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_insights",
                    "description": "Generate business insights from metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metrics": {"type": "object"},
                            "context": {"type": "string"},
                        },
                        "required": ["metrics"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_visualization_spec",
                    "description": "Create specification for data visualization",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "array"},
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
        ]

        # Execute workflow
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "database": {
                    "query": "SELECT 'Widget A' as product, 'North' as region, 1500.0 as amount",
                    "database_type": "postgresql",
                    "connection_config": {
                        "host": "localhost",
                        "port": 5434,
                        "database": "kailash_test",
                        "user": "test_user",
                        "password": "test_password",
                    },
                },
                "agent": {
                    "provider": "mock",  # Use mock for faster E2E tests
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a data analyst. Analyze the provided sales data.",
                        },
                        {
                            "role": "user",
                            "content": "Calculate total sales by region, identify top products, and create a visualization spec for the results.",
                        },
                    ],
                    "tools": analysis_tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 4},
                },
            },
        )

        # Verify flow completed successfully
        assert "data" in outputs["database"]
        assert len(outputs["database"]["data"]) > 0
        assert "context" in outputs["agent"] or "response" in outputs["agent"]

    def test_user_flow_customer_support_automation(self):
        """Test complete flow: Customer support with database lookups and actions."""
        # Build workflow using WorkflowBuilder
        builder = WorkflowBuilder("support_automation")

        # Add nodes
        builder.add_node(
            "customer_lookup",
            "SQLDatabaseNode",
            {
                "name": "customer_db",
                "connection_string": "sqlite:///:memory:",
                "query": "SELECT 'customer_123' as customer_id, 'John Doe' as name",
            },
        )

        builder.add_node("support_agent", "LLMAgentNode", {"name": "support_ai"})

        builder.add_node(
            "action_executor", "PythonCodeNode", {"name": "execute_actions"}
        )

        # Connect nodes
        builder.add_connection(
            "customer_lookup", "result", "support_agent", "customer_data"
        )
        builder.add_connection(
            "support_agent", "actions", "action_executor", "actions_to_execute"
        )

        workflow = builder.build()

        # Support tools
        support_tools = [
            {
                "type": "function",
                "function": {
                    "name": "check_order_status",
                    "description": "Check order status",
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
                    "name": "process_refund",
                    "description": "Process a refund",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "amount": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["order_id", "amount", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_support_ticket",
                    "description": "Create support ticket",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"},
                            "issue": {"type": "string"},
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                            },
                            "actions_taken": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["customer_id", "issue", "priority"],
                    },
                },
            },
        ]

        # Execute workflow
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "customer_lookup": {
                    "query": "SELECT * FROM customers WHERE email = 'john@example.com'",
                    "connection_config": {
                        "host": "localhost",
                        "port": 5434,
                        "database": "kailash_test",
                        "user": "test_user",
                        "password": "test_password",
                    },
                },
                "support_agent": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a customer support agent. Use the available tools to help customers.",
                        },
                        {
                            "role": "user",
                            "content": "Customer john@example.com is complaining about order #12345 being delayed. Check the order and create a high priority ticket with appropriate actions.",
                        },
                    ],
                    "tools": support_tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 3},
                },
                "action_executor": {
                    "code": """
# Execute support actions
import json

actions = json.loads(actions_to_execute) if isinstance(actions_to_execute, str) else actions_to_execute
result = {
    "executed_actions": [],
    "status": "completed"
}

for action in actions:
    # Simulate action execution
    result["executed_actions"].append({
        "action": action,
        "status": "success",
        "timestamp": time.time()
    })
"""
                },
            },
        )

        # Verify complete flow
        assert outputs["customer_lookup"]["success"] is True
        assert outputs["support_agent"]["success"] is True
        assert outputs["action_executor"]["success"] is True

    def test_user_flow_research_assistant_with_mcp(self):
        """Test research assistant flow with MCP server integration."""
        workflow = Workflow("research_assistant", "AI Research Assistant")

        # Add research agent
        agent = LLMAgentNode(name="researcher")
        workflow.add_node("agent", agent)

        # MCP and regular tools for research
        research_tools = [
            {
                "type": "function",
                "function": {
                    "name": "mcp_web_search",
                    "description": "Search the web using MCP server",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "num_results": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                    "mcp_server": "web_search",
                    "mcp_server_config": {"name": "web_search", "transport": "stdio"},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mcp_document_reader",
                    "description": "Read documents using MCP server",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "extract": {
                                "type": "string",
                                "enum": ["text", "summary", "keywords"],
                            },
                        },
                        "required": ["url"],
                    },
                    "mcp_server": "document_reader",
                    "mcp_server_config": {
                        "name": "document_reader",
                        "transport": "stdio",
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compile_research",
                    "description": "Compile research findings",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sources": {"type": "array", "items": {"type": "object"}},
                            "topic": {"type": "string"},
                            "format": {
                                "type": "string",
                                "enum": ["summary", "detailed", "academic"],
                            },
                        },
                        "required": ["sources", "topic"],
                    },
                },
            },
        ]

        # Execute research workflow
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "agent": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a research assistant. Use MCP tools to search and read documents.",
                        },
                        {
                            "role": "user",
                            "content": "Research the latest developments in quantum computing. Find at least 3 sources and compile a summary.",
                        },
                    ],
                    "tools": research_tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 5, "timeout": 60},
                }
            },
        )

        assert outputs["agent"]["success"] is True
        assert outputs["agent"]["context"]["tools_available"] == 3
        # Should have MCP tools available

    def test_user_flow_middleware_integration(self):
        """Test tool execution through middleware gateway."""
        # Create gateway
        gateway = create_gateway(
            title="Tool Execution Gateway",
            database_url="postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

        # Create workflow with tool-enabled agent
        workflow = Workflow("middleware_tool_test", "Middleware Tool Test")

        agent = LLMAgentNode(name="gateway_agent")
        workflow.add_node("agent", agent)

        # API integration tools
        api_tools = [
            {
                "type": "function",
                "function": {
                    "name": "call_api",
                    "description": "Call external API",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "endpoint": {"type": "string"},
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "DELETE"],
                            },
                            "data": {"type": "object"},
                        },
                        "required": ["endpoint", "method"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "process_response",
                    "description": "Process API response",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "response": {"type": "object"},
                            "extract_fields": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["response"],
                    },
                },
            },
        ]

        # Execute through runtime (gateway would handle in production)
        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "agent": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Call the /status endpoint with GET method and extract the version field from the response.",
                        }
                    ],
                    "tools": api_tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 2},
                }
            },
        )

        assert outputs["agent"]["success"] is True
        assert outputs["agent"]["context"]["tools_available"] == 2

    @pytest.mark.slow
    def test_user_flow_complex_business_automation(self):
        """Test complex business automation with multiple agents and tools."""
        # Create multi-agent workflow
        builder = WorkflowBuilder("business_automation")

        # Add multiple specialized agents
        builder.add_node("data_analyst", "LLMAgentNode", {"name": "analyst"})
        builder.add_node("decision_maker", "LLMAgentNode", {"name": "decision"})
        builder.add_node("executor", "LLMAgentNode", {"name": "executor"})

        # Add data sources
        builder.add_node("sales_db", "SQLDatabaseNode", {"name": "sales"})
        builder.add_node("inventory_db", "SQLDatabaseNode", {"name": "inventory"})

        # Connect workflow
        builder.add_connection("sales_db", "result", "data_analyst", "sales_data")
        builder.add_connection(
            "inventory_db", "result", "data_analyst", "inventory_data"
        )
        builder.add_connection(
            "data_analyst", "analysis", "decision_maker", "analysis_input"
        )
        builder.add_connection(
            "decision_maker", "decisions", "executor", "actions_to_execute"
        )

        workflow = builder.build()

        # Define tools for each agent
        analyst_tools = [
            {
                "type": "function",
                "function": {
                    "name": "analyze_trends",
                    "description": "Analyze sales and inventory trends",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sales_data": {"type": "array"},
                            "inventory_data": {"type": "array"},
                            "period": {"type": "string"},
                        },
                        "required": ["sales_data", "inventory_data"],
                    },
                },
            }
        ]

        decision_tools = [
            {
                "type": "function",
                "function": {
                    "name": "evaluate_options",
                    "description": "Evaluate business options",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "analysis": {"type": "object"},
                            "constraints": {"type": "object"},
                            "objectives": {"type": "array"},
                        },
                        "required": ["analysis"],
                    },
                },
            }
        ]

        executor_tools = [
            {
                "type": "function",
                "function": {
                    "name": "place_order",
                    "description": "Place inventory order",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "items": {"type": "array"},
                            "priority": {"type": "string"},
                            "budget": {"type": "number"},
                        },
                        "required": ["items"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_pricing",
                    "description": "Adjust product pricing",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "products": {"type": "array"},
                            "adjustment_type": {
                                "type": "string",
                                "enum": ["increase", "decrease", "dynamic"],
                            },
                            "percentage": {"type": "number"},
                        },
                        "required": ["products", "adjustment_type"],
                    },
                },
            },
        ]

        # Execute complex workflow
        db_config = {
            "host": "localhost",
            "port": 5434,
            "database": "kailash_test",
            "user": "test_user",
            "password": "test_password",
        }

        outputs, run_id = self.runtime.execute(
            workflow,
            parameters={
                "sales_db": {
                    "query": "SELECT * FROM sales WHERE date >= CURRENT_DATE - INTERVAL '30 days'",
                    "database_type": "postgresql",
                    "connection_config": db_config,
                },
                "inventory_db": {
                    "query": "SELECT * FROM inventory WHERE quantity < reorder_level",
                    "database_type": "postgresql",
                    "connection_config": db_config,
                },
                "data_analyst": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Analyze sales and inventory data to identify trends and issues.",
                        },
                        {
                            "role": "user",
                            "content": "Analyze the provided data and create a comprehensive report.",
                        },
                    ],
                    "tools": analyst_tools,
                    "auto_execute_tools": True,
                },
                "decision_maker": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Make business decisions based on analysis.",
                        },
                        {
                            "role": "user",
                            "content": "Based on the analysis, decide on inventory orders and pricing adjustments.",
                        },
                    ],
                    "tools": decision_tools,
                    "auto_execute_tools": True,
                },
                "executor": {
                    "provider": "mock",
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": "Execute business decisions."},
                        {
                            "role": "user",
                            "content": "Execute the decided actions for inventory and pricing.",
                        },
                    ],
                    "tools": executor_tools,
                    "auto_execute_tools": True,
                    "tool_execution_config": {"max_rounds": 3},
                },
            },
        )

        # Verify all agents completed successfully
        assert outputs["data_analyst"]["success"] is True
        assert outputs["decision_maker"]["success"] is True
        assert outputs["executor"]["success"] is True

        # Verify tools were available
        assert outputs["data_analyst"]["context"]["tools_available"] >= 1
        assert outputs["decision_maker"]["context"]["tools_available"] >= 1
        assert outputs["executor"]["context"]["tools_available"] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
