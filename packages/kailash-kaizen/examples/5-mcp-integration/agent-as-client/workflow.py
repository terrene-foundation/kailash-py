"""
Example: Agent as MCP Client - Production MCP Implementation

This example demonstrates how Kaizen agents consume external MCP tools using
the Kailash SDK's production-ready MCP implementation with real JSON-RPC 2.0.

✅ MIGRATED TO PRODUCTION MCP (2025-10-04)
- Uses kailash.mcp_server (production-ready, 100% MCP spec compliant)
- BaseAgent helpers: setup_mcp_client(), call_mcp_tool()
- Real JSON-RPC 2.0 protocol (no mocking)
- Multi-transport support (STDIO, HTTP, WebSocket, SSE)
- Enterprise features (auth, retry, circuit breaker, metrics)

Key Migration Changes:
1. Imports: kaizen.mcp → kailash.mcp_server (via BaseAgent)
2. Setup: MCPConnection → BaseAgent.setup_mcp_client()
3. Invocation: connection.call_tool() → BaseAgent.call_mcp_tool()
4. Configuration: URL-based → Transport-based configs
5. Execution: Sync methods → Async methods (await)

Use Case:
An intelligent research assistant that leverages external MCP tools (search,
compute, data analysis) to answer complex questions by orchestrating multiple
specialized services.

Learning Objectives:
- Use BaseAgent.setup_mcp_client() for production MCP connection management
- Configure multi-transport MCP servers (STDIO, HTTP, WebSocket)
- Discover available tools via real JSON-RPC protocol
- Invoke tools using BaseAgent.call_mcp_tool() helper (async)
- Handle multi-tool workflows with enterprise features
- Implement production patterns (auth, retry, circuit breaker, metrics)

Estimated time: 20 minutes
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Kaizen framework imports
from kaizen.core.base_agent import BaseAgent
from kaizen.memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# NOTE: kailash.mcp_server imported via BaseAgent helpers
# - BaseAgent.setup_mcp_client() handles MCPClient creation
# - BaseAgent.call_mcp_tool() handles tool invocation
# - No direct kailash.mcp_server imports needed in agent code

logger = logging.getLogger(__name__)


# ===================================================================
# CONFIGURATION
# ===================================================================


@dataclass
class MCPClientConfig:
    """Configuration for MCP client agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000

    # MCP server configurations (transport-based)
    mcp_servers: List[Dict[str, Any]] = field(
        default_factory=lambda: [
            # HTTP transport example
            {
                "name": "search-tools",
                "transport": "http",
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer demo-key"},
            },
            # STDIO transport example
            {
                "name": "compute-tools",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_compute_server"],
            },
        ]
    )

    # MCP client settings
    retry_strategy: str = "circuit_breaker"
    enable_metrics: bool = True
    connection_timeout: int = 30


# ===================================================================
# SIGNATURES
# ===================================================================


class TaskAnalysisSignature(Signature):
    """Analyze task to determine required MCP tools."""

    task_description: str = InputField(desc="User task requiring external tools")
    available_tools: str = InputField(desc="JSON list of available MCP tools")
    context: str = InputField(desc="Additional context", default="")

    required_tools: str = OutputField(desc="JSON list of required tools with reasons")
    execution_plan: str = OutputField(desc="Step-by-step execution plan")
    estimated_complexity: float = OutputField(
        desc="Complexity score 0.0-1.0", default=0.5
    )


class ToolInvocationSignature(Signature):
    """Prepare tool invocation with proper arguments."""

    tool_name: str = InputField(desc="Name of MCP tool to invoke")
    tool_schema: str = InputField(desc="JSON schema of tool parameters")
    user_request: str = InputField(desc="User's original request")
    context: str = InputField(desc="Execution context", default="")

    tool_arguments: str = OutputField(desc="JSON arguments for tool invocation")
    invocation_reasoning: str = OutputField(desc="Why these arguments were chosen")
    expected_output: str = OutputField(desc="Expected output description")


class ResultSynthesisSignature(Signature):
    """Synthesize results from multiple MCP tool calls."""

    task_description: str = InputField(desc="Original user task")
    tool_results: str = InputField(desc="JSON results from MCP tools")
    execution_context: str = InputField(desc="Execution metadata", default="")

    final_answer: str = OutputField(desc="Synthesized final answer")
    confidence_score: float = OutputField(
        desc="Confidence in answer 0.0-1.0", default=0.8
    )
    tool_usage_summary: str = OutputField(desc="Summary of which tools were used")


