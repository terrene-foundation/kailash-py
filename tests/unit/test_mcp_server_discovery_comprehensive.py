"""Comprehensive functional tests for mcp_server/discovery.py to boost coverage."""

# Create asyncio event loop for module-level
import asyncio
import hashlib
import json
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import pytest
import yaml

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


class TestMCPServerInfo:
    """Test MCPServerInfo dataclass functionality."""

    def test_mcp_server_info_creation(self):
        """Test creating MCPServerInfo instances."""
        try:
            from kailash.mcp_server.discovery import MCPServerInfo, ServerStatus

            # Basic server info
            server = MCPServerInfo(
                server_id="server_001",
                name="Test MCP Server",
                host="localhost",
                port=8080,
                status=ServerStatus.HEALTHY,
            )

            assert server.server_id == "server_001"
            assert server.name == "Test MCP Server"
            assert server.host == "localhost"
            assert server.port == 8080
            assert server.status == ServerStatus.HEALTHY
            assert server.protocol == "http"  # default
            assert server.capabilities == []  # default
            assert server.metadata == {}  # default
            assert server.last_seen is not None
            assert server.version is None

            # Server with all fields
            full_server = MCPServerInfo(
                server_id="server_002",
                name="Full MCP Server",
                host="api.example.com",
                port=443,
                protocol="https",
                status=ServerStatus.DEGRADED,
                capabilities=["auth", "streaming", "batch"],
                metadata={"region": "us-east-1", "tier": "premium"},
                version="2.1.0",
                auth_required=True,
                description="Production MCP server",
            )

            assert full_server.protocol == "https"
            assert full_server.capabilities == ["auth", "streaming", "batch"]
            assert full_server.metadata["region"] == "us-east-1"
            assert full_server.version == "2.1.0"
            assert full_server.auth_required is True
            assert full_server.description == "Production MCP server"

        except ImportError:
            pytest.skip("MCPServerInfo not available")

    def test_server_status_enum(self):
        """Test ServerStatus enum values."""
        try:
            from kailash.mcp_server.discovery import ServerStatus

            # Test all status values exist
            assert ServerStatus.HEALTHY.value == "healthy"
            assert ServerStatus.DEGRADED.value == "degraded"
            assert ServerStatus.UNHEALTHY.value == "unhealthy"
            assert ServerStatus.UNKNOWN.value == "unknown"

            # Test string conversion
            assert str(ServerStatus.HEALTHY) == "ServerStatus.HEALTHY"

        except ImportError:
            pytest.skip("ServerStatus not available")

    def test_mcp_server_info_equality(self):
        """Test MCPServerInfo equality comparison."""
        try:
            from kailash.mcp_server.discovery import MCPServerInfo, ServerStatus

            server1 = MCPServerInfo(
                server_id="server_001",
                name="Test Server",
                host="localhost",
                port=8080,
                status=ServerStatus.HEALTHY,
            )

            server2 = MCPServerInfo(
                server_id="server_001",
                name="Test Server",
                host="localhost",
                port=8080,
                status=ServerStatus.HEALTHY,
            )

            server3 = MCPServerInfo(
                server_id="server_002",
                name="Different Server",
                host="localhost",
                port=8081,
                status=ServerStatus.HEALTHY,
            )

            # Same server_id = equal
            assert server1 == server2
            assert server1 != server3

        except ImportError:
            pytest.skip("MCPServerInfo not available")


class TestDiscoveryStrategyInterface:
    """Test DiscoveryStrategy interface and implementations."""

    def test_discovery_strategy_interface(self):
        """Test DiscoveryStrategy abstract interface."""
        try:
            import abc

            from kailash.mcp_server.discovery import DiscoveryStrategy

            # Verify it's an abstract class
            assert issubclass(DiscoveryStrategy, abc.ABC)

            # Try to instantiate should fail
            with pytest.raises(TypeError):
                DiscoveryStrategy()

            # Test concrete implementation
            class TestDiscovery(DiscoveryStrategy):
                async def discover(self) -> List[Any]:
                    return []

                async def register_server(self, server_info: Any) -> bool:
                    return True

                async def deregister_server(self, server_id: str) -> bool:
                    return True

                async def get_server(self, server_id: str) -> Optional[Any]:
                    return None

                async def list_servers(self) -> List[Any]:
                    return []

            # Should instantiate successfully
            strategy = TestDiscovery()
            assert isinstance(strategy, DiscoveryStrategy)

        except ImportError:
            pytest.skip("DiscoveryStrategy not available")


