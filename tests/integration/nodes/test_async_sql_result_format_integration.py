"""Integration tests for AsyncSQLDatabaseNode result format with REAL PostgreSQL."""

import asyncio
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLResultFormatIntegration:
    """Test result format functionality with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database with sample data."""
        conn_string = get_postgres_connection_string()

        # Create test table
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Drop and recreate table
        await setup_node.execute_async(query="DROP TABLE IF EXISTS format_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE format_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                age INTEGER,
                salary DECIMAL(10, 2),
                hire_date DATE,
                last_login TIMESTAMP,
                active BOOLEAN,
                metadata JSONB
            )
        """
        )

        # Insert test data
        await setup_node.execute_async(
            query="""
            INSERT INTO format_test (name, age, salary, hire_date, last_login, active, metadata)
            VALUES
                ('John Doe', 30, 75000.50, '2020-01-15', '2024-01-15 10:30:00', true, '{"dept": "Engineering"}'),
                ('Jane Smith', 25, 65000.00, '2021-03-20', '2024-01-14 15:45:00', true, '{"dept": "Marketing"}'),
                ('Bob Johnson', 35, 85000.75, '2019-06-10', '2024-01-13 09:00:00', false, '{"dept": "Sales"}')
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS format_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_dict_format_real_data(self, setup_database):
        """Test dict format with real database data."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            result = await node.execute_async(
                query="SELECT * FROM format_test ORDER BY id", result_format="dict"
            )

            assert result["result"]["format"] == "dict"
            assert result["result"]["row_count"] == 3

            data = result["result"]["data"]
            assert isinstance(data, list)
            assert len(data) == 3

            # Check first row structure
            first_row = data[0]
            assert isinstance(first_row, dict)
            assert first_row["name"] == "John Doe"
            assert first_row["age"] == 30
            assert first_row["salary"] == 75000.5  # Decimal converted to float
            assert first_row["active"] is True
            assert isinstance(first_row["metadata"], dict)
            assert first_row["metadata"]["dept"] == "Engineering"

            # Check date/time serialization
            assert isinstance(first_row["hire_date"], str)
            assert first_row["hire_date"] == "2020-01-15"
            assert isinstance(first_row["last_login"], str)
            assert "2024-01-15" in first_row["last_login"]

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_list_format_real_data(self, setup_database):
        """Test list format with real database data."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            result = await node.execute_async(
                query="SELECT id, name, age, salary FROM format_test ORDER BY id",
                result_format="list",
            )

            assert result["result"]["format"] == "list"
            assert result["result"]["row_count"] == 3

            data = result["result"]["data"]
            assert isinstance(data, list)
            assert len(data) == 3

            # Check that we have columns info
            assert "columns" in result["result"]
            assert result["result"]["columns"] == ["id", "name", "age", "salary"]

            # Check first row is a list
            first_row = data[0]
            assert isinstance(first_row, list)
            assert first_row == [1, "John Doe", 30, 75000.5]

            # Check all rows
            assert data[1] == [2, "Jane Smith", 25, 65000.0]
            assert data[2] == [3, "Bob Johnson", 35, 85000.75]

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_dataframe_format_if_pandas_available(self, setup_database):
        """Test dataframe format with real data (if pandas is available)."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            result = await node.execute_async(
                query="SELECT id, name, age, salary FROM format_test ORDER BY id",
                result_format="dataframe",
            )

            assert result["result"]["format"] == "dataframe"

            try:
                import pandas as pd

                # If pandas is available, check DataFrame
                df = result["result"]["data"]
                assert isinstance(df, pd.DataFrame)
                assert len(df) == 3
                assert list(df.columns) == ["id", "name", "age", "salary"]
                assert df.iloc[0]["name"] == "John Doe"
            except ImportError:
                # If pandas not available, should fall back to dict format
                data = result["result"]["data"]
                assert isinstance(data, list)
                assert isinstance(data[0], dict)

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_empty_result_all_formats(self, setup_database):
        """Test all formats with empty results."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            for format_type in ["dict", "list", "dataframe"]:
                result = await node.execute_async(
                    query="SELECT * FROM format_test WHERE id > 1000",
                    result_format=format_type,
                )

                assert result["result"]["format"] == format_type
                assert result["result"]["row_count"] == 0

                data = result["result"]["data"]

                # Check appropriate empty structure
                if format_type == "dataframe":
                    try:
                        import pandas as pd

                        assert isinstance(data, pd.DataFrame) and len(data) == 0
                    except ImportError:
                        assert data == []
                else:
                    assert data == []

                # List format should still have columns even if no data
                if format_type == "list":
                    # Note: With no results, we can't determine columns
                    assert (
                        "columns" not in result["result"]
                        or result["result"]["columns"] == []
                    )

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_null_handling_all_formats(self, setup_database):
        """Test NULL value handling in all formats."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert a row with NULLs
            await node.execute_async(
                query="INSERT INTO format_test (name, age, salary) VALUES (:name, :age, :salary)",
                params={"name": "Null Test", "age": None, "salary": None},
            )

            # Test dict format
            dict_result = await node.execute_async(
                query="SELECT name, age, salary FROM format_test WHERE name = :name",
                params={"name": "Null Test"},
                result_format="dict",
            )

            dict_data = dict_result["result"]["data"][0]
            assert dict_data["name"] == "Null Test"
            assert dict_data["age"] is None
            assert dict_data["salary"] is None

            # Test list format
            list_result = await node.execute_async(
                query="SELECT name, age, salary FROM format_test WHERE name = :name",
                params={"name": "Null Test"},
                result_format="list",
            )

            list_data = list_result["result"]["data"][0]
            assert list_data == ["Null Test", None, None]

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_complex_query_all_formats(self, setup_database):
        """Test complex query with joins and aggregations in all formats."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Complex aggregation query
            query = """
                SELECT
                    active,
                    COUNT(*) as employee_count,
                    AVG(age) as avg_age,
                    SUM(salary) as total_salary,
                    MIN(hire_date) as earliest_hire,
                    MAX(last_login) as latest_login
                FROM format_test
                GROUP BY active
                ORDER BY active DESC
            """

            # Test dict format
            dict_result = await node.execute_async(query=query, result_format="dict")

            assert dict_result["result"]["row_count"] == 2
            active_row = dict_result["result"]["data"][0]
            assert active_row["active"] is True
            assert active_row["employee_count"] == 2
            assert isinstance(active_row["avg_age"], float)
            assert isinstance(active_row["total_salary"], float)

            # Test list format
            list_result = await node.execute_async(query=query, result_format="list")

            assert list_result["result"]["row_count"] == 2
            assert len(list_result["result"]["columns"]) == 6
            assert isinstance(list_result["result"]["data"][0], list)
            assert len(list_result["result"]["data"][0]) == 6

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_format_switching_same_query(self, setup_database):
        """Test running same query with different formats."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            query = "SELECT id, name, age FROM format_test WHERE id = :id"
            params = {"id": 1}

            # Get data in dict format
            dict_result = await node.execute_async(
                query=query, params=params, result_format="dict"
            )

            # Get same data in list format
            list_result = await node.execute_async(
                query=query, params=params, result_format="list"
            )

            # Verify same data, different format
            dict_data = dict_result["result"]["data"][0]
            list_data = list_result["result"]["data"][0]

            assert dict_data["id"] == list_data[0]
            assert dict_data["name"] == list_data[1]
            assert dict_data["age"] == list_data[2]

            # Verify columns in list format
            assert list_result["result"]["columns"] == ["id", "name", "age"]

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_large_result_set_formatting(self, setup_database):
        """Test formatting with larger result sets."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
        )

        try:
            # Insert more data
            for i in range(50):
                await node.execute_async(
                    query="INSERT INTO format_test (name, age, salary) VALUES (:name, :age, :salary)",
                    params={
                        "name": f"Employee{i}",
                        "age": 20 + i,
                        "salary": 50000 + i * 1000,
                    },
                )

            # Test all formats with larger dataset
            for format_type in ["dict", "list"]:
                result = await node.execute_async(
                    query="SELECT * FROM format_test ORDER BY id",
                    result_format=format_type,
                )

                assert result["result"]["row_count"] == 53  # 3 original + 50 new
                assert len(result["result"]["data"]) == 53

                if format_type == "dict":
                    assert all(
                        isinstance(row, dict) for row in result["result"]["data"]
                    )
                elif format_type == "list":
                    assert all(
                        isinstance(row, list) for row in result["result"]["data"]
                    )
                    assert "columns" in result["result"]

        finally:
            await node.cleanup()