# ===================================================================
# MCP CLIENT AGENT
# ===================================================================


class MCPClientAgent(BaseAgent):
    """
    Agent that consumes external MCP tools using Kailash SDK's production MCP.

    This agent:
    1. Uses BaseAgent.setup_mcp_client() for connection management
    2. Discovers available tools using real JSON-RPC protocol
    3. Analyzes tasks to determine required tools
    4. Invokes tools via BaseAgent.call_mcp_tool() helper
    5. Synthesizes results from multiple tool calls

    Uses production-ready Kailash MCP infrastructure - NO MOCKING.
    """

    def __init__(
        self, config: MCPClientConfig, shared_memory: Optional[SharedMemoryPool] = None
    ):
        """
        Initialize MCP client agent with production MCP connections.

        Args:
            config: Configuration including MCP server transport configs
            shared_memory: Optional shared memory pool
        """
        # Initialize base agent with config auto-extraction
        super().__init__(
            config=config,
            signature=TaskAnalysisSignature(),
            shared_memory=shared_memory,
        )

        self.client_config = config

    async def _setup_mcp_connections(self):
        """
        Establish real MCP connections using BaseAgent helper.

        Uses BaseAgent.setup_mcp_client() for production-ready MCP setup.
        All tools automatically available in self._available_mcp_tools.
        """
        logger.info(
            f"Setting up MCP connections to {len(self.client_config.mcp_servers)} servers"
        )

        # Use BaseAgent helper for production MCP setup
        await self.setup_mcp_client(
            servers=self.client_config.mcp_servers,
            retry_strategy=self.client_config.retry_strategy,
            enable_metrics=self.client_config.enable_metrics,
        )

        logger.info(
            f"✓ MCP setup complete: {len(self._available_mcp_tools)} tools discovered"
        )

    async def analyze_task(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Analyze task to determine required MCP tools.

        Args:
            task: User task description
            context: Additional context

        Returns:
            Dictionary with required tools and execution plan
        """
        # Create signature for task analysis
        self.signature = TaskAnalysisSignature()

        # Prepare available tools JSON from BaseAgent's MCP tools
        available_tools_json = json.dumps(
            [
                {
                    "id": tool_id,
                    "name": tool_data["name"],
                    "description": tool_data.get("description", ""),
                    "server": tool_data["server_config"]["name"],
                }
                for tool_id, tool_data in self._available_mcp_tools.items()
            ],
            indent=2,
        )

        # Run analysis
        result = self.run(
            task_description=task, available_tools=available_tools_json, context=context
        )

        # Parse required tools
        try:
            required_tools = json.loads(
                self.extract_str(result, "required_tools", default="[]")
            )
        except json.JSONDecodeError:
            required_tools = []

        execution_plan = self.extract_str(result, "execution_plan", default="")
        complexity = self.extract_float(result, "estimated_complexity", default=0.5)

        # Store in memory
        self.write_to_memory(
            content={
                "task": task,
                "required_tools": required_tools,
                "execution_plan": execution_plan,
                "complexity": complexity,
            },
            tags=["task_analysis", "mcp"],
            importance=0.8,
        )

        return {
            "required_tools": required_tools,
            "execution_plan": execution_plan,
            "complexity": complexity,
        }

    async def invoke_tool(
        self, tool_id: str, user_request: str, context: str = ""
    ) -> Dict[str, Any]:
        """
        Invoke MCP tool using BaseAgent helper with real JSON-RPC 2.0 protocol.

        This uses BaseAgent.call_mcp_tool() for production MCP invocation.

        Args:
            tool_id: Full tool ID (format: "server_name:tool_name")
            user_request: User's request
            context: Execution context

        Returns:
            Tool invocation result
        """
        # Verify tool exists
        if tool_id not in self._available_mcp_tools:
            return {
                "success": False,
                "error": f"Tool {tool_id} not found",
                "available_tools": list(self._available_mcp_tools.keys()),
            }

        tool_data = self._available_mcp_tools[tool_id]
        tool_name = tool_data["name"]

        # Prepare tool arguments using LLM
        self.signature = ToolInvocationSignature()

        tool_schema_json = json.dumps(tool_data.get("inputSchema", {}), indent=2)

        preparation_result = self.run(
            tool_name=tool_name,
            tool_schema=tool_schema_json,
            user_request=user_request,
            context=context,
        )

        # Parse arguments
        try:
            tool_arguments = json.loads(
                self.extract_str(preparation_result, "tool_arguments", default="{}")
            )
        except json.JSONDecodeError:
            tool_arguments = {}

        reasoning = self.extract_str(
            preparation_result, "invocation_reasoning", default=""
        )

        logger.info(
            f"Invoking MCP tool: {tool_name} (ID: {tool_id})\n"
            f"Arguments: {json.dumps(tool_arguments, indent=2)}\n"
            f"Reasoning: {reasoning}"
        )

        # REAL MCP TOOL INVOCATION via BaseAgent helper
        invocation_result = await self.call_mcp_tool(
            tool_id=tool_id,
            arguments=tool_arguments,
            timeout=30.0,
            store_in_memory=True,  # Automatically stores in shared memory
        )

        return invocation_result

    async def execute_task(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Execute complete task using MCP tools (async).

        Full workflow:
        1. Analyze task to determine required tools
        2. Invoke each tool via real MCP protocol
        3. Synthesize results into final answer

        Args:
            task: User task
            context: Additional context

        Returns:
            Final execution result
        """
        logger.info(f"Executing task with MCP tools: {task}")

        # Step 1: Analyze task
        analysis = await self.analyze_task(task, context)
        required_tools = analysis["required_tools"]

        if not required_tools:
            return {
                "success": False,
                "error": "No tools identified for task",
                "analysis": analysis,
            }

        # Step 2: Invoke each tool (async)
        tool_results = []
        for tool_requirement in required_tools:
            tool_id = tool_requirement.get("tool_id")
            if not tool_id:
                continue

            result = await self.invoke_tool(
                tool_id=tool_id, user_request=task, context=context
            )

            tool_results.append({"tool_id": tool_id, "result": result})

        # Step 3: Synthesize results
        self.signature = ResultSynthesisSignature()

        synthesis_result = self.run(
            task_description=task,
            tool_results=json.dumps(tool_results, indent=2),
            execution_context=context,
        )

        final_answer = self.extract_str(synthesis_result, "final_answer", default="")
        confidence = self.extract_float(
            synthesis_result, "confidence_score", default=0.8
        )
        usage_summary = self.extract_str(
            synthesis_result, "tool_usage_summary", default=""
        )

        # Store final result
        self.write_to_memory(
            content={
                "task": task,
                "required_tools": required_tools,
                "tool_results": tool_results,
                "final_answer": final_answer,
                "confidence": confidence,
                "usage_summary": usage_summary,
            },
            tags=["task_execution", "mcp", "final_result"],
            importance=1.0,
        )

        return {
            "success": True,
            "task": task,
            "final_answer": final_answer,
            "confidence": confidence,
            "tool_usage_summary": usage_summary,
            "tool_results": tool_results,
            "execution_plan": analysis["execution_plan"],
        }


# ===================================================================
# EXAMPLE USAGE
# ===================================================================


async def example_basic_usage():
    """Example 1: Basic MCP client usage (async)."""
    print("=" * 70)
    print("Example 1: Basic MCP Client Usage")
    print("=" * 70)
    print()

    # Configure agent with MCP servers (transport-based)
    config = MCPClientConfig(
        mcp_servers=[
            {
                "name": "search-tools",
                "transport": "http",
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer demo-key"},
            },
            {
                "name": "compute-tools",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_compute_server"],
            },
        ]
    )

    # Create agent
    agent = MCPClientAgent(config)

    # Setup MCP connections (async)
    await agent._setup_mcp_connections()

    print(f"Available tools: {len(agent._available_mcp_tools)}")
    print()

    # List discovered tools
    print("Discovered MCP Tools:")
    print("-" * 70)
    for tool_id, tool_data in agent._available_mcp_tools.items():
        print(f"  • {tool_id}")
        print(f"    Description: {tool_data.get('description', 'N/A')}")
        print(f"    Server: {tool_data['server_config']['name']}")
    print()


async def example_task_execution():
    """Example 2: Execute task using MCP tools (async)."""
    print("=" * 70)
    print("Example 2: Task Execution with MCP Tools")
    print("=" * 70)
    print()

    config = MCPClientConfig()
    agent = MCPClientAgent(config)

    # Setup MCP (async)
    await agent._setup_mcp_connections()

    # Execute task (async)
    task = "Search for information about quantum computing and calculate 2^10"
    print(f"Task: {task}")
    print()

    result = await agent.execute_task(task)

    if result["success"]:
        print("Execution Result:")
        print("-" * 70)
        print(f"Answer: {result['final_answer']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print()
        print("Tool Usage:")
        print(result["tool_usage_summary"])
    else:
        print(f"Execution failed: {result.get('error')}")

    print()


async def example_multi_tool_workflow():
    """Example 3: Complex multi-tool workflow (async)."""
    print("=" * 70)
    print("Example 3: Multi-Tool Workflow")
    print("=" * 70)
    print()

    config = MCPClientConfig(
        mcp_servers=[
            {
                "name": "search-tools",
                "transport": "http",
                "url": "http://localhost:8080",
            },
            {
                "name": "compute-tools",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_compute_server"],
            },
            {"name": "data-tools", "transport": "http", "url": "http://localhost:8082"},
        ]
    )

    agent = MCPClientAgent(config)

    # Setup MCP (async)
    await agent._setup_mcp_connections()

    # Complex task requiring multiple tools
    task = (
        "Research current AI trends, analyze the data statistically, "
        "and compute growth projections for the next 5 years"
    )

    print(f"Complex Task: {task}")
    print()

    # Step 1: Analyze (async)
    print("Step 1: Analyzing task...")
    analysis = await agent.analyze_task(task)

    print(f"Required tools: {len(analysis['required_tools'])}")
    print(f"Complexity: {analysis['complexity']:.2f}")
    print()
    print("Execution Plan:")
    print(analysis["execution_plan"])
    print()

    # Step 2: Execute (async)
    print("Step 2: Executing with MCP tools...")
    result = await agent.execute_task(task)

    if result["success"]:
        print()
        print("Final Result:")
        print("-" * 70)
        print(result["final_answer"])

    print()


# ===================================================================
# MAIN
# ===================================================================


async def main_async():
    """Run all examples (async)."""
    print("\n")
    print("=" * 70)
    print("MCP Client Agent - Production MCP Examples")
    print("=" * 70)
    print()
    print("This example demonstrates PRODUCTION MCP usage:")
    print("  • Kailash SDK's production-ready MCPClient")
    print("  • Real JSON-RPC 2.0 protocol (no mocking)")
    print("  • BaseAgent helpers (setup_mcp_client, call_mcp_tool)")
    print("  • Multi-transport support (STDIO, HTTP, WebSocket, SSE)")
    print("  • Enterprise features (auth, retry, circuit breaker, metrics)")
    print()
    print("NOTE: Requires MCP servers configured in transport configs")
    print("=" * 70)
    print("\n")

    # Run examples (async)
    await example_basic_usage()
    print("\n")

    await example_task_execution()
    print("\n")

    await example_multi_tool_workflow()
    print("\n")

    print("=" * 70)
    print("Examples Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to use BaseAgent.setup_mcp_client() for MCP connections")
    print("  ✓ How to configure multi-transport MCP servers")
    print("  ✓ How to invoke tools using BaseAgent.call_mcp_tool()")
    print("  ✓ How to orchestrate multi-tool workflows asynchronously")
    print("  ✓ How to synthesize results from multiple tools")
    print()
    print("Production Features Used:")
    print("  → Circuit breaker retry strategy for resilience")
    print("  → Metrics collection for monitoring")
    print("  → Automatic tool result caching")
    print("  → Multi-transport support (STDIO, HTTP, WebSocket)")
    print("  → Authentication via headers/tokens")
    print("  → Automatic memory storage for tool calls")
    print()
    print("Migration from kaizen.mcp to kailash.mcp_server:")
    print("  → Replaced MCPConnection with BaseAgent.setup_mcp_client()")
    print("  → Replaced manual tool invocation with call_mcp_tool()")
    print("  → Added async/await for all MCP methods")
    print("  → Switched to transport-based server configuration")
    print("  → Using production JSON-RPC protocol (no mocking)")
    print()


def main():
    """Entry point."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run async main
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