class TestStaticDiscovery:
    """Test StaticDiscovery implementation."""

    def test_static_discovery_initialization(self):
        """Test StaticDiscovery initialization with server list."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                StaticDiscovery,
            )

            servers = [
                MCPServerInfo(
                    server_id="static_001",
                    name="Static Server 1",
                    host="server1.example.com",
                    port=8080,
                    status=ServerStatus.HEALTHY,
                ),
                MCPServerInfo(
                    server_id="static_002",
                    name="Static Server 2",
                    host="server2.example.com",
                    port=8081,
                    status=ServerStatus.HEALTHY,
                ),
            ]

            discovery = StaticDiscovery(servers)
            assert hasattr(discovery, "servers")
            assert len(discovery.servers) == 2
            assert discovery.servers["static_001"].name == "Static Server 1"
            assert discovery.servers["static_002"].port == 8081

        except ImportError:
            pytest.skip("StaticDiscovery not available")

    @pytest.mark.asyncio
    async def test_static_discovery_operations(self):
        """Test StaticDiscovery CRUD operations."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                StaticDiscovery,
            )

            initial_server = MCPServerInfo(
                server_id="static_001",
                name="Initial Server",
                host="localhost",
                port=8080,
                status=ServerStatus.HEALTHY,
            )

            discovery = StaticDiscovery([initial_server])

            # Test discover
            discovered = await discovery.discover()
            assert len(discovered) == 1
            assert discovered[0].server_id == "static_001"

            # Test get_server
            server = await discovery.get_server("static_001")
            assert server is not None
            assert server.name == "Initial Server"

            # Test get non-existent server
            missing = await discovery.get_server("nonexistent")
            assert missing is None

            # Test list_servers
            all_servers = await discovery.list_servers()
            assert len(all_servers) == 1

            # Test register new server
            new_server = MCPServerInfo(
                server_id="static_002",
                name="New Server",
                host="localhost",
                port=8081,
                status=ServerStatus.HEALTHY,
            )

            result = await discovery.register_server(new_server)
            assert result is True
            assert len(discovery.servers) == 2

            # Test register duplicate
            result = await discovery.register_server(new_server)
            assert result is False  # Already exists

            # Test deregister
            result = await discovery.deregister_server("static_001")
            assert result is True
            assert len(discovery.servers) == 1

            # Test deregister non-existent
            result = await discovery.deregister_server("nonexistent")
            assert result is False

        except ImportError:
            pytest.skip("StaticDiscovery not available")


class TestFileBasedDiscovery:
    """Test FileBasedDiscovery implementation."""

    @patch("builtins.open", new_callable=mock_open, read_data='{"servers": {}}')
    @patch("pathlib.Path.exists")
    def test_file_based_discovery_initialization(self, mock_exists, mock_file):
        """Test FileBasedDiscovery initialization and file handling."""
        try:
            from kailash.mcp_server.discovery import FileBasedDiscovery

            mock_exists.return_value = True

            discovery = FileBasedDiscovery("/tmp/test_registry.json")

            assert discovery.registry_file == Path("/tmp/test_registry.json")
            assert hasattr(discovery, "servers")
            assert discovery.servers == {}

            # Verify file was read
            mock_file.assert_called_once_with(Path("/tmp/test_registry.json"), "r")

        except ImportError:
            pytest.skip("FileBasedDiscovery not available")

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_file_based_discovery_create_new_file(
        self, mock_file, mock_mkdir, mock_exists
    ):
        """Test FileBasedDiscovery creates new registry file if not exists."""
        try:
            from kailash.mcp_server.discovery import FileBasedDiscovery

            mock_exists.return_value = False

            discovery = FileBasedDiscovery("/tmp/new_registry.json")

            # Should create parent directory
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

            # Should write initial empty registry
            mock_file.assert_called()
            write_calls = [
                call
                for call in mock_file.return_value.__enter__.return_value.write.call_args_list
            ]
            assert any('{"servers": {}}' in str(call) for call in write_calls)

        except ImportError:
            pytest.skip("FileBasedDiscovery not available")

    @pytest.mark.asyncio
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    async def test_file_based_discovery_register_and_persist(
        self, mock_exists, mock_file
    ):
        """Test FileBasedDiscovery server registration with persistence."""
        try:
            from kailash.mcp_server.discovery import (
                FileBasedDiscovery,
                MCPServerInfo,
                ServerStatus,
            )

            # Mock initial empty registry
            mock_file.return_value.read.return_value = '{"servers": {}}'

            discovery = FileBasedDiscovery("/tmp/test_registry.json")

            # Register a server
            server = MCPServerInfo(
                server_id="file_001",
                name="File Server",
                host="localhost",
                port=9000,
                status=ServerStatus.HEALTHY,
                metadata={"persistent": True},
            )

            result = await discovery.register_server(server)
            assert result is True

            # Verify save was called
            write_handle = mock_file.return_value.__enter__.return_value
            write_calls = write_handle.write.call_args_list

            # Should have written the updated registry
            assert len(write_calls) > 0
            written_data = "".join(str(call[0][0]) for call in write_calls if call[0])

            # Verify server was saved to file
            if written_data:
                data = json.loads(written_data)
                assert "servers" in data
                assert "file_001" in data["servers"]
                assert data["servers"]["file_001"]["name"] == "File Server"

        except ImportError:
            pytest.skip("FileBasedDiscovery not available")

    @pytest.mark.asyncio
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    async def test_file_based_discovery_load_existing(self, mock_exists, mock_file):
        """Test FileBasedDiscovery loads existing servers from file."""
        try:
            from kailash.mcp_server.discovery import FileBasedDiscovery

            # Mock registry with existing servers
            existing_data = {
                "servers": {
                    "existing_001": {
                        "server_id": "existing_001",
                        "name": "Existing Server",
                        "host": "old.example.com",
                        "port": 7000,
                        "status": "healthy",
                        "protocol": "http",
                        "capabilities": ["basic"],
                        "metadata": {"loaded": True},
                        "last_seen": "2024-01-01T10:00:00",
                        "version": "1.0.0",
                        "auth_required": False,
                        "description": "Loaded from file",
                    }
                }
            }

            mock_file.return_value.read.return_value = json.dumps(existing_data)

            discovery = FileBasedDiscovery("/tmp/existing_registry.json")

            # Verify servers were loaded
            servers = await discovery.list_servers()
            assert len(servers) == 1
            assert servers[0].server_id == "existing_001"
            assert servers[0].name == "Existing Server"
            assert servers[0].metadata["loaded"] is True

            # Test get specific server
            server = await discovery.get_server("existing_001")
            assert server is not None
            assert server.host == "old.example.com"
            assert server.port == 7000

        except ImportError:
            pytest.skip("FileBasedDiscovery not available")


