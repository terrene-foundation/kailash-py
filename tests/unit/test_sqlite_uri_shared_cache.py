"""Unit tests for SQLiteAdapter URI shared-cache for :memory: databases (TODO-001).

Tests the Core SDK SQLiteAdapter directly to verify:
1. :memory: connection strings are translated to URI form with shared cache
2. file: prefix parsing preserves full URIs with query parameters
3. WAL pragma is skipped for in-memory databases
4. Class-level _shared_memory_connections and _connection_locks are removed
5. connect_kwargs with uri=True are used for memory databases
"""

import pytest
from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter


@pytest.mark.asyncio
class TestSQLiteAdapterMemoryDBTranslation:
    """Test that :memory: connection strings are translated to URI shared-cache form."""

    async def test_memory_db_detected_from_connection_string(self):
        """Test that :memory: is detected as a memory database."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        assert adapter._is_memory_db is True

    async def test_memory_db_path_translated_to_uri(self):
        """Test that :memory: path is translated to file:<name>?mode=memory&cache=shared."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        assert adapter._db_path.startswith("file:")
        assert "mode=memory" in adapter._db_path
        assert "cache=shared" in adapter._db_path

    async def test_memory_db_connect_kwargs_has_uri_true(self):
        """Test that connect kwargs include uri=True for memory databases."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        assert adapter._connect_kwargs.get("uri") is True

    async def test_non_memory_db_connect_kwargs_empty(self):
        """Test that connect kwargs are empty for non-memory databases."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                database=db_path,
            )
            adapter = SQLiteAdapter(config)
            await adapter.connect()

            assert adapter._connect_kwargs == {}
            assert adapter._is_memory_db is False
        finally:
            os.unlink(db_path)

    async def test_sqlite_uri_memory_detected_from_connection_string(self):
        """Test that sqlite:///:memory: is detected as memory database."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string="sqlite:///:memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        assert adapter._is_memory_db is True
        assert "mode=memory" in adapter._db_path
        assert "cache=shared" in adapter._db_path

    async def test_mode_memory_in_uri_detected(self):
        """Test that URIs containing mode=memory are detected as memory databases."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string="file:test_db?mode=memory&cache=shared",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        assert adapter._is_memory_db is True
        # Should preserve the full URI as-is since it already has parameters
        assert adapter._db_path == "file:test_db?mode=memory&cache=shared"


@pytest.mark.asyncio
class TestSQLiteAdapterFilePrefixParsing:
    """Test that file: prefix parsing preserves full URIs with query parameters."""

    async def test_file_uri_with_params_preserved(self):
        """Test that file:path?params URIs are preserved as-is."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string="file:mydb?mode=memory&cache=shared",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        # The full URI should be preserved, not stripped
        assert adapter._db_path == "file:mydb?mode=memory&cache=shared"

    async def test_simple_file_prefix_stripped(self):
        """Test that simple file: prefix without params is stripped."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            config = DatabaseConfig(
                type=DatabaseType.SQLITE,
                connection_string=f"file:{db_path}",
            )
            adapter = SQLiteAdapter(config)
            await adapter.connect()

            # Simple file: prefix should be stripped
            assert adapter._db_path == db_path
        finally:
            os.unlink(db_path)


class TestSQLiteAdapterNoClassLevelState:
    """Test that class-level _shared_memory_connections and _connection_locks are removed."""

    def test_no_shared_memory_connections_class_attr(self):
        """Test that _shared_memory_connections class attribute is removed."""
        assert not hasattr(SQLiteAdapter, "_shared_memory_connections"), (
            "Class-level _shared_memory_connections should be removed. "
            "URI shared-cache replaces the shared connection dict approach."
        )

    def test_no_connection_locks_class_attr(self):
        """Test that _connection_locks class attribute is removed."""
        assert not hasattr(SQLiteAdapter, "_connection_locks"), (
            "Class-level _connection_locks should be removed. "
            "URI shared-cache eliminates the need for connection locks."
        )


@pytest.mark.asyncio
class TestSQLiteAdapterWALPragmaSkipped:
    """Test that WAL pragma is skipped for in-memory databases."""

    async def test_wal_pragma_skipped_for_memory_db(self):
        """Test that journal_mode=WAL is not set for memory databases."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        # Get a connection and check journal_mode
        conn = await adapter._get_connection()
        try:
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            journal_mode = row[0] if row else None

            # For shared-cache memory DBs, journal_mode should NOT be WAL
            # It should be "memory" (the default for in-memory databases)
            assert (
                journal_mode != "wal"
            ), f"WAL should not be set for memory databases, got: {journal_mode}"
        finally:
            await conn.close()

    async def test_other_pragmas_still_applied_for_memory_db(self):
        """Test that non-WAL pragmas are still applied to memory databases."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        conn = await adapter._get_connection()
        try:
            # Check foreign_keys pragma is set
            cursor = await conn.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1, "foreign_keys should be ON for memory databases"

            # Check busy_timeout pragma is set
            cursor = await conn.execute("PRAGMA busy_timeout")
            row = await cursor.fetchone()
            assert row[0] == 5000, "busy_timeout should be 5000 for memory databases"
        finally:
            await conn.close()


@pytest.mark.asyncio
class TestSQLiteAdapterSharedCacheConnections:
    """Test that URI shared-cache allows multiple connections to share data."""

    async def test_two_connections_share_data_via_uri_cache(self):
        """Test that two connections to the same memory DB share data via URI cache."""
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=":memory:",
        )
        adapter = SQLiteAdapter(config)
        await adapter.connect()

        # Connection 1: create table and insert data
        conn1 = await adapter._get_connection()
        await conn1.execute("CREATE TABLE shared_test (id INTEGER, val TEXT)")
        await conn1.execute("INSERT INTO shared_test VALUES (1, 'hello')")
        await conn1.commit()

        # Connection 2: should see the data via shared cache
        conn2 = await adapter._get_connection()
        cursor = await conn2.execute("SELECT val FROM shared_test WHERE id = 1")
        row = await cursor.fetchone()

        assert row is not None, (
            "Second connection should see data from first connection "
            "via URI shared-cache"
        )
        assert row[0] == "hello"

        await conn1.close()
        await conn2.close()
