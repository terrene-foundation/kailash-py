"""Unit tests for the Channel framework."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.kailash.channels.base import (
    Channel,
    ChannelConfig,
    ChannelEvent,
    ChannelResponse,
    ChannelStatus,
    ChannelType,
)
from src.kailash.channels.session import CrossChannelSession, SessionManager


class TestChannelBase:
    """Unit tests for base Channel class."""

    def test_channel_config_creation(self):
        """Test ChannelConfig creation."""
        config = ChannelConfig(
            name="test_channel",
            channel_type=ChannelType.API,
            host="localhost",
            port=8000,
        )

        assert config.name == "test_channel"
        assert config.channel_type == ChannelType.API
        assert config.host == "localhost"
        assert config.port == 8000
        assert config.enabled is True
        assert config.enable_sessions is True

    def test_channel_event_creation(self):
        """Test ChannelEvent creation."""
        event = ChannelEvent(
            event_id="test_event_1",
            channel_name="test_channel",
            channel_type=ChannelType.CLI,
            event_type="command_executed",
            payload={"command": "help", "success": True},
        )

        assert event.event_id == "test_event_1"
        assert event.channel_name == "test_channel"
        assert event.channel_type == ChannelType.CLI
        assert event.event_type == "command_executed"
        assert event.payload["command"] == "help"
        assert event.session_id is None

    def test_channel_response_creation(self):
        """Test ChannelResponse creation."""
        response = ChannelResponse(
            success=True,
            data={"result": "success"},
            metadata={"channel": "test", "type": "api"},
        )

        assert response.success is True
        assert response.data["result"] == "success"
        assert response.error is None
        assert response.metadata["channel"] == "test"

    @pytest.mark.asyncio
    async def test_abstract_channel_methods(self):
        """Test that Channel is abstract and requires implementation."""
        config = ChannelConfig(name="test", channel_type=ChannelType.API)

        # Should not be able to instantiate abstract Channel directly
        with pytest.raises(TypeError):
            Channel(config)


class TestSessionManager:
    """Unit tests for SessionManager."""

    @pytest.mark.asyncio
    async def test_session_manager_lifecycle(self):
        """Test session manager start/stop."""
        manager = SessionManager(default_timeout=30, cleanup_interval=10)

        assert not manager._running

        await manager.start()
        assert manager._running
        assert manager._cleanup_task is not None

        await manager.stop()
        assert not manager._running

    def test_create_session(self):
        """Test session creation."""
        manager = SessionManager()

        session = manager.create_session(user_id="test_user")

        assert session.user_id == "test_user"
        assert session.session_id in manager._sessions
        assert session.status.value == "active"

    def test_create_session_with_custom_id(self):
        """Test session creation with custom ID."""
        manager = SessionManager()

        session = manager.create_session(
            user_id="test_user", session_id="custom_session_123"
        )

        assert session.session_id == "custom_session_123"
        assert session.user_id == "test_user"

    def test_duplicate_session_id_error(self):
        """Test error when creating duplicate session ID."""
        manager = SessionManager()

        manager.create_session(session_id="duplicate_id")

        with pytest.raises(ValueError, match="Session duplicate_id already exists"):
            manager.create_session(session_id="duplicate_id")

    def test_get_session(self):
        """Test getting existing session."""
        manager = SessionManager()

        original = manager.create_session(user_id="test_user")
        retrieved = manager.get_session(original.session_id)

        assert retrieved is not None
        assert retrieved.session_id == original.session_id
        assert retrieved.user_id == "test_user"

    def test_get_nonexistent_session(self):
        """Test getting non-existent session."""
        manager = SessionManager()

        result = manager.get_session("nonexistent_session")

        assert result is None

    def test_get_or_create_session(self):
        """Test get or create session functionality."""
        manager = SessionManager()

        # First call should create
        session1 = manager.get_or_create_session("test_session", user_id="user1")
        assert session1.session_id == "test_session"
        assert session1.user_id == "user1"

        # Second call should return existing
        session2 = manager.get_or_create_session("test_session", user_id="user2")
        assert session2.session_id == "test_session"
        assert session2.user_id == "user1"  # Should keep original user_id

    def test_terminate_session(self):
        """Test session termination."""
        manager = SessionManager()

        session = manager.create_session()
        session_id = session.session_id

        # Terminate should return True and remove session
        result = manager.terminate_session(session_id)
        assert result is True
        assert manager.get_session(session_id) is None

    def test_list_sessions(self):
        """Test listing sessions."""
        manager = SessionManager()

        session1 = manager.create_session(user_id="user1")
        session2 = manager.create_session(user_id="user2")
        session3 = manager.create_session(user_id="user1")

        # List all sessions
        all_sessions = manager.list_sessions()
        assert len(all_sessions) == 3

        # List sessions by user
        user1_sessions = manager.list_sessions(user_id="user1")
        assert len(user1_sessions) == 2

        user2_sessions = manager.list_sessions(user_id="user2")
        assert len(user2_sessions) == 1

    def test_channel_sessions(self):
        """Test getting sessions by channel."""
        manager = SessionManager()

        session1 = manager.create_session()
        session2 = manager.create_session()
        session3 = manager.create_session()

        # Add channels to sessions
        session1.add_channel("api_channel")
        session1.add_channel("cli_channel")
        session2.add_channel("api_channel")
        session3.add_channel("mcp_channel")

        # Test channel filtering
        api_sessions = manager.get_channel_sessions("api_channel")
        assert len(api_sessions) == 2

        cli_sessions = manager.get_channel_sessions("cli_channel")
        assert len(cli_sessions) == 1

        mcp_sessions = manager.get_channel_sessions("mcp_channel")
        assert len(mcp_sessions) == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self):
        """Test broadcasting events to channel."""
        manager = SessionManager()

        session1 = manager.create_session()
        session2 = manager.create_session()
        session3 = manager.create_session()

        session1.add_channel("api_channel")
        session2.add_channel("api_channel")
        session3.add_channel("cli_channel")

        # Broadcast to API channel
        event_data = {"type": "notification", "message": "Hello API users"}
        count = await manager.broadcast_to_channel("api_channel", event_data)

        assert count == 2

        # Check that sessions received the event
        assert len(session1.event_history) == 1
        assert len(session2.event_history) == 1
        assert len(session3.event_history) == 0  # Not on API channel

    def test_session_manager_stats(self):
        """Test session manager statistics."""
        manager = SessionManager(default_timeout=60, cleanup_interval=30)

        session1 = manager.create_session()
        session2 = manager.create_session()
        session1.add_channel("api")
        session2.add_channel("api")
        session2.add_channel("cli")

        stats = manager.get_stats()

        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2
        assert stats["idle_sessions"] == 0
        assert stats["channel_usage"]["api"] == 2
        assert stats["channel_usage"]["cli"] == 1
        assert stats["default_timeout"] == 60
        assert stats["cleanup_interval"] == 30


class TestCrossChannelSession:
    """Unit tests for CrossChannelSession."""

    def test_session_creation(self):
        """Test session creation and basic properties."""
        session = CrossChannelSession(session_id="test_session", user_id="test_user")

        assert session.session_id == "test_session"
        assert session.user_id == "test_user"
        assert session.status.value == "active"
        assert len(session.active_channels) == 0
        assert len(session.shared_data) == 0

    def test_channel_management(self):
        """Test adding and removing channels."""
        session = CrossChannelSession(session_id="test", user_id="user")

        # Add channel
        session.add_channel("api_channel", {"key": "value"})
        assert "api_channel" in session.active_channels
        assert session.channel_contexts["api_channel"]["key"] == "value"

        # Add another channel
        session.add_channel("cli_channel")
        assert "cli_channel" in session.active_channels
        assert len(session.active_channels) == 2

        # Remove channel
        session.remove_channel("api_channel")
        assert "api_channel" not in session.active_channels
        assert "api_channel" not in session.channel_contexts
        assert len(session.active_channels) == 1

    def test_channel_context_updates(self):
        """Test updating channel context."""
        session = CrossChannelSession(session_id="test", user_id="user")

        session.add_channel("test_channel", {"initial": "data"})

        # Update context
        session.update_channel_context(
            "test_channel", {"new": "value", "initial": "updated"}
        )

        context = session.get_channel_context("test_channel")
        assert context["initial"] == "updated"
        assert context["new"] == "value"

    def test_shared_data_management(self):
        """Test shared data across channels."""
        session = CrossChannelSession(session_id="test", user_id="user")

        # Set shared data
        session.set_shared_data("user_preferences", {"theme": "dark"})
        session.set_shared_data("session_count", 5)

        # Get shared data
        assert session.get_shared_data("user_preferences")["theme"] == "dark"
        assert session.get_shared_data("session_count") == 5
        assert session.get_shared_data("nonexistent", "default") == "default"

    def test_event_history(self):
        """Test event history management."""
        session = CrossChannelSession(session_id="test", user_id="user")

        # Add events
        session.add_event({"type": "login", "timestamp": 123456})
        session.add_event({"type": "command", "data": "help"})

        assert len(session.event_history) == 2
        assert session.event_history[0]["type"] == "login"
        assert session.event_history[1]["type"] == "command"
        assert "session_id" in session.event_history[0]

    def test_event_history_size_limit(self):
        """Test event history size limiting."""
        session = CrossChannelSession(session_id="test", user_id="user")
        session.max_history_size = 3

        # Add more events than max size
        for i in range(5):
            session.add_event({"type": "event", "number": i})

        assert len(session.event_history) == 3
        # Should keep the latest events
        assert session.event_history[-1]["number"] == 4

    def test_session_touch(self):
        """Test session activity tracking."""
        session = CrossChannelSession(session_id="test", user_id="user")

        original_time = session.last_activity

        # Add small delay to ensure time difference
        import time

        time.sleep(0.001)

        # Touch should update last activity
        session.touch()
        assert session.last_activity > original_time

    def test_session_expiry(self):
        """Test session expiry logic."""
        session = CrossChannelSession(session_id="test", user_id="user")

        # New session should not be expired
        assert not session.is_expired(timeout=3600)

        # Set old last activity
        session.last_activity = session.last_activity - 7200  # 2 hours ago
        assert session.is_expired(timeout=3600)  # 1 hour timeout

    def test_session_extension(self):
        """Test extending session expiry."""
        session = CrossChannelSession(session_id="test", user_id="user")

        # Extend expiry
        session.extend_expiry(1800)  # 30 minutes
        assert session.expires_at is not None

        # Should not be expired
        assert not session.is_expired()

    def test_session_to_dict(self):
        """Test session serialization."""
        session = CrossChannelSession(session_id="test", user_id="user")
        session.add_channel("api")
        session.set_shared_data("key", "value")
        session.add_event({"type": "test"})

        data = session.to_dict()

        assert data["session_id"] == "test"
        assert data["user_id"] == "user"
        assert "api" in data["active_channels"]
        assert data["shared_data"]["key"] == "value"
        assert data["event_count"] == 1
