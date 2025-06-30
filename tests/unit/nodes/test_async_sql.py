"""Tests for AsyncSQLDatabaseNode."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    MySQLAdapter,
    PostgreSQLAdapter,
    SQLiteAdapter,
)
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


class TestAsyncSQLDatabaseNode:
    """Test AsyncSQLDatabaseNode functionality."""

    def test_node_initialization(self):
        """Test node initialization with various configs."""
        # Test PostgreSQL config
        node = AsyncSQLDatabaseNode(
            name="test_pg",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="SELECT * FROM users",
        )
        # Verify key configuration parameters are stored
        assert node.config["database_type"] == "postgresql"

        # Test with connection string
        node = AsyncSQLDatabaseNode(
            name="test_conn",
            database_type="postgresql",
            connection_string="postgresql://user:pass@host/db",
            query="SELECT 1",
        )
        assert node.config["connection_string"] == "postgresql://user:pass@host/db"

    def test_validation_errors(self):
        """Test configuration validation."""
        # Invalid database type - validation happens during initialization
        with pytest.raises(NodeConfigurationError, match="Invalid database_type"):
            AsyncSQLDatabaseNode(name="test", database_type="invalid", query="SELECT 1")

        # Missing required params for PostgreSQL
        with pytest.raises(NodeConfigurationError, match="requires host and database"):
            AsyncSQLDatabaseNode(
                name="test", database_type="postgresql", query="SELECT 1"
            )

        # Invalid fetch mode
        with pytest.raises(NodeConfigurationError, match="Invalid fetch_mode"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="sqlite",
                database="test.db",
                query="SELECT 1",
                fetch_mode="invalid",
            )

        # Missing fetch_size for many mode
        with pytest.raises(NodeConfigurationError, match="fetch_size required"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="sqlite",
                database="test.db",
                query="SELECT 1",
                fetch_mode="many",
            )

    @pytest.mark.asyncio
    async def test_postgresql_adapter(self):
        """Test PostgreSQL adapter functionality."""
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        adapter = PostgreSQLAdapter(config)

        # Mock asyncpg module
        mock_asyncpg = MagicMock()
        mock_pool = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        # Create a proper async context manager for connection acquisition
        class MockConnection:
            def __init__(self):
                self.fetch = AsyncMock(return_value=[{"col1": "value1"}])
                self.fetchrow = AsyncMock(return_value={"col1": "value1"})

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        # Set up pool.acquire() to return the context manager
        mock_pool.acquire = MagicMock(return_value=MockConnection())

        with patch.dict("sys.modules", {"asyncpg": mock_asyncpg}):

            # Test connection
            await adapter.connect()
            mock_asyncpg.create_pool.assert_called_once()

            # Test query execution - mock_pool.acquire already returns MockConnection
            # Get a connection from the pool to set up test expectations
            mock_conn_context = mock_pool.acquire()
            mock_conn = await mock_conn_context.__aenter__()

            # Test fetch one
            mock_row = {"id": 1, "name": "test"}
            mock_conn.fetchrow = AsyncMock(return_value=mock_row)
            result = await adapter.execute(
                "SELECT * FROM users", fetch_mode=FetchMode.ONE
            )
            assert result == mock_row

            # Test fetch all
            mock_rows = [{"id": 1}, {"id": 2}]
            mock_conn.fetch = AsyncMock(return_value=mock_rows)
            result = await adapter.execute(
                "SELECT * FROM users", fetch_mode=FetchMode.ALL
            )
            assert result == mock_rows

            # Test disconnect
            await adapter.disconnect()
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_mysql_adapter(self):
        """Test MySQL adapter functionality."""
        config = DatabaseConfig(
            type=DatabaseType.MYSQL,
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        adapter = MySQLAdapter(config)

        # Mock aiomysql
        mock_aiomysql = MagicMock()
        mock_pool = AsyncMock()
        # Make close() a regular synchronous mock
        mock_pool.close = MagicMock()
        mock_aiomysql.create_pool = AsyncMock(return_value=mock_pool)

        with patch.dict("sys.modules", {"aiomysql": mock_aiomysql}):

            # Test connection
            await adapter.connect()
            mock_aiomysql.create_pool.assert_called_once()

            # Test query execution
            # Create proper async context managers
            class MockCursor:
                def __init__(self):
                    self.fetchone = AsyncMock(return_value=(1, "test"))
                    self.fetchall = AsyncMock(return_value=[])
                    self.description = [("id",), ("name",)]
                    self.execute = AsyncMock()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            class MockConnection:
                def __init__(self):
                    self.cursor = MagicMock(return_value=MockCursor())

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Set up pool.acquire() to return the context manager
            mock_pool.acquire = MagicMock(return_value=MockConnection())

            # Test fetch one
            result = await adapter.execute(
                "SELECT * FROM users", fetch_mode=FetchMode.ONE
            )
            assert result == {"id": 1, "name": "test"}

            # Test disconnect
            await adapter.disconnect()
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_sqlite_adapter(self):
        """Test SQLite adapter functionality."""
        config = DatabaseConfig(type=DatabaseType.SQLITE, database="test.db")

        adapter = SQLiteAdapter(config)

        # Mock aiosqlite
        mock_aiosqlite = MagicMock()

        with patch.dict("sys.modules", {"aiosqlite": mock_aiosqlite}):
            # Create proper async context manager for SQLite
            class MockDB:
                def __init__(self):
                    self.execute = AsyncMock()

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_db = MockDB()
            mock_aiosqlite.connect = MagicMock(return_value=mock_db)
            mock_aiosqlite.Row = MagicMock()

            # Store reference for adapter
            adapter._aiosqlite = mock_aiosqlite

            # Test connection (no-op for SQLite)
            await adapter.connect()
            mock_cursor = AsyncMock()
            mock_db.execute = AsyncMock(return_value=mock_cursor)

            # Test fetch one
            mock_row = MagicMock()
            mock_row.__getitem__ = lambda self, key: {"id": 1, "name": "test"}[key]
            mock_row.keys = lambda: ["id", "name"]
            mock_cursor.fetchone = AsyncMock(return_value=mock_row)

            result = await adapter.execute(
                "SELECT * FROM users", fetch_mode=FetchMode.ONE
            )
            # Result will be dict(mock_row)

            # Test disconnect (no-op for SQLite)
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_node_execution(self):
        """Test full node execution flow."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="SELECT * FROM users WHERE active = :active",
            params={"active": True},
        )

        # Mock the adapter
        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Mock successful query
            mock_data = [{"id": 1, "name": "User 1"}, {"id": 2, "name": "User 2"}]
            mock_adapter.execute = AsyncMock(return_value=mock_data)

            result = await node.execute_async()

            assert result["result"]["data"] == mock_data
            assert result["result"]["row_count"] == 2
            assert result["result"]["database_type"] == "postgresql"

            # Verify adapter was called correctly
            mock_adapter.execute.assert_called_once_with(
                query="SELECT * FROM users WHERE active = :active",
                params={"active": True},
                fetch_mode=FetchMode.ALL,
                fetch_size=None,
            )

    @pytest.mark.asyncio
    async def test_node_with_runtime_inputs(self):
        """Test node execution with runtime parameter overrides."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="SELECT * FROM users",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            # Override query and params at runtime
            result = await node.execute_async(
                query="SELECT * FROM posts WHERE user_id = :user_id",
                params={"user_id": 1},
                fetch_mode="one",
            )

            mock_adapter.execute.assert_called_once_with(
                query="SELECT * FROM posts WHERE user_id = :user_id",
                params={"user_id": 1},
                fetch_mode=FetchMode.ONE,
                fetch_size=None,
            )

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling and retry logic."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="SELECT * FROM users",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Test retry logic - fail twice, succeed on third
            call_count = 0

            async def mock_execute(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise Exception("Connection failed")
                return [{"id": 1}]

            mock_adapter.execute = mock_execute

            # Should succeed after retries
            result = await node.execute_async()
            assert call_count == 3
            assert result["result"]["data"] == [{"id": 1}]

            # Test permanent failure
            mock_adapter.execute = AsyncMock(side_effect=Exception("Database error"))

            with pytest.raises(NodeExecutionError, match="Database query failed"):
                await node.execute_async()

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test resource cleanup."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="SELECT 1",
        )

        # Create mock adapter
        mock_adapter = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        await node.cleanup()

        mock_adapter.disconnect.assert_called_once()
        assert node._adapter is None
        assert node._connected is False
