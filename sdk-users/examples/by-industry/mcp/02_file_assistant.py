"""
Example: File Assistant
Description: MCP-enabled agent that can read and analyze files
Requirements: @modelcontextprotocol/server-filesystem (optional)
"""

import os

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    # Create workflow
    workflow = WorkflowBuilder()

    # Add file analysis agent
    workflow.add_node("LLMAgentNode", "file_agent", {})

    # Create runtime
    runtime = LocalRuntime()

    # Current directory for demo
    current_dir = os.getcwd()

    # Execute workflow
    results, run_id = runtime.execute(
        workflow,
        parameters={
            "file_agent": {
                # Configuration
                "provider": "ollama",  # Change to "openai" or "anthropic" as needed
                "model": "llama3.2",  # Change to "gpt-4" or "claude-3" as needed
                # Real MCP execution is now always enabled
                # Request to analyze files
                "messages": [
                    {
                        "role": "user",
                        "content": "List all Python files in the current directory and tell me what they do",
                    }
                ],
                # MCP filesystem server
                "mcp_servers": [
                    {
                        "name": "filesystem",
                        "transport": "stdio",
                        "command": "npx",
                        "args": [
                            "@modelcontextprotocol/server-filesystem",
                            current_dir,
                        ],
                    }
                ],
                # Enable automatic tool discovery and execution
                "auto_discover_tools": True,
                "auto_execute_tools": True,
                # Tool execution configuration
                "tool_execution_config": {"max_rounds": 3, "timeout": 60},
            }
        },
    )

    # Display results
    if results["file_agent"]["success"]:
        print("File Assistant Response:")
        print("=" * 70)
        print(results["file_agent"]["response"])

        # Show tool execution details
        if "context" in results["file_agent"]:
            context = results["file_agent"]["context"]
            if "tools_executed" in context and isinstance(
                context["tools_executed"], list
            ):
                print("\nTools Executed:")
                print("-" * 70)
                for execution in context["tools_executed"]:
                    print(f"Tool: {execution.get('tool', 'unknown')}")
                    print(f"Status: {execution.get('status', 'unknown')}")
                    if "error" in execution:
                        print(f"Error: {execution['error']}")
                    print()
    else:
        print(f"Error: {results['file_agent']['error']}")

    # Alternative without real MCP server
    print("\n" + "=" * 70)
    print("Alternative: Using mock mode (no MCP server required)")
    print("-" * 70)

    # Re-run with mock
    mock_results, _ = runtime.execute(
        workflow,
        parameters={
            "file_agent": {
                "provider": "mock",
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "List Python files and their purposes"}
                ],
                "mcp_servers": [
                    {
                        "name": "mock-fs",
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["mock"],
                    }
                ],
                "mock_response": """I've analyzed the Python files in the current directory:

1. **01_simple_mcp_agent.py**
   - Demonstrates basic MCP agent setup
   - Shows how to configure MCP servers
   - Includes tool discovery example

2. **02_file_assistant.py** (this file)
   - Shows file system integration via MCP
   - Demonstrates automatic tool execution
   - Includes both real and mock examples

3. **03_multi_tool_agent.py**
   - Example of using multiple MCP servers
   - Shows tool coordination
   - Demonstrates complex workflows

Each file includes detailed comments and can run in mock mode for testing.""",
            }
        },
    )

    if mock_results["file_agent"]["success"]:
        print(mock_results["file_agent"]["response"])


if __name__ == "__main__":
    print("File Assistant Example")
    print("=" * 70)
    print("This example shows how to create an AI agent that can:")
    print("- Access the file system through MCP")
    print("- List and analyze files")
    print("- Execute file operations automatically")
    print("\nRunning example...\n")

    main()
