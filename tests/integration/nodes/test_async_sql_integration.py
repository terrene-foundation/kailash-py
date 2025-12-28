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

            # Verify adapter was called correctly (including transaction parameter)
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args
            assert call_args[1]["query"] == "SELECT * FROM users WHERE active = :active"
            assert call_args[1]["params"] == {"active": True}
            assert call_args[1]["fetch_mode"] == FetchMode.ALL
            assert call_args[1]["fetch_size"] is None
            assert "transaction" in call_args[1]  # Transaction should be present

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

            # Verify adapter was called correctly (including transaction parameter)
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args
            assert (
                call_args[1]["query"] == "SELECT * FROM posts WHERE user_id = :user_id"
            )
            assert call_args[1]["params"] == {"user_id": 1}
            assert call_args[1]["fetch_mode"] == FetchMode.ONE
            assert call_args[1]["fetch_size"] is None
            assert "transaction" in call_args[1]  # Transaction should be present

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

            # Mock transaction methods
            mock_adapter.begin_transaction = AsyncMock()
            mock_adapter.commit_transaction = AsyncMock()
            mock_adapter.rollback_transaction = AsyncMock()

            # Test permanent failure (no retry expected in unit test)
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

    @pytest.mark.asyncio
    async def test_transaction_mode_auto(self):
        """Test auto transaction mode - each query in its own transaction."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",  # This is the default
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Mock transaction methods
            mock_transaction = MagicMock()
            mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
            mock_adapter.commit_transaction = AsyncMock()
            mock_adapter.rollback_transaction = AsyncMock()
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            # Execute successful query
            result = await node.execute_async(
                query="INSERT INTO users VALUES (1, 'test')"
            )

            # Verify transaction flow
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute.assert_called_once_with(
                query="INSERT INTO users VALUES (1, 'test')",
                params=None,
                fetch_mode=FetchMode.ALL,
                fetch_size=None,
                transaction=mock_transaction,
                parameter_types=None,
            )
            mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)
            mock_adapter.rollback_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_transaction_mode_auto_rollback(self):
        """Test auto transaction mode rollback on error."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Mock transaction methods
            mock_transaction = MagicMock()
            mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
            mock_adapter.commit_transaction = AsyncMock()
            mock_adapter.rollback_transaction = AsyncMock()
            mock_adapter.execute = AsyncMock(side_effect=Exception("Database error"))

            # Execute failing query
            with pytest.raises(NodeExecutionError, match="Database query failed"):
                await node.execute_async(query="INVALID SQL")

            # Verify rollback was called (1 time since "Database error" is not retryable)
            assert (
                mock_adapter.begin_transaction.call_count == 1
            )  # 1 attempt (not retryable)
            assert mock_adapter.rollback_transaction.call_count == 1
            mock_adapter.commit_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_transaction_mode_manual(self):
        """Test manual transaction mode with explicit control."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Mock transaction methods
            mock_transaction = MagicMock()
            mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
            mock_adapter.commit_transaction = AsyncMock()
            mock_adapter.rollback_transaction = AsyncMock()
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            # Begin transaction
            tx = await node.begin_transaction()
            assert tx == mock_transaction
            assert node._active_transaction == mock_transaction

            # Execute queries within transaction
            await node.execute_async(query="INSERT INTO users VALUES (1, 'test')")
            await node.execute_async(
                query="UPDATE users SET name = 'updated' WHERE id = 1"
            )

            # Verify both queries used the same transaction
            assert mock_adapter.execute.call_count == 2
            for call in mock_adapter.execute.call_args_list:
                assert call.kwargs["transaction"] == mock_transaction

            # Commit transaction
            await node.commit()
            mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)
            assert node._active_transaction is None

    @pytest.mark.asyncio
    async def test_transaction_mode_manual_rollback(self):
        """Test manual transaction rollback."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Mock transaction methods
            mock_transaction = MagicMock()
            mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
            mock_adapter.rollback_transaction = AsyncMock()
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            # Begin transaction
            await node.begin_transaction()

            # Execute query
            await node.execute_async(query="INSERT INTO users VALUES (1, 'test')")

            # Rollback transaction
            await node.rollback()
            mock_adapter.rollback_transaction.assert_called_once_with(mock_transaction)
            assert node._active_transaction is None

    @pytest.mark.asyncio
    async def test_transaction_mode_none(self):
        """Test no transaction mode - queries execute immediately."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="none",
        )

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            # Execute query - should not use transactions
            await node.execute_async(query="INSERT INTO users VALUES (1, 'test')")

            # Verify no transaction methods were called
            assert (
                not hasattr(mock_adapter, "begin_transaction")
                or not mock_adapter.begin_transaction.called
            )
            mock_adapter.execute.assert_called_once_with(
                query="INSERT INTO users VALUES (1, 'test')",
                params=None,
                fetch_mode=FetchMode.ALL,
                fetch_size=None,
                parameter_types=None,
            )

    @pytest.mark.asyncio
    async def test_transaction_mode_errors(self):
        """Test transaction mode validation errors."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",  # Not manual mode
        )

        # Test calling manual transaction methods in auto mode
        with pytest.raises(
            NodeExecutionError, match="can only be called in 'manual' transaction mode"
        ):
            await node.begin_transaction()

        with pytest.raises(
            NodeExecutionError, match="can only be called in 'manual' transaction mode"
        ):
            await node.commit()

        with pytest.raises(
            NodeExecutionError, match="can only be called in 'manual' transaction mode"
        ):
            await node.rollback()

    @pytest.mark.asyncio
    async def test_cleanup_with_active_transaction(self):
        """Test cleanup rolls back active transactions."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        # Set up active transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        node._adapter = mock_adapter
        node._connected = True
        node._active_transaction = mock_transaction

        await node.cleanup()

        # Verify rollback was attempted
        mock_adapter.rollback_transaction.assert_called_once_with(mock_transaction)
        assert node._active_transaction is None
