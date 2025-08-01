"""
Example: Multi-Tool Agent
Description: Agent using multiple MCP servers for different capabilities
Requirements: None (uses mock servers for demonstration)
"""

from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    # Create workflow
    workflow = WorkflowBuilder()

    # Add multi-capable agent
    workflow.add_node("LLMAgentNode", "multi_agent", {})

    # Create runtime
    runtime = LocalRuntime()

    # Execute with multiple MCP servers
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={
            "multi_agent": {
                # LLM configuration
                "provider": "ollama",  # or "openai", "anthropic"
                "model": "llama3.2",  # or "gpt-4", "claude-3"
                # Real MCP execution is now always enabled
                # Complex request requiring multiple tools
                "messages": [
                    {
                        "role": "user",
                        "content": "Get the current weather in New York, calculate if I need a jacket "
                        "(below 60°F), and save the recommendation to a file.",
                    }
                ],
                # Multiple MCP servers
                "mcp_servers": [
                    {
                        "name": "weather-service",
                        "transport": "http",
                        "url": "http://localhost:8081",  # Mock weather API
                        "headers": {"API-Key": "demo-key"},
                    },
                    {
                        "name": "calculator",
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "mcp_calc_server"],  # Mock calculator
                    },
                    {
                        "name": "file-system",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-filesystem", "./output"],
                    },
                ],
                # Enable all MCP features
                "auto_discover_tools": True,
                "auto_execute_tools": True,
                # Advanced configuration
                "tool_discovery_config": {
                    "cache_discoveries": True,
                    "parallel_discovery": True,
                },
                "tool_execution_config": {
                    "max_rounds": 5,
                    "parallel": True,
                    "timeout": 120,
                },
            }
        },
    )

    # Display results
    if results["multi_agent"]["success"]:
        print("Multi-Tool Agent Response:")
        print("=" * 70)
        print(results["multi_agent"]["response"])

        # Show detailed execution info
        if "context" in results["multi_agent"]:
            context = results["multi_agent"]["context"]

            # Tools discovered
            if "tools_available" in context and isinstance(
                context["tools_available"], list
            ):
                print("\nDiscovered Tools:")
                print("-" * 70)
                tools_by_server = {}
                for tool in context["tools_available"]:
                    server = tool.get("server", "unknown")
                    if server not in tools_by_server:
                        tools_by_server[server] = []
                    tools_by_server[server].append(tool.get("name", "unknown"))

                for server, tools in tools_by_server.items():
                    print(f"\n{server}:")
                    for tool in tools:
                        print(f"  - {tool}")

            # Tools executed
            if "tools_executed" in context and isinstance(
                context["tools_executed"], list
            ):
                print("\nExecution Flow:")
                print("-" * 70)
                for i, execution in enumerate(context["tools_executed"], 1):
                    print(
                        f"{i}. {execution.get('tool', 'unknown')} "
                        f"({execution.get('server', 'unknown')})"
                    )
                    print(f"   Status: {execution.get('status', 'unknown')}")
                    if "result" in execution:
                        print(f"   Result: {execution['result']}")
    else:
        print(f"Error: {results['multi_agent']['error']}")

    # Mock example for demonstration
    print("\n" + "=" * 70)
    print("Mock Execution (for demonstration without real servers)")
    print("-" * 70)

    mock_results, _ = runtime.execute(
        workflow.build(),
        parameters={
            "multi_agent": {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {
                        "role": "user",
                        "content": "Get weather, check if I need a jacket, save recommendation",
                    }
                ],
                "mcp_servers": [
                    {"name": "weather", "transport": "stdio", "command": "echo"},
                    {"name": "calc", "transport": "stdio", "command": "echo"},
                    {"name": "files", "transport": "stdio", "command": "echo"},
                ],
                "mock_response": """I'll help you with that! Let me use the available tools to:
1. Get the current weather in New York
2. Check if you need a jacket
3. Save the recommendation

**Step 1: Getting Weather Data**
Tool: get_weather (weather-service)
Result: Current temperature in New York: 55°F, Partly cloudy

**Step 2: Checking Jacket Requirement**
Tool: compare_temperature (calculator)
Result: 55°F is below 60°F - Jacket recommended!

**Step 3: Saving Recommendation**
Tool: write_file (file-system)
Result: Saved to 'weather_recommendation.txt'

**Summary:**
✓ Current temperature: 55°F
✓ Jacket needed: Yes (below 60°F threshold)
✓ Recommendation saved to file

The weather in New York is currently 55°F with partly cloudy skies. Since this is below your 60°F threshold, I recommend wearing a jacket. I've saved this recommendation to 'weather_recommendation.txt' for your reference.""",
            }
        },
    )

    if mock_results["multi_agent"]["success"]:
        print(mock_results["multi_agent"]["response"])


def show_advanced_example():
    """Show advanced multi-tool coordination pattern"""
    print("\n" + "=" * 70)
    print("Advanced Pattern: Tool Coordination")
    print("-" * 70)
    print(
        """
# Advanced multi-tool workflow with dependencies
workflow = WorkflowBuilder()

# Data collector agent
workflow.add_node("LLMAgentNode", "collector", {})

# Data processor agent
workflow.add_node("LLMAgentNode", "processor", {})

# Connect agents
workflow.add_connection("collector", "data", "processor", "input_data")

# Collector gathers from multiple sources
collector_params = {
    "mcp_servers": [
        {"name": "database", "transport": "stdio", "command": "mcp-sqlite"},
        {"name": "api", "transport": "http", "url": "http://api.example.com"},
        {"name": "files", "transport": "stdio", "command": "mcp-fs"}
    ],
    "messages": [{"role": "user", "content": "Gather all customer data"}]
}

# Processor analyzes collected data
processor_params = {
    "mcp_servers": [
        {"name": "analytics", "transport": "stdio", "command": "mcp-analytics"},
        {"name": "ml-models", "transport": "http", "url": "http://ml.example.com"}
    ],
    "messages": [{"role": "user", "content": "Analyze the collected data"}]
}
"""
    )


if __name__ == "__main__":
    print("Multi-Tool Agent Example")
    print("=" * 70)
    print("This example demonstrates:")
    print("- Using multiple MCP servers simultaneously")
    print("- Coordinating tools from different sources")
    print("- Handling complex multi-step operations")
    print("\nRunning example...\n")

    main()
    show_advanced_example()
