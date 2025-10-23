"""Integration tests for AsyncSQLDatabaseNode parameter handling with REAL PostgreSQL."""

import asyncio
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLParameterHandlingIntegration:
    """Test parameter handling functionality with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database with various data types."""
        conn_string = get_postgres_connection_string()

        # Create test table with various column types
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Drop and recreate table
        await setup_node.execute_async(query="DROP TABLE IF EXISTS param_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE param_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                age INTEGER,
                salary DECIMAL(10, 2),
                active BOOLEAN,
                created_date DATE,
                updated_at TIMESTAMP,
                metadata JSONB,
                tags TEXT[],
                binary_data BYTEA,
                uuid_field UUID
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS param_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_sqlite_style_parameters(self, setup_database):
        """Test SQLite-style ? parameters with real database."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert using ? placeholders
            await node.execute_async(
                query="INSERT INTO param_test (name, age, active) VALUES (?, ?, ?)",
                params=["John Doe", 30, True],
            )

            # Query using ? placeholders
            result = await node.execute_async(
                query="SELECT name, age FROM param_test WHERE active = ? AND age > ?",
                params=[True, 25],
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["name"] == "John Doe"
            assert result["result"]["data"][0]["age"] == 30

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_postgresql_style_parameters(self, setup_database):
        """Test PostgreSQL-style $1, $2 parameters with real database."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert using $1, $2 placeholders
            await node.execute_async(
                query="INSERT INTO param_test (name, age, salary) VALUES ($1, $2, $3)",
                params=["Jane Smith", 35, Decimal("75000.50")],
            )

            # Update using $1, $2 placeholders
            await node.execute_async(
                query="UPDATE param_test SET salary = $1 WHERE name = $2",
                params=[Decimal("80000.00"), "Jane Smith"],
            )

            # Verify
            result = await node.execute_async(
                query="SELECT name, salary FROM param_test WHERE name = $1",
                params=["Jane Smith"],
            )

            assert len(result["result"]["data"]) == 1
            assert (
                result["result"]["data"][0]["salary"] == 80000.0
            )  # Decimal converted to float

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_mysql_style_parameters(self, setup_database):
        """Test MySQL-style %s parameters with real database."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert using %s placeholders
            await node.execute_async(
                query="INSERT INTO param_test (name, created_date, active) VALUES (%s, %s, %s)",
                params=["Bob Johnson", date(2024, 1, 15), False],
            )

            # Query using %s placeholders
            result = await node.execute_async(
                query="SELECT name, created_date FROM param_test WHERE created_date = %s",
                params=[date(2024, 1, 15)],
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["name"] == "Bob Johnson"
            assert (
                result["result"]["data"][0]["created_date"] == "2024-01-15"
            )  # Date serialized

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_complex_type_serialization(self, setup_database):
        """Test serialization of complex database types."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Prepare test data
            test_uuid = uuid4()
            test_datetime = datetime(2024, 1, 15, 10, 30, 45)
            test_decimal = Decimal("12345.67")
            test_json = {"key": "value", "nested": {"array": [1, 2, 3]}}
            test_bytes = b"Binary data here"
            test_array = ["tag1", "tag2", "tag3"]

            # Insert complex types
            await node.execute_async(
                query="""
                    INSERT INTO param_test
                    (name, salary, updated_at, metadata, binary_data, tags, uuid_field)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params=[
                    "Complex Types",
                    test_decimal,
                    test_datetime,
                    test_json,
                    test_bytes,
                    test_array,
                    test_uuid,
                ],
            )

            # Query back the data
            result = await node.execute_async(
                query="SELECT * FROM param_test WHERE name = ?",
                params=["Complex Types"],
            )

            data = result["result"]["data"][0]

            # Verify type conversions
            assert data["salary"] == 12345.67  # Decimal -> float
            assert (
                data["updated_at"] == test_datetime.isoformat()
            )  # datetime -> ISO string
            # JSONB is returned as string, need to parse it
            assert json.loads(data["metadata"]) == test_json
            assert data["binary_data"] == "QmluYXJ5IGRhdGEgaGVyZQ=="  # bytes -> base64
            assert data["tags"] == test_array  # Array preserved
            assert data["uuid_field"] == str(test_uuid)  # UUID -> string

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_single_parameter_handling(self, setup_database):
        """Test single parameter (not in list) handling."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert a test record
            await node.execute_async(
                query="INSERT INTO param_test (name, age) VALUES ('Single Param', 40)"
            )

            # Query with single parameter (not wrapped in list)
            result = await node.execute_async(
                query="SELECT * FROM param_test WHERE age = ?",
                params=40,  # Single value, not a list
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["name"] == "Single Param"

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_mixed_named_and_positional(self, setup_database):
        """Test that named parameters work alongside positional conversion."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # First, use positional parameters
            await node.execute_async(
                query="INSERT INTO param_test (name, age) VALUES (?, ?)",
                params=["Positional User", 25],
            )

            # Then use named parameters in the same session
            await node.execute_async(
                query="INSERT INTO param_test (name, age) VALUES (:name, :age)",
                params={"name": "Named User", "age": 30},
            )

            # Query both
            result = await node.execute_async(
                query="SELECT name, age FROM param_test ORDER BY age"
            )

            assert len(result["result"]["data"]) == 2
            assert result["result"]["data"][0]["name"] == "Positional User"
            assert result["result"]["data"][1]["name"] == "Named User"

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_null_handling(self, setup_database):
        """Test NULL value handling in parameters."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert with NULL values
            await node.execute_async(
                query="INSERT INTO param_test (name, age, salary, metadata) VALUES (?, ?, ?, ?)",
                params=["Null Test", None, None, None],
            )

            # Query for NULL values
            result = await node.execute_async(
                query="SELECT * FROM param_test WHERE age IS NULL AND salary IS NULL"
            )

            assert len(result["result"]["data"]) == 1
            data = result["result"]["data"][0]
            assert data["name"] == "Null Test"
            assert data["age"] is None
            assert data["salary"] is None
            assert data["metadata"] is None

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_large_parameter_count(self, setup_database):
        """Test queries with many parameters."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Create a query with many parameters
            num_params = 10
            placeholders = ", ".join(["?"] * num_params)
            values = list(range(num_params))

            # Insert multiple records
            for i in range(5):
                name_params = [f"User{i}_{v}" for v in values]
                query = f"INSERT INTO param_test (name) VALUES ({placeholders})"

                # This will insert one record with the first parameter as name
                await node.execute_async(
                    query="INSERT INTO param_test (name) VALUES (?)",
                    params=[name_params[0]],
                )

            # Query to verify
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM param_test WHERE name LIKE ?",
                params=["User%"],
            )

            assert result["result"]["data"][0]["count"] == 5

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_special_characters_in_params(self, setup_database):
        """Test parameters containing special characters."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Test various special characters
            special_names = [
                "O'Brien",  # Single quote
                'Name with "quotes"',  # Double quotes
                "Name with ? question",  # Question mark
                "Name with $1 dollar",  # Dollar sign
                "Name with %s percent",  # Percent
                "Name with \\ backslash",  # Backslash
                "Name with ; semicolon",  # Semicolon
            ]

            for name in special_names:
                await node.execute_async(
                    query="INSERT INTO param_test (name) VALUES (?)", params=[name]
                )

            # Query each one back
            for name in special_names:
                result = await node.execute_async(
                    query="SELECT name FROM param_test WHERE name = ?", params=[name]
                )

                assert len(result["result"]["data"]) == 1
                assert result["result"]["data"][0]["name"] == name

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_parameter_type_preservation(self, setup_database):
        """Test that parameter types are preserved during conversion."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Test different numeric types
            await node.execute_async(
                query="INSERT INTO param_test (name, age, salary) VALUES (?, ?, ?)",
                params=["Type Test", 42, Decimal("99999.99")],
            )

            # Query with type-specific comparisons
            result = await node.execute_async(
                query="SELECT * FROM param_test WHERE age = ? AND salary = ?",
                params=[42, Decimal("99999.99")],
            )

            assert len(result["result"]["data"]) == 1
            data = result["result"]["data"][0]
            assert data["age"] == 42
            assert data["salary"] == 99999.99  # Decimal serialized to float

        finally:
            await node.cleanup()
