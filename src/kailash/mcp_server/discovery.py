"""
Service Discovery System for MCP Servers and Clients.

This module provides automatic discovery of MCP servers, their capabilities,
and health status. It supports multiple discovery mechanisms including
file-based registry, network scanning, and external service registries.

Features:
- Automatic server registration and deregistration
- Health checking and monitoring
- Capability-based server filtering
- Load balancing and failover
- Real-time server status updates
- Network-based discovery protocols

Examples:
    Basic service registry:

    >>> registry = ServiceRegistry()
    >>> registry.register_server({
    ...     "name": "weather-server",
    ...     "transport": "http",
    ...     "url": "http://localhost:8080",
    ...     "capabilities": ["weather.get", "weather.forecast"]
    ... })
    >>> servers = registry.discover_servers(capability="weather.get")

    Network discovery:

    >>> discoverer = NetworkDiscovery()
    >>> servers = await discoverer.scan_network("192.168.1.0/24")

    Service mesh integration:

    >>> mesh = ServiceMesh(registry)
    >>> client = await mesh.get_client_for_capability("weather.get")
"""

import asyncio
import json
import logging
import socket
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from urllib.parse import urlparse

from .auth import AuthProvider
from .errors import MCPError, MCPErrorCode, ServiceDiscoveryError

logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about a discovered MCP server."""

    name: str
    transport: str  # stdio, sse, http
    capabilities: List[str] = None  # List of tool names or capability strings
    metadata: Dict[str, Any] = None
    id: Optional[str] = None
    endpoint: Optional[str] = None  # URL or command
    command: Optional[str] = None  # For stdio transport
    args: Optional[List[str]] = None  # For stdio transport
    url: Optional[str] = None  # For HTTP/SSE transport
    health_endpoint: Optional[str] = None  # Health check endpoint path
    health_status: str = "unknown"  # healthy, unhealthy, unknown
    health: Optional[Dict[str, Any]] = None  # Health information dict
    last_seen: float = 0.0
    response_time: Optional[float] = None
    version: str = "1.0.0"
    auth_required: bool = False

    def __post_init__(self):
        if self.last_seen == 0.0:
            self.last_seen = time.time()

        # Auto-generate ID if not provided
        if self.id is None:
            self.id = f"{self.name}_{hash(self.name) % 10000}"

        # Initialize metadata if None
        if self.metadata is None:
            self.metadata = {}

        # Initialize capabilities if None
        if self.capabilities is None:
            self.capabilities = []

        # Extract response_time from health if available
        if self.health and isinstance(self.health, dict):
            if "response_time" in self.health and self.response_time is None:
                self.response_time = self.health["response_time"]
            if "status" in self.health and self.health_status == "unknown":
                self.health_status = self.health["status"]

        # Set endpoint based on transport if not provided
        if self.endpoint is None:
            if self.transport == "stdio" and self.command:
                self.endpoint = self.command
            elif self.transport in ["http", "sse"] and self.url:
                self.endpoint = self.url
            else:
                self.endpoint = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerInfo":
        """Create from dictionary format."""
        return cls(**data)

    def is_healthy(self, max_age: float = 300.0) -> bool:
        """Check if server is considered healthy."""
        # Check health dict first
        if self.health and isinstance(self.health, dict):
            status = self.health.get("status", "unknown")
            if status == "healthy":
                age = time.time() - self.last_seen
                return age < max_age
            else:
                return False

        # Fall back to health_status field
        age = time.time() - self.last_seen
        return self.health_status == "healthy" and age < max_age

    def matches_capability(self, capability: str) -> bool:
        """Check if server provides a specific capability."""
        return capability in self.capabilities

    def has_capability(self, capability: str) -> bool:
        """Check if server provides a specific capability (alias for matches_capability)."""
        return self.matches_capability(capability)

    def matches_transport(self, transport: str) -> bool:
        """Check if server supports a transport type."""
        return self.transport == transport

    def matches_filter(self, **filters) -> bool:
        """Check if server matches all provided filter criteria.

        Args:
            **filters: Filter criteria (capability, transport, metadata, name, etc)

        Returns:
            True if all filters match
        """
        # Check capability filter
        if "capability" in filters:
            if not self.has_capability(filters["capability"]):
                return False

        # Check transport filter
        if "transport" in filters:
            if not self.matches_transport(filters["transport"]):
                return False

        # Check name filter
        if "name" in filters:
            if self.name != filters["name"]:
                return False

        # Check metadata filter (as a dict)
        if "metadata" in filters:
            filter_metadata = filters["metadata"]
            if not self.metadata:
                return False
            for key, value in filter_metadata.items():
                if key not in self.metadata or self.metadata[key] != value:
                    return False

        # Check other direct attributes
        for key, value in filters.items():
            if key not in ["capability", "transport", "name", "metadata"]:
                # Check if it's a direct attribute
                if hasattr(self, key):
                    if getattr(self, key) != value:
                        return False
                else:
                    # If not an attribute, check in metadata
                    if self.metadata and key in self.metadata:
                        if self.metadata[key] != value:
                            return False
                    else:
                        return False

        return True

    def get_priority_score(self) -> float:
        """Calculate priority score for load balancing."""
        base_score = 1.0

        # Health bonus
        if self.health_status == "healthy":
            base_score += 0.5
        elif self.health_status == "unhealthy":
            base_score -= 0.5

        # Response time bonus (lower is better)
        if self.response_time:
            if self.response_time < 0.1:  # < 100ms
                base_score += 0.3
            elif self.response_time > 1.0:  # > 1s
                base_score -= 0.3

        # Age penalty
        age = time.time() - self.last_seen
        if age > 60:  # Over 1 minute old
            base_score -= min(0.4, age / 300)  # Max penalty of 0.4

        return max(0.1, base_score)  # Minimum score of 0.1


class DiscoveryBackend(ABC):
    """Abstract base class for discovery backends."""

    @abstractmethod
    async def register_server(self, server_info: ServerInfo) -> bool:
        """Register a server with the discovery backend."""
        pass

    @abstractmethod
    async def deregister_server(self, server_id: str) -> bool:
        """Deregister a server from the discovery backend."""
        pass

    @abstractmethod
    async def get_servers(self, **filters) -> List[ServerInfo]:
        """Get list of servers matching filters."""
        pass

    @abstractmethod
    async def update_server_health(
        self, server_id: str, health_status: str, response_time: Optional[float] = None
    ) -> bool:
        """Update server health status."""
        pass


class FileBasedDiscovery(DiscoveryBackend):
    """File-based service discovery using JSON registry."""

    def __init__(self, registry_path: Union[str, Path] = "mcp_registry.json"):
        """Initialize file-based discovery.

        Args:
            registry_path: Path to the JSON registry file
        """
        self.registry_path = Path(registry_path)
        self._ensure_registry_file()

    @property
    def _servers(self) -> Dict[str, ServerInfo]:
        """Get servers as a dict for compatibility with tests."""
        registry = self._read_registry()
        servers = {}
        for server_id, server_data in registry["servers"].items():
            server_info = ServerInfo.from_dict(server_data)
            servers[server_info.name] = server_info
        return servers

    def _ensure_registry_file(self):
        """Ensure registry file exists."""
        if not self.registry_path.exists():
            self.registry_path.write_text(
                json.dumps(
                    {"servers": {}, "last_updated": time.time(), "version": "1.0"},
                    indent=2,
                )
            )

    def _read_registry(self) -> Dict[str, Any]:
        """Read registry from file."""
        try:
            return json.loads(self.registry_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Failed to read registry: {e}")
            return {"servers": {}, "last_updated": time.time(), "version": "1.0"}

    def _write_registry(self, registry: Dict[str, Any]):
        """Write registry to file."""
        registry["last_updated"] = time.time()
        self.registry_path.write_text(json.dumps(registry, indent=2))

    async def register_server(self, server_info: ServerInfo) -> bool:
        """Register a server in the file registry."""
        try:
            registry = self._read_registry()
            registry["servers"][server_info.id] = server_info.to_dict()
            self._write_registry(registry)
            logger.info(f"Registered server: {server_info.name} ({server_info.id})")
            return True
        except Exception as e:
            logger.error(f"Failed to register server {server_info.id}: {e}")
            return False

    async def deregister_server(self, server_id: str) -> bool:
        """Deregister a server from the file registry."""
        try:
            registry = self._read_registry()
            if server_id in registry["servers"]:
                del registry["servers"][server_id]
                self._write_registry(registry)
                logger.info(f"Deregistered server: {server_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to deregister server {server_id}: {e}")
            return False

    async def unregister_server(self, server_name: str) -> bool:
        """Unregister a server by name (alias for test compatibility)."""
        # Find server by name
        registry = self._read_registry()
        server_id_to_remove = None

        for server_id, server_data in registry["servers"].items():
            if server_data.get("name") == server_name:
                server_id_to_remove = server_id
                break

        if server_id_to_remove:
            return await self.deregister_server(server_id_to_remove)
        return False

    async def get_servers(self, **filters) -> List[ServerInfo]:
        """Get servers matching filters."""
        try:
            registry = self._read_registry()
            servers = []

            for server_data in registry["servers"].values():
                server_info = ServerInfo.from_dict(server_data)

                # Apply filters
                if self._matches_filters(server_info, filters):
                    servers.append(server_info)

            return servers
        except Exception as e:
            logger.error(f"Failed to get servers: {e}")
            return []

    async def discover_servers(self, **filters) -> List[ServerInfo]:
        """Discover servers matching filters (alias for get_servers)."""
        return await self.get_servers(**filters)

    async def get_server(self, server_name: str) -> Optional[ServerInfo]:
        """Get a specific server by name."""
        servers = await self.get_servers()
        for server in servers:
            if server.name == server_name:
                return server
        return None

    async def update_server_health(
        self,
        server_identifier: str,
        health_info: Union[str, Dict[str, Any]],
        response_time: Optional[float] = None,
    ) -> bool:
        """Update server health in the registry.

        Args:
            server_identifier: Server ID or name
            health_info: Health status string or health info dict
            response_time: Optional response time (if health_info is string)
        """
        try:
            registry = self._read_registry()

            # Find server by ID or name
            server_id = None
            for sid, server_data in registry["servers"].items():
                if (
                    sid == server_identifier
                    or server_data.get("name") == server_identifier
                ):
                    server_id = sid
                    break

            if not server_id:
                return False

            # Update health info
            if isinstance(health_info, dict):
                # Full health info dict provided
                registry["servers"][server_id]["health"] = health_info
                if "status" in health_info:
                    registry["servers"][server_id]["health_status"] = health_info[
                        "status"
                    ]
                if "response_time" in health_info:
                    registry["servers"][server_id]["response_time"] = health_info[
                        "response_time"
                    ]
            else:
                # Simple string status
                registry["servers"][server_id]["health_status"] = health_info
                if response_time is not None:
                    registry["servers"][server_id]["response_time"] = response_time

            registry["servers"][server_id]["last_seen"] = time.time()
            self._write_registry(registry)
            return True

        except Exception as e:
            logger.error(f"Failed to update server health {server_identifier}: {e}")
            return False

    def _matches_filters(
        self, server_info: ServerInfo, filters: Dict[str, Any]
    ) -> bool:
        """Check if server matches the provided filters."""
        for key, value in filters.items():
            if key == "capability":
                if not server_info.matches_capability(value):
                    return False
            elif key == "transport":
                if not server_info.matches_transport(value):
                    return False
            elif key == "healthy_only":
                if value and not server_info.is_healthy():
                    return False
            elif key == "name":
                if server_info.name != value:
                    return False
            elif key == "auth_required":
                if server_info.auth_required != value:
                    return False

        return True

    async def save_registry(self, path: str) -> None:
        """Save the current registry to a different file."""
        # Use async file operations to avoid blocking
        import json

        import aiofiles

        try:
            # Read current registry
            registry = self._read_registry()

            # Write to the specified path asynchronously
            async with aiofiles.open(path, "w") as f:
                await f.write(json.dumps(registry, indent=2))

        except Exception as e:
            logger.error(f"Failed to save registry to {path}: {e}")
            raise

    async def load_registry(self, path: str) -> None:
        """Load registry from a different file."""
        import json
        from pathlib import Path

        import aiofiles

        try:
            if not Path(path).exists():
                # Create empty registry if file doesn't exist
                logger.warning(
                    f"Registry file not found: {path}, creating empty registry"
                )
                self._ensure_registry_file()
                return

            # Read from the specified path asynchronously
            async with aiofiles.open(path, "r") as f:
                content = await f.read()
                registry = json.loads(content)

            # Write to our registry path
            self._write_registry(registry)

        except Exception as e:
            logger.error(f"Failed to load registry from {path}: {e}")
            raise


class NetworkDiscovery(asyncio.DatagramProtocol):
    """Network-based discovery using UDP broadcast/multicast."""

    DISCOVERY_PORT = 8765
    MULTICAST_GROUP = "224.0.0.251"

    def __init__(
        self,
        port: int = DISCOVERY_PORT,
        multicast_group: str = None,
        interface: str = "0.0.0.0",
    ):
        """Initialize network discovery.

        Args:
            port: UDP port for discovery
            multicast_group: Multicast group address
            interface: Network interface to bind to
        """
        self.port = port
        self.multicast_group = multicast_group or self.MULTICAST_GROUP
        self.interface = interface
        self.running = False
        self._discovered_servers: Dict[str, ServerInfo] = {}
        self._discovery_socket: Optional[socket.socket] = None
        self._transport = None
        self._protocol = None

    async def start(self):
        """Start network discovery."""
        loop = asyncio.get_event_loop()

        # Create UDP endpoint
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.interface, self.port), reuse_port=True
        )

        self._transport = transport
        self._protocol = protocol
        self.running = True

    async def stop(self):
        """Stop network discovery."""
        self.running = False
        if self._transport:
            self._transport.close()
            self._transport = None
            self._protocol = None

    # AsyncIO DatagramProtocol methods
    def connection_made(self, transport):
        """Called when a connection is made."""
        self._transport = transport
        logger.info(f"Network discovery protocol connected on port {self.port}")

    def datagram_received(self, data, addr):
        """Called when a datagram is received."""
        try:
            message = json.loads(data.decode())
            # Try to get current event loop
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._handle_discovery_message(message, addr))
            except RuntimeError:
                # No event loop, run synchronously
                asyncio.run(self._handle_discovery_message(message, addr))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received from {addr}")
        except Exception as e:
            logger.error(f"Error handling datagram from {addr}: {e}")

    def error_received(self, exc):
        """Called when an error is received."""
        logger.error(f"Network discovery protocol error: {exc}")

    def connection_lost(self, exc):
        """Called when the connection is lost."""
        if exc:
            logger.error(f"Network discovery connection lost: {exc}")
        else:
            logger.info("Network discovery connection closed")
        self.running = False

    async def start_discovery_listener(self):
        """Start listening for server announcements."""
        await self.start()

        # Create UDP socket for listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))

        # Join multicast group
        mreq = socket.inet_aton(self.MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        self._discovery_socket = sock

        logger.info(f"Started network discovery listener on port {self.port}")

        while self.running:
            try:
                # Set timeout to check running flag periodically
                sock.settimeout(1.0)
                data, addr = sock.recvfrom(1024)

                await self._process_announcement(data, addr)

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error in discovery listener: {e}")

    async def _process_announcement(self, data: bytes, addr: tuple):
        """Process server announcement."""
        try:
            announcement = json.loads(data.decode())

            if announcement.get("type") == "mcp_server_announcement":
                server_info = ServerInfo(
                    id=announcement.get("id", str(uuid.uuid4())),
                    name=announcement.get("name", "unknown"),
                    transport=announcement.get("transport", "http"),
                    endpoint=announcement.get("endpoint", f"http://{addr[0]}:8080"),
                    capabilities=announcement.get("capabilities", []),
                    metadata=announcement.get("metadata", {}),
                    health_status="healthy",
                    last_seen=time.time(),
                    version=announcement.get("version", "1.0.0"),
                    auth_required=announcement.get("auth_required", False),
                )

                self._discovered_servers[server_info.id] = server_info
                logger.info(f"Discovered server: {server_info.name} at {addr[0]}")

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Invalid announcement from {addr[0]}: {e}")

    async def _is_port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a port is open on a host.

        Args:
            host: Host to check
            port: Port to check
            timeout: Connection timeout

        Returns:
            True if port is open, False otherwise
        """
        try:
            # Create socket connection with timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (OSError, socket.error, socket.timeout):
            return False

    async def scan_network(
        self, network: str = "192.168.1.0/24", timeout: float = 5.0
    ) -> List[ServerInfo]:
        """Actively scan network for MCP servers.

        Args:
            network: Network to scan (CIDR notation)
            timeout: Scan timeout in seconds

        Returns:
            List of discovered servers
        """
        import ipaddress

        discovered = []
        network_obj = ipaddress.IPv4Network(network, strict=False)

        logger.info(f"Scanning network {network} for MCP servers...")

        # Create semaphore to limit concurrent connections
        semaphore = asyncio.Semaphore(50)

        async def scan_host(ip: str):
            async with semaphore:
                try:
                    # Try common MCP ports
                    for port in [8080, 8765, 3000, 5000]:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(str(ip), port), timeout=1.0
                            )

                            # Send MCP discovery request
                            discovery_request = json.dumps(
                                {"type": "mcp_discovery_request", "version": "1.0"}
                            ).encode()

                            writer.write(discovery_request)
                            await writer.drain()

                            # Read response
                            response_data = await asyncio.wait_for(
                                reader.read(1024), timeout=2.0
                            )

                            response = json.loads(response_data.decode())

                            if response.get("type") == "mcp_discovery_response":
                                server_info = ServerInfo(
                                    id=response.get("id", str(uuid.uuid4())),
                                    name=response.get("name", f"server-{ip}"),
                                    transport=response.get("transport", "http"),
                                    endpoint=f"http://{ip}:{port}",
                                    capabilities=response.get("capabilities", []),
                                    metadata=response.get("metadata", {}),
                                    health_status="healthy",
                                    version=response.get("version", "1.0.0"),
                                    auth_required=response.get("auth_required", False),
                                )
                                discovered.append(server_info)
                                break

                            writer.close()
                            await writer.wait_closed()

                        except (
                            asyncio.TimeoutError,
                            ConnectionRefusedError,
                            json.JSONDecodeError,
                        ):
                            continue
                        except Exception as e:
                            logger.debug(f"Error scanning {ip}:{port}: {e}")
                            continue

                except Exception as e:
                    logger.debug(f"Error scanning host {ip}: {e}")

        # Scan all hosts in parallel
        tasks = [scan_host(ip) for ip in network_obj.hosts()]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Network scan completed. Found {len(discovered)} servers.")
        return discovered

    def _send_message(self, message: Dict[str, Any], address: tuple = None):
        """Send a message over the network."""
        if not self._transport:
            logger.warning("Transport not initialized")
            return

        data = json.dumps(message).encode()

        if address:
            self._transport.sendto(data, address)
        else:
            # Broadcast/multicast
            self._transport.sendto(data, (self.multicast_group, self.port))

    async def announce_server(self, server_info: ServerInfo):
        """Announce a server on the network."""
        message = {"type": "server_announcement", "server": server_info.to_dict()}
        self._send_message(message)

    def stop_discovery(self):
        """Stop network discovery."""
        self.running = False
        if self._discovery_socket:
            self._discovery_socket.close()
            self._discovery_socket = None
        logger.info("Stopped network discovery")

    def get_discovered_servers(self) -> List[ServerInfo]:
        """Get list of currently discovered servers."""
        # Filter out stale servers (older than 5 minutes)
        current_time = time.time()
        active_servers = []

        for server in self._discovered_servers.values():
            if current_time - server.last_seen < 300:  # 5 minutes
                active_servers.append(server)

        return active_servers

    async def discover_servers(self, **filters) -> List[ServerInfo]:
        """Discover servers on the network (returns already discovered servers).

        Args:
            **filters: Filters to apply (capability, transport, etc)

        Returns:
            List of servers matching filters
        """
        servers = self.get_discovered_servers()

        # Apply filters
        if filters:
            filtered = []
            for server in servers:
                if server.matches_filter(**filters):
                    filtered.append(server)
            return filtered

        return servers

    async def _handle_discovery_message(self, message: Dict[str, Any], addr: tuple):
        """Handle incoming discovery message."""
        msg_type = message.get("type")

        if msg_type == "server_announcement":
            # Handle server announcement
            server_data = message.get("server", {})
            server_info = ServerInfo.from_dict(server_data)
            server_info.last_seen = time.time()

            # Store by name
            self._discovered_servers[server_info.name] = server_info
            logger.info(f"Discovered server: {server_info.name} from {addr}")

        elif msg_type == "server_query":
            # Respond to server queries
            pass

        else:
            logger.debug(f"Unknown message type: {msg_type}")


