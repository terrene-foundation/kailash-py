"""Simple MCP server implementation for Nexus workflows.

This module provides a basic MCP server that exposes Nexus workflows
as tools for AI agents. It implements a subset of MCP protocol for
testing and demonstration purposes.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

import websockets

from .transport import WebSocketClientTransport, WebSocketServerTransport

logger = logging.getLogger(__name__)


class MCPServer:
    """Simple MCP server that exposes workflows as tools."""

    def __init__(
        self, host: str = "0.0.0.0", port: int = 3001, use_transport: bool = True
    ):
        """Initialize MCP server.

        Args:
            host: Host to bind to
            port: Port to listen on
            use_transport: Use WebSocketServerTransport instead of direct websockets
        """
        self.host = host
        self.port = port
        self.use_transport = use_transport
        self._workflows: Dict[str, Any] = {}
        self._resources: Dict[str, Any] = {}  # Resource handlers
        self._clients: Set[Any] = set()  # WebSocket connections
        self._server = None
        self._serving_task = None
        self._transport = None

    def _create_workflow_resource_handler(self, name: str, workflow: Any):
        """Create a resource handler function for a workflow.

        Args:
            name: Workflow name
            workflow: Workflow instance

        Returns:
            Async function that returns workflow metadata/documentation
        """

        async def handler(uri: str):
            """Resource handler for workflow metadata."""
            # Extract workflow metadata
            metadata = {
                "name": name,
                "uri": uri,
                "description": getattr(workflow, "description", f"Workflow: {name}"),
            }

            # Add workflow metadata if available
            if hasattr(workflow, "metadata") and workflow.metadata:
                metadata["workflow_metadata"] = workflow.metadata

            return {
                "content": json.dumps(metadata, indent=2),
                "mimeType": "application/json",
            }

        return handler

    def register_workflow(self, name: str, workflow: Any):
        """Register a workflow to be exposed as an MCP tool and resource.

        Args:
            name: Name of the workflow/tool
            workflow: Workflow instance
        """
        self._workflows[name] = workflow

        # Also register as a resource with workflow:// URI pattern
        resource_uri = f"workflow://{name}"
        self._resources[resource_uri] = self._create_workflow_resource_handler(
            name, workflow
        )

        logger.info(f"Registered workflow '{name}' as MCP tool and resource")

    async def handle_client(self, websocket):
        """Handle MCP client connection (legacy method for backward compatibility)."""
        self._clients.add(websocket)
        logger.info("MCP client connected")

        try:
            async for message in websocket:
                try:
                    request = json.loads(message)
                    response = await self.handle_request(request)
                    await websocket.send(json.dumps(response))
                except json.JSONDecodeError as e:
                    error_response = {"type": "error", "error": f"Invalid JSON: {e}"}
                    await websocket.send(json.dumps(error_response))
                except Exception as e:
                    logger.error(f"Error handling MCP request: {e}")
                    error_response = {"type": "error", "error": str(e)}
                    await websocket.send(json.dumps(error_response))

        except websockets.exceptions.ConnectionClosed:
            logger.info("MCP client disconnected")
        finally:
            self._clients.remove(websocket)

    async def handle_transport_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP message from transport layer.

        Args:
            message: Message from transport including _client reference

        Returns:
            Response message
        """
        # Remove client reference before processing
        client = message.pop("_client", None)

        # Handle the request
        response = await self.handle_request(message)

        return response

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP protocol request.

        Args:
            request: MCP request object

        Returns:
            MCP response object
        """
        request_type = request.get("type", "")

        if request_type == "list_tools":
            return await self.handle_list_tools()
        elif request_type == "call_tool":
            return await self.handle_call_tool(request)
        elif request_type == "list_resources":
            return await self.handle_list_resources()
        else:
            return {"type": "error", "error": f"Unknown request type: {request_type}"}

    async def handle_list_tools(self) -> Dict[str, Any]:
        """Handle list_tools request.

        Returns:
            List of available tools (workflows)
        """
        tools = []
        for name, workflow in self._workflows.items():
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
                }
            )

        return {"type": "tools", "tools": tools}

    async def handle_call_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle call_tool request.

        Args:
            request: Tool call request

        Returns:
            Tool execution result
        """
        tool_name = request.get("name", "")
        arguments = request.get("arguments", {})

        # P0-5: Validate workflow name and inputs
        from nexus.validation import validate_workflow_inputs, validate_workflow_name

        try:
            validate_workflow_name(tool_name)
            arguments = validate_workflow_inputs(arguments)
        except ValueError as e:
            return {"type": "error", "error": f"Validation error: {str(e)}"}

        if tool_name not in self._workflows:
            return {"type": "error", "error": f"Unknown tool: {tool_name}"}

        # Execute the workflow
        try:
            # P0-6 FIX: Use AsyncLocalRuntime to prevent event loop blocking
            # This allows MCP to handle concurrent requests efficiently
            from kailash.runtime import AsyncLocalRuntime

            workflow = self._workflows[tool_name]
            runtime = AsyncLocalRuntime()

            # Transform arguments to node-specific format for PythonCodeNode
            # Format: {node_id: {"parameters": arguments}}
            # This makes arguments available as 'parameters' variable in PythonCodeNode code
            node_params = {}
            for node_id in workflow.nodes.keys():
                node_params[node_id] = {"parameters": arguments}

            # Execute workflow with async runtime (no thread wrapper needed)
            # AsyncLocalRuntime.execute_workflow_async returns (results, run_id) tuple
            execution_result = await runtime.execute_workflow_async(
                workflow, inputs=node_params
            )
            if isinstance(execution_result, tuple):
                results, run_id = execution_result
            else:
                results = execution_result.get("results", execution_result)
                run_id = execution_result.get("run_id", None)

            # Extract result from the workflow execution
            # Results format: {"node_id": {"result": value}}
            if results:
                # Get the first node's result
                first_result = next(iter(results.values()))
                if isinstance(first_result, dict) and "result" in first_result:
                    result = first_result["result"]
                else:
                    result = first_result
            else:
                result = {
                    "status": "success",
                    "workflow": tool_name,
                    "parameters": arguments,
                }

        except Exception as e:
            logger.error(f"Error executing workflow {tool_name}: {e}")
            result = {"error": str(e), "workflow": tool_name}

        return {"type": "result", "result": result}

    async def handle_list_resources(self) -> Dict[str, Any]:
        """Handle list_resources request.

        Returns:
            List of available resources
        """
        resources = []
        for name in self._workflows.keys():
            resources.append(
                {
                    "uri": f"workflow://{name}",
                    "name": name,
                    "mimeType": "application/x-workflow",
                }
            )

        return {"type": "resources", "resources": resources}

    async def start(self):
        """Start the MCP server."""
        logger.info(f"Starting MCP server on {self.host}:{self.port}")

        if self.use_transport:
            # Use the new transport layer
            self._transport = WebSocketServerTransport(
                host=self.host,
                port=self.port,
                message_handler=self.handle_transport_message,
            )
            await self._transport.start()
        else:
            # Legacy direct websockets mode
            self._server = await websockets.serve(
                self.handle_client, self.host, self.port
            )
            logger.info(f"MCP server listening on ws://{self.host}:{self.port}")

    async def stop(self):
        """Stop the MCP server."""
        if self.use_transport and self._transport:
            await self._transport.stop()
        elif self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("MCP server stopped")


