"""
Example: Simple MCP Agent
Description: Basic example of an LLM agent using MCP tools
Requirements: None (uses mock provider for demonstration)
"""

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    # Create workflow
    workflow = WorkflowBuilder()

    # Add LLM agent node
    workflow.add_node("LLMAgentNode", "assistant", {})

    # Create runtime
    runtime = LocalRuntime()

    # Execute with MCP configuration
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={
            "assistant": {
                # Use mock provider for testing (no API key needed)
                "provider": "mock",
                "model": "gpt-4",
                # Using mock provider for this example (no real MCP needed)
                # User message
                "messages": [
                    {"role": "user", "content": "What tools do you have available?"}
                ],
                # MCP server configuration
                "mcp_servers": [
                    {
                        "name": "demo-tools",
                        "transport": "stdio",
                        "command": "echo",  # Mock server
                        "args": ["mock-mcp-server"],
                    }
                ],
                # Enable tool discovery
                "auto_discover_tools": True,
                # Mock response for demonstration
                "mock_response": """I have discovered the following tools:

1. **calculate_sum** - Add two numbers together
2. **get_weather** - Get weather information for a city
3. **search_files** - Search for files in a directory

These tools are available through the MCP server 'demo-tools'. Would you like me to use any of them?""",
            }
        },
    )

    # Display results
    if results["assistant"]["success"]:
        print("Assistant Response:")
        print("-" * 50)
        print(results["assistant"]["response"])

        # Show tool discovery info if available
        if "context" in results["assistant"]:
            context = results["assistant"]["context"]
            if "tools_available" in context and isinstance(
                context["tools_available"], list
            ):
                print("\nDiscovered Tools:")
                print("-" * 50)
                for tool in context["tools_available"]:
                    print(f"- {tool}")
    else:
        print(f"Error: {results['assistant']['error']}")


if __name__ == "__main__":
    main()

    print("\n" + "=" * 50)
    print("To use with a real LLM, change:")
    print('  provider: "ollama" (for local)')
    print('  provider: "openai" (requires OPENAI_API_KEY)')
    print('  provider: "anthropic" (requires ANTHROPIC_API_KEY)')
