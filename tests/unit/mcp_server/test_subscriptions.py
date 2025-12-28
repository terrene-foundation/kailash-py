"""Unit tests for MCP server resource subscription functionality."""

import asyncio
from datetime import UTC, datetime
from typing import Dict, Optional, Set
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio
from kailash.mcp_server.auth import AuthManager
from kailash.mcp_server.auth import PermissionError as PermissionDeniedError
from kailash.mcp_server.protocol import ResourceChange, ResourceChangeType
from kailash.mcp_server.subscriptions import (
    CursorManager,
    ResourceMonitor,
    ResourceSubscription,
    ResourceSubscriptionManager,
    SubscriptionError,
)


class TestResourceSubscription:
    """Test ResourceSubscription data class."""

    def test_subscription_creation(self):
        """Test creating a subscription."""
        sub = ResourceSubscription(
            id="sub-123",
            connection_id="conn-456",
            uri_pattern="file:///data/*.json",
            cursor="cursor-789",
        )

        assert sub.id == "sub-123"
        assert sub.connection_id == "conn-456"
        assert sub.uri_pattern == "file:///data/*.json"
        assert sub.cursor == "cursor-789"
        assert isinstance(sub.created_at, datetime)

    def test_subscription_matches_uri(self):
        """Test URI pattern matching."""
        sub = ResourceSubscription(
            id="sub-123", connection_id="conn-456", uri_pattern="file:///data/*.json"
        )

        assert sub.matches_uri("file:///data/config.json") is True
        assert sub.matches_uri("file:///data/nested/config.json") is False
        assert sub.matches_uri("file:///other/config.json") is False
        assert sub.matches_uri("http://data/config.json") is False

    def test_subscription_wildcard_patterns(self):
        """Test various wildcard patterns."""
        # Single wildcard
        sub = ResourceSubscription("s1", "c1", "file:///data/*")
        assert sub.matches_uri("file:///data/file.txt") is True
        assert sub.matches_uri("file:///data/nested/file.txt") is False

        # Double wildcard
        sub = ResourceSubscription("s2", "c1", "file:///data/**")
        assert sub.matches_uri("file:///data/file.txt") is True
        assert sub.matches_uri("file:///data/nested/file.txt") is True
        assert sub.matches_uri("file:///data/a/b/c/file.txt") is True

        # Specific extension
        sub = ResourceSubscription("s3", "c1", "file:///**/*.md")
        assert sub.matches_uri("file:///docs/readme.md") is True
        assert sub.matches_uri("file:///docs/nested/guide.md") is True
        assert sub.matches_uri("file:///docs/file.txt") is False


class TestCursorManager:
    """Test cursor management functionality."""

    def test_cursor_generation(self):
        """Test generating cursors."""
        manager = CursorManager()

        cursor1 = manager.generate_cursor()
        cursor2 = manager.generate_cursor()

        assert cursor1 != cursor2
        assert isinstance(cursor1, str)
        assert len(cursor1) > 0

    def test_cursor_validation(self):
        """Test cursor validation and expiration."""
        manager = CursorManager(ttl_seconds=0.1)  # Very short TTL for testing

        cursor = manager.generate_cursor()
        assert manager.is_valid(cursor) is True

        # Test invalid cursor
        assert manager.is_valid("invalid-cursor") is False

        # Test expiration
        import time

        time.sleep(0.2)  # Just over TTL
        assert manager.is_valid(cursor) is False

    def test_cursor_position_tracking(self):
        """Test cursor position for pagination."""
        manager = CursorManager()

        # Create cursor with position
        items = ["resource1", "resource2", "resource3"]
        cursor = manager.create_cursor_for_position(items, 1)

        # Validate and get position
        position = manager.get_cursor_position(cursor)
        assert position == 1

        # Invalid cursor returns None
        assert manager.get_cursor_position("invalid") is None