class ServiceRegistry:
    """Main service registry coordinating multiple discovery backends."""

    def __init__(self, backends: Optional[List[DiscoveryBackend]] = None):
        """Initialize service registry.

        Args:
            backends: List of discovery backends to use
        """
        if backends is None:
            backends = [FileBasedDiscovery()]

        self.backends = backends
        self.health_checker = HealthChecker()  # Initialize health checker
        self.load_balancer = LoadBalancer()
        self.service_mesh = ServiceMesh(self)
        self._server_cache: Dict[str, ServerInfo] = {}
        self._cache_expiry = 60.0  # Cache for 1 minute
        self._last_cache_update = 0.0

    async def register_server(
        self, server_info: Union[ServerInfo, Dict[str, Any]]
    ) -> bool:
        """Register a server with all backends.

        Args:
            server_info: ServerInfo object or server configuration dictionary

        Returns:
            True if registration succeeded in at least one backend
        """
        # Convert config to ServerInfo if needed
        if isinstance(server_info, dict):
            server_config = server_info
            server_info = ServerInfo(
                name=server_config["name"],
                transport=server_config["transport"],
                capabilities=server_config.get("capabilities", []),
                id=server_config.get("id"),
                endpoint=server_config.get("endpoint"),
                command=server_config.get("command"),
                args=server_config.get("args"),
                url=server_config.get("url"),
                metadata=server_config.get("metadata", {}),
                auth_required=server_config.get("auth_required", False),
                version=server_config.get("version", "1.0.0"),
            )

        success_count = 0
        for backend in self.backends:
            try:
                if await backend.register_server(server_info):
                    success_count += 1
            except Exception as e:
                logger.error(
                    f"Backend {type(backend).__name__} registration failed: {e}"
                )

        if success_count > 0:
            # Update cache
            self._server_cache[server_info.id] = server_info
            logger.info(
                f"Successfully registered server {server_info.name} with {success_count} backends"
            )
            return True

        return False

    async def deregister_server(self, server_id: str) -> bool:
        """Deregister a server from all backends."""
        success_count = 0
        for backend in self.backends:
            try:
                if await backend.deregister_server(server_id):
                    success_count += 1
            except Exception as e:
                logger.error(
                    f"Backend {type(backend).__name__} deregistration failed: {e}"
                )

        # Remove from cache
        if server_id in self._server_cache:
            del self._server_cache[server_id]

        return success_count > 0

    async def discover_servers(self, **filters) -> List[ServerInfo]:
        """Discover servers matching the given filters.

        Args:
            **filters: Filter criteria (capability, transport, healthy_only, etc.)

        Returns:
            List of matching servers, deduplicated and sorted by priority
        """
        # Check cache first
        if (
            time.time() - self._last_cache_update
        ) < self._cache_expiry and not filters.get("force_refresh"):
            cached_servers = list(self._server_cache.values())
            return self._filter_and_sort_servers(cached_servers, filters)

        # Fetch from all backends
        all_servers: Dict[str, ServerInfo] = {}

        for backend in self.backends:
            try:
                servers = await backend.get_servers(**filters)
                for server in servers:
                    # Use latest info if server exists in multiple backends
                    if (
                        server.id not in all_servers
                        or server.last_seen > all_servers[server.id].last_seen
                    ):
                        all_servers[server.id] = server
            except Exception as e:
                logger.error(f"Backend {type(backend).__name__} discovery failed: {e}")

        # Update cache
        self._server_cache = all_servers.copy()
        self._last_cache_update = time.time()

        servers_list = list(all_servers.values())
        return self._filter_and_sort_servers(servers_list, filters)

    def _filter_and_sort_servers(
        self, servers: List[ServerInfo], filters: Dict[str, Any]
    ) -> List[ServerInfo]:
        """Filter and sort servers by priority."""
        filtered_servers = []

        for server in servers:
            # Apply remaining filters not handled by backends
            if filters.get("healthy_only") and not server.is_healthy():
                continue
            if filters.get("capability") and not server.matches_capability(
                filters["capability"]
            ):
                continue
            if filters.get("transport") and not server.matches_transport(
                filters["transport"]
            ):
                continue

            filtered_servers.append(server)

        # Sort by priority score (highest first)
        filtered_servers.sort(key=lambda s: s.get_priority_score(), reverse=True)

        return filtered_servers

    async def get_best_server(
        self, capability: str, transport: Optional[str] = None
    ) -> Optional[ServerInfo]:
        """Get the best server for a specific capability.

        Args:
            capability: Required capability
            transport: Preferred transport type

        Returns:
            Best available server or None
        """
        filters = {"capability": capability, "healthy_only": True}
        if transport:
            filters["transport"] = transport

        servers = await self.discover_servers(**filters)
        return servers[0] if servers else None

    def start_health_checking(self, interval: float = 30.0):
        """Start periodic health checking of registered servers.

        Args:
            interval: Health check interval in seconds
        """
        if not self.health_checker:
            self.health_checker = HealthChecker(self)

        asyncio.create_task(self.health_checker.start_periodic_checks(interval))

    def stop_health_checking(self):
        """Stop health checking."""
        if self.health_checker:
            self.health_checker.stop()

    async def start_health_monitoring(self, interval: float = 30.0):
        """Start health monitoring (async version)."""
        if self.health_checker:
            await self.health_checker.start(self)

    async def stop_health_monitoring(self):
        """Stop health monitoring (async version)."""
        if self.health_checker:
            await self.health_checker.stop()

    async def get_best_server_for_capability(
        self, capability: str
    ) -> Optional[ServerInfo]:
        """Get best server for capability (async version)."""
        return await self.get_best_server(capability)


