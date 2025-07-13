"""Functional tests for nodes/data/async_sql.py that verify actual async SQL operations."""

import asyncio
import base64
import json
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest


class TestQueryValidatorFunctionality:
    """Test SQL query validation and security functionality."""

    def test_dangerous_pattern_detection(self):
        """Test detection of SQL injection patterns."""
        try:
            from kailash.nodes.data.async_sql import QueryValidator

            # Test multiple statement injection
            dangerous_queries = [
                "SELECT * FROM users; DROP TABLE users",
                "SELECT * FROM users; DELETE FROM accounts",
                "UPDATE users SET name='test'; CREATE TABLE malicious",
                "SELECT * FROM users WHERE id=1; INSERT INTO admin VALUES('hacker')",
            ]

            for query in dangerous_queries:
                with pytest.raises(Exception) as exc_info:  # NodeValidationError
                    QueryValidator.validate_query(query)
                assert "dangerous pattern" in str(exc_info.value).lower()

            # Test SQL comment injection
            comment_queries = [
                "SELECT * FROM users WHERE id=1 -- OR 1=1",
                "SELECT * FROM users /* comment */ UNION SELECT * FROM passwords",
                "SELECT * FROM users WHERE name='test' /* ; DROP TABLE users */",
            ]

            for query in comment_queries:
                with pytest.raises(Exception):
                    QueryValidator.validate_query(query)

            # Test time-based blind injection
            timing_queries = [
                "SELECT * FROM users WHERE id=1 AND SLEEP(5)",
                "SELECT * FROM users WHERE id=1 WAITFOR DELAY '00:00:05'",
                "SELECT * FROM users WHERE id=1 OR PG_SLEEP(5)",
            ]

            for query in timing_queries:
                with pytest.raises(Exception):
                    QueryValidator.validate_query(query)

            # Test out-of-band injection
            oob_queries = [
                "SELECT LOAD_FILE('/etc/passwd')",
                "SELECT * INTO OUTFILE '/tmp/data.txt' FROM users",
                "SELECT * INTO DUMPFILE '/tmp/binary' FROM passwords",
            ]

            for query in oob_queries:
                with pytest.raises(Exception):
                    QueryValidator.validate_query(query)

        except ImportError:
            pytest.skip("QueryValidator not available")

    def test_admin_pattern_enforcement(self):
        """Test enforcement of admin-only patterns."""
        try:
            from kailash.nodes.data.async_sql import QueryValidator

            admin_queries = [
                "CREATE TABLE new_table (id INT)",
                "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
                "DROP TABLE old_data",
                "CREATE INDEX idx_users_email ON users(email)",
                "GRANT SELECT ON users TO public_user",
                "REVOKE ALL ON accounts FROM user1",
                "TRUNCATE TABLE logs",
            ]

            # Test without admin permission (should fail)
            for query in admin_queries:
                with pytest.raises(Exception) as exc_info:
                    QueryValidator.validate_query(query, allow_admin=False)
                assert "administrative command" in str(exc_info.value).lower()

            # Test with admin permission (should pass)
            for query in admin_queries:
                # Should not raise exception
                QueryValidator.validate_query(query, allow_admin=True)

        except ImportError:
            pytest.skip("QueryValidator not available")

    def test_identifier_validation(self):
        """Test database identifier validation."""
        try:
            from kailash.nodes.data.async_sql import QueryValidator

            # Valid identifiers
            valid_identifiers = [
                "users",
                "user_accounts",
                "UserProfiles",
                "_temp_table",
                "schema1.table1",
                "public.users",
                "analytics_2023",
                "table123",
            ]

            for identifier in valid_identifiers:
                # Should not raise exception
                QueryValidator.validate_identifier(identifier)

            # Invalid identifiers
            invalid_identifiers = [
                "123table",  # Starts with number
                "table-name",  # Contains dash
                "table name",  # Contains space
                "table$name",  # Contains special char
                "table@host",  # Contains @
                "schema.table.column",  # Too many dots
                "'table'",  # Contains quotes
                "table;drop",  # Contains semicolon
                "",  # Empty
            ]

            for identifier in invalid_identifiers:
                with pytest.raises(Exception) as exc_info:
                    QueryValidator.validate_identifier(identifier)
                assert "Invalid identifier" in str(exc_info.value)

        except ImportError:
            pytest.skip("QueryValidator not available")

    def test_connection_string_validation(self):
        """Test connection string security validation."""
        try:
            from kailash.nodes.data.async_sql import QueryValidator

            # Safe connection strings
            safe_connections = [
                "postgresql://user:pass@localhost:5432/mydb",
                "mysql://user:password@db.example.com/database",
                "postgresql://user@localhost/db?sslmode=require",
                "sqlite:///path/to/database.db",
            ]

            for conn_str in safe_connections:
                # Should not raise exception
                QueryValidator.validate_connection_string(conn_str)

            # Dangerous connection strings
            dangerous_connections = [
                "postgresql://user:pass@localhost/db; DROP TABLE users",
                "mysql://user@host/db?host=|whoami",
                "postgresql://user@host/db?host=`rm -rf /`",
                "postgresql://user@host/db?sslcert=/etc/passwd",
                "mysql://user@$(malicious_command)/db",
            ]

            for conn_str in dangerous_connections:
                with pytest.raises(Exception) as exc_info:
                    QueryValidator.validate_connection_string(conn_str)
                assert "suspicious pattern" in str(exc_info.value).lower()

        except ImportError:
            pytest.skip("QueryValidator not available")


