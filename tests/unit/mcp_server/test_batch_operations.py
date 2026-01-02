"""Unit tests for batch subscribe/unsubscribe operations in MCP resource subscriptions."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import ResourceSubscriptionManager


class TestBatchSubscriptions:
    """Test batch subscription operations."""

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

    @pytest.mark.asyncio
    async def test_create_batch_subscriptions_success(self, subscription_manager):
        """Test successful batch subscription creation."""
        subscriptions = [
            {
                "uri_pattern": "file:///*.json",
                "fields": ["uri", "content"],
                "subscription_name": "json_files",
            },
            {
                "uri_pattern": "config:///database",
                "fragments": {"dbInfo": ["host", "port"]},
                "subscription_name": "db_config",
            },
            {"uri_pattern": "file:///logs/*.log", "cursor": "cursor_123"},
        ]

        result = await subscription_manager.create_batch_subscriptions(
            subscriptions=subscriptions, connection_id="conn_123"
        )

        # Verify results
        assert result["total_requested"] == 3
        assert result["total_created"] == 3
        assert result["total_failed"] == 0
        assert len(result["successful"]) == 3
        assert len(result["failed"]) == 0

        # Check successful subscriptions
        for i, success in enumerate(result["successful"]):
            assert success["index"] == i
            assert "subscription_id" in success
            assert success["uri_pattern"] == subscriptions[i]["uri_pattern"]
            if "subscription_name" in subscriptions[i]:
                assert (
                    success["subscription_name"]
                    == subscriptions[i]["subscription_name"]
                )

        # Verify subscriptions were actually created
        assert len(subscription_manager._subscriptions) == 3
        assert len(subscription_manager._connection_subscriptions["conn_123"]) == 3

    @pytest.mark.asyncio
    async def test_create_batch_subscriptions_partial_failure(
        self, subscription_manager
    ):
        """Test batch subscription creation with some failures."""
        subscriptions = [
            {"uri_pattern": "file:///*.json", "fields": ["uri", "content"]},
            {
                # Missing uri_pattern - should fail
                "fields": ["uri", "name"]
            },
            {
                "uri_pattern": "config:///settings",
                "fragments": {"basic": ["name", "value"]},
            },
        ]

        result = await subscription_manager.create_batch_subscriptions(
            subscriptions=subscriptions, connection_id="conn_123"
        )

        # Verify results
        assert result["total_requested"] == 3
        assert result["total_created"] == 2
        assert result["total_failed"] == 1
        assert len(result["successful"]) == 2
        assert len(result["failed"]) == 1

        # Check failed subscription
        failed = result["failed"][0]
        assert failed["index"] == 1
        assert "Missing required parameter: uri_pattern" in failed["error"]

        # Check successful subscriptions - adjust for actual behavior
        successful_indices = [s["index"] for s in result["successful"]]
        assert 0 in successful_indices
        assert 2 in successful_indices

    @pytest.mark.asyncio
    async def test_create_batch_subscriptions_empty_list(self, subscription_manager):
        """Test batch subscription creation with empty list."""
        result = await subscription_manager.create_batch_subscriptions(
            subscriptions=[], connection_id="conn_123"
        )

        assert result["total_requested"] == 0
        assert result["total_created"] == 0
        assert result["total_failed"] == 0
        assert len(result["successful"]) == 0
        assert len(result["failed"]) == 0

    @pytest.mark.asyncio
    async def test_create_batch_subscriptions_with_auth_error(
        self, subscription_manager
    ):
        """Test batch subscription creation with authorization errors."""
        # Mock auth manager to reject certain patterns
        mock_auth = MagicMock()
        subscription_manager.auth_manager = mock_auth

        async def mock_authenticate_and_authorize(user_context, required_permission):
            # Reject patterns containing "secret"
            if "secret" in user_context.get("current_pattern", ""):
                raise Exception("Access denied to secret resources")

        mock_auth.authenticate_and_authorize = mock_authenticate_and_authorize

        subscriptions = [
            {"uri_pattern": "file:///public/*.json"},
            {"uri_pattern": "file:///secret/*.json"},  # Should fail auth
            {"uri_pattern": "config:///settings"},
        ]

        # Need to patch create_subscription to pass the pattern in context
        original_create = subscription_manager.create_subscription

        async def patched_create_subscription(
            connection_id, uri_pattern, user_context=None, **kwargs
        ):
            if user_context:
                user_context["current_pattern"] = uri_pattern
            return await original_create(
                connection_id, uri_pattern, user_context, **kwargs
            )

        subscription_manager.create_subscription = patched_create_subscription

        result = await subscription_manager.create_batch_subscriptions(
            subscriptions=subscriptions,
            connection_id="conn_123",
            user_context={"user_id": "user_123"},
        )

        # Should have one failure (the secret pattern)
        assert result["total_requested"] == 3
        assert result["total_created"] == 2
        assert result["total_failed"] == 1

        # Check that the failed one is the secret pattern
        failed = result["failed"][0]
        assert failed["index"] == 1
        assert (
            "Access denied" in failed["error"]
            or "Not authorized to subscribe to resources" in failed["error"]
        )

    @pytest.mark.asyncio
    async def test_create_batch_subscriptions_with_event_store(
        self, subscription_manager
    ):
        """Test batch subscription creation logs to event store."""
        # Mock event store
        mock_event_store = MagicMock()
        mock_event_store.append = AsyncMock()
        subscription_manager.event_store = mock_event_store

        subscriptions = [
            {"uri_pattern": "file:///*.json"},
            {"uri_pattern": "config:///database"},
        ]

        result = await subscription_manager.create_batch_subscriptions(
            subscriptions=subscriptions,
            connection_id="conn_123",
            user_context={"user_id": "user_123"},
        )

        # Verify event was logged - batch operations log individual subscriptions + batch event
        assert mock_event_store.append.call_count >= 1

        # Find the batch subscription event
        batch_calls = [
            call
            for call in mock_event_store.append.call_args_list
            if call[1]["data"]["type"] == "batch_subscription_created"
        ]

        assert len(batch_calls) == 1
        call_kwargs = batch_calls[0][1]
        assert call_kwargs["data"]["connection_id"] == "conn_123"
        assert call_kwargs["data"]["total_requested"] == 2
        assert call_kwargs["data"]["total_created"] == 2
        assert call_kwargs["data"]["user_id"] == "user_123"


class TestBatchUnsubscriptions:
    """Test batch unsubscription operations."""

    @pytest.fixture
    def subscription_manager(self):
        """Create subscription manager for testing."""
        return ResourceSubscriptionManager()

    @pytest.mark.asyncio
    async def test_remove_batch_subscriptions_success(self, subscription_manager):
        """Test successful batch subscription removal."""
        # First create some subscriptions
        sub_id1 = await subscription_manager.create_subscription(
            "conn_123", "file:///*.json"
        )
        sub_id2 = await subscription_manager.create_subscription(
            "conn_123", "config:///database"
        )
        sub_id3 = await subscription_manager.create_subscription(
            "conn_123", "file:///logs/*.log"
        )

        # Remove them in batch
        subscription_ids = [sub_id1, sub_id2, sub_id3]
        result = await subscription_manager.remove_batch_subscriptions(
            subscription_ids=subscription_ids, connection_id="conn_123"
        )

        # Verify results
        assert result["total_requested"] == 3
        assert result["total_removed"] == 3
        assert result["total_failed"] == 0
        assert len(result["successful"]) == 3
        assert len(result["failed"]) == 0

        # Check successful removals
        for i, success in enumerate(result["successful"]):
            assert success["index"] == i
            assert success["subscription_id"] == subscription_ids[i]
            assert success["removed"] is True

        # Verify subscriptions were actually removed
        assert len(subscription_manager._subscriptions) == 0
        assert "conn_123" not in subscription_manager._connection_subscriptions

    @pytest.mark.asyncio
    async def test_remove_batch_subscriptions_partial_failure(
        self, subscription_manager
    ):
        """Test batch subscription removal with some failures."""
        # Create some subscriptions
        sub_id1 = await subscription_manager.create_subscription(
            "conn_123", "file:///*.json"
        )
        sub_id2 = await subscription_manager.create_subscription(
            "conn_123", "config:///database"
        )

        # Try to remove valid and invalid subscription IDs
        subscription_ids = [sub_id1, "invalid_id", sub_id2]
        result = await subscription_manager.remove_batch_subscriptions(
            subscription_ids=subscription_ids, connection_id="conn_123"
        )

        # Verify results
        assert result["total_requested"] == 3
        assert result["total_removed"] == 2
        assert result["total_failed"] == 1
        assert len(result["successful"]) == 2
        assert len(result["failed"]) == 1

        # Check failed removal
        failed = result["failed"][0]
        assert failed["index"] == 1
        assert failed["subscription_id"] == "invalid_id"
        assert "not found" in failed["error"].lower()

        # Check successful removals
        assert result["successful"][0]["subscription_id"] == sub_id1
        assert result["successful"][1]["subscription_id"] == sub_id2

    @pytest.mark.asyncio
    async def test_remove_batch_subscriptions_wrong_connection(
        self, subscription_manager
    ):
        """Test batch subscription removal with wrong connection ID."""
        # Create subscriptions for one connection
        sub_id1 = await subscription_manager.create_subscription(
            "conn_123", "file:///*.json"
        )
        sub_id2 = await subscription_manager.create_subscription(
            "conn_123", "config:///database"
        )

        # Try to remove them from different connection
        subscription_ids = [sub_id1, sub_id2]
        result = await subscription_manager.remove_batch_subscriptions(
            subscription_ids=subscription_ids,
            connection_id="conn_456",  # Different connection
        )

        # Should fail because wrong connection
        assert result["total_requested"] == 2
        assert result["total_removed"] == 0
        assert result["total_failed"] == 2
        assert len(result["successful"]) == 0
        assert len(result["failed"]) == 2

        # Subscriptions should still exist
        assert len(subscription_manager._subscriptions) == 2

    @pytest.mark.asyncio
    async def test_remove_batch_subscriptions_empty_list(self, subscription_manager):
        """Test batch subscription removal with empty list."""
        result = await subscription_manager.remove_batch_subscriptions(
            subscription_ids=[], connection_id="conn_123"
        )

        assert result["total_requested"] == 0
        assert result["total_removed"] == 0
        assert result["total_failed"] == 0
        assert len(result["successful"]) == 0
        assert len(result["failed"]) == 0

    @pytest.mark.asyncio
    async def test_remove_batch_subscriptions_with_event_store(
        self, subscription_manager
    ):
        """Test batch subscription removal logs to event store."""
        # Mock event store
        mock_event_store = MagicMock()
        mock_event_store.append = AsyncMock()
        subscription_manager.event_store = mock_event_store

        # Create and remove subscriptions
        sub_id1 = await subscription_manager.create_subscription(
            "conn_123", "file:///*.json"
        )
        sub_id2 = await subscription_manager.create_subscription(
            "conn_123", "config:///database"
        )

        subscription_ids = [sub_id1, sub_id2]
        result = await subscription_manager.remove_batch_subscriptions(
            subscription_ids=subscription_ids, connection_id="conn_123"
        )

        # Verify event was logged (should be called multiple times - for creation and removal)
        assert mock_event_store.append.call_count >= 1

        # Find the batch removal event
        batch_removal_calls = [
            call
            for call in mock_event_store.append.call_args_list
            if call[1]["data"]["type"] == "batch_subscription_removed"
        ]

        assert len(batch_removal_calls) == 1
        call_kwargs = batch_removal_calls[0][1]
        assert call_kwargs["data"]["connection_id"] == "conn_123"
        assert call_kwargs["data"]["total_requested"] == 2
        assert call_kwargs["data"]["total_removed"] == 2


class TestBatchOperationsServerHandlers:
    """Test batch operation server handlers."""

    @pytest.fixture
    def mock_server(self):
        """Create mock MCP server."""
        server = MCPServer("test_server")
        server.subscription_manager = ResourceSubscriptionManager()
        return server

    @pytest.mark.asyncio
    async def test_handle_batch_subscribe_success(self, mock_server):
        """Test server batch subscribe handler success."""
        params = {
            "subscriptions": [
                {"uri_pattern": "file:///*.json", "fields": ["uri", "content"]},
                {
                    "uri_pattern": "config:///database",
                    "fragments": {"info": ["host", "port"]},
                },
            ]
        }

        result = await mock_server._handle_batch_subscribe(
            params, "req_123", "client_123"
        )

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "req_123"
        assert "result" in result

        batch_result = result["result"]
        assert batch_result["total_requested"] == 2
        assert batch_result["total_created"] == 2
        assert batch_result["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_handle_batch_subscribe_no_subscriptions_param(self, mock_server):
        """Test server batch subscribe handler with missing subscriptions parameter."""
        params = {}  # No subscriptions parameter

        result = await mock_server._handle_batch_subscribe(
            params, "req_123", "client_123"
        )

        # Should return error
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "req_123"
        assert "error" in result
        assert result["error"]["code"] == -32602
        assert (
            "Missing or invalid parameter: subscriptions" in result["error"]["message"]
        )

    @pytest.mark.asyncio
    async def test_handle_batch_subscribe_invalid_subscriptions_param(
        self, mock_server
    ):
        """Test server batch subscribe handler with invalid subscriptions parameter."""
        params = {"subscriptions": "not_a_list"}  # Should be a list

        result = await mock_server._handle_batch_subscribe(
            params, "req_123", "client_123"
        )

        # Should return error
        assert result["jsonrpc"] == "2.0"
        assert "error" in result
        assert result["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_handle_batch_subscribe_subscriptions_disabled(self, mock_server):
        """Test server batch subscribe handler when subscriptions are disabled."""
        mock_server.subscription_manager = None  # Disable subscriptions

        params = {"subscriptions": [{"uri_pattern": "file:///*.json"}]}

        result = await mock_server._handle_batch_subscribe(
            params, "req_123", "client_123"
        )

        # Should return error
        assert result["jsonrpc"] == "2.0"
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Subscriptions not enabled" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_batch_unsubscribe_success(self, mock_server):
        """Test server batch unsubscribe handler success."""
        # First create subscriptions
        sub_id1 = await mock_server.subscription_manager.create_subscription(
            "client_123", "file:///*.json"
        )
        sub_id2 = await mock_server.subscription_manager.create_subscription(
            "client_123", "config:///database"
        )

        params = {"subscriptionIds": [sub_id1, sub_id2]}

        result = await mock_server._handle_batch_unsubscribe(
            params, "req_123", "client_123"
        )

        # Verify response
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "req_123"
        assert "result" in result

        batch_result = result["result"]
        assert batch_result["total_requested"] == 2
        assert batch_result["total_removed"] == 2
        assert batch_result["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_handle_batch_unsubscribe_no_subscription_ids_param(
        self, mock_server
    ):
        """Test server batch unsubscribe handler with missing subscriptionIds parameter."""
        params = {}  # No subscriptionIds parameter

        result = await mock_server._handle_batch_unsubscribe(
            params, "req_123", "client_123"
        )

        # Should return error
        assert result["jsonrpc"] == "2.0"
        assert "error" in result
        assert result["error"]["code"] == -32602
        assert (
            "Missing or invalid parameter: subscriptionIds"
            in result["error"]["message"]
        )

    @pytest.mark.asyncio
    async def test_handle_batch_unsubscribe_subscriptions_disabled(self, mock_server):
        """Test server batch unsubscribe handler when subscriptions are disabled."""
        mock_server.subscription_manager = None  # Disable subscriptions

        params = {"subscriptionIds": ["sub_123"]}

        result = await mock_server._handle_batch_unsubscribe(
            params, "req_123", "client_123"
        )

        # Should return error
        assert result["jsonrpc"] == "2.0"
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Subscriptions not enabled" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_server_capabilities_include_batch_operations(self, mock_server):
        """Test that server capabilities include batch operations."""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }

        result = await mock_server._handle_initialize(params, "init_123", "client_123")

        # Check capabilities
        assert result["jsonrpc"] == "2.0"
        assert "result" in result

        capabilities = result["result"]["capabilities"]
        resources_capabilities = capabilities["resources"]

        assert "batch_subscribe" in resources_capabilities
        assert "batch_unsubscribe" in resources_capabilities
        assert (
            resources_capabilities["batch_subscribe"]
            == mock_server.enable_subscriptions
        )
        assert (
            resources_capabilities["batch_unsubscribe"]
            == mock_server.enable_subscriptions
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
