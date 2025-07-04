"""End-to-end tests for complete MCP workflows.

NO MOCKING - Uses real Docker services for complete scenarios.
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
import redis.asyncio as redis

from kailash.mcp_server import MCPClient, MCPServer
from kailash.mcp_server.discovery import (
    FileBasedDiscovery,
    ServiceMesh,
    ServiceRegistry,
    create_default_registry,
)
from kailash.mcp_server.oauth import AuthorizationServer, OAuth2Client
from kailash.mcp_server.transports import get_transport_manager
from tests.utils.docker_config import (
    OLLAMA_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.slow
class TestMCPCompleteWorkflows:
    """Test complete MCP workflows end-to-end."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure all required Docker services are running."""
        await ensure_docker_services()
        yield

    @pytest.mark.asyncio
    async def test_full_mcp_server_lifecycle(self):
        """Test complete MCP server lifecycle with all features."""
        # 1. Create MCP server with all features enabled
        server = MCPServer(
            name="production-server",
            cache_backend="redis",
            cache_config={
                "redis_url": get_redis_url(),
                "prefix": "mcp_prod:",
                "ttl": 3600,
            },
            enable_metrics=True,
            enable_monitoring=True,
        )

        # 2. Register various tools
        @server.tool(cache_key="math_add", cache_ttl=300)
        async def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        @server.tool()
        async def multiply(x: float, y: float) -> float:
            """Multiply two numbers."""
            await asyncio.sleep(0.05)  # Simulate work
            return x * y

        @server.tool(required_permissions=["compute.heavy"])
        async def heavy_compute(n: int) -> int:
            """Perform heavy computation."""
            await asyncio.sleep(0.1)
            return sum(i * i for i in range(n))

        # 3. Register resources
        @server.resource("config://app/settings")
        async def get_settings():
            """Get application settings."""
            return {
                "debug": False,
                "version": "1.0.0",
                "features": ["caching", "monitoring", "auth"],
            }

        @server.resource("data://users/{user_id}")
        async def get_user_data(user_id: str):
            """Get user data by ID."""
            # In real app, would query database
            return {"id": user_id, "name": f"User {user_id}", "created_at": time.time()}

        # 4. Test tool execution
        result = await add(10, 20)
        assert result == 30

        # 5. Verify caching
        redis_client = redis.from_url(get_redis_url())
        try:
            # Check cache was populated
            cache_key = "mcp_prod:math_add:10:20"
            cached = await redis_client.get(cache_key)
            assert cached is not None

            # Second call should be from cache
            start_time = time.time()
            result2 = await add(10, 20)
            elapsed = time.time() - start_time
            assert result2 == 30
            assert elapsed < 0.01  # Should be instant from cache

        finally:
            await redis_client.aclose()

        # 6. Test metrics collection
        metrics = server.get_metrics()
        assert "tools_executed" in metrics
        assert metrics["tools_executed"] >= 1

    @pytest.mark.asyncio
    async def test_service_discovery_and_routing(self):
        """Test service discovery and intelligent routing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "services.json"

            # 1. Set up service registry
            discovery = FileBasedDiscovery(registry_path)
            registry = ServiceRegistry(backends=[discovery])

            # 2. Register multiple services
            services = [
                {
                    "name": "llm-server-1",
                    "transport": "http",
                    "url": "http://localhost:8001",
                    "capabilities": ["llm", "embeddings"],
                    "metadata": {"model": "llama2", "gpu": True},
                },
                {
                    "name": "llm-server-2",
                    "transport": "http",
                    "url": "http://localhost:8002",
                    "capabilities": ["llm"],
                    "metadata": {"model": "llama3", "gpu": False},
                },
                {
                    "name": "tool-server",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "tool_server"],
                    "capabilities": ["tools", "code_execution"],
                },
                {
                    "name": "data-server",
                    "transport": "websocket",
                    "url": "ws://localhost:8003",
                    "capabilities": ["resources", "search"],
                },
            ]

            for service_config in services:
                from kailash.mcp_server.discovery import ServerInfo

                server = ServerInfo(**service_config)
                await registry.register_server(server)

            # 3. Test discovery by capability
            llm_servers = await registry.discover_servers(capability="llm")
            assert len(llm_servers) == 2

            tool_servers = await registry.discover_servers(capability="tools")
            assert len(tool_servers) == 1
            assert tool_servers[0].name == "tool-server"

            # 4. Test best server selection
            best_llm = await registry.get_best_server_for_capability("llm")
            assert best_llm is not None
            assert best_llm.name in ["llm-server-1", "llm-server-2"]

            # 5. Create service mesh for failover
            mesh = ServiceMesh(registry)

            # Test real failover with multiple server instances
            # In production, this would handle server failures gracefully

            # Simulate multiple tool calls to test load balancing
            results = []
            for i in range(3):
                try:
                    # Call tool through service mesh
                    result = await mesh.call_with_failover(
                        "tools",  # capability
                        "add",  # tool name
                        {"a": i, "b": 10},  # arguments
                        max_retries=2,
                    )
                    results.append(result)
                except Exception as e:
                    # In real scenario, would log and handle failure
                    print(f"Call {i} failed: {e}")

            # At least some calls should succeed if servers are healthy
            assert len(results) > 0

    @pytest.mark.asyncio
    @pytest.mark.requires_ollama
    async def test_mcp_with_llm_integration(self):
        """Test MCP server integrated with Ollama LLM."""
        # Check if Ollama is available
        ollama_url = f"http://localhost:{OLLAMA_CONFIG['port']}/api/tags"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ollama_url) as resp:
                    if resp.status != 200:
                        pytest.skip("Ollama not available")
                    data = await resp.json()
                    if not any("llama" in m["name"] for m in data.get("models", [])):
                        pytest.skip("No Llama model available in Ollama")
        except:
            pytest.skip("Ollama not available")

        # Create MCP server with LLM tools
        server = MCPServer("llm-server")

        @server.tool()
        async def generate_text(prompt: str, max_tokens: int = 100) -> str:
            """Generate text using Ollama."""
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "llama3.2:1b",  # Use small model for tests
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.7},
                }

                async with session.post(
                    f"http://localhost:{OLLAMA_CONFIG['port']}/api/generate",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("response", "")
                    else:
                        return f"Error: {resp.status}"

        @server.tool()
        async def generate_embeddings(text: str) -> list:
            """Generate embeddings using Ollama."""
            async with aiohttp.ClientSession() as session:
                payload = {"model": "nomic-embed-text", "prompt": text}

                async with session.post(
                    f"http://localhost:{OLLAMA_CONFIG['port']}/api/embeddings",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("embedding", [])
                    else:
                        return []

        # Test text generation
        response = await generate_text("What is Python?", max_tokens=50)
        assert isinstance(response, str)
        assert len(response) > 0

        # Test embedding generation
        embeddings = await generate_embeddings("Hello, world!")
        assert isinstance(embeddings, list)
        assert len(embeddings) > 0  # Should have embedding dimensions

    @pytest.mark.asyncio
    async def test_oauth_flow_complete(self):
        """Test complete OAuth 2.1 authorization flow."""
        # This test simulates a complete OAuth flow
        # In production, would use real OAuth server

        # 1. Create authorization server
        from kailash.mcp_server.oauth import (
            AuthorizationServer,
            InMemoryClientStore,
            InMemoryTokenStore,
            JWTManager,
        )

        # Create JWT manager with test keys
        jwt_manager = JWTManager(
            private_key=None,  # Would use real keys in production
            public_key=None,
            issuer="http://localhost:9000",
        )

        auth_server = AuthorizationServer(
            issuer="http://localhost:9000",
            jwt_manager=jwt_manager,
            client_store=InMemoryClientStore(),
            token_store=InMemoryTokenStore(),
        )

        # 2. Register a client
        client = await auth_server.register_client(
            client_name="MCP Test Client",
            redirect_uris=["http://localhost:3000/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["read", "write", "execute"],
        )

        assert client.client_id is not None
        assert client.client_secret is not None

        # 3. Generate authorization code
        auth_code = await auth_server.generate_authorization_code(
            client_id=client.client_id,
            user_id="test-user-123",
            redirect_uri="http://localhost:3000/callback",
            scopes=["read", "write"],
        )

        assert auth_code is not None

        # 4. Exchange code for tokens
        tokens = await auth_server.exchange_authorization_code(
            client_id=client.client_id,
            client_secret=client.client_secret,
            code=auth_code,
            redirect_uri="http://localhost:3000/callback",
        )

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "Bearer"

        # 5. Introspect token
        introspection = await auth_server.introspect_token(tokens["access_token"])

        assert introspection["active"] is True
        assert introspection["client_id"] == client.client_id

        # 6. Refresh token
        new_tokens = await auth_server.refresh_access_token(
            client_id=client.client_id,
            client_secret=client.client_secret,
            refresh_token=tokens["refresh_token"],
        )

        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != tokens["access_token"]

    @pytest.mark.asyncio
    async def test_transport_manager_lifecycle(self):
        """Test transport manager with multiple transports."""
        manager = get_transport_manager()

        # 1. Create various transports
        transports = {
            "stdio": manager.create_transport("stdio", command="echo", args=["test"]),
            "sse": manager.create_transport("sse", base_url="http://localhost:8888"),
            "websocket": manager.create_transport(
                "websocket", url="ws://localhost:8889/mcp"
            ),
            "http": manager.create_transport(
                "streamable_http", base_url="http://localhost:8888"
            ),
        }

        # 2. Register transports
        for name, transport in transports.items():
            manager.register_transport(name, transport)

        # 3. Verify registration
        registered = manager.list_transports()
        assert len(registered) >= 4

        # 4. Get specific transport
        stdio_transport = manager.get_transport("stdio")
        assert stdio_transport is not None
        assert stdio_transport.command == "echo"

        # 5. Test cleanup
        await manager.disconnect_all()

        # All transports should be cleared
        assert len(manager.list_transports()) == 0

    @pytest.mark.asyncio
    async def test_mcp_monitoring_and_metrics(self):
        """Test MCP monitoring and metrics collection."""
        # Create server with monitoring enabled
        server = MCPServer(
            name="monitored-server",
            enable_metrics=True,
            enable_monitoring=True,
            cache_backend="redis",
            cache_config={"redis_url": get_redis_url()},
        )

        # Register monitored tools
        call_count = 0

        @server.tool(monitor=True)
        async def monitored_tool(x: int) -> int:
            """Tool with monitoring enabled."""
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate work
            return x * x

        @server.tool(monitor=True, alert_threshold_ms=50)
        async def slow_tool(n: int) -> int:
            """Tool that might trigger alerts."""
            await asyncio.sleep(0.1)  # Deliberately slow
            return n + 1

        # Execute tools multiple times
        for i in range(5):
            await monitored_tool(i)

        # Execute slow tool
        await slow_tool(10)

        # Check metrics
        metrics = server.get_metrics()

        assert metrics["tools_executed"] >= 6
        assert "monitored_tool" in metrics.get("tool_execution_times", {})
        assert "slow_tool" in metrics.get("tool_execution_times", {})

        # Verify execution counts
        assert call_count == 5

        # Check if slow execution was logged (would trigger alert in production)
        slow_metrics = metrics.get("tool_execution_times", {}).get("slow_tool", {})
        if slow_metrics:
            assert slow_metrics.get("max_time_ms", 0) > 50
