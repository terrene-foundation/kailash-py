"""Unit tests for MCP service discovery system."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.discovery import (
    DiscoveryBackend,
    FileBasedDiscovery,
    HealthChecker,
    LoadBalancer,
    NetworkDiscovery,
    ServerInfo,
    ServiceMesh,
    ServiceRegistry,
    create_default_registry,
    discover_mcp_servers,
    get_mcp_client,
)
from kailash.mcp_server.errors import ServiceDiscoveryError


class TestServerInfo:
    """Test server information representation."""

    def test_server_info_creation(self):
        """Test creating server info."""
        server = ServerInfo(
            name="test-server",
            transport="stdio",
            command="python",
            args=["-m", "test_server"],
            capabilities=["tools", "resources"],
            metadata={"version": "1.0.0"},
        )

        assert server.name == "test-server"
        assert server.transport == "stdio"
        assert server.command == "python"
        assert server.args == ["-m", "test_server"]
        assert "tools" in server.capabilities
        assert server.metadata["version"] == "1.0.0"

    def test_server_info_to_dict(self):
        """Test converting server info to dictionary."""
        server = ServerInfo(
            name="test-server",
            transport="http",
            url="http://localhost:8000",
            capabilities=["tools"],
        )

        data = server.to_dict()

        assert data["name"] == "test-server"
        assert data["transport"] == "http"
        assert data["url"] == "http://localhost:8000"
        assert data["capabilities"] == ["tools"]

    def test_server_info_from_dict(self):
        """Test creating server info from dictionary."""
        data = {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "server"],
            "capabilities": ["tools", "resources"],
            "health": {"status": "healthy", "last_check": 1234567890},
        }

        server = ServerInfo.from_dict(data)

        assert server.name == "test-server"
        assert server.transport == "stdio"
        assert server.command == "python"
        assert server.args == ["-m", "server"]
        assert server.capabilities == ["tools", "resources"]
        assert server.health["status"] == "healthy"

    def test_server_info_is_healthy(self):
        """Test checking if server is healthy."""
        # Healthy server
        healthy_server = ServerInfo(
            name="healthy",
            transport="stdio",
            health={"status": "healthy", "last_check": time.time()},
        )
        assert healthy_server.is_healthy() is True

        # Unhealthy server
        unhealthy_server = ServerInfo(
            name="unhealthy",
            transport="stdio",
            health={"status": "unhealthy", "last_check": time.time()},
        )
        assert unhealthy_server.is_healthy() is False

        # No health info
        unknown_server = ServerInfo(name="unknown", transport="stdio")
        assert unknown_server.is_healthy() is False

    def test_server_info_has_capability(self):
        """Test checking if server has capability."""
        server = ServerInfo(
            name="test",
            transport="stdio",
            capabilities=["tools", "resources", "prompts"],
        )

        assert server.has_capability("tools") is True
        assert server.has_capability("resources") is True
        assert server.has_capability("admin") is False

    def test_server_info_matches_filter(self):
        """Test checking if server matches filter criteria."""
        server = ServerInfo(
            name="api-server",
            transport="http",
            capabilities=["tools", "resources"],
            metadata={"environment": "production", "version": "2.1.0"},
        )

        # Test capability filter
        assert server.matches_filter(capability="tools") is True
        assert server.matches_filter(capability="admin") is False

        # Test transport filter
        assert server.matches_filter(transport="http") is True
        assert server.matches_filter(transport="stdio") is False

        # Test metadata filter
        assert server.matches_filter(metadata={"environment": "production"}) is True
        assert server.matches_filter(metadata={"environment": "development"}) is False

        # Test name filter
        assert server.matches_filter(name="api-server") is True
        assert server.matches_filter(name="other-server") is False


class TestFileBasedDiscovery:
    """Test file-based discovery backend."""

    def setup_method(self):
        """Set up test environment."""
        # Use a temporary file for each test
        import tempfile

        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.temp_file.close()
        self.discovery = FileBasedDiscovery(self.temp_file.name)

    def teardown_method(self):
        """Clean up test environment."""
        import os

        if hasattr(self, "temp_file") and os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    @pytest.mark.asyncio
    async def test_register_server(self):
        """Test registering a server."""
        server = ServerInfo(
            name="test-server",
            transport="stdio",
            command="python",
            args=["-m", "test_server"],
        )

        await self.discovery.register_server(server)

        assert "test-server" in self.discovery._servers
        assert self.discovery._servers["test-server"] == server

    @pytest.mark.asyncio
    async def test_unregister_server(self):
        """Test unregistering a server."""
        server = ServerInfo(name="test-server", transport="stdio")
        await self.discovery.register_server(server)

        result = await self.discovery.unregister_server("test-server")
        assert result is True
        assert "test-server" not in self.discovery._servers

        # Try to unregister again
        result = await self.discovery.unregister_server("test-server")
        assert result is False

    @pytest.mark.asyncio
    async def test_discover_servers_no_filter(self):
        """Test discovering all servers."""
        server1 = ServerInfo(name="server1", transport="stdio", capabilities=["tools"])
        server2 = ServerInfo(
            name="server2", transport="http", capabilities=["resources"]
        )

        await self.discovery.register_server(server1)
        await self.discovery.register_server(server2)

        servers = await self.discovery.discover_servers()

        assert len(servers) == 2
        server_names = [s.name for s in servers]
        assert "server1" in server_names
        assert "server2" in server_names

    @pytest.mark.asyncio
    async def test_discover_servers_with_capability_filter(self):
        """Test discovering servers with capability filter."""
        server1 = ServerInfo(
            name="tools-server", transport="stdio", capabilities=["tools"]
        )
        server2 = ServerInfo(
            name="resources-server", transport="http", capabilities=["resources"]
        )
        server3 = ServerInfo(
            name="both-server", transport="stdio", capabilities=["tools", "resources"]
        )

        await self.discovery.register_server(server1)
        await self.discovery.register_server(server2)
        await self.discovery.register_server(server3)

        tools_servers = await self.discovery.discover_servers(capability="tools")

        assert len(tools_servers) == 2
        server_names = [s.name for s in tools_servers]
        assert "tools-server" in server_names
        assert "both-server" in server_names
        assert "resources-server" not in server_names

    @pytest.mark.asyncio
    async def test_discover_servers_with_transport_filter(self):
        """Test discovering servers with transport filter."""
        server1 = ServerInfo(name="stdio-server", transport="stdio")
        server2 = ServerInfo(name="http-server", transport="http")

        await self.discovery.register_server(server1)
        await self.discovery.register_server(server2)

        stdio_servers = await self.discovery.discover_servers(transport="stdio")

        assert len(stdio_servers) == 1
        assert stdio_servers[0].name == "stdio-server"

    @pytest.mark.asyncio
    async def test_get_server(self):
        """Test getting specific server."""
        server = ServerInfo(name="test-server", transport="stdio")
        await self.discovery.register_server(server)

        retrieved = await self.discovery.get_server("test-server")
        assert retrieved is not None
        assert retrieved.name == "test-server"

        # Non-existent server
        not_found = await self.discovery.get_server("nonexistent")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_update_server_health(self):
        """Test updating server health status."""
        server = ServerInfo(name="test-server", transport="stdio")
        await self.discovery.register_server(server)

        health_info = {
            "status": "healthy",
            "last_check": time.time(),
            "response_time": 0.1,
        }
        await self.discovery.update_server_health("test-server", health_info)

        updated_server = await self.discovery.get_server("test-server")
        assert updated_server.health["status"] == "healthy"
        assert updated_server.health["response_time"] == 0.1

    @pytest.mark.asyncio
    async def test_save_and_load_registry(self):
        """Test saving and loading server registry."""
        # Register some servers
        server1 = ServerInfo(name="server1", transport="stdio", capabilities=["tools"])
        server2 = ServerInfo(
            name="server2", transport="http", capabilities=["resources"]
        )

        await self.discovery.register_server(server1)
        await self.discovery.register_server(server2)

        # Mock aiofiles for save operation
        mock_file = AsyncMock()
        saved_content = None

        async def capture_write(content):
            nonlocal saved_content
            saved_content = content

        mock_file.write = capture_write

        with patch("aiofiles.open") as mock_aiofiles_open:
            # Create async context manager
            mock_aiofiles_open.return_value.__aenter__.return_value = mock_file
            mock_aiofiles_open.return_value.__aexit__.return_value = None

            await self.discovery.save_registry("test_registry.json")

            mock_aiofiles_open.assert_called_once_with("test_registry.json", "w")

            # Verify the saved data
            assert saved_content is not None
            import json

            saved_data = json.loads(saved_content)
            assert len(saved_data["servers"]) == 2

    @pytest.mark.asyncio
    async def test_load_registry_file_not_found(self):
        """Test loading registry when file doesn't exist."""
        from pathlib import Path

        with patch.object(Path, "exists", return_value=False):
            # Should not raise exception
            await self.discovery.load_registry("nonexistent.json")

            # Registry should still have any servers that were already registered
            # (it just logs a warning and returns without changing the registry)

    @pytest.mark.asyncio
    async def test_load_registry_success(self):
        """Test successfully loading registry from file."""
        from pathlib import Path

        # Create test registry data
        test_registry = {
            "servers": {
                "server1": {
                    "name": "server1",
                    "transport": "stdio",
                    "capabilities": ["tools"],
                    "health_status": "healthy",
                },
                "server2": {
                    "name": "server2",
                    "transport": "http",
                    "capabilities": ["resources"],
                    "health_status": "healthy",
                },
            },
            "last_updated": time.time(),
            "version": "1.0",
        }

        # Mock file reading
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=json.dumps(test_registry))

        with patch.object(Path, "exists", return_value=True):
            with patch("aiofiles.open") as mock_aiofiles_open:
                # Create async context manager
                mock_aiofiles_open.return_value.__aenter__.return_value = mock_file
                mock_aiofiles_open.return_value.__aexit__.return_value = None

                # Clear any existing servers first
                self.discovery._servers.clear()

                # Load the registry
                await self.discovery.load_registry("test_registry.json")

                # Verify servers were loaded
                servers = await self.discovery.discover_servers()
                assert len(servers) == 2
                assert any(s.name == "server1" for s in servers)
                assert any(s.name == "server2" for s in servers)


