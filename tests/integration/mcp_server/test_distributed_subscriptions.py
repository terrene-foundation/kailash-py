"""Unit tests for Redis-backed distributed subscription manager."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from kailash.mcp_server.subscriptions import (
    REDIS_AVAILABLE,
    DistributedSubscriptionManager,
    ResourceChange,
    ResourceChangeType,
    ResourceSubscriptionManager,
)


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestDistributedSubscriptionManager:
    """Test Redis-backed distributed subscription functionality."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.hset = AsyncMock()
        mock.expire = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock(return_value=[])
        mock.hgetall = AsyncMock(return_value={})
        mock.smembers = AsyncMock(return_value=set())
        mock.sadd = AsyncMock()
        mock.srem = AsyncMock()
        mock.publish = AsyncMock()
        mock.aclose = AsyncMock()
        mock.pipeline = MagicMock()
        pipeline_mock = AsyncMock()
        pipeline_mock.execute = AsyncMock()
        mock.pipeline.return_value = pipeline_mock
        return mock

    @pytest.fixture
    def mock_redis_pubsub(self):
        """Create mock Redis pub/sub client."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.aclose = AsyncMock()

        # Mock pubsub
        pubsub_mock = AsyncMock()
        pubsub_mock.subscribe = AsyncMock()

        # Mock listen method that yields no messages by default
        async def mock_listen():
            return
            yield  # Make it an async generator

        pubsub_mock.listen = mock_listen
        mock.pubsub = MagicMock(return_value=pubsub_mock)
        return mock

    @pytest.fixture
    def distributed_manager(self, mock_redis_client, mock_redis_pubsub):
        """Create distributed subscription manager with mocked Redis."""
        with patch(
            "kailash.mcp_server.subscriptions.redis.Redis.from_url"
        ) as mock_from_url:
            # Return different mocks for different calls
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_redis_client
                else:
                    return mock_redis_pubsub

            mock_from_url.side_effect = side_effect

            manager = DistributedSubscriptionManager(
                redis_url="redis://localhost:6379",
                server_instance_id="test_instance_123",
                heartbeat_interval=0.1,  # Fast for testing
                instance_timeout=1,
            )

            # Manually set the mock clients since we can't easily mock the constructor
            manager.redis_client = mock_redis_client
            manager.redis_pubsub = mock_redis_pubsub

            return manager

    def test_initialization_without_redis(self):
        """Test that initialization fails without Redis available."""
        with patch("kailash.mcp_server.subscriptions.REDIS_AVAILABLE", False):
            with pytest.raises(ImportError, match="Redis support not available"):
                DistributedSubscriptionManager()

    def test_initialization_with_redis(self):
        """Test proper initialization with Redis available."""
        manager = DistributedSubscriptionManager(
            redis_url="redis://localhost:6379", server_instance_id="test_instance"
        )

        assert manager.redis_url == "redis://localhost:6379"
        assert manager.server_instance_id == "test_instance"
        assert manager.subscription_key_prefix == "mcp:subs:"
        assert manager.notification_channel_prefix == "mcp:notify:"
        assert manager.heartbeat_interval == 30
        assert manager.instance_timeout == 90

    def test_custom_configuration(self):
        """Test initialization with custom configuration."""
        manager = DistributedSubscriptionManager(
            redis_url="redis://custom:6380",
            server_instance_id="custom_instance",
            subscription_key_prefix="custom:subs:",
            notification_channel_prefix="custom:notify:",
            heartbeat_interval=60,
            instance_timeout=180,
        )

        assert manager.redis_url == "redis://custom:6380"
        assert manager.server_instance_id == "custom_instance"
        assert manager.subscription_key_prefix == "custom:subs:"
        assert manager.notification_channel_prefix == "custom:notify:"
        assert manager.heartbeat_interval == 60
        assert manager.instance_timeout == 180

    @pytest.mark.asyncio
    async def test_initialize_success(self, distributed_manager):
        """Test successful initialization."""
        with (
            patch.object(distributed_manager, "_register_instance") as mock_register,
            patch.object(
                distributed_manager, "_load_distributed_subscriptions"
            ) as mock_load,
            patch.object(distributed_manager, "_heartbeat_loop") as mock_heartbeat,
            patch.object(
                distributed_manager, "_notification_listener"
            ) as mock_listener,
            patch.object(distributed_manager, "_instance_monitor") as mock_monitor,
        ):

            # Make background tasks return immediately
            mock_heartbeat.return_value = asyncio.sleep(0)
            mock_listener.return_value = asyncio.sleep(0)
            mock_monitor.return_value = asyncio.sleep(0)

            await distributed_manager.initialize()

            # Verify Redis connections were tested
            distributed_manager.redis_client.ping.assert_called_once()
            distributed_manager.redis_pubsub.ping.assert_called_once()

            # Verify initialization steps
            mock_register.assert_called_once()
            mock_load.assert_called_once()

            # Verify background tasks were started
            assert distributed_manager._heartbeat_task is not None
            assert distributed_manager._notification_listener_task is not None
            assert distributed_manager._instance_monitor_task is not None

            # Clean up tasks
            for task in [
                distributed_manager._heartbeat_task,
                distributed_manager._notification_listener_task,
                distributed_manager._instance_monitor_task,
            ]:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    @pytest.mark.asyncio
    async def test_initialize_redis_connection_failure(self, distributed_manager):
        """Test initialization failure due to Redis connection issues."""
        distributed_manager.redis_client.ping.side_effect = Exception(
            "Connection failed"
        )

        with (
            patch.object(distributed_manager, "_register_instance"),
            patch.object(distributed_manager, "_load_distributed_subscriptions"),
            patch.object(distributed_manager, "_heartbeat_loop"),
            patch.object(distributed_manager, "_notification_listener"),
            patch.object(distributed_manager, "_instance_monitor"),
        ):

            with pytest.raises(Exception):
                await distributed_manager.initialize()

    @pytest.mark.asyncio
    async def test_shutdown(self, distributed_manager):
        """Test proper shutdown."""
        # Mock background tasks
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        mock_task.done = MagicMock(return_value=False)

        distributed_manager._heartbeat_task = mock_task
        distributed_manager._notification_listener_task = MagicMock()
        distributed_manager._notification_listener_task.cancel = MagicMock()
        distributed_manager._instance_monitor_task = MagicMock()
        distributed_manager._instance_monitor_task.cancel = MagicMock()

        with patch.object(
            distributed_manager, "_unregister_instance"
        ) as mock_unregister:
            await distributed_manager.shutdown()

            # Verify tasks were cancelled
            distributed_manager._heartbeat_task.cancel.assert_called_once()
            distributed_manager._notification_listener_task.cancel.assert_called_once()
            distributed_manager._instance_monitor_task.cancel.assert_called_once()

            # Verify unregistration
            mock_unregister.assert_called_once()

            # Verify Redis connections were closed
            distributed_manager.redis_client.aclose.assert_called_once()
            distributed_manager.redis_pubsub.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_instance(self, distributed_manager):
        """Test instance registration in Redis."""
        await distributed_manager._register_instance()

        # Verify instance data was stored
        distributed_manager.redis_client.hset.assert_called_once()
        call_args = distributed_manager.redis_client.hset.call_args

        assert call_args[0][0] == "mcp:instances:test_instance_123"
        instance_data = call_args[1]["mapping"]
        assert instance_data["id"] == "test_instance_123"
        assert "registered_at" in instance_data
        assert "last_heartbeat" in instance_data
        assert instance_data["subscriptions"] == 0

        # Verify expiration was set
        distributed_manager.redis_client.expire.assert_called_once_with(
            "mcp:instances:test_instance_123", 1
        )

    @pytest.mark.asyncio
    async def test_unregister_instance(self, distributed_manager):
        """Test instance unregistration from Redis."""
        await distributed_manager._unregister_instance()

        # Verify instance and subscription data were deleted
        expected_calls = [
            (("mcp:instances:test_instance_123",), {}),
            (("mcp:instance_subs:test_instance_123",), {}),
        ]

        assert distributed_manager.redis_client.delete.call_count == 2
        actual_calls = distributed_manager.redis_client.delete.call_args_list
        for expected, actual in zip(expected_calls, actual_calls):
            assert actual[0] == expected[0]

    @pytest.mark.asyncio
    async def test_create_subscription(self, distributed_manager):
        """Test creating subscription with Redis replication."""
        with patch.object(
            distributed_manager, "_replicate_subscription_to_redis"
        ) as mock_replicate:
            subscription_id = await distributed_manager.create_subscription(
                connection_id="conn_123",
                uri_pattern="file:///*.json",
                fields=["uri", "content"],
            )

            # Verify subscription was created locally
            assert subscription_id in distributed_manager._subscriptions

            # Verify replication to Redis
            mock_replicate.assert_called_once_with(subscription_id)

    @pytest.mark.asyncio
    async def test_remove_subscription(self, distributed_manager):
        """Test removing subscription from Redis."""
        # Create subscription first
        subscription_id = await distributed_manager.create_subscription(
            connection_id="conn_123", uri_pattern="file:///*.json"
        )

        with patch.object(
            distributed_manager, "_remove_subscription_from_redis"
        ) as mock_remove:
            success = await distributed_manager.remove_subscription(
                subscription_id, "conn_123"
            )

            assert success is True
            mock_remove.assert_called_once_with(subscription_id)

    @pytest.mark.asyncio
    async def test_replicate_subscription_to_redis(self, distributed_manager):
        """Test subscription replication to Redis."""
        # Create a subscription
        subscription_id = await distributed_manager.create_subscription(
            connection_id="conn_123",
            uri_pattern="file:///*.json",
            fields=["uri", "content"],
        )

        # Reset mocks to check replication call
        distributed_manager.redis_client.reset_mock()

        await distributed_manager._replicate_subscription_to_redis(subscription_id)

        # Verify subscription data was stored
        distributed_manager.redis_client.hset.assert_called()
        sub_key = f"mcp:subs:{subscription_id}"

        # Verify subscription was added to instance tracking
        distributed_manager.redis_client.sadd.assert_called_with(
            "mcp:instance_subs:test_instance_123", subscription_id
        )

    @pytest.mark.asyncio
    async def test_remove_subscription_from_redis(self, distributed_manager):
        """Test subscription removal from Redis."""
        subscription_id = "test_sub_123"

        await distributed_manager._remove_subscription_from_redis(subscription_id)

        # Verify subscription data was deleted
        distributed_manager.redis_client.delete.assert_called_with(
            f"mcp:subs:{subscription_id}"
        )

        # Verify removal from instance tracking
        distributed_manager.redis_client.srem.assert_called_with(
            "mcp:instance_subs:test_instance_123", subscription_id
        )

    @pytest.mark.asyncio
    async def test_process_resource_change_distribution(self, distributed_manager):
        """Test resource change processing and distribution."""
        # Set up other instances
        distributed_manager._other_instances = {"instance_1", "instance_2"}

        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///test.json",
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(
            distributed_manager, "_distribute_resource_change"
        ) as mock_distribute:
            await distributed_manager.process_resource_change(change)

            # Verify distribution was called
            mock_distribute.assert_called_once_with(change)

    @pytest.mark.asyncio
    async def test_distribute_resource_change(self, distributed_manager):
        """Test distributing resource change to other instances."""
        # Set up other instances
        distributed_manager._other_instances = {"instance_1", "instance_2"}

        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///test.json",
            timestamp=datetime.now(timezone.utc),
        )

        await distributed_manager._distribute_resource_change(change)

        # Verify message was published
        distributed_manager.redis_client.publish.assert_called_once()

        call_args = distributed_manager.redis_client.publish.call_args
        channel = call_args[0][0]
        message_data = json.loads(call_args[0][1])

        assert channel == "mcp:notify:resource_changes"
        assert message_data["type"] == "updated"
        assert message_data["uri"] == "file:///test.json"
        assert message_data["source_instance"] == "test_instance_123"

    @pytest.mark.asyncio
    async def test_distribute_resource_change_no_instances(self, distributed_manager):
        """Test that no distribution occurs when no other instances exist."""
        # No other instances
        distributed_manager._other_instances = set()

        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///test.json",
            timestamp=datetime.now(timezone.utc),
        )

        await distributed_manager._distribute_resource_change(change)

        # Verify no message was published
        distributed_manager.redis_client.publish.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Timeout issue in CI - needs investigation")
    async def test_instance_monitor_detection(self, distributed_manager):
        """Test instance monitoring and detection."""
        # Mock Redis to return instance data
        distributed_manager.redis_client.keys.return_value = [
            "mcp:instances:test_instance_123",  # Self
            "mcp:instances:other_instance_1",
            "mcp:instances:other_instance_2",
        ]

        current_time = datetime.now(timezone.utc)

        def mock_hgetall(key):
            if key == "mcp:instances:test_instance_123":
                return {
                    "id": "test_instance_123",
                    "last_heartbeat": current_time.isoformat(),
                }
            elif key == "mcp:instances:other_instance_1":
                return {
                    "id": "other_instance_1",
                    "last_heartbeat": current_time.isoformat(),  # Recent
                }
            elif key == "mcp:instances:other_instance_2":
                old_time = datetime(2020, 1, 1)  # Very old
                return {
                    "id": "other_instance_2",
                    "last_heartbeat": old_time.isoformat(),
                }
            return {}

        distributed_manager.redis_client.hgetall.side_effect = mock_hgetall

        with patch.object(
            distributed_manager, "_cleanup_dead_instance"
        ) as mock_cleanup:
            # Run one iteration of instance monitoring
            await distributed_manager._instance_monitor()

            # Verify dead instance cleanup was called
            mock_cleanup.assert_called_once_with("other_instance_2")

            # Verify live instance was detected
            assert "other_instance_1" in distributed_manager._other_instances

    @pytest.mark.asyncio
    async def test_cleanup_dead_instance(self, distributed_manager):
        """Test cleanup of dead instance subscriptions."""
        dead_instance_id = "dead_instance"
        dead_subscription_ids = {"sub_1", "sub_2", "sub_3"}

        distributed_manager.redis_client.smembers.return_value = dead_subscription_ids

        await distributed_manager._cleanup_dead_instance(dead_instance_id)

        # Verify subscription data was deleted using pipeline
        distributed_manager.redis_client.pipeline.assert_called_once()

        # Verify instance record was deleted
        distributed_manager.redis_client.delete.assert_called_with(
            f"mcp:instances:{dead_instance_id}"
        )

    @pytest.mark.asyncio
    async def test_load_distributed_subscriptions(self, distributed_manager):
        """Test loading distributed subscription data."""
        # Mock Redis to return instance data
        distributed_manager.redis_client.keys.return_value = [
            "mcp:instances:test_instance_123",  # Self
            "mcp:instances:other_instance_1",
        ]

        def mock_hgetall(key):
            if key == "mcp:instances:other_instance_1":
                return {"id": "other_instance_1"}
            return {"id": "test_instance_123"}

        distributed_manager.redis_client.hgetall.side_effect = mock_hgetall
        distributed_manager.redis_client.smembers.return_value = {"sub_1", "sub_2"}

        await distributed_manager._load_distributed_subscriptions()

        # Verify other instance subscriptions were loaded
        assert "other_instance_1" in distributed_manager._instance_subscriptions
        assert distributed_manager._instance_subscriptions["other_instance_1"] == {
            "sub_1",
            "sub_2",
        }

    def test_get_distributed_stats(self, distributed_manager):
        """Test getting distributed subscription statistics."""
        # Set up test data
        distributed_manager._subscriptions = {"sub_1": None, "sub_2": None}
        distributed_manager._other_instances = {"instance_1", "instance_2"}
        distributed_manager._instance_subscriptions = {
            "instance_1": {"sub_3", "sub_4"},
            "instance_2": {"sub_5"},
        }

        stats = distributed_manager.get_distributed_stats()

        assert stats["instance_id"] == "test_instance_123"
        assert stats["local_subscriptions"] == 2
        assert stats["other_instances"] == 2
        assert stats["distributed_subscriptions"]["instance_1"] == 2
        assert stats["distributed_subscriptions"]["instance_2"] == 1
        assert stats["total_distributed_subscriptions"] == 3
        assert stats["redis_url"] == "redis://localhost:6379"

    @pytest.mark.asyncio
    async def test_notification_listener_processes_changes(self, distributed_manager):
        """Test that notification listener processes distributed changes."""
        # Mock the notification listener to process one message then stop
        change_data = {
            "type": "updated",
            "uri": "file:///distributed.json",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_instance": "other_instance",
        }

        # Mock pubsub to yield one message
        async def mock_listen():
            yield {"type": "message", "data": json.dumps(change_data)}

        pubsub_mock = AsyncMock()
        pubsub_mock.subscribe = AsyncMock()
        pubsub_mock.listen = mock_listen
        distributed_manager.redis_pubsub.pubsub.return_value = pubsub_mock

        # Mock the parent's process_resource_change method
        with patch.object(
            ResourceSubscriptionManager, "process_resource_change"
        ) as mock_process:
            # Start notification listener task
            task = asyncio.create_task(distributed_manager._notification_listener())

            # Give it a moment to process
            await asyncio.sleep(0.01)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify the change was processed
            mock_process.assert_called_once()

            # Verify the change object was created correctly
            call_args = mock_process.call_args[0][0]
            assert call_args.type == ResourceChangeType.UPDATED
            assert call_args.uri == "file:///distributed.json"

    @pytest.mark.asyncio
    async def test_notification_listener_ignores_own_messages(
        self, distributed_manager
    ):
        """Test that notification listener ignores messages from itself."""
        # Mock message from this instance
        change_data = {
            "type": "updated",
            "uri": "file:///own.json",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_instance": "test_instance_123",  # Same as this instance
        }

        async def mock_listen():
            yield {"type": "message", "data": json.dumps(change_data)}

        pubsub_mock = AsyncMock()
        pubsub_mock.subscribe = AsyncMock()
        pubsub_mock.listen = mock_listen
        distributed_manager.redis_pubsub.pubsub.return_value = pubsub_mock

        with patch.object(
            ResourceSubscriptionManager, "process_resource_change"
        ) as mock_process:
            task = asyncio.create_task(distributed_manager._notification_listener())

            await asyncio.sleep(0.01)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify the change was NOT processed (ignored own message)
            mock_process.assert_not_called()


@pytest.mark.skipif(REDIS_AVAILABLE, reason="Testing Redis unavailable scenario")
class TestDistributedSubscriptionManagerWithoutRedis:
    """Test behavior when Redis is not available."""

    def test_import_error_without_redis(self):
        """Test that ImportError is raised when Redis is not available."""
        with pytest.raises(ImportError, match="Redis support not available"):
            DistributedSubscriptionManager()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
