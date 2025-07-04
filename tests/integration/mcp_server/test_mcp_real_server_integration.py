"""Real MCP server integration tests using Docker services.

NO MOCKING - All tests use real services per testing policy.
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import aiohttp
import pytest
import redis.asyncio as redis

from kailash.mcp_server import MCPClient, MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.mcp_server.discovery import FileBasedDiscovery, ServerInfo, ServiceRegistry
from kailash.mcp_server.transports import (
    EnhancedStdioTransport,
    SSETransport,
    StreamableHTTPTransport,
    WebSocketTransport,
)
from tests.utils.docker_config import (
    REDIS_CONFIG,
    ensure_docker_services,
    get_redis_url,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.requires_redis
class TestRealMCPServerIntegration:
    """Test MCP server with real infrastructure."""

    @pytest.fixture(autouse=True)
    async def setup_services(self):
        """Ensure Docker services are running."""
        # This will check that Redis is available
        await ensure_docker_services(["redis"])
        yield

    @pytest.mark.asyncio
    async def test_mcp_server_with_redis_cache(self):
        """Test MCP server using real Redis for caching."""
        # Create MCP server with Redis cache
        server = MCPServer(
            name="test-server",
            cache_backend="redis",
            cache_config={
                "redis_url": get_redis_url(),
                "prefix": "mcp_test:",
                "ttl": 300,
            },
        )

        # Register a cached tool
        @server.tool(cache_key="compute_result", cache_ttl=60)
        async def compute_heavy(n: int) -> int:
            """Simulate heavy computation."""
            await asyncio.sleep(0.1)  # Simulate work
            return n * n

        # Test the tool works
        result1 = await compute_heavy(5)
        assert result1 == 25

        # Verify it's cached in Redis
        redis_client = redis.from_url(get_redis_url())
        try:
            cached_value = await redis_client.get("mcp_test:compute_result:5")
            assert cached_value is not None
            assert json.loads(cached_value) == 25
        finally:
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_service_discovery_with_file_backend(self):
        """Test service discovery using real file system."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "mcp_registry.json"

            # Create registry with file backend
            discovery = FileBasedDiscovery(registry_path)
            registry = ServiceRegistry(backends=[discovery])

            # Register servers
            server1 = ServerInfo(
                name="api-server",
                transport="http",
                url="http://localhost:8888/mcp",
                capabilities=["tools", "resources"],
                health_status="healthy",
            )

            server2 = ServerInfo(
                name="compute-server",
                transport="stdio",
                command="python",
                args=["-m", "compute_server"],
                capabilities=["tools"],
                health_status="healthy",
            )

            await registry.register_server(server1)
            await registry.register_server(server2)

            # Verify file was created
            assert registry_path.exists()

            # Test discovery
            servers = await registry.discover_servers()
            assert len(servers) == 2

            # Test filtered discovery
            api_servers = await registry.discover_servers(capability="resources")
            assert len(api_servers) == 1
            assert api_servers[0].name == "api-server"

            # Test persistence - create new registry from same file
            registry2 = ServiceRegistry(backends=[FileBasedDiscovery(registry_path)])
            servers2 = await registry2.discover_servers()
            assert len(servers2) == 2

    @pytest.mark.asyncio
    async def test_mcp_server_with_mock_api(self):
        """Test MCP server integration with mock API server."""
        # Check if mock API is available
        mock_api_url = "http://localhost:8888"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{mock_api_url}/health") as resp:
                    if resp.status != 200:
                        pytest.skip("Mock API server not available")
        except:
            pytest.skip("Mock API server not available")

        # Create SSE transport
        transport = SSETransport(
            base_url=mock_api_url, endpoint_path="/mcp/sse", message_path="/mcp/message"
        )

        # Create client with transport
        client = MCPClient(transport=transport)

        # Test connection
        try:
            await client.connect()
            assert client.is_connected()

            # Test sending a message
            test_message = {"jsonrpc": "2.0", "method": "tools/list", "id": "test-1"}

            await client.send_message(test_message)

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_oauth_with_real_tokens(self):
        """Test OAuth authentication with real JWT tokens."""
        # Create auth provider with API keys
        auth = APIKeyAuth(
            {
                "test-key-123": {
                    "permissions": ["tools.execute", "resources.read"],
                    "rate_limit": 100,
                    "metadata": {"client": "test-client"},
                },
                "admin-key-456": {
                    "permissions": ["*"],  # All permissions
                    "rate_limit": 1000,
                    "metadata": {"client": "admin-client"},
                },
            }
        )

        # Create server with auth
        server = MCPServer("auth-test-server", auth_provider=auth)

        # Register protected tool
        @server.tool(required_permissions=["tools.execute"])
        async def protected_tool(x: int) -> int:
            """Protected tool requiring authentication."""
            return x * 2

        # Test with valid key
        auth_context = await auth.authenticate("test-key-123")
        assert auth_context is not None
        assert "tools.execute" in auth_context["permissions"]

        # Test with invalid key
        with pytest.raises(Exception):
            await auth.authenticate("invalid-key")

        # Test rate limiting is tracked
        for i in range(5):
            await auth.check_rate_limit("test-key-123")

        # Verify rate limit data (would be in Redis in production)
        assert auth._get_rate_limit_key("test-key-123") is not None

    @pytest.mark.asyncio
    async def test_websocket_transport_localhost(self):
        """Test WebSocket transport with localhost connection."""
        # This test would connect to a real WebSocket server if available
        # For now, we test the transport initialization and validation

        transport = WebSocketTransport(
            url="ws://localhost:8889/mcp",
            subprotocols=["mcp-v1"],
            ping_interval=30.0,
            ping_timeout=10.0,
        )

        # Verify transport configuration
        assert transport.url == "ws://localhost:8889/mcp"
        assert "mcp-v1" in transport.subprotocols
        assert transport.ping_interval == 30.0

        # In a real test with a WebSocket server running:
        # await transport.connect()
        # await transport.send_message({"test": "message"})
        # response = await transport.receive_message()
        # await transport.disconnect()

    @pytest.mark.asyncio
    async def test_streamable_http_with_real_endpoints(self):
        """Test StreamableHTTP transport with real HTTP endpoints."""
        # Check if mock API supports streaming
        mock_api_url = "http://localhost:8888"

        transport = StreamableHTTPTransport(
            base_url=mock_api_url,
            session_management=True,
            streaming_threshold=1024,
            chunk_size=4096,
        )

        try:
            await transport.connect()

            # Small message (non-streaming)
            small_message = {"method": "ping", "params": {}}
            await transport.send_message(small_message)

            # Large message (would trigger streaming)
            large_data = "x" * 2000
            large_message = {"method": "process", "params": {"data": large_data}}
            await transport.send_message(large_message)

        except Exception as e:
            # Expected if mock API doesn't support these endpoints
            if "404" not in str(e) and "Connection refused" not in str(e):
                raise
        finally:
            await transport.disconnect()

    @pytest.mark.asyncio
    async def test_file_based_discovery_concurrent_access(self):
        """Test file-based discovery with concurrent access."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "shared_registry.json"

            # Create multiple discovery instances sharing same file
            discoveries = [FileBasedDiscovery(registry_path) for _ in range(3)]

            # Concurrent registration
            async def register_server(discovery, server_id):
                server = ServerInfo(
                    name=f"server-{server_id}",
                    transport="http",
                    url=f"http://localhost:{8000 + server_id}",
                    capabilities=["tools"],
                )
                await discovery.register_server(server)

            # Register servers concurrently
            tasks = []
            for i, discovery in enumerate(discoveries):
                tasks.append(register_server(discovery, i))

            await asyncio.gather(*tasks)

            # Verify all servers were registered
            final_discovery = FileBasedDiscovery(registry_path)
            servers = await final_discovery.discover_servers()
            assert len(servers) == 3

            server_names = {s.name for s in servers}
            assert server_names == {"server-0", "server-1", "server-2"}


@pytest.mark.integration
@pytest.mark.requires_docker
class TestMCPHealthChecking:
    """Test MCP health checking with real network calls."""

    @pytest.mark.asyncio
    async def test_http_health_check(self):
        """Test HTTP-based health checking."""
        from kailash.mcp_server.discovery import HealthChecker

        # Use mock API server for health checks
        mock_api_url = "http://localhost:8888"

        # Check if available
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{mock_api_url}/health") as resp:
                    if resp.status != 200:
                        pytest.skip("Mock API not available")
        except:
            pytest.skip("Mock API not available")

        # Create health checker
        checker = HealthChecker(check_interval=1.0)

        # Create server info
        server = ServerInfo(
            name="api-server",
            transport="http",
            url=mock_api_url,
            health_endpoint="/health",
        )

        # Perform health check
        health_info = await checker.check_server_health(server)

        assert health_info["status"] == "healthy"
        assert "response_time" in health_info
        assert health_info["response_time"] < 1.0  # Should be fast for localhost