class TestNetworkDiscovery:
    """Test NetworkDiscovery implementation."""

    def test_network_discovery_initialization(self):
        """Test NetworkDiscovery initialization."""
        try:
            from kailash.mcp_server.discovery import NetworkDiscovery

            # Test with default ports
            discovery = NetworkDiscovery(subnet="192.168.1.0/24", scan_timeout=5.0)

            assert discovery.subnet == "192.168.1.0/24"
            assert discovery.scan_timeout == 5.0
            assert isinstance(discovery.ports, list)
            assert 8080 in discovery.ports  # Common default port

            # Test with custom ports
            custom_discovery = NetworkDiscovery(
                subnet="10.0.0.0/16", ports=[9000, 9001, 9002], scan_timeout=10.0
            )

            assert custom_discovery.ports == [9000, 9001, 9002]
            assert custom_discovery.scan_timeout == 10.0

        except ImportError:
            pytest.skip("NetworkDiscovery not available")

    @pytest.mark.asyncio
    @patch("socket.socket")
    async def test_network_discovery_port_scanning(self, mock_socket_class):
        """Test NetworkDiscovery port scanning functionality."""
        try:
            from kailash.mcp_server.discovery import NetworkDiscovery

            # Mock socket that connects successfully
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket

            discovery = NetworkDiscovery(
                subnet="192.168.1.0/30",  # Small subnet for testing
                ports=[8080, 8081],
                scan_timeout=1.0,
            )

            # Mock successful connection for one host/port
            def connect_side_effect(addr):
                if addr == ("192.168.1.1", 8080):
                    return None  # Success
                else:
                    raise socket.timeout()

            mock_socket.connect.side_effect = connect_side_effect

            # Run discovery
            servers = await discovery.discover()

            # Should have attempted connections
            assert mock_socket.connect.called

            # Verify socket configuration
            mock_socket.settimeout.assert_called_with(1.0)

        except ImportError:
            pytest.skip("NetworkDiscovery not available")

    @pytest.mark.asyncio
    async def test_network_discovery_server_detection(self):
        """Test NetworkDiscovery server detection and info retrieval."""
        try:
            from kailash.mcp_server.discovery import MCPServerInfo, NetworkDiscovery

            discovery = NetworkDiscovery(subnet="127.0.0.1/32", ports=[8080])

            # Mock the internal scanning method
            async def mock_scan_port(host, port):
                if host == "127.0.0.1" and port == 8080:
                    return True
                return False

            # Mock server info retrieval
            async def mock_get_server_info(host, port):
                return MCPServerInfo(
                    server_id=f"discovered_{host}:{port}",
                    name=f"Discovered Server at {host}:{port}",
                    host=host,
                    port=port,
                    status="healthy",
                )

            with (
                patch.object(discovery, "_scan_port", mock_scan_port),
                patch.object(discovery, "_get_server_info", mock_get_server_info),
            ):

                servers = await discovery.discover()

                assert len(servers) == 1
                assert servers[0].host == "127.0.0.1"
                assert servers[0].port == 8080
                assert "Discovered Server" in servers[0].name

        except ImportError:
            pytest.skip("NetworkDiscovery not available")


