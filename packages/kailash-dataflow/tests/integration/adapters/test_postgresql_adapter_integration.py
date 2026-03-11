"""
Integration tests for PostgreSQL database adapter with REAL infrastructure.

Tests PostgreSQL-specific functionality using real database connections.
NO MOCKING - uses shared SDK Docker PostgreSQL on port 5434.
"""

import asyncio
import time

import asyncpg
import pytest
from dataflow.adapters.exceptions import ConnectionError, QueryError
from dataflow.adapters.postgresql import PostgreSQLAdapter

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
class TestPostgreSQLAdapterIntegration:
    """Test PostgreSQL adapter with real database."""

    @pytest.fixture
    async def test_table_name(self):
        """Generate unique table name for test isolation."""
        import random

        return f"test_adapter_{int(time.time())}_{random.randint(1000, 9999)}"

    @pytest.fixture
    async def adapter(self, test_suite):
        """Create PostgreSQL adapter with real connection."""
        # Use test suite database URL
        connection_string = test_suite.config.url
        adapter = PostgreSQLAdapter(connection_string, pool_size=2, max_overflow=2)

        yield adapter

        # Cleanup
        if adapter.is_connected:
            await adapter.close_connection_pool()

    @pytest.fixture
    async def connected_adapter(self, adapter):
        """Create and connect PostgreSQL adapter."""
        await adapter.create_connection_pool()
        return adapter

    @pytest.mark.timeout(5)
    async def test_adapter_initialization(self, test_suite):
        """Test PostgreSQL adapter initializes correctly."""
        connection_string = test_suite.config.url

        adapter = PostgreSQLAdapter(connection_string, pool_size=15, max_overflow=25)

        assert adapter.connection_string == connection_string
        assert adapter.scheme == "postgresql"
        assert adapter.host == "localhost"
        assert adapter.port == 5434
        assert adapter.database == "kailash_test"
        assert adapter.username == "test_user"
        assert adapter.password == "test_password"
        assert adapter.pool_size == 15
        assert adapter.max_overflow == 25
        assert not adapter.is_connected

    @pytest.mark.timeout(5)
    async def test_create_connection_pool_success(self, adapter):
        """Test successful connection pool creation with real database."""
        await adapter.create_connection_pool()

        assert adapter.connection_pool is not None
        assert adapter.is_connected

        # Verify we can acquire a connection
        async with adapter.connection_pool.acquire() as conn:
            # Test the connection with a simple query
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    @pytest.mark.timeout(5)
    async def test_create_connection_pool_failure(self, test_suite):
        """Test connection pool creation failure with bad credentials."""
        # Create invalid connection string by modifying test_suite URL
        bad_connection_string = test_suite.config.url.replace(
            "test_user:test_password", "bad_user:bad_pass"
        )
        adapter = PostgreSQLAdapter(bad_connection_string)

        with pytest.raises(ConnectionError):
            await adapter.create_connection_pool()

        assert adapter.connection_pool is None
        assert not adapter.is_connected

    @pytest.mark.timeout(5)
    async def test_execute_query_success(self, connected_adapter, test_table_name):
        """Test successful query execution with real database."""
        # Create a test table
        create_table_query = f"""
            CREATE TABLE {test_table_name} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL
            )
        """

        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(create_table_query)

            # Insert test data
            await conn.execute(
                f"INSERT INTO {test_table_name} (name) VALUES ($1), ($2)",
                "Alice",
                "Bob",
            )

        # Test query execution
        result = await connected_adapter.execute_query(
            f"SELECT * FROM {test_table_name} ORDER BY id"
        )

        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(5)
    async def test_execute_query_with_params(self, connected_adapter, test_table_name):
        """Test query execution with parameters using real database."""
        # Create and populate test table
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    age INTEGER
                )
            """
            )

            await conn.execute(
                f"INSERT INTO {test_table_name} (name, age) VALUES ($1, $2), ($3, $4)",
                "Alice",
                25,
                "Bob",
                30,
            )

        # Test parameterized query
        result = await connected_adapter.execute_query(
            f"SELECT * FROM {test_table_name} WHERE age > $1", [26]
        )

        assert len(result) == 1
        assert result[0]["name"] == "Bob"
        assert result[0]["age"] == 30

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(5)
    async def test_execute_query_not_connected(self, adapter):
        """Test query execution when not connected."""
        with pytest.raises(ConnectionError):
            await adapter.execute_query("SELECT 1")

    @pytest.mark.timeout(5)
    async def test_execute_query_error(self, connected_adapter):
        """Test query execution with database error."""
        with pytest.raises(QueryError):
            await connected_adapter.execute_query("SELECT * FROM nonexistent_table_xyz")

    @pytest.mark.timeout(5)
    async def test_execute_insert(self, connected_adapter, test_table_name):
        """Test INSERT query execution with real database."""
        # Create test table
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL
                )
            """
            )

        # Test insert
        result = await connected_adapter.execute_insert(
            f"INSERT INTO {test_table_name} (name) VALUES ($1)", ["Charlie"]
        )

        # PostgreSQL returns a string like "INSERT 0 1"
        assert "INSERT" in result or result is None  # Some adapters might return None

        # Verify data was inserted
        rows = await connected_adapter.execute_query(f"SELECT * FROM {test_table_name}")
        assert len(rows) == 1
        assert rows[0]["name"] == "Charlie"

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(5)
    async def test_execute_bulk_insert(self, connected_adapter, test_table_name):
        """Test bulk insert operation with real database."""
        # Create test table
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100)
                )
            """
            )

        # Test bulk insert
        data = [
            ("Alice", "alice@example.com"),
            ("Bob", "bob@example.com"),
            ("Charlie", "charlie@example.com"),
        ]

        await connected_adapter.execute_bulk_insert(
            f"INSERT INTO {test_table_name} (name, email) VALUES ($1, $2)", data
        )

        # Verify all data was inserted
        rows = await connected_adapter.execute_query(
            f"SELECT * FROM {test_table_name} ORDER BY name"
        )
        assert len(rows) == 3
        assert rows[0]["name"] == "Alice"
        assert rows[1]["name"] == "Bob"
        assert rows[2]["name"] == "Charlie"

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(5)
    async def test_close_connection_pool(self, adapter):
        """Test connection pool cleanup with real connection."""
        # First create a connection
        await adapter.create_connection_pool()
        assert adapter.is_connected

        # Close it
        await adapter.close_connection_pool()

        assert adapter.connection_pool is None
        assert not adapter.is_connected

        # Verify we can't execute queries anymore
        with pytest.raises(ConnectionError):
            await adapter.execute_query("SELECT 1")

    @pytest.mark.timeout(5)
    async def test_transaction_context(self, connected_adapter, test_table_name):
        """Test transaction context management with real database."""
        # Create test table
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    value INTEGER NOT NULL
                )
            """
            )

        # Test successful transaction
        async with connected_adapter.transaction() as trans:
            # Insert data within transaction
            await trans.connection.execute(
                f"INSERT INTO {test_table_name} (value) VALUES ($1), ($2)", 10, 20
            )

        # Verify data was committed
        rows = await connected_adapter.execute_query(f"SELECT * FROM {test_table_name}")
        assert len(rows) == 2

        # Test rolled back transaction
        try:
            async with connected_adapter.transaction() as trans:
                await trans.connection.execute(
                    f"INSERT INTO {test_table_name} (value) VALUES ($1)", 30
                )
                # Force an error to trigger rollback
                raise Exception("Test rollback")
        except Exception:
            pass

        # Verify rollback - should still have only 2 rows
        rows = await connected_adapter.execute_query(f"SELECT * FROM {test_table_name}")
        assert len(rows) == 2

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(5)
    async def test_postgresql_specific_features(
        self, connected_adapter, test_table_name
    ):
        """Test PostgreSQL-specific features with real database."""
        # Create table with JSON column
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    data JSONB,
                    tags TEXT[]
                )
            """
            )

            # Insert data with JSON and arrays
            import json

            await conn.execute(
                f"INSERT INTO {test_table_name} (data, tags) VALUES ($1::jsonb, $2)",
                json.dumps({"name": "test", "value": 42}),
                ["tag1", "tag2", "tag3"],
            )

        # Query JSON data
        result = await connected_adapter.execute_query(
            f"SELECT data->>'name' as name FROM {test_table_name}"
        )
        assert result[0]["name"] == "test"

        # Query array data
        result = await connected_adapter.execute_query(
            f"SELECT tags[1] as first_tag FROM {test_table_name}"
        )
        assert result[0]["first_tag"] == "tag1"

        # Test window functions
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {test_table_name} (data, tags)
                VALUES ($1::jsonb, $2), ($3::jsonb, $4)
            """,
                json.dumps({"name": "test2", "value": 100}),
                ["tag4"],
                json.dumps({"name": "test3", "value": 200}),
                ["tag5"],
            )

        result = await connected_adapter.execute_query(
            f"""
            SELECT
                data->>'name' as name,
                ROW_NUMBER() OVER (ORDER BY data->>'value') as row_num
            FROM {test_table_name}
            ORDER BY row_num
        """
        )

        assert len(result) == 3
        assert result[0]["row_num"] == 1
        assert result[1]["row_num"] == 2
        assert result[2]["row_num"] == 3

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    def test_get_dialect(self, adapter):
        """Test PostgreSQL dialect identification."""
        assert adapter.get_dialect() == "postgresql"

    def test_supports_feature(self, adapter):
        """Test PostgreSQL feature support checking."""
        # PostgreSQL supports these features
        assert adapter.supports_feature("json")
        assert adapter.supports_feature("arrays")
        assert adapter.supports_feature("window_functions")
        assert adapter.supports_feature("cte")
        assert adapter.supports_feature("fulltext_search")

        # Doesn't support non-existent features
        assert not adapter.supports_feature("nonexistent_feature")

    def test_format_query_postgresql_style(self, adapter):
        """Test PostgreSQL-style parameter formatting."""
        # Test standard parameter substitution
        query = "SELECT * FROM users WHERE id = ? AND name = ?"
        params = [1, "Alice"]

        formatted_query, formatted_params = adapter.format_query(query, params)

        assert formatted_query == "SELECT * FROM users WHERE id = $1 AND name = $2"
        assert formatted_params == params

    @pytest.mark.timeout(10)
    async def test_get_table_schema_real(self, connected_adapter, test_table_name):
        """Test get_table_schema() with real database - NEW FUNCTIONALITY."""
        # Create a test table with various column types
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    age INTEGER,
                    email VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    balance NUMERIC(10, 2)
                )
            """
            )

        # Test get_table_schema - should return REAL schema now (not mocked)
        schema = await connected_adapter.get_table_schema(test_table_name)

        # Verify schema structure
        assert "id" in schema
        assert "name" in schema
        assert "age" in schema
        assert "email" in schema
        assert "created_at" in schema
        assert "balance" in schema

        # Verify column details
        assert schema["id"]["type"] == "integer"
        assert schema["id"]["primary_key"] is True
        assert schema["id"]["nullable"] is False

        assert schema["name"]["type"] == "character varying"
        assert schema["name"]["nullable"] is False
        assert schema["name"]["max_length"] == 100

        assert schema["age"]["type"] == "integer"
        assert schema["age"]["nullable"] is True

        assert schema["balance"]["type"] == "numeric"
        assert schema["balance"]["precision"] == 10
        assert schema["balance"]["scale"] == 2

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(10)
    async def test_create_table_real(self, connected_adapter, test_table_name):
        """Test create_table() with real database - NEW FUNCTIONALITY."""
        # Define table schema
        schema = {
            "id": {
                "type": "SERIAL",
                "nullable": False,
                "primary_key": True,
            },
            "username": {
                "type": "VARCHAR",
                "max_length": 50,
                "nullable": False,
            },
            "email": {
                "type": "VARCHAR",
                "max_length": 100,
                "nullable": True,
            },
            "age": {
                "type": "INTEGER",
                "nullable": True,
                "default": "18",
            },
        }

        # Test create_table - should actually create table now (not just log)
        await connected_adapter.create_table(test_table_name, schema)

        # Verify table was created by querying it
        async with connected_adapter.connection_pool.acquire() as conn:
            # Check table exists
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
            """,
                test_table_name,
            )
            assert result is True

            # Test inserting data to verify structure
            await conn.execute(
                f"INSERT INTO {test_table_name} (username, email, age) VALUES ($1, $2, $3)",
                "testuser",
                "test@example.com",
                25,
            )

            # Verify data was inserted
            row = await conn.fetchrow(f"SELECT * FROM {test_table_name}")
            assert row["username"] == "testuser"
            assert row["email"] == "test@example.com"
            assert row["age"] == 25

        # Cleanup
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(f"DROP TABLE {test_table_name}")

    @pytest.mark.timeout(10)
    async def test_drop_table_real(self, connected_adapter, test_table_name):
        """Test drop_table() with real database - NEW FUNCTIONALITY."""
        # First create a table
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE {test_table_name} (
                    id SERIAL PRIMARY KEY,
                    data TEXT
                )
            """
            )

            # Verify table exists
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
            """,
                test_table_name,
            )
            assert result is True

        # Test drop_table - should actually drop table now (not just log)
        await connected_adapter.drop_table(test_table_name)

        # Verify table was dropped
        async with connected_adapter.connection_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
            """,
                test_table_name,
            )
            assert result is False

    @pytest.mark.timeout(5)
    async def test_get_server_version_real(self, connected_adapter):
        """Test get_server_version() with real database - NEW METHOD."""
        version = await connected_adapter.get_server_version()

        # Verify we got a real version string
        assert version != "unknown"
        assert "PostgreSQL" in version
        assert len(version) > 10  # Version string should be reasonably long

        # Version should contain version number
        import re

        version_pattern = r"\d+\.\d+"
        assert re.search(
            version_pattern, version
        ), f"No version number found in: {version}"

    @pytest.mark.timeout(5)
    async def test_get_database_size_real(self, connected_adapter):
        """Test get_database_size() with real database - NEW METHOD."""
        size = await connected_adapter.get_database_size()

        # Verify we got a real size
        assert size > 0  # Database should have some size
        assert isinstance(size, int)

        # Size should be reasonable (between 1KB and 1GB for test database)
        assert size > 1024  # At least 1KB
        assert size < 1024 * 1024 * 1024  # Less than 1GB

    @pytest.mark.timeout(10)
    async def test_schema_operations_integration(
        self, connected_adapter, test_table_name
    ):
        """Test complete schema operation workflow - create, inspect, drop."""
        # Step 1: Create table using create_table()
        schema_def = {
            "id": {"type": "INTEGER", "nullable": False, "primary_key": True},
            "name": {"type": "VARCHAR", "max_length": 100, "nullable": False},
            "score": {"type": "INTEGER", "nullable": True, "default": "0"},
        }

        await connected_adapter.create_table(test_table_name, schema_def)

        # Step 2: Get schema using get_table_schema()
        retrieved_schema = await connected_adapter.get_table_schema(test_table_name)

        # Step 3: Verify schema matches
        assert "id" in retrieved_schema
        assert "name" in retrieved_schema
        assert "score" in retrieved_schema

        assert retrieved_schema["id"]["primary_key"] is True
        assert retrieved_schema["name"]["nullable"] is False
        assert retrieved_schema["score"]["nullable"] is True

        # Step 4: Test table is functional
        async with connected_adapter.connection_pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {test_table_name} (id, name, score) VALUES (1, 'test', 100)"
            )
            row = await conn.fetchrow(f"SELECT * FROM {test_table_name}")
            assert row["id"] == 1
            assert row["name"] == "test"
            assert row["score"] == 100

        # Step 5: Drop table using drop_table()
        await connected_adapter.drop_table(test_table_name)

        # Step 6: Verify table no longer exists
        async with connected_adapter.connection_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = $1
                )
            """,
                test_table_name,
            )
            assert result is False

    def test_supports_transactions_property(self, adapter):
        """Test supports_transactions property - NEW PROPERTY."""
        assert adapter.supports_transactions is True
        assert isinstance(adapter.supports_transactions, bool)
