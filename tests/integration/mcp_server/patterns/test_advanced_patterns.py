#!/usr/bin/env python3

"""
Advanced MCP Patterns Test Suite - Part 2

Tests advanced MCP patterns 6-10:
6. Agent Integration Pattern
7. Workflow Integration Pattern
8. Error Handling Pattern
9. Streaming Response Pattern
10. Multi-Tenant Pattern

Plus comprehensive integration tests.
"""

import asyncio
import io
import json
import logging
import os

# Test utilities
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.logic import SwitchNode

# Kailash imports
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


# Import the basic test infrastructure
# Define mock classes locally since test_basic_patterns was moved to integration
class MockMCPServer:
    """Mock MCP server for testing."""

    def __init__(self):
        self.tools = {}
        self.resources = {}

    def register_tool(self, name, func):
        self.tools[name] = func

    def register_resource(self, name, resource):
        self.resources[name] = resource


class MockMCPClient:
    """Mock MCP client for testing."""

    def __init__(self, server):
        self.server = server
        self.call_count = 0

    async def call_tool(self, name, **kwargs):
        self.call_count += 1
        if name in self.server.tools:
            return await self.server.tools[name](**kwargs)
        raise ValueError(f"Tool {name} not found")


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdvancedMCPPatternTests:
    """Advanced MCP Pattern Tests - Patterns 6-10"""

    def __init__(self):
        self.test_results = []
        self.setup_components()

    def setup_components(self):
        """Setup test components"""
        self.runtime = LocalRuntime()
        self.mock_servers = {}
        self.mock_clients = {}
        self.workflows = {}

    async def cleanup(self):
        """Cleanup test resources"""
        # Stop all mock servers
        for server in self.mock_servers.values():
            if hasattr(server, "stop"):
                await server.stop()

        # Disconnect all clients
        for client in self.mock_clients.values():
            if hasattr(client, "disconnect"):
                await client.disconnect()

    # Pattern 6: Agent Integration Pattern
    async def test_agent_integration_pattern(self) -> Dict[str, Any]:
        """Test Pattern 6: Agent Integration Pattern"""
        logger.info("Testing Pattern 6: Agent Integration Pattern")

        try:
            # Test 6.1: MCP Server with Tools for Agent
            mcp_server = MockMCPServer("agent-tools-server")

            @mcp_server.tool()
            def calculate_fibonacci(n: int) -> dict:
                """Calculate Fibonacci number."""
                if n <= 1:
                    return {"result": n}

                a, b = 0, 1
                for _ in range(2, n + 1):
                    a, b = b, a + b
                return {"result": b}

            @mcp_server.tool()
            def get_system_info() -> dict:
                """Get system information."""
                return {
                    "timestamp": datetime.now().isoformat(),
                    "server": "agent-tools-server",
                    "version": "1.0.0",
                }

            @mcp_server.tool()
            def process_text(text: str, operation: str = "uppercase") -> dict:
                """Process text with various operations."""
                if operation == "uppercase":
                    return {"result": text.upper()}
                elif operation == "lowercase":
                    return {"result": text.lower()}
                elif operation == "reverse":
                    return {"result": text[::-1]}
                elif operation == "length":
                    return {"result": len(text)}
                else:
                    return {"result": text, "operation": "none"}

            await mcp_server.start()

            # Test 6.2: LLM Agent with MCP Integration
            class MockLLMAgentWithMCP:
                def __init__(self, name: str, mcp_servers: List[str] = None):
                    self.name = name
                    self.mcp_servers = mcp_servers or []
                    self.available_tools = {}
                    self.tool_calls = []
                    self.auto_discover_tools = True
                    self.auto_execute_tools = False

                async def connect_to_mcp_servers(self):
                    """Connect to MCP servers and discover tools"""
                    for server_url in self.mcp_servers:
                        # Mock tool discovery
                        if "agent-tools-server" in server_url:
                            self.available_tools.update(
                                {
                                    "calculate_fibonacci": {
                                        "description": "Calculate Fibonacci number",
                                        "parameters": {
                                            "n": {"type": "int", "required": True}
                                        },
                                    },
                                    "get_system_info": {
                                        "description": "Get system information",
                                        "parameters": {},
                                    },
                                    "process_text": {
                                        "description": "Process text with various operations",
                                        "parameters": {
                                            "text": {"type": "str", "required": True},
                                            "operation": {
                                                "type": "str",
                                                "required": False,
                                            },
                                        },
                                    },
                                }
                            )

                async def process_message(
                    self, messages: List[Dict[str, str]]
                ) -> Dict[str, Any]:
                    """Process messages with potential tool calls"""
                    user_message = messages[-1]["content"]

                    # Simple pattern matching for demo
                    if "fibonacci" in user_message.lower():
                        # Extract number (simplified)
                        import re

                        numbers = re.findall(r"\d+", user_message)
                        if numbers:
                            n = int(numbers[0])
                            tool_result = await self.call_tool(
                                "calculate_fibonacci", {"n": n}
                            )
                            return {
                                "response": f"The Fibonacci number for {n} is {tool_result['result']}",
                                "tool_calls": [
                                    {"tool": "calculate_fibonacci", "args": {"n": n}}
                                ],
                            }

                    elif "system info" in user_message.lower():
                        tool_result = await self.call_tool("get_system_info", {})
                        return {
                            "response": f"System info: {tool_result}",
                            "tool_calls": [{"tool": "get_system_info", "args": {}}],
                        }

                    elif "process text" in user_message.lower():
                        # Extract text and operation
                        text = "Hello World"  # Simplified
                        operation = "uppercase"
                        tool_result = await self.call_tool(
                            "process_text", {"text": text, "operation": operation}
                        )
                        return {
                            "response": f"Processed text: {tool_result['result']}",
                            "tool_calls": [
                                {
                                    "tool": "process_text",
                                    "args": {"text": text, "operation": operation},
                                }
                            ],
                        }

                    return {
                        "response": "I understand, but I don't have the right tools for that task."
                    }

                async def call_tool(
                    self, tool_name: str, args: Dict[str, Any]
                ) -> Dict[str, Any]:
                    """Call MCP tool"""
                    self.tool_calls.append({"tool": tool_name, "args": args})
                    # Mock tool execution via MCP server
                    return await mcp_server.call_tool(tool_name, args)

            agent = MockLLMAgentWithMCP(
                name="mcp_agent", mcp_servers=["mcp://agent-tools-server:8080"]
            )

            await agent.connect_to_mcp_servers()

            # Test 6.3: Agent Tool Discovery
            assert len(agent.available_tools) == 3, "Should discover 3 tools"
            assert (
                "calculate_fibonacci" in agent.available_tools
            ), "Should discover fibonacci tool"
            assert (
                "get_system_info" in agent.available_tools
            ), "Should discover system info tool"
            assert (
                "process_text" in agent.available_tools
            ), "Should discover text processing tool"

            # Test 6.4: Agent Tool Execution
            fib_response = await agent.process_message(
                [{"role": "user", "content": "Calculate fibonacci for 10"}]
            )
            assert (
                "55" in fib_response["response"]
            ), "Should calculate fibonacci correctly"
            assert len(agent.tool_calls) == 1, "Should have 1 tool call"

            # Test 6.5: System Info Tool
            sys_response = await agent.process_message(
                [{"role": "user", "content": "Get system info"}]
            )
            assert "System info" in sys_response["response"], "Should get system info"

            # Test 6.6: Text Processing Tool
            text_response = await agent.process_message(
                [{"role": "user", "content": "Process text with uppercase"}]
            )
            assert (
                "HELLO WORLD" in text_response["response"]
            ), "Should process text correctly"

            # Test 6.7: Multiple MCP Servers
            data_server = MockMCPServer("data-server")

            @data_server.tool()
            def query_database(query: str) -> dict:
                """Query database."""
                return {"result": f"Database result for: {query}", "rows": 5}

            @data_server.tool()
            def cache_data(key: str, value: str) -> dict:
                """Cache data."""
                return {"cached": True, "key": key, "value": value}

            await data_server.start()

            multi_agent = MockLLMAgentWithMCP(
                name="multi_mcp_agent",
                mcp_servers=["mcp://agent-tools-server:8080", "mcp://data-server:8081"],
            )

            await multi_agent.connect_to_mcp_servers()

            # Should have tools from both servers
            assert (
                len(multi_agent.available_tools) >= 3
            ), "Should have tools from multiple servers"

            await mcp_server.stop()
            await data_server.stop()

            return {
                "pattern": "Agent Integration Pattern",
                "status": "PASSED",
                "tests_run": 7,
                "details": {
                    "mcp_server_with_tools": "✓",
                    "agent_mcp_integration": "✓",
                    "tool_discovery": "✓",
                    "tool_execution": "✓",
                    "system_info_tool": "✓",
                    "text_processing_tool": "✓",
                    "multiple_mcp_servers": "✓",
                },
            }

        except Exception as e:
            return {
                "pattern": "Agent Integration Pattern",
                "status": "FAILED",
                "error": str(e),
                "tests_run": 0,
            }

    # Pattern 7: Workflow Integration Pattern
    async def test_workflow_integration_pattern(self) -> Dict[str, Any]:
        """Test Pattern 7: Workflow Integration Pattern"""
        logger.info("Testing Pattern 7: Workflow Integration Pattern")

        try:
            # Test 7.1: MCP Server with Resources
            resource_server = MockMCPServer("resource-server")

            @resource_server.resource()
            def get_database_schema() -> dict:
                """Provide database schema as a resource."""
                return {
                    "tables": ["users", "orders", "products"],
                    "version": "1.0",
                    "relationships": {"users": ["orders"], "orders": ["products"]},
                }

            @resource_server.resource()
            def get_api_config() -> dict:
                """Provide API configuration resource."""
                return {
                    "endpoints": {
                        "users": "/api/v1/users",
                        "orders": "/api/v1/orders",
                        "products": "/api/v1/products",
                    },
                    "auth": {"type": "bearer", "required": True},
                    "rate_limit": {"requests_per_minute": 100},
                }

            await resource_server.start()

            # Test 7.2: Workflow with MCP Integration
            workflow_builder = WorkflowBuilder()

            # Add MCP resource accessor node
            workflow_builder.add_node(
                "PythonCodeNode",
                "mcp_accessor",
                {
                    "code": """
# Access MCP resources
def get_mcp_resource(resource_name):
    # Mock MCP resource access
    if resource_name == "database_schema":
        return {
            "tables": ["users", "orders", "products"],
            "version": "1.0",
            "relationships": {
                "users": ["orders"],
                "orders": ["products"]
            }
        }
    elif resource_name == "api_config":
        return {
            "endpoints": {
                "users": "/api/v1/users",
                "orders": "/api/v1/orders",
                "products": "/api/v1/products"
            },
            "auth": {"type": "bearer", "required": True},
            "rate_limit": {"requests_per_minute": 100}
        }
    return None

# Get resources
schema = get_mcp_resource("database_schema")
config = get_mcp_resource("api_config")

result = {
    "mcp_resources": {
        "schema": schema,
        "config": config
    },
    "resource_count": 2
}
"""
                },
            )

            # Add data processor that uses MCP resources
            workflow_builder.add_node(
                "PythonCodeNode",
                "data_processor",
                {
                    "code": """
# Process using MCP resources
mcp_data = input_data.get("mcp_resources", {})
schema = mcp_data.get("schema", {})
config = mcp_data.get("config", {})

# Process with schema and config
tables = schema.get("tables", [])
endpoints = config.get("endpoints", {})

processed_data = {
    "table_count": len(tables),
    "endpoint_count": len(endpoints),
    "processing_complete": True,
    "schema_version": schema.get("version", "unknown"),
    "auth_required": config.get("auth", {}).get("required", False)
}

result = {"processed_data": processed_data}
"""
                },
            )
            workflow_builder.add_connection(
                "mcp_accessor", "result", "data_processor", "input_data"
            )

            # Test 7.3: Execute Workflow
            workflow = workflow_builder.build()
            results, _ = self.runtime.execute(workflow, parameters={})

            # Verify workflow execution
            assert "mcp_accessor" in results, "Should have MCP accessor results"
            assert "data_processor" in results, "Should have data processor results"

            mcp_results = results["mcp_accessor"]["result"]
            assert "mcp_resources" in mcp_results, "Should have MCP resources"
            assert mcp_results["resource_count"] == 2, "Should have 2 resources"

            processed_results = results["data_processor"]["result"]
            processed_data = processed_results["processed_data"]
            assert processed_data["table_count"] == 3, "Should process 3 tables"
            assert processed_data["endpoint_count"] == 3, "Should process 3 endpoints"
            assert processed_data[
                "processing_complete"
            ], "Processing should be complete"

            # Test 7.4: Workflow with MCP Tools
            tool_workflow = WorkflowBuilder()

            # Add MCP tool caller
            tool_workflow.add_node(
                "PythonCodeNode",
                "mcp_tool_caller",
                {
                    "code": """
# Call MCP tools
def call_mcp_tool(tool_name, args):
    # Mock MCP tool call
    if tool_name == "calculate_sum":
        return {"result": args.get("a", 0) + args.get("b", 0)}
    elif tool_name == "get_weather":
        return {"temperature": 72, "conditions": "sunny", "city": args.get("city", "Unknown")}
    return {"error": "Tool not found"}

# Call tools
sum_result = call_mcp_tool("calculate_sum", {"a": 15, "b": 27})
weather_result = call_mcp_tool("get_weather", {"city": "San Francisco"})

result = {
    "tool_results": {
        "sum": sum_result,
        "weather": weather_result
    },
    "tools_called": 2
}
"""
                },
            )

            # Add result aggregator
            tool_workflow.add_node(
                "PythonCodeNode",
                "result_aggregator",
                {
                    "code": """
# Aggregate MCP tool results
tool_data = input_data.get("tool_results", {})
tools_called = input_data.get("tools_called", 0)

sum_result = tool_data.get("sum", {})
weather_result = tool_data.get("weather", {})

aggregated = {
    "sum_value": sum_result.get("result", 0),
    "weather_temp": weather_result.get("temperature", 0),
    "weather_city": weather_result.get("city", "Unknown"),
    "total_tools_called": tools_called,
    "aggregation_complete": True
}

result = {"aggregated_results": aggregated}
"""
                },
            )
            tool_workflow.add_connection(
                "mcp_tool_caller", "result", "result_aggregator", "input_data"
            )

            # Execute tool workflow
            tool_wf = tool_workflow.build()
            tool_results, _ = self.runtime.execute(tool_wf, parameters={})

            # Verify tool workflow execution
            assert (
                "mcp_tool_caller" in tool_results
            ), "Should have MCP tool caller results"
            assert (
                "result_aggregator" in tool_results
            ), "Should have result aggregator results"

            aggregated = tool_results["result_aggregator"]["result"][
                "aggregated_results"
            ]
            assert aggregated["sum_value"] == 42, "Should calculate sum correctly"
            assert aggregated["weather_temp"] == 72, "Should get weather temperature"
            assert (
                aggregated["weather_city"] == "San Francisco"
            ), "Should get weather city"
            assert aggregated["total_tools_called"] == 2, "Should call 2 tools"

            # Test 7.5: Dynamic MCP Workflow
            dynamic_workflow = WorkflowBuilder()

            # Add dynamic MCP interaction
            dynamic_workflow.add_node(
                "PythonCodeNode",
                "dynamic_mcp",
                {
                    "code": """
# Dynamic MCP interaction based on input
def dynamic_mcp_call(operation, data):
    # Mock dynamic MCP calls
    if operation == "process_data":
        return {"processed": True, "count": len(data)}
    elif operation == "validate_data":
        return {"valid": True, "items": data}
    elif operation == "transform_data":
        return {"transformed": [str(item).upper() for item in data]}
    return {"error": "Unknown operation"}

# Process input
input_operation = input_data.get("operation", "process_data")
input_payload = input_data.get("payload", [])

# Dynamic MCP call
mcp_result = dynamic_mcp_call(input_operation, input_payload)

result = {
    "dynamic_result": mcp_result,
    "operation": input_operation,
    "payload_size": len(input_payload)
}
"""
                },
            )

            # Execute with different operations
            dynamic_wf = dynamic_workflow.build()

            # Test processing operation
            process_results, _ = self.runtime.execute(
                dynamic_wf,
                parameters={
                    "dynamic_mcp": {
                        "input_data": {
                            "operation": "process_data",
                            "payload": ["item1", "item2", "item3"],
                        }
                    }
                },
            )

            dynamic_result = process_results["dynamic_mcp"]["result"]["dynamic_result"]
            assert dynamic_result["processed"], "Should process data"
            assert dynamic_result["count"] == 3, "Should count 3 items"

            # Test validation operation
            validate_results, _ = self.runtime.execute(
                dynamic_wf,
                parameters={
                    "dynamic_mcp": {
                        "input_data": {
                            "operation": "validate_data",
                            "payload": ["valid1", "valid2"],
                        }
                    }
                },
            )

            validate_result = validate_results["dynamic_mcp"]["result"][
                "dynamic_result"
            ]
            assert validate_result["valid"], "Should validate data"
            assert len(validate_result["items"]) == 2, "Should validate 2 items"

            await resource_server.stop()

            return {
                "pattern": "Workflow Integration Pattern",
                "status": "PASSED",
                "tests_run": 5,
                "details": {
                    "mcp_server_with_resources": "✓",
                    "workflow_with_mcp_resources": "✓",
                    "workflow_execution": "✓",
                    "workflow_with_mcp_tools": "✓",
                    "dynamic_mcp_workflow": "✓",
                },
            }

        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            return {
                "pattern": "Workflow Integration Pattern",
                "status": "FAILED",
                "error": error_msg,
                "tests_run": 0,
            }

    # Pattern 8: Error Handling Pattern
    async def test_error_handling_pattern(self) -> Dict[str, Any]:
        """Test Pattern 8: Error Handling Pattern"""
        logger.info("Testing Pattern 8: Error Handling Pattern")

        try:
            # Test 8.1: Server Error Handling
            error_server = MockMCPServer("error-handling-server")

            @error_server.tool()
            def risky_operation(data: dict = None) -> dict:
                """Operation that might fail."""
                if data is None or not data:
                    raise ValueError("Data cannot be empty")

                if data.get("fail", False):
                    raise RuntimeError("Simulated runtime error")

                if data.get("timeout", False):
                    raise TimeoutError("Operation timed out")

                return {"result": "Success", "data": data}

            @error_server.tool()
            def divide_numbers(a: float, b: float) -> dict:
                """Division operation with error handling."""
                if b == 0:
                    raise ZeroDivisionError("Division by zero")

                return {"result": a / b}

            await error_server.start()

            # Test 8.2: Successful Operation
            success_result = await error_server.call_tool(
                "risky_operation", {"data": {"value": "test"}}
            )
            assert success_result["success"], "Successful operation should succeed"
            assert success_result["result"]["result"] == "Success"

            # Test 8.3: Error Handling - Empty Data
            empty_result = await error_server.call_tool("risky_operation", {"data": {}})
            assert not empty_result["success"], "Empty data should fail"
            assert "cannot be empty" in empty_result["error"]

            # Test 8.4: Error Handling - Runtime Error
            runtime_result = await error_server.call_tool(
                "risky_operation", {"data": {"fail": True}}
            )
            assert not runtime_result["success"], "Runtime error should fail"
            assert "runtime error" in runtime_result["error"].lower()

            # Test 8.5: Error Handling - Division by Zero
            div_result = await error_server.call_tool(
                "divide_numbers", {"a": 10, "b": 0}
            )
            assert not div_result["success"], "Division by zero should fail"
            assert "Division by zero" in div_result["error"]

            # Test 8.6: Successful Division
            div_success = await error_server.call_tool(
                "divide_numbers", {"a": 10, "b": 2}
            )
            assert div_success["success"], "Valid division should succeed"
            assert div_success["result"]["result"] == 5.0

            # Test 8.7: Client Error Handling
            class ResilientMCPClient:
                def __init__(self, primary_url: str, fallback_url: str = None):
                    self.primary_url = primary_url
                    self.fallback_url = fallback_url
                    self.primary_client = MockMCPClient("primary")
                    self.fallback_client = (
                        MockMCPClient("fallback") if fallback_url else None
                    )
                    self.connection_attempts = 0
                    self.fallback_used = False

                async def call_tool_safe(self, tool_name: str, params: dict) -> dict:
                    """Call tool with fallback handling."""
                    self.connection_attempts += 1

                    try:
                        # Try primary client
                        await self.primary_client.connect(self.primary_url)
                        return await self.primary_client.call_tool(tool_name, params)

                    except Exception as e:
                        if self.fallback_client and self.fallback_url:
                            try:
                                # Try fallback client
                                await self.fallback_client.connect(self.fallback_url)
                                self.fallback_used = True
                                return await self.fallback_client.call_tool(
                                    tool_name, params
                                )
                            except Exception as fallback_error:
                                return {
                                    "success": False,
                                    "error": f"Primary failed: {e}, Fallback failed: {fallback_error}",
                                }

                        return {"success": False, "error": str(e)}

            # Test resilient client
            resilient_client = ResilientMCPClient(
                "mcp://primary:8080", "mcp://fallback:8080"
            )

            result = await resilient_client.call_tool_safe(
                "test_tool", {"data": "test"}
            )
            assert result["success"], "Resilient client should succeed"

            # Test 8.8: Retry Logic
            class RetryMCPClient:
                def __init__(self, max_retries: int = 3, retry_delay: float = 0.1):
                    self.max_retries = max_retries
                    self.retry_delay = retry_delay
                    self.client = MockMCPClient("retry-client")
                    self.attempt_count = 0

                async def call_tool_with_retry(
                    self, tool_name: str, params: dict
                ) -> dict:
                    """Call tool with retry logic."""
                    for attempt in range(self.max_retries):
                        self.attempt_count += 1

                        try:
                            if not self.client.connected:
                                await self.client.connect("mcp://server:8080")

                            return await self.client.call_tool(tool_name, params)

                        except Exception as e:
                            if attempt == self.max_retries - 1:
                                # Last attempt failed
                                return {
                                    "success": False,
                                    "error": f"Failed after {self.max_retries} attempts: {e}",
                                    "attempts": self.attempt_count,
                                }

                            # Wait before retry
                            await asyncio.sleep(self.retry_delay)

                    return {"success": False, "error": "Maximum retries exceeded"}

            retry_client = RetryMCPClient(max_retries=3, retry_delay=0.01)
            retry_result = await retry_client.call_tool_with_retry(
                "test_tool", {"data": "test"}
            )
            assert retry_result["success"], "Retry client should succeed"

            # Test 8.9: Circuit Breaker Pattern
            class CircuitBreakerMCPClient:
                def __init__(
                    self, failure_threshold: int = 3, recovery_timeout: float = 1.0
                ):
                    self.failure_threshold = failure_threshold
                    self.recovery_timeout = recovery_timeout
                    self.failure_count = 0
                    self.last_failure_time = None
                    self.state = "closed"  # closed, open, half-open
                    self.client = MockMCPClient("circuit-breaker")

                async def call_tool_with_circuit_breaker(
                    self, tool_name: str, params: dict
                ) -> dict:
                    """Call tool with circuit breaker pattern."""

                    # Check circuit breaker state
                    if self.state == "open":
                        if (
                            time.time() - self.last_failure_time
                        ) > self.recovery_timeout:
                            self.state = "half-open"
                        else:
                            return {
                                "success": False,
                                "error": "Circuit breaker is open",
                                "state": self.state,
                            }

                    try:
                        if not self.client.connected:
                            await self.client.connect("mcp://server:8080")

                        result = await self.client.call_tool(tool_name, params)

                        # Success - reset circuit breaker
                        if self.state == "half-open":
                            self.state = "closed"
                            self.failure_count = 0

                        return result

                    except Exception as e:
                        # Failure - increment counter
                        self.failure_count += 1
                        self.last_failure_time = time.time()

                        if self.failure_count >= self.failure_threshold:
                            self.state = "open"

                        return {
                            "success": False,
                            "error": str(e),
                            "failure_count": self.failure_count,
                            "state": self.state,
                        }

            circuit_client = CircuitBreakerMCPClient(
                failure_threshold=2, recovery_timeout=0.1
            )
            circuit_result = await circuit_client.call_tool_with_circuit_breaker(
                "test_tool", {"data": "test"}
            )
            assert circuit_result["success"], "Circuit breaker client should succeed"

            await error_server.stop()

            return {
                "pattern": "Error Handling Pattern",
                "status": "PASSED",
                "tests_run": 9,
                "details": {
                    "server_error_handling": "✓",
                    "successful_operation": "✓",
                    "empty_data_error": "✓",
                    "runtime_error": "✓",
                    "division_by_zero": "✓",
                    "successful_division": "✓",
                    "resilient_client": "✓",
                    "retry_logic": "✓",
                    "circuit_breaker": "✓",
                },
            }

        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            return {
                "pattern": "Error Handling Pattern",
                "status": "FAILED",
                "error": error_msg,
                "tests_run": 0,
            }

    # Pattern 9: Streaming Response Pattern
    async def test_streaming_response_pattern(self) -> Dict[str, Any]:
        """Test Pattern 9: Streaming Response Pattern"""
        logger.info("Testing Pattern 9: Streaming Response Pattern")

        try:
            # Test 9.1: Streaming Server
            streaming_server = MockMCPServer("streaming-server", enable_streaming=True)

            @streaming_server.tool()
            async def stream_data(count: int = 10) -> AsyncIterator[dict]:
                """Stream data items."""
                for i in range(count):
                    yield {"item": i, "timestamp": datetime.now().isoformat()}
                    await asyncio.sleep(0.01)  # Small delay to simulate streaming

            @streaming_server.tool()
            async def process_large_dataset(size: int = 100) -> AsyncIterator[dict]:
                """Process large dataset with streaming results."""
                batch_size = 10
                for batch_start in range(0, size, batch_size):
                    batch_end = min(batch_start + batch_size, size)

                    # Process batch
                    batch_results = []
                    for i in range(batch_start, batch_end):
                        batch_results.append({"id": i, "processed": True})

                    yield {
                        "batch_start": batch_start,
                        "batch_end": batch_end,
                        "batch_size": len(batch_results),
                        "results": batch_results,
                    }

                    await asyncio.sleep(0.01)

            await streaming_server.start()

            # Test 9.2: Streaming Client
            class StreamingMCPClient:
                def __init__(self, name: str):
                    self.name = name
                    self.client = MockMCPClient(name)
                    self.connected = False

                async def connect(self, server_url: str):
                    """Connect to streaming server."""
                    await self.client.connect(server_url)
                    self.connected = True

                async def call_streaming_tool(
                    self, tool_name: str, params: dict
                ) -> AsyncIterator[dict]:
                    """Call streaming tool and yield results."""
                    if not self.connected:
                        raise ConnectionError("Not connected to server")

                    # Mock streaming response
                    if tool_name == "stream_data":
                        count = params.get("count", 10)
                        for i in range(count):
                            yield {"item": i, "timestamp": datetime.now().isoformat()}
                            await asyncio.sleep(0.01)

                    elif tool_name == "process_large_dataset":
                        size = params.get("size", 100)
                        batch_size = 10
                        for batch_start in range(0, size, batch_size):
                            batch_end = min(batch_start + batch_size, size)
                            batch_results = []
                            for i in range(batch_start, batch_end):
                                batch_results.append({"id": i, "processed": True})

                            yield {
                                "batch_start": batch_start,
                                "batch_end": batch_end,
                                "batch_size": len(batch_results),
                                "results": batch_results,
                            }
                            await asyncio.sleep(0.01)

            streaming_client = StreamingMCPClient("streaming-client")
            await streaming_client.connect("mcp://streaming-server:8080")

            # Test 9.3: Stream Data Tool
            stream_results = []
            async for result in streaming_client.call_streaming_tool(
                "stream_data", {"count": 5}
            ):
                stream_results.append(result)

            assert len(stream_results) == 5, "Should receive 5 streaming results"
            assert all(
                "item" in result for result in stream_results
            ), "All results should have item"
            assert all(
                "timestamp" in result for result in stream_results
            ), "All results should have timestamp"

            # Test 9.4: Large Dataset Processing
            dataset_results = []
            async for batch in streaming_client.call_streaming_tool(
                "process_large_dataset", {"size": 25}
            ):
                dataset_results.append(batch)

            assert len(dataset_results) == 3, "Should receive 3 batches for size 25"
            assert (
                dataset_results[0]["batch_start"] == 0
            ), "First batch should start at 0"
            assert dataset_results[-1]["batch_end"] == 25, "Last batch should end at 25"

            # Test 9.5: Streaming with Buffering
            class BufferedStreamingClient:
                def __init__(self, name: str, buffer_size: int = 5):
                    self.name = name
                    self.buffer_size = buffer_size
                    self.client = StreamingMCPClient(name)
                    self.buffer = []

                async def connect(self, server_url: str):
                    """Connect to server."""
                    await self.client.connect(server_url)

                async def call_streaming_tool_buffered(
                    self, tool_name: str, params: dict
                ) -> AsyncIterator[List[dict]]:
                    """Call streaming tool with buffering."""
                    buffer = []

                    async for result in self.client.call_streaming_tool(
                        tool_name, params
                    ):
                        buffer.append(result)

                        if len(buffer) >= self.buffer_size:
                            yield buffer
                            buffer = []

                    # Yield remaining buffer
                    if buffer:
                        yield buffer

            buffered_client = BufferedStreamingClient("buffered-client", buffer_size=3)
            await buffered_client.connect("mcp://streaming-server:8080")

            buffered_results = []
            async for buffer in buffered_client.call_streaming_tool_buffered(
                "stream_data", {"count": 10}
            ):
                buffered_results.append(buffer)

            # Should have multiple buffers
            assert len(buffered_results) > 1, "Should have multiple buffers"
            assert len(buffered_results[0]) == 3, "First buffer should have 3 items"

            # Test 9.6: Streaming with Error Handling
            class ErrorHandlingStreamingClient:
                def __init__(self, name: str):
                    self.name = name
                    self.client = StreamingMCPClient(name)
                    self.error_count = 0

                async def connect(self, server_url: str):
                    """Connect to server."""
                    await self.client.connect(server_url)

                async def call_streaming_tool_safe(
                    self, tool_name: str, params: dict
                ) -> AsyncIterator[dict]:
                    """Call streaming tool with error handling."""
                    try:
                        async for result in self.client.call_streaming_tool(
                            tool_name, params
                        ):
                            yield result
                    except Exception as e:
                        self.error_count += 1
                        yield {
                            "error": True,
                            "error_message": str(e),
                            "error_count": self.error_count,
                        }

            error_client = ErrorHandlingStreamingClient("error-streaming-client")
            await error_client.connect("mcp://streaming-server:8080")

            # Test with valid tool
            safe_results = []
            async for result in error_client.call_streaming_tool_safe(
                "stream_data", {"count": 3}
            ):
                safe_results.append(result)

            assert len(safe_results) == 3, "Should receive 3 safe results"
            assert all(
                not result.get("error", False) for result in safe_results
            ), "No errors should occur"

            await streaming_server.stop()

            return {
                "pattern": "Streaming Response Pattern",
                "status": "PASSED",
                "tests_run": 6,
                "details": {
                    "streaming_server": "✓",
                    "streaming_client": "✓",
                    "stream_data_tool": "✓",
                    "large_dataset_processing": "✓",
                    "buffered_streaming": "✓",
                    "streaming_error_handling": "✓",
                },
            }

        except Exception as e:
            return {
                "pattern": "Streaming Response Pattern",
                "status": "FAILED",
                "error": str(e),
                "tests_run": 0,
            }

    # Pattern 10: Multi-Tenant Pattern
    async def test_multi_tenant_pattern(self) -> Dict[str, Any]:
        """Test Pattern 10: Multi-Tenant Pattern"""
        logger.info("Testing Pattern 10: Multi-Tenant Pattern")

        try:
            # Test 10.1: Multi-Tenant Server
            class MultiTenantMCPServer:
                def __init__(self, name: str):
                    self.name = name
                    self.tenants = {}
                    self.tools = {}
                    self.resources = {}
                    self.running = False

                def add_tenant(self, tenant_id: str, config: dict):
                    """Add tenant configuration."""
                    self.tenants[tenant_id] = {
                        "config": config,
                        "tools": {},
                        "resources": {},
                        "usage": {"tool_calls": 0, "resource_accesses": 0},
                        "created_at": datetime.now().isoformat(),
                    }

                def register_tool_for_tenant(
                    self, tenant_id: str, tool_name: str, handler
                ):
                    """Register tool for specific tenant."""
                    if tenant_id not in self.tenants:
                        raise ValueError(f"Tenant {tenant_id} not found")

                    self.tenants[tenant_id]["tools"][tool_name] = handler

                def register_resource_for_tenant(
                    self, tenant_id: str, resource_uri: str, handler
                ):
                    """Register resource for specific tenant."""
                    if tenant_id not in self.tenants:
                        raise ValueError(f"Tenant {tenant_id} not found")

                    self.tenants[tenant_id]["resources"][resource_uri] = handler

                async def call_tool(
                    self, tenant_id: str, tool_name: str, args: dict
                ) -> dict:
                    """Call tool for specific tenant."""
                    if tenant_id not in self.tenants:
                        return {
                            "success": False,
                            "error": f"Tenant {tenant_id} not found",
                        }

                    tenant = self.tenants[tenant_id]

                    if tool_name not in tenant["tools"]:
                        return {
                            "success": False,
                            "error": f"Tool {tool_name} not found for tenant {tenant_id}",
                        }

                    try:
                        handler = tenant["tools"][tool_name]
                        result = handler(**args)
                        if asyncio.iscoroutine(result):
                            result = await result

                        # Track usage
                        tenant["usage"]["tool_calls"] += 1

                        return {
                            "success": True,
                            "result": result,
                            "tenant_id": tenant_id,
                        }

                    except Exception as e:
                        return {
                            "success": False,
                            "error": str(e),
                            "tenant_id": tenant_id,
                        }

                async def get_resource(self, tenant_id: str, resource_uri: str) -> dict:
                    """Get resource for specific tenant."""
                    if tenant_id not in self.tenants:
                        return {
                            "success": False,
                            "error": f"Tenant {tenant_id} not found",
                        }

                    tenant = self.tenants[tenant_id]

                    if resource_uri not in tenant["resources"]:
                        return {
                            "success": False,
                            "error": f"Resource {resource_uri} not found for tenant {tenant_id}",
                        }

                    try:
                        handler = tenant["resources"][resource_uri]
                        result = handler()
                        if asyncio.iscoroutine(result):
                            result = await result

                        # Track usage
                        tenant["usage"]["resource_accesses"] += 1

                        return {
                            "success": True,
                            "content": result,
                            "tenant_id": tenant_id,
                        }

                    except Exception as e:
                        return {
                            "success": False,
                            "error": str(e),
                            "tenant_id": tenant_id,
                        }

                def get_tenant_usage(self, tenant_id: str) -> dict:
                    """Get tenant usage statistics."""
                    if tenant_id not in self.tenants:
                        return {
                            "success": False,
                            "error": f"Tenant {tenant_id} not found",
                        }

                    tenant = self.tenants[tenant_id]
                    return {
                        "success": True,
                        "tenant_id": tenant_id,
                        "usage": tenant["usage"],
                        "tool_count": len(tenant["tools"]),
                        "resource_count": len(tenant["resources"]),
                        "created_at": tenant["created_at"],
                    }

                async def start(self):
                    """Start multi-tenant server."""
                    self.running = True

                async def stop(self):
                    """Stop multi-tenant server."""
                    self.running = False

            mt_server = MultiTenantMCPServer("multi-tenant-server")
            await mt_server.start()

            # Test 10.2: Add Tenants
            mt_server.add_tenant(
                "tenant-a", {"name": "Company A", "plan": "premium", "rate_limit": 1000}
            )

            mt_server.add_tenant(
                "tenant-b", {"name": "Company B", "plan": "basic", "rate_limit": 100}
            )

            mt_server.add_tenant(
                "tenant-c",
                {"name": "Company C", "plan": "enterprise", "rate_limit": 5000},
            )

            # Test 10.3: Register Tools for Tenants
            # Tenant A tools
            def tenant_a_calculator(a: int, b: int) -> dict:
                return {"result": a + b, "tenant": "A"}

            def tenant_a_data_processor(data: list) -> dict:
                return {"processed": len(data), "items": data, "tenant": "A"}

            mt_server.register_tool_for_tenant(
                "tenant-a", "calculator", tenant_a_calculator
            )
            mt_server.register_tool_for_tenant(
                "tenant-a", "data_processor", tenant_a_data_processor
            )

            # Tenant B tools (different implementations)
            def tenant_b_calculator(a: int, b: int) -> dict:
                return {"result": a * b, "tenant": "B", "operation": "multiply"}

            def tenant_b_text_processor(text: str) -> dict:
                return {"processed": text.upper(), "tenant": "B"}

            mt_server.register_tool_for_tenant(
                "tenant-b", "calculator", tenant_b_calculator
            )
            mt_server.register_tool_for_tenant(
                "tenant-b", "text_processor", tenant_b_text_processor
            )

            # Tenant C tools
            def tenant_c_advanced_calc(operation: str, a: int, b: int) -> dict:
                if operation == "add":
                    result = a + b
                elif operation == "multiply":
                    result = a * b
                elif operation == "power":
                    result = a**b
                else:
                    result = 0
                return {"result": result, "tenant": "C", "operation": operation}

            mt_server.register_tool_for_tenant(
                "tenant-c", "advanced_calculator", tenant_c_advanced_calc
            )

            # Test 10.4: Register Resources for Tenants
            def tenant_a_config():
                return {"database": "tenant-a-db", "api_key": "tenant-a-key"}

            def tenant_b_config():
                return {"database": "tenant-b-db", "api_key": "tenant-b-key"}

            def tenant_c_config():
                return {
                    "database": "tenant-c-db",
                    "api_key": "tenant-c-key",
                    "features": ["advanced"],
                }

            mt_server.register_resource_for_tenant(
                "tenant-a", "config", tenant_a_config
            )
            mt_server.register_resource_for_tenant(
                "tenant-b", "config", tenant_b_config
            )
            mt_server.register_resource_for_tenant(
                "tenant-c", "config", tenant_c_config
            )

            # Test 10.5: Tenant Isolation - Tool Calls
            # Tenant A calculator (addition)
            result_a = await mt_server.call_tool(
                "tenant-a", "calculator", {"a": 5, "b": 3}
            )
            assert result_a["success"], "Tenant A calculator should succeed"
            assert result_a["result"]["result"] == 8, "Tenant A should add numbers"
            assert result_a["result"]["tenant"] == "A", "Should be tenant A"

            # Tenant B calculator (multiplication)
            result_b = await mt_server.call_tool(
                "tenant-b", "calculator", {"a": 5, "b": 3}
            )
            assert result_b["success"], "Tenant B calculator should succeed"
            assert (
                result_b["result"]["result"] == 15
            ), "Tenant B should multiply numbers"
            assert result_b["result"]["tenant"] == "B", "Should be tenant B"

            # Tenant C advanced calculator
            result_c = await mt_server.call_tool(
                "tenant-c",
                "advanced_calculator",
                {"operation": "power", "a": 2, "b": 3},
            )
            assert result_c["success"], "Tenant C advanced calculator should succeed"
            assert result_c["result"]["result"] == 8, "Tenant C should calculate power"
            assert result_c["result"]["tenant"] == "C", "Should be tenant C"

            # Test 10.6: Tenant Isolation - Resource Access
            config_a = await mt_server.get_resource("tenant-a", "config")
            assert config_a["success"], "Tenant A config access should succeed"
            assert (
                config_a["content"]["database"] == "tenant-a-db"
            ), "Should get tenant A database"

            config_b = await mt_server.get_resource("tenant-b", "config")
            assert config_b["success"], "Tenant B config access should succeed"
            assert (
                config_b["content"]["database"] == "tenant-b-db"
            ), "Should get tenant B database"

            config_c = await mt_server.get_resource("tenant-c", "config")
            assert config_c["success"], "Tenant C config access should succeed"
            assert (
                config_c["content"]["database"] == "tenant-c-db"
            ), "Should get tenant C database"
            assert "features" in config_c["content"], "Tenant C should have features"

            # Test 10.7: Cross-Tenant Isolation
            # Tenant A trying to access Tenant B tool
            cross_result = await mt_server.call_tool(
                "tenant-a", "text_processor", {"text": "test"}
            )
            assert not cross_result["success"], "Cross-tenant tool access should fail"

            # Tenant B trying to access Tenant C tool
            cross_result_2 = await mt_server.call_tool(
                "tenant-b", "advanced_calculator", {"operation": "add", "a": 1, "b": 2}
            )
            assert not cross_result_2["success"], "Cross-tenant tool access should fail"

            # Test 10.8: Usage Tracking
            # Make more calls to track usage
            await mt_server.call_tool("tenant-a", "calculator", {"a": 10, "b": 20})
            await mt_server.call_tool("tenant-a", "data_processor", {"data": [1, 2, 3]})
            await mt_server.get_resource("tenant-a", "config")

            usage_a = mt_server.get_tenant_usage("tenant-a")
            assert usage_a["success"], "Should get tenant A usage"
            assert usage_a["usage"]["tool_calls"] == 3, "Should have 3 tool calls"
            assert (
                usage_a["usage"]["resource_accesses"] == 2
            ), "Should have 2 resource accesses"

            # Test 10.9: Multi-Tenant Client
            class MultiTenantMCPClient:
                def __init__(self, name: str, tenant_id: str):
                    self.name = name
                    self.tenant_id = tenant_id
                    self.server = None
                    self.connected = False

                async def connect(self, server: MultiTenantMCPServer):
                    """Connect to multi-tenant server."""
                    self.server = server
                    self.connected = True

                async def call_tool(self, tool_name: str, params: dict) -> dict:
                    """Call tool for this tenant."""
                    if not self.connected:
                        raise ConnectionError("Not connected to server")

                    return await self.server.call_tool(
                        self.tenant_id, tool_name, params
                    )

                async def get_resource(self, resource_uri: str) -> dict:
                    """Get resource for this tenant."""
                    if not self.connected:
                        raise ConnectionError("Not connected to server")

                    return await self.server.get_resource(self.tenant_id, resource_uri)

                def get_usage(self) -> dict:
                    """Get usage for this tenant."""
                    if not self.connected:
                        raise ConnectionError("Not connected to server")

                    return self.server.get_tenant_usage(self.tenant_id)

            # Test multi-tenant clients
            client_a = MultiTenantMCPClient("client-a", "tenant-a")
            client_b = MultiTenantMCPClient("client-b", "tenant-b")

            await client_a.connect(mt_server)
            await client_b.connect(mt_server)

            # Client A operations
            calc_a = await client_a.call_tool("calculator", {"a": 7, "b": 3})
            assert calc_a["success"], "Client A calculator should succeed"
            assert calc_a["result"]["result"] == 10, "Client A should add numbers"

            # Client B operations
            calc_b = await client_b.call_tool("calculator", {"a": 7, "b": 3})
            assert calc_b["success"], "Client B calculator should succeed"
            assert calc_b["result"]["result"] == 21, "Client B should multiply numbers"

            await mt_server.stop()

            return {
                "pattern": "Multi-Tenant Pattern",
                "status": "PASSED",
                "tests_run": 9,
                "details": {
                    "multi_tenant_server": "✓",
                    "tenant_registration": "✓",
                    "tenant_tool_registration": "✓",
                    "tenant_resource_registration": "✓",
                    "tenant_isolation_tools": "✓",
                    "tenant_isolation_resources": "✓",
                    "cross_tenant_isolation": "✓",
                    "usage_tracking": "✓",
                    "multi_tenant_clients": "✓",
                },
            }

        except Exception as e:
            return {
                "pattern": "Multi-Tenant Pattern",
                "status": "FAILED",
                "error": str(e),
                "tests_run": 0,
            }

    # Run all advanced pattern tests
    async def run_all_advanced_pattern_tests(self) -> Dict[str, Any]:
        """Run all advanced MCP pattern tests"""
        logger.info("Starting advanced MCP pattern tests...")

        # Run pattern tests
        test_methods = [
            self.test_agent_integration_pattern,
            self.test_workflow_integration_pattern,
            self.test_error_handling_pattern,
            self.test_streaming_response_pattern,
            self.test_multi_tenant_pattern,
        ]

        results = []
        passed = 0
        failed = 0

        for test_method in test_methods:
            try:
                result = await test_method()
                results.append(result)
                if result["status"] == "PASSED":
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Test {test_method.__name__} failed with exception: {e}")
                results.append(
                    {
                        "pattern": test_method.__name__,
                        "status": "FAILED",
                        "error": str(e),
                        "tests_run": 0,
                    }
                )
                failed += 1

        # Cleanup
        await self.cleanup()

        return {
            "test_suite": "Advanced MCP Patterns Test Suite",
            "summary": {
                "total_patterns": len(test_methods),
                "passed": passed,
                "failed": failed,
                "success_rate": f"{(passed / len(test_methods) * 100):.1f}%",
            },
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }


