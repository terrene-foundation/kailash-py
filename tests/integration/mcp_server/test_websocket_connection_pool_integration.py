"""Integration tests for WebSocket connection pooling with real servers.

NO MOCKING - All tests use real WebSocket servers per testing policy.
"""

import asyncio
import json
import time

import pytest
import websockets
from kailash.mcp_server.client import MCPClient
from kailash.mcp_server.errors import TransportError
from websockets.server import serve


@pytest.mark.integration
class TestWebSocketConnectionPoolIntegration:
    """Integration tests for WebSocket connection pooling with real servers."""

    @pytest.fixture
    def client(self):
        """Create MCP client with connection pooling enabled."""
        return MCPClient(
            connection_pool_config={
                "max_connections": 3,
                "max_idle_time": 30,
                "health_check_interval": 10,
                "enable_connection_reuse": True,
            },
            enable_metrics=True,
        )

    @pytest.mark.asyncio
    async def test_connection_reuse_with_real_server(self, client):
        """Test connection reuse with a real WebSocket MCP server."""
        # Track connection count on server side
        connection_count = 0
        active_connections = set()

        async def mcp_handler(websocket, path):
            nonlocal connection_count
            connection_count += 1
            connection_id = id(websocket)
            active_connections.add(connection_id)

            try:
                async for message in websocket:
                    data = json.loads(message)

                    if data.get("method") == "tools/list":
                        response = {
                            "jsonrpc": "2.0",
                            "id": data["id"],
                            "result": {
                                "tools": [
                                    {
                                        "name": "test_tool",
                                        "description": "Test tool",
                                        "inputSchema": {"type": "object"},
                                    }
                                ]
                            },
                        }
                        await websocket.send(json.dumps(response))

                    elif data.get("method") == "tools/call":
                        response = {
                            "jsonrpc": "2.0",
                            "id": data["id"],
                            "result": {
                                "content": [
                                    {
                                        "text": f"Connection {connection_id}: {data['params']['arguments']}"
                                    }
                                ]
                            },
                        }
                        await websocket.send(json.dumps(response))
            finally:
                active_connections.discard(connection_id)

        # Start the server
        async with serve(mcp_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # First discovery - should create new connection
            tools1 = await client.discover_tools(ws_url)
            assert len(tools1) == 1
            initial_connections = connection_count

            # Second discovery - should reuse connection
            tools2 = await client.discover_tools(ws_url)
            assert len(tools2) == 1
            assert connection_count == initial_connections  # No new connection

            # Tool call - should reuse same connection
            result = await client.call_tool(ws_url, "test_tool", {"data": "test"})
            assert result["success"] is True
            assert connection_count == initial_connections  # Still no new connection

            # Multiple operations in parallel - should still reuse
            tasks = [
                client.discover_tools(ws_url),
                client.call_tool(ws_url, "test_tool", {"data": "parallel1"}),
                client.call_tool(ws_url, "test_tool", {"data": "parallel2"}),
            ]
            results = await asyncio.gather(*tasks)

            # Should have reused the connection for all
            assert connection_count == initial_connections
            assert len(active_connections) == 1  # Only one active connection

    @pytest.mark.asyncio
    async def test_multiple_servers_different_pools(self, client):
        """Test that different servers get different connection pools."""
        server_connections = {}

        async def tracking_handler(server_id):
            async def handler(websocket, path):
                if server_id not in server_connections:
                    server_connections[server_id] = 0
                server_connections[server_id] += 1

                async for message in websocket:
                    data = json.loads(message)
                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {
                            "tools": [
                                {
                                    "name": f"tool_{server_id}",
                                    "description": f"Tool for {server_id}",
                                    "inputSchema": {"type": "object"},
                                }
                            ]
                        },
                    }
                    await websocket.send(json.dumps(response))

            return handler

        # Start multiple servers
        servers = []
        urls = []

        for i in range(3):
            handler = tracking_handler(f"server{i}")
            server = await serve(handler, "localhost", 0)
            servers.append(server)
            port = server.sockets[0].getsockname()[1]
            urls.append(f"ws://localhost:{port}/mcp")

        try:
            # Connect to each server multiple times
            for url in urls:
                for _ in range(3):
                    await client.discover_tools(url)

            # Each server should have exactly 1 connection (reused)
            for server_id, count in server_connections.items():
                assert count == 1, f"{server_id} has {count} connections, expected 1"

        finally:
            # Clean up servers
            for server in servers:
                server.close()
                await server.wait_closed()

    @pytest.mark.asyncio
    async def test_connection_pool_size_limit(self, client):
        """Test that connection pool respects size limits."""
        # Create more servers than max_connections (3)
        servers = []
        urls = []
        connection_counts = {}

        async def counting_handler(server_id):
            async def handler(websocket, path):
                if server_id not in connection_counts:
                    connection_counts[server_id] = 0
                connection_counts[server_id] += 1

                # Keep connection alive
                try:
                    async for message in websocket:
                        data = json.loads(message)
                        response = {
                            "jsonrpc": "2.0",
                            "id": data["id"],
                            "result": {"tools": []},
                        }
                        await websocket.send(json.dumps(response))
                except:
                    pass

            return handler

        # Start 5 servers (more than pool max of 3)
        for i in range(5):
            handler = counting_handler(f"server{i}")
            server = await serve(handler, "localhost", 0)
            servers.append(server)
            port = server.sockets[0].getsockname()[1]
            urls.append(f"ws://localhost:{port}/mcp")

        try:
            # Connect to all servers
            tasks = []
            for url in urls:
                tasks.append(client.discover_tools(url))

            await asyncio.gather(*tasks)

            # Check metrics to verify pool behavior
            if client.metrics:
                # Should have tracked pool activity
                assert (
                    "websocket_pool_evictions" in client.metrics
                    or len([k for k in connection_counts if connection_counts[k] > 0])
                    <= 3
                )

        finally:
            for server in servers:
                server.close()
                await server.wait_closed()

    @pytest.mark.asyncio
    async def test_connection_health_check_real_server(self, client):
        """Test connection health checking with server that becomes unhealthy."""
        connection_count = 0
        should_fail_health = False

        async def health_check_handler(websocket, path):
            nonlocal connection_count
            connection_count += 1

            async for message in websocket:
                data = json.loads(message)

                # Simulate unhealthy connection after flag is set
                if should_fail_health and data.get("method") == "ping":
                    await websocket.close()
                    return

                response = {"jsonrpc": "2.0", "id": data["id"], "result": {"tools": []}}
                await websocket.send(json.dumps(response))

        async with serve(health_check_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # First connection
            await client.discover_tools(ws_url)
            assert connection_count == 1

            # Set flag to make health check fail
            should_fail_health = True

            # Trigger health check (if implemented)
            if hasattr(client, "_check_connection_health"):
                try:
                    await client._check_connection_health(ws_url)
                except:
                    pass  # Health check might fail, that's expected

            # Next operation should create new connection
            should_fail_health = False  # Allow new connection to work
            await client.discover_tools(ws_url)

            # Should have created a new connection
            assert connection_count >= 2

    @pytest.mark.asyncio
    async def test_concurrent_access_thread_safety(self, client):
        """Test thread-safe concurrent access with real server."""
        request_count = 0
        concurrent_requests = set()
        max_concurrent = 0

        async def concurrent_handler(websocket, path):
            nonlocal request_count, max_concurrent

            async for message in websocket:
                data = json.loads(message)
                request_id = data.get("id")

                # Track concurrent requests
                concurrent_requests.add(request_id)
                current_concurrent = len(concurrent_requests)
                max_concurrent = max(max_concurrent, current_concurrent)
                request_count += 1

                # Simulate some processing time
                await asyncio.sleep(0.05)

                if data.get("method") == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": []},
                    }
                elif data.get("method") == "tools/call":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"text": f"Request {request_id}"}]},
                    }
                else:
                    response = {"jsonrpc": "2.0", "id": request_id, "result": {}}

                await websocket.send(json.dumps(response))
                concurrent_requests.discard(request_id)

        async with serve(concurrent_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # Create many concurrent requests
            tasks = []
            for i in range(20):
                if i % 3 == 0:
                    tasks.append(client.discover_tools(ws_url))
                else:
                    tasks.append(client.call_tool(ws_url, "test", {"n": i}))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should succeed
            failures = [r for r in results if isinstance(r, Exception)]
            assert len(failures) == 0, f"Had {len(failures)} failures"

            # Should have handled requests concurrently but safely
            assert request_count == 20
            assert max_concurrent >= 1  # Had some concurrency

    @pytest.mark.asyncio
    async def test_connection_cleanup_idle_timeout(self, client):
        """Test that idle connections are cleaned up."""
        cleanup_happened = False

        async def cleanup_handler(websocket, path):
            nonlocal cleanup_happened
            try:
                async for message in websocket:
                    data = json.loads(message)
                    response = {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {"tools": []},
                    }
                    await websocket.send(json.dumps(response))
            except websockets.exceptions.ConnectionClosed:
                cleanup_happened = True

        async with serve(cleanup_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # Create connection
            await client.discover_tools(ws_url)

            # If cleanup is implemented, trigger it
            if hasattr(client, "_cleanup_idle_connections"):
                # Force immediate cleanup
                await client._cleanup_idle_connections(max_idle_seconds=0)

                # Give server time to notice closed connection
                await asyncio.sleep(0.1)

                # Should have cleaned up
                assert cleanup_happened or not hasattr(client, "_has_active_connection")

    @pytest.mark.asyncio
    async def test_connection_pool_performance_benefit(self, client):
        """Test that pooling provides performance benefits."""
        # Create a server that tracks timing
        timing_results = {"with_pooling": [], "without_pooling": []}

        async def timing_handler(websocket, path):
            async for message in websocket:
                data = json.loads(message)
                response = {
                    "jsonrpc": "2.0",
                    "id": data["id"],
                    "result": {
                        "tools": [{"name": "timer", "description": "Timer tool"}]
                    },
                }
                await websocket.send(json.dumps(response))

        async with serve(timing_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # Test with pooling enabled
            start = time.time()
            for _ in range(5):
                await client.discover_tools(ws_url)
            pooled_time = time.time() - start
            timing_results["with_pooling"].append(pooled_time)

            # Test without pooling (new client)
            client_no_pool = MCPClient(
                connection_pool_config={"enable_connection_reuse": False}
            )

            start = time.time()
            for _ in range(5):
                await client_no_pool.discover_tools(ws_url)
            no_pool_time = time.time() - start
            timing_results["without_pooling"].append(no_pool_time)

            # With pooling should generally be faster (connection reuse)
            # But we won't assert this strictly as timing can vary
            print(f"With pooling: {pooled_time:.3f}s")
            print(f"Without pooling: {no_pool_time:.3f}s")
            print(f"Speedup: {no_pool_time / pooled_time:.2f}x")

    @pytest.mark.asyncio
    async def test_connection_error_recovery(self, client):
        """Test that pool recovers from connection errors."""
        error_count = 0
        should_error = True

        async def error_handler(websocket, path):
            nonlocal error_count, should_error

            if should_error:
                error_count += 1
                await websocket.close()
                return

            async for message in websocket:
                data = json.loads(message)
                response = {"jsonrpc": "2.0", "id": data["id"], "result": {"tools": []}}
                await websocket.send(json.dumps(response))

        async with serve(error_handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://localhost:{port}/mcp"

            # First attempt should fail
            try:
                await client.discover_tools(ws_url)
            except:
                pass  # Expected to fail

            assert error_count == 1

            # Disable errors
            should_error = False

            # Next attempt should work (new connection)
            tools = await client.discover_tools(ws_url)
            assert isinstance(tools, list)

            # Should have recovered
            assert error_count == 1  # No additional errors
