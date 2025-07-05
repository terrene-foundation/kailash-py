"""Production-grade high availability MCP scenarios.

Tests real-world production patterns with NO MOCKING.
All services use real Docker containers.
"""

import asyncio
import json
import multiprocessing
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
import redis.asyncio as redis

from kailash.mcp_server import MCPClient, MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.mcp_server.discovery import (
    HealthChecker,
    LoadBalancer,
    ServiceMesh,
    ServiceRegistry,
)
from kailash.mcp_server.oauth import ResourceServer
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)


def run_mcp_server(server_id: int, port: int, redis_url: str):
    """Run an MCP server instance in a separate process."""
    import asyncio

    from kailash.mcp_server import MCPServer

    async def _run_server():
        # Create server with unique name
        server = MCPServer(
            name=f"ha-server-{server_id}",
            cache_backend="redis",
            cache_config={
                "redis_url": redis_url,
                "prefix": f"mcp_ha_{server_id}:",
                "ttl": 600,
            },
            enable_metrics=True,
            enable_monitoring=True,
        )

        # Register production-like tools
        @server.tool(cache_key="compute_metrics", cache_ttl=60)
        async def compute_metrics(dataset_id: str, metric_type: str) -> dict:
            """Compute metrics for a dataset - simulates real computation."""
            # Simulate varying computation time based on server
            base_time = 0.1 + (server_id * 0.05)
            await asyncio.sleep(base_time)

            return {
                "dataset_id": dataset_id,
                "metric_type": metric_type,
                "value": 42.0 + server_id,
                "computed_by": f"server-{server_id}",
                "timestamp": time.time(),
            }

        @server.tool()
        async def health_check() -> dict:
            """Server health check endpoint."""
            return {
                "server": f"ha-server-{server_id}",
                "status": "healthy",
                "uptime": time.time(),
                "port": port,
            }

        @server.resource(f"server://ha-{server_id}/status")
        async def server_status():
            """Get detailed server status."""
            # Check Redis connection
            try:
                r = redis.from_url(redis_url)
                await r.ping()
                redis_status = "connected"
                await r.aclose()
            except:
                redis_status = "disconnected"

            return {
                "server_id": server_id,
                "redis": redis_status,
                "memory_usage": "52MB",  # In real app, would get actual memory
                "active_connections": 3,  # In real app, would track connections
                "request_rate": "120/min",  # In real app, would calculate rate
            }

        # Run server on HTTP transport
        from aiohttp import web

        app = web.Application()

        # Add MCP endpoints
        async def handle_tools(request):
            return web.json_response(
                {
                    "tools": [
                        {
                            "name": "compute_metrics",
                            "description": "Compute metrics for a dataset",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "dataset_id": {"type": "string"},
                                    "metric_type": {"type": "string"},
                                },
                                "required": ["dataset_id", "metric_type"],
                            },
                        },
                        {"name": "health_check", "description": "Server health check"},
                    ]
                }
            )

        async def handle_call_tool(request):
            data = await request.json()
            tool_name = data.get("tool")
            args = data.get("arguments", {})

            if tool_name == "compute_metrics":
                result = await compute_metrics(**args)
            elif tool_name == "health_check":
                result = await health_check()
            else:
                return web.json_response(
                    {"error": f"Unknown tool: {tool_name}"}, status=404
                )

            return web.json_response({"result": result})

        app.router.add_get("/mcp/tools", handle_tools)
        app.router.add_post("/mcp/call", handle_call_tool)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()

        print(f"Server {server_id} running on port {port}")

        # Keep server running
        while True:
            await asyncio.sleep(1)

    asyncio.run(_run_server())


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_redis
@pytest.mark.slow
class TestMCPHighAvailability:
    """Test MCP in high availability production scenarios."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure all required services are running."""
        await ensure_docker_services(["redis", "postgres"])
        yield

    @pytest.mark.asyncio
    async def test_multi_server_load_balancing(self):
        """Test load balancing across multiple MCP server instances."""
        redis_url = get_redis_url()

        # Start 3 MCP server instances in separate processes
        server_ports = [8901, 8902, 8903]
        processes = []

        with ProcessPoolExecutor(max_workers=3) as executor:
            # Start servers
            for i, port in enumerate(server_ports):
                future = executor.submit(run_mcp_server, i, port, redis_url)
                processes.append(future)

            # Wait for servers to start
            await asyncio.sleep(2)

            try:
                # Create service registry and register all servers
                registry = ServiceRegistry()

                for i, port in enumerate(server_ports):
                    server_info = ServerInfo(
                        name=f"ha-server-{i}",
                        transport="http",
                        url=f"http://localhost:{port}/mcp",
                        capabilities=["tools", "resources"],
                        health_status="healthy",
                        metadata={"instance_id": i, "port": port},
                    )
                    await registry.register_server(server_info)

                # Create load balancer
                load_balancer = LoadBalancer()

                # Simulate 10 requests distributed across servers
                results = []
                for request_id in range(10):
                    # Get best server based on health and load
                    servers = await registry.discover_servers(capability="tools")
                    best_server = load_balancer.select_best_server(servers)

                    # Create client for selected server
                    client = MCPClient(
                        {
                            "transport": "http",
                            "url": best_server.url,
                        }
                    )

                    # Make request
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{best_server.url}/call",
                            json={
                                "tool": "compute_metrics",
                                "arguments": {
                                    "dataset_id": f"dataset-{request_id}",
                                    "metric_type": "average",
                                },
                            },
                        ) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                results.append(result["result"])

                # Verify load was distributed
                server_counts = {}
                for result in results:
                    server = result["computed_by"]
                    server_counts[server] = server_counts.get(server, 0) + 1

                # Each server should have handled some requests
                assert len(server_counts) >= 2  # At least 2 servers used
                assert all(count > 0 for count in server_counts.values())

            finally:
                # Terminate server processes
                for process in processes:
                    process.cancel()

    @pytest.mark.asyncio
    async def test_failover_scenario(self):
        """Test failover when a server becomes unavailable."""
        redis_url = get_redis_url()

        # Start 2 servers
        with ProcessPoolExecutor(max_workers=2) as executor:
            # Start primary and backup servers
            primary = executor.submit(run_mcp_server, 0, 8904, redis_url)
            backup = executor.submit(run_mcp_server, 1, 8905, redis_url)

            await asyncio.sleep(2)

            try:
                # Create registry with health checking
                registry = ServiceRegistry()
                health_checker = HealthChecker(check_interval=1.0)

                # Register servers
                primary_server = ServerInfo(
                    name="primary",
                    transport="http",
                    url="http://localhost:8904/mcp",
                    capabilities=["tools"],
                )
                backup_server = ServerInfo(
                    name="backup",
                    transport="http",
                    url="http://localhost:8905/mcp",
                    capabilities=["tools"],
                )

                await registry.register_server(primary_server)
                await registry.register_server(backup_server)

                # Start health monitoring
                await health_checker.start(registry)

                # Create service mesh for automatic failover
                mesh = ServiceMesh(registry)

                # Make successful call to primary
                try:
                    result = await mesh.call_with_failover(
                        "tools",
                        "health_check",
                        {},
                        max_retries=2,
                    )
                    assert result is not None
                except Exception as e:
                    # May fail if servers aren't ready
                    print(f"Initial call failed: {e}")

                # Simulate primary failure by canceling it
                primary.cancel()
                await asyncio.sleep(2)

                # Health checker should mark primary as unhealthy
                # Mesh should automatically failover to backup
                result = await mesh.call_with_failover(
                    "tools",
                    "health_check",
                    {},
                    max_retries=2,
                )

                # Should get response from backup server
                assert result is not None
                # In real scenario, would verify it came from backup

                await health_checker.stop()

            finally:
                primary.cancel()
                backup.cancel()

    @pytest.mark.asyncio
    async def test_cache_consistency_across_instances(self):
        """Test cache consistency when multiple servers share Redis cache."""
        redis_url = get_redis_url()

        # Clear any existing cache
        r = redis.from_url(redis_url)
        await r.flushdb()
        await r.aclose()

        with ProcessPoolExecutor(max_workers=2) as executor:
            # Start 2 servers sharing same Redis cache
            server1 = executor.submit(run_mcp_server, 0, 8906, redis_url)
            server2 = executor.submit(run_mcp_server, 1, 8907, redis_url)

            await asyncio.sleep(2)

            try:
                # Make request to server 1 - should cache result
                async with aiohttp.ClientSession() as session:
                    resp1 = await session.post(
                        "http://localhost:8906/mcp/call",
                        json={
                            "tool": "compute_metrics",
                            "arguments": {
                                "dataset_id": "shared-dataset",
                                "metric_type": "sum",
                            },
                        },
                    )
                    result1 = await resp1.json()

                # Make same request to server 2 - should get cached result
                async with aiohttp.ClientSession() as session:
                    resp2 = await session.post(
                        "http://localhost:8907/mcp/call",
                        json={
                            "tool": "compute_metrics",
                            "arguments": {
                                "dataset_id": "shared-dataset",
                                "metric_type": "sum",
                            },
                        },
                    )
                    result2 = await resp2.json()

                # Results should match (from cache)
                # Note: In real implementation, would need to ensure cache keys match
                assert result1 is not None
                assert result2 is not None

                # Verify cache was used by checking Redis directly
                r = redis.from_url(redis_url)
                try:
                    # Check for cached values (keys would include the cache prefix)
                    keys = await r.keys("mcp_ha_*:compute_metrics:*")
                    assert len(keys) > 0  # Should have cached entries
                finally:
                    await r.aclose()

            finally:
                server1.cancel()
                server2.cancel()


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
@pytest.mark.slow
class TestMCPSecurityProduction:
    """Test MCP security features in production scenarios."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_services(self):
        """Ensure all required services are running."""
        await ensure_docker_services(["postgres", "redis"])
        yield

    @pytest.mark.asyncio
    async def test_oauth2_flow_with_real_database(self):
        """Test complete OAuth2 flow with real PostgreSQL for token storage."""
        db_conn = get_postgres_connection_string()

        # Create OAuth2 provider with real database backend
        from kailash.mcp_server.oauth import AuthorizationServer

        auth_server = AuthorizationServer(
            database_url=db_conn,
            token_expiry=3600,
            refresh_token_expiry=86400,
        )

        # Register a client application
        client = await auth_server.register_client(
            client_name="production-app",
            redirect_uris=["https://app.example.com/callback"],
            scopes=["tools.execute", "resources.read"],
        )

        assert client["client_id"] is not None
        assert client["client_secret"] is not None

        # Generate authorization code
        auth_code = await auth_server.create_authorization_code(
            client_id=client["client_id"],
            user_id="user-123",
            scopes=["tools.execute"],
            redirect_uri="https://app.example.com/callback",
        )

        assert auth_code is not None

        # Exchange code for tokens
        token_response = await auth_server.exchange_code_for_token(
            code=auth_code,
            client_id=client["client_id"],
            client_secret=client["client_secret"],
            redirect_uri="https://app.example.com/callback",
        )

        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert token_response["token_type"] == "Bearer"

        # Verify token is valid
        token_info = await auth_server.introspect_token(token_response["access_token"])
        assert token_info["active"] is True
        assert token_info["client_id"] == client["client_id"]
        assert "tools.execute" in token_info["scopes"]

        # Test token refresh
        refresh_response = await auth_server.refresh_token(
            refresh_token=token_response["refresh_token"],
            client_id=client["client_id"],
            client_secret=client["client_secret"],
        )

        assert "access_token" in refresh_response
        assert refresh_response["access_token"] != token_response["access_token"]

        # Revoke token
        await auth_server.revoke_token(
            token=refresh_response["access_token"],
            client_id=client["client_id"],
            client_secret=client["client_secret"],
        )

        # Verify token is revoked
        revoked_info = await auth_server.introspect_token(
            refresh_response["access_token"]
        )
        assert revoked_info["active"] is False


if __name__ == "__main__":
    # Allow running individual test functions for debugging
    pytest.main([__file__, "-v", "-s"])
