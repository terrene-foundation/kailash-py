#!/usr/bin/env python3
"""
MCP Server Example - New Architecture
=====================================

This example demonstrates the new MCP server architecture where servers
are standalone services, not workflow nodes.

Key Changes:
- MCPServer is no longer a node
- Servers run as independent services
- Use the FastMCP-based server framework

This example shows:
- How to create a custom MCP server
- Registering tools and resources
- Running servers alongside workflows
- Integration with LLM agents

To run MCP servers, use the command line:
    python -m kailash.mcp.servers.ai_registry --port 8080
"""

from datetime import datetime
from typing import Any

from examples.utils.data_paths import get_input_data_path
from kailash import Workflow
from kailash.mcp import MCPServer, SimpleMCPServer
from kailash.nodes.ai import LLMAgentNode


class WorkflowMCPServer:
    """Example MCP server that exposes workflow capabilities."""

    def __init__(self, name: str = "workflow-server", port: int = 8080):
        # Use enhanced MCP server with production features
        self.server = MCPServer(name)
        self.name = name
        self.port = port
        self.setup_resources()
        self.setup_tools()
        self.setup_prompts()

    def setup_resources(self):
        """Set up server resources."""

        # Static resource
        @self.server.resource("workflow://status")
        def get_workflow_status():
            return {
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "nodes_active": 3,
                "tasks_completed": 42,
            }

        # Dynamic resource with parameter
        @self.server.resource("workflow://metrics/{metric_type}")
        def get_metrics(metric_type: str):
            metrics = {
                "performance": {
                    "cpu_usage": "23%",
                    "memory_usage": "512MB",
                    "throughput": "1000 items/sec",
                },
                "errors": {"error_rate": "0.01%", "last_error": None, "error_count": 5},
            }
            return metrics.get(metric_type, {"error": "Unknown metric type"})

    def setup_tools(self):
        """Set up server tools."""

        @self.server.tool(cache_key="execution", cache_ttl=30)  # Cache for 30 seconds
        def execute_node(
            node_id: str, parameters: dict[str, Any] = None
        ) -> dict[str, Any]:
            """Execute a specific workflow node with caching.

            Args:
                node_id: ID of the node to execute
                parameters: Optional parameters for the node

            Returns:
                Execution result
            """
            # Simulate some processing time
            import time

            time.sleep(0.1)

            return {
                "success": True,
                "node_id": node_id,
                "result": f"Node {node_id} executed with params: {parameters}",
                "execution_time": 0.5,
                "cached": False,  # Will be True on cache hits
            }

        @self.server.tool(format_response="markdown")  # Format as markdown
        def get_node_status(node_id: str) -> dict[str, Any]:
            """Get the status of a workflow node with markdown formatting.

            Args:
                node_id: ID of the node to check

            Returns:
                Node status information
            """
            return {
                "title": f"Status for Node {node_id}",
                "node_id": node_id,
                "status": "active",
                "last_run": datetime.now().isoformat(),
                "success_rate": 0.95,
                "metrics": {
                    "total_runs": 1205,
                    "avg_duration": "2.3s",
                    "error_count": 12,
                },
            }

        @self.server.tool()  # Regular tool with automatic metrics
        def pause_workflow(reason: str = "") -> dict[str, Any]:
            """Pause the workflow execution.

            Args:
                reason: Optional reason for pausing

            Returns:
                Pause confirmation
            """
            return {
                "paused": True,
                "reason": reason,
                "paused_at": datetime.now().isoformat(),
            }

    def setup_prompts(self):
        """Set up server prompts."""

        @self.server.prompt("analyze_workflow")
        def analyze_workflow_prompt(workflow_id: str, time_range: str = "1h") -> str:
            """Generate a prompt for workflow analysis."""
            return f"""Analyze the workflow '{workflow_id}' performance over the last {time_range}.

Consider:
- Execution time trends
- Error rates and patterns
- Resource utilization
- Bottlenecks and optimization opportunities

Provide a comprehensive analysis with actionable recommendations."""

    def start(self):
        """Start the MCP server."""
        print(f"Starting {self.name} with enhanced capabilities...")
        print(f"Cache enabled: {self.server.cache.enabled}")
        print(f"Metrics enabled: {self.server.metrics.enabled}")
        self.server.run()

    def get_stats(self):
        """Get server statistics."""
        return self.server.get_server_stats()


def demonstrate_custom_server():
    """Demonstrate creating a custom MCP server."""
    print("CUSTOM MCP SERVER EXAMPLE")
    print("=" * 70)
    print("\nCreating a custom MCP server for workflow management...")

    # Create the server instance
    server = WorkflowMCPServer(name="workflow-mcp", port=8081)

    print(f"\n✅ Server created: {server.name}")
    print(f"   Port: {server.port}")
    print("\nTo run this server, use:")
    print(f"   python -m {__name__} --serve")
    print("\nOr programmatically:")
    print("   server.start()  # Runs until stopped")


