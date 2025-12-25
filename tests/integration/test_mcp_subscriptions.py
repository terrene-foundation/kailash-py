"""Integration tests for MCP server resource subscriptions with real infrastructure."""

import asyncio
import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.mcp_server.subscriptions import ResourceSubscriptionManager
from kailash.middleware.communication.realtime import ConnectionManager, SSEManager
from kailash.middleware.gateway.event_store import EventStore

from tests.utils.docker_manager import DockerTestManager
from tests.utils.test_helpers import wait_for_condition


@pytest.fixture(scope="module")
def docker_manager():
    """Create Docker test manager for real services."""
    manager = DockerTestManager()
    manager.start_services(["redis", "postgres"])
    yield manager
    manager.stop_services()


@pytest.fixture
async def redis_client(docker_manager):
    """Create Redis client for tests."""
    import redis.asyncio as redis

    client = await redis.from_url(
        docker_manager.get_service_url("redis"), decode_responses=True
    )
    yield client
    await client.close()


@pytest.fixture
async def event_store(redis_client):
    """Create real event store."""
    store = EventStore(redis_client=redis_client)
    await store.initialize()
    yield store
    await store.cleanup()


@pytest.fixture
def temp_resources():
    """Create temporary resource directory."""
    temp_dir = tempfile.mkdtemp()

    # Create test resources
    (Path(temp_dir) / "data.json").write_text('{"value": 1}')
    (Path(temp_dir) / "config.yaml").write_text("key: value")
    (Path(temp_dir) / "docs" / "readme.md").parent.mkdir(parents=True)
    (Path(temp_dir) / "docs" / "readme.md").write_text("# Test")

    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
async def mcp_server(event_store, temp_resources):
    """Create MCP server with subscription support."""
    auth = APIKeyAuth(keys={"test-key": {"permissions": ["read", "subscribe"]}})

    server = MCPServer(
        name="test-subscription-server",
        auth_provider=auth,
        enable_subscriptions=True,
        event_store=event_store,
    )

    # Register test resources
    @server.resource(f"file://{temp_resources}/data.json")
    async def data_resource():
        content = (Path(temp_resources) / "data.json").read_text()
        return {
            "uri": f"file://{temp_resources}/data.json",
            "mimeType": "application/json",
            "text": content,
        }

    @server.resource(f"file://{temp_resources}/config.yaml")
    async def config_resource():
        content = (Path(temp_resources) / "config.yaml").read_text()
        return {
            "uri": f"file://{temp_resources}/config.yaml",
            "mimeType": "application/yaml",
            "text": content,
        }

    @server.resource(f"file://{temp_resources}/docs/readme.md")
    async def readme_resource():
        content = (Path(temp_resources) / "docs" / "readme.md").read_text()
        return {
            "uri": f"file://{temp_resources}/docs/readme.md",
            "mimeType": "text/markdown",
            "text": content,
        }

    await server.initialize()
    yield server
    await server.shutdown()