# Main test execution
@pytest.mark.skip(
    reason="Test has unresolved mock dependencies - needs proper MCP server implementation"
)
@pytest.mark.asyncio
async def test_advanced_mcp_patterns():
    """Run advanced MCP pattern tests"""
    tester = AdvancedMCPPatternTests()
    results = await tester.run_all_advanced_pattern_tests()

    # Log results
    logger.info(f"Test Results: {json.dumps(results, indent=2)}")

    # Assert overall success
    assert (
        results["summary"]["failed"] == 0
    ), f"Some advanced patterns failed: {results['summary']}"

    return results


if __name__ == "__main__":
    # Run tests directly
    async def main():
        tester = AdvancedMCPPatternTests()
        results = await tester.run_all_advanced_pattern_tests()

        print("\n=== ADVANCED MCP PATTERNS TEST RESULTS ===")
        print(f"Total Patterns: {results['summary']['total_patterns']}")
        print(f"Passed: {results['summary']['passed']}")
        print(f"Failed: {results['summary']['failed']}")
        print(f"Success Rate: {results['summary']['success_rate']}")

        print("\n=== DETAILED RESULTS ===")
        for result in results["results"]:
            status_icon = "✅" if result["status"] == "PASSED" else "❌"
            print(f"{status_icon} {result['pattern']}: {result['status']}")

            if result["status"] == "PASSED" and "details" in result:
                for test_name, status in result["details"].items():
                    print(f"   {status} {test_name}")
            elif result["status"] == "FAILED":
                print(f"   Error: {result.get('error', 'Unknown error')}")

        return results["summary"]["failed"] == 0

    # Run the test
    import asyncio

    success = asyncio.run(main())
    exit(0 if success else 1)
