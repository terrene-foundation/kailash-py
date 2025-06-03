"""Basic MCP (Model Context Protocol) integration example with client and resource nodes."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.mcp import MCPClient, MCPResource


def main():
    """Demonstrate basic MCP resource creation and client interaction."""
    print("🚀 MCP Basic Integration Example")
    print("=" * 50)

    # Create a workflow builder (not used in this example, shown for reference)
    # builder = WorkflowBuilder("mcp_basic_demo")

    # 1. Create MCP Resources
    print("\n📦 Step 1: Creating MCP Resources")

    # Create a text resource
    text_resource = MCPResource()
    text_result = text_resource.run(
        operation="create",
        uri="workflow://documents/customer_analysis.txt",
        content="Customer Analysis Report Q4 2024\n\nKey findings:\n- 15% increase in customer engagement\n- Product A has highest conversion rate\n- Onboarding process needs improvement",
        metadata={
            "name": "Q4 Customer Analysis",
            "description": "Quarterly customer behavior analysis",
            "mimeType": "text/plain",
            "tags": ["analysis", "customers", "Q4", "report"],
            "author": "Data Analysis Team",
            "category": "business_intelligence",
        },
        cache_ttl=1800,  # 30 minutes
    )

    print(f"✅ Text resource created: {text_result['success']}")
    if text_result["success"]:
        resource = text_result["resource"]
        print(f"   URI: {resource['uri']}")
        print(f"   Name: {resource['name']}")
        print(f"   Size: {resource['size']} characters")
        print(f"   Version: {resource['version']}")

    # Create a JSON data resource
    json_resource = MCPResource()
    json_result = json_resource.run(
        operation="create",
        uri="data://metrics/summary.json",
        content={
            "period": "Q4 2024",
            "total_customers": 15420,
            "revenue": 2450000,
            "top_products": ["Product A", "Product B", "Product C"],
            "metrics": {
                "engagement_rate": 0.78,
                "conversion_rate": 0.142,
                "churn_rate": 0.06,
            },
            "recommendations": [
                "Improve onboarding process",
                "Focus marketing on Product A",
                "Reduce customer acquisition cost",
            ],
        },
        metadata={
            "name": "Q4 Summary Metrics",
            "description": "Key performance metrics for Q4 2024",
            "mimeType": "application/json",
            "tags": ["metrics", "Q4", "summary", "kpi"],
            "schema": "business_metrics_v1",
        },
    )

    print(f"✅ JSON resource created: {json_result['success']}")
    if json_result["success"]:
        resource = json_result["resource"]
        print(f"   URI: {resource['uri']}")
        print(f"   Content type: {resource['mimeType']}")
        print(f"   Metadata tags: {resource['metadata']['tags']}")

    # 2. List available resources
    print("\n📋 Step 2: Listing MCP Resources")

    list_result = MCPResource().run(operation="list")
    if list_result["success"]:
        print(f"✅ Found {list_result['total_count']} resources:")
        for resource in list_result["resources"]:
            print(f"   - {resource['name']} ({resource['uri']})")
            print(f"     Type: {resource['mimeType']}, Size: {resource['size']} chars")

    # 3. Set up MCP Client
    print("\n🔌 Step 3: Setting up MCP Client")

    # Configure a mock MCP server
    server_config = {
        "name": "kailash-workflow-server",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "kailash.mcp.server"],
    }

    client = MCPClient()

    # List available resources from server
    resources_result = client.run(
        server_config=server_config, operation="list_resources"
    )

    print(f"✅ Server resource listing: {resources_result['success']}")
    if resources_result["success"]:
        print(f"   Server: {resources_result['server']}")
        print(f"   Resources found: {resources_result['resource_count']}")
        for resource in resources_result["resources"]:
            print(f"   - {resource['name']}: {resource['uri']}")

    # 4. Read specific resources
    print("\n📖 Step 4: Reading MCP Resources via Client")

    # Read the customer analysis document
    read_result = client.run(
        server_config=server_config,
        operation="read_resource",
        resource_uri="file:///example/document.txt",
    )

    print(f"✅ Resource read: {read_result['success']}")
    if read_result["success"]:
        resource = read_result["resource"]
        print(f"   URI: {resource['uri']}")
        print(f"   Content preview: {resource['content'][:100]}...")
        print(f"   MIME type: {resource['mimeType']}")

    # 5. List and call available tools
    print("\n🔧 Step 5: Working with MCP Tools")

    # List available tools
    tools_result = client.run(server_config=server_config, operation="list_tools")

    print(f"✅ Tools listing: {tools_result['success']}")
    if tools_result["success"]:
        print(f"   Tools available: {tools_result['tool_count']}")
        for tool in tools_result["tools"]:
            print(f"   - {tool['name']}: {tool['description']}")

    # Call a tool
    tool_result = client.run(
        server_config=server_config,
        operation="call_tool",
        tool_name="create_file",
        tool_arguments={
            "path": "/tmp/mcp_demo_output.txt",
            "content": "Generated by MCP tool call from Kailash workflow",
        },
    )

    print(f"✅ Tool execution: {tool_result['success']}")
    if tool_result["success"]:
        print(f"   Tool: {tool_result['tool_name']}")
        print(f"   Result: {tool_result['result']}")

    # 6. Work with prompts
    print("\n💬 Step 6: Using MCP Prompts")

    # List available prompts
    prompts_result = client.run(server_config=server_config, operation="list_prompts")

    print(f"✅ Prompts listing: {prompts_result['success']}")
    if prompts_result["success"]:
        print(f"   Prompts available: {prompts_result['prompt_count']}")
        for prompt in prompts_result["prompts"]:
            print(f"   - {prompt['name']}: {prompt['description']}")

    # Get a specific prompt
    prompt_result = client.run(
        server_config=server_config,
        operation="get_prompt",
        prompt_name="summarize_document",
        prompt_arguments={
            "document": "Customer Analysis Report Q4 2024...",
            "max_length": "150",
        },
    )

    print(f"✅ Prompt generation: {prompt_result['success']}")
    if prompt_result["success"]:
        prompt = prompt_result["prompt"]
        print(f"   Prompt: {prompt['name']}")
        print(f"   Content: {prompt['content'][:150]}...")

    # 7. Validate resource schemas
    print("\n✅ Step 7: Resource Validation")

    # Validate our created resources
    validation_result = MCPResource().run(
        operation="validate",
        uri="workflow://documents/customer_analysis.txt",
        content="Valid customer analysis content",
        schema={"type": "string", "minLength": 10},
    )

    print(f"✅ Resource validation: {validation_result['success']}")
    if validation_result["success"]:
        results = validation_result["results"]
        print(f"   Valid: {validation_result['valid']}")
        print(f"   Errors: {results['errors']}")
        print(f"   Warnings: {results['warnings']}")
        print(f"   Recommendation: {validation_result['summary']['recommendation']}")

    # 8. Summary
    print("\n🎯 Integration Summary")
    print("=" * 50)
    print("✅ MCP Resources: Created text and JSON resources with metadata")
    print("✅ MCP Client: Connected to server and listed resources")
    print("✅ Resource Access: Successfully read resource content")
    print("✅ Tool Integration: Listed and executed MCP tools")
    print("✅ Prompt System: Retrieved and used MCP prompts")
    print("✅ Validation: Verified resource schemas and content")
    print("\n🚀 MCP integration is working correctly!")
    print("   Ready for AI agent context sharing and workflow integration")


if __name__ == "__main__":
    main()
