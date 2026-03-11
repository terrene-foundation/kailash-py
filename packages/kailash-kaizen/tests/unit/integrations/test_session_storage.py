"""
Unit tests for SessionStorage DataFlow persistence.

Tests the storage backend that persists cross-channel sessions to database
using DataFlow-generated nodes.

Note: These tests focus on:
1. Record conversion logic (to_db_record, from_db_record)
2. Manager integration with storage backend

The actual storage operations (save, load, update) require DataFlow
to be properly configured and are tested in integration tests.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from kaizen.integrations.nexus.session_manager import (
    CrossChannelSession,
    NexusSessionManager,
)

# Check if DataFlow is available
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False


# Create test session helper
def create_test_session(
    session_id: str = "sess-001",
    user_id: str = "user-123",
    ttl_hours: int = 1,
    state: dict = None,
    channel_activity: dict = None,
    memory_pool_id: str = None,
) -> CrossChannelSession:
    """Create a test session."""
    now = datetime.now()
    session = CrossChannelSession(
        session_id=session_id,
        user_id=user_id,
        created_at=now,
        last_accessed=now,
        expires_at=now + timedelta(hours=ttl_hours),
        state=state or {"key": "value"},
        channel_activity=channel_activity or {},
        memory_pool_id=memory_pool_id,
    )
    return session


def create_mock_storage():
    """Create a storage instance for testing without DataFlow dependency."""
    from kaizen.integrations.nexus.storage import SessionStorage

    storage = object.__new__(SessionStorage)
    storage.db = MagicMock()
    storage._models = {}
    storage.runtime = AsyncMock()
    storage.MODEL_NAME = "CrossChannelSession"
    return storage


class TestStorageRecordConversion:
    """Tests for converting between CrossChannelSession and database records."""

    def test_to_db_record_serializes_state(self):
        """Test that state dict is serialized to JSON string."""
        storage = create_mock_storage()

        session = create_test_session(state={"count": 42, "items": ["a", "b"]})
        record = storage._to_db_record(session)

        assert "state_json" in record
        parsed = json.loads(record["state_json"])
        assert parsed["count"] == 42
        assert parsed["items"] == ["a", "b"]

    def test_to_db_record_serializes_channel_activity(self):
        """Test that channel_activity dict is serialized to JSON string."""
        storage = create_mock_storage()

        now = datetime.now()
        session = create_test_session(
            channel_activity={"api": now, "cli": now - timedelta(minutes=5)}
        )
        record = storage._to_db_record(session)

        assert "channel_activity_json" in record
        parsed = json.loads(record["channel_activity_json"])
        assert "api" in parsed
        assert "cli" in parsed

    def test_to_db_record_converts_datetime_to_iso(self):
        """Test that datetime fields are converted to ISO strings."""
        storage = create_mock_storage()

        session = create_test_session()
        record = storage._to_db_record(session)

        assert isinstance(record["last_accessed"], str)
        assert isinstance(record["expires_at"], str)
        # Should be valid ISO format
        datetime.fromisoformat(record["last_accessed"])
        datetime.fromisoformat(record["expires_at"])

    def test_to_db_record_uses_session_id_as_id(self):
        """Test that session_id maps to id field."""
        storage = create_mock_storage()

        session = create_test_session(session_id="my-session-123")
        record = storage._to_db_record(session)

        assert record["id"] == "my-session-123"

    def test_from_db_record_deserializes_state(self):
        """Test that state_json string is deserialized to dict."""
        storage = create_mock_storage()

        record = {
            "id": "sess-001",
            "user_id": "user-123",
            "last_accessed": "2025-01-15T10:00:00",
            "expires_at": "2025-01-15T11:00:00",
            "state_json": '{"key": "value", "count": 42}',
            "channel_activity_json": "{}",
            "created_at": "2025-01-15T09:00:00",
        }

        session = storage._from_db_record(record)

        assert session.state == {"key": "value", "count": 42}
        assert isinstance(session.state, dict)

    def test_from_db_record_deserializes_channel_activity(self):
        """Test that channel_activity_json string is deserialized to dict."""
        storage = create_mock_storage()

        record = {
            "id": "sess-001",
            "user_id": "user-123",
            "last_accessed": "2025-01-15T10:00:00",
            "expires_at": "2025-01-15T11:00:00",
            "state_json": "{}",
            "channel_activity_json": '{"api": "2025-01-15T10:00:00", "mcp": "2025-01-15T10:05:00"}',
            "created_at": "2025-01-15T09:00:00",
        }

        session = storage._from_db_record(record)

        assert "api" in session.channel_activity
        assert "mcp" in session.channel_activity
        assert isinstance(session.channel_activity["api"], datetime)

    def test_from_db_record_parses_datetime_strings(self):
        """Test that datetime strings are parsed to datetime objects."""
        storage = create_mock_storage()

        record = {
            "id": "sess-001",
            "user_id": "user-123",
            "last_accessed": "2025-01-15T10:30:00",
            "expires_at": "2025-01-15T11:30:00",
            "state_json": "{}",
            "channel_activity_json": "{}",
            "created_at": "2025-01-15T09:00:00",
        }

        session = storage._from_db_record(record)

        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_accessed, datetime)
        assert isinstance(session.expires_at, datetime)
        assert session.last_accessed.hour == 10
        assert session.last_accessed.minute == 30

    def test_from_db_record_handles_memory_pool_id(self):
        """Test that memory_pool_id is preserved."""
        storage = create_mock_storage()

        record = {
            "id": "sess-001",
            "user_id": "user-123",
            "last_accessed": "2025-01-15T10:00:00",
            "expires_at": "2025-01-15T11:00:00",
            "state_json": "{}",
            "channel_activity_json": "{}",
            "created_at": "2025-01-15T09:00:00",
            "memory_pool_id": "pool-456",
        }

        session = storage._from_db_record(record)

        assert session.memory_pool_id == "pool-456"

    def test_roundtrip_conversion_preserves_data(self):
        """Test that converting to record and back preserves all data."""
        storage = create_mock_storage()

        now = datetime.now()
        original = create_test_session(
            session_id="roundtrip-001",
            user_id="user-abc",
            state={"key": "value", "nested": {"inner": 123}},
            channel_activity={"api": now, "cli": now - timedelta(minutes=10)},
            memory_pool_id="pool-xyz",
        )

        # Convert to record and back
        record = storage._to_db_record(original)
        record["created_at"] = original.created_at.isoformat()
        restored = storage._from_db_record(record)

        # Verify key fields preserved
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.state == original.state
        assert restored.memory_pool_id == original.memory_pool_id
        # Channel activity keys preserved
        assert set(restored.channel_activity.keys()) == set(
            original.channel_activity.keys()
        )


@pytest.mark.skipif(
    not DATAFLOW_AVAILABLE,
    reason="DataFlow not installed - storage operations require DataFlow",
)
class TestStorageOperations:
    """
    Tests for storage CRUD operations.

    Note: These tests require DataFlow to be properly configured since
    the storage methods create workflows with DataFlow-generated nodes.
    The tests are skipped when DataFlow is not available.

    For unit testing of the manager integration with storage, see
    TestSessionManagerIntegration which uses mocked storage backends.
    """

    pass  # Integration tests go in tests/integration/integrations/


class TestSessionManagerIntegration:
    """Tests for session manager integration with storage backend."""

    @pytest.mark.asyncio
    async def test_create_session_async_persists_to_storage(self):
        """Test that create_session_async saves to storage when configured."""
        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="sess-001")

        manager = NexusSessionManager(storage_backend=mock_storage)

        session = await manager.create_session_async(user_id="user-123")

        # Verify storage.save was called
        mock_storage.save.assert_called_once()
        saved_session = mock_storage.save.call_args[0][0]
        assert saved_session.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_update_session_state_async_persists(self):
        """Test that update_session_state_async updates storage."""
        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="sess-001")
        mock_storage.update = AsyncMock()

        manager = NexusSessionManager(storage_backend=mock_storage)

        session = await manager.create_session_async(user_id="user-123")

        # Update state
        success = await manager.update_session_state_async(
            session.session_id, {"new_key": "new_value"}, channel="api"
        )

        assert success is True
        mock_storage.update.assert_called_once()
        updated_session = mock_storage.update.call_args[0][0]
        assert updated_session.state["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_bind_memory_pool_async_persists(self):
        """Test that bind_memory_pool_async updates storage."""
        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="sess-001")
        mock_storage.update = AsyncMock()

        manager = NexusSessionManager(storage_backend=mock_storage)

        session = await manager.create_session_async(user_id="user-123")

        # Bind memory pool
        success = await manager.bind_memory_pool_async(session.session_id, "pool-456")

        assert success is True
        mock_storage.update.assert_called_once()
        updated_session = mock_storage.update.call_args[0][0]
        assert updated_session.memory_pool_id == "pool-456"

    @pytest.mark.asyncio
    async def test_delete_session_async_removes_from_storage(self):
        """Test that delete_session_async removes from storage."""
        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="sess-001")
        mock_storage.delete = AsyncMock(return_value=True)

        manager = NexusSessionManager(storage_backend=mock_storage)

        session = await manager.create_session_async(user_id="user-123")

        # Delete session
        deleted = await manager.delete_session_async(session.session_id)

        assert deleted is True
        mock_storage.delete.assert_called_once_with(session.session_id)
        assert session.session_id not in manager.sessions

    @pytest.mark.asyncio
    async def test_load_session_async_from_storage(self):
        """Test that load_session_async loads from storage."""
        mock_storage = AsyncMock()

        # Create a session to return
        loaded_session = create_test_session(
            session_id="sess-from-storage",
            user_id="storage-user",
        )
        mock_storage.load = AsyncMock(return_value=loaded_session)

        manager = NexusSessionManager(storage_backend=mock_storage)

        # Session not in memory
        assert "sess-from-storage" not in manager.sessions

        # Load from storage
        session = await manager.load_session_async("sess-from-storage")

        assert session is not None
        assert session.session_id == "sess-from-storage"
        assert session.user_id == "storage-user"
        # Should now be cached in memory
        assert "sess-from-storage" in manager.sessions

    @pytest.mark.asyncio
    async def test_load_session_async_uses_cache_first(self):
        """Test that load_session_async uses memory cache before storage."""
        mock_storage = AsyncMock()
        mock_storage.save = AsyncMock(return_value="sess-001")
        mock_storage.load = AsyncMock()

        manager = NexusSessionManager(storage_backend=mock_storage)

        # Create session (stored in memory)
        session = await manager.create_session_async(user_id="user-123")

        # Load should use memory cache
        loaded = await manager.load_session_async(session.session_id)

        assert loaded is not None
        assert loaded.session_id == session.session_id
        # Storage.load should NOT be called (used cache)
        mock_storage.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_async_cleans_storage(self):
        """Test that cleanup also cleans storage."""
        mock_storage = AsyncMock()
        mock_storage.cleanup_expired = AsyncMock(return_value=5)

        manager = NexusSessionManager(storage_backend=mock_storage)

        # Create and expire a session
        session = manager.create_session(user_id="user-123", ttl_hours=0)
        session.expires_at = datetime.now() - timedelta(seconds=1)

        # Cleanup
        count = await manager.cleanup_expired_sessions_async()

        assert count >= 1
        mock_storage.cleanup_expired.assert_called_once()

    @pytest.mark.asyncio
    async def test_operations_work_without_storage_backend(self):
        """Test that sync operations work without storage backend."""
        # No storage backend
        manager = NexusSessionManager(storage_backend=None)

        # These should work without errors
        session = manager.create_session(user_id="user-123")
        manager.update_session_state(session.session_id, {"key": "value"})
        manager.bind_memory_pool(session.session_id, "pool-456")

        # Verify in-memory storage
        assert manager.sessions[session.session_id].state["key"] == "value"
        assert manager.sessions[session.session_id].memory_pool_id == "pool-456"

    @pytest.mark.asyncio
    async def test_async_operations_work_without_storage_backend(self):
        """Test that async operations work without storage backend."""
        # No storage backend
        manager = NexusSessionManager(storage_backend=None)

        # These should work without errors
        session = await manager.create_session_async(user_id="user-123")
        await manager.update_session_state_async(session.session_id, {"key": "value"})

        # Verify in-memory storage
        assert manager.sessions[session.session_id].state["key"] == "value"
