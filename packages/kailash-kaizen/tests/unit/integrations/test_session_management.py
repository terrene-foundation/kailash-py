"""
Unit tests for Nexus session management.

Tests session creation, state management, cross-channel synchronization,
and memory pool integration.

Phase 3 of TODO-149: Unified Session Management
"""

from datetime import datetime, timedelta
from time import sleep

import pytest
from kaizen.integrations.nexus import NEXUS_AVAILABLE

if not NEXUS_AVAILABLE:
    pytest.skip("Nexus not available", allow_module_level=True)

from kaizen.integrations.nexus.session_manager import (
    CrossChannelSession,
    NexusSessionManager,
)


class TestCrossChannelSession:
    """Test CrossChannelSession functionality."""

    def test_create_session_with_defaults(self):
        """Test session creation with default values."""
        session = CrossChannelSession(user_id="user-123")

        assert session.session_id  # Auto-generated
        assert session.user_id == "user-123"
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_accessed, datetime)
        assert isinstance(session.expires_at, datetime)
        assert session.state == {}
        assert session.channel_activity == {}
        assert session.memory_pool_id is None

    def test_create_session_with_custom_id(self):
        """Test session creation with custom ID."""
        session = CrossChannelSession(
            session_id="custom-session-123", user_id="user-456"
        )

        assert session.session_id == "custom-session-123"
        assert session.user_id == "user-456"

    def test_session_expiration_default(self):
        """Test default session expiration (1 hour)."""
        session = CrossChannelSession(user_id="user-123")

        expected_expiry = session.created_at + timedelta(hours=1)
        assert abs((session.expires_at - expected_expiry).total_seconds()) < 1

    def test_session_is_expired_false(self):
        """Test is_expired returns False for active session."""
        session = CrossChannelSession(user_id="user-123")
        assert not session.is_expired()

    def test_session_is_expired_true(self):
        """Test is_expired returns True for expired session."""
        session = CrossChannelSession(
            user_id="user-123", expires_at=datetime.now() - timedelta(seconds=1)
        )
        assert session.is_expired()

    def test_refresh_extends_expiration(self):
        """Test refresh extends session expiration."""
        session = CrossChannelSession(user_id="user-123")
        original_expiry = session.expires_at

        sleep(0.1)  # Small delay
        session.refresh()

        assert session.expires_at > original_expiry
        assert session.last_accessed > session.created_at

    def test_refresh_with_channel_tracking(self):
        """Test refresh tracks channel activity."""
        session = CrossChannelSession(user_id="user-123")

        session.refresh(channel="api")
        assert "api" in session.channel_activity

        session.refresh(channel="cli")
        assert "cli" in session.channel_activity

        session.refresh(channel="mcp")
        assert "mcp" in session.channel_activity

        assert len(session.channel_activity) == 3

    def test_update_state(self):
        """Test updating session state."""
        session = CrossChannelSession(user_id="user-123")

        session.update_state({"key1": "value1"})
        assert session.state == {"key1": "value1"}

        session.update_state({"key2": "value2"})
        assert session.state == {"key1": "value1", "key2": "value2"}

    def test_update_state_with_channel(self):
        """Test updating state tracks channel activity."""
        session = CrossChannelSession(user_id="user-123")

        session.update_state({"data": "from-api"}, channel="api")
        assert "api" in session.channel_activity
        assert session.state["data"] == "from-api"

    def test_get_state_returns_copy(self):
        """Test get_state returns a copy, not reference."""
        session = CrossChannelSession(user_id="user-123")
        session.state = {"key": "value"}

        state_copy = session.get_state()
        state_copy["key"] = "modified"

        assert session.state["key"] == "value"  # Original unchanged

    def test_get_state_with_channel_tracking(self):
        """Test get_state tracks channel activity."""
        session = CrossChannelSession(user_id="user-123")

        session.get_state(channel="cli")
        assert "cli" in session.channel_activity


