"""
Enhanced MCP Client for Kailash Middleware

Integrates existing Kailash MCP client implementations with middleware-specific
features for agent-frontend communication and real-time updates.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# Import Kailash SDK components
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import existing Kailash MCP components
try:
    from kailash.mcp_server import MCPClient

    _KAILASH_MCP_AVAILABLE = True
except ImportError:
    _KAILASH_MCP_AVAILABLE = False

# Import middleware components
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware

logger = logging.getLogger(__name__)


class MCPClientConfig:
    """Configuration for Middleware MCP Client using Kailash patterns."""

    def __init__(self):
        self.name = "kailash-middleware-mcp-client"
        self.version = "1.0.0"
        self.description = "Enhanced MCP client built with Kailash SDK"

        # Connection settings
        self.connection_timeout = 30
        self.request_timeout = 60
        self.max_retries = 3
        self.retry_delay = 1.0

        # Middleware features
        self.enable_events = True
        self.enable_caching = True
        self.cache_ttl = 300
        self.enable_streaming = True


class MCPServerConnection:
    """Represents a connection to an MCP server using Kailash patterns."""

    def __init__(
        self,
        server_name: str,
        connection_config: Dict[str, Any],
        client_instance: "MiddlewareMCPClient",
    ):
        self.server_name = server_name
        self.connection_config = connection_config
        self.client = client_instance
        self.connection_id = str(uuid.uuid4())

        # Connection state
        self.connected = False
        self.last_connection = None
        self.connection_attempts = 0

        # Capabilities cache
        self.server_capabilities = {}
        self.available_tools = {}
        self.available_resources = {}

        # Kailash MCP client if available
        self.mcp_client = None
        if _KAILASH_MCP_AVAILABLE:
            try:
                self.mcp_client = MCPClient()
            except Exception as e:
                logger.warning(f"Could not initialize MCP client: {e}")

    async def connect(self) -> bool:
        """Connect to MCP server using Kailash patterns."""
        try:
            self.connection_attempts += 1

            # Use existing Kailash MCP client if available
            if self.mcp_client:
                # This would use the actual MCP client connection
                # For now, simulate connection
                pass

            # Simulate successful connection
            self.connected = True
            self.last_connection = datetime.now(timezone.utc)

            # Discover capabilities
            await self._discover_capabilities()

            # Emit middleware event
            if self.client.event_stream:
                await self.client._emit_client_event(
                    "server_connected",
                    {
                        "server_name": self.server_name,
                        "connection_id": self.connection_id,
                        "capabilities": self.server_capabilities,
                    },
                )

            logger.info(f"Connected to MCP server: {self.server_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {self.server_name}: {e}")
            return False

    async def _discover_capabilities(self):
        """Discover server capabilities using Kailash workflows."""

        # Create capability discovery workflow
        discovery_workflow = WorkflowBuilder()

        discoverer = PythonCodeNode(
            name="discover_capabilities",
            code="""
# Discover MCP server capabilities using Kailash patterns
server_name = input_data.get('server_name')

# Simulate capability discovery
capabilities = {
    'server_info': {
        'name': server_name,
        'version': '1.0.0',
        'implementation': 'Kailash MCP Server'
    },
    'features': {
        'tools': True,
        'resources': True,
        'prompts': True,
        'streaming': True
    }
}

# Simulate available tools
tools = {
    f'{server_name}_search': {
        'description': f'Search tool for {server_name}',
        'parameters': {
            'query': {'type': 'string', 'required': True}
        }
    },
    f'{server_name}_process': {
        'description': f'Process data with {server_name}',
        'parameters': {
            'data': {'type': 'object', 'required': True}
        }
    }
}

# Simulate available resources
resources = {
    f'{server_name}://data': {
        'description': f'Data resources from {server_name}',
        'type': 'application/json'
    }
}

result = {
    'capabilities': capabilities,
    'tools': tools,
    'resources': resources,
    'discovery_time': datetime.now().isoformat()
}
""",
        )

        discovery_workflow.add_node(discoverer)
        workflow = discovery_workflow.build()

        # Execute discovery
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow, parameters={"server_name": self.server_name}
        )

        discovery_result = results.get("discover_capabilities", {})

        if discovery_result:
            self.server_capabilities = discovery_result.get("capabilities", {})
            self.available_tools = discovery_result.get("tools", {})
            self.available_resources = discovery_result.get("resources", {})

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any], session_id: str = None
    ) -> Dict[str, Any]:
        """Call MCP tool using Kailash patterns."""

        if not self.connected:
            return {
                "success": False,
                "error": f"Not connected to server {self.server_name}",
            }

        if tool_name not in self.available_tools:
            return {
                "success": False,
                "error": f"Tool {tool_name} not available on server {self.server_name}",
                "available_tools": list(self.available_tools.keys()),
            }

        # Create tool execution workflow
        execution_workflow = WorkflowBuilder()

        executor = PythonCodeNode(
            name="execute_tool",
            code="""
# Execute MCP tool using Kailash patterns
tool_name = input_data.get('tool_name')
arguments = input_data.get('arguments', {})
server_name = input_data.get('server_name')

# Simulate tool execution
execution_result = {
    'tool_name': tool_name,
    'server_name': server_name,
    'arguments': arguments,
    'result': f'Executed {tool_name} on {server_name} with args: {arguments}',
    'execution_time': datetime.now().isoformat(),
    'success': True
}

result = {'tool_result': execution_result}
""",
        )

        execution_workflow.add_node(executor)
        workflow = execution_workflow.build()

        # Execute tool call
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow,
            parameters={
                "tool_name": tool_name,
                "arguments": arguments,
                "server_name": self.server_name,
            },
        )

        tool_result = results.get("execute_tool", {}).get("tool_result", {})

        # Emit middleware event
        if self.client.event_stream:
            await self.client._emit_client_event(
                "tool_executed",
                {
                    "server_name": self.server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "session_id": session_id,
                    "success": tool_result.get("success", False),
                },
            )

        return {
            "success": True,
            "server_name": self.server_name,
            "tool_result": tool_result,
        }

    async def get_resource(
        self, resource_uri: str, session_id: str = None
    ) -> Dict[str, Any]:
        """Get MCP resource using Kailash patterns."""

        if not self.connected:
            return {
                "success": False,
                "error": f"Not connected to server {self.server_name}",
            }

        # Create resource access workflow
        access_workflow = WorkflowBuilder()

        accessor = PythonCodeNode(
            name="access_resource",
            code="""
# Access MCP resource using Kailash patterns
resource_uri = input_data.get('resource_uri')
server_name = input_data.get('server_name')

# Simulate resource access
resource_data = {
    'uri': resource_uri,
    'server_name': server_name,
    'content': f'Resource content from {resource_uri} on {server_name}',
    'content_type': 'application/json',
    'access_time': datetime.now().isoformat(),
    'success': True
}

