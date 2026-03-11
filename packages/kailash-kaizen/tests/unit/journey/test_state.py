"""
Unit tests for JourneyStateManager and StateBackend implementations (TODO-JO-004).

Tests cover:
- REQ-PM-003: JourneyStateManager class
- StateBackend abstract interface
- MemoryStateBackend (in-memory storage)
- Session serialization/deserialization
- JourneySession dataclass

These are Tier 1 (Unit) tests that don't require real infrastructure.
DataFlowStateBackend tests are in integration tests (require real database).
"""

from datetime import datetime
from typing import Any, Dict

import pytest

from kaizen.journey import JourneyConfig
from kaizen.journey.errors import StateError
from kaizen.journey.state import (
    DataFlowStateBackend,
    JourneySession,
    JourneyStateManager,
    MemoryStateBackend,
    StateBackend,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def config():
    """Create default JourneyConfig."""
    return JourneyConfig()


@pytest.fixture
def memory_backend():
    """Create MemoryStateBackend instance."""
    return MemoryStateBackend()


@pytest.fixture
def state_manager(config):
    """Create JourneyStateManager instance."""
    return JourneyStateManager(config)


@pytest.fixture
def sample_session():
    """Create sample JourneySession."""
    return JourneySession(
        session_id="test-session-123",
        journey_class=None,  # Set by PathwayManager during restore
        current_pathway_id="intake",
        pathway_stack=["intake"],
        conversation_history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        accumulated_context={"name": "Alice", "email": "alice@example.com"},
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 30, 0),
    )


# ============================================================================
# JourneySession Dataclass Tests
# ============================================================================


class TestJourneySession:
    """Tests for JourneySession dataclass."""

    def test_create_session(self):
        """Test creating JourneySession."""
        session = JourneySession(
            session_id="session-123",
            journey_class=None,
            current_pathway_id="intake",
        )

        assert session.session_id == "session-123"
        assert session.journey_class is None
        assert session.current_pathway_id == "intake"
        assert session.pathway_stack == []
        assert session.conversation_history == []
        assert session.accumulated_context == {}

    def test_session_with_all_fields(self, sample_session):
        """Test session with all fields populated."""
        assert sample_session.session_id == "test-session-123"
        assert sample_session.current_pathway_id == "intake"
        assert sample_session.pathway_stack == ["intake"]
        assert len(sample_session.conversation_history) == 2
        assert sample_session.accumulated_context["name"] == "Alice"

    def test_session_defaults(self):
        """Test session default values."""
        session = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="main",
        )

        assert session.pathway_stack == []
        assert session.conversation_history == []
        assert session.accumulated_context == {}
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)


# ============================================================================
# StateBackend Abstract Interface Tests
# ============================================================================


class TestStateBackendInterface:
    """Tests for StateBackend abstract interface."""

    def test_abstract_methods_defined(self):
        """Test that StateBackend defines required abstract methods."""
        methods = ["save", "load", "delete", "list_sessions"]
        for method in methods:
            assert hasattr(StateBackend, method)

    def test_cannot_instantiate_abstract(self):
        """Test that StateBackend cannot be instantiated."""
        with pytest.raises(TypeError):
            StateBackend()


# ============================================================================
# MemoryStateBackend Tests
# ============================================================================


class TestMemoryStateBackend:
    """Tests for MemoryStateBackend."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, memory_backend):
        """Test saving and loading session."""
        data = {"key": "value", "nested": {"a": 1}}

        await memory_backend.save("session-1", data)
        loaded = await memory_backend.load("session-1")

        assert loaded == data

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, memory_backend):
        """Test loading non-existent session returns None."""
        loaded = await memory_backend.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_save_creates_copy(self, memory_backend):
        """Test that save creates a copy of data."""
        data = {"key": "original"}

        await memory_backend.save("session-1", data)
        data["key"] = "modified"  # Modify original

        loaded = await memory_backend.load("session-1")
        assert loaded["key"] == "original"  # Should not be modified

    @pytest.mark.asyncio
    async def test_load_returns_copy(self, memory_backend):
        """Test that load returns a copy of data."""
        data = {"key": "value"}
        await memory_backend.save("session-1", data)

        loaded1 = await memory_backend.load("session-1")
        loaded2 = await memory_backend.load("session-1")

        assert loaded1 is not loaded2
        assert loaded1 == loaded2

    @pytest.mark.asyncio
    async def test_delete(self, memory_backend):
        """Test deleting session."""
        await memory_backend.save("session-1", {"key": "value"})
        await memory_backend.delete("session-1")

        loaded = await memory_backend.load("session-1")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, memory_backend):
        """Test deleting non-existent session doesn't raise."""
        await memory_backend.delete("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_list_sessions(self, memory_backend):
        """Test listing all sessions."""
        await memory_backend.save("session-1", {"a": 1})
        await memory_backend.save("session-2", {"b": 2})
        await memory_backend.save("session-3", {"c": 3})

        sessions = await memory_backend.list_sessions()

        assert len(sessions) == 3
        assert "session-1" in sessions
        assert "session-2" in sessions
        assert "session-3" in sessions

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, memory_backend):
        """Test listing sessions when empty."""
        sessions = await memory_backend.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_exists(self, memory_backend):
        """Test exists method."""
        await memory_backend.save("session-1", {"key": "value"})

        assert await memory_backend.exists("session-1") is True
        assert await memory_backend.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear(self, memory_backend):
        """Test clearing all sessions."""
        await memory_backend.save("session-1", {"a": 1})
        await memory_backend.save("session-2", {"b": 2})

        memory_backend.clear()

        sessions = await memory_backend.list_sessions()
        assert sessions == []

    @pytest.mark.asyncio
    async def test_get_size(self, memory_backend):
        """Test getting storage size."""
        assert memory_backend.get_size() == 0

        await memory_backend.save("session-1", {"a": 1})
        assert memory_backend.get_size() == 1

        await memory_backend.save("session-2", {"b": 2})
        assert memory_backend.get_size() == 2


