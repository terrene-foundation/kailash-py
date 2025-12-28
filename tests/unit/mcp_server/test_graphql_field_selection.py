"""Unit tests for GraphQL-style field selection in MCP resource subscriptions."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from kailash.mcp_server.protocol import ResourceChange, ResourceChangeType
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import (
    ResourceSubscription,
    ResourceSubscriptionManager,
)


class TestGraphQLFieldSelection:
    """Test GraphQL-style field selection functionality."""

    @pytest.fixture
    def subscription_manager(self):
        """Create subscription manager for testing."""
        return ResourceSubscriptionManager()

    @pytest.fixture
    def mock_server(self):
        """Create mock MCP server."""
        server = MCPServer("test_server")
        server.subscription_manager = ResourceSubscriptionManager()
        return server

    def test_subscription_field_selection_initialization(self):
        """Test ResourceSubscription initialization with field selection."""
        # Test with fields only
        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri", "content.text", "metadata.size"],
        )

        assert subscription.fields == ["uri", "content.text", "metadata.size"]
        assert subscription.fragments is None

    def test_subscription_fragment_selection_initialization(self):
        """Test ResourceSubscription initialization with fragments."""
        fragments = {"basicInfo": ["uri", "name"], "metadata": ["size", "modified"]}

        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fragments=fragments,
        )

        assert subscription.fragments == fragments
        assert subscription.fields is None

    def test_extract_field_value_simple(self):
        """Test extracting simple field values."""
        subscription = ResourceSubscription(
            id="sub_123", connection_id="conn_123", uri_pattern="file:///*.json"
        )

        data = {"uri": "file:///document.json", "name": "document", "size": 1024}

        # Test simple field extraction
        assert subscription._extract_field_value(data, "uri") == "file:///document.json"
        assert subscription._extract_field_value(data, "name") == "document"
        assert subscription._extract_field_value(data, "size") == 1024
        assert subscription._extract_field_value(data, "nonexistent") is None

    def test_extract_field_value_nested(self):
        """Test extracting nested field values."""
        subscription = ResourceSubscription(
            id="sub_123", connection_id="conn_123", uri_pattern="file:///*.json"
        )

        data = {
            "uri": "file:///document.json",
            "content": {"text": "Hello world", "type": "plain"},
            "metadata": {"size": 1024, "modified": "2024-01-01T00:00:00Z"},
        }

        # Test nested field extraction
        assert subscription._extract_field_value(data, "content.text") == "Hello world"
        assert subscription._extract_field_value(data, "content.type") == "plain"
        assert subscription._extract_field_value(data, "metadata.size") == 1024
        assert (
            subscription._extract_field_value(data, "metadata.modified")
            == "2024-01-01T00:00:00Z"
        )
        assert subscription._extract_field_value(data, "content.nonexistent") is None

    def test_set_nested_value(self):
        """Test setting nested values in result data."""
        subscription = ResourceSubscription(
            id="sub_123", connection_id="conn_123", uri_pattern="file:///*.json"
        )

        result = {}

        # Test setting simple values
        subscription._set_nested_value(result, "uri", "file:///test.json")
        assert result["uri"] == "file:///test.json"

        # Test setting nested values
        subscription._set_nested_value(result, "content.text", "Hello")
        assert result["content"]["text"] == "Hello"

        subscription._set_nested_value(result, "content.type", "plain")
        assert result["content"]["type"] == "plain"

        subscription._set_nested_value(result, "metadata.size", 512)
        assert result["metadata"]["size"] == 512

    def test_apply_field_selection_with_fields(self):
        """Test applying field selection with direct fields."""
        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri", "content.text", "metadata.size"],
        )

        resource_data = {
            "uri": "file:///document.json",
            "name": "document",
            "content": {"text": "Hello world", "type": "plain", "encoding": "utf-8"},
            "metadata": {
                "size": 1024,
                "modified": "2024-01-01T00:00:00Z",
                "created": "2023-12-01T00:00:00Z",
            },
        }

        result = subscription.apply_field_selection(resource_data)

        # Should only include selected fields
        expected = {
            "uri": "file:///document.json",
            "content": {"text": "Hello world"},
            "metadata": {"size": 1024},
        }

        assert result == expected

    def test_apply_field_selection_with_fragments(self):
        """Test applying field selection with fragments."""
        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fragments={"basicInfo": ["uri", "name"], "sizeInfo": ["metadata.size"]},
        )

        resource_data = {
            "uri": "file:///document.json",
            "name": "document",
            "content": {"text": "Hello world", "type": "plain"},
            "metadata": {"size": 1024, "modified": "2024-01-01T00:00:00Z"},
        }

        result = subscription.apply_field_selection(resource_data)

        # Should include fragments with GraphQL-style naming
        expected = {
            "__basicInfo": {"uri": "file:///document.json", "name": "document"},
            "__sizeInfo": {"metadata": {"size": 1024}},
        }

        assert result == expected

    def test_apply_field_selection_mixed(self):
        """Test applying field selection with both fields and fragments."""
        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri"],
            fragments={"contentInfo": ["content.text", "content.type"]},
        )

        resource_data = {
            "uri": "file:///document.json",
            "name": "document",
            "content": {"text": "Hello world", "type": "plain", "encoding": "utf-8"},
            "metadata": {"size": 1024},
        }

        result = subscription.apply_field_selection(resource_data)

        # Should include both direct fields and fragments
        expected = {
            "uri": "file:///document.json",
            "__contentInfo": {"content": {"text": "Hello world", "type": "plain"}},
        }

        assert result == expected

    def test_apply_field_selection_no_selection(self):
        """Test that no field selection returns all data."""
        subscription = ResourceSubscription(
            id="sub_123", connection_id="conn_123", uri_pattern="file:///*.json"
        )

        resource_data = {
            "uri": "file:///document.json",
            "content": {"text": "Hello"},
            "metadata": {"size": 1024},
        }

        result = subscription.apply_field_selection(resource_data)

        # Should return all data unchanged
        assert result == resource_data

    def test_apply_field_selection_missing_fields(self):
        """Test field selection with missing fields."""
        subscription = ResourceSubscription(
            id="sub_123",
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri", "nonexistent.field", "content.missing"],
        )

        resource_data = {
            "uri": "file:///document.json",
            "content": {"text": "Hello world"},
        }

        result = subscription.apply_field_selection(resource_data)

        # Should only include fields that exist
        expected = {"uri": "file:///document.json"}

        assert result == expected

    @pytest.mark.asyncio
    async def test_create_subscription_with_fields(self, subscription_manager):
        """Test creating subscription with field selection."""
        subscription_id = await subscription_manager.create_subscription(
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri", "content.text"],
        )

        subscription = subscription_manager.get_subscription(subscription_id)
        assert subscription is not None
        assert subscription.fields == ["uri", "content.text"]
        assert subscription.fragments is None

    @pytest.mark.asyncio
    async def test_create_subscription_with_fragments(self, subscription_manager):
        """Test creating subscription with fragments."""
        fragments = {"basicInfo": ["uri", "name"], "metadata": ["size", "modified"]}

        subscription_id = await subscription_manager.create_subscription(
            connection_id="conn_123", uri_pattern="file:///*.json", fragments=fragments
        )

        subscription = subscription_manager.get_subscription(subscription_id)
        assert subscription is not None
        assert subscription.fragments == fragments
        assert subscription.fields is None

    @pytest.mark.asyncio
    async def test_process_resource_change_with_field_selection(
        self, subscription_manager
    ):
        """Test processing resource changes with field selection applied."""
        # Set up notification callback
        notifications = []

        async def capture_notification(connection_id, notification):
            notifications.append((connection_id, notification))

        subscription_manager.set_notification_callback(capture_notification)

        # Create subscription with field selection
        subscription_id = await subscription_manager.create_subscription(
            connection_id="conn_123",
            uri_pattern="file:///document.json",
            fields=["uri", "content.text"],
        )

        # Mock resource data
        subscription_manager._get_resource_data = AsyncMock(
            return_value={
                "uri": "file:///document.json",
                "name": "document",
                "content": {"text": "Hello world", "type": "plain"},
                "metadata": {"size": 1024, "modified": "2024-01-01T00:00:00Z"},
            }
        )

        # Process resource change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///document.json",
            timestamp=datetime.now(UTC),
        )

        await subscription_manager.process_resource_change(change)

        # Verify notification was sent with filtered data
        assert len(notifications) == 1
        connection_id, notification = notifications[0]
        assert connection_id == "conn_123"
        assert notification["method"] == "notifications/resources/updated"

        # Check that data was filtered
        filtered_data = notification["params"]["data"]
        expected_data = {
            "uri": "file:///document.json",
            "content": {"text": "Hello world"},
        }
        assert filtered_data == expected_data

    @pytest.mark.asyncio
    async def test_server_handle_subscribe_with_field_selection(self, mock_server):
        """Test server's subscribe handler with field selection."""
        params = {
            "uri": "file:///*.json",
            "fields": ["uri", "content.text"],
            "fragments": {"basicInfo": ["uri", "name"]},
        }

        # Mock create_subscription to capture parameters
        create_subscription_mock = AsyncMock(return_value="sub_123")
        mock_server.subscription_manager.create_subscription = create_subscription_mock

        result = await mock_server._handle_subscribe(params, "req_123", "client_123")

        # Verify subscription was created with field selection
        create_subscription_mock.assert_called_once_with(
            connection_id="client_123",
            uri_pattern="file:///*.json",
            cursor=None,
            user_context={"user_id": "client_123", "connection_id": "client_123"},
            fields=["uri", "content.text"],
            fragments={"basicInfo": ["uri", "name"]},
        )

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["result"]["subscriptionId"] == "sub_123"
        assert result["id"] == "req_123"

    @pytest.mark.asyncio
    async def test_server_handle_subscribe_without_field_selection(self, mock_server):
        """Test server's subscribe handler without field selection."""
        params = {"uri": "file:///*.json"}

        # Mock create_subscription to capture parameters
        create_subscription_mock = AsyncMock(return_value="sub_123")
        mock_server.subscription_manager.create_subscription = create_subscription_mock

        result = await mock_server._handle_subscribe(params, "req_123", "client_123")

        # Verify subscription was created without field selection
        create_subscription_mock.assert_called_once_with(
            connection_id="client_123",
            uri_pattern="file:///*.json",
            cursor=None,
            user_context={"user_id": "client_123", "connection_id": "client_123"},
            fields=None,
            fragments=None,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