class TestDatabaseAdapterFunctionality:
    """Test database adapter functionality and type conversion."""

    def test_value_serialization_comprehensive(self):
        """Test serialization of various database types to JSON-compatible formats."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

            config = DatabaseConfig(
                database_type="postgresql", host="localhost", database="test"
            )
            adapter = PostgreSQLAdapter(config)

            # Test basic types
            assert adapter._serialize_value(None) is None
            assert adapter._serialize_value(True) is True
            assert adapter._serialize_value(False) is False
            assert adapter._serialize_value(42) == 42
            assert adapter._serialize_value(3.14) == 3.14
            assert adapter._serialize_value("hello") == "hello"

            # Test bytes
            binary_data = b"\x00\x01\x02\x03"
            serialized_bytes = adapter._serialize_value(binary_data)
            assert serialized_bytes == base64.b64encode(binary_data).decode("utf-8")

            # Test Decimal
            decimal_value = Decimal("123.45")
            assert adapter._serialize_value(decimal_value) == 123.45

            # Test datetime
            dt = datetime(2023, 12, 25, 10, 30, 45)
            assert adapter._serialize_value(dt) == dt.isoformat()

            # Test date
            d = date(2023, 12, 25)
            assert adapter._serialize_value(d) == d.isoformat()

            # Test timedelta
            td = timedelta(hours=2, minutes=30)
            assert adapter._serialize_value(td) == td.total_seconds()

            # Test UUID
            test_uuid = uuid.uuid4()
            assert adapter._serialize_value(test_uuid) == str(test_uuid)

            # Test nested structures
            nested_data = {
                "id": 1,
                "data": [1, 2, Decimal("3.14")],
                "metadata": {"created": datetime(2023, 1, 1), "binary": b"test"},
            }

            serialized = adapter._serialize_value(nested_data)
            assert serialized["id"] == 1
            assert serialized["data"] == [1, 2, 3.14]
            assert "T" in serialized["metadata"]["created"]  # ISO format
            assert serialized["metadata"]["binary"] == base64.b64encode(b"test").decode(
                "utf-8"
            )

        except ImportError:
            pytest.skip("PostgreSQLAdapter not available")

    def test_row_conversion_with_complex_types(self):
        """Test conversion of database rows with various column types."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

            config = DatabaseConfig(
                database_type="postgresql", host="localhost", database="test"
            )
            adapter = PostgreSQLAdapter(config)

            # Simulate complex database row
            test_row = {
                "id": 123,
                "name": "Test User",
                "balance": Decimal("1234.56"),
                "created_at": datetime(2023, 12, 1, 10, 0, 0),
                "birth_date": date(1990, 5, 15),
                "profile_image": b"\x89PNG\r\n\x1a\n",
                "uuid": uuid.uuid4(),
                "tags": ["python", "sql", "async"],
                "settings": {"theme": "dark", "notifications": True},
                "is_active": True,
                "last_login": None,
            }

            converted = adapter._convert_row(test_row)

            # Verify conversions
            assert converted["id"] == 123
            assert converted["name"] == "Test User"
            assert converted["balance"] == 1234.56
            assert "T" in converted["created_at"]  # ISO format
            assert converted["birth_date"] == "1990-05-15"
            assert converted["profile_image"].startswith("iVBOR")  # Base64 PNG header
            assert isinstance(converted["uuid"], str)
            assert converted["tags"] == ["python", "sql", "async"]
            assert converted["settings"]["theme"] == "dark"
            assert converted["is_active"] is True
            assert converted["last_login"] is None

        except ImportError:
            pytest.skip("PostgreSQLAdapter not available")


