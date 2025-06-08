#!/usr/bin/env python3
"""
MCP Client Integration Example - New Architecture
=================================================

This example demonstrates the new MCP architecture where MCP is a built-in
capability of LLM agents rather than a separate node.

Key Changes:
- MCPClient is no longer a standalone node
- MCP functionality is integrated into LLMAgentNode
- MCP servers are configured directly in the agent

This example shows:
- How to configure LLM agents with MCP servers
- Automatic tool discovery and usage
- Resource retrieval through MCP

To run this example, you need to have the filesystem MCP server installed:
    npm install -g @modelcontextprotocol/server-filesystem
"""

import json
import shutil
import tempfile
from pathlib import Path

from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime import LocalRuntime


def create_test_files():
    """Create temporary test files for the filesystem server."""
    temp_dir = tempfile.mkdtemp(prefix="mcp_test_")

    # Create some test files
    test_files = {
        "README.md": "# MCP Test Files\n\nThis directory contains test files for the MCP filesystem server.",
        "data.json": json.dumps(
            {"name": "Test Data", "value": 42, "items": ["apple", "banana", "cherry"]},
            indent=2,
        ),
        "config.yaml": "server:\n  host: localhost\n  port: 8080\n\nfeatures:\n  - search\n  - index\n  - cache",
        "sample.txt": "This is a sample text file.\nIt has multiple lines.\nUsed for testing MCP operations.",
    }

    for filename, content in test_files.items():
        filepath = Path(temp_dir) / filename
        filepath.write_text(content)

    return temp_dir


def show_deprecated_pattern():
    """Show why the old pattern is deprecated."""
    print("DEPRECATED PATTERN - DO NOT USE")
    print("=" * 70)
    print("\nThe following pattern is no longer supported:")
    print("❌ workflow.add_node('mcp_client', MCPClientNode())")
    print("\nMCPClient is no longer available as a node.")
    print("Instead, MCP is now a built-in capability of LLM agents.")
    print("\nReason: MCP servers need to be long-lived services,")
    print("not ephemeral nodes in a workflow.")


def show_recommended_pattern():
    """Show the recommended pattern using LLMAgentNode."""
    print("\n\nRECOMMENDED PATTERN - USE THIS INSTEAD")
    print("=" * 70)
    print("\nUse LLMAgentNode with built-in MCP capabilities:")
    print(
        "✅ workflow.add_node('agent', LLMAgentNode(mcp_servers=['http://localhost:8080']))"
    )
    print("\nExample workflow with LLMAgentNode:")

    # Show example code (now fully functional!)
    example_code = """
    from kailash.nodes.ai import LLMAgentNode

    # Create workflow
    workflow = Workflow("mcp-integrated", name="mcp_integrated")

    # Add LLM agent with MCP servers
    workflow.add_node("agent", LLMAgentNode(name="agent"))

    # The agent automatically discovers and uses MCP tools
    parameters = {
        "agent": {
            "provider": "ollama",
            "model": "llama3.1:8b-instruct-q8_0",
            "messages": [
                {"role": "user", "content": "List all JSON files and summarize their contents"}
            ],
            "mcp_servers": [
                "http://localhost:8080",     # HTTP transport
                {                            # Stdio transport
                    "name": "filesystem",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
                }
            ],
            "auto_discover_tools": True
        }
    }
    """

    print(example_code)
    print(
        "\nNote: This pattern is now fully functional with the enhanced LLMAgentNode!"
    )


def demonstrate_llm_agent_with_mcp():
    """Demonstrate LLMAgentNode with MCP integration."""
    print("\n\nRECOMMENDED APPROACH - LLMAgentNode with MCP")
    print("=" * 70)
    print("\nThis demonstrates the proper way to use MCP capabilities.")

    # Create test files
    test_dir = create_test_files()
    print(f"\nCreated test directory: {test_dir}")

    # Create workflow with LLM agent
    workflow = Workflow("mcp-demo", "MCP Integration Demo")
    workflow.add_node("agent", LLMAgentNode())

    # Configure agent with MCP servers
    parameters = {
        "agent": {
            "provider": "mock",  # Use mock provider for demo
            "model": "demo-model",
            "messages": [
                {"role": "user", "content": "List all files and analyze the JSON data"}
            ],
            "mcp_servers": [
                {
                    "name": "filesystem",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", test_dir],
                }
            ],
            "auto_discover_tools": True,
            "mcp_context": [f"file://{test_dir}/data.json"],
        }
    }

    # Execute workflow
    runtime = LocalRuntime()
    print("\nExecuting workflow with MCP-enabled agent...")

    try:
        results, execution_id = runtime.execute(workflow, parameters)

        if results.get("agent", {}).get("success"):
            agent_result = results["agent"]
            print("\n✅ LLMAgentNode with MCP executed successfully!")
            print("\n📝 Agent Response:")
            print(agent_result.get("response", {}).get("content", "No response"))

            context = agent_result.get("context", {})
            print("\n📊 MCP Context Used:")
            print(f"   - Resources: {context.get('mcp_resources_used', 0)}")
            print(f"   - Tools available: {context.get('tools_available', 0)}")
        else:
            print(
                "\n❌ Workflow execution failed:", results.get("agent", {}).get("error")
            )
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")

    # Cleanup
    shutil.rmtree(test_dir)
    print("\n✅ This is the recommended approach for MCP integration!")


def main():
    """Run MCP client migration examples."""
    print("\n" + "=" * 70)
    print("MCP CLIENT MIGRATION GUIDE")
    print("=" * 70)

    # Show deprecated pattern
    show_deprecated_pattern()

    # Show recommended pattern
    show_recommended_pattern()

    # Demonstrate the recommended approach
    demonstrate_llm_agent_with_mcp()

    print("\n" + "=" * 70)
    print("MCP Client Migration Guide completed!")
    print("\nKey Takeaways:")
    print("1. MCPClient is no longer a node - it's a service capability")
    print("2. Use LLMAgentNode with mcp_servers parameter for MCP integration")
    print("3. MCP servers are configured directly on the agent")
    print("\nFor more information, see the documentation on MCP integration.")


if __name__ == "__main__":
    main()