def demonstrate_simple_server():
    """Demonstrate using SimpleMCPServer for quick prototyping."""
    print("\n\nSIMPLE MCP SERVER EXAMPLE")
    print("=" * 70)
    print("\nCreating a simple MCP server with inline definitions...")

    # Create a simple server (minimal features enabled)
    simple_server = SimpleMCPServer("simple-workflow", "Simple workflow management")

    # Add resources
    @simple_server.resource("workflow://config")
    def get_config():
        """Get workflow configuration."""
        return {"max_nodes": 10, "timeout": 300}

    # Add tools inline
    @simple_server.tool()
    def list_nodes() -> list[str]:
        """List all workflow nodes."""
        return ["input", "processor", "output", "validator"]

    @simple_server.tool(format_response="json")  # Even simple server gets formatting
    def get_node_config(node_name: str) -> dict[str, Any]:
        """Get configuration for a specific node."""
        configs = {
            "input": {"type": "file", "path": f"/{get_input_data_path('input.csv')}"},
            "processor": {
                "type": "transform",
                "operations": ["normalize", "aggregate"],
            },
            "output": {"type": "database", "table": "results"},
            "validator": {"type": "schema", "strict": True},
        }
        return configs.get(node_name, {"error": "Node not found"})

    print(f"\n✅ Simple server created: {simple_server.name}")
    print(f"   Cache enabled: {simple_server.cache.enabled}")
    print(f"   Metrics enabled: {simple_server.metrics.enabled}")
    print("   This is ideal for quick prototyping and testing")


def demonstrate_server_with_llm_agent():
    """Demonstrate using MCP server with LLM agent."""
    print("\n\nMCP SERVER WITH LLM AGENT")
    print("=" * 70)
    print("\nThis shows how LLM agents interact with MCP servers...")

    # Create workflow with LLM agent
    workflow = Workflow("mcp-agent-demo", "MCP Agent Integration")
    workflow.add_node("agent", LLMAgentNode())

    # Configure agent to use MCP server

    print("\n📋 Agent Configuration:")
    print("   - Connected to workflow MCP server")
    print("   - Auto-discovering available tools")
    print("   - Can execute workflow operations through MCP")

    # Show example execution (without actually running)
    print("\n📝 Example agent capabilities through MCP:")
    print("   - execute_node(node_id='processor')")
    print("   - get_node_status(node_id='validator')")
    print("   - pause_workflow(reason='Maintenance')")
    print("   - Access workflow://status resource")


def show_running_server_example():
    """Show how to run an MCP server process."""
    print("\n\nRUNNING MCP SERVERS")
    print("=" * 70)
    print("\nMCP servers run as independent processes:")

    print("\n1. Using the command line:")
    print("   python -m kailash.mcp.servers.ai_registry --port 8080")

    print("\n2. Using a Python script:")
    print(
        """
   from kailash.mcp.servers.ai_registry import AIRegistryServer

   server = AIRegistryServer(port=8080)
   server.start()  # Blocks until stopped
   """
    )

    print("\n3. Running in a subprocess:")
    print(
        """
   import subprocess

   # Start server in background
   proc = subprocess.Popen([
       "python", "-m", "kailash.mcp.servers.ai_registry",
       "--port", "8080"
   ])

   # Your workflow code here...

   # Stop server when done
   proc.terminate()
   """
    )

    print("\n4. Using multiprocessing (for examples):")
    print(
        """
   from multiprocessing import Process

   def run_server():
       server = AIRegistryServer(port=8080)
       server.start()

   # Start in separate process
   server_process = Process(target=run_server)
   server_process.start()

   # Your workflow code here...

   # Stop when done
   server_process.terminate()
   """
    )


def main():
    """Run all MCP server examples."""
    print("\n" + "=" * 70)
    print("MCP SERVER EXAMPLES - NEW ARCHITECTURE")
    print("=" * 70)
    print("\nMCP servers are now standalone services, not workflow nodes.")
    print("They run independently and can be accessed by LLM agents.")

    # Show different server examples
    demonstrate_custom_server()
    demonstrate_simple_server()
    demonstrate_server_with_llm_agent()
    show_running_server_example()

    print("\n" + "=" * 70)
    print("MCP Server examples completed!")
    print("\nKey Takeaways:")
    print("1. MCPServer is no longer a workflow node")
    print("2. Servers run as independent long-lived processes")
    print("3. Use FastMCP decorators to define tools and resources")
    print("4. LLM agents can discover and use MCP server capabilities")
    print("5. Multiple transport options: stdio, HTTP, SSE")
    print("\nFor production use, run servers as separate processes.")


# Allow running as a server if called with --serve
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        print("Starting WorkflowMCPServer with enhanced capabilities...")
        server = WorkflowMCPServer(name="workflow-mcp", port=8081)

        # Show server stats before starting
        print("\nServer Statistics:")
        stats = server.get_stats()
        print(f"Tools registered: {stats['tools']['registered_tools']}")
        print(f"Cached tools: {stats['tools']['cached_tools']}")
        print(f"Cache enabled: {stats['server']['config']['cache']['enabled']}")
        print(f"Metrics enabled: {stats['server']['config']['metrics']['enabled']}")

        server.start()  # This will block
    else:
        main()
