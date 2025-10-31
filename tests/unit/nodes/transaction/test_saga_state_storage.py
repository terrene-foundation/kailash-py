"""Unit tests for Saga State Storage implementations."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.transaction.saga_state_storage import (
    DatabaseStateStorage,
    InMemoryStateStorage,
    RedisStateStorage,
    StorageFactory,
)


class TestInMemoryStateStorage:
    """Test suite for InMemoryStateStorage."""

    @pytest.fixture
    def storage(self):
        """Create an InMemoryStateStorage instance."""
        return InMemoryStateStorage()

    @pytest.mark.asyncio
    async def test_save_and_load_state(self, storage):
        """Test saving and loading saga state."""
        saga_id = "test_saga_123"
        state_data = {
            "saga_id": saga_id,
            "saga_name": "test_saga",
            "state": "running",
            "context": {"user_id": "user123"},
        }

        # Save state
        success = await storage.save_state(saga_id, state_data)
        assert success is True

        # Load state
        loaded_data = await storage.load_state(saga_id)
        assert loaded_data == state_data

    @pytest.mark.asyncio
    async def test_load_nonexistent_state(self, storage):
        """Test loading a non-existent saga."""
        result = await storage.load_state("nonexistent_saga")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_state(self, storage):
        """Test deleting saga state."""
        saga_id = "test_saga_456"
        state_data = {"saga_id": saga_id, "state": "completed"}

        # Save and verify
        await storage.save_state(saga_id, state_data)
        assert await storage.load_state(saga_id) is not None

        # Delete
        success = await storage.delete_state(saga_id)
        assert success is True

        # Verify deleted
        assert await storage.load_state(saga_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_state(self, storage):
        """Test deleting non-existent saga."""
        success = await storage.delete_state("nonexistent_saga")
        assert success is False

    @pytest.mark.asyncio
    async def test_list_sagas_no_filter(self, storage):
        """Test listing all sagas without filter."""
        # Save multiple sagas
        await storage.save_state("saga1", {"state": "running"})
        await storage.save_state("saga2", {"state": "completed"})
        await storage.save_state("saga3", {"state": "running"})

        # List all
        saga_ids = await storage.list_sagas()
        assert set(saga_ids) == {"saga1", "saga2", "saga3"}

    @pytest.mark.asyncio
    async def test_list_sagas_with_filter(self, storage):
        """Test listing sagas with filter criteria."""
        # Save sagas with different states
        await storage.save_state("saga1", {"state": "running", "type": "order"})
        await storage.save_state("saga2", {"state": "completed", "type": "payment"})
        await storage.save_state("saga3", {"state": "running", "type": "payment"})

        # Filter by state
        saga_ids = await storage.list_sagas({"state": "running"})
        assert set(saga_ids) == {"saga1", "saga3"}

        # Filter by type
        saga_ids = await storage.list_sagas({"type": "payment"})
        assert set(saga_ids) == {"saga2", "saga3"}


class TestRedisStateStorage:
    """Test suite for RedisStateStorage."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.get = AsyncMock()
        mock.delete = AsyncMock(return_value=1)
        mock.sadd = AsyncMock()
        mock.srem = AsyncMock()
        mock.smembers = AsyncMock(return_value=set())
        return mock

    @pytest.fixture
    def storage(self, mock_redis):
        """Create a RedisStateStorage instance."""
        return RedisStateStorage(mock_redis)

    @pytest.mark.asyncio
    async def test_save_state_pending(self, storage, mock_redis):
        """Test saving pending saga state."""
        saga_id = "test_saga"
        state_data = {
            "saga_id": saga_id,
            "state": "pending",
            "context": {"test": "data"},
        }

        success = await storage.save_state(saga_id, state_data)
        assert success is True

        # Verify Redis calls
        mock_redis.set.assert_called_once()
        key, value = mock_redis.set.call_args[0]
        assert key == "saga:state:test_saga"
        assert json.loads(value)["saga_id"] == saga_id

        # Verify index updates
        mock_redis.sadd.assert_any_call("saga:state:index", saga_id)
        mock_redis.sadd.assert_any_call("saga:state:state:pending", saga_id)

    @pytest.mark.asyncio
    async def test_save_state_completed_with_ttl(self, storage, mock_redis):
        """Test saving completed saga state with TTL."""
        saga_id = "completed_saga"
        state_data = {
            "saga_id": saga_id,
            "state": "completed",
        }

        await storage.save_state(saga_id, state_data)

        # Verify setex was called for completed state
        mock_redis.setex.assert_called_once()
        key, ttl, value = mock_redis.setex.call_args[0]
        assert key == "saga:state:completed_saga"
        assert ttl == 604800  # 7 days

    @pytest.mark.asyncio
    async def test_load_state(self, storage, mock_redis):
        """Test loading saga state."""
        saga_id = "test_saga"
        state_data = {"saga_id": saga_id, "state": "running"}
        mock_redis.get.return_value = json.dumps(state_data)

        loaded_data = await storage.load_state(saga_id)
        assert loaded_data == state_data

        mock_redis.get.assert_called_with("saga:state:test_saga")

    @pytest.mark.asyncio
    async def test_load_state_not_found(self, storage, mock_redis):
        """Test loading non-existent saga."""
        mock_redis.get.return_value = None

        result = await storage.load_state("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_state(self, storage, mock_redis):
        """Test deleting saga state."""
        saga_id = "test_saga"
        state_data = {"saga_id": saga_id, "state": "failed"}

        # Mock load_state for cleanup
        with patch.object(storage, "load_state", return_value=state_data):
            success = await storage.delete_state(saga_id)
            assert success is True

        # Verify delete and index cleanup
        mock_redis.delete.assert_called_with("saga:state:test_saga")
        mock_redis.srem.assert_any_call("saga:state:index", saga_id)
        mock_redis.srem.assert_any_call("saga:state:state:failed", saga_id)

    @pytest.mark.asyncio
    async def test_list_sagas_by_state(self, storage, mock_redis):
        """Test listing sagas filtered by state."""
        mock_redis.smembers.return_value = {"saga1", "saga2"}

        saga_ids = await storage.list_sagas({"state": "running"})
        assert set(saga_ids) == {"saga1", "saga2"}

        mock_redis.smembers.assert_called_with("saga:state:state:running")


class TestDatabaseStateStorage:
    """Test suite for DatabaseStateStorage."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock database pool."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__.return_value = None
        return mock_pool, mock_conn

    @pytest.fixture
    def storage(self, mock_pool):
        """Create a DatabaseStateStorage instance."""
        pool, _ = mock_pool
        with patch.object(DatabaseStateStorage, "_ensure_table_exists"):
            return DatabaseStateStorage(pool)

    @pytest.mark.asyncio
    async def test_save_state(self, storage, mock_pool):
        """Test saving saga state to database."""
        _, mock_conn = mock_pool
        saga_id = "test_saga"
        state_data = {
            "saga_id": saga_id,
            "saga_name": "test",
            "state": "running",
            "context": {"user": "test"},
        }

        success = await storage.save_state(saga_id, state_data)
        assert success is True

        # Verify execute was called with correct query
        mock_conn.execute.assert_called_once()
        args = mock_conn.execute.call_args[0]
        assert "INSERT INTO saga_states" in args[0]
        assert "ON CONFLICT" in args[0]

    @pytest.mark.asyncio
    async def test_load_state(self, storage, mock_pool):
        """Test loading saga state from database."""
        _, mock_conn = mock_pool
        saga_id = "test_saga"
        state_data = {"saga_id": saga_id, "state": "completed"}

        mock_conn.fetchrow.return_value = {"state_data": json.dumps(state_data)}

        loaded_data = await storage.load_state(saga_id)
        assert loaded_data == state_data

    @pytest.mark.asyncio
    async def test_delete_state(self, storage, mock_pool):
        """Test deleting saga state from database."""
        _, mock_conn = mock_pool
        mock_conn.execute.return_value = "DELETE 1"

        success = await storage.delete_state("test_saga")
        assert success is True

        # Verify delete query
        args = mock_conn.execute.call_args[0]
        assert "DELETE FROM saga_states" in args[0]

    @pytest.mark.asyncio
    async def test_list_sagas_with_filter(self, storage, mock_pool):
        """Test listing sagas with filter."""
        _, mock_conn = mock_pool
        mock_conn.fetch.return_value = [
            {"saga_id": "saga1"},
            {"saga_id": "saga2"},
        ]

        saga_ids = await storage.list_sagas({"state": "running"})
        assert saga_ids == ["saga1", "saga2"]

        # Verify query with WHERE clause
        args = mock_conn.fetch.call_args[0]
        assert "WHERE" in args[0]
        assert "state = $1" in args[0]


class TestStorageFactory:
    """Test suite for StorageFactory."""

    def test_create_memory_storage(self):
        """Test creating in-memory storage."""
        storage = StorageFactory.create_storage("memory")
        assert isinstance(storage, InMemoryStateStorage)

    def test_create_redis_storage(self):
        """Test creating Redis storage."""
        mock_redis = MagicMock()
        storage = StorageFactory.create_storage(
            "redis", redis_client=mock_redis, key_prefix="test:"
        )
        assert isinstance(storage, RedisStateStorage)
        assert storage.key_prefix == "test:"

    def test_create_redis_storage_missing_client(self):
        """Test creating Redis storage without client."""
        with pytest.raises(ValueError, match="redis_client is required"):
            StorageFactory.create_storage("redis")

    def test_create_database_storage(self):
        """Test creating database storage."""
        mock_pool = MagicMock()
        with patch.object(DatabaseStateStorage, "_ensure_table_exists"):
            storage = StorageFactory.create_storage(
                "database", db_pool=mock_pool, table_name="test_table"
            )
        assert isinstance(storage, DatabaseStateStorage)
        assert storage.table_name == "test_table"

    def test_create_database_storage_missing_pool(self):
        """Test creating database storage without pool."""
        with pytest.raises(ValueError, match="db_pool is required"):
            StorageFactory.create_storage("database")

    def test_create_unknown_storage(self):
        """Test creating unknown storage type."""
        with pytest.raises(ValueError, match="Unknown storage type"):
            StorageFactory.create_storage("unknown")