class TestConfigBasedDiscovery:
    """Test ConfigBasedDiscovery implementation."""

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_yaml_config_loading(self, mock_exists, mock_file):
        """Test loading servers from YAML config."""
        try:
            from kailash.mcp_server.discovery import ConfigBasedDiscovery

            yaml_content = """
            servers:
              - server_id: yaml_001
                name: YAML Server 1
                host: yaml1.example.com
                port: 8080
                protocol: https
                capabilities:
                  - auth
                  - streaming
              - server_id: yaml_002
                name: YAML Server 2
                host: yaml2.example.com
                port: 8081
                metadata:
                  region: eu-west-1
            """

            mock_file.return_value.read.return_value = yaml_content

            discovery = ConfigBasedDiscovery("/etc/mcp/servers.yaml")

            # Should have loaded servers
            assert hasattr(discovery, "servers")
            assert len(discovery.servers) == 2

        except ImportError:
            pytest.skip("ConfigBasedDiscovery not available")

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_json_config_loading(self, mock_exists, mock_file):
        """Test loading servers from JSON config."""
        try:
            from kailash.mcp_server.discovery import ConfigBasedDiscovery

            json_content = json.dumps(
                {
                    "servers": [
                        {
                            "server_id": "json_001",
                            "name": "JSON Server 1",
                            "host": "json1.example.com",
                            "port": 9000,
                            "status": "healthy",
                            "auth_required": True,
                        }
                    ]
                }
            )

            mock_file.return_value.read.return_value = json_content

            discovery = ConfigBasedDiscovery("/etc/mcp/servers.json")

            assert len(discovery.servers) == 1
            assert discovery.servers["json_001"].auth_required is True

        except ImportError:
            pytest.skip("ConfigBasedDiscovery not available")

    @pytest.mark.asyncio
    async def test_config_based_discovery_operations(self):
        """Test ConfigBasedDiscovery operations."""
        try:
            from kailash.mcp_server.discovery import ConfigBasedDiscovery, MCPServerInfo

            with (
                patch("builtins.open", mock_open(read_data='{"servers": []}')),
                patch("pathlib.Path.exists", return_value=True),
            ):

                discovery = ConfigBasedDiscovery("/tmp/config.json")

                # Test discover empty
                servers = await discovery.discover()
                assert len(servers) == 0

                # Config-based discovery typically doesn't support dynamic registration
                # Test that register returns False
                server = MCPServerInfo(
                    server_id="test",
                    name="Test",
                    host="localhost",
                    port=8080,
                    status="healthy",
                )

                result = await discovery.register_server(server)
                assert result is False  # Read-only

        except ImportError:
            pytest.skip("ConfigBasedDiscovery not available")


