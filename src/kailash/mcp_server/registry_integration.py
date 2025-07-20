"""
Registry Integration for MCP Servers.

This module provides automatic registration and deregistration of MCP servers
with the service discovery system. It includes health announcement, capability
broadcasting, and graceful shutdown handling.

Features:
- Automatic server registration on startup
- Periodic health announcements
- Graceful deregistration on shutdown
- Capability discovery and broadcasting
- Network announcement protocols
- Registry backend integration

Examples:
    Auto-registration with file registry:

    >>> from kailash.mcp_server import MCPServer
    >>> from kailash.mcp_server.registry_integration import ServerRegistrar
    >>>
    >>> server = MCPServer("my-server")
    >>> registrar = ServerRegistrar(server)
    >>>
    >>> @server.tool()
    >>> def search(query: str) -> str:
    ...     return f"Results: {query}"
    >>>
    >>> # Server will auto-register when started
    >>> registrar.start_with_registration()

    Custom registry backend:

    >>> from kailash.mcp_server.discovery import ServiceRegistry, FileBasedDiscovery
    >>>
    >>> registry = ServiceRegistry([FileBasedDiscovery("custom_registry.json")])
    >>> registrar = ServerRegistrar(server, registry=registry)
    >>> registrar.start_with_registration()
"""

import asyncio
import atexit
import json
import logging
import signal
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from .discovery import (
    NetworkDiscovery,
    ServerInfo,
    ServiceRegistry,
    create_default_registry,
)
from .errors import ServiceDiscoveryError

logger = logging.getLogger(__name__)


