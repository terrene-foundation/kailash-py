"""Integration tests for MCP server resource subscription functionality.

Tests the complete subscription workflow with real WebSocket connections,
authentication, and resource change notifications.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
import websockets
from kailash.mcp_server.auth import APIKeyAuth, AuthManager
from kailash.mcp_server.protocol import ResourceChange, ResourceChangeType
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import ResourceSubscriptionManager


class TestMCPResourceSubscriptionIntegration:
    """Integration tests for MCP resource subscriptions."""

    @pytest_asyncio.fixture
    async def auth_provider(self):
        """Create auth provider with API key auth."""
        return APIKeyAuth(keys=["test_key_123"])

    @pytest_asyncio.fixture
    async def event_store(self):
        """Create mock event store."""
        store = Mock()
        store.append_event = AsyncMock()
        store.stream_events = AsyncMock(return_value=[])
        return store

    @pytest_asyncio.fixture
    async def mcp_server(self, event_store):
        """Create MCP server with subscription support."""
        server = MCPServer(
            name="test-server",
            transport="websocket",
            websocket_host="127.0.0.1",
            websocket_port=9001,  # Use fixed port for testing
            enable_subscriptions=True,
            auth_provider=None,  # Disable auth for testing
            event_store=event_store,
        )

        # Add test resources using the decorator approach
        @server.resource("file:///{filename}")
        def file_resource(filename):
            if filename == "test.json":
                return {"content": "test data", "version": 1}
            elif filename == "config.yaml":
                return {"content": "config: value", "version": 1}
            else:
                return {"content": f"content for {filename}", "version": 1}

        # Add more resources for pagination testing
        @server.resource("config:///{section}")
        def config_resource(section):
            configs = {
                "database": {"host": "localhost", "port": 5432},
                "redis": {"host": "localhost", "port": 6379},
                "logging": {"level": "INFO", "format": "json"},
            }
            return configs.get(section, {})

        @server.resource("api:///{endpoint}")
        def api_resource(endpoint):
            return {"endpoint": endpoint, "status": "active"}

        yield server

        # Cleanup
        if server._transport:
            await server._transport.disconnect()

    @pytest_asyncio.fixture
    async def running_server(self, mcp_server):
        """Start the MCP server and return connection info."""
        # Start server in background
        server_task = asyncio.create_task(mcp_server._run_websocket())

        # Wait for server to start
        await asyncio.sleep(0.2)

        # Get actual port (since we used port 0)
        actual_port = mcp_server.websocket_port
        if mcp_server._transport and hasattr(mcp_server._transport, "port"):
            actual_port = mcp_server._transport.port

        yield {"host": "127.0.0.1", "port": actual_port, "server": mcp_server}

        # Cleanup
        if mcp_server.subscription_manager:
            await mcp_server.subscription_manager.shutdown()

        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    async def create_websocket_client(self, host: str, port: int):
        """Create WebSocket client connection."""
        uri = f"ws://{host}:{port}"
        return await websockets.connect(uri)

    async def send_mcp_request(
        self, websocket, method: str, params: Dict[str, Any] = None
    ):
        """Send MCP request and return response."""
        request = {
            "jsonrpc": "2.0",
            "id": f"req_{method}_{asyncio.get_event_loop().time()}",
            "method": method,
            "params": params or {},
        }

        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        return json.loads(response)

    @pytest.mark.asyncio
    async def test_server_subscription_capabilities(self, running_server):
        """Test that server advertises subscription capabilities."""
        server_info = running_server

        async with await self.create_websocket_client(
            server_info["host"], server_info["port"]
        ) as ws:
            # Send initialize request
            response = await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # Verify subscription capabilities are advertised
            assert "result" in response
            capabilities = response["result"]["capabilities"]
            assert "resources" in capabilities

            resources_caps = capabilities["resources"]
            assert resources_caps["subscribe"] is True
            assert resources_caps["listChanged"] is True
            assert resources_caps["listSupported"] is True
            assert resources_caps["readSupported"] is True

    @pytest.mark.asyncio
    async def test_resource_subscription_lifecycle(self, running_server):
        """Test complete subscription lifecycle: create, notify, cleanup."""
        server_info = running_server

        async with await self.create_websocket_client(
            server_info["host"], server_info["port"]
        ) as ws:
            # Initialize connection
            await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # Create subscription
            subscribe_response = await self.send_mcp_request(
                ws, "resources/subscribe", {"uri": "file:///test.json"}
            )

            assert (
                "result" in subscribe_response
            ), f"Expected result in response: {subscribe_response}"
            subscription_id = subscribe_response["result"]["subscriptionId"]
            assert subscription_id is not None

            # Verify subscription was created
            server = server_info["server"]
            assert server.subscription_manager is not None
            subscription = server.subscription_manager.get_subscription(subscription_id)
            assert subscription is not None
            assert subscription.uri_pattern == "file:///test.json"

            # Trigger resource change
            change = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///test.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change)

            # Check for notification (with timeout)
            try:
                notification_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                notification = json.loads(notification_raw)

                assert notification["method"] == "notifications/resources/updated"
                assert notification["params"]["uri"] == "file:///test.json"
                assert notification["params"]["type"] == "updated"
            except asyncio.TimeoutError:
                pytest.fail("No notification received within timeout")

            # Unsubscribe
            unsubscribe_response = await self.send_mcp_request(
                ws, "resources/unsubscribe", {"subscriptionId": subscription_id}
            )

            assert "result" in unsubscribe_response
            assert unsubscribe_response["result"]["success"] is True

            # Verify subscription was removed
            subscription = server.subscription_manager.get_subscription(subscription_id)
            assert subscription is None

    @pytest.mark.asyncio
    async def test_wildcard_subscription_matching(self, running_server):
        """Test wildcard pattern matching in subscriptions."""
        server_info = running_server

        async with await self.create_websocket_client(
            server_info["host"], server_info["port"]
        ) as ws:
            # Initialize connection
            await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # Create wildcard subscription
            subscribe_response = await self.send_mcp_request(
                ws,
                "resources/subscribe",
                {"uri": "file:///*.json"},  # Match all JSON files
            )

            assert "result" in subscribe_response
            subscription_id = subscribe_response["result"]["subscriptionId"]

            # Trigger changes to different JSON files
            server = server_info["server"]

            for uri in [
                "file:///test.json",
                "file:///data.json",
                "file:///config.json",
            ]:
                change = ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri=uri,
                    timestamp=datetime.utcnow(),
                )
                await server.subscription_manager.process_resource_change(change)

                # Should receive notification for each
                try:
                    notification_raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    notification = json.loads(notification_raw)

                    assert notification["method"] == "notifications/resources/updated"
                    assert notification["params"]["uri"] == uri
                except asyncio.TimeoutError:
                    pytest.fail(f"No notification received for {uri}")

            # Test non-matching file (should not trigger notification)
            change = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///test.yaml",  # YAML file, not JSON
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change)

            # Should not receive notification
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.2)
                pytest.fail("Received unexpected notification for non-matching pattern")
            except asyncio.TimeoutError:
                pass  # Expected - no notification should be sent

    @pytest.mark.asyncio
    async def test_cursor_based_resource_listing(self, running_server):
        """Test cursor-based pagination in resource listing."""
        server_info = running_server

        async with await self.create_websocket_client(
            server_info["host"], server_info["port"]
        ) as ws:
            # Initialize connection
            await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # List resources with limit
            list_response = await self.send_mcp_request(
                ws, "resources/list", {"limit": 1}
            )

            assert "result" in list_response
            result = list_response["result"]

            # Should have resources and next cursor
            assert "resources" in result
            assert len(result["resources"]) == 1
            assert "nextCursor" in result

            # Use cursor for next page
            next_response = await self.send_mcp_request(
                ws, "resources/list", {"cursor": result["nextCursor"], "limit": 1}
            )

            assert "result" in next_response
            next_result = next_response["result"]

            # Should have different resources
            first_uri = result["resources"][0]["uri"]
            second_uri = next_result["resources"][0]["uri"]
            assert first_uri != second_uri

    @pytest.mark.asyncio
    async def test_subscription_authentication(self, event_store):
        """Test subscription with authentication requirements."""
        from unittest.mock import AsyncMock, Mock

        from kailash.mcp_server.auth import PermissionError as PermissionDeniedError

        # Create server with authentication enabled
        auth_provider = Mock()
        auth_provider.authenticate_and_authorize = AsyncMock(
            side_effect=PermissionDeniedError("Not authorized")
        )

        server = MCPServer(
            name="auth-test-server",
            transport="websocket",
            websocket_host="127.0.0.1",
            websocket_port=9003,  # Different port for auth test
            enable_subscriptions=True,
            auth_provider=auth_provider,
            event_store=event_store,
        )

        # Add test resource
        @server.resource("file:///{filename}")
        def file_resource(filename):
            return {"content": f"content for {filename}", "version": 1}

        # Start server in background
        server_task = asyncio.create_task(server._run_websocket())
        await asyncio.sleep(0.2)

        try:
            async with await self.create_websocket_client("127.0.0.1", 9003) as ws:
                # Initialize connection
                await self.send_mcp_request(
                    ws,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"resources": {}},
                        "clientInfo": {"name": "test-client", "version": "1.0.0"},
                    },
                )

                # Try to subscribe without authentication (should fail)
                subscribe_response = await self.send_mcp_request(
                    ws, "resources/subscribe", {"uri": "file:///test.json"}
                )

                # Should receive error due to missing authentication
                assert "error" in subscribe_response
                # Authentication error returns -32601 with authorization message
                assert subscribe_response["error"]["code"] == -32601
                assert "authorized" in subscribe_response["error"]["message"].lower()
        finally:
            # Cleanup
            if server.subscription_manager:
                await server.subscription_manager.shutdown()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_multiple_client_subscriptions(self, running_server):
        """Test multiple clients with independent subscriptions."""
        server_info = running_server

        # Create two client connections
        async with (
            await self.create_websocket_client(
                server_info["host"], server_info["port"]
            ) as ws1,
            await self.create_websocket_client(
                server_info["host"], server_info["port"]
            ) as ws2,
        ):

            # Initialize both connections
            for ws in [ws1, ws2]:
                await self.send_mcp_request(
                    ws,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"resources": {}},
                        "clientInfo": {"name": "test-client", "version": "1.0.0"},
                    },
                )

            # Create different subscriptions on each client
            sub1_response = await self.send_mcp_request(
                ws1, "resources/subscribe", {"uri": "file:///test.json"}
            )
            sub2_response = await self.send_mcp_request(
                ws2, "resources/subscribe", {"uri": "file:///config.yaml"}
            )

            assert "result" in sub1_response
            assert "result" in sub2_response

            sub1_id = sub1_response["result"]["subscriptionId"]
            sub2_id = sub2_response["result"]["subscriptionId"]

            # Trigger change for first subscription
            server = server_info["server"]
            change1 = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///test.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change1)

            # Only first client should receive notification
            try:
                notification1_raw = await asyncio.wait_for(ws1.recv(), timeout=0.5)
                notification1 = json.loads(notification1_raw)
                assert notification1["params"]["uri"] == "file:///test.json"
            except asyncio.TimeoutError:
                pytest.fail("Client 1 did not receive notification")

            # Second client should not receive notification
            try:
                await asyncio.wait_for(ws2.recv(), timeout=0.2)
                pytest.fail("Client 2 received unexpected notification")
            except asyncio.TimeoutError:
                pass  # Expected

            # Trigger change for second subscription
            change2 = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///config.yaml",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change2)

            # Only second client should receive notification
            try:
                notification2_raw = await asyncio.wait_for(ws2.recv(), timeout=0.5)
                notification2 = json.loads(notification2_raw)
                assert notification2["params"]["uri"] == "file:///config.yaml"
            except asyncio.TimeoutError:
                pytest.fail("Client 2 did not receive notification")

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_disconnect(self, running_server):
        """Test that subscriptions are cleaned up when client disconnects."""
        server_info = running_server
        server = server_info["server"]

        # Create connection and subscription
        ws = await self.create_websocket_client(
            server_info["host"], server_info["port"]
        )

        try:
            # Initialize connection
            await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # Create subscription
            subscribe_response = await self.send_mcp_request(
                ws, "resources/subscribe", {"uri": "file:///test.json"}
            )

            subscription_id = subscribe_response["result"]["subscriptionId"]

            # Verify subscription exists
            subscription = server.subscription_manager.get_subscription(subscription_id)
            assert subscription is not None

            # Get the actual connection ID from the subscription
            connection_id = subscription.connection_id

        finally:
            # Close WebSocket connection
            await ws.close()

        # Simulate connection cleanup using the actual connection ID
        removed_count = await server.subscription_manager.cleanup_connection(
            connection_id
        )
        assert removed_count > 0  # Should have removed at least one subscription

        # Verify subscription was cleaned up
        subscription = server.subscription_manager.get_subscription(subscription_id)
        assert subscription is None

    @pytest.mark.asyncio
    async def test_subscription_rate_limiting(self, running_server):
        """Test subscription rate limiting functionality."""
        server_info = running_server
        server = server_info["server"]

        # Configure rate limiter to allow only 1 subscription
        if server.subscription_manager:
            rate_limiter = Mock()
            rate_limiter.check_rate_limit = AsyncMock(
                side_effect=[True, False]
            )  # First succeeds, second fails
            server.subscription_manager.rate_limiter = rate_limiter

        async with await self.create_websocket_client(
            server_info["host"], server_info["port"]
        ) as ws:
            # Initialize connection
            await self.send_mcp_request(
                ws,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            )

            # First subscription should succeed
            subscribe_response1 = await self.send_mcp_request(
                ws, "resources/subscribe", {"uri": "file:///test.json"}
            )

            assert "result" in subscribe_response1

            # Second subscription should fail due to rate limiting
            subscribe_response2 = await self.send_mcp_request(
                ws, "resources/subscribe", {"uri": "file:///config.yaml"}
            )

            assert "error" in subscribe_response2
            assert "Rate limit" in subscribe_response2["error"]["message"]
