"""Tests for AsyncSQLDatabaseNode."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseType,
    FetchMode,
    DatabaseConfig,
    PostgreSQLAdapter,
    MySQLAdapter,
    SQLiteAdapter
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


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
            query="SELECT * FROM users"
        )
        assert node.name == "test_pg"
        assert node.config["database_type"] == "postgresql"
        
        # Test with connection string
        node = AsyncSQLDatabaseNode(
            name="test_conn",
            database_type="postgresql",
            connection_string="postgresql://user:pass@host/db",
            query="SELECT 1"
        )
        assert node.config["connection_string"] == "postgresql://user:pass@host/db"
    
    def test_validation_errors(self):
        """Test configuration validation."""
        # Invalid database type
        with pytest.raises(NodeValidationError, match="Invalid database_type"):
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="invalid",
                query="SELECT 1"
            )
            node.validate_config()
        
        # Missing required params for PostgreSQL
        with pytest.raises(NodeValidationError, match="requires host and database"):
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                query="SELECT 1"
            )
            node.validate_config()
        
        # Invalid fetch mode
        with pytest.raises(NodeValidationError, match="Invalid fetch_mode"):
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="sqlite",
                database="test.db",
                query="SELECT 1",
                fetch_mode="invalid"
            )
            node.validate_config()
        
        # Missing fetch_size for many mode
        with pytest.raises(NodeValidationError, match="fetch_size required"):
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="sqlite",
                database="test.db",
                query="SELECT 1",
                fetch_mode="many"
            )
            node.validate_config()
    
    @pytest.mark.asyncio
    async def test_postgresql_adapter(self):
        """Test PostgreSQL adapter functionality."""
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass"
        )
        
        adapter = PostgreSQLAdapter(config)
        
        # Mock asyncpg
        with patch("kailash.nodes.data.async_sql.asyncpg") as mock_asyncpg:
            mock_pool = AsyncMock()
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
            
            # Test connection
            await adapter.connect()
            mock_asyncpg.create_pool.assert_called_once()
            
            # Test query execution
            mock_conn = AsyncMock()
            mock_pool.acquire = AsyncMock(return_value=mock_conn)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=None)
            
            # Test fetch one
            mock_row = {"id": 1, "name": "test"}
            mock_conn.fetchrow = AsyncMock(return_value=mock_row)
            result = await adapter.execute("SELECT * FROM users", fetch_mode=FetchMode.ONE)
            assert result == mock_row
            
            # Test fetch all
            mock_rows = [{"id": 1}, {"id": 2}]
            mock_conn.fetch = AsyncMock(return_value=mock_rows)
            result = await adapter.execute("SELECT * FROM users", fetch_mode=FetchMode.ALL)
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
            password="testpass"
        )
        
        adapter = MySQLAdapter(config)
        
        # Mock aiomysql
        with patch("kailash.nodes.data.async_sql.aiomysql") as mock_aiomysql:
            mock_pool = AsyncMock()
            mock_aiomysql.create_pool = AsyncMock(return_value=mock_pool)
            
            # Test connection
            await adapter.connect()
            mock_aiomysql.create_pool.assert_called_once()
            
            # Test query execution
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_pool.acquire = AsyncMock(return_value=mock_conn)
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=None)
            mock_conn.cursor = AsyncMock(return_value=mock_cursor)
            mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
            mock_cursor.__aexit__ = AsyncMock(return_value=None)
            
            # Test fetch one
            mock_cursor.fetchone = AsyncMock(return_value=(1, "test"))
            mock_cursor.description = [("id",), ("name",)]
            result = await adapter.execute("SELECT * FROM users", fetch_mode=FetchMode.ONE)
            assert result == {"id": 1, "name": "test"}
            
            # Test disconnect
            await adapter.disconnect()
            mock_pool.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sqlite_adapter(self):
        """Test SQLite adapter functionality."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            database="test.db"
        )
        
        adapter = SQLiteAdapter(config)
        
        # Mock aiosqlite
        with patch("kailash.nodes.data.async_sql.aiosqlite") as mock_aiosqlite:
            mock_db = AsyncMock()
            mock_aiosqlite.connect = AsyncMock(return_value=mock_db)
            mock_aiosqlite.Row = MagicMock()
            
            # Store reference for adapter
            adapter._aiosqlite = mock_aiosqlite
            
            # Test connection (no-op for SQLite)
            await adapter.connect()
            
            # Test query execution
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_cursor = AsyncMock()
            mock_db.execute = AsyncMock(return_value=mock_cursor)
            
            # Test fetch one
            mock_row = MagicMock()
            mock_row.__getitem__ = lambda self, key: {"id": 1, "name": "test"}[key]
            mock_row.keys = lambda: ["id", "name"]
            mock_cursor.fetchone = AsyncMock(return_value=mock_row)
            
            result = await adapter.execute("SELECT * FROM users", fetch_mode=FetchMode.ONE)
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
            params={"active": True}
        )
        
        # Mock the adapter
        with patch.object(node, '_get_adapter') as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            
            # Mock successful query
            mock_data = [{"id": 1, "name": "User 1"}, {"id": 2, "name": "User 2"}]
            mock_adapter.execute = AsyncMock(return_value=mock_data)
            
            result = await node.async_run()
            
            assert result["result"]["data"] == mock_data
            assert result["result"]["row_count"] == 2
            assert result["result"]["database_type"] == "postgresql"
            
            # Verify adapter was called correctly
            mock_adapter.execute.assert_called_once_with(
                query="SELECT * FROM users WHERE active = :active",
                params={"active": True},
                fetch_mode=FetchMode.ALL,
                fetch_size=None
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
            query="SELECT * FROM users"
        )
        
        with patch.object(node, '_get_adapter') as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])
            
            # Override query and params at runtime
            result = await node.async_run(
                query="SELECT * FROM posts WHERE user_id = :user_id",
                params={"user_id": 1},
                fetch_mode="one"
            )
            
            mock_adapter.execute.assert_called_once_with(
                query="SELECT * FROM posts WHERE user_id = :user_id",
                params={"user_id": 1},
                fetch_mode=FetchMode.ONE,
                fetch_size=None
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
            query="SELECT * FROM users"
        )
        
        with patch.object(node, '_get_adapter') as mock_get_adapter:
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
            result = await node.async_run()
            assert call_count == 3
            assert result["result"]["data"] == [{"id": 1}]
            
            # Test permanent failure
            mock_adapter.execute = AsyncMock(side_effect=Exception("Database error"))
            
            with pytest.raises(NodeExecutionError, match="Database query failed"):
                await node.async_run()
    
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
            query="SELECT 1"
        )
        
        # Create mock adapter
        mock_adapter = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True
        
        await node.cleanup()
        
        mock_adapter.disconnect.assert_called_once()
        assert node._adapter is None
        assert node._connected is False