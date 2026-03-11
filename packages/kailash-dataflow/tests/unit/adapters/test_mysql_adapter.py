"""
Unit tests for MySQL database adapter.

Tests MySQL-specific functionality without requiring database connection.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dataflow.adapters.exceptions import ConnectionError, QueryError
from dataflow.adapters.mysql import MySQLAdapter


class TestMySQLAdapter:
    """Test MySQL adapter functionality."""

    def test_adapter_initialization(self):
        """Test MySQL adapter initializes correctly."""
        connection_string = "mysql://test:test@localhost:3306/testdb"

        adapter = MySQLAdapter(connection_string, pool_size=15, max_overflow=25)

        assert adapter.connection_string == connection_string
        assert adapter.scheme == "mysql"
        assert adapter.host == "localhost"
        assert adapter.port == 3306
        assert adapter.database == "testdb"
        assert adapter.username == "test"
        assert adapter.password == "test"
        assert adapter.pool_size == 15
        assert adapter.max_overflow == 25
        assert not adapter.is_connected
        assert adapter.charset == "utf8mb4"
        assert adapter.collation == "utf8mb4_unicode_ci"

    def test_adapter_initialization_with_charset(self):
        """Test MySQL adapter with custom charset."""
        connection_string = "mysql://test:test@localhost:3306/testdb?charset=latin1"

        adapter = MySQLAdapter(connection_string)

        assert adapter.charset == "latin1"

    def test_adapter_initialization_default_port(self):
        """Test MySQL adapter uses default port when not specified."""
        connection_string = "mysql://test:test@localhost/testdb"

        adapter = MySQLAdapter(connection_string)

        assert adapter.port == 3306  # MySQL default port

    def test_get_dialect(self):
        """Test MySQL dialect identification."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        dialect = adapter.get_dialect()

        assert dialect == "mysql"

    def test_database_type(self):
        """Test database type property."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        assert adapter.database_type == "mysql"

    def test_default_port(self):
        """Test default port property."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        assert adapter.default_port == 3306

    @pytest.mark.asyncio
    async def test_create_connection_pool_success(self):
        """Test successful connection pool creation."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock aiomysql.create_pool
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.release = Mock()
        mock_pool.close = Mock()
        mock_pool.wait_closed = AsyncMock()

        with patch(
            "aiomysql.create_pool", new_callable=AsyncMock, return_value=mock_pool
        ):
            await adapter.create_connection_pool()

            assert adapter.connection_pool == mock_pool
            assert adapter.is_connected

    @pytest.mark.asyncio
    async def test_create_connection_pool_failure(self):
        """Test connection pool creation failure."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        with patch(
            "aiomysql.create_pool",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            with pytest.raises(ConnectionError, match="Connection failed"):
                await adapter.create_connection_pool()

            assert adapter.connection_pool is None
            assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_execute_query_success(self):
        """Test successful query execution."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock cursor and connection
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[{"id": 1, "name": "test"}])
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.cursor = Mock(return_value=mock_cursor)
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=mock_connection)

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_query("SELECT * FROM users")

        assert result == [{"id": 1, "name": "test"}]
        mock_cursor.execute.assert_called_once_with("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_execute_query_with_params(self):
        """Test query execution with parameters."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock cursor
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[{"id": 1, "name": "Alice"}])
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.cursor = Mock(return_value=mock_cursor)
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=mock_connection)

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_query("SELECT * FROM users WHERE id = %s", [1])

        assert result == [{"id": 1, "name": "Alice"}]
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM users WHERE id = %s", [1]
        )

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self):
        """Test query execution when not connected."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        with pytest.raises(ConnectionError, match="Not connected to database"):
            await adapter.execute_query("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_execute_query_error(self):
        """Test query execution with database error."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock cursor that raises error
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock(side_effect=Exception("Table does not exist"))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        # __aexit__ should return False/None to propagate exceptions
        mock_cursor.__aexit__ = AsyncMock(return_value=False)

        mock_connection = AsyncMock()
        mock_connection.cursor = Mock(return_value=mock_cursor)
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        # __aexit__ should return False/None to propagate exceptions
        mock_connection.__aexit__ = AsyncMock(return_value=False)

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=mock_connection)

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        with pytest.raises(QueryError, match="Query execution failed"):
            await adapter.execute_query("SELECT * FROM nonexistent_table")

    @pytest.mark.asyncio
    async def test_execute_insert_query(self):
        """Test INSERT query execution."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock cursor for INSERT
        mock_cursor = AsyncMock()
        mock_cursor.execute = AsyncMock()
        mock_cursor.lastrowid = 123
        mock_cursor.rowcount = 1
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.cursor = Mock(return_value=mock_cursor)
        mock_connection.commit = AsyncMock()
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=mock_connection)

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        result = await adapter.execute_insert(
            "INSERT INTO users (name) VALUES (%s)", ["Alice"]
        )

        assert result["lastrowid"] == 123
        assert result["rowcount"] == 1
        mock_cursor.execute.assert_called_once_with(
            "INSERT INTO users (name) VALUES (%s)", ["Alice"]
        )
        mock_connection.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_bulk_insert(self):
        """Test bulk insert operation."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock cursor for bulk insert
        mock_cursor = AsyncMock()
        mock_cursor.executemany = AsyncMock()
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock()

        mock_connection = AsyncMock()
        mock_connection.cursor = Mock(return_value=mock_cursor)
        mock_connection.commit = AsyncMock()
        mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_connection.__aexit__ = AsyncMock()

        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=mock_connection)

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        data = [("Alice",), ("Bob",), ("Charlie",)]
        await adapter.execute_bulk_insert("INSERT INTO users (name) VALUES (%s)", data)

        mock_cursor.executemany.assert_called_once_with(
            "INSERT INTO users (name) VALUES (%s)", data
        )
        mock_connection.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_connection_pool(self):
        """Test connection pool cleanup."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock connection pool
        mock_pool = AsyncMock()
        mock_pool.close = Mock()
        mock_pool.wait_closed = AsyncMock()

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        await adapter.close_connection_pool()

        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()
        assert adapter.connection_pool is None
        assert not adapter.is_connected

    def test_get_connection_parameters(self):
        """Test extracting connection parameters for aiomysql."""
        adapter = MySQLAdapter(
            "mysql://test:test@localhost:3306/testdb?charset=utf8mb4",
            pool_size=15,
            max_overflow=25,
        )

        params = adapter.get_connection_parameters()

        assert params["host"] == "localhost"
        assert params["port"] == 3306
        assert params["user"] == "test"
        assert params["password"] == "test"
        assert params["db"] == "testdb"
        assert params["charset"] == "utf8mb4"
        assert params["minsize"] == 15
        assert params["maxsize"] == 40  # pool_size + max_overflow

    def test_get_connection_parameters_with_ssl(self):
        """Test connection parameters with SSL configuration."""
        adapter = MySQLAdapter(
            "mysql://test:test@localhost:3306/testdb",
            ssl_ca="/path/to/ca.pem",
            ssl_cert="/path/to/cert.pem",
            ssl_key="/path/to/key.pem",
            ssl_verify_cert=True,
        )

        params = adapter.get_connection_parameters()

        assert "ssl" in params
        assert params["ssl"]["ca"] == "/path/to/ca.pem"
        assert params["ssl"]["cert"] == "/path/to/cert.pem"
        assert params["ssl"]["key"] == "/path/to/key.pem"
        assert params["ssl"]["check_hostname"] is True

    def test_format_query_mysql_style(self):
        """Test MySQL-style parameter formatting."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Test standard parameter substitution
        query = "SELECT * FROM users WHERE id = ? AND name = ?"
        params = [1, "Alice"]

        formatted_query, formatted_params = adapter.format_query(query, params)

        assert formatted_query == "SELECT * FROM users WHERE id = %s AND name = %s"
        assert formatted_params == params

    def test_supports_feature(self):
        """Test MySQL feature support."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # MySQL supports these features
        assert adapter.supports_feature("json")  # MySQL 5.7+
        assert adapter.supports_feature("window_functions")  # MySQL 8.0+
        assert adapter.supports_feature("cte")  # MySQL 8.0+
        assert adapter.supports_feature("upsert")  # ON DUPLICATE KEY UPDATE
        assert adapter.supports_feature("fulltext_search")
        assert adapter.supports_feature("spatial_indexes")
        assert adapter.supports_feature("regex")

        # MySQL doesn't support these features
        assert not adapter.supports_feature("arrays")  # PostgreSQL-specific
        assert not adapter.supports_feature("hstore")  # PostgreSQL-specific
        assert not adapter.supports_feature("nonexistent_feature")

    def test_supports_savepoints(self):
        """Test savepoint support property."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        assert adapter.supports_savepoints is True

    def test_supports_transactions(self):
        """Test transaction support property."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        assert adapter.supports_transactions is True

    def test_get_tables_query(self):
        """Test getting tables list query."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        tables_query = adapter.get_tables_query()

        assert "INFORMATION_SCHEMA.TABLES" in tables_query
        assert "TABLE_SCHEMA = 'testdb'" in tables_query
        assert "TABLE_TYPE = 'BASE TABLE'" in tables_query

    def test_get_columns_query(self):
        """Test getting column info query."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        columns_query = adapter.get_columns_query("users")

        assert "INFORMATION_SCHEMA.COLUMNS" in columns_query
        assert "TABLE_SCHEMA = 'testdb'" in columns_query
        assert "TABLE_NAME = 'users'" in columns_query

    def test_encode_string_utf8mb4(self):
        """Test string encoding with utf8mb4 charset."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        text = "Hello 世界 🌍"
        encoded = adapter.encode_string(text)

        assert encoded == text  # UTF-8 should handle all characters

    def test_encode_string_latin1(self):
        """Test string encoding with latin1 charset."""
        adapter = MySQLAdapter(
            "mysql://test:test@localhost:3306/testdb", charset="latin1"
        )

        text = "Hello World"
        encoded = adapter.encode_string(text)

        assert encoded == text

    def test_decode_string(self):
        """Test string decoding."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        text = "Hello World"
        decoded = adapter.decode_string(text)

        assert decoded == text

    @pytest.mark.asyncio
    async def test_get_table_schema(self):
        """Test getting table schema from INFORMATION_SCHEMA."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock query result
        mock_rows = [
            {
                "COLUMN_NAME": "id",
                "COLUMN_TYPE": "int(11)",
                "IS_NULLABLE": "NO",
                "COLUMN_KEY": "PRI",
                "COLUMN_DEFAULT": None,
                "EXTRA": "auto_increment",
                "CHARACTER_MAXIMUM_LENGTH": None,
                "NUMERIC_PRECISION": 10,
                "NUMERIC_SCALE": 0,
            },
            {
                "COLUMN_NAME": "name",
                "COLUMN_TYPE": "varchar(255)",
                "IS_NULLABLE": "YES",
                "COLUMN_KEY": "",
                "COLUMN_DEFAULT": None,
                "EXTRA": "",
                "CHARACTER_MAXIMUM_LENGTH": 255,
                "NUMERIC_PRECISION": None,
                "NUMERIC_SCALE": None,
            },
        ]

        # Mock execute_query
        adapter.is_connected = True
        with patch.object(
            adapter, "execute_query", new_callable=AsyncMock, return_value=mock_rows
        ):
            schema = await adapter.get_table_schema("users")

        assert "id" in schema
        assert schema["id"]["type"] == "int(11)"
        assert schema["id"]["nullable"] is False
        assert schema["id"]["primary_key"] is True
        assert schema["id"]["auto_increment"] is True

        assert "name" in schema
        assert schema["name"]["type"] == "varchar(255)"
        assert schema["name"]["nullable"] is True
        assert schema["name"]["max_length"] == 255

    @pytest.mark.asyncio
    async def test_create_table(self):
        """Test table creation."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        schema = {
            "id": {
                "type": "INT",
                "nullable": False,
                "primary_key": True,
                "auto_increment": True,
            },
            "name": {
                "type": "VARCHAR(255)",
                "nullable": True,
            },
        }

        adapter.is_connected = True
        with patch.object(
            adapter, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            await adapter.create_table("users", schema)

            # Verify CREATE TABLE query was called
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0][0]
            assert "CREATE TABLE `users`" in call_args
            assert "INT NOT NULL AUTO_INCREMENT" in call_args
            assert "VARCHAR(255)" in call_args
            assert "PRIMARY KEY" in call_args
            assert "ENGINE=InnoDB" in call_args
            assert "CHARSET=utf8mb4" in call_args

    @pytest.mark.asyncio
    async def test_drop_table(self):
        """Test table drop."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        adapter.is_connected = True
        with patch.object(
            adapter, "execute_query", new_callable=AsyncMock
        ) as mock_execute:
            await adapter.drop_table("users")

            # Verify DROP TABLE query was called
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0][0]
            assert "DROP TABLE IF EXISTS `users`" in call_args

    @pytest.mark.asyncio
    async def test_get_storage_engines(self):
        """Test getting available storage engines."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock SHOW ENGINES result
        mock_engines = [
            {
                "Engine": "InnoDB",
                "Support": "DEFAULT",
                "Comment": "Supports transactions",
                "Transactions": "YES",
                "XA": "YES",
                "Savepoints": "YES",
            },
            {
                "Engine": "MyISAM",
                "Support": "YES",
                "Comment": "MyISAM storage engine",
                "Transactions": "NO",
                "XA": "NO",
                "Savepoints": "NO",
            },
        ]

        adapter.is_connected = True
        with patch.object(
            adapter, "execute_query", new_callable=AsyncMock, return_value=mock_engines
        ):
            engines = await adapter.get_storage_engines()

        assert "InnoDB" in engines
        assert engines["InnoDB"]["support"] == "DEFAULT"
        assert engines["InnoDB"]["transactions"] == "YES"

        assert "MyISAM" in engines
        assert engines["MyISAM"]["support"] == "YES"
        assert engines["MyISAM"]["transactions"] == "NO"

    @pytest.mark.asyncio
    async def test_get_server_version(self):
        """Test getting MySQL server version."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        adapter.is_connected = True
        with patch.object(
            adapter,
            "execute_query",
            new_callable=AsyncMock,
            return_value=[{"version": "8.0.32"}],
        ):
            version = await adapter.get_server_version()

        assert version == "8.0.32"

    @pytest.mark.asyncio
    async def test_get_database_size(self):
        """Test getting database size."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        adapter.is_connected = True
        with patch.object(
            adapter,
            "execute_query",
            new_callable=AsyncMock,
            return_value=[{"size_bytes": 1024000}],
        ):
            size = await adapter.get_database_size()

        assert size == 1024000

    @pytest.mark.asyncio
    async def test_transaction_context_success(self):
        """Test transaction context manager with successful commit."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock connection
        mock_connection = AsyncMock()
        mock_connection.begin = AsyncMock()
        mock_connection.commit = AsyncMock()
        mock_connection.rollback = AsyncMock()

        # Mock pool
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = Mock()

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        async with adapter.transaction() as trans:
            # Successful transaction
            pass

        # Verify transaction lifecycle
        mock_connection.begin.assert_called_once()
        mock_connection.commit.assert_called_once()
        mock_connection.rollback.assert_not_called()
        mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_transaction_context_rollback(self):
        """Test transaction context manager with rollback on error."""
        adapter = MySQLAdapter("mysql://test:test@localhost:3306/testdb")

        # Mock connection
        mock_connection = AsyncMock()
        mock_connection.begin = AsyncMock()
        mock_connection.commit = AsyncMock()
        mock_connection.rollback = AsyncMock()

        # Mock pool
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)
        mock_pool.release = Mock()

        adapter.connection_pool = mock_pool
        adapter.is_connected = True

        try:
            async with adapter.transaction() as trans:
                # Raise error to trigger rollback
                raise Exception("Transaction failed")
        except Exception:
            pass

        # Verify transaction was rolled back
        mock_connection.begin.assert_called_once()
        mock_connection.commit.assert_not_called()
        mock_connection.rollback.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_connection)