class HealthChecker:
    """Health checker for registered MCP servers."""

    def __init__(self, registry: ServiceRegistry = None, check_interval: float = 30.0):
        """Initialize health checker.

        Args:
            registry: Service registry to check (optional)
            check_interval: Default check interval in seconds
        """
        self.registry = registry
        self.check_interval = check_interval
        self._running = False
        self._check_task = None
        self.running = False  # Keep for backward compatibility

    async def start(self, registry: ServiceRegistry = None):
        """Start health checking with the registry."""
        if registry:
            self.registry = registry
        if not self.registry:
            raise ValueError("No registry provided for health checking")

        # Set running state immediately
        self._running = True
        self.running = True

        # Start periodic checks
        self._check_task = asyncio.create_task(
            self.start_periodic_checks(self.check_interval)
        )

    async def start_periodic_checks(self, interval: float = 30.0):
        """Start periodic health checks.

        Args:
            interval: Check interval in seconds
        """
        self._running = True
        self.running = True  # Keep for backward compatibility
        logger.info(f"Started health checking with {interval}s interval")

        while self._running:
            try:
                await self.check_all_servers()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in health checking: {e}")
                await asyncio.sleep(min(interval, 10))  # Back off on error

    async def check_all_servers(self):
        """Check health of all registered servers."""
        # Get all servers without filters
        servers = await self.registry.discover_servers(force_refresh=True)

        # Check health in parallel with limited concurrency
        semaphore = asyncio.Semaphore(10)

        async def check_server(server: ServerInfo):
            async with semaphore:
                health_result = await self.check_server_health(server)
                health_status = health_result["status"]
                response_time = health_result.get("response_time")

                # Update health in all backends
                for backend in self.registry.backends:
                    try:
                        await backend.update_server_health(
                            server.id, health_status, response_time
                        )
                    except Exception as e:
                        logger.error(f"Failed to update health for {server.id}: {e}")

        # Run health checks in parallel
        await asyncio.gather(
            *[check_server(server) for server in servers], return_exceptions=True
        )

    async def check_server_health(self, server: ServerInfo) -> Dict[str, Any]:
        """Check health of a single server.

        Args:
            server: Server to check

        Returns:
            Dictionary with status and response_time
        """
        start_time = time.time()

        try:
            if server.transport == "http" or server.transport == "sse":
                # HTTP/SSE health check
                import aiohttp

                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    # Try health endpoint first (use configured endpoint or default to /health)
                    health_path = server.health_endpoint or "/health"
                    base_url = server.endpoint or server.url or ""
                    health_url = f"{base_url.rstrip('/')}{health_path}"
                    try:
                        async with session.get(health_url) as response:
                            if response.status == 200:
                                response_time = time.time() - start_time
                                return {
                                    "status": "healthy",
                                    "response_time": response_time,
                                }
                    except:
                        pass

                    # Fallback to main endpoint
                    try:
                        async with session.get(server.endpoint) as response:
                            response_time = time.time() - start_time
                            if response.status < 500:
                                return {
                                    "status": "healthy",
                                    "response_time": response_time,
                                }
                            else:
                                return {
                                    "status": "unhealthy",
                                    "response_time": response_time,
                                }
                    except:
                        return {"status": "unhealthy", "response_time": None}

            elif server.transport == "stdio":
                # For stdio, check if command exists and is executable
                if server.command:
                    try:
                        # Test if we can run the command
                        import asyncio

                        process = await asyncio.create_subprocess_exec(
                            server.command,
                            *(server.args if server.args else []),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        returncode = await process.wait()
                        response_time = time.time() - start_time

                        if returncode == 0:
                            return {"status": "healthy", "response_time": response_time}
                        else:
                            return {
                                "status": "unhealthy",
                                "response_time": response_time,
                            }
                    except Exception as e:
                        return {
                            "status": "unhealthy",
                            "response_time": None,
                            "error": str(e),
                        }
                else:
                    # No command specified, check if recently seen
                    age = time.time() - server.last_seen
                    if age < 300:  # 5 minutes
                        return {"status": "healthy", "response_time": None}
                    else:
                        return {"status": "unknown", "response_time": None}

            else:
                logger.warning(
                    f"Unknown transport type for health check: {server.transport}"
                )
                return {"status": "unknown", "response_time": None}

        except Exception as e:
            logger.debug(f"Health check failed for {server.name}: {e}")
            return {"status": "unhealthy", "response_time": None}

    async def stop(self):
        """Stop health checking."""
        self._running = False
        self.running = False
        if self._check_task:
            self._check_task.cancel()
            self._check_task = None
        logger.info("Stopped health checking")


class ServiceMesh:
    """Service mesh for intelligent client routing and load balancing."""

    def __init__(self, registry: ServiceRegistry):
        """Initialize service mesh.

        Args:
            registry: Service registry to use
        """
        self.registry = registry
        self._client_cache: Dict[str, Any] = {}
        self._load_balancer = LoadBalancer()

    async def get_client_for_capability(
        self, capability: str, transport: Optional[str] = None
    ) -> Optional[Any]:
        """Get an MCP client for a specific capability.

        Args:
            capability: Required capability
            transport: Preferred transport type

        Returns:
            Configured MCP client or None
        """
        # Find best server
        server = await self.registry.get_best_server(capability, transport)
        if not server:
            logger.warning(f"No server found for capability: {capability}")
            return None

        # Check cache
        cache_key = f"{server.id}_{capability}"
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # Create new client
        try:
            client = await self._create_client(server)
            self._client_cache[cache_key] = client
            logger.info(f"Created MCP client for {server.name} ({capability})")
            return client
        except Exception as e:
            logger.error(f"Failed to create client for {server.name}: {e}")
            return None

    async def call_with_failover(
        self,
        capability: str,
        tool_name: str,
        arguments: Dict[str, Any],
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Call a tool with automatic failover to backup servers.

        Args:
            capability: Required capability
            tool_name: Tool to call
            arguments: Tool arguments
            max_retries: Maximum retry attempts

        Returns:
            Tool result
        """
        servers = await self.registry.discover_servers(
            capability=capability, healthy_only=True
        )

        if not servers:
            raise ServiceDiscoveryError(
                f"No healthy servers found for capability: {capability}"
            )

        last_error = None

        for attempt in range(max_retries):
            # Select server using load balancer
            server = self._load_balancer.select_server(servers)
            if not server:
                break

            try:
                # Create client for the selected server
                client = await self._create_client(server)

                # Call the tool
                result = await client.call_tool(tool_name, arguments)

                # Record successful call
                self._load_balancer.record_success(server.id)
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"Call to {server.name} failed: {e}")

                # Record failure and remove from current attempt
                self._load_balancer.record_failure(server.id)
                servers = [s for s in servers if s.id != server.id]

        # All retries failed
        raise ServiceDiscoveryError(
            f"All servers failed for capability {capability}: {last_error}"
        )

    def _create_server_config(self, server: ServerInfo) -> Dict[str, Any]:
        """Create server configuration for MCP client.

        Args:
            server: Server information

        Returns:
            Server configuration dictionary
        """
        if server.transport == "stdio":
            # Parse command from endpoint
            if server.endpoint.startswith("python "):
                command_parts = server.endpoint.split()
                return {
                    "transport": "stdio",
                    "command": command_parts[0],
                    "args": command_parts[1:],
                    "env": server.metadata.get("env", {}),
                }
            else:
                return {
                    "transport": "stdio",
                    "command": server.endpoint,
                    "args": [],
                    "env": server.metadata.get("env", {}),
                }

        elif server.transport in ["http", "sse"]:
            config = {"transport": server.transport, "url": server.endpoint}

            # Add authentication config if present
            if server.auth_required:
                auth_config = server.metadata.get("auth_config", {})
                if auth_config:
                    config["auth"] = auth_config

            return config

        else:
            # Fallback configuration
            return {"transport": server.transport, "url": server.endpoint}

    async def _create_client(self, server: ServerInfo) -> Any:
        """Create a client for the given server.

        Args:
            server: Server to create client for

        Returns:
            MCP client instance
        """
        try:
            from .client import MCPClient

            # Create client configuration based on transport
            if server.transport == "stdio":
                client = MCPClient(
                    transport="stdio",
                    command=server.command,
                    args=server.args,
                    env=server.metadata.get("env", {}),
                )
            elif server.transport in ["http", "sse"]:
                client = MCPClient(
                    transport=server.transport, url=server.url or server.endpoint
                )
            else:
                raise ValueError(f"Unsupported transport: {server.transport}")

            return client
        except Exception as e:
            logger.error(f"Failed to create client for {server.name}: {e}")
            raise


class LoadBalancer:
    """Load balancer for distributing requests across servers."""

    def __init__(self):
        """Initialize load balancer."""
        self._server_stats: Dict[str, Dict[str, Any]] = {}

    def select_server(self, servers: List[ServerInfo]) -> Optional[ServerInfo]:
        """Select best server based on load balancing algorithm.

        Args:
            servers: List of available servers

        Returns:
            Selected server or None
        """
        if not servers:
            return None

        # Weight servers by priority score and current load
        weighted_servers = []

        for server in servers:
            base_weight = server.get_priority_score()

            # Adjust weight based on current load
            stats = self._server_stats.get(server.id, {})
            recent_failures = stats.get("recent_failures", 0)
            recent_calls = stats.get("recent_calls", 0)

            # Penalty for recent failures
            if recent_failures > 0:
                base_weight *= 1.0 - min(0.5, recent_failures * 0.1)

            # Penalty for high load
            if recent_calls > 10:
                base_weight *= 1.0 - min(0.3, (recent_calls - 10) * 0.02)

            weighted_servers.append((server, max(0.1, base_weight)))

        # Select using weighted random
        import random

        total_weight = sum(weight for _, weight in weighted_servers)

        if total_weight == 0:
            return servers[0]  # Fallback to first server

        r = random.uniform(0, total_weight)
        current_weight = 0

        for server, weight in weighted_servers:
            current_weight += weight
            if r <= current_weight:
                return server

        return servers[0]  # Fallback

    def record_success(self, server_id: str):
        """Record successful call to server."""
        if server_id not in self._server_stats:
            self._server_stats[server_id] = {
                "recent_calls": 0,
                "recent_failures": 0,
                "last_reset": time.time(),
            }

        stats = self._server_stats[server_id]
        stats["recent_calls"] += 1

        # Decay recent failures on success
        stats["recent_failures"] = max(0, stats["recent_failures"] - 1)

        self._maybe_reset_stats(server_id)

    def record_failure(self, server_id: str):
        """Record failed call to server."""
        if server_id not in self._server_stats:
            self._server_stats[server_id] = {
                "recent_calls": 0,
                "recent_failures": 0,
                "last_reset": time.time(),
            }

        stats = self._server_stats[server_id]
        stats["recent_failures"] += 1

        self._maybe_reset_stats(server_id)

    def _maybe_reset_stats(self, server_id: str):
        """Reset stats if they're getting stale."""
        stats = self._server_stats[server_id]
        if time.time() - stats["last_reset"] > 300:  # Reset every 5 minutes
            stats["recent_calls"] = 0
            stats["recent_failures"] = 0
            stats["last_reset"] = time.time()

    def _calculate_priority_score(self, server: ServerInfo) -> float:
        """Calculate priority score for a server.

        Args:
            server: Server to calculate score for

        Returns:
            Priority score (0 means unhealthy)
        """
        # Unhealthy servers get 0 score
        if hasattr(server, "health") and server.health:
            if server.health.get("status") == "unhealthy":
                return 0
        elif server.health_status == "unhealthy":
            return 0

        # Use server's get_priority_score method
        return server.get_priority_score()

    def select_best_server(self, servers: List[ServerInfo]) -> Optional[ServerInfo]:
        """Select the best server based on priority scores.

        Args:
            servers: List of servers to choose from

        Returns:
            Best server or None
        """
        if not servers:
            return None

        # Score and sort servers
        scored_servers = [
            (server, self._calculate_priority_score(server)) for server in servers
        ]
        scored_servers.sort(key=lambda x: x[1], reverse=True)

        # Return best server (highest score)
        return scored_servers[0][0] if scored_servers else None

    def select_servers_round_robin(
        self, servers: List[ServerInfo], count: int
    ) -> List[ServerInfo]:
        """Select servers using round-robin algorithm.

        Args:
            servers: List of available servers
            count: Number of servers to select

        Returns:
            Selected servers
        """
        if not servers:
            return []

        # Track round-robin state
        if not hasattr(self, "_round_robin_index"):
            self._round_robin_index = {}

        # Create a key for this server list
        server_key = tuple(s.name for s in servers)

        if server_key not in self._round_robin_index:
            self._round_robin_index[server_key] = 0

        selected = []
        start_index = self._round_robin_index[server_key]

        for i in range(count):
            index = (start_index + i) % len(servers)
            selected.append(servers[index])

        # Update index for next call
        self._round_robin_index[server_key] = (start_index + count) % len(servers)

        return selected

    def select_servers(
        self, servers: List[ServerInfo], count: int = 1, strategy: str = "priority"
    ) -> List[ServerInfo]:
        """Select multiple servers based on strategy.

        Args:
            servers: List of available servers
            count: Number of servers to select
            strategy: Selection strategy ("priority", "round_robin", "random")

        Returns:
            Selected servers
        """
        if not servers:
            return []

        count = min(count, len(servers))

        if strategy == "round_robin":
            return self.select_servers_round_robin(servers, count)
        elif strategy == "random":
            import random

            return random.sample(servers, count)
        else:  # priority
            # Sort by priority score
            scored = [(s, self._calculate_priority_score(s)) for s in servers]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [s[0] for s in scored[:count]]


# Convenience functions for easy setup
def create_default_registry() -> ServiceRegistry:
    """Create a default service registry with file and network discovery."""
    file_backend = FileBasedDiscovery()
    return ServiceRegistry([file_backend])


async def discover_mcp_servers(
    capability: Optional[str] = None, transport: Optional[str] = None
) -> List[ServerInfo]:
    """Discover MCP servers with optional filtering.

    Args:
        capability: Filter by capability
        transport: Filter by transport type

    Returns:
        List of discovered servers
    """
    registry = create_default_registry()

    filters = {}
    if capability:
        filters["capability"] = capability
    if transport:
        filters["transport"] = transport

    return await registry.discover_servers(**filters)


async def get_mcp_client(capability: str, transport: Optional[str] = None):
    """Get an MCP client for a specific capability.

    Args:
        capability: Required capability
        transport: Preferred transport type

    Returns:
        Configured MCP client
    """
    registry = create_default_registry()
    mesh = ServiceMesh(registry)

    return await mesh.get_client_for_capability(capability, transport)