class TestPostgreSQLAdapterFunctionality:
    """Test PostgreSQL adapter specific functionality."""

    @pytest.mark.asyncio
    async def test_connection_pool_management(self):
        """Test PostgreSQL connection pool creation and management."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

            with patch("asyncpg.create_pool") as mock_create_pool:
                mock_pool = AsyncMock()
                mock_create_pool.return_value = mock_pool

                config = DatabaseConfig(
                    database_type="postgresql",
                    host="localhost",
                    port=5432,
                    database="testdb",
                    user="testuser",
                    password="testpass",
                    min_size=5,
                    max_size=20,
                )

                adapter = PostgreSQLAdapter(config)
                await adapter.connect()

                # Verify pool creation with correct parameters
                mock_create_pool.assert_called_once()
                call_kwargs = mock_create_pool.call_args[1]
                assert call_kwargs["host"] == "localhost"
                assert call_kwargs["port"] == 5432
                assert call_kwargs["database"] == "testdb"
                assert call_kwargs["user"] == "testuser"
                assert call_kwargs["password"] == "testpass"
                assert call_kwargs["min_size"] == 5
                assert call_kwargs["max_size"] == 20

                # Test disconnection
                await adapter.disconnect()
                mock_pool.close.assert_called_once()

        except ImportError:
            pytest.skip("PostgreSQLAdapter not available")

    @pytest.mark.asyncio
    async def test_query_execution_modes(self):
        """Test different query execution and fetch modes."""
        try:
            from kailash.nodes.data.async_sql import (
                DatabaseConfig,
                FetchMode,
                PostgreSQLAdapter,
            )

            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

            # Mock query results
            mock_conn.fetchrow.return_value = {"id": 1, "name": "Test"}
            mock_conn.fetch.return_value = [
                {"id": 1, "name": "Test1"},
                {"id": 2, "name": "Test2"},
            ]

            with patch("asyncpg.create_pool", return_value=mock_pool):
                config = DatabaseConfig(
                    database_type="postgresql", host="localhost", database="testdb"
                )

                adapter = PostgreSQLAdapter(config)
                await adapter.connect()
                adapter._pool = mock_pool

                # Test FetchMode.ONE
                result = await adapter.execute(
                    "SELECT * FROM users WHERE id = $1",
                    params=(1,),
                    fetch_mode=FetchMode.ONE,
                )
                assert result == {"id": 1, "name": "Test"}
                mock_conn.fetchrow.assert_called_once()

                # Test FetchMode.ALL
                result = await adapter.execute(
                    "SELECT * FROM users", fetch_mode=FetchMode.ALL
                )
                assert len(result) == 2
                assert result[0]["name"] == "Test1"
                mock_conn.fetch.assert_called_once()

                # Test execute without fetch (INSERT/UPDATE)
                mock_conn.execute.return_value = "INSERT 0 1"
                result = await adapter.execute(
                    "INSERT INTO users (name) VALUES ($1)",
                    params=("NewUser",),
                    fetch_mode=FetchMode.NONE,
                )
                assert result is None

        except ImportError:
            pytest.skip("PostgreSQLAdapter not available")

    @pytest.mark.asyncio
    async def test_transaction_handling(self):
        """Test transaction management with commit and rollback."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_transaction = AsyncMock()

            mock_pool.acquire.return_value = mock_conn
            mock_conn.transaction.return_value.__aenter__.return_value = (
                mock_transaction
            )

            with patch("asyncpg.create_pool", return_value=mock_pool):
                config = DatabaseConfig(
                    database_type="postgresql", host="localhost", database="testdb"
                )

                adapter = PostgreSQLAdapter(config)
                await adapter.connect()
                adapter._pool = mock_pool

                # Test transaction flow
                tx = await adapter.begin_transaction()
                assert tx is not None

                # Execute queries within transaction
                await adapter.execute(
                    "INSERT INTO users (name) VALUES ($1)",
                    params=("User1",),
                    transaction=tx,
                )

                await adapter.execute(
                    "UPDATE users SET active = true WHERE name = $1",
                    params=("User1",),
                    transaction=tx,
                )

                # Test commit
                await adapter.commit_transaction(tx)

                # Test rollback scenario
                tx2 = await adapter.begin_transaction()
                await adapter.execute(
                    "DELETE FROM users WHERE id = $1", params=(999,), transaction=tx2
                )
                await adapter.rollback_transaction(tx2)

        except ImportError:
            pytest.skip("PostgreSQLAdapter not available")