class SimpleMCPClient:
    """Simple MCP client for testing."""

    def __init__(
        self, host: str = "localhost", port: int = 3001, use_transport: bool = True
    ):
        """Initialize MCP client.

        Args:
            host: Server host
            port: Server port
            use_transport: Use WebSocketClientTransport instead of direct websockets
        """
        self.host = host
        self.port = port
        self.use_transport = use_transport
        self._websocket = None
        self._transport = None

    async def connect(self):
        """Connect to MCP server."""
        uri = f"ws://{self.host}:{self.port}"

        if self.use_transport:
            # Use the new transport layer
            self._transport = WebSocketClientTransport(uri)
            await self._transport.start()
        else:
            # Legacy direct websockets mode
            self._websocket = await websockets.connect(uri)
            logger.info(f"Connected to MCP server at {uri}")

    async def disconnect(self):
        """Disconnect from MCP server."""
        if self.use_transport and self._transport:
            await self._transport.stop()
            self._transport = None
        elif self._websocket:
            await self._websocket.close()
            self._websocket = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools.

        Returns:
            List of tool definitions
        """
        request = {"type": "list_tools"}

        if self.use_transport:
            if not self._transport:
                raise RuntimeError("Not connected to MCP server")

            await self._transport.send_message(request)
            result = await self._transport.receive_message()
        else:
            if not self._websocket:
                raise RuntimeError("Not connected to MCP server")

            await self._websocket.send(json.dumps(request))
            response = await self._websocket.recv()
            result = json.loads(response)

        if result.get("type") == "error":
            raise RuntimeError(f"MCP error: {result.get('error')}")

        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        request = {"type": "call_tool", "name": name, "arguments": arguments}

        if self.use_transport:
            if not self._transport:
                raise RuntimeError("Not connected to MCP server")

            await self._transport.send_message(request)
            result = await self._transport.receive_message()
        else:
            if not self._websocket:
                raise RuntimeError("Not connected to MCP server")

            await self._websocket.send(json.dumps(request))
            response = await self._websocket.recv()
            result = json.loads(response)

        if result.get("type") == "error":
            raise RuntimeError(f"MCP error: {result.get('error')}")

        return result.get("result")