class TestNexusSessionManager:
    """Test NexusSessionManager functionality."""

    def test_create_session(self):
        """Test creating a new session."""
        manager = NexusSessionManager()

        session = manager.create_session(user_id="user-123")

        assert session.user_id == "user-123"
        assert session.session_id in manager.sessions

    def test_create_session_with_custom_id(self):
        """Test creating session with custom ID."""
        manager = NexusSessionManager()

        session = manager.create_session(session_id="custom-123", user_id="user-456")

        assert session.session_id == "custom-123"
        assert "custom-123" in manager.sessions

    def test_create_session_with_custom_ttl(self):
        """Test creating session with custom TTL."""
        manager = NexusSessionManager()

        session = manager.create_session(user_id="user-123", ttl_hours=2)

        expected_expiry = datetime.now() + timedelta(hours=2)
        assert abs((session.expires_at - expected_expiry).total_seconds()) < 2

    def test_get_session_existing(self):
        """Test retrieving existing session."""
        manager = NexusSessionManager()
        created_session = manager.create_session(user_id="user-123")

        retrieved_session = manager.get_session(created_session.session_id)

        assert retrieved_session is not None
        assert retrieved_session.session_id == created_session.session_id

    def test_get_session_not_found(self):
        """Test retrieving non-existent session."""
        manager = NexusSessionManager()

        session = manager.get_session("non-existent")

        assert session is None

    def test_get_session_expired_returns_none(self):
        """Test get_session returns None for expired session."""
        manager = NexusSessionManager()

        # Create expired session
        session = manager.create_session(user_id="user-123", ttl_hours=0)
        session.expires_at = datetime.now() - timedelta(seconds=1)
        manager.sessions[session.session_id] = session

        retrieved = manager.get_session(session.session_id)

        assert retrieved is None
        assert session.session_id not in manager.sessions  # Cleaned up

    def test_update_session_state_success(self):
        """Test updating session state successfully."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        result = manager.update_session_state(session.session_id, {"key": "value"})

        assert result is True
        assert manager.sessions[session.session_id].state == {"key": "value"}

    def test_update_session_state_with_channel(self):
        """Test updating session state with channel tracking."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        result = manager.update_session_state(
            session.session_id, {"data": "from-api"}, channel="api"
        )

        assert result is True
        assert "api" in manager.sessions[session.session_id].channel_activity

    def test_update_session_state_not_found(self):
        """Test updating non-existent session returns False."""
        manager = NexusSessionManager()

        result = manager.update_session_state("non-existent", {"key": "value"})

        assert result is False

    def test_get_session_state_success(self):
        """Test retrieving session state successfully."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")
        manager.update_session_state(session.session_id, {"key": "value"})

        state = manager.get_session_state(session.session_id)

        assert state is not None
        assert state == {"key": "value"}

    def test_get_session_state_with_channel(self):
        """Test get_session_state tracks channel activity."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        state = manager.get_session_state(session.session_id, channel="mcp")

        assert state is not None
        assert "mcp" in manager.sessions[session.session_id].channel_activity

    def test_get_session_state_not_found(self):
        """Test retrieving state for non-existent session."""
        manager = NexusSessionManager()

        state = manager.get_session_state("non-existent")

        assert state is None

    def test_bind_memory_pool_success(self):
        """Test binding session to memory pool."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        result = manager.bind_memory_pool(session.session_id, "memory-pool-456")

        assert result is True
        assert manager.sessions[session.session_id].memory_pool_id == "memory-pool-456"

    def test_bind_memory_pool_not_found(self):
        """Test binding memory pool to non-existent session."""
        manager = NexusSessionManager()

        result = manager.bind_memory_pool("non-existent", "memory-pool-456")

        assert result is False

    def test_cleanup_expired_sessions(self):
        """Test cleaning up expired sessions."""
        manager = NexusSessionManager()

        # Create active session
        active = manager.create_session(user_id="user-active", ttl_hours=1)

        # Create expired session
        expired = manager.create_session(user_id="user-expired", ttl_hours=0)
        expired.expires_at = datetime.now() - timedelta(seconds=1)
        manager.sessions[expired.session_id] = expired

        count = manager.cleanup_expired_sessions()

        assert count == 1
        assert active.session_id in manager.sessions
        assert expired.session_id not in manager.sessions

    def test_cleanup_interval_auto_cleanup(self):
        """Test automatic cleanup based on interval.

        Note: cleanup_interval=0 is falsy and won't trigger auto-cleanup.
        Use small positive value and set last_cleanup to past time.
        """
        manager = NexusSessionManager(cleanup_interval=1)  # 1 second interval

        # Create expired session
        expired = manager.create_session(user_id="user-expired", ttl_hours=0)
        expired.expires_at = datetime.now() - timedelta(seconds=1)
        manager.sessions[expired.session_id] = expired

        # Set last_cleanup to past to trigger cleanup on next operation
        manager._last_cleanup = datetime.now() - timedelta(seconds=2)

        # Trigger cleanup via create_session
        manager.create_session(user_id="user-new")

        assert expired.session_id not in manager.sessions


class TestCrossChannelSync:
    """Test cross-channel state synchronization."""

    def test_api_to_cli_sync(self):
        """Test state syncs from API to CLI."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # API updates state
        manager.update_session_state(
            session.session_id, {"message": "Hello from API"}, channel="api"
        )

        # CLI retrieves state
        cli_state = manager.get_session_state(session.session_id, channel="cli")

        assert cli_state["message"] == "Hello from API"
        assert "api" in manager.sessions[session.session_id].channel_activity
        assert "cli" in manager.sessions[session.session_id].channel_activity

    def test_cli_to_mcp_sync(self):
        """Test state syncs from CLI to MCP."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # CLI updates state
        manager.update_session_state(
            session.session_id, {"command": "process-data"}, channel="cli"
        )

        # MCP retrieves state
        mcp_state = manager.get_session_state(session.session_id, channel="mcp")

        assert mcp_state["command"] == "process-data"
        assert "cli" in manager.sessions[session.session_id].channel_activity
        assert "mcp" in manager.sessions[session.session_id].channel_activity

    def test_mcp_to_api_sync(self):
        """Test state syncs from MCP to API."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # MCP updates state
        manager.update_session_state(
            session.session_id, {"tool_result": "success"}, channel="mcp"
        )

        # API retrieves state
        api_state = manager.get_session_state(session.session_id, channel="api")

        assert api_state["tool_result"] == "success"
        assert "mcp" in manager.sessions[session.session_id].channel_activity
        assert "api" in manager.sessions[session.session_id].channel_activity

    def test_multi_channel_consistency(self):
        """Test all channels see same state."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # API updates
        manager.update_session_state(
            session.session_id, {"key1": "value1"}, channel="api"
        )

        # CLI updates
        manager.update_session_state(
            session.session_id, {"key2": "value2"}, channel="cli"
        )

        # MCP updates
        manager.update_session_state(
            session.session_id, {"key3": "value3"}, channel="mcp"
        )

        # All channels should see combined state
        api_state = manager.get_session_state(session.session_id, channel="api")
        cli_state = manager.get_session_state(session.session_id, channel="cli")
        mcp_state = manager.get_session_state(session.session_id, channel="mcp")

        expected_state = {"key1": "value1", "key2": "value2", "key3": "value3"}
        assert api_state == expected_state
        assert cli_state == expected_state
        assert mcp_state == expected_state


class TestMemoryIntegration:
    """Test session integration with SharedMemoryPool."""

    def test_session_memory_binding(self):
        """Test sessions bind to SharedMemoryPool."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        result = manager.bind_memory_pool(session.session_id, "shared-pool-789")

        assert result is True
        assert session.memory_pool_id == "shared-pool-789"

    def test_memory_state_sync(self):
        """Test session state syncs with memory pool."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # Bind to memory pool
        manager.bind_memory_pool(session.session_id, "pool-123")

        # Update state with memory-related data
        manager.update_session_state(
            session.session_id,
            {"memory_pool_id": "pool-123", "agent_memories": ["memory1", "memory2"]},
        )

        state = manager.get_session_state(session.session_id)
        assert state["memory_pool_id"] == "pool-123"
        assert state["agent_memories"] == ["memory1", "memory2"]

    def test_cross_agent_memory_access(self):
        """Test agents share memory via session."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # Bind to shared memory pool
        manager.bind_memory_pool(session.session_id, "shared-pool")

        # Agent 1 stores memory
        manager.update_session_state(
            session.session_id,
            {
                "agent1_data": "context from agent 1",
                "shared_context": "available to all",
            },
            channel="api",
        )

        # Agent 2 accesses memory
        agent2_state = manager.get_session_state(session.session_id, channel="cli")

        assert agent2_state["agent1_data"] == "context from agent 1"
        assert agent2_state["shared_context"] == "available to all"


class TestMultiUserIsolation:
    """Test session isolation between users."""

    def test_sessions_isolated_per_user(self):
        """Test sessions are isolated per user."""
        manager = NexusSessionManager()

        # Create sessions for different users
        session1 = manager.create_session(user_id="user-1")
        session2 = manager.create_session(user_id="user-2")

        # Update states independently
        manager.update_session_state(session1.session_id, {"data": "user1-data"})
        manager.update_session_state(session2.session_id, {"data": "user2-data"})

        # Verify isolation
        state1 = manager.get_session_state(session1.session_id)
        state2 = manager.get_session_state(session2.session_id)

        assert state1["data"] == "user1-data"
        assert state2["data"] == "user2-data"
        assert state1 != state2