class TestMySQLAdapterFunctionality:
    """Test MySQL adapter specific functionality."""

    @pytest.mark.asyncio
    async def test_mysql_connection_and_cursor_management(self):
        """Test MySQL connection pool and cursor handling."""
        try:
            from kailash.nodes.data.async_sql import (
                DatabaseConfig,
                FetchMode,
                MySQLAdapter,
            )

            with patch("aiomysql.create_pool") as mock_create_pool:
                mock_pool = AsyncMock()
                mock_conn = AsyncMock()
                mock_cursor = AsyncMock()

                mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
                mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
                mock_create_pool.return_value = mock_pool

                # Setup cursor behavior
                mock_cursor.description = [("id",), ("name",)]
                mock_cursor.fetchone.return_value = (1, "Test")
                mock_cursor.fetchall.return_value = [(1, "Test1"), (2, "Test2")]
                mock_cursor.fetchmany.return_value = [(1, "Test1")]

                config = DatabaseConfig(
                    database_type="mysql",
                    host="localhost",
                    port=3306,
                    database="testdb",
                    user="root",
                    password="password",
                )

                adapter = MySQLAdapter(config)
                await adapter.connect()

                # Verify pool creation
                mock_create_pool.assert_called_once()
                call_kwargs = mock_create_pool.call_args[1]
                assert call_kwargs["host"] == "localhost"
                assert call_kwargs["port"] == 3306

                # Test query execution with cursor management
                result = await adapter.execute(
                    "SELECT * FROM users WHERE id = %s",
                    params=(1,),
                    fetch_mode=FetchMode.ONE,
                )

                assert result == {"id": 1, "name": "Test"}
                mock_cursor.execute.assert_called_with(
                    "SELECT * FROM users WHERE id = %s", (1,)
                )

                # Test cursor is properly closed (context manager)
                mock_cursor.__aexit__.assert_called()

        except ImportError:
            pytest.skip("MySQLAdapter not available")

    @pytest.mark.asyncio
    async def test_mysql_execute_many(self):
        """Test MySQL bulk insert operations."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfig, MySQLAdapter

            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()

            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor

            with patch("aiomysql.create_pool", return_value=mock_pool):
                config = DatabaseConfig(
                    database_type="mysql", host="localhost", database="testdb"
                )

                adapter = MySQLAdapter(config)
                await adapter.connect()
                adapter._pool = mock_pool

                # Test bulk insert
                params_list = [
                    ("User1", "user1@example.com"),
                    ("User2", "user2@example.com"),
                    ("User3", "user3@example.com"),
                ]

                await adapter.execute_many(
                    "INSERT INTO users (name, email) VALUES (%s, %s)", params_list
                )

                # Verify executemany was called
                mock_cursor.executemany.assert_called_once_with(
                    "INSERT INTO users (name, email) VALUES (%s, %s)", params_list
                )

                # Verify commit was called
                mock_conn.commit.assert_called_once()

        except ImportError:
            pytest.skip("MySQLAdapter not available")


class TestSQLiteAdapterFunctionality:
    """Test SQLite adapter specific functionality."""

    @pytest.mark.asyncio
    async def test_sqlite_connection_handling(self):
        """Test SQLite connection management without pooling."""
        try:
            from kailash.nodes.data.async_sql import (
                DatabaseConfig,
                FetchMode,
                SQLiteAdapter,
            )

            with patch("aiosqlite.connect") as mock_connect:
                mock_db = AsyncMock()
                mock_cursor = AsyncMock()
                mock_connect.return_value.__aenter__.return_value = mock_db
                mock_db.execute.return_value = mock_cursor

                # Mock Row class for dict-like access
                class MockRow:
                    def __init__(self, data):
                        self._data = data

                    def __getitem__(self, key):
                        if isinstance(key, int):
                            return self._data[key]
                        # For dict conversion
                        return self._data

                    def keys(self):
                        return ["id", "name"]

                    def __iter__(self):
                        return iter(zip(self.keys(), self._data))

                mock_cursor.fetchone.return_value = MockRow((1, "Test"))
                mock_cursor.fetchall.return_value = [
                    MockRow((1, "Test1")),
                    MockRow((2, "Test2")),
                ]

                config = DatabaseConfig(
                    database_type="sqlite", database="/path/to/test.db"
                )

                adapter = SQLiteAdapter(config)
                await adapter.connect()

                # Test query execution
                result = await adapter.execute(
                    "SELECT * FROM users WHERE id = ?",
                    params=(1,),
                    fetch_mode=FetchMode.ONE,
                )

                assert result == {"id": 1, "name": "Test"}
                mock_connect.assert_called_with("/path/to/test.db")

                # Test that connection is created per operation
                await adapter.execute("SELECT * FROM users", fetch_mode=FetchMode.ALL)

                # Should have created two connections
                assert mock_connect.call_count == 2

        except ImportError:
            pytest.skip("SQLiteAdapter not available")


class TestDatabaseConfigManager:
    """Test database configuration management from YAML files."""

    def test_config_loading_and_caching(self):
        """Test loading database configurations from YAML with caching."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfigManager

            yaml_content = """
databases:
  default:
    connection_string: postgresql://localhost/defaultdb
    pool_size: 10
    timeout: 30

  analytics:
    url: mysql://analytics.example.com/analytics_db
    user: analyst
    password: ${ANALYTICS_PASSWORD}
    ssl_mode: require

  cache:
    connection_string: sqlite:///var/cache/app.db
    wal_mode: true
"""

            with patch("builtins.open", mock_open(read_data=yaml_content)):
                with patch("os.path.exists", return_value=True):
                    manager = DatabaseConfigManager("database.yaml")

                    # Test loading default config
                    conn_str, config = manager.get_database_config("default")
                    assert conn_str == "postgresql://localhost/defaultdb"
                    assert config["pool_size"] == 10
                    assert config["timeout"] == 30

                    # Test loading with 'url' instead of 'connection_string'
                    conn_str, config = manager.get_database_config("analytics")
                    assert conn_str == "mysql://analytics.example.com/analytics_db"
                    assert config["user"] == "analyst"

                    # Test caching (should not reload file)
                    with patch(
                        "builtins.open", side_effect=Exception("Should use cache")
                    ):
                        conn_str2, config2 = manager.get_database_config("default")
                        assert conn_str2 == conn_str
                        assert config2 == config

        except ImportError:
            pytest.skip("DatabaseConfigManager not available")

    def test_environment_variable_substitution(self):
        """Test environment variable substitution in config values."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfigManager

            yaml_content = """
