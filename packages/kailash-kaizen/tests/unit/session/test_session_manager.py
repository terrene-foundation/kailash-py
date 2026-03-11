"""
Unit Tests for Session Manager (Tier 1)

Tests the KaizenSessionManager and storage backends.
Part of TODO-204 Enterprise-App Streaming Integration.

Coverage:
- KaizenSessionManager initialization
- Session lifecycle (start, update, pause, resume, end)
- InMemorySessionStorage
- FilesystemSessionStorage
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from kaizen.session.manager import (
    FilesystemSessionStorage,
    InMemorySessionStorage,
    KaizenSessionManager,
    SessionStorage,
)
from kaizen.session.state import (
    Message,
    SessionState,
    SessionStatus,
    SessionSummary,
    ToolInvocation,
)


class MockAgent:
    """Mock agent for testing."""

    def __init__(self, name: str = "MockAgent", agent_id: str = "mock-001"):
        self.name = name
        self.agent_id = agent_id


class TestInMemorySessionStorage:
    """Test InMemorySessionStorage."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test saving and loading session state."""
        storage = InMemorySessionStorage()

        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )
        state.tokens_used = 100

        await storage.save("session-123", state)
        loaded = await storage.load("session-123")

        assert loaded is not None
        assert loaded.session_id == "session-123"
        assert loaded.tokens_used == 100

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        """Test loading nonexistent session."""
        storage = InMemorySessionStorage()

        loaded = await storage.load("nonexistent")

        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting session."""
        storage = InMemorySessionStorage()

        state = SessionState(
            session_id="session-del",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        await storage.save("session-del", state)
        result = await storage.delete("session-del")
        loaded = await storage.load("session-del")

        assert result is True
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting nonexistent session."""
        storage = InMemorySessionStorage()

        result = await storage.delete("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test listing all sessions."""
        storage = InMemorySessionStorage()

        for i in range(3):
            state = SessionState(
                session_id=f"session-{i}",
                agent_id="agent-001",
                trust_chain_id="chain-abc",
            )
            await storage.save(f"session-{i}", state)

        sessions = await storage.list_sessions()

        assert len(sessions) == 3
        assert "session-0" in sessions
        assert "session-1" in sessions
        assert "session-2" in sessions

    @pytest.mark.asyncio
    async def test_list_sessions_with_status_filter(self):
        """Test listing sessions with status filter."""
        storage = InMemorySessionStorage()

        active_state = SessionState(
            session_id="session-active",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
            status=SessionStatus.ACTIVE,
        )
        paused_state = SessionState(
            session_id="session-paused",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
            status=SessionStatus.PAUSED,
        )

        await storage.save("session-active", active_state)
        await storage.save("session-paused", paused_state)

        sessions = await storage.list_sessions(status=SessionStatus.ACTIVE)

        assert len(sessions) == 1
        assert "session-active" in sessions


class TestFilesystemSessionStorage:
    """Test FilesystemSessionStorage."""

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test saving and loading with filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemSessionStorage(directory=tmpdir)

            state = SessionState(
                session_id="session-fs-123",
                agent_id="agent-001",
                trust_chain_id="chain-abc",
            )
            state.tokens_used = 250

            await storage.save("session-fs-123", state)

            # Verify file exists
            session_file = Path(tmpdir) / "session-fs-123.json"
            assert session_file.exists()

            loaded = await storage.load("session-fs-123")

            assert loaded is not None
            assert loaded.session_id == "session-fs-123"
            assert loaded.tokens_used == 250

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        """Test loading nonexistent session from filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemSessionStorage(directory=tmpdir)

            loaded = await storage.load("nonexistent")

            assert loaded is None

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting session file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemSessionStorage(directory=tmpdir)

            state = SessionState(
                session_id="session-fs-del",
                agent_id="agent-001",
                trust_chain_id="chain-abc",
            )

            await storage.save("session-fs-del", state)
            session_file = Path(tmpdir) / "session-fs-del.json"
            assert session_file.exists()

            result = await storage.delete("session-fs-del")
            assert result is True
            assert not session_file.exists()

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test listing sessions from filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemSessionStorage(directory=tmpdir)

            for i in range(2):
                state = SessionState(
                    session_id=f"session-list-{i}",
                    agent_id="agent-001",
                    trust_chain_id="chain-abc",
                )
                await storage.save(f"session-list-{i}", state)

            sessions = await storage.list_sessions()

            assert len(sessions) == 2


class TestKaizenSessionManager:
    """Test KaizenSessionManager."""

    @pytest.mark.asyncio
    async def test_custom_storage(self):
        """Test custom storage backend."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)

        assert manager._storage is storage

    @pytest.mark.asyncio
    async def test_start_session(self):
        """Test starting a new session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-123",
        )

        assert session_id is not None
        assert session_id.startswith("session-")

        # Verify session was created
        state = await manager.get_session_state(session_id)
        assert state is not None
        assert state.agent_id == "mock-001"
        assert state.trust_chain_id == "chain-123"
        assert state.status == SessionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_start_session_with_custom_id(self):
        """Test starting session with custom ID."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-xyz",
            session_id="custom-session-id",
        )

        assert session_id == "custom-session-id"

    @pytest.mark.asyncio
    async def test_get_session_state(self):
        """Test getting session state."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        state = await manager.get_session_state(session_id)

        assert state is not None
        assert state.session_id == session_id
        assert state.status == SessionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self):
        """Test getting nonexistent session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)

        state = await manager.get_session_state("nonexistent")

        assert state is None

    @pytest.mark.asyncio
    async def test_update_session(self):
        """Test updating session state."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        # Get and modify state
        state = await manager.get_session_state(session_id)
        state.add_message(Message(role="user", content="Hello"))
        state.update_metrics(tokens_added=100)

        await manager.update_session(session_id, state)

        # Reload and verify
        reloaded = await manager.get_session_state(session_id)
        assert len(reloaded.messages) == 1
        assert reloaded.tokens_used == 100

    @pytest.mark.asyncio
    async def test_pause_session(self):
        """Test pausing a session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        await manager.pause_session(session_id)

        state = await manager.get_session_state(session_id)
        assert state.status == SessionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_session(self):
        """Test resuming a paused session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        await manager.pause_session(session_id)
        state = await manager.resume_session(session_id)

        assert state is not None
        assert state.status == SessionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_resume_nonexistent_session(self):
        """Test resuming nonexistent session raises error."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)

        with pytest.raises(ValueError, match="not found"):
            await manager.resume_session("nonexistent")

    @pytest.mark.asyncio
    async def test_end_session_completed(self):
        """Test ending session as completed."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        # Add some data
        state = await manager.get_session_state(session_id)
        state.add_message(Message(role="user", content="Hello"))
        state.update_metrics(tokens_added=500, cost_added_usd=0.025)
        await manager.update_session(session_id, state)

        summary = await manager.end_session(
            session_id=session_id,
            status="completed",
        )

        assert summary is not None
        assert summary.session_id == session_id
        assert summary.status == SessionStatus.COMPLETED
        assert summary.total_tokens == 500
        assert summary.total_messages == 1

    @pytest.mark.asyncio
    async def test_end_session_failed(self):
        """Test ending session as failed."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        summary = await manager.end_session(
            session_id=session_id,
            status="failed",
            error_message="Model error occurred",
        )

        assert summary.status == SessionStatus.FAILED
        assert summary.error_message == "Model error occurred"

    @pytest.mark.asyncio
    async def test_end_nonexistent_session(self):
        """Test ending nonexistent session raises error."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)

        with pytest.raises(ValueError, match="not found"):
            await manager.end_session(
                session_id="nonexistent",
                status="completed",
            )

    @pytest.mark.asyncio
    async def test_add_message(self):
        """Test adding message via manager."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        await manager.add_message(
            session_id=session_id,
            role="user",
            content="Test message",
        )

        state = await manager.get_session_state(session_id)
        assert len(state.messages) == 1
        assert state.messages[0].content == "Test message"

    @pytest.mark.asyncio
    async def test_add_tool_invocation(self):
        """Test adding tool invocation via manager."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        await manager.add_tool_invocation(
            session_id=session_id,
            tool_name="search",
            tool_call_id="call-123",
            input={"query": "test"},
        )

        state = await manager.get_session_state(session_id)
        assert len(state.tool_invocations) == 1
        assert state.tool_invocations[0].tool_name == "search"

    @pytest.mark.asyncio
    async def test_update_metrics(self):
        """Test updating metrics via manager."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        await manager.update_metrics(
            session_id=session_id,
            tokens_added=100,
            cost_added_usd=0.01,
        )

        state = await manager.get_session_state(session_id)
        assert state.tokens_used == 100
        assert state.cost_usd == 0.01

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        """Test listing sessions."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        # Start 3 sessions
        for i in range(3):
            await manager.start_session(
                agent=agent,
                trust_chain_id=f"chain-{i}",
            )

        sessions = await manager.list_sessions()

        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_delete_session(self):
        """Test deleting a session."""
        storage = InMemorySessionStorage()
        manager = KaizenSessionManager(storage=storage)
        agent = MockAgent()

        session_id = await manager.start_session(
            agent=agent,
            trust_chain_id="chain-abc",
        )

        result = await manager.delete_session(session_id)
        state = await manager.get_session_state(session_id)

        assert result is True
        assert state is None


class TestSessionManagerWithFilesystem:
    """Test KaizenSessionManager with filesystem storage."""

    @pytest.mark.asyncio
    async def test_persistence_across_managers(self):
        """Test session persists when manager is recreated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FilesystemSessionStorage(directory=tmpdir)

            # Create session with first manager
            manager1 = KaizenSessionManager(storage=storage)
            agent = MockAgent()

            session_id = await manager1.start_session(
                agent=agent,
                trust_chain_id="chain-persist",
                session_id="persist-test",
            )

            state = await manager1.get_session_state(session_id)
            state.update_metrics(tokens_added=999)
            await manager1.update_session(session_id, state)

            # Create new manager with same storage
            storage2 = FilesystemSessionStorage(directory=tmpdir)
            manager2 = KaizenSessionManager(storage=storage2)
            loaded = await manager2.get_session_state("persist-test")

            assert loaded is not None
            assert loaded.tokens_used == 999
