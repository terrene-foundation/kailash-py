"""Integration tests for GraphQL-style field selection in MCP resource subscriptions."""

import asyncio
from datetime import datetime
from typing import Any, Dict

import pytest
import pytest_asyncio
from kailash.mcp_server.auth import AuthManager
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import (
    ResourceChange,
    ResourceChangeType,
    ResourceSubscriptionManager,
)
from kailash.middleware.gateway.event_store import EventStore

from tests.integration.docker_test_base import DockerIntegrationTestBase


class TestGraphQLFieldSelectionIntegration(DockerIntegrationTestBase):
    """Integration tests for GraphQL field selection with real infrastructure."""

    @pytest_asyncio.fixture
    async def subscription_manager(self, postgres_conn):
        """Create subscription manager with real event store."""
        event_store = EventStore(postgres_conn)

        manager = ResourceSubscriptionManager(event_store=event_store)

        await manager.initialize()

        yield manager

        await manager.shutdown()

    @pytest_asyncio.fixture
    async def mcp_server(self, postgres_conn):
        """Create MCP server with real infrastructure."""
        event_store = EventStore(postgres_conn)

        server = MCPServer(
            "integration_test_server",
            event_store=event_store,
            enable_subscriptions=True,
        )

        # Initialize subscription manager manually
        server.subscription_manager = ResourceSubscriptionManager(
            event_store=event_store
        )
        await server.subscription_manager.initialize()

        yield server

        if server.subscription_manager:
            await server.subscription_manager.shutdown()

    @pytest.mark.asyncio
    async def test_field_selection_with_real_event_store(self, subscription_manager):
        """Test field selection with real event store logging."""
        # Create subscription with field selection
        subscription_id = await subscription_manager.create_subscription(
            connection_id="integration_conn_123",
            uri_pattern="file:///test/*.json",
            fields=["uri", "content.text", "metadata.size"],
        )

        assert subscription_id is not None

        # Verify subscription was created
        subscription = subscription_manager.get_subscription(subscription_id)
        assert subscription is not None
        assert subscription.fields == ["uri", "content.text", "metadata.size"]
        assert subscription.connection_id == "integration_conn_123"

    @pytest.mark.asyncio
    async def test_fragment_selection_with_real_event_store(self, subscription_manager):
        """Test fragment selection with real event store logging."""
        fragments = {
            "basicInfo": ["uri", "name"],
            "contentInfo": ["content.text", "content.type"],
            "metadata": ["metadata.size", "metadata.modified"],
        }

        # Create subscription with fragments
        subscription_id = await subscription_manager.create_subscription(
            connection_id="integration_conn_456",
            uri_pattern="config:///*",
            fragments=fragments,
        )

        assert subscription_id is not None

        # Verify subscription was created with fragments
        subscription = subscription_manager.get_subscription(subscription_id)
        assert subscription is not None
        assert subscription.fragments == fragments
        assert subscription.connection_id == "integration_conn_456"

    @pytest.mark.asyncio
    async def test_resource_change_processing_with_field_selection(
        self, subscription_manager
    ):
        """Test processing resource changes with field selection applied."""
        # Track notifications
        notifications = []

        async def notification_handler(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(notification_handler)

        # Create subscription with specific field selection
        subscription_id = await subscription_manager.create_subscription(
            connection_id="integration_conn_789",
            uri_pattern="file:///integration_test.json",
            fields=["uri", "content.text"],
        )

        # Mock the resource data method to return comprehensive data
        async def mock_get_resource_data(uri: str) -> Dict[str, Any]:
            return {
                "uri": uri,
                "name": "integration_test.json",
                "content": {
                    "text": "Integration test content",
                    "type": "json",
                    "encoding": "utf-8",
                },
                "metadata": {
                    "size": 2048,
                    "modified": "2024-01-15T10:30:00Z",
                    "created": "2024-01-01T00:00:00Z",
                    "hash": "abc123def456",
                },
            }

        subscription_manager._get_resource_data = mock_get_resource_data

        # Create and process a resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///integration_test.json",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify notification was sent with filtered data
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        assert connection_id == "integration_conn_789"
        assert notification["method"] == "notifications/resources/updated"
        assert notification["params"]["uri"] == "file:///integration_test.json"
        assert notification["params"]["type"] == "updated"

        # Verify field selection was applied
        filtered_data = notification["params"]["data"]
        expected_data = {
            "uri": "file:///integration_test.json",
            "content": {"text": "Integration test content"},
        }

        assert filtered_data == expected_data

        # Verify that filtered data doesn't contain excluded fields
        assert "name" not in filtered_data
        assert "metadata" not in filtered_data
        assert "content" in filtered_data
        assert "type" not in filtered_data["content"]
        assert "encoding" not in filtered_data["content"]

    @pytest.mark.asyncio
    async def test_fragment_processing_with_resource_changes(
        self, subscription_manager
    ):
        """Test processing resource changes with fragment selection."""
        # Track notifications
        notifications = []

        async def notification_handler(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(notification_handler)

        # Create subscription with fragments
        fragments = {"basicInfo": ["uri", "name"], "sizeData": ["metadata.size"]}

        subscription_id = await subscription_manager.create_subscription(
            connection_id="integration_conn_fragment",
            uri_pattern="config:///database",
            fragments=fragments,
        )

        # Mock comprehensive resource data
        async def mock_get_resource_data(uri: str) -> Dict[str, Any]:
            return {
                "uri": uri,
                "name": "database_config",
                "content": {"host": "localhost", "port": 5432, "database": "myapp"},
                "metadata": {
                    "size": 512,
                    "modified": "2024-01-15T10:30:00Z",
                    "format": "json",
                },
            }

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="config:///database",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Verify notification with fragment selection
        assert len(notifications) == 1
        connection_id, notification = notifications[0]

        assert connection_id == "integration_conn_fragment"

        # Check fragment structure
        filtered_data = notification["params"]["data"]
        expected_data = {
            "__basicInfo": {"uri": "config:///database", "name": "database_config"},
            "__sizeData": {"metadata": {"size": 512}},
        }

        assert filtered_data == expected_data

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_different_field_selections(
        self, subscription_manager
    ):
        """Test multiple subscriptions with different field selections on same resource."""
        # Track notifications
        notifications = []

        async def notification_handler(
            connection_id: str, notification: Dict[str, Any]
        ):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(notification_handler)

        # Create multiple subscriptions with different field selections
        sub1_id = await subscription_manager.create_subscription(
            connection_id="conn_fields",
            uri_pattern="file:///shared.json",
            fields=["uri", "content.text"],
        )

        sub2_id = await subscription_manager.create_subscription(
            connection_id="conn_fragments",
            uri_pattern="file:///shared.json",
            fragments={"metadata": ["metadata.size", "metadata.modified"]},
        )

        sub3_id = await subscription_manager.create_subscription(
            connection_id="conn_all",
            uri_pattern="file:///shared.json",
            # No field selection - should get all data
        )

        # Mock resource data
        full_resource_data = {
            "uri": "file:///shared.json",
            "name": "shared_file",
            "content": {"text": "Shared content", "type": "json"},
            "metadata": {
                "size": 1024,
                "modified": "2024-01-15T12:00:00Z",
                "created": "2024-01-01T00:00:00Z",
            },
        }

        async def mock_get_resource_data(uri: str) -> Dict[str, Any]:
            return full_resource_data

        subscription_manager._get_resource_data = mock_get_resource_data

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///shared.json",
            timestamp=datetime.utcnow(),
        )

        await subscription_manager.process_resource_change(change)

        # Should have 3 notifications with different filtered data
        assert len(notifications) == 3

        # Sort notifications by connection_id for consistent testing
        notifications.sort(key=lambda x: x[0])

        # Check first subscription (fields selection)
        conn_id, notification = notifications[0]  # conn_all
        assert conn_id == "conn_all"
        assert notification["params"]["data"] == full_resource_data  # No filtering

        # Check second subscription (fields selection)
        conn_id, notification = notifications[1]  # conn_fields
        assert conn_id == "conn_fields"
        expected_fields_data = {
            "uri": "file:///shared.json",
            "content": {"text": "Shared content"},
        }
        assert notification["params"]["data"] == expected_fields_data

        # Check third subscription (fragment selection)
        conn_id, notification = notifications[2]  # conn_fragments
        assert conn_id == "conn_fragments"
        expected_fragments_data = {
            "__metadata": {
                "metadata": {"size": 1024, "modified": "2024-01-15T12:00:00Z"}
            }
        }
        assert notification["params"]["data"] == expected_fragments_data

    @pytest.mark.asyncio
    async def test_server_subscribe_handler_integration(self, mcp_server):
        """Test server's subscribe handler with field selection integration."""
        # Test subscribing with field selection
        subscribe_params = {
            "uri": "file:///integration/*.json",
            "fields": ["uri", "content.text"],
            "fragments": {"basicInfo": ["uri", "name"]},
        }

        result = await mcp_server._handle_subscribe(
            subscribe_params, "integration_req_123", "integration_client_123"
        )

        # Verify successful subscription
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "integration_req_123"
        assert "result" in result
        assert "subscriptionId" in result["result"]

        subscription_id = result["result"]["subscriptionId"]

        # Verify subscription was created with correct field selection
        subscription = mcp_server.subscription_manager.get_subscription(subscription_id)
        assert subscription is not None
        assert subscription.fields == ["uri", "content.text"]
        assert subscription.fragments == {"basicInfo": ["uri", "name"]}
        assert subscription.uri_pattern == "file:///integration/*.json"
        assert subscription.connection_id == "integration_client_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
