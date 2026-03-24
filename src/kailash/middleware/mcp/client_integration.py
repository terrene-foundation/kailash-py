"""
Enhanced MCP Client for Kailash Middleware

Integrates real MCP protocol client with middleware-specific features for
agent-frontend communication and real-time updates.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# Import middleware components
from ..communication.events import EventStream, EventType
from ..core.agent_ui import AgentUIMiddleware

logger = logging.getLogger(__name__)


# ---- MCP protocol transport helpers ----

try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.sse import sse_client

    _MCP_AVAILABLE = True
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment]
    sse_client = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False


class MCPClientConfig:
    """Configuration for Middleware MCP Client using real MCP protocol."""

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
    """Represents a live MCP protocol connection to a server."""

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
        self.available_tools: Dict[str, Any] = {}
        self.available_resources: Dict[str, Any] = {}

        # MCP session (set during connect)
        self._session: Optional[Any] = None
        self._read_stream = None
        self._write_stream = None
        self._cleanup_tasks: List[Any] = []

    async def connect(self) -> bool:
        """Connect to MCP server using real MCP protocol transport.

        Supports two transport modes via connection_config:
        - "stdio": launches a subprocess (requires "command" and optional "args")
        - "sse":   connects to an HTTP SSE endpoint (requires "url")
        """
        if not _MCP_AVAILABLE:
            logger.error(
                "mcp library is not installed. "
                "Install it with: pip install 'mcp[cli]>=1.23.0'"
            )
            return False

        self.connection_attempts += 1
        transport = self.connection_config.get("transport", "stdio")

        try:
            if transport == "stdio":
                command = self.connection_config.get("command")
                args = self.connection_config.get("args", [])
                env = self.connection_config.get("env")
                if not command:
                    raise ValueError(
                        "stdio transport requires 'command' in connection_config"
                    )

                params = StdioServerParameters(  # type: ignore[reportOptionalCall]
                    command=command,
                    args=args,
                    env=env,
                )
                read_stream, write_stream = await self._enter_cm(stdio_client(params))  # type: ignore[reportOptionalCall]
            elif transport == "sse":
                url = self.connection_config.get("url")
                if not url:
                    raise ValueError(
                        "sse transport requires 'url' in connection_config"
                    )
                read_stream, write_stream = await self._enter_cm(sse_client(url))  # type: ignore[reportOptionalCall]
            else:
                raise ValueError(f"Unsupported transport: {transport}")

            self._read_stream = read_stream
            self._write_stream = write_stream

            # Create MCP session
            session = await self._enter_cm(ClientSession(read_stream, write_stream))  # type: ignore[reportOptionalCall]
            self._session = session

            # Initialize the session (MCP handshake)
            await session.initialize()

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

    async def _enter_cm(self, cm):
        """Enter an async context manager and track it for cleanup."""
        result = await cm.__aenter__()
        self._cleanup_tasks.append(cm)
        return result

    async def _discover_capabilities(self):
        """Discover server capabilities via real MCP protocol calls."""
        if not self._session:
            return

        session = self._session

        # Build server_capabilities from the session info
        self.server_capabilities = {
            "server_info": {
                "name": self.server_name,
            },
            "features": {
                "tools": True,
                "resources": True,
            },
        }

        # Discover tools via tools/list
        try:
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                self.available_tools[tool.name] = {
                    "description": tool.description or "",
                    "parameters": (
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                }
        except Exception as e:
            logger.warning(f"Could not list tools from {self.server_name}: {e}")

        # Discover resources via resources/list
        try:
            resources_result = await session.list_resources()
            for resource in resources_result.resources:
                self.available_resources[str(resource.uri)] = {
                    "description": resource.description or "",
                    "name": resource.name,
                }
        except Exception as e:
            logger.warning(f"Could not list resources from {self.server_name}: {e}")

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call an MCP tool on the connected server.

        Uses the real MCP tools/call protocol method.
        """
        if not self.connected or not self._session:
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

        try:
            result = await self._session.call_tool(tool_name, arguments)

            # MCP call_tool returns a CallToolResult with content list
            content_parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                elif hasattr(item, "data"):
                    content_parts.append(item.data)

            tool_result = {
                "tool_name": tool_name,
                "server_name": self.server_name,
                "result": (
                    content_parts[0] if len(content_parts) == 1 else content_parts
                ),
                "is_error": getattr(result, "isError", False),
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "success": not getattr(result, "isError", False),
            }

            # Emit middleware event
            if self.client.event_stream:
                await self.client._emit_client_event(
                    "tool_executed",
                    {
                        "server_name": self.server_name,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "session_id": session_id,
                        "success": tool_result["success"],
                    },
                )

            return {
                "success": True,
                "server_name": self.server_name,
                "tool_result": tool_result,
            }

        except Exception as e:
            logger.error(f"Tool call {tool_name} on {self.server_name} failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "server_name": self.server_name,
            }

    async def get_resource(
        self, resource_uri: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read an MCP resource via the real resources/read protocol method."""
        if not self.connected or not self._session:
            return {
                "success": False,
                "error": f"Not connected to server {self.server_name}",
            }

        try:
            result = await self._session.read_resource(resource_uri)

            # MCP read_resource returns a ReadResourceResult with contents
            content_parts = []
            for item in result.contents:
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                elif hasattr(item, "blob"):
                    content_parts.append(item.blob)

            resource_data = {
                "uri": resource_uri,
                "server_name": self.server_name,
                "content": (
                    content_parts[0] if len(content_parts) == 1 else content_parts
                ),
                "content_type": "application/json",
                "access_time": datetime.now(timezone.utc).isoformat(),
                "success": True,
            }

            # Emit middleware event
            if self.client.event_stream:
                await self.client._emit_client_event(
                    "resource_accessed",
                    {
                        "server_name": self.server_name,
                        "resource_uri": resource_uri,
                        "session_id": session_id,
                        "success": True,
                    },
                )

            return {
                "success": True,
                "server_name": self.server_name,
                "resource_data": resource_data,
            }

        except Exception as e:
            logger.error(
                f"Resource read {resource_uri} on {self.server_name} failed: {e}"
            )
            return {
                "success": False,
                "error": str(e),
                "server_name": self.server_name,
            }

    async def disconnect(self):
        """Disconnect from MCP server and clean up transport resources."""
        if self.connected:
            self.connected = False

            # Clean up async context managers in reverse order
            for cm in reversed(self._cleanup_tasks):
                try:
                    await cm.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error during cleanup of {self.server_name}: {e}")

            self._cleanup_tasks.clear()
            self._session = None
            self._read_stream = None
            self._write_stream = None

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

    async def ping(self) -> bool:
        """Check if the MCP server connection is still alive.

        Returns:
            True if the connection is healthy
        """
        if not self.connected or not self._session:
            return False

        try:
            # Use MCP ping if available, otherwise list_tools as a health check
            if hasattr(self._session, "send_ping"):
                await self._session.send_ping()
            else:
                await self._session.list_tools()
            return True
        except Exception as e:
            logger.warning(f"Ping failed for {self.server_name}: {e}")
            self.connected = False
            return False


class MiddlewareMCPClient:
    """
    Enhanced MCP Client built with real MCP protocol transport.

    Integrates with the middleware layer for real-time events,
    session management, and agent-UI communication.
    """

    def __init__(
        self,
        config: Optional[MCPClientConfig] = None,
        event_stream: Optional[EventStream] = None,
        agent_ui: Optional[AgentUIMiddleware] = None,
    ):
        self.config = config or MCPClientConfig()
        self.event_stream = event_stream
        self.agent_ui = agent_ui

        # Client state
        self.client_id = str(uuid.uuid4())
        self.server_connections: Dict[str, MCPServerConnection] = {}

        # Cache for tool/resource discovery
        self._capability_cache = {}
        self._cache_timestamps = {}

    async def add_server(
        self, server_name: str, connection_config: Dict[str, Any]
    ) -> bool:
        """Add and connect to an MCP server.

        Args:
            server_name: Logical name for this server connection
            connection_config: Transport configuration dict. Must include:
                - "transport": "stdio" or "sse"
                For stdio: "command" (str), optional "args" (list), "env" (dict)
                For sse: "url" (str)
        """
        if server_name in self.server_connections:
            logger.warning(f"Server {server_name} already exists")
            return False

        # Create server connection
        connection = MCPServerConnection(server_name, connection_config, self)

        # Attempt to connect with retries
        success = False
        for attempt in range(self.config.max_retries):
            success = await connection.connect()
            if success:
                break
            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay)

        if success:
            self.server_connections[server_name] = connection

            # Emit middleware event
            if self.event_stream:
                await self._emit_client_event(
                    "server_added",
                    {
                        "server_name": server_name,
                        "connection_config": {
                            k: v
                            for k, v in connection_config.items()
                            if k not in ("env",)  # Don't leak env vars
                        },
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
        session_id: Optional[str] = None,
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
        self, server_name: str, resource_uri: str, session_id: Optional[str] = None
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
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Call tool on all servers that support it."""

        results = {}

        for server_name, connection in self.server_connections.items():
            if connection.connected and tool_name in connection.available_tools:
                result = await connection.call_tool(tool_name, arguments, session_id)
                results[server_name] = result

        return results

    async def check_health(self) -> Dict[str, bool]:
        """Check health of all server connections.

        Returns:
            Dict mapping server_name -> is_healthy
        """
        health = {}
        for server_name, connection in self.server_connections.items():
            health[server_name] = await connection.ping()
        return health

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

        from ..communication.events import WorkflowEvent

        event = WorkflowEvent(  # type: ignore[reportCallIssue]
            type=EventType.SYSTEM_STATUS,
            workflow_id="mcp_client",
            data={
                "mcp_client_event": event_type,
                "client_id": self.client_id,
                "client_name": self.config.name,
                **data,
            },
        )

        await self.event_stream.emit(event)  # type: ignore[reportOptionalMemberAccess]

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