class TestNetworkDiscovery:
    """Test network-based discovery backend."""

    def setup_method(self):
        """Set up test environment."""
        self.discovery = NetworkDiscovery(
            multicast_group="224.0.0.100", port=12345, interface="0.0.0.0"
        )

    def test_network_discovery_initialization(self):
        """Test network discovery initialization."""
        assert self.discovery.multicast_group == "224.0.0.100"
        assert self.discovery.port == 12345
        assert self.discovery.interface == "0.0.0.0"

    @pytest.mark.asyncio
    async def test_start_stop_discovery(self):
        """Test starting and stopping network discovery."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_transport = MagicMock()
            mock_protocol = MagicMock()
            mock_loop.return_value.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )

            await self.discovery.start()
            assert self.discovery._transport is mock_transport

            await self.discovery.stop()
            mock_transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_announce_server(self):
        """Test announcing server on network."""
        server = ServerInfo(
            name="test-server",
            transport="stdio",
            command="python",
            args=["-m", "server"],
        )

        with patch.object(self.discovery, "_send_message") as mock_send:
            await self.discovery.announce_server(server)

            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            message = call_args[0]
            assert message["type"] == "server_announcement"
            assert message["server"]["name"] == "test-server"

    def test_handle_server_announcement(self):
        """Test handling incoming server announcement."""
        announcement = {
            "type": "server_announcement",
            "server": {
                "name": "remote-server",
                "transport": "http",
                "url": "http://192.168.1.100:8080",
                "capabilities": ["tools"],
            },
        }

        # Mock the datagram_received method
        data = json.dumps(announcement).encode()
        addr = ("192.168.1.100", 12345)

        self.discovery.datagram_received(data, addr)

        # Server should be registered
        assert "remote-server" in self.discovery._discovered_servers

    def test_handle_invalid_announcement(self):
        """Test handling invalid announcement data."""
        # Invalid JSON
        invalid_data = b"invalid json data"
        addr = ("192.168.1.100", 12345)

        # Should not raise exception
        self.discovery.datagram_received(invalid_data, addr)

    @pytest.mark.asyncio
    async def test_discover_servers_network(self):
        """Test discovering servers from network announcements."""
        # Simulate some discovered servers
        server1 = ServerInfo(name="server1", transport="http")
        server2 = ServerInfo(name="server2", transport="stdio")

        self.discovery._discovered_servers["server1"] = server1
        self.discovery._discovered_servers["server2"] = server2

        servers = await self.discovery.discover_servers()

        assert len(servers) == 2
        server_names = [s.name for s in servers]
        assert "server1" in server_names
        assert "server2" in server_names

    @pytest.mark.asyncio
    async def test_discover_servers_with_filter(self):
        """Test discovering servers with filters."""
        server1 = ServerInfo(
            name="tools-server", transport="http", capabilities=["tools"]
        )
        server2 = ServerInfo(
            name="resources-server", transport="stdio", capabilities=["resources"]
        )

        self.discovery._discovered_servers["tools-server"] = server1
        self.discovery._discovered_servers["resources-server"] = server2

        tools_servers = await self.discovery.discover_servers(capability="tools")

        assert len(tools_servers) == 1
        assert tools_servers[0].name == "tools-server"


class TestHealthChecker:
    """Test server health checking."""

    def setup_method(self):
        """Set up test environment."""
        self.health_checker = HealthChecker(check_interval=1.0)

    def test_health_checker_initialization(self):
        """Test health checker initialization."""
        assert self.health_checker.check_interval == 1.0
        assert self.health_checker._running is False

    @pytest.mark.asyncio
    async def test_check_server_health_stdio(self):
        """Test checking health of stdio server."""
        server = ServerInfo(
            name="stdio-server",
            transport="stdio",
            command="python",
            args=["-c", "print('healthy')"],
        )

        # Mock subprocess execution
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.wait.return_value = 0  # Success
            mock_subprocess.return_value = mock_process

            health = await self.health_checker.check_server_health(server)

            assert health["status"] == "healthy"
            assert health["response_time"] >= 0

    @pytest.mark.asyncio
    async def test_check_server_health_stdio_failed(self):
        """Test checking health of failed stdio server."""
        server = ServerInfo(
            name="failed-server", transport="stdio", command="nonexistent_command"
        )

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.side_effect = OSError("Command not found")

            health = await self.health_checker.check_server_health(server)

            assert health["status"] == "unhealthy"
            assert "error" in health

    @pytest.mark.asyncio
    async def test_check_server_health_http(self):
        """Test checking health of HTTP server."""
        server = ServerInfo(
            name="http-server", transport="http", url="http://localhost:8080"
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response

            health = await self.health_checker.check_server_health(server)

            assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_server_health_http_failed(self):
        """Test checking health of failed HTTP server."""
        server = ServerInfo(
            name="http-server", transport="http", url="http://localhost:8080"
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            health = await self.health_checker.check_server_health(server)

            assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_start_stop_health_checking(self):
        """Test starting and stopping health checking."""
        servers = [
            ServerInfo(name="server1", transport="stdio", command="echo"),
            ServerInfo(name="server2", transport="stdio", command="echo"),
        ]

        discovery = FileBasedDiscovery()
        for server in servers:
            await discovery.register_server(server)

        # Mock health checks
        with patch.object(self.health_checker, "check_server_health") as mock_check:
            mock_check.return_value = {"status": "healthy", "last_check": time.time()}

            await self.health_checker.start(discovery)
            assert self.health_checker._running is True

            # Give it a moment to run
            await asyncio.sleep(0.1)

            await self.health_checker.stop()
            assert self.health_checker._running is False


class TestLoadBalancer:
    """Test load balancing for server selection."""

    def setup_method(self):
        """Set up test environment."""
        self.load_balancer = LoadBalancer()

    def test_calculate_priority_score(self):
        """Test calculating priority score for server."""
        server = ServerInfo(
            name="test-server",
            transport="stdio",
            health={
                "status": "healthy",
                "response_time": 0.1,
                "last_check": time.time(),
            },
            metadata={"priority": 10},
        )

        score = self.load_balancer._calculate_priority_score(server)

        # Score should be positive for healthy server
        assert score > 0

    def test_calculate_priority_score_unhealthy(self):
        """Test priority score for unhealthy server."""
        server = ServerInfo(
            name="unhealthy-server", transport="stdio", health={"status": "unhealthy"}
        )

        score = self.load_balancer._calculate_priority_score(server)

        # Score should be 0 for unhealthy server
        assert score == 0

    def test_select_best_server(self):
        """Test selecting best server from candidates."""
        servers = [
            ServerInfo(
                name="fast-server",
                transport="stdio",
                health={"status": "healthy", "response_time": 0.05},
            ),
            ServerInfo(
                name="slow-server",
                transport="stdio",
                health={"status": "healthy", "response_time": 0.5},
            ),
            ServerInfo(
                name="unhealthy-server",
                transport="stdio",
                health={"status": "unhealthy"},
            ),
        ]

        best = self.load_balancer.select_best_server(servers)

        # Should select the fastest healthy server
        assert best.name == "fast-server"

    def test_select_best_server_no_healthy(self):
        """Test selecting server when none are healthy."""
        servers = [
            ServerInfo(
                name="server1", transport="stdio", health={"status": "unhealthy"}
            ),
            ServerInfo(
                name="server2", transport="stdio", health={"status": "unhealthy"}
            ),
        ]

        best = self.load_balancer.select_best_server(servers)

        # Should still return a server (round-robin fallback)
        assert best is not None

    def test_select_servers_round_robin(self):
        """Test round-robin server selection."""
        servers = [
            ServerInfo(name="server1", transport="stdio"),
            ServerInfo(name="server2", transport="stdio"),
            ServerInfo(name="server3", transport="stdio"),
        ]

        selected = []
        for i in range(6):  # Select twice through the list
            server = self.load_balancer.select_servers_round_robin(servers, 1)[0]
            selected.append(server.name)

        # Should cycle through servers
        expected = ["server1", "server2", "server3", "server1", "server2", "server3"]
        assert selected == expected

    def test_select_multiple_servers(self):
        """Test selecting multiple servers."""
        servers = [
            ServerInfo(
                name="server1",
                transport="stdio",
                health={"status": "healthy", "response_time": 0.1},
            ),
            ServerInfo(
                name="server2",
                transport="stdio",
                health={"status": "healthy", "response_time": 0.2},
            ),
            ServerInfo(
                name="server3",
                transport="stdio",
                health={"status": "healthy", "response_time": 0.3},
            ),
        ]

        selected = self.load_balancer.select_servers(
            servers, count=2, strategy="priority"
        )

        assert len(selected) == 2
        # Should select the two best servers
        assert selected[0].name == "server1"
        assert selected[1].name == "server2"


class TestServiceRegistry:
    """Test service registry coordination."""

    def setup_method(self):
        """Set up test environment."""
        self.registry = ServiceRegistry()

    @pytest.mark.asyncio
    async def test_register_server(self):
        """Test registering server through registry."""
        server = ServerInfo(name="test-server", transport="stdio")

        await self.registry.register_server(server)

        # Should be registered in all backends
        for backend in self.registry.backends:
            registered_server = await backend.get_server("test-server")
            assert registered_server is not None

    @pytest.mark.asyncio
    async def test_discover_servers_aggregated(self):
        """Test discovering servers from all backends."""
        # Register servers in different backends
        server1 = ServerInfo(name="server1", transport="stdio")
        server2 = ServerInfo(name="server2", transport="http")

        await self.registry.backends[0].register_server(server1)

        # Mock network discovery
        if len(self.registry.backends) > 1:
            self.registry.backends[1]._discovered_servers = {"server2": server2}

        servers = await self.registry.discover_servers()

        # Should get servers from all backends (deduplicated)
        server_names = [s.name for s in servers]
        assert "server1" in server_names

    @pytest.mark.asyncio
    async def test_get_best_server_for_capability(self):
        """Test getting best server for specific capability."""
        servers = [
            ServerInfo(
                name="tools-server-1",
                transport="stdio",
                capabilities=["tools"],
                health={"status": "healthy", "response_time": 0.1},
            ),
            ServerInfo(
                name="tools-server-2",
                transport="stdio",
                capabilities=["tools"],
                health={"status": "healthy", "response_time": 0.2},
            ),
            ServerInfo(
                name="resources-server",
                transport="stdio",
                capabilities=["resources"],
                health={"status": "healthy", "response_time": 0.05},
            ),
        ]

        for server in servers:
            await self.registry.register_server(server)

        best = await self.registry.get_best_server_for_capability("tools")

        # Should get the fastest tools server
        assert best.name == "tools-server-1"

    @pytest.mark.asyncio
    async def test_start_stop_health_monitoring(self):
        """Test starting and stopping health monitoring."""
        with patch.object(self.registry.health_checker, "start") as mock_start:
            with patch.object(
                self.registry.health_checker, "stop", new_callable=AsyncMock
            ) as mock_stop:
                await self.registry.start_health_monitoring()
                mock_start.assert_called_once()

                await self.registry.stop_health_monitoring()
                mock_stop.assert_called_once()


class TestServiceMesh:
    """Test service mesh functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.registry = ServiceRegistry()
        self.mesh = ServiceMesh(self.registry)

    @pytest.mark.asyncio
    async def test_call_with_failover(self):
        """Test calling with automatic failover."""
        # Setup servers
        servers = [
            ServerInfo(name="server1", transport="stdio", capabilities=["tools"]),
            ServerInfo(name="server2", transport="stdio", capabilities=["tools"]),
        ]

        for server in servers:
            await self.registry.register_server(server)

        # Mock client calls
        with patch.object(self.mesh, "_create_client") as mock_create_client:
            mock_client = AsyncMock()

            # First call fails, second succeeds
            mock_client.call_tool.side_effect = [
                Exception("Server unavailable"),
                {"result": "success"},
            ]
            mock_create_client.return_value = mock_client

            result = await self.mesh.call_with_failover(
                "tools", "test_tool", {"param": "value"}, max_retries=2
            )

            assert result["result"] == "success"
            assert mock_client.call_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_call_with_failover_all_failed(self):
        """Test call when all servers fail."""
        server = ServerInfo(name="server1", transport="stdio", capabilities=["tools"])
        await self.registry.register_server(server)

        with patch.object(self.mesh, "_create_client") as mock_create_client:
            mock_client = AsyncMock()
            mock_client.call_tool.side_effect = Exception("Always fails")
            mock_create_client.return_value = mock_client

            with pytest.raises(ServiceDiscoveryError):
                await self.mesh.call_with_failover(
                    "tools", "test_tool", {"param": "value"}, max_retries=1
                )

    @pytest.mark.asyncio
    async def test_get_client_for_capability(self):
        """Test getting client for specific capability."""
        server = ServerInfo(
            name="tools-server",
            transport="stdio",
            capabilities=["tools"],
            command="python",
            args=["-m", "server"],
        )
        await self.registry.register_server(server)

        with patch.object(self.mesh, "_create_client") as mock_create_client:
            mock_client = MagicMock()
            mock_create_client.return_value = mock_client

            client = await self.mesh.get_client_for_capability("tools")

            assert client is mock_client
            # Verify that _create_client was called with a server that has the right capabilities
            mock_create_client.assert_called_once()
            called_server = mock_create_client.call_args[0][0]
            assert "tools" in called_server.capabilities
            assert called_server.transport == "stdio"

    @pytest.mark.asyncio
    async def test_create_client_stdio(self):
        """Test creating client for stdio server."""
        server = ServerInfo(
            name="stdio-server",
            transport="stdio",
            command="python",
            args=["-m", "server"],
        )

        with patch("kailash.mcp_server.client.MCPClient") as mock_mcp_client:
            mock_client = MagicMock()
            mock_mcp_client.return_value = mock_client

            client = await self.mesh._create_client(server)

            assert client is mock_client

    @pytest.mark.asyncio
    async def test_create_client_http(self):
        """Test creating client for HTTP server."""
        server = ServerInfo(
            name="http-server", transport="http", url="http://localhost:8080"
        )

        with patch("kailash.mcp_server.client.MCPClient") as mock_mcp_client:
            mock_client = MagicMock()
            mock_mcp_client.return_value = mock_client

            client = await self.mesh._create_client(server)

            assert client is mock_client


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_default_registry(self):
        """Test creating default service registry."""
        registry = create_default_registry()

        assert isinstance(registry, ServiceRegistry)
        assert len(registry.backends) >= 1  # Should have at least file-based discovery

    @pytest.mark.asyncio
    async def test_discover_mcp_servers(self):
        """Test discover_mcp_servers convenience function."""
        with patch(
            "kailash.mcp_server.discovery.create_default_registry"
        ) as mock_create:
            mock_registry = AsyncMock()
            mock_registry.discover_servers.return_value = [
                ServerInfo(name="server1", transport="stdio", capabilities=["tools"])
            ]
            mock_create.return_value = mock_registry

            servers = await discover_mcp_servers(capability="tools")

            assert len(servers) == 1
            assert servers[0].name == "server1"

    @pytest.mark.asyncio
    async def test_get_mcp_client(self):
        """Test get_mcp_client convenience function."""
        with patch(
            "kailash.mcp_server.discovery.create_default_registry"
        ) as mock_create:
            with patch("kailash.mcp_server.discovery.ServiceMesh") as mock_mesh_class:
                mock_registry = AsyncMock()
                mock_mesh = AsyncMock()
                mock_client = MagicMock()

                mock_mesh.get_client_for_capability.return_value = mock_client
                mock_mesh_class.return_value = mock_mesh
                mock_create.return_value = mock_registry

                client = await get_mcp_client("tools")

                assert client is mock_client
                mock_mesh.get_client_for_capability.assert_called_once_with(
                    "tools", None
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
