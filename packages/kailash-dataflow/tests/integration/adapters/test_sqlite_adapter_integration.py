"""
Integration tests for SQLite database adapter with REAL infrastructure.

Tests SQLite-specific functionality including connection pooling.
NO MOCKING - uses real file-based and in-memory databases.
"""

import asyncio
import os
import tempfile
import time

import pytest
from dataflow.adapters.exceptions import ConnectionError, QueryError
from dataflow.adapters.sqlite import SQLiteAdapter


@pytest.mark.integration
class TestSQLiteAdapterIntegration:
    """Test SQLite adapter with real database."""

    @pytest.fixture
    async def test_table_name(self):
        """Generate unique table name for test isolation."""
        import random

        return f"test_adapter_{int(time.time())}_{random.randint(1000, 9999)}"

    @pytest.fixture
    async def temp_db_path(self):
        """Create temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        # Cleanup
        try:
            os.unlink(path)
        except:
            pass

    @pytest.fixture
    async def adapter_memory(self):
        """Create SQLite adapter with in-memory database."""
        adapter = SQLiteAdapter(":memory:", pool_size=2, max_overflow=2)
        yield adapter

        # Cleanup
        if adapter.is_connected:
            await adapter.disconnect()

    @pytest.fixture
    async def adapter_file(self, temp_db_path):
        """Create SQLite adapter with file-based database."""
        adapter = SQLiteAdapter(
            temp_db_path, pool_size=2, max_overflow=2, enable_connection_pooling=True
        )
        yield adapter

        # Cleanup
        if adapter.is_connected:
            await adapter.disconnect()

    @pytest.fixture
    async def connected_adapter_memory(self, adapter_memory):
        """Create and connect SQLite adapter (memory)."""
        await adapter_memory.connect()
        return adapter_memory

    @pytest.fixture
    async def connected_adapter_file(self, adapter_file):
        """Create and connect SQLite adapter (file)."""
        await adapter_file.connect()
        return adapter_file

    @pytest.mark.timeout(5)
    async def test_adapter_initialization_memory(self):
        """Test SQLite adapter initializes correctly with memory database."""
        adapter = SQLiteAdapter(":memory:", pool_size=5)

        assert adapter.database_path == ":memory:"
        assert adapter.is_memory_database is True
        assert adapter.pool_size == 5
        assert adapter.enable_connection_pooling is True
        assert not adapter.is_connected

    @pytest.mark.timeout(5)
    async def test_adapter_initialization_file(self, temp_db_path):
        """Test SQLite adapter initializes correctly with file database."""
        adapter = SQLiteAdapter(temp_db_path, pool_size=10)

        assert adapter.database_path == temp_db_path
        assert adapter.is_memory_database is False
        assert adapter.pool_size == 10
        assert not adapter.is_connected

    @pytest.mark.timeout(5)
    async def test_connection_pooling_enabled(self, connected_adapter_file):
        """Test that connection pooling is actually used - NEW FUNCTIONALITY."""
        # Verify pool was initialized
        assert len(connected_adapter_file._connection_pool) > 0
        assert connected_adapter_file._pool_stats.total_connections > 0
        assert connected_adapter_file._pool_stats.idle_connections > 0

        initial_pool_size = len(connected_adapter_file._connection_pool)

        # Execute query - should use connection from pool
        result = await connected_adapter_file.execute_query("SELECT 1 as value")

        # Verify pool still has connections (connection was returned)
        assert len(connected_adapter_file._connection_pool) > 0

        # Pool size should be stable (connections reused)
        assert len(connected_adapter_file._connection_pool) <= initial_pool_size + 1

    @pytest.mark.timeout(10)
    async def test_connection_pooling_multiple_queries(
        self, connected_adapter_file, test_table_name
    ):
        """Test connection pooling across multiple queries."""
        # Create table
        await connected_adapter_file.execute_query(
            f"""
            CREATE TABLE {test_table_name} (
                id INTEGER PRIMARY KEY,
                value INTEGER
            )
        """
        )

        # Execute multiple queries - all should use pooled connections
        for i in range(10):
            await connected_adapter_file.execute_query(
                f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", [i, i * 10]
            )

        # Verify all data was inserted correctly
        results = await connected_adapter_file.execute_query(
            f"SELECT COUNT(*) as count FROM {test_table_name}"
        )
        assert results[0]["count"] == 10

        # Pool should still have connections available
        assert len(connected_adapter_file._connection_pool) > 0

    @pytest.mark.timeout(5)
    async def test_execute_query_with_pooling(
        self, connected_adapter_file, test_table_name
    ):
        """Test execute_query uses connection pool."""
        # Create table
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY, name TEXT)"
        )

        # Insert data
        await connected_adapter_file.execute_query(
            f"INSERT INTO {test_table_name} (id, name) VALUES (?, ?)", [1, "Alice"]
        )

        # Query data - should use pooled connection
        result = await connected_adapter_file.execute_query(
            f"SELECT * FROM {test_table_name}"
        )

        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    @pytest.mark.timeout(5)
    async def test_execute_transaction_with_pooling(
        self, connected_adapter_file, test_table_name
    ):
        """Test execute_transaction uses connection pool - FIXED."""
        # Create table
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY, value INTEGER)"
        )

        # Execute transaction with multiple queries
        queries = [
            (f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", [1, 100]),
            (f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", [2, 200]),
            (f"SELECT * FROM {test_table_name}", []),
        ]

        results = await connected_adapter_file.execute_transaction(queries)

        # Verify transaction succeeded
        assert len(results) == 3
        assert len(results[2]) == 2  # SELECT should return 2 rows

    @pytest.mark.timeout(5)
    async def test_transaction_context_manager(
        self, connected_adapter_file, test_table_name
    ):
        """Test transaction() context manager - NEW FUNCTIONALITY."""
        # Create table
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY, value INTEGER)"
        )

        # Test successful transaction using context manager
        async with connected_adapter_file.transaction() as trans:
            await trans.connection.execute(
                f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", (1, 100)
            )
            await trans.connection.execute(
                f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", (2, 200)
            )
            await trans.connection.commit()

        # Verify data was committed
        result = await connected_adapter_file.execute_query(
            f"SELECT COUNT(*) as count FROM {test_table_name}"
        )
        assert result[0]["count"] == 2

        # Test rolled back transaction
        try:
            async with connected_adapter_file.transaction() as trans:
                await trans.connection.execute(
                    f"INSERT INTO {test_table_name} (id, value) VALUES (?, ?)", (3, 300)
                )
                # Force rollback by raising exception
                raise Exception("Test rollback")
        except Exception:
            pass

        # Verify rollback - should still have only 2 rows
        result = await connected_adapter_file.execute_query(
            f"SELECT COUNT(*) as count FROM {test_table_name}"
        )
        assert result[0]["count"] == 2

    @pytest.mark.timeout(5)
    async def test_execute_insert(self, connected_adapter_file, test_table_name):
        """Test execute_insert() - NEW METHOD."""
        # Create table
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY, name TEXT)"
        )

        # Test execute_insert
        result = await connected_adapter_file.execute_insert(
            f"INSERT INTO {test_table_name} (id, name) VALUES (?, ?)", [1, "Test"]
        )

        # Verify result contains lastrowid and rowcount
        assert "lastrowid" in result
        assert "rowcount" in result
        assert result["lastrowid"] == 1
        assert result["rowcount"] == 1

        # Verify data was inserted
        rows = await connected_adapter_file.execute_query(
            f"SELECT * FROM {test_table_name}"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "Test"

    @pytest.mark.timeout(5)
    async def test_execute_bulk_insert(self, connected_adapter_file, test_table_name):
        """Test execute_bulk_insert() - NEW METHOD."""
        # Create table
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)"
        )

        # Test bulk insert
        data = [(1, "Alice", 100), (2, "Bob", 200), (3, "Charlie", 300)]

        await connected_adapter_file.execute_bulk_insert(
            f"INSERT INTO {test_table_name} (id, name, value) VALUES (?, ?, ?)", data
        )

        # Verify all data was inserted
        rows = await connected_adapter_file.execute_query(
            f"SELECT * FROM {test_table_name} ORDER BY id"
        )
        assert len(rows) == 3
        assert rows[0]["name"] == "Alice"
        assert rows[1]["name"] == "Bob"
        assert rows[2]["name"] == "Charlie"

    @pytest.mark.timeout(5)
    async def test_get_table_schema(self, connected_adapter_file, test_table_name):
        """Test get_table_schema() uses connection pool - FIXED."""
        # Create table with various column types
        await connected_adapter_file.execute_query(
            f"""
            CREATE TABLE {test_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER,
                email TEXT DEFAULT 'unknown@example.com'
            )
        """
        )

        # Get schema - should use pooled connection
        schema = await connected_adapter_file.get_table_schema(test_table_name)

        # Verify schema
        assert "id" in schema
        assert "name" in schema
        assert "age" in schema
        assert "email" in schema

        assert schema["id"]["type"] == "integer"
        assert schema["id"]["primary_key"] is True
        assert schema["name"]["nullable"] is False
        assert schema["age"]["nullable"] is True

    @pytest.mark.timeout(5)
    async def test_create_table(self, connected_adapter_file, test_table_name):
        """Test create_table() uses connection pool - FIXED."""
        # Define schema
        schema = {
            "id": {"type": "INTEGER", "primary_key": True},
            "username": {"type": "TEXT", "nullable": False},
            "score": {"type": "INTEGER", "nullable": True, "default": "0"},
        }

        # Create table - should use pooled connection
        await connected_adapter_file.create_table(test_table_name, schema)

        # Verify table exists by inserting data
        await connected_adapter_file.execute_query(
            f"INSERT INTO {test_table_name} (id, username, score) VALUES (?, ?, ?)",
            [1, "testuser", 100],
        )

        result = await connected_adapter_file.execute_query(
            f"SELECT * FROM {test_table_name}"
        )
        assert len(result) == 1
        assert result[0]["username"] == "testuser"

    @pytest.mark.timeout(5)
    async def test_drop_table(self, connected_adapter_file, test_table_name):
        """Test drop_table() uses connection pool - FIXED."""
        # Create table first
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY)"
        )

        # Drop table - should use pooled connection
        await connected_adapter_file.drop_table(test_table_name)

        # Verify table was dropped by trying to query it
        with pytest.raises(QueryError):
            await connected_adapter_file.execute_query(
                f"SELECT * FROM {test_table_name}"
            )

    @pytest.mark.timeout(5)
    async def test_get_server_version(self, connected_adapter_file):
        """Test get_server_version() - NEW METHOD."""
        version = await connected_adapter_file.get_server_version()

        # Verify we got a version string
        assert version != "unknown"
        assert len(version) > 0

        # Version should be in format like "3.39.0"
        import re

        version_pattern = r"\d+\.\d+\.\d+"
        assert re.search(
            version_pattern, version
        ), f"No version number found in: {version}"

    @pytest.mark.timeout(5)
    async def test_get_database_size(self, connected_adapter_file):
        """Test get_database_size() - NEW METHOD."""
        # File-based database should have a size
        size = await connected_adapter_file.get_database_size()

        assert size > 0
        assert isinstance(size, int)

        # Should be reasonable (at least a few KB)
        assert size > 1024  # At least 1KB

    @pytest.mark.timeout(5)
    async def test_get_database_size_memory(self, connected_adapter_memory):
        """Test get_database_size() with memory database."""
        # Memory database should return 0
        size = await connected_adapter_memory.get_database_size()

        assert size == 0

    @pytest.mark.timeout(5)
    async def test_get_connection_parameters(self, adapter_file):
        """Test get_connection_parameters() - NEW METHOD."""
        params = adapter_file.get_connection_parameters()

        # Verify required parameters
        assert "database" in params
        assert "timeout" in params
        assert "isolation_level" in params
        assert "check_same_thread" in params
        assert "pragmas" in params

        assert params["database"] == adapter_file.database_path
        assert params["check_same_thread"] is False

    def test_get_tables_query(self, adapter_file):
        """Test get_tables_query() - NEW METHOD."""
        query = adapter_file.get_tables_query()

        assert "sqlite_master" in query
        assert "table_name" in query.lower() or "name" in query

    def test_get_columns_query(self, adapter_file):
        """Test get_columns_query() - NEW METHOD."""
        query = adapter_file.get_columns_query("test_table")

        assert "PRAGMA" in query
        assert "table_info" in query
        assert "test_table" in query

    @pytest.mark.timeout(10)
    async def test_connection_pool_stats(self, connected_adapter_file, test_table_name):
        """Test connection pool statistics tracking."""
        initial_stats = connected_adapter_file._pool_stats

        # Execute some queries
        await connected_adapter_file.execute_query(
            f"CREATE TABLE {test_table_name} (id INTEGER PRIMARY KEY)"
        )

        for i in range(5):
            await connected_adapter_file.execute_query(
                f"INSERT INTO {test_table_name} (id) VALUES (?)", [i]
            )

        # Verify stats are being tracked
        assert connected_adapter_file._pool_stats.total_connections > 0

    @pytest.mark.timeout(5)
    async def test_wal_mode_enabled(self, connected_adapter_file):
        """Test that WAL mode is enabled by default for better concurrency."""
        # Check pragma setting
        result = await connected_adapter_file.execute_query("PRAGMA journal_mode")

        # Should be WAL by default
        assert result[0]["journal_mode"].upper() == "WAL"

    def test_supports_feature(self, adapter_file):
        """Test SQLite feature support checking."""
        # SQLite supports these features
        assert adapter_file.supports_feature("json")
        assert adapter_file.supports_feature("window_functions")
        assert adapter_file.supports_feature("cte")
        assert adapter_file.supports_feature("upsert")

        # Doesn't support these
        assert not adapter_file.supports_feature("arrays")
        assert not adapter_file.supports_feature("hstore")

    def test_get_dialect(self, adapter_file):
        """Test SQLite dialect identification."""
        assert adapter_file.get_dialect() == "sqlite"

    @pytest.mark.timeout(5)
    async def test_disconnect_cleanup(self, adapter_file):
        """Test that disconnect properly cleans up connection pool."""
        await adapter_file.connect()

        initial_pool_size = len(adapter_file._connection_pool)
        assert initial_pool_size > 0

        # Disconnect
        await adapter_file.disconnect()

        # Pool should be cleared
        assert len(adapter_file._connection_pool) == 0
        assert adapter_file._pool_stats.total_connections == 0
        assert adapter_file._pool_stats.idle_connections == 0
        assert not adapter_file.is_connected
