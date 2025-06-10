#!/usr/bin/env python3
"""
LLM Agent with MCP Integration Example
======================================

This example demonstrates the new pattern for using LLMAgentNode with built-in
MCP (Model Context Protocol) capabilities. MCPClient is no longer a separate node
but is integrated directly into LLMAgentNode.

Key Features Demonstrated:
- Built-in MCP server connectivity
- Automatic tool discovery from MCP servers
- Context retrieval from MCP resources
- Seamless integration with LLM conversations

Migration from old pattern:
- Old: workflow.add_node("mcp", MCPClient()) + workflow.add_node("agent", LLMAgentNode())
- New: workflow.add_node("agent", LLMAgentNode(mcp_servers=[...]))
"""


from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime import LocalRuntime


def demonstrate_mcp_integration():
    """Demonstrate LLMAgentNode with integrated MCP support."""
    print("LLM Agent with MCP Integration (Using Ollama)")
    print("=" * 70)

    # Create workflow
    workflow = Workflow("llm-mcp-demo", name="llm_mcp_demo")

    # Add LLM agent with MCP servers configured
    workflow.add_node("agent", LLMAgentNode(name="mcp_enabled_agent"))

    # Create runtime
    runtime = LocalRuntime()

    # Example 1: Basic MCP context retrieval
    print("\n1. Basic MCP Context Retrieval")
    print("-" * 30)

    parameters = {
        "agent": {
            "provider": "ollama",
            "model": "llama3.1:8b-instruct-q8_0",
            "messages": [
                {
                    "role": "user",
                    "content": "What data is available in the MCP servers?",
                }
            ],
            "mcp_servers": [
                {
                    "name": "data-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "mcp_data_server"],
                }
            ],
            "mcp_context": ["data://sales/2024", "resource://templates/analysis"],
        }
    }

    results, _ = runtime.execute(workflow, parameters=parameters)

    if results["agent"]["success"]:
        print(f"✅ Response: {results['agent']['response']['content']}")
        print(
            f"   MCP resources used: {results['agent']['context']['mcp_resources_used']}"
        )
    else:
        print(f"❌ Error: {results['agent']['error']}")

    # Example 2: Automatic MCP tool discovery
    print("\n2. Automatic MCP Tool Discovery")
    print("-" * 30)

    parameters["agent"]["messages"] = [
        {"role": "user", "content": "Search for customer data from last quarter"}
    ]
    parameters["agent"]["auto_discover_tools"] = True

    results, _ = runtime.execute(workflow, parameters=parameters)

    if results["agent"]["success"]:
        print(f"✅ Response: {results['agent']['response']['content']}")
        print(f"   Tools available: {results['agent']['context']['tools_available']}")
    else:
        print(f"❌ Error: {results['agent']['error']}")

    # Example 3: Multiple MCP servers
    print("\n3. Multiple MCP Servers")
    print("-" * 30)

    parameters["agent"]["mcp_servers"] = [
        {"name": "data-server", "transport": "stdio", "command": "mcp-data-server"},
        {
            "name": "api-server",
            "transport": "http",
            "url": "http://localhost:8080",
            "headers": {"Authorization": "Bearer token"},
        },
    ]
    parameters["agent"]["messages"] = [
        {"role": "user", "content": "Combine data from both servers to create a report"}
    ]

    results, _ = runtime.execute(workflow, parameters=parameters)

    if results["agent"]["success"]:
        print(f"✅ Response: {results['agent']['response']['content']}")
        metadata = results["agent"]["metadata"]
        print(f"   Provider: {metadata['provider']}, Model: {metadata['model']}")
    else:
        print(f"❌ Error: {results['agent']['error']}")