class TestMCPSubscriptionIntegration:
    """Test MCP subscription functionality with real components."""

    @pytest.mark.asyncio
    async def test_server_declares_subscription_capability(self, mcp_server):
        """Test that server declares subscription capabilities."""
        # Simulate initialization request
        response = await mcp_server._handle_initialize({}, "req-1")

        assert "capabilities" in response
        assert "resources" in response["capabilities"]
        assert response["capabilities"]["resources"]["subscribe"] is True
        assert response["capabilities"]["resources"]["listChanged"] is True

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_flow(self, mcp_server):
        """Test complete subscription lifecycle."""
        connection_id = "test-conn-1"

        # Subscribe to JSON files
        subscribe_response = await mcp_server._handle_subscribe(
            {"uri": f"file://{mcp_server.temp_resources}/*.json", "cursor": None},
            "req-2",
            connection_id=connection_id,
            auth_context={"permissions": ["subscribe"]},
        )

        assert "subscriptionId" in subscribe_response
        sub_id = subscribe_response["subscriptionId"]

        # Verify subscription exists
        subscription = mcp_server.subscription_manager.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.connection_id == connection_id

        # Unsubscribe
        unsubscribe_response = await mcp_server._handle_unsubscribe(
            {"subscriptionId": sub_id}, "req-3", connection_id=connection_id
        )

        assert unsubscribe_response["success"] is True

        # Verify subscription removed
        assert mcp_server.subscription_manager.get_subscription(sub_id) is None

    @pytest.mark.asyncio
    async def test_resource_change_notifications(self, mcp_server, temp_resources):
        """Test that resource changes trigger notifications."""
        connection_id = "test-conn-2"
        notifications = []

        # Set up notification capture
        async def capture_notification(conn_id, message):
            if conn_id == connection_id:
                notifications.append(message)

        mcp_server.subscription_manager.set_notification_callback(capture_notification)

        # Subscribe to all JSON files
        subscribe_response = await mcp_server._handle_subscribe(
            {"uri": f"file://{temp_resources}/*.json"},
            "req-4",
            connection_id=connection_id,
            auth_context={"permissions": ["subscribe"]},
        )

        # Modify a resource
        data_path = Path(temp_resources) / "data.json"
        original_content = data_path.read_text()
        data_path.write_text('{"value": 2}')

        # Trigger resource read to detect change
        await mcp_server._handle_read_resource(
            {"uri": f"file://{temp_resources}/data.json"}, "req-5"
        )

        # Wait for notification
        await wait_for_condition(lambda: len(notifications) > 0, timeout=2)

        # Verify notification
        assert len(notifications) == 1
        assert notifications[0]["method"] == "notifications/resources/updated"
        assert notifications[0]["params"]["uri"] == f"file://{temp_resources}/data.json"
        assert notifications[0]["params"]["type"] == "updated"

        # Restore original content
        data_path.write_text(original_content)

    @pytest.mark.asyncio
    async def test_cursor_based_pagination(self, mcp_server, temp_resources):
        """Test cursor-based pagination for resource listing."""
        # List resources with limit
        response1 = await mcp_server._handle_list_resources(
            {"cursor": None, "limit": 2}, "req-6"
        )

        assert len(response1["resources"]) == 2
        assert "nextCursor" in response1
        assert response1["nextCursor"] is not None

        # Get next page
        response2 = await mcp_server._handle_list_resources(
            {"cursor": response1["nextCursor"], "limit": 2}, "req-7"
        )

        assert len(response2["resources"]) >= 1

        # Verify no duplicate resources
        uris1 = {r["uri"] for r in response1["resources"]}
        uris2 = {r["uri"] for r in response2["resources"]}
        assert len(uris1.intersection(uris2)) == 0

    @pytest.mark.asyncio
    async def test_connection_cleanup(self, mcp_server):
        """Test that subscriptions are cleaned up on disconnect."""
        connection_id = "test-conn-3"

        # Create multiple subscriptions
        sub_ids = []
        for pattern in ["*.json", "*.yaml", "*.md"]:
            response = await mcp_server._handle_subscribe(
                {"uri": f"file://{mcp_server.temp_resources}/{pattern}"},
                f"req-{pattern}",
                connection_id=connection_id,
                auth_context={"permissions": ["subscribe"]},
            )
            sub_ids.append(response["subscriptionId"])

        # Verify subscriptions exist
        subs = mcp_server.subscription_manager.get_connection_subscriptions(
            connection_id
        )
        assert len(subs) == 3

        # Simulate disconnect
        await mcp_server._handle_connection_close(connection_id)

        # Verify all subscriptions removed
        subs = mcp_server.subscription_manager.get_connection_subscriptions(
            connection_id
        )
        assert len(subs) == 0

        # Verify individual subscriptions gone
        for sub_id in sub_ids:
            assert mcp_server.subscription_manager.get_subscription(sub_id) is None

    @pytest.mark.asyncio
    async def test_subscription_permission_enforcement(self, mcp_server):
        """Test that subscription permissions are enforced."""
        connection_id = "test-conn-4"

        # Try to subscribe without permission
        with pytest.raises(PermissionError):
            await mcp_server._handle_subscribe(
                {"uri": "file:///*.json"},
                "req-8",
                connection_id=connection_id,
                auth_context={"permissions": ["read"]},  # No 'subscribe' permission
            )

    @pytest.mark.asyncio
    async def test_event_store_persistence(self, mcp_server, event_store):
        """Test that resource changes are persisted in event store."""
        # Subscribe to track changes
        connection_id = "test-conn-5"
        await mcp_server._handle_subscribe(
            {"uri": "file:///*.json"},
            "req-9",
            connection_id=connection_id,
            auth_context={"permissions": ["subscribe"]},
        )

        # Trigger a change
        change_time = datetime.utcnow()
        await mcp_server.subscription_manager.process_resource_change(
            {
                "type": "updated",
                "uri": "file:///test.json",
                "timestamp": change_time.isoformat(),
            }
        )

        # Query event store
        events = []
        async for event in event_store.stream_events(
            stream_name="resource_changes", start_time=change_time
        ):
            events.append(event)

        # Verify event stored
        assert len(events) >= 1
        assert events[0]["type"] == "resource.changed"
        assert events[0]["data"]["uri"] == "file:///test.json"

    @pytest.mark.asyncio
    async def test_websocket_notification_delivery(self, mcp_server):
        """Test WebSocket delivery of notifications."""
        # Create WebSocket connection manager
        ws_manager = ConnectionManager()
        mcp_server.subscription_manager.set_notification_callback(
            ws_manager.send_to_connection
        )

        # Simulate WebSocket connection
        connection_id = "ws-conn-1"
        mock_websocket = AsyncMock()
        await ws_manager.connect(connection_id, mock_websocket)

        # Subscribe
        await mcp_server._handle_subscribe(
            {"uri": "file:///*.json"},
            "req-10",
            connection_id=connection_id,
            auth_context={"permissions": ["subscribe"]},
        )

        # Trigger notification
        await mcp_server.subscription_manager.process_resource_change(
            {
                "type": "created",
                "uri": "file:///new.json",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Verify WebSocket received message
        await asyncio.sleep(0.1)  # Allow async delivery
        mock_websocket.send_json.assert_called_once()

        message = mock_websocket.send_json.call_args[0][0]
        assert message["method"] == "notifications/resources/updated"
        assert message["params"]["uri"] == "file:///new.json"

    @pytest.mark.asyncio
    async def test_subscription_pattern_matching(self, mcp_server, temp_resources):
        """Test various subscription patterns."""
        patterns_and_matches = [
            ("file://**/*.json", ["data.json"]),
            ("file://**/docs/*.md", ["docs/readme.md"]),
            ("file://**/*", ["data.json", "config.yaml", "docs/readme.md"]),
        ]

        for pattern, expected_files in patterns_and_matches:
            connection_id = f"conn-pattern-{pattern}"
            notifications = []

            # Capture notifications
            async def capture(conn_id, msg):
                if conn_id == connection_id:
                    notifications.append(msg)

            mcp_server.subscription_manager.set_notification_callback(capture)

            # Subscribe
            await mcp_server._handle_subscribe(
                {"uri": pattern},
                f"req-{pattern}",
                connection_id=connection_id,
                auth_context={"permissions": ["subscribe"]},
            )

            # Trigger changes for all resources
            for filename in ["data.json", "config.yaml", "docs/readme.md"]:
                await mcp_server.subscription_manager.process_resource_change(
                    {
                        "type": "updated",
                        "uri": f"file://{temp_resources}/{filename}",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            # Verify only expected files triggered notifications
            await asyncio.sleep(0.1)
            notified_files = [
                n["params"]["uri"].replace(f"file://{temp_resources}/", "")
                for n in notifications
            ]

            assert set(notified_files) == set(expected_files)

    @pytest.mark.asyncio
    async def test_concurrent_subscriptions(self, mcp_server):
        """Test handling many concurrent subscriptions."""
        num_connections = 50
        subscriptions_per_connection = 5

        async def create_connection_subs(conn_num):
            connection_id = f"conn-{conn_num}"
            sub_ids = []

            for i in range(subscriptions_per_connection):
                response = await mcp_server._handle_subscribe(
                    {"uri": f"file:///{conn_num}/{i}/*.json"},
                    f"req-{conn_num}-{i}",
                    connection_id=connection_id,
                    auth_context={"permissions": ["subscribe"]},
                )
                sub_ids.append(response["subscriptionId"])

            return connection_id, sub_ids

        # Create many subscriptions concurrently
        tasks = [create_connection_subs(i) for i in range(num_connections)]
        results = await asyncio.gather(*tasks)

        # Verify all created
        total_subs = sum(len(subs) for _, subs in results)
        assert total_subs == num_connections * subscriptions_per_connection

        # Test concurrent cleanup
        cleanup_tasks = [
            mcp_server._handle_connection_close(conn_id)
            for conn_id, _ in results[::2]  # Every other connection
        ]
        await asyncio.gather(*cleanup_tasks)

        # Verify half cleaned up
        remaining = 0
        for conn_id, _ in results:
            subs = mcp_server.subscription_manager.get_connection_subscriptions(conn_id)
            remaining += len(subs)

        assert remaining == (num_connections // 2) * subscriptions_per_connection