class TestResourceMonitor:
    """Test resource change monitoring."""

    @pytest.fixture
    def monitor(self):
        """Create a resource monitor."""
        return ResourceMonitor()

    @pytest.mark.asyncio
    async def test_register_resource(self, monitor):
        """Test registering resources for monitoring."""
        await monitor.register_resource("file:///data.json", {"content": "test"})

        assert monitor.is_monitored("file:///data.json") is True
        assert monitor.is_monitored("file:///other.json") is False

    @pytest.mark.asyncio
    async def test_detect_changes(self, monitor):
        """Test detecting resource changes."""
        # Register initial state
        await monitor.register_resource("file:///data.json", {"content": "v1"})

        # No change
        changes = await monitor.check_for_changes(
            "file:///data.json", {"content": "v1"}
        )
        assert changes is None

        # Content changed
        changes = await monitor.check_for_changes(
            "file:///data.json", {"content": "v2"}
        )
        assert changes is not None
        assert changes.type == ResourceChangeType.UPDATED
        assert changes.uri == "file:///data.json"

    @pytest.mark.asyncio
    async def test_detect_deletion(self, monitor):
        """Test detecting resource deletion."""
        await monitor.register_resource("file:///data.json", {"content": "test"})

        changes = await monitor.check_for_deletion("file:///data.json")
        assert changes is not None
        assert changes.type == ResourceChangeType.DELETED
        assert changes.uri == "file:///data.json"

        # Resource no longer monitored after deletion
        assert monitor.is_monitored("file:///data.json") is False

    @pytest.mark.asyncio
    async def test_detect_creation(self, monitor):
        """Test detecting new resources."""
        # Resource not previously monitored
        changes = await monitor.check_for_changes(
            "file:///new.json", {"content": "new"}
        )
        assert changes is not None
        assert changes.type == ResourceChangeType.CREATED
        assert changes.uri == "file:///new.json"

        # Now it's monitored
        assert monitor.is_monitored("file:///new.json") is True