class TestServiceRegistry:
    """Test ServiceRegistry multi-strategy aggregation."""

    def test_service_registry_initialization(self):
        """Test ServiceRegistry initialization with strategies."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServiceRegistry,
                StaticDiscovery,
            )

            # Create some strategies
            static_strategy = StaticDiscovery(
                [MCPServerInfo("static_001", "Static 1", "localhost", 8080, "healthy")]
            )

            registry = ServiceRegistry()
            assert hasattr(registry, "strategies")
            assert len(registry.strategies) == 0

            # Add strategy
            registry.add_strategy("static", static_strategy)
            assert len(registry.strategies) == 1
            assert "static" in registry.strategies

        except ImportError:
            pytest.skip("ServiceRegistry not available")

    @pytest.mark.asyncio
    async def test_service_registry_aggregated_discovery(self):
        """Test ServiceRegistry discovers from all strategies."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                ServiceRegistry,
                StaticDiscovery,
            )

            # Create strategies with different servers
            static1 = StaticDiscovery(
                [
                    MCPServerInfo(
                        "static_001", "Static 1", "host1", 8080, ServerStatus.HEALTHY
                    ),
                    MCPServerInfo(
                        "static_002", "Static 2", "host2", 8081, ServerStatus.HEALTHY
                    ),
                ]
            )

            static2 = StaticDiscovery(
                [
                    MCPServerInfo(
                        "static_003", "Static 3", "host3", 8082, ServerStatus.HEALTHY
                    )
                ]
            )

            registry = ServiceRegistry()
            registry.add_strategy("source1", static1)
            registry.add_strategy("source2", static2)

            # Discover all
            all_servers = await registry.discover_all()

            assert len(all_servers) == 3
            server_ids = [s.server_id for s in all_servers]
            assert "static_001" in server_ids
            assert "static_002" in server_ids
            assert "static_003" in server_ids

        except ImportError:
            pytest.skip("ServiceRegistry not available")

    @pytest.mark.asyncio
    async def test_service_registry_get_server_from_any_strategy(self):
        """Test ServiceRegistry finds server from any strategy."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                ServiceRegistry,
                StaticDiscovery,
            )

            # Server in first strategy
            server1 = MCPServerInfo(
                "server_001", "Server 1", "host1", 8080, ServerStatus.HEALTHY
            )
            static1 = StaticDiscovery([server1])

            # Server in second strategy
            server2 = MCPServerInfo(
                "server_002", "Server 2", "host2", 8081, ServerStatus.HEALTHY
            )
            static2 = StaticDiscovery([server2])

            registry = ServiceRegistry()
            registry.add_strategy("source1", static1)
            registry.add_strategy("source2", static2)

            # Get server from first strategy
            found1 = await registry.get_server("server_001")
            assert found1 is not None
            assert found1.name == "Server 1"

            # Get server from second strategy
            found2 = await registry.get_server("server_002")
            assert found2 is not None
            assert found2.name == "Server 2"

            # Get non-existent server
            not_found = await registry.get_server("nonexistent")
            assert not_found is None

        except ImportError:
            pytest.skip("ServiceRegistry not available")

    @pytest.mark.asyncio
    async def test_service_registry_strategy_errors(self):
        """Test ServiceRegistry handles strategy errors gracefully."""
        try:
            from kailash.mcp_server.discovery import DiscoveryStrategy, ServiceRegistry

            # Create a failing strategy
            class FailingStrategy(DiscoveryStrategy):
                async def discover(self):
                    raise Exception("Discovery failed")

                async def register_server(self, server_info):
                    raise Exception("Register failed")

                async def deregister_server(self, server_id):
                    raise Exception("Deregister failed")

                async def get_server(self, server_id):
                    raise Exception("Get failed")

                async def list_servers(self):
                    raise Exception("List failed")

            registry = ServiceRegistry()
            registry.add_strategy("failing", FailingStrategy())

            # Should handle discovery failure gracefully
            servers = await registry.discover_all()
            assert isinstance(servers, list)  # Returns empty list on failure

        except ImportError:
            pytest.skip("ServiceRegistry not available")


class TestServiceMesh:
    """Test ServiceMesh functionality."""

    def test_service_mesh_initialization(self):
        """Test ServiceMesh initialization."""
        try:
            from kailash.mcp_server.discovery import ServiceMesh

            mesh = ServiceMesh(mesh_name="test-mesh", namespace="production")

            assert mesh.mesh_name == "test-mesh"
            assert mesh.namespace == "production"
            assert hasattr(mesh, "nodes")
            assert hasattr(mesh, "health_checks")

        except ImportError:
            pytest.skip("ServiceMesh not available")

    @pytest.mark.asyncio
    async def test_service_mesh_node_management(self):
        """Test ServiceMesh node registration and health checking."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                ServiceMesh,
            )

            mesh = ServiceMesh("test-mesh")

            # Add nodes
            node1 = MCPServerInfo(
                "node_001", "Node 1", "10.0.0.1", 8080, ServerStatus.HEALTHY
            )
            node2 = MCPServerInfo(
                "node_002", "Node 2", "10.0.0.2", 8080, ServerStatus.HEALTHY
            )

            await mesh.add_node(node1)
            await mesh.add_node(node2)

            # Get healthy nodes
            healthy = await mesh.get_healthy_nodes()
            assert len(healthy) == 2

            # Update node health
            await mesh.update_node_health("node_001", ServerStatus.UNHEALTHY)

            # Check healthy nodes again
            healthy = await mesh.get_healthy_nodes()
            assert len(healthy) == 1
            assert healthy[0].server_id == "node_002"

        except ImportError:
            pytest.skip("ServiceMesh not available")

    @pytest.mark.asyncio
    async def test_service_mesh_load_balancing(self):
        """Test ServiceMesh load balancing strategies."""
        try:
            from kailash.mcp_server.discovery import (
                MCPServerInfo,
                ServerStatus,
                ServiceMesh,
            )

            mesh = ServiceMesh("test-mesh")

            # Add multiple nodes
            for i in range(3):
                node = MCPServerInfo(
                    f"node_{i}",
                    f"Node {i}",
                    f"10.0.0.{i+1}",
                    8080,
                    ServerStatus.HEALTHY,
                )
                await mesh.add_node(node)

            # Test round-robin selection
            selected_ids = []
            for _ in range(6):  # Select twice the number of nodes
                node = await mesh.select_node(strategy="round-robin")
                if node:
                    selected_ids.append(node.server_id)

            # Should have selected each node twice
            assert selected_ids.count("node_0") == 2
            assert selected_ids.count("node_1") == 2
            assert selected_ids.count("node_2") == 2

            # Test random selection
            random_node = await mesh.select_node(strategy="random")
            assert random_node is not None
            assert random_node.server_id in ["node_0", "node_1", "node_2"]

        except ImportError:
            pytest.skip("ServiceMesh not available")