class ServerRegistrar:
    """Handles automatic registration and lifecycle management for MCP servers."""

    def __init__(
        self,
        server: Any,  # MCPServer instance
        registry: Optional[ServiceRegistry] = None,
        auto_announce: bool = True,
        announce_interval: float = 30.0,
        enable_network_discovery: bool = False,
        server_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize server registrar.

        Args:
            server: MCP server instance to register
            registry: Service registry to use (creates default if None)
            auto_announce: Enable periodic health announcements
            announce_interval: Health announcement interval in seconds
            enable_network_discovery: Enable UDP network announcements
            server_metadata: Additional server metadata
        """
        self.server = server
        self.registry = registry or create_default_registry()
        self.auto_announce = auto_announce
        self.announce_interval = announce_interval
        self.enable_network_discovery = enable_network_discovery
        self.server_metadata = server_metadata or {}

        # Server info
        self.server_id = str(uuid.uuid4())
        self.server_info: Optional[ServerInfo] = None
        self.registered = False

        # Announcement tracking
        self.announcement_task: Optional[asyncio.Task] = None
        self.network_announcer: Optional[NetworkAnnouncer] = None

        # Setup cleanup handlers
        self._setup_cleanup_handlers()

    def _setup_cleanup_handlers(self):
        """Setup cleanup handlers for graceful shutdown."""

        def cleanup():
            if self.registered:
                try:
                    asyncio.run(self.deregister())
                except Exception as e:
                    logger.error(f"Error during cleanup: {e}")

        atexit.register(cleanup)

        # Handle signals
        for sig in [signal.SIGTERM, signal.SIGINT]:
            try:
                signal.signal(sig, lambda s, f: cleanup())
            except (ValueError, OSError):
                # Signal handling not available (e.g., in threads)
                pass

    async def register(self) -> bool:
        """Register server with the discovery system.

        Returns:
            True if registration succeeded
        """
        try:
            # Discover server capabilities
            capabilities = await self._discover_capabilities()

            # Create server info
            self.server_info = ServerInfo(
                id=self.server_id,
                name=self.server.name,
                transport=self._determine_transport(),
                endpoint=self._determine_endpoint(),
                capabilities=capabilities,
                metadata=self._create_metadata(),
                health_status="healthy",
                version=getattr(self.server, "version", "1.0.0"),
                auth_required=getattr(self.server, "auth_manager", None) is not None,
            )

            # Register with registry
            success = await self.registry.register_server(self.server_info.to_dict())

            if success:
                self.registered = True
                logger.info(
                    f"Successfully registered server {self.server.name} ({self.server_id})"
                )

                # Start announcements if enabled
                if self.auto_announce:
                    await self._start_announcements()

                # Start network discovery if enabled
                if self.enable_network_discovery:
                    self.network_announcer = NetworkAnnouncer(self.server_info)
                    await self.network_announcer.start()

                return True
            else:
                logger.error(f"Failed to register server {self.server.name}")
                return False

        except Exception as e:
            logger.error(f"Error registering server: {e}")
            return False

    async def deregister(self) -> bool:
        """Deregister server from the discovery system.

        Returns:
            True if deregistration succeeded
        """
        if not self.registered:
            return True

        try:
            # Stop announcements
            if self.announcement_task:
                self.announcement_task.cancel()
                try:
                    await self.announcement_task
                except asyncio.CancelledError:
                    pass
                self.announcement_task = None

            # Stop network announcer
            if self.network_announcer:
                await self.network_announcer.stop()
                self.network_announcer = None

            # Deregister from registry
            success = await self.registry.deregister_server(self.server_id)

            if success:
                self.registered = False
                logger.info(f"Successfully deregistered server {self.server.name}")
                return True
            else:
                logger.error(f"Failed to deregister server {self.server.name}")
                return False

        except Exception as e:
            logger.error(f"Error deregistering server: {e}")
            return False

    async def update_health(
        self, health_status: str = "healthy", response_time: Optional[float] = None
    ):
        """Update server health status.

        Args:
            health_status: New health status
            response_time: Optional response time measurement
        """
        if not self.registered:
            return

        try:
            # Update in all registry backends
            for backend in self.registry.backends:
                await backend.update_server_health(
                    self.server_id, health_status, response_time
                )

            # Update local server info
            if self.server_info:
                self.server_info.health_status = health_status
                self.server_info.last_seen = time.time()
                if response_time is not None:
                    self.server_info.response_time = response_time

        except Exception as e:
            logger.error(f"Error updating health: {e}")

    def start_with_registration(self):
        """Start the server with automatic registration.

        This is a convenience method that handles registration and then
        starts the server. Use this instead of server.run() for automatic
        service discovery integration.
        """

        async def startup_sequence():
            # Register server
            success = await self.register()
            if not success:
                logger.warning("Server registration failed, but continuing startup")

            # Start health monitoring
            if hasattr(self.server, "start_health_checking"):
                self.server.start_health_checking()

        # Run registration in event loop
        try:
            asyncio.run(startup_sequence())
        except RuntimeError:
            # Already in event loop, schedule as task
            asyncio.create_task(startup_sequence())

        # Start the actual server
        try:
            self.server.run()
        finally:
            # Ensure cleanup happens
            try:
                asyncio.run(self.deregister())
            except Exception as e:
                logger.error(f"Error during final cleanup: {e}")

    async def _discover_capabilities(self) -> List[str]:
        """Discover server capabilities by examining registered tools."""
        capabilities = []

        # Get tools from server registry
        if hasattr(self.server, "_tool_registry"):
            capabilities.extend(self.server._tool_registry.keys())

        # Get resources
        if hasattr(self.server, "_resource_registry"):
            for uri in self.server._resource_registry.keys():
                capabilities.append(f"resource:{uri}")

        # Get prompts
        if hasattr(self.server, "_prompt_registry"):
            for name in self.server._prompt_registry.keys():
                capabilities.append(f"prompt:{name}")

        # Add custom capabilities from metadata
        custom_capabilities = self.server_metadata.get("capabilities", [])
        capabilities.extend(custom_capabilities)

        return list(set(capabilities))  # Remove duplicates

    def _determine_transport(self) -> str:
        """Determine the transport type used by the server."""
        # Check server configuration
        if (
            hasattr(self.server, "enable_http_transport")
            and self.server.enable_http_transport
        ):
            return "http"
        elif (
            hasattr(self.server, "enable_sse_transport")
            and self.server.enable_sse_transport
        ):
            return "sse"
        else:
            return "stdio"

    def _determine_endpoint(self) -> str:
        """Determine the server endpoint."""
        transport = self._determine_transport()

        if transport in ["http", "sse"]:
            # For HTTP/SSE, construct URL
            host = getattr(self.server, "host", "localhost")
            port = getattr(self.server, "port", 8080)
            return f"http://{host}:{port}"

        elif transport == "stdio":
            # For stdio, provide command to start server
            # This assumes the server can be started with Python
            server_script = self.server_metadata.get("startup_command")
            if server_script:
                return server_script
            else:
                # Default command
                return f"python -m {self.server.__class__.__module__}"

        else:
            return "unknown"

    def _create_metadata(self) -> Dict[str, Any]:
        """Create metadata for server registration."""
        metadata = self.server_metadata.copy()

        # Add server configuration
        if hasattr(self.server, "config"):
            metadata["config"] = self.server.config.to_dict()

        # Add feature flags
        metadata["features"] = {
            "caching": getattr(self.server, "cache", None) is not None,
            "metrics": getattr(self.server, "metrics", None) is not None,
            "auth": getattr(self.server, "auth_manager", None) is not None,
            "circuit_breaker": getattr(self.server, "circuit_breaker", None)
            is not None,
            "streaming": getattr(self.server, "enable_streaming", False),
        }

        # Add authentication config if present
        if hasattr(self.server, "auth_manager") and self.server.auth_manager:
            auth_config = {
                "type": type(self.server.auth_manager.provider)
                .__name__.lower()
                .replace("auth", ""),
                "required": True,
            }
            metadata["auth_config"] = auth_config

        # Add runtime info
        metadata["runtime"] = {
            "python_version": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
            "platform": __import__("platform").system(),
            "registered_at": time.time(),
        }

        return metadata

    async def _start_announcements(self):
        """Start periodic health announcements."""

        async def announce_health():
            while self.registered:
                try:
                    # Perform health check
                    health_status = await self._check_health()
                    await self.update_health(health_status)

                    await asyncio.sleep(self.announce_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in health announcement: {e}")
                    await asyncio.sleep(min(self.announce_interval, 10))

        self.announcement_task = asyncio.create_task(announce_health())

    async def _check_health(self) -> str:
        """Check server health status.

        Returns:
            Health status string
        """
        try:
            # Use server's health check if available
            if hasattr(self.server, "health_check"):
                health_result = self.server.health_check()
                return health_result.get("status", "unknown")

            # Basic health check - ensure server is running
            if hasattr(self.server, "_running") and self.server._running:
                return "healthy"
            else:
                return "unknown"

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return "unhealthy"


class NetworkAnnouncer:
    """Handles UDP network announcements for MCP servers."""

    def __init__(self, server_info: ServerInfo, port: int = 8765):
        """Initialize network announcer.

        Args:
            server_info: Server information to announce
            port: UDP port for announcements
        """
        self.server_info = server_info
        self.port = port
        self.running = False
        self.announcement_task: Optional[asyncio.Task] = None
        self.socket: Optional[socket.socket] = None

    async def start(self):
        """Start network announcements."""
        self.running = True

        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Start announcement task
        self.announcement_task = asyncio.create_task(self._announce_loop())

        logger.info(f"Started network announcements for {self.server_info.name}")

    async def stop(self):
        """Stop network announcements."""
        self.running = False

        if self.announcement_task:
            self.announcement_task.cancel()
            try:
                await self.announcement_task
            except asyncio.CancelledError:
                pass

        if self.socket:
            self.socket.close()
            self.socket = None

        logger.info(f"Stopped network announcements for {self.server_info.name}")

    async def _announce_loop(self):
        """Main announcement loop."""
        while self.running:
            try:
                await self._send_announcement()
                await asyncio.sleep(30)  # Announce every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in network announcement: {e}")
                await asyncio.sleep(0.1)  # Fast retry for tests

    async def _send_announcement(self):
        """Send UDP announcement."""
        if not self.socket:
            return

        announcement = {
            "type": "mcp_server_announcement",
            "id": self.server_info.id,
            "name": self.server_info.name,
            "transport": self.server_info.transport,
            "endpoint": self.server_info.endpoint,
            "capabilities": self.server_info.capabilities,
            "metadata": self.server_info.metadata,
            "health_status": self.server_info.health_status,
            "version": self.server_info.version,
            "auth_required": self.server_info.auth_required,
            "timestamp": time.time(),
        }

        message = json.dumps(announcement).encode()

        # Broadcast to network
        try:
            self.socket.sendto(message, ("<broadcast>", self.port))
        except Exception as e:
            logger.debug(f"Failed to send broadcast: {e}")

        # Send to multicast group
        try:
            self.socket.sendto(message, (NetworkDiscovery.MULTICAST_GROUP, self.port))
        except Exception as e:
            logger.debug(f"Failed to send multicast: {e}")


def enable_auto_discovery(server, **kwargs):
    """Enable automatic discovery for an MCP server.

    This is a convenience function that creates a ServerRegistrar
    and configures it for the given server.

    Args:
        server: MCP server instance
        **kwargs: Configuration options for ServerRegistrar

    Returns:
        ServerRegistrar instance

    Examples:
        >>> from kailash.mcp_server import MCPServer
        >>> from kailash.mcp_server.registry_integration import enable_auto_discovery
        >>>
        >>> server = MCPServer("my-server")
        >>> registrar = enable_auto_discovery(server, enable_network_discovery=True)
        >>> registrar.start_with_registration()
    """
    return ServerRegistrar(server, **kwargs)


def register_server_manually(
    name: str,
    transport: str,
    endpoint: str,
    capabilities: List[str],
    metadata: Optional[Dict[str, Any]] = None,
    registry: Optional[ServiceRegistry] = None,
) -> bool:
    """Manually register a server with the discovery system.

    This is useful for registering external servers that don't use
    the Kailash MCP server framework.

    Args:
        name: Server name
        transport: Transport type (stdio, http, sse)
        endpoint: Server endpoint
        capabilities: List of capabilities
        metadata: Optional metadata
        registry: Service registry to use

    Returns:
        True if registration succeeded

    Examples:
        >>> register_server_manually(
        ...     name="external-server",
        ...     transport="http",
        ...     endpoint="http://external-host:8080",
        ...     capabilities=["search", "analyze"],
        ...     metadata={"version": "2.0", "external": True}
        ... )
    """
    if registry is None:
        registry = create_default_registry()

    server_config = {
        "name": name,
        "transport": transport,
        "endpoint": endpoint,
        "capabilities": capabilities,
        "metadata": metadata or {},
        "auth_required": False,
    }

    try:
        return asyncio.run(registry.register_server(server_config))
    except RuntimeError:
        # Already in event loop
        return asyncio.create_task(registry.register_server(server_config))