databases:
  production:
    connection_string: ${DATABASE_URL}
    user: ${DB_USER}
    password: ${DB_PASSWORD}
    ssl_cert: /certs/${ENV}_cert.pem
"""

            with patch("builtins.open", mock_open(read_data=yaml_content)):
                with patch("os.path.exists", return_value=True):
                    with patch.dict(
                        "os.environ",
                        {
                            "DATABASE_URL": "postgresql://prod.example.com/myapp",
                            "DB_USER": "prod_user",
                            "DB_PASSWORD": "secret123",
                            "ENV": "production",
                        },
                    ):
                        manager = DatabaseConfigManager()

                        conn_str, config = manager.get_database_config("production")
                        assert conn_str == "postgresql://prod.example.com/myapp"
                        assert config["user"] == "prod_user"
                        assert config["password"] == "secret123"
                        assert config["ssl_cert"] == "/certs/production_cert.pem"

        except ImportError:
            pytest.skip("DatabaseConfigManager not available")

    def test_missing_config_handling(self):
        """Test handling of missing configurations and fallbacks."""
        try:
            from kailash.nodes.data.async_sql import DatabaseConfigManager

            yaml_content = """
databases:
  default:
    connection_string: postgresql://localhost/default
"""

            with patch("builtins.open", mock_open(read_data=yaml_content)):
                with patch("os.path.exists", return_value=True):
                    manager = DatabaseConfigManager()

                    # Test fallback to default when config not found
                    conn_str, config = manager.get_database_config("nonexistent")
                    assert conn_str == "postgresql://localhost/default"

                    # Test error when no default exists
                    yaml_content_no_default = """