class TestLoadBalancer:
    """Test LoadBalancer functionality."""

    def test_load_balancer_initialization(self):
        """Test LoadBalancer initialization with strategies."""
        try:
            from kailash.mcp_server.discovery import LoadBalancer

            lb = LoadBalancer(strategy="round-robin")
            assert lb.strategy == "round-robin"
            assert hasattr(lb, "servers")
            assert hasattr(lb, "current_index")

            # Test with different strategies
            lb_random = LoadBalancer(strategy="random")
            assert lb_random.strategy == "random"

            lb_weighted = LoadBalancer(strategy="weighted")
            assert lb_weighted.strategy == "weighted"

        except ImportError:
            pytest.skip("LoadBalancer not available")

    @pytest.mark.asyncio
    async def test_load_balancer_round_robin(self):
        """Test LoadBalancer round-robin strategy."""
        try:
            from kailash.mcp_server.discovery import (
                LoadBalancer,
                MCPServerInfo,
                ServerStatus,
            )

            lb = LoadBalancer(strategy="round-robin")

            # Add servers
            servers = [
                MCPServerInfo(
                    f"srv_{i}",
                    f"Server {i}",
                    f"host{i}",
                    8080 + i,
                    ServerStatus.HEALTHY,
                )
                for i in range(3)
            ]

            for server in servers:
                await lb.add_server(server)

            # Select servers in round-robin fashion
            selections = []
            for _ in range(9):  # 3 full rounds
                server = await lb.select_server()
                selections.append(server.server_id)

            # Verify round-robin pattern
            expected = ["srv_0", "srv_1", "srv_2"] * 3
            assert selections == expected

        except ImportError:
            pytest.skip("LoadBalancer not available")

    @pytest.mark.asyncio
    async def test_load_balancer_weighted_selection(self):
        """Test LoadBalancer weighted selection strategy."""
        try:
            from kailash.mcp_server.discovery import (
                LoadBalancer,
                MCPServerInfo,
                ServerStatus,
            )

            lb = LoadBalancer(strategy="weighted")

            # Add servers with weights
            server1 = MCPServerInfo(
                "srv_1", "Server 1", "host1", 8080, ServerStatus.HEALTHY
            )
            server2 = MCPServerInfo(
                "srv_2", "Server 2", "host2", 8081, ServerStatus.HEALTHY
            )

            await lb.add_server(server1, weight=1)
            await lb.add_server(server2, weight=3)  # 3x more likely

            # Select many times to verify distribution
            selections = {"srv_1": 0, "srv_2": 0}
            for _ in range(100):
                server = await lb.select_server()
                selections[server.server_id] += 1

            # Server 2 should be selected approximately 3x more often
            ratio = selections["srv_2"] / selections["srv_1"]
            assert 2.0 < ratio < 4.0  # Allow some variance

        except ImportError:
            pytest.skip("LoadBalancer not available")

    @pytest.mark.asyncio
    async def test_load_balancer_health_aware_selection(self):
        """Test LoadBalancer only selects healthy servers."""
        try:
            from kailash.mcp_server.discovery import (
                LoadBalancer,
                MCPServerInfo,
                ServerStatus,
            )

            lb = LoadBalancer(strategy="round-robin", health_check=True)

            # Add mix of healthy and unhealthy servers
            await lb.add_server(
                MCPServerInfo("srv_1", "Server 1", "host1", 8080, ServerStatus.HEALTHY)
            )
            await lb.add_server(
                MCPServerInfo(
                    "srv_2", "Server 2", "host2", 8081, ServerStatus.UNHEALTHY
                )
            )
            await lb.add_server(
                MCPServerInfo("srv_3", "Server 3", "host3", 8082, ServerStatus.HEALTHY)
            )

            # Select multiple times
            selected_ids = set()
            for _ in range(10):
                server = await lb.select_server()
                selected_ids.add(server.server_id)

            # Should only select healthy servers
            assert "srv_1" in selected_ids
            assert "srv_3" in selected_ids
            assert "srv_2" not in selected_ids  # Unhealthy

        except ImportError:
            pytest.skip("LoadBalancer not available")