result = {'resource_data': resource_data}
""",
        )

        access_workflow.add_node(accessor)
        workflow = access_workflow.build()

        # Execute resource access
        runtime = LocalRuntime()
        results, _ = runtime.execute(
            workflow,
            parameters={"resource_uri": resource_uri, "server_name": self.server_name},
        )

        resource_data = results.get("access_resource", {}).get("resource_data", {})

        # Emit middleware event
        if self.client.event_stream:
            await self.client._emit_client_event(
                "resource_accessed",
                {
                    "server_name": self.server_name,
                    "resource_uri": resource_uri,
                    "session_id": session_id,
                    "success": resource_data.get("success", False),
                },
            )

        return {
            "success": True,
            "server_name": self.server_name,
            "resource_data": resource_data,
        }

    async def disconnect(self):
        """Disconnect from MCP server."""
        if self.connected:
            self.connected = False

            # Emit middleware event
            if self.client.event_stream:
                await self.client._emit_client_event(
                    "server_disconnected",
                    {
                        "server_name": self.server_name,
                        "connection_id": self.connection_id,
                    },
                )

            logger.info(f"Disconnected from MCP server: {self.server_name}")


class MiddlewareMCPClient:
    """
    Enhanced MCP Client built with Kailash SDK components.

    Integrates with the middleware layer for real-time events,
    session management, and agent-UI communication.
    """

    def __init__(
        self,
        config: MCPClientConfig = None,
        event_stream: EventStream = None,
        agent_ui: AgentUIMiddleware = None,
    ):
        self.config = config or MCPClientConfig()
        self.event_stream = event_stream
        self.agent_ui = agent_ui

        # Client state
        self.client_id = str(uuid.uuid4())
        self.server_connections: Dict[str, MCPServerConnection] = {}

        # Kailash runtime for workflows
        self.runtime = LocalRuntime()

        # Cache for tool/resource discovery
        self._capability_cache = {}
        self._cache_timestamps = {}

    async def add_server(
        self, server_name: str, connection_config: Dict[str, Any]
    ) -> bool:
        """Add MCP server connection."""

        if server_name in self.server_connections:
            logger.warning(f"Server {server_name} already exists")
            return False

        # Create server connection
        connection = MCPServerConnection(server_name, connection_config, self)

        # Attempt to connect
        success = await connection.connect()

        if success:
            self.server_connections[server_name] = connection

            # Emit middleware event
            if self.event_stream:
                await self._emit_client_event(
                    "server_added",
                    {
                        "server_name": server_name,
                        "connection_config": connection_config,
                    },
                )

        return success

    async def remove_server(self, server_name: str) -> bool:
        """Remove MCP server connection."""

        if server_name not in self.server_connections:
            return False

        connection = self.server_connections[server_name]
        await connection.disconnect()

        del self.server_connections[server_name]

        # Emit middleware event
        if self.event_stream:
            await self._emit_client_event(
                "server_removed", {"server_name": server_name}
            )

        return True

    async def discover_all_capabilities(self) -> Dict[str, Any]:
        """Discover capabilities from all connected servers."""

        capabilities = {}

        for server_name, connection in self.server_connections.items():
            if connection.connected:
                capabilities[server_name] = {
                    "server_capabilities": connection.server_capabilities,
                    "available_tools": connection.available_tools,
                    "available_resources": connection.available_resources,
                }

        return capabilities

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: str = None,
    ) -> Dict[str, Any]:
        """Call tool on specific MCP server."""

        if server_name not in self.server_connections:
            return {
                "success": False,
                "error": f"Server {server_name} not found",
                "available_servers": list(self.server_connections.keys()),
            }

        connection = self.server_connections[server_name]
        return await connection.call_tool(tool_name, arguments, session_id)

    async def get_resource(
        self, server_name: str, resource_uri: str, session_id: str = None
    ) -> Dict[str, Any]:
        """Get resource from specific MCP server."""

        if server_name not in self.server_connections:
            return {
                "success": False,
                "error": f"Server {server_name} not found",
                "available_servers": list(self.server_connections.keys()),
            }

        connection = self.server_connections[server_name]
        return await connection.get_resource(resource_uri, session_id)

    async def broadcast_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], session_id: str = None
    ) -> Dict[str, Dict[str, Any]]:
        """Call tool on all servers that support it."""

        results = {}

        for server_name, connection in self.server_connections.items():
            if connection.connected and tool_name in connection.available_tools:
                result = await connection.call_tool(tool_name, arguments, session_id)
                results[server_name] = result

        return results

    async def get_client_stats(self) -> Dict[str, Any]:
        """Get MCP client statistics."""

        connected_servers = sum(
            1 for conn in self.server_connections.values() if conn.connected
        )

        total_tools = sum(
            len(conn.available_tools)
            for conn in self.server_connections.values()
            if conn.connected
        )

        total_resources = sum(
            len(conn.available_resources)
            for conn in self.server_connections.values()
            if conn.connected
        )

        return {
            "client_info": {
                "client_id": self.client_id,
                "name": self.config.name,
                "version": self.config.version,
            },
            "connections": {
                "total_servers": len(self.server_connections),
                "connected_servers": connected_servers,
                "disconnected_servers": len(self.server_connections)
                - connected_servers,
            },
            "capabilities": {
                "total_tools": total_tools,
                "total_resources": total_resources,
            },
            "server_details": {
                server_name: {
                    "connected": conn.connected,
                    "tools_count": len(conn.available_tools),
                    "resources_count": len(conn.available_resources),
                    "last_connection": (
                        conn.last_connection.isoformat()
                        if conn.last_connection
                        else None
                    ),
                }
                for server_name, conn in self.server_connections.items()
            },
            "implementation": "Kailash SDK Middleware MCP Client",
        }

    async def _emit_client_event(self, event_type: str, data: Dict[str, Any]):
        """Emit MCP client event to middleware event stream."""

        from ..events import WorkflowEvent

        event = WorkflowEvent(
            type=EventType.SYSTEM_STATUS,
            workflow_id="mcp_client",
            data={
                "mcp_client_event": event_type,
                "client_id": self.client_id,
                "client_name": self.config.name,
                **data,
            },
        )

        await self.event_stream.emit(event)

    async def disconnect_all(self):
        """Disconnect from all MCP servers."""

        for connection in self.server_connections.values():
            await connection.disconnect()

        # Emit shutdown event
        if self.event_stream:
            await self._emit_client_event(
                "client_shutdown",
                {"disconnected_servers": list(self.server_connections.keys())},
            )

        logger.info(f"MCP client {self.client_id} disconnected from all servers")