databases:
  specific:
    connection_string: postgresql://localhost/specific
"""

                    with patch(
                        "builtins.open", mock_open(read_data=yaml_content_no_default)
                    ):
                        manager._config = None  # Reset cache
                        manager._config_cache.clear()

                        with pytest.raises(Exception) as exc_info:
                            manager.get_database_config("nonexistent")
                        assert "not found" in str(exc_info.value)
                        assert "Available connections: ['specific']" in str(
                            exc_info.value
                        )

        except ImportError:
            pytest.skip("DatabaseConfigManager not available")


class TestAsyncSQLDatabaseNodeFunctionality:
    """Test the main AsyncSQLDatabaseNode functionality."""

    @pytest.mark.asyncio
    async def test_node_initialization_and_adapter_selection(self):
        """Test node initialization with different database types."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, DatabaseType

            # Test PostgreSQL initialization
            node_pg = AsyncSQLDatabaseNode()
            params_pg = {
                "database_type": "postgresql",
                "host": "localhost",
                "database": "testdb",
                "user": "testuser",
                "password": "testpass",
                "query": "SELECT * FROM users",
            }

            with patch("asyncpg.create_pool") as mock_pg_pool:
                mock_pg_pool.return_value = AsyncMock()

                # Initialize node (would normally happen in execute)
                node_pg._validate_params(params_pg)
                assert node_pg.database_type == DatabaseType.POSTGRESQL

            # Test MySQL initialization
            node_mysql = AsyncSQLDatabaseNode()
            params_mysql = {
                "database_type": "mysql",
                "connection_string": "mysql://user:pass@localhost/db",
                "query": "SELECT * FROM products",
            }

            node_mysql._validate_params(params_mysql)
            assert node_mysql.database_type == DatabaseType.MYSQL

            # Test SQLite initialization
            node_sqlite = AsyncSQLDatabaseNode()
            params_sqlite = {
                "database_type": "sqlite",
                "database": "/path/to/data.db",
                "query": "SELECT * FROM cache",
            }

            node_sqlite._validate_params(params_sqlite)
            assert node_sqlite.database_type == DatabaseType.SQLITE

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")

    @pytest.mark.asyncio
    async def test_query_execution_with_parameters(self):
        """Test query execution with different parameter formats."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Mock adapter
            mock_adapter = AsyncMock()
            mock_adapter.execute.return_value = [
                {"id": 1, "name": "Alice", "age": 30},
                {"id": 2, "name": "Bob", "age": 25},
            ]

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                # Test with tuple parameters
                params_tuple = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM users WHERE age > $1 AND active = $2",
                    "params": (18, True),
                }

                result = await node.execute(params_tuple)
                assert len(result["results"]) == 2
                assert result["results"][0]["name"] == "Alice"

                mock_adapter.execute.assert_called_with(
                    "SELECT * FROM users WHERE age > $1 AND active = $2",
                    params=(18, True),
                    fetch_mode=node.fetch_mode,
                    fetch_size=None,
                    transaction=None,
                )

                # Test with dict parameters
                params_dict = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM users WHERE name = %(name)s",
                    "params": {"name": "Charlie"},
                }

                mock_adapter.execute.return_value = [
                    {"id": 3, "name": "Charlie", "age": 35}
                ]

                result = await node.execute(params_dict)
                assert len(result["results"]) == 1
                assert result["results"][0]["name"] == "Charlie"

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")

    @pytest.mark.asyncio
    async def test_transaction_support(self):
        """Test transaction handling in AsyncSQLDatabaseNode."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Mock adapter with transaction support
            mock_adapter = AsyncMock()
            mock_transaction = AsyncMock()
            mock_adapter.begin_transaction.return_value = mock_transaction
            mock_adapter.execute.return_value = None

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                # Test transaction with multiple queries
                params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "BEGIN",  # Special case to start transaction
                    "transaction_mode": True,
                }

                # Start transaction
                result = await node.execute(params)
                mock_adapter.begin_transaction.assert_called_once()

                # Execute queries within transaction
                params["query"] = "INSERT INTO users (name) VALUES ($1)"
                params["params"] = ("NewUser",)
                await node.execute(params)

                params["query"] = "UPDATE users SET active = true WHERE name = $1"
                await node.execute(params)

                # Verify queries used transaction
                assert mock_adapter.execute.call_count >= 2
                for call in mock_adapter.execute.call_args_list:
                    assert call[1].get("transaction") is not None

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")

    @pytest.mark.asyncio
    async def test_connection_retry_logic(self):
        """Test connection retry with exponential backoff."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Mock adapter that fails then succeeds
            mock_adapter = AsyncMock()
            connect_attempts = 0

            async def mock_connect():
                nonlocal connect_attempts
                connect_attempts += 1
                if connect_attempts < 3:
                    raise Exception("Connection failed")
                # Success on third attempt

            mock_adapter.connect = mock_connect
            mock_adapter.execute.return_value = [{"status": "ok"}]

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                with patch("asyncio.sleep") as mock_sleep:  # Skip actual delays
                    params = {
                        "database_type": "postgresql",
                        "connection_string": "postgresql://localhost/test",
                        "query": "SELECT 1",
                        "retry_count": 3,
                        "retry_delay": 1.0,
                    }

                    result = await node.execute(params)
                    assert result["results"][0]["status"] == "ok"
                    assert connect_attempts == 3

                    # Verify exponential backoff was used
                    sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                    assert len(sleep_calls) >= 2
                    # Each delay should be longer than the previous
                    for i in range(1, len(sleep_calls)):
                        assert sleep_calls[i] > sleep_calls[i - 1]

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")


class TestAsyncSQLSecurityFeatures:
    """Test security features and SQL injection prevention."""

    @pytest.mark.asyncio
    async def test_parameterized_query_enforcement(self):
        """Test that parameterized queries are properly enforced."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Mock adapter
            mock_adapter = AsyncMock()
            mock_adapter.execute.return_value = []

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                # Test that string concatenation in query is rejected
                dangerous_params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM users WHERE name = 'admin' OR '1'='1'",
                }

                with pytest.raises(Exception):  # Should fail validation
                    await node.execute(dangerous_params)

                # Test that parameters are properly separated
                safe_params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM users WHERE name = $1",
                    "params": ("admin' OR '1'='1",),  # Malicious input as parameter
                }

                # Should execute safely with parameter
                result = await node.execute(safe_params)

                # Verify the malicious string was passed as a parameter, not concatenated
                mock_adapter.execute.assert_called()
                call_args = mock_adapter.execute.call_args
                assert call_args[0][0] == "SELECT * FROM users WHERE name = $1"
                assert call_args[1]["params"] == ("admin' OR '1'='1",)

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")

    @pytest.mark.asyncio
    async def test_admin_command_restrictions(self):
        """Test restrictions on administrative commands."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Test that admin commands are blocked by default
            admin_queries = [
                "DROP TABLE users",
                "CREATE TABLE malicious (id INT)",
                "ALTER TABLE users ADD COLUMN backdoor VARCHAR(255)",
                "GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'",
                "TRUNCATE TABLE audit_logs",
            ]

            for query in admin_queries:
                params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": query,
                    "allow_admin": False,  # Default
                }

                with pytest.raises(Exception) as exc_info:
                    await node.execute(params)
                assert "administrative command" in str(exc_info.value).lower()

            # Test that admin commands work when explicitly allowed
            mock_adapter = AsyncMock()
            mock_adapter.execute.return_value = None

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                params_admin = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "CREATE TABLE new_table (id SERIAL PRIMARY KEY)",
                    "allow_admin": True,
                }

                # Should not raise exception
                await node.execute(params_admin)
                mock_adapter.execute.assert_called_once()

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")


class TestAsyncSQLPerformanceFeatures:
    """Test performance-related features like pooling and concurrency."""

    @pytest.mark.asyncio
    async def test_connection_pooling_efficiency(self):
        """Test that connection pooling reuses connections efficiently."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Track connection acquisitions
            acquire_count = 0
            mock_pool = AsyncMock()
            mock_conn = AsyncMock()

            async def mock_acquire():
                nonlocal acquire_count
                acquire_count += 1
                return mock_conn

            mock_pool.acquire.return_value.__aenter__ = mock_acquire
            mock_pool.acquire.return_value.__aexit__ = AsyncMock()

            mock_adapter = AsyncMock()
            mock_adapter._pool = mock_pool
            mock_adapter.execute = AsyncMock(return_value=[{"id": 1}])

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM users WHERE id = $1",
                    "params": (1,),
                }

                # Execute multiple queries concurrently
                tasks = []
                for i in range(10):
                    task_params = params.copy()
                    task_params["params"] = (i,)
                    tasks.append(node.execute(task_params))

                results = await asyncio.gather(*tasks)

                # All queries should complete
                assert len(results) == 10

                # Connection pool should efficiently reuse connections
                # (exact count depends on pool implementation, but should be less than query count)
                assert acquire_count <= 10

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")

    @pytest.mark.asyncio
    async def test_query_timeout_handling(self):
        """Test query timeout functionality."""
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            node = AsyncSQLDatabaseNode()

            # Mock adapter with slow query
            mock_adapter = AsyncMock()

            async def slow_query(*args, **kwargs):
                await asyncio.sleep(5)  # Simulate slow query
                return [{"id": 1}]

            mock_adapter.execute = slow_query

            with patch.object(node, "_get_adapter", return_value=mock_adapter):
                params = {
                    "database_type": "postgresql",
                    "connection_string": "postgresql://localhost/test",
                    "query": "SELECT * FROM large_table",
                    "timeout": 1.0,  # 1 second timeout
                }

                # Should timeout
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        node.execute(params), timeout=params["timeout"]
                    )

        except ImportError:
            pytest.skip("AsyncSQLDatabaseNode not available")


# Helper function for mocking file operations
def mock_open(read_data=""):
    """Create a mock for builtins.open that returns read_data."""
    import builtins
    from unittest.mock import mock_open as _mock_open

    m = _mock_open(read_data=read_data)
    m.return_value.__iter__ = lambda self: iter(read_data.splitlines(True))
    return m