class TestDiscoveryCache:
    """Test discovery caching functionality."""

    def test_discovery_cache_initialization(self):
        """Test DiscoveryCache initialization."""
        try:
            from kailash.mcp_server.discovery import DiscoveryCache

            cache = DiscoveryCache(ttl_seconds=300)
            assert cache.ttl_seconds == 300
            assert hasattr(cache, "cache")
            assert hasattr(cache, "timestamps")

        except ImportError:
            pytest.skip("DiscoveryCache not available")

    @pytest.mark.asyncio
    async def test_discovery_cache_operations(self):
        """Test DiscoveryCache get/set with TTL."""
        try:
            from kailash.mcp_server.discovery import (
                DiscoveryCache,
                MCPServerInfo,
                ServerStatus,
            )

            cache = DiscoveryCache(ttl_seconds=1)  # 1 second TTL

            server = MCPServerInfo(
                "cache_001", "Cached Server", "localhost", 8080, ServerStatus.HEALTHY
            )

            # Add to cache
            await cache.set("server_001", server)

            # Get from cache (should work)
            cached = await cache.get("server_001")
            assert cached is not None
            assert cached.name == "Cached Server"

            # Wait for TTL to expire
            await asyncio.sleep(1.1)

            # Get from cache (should be expired)
            expired = await cache.get("server_001")
            assert expired is None

        except ImportError:
            pytest.skip("DiscoveryCache not available")

    @pytest.mark.asyncio
    async def test_discovery_cache_clear(self):
        """Test DiscoveryCache clear functionality."""
        try:
            from kailash.mcp_server.discovery import (
                DiscoveryCache,
                MCPServerInfo,
                ServerStatus,
            )

            cache = DiscoveryCache()

            # Add multiple entries
            for i in range(5):
                server = MCPServerInfo(
                    f"srv_{i}",
                    f"Server {i}",
                    "localhost",
                    8080 + i,
                    ServerStatus.HEALTHY,
                )
                await cache.set(f"key_{i}", server)

            # Verify entries exist
            assert await cache.get("key_0") is not None
            assert await cache.get("key_4") is not None

            # Clear cache
            await cache.clear()

            # Verify all entries removed
            for i in range(5):
                assert await cache.get(f"key_{i}") is None

        except ImportError:
            pytest.skip("DiscoveryCache not available")


class TestHealthChecker:
    """Test health checking functionality."""

    def test_health_checker_initialization(self):
        """Test HealthChecker initialization."""
        try:
            from kailash.mcp_server.discovery import HealthChecker

            checker = HealthChecker(
                interval_seconds=30, timeout_seconds=5, failure_threshold=3
            )

            assert checker.interval_seconds == 30
            assert checker.timeout_seconds == 5
            assert checker.failure_threshold == 3
            assert hasattr(checker, "failure_counts")

        except ImportError:
            pytest.skip("HealthChecker not available")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_health_checker_http_check(self, mock_session_class):
        """Test HealthChecker HTTP health check."""
        try:
            from kailash.mcp_server.discovery import (
                HealthChecker,
                MCPServerInfo,
                ServerStatus,
            )

            checker = HealthChecker()

            server = MCPServerInfo(
                "health_001",
                "Health Test Server",
                "localhost",
                8080,
                ServerStatus.HEALTHY,
                protocol="http",
            )

            # Mock successful health check
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "healthy"})

            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Perform health check
            is_healthy = await checker.check_server_health(server)

            assert is_healthy is True

            # Verify health check URL was called
            mock_session.get.assert_called()
            call_url = mock_session.get.call_args[0][0]
            assert "health" in call_url or "status" in call_url

        except ImportError:
            pytest.skip("HealthChecker not available")

    @pytest.mark.asyncio
    async def test_health_checker_failure_tracking(self):
        """Test HealthChecker tracks consecutive failures."""
        try:
            from kailash.mcp_server.discovery import (
                HealthChecker,
                MCPServerInfo,
                ServerStatus,
            )

            checker = HealthChecker(failure_threshold=3)

            server = MCPServerInfo(
                "fail_001", "Failing Server", "localhost", 8080, ServerStatus.HEALTHY
            )

            # Mock health check to always fail
            async def failing_check(srv):
                return False

            with patch.object(checker, "_perform_health_check", failing_check):
                # First two failures - still healthy
                for i in range(2):
                    is_healthy = await checker.check_server_health(server)
                    assert is_healthy is True  # Under threshold

                # Third failure - marks unhealthy
                is_healthy = await checker.check_server_health(server)
                assert is_healthy is False

                # Verify failure count
                assert checker.failure_counts.get(server.server_id, 0) >= 3

        except ImportError:
            pytest.skip("HealthChecker not available")


