#!/usr/bin/env python3
"""
MCP Capability Mixin Example
============================

This example demonstrates how to add MCP capabilities to any node
using the MCPCapabilityMixin, without requiring it to be an LLM agent.

Key Concepts:
- MCPCapabilityMixin adds MCP client functionality to any node
- Nodes can discover tools, call them, and access resources
- Both sync and async methods are available

Use Cases:
- Data processing nodes that need external tools
- Validation nodes that check against MCP resources
- Integration nodes that bridge MCP services
"""

from typing import Any, Dict

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.mixins import MCPCapabilityMixin
from kailash.runtime import LocalRuntime


class DataEnrichmentNode(Node, MCPCapabilityMixin):
    """Example node that enriches data using MCP tools.

    This node demonstrates how a non-LLM node can use MCP
    capabilities to enhance its functionality.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define node parameters including MCP configuration."""
        return {
            "data": NodeParameter(
                name="data", type=list, required=True, description="Data to enrich"
            ),
            "mcp_servers": NodeParameter(
                name="mcp_servers",
                type=list,
                required=False,
                default=[],
                description="MCP servers to use for enrichment",
            ),
            "enrichment_tool": NodeParameter(
                name="enrichment_tool",
                type=str,
                required=False,
                default="enrich_data",
                description="Name of the MCP tool to use",
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Enrich data using MCP tools."""
        data = kwargs.get("data", [])
        mcp_servers = kwargs.get("mcp_servers", [])
        tool_name = kwargs.get("enrichment_tool", "enrich_data")

        # Check if we have MCP servers configured
        if not mcp_servers:
            return {
                "enriched_data": data,
                "enrichment_applied": False,
                "message": "No MCP servers configured",
            }

        # Discover available tools
        try:
            tools = self.discover_mcp_tools_sync(mcp_servers)
            available_tools = [t["function"]["name"] for t in tools]

            if tool_name not in available_tools:
                return {
                    "enriched_data": data,
                    "enrichment_applied": False,
                    "message": f"Tool '{tool_name}' not found. Available: {available_tools}",
                }

            # Call the enrichment tool
            result = self.call_mcp_tool_sync(
                mcp_servers[0], tool_name, {"data": data}  # Use first server
            )

            return {
                "enriched_data": result,
                "enrichment_applied": True,
                "tools_discovered": len(tools),
                "message": f"Data enriched using '{tool_name}'",
            }

        except Exception as e:
            return {
                "enriched_data": data,
                "enrichment_applied": False,
                "error": str(e),
                "message": f"Failed to enrich data: {e}",
            }


class MCPResourceValidatorNode(Node, MCPCapabilityMixin):
    """Validates data against MCP resources."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=dict, required=True),
            "mcp_server": NodeParameter(name="mcp_server", type=str, required=True),
            "validation_resource": NodeParameter(
                name="validation_resource",
                type=str,
                required=True,
                description="URI of the validation resource",
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Validate data against MCP resource."""
        data = kwargs.get("data", {})
        server = kwargs.get("mcp_server")
        resource_uri = kwargs.get("validation_resource")

        try:
            # Read validation rules from MCP resource
            validation_rules = self.read_mcp_resource_sync(server, resource_uri)

            # Simple validation example
            valid = True
            errors = []

            if isinstance(validation_rules, dict):
                for field, rule in validation_rules.items():
                    if field not in data:
                        errors.append(f"Missing required field: {field}")
                        valid = False
                    elif "type" in rule:
                        expected_type = rule["type"]
                        if not isinstance(data[field], eval(expected_type)):
                            errors.append(f"Field '{field}' should be {expected_type}")
                            valid = False

            return {
                "data": data,
                "valid": valid,
                "errors": errors,
                "validation_resource": resource_uri,
            }

        except Exception as e:
            return {
                "data": data,
                "valid": False,
                "errors": [f"Validation failed: {e}"],
                "validation_resource": resource_uri,
            }


def demonstrate_mcp_mixin():
    """Demonstrate using MCP mixin with custom nodes."""
    print("MCP CAPABILITY MIXIN DEMONSTRATION")
    print("=" * 70)

    # Create workflow
    workflow = Workflow("mcp-mixin-demo", "MCP Mixin Example")

    # Add nodes
    workflow.add_node("generator", PythonCodeNode())
    workflow.add_node("enricher", DataEnrichmentNode())
    workflow.add_node("validator", MCPResourceValidatorNode())

    # Connect nodes
    workflow.connect("generator", "enricher", mapping={"result": "data"})
    workflow.connect("enricher", "validator", mapping={"enriched_data": "data"})

    # Parameters
    parameters = {
        "generator": {
            "code": """
# Generate sample data
result = [
    {"id": 1, "name": "Item 1", "value": 100},
    {"id": 2, "name": "Item 2", "value": 200},
    {"id": 3, "name": "Item 3", "value": 300}
]
"""
        },
        "enricher": {
            # In a real scenario, this would connect to an actual MCP server
            "mcp_servers": [],  # No servers for demo
            "enrichment_tool": "add_metadata",
        },
        "validator": {
            "mcp_server": "http://localhost:8080",
            "validation_resource": "validation://item-schema",
        },
    }

    # Execute
    runtime = LocalRuntime()

    print("\n1. Executing workflow with MCP-capable nodes...")
    results, _ = runtime.execute(workflow, parameters)

    # Display results
    print("\n2. Generator Output:")
    gen_result = results.get("generator", {})
    if "result" in gen_result:
        print(f"   Generated {len(gen_result['result'])} items")

    print("\n3. Enricher Output:")
    enrich_result = results.get("enricher", {})
    print(f"   Enrichment applied: {enrich_result.get('enrichment_applied', False)}")
    print(f"   Message: {enrich_result.get('message', 'N/A')}")

    print("\n4. Validator Output:")
    val_result = results.get("validator", {})
    print(f"   Validation passed: {val_result.get('valid', False)}")
    if val_result.get("errors"):
        print(f"   Errors: {val_result['errors']}")


def demonstrate_mcp_tool_discovery():
    """Show how nodes can discover MCP tools."""
    print("\n\nMCP TOOL DISCOVERY EXAMPLE")
    print("=" * 70)

    class ToolExplorerNode(Node, MCPCapabilityMixin):
        """Node that explores available MCP tools."""

        def get_parameters(self) -> Dict[str, NodeParameter]:
            return {
                "mcp_servers": NodeParameter(
                    name="mcp_servers", type=list, required=True
                )
            }

        def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
            servers = kwargs.get("mcp_servers", [])

            all_tools = []
            server_info = []

            for server in servers:
                try:
                    tools = self.discover_mcp_tools_sync([server])
                    all_tools.extend(tools)
                    server_info.append(
                        {
                            "server": server,
                            "tools_count": len(tools),
                            "tools": [t["function"]["name"] for t in tools],
                        }
                    )
                except Exception as e:
                    server_info.append({"server": server, "error": str(e)})

            return {
                "total_tools": len(all_tools),
                "servers_checked": len(servers),
                "server_details": server_info,
                "tool_summary": self.format_mcp_tools_for_display(all_tools),
            }

    # Create and run explorer
    explorer = ToolExplorerNode()

    # Mock server configuration
    result = explorer.run(
        {},
        mcp_servers=[
            "http://localhost:8080",  # AI Registry server
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            },
        ],
    )

    print("\nTool Discovery Results:")
    print(f"Total tools found: {result['total_tools']}")
    print(f"Servers checked: {result['servers_checked']}")
    print("\nServer Details:")
    for server in result["server_details"]:
        if "error" in server:
            print(f"  - {server['server']}: Error - {server['error']}")
        else:
            print(f"  - {server['server']}: {server['tools_count']} tools")


def main():
    """Run all MCP mixin examples."""
    print("\n" + "=" * 70)
    print("MCP CAPABILITY MIXIN EXAMPLES")
    print("=" * 70)
    print("\nThese examples show how to add MCP capabilities to any node")
    print("without requiring it to be an LLM agent.")

    # Run demonstrations
    demonstrate_mcp_mixin()
    demonstrate_mcp_tool_discovery()

    print("\n" + "=" * 70)
    print("KEY TAKEAWAYS:")
    print("1. MCPCapabilityMixin adds MCP client features to any node")
    print("2. Nodes can discover tools, call them, and access resources")
    print("3. Both synchronous and asynchronous methods are available")
    print("4. Perfect for data processing, validation, and integration nodes")
    print("\nFor real usage, ensure MCP servers are running and accessible.")


if __name__ == "__main__":
    main()
