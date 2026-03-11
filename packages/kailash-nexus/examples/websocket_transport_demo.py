"""Demonstration of WebSocketServerTransport usage in Nexus MCP.

This example shows how to use the WebSocketServerTransport for building
MCP servers with advanced features like client management, broadcasting,
and custom message handling.
"""

import asyncio
import logging
from typing import Any, Dict

from kailash.workflow.builder import WorkflowBuilder
from nexus.mcp import WebSocketClientTransport, WebSocketServerTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdvancedMCPServer:
    """Advanced MCP server using WebSocketServerTransport."""

    def __init__(self, host: str = "0.0.0.0", port: int = 3001):
        """Initialize advanced MCP server."""
        self.transport = WebSocketServerTransport(
            host=host, port=port, message_handler=self.handle_message
        )
        self.workflows = {}
        self.client_sessions = {}  # Track client sessions

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP messages with advanced features.

        Args:
            message: Incoming message with _client reference

        Returns:
            Response message
        """
        client = message.pop("_client", None)
        msg_type = message.get("type")

        # Track client session
        if client and client not in self.client_sessions:
            self.client_sessions[client] = {
                "connected_at": asyncio.get_event_loop().time(),
                "requests": 0,
            }

        if client:
            self.client_sessions[client]["requests"] += 1

        # Handle different message types
        if msg_type == "list_tools":
            return await self.handle_list_tools()
        elif msg_type == "call_tool":
            return await self.handle_call_tool(message)
        elif msg_type == "subscribe":
            return await self.handle_subscribe(message, client)
        elif msg_type == "get_stats":
            return await self.handle_get_stats()
        else:
            return {"type": "error", "error": f"Unknown message type: {msg_type}"}

    async def handle_list_tools(self) -> Dict[str, Any]:
        """List available tools with detailed metadata."""
        tools = []
        for name, workflow in self.workflows.items():
            tools.append(
                {
                    "name": name,
                    "description": f"Workflow: {name}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "parameters": {
                                "type": "object",
                                "description": "Workflow parameters",
                            }
                        },
                    },
                    "metadata": {
                        "version": "1.0",
                        "category": "workflow",
                        "tags": ["nexus", "workflow"],
                    },
                }
            )
        return {"type": "tools", "tools": tools}

    async def handle_call_tool(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and broadcast status updates."""
        tool_name = message.get("name")
        arguments = message.get("arguments", {})

        if tool_name not in self.workflows:
            return {"type": "error", "error": f"Unknown tool: {tool_name}"}

        # Broadcast execution start
        await self.transport.broadcast_notification(
            {
                "event": "tool_execution_started",
                "tool": tool_name,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        try:
            # Execute workflow
            from kailash.runtime.local import LocalRuntime

            workflow = self.workflows[tool_name]
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow, parameters=arguments)

            # Broadcast execution complete
            await self.transport.broadcast_notification(
                {
                    "event": "tool_execution_completed",
                    "tool": tool_name,
                    "run_id": run_id,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            return {
                "type": "result",
                "result": results,
                "metadata": {
                    "run_id": run_id,
                    "execution_time": asyncio.get_event_loop().time(),
                },
            }

        except Exception as e:
            # Broadcast execution error
            await self.transport.broadcast_notification(
                {
                    "event": "tool_execution_error",
                    "tool": tool_name,
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            return {"type": "error", "error": str(e)}

    async def handle_subscribe(self, message: Dict[str, Any], client) -> Dict[str, Any]:
        """Handle event subscription requests."""
        events = message.get("events", [])

        if client:
            self.client_sessions[client]["subscriptions"] = events

        return {
            "type": "subscribed",
            "events": events,
            "message": f"Subscribed to {len(events)} events",
        }

    async def handle_get_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        return {
            "type": "stats",
            "stats": {
                "connected_clients": self.transport.get_connected_clients(),
                "total_workflows": len(self.workflows),
                "client_sessions": len(self.client_sessions),
                "uptime": asyncio.get_event_loop().time(),
            },
        }

    def register_workflow(self, name: str, workflow):
        """Register a workflow as a tool."""
        self.workflows[name] = workflow
        logger.info(f"Registered workflow: {name}")

    async def start(self):
        """Start the MCP server."""
        await self.transport.start()

        # Wait for at least one client before proceeding
        logger.info("Waiting for clients to connect...")
        connected = await self.transport.wait_for_clients(min_clients=1, timeout=30)

        if connected:
            logger.info("Client connected, server ready!")

            # Send welcome broadcast
            await self.transport.broadcast_notification(
                {
                    "event": "server_ready",
                    "workflows": list(self.workflows.keys()),
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )
        else:
            logger.warning("No clients connected within timeout")

    async def stop(self):
        """Stop the MCP server."""
        # Send shutdown notification
        await self.transport.broadcast_notification(
            {"event": "server_shutdown", "timestamp": asyncio.get_event_loop().time()}
        )

        await self.transport.stop()


class AdvancedMCPClient:
    """Advanced MCP client using WebSocketClientTransport."""

    def __init__(self, uri: str = "ws://localhost:3001"):
        """Initialize advanced MCP client."""
        self.transport = WebSocketClientTransport(
            uri=uri, message_handler=self.handle_notification
        )
        self.notifications = []

    async def handle_notification(self, message: Dict[str, Any]):
        """Handle server notifications.

        Args:
            message: Notification message from server
        """
        if message.get("type") == "notification":
            self.notifications.append(message)
            logger.info(f"Received notification: {message.get('event')}")

    async def connect(self):
        """Connect to MCP server."""
        await self.transport.start()

        # Subscribe to events
        await self.transport.send_message(
            {
                "type": "subscribe",
                "events": [
                    "tool_execution_started",
                    "tool_execution_completed",
                    "tool_execution_error",
                ],
            }
        )

    async def disconnect(self):
        """Disconnect from MCP server."""
        await self.transport.stop()

    async def list_tools(self) -> list:
        """List available tools."""
        await self.transport.send_message({"type": "list_tools"})
        response = await self.transport.receive_message()
        return response.get("tools", [])

    async def call_tool(self, name: str, parameters: Dict[str, Any]) -> Any:
        """Call a tool with parameters."""
        await self.transport.send_message(
            {"type": "call_tool", "name": name, "arguments": parameters}
        )
        response = await self.transport.receive_message()

        if response.get("type") == "error":
            raise RuntimeError(f"Tool execution failed: {response.get('error')}")

        return response.get("result")

    async def get_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        await self.transport.send_message({"type": "get_stats"})
        response = await self.transport.receive_message()
        return response.get("stats", {})

    def get_notifications(self) -> list:
        """Get all received notifications."""
        return self.notifications


async def demo_basic_usage():
    """Demonstrate basic WebSocketServerTransport usage."""
    logger.info("=== Basic WebSocketServerTransport Demo ===")

    # Create server with custom message handler
    async def echo_handler(message: Dict[str, Any]) -> Dict[str, Any]:
        """Simple echo handler."""
        return {"type": "echo", "original": message}

    server = WebSocketServerTransport(
        host="127.0.0.1", port=3002, message_handler=echo_handler
    )

    # Start server
    await server.start()
    logger.info(f"Server started with {server.get_connected_clients()} clients")

    # Simulate some activity
    await asyncio.sleep(2)

    # Broadcast a notification
    await server.broadcast_notification(
        {
            "message": "Server is operational",
            "timestamp": asyncio.get_event_loop().time(),
        }
    )

    # Stop server
    await server.stop()
    logger.info("Server stopped")


async def demo_advanced_mcp():
    """Demonstrate advanced MCP server with workflows."""
    logger.info("=== Advanced MCP Server Demo ===")

    # Create advanced MCP server
    server = AdvancedMCPServer(port=3003)

    # Create and register sample workflows
    workflow1 = WorkflowBuilder()
    workflow1.add_node(
        "PythonCodeNode",
        "process",
        {"code": "result = {'sum': sum(parameters.get('numbers', []))}"},
    )
    server.register_workflow("calculate_sum", workflow1.build())

    workflow2 = WorkflowBuilder()
    workflow2.add_node(
        "PythonCodeNode",
        "transform",
        {
            "code": "result = {'transformed': [x * 2 for x in parameters.get('values', [])]}"
        },
    )
    server.register_workflow("transform_values", workflow2.build())

    # Start server in background
    server_task = asyncio.create_task(server.start())

    # Give server time to start
    await asyncio.sleep(1)

    # Create client and connect
    client = AdvancedMCPClient("ws://localhost:3003")
    await client.connect()

    # List available tools
    tools = await client.list_tools()
    logger.info(f"Available tools: {[t['name'] for t in tools]}")

    # Get server stats
    stats = await client.get_stats()
    logger.info(f"Server stats: {stats}")

    # Call a tool
    result = await client.call_tool("calculate_sum", {"numbers": [1, 2, 3, 4, 5]})
    logger.info(f"Sum result: {result}")

    # Call another tool
    result = await client.call_tool("transform_values", {"values": [1, 2, 3]})
    logger.info(f"Transform result: {result}")

    # Check notifications
    notifications = client.get_notifications()
    logger.info(f"Received {len(notifications)} notifications")

    # Cleanup
    await client.disconnect()
    await server.stop()

    # Cancel server task
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


async def main():
    """Run all demonstrations."""
    try:
        # Run basic demo
        await demo_basic_usage()

        # Add delay between demos
        await asyncio.sleep(1)

        # Run advanced demo
        await demo_advanced_mcp()

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