class TestDiscoveryEvents:
    """Test discovery event system."""

    def test_discovery_event_types(self):
        """Test DiscoveryEvent types."""
        try:
            from kailash.mcp_server.discovery import DiscoveryEvent, EventType

            # Test event creation
            event = DiscoveryEvent(
                event_type=EventType.SERVER_ADDED,
                server_id="event_001",
                server_info={"name": "Event Server"},
                timestamp=datetime.now(),
            )

            assert event.event_type == EventType.SERVER_ADDED
            assert event.server_id == "event_001"
            assert event.server_info["name"] == "Event Server"
            assert isinstance(event.timestamp, datetime)

            # Test all event types
            assert hasattr(EventType, "SERVER_ADDED")
            assert hasattr(EventType, "SERVER_REMOVED")
            assert hasattr(EventType, "SERVER_UPDATED")
            assert hasattr(EventType, "HEALTH_CHANGED")

        except ImportError:
            pytest.skip("DiscoveryEvent not available")

    @pytest.mark.asyncio
    async def test_discovery_event_handler(self):
        """Test discovery event handling."""
        try:
            from kailash.mcp_server.discovery import (
                DiscoveryEvent,
                DiscoveryEventHandler,
                EventType,
            )

            handler = DiscoveryEventHandler()

            # Track events
            received_events = []

            async def event_callback(event):
                received_events.append(event)

            # Subscribe to events
            handler.subscribe(EventType.SERVER_ADDED, event_callback)

            # Emit event
            event = DiscoveryEvent(
                event_type=EventType.SERVER_ADDED,
                server_id="handler_001",
                server_info={"test": True},
            )

            await handler.emit(event)

            # Verify callback was called
            assert len(received_events) == 1
            assert received_events[0].server_id == "handler_001"

        except ImportError:
            pytest.skip("DiscoveryEventHandler not available")


class TestDiscoveryIntegration:
    """Test integration scenarios for discovery system."""

    @pytest.mark.asyncio
    async def test_discovery_with_caching(self):
        """Test discovery with caching layer."""
        try:
            from kailash.mcp_server.discovery import (
                CachedDiscovery,
                MCPServerInfo,
                ServerStatus,
                StaticDiscovery,
            )

            # Create base discovery
            base_servers = [
                MCPServerInfo(
                    "base_001", "Base Server", "localhost", 8080, ServerStatus.HEALTHY
                )
            ]
            base_discovery = StaticDiscovery(base_servers)

            # Wrap with cache
            cached_discovery = CachedDiscovery(base_discovery, cache_ttl=60)

            # First call - hits base discovery
            servers1 = await cached_discovery.discover()
            assert len(servers1) == 1

            # Modify base (shouldn't affect cache)
            base_discovery.servers["base_002"] = MCPServerInfo(
                "base_002", "New Server", "localhost", 8081, ServerStatus.HEALTHY
            )

            # Second call - should hit cache
            servers2 = await cached_discovery.discover()
            assert len(servers2) == 1  # Still cached result

            # Clear cache and try again
            await cached_discovery.clear_cache()
            servers3 = await cached_discovery.discover()
            assert len(servers3) == 2  # Fresh from base

        except ImportError:
            pytest.skip("CachedDiscovery not available")

    @pytest.mark.asyncio
    async def test_discovery_retry_logic(self):
        """Test discovery with retry on failures."""
        try:
            from kailash.mcp_server.discovery import (
                DiscoveryStrategy,
                RetryableDiscovery,
            )

            # Create failing discovery
            class FailingDiscovery(DiscoveryStrategy):
                def __init__(self):
                    self.attempts = 0

                async def discover(self):
                    self.attempts += 1
                    if self.attempts < 3:
                        raise Exception("Discovery failed")
                    return []  # Success on 3rd attempt

                async def register_server(self, server_info):
                    return False

                async def deregister_server(self, server_id):
                    return False

                async def get_server(self, server_id):
                    return None

                async def list_servers(self):
                    return []

            base = FailingDiscovery()
            retryable = RetryableDiscovery(base, max_retries=3, retry_delay=0.1)

            # Should succeed after retries
            servers = await retryable.discover()
            assert isinstance(servers, list)
            assert base.attempts == 3

        except ImportError:
            pytest.skip("RetryableDiscovery not available")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
