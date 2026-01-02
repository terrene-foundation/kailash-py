"""End-to-end tests for MCP server resource subscription functionality.

Tests complete MCP resource subscription workflows with real client scenarios,
multiple simultaneous connections, resource changes, and production-like conditions.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
import websockets
from kailash.mcp_server.protocol import ResourceChange, ResourceChangeType
from kailash.mcp_server.server import MCPServer


class MCPTestClient:
    """Test MCP client for E2E testing."""

    def __init__(self, host: str, port: int, client_name: str = "test-client"):
        self.host = host
        self.port = port
        self.client_name = client_name
        self.websocket = None
        self.subscriptions = {}
        self.notifications = []
        self.request_id = 0

    async def connect(self):
        """Connect to MCP server."""
        uri = f"ws://{self.host}:{self.port}"
        self.websocket = await websockets.connect(uri)

        # Initialize MCP session
        await self.initialize()

    async def disconnect(self):
        """Disconnect from MCP server."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def initialize(self):
        """Initialize MCP session."""
        response = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"resources": {"subscribe": True}},
                "clientInfo": {"name": self.client_name, "version": "1.0.0"},
            },
        )

        assert "result" in response
        return response["result"]

    async def send_request(
        self, method: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send MCP request and return response."""
        self.request_id += 1
        request_id = f"{self.client_name}_{self.request_id}"
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        await self.websocket.send(json.dumps(request))

        # Keep receiving messages until we get the response (not a notification)
        while True:
            response = await self.websocket.recv()
            message = json.loads(response)

            # Check if this is a notification (no id field) or response to another request
            if "id" not in message:
                # This is a notification, store it and continue waiting
                self.notifications.append(message)
                continue
            elif message.get("id") == request_id:
                # This is our response
                return message
            else:
                # This is a response to a different request, ignore and continue
                continue

    async def list_resources(
        self, cursor: str = None, limit: int = None
    ) -> Dict[str, Any]:
        """List available resources."""
        params = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = limit

        return await self.send_request("resources/list", params)

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific resource."""
        return await self.send_request("resources/read", {"uri": uri})

    async def subscribe_to_resource(self, uri_pattern: str, cursor: str = None) -> str:
        """Subscribe to resource changes."""
        params = {"uri": uri_pattern}
        if cursor:
            params["cursor"] = cursor

        response = await self.send_request("resources/subscribe", params)

        if "result" in response:
            subscription_id = response["result"]["subscriptionId"]
            self.subscriptions[subscription_id] = uri_pattern
            return subscription_id
        else:
            raise Exception(f"Subscription failed: {response}")

    async def unsubscribe_from_resource(self, subscription_id: str) -> bool:
        """Unsubscribe from resource changes."""
        response = await self.send_request(
            "resources/unsubscribe", {"subscriptionId": subscription_id}
        )

        if "result" in response:
            success = response["result"]["success"]
            if success and subscription_id in self.subscriptions:
                del self.subscriptions[subscription_id]
            return success
        else:
            return False

    async def listen_for_notifications(
        self, timeout: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Listen for notifications from server."""
        notifications = []
        end_time = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < end_time:
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=end_time - asyncio.get_event_loop().time(),
                )
                data = json.loads(message)

                # Check if it's a notification (no id field)
                if "method" in data and "id" not in data:
                    notifications.append(data)
                    self.notifications.append(data)

            except asyncio.TimeoutError:
                break

        return notifications


class TestMCPResourceSubscriptionsE2E:
    """End-to-end tests for MCP resource subscriptions."""

    @pytest_asyncio.fixture
    async def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest_asyncio.fixture
    async def event_store(self):
        """Create async mock event store for E2E testing."""
        store = AsyncMock()
        store.append_event = AsyncMock()
        store.stream_events = AsyncMock(return_value=[])
        return store

    @pytest_asyncio.fixture
    async def mcp_server(self, temp_dir, event_store):
        """Create MCP server with file-based resources."""
        server = MCPServer(
            name="e2e-test-server",
            transport="websocket",
            websocket_host="127.0.0.1",
            websocket_port=9002,  # Different port for E2E tests
            enable_subscriptions=True,
            auth_provider=None,  # No auth for E2E testing
            event_store=event_store,
        )

        # Add file system resources
        @server.resource("file:///{filepath}")
        def file_resource(filepath):
            """Read file from temp directory."""
            file_path = temp_dir / filepath
            if file_path.exists():
                return {
                    "content": file_path.read_text(),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        file_path.stat().st_mtime
                    ).isoformat(),
                }
            else:
                raise FileNotFoundError(f"File not found: {filepath}")

        # Add configuration resource
        @server.resource("config:///{section}")
        def config_resource(section):
            """Return configuration for different sections."""
            import json

            configs = {
                "database": {"host": "localhost", "port": 5432, "name": "testdb"},
                "redis": {"host": "localhost", "port": 6379, "db": 0},
                "logging": {"level": "INFO", "format": "json"},
            }
            # Return JSON-serialized content for proper MCP format
            return json.dumps(configs.get(section, {}))

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

        yield {"host": "127.0.0.1", "port": 9002, "server": mcp_server}

        # Cleanup
        if mcp_server.subscription_manager:
            await mcp_server.subscription_manager.shutdown()

        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    async def create_test_file(self, temp_dir: Path, filename: str, content: str):
        """Create a test file in the temp directory."""
        file_path = temp_dir / filename
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_single_client_subscription_workflow(self, running_server):
        """Test complete workflow: subscribe to resource, trigger change, receive notification."""
        server_info = running_server

        # Create MCP client
        client = MCPTestClient(server_info["host"], server_info["port"], "client1")

        try:
            await client.connect()

            # Subscribe to a config resource (simpler than file resources)
            subscription_id = await client.subscribe_to_resource("config:///database")
            assert subscription_id is not None

            # Trigger resource change notification
            server = server_info["server"]
            change = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="config:///database",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change)

            # Listen for notification
            notifications = await client.listen_for_notifications(timeout=2.0)

            assert len(notifications) > 0
            notification = notifications[0]
            assert notification["method"] == "notifications/resources/updated"
            assert notification["params"]["uri"] == "config:///database"
            assert notification["params"]["type"] == "updated"

            # Unsubscribe
            success = await client.unsubscribe_from_resource(subscription_id)
            assert success is True

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_clients_different_subscriptions(
        self, running_server, temp_dir
    ):
        """Test multiple clients with different resource subscriptions."""
        server_info = running_server

        # Create test files
        await self.create_test_file(temp_dir, "client1.json", '{"client": 1}')
        await self.create_test_file(temp_dir, "client2.json", '{"client": 2}')
        await self.create_test_file(temp_dir, "shared.json", '{"shared": true}')

        # Create multiple clients
        client1 = MCPTestClient(server_info["host"], server_info["port"], "client1")
        client2 = MCPTestClient(server_info["host"], server_info["port"], "client2")

        try:
            await client1.connect()
            await client2.connect()

            # Client 1 subscribes to its file and shared file
            sub1_own = await client1.subscribe_to_resource("file:///client1.json")
            sub1_shared = await client1.subscribe_to_resource("file:///shared.json")

            # Client 2 subscribes to its file and shared file
            sub2_own = await client2.subscribe_to_resource("file:///client2.json")
            sub2_shared = await client2.subscribe_to_resource("file:///shared.json")

            # Modify client1's file
            await self.create_test_file(
                temp_dir, "client1.json", '{"client": 1, "updated": true}'
            )

            server = server_info["server"]
            change1 = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///client1.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change1)

            # Only client1 should receive notification
            notifications1 = await client1.listen_for_notifications(timeout=1.0)
            notifications2 = await client2.listen_for_notifications(timeout=1.0)

            assert len(notifications1) == 1
            assert notifications1[0]["params"]["uri"] == "file:///client1.json"
            assert len(notifications2) == 0

            # Modify shared file
            await self.create_test_file(
                temp_dir, "shared.json", '{"shared": true, "modified": true}'
            )

            change_shared = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///shared.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change_shared)

            # Both clients should receive notification for shared file
            notifications1 = await client1.listen_for_notifications(timeout=1.0)
            notifications2 = await client2.listen_for_notifications(timeout=1.0)

            assert len(notifications1) == 1
            assert notifications1[0]["params"]["uri"] == "file:///shared.json"
            assert len(notifications2) == 1
            assert notifications2[0]["params"]["uri"] == "file:///shared.json"

        finally:
            await client1.disconnect()
            await client2.disconnect()

    @pytest.mark.asyncio
    async def test_wildcard_subscription_with_multiple_files(
        self, running_server, temp_dir
    ):
        """Test wildcard subscriptions matching multiple files."""
        server_info = running_server

        # Create multiple JSON files
        json_files = ["data1.json", "data2.json", "config.json"]
        for filename in json_files:
            await self.create_test_file(temp_dir, filename, f'{{"file": "{filename}"}}')

        # Create non-JSON file that shouldn't match
        await self.create_test_file(temp_dir, "readme.txt", "This is a text file")

        client = MCPTestClient(
            server_info["host"], server_info["port"], "wildcard_client"
        )

        try:
            await client.connect()

            # Subscribe to all JSON files using wildcard
            subscription_id = await client.subscribe_to_resource("file:///*.json")

            server = server_info["server"]

            # Modify each JSON file and verify notifications
            for filename in json_files:
                await self.create_test_file(
                    temp_dir, filename, f'{{"file": "{filename}", "updated": true}}'
                )

                change = ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri=f"file:///{filename}",
                    timestamp=datetime.utcnow(),
                )
                await server.subscription_manager.process_resource_change(change)

                # Should receive notification for this file
                notifications = await client.listen_for_notifications(timeout=1.0)
                assert len(notifications) == 1
                assert notifications[0]["params"]["uri"] == f"file:///{filename}"

            # Modify the text file (should not trigger notification)
            await self.create_test_file(temp_dir, "readme.txt", "Updated text file")

            change_txt = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///readme.txt",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change_txt)

            # Should not receive notification for text file
            notifications = await client.listen_for_notifications(timeout=0.5)
            assert len(notifications) == 0

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_configuration_subscription_workflow(self, running_server):
        """Test subscribing to configuration changes."""
        server_info = running_server

        client = MCPTestClient(
            server_info["host"], server_info["port"], "config_client"
        )

        try:
            await client.connect()

            # Subscribe to database configuration
            subscription_id = await client.subscribe_to_resource("config:///database")

            # Read initial configuration
            read_response = await client.read_resource("config:///database")
            assert "result" in read_response

            # MCP resources/read returns contents array
            result = read_response["result"]
            assert "contents" in result
            assert len(result["contents"]) > 0

            # Parse the JSON content from the first content item
            content_text = result["contents"][0]["text"]
            import json

            config = json.loads(content_text)

            assert config["host"] == "localhost"
            assert config["port"] == 5432

            # Simulate configuration change
            server = server_info["server"]
            change = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="config:///database",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(change)

            # Should receive notification
            notifications = await client.listen_for_notifications(timeout=1.0)
            assert len(notifications) == 1
            assert notifications[0]["params"]["uri"] == "config:///database"

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_client_reconnection_and_resubscription(
        self, running_server, temp_dir
    ):
        """Test client reconnection and automatic resubscription."""
        server_info = running_server

        # Create test file
        await self.create_test_file(temp_dir, "persistent.json", '{"persistent": true}')

        client = MCPTestClient(
            server_info["host"], server_info["port"], "reconnect_client"
        )

        # First connection
        await client.connect()
        subscription_id = await client.subscribe_to_resource("file:///persistent.json")
        assert subscription_id is not None

        # Disconnect
        await client.disconnect()

        # Reconnect
        await client.connect()

        # Resubscribe to the same resource
        new_subscription_id = await client.subscribe_to_resource(
            "file:///persistent.json"
        )
        assert new_subscription_id is not None
        assert new_subscription_id != subscription_id  # Should be a new subscription

        # Modify file and verify notification works after reconnection
        await self.create_test_file(
            temp_dir, "persistent.json", '{"persistent": true, "reconnected": true}'
        )

        server = server_info["server"]
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///persistent.json",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change)

        # Should receive notification on new connection
        notifications = await client.listen_for_notifications(timeout=1.0)
        assert len(notifications) == 1
        assert notifications[0]["params"]["uri"] == "file:///persistent.json"

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_subscription_limit_and_cleanup(self, running_server, temp_dir):
        """Test subscription limits and proper cleanup."""
        server_info = running_server

        # Create multiple test files
        test_files = []
        for i in range(5):
            filename = f"test_{i}.json"
            await self.create_test_file(temp_dir, filename, f'{{"id": {i}}}')
            test_files.append(filename)

        client = MCPTestClient(server_info["host"], server_info["port"], "limit_client")

        try:
            await client.connect()

            # Create multiple subscriptions
            subscription_ids = []
            for filename in test_files:
                sub_id = await client.subscribe_to_resource(f"file:///{filename}")
                subscription_ids.append(sub_id)

            assert len(subscription_ids) == 5
            assert len(set(subscription_ids)) == 5  # All unique

            # Verify all subscriptions are active
            server = server_info["server"]
            for i, sub_id in enumerate(subscription_ids):
                subscription = server.subscription_manager.get_subscription(sub_id)
                assert subscription is not None
                assert subscription.uri_pattern == f"file:///test_{i}.json"

            # Unsubscribe from half of them
            for sub_id in subscription_ids[:3]:
                success = await client.unsubscribe_from_resource(sub_id)
                assert success is True

            # Verify cleanup
            for sub_id in subscription_ids[:3]:
                subscription = server.subscription_manager.get_subscription(sub_id)
                assert subscription is None

            # Verify remaining subscriptions still work
            for i in range(3, 5):
                filename = f"test_{i}.json"
                await self.create_test_file(
                    temp_dir, filename, f'{{"id": {i}, "updated": true}}'
                )

                change = ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri=f"file:///{filename}",
                    timestamp=datetime.utcnow(),
                )
                await server.subscription_manager.process_resource_change(change)

                notifications = await client.listen_for_notifications(timeout=1.0)
                assert len(notifications) == 1
                assert notifications[0]["params"]["uri"] == f"file:///{filename}"

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_resource_creation_and_deletion_notifications(
        self, running_server, temp_dir
    ):
        """Test notifications for resource creation and deletion."""
        server_info = running_server

        client = MCPTestClient(
            server_info["host"], server_info["port"], "lifecycle_client"
        )

        try:
            await client.connect()

            # Subscribe to a file that doesn't exist yet
            subscription_id = await client.subscribe_to_resource(
                "file:///lifecycle.json"
            )

            server = server_info["server"]

            # Simulate file creation
            await self.create_test_file(temp_dir, "lifecycle.json", '{"created": true}')

            create_change = ResourceChange(
                type=ResourceChangeType.CREATED,
                uri="file:///lifecycle.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(create_change)

            # Should receive creation notification
            notifications = await client.listen_for_notifications(timeout=1.0)
            assert len(notifications) == 1
            assert notifications[0]["method"] == "notifications/resources/updated"
            assert notifications[0]["params"]["uri"] == "file:///lifecycle.json"
            assert notifications[0]["params"]["type"] == "created"

            # Simulate file deletion
            (temp_dir / "lifecycle.json").unlink()

            delete_change = ResourceChange(
                type=ResourceChangeType.DELETED,
                uri="file:///lifecycle.json",
                timestamp=datetime.utcnow(),
            )
            await server.subscription_manager.process_resource_change(delete_change)

            # Should receive deletion notification
            notifications = await client.listen_for_notifications(timeout=1.0)
            assert len(notifications) == 1
            assert notifications[0]["params"]["uri"] == "file:///lifecycle.json"
            assert notifications[0]["params"]["type"] == "deleted"

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_high_frequency_changes(self, running_server, temp_dir):
        """Test handling of high-frequency resource changes."""
        server_info = running_server

        # Create test file
        await self.create_test_file(temp_dir, "highfreq.json", '{"counter": 0}')

        client = MCPTestClient(
            server_info["host"], server_info["port"], "highfreq_client"
        )

        try:
            await client.connect()

            # Subscribe to the file
            subscription_id = await client.subscribe_to_resource(
                "file:///highfreq.json"
            )

            server = server_info["server"]

            # Generate rapid file changes
            num_changes = 10
            for i in range(1, num_changes + 1):
                await self.create_test_file(
                    temp_dir, "highfreq.json", f'{{"counter": {i}}}'
                )

                change = ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri="file:///highfreq.json",
                    timestamp=datetime.utcnow(),
                )
                await server.subscription_manager.process_resource_change(change)

                # Small delay to prevent overwhelming
                await asyncio.sleep(0.1)

            # Collect all notifications
            all_notifications = []
            timeout_count = 0
            while timeout_count < 3:  # Allow up to 3 consecutive timeouts
                notifications = await client.listen_for_notifications(timeout=0.5)
                if notifications:
                    all_notifications.extend(notifications)
                    timeout_count = 0
                else:
                    timeout_count += 1

            # Should receive multiple notifications
            assert len(all_notifications) >= 5  # At least half of the changes

            # All notifications should be for the same file
            for notification in all_notifications:
                assert notification["params"]["uri"] == "file:///highfreq.json"
                assert notification["params"]["type"] == "updated"

        finally:
            await client.disconnect()