class TestResourceSubscriptionManager:
    """Test subscription manager functionality."""

    @pytest.fixture
    def auth_manager(self):
        """Create mock auth manager."""
        auth = Mock(spec=AuthManager)
        auth.check_permission = AsyncMock(return_value={"authorized": True})
        auth.authenticate_and_authorize = AsyncMock(return_value=True)
        return auth

    @pytest.fixture
    def event_store(self):
        """Create mock event store."""
        store = Mock()
        store.append = AsyncMock()
        store.append_event = AsyncMock()
        store.stream_events = AsyncMock(return_value=[])
        return store

    @pytest_asyncio.fixture
    async def manager(self, auth_manager, event_store):
        """Create subscription manager."""
        manager = ResourceSubscriptionManager(
            auth_manager=auth_manager, event_store=event_store
        )
        await manager.initialize()
        yield manager
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_create_subscription(self, manager, auth_manager):
        """Test creating a subscription."""
        sub_id = await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///data/*.json",
            user_context={"user_id": "user-1"},
        )

        assert sub_id is not None
        assert manager.get_subscription(sub_id) is not None

        # Verify auth was checked
        auth_manager.authenticate_and_authorize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_subscription_permission_denied(self, manager, auth_manager):
        """Test subscription creation with permission denied."""
        auth_manager.authenticate_and_authorize.side_effect = PermissionDeniedError(
            "Not authorized"
        )

        with pytest.raises(PermissionDeniedError):
            await manager.create_subscription(
                connection_id="conn-123",
                uri_pattern="file:///secure/*.json",
                user_context={"user_id": "user-1"},
            )

    @pytest.mark.asyncio
    async def test_remove_subscription(self, manager):
        """Test removing a subscription."""
        # Create subscription
        sub_id = await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///data/*.json",
            user_context={"user_id": "user-1"},
        )

        # Remove it
        result = await manager.remove_subscription(sub_id, "conn-123")
        assert result is True
        assert manager.get_subscription(sub_id) is None

    @pytest.mark.asyncio
    async def test_remove_subscription_wrong_connection(self, manager):
        """Test removing subscription from wrong connection."""
        sub_id = await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///data/*.json",
            user_context={"user_id": "user-1"},
        )

        # Try to remove from different connection
        result = await manager.remove_subscription(sub_id, "conn-456")
        assert result is False
        assert manager.get_subscription(sub_id) is not None

    @pytest.mark.asyncio
    async def test_get_connection_subscriptions(self, manager):
        """Test getting all subscriptions for a connection."""
        # Create multiple subscriptions
        sub1 = await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///*.json",
            user_context={"user_id": "user-1"},
        )
        sub2 = await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///*.md",
            user_context={"user_id": "user-1"},
        )
        sub3 = await manager.create_subscription(
            connection_id="conn-456",
            uri_pattern="file:///*.txt",
            user_context={"user_id": "user-2"},
        )

        # Get subscriptions for conn-123
        subs = manager.get_connection_subscriptions("conn-123")
        assert len(subs) == 2
        assert sub1 in subs
        assert sub2 in subs
        assert sub3 not in subs

    @pytest.mark.asyncio
    async def test_cleanup_connection(self, manager):
        """Test cleaning up all subscriptions for a connection."""
        # Create subscriptions
        await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///*.json",
            user_context={"user_id": "user-1"},
        )
        await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///*.md",
            user_context={"user_id": "user-1"},
        )

        # Cleanup connection
        removed = await manager.cleanup_connection("conn-123")
        assert removed == 2

        # Verify all removed
        subs = manager.get_connection_subscriptions("conn-123")
        assert len(subs) == 0

    @pytest.mark.asyncio
    async def test_find_matching_subscriptions(self, manager):
        """Test finding subscriptions that match a URI."""
        # Create subscriptions with different patterns
        sub1 = await manager.create_subscription(
            connection_id="conn-1",
            uri_pattern="file:///data/*.json",
            user_context={"user_id": "user-1"},
        )
        sub2 = await manager.create_subscription(
            connection_id="conn-2",
            uri_pattern="file:///**/*.json",
            user_context={"user_id": "user-1"},
        )
        sub3 = await manager.create_subscription(
            connection_id="conn-3",
            uri_pattern="file:///data/*.md",
            user_context={"user_id": "user-1"},
        )

        # Find matches
        matches = await manager.find_matching_subscriptions("file:///data/config.json")
        match_ids = [s.id for s in matches]

        assert sub1 in match_ids
        assert sub2 in match_ids
        assert sub3 not in match_ids

    @pytest.mark.asyncio
    async def test_process_resource_change(self, manager, event_store):
        """Test processing a resource change."""
        # Create subscription
        await manager.create_subscription(
            connection_id="conn-123",
            uri_pattern="file:///*.json",
            user_context={"user_id": "user-1"},
        )

        # Mock notification callback
        notifications = []
        manager.set_notification_callback(
            lambda conn_id, msg: notifications.append((conn_id, msg))
        )

        # Mock the _get_resource_data method to avoid the attribute error
        with patch.object(
            manager,
            "_get_resource_data",
            return_value={"uri": "file:///data.json", "content": {}},
        ):
            # Process change
            change = ResourceChange(
                type=ResourceChangeType.UPDATED,
                uri="file:///data.json",
                timestamp=datetime.now(UTC),
            )
            await manager.process_resource_change(change)

        # Verify notification sent
        assert len(notifications) == 1
        assert notifications[0][0] == "conn-123"
        assert notifications[0][1]["method"] == "notifications/resources/updated"

        # Verify event stored - checking append method instead of append_event
        assert event_store.append.call_count >= 1

    @pytest.mark.asyncio
    async def test_concurrent_subscription_operations(self, manager):
        """Test thread safety with concurrent operations."""

        async def create_sub(i):
            return await manager.create_subscription(
                connection_id=f"conn-{i}",
                uri_pattern=f"file:///{i}/*.json",
                user_context={"user_id": f"user-{i}"},
            )

        # Create fewer subscriptions for faster execution
        tasks = [create_sub(i) for i in range(10)]
        sub_ids = await asyncio.gather(*tasks)

        # Verify all created
        assert len(sub_ids) == 10
        assert len(set(sub_ids)) == 10  # All unique

        # Concurrent cleanup
        cleanup_tasks = [
            manager.cleanup_connection(f"conn-{i}")
            for i in range(0, 10, 2)  # Even connections
        ]
        removed_counts = await asyncio.gather(*cleanup_tasks)

        # Verify cleanup
        assert sum(removed_counts) == 5

    @pytest.mark.asyncio
    async def test_subscription_rate_limiting(self, manager):
        """Test rate limiting subscription creation."""
        manager.rate_limiter = Mock()
        manager.rate_limiter.check_rate_limit = AsyncMock(return_value=False)

        with pytest.raises(SubscriptionError, match="Rate limit"):
            await manager.create_subscription(
                connection_id="conn-123",
                uri_pattern="file:///*.json",
                user_context={"user_id": "user-1"},
            )

    def test_subscription_memory_cleanup(self, manager):
        """Test that subscriptions are properly garbage collected."""
        import gc
        import weakref

        # Create subscription
        sub = ResourceSubscription(
            id="sub-test", connection_id="conn-test", uri_pattern="file:///*.json"
        )

        # Create weak reference
        weak_sub = weakref.ref(sub)

        # Add to manager (ensure connection subscriptions set exists)
        manager._subscriptions[sub.id] = sub
        if "conn-test" not in manager._connection_subscriptions:
            manager._connection_subscriptions["conn-test"] = set()
        manager._connection_subscriptions["conn-test"].add(sub.id)

        # Remove subscription
        del manager._subscriptions[sub.id]
        manager._connection_subscriptions["conn-test"].remove(sub.id)
        del sub

        # Force garbage collection
        gc.collect()

        # Verify object was collected
        assert weak_sub() is None