# ============================================================================
# JourneyStateManager Initialization Tests
# ============================================================================


class TestJourneyStateManagerInit:
    """Tests for JourneyStateManager initialization."""

    def test_init_with_memory_config(self):
        """Test initialization with memory persistence config."""
        config = JourneyConfig(context_persistence="memory")
        manager = JourneyStateManager(config)

        assert manager.config is config
        assert isinstance(manager._backend, MemoryStateBackend)

    def test_init_default_backend(self, state_manager):
        """Test default backend is MemoryStateBackend."""
        assert isinstance(state_manager.get_backend(), MemoryStateBackend)

    def test_set_backend(self, state_manager, memory_backend):
        """Test setting custom backend."""
        custom_backend = MemoryStateBackend()
        state_manager.set_backend(custom_backend)

        assert state_manager.get_backend() is custom_backend


# ============================================================================
# JourneyStateManager Session Operations Tests
# ============================================================================


class TestJourneyStateManagerOperations:
    """Tests for JourneyStateManager session operations."""

    @pytest.mark.asyncio
    async def test_save_session(self, state_manager, sample_session):
        """Test saving a session."""
        await state_manager.save_session(sample_session)

        # Verify by loading
        loaded = await state_manager.load_session(sample_session.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_session.session_id
        assert loaded.current_pathway_id == sample_session.current_pathway_id

    @pytest.mark.asyncio
    async def test_load_session(self, state_manager, sample_session):
        """Test loading a session."""
        await state_manager.save_session(sample_session)
        loaded = await state_manager.load_session(sample_session.session_id)

        assert loaded.session_id == sample_session.session_id
        assert loaded.current_pathway_id == sample_session.current_pathway_id
        assert loaded.pathway_stack == sample_session.pathway_stack
        assert loaded.conversation_history == sample_session.conversation_history
        assert loaded.accumulated_context == sample_session.accumulated_context

    @pytest.mark.asyncio
    async def test_load_nonexistent_session(self, state_manager):
        """Test loading non-existent session returns None."""
        loaded = await state_manager.load_session("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_session(self, state_manager, sample_session):
        """Test deleting a session."""
        await state_manager.save_session(sample_session)
        await state_manager.delete_session(sample_session.session_id)

        loaded = await state_manager.load_session(sample_session.session_id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_sessions(self, state_manager):
        """Test listing all sessions."""
        session1 = JourneySession(
            session_id="session-1",
            journey_class=None,
            current_pathway_id="intake",
        )
        session2 = JourneySession(
            session_id="session-2",
            journey_class=None,
            current_pathway_id="booking",
        )

        await state_manager.save_session(session1)
        await state_manager.save_session(session2)

        sessions = await state_manager.list_sessions()

        assert len(sessions) == 2
        assert "session-1" in sessions
        assert "session-2" in sessions

    @pytest.mark.asyncio
    async def test_session_exists(self, state_manager, sample_session):
        """Test checking session existence."""
        assert await state_manager.session_exists(sample_session.session_id) is False

        await state_manager.save_session(sample_session)

        assert await state_manager.session_exists(sample_session.session_id) is True


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Tests for session serialization/deserialization."""

    def test_serialize_session(self, state_manager, sample_session):
        """Test session serialization."""
        data = state_manager._serialize_session(sample_session)

        assert data["session_id"] == sample_session.session_id
        assert data["current_pathway_id"] == sample_session.current_pathway_id
        assert data["pathway_stack"] == sample_session.pathway_stack
        assert data["conversation_history"] == sample_session.conversation_history
        assert data["accumulated_context"] == sample_session.accumulated_context

    def test_serialize_preserves_timestamps(self, state_manager, sample_session):
        """Test that serialization preserves timestamps as ISO strings."""
        data = state_manager._serialize_session(sample_session)

        assert "created_at" in data
        assert "updated_at" in data
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

    def test_deserialize_session(self, state_manager, sample_session):
        """Test session deserialization."""
        data = state_manager._serialize_session(sample_session)
        restored = state_manager._deserialize_session(data)

        assert restored.session_id == sample_session.session_id
        assert restored.current_pathway_id == sample_session.current_pathway_id
        assert restored.pathway_stack == sample_session.pathway_stack
        assert restored.conversation_history == sample_session.conversation_history
        assert restored.accumulated_context == sample_session.accumulated_context

    def test_deserialize_handles_missing_fields(self, state_manager):
        """Test deserialization handles missing optional fields."""
        minimal_data = {
            "session_id": "test",
            "current_pathway_id": "main",
        }

        restored = state_manager._deserialize_session(minimal_data)

        assert restored.session_id == "test"
        assert restored.current_pathway_id == "main"
        assert restored.pathway_stack == []
        assert restored.conversation_history == []
        assert restored.accumulated_context == {}

    def test_deserialize_handles_string_timestamps(self, state_manager):
        """Test deserialization handles string timestamps."""
        data = {
            "session_id": "test",
            "current_pathway_id": "main",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:30:00",
        }

        restored = state_manager._deserialize_session(data)

        assert isinstance(restored.created_at, datetime)
        assert isinstance(restored.updated_at, datetime)

    def test_journey_class_serialized_as_string(self, state_manager):
        """Test that journey_class is serialized as module.classname string."""

        # Create a session with a mock journey class
        class MockJourney:
            pass

        session = JourneySession(
            session_id="test",
            journey_class=MockJourney,
            current_pathway_id="main",
        )

        data = state_manager._serialize_session(session)

        # journey_class should be a string (module.classname)
        assert isinstance(data["journey_class"], str)
        assert "MockJourney" in data["journey_class"]

    def test_journey_class_none_after_deserialize(self, state_manager):
        """Test that journey_class is None after deserialization."""
        data = {
            "session_id": "test",
            "journey_class": "some.module.JourneyClass",
            "current_pathway_id": "main",
        }

        restored = state_manager._deserialize_session(data)

        # journey_class should be None (set by PathwayManager)
        assert restored.journey_class is None


# ============================================================================
# DataFlowStateBackend Tests (Basic - no real DB)
# ============================================================================


class TestDataFlowStateBackendBasic:
    """Basic tests for DataFlowStateBackend (without real database)."""

    def test_init(self):
        """Test DataFlowStateBackend initialization."""
        mock_db = object()  # Mock DataFlow instance
        backend = DataFlowStateBackend(mock_db)

        assert backend.db is mock_db
        assert backend.model_name == "JourneySession"

    def test_init_custom_model_name(self):
        """Test DataFlowStateBackend with custom model name."""
        mock_db = object()
        backend = DataFlowStateBackend(mock_db, model_name="CustomSession")

        assert backend.model_name == "CustomSession"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_save_session_with_complex_context(self, state_manager):
        """Test saving session with complex accumulated context."""
        session = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="main",
            accumulated_context={
                "nested": {"deep": {"value": [1, 2, 3]}},
                "list": ["a", "b", "c"],
                "number": 42.5,
                "boolean": True,
            },
        )

        await state_manager.save_session(session)
        loaded = await state_manager.load_session("test")

        assert loaded.accumulated_context == session.accumulated_context

    @pytest.mark.asyncio
    async def test_multiple_saves_overwrites(self, state_manager):
        """Test that multiple saves to same session_id overwrites."""
        session1 = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="intake",
        )
        session2 = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="booking",
        )

        await state_manager.save_session(session1)
        await state_manager.save_session(session2)

        loaded = await state_manager.load_session("test")
        assert loaded.current_pathway_id == "booking"

    @pytest.mark.asyncio
    async def test_empty_conversation_history(self, state_manager):
        """Test session with empty conversation history."""
        session = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="main",
            conversation_history=[],
        )

        await state_manager.save_session(session)
        loaded = await state_manager.load_session("test")

        assert loaded.conversation_history == []

    @pytest.mark.asyncio
    async def test_unicode_in_context(self, state_manager):
        """Test session with unicode characters in context."""
        session = JourneySession(
            session_id="test",
            journey_class=None,
            current_pathway_id="main",
            accumulated_context={
                "name": "Alice (Alice)",
                "greeting": "Hola, como estas?",
                "emoji": "Hello! How are you?",
            },
        )

        await state_manager.save_session(session)
        loaded = await state_manager.load_session("test")

        assert loaded.accumulated_context == session.accumulated_context