def demonstrate_migration_pattern():
    """Show the migration from old MCPClient pattern to new integrated pattern."""
    print("\n\nMigration Pattern Demonstration")
    print("=" * 70)

    print("\n❌ OLD PATTERN (Deprecated):")
    print("```python")
    print("# This required two separate nodes and manual connection")
    print("workflow.add_node('mcp_client', MCPClient())")
    print("workflow.add_node('agent', LLMAgentNode())")
    print("workflow.connect('mcp_client', 'agent')")
    print("```")

    print("\n✅ NEW PATTERN (Recommended):")
    print("```python")
    print("# Single node with integrated MCP support")
    print("workflow.add_node('agent', LLMAgentNode(name='mcp_agent'))")
    print("")
    print("# Configure MCP servers in parameters")
    print("parameters = {")
    print("    'agent': {")
    print("        'mcp_servers': [...],")
    print("        'mcp_context': [...],")
    print("        'auto_discover_tools': True")
    print("    }")
    print("}")
    print("```")

    print("\nBenefits of new pattern:")
    print("• Simpler workflow setup")
    print("• Automatic tool integration")
    print("• Better error handling")
    print("• Seamless context injection")
    print("• No manual wiring needed")


def demonstrate_advanced_features():
    """Demonstrate advanced MCP integration features."""
    print("\n\nAdvanced MCP Integration Features")
    print("=" * 70)

    workflow = Workflow("advanced-mcp", name="advanced_mcp")
    workflow.add_node("agent", LLMAgentNode(name="advanced_agent"))

    runtime = LocalRuntime()

    # Example: MCP with RAG integration
    print("\n1. MCP + RAG Integration")
    print("-" * 30)

    parameters = {
        "agent": {
            "provider": "ollama",
            "model": "llama3.1:8b-instruct-q8_0",
            "messages": [
                {
                    "role": "user",
                    "content": "Find and summarize our compliance policies",
                }
            ],
            "mcp_servers": [
                {
                    "name": "knowledge-base",
                    "transport": "stdio",
                    "command": "mcp-kb-server",
                }
            ],
            "rag_config": {"enabled": True, "top_k": 5, "similarity_threshold": 0.7},
            "auto_discover_tools": True,
        }
    }

    results, _ = runtime.execute(workflow, parameters=parameters)

    if results["agent"]["success"]:
        print("✅ Combined MCP + RAG response generated")
        context = results["agent"]["context"]
        print(f"   MCP resources: {context['mcp_resources_used']}")
        print(f"   RAG documents: {context['rag_documents_retrieved']}")

    # Example: Tool calling with MCP
    print("\n2. MCP Tool Calling")
    print("-" * 30)

    parameters["agent"]["messages"] = [
        {"role": "user", "content": "Create a sales report for Q4 2024"}
    ]
    parameters["agent"]["generation_config"] = {
        "temperature": 0,  # Use 0 for tool calling
        "tool_choice": "auto",
    }

    results, _ = runtime.execute(workflow, parameters=parameters)

    if results["agent"]["success"]:
        response = results["agent"]["response"]
        if "tool_calls" in response:
            print(f"✅ Agent called {len(response['tool_calls'])} MCP tools")
            for call in response["tool_calls"]:
                print(f"   - {call['function']['name']}")
        else:
            print(f"✅ Response: {response['content']}")


def main():
    """Run all MCP integration examples."""
    # Basic integration
    demonstrate_mcp_integration()

    # Migration pattern
    demonstrate_migration_pattern()

    # Advanced features
    demonstrate_advanced_features()

    print("\n" + "=" * 70)
    print("MCP Integration Examples Completed!")
    print("\nKey Takeaways:")
    print("1. MCPClient is now internal - use LLMAgentNode directly")
    print("2. Configure MCP servers via the mcp_servers parameter")
    print("3. Enable auto_discover_tools for automatic tool integration")
    print("4. MCP context is seamlessly injected into conversations")
    print("5. Works with RAG, tool calling, and all LLM features")
    print("\nFor more information, see the documentation on MCP integration.")


if __name__ == "__main__":
    main()
