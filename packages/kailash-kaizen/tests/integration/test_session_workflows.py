"""
Integration tests for Nexus session workflows.

Tests real-world session scenarios across multiple channels.

Phase 3 of TODO-149: Unified Session Management
"""

from dataclasses import dataclass
from time import sleep

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.integrations.nexus import NEXUS_AVAILABLE
from kaizen.signatures import InputField, OutputField, Signature

if not NEXUS_AVAILABLE:
    pytest.skip("Nexus not available", allow_module_level=True)

from kaizen.integrations.nexus.session_manager import NexusSessionManager


# Test fixtures
@dataclass
class ConversationAgentConfig:
    """Configuration for test agent."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"


class ConversationSignature(Signature):
    """Conversation agent signature."""

    message: str = InputField(description="User message")
    context: dict = InputField(description="Conversation context", default_factory=dict)
    response: str = OutputField(description="Agent response")


class ConversationAgent(BaseAgent):
    """Test agent for conversation scenarios."""

    def __init__(self, config: ConversationAgentConfig):
        super().__init__(config=config, signature=ConversationSignature())

    def chat(self, message: str, context: dict = None) -> dict:
        """Chat with context."""
        return self.run(message=message, context=context or {})


class TestMultiChannelConversation:
    """Test conversations spanning multiple channels."""

    def test_conversation_continues_across_channels(self):
        """Test conversation context preserved across channels."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-123")

        # API: Start conversation
        manager.update_session_state(
            session.session_id,
            {
                "conversation_history": [
                    {"role": "user", "content": "What's the weather?"},
                    {"role": "assistant", "content": "I'll check for you."},
                ]
            },
            channel="api",
        )

        # CLI: Continue conversation
        cli_state = manager.get_session_state(session.session_id, channel="cli")
        assert len(cli_state["conversation_history"]) == 2

        manager.update_session_state(
            session.session_id,
            {
                "conversation_history": cli_state["conversation_history"]
                + [{"role": "user", "content": "Thanks!"}]
            },
            channel="cli",
        )

        # MCP: View full conversation
        mcp_state = manager.get_session_state(session.session_id, channel="mcp")
        assert len(mcp_state["conversation_history"]) == 3

        # Verify all channels see same history
        final_api = manager.get_session_state(session.session_id, channel="api")
        final_cli = manager.get_session_state(session.session_id, channel="cli")
        final_mcp = manager.get_session_state(session.session_id, channel="mcp")

        assert final_api == final_cli == final_mcp

    def test_agent_context_preserved(self):
        """Test agent execution context preserved across channels."""
        manager = NexusSessionManager()
        config = ConversationAgentConfig()
        ConversationAgent(config)

        session = manager.create_session(user_id="user-456")

        # API: First message
        manager.update_session_state(
            session.session_id,
            {"user_preferences": {"language": "en"}, "message_count": 1},
            channel="api",
        )

        # CLI: Second message (accesses preferences)
        cli_state = manager.get_session_state(session.session_id, channel="cli")
        assert cli_state["user_preferences"]["language"] == "en"

        manager.update_session_state(
            session.session_id,
            {"message_count": cli_state["message_count"] + 1},
            channel="cli",
        )

        # MCP: Third message
        mcp_state = manager.get_session_state(session.session_id, channel="mcp")
        assert mcp_state["message_count"] == 2


class TestSessionStateRecovery:
    """Test session recovery after disconnect."""

    def test_recover_state_after_disconnect(self):
        """Test state recovery after simulated disconnect."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-789")

        # Establish state
        manager.update_session_state(
            session.session_id,
            {"work_in_progress": True, "data": [1, 2, 3, 4, 5]},
            channel="api",
        )

        # Simulate disconnect (no action needed)

        # Reconnect and recover
        recovered_state = manager.get_session_state(session.session_id, channel="api")

        assert recovered_state["work_in_progress"] is True
        assert recovered_state["data"] == [1, 2, 3, 4, 5]

    def test_session_persistence_during_inactive_period(self):
        """Test session persists during short inactive period."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-inactive", ttl_hours=1)

        manager.update_session_state(
            session.session_id, {"important_data": "must-persist"}
        )

        # Simulate brief inactivity
        sleep(0.1)

        # Verify still accessible
        state = manager.get_session_state(session.session_id)
        assert state is not None
        assert state["important_data"] == "must-persist"


class TestConcurrentChannelAccess:
    """Test multiple channels accessing session simultaneously."""

    def test_concurrent_channel_reads(self):
        """Test multiple channels can read session simultaneously."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-concurrent")

        manager.update_session_state(
            session.session_id, {"shared_data": "accessible-by-all"}
        )

        # Simulate concurrent reads
        api_state = manager.get_session_state(session.session_id, channel="api")
        cli_state = manager.get_session_state(session.session_id, channel="cli")
        mcp_state = manager.get_session_state(session.session_id, channel="mcp")

        assert api_state["shared_data"] == "accessible-by-all"
        assert cli_state["shared_data"] == "accessible-by-all"
        assert mcp_state["shared_data"] == "accessible-by-all"

    def test_concurrent_channel_writes(self):
        """Test multiple channels can write to session."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-writes")

        # Concurrent writes from different channels
        manager.update_session_state(
            session.session_id, {"api_data": "from-api"}, channel="api"
        )

        manager.update_session_state(
            session.session_id, {"cli_data": "from-cli"}, channel="cli"
        )

        manager.update_session_state(
            session.session_id, {"mcp_data": "from-mcp"}, channel="mcp"
        )

        # Verify all writes preserved
        final_state = manager.get_session_state(session.session_id)
        assert final_state["api_data"] == "from-api"
        assert final_state["cli_data"] == "from-cli"
        assert final_state["mcp_data"] == "from-mcp"

    def test_state_merging_on_update(self):
        """Test concurrent updates merge correctly."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-merge")

        # Initial state
        manager.update_session_state(session.session_id, {"counter": 0, "data": []})

        # Concurrent updates (simulated)
        state1 = manager.get_session_state(session.session_id, channel="api")
        manager.update_session_state(
            session.session_id, {"counter": state1["counter"] + 1}, channel="api"
        )

        state2 = manager.get_session_state(session.session_id, channel="cli")
        manager.update_session_state(
            session.session_id, {"data": state2["data"] + ["item1"]}, channel="cli"
        )

        # Verify both updates applied
        final_state = manager.get_session_state(session.session_id)
        assert final_state["counter"] == 1
        assert final_state["data"] == ["item1"]


class TestSessionMemoryPersistence:
    """Test memory persistence via sessions."""

    def test_memory_persists_across_requests(self):
        """Test memory data persists across multiple requests."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-memory")

        # Bind to memory pool
        manager.bind_memory_pool(session.session_id, "memory-pool-xyz")

        # Store memory in session
        manager.update_session_state(
            session.session_id,
            {
                "agent_memories": [
                    {
                        "timestamp": "2025-01-01",
                        "content": "User prefers concise responses",
                    }
                ]
            },
        )

        # Later request accesses memory
        state = manager.get_session_state(session.session_id)
        assert len(state["agent_memories"]) == 1
        assert "concise responses" in state["agent_memories"][0]["content"]

    def test_shared_memory_across_agents(self):
        """Test multiple agents share memory via session."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-shared")

        # Bind to shared pool
        manager.bind_memory_pool(session.session_id, "shared-pool-abc")

        # Agent 1 stores context
        manager.update_session_state(
            session.session_id,
            {"shared_context": {"user_goal": "analyze data", "progress": "50%"}},
            channel="api",
        )

        # Agent 2 accesses context
        cli_state = manager.get_session_state(session.session_id, channel="cli")
        assert cli_state["shared_context"]["user_goal"] == "analyze data"

        # Agent 2 updates progress
        manager.update_session_state(
            session.session_id,
            {"shared_context": {"user_goal": "analyze data", "progress": "100%"}},
            channel="cli",
        )

        # Agent 1 sees update
        api_state = manager.get_session_state(session.session_id, channel="api")
        assert api_state["shared_context"]["progress"] == "100%"

    def test_memory_cleanup_on_expiration(self):
        """Test memory cleaned up when session expires."""
        from datetime import datetime, timedelta

        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-cleanup", ttl_hours=1)

        # Store memory
        manager.update_session_state(
            session.session_id, {"memory_data": "should-be-cleaned"}
        )

        # Expire session (set to past)
        session.expires_at = datetime.now() - timedelta(seconds=1)

        # Cleanup
        count = manager.cleanup_expired_sessions()
        assert count == 1

        # Verify session and memory gone
        state = manager.get_session_state(session.session_id)
        assert state is None


class TestChannelActivityTracking:
    """Test channel activity tracking."""

    def test_track_channel_usage(self):
        """Test tracking which channels are used."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-tracking")

        # Use different channels
        manager.update_session_state(session.session_id, {"data": "1"}, channel="api")
        sleep(0.01)
        manager.update_session_state(session.session_id, {"data": "2"}, channel="cli")
        sleep(0.01)
        manager.update_session_state(session.session_id, {"data": "3"}, channel="mcp")

        # Verify tracking
        tracked_session = manager.get_session(session.session_id)
        assert "api" in tracked_session.channel_activity
        assert "cli" in tracked_session.channel_activity
        assert "mcp" in tracked_session.channel_activity

        # Verify ordering (later channels have later timestamps)
        assert (
            tracked_session.channel_activity["api"]
            < tracked_session.channel_activity["mcp"]
        )

    def test_last_accessed_channel(self):
        """Test identifying last accessed channel."""
        manager = NexusSessionManager()
        session = manager.create_session(user_id="user-last-access")

        manager.get_session_state(session.session_id, channel="api")
        sleep(0.01)
        manager.get_session_state(session.session_id, channel="cli")

        tracked_session = manager.get_session(session.session_id)
        channels = sorted(
            tracked_session.channel_activity.items(), key=lambda x: x[1], reverse=True
        )

        assert channels[0][0] == "cli"  # Last accessed
