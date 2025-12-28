"""Unit tests for AsyncSQLDatabaseNode parameter handling improvements."""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseAdapter,
    DatabaseType,
)


class TestAsyncSQLParameterConversion:
    """Test parameter style conversion functionality."""

    def test_convert_sqlite_style_parameters(self):
        """Test conversion of SQLite-style ? placeholders."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        query = "SELECT * FROM users WHERE age > ? AND active = ? AND name = ?"
        params = [25, True, "John"]

        new_query, param_dict = node._convert_to_named_parameters(query, params)

        assert (
            new_query
            == "SELECT * FROM users WHERE age > :p0 AND active = :p1 AND name = :p2"
        )
        assert param_dict == {"p0": 25, "p1": True, "p2": "John"}

    def test_convert_postgresql_style_parameters(self):
        """Test conversion of PostgreSQL-style $1, $2 placeholders."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        query = "UPDATE users SET name = $1, age = $2 WHERE id = $3"
        params = ["Jane", 30, 123]

        new_query, param_dict = node._convert_to_named_parameters(query, params)

        assert new_query == "UPDATE users SET name = :p0, age = :p1 WHERE id = :p2"
        assert param_dict == {"p0": "Jane", "p1": 30, "p2": 123}

    def test_convert_mysql_style_parameters(self):
        """Test conversion of MySQL-style %s placeholders."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        query = "INSERT INTO logs (message, level, timestamp) VALUES (%s, %s, %s)"
        params = ["Error occurred", "ERROR", datetime.now()]

        new_query, param_dict = node._convert_to_named_parameters(query, params)

        assert (
            new_query
            == "INSERT INTO logs (message, level, timestamp) VALUES (:p0, :p1, :p2)"
        )
        assert param_dict["p0"] == "Error occurred"
        assert param_dict["p1"] == "ERROR"
        assert isinstance(param_dict["p2"], datetime)

    def test_mixed_parameter_styles(self):
        """Test that mixed styles are handled correctly."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        # Should not mix styles, but test that each is converted properly
        query1 = "SELECT * FROM users WHERE id = $1"
        query2 = "SELECT * FROM users WHERE id = ?"
        query3 = "SELECT * FROM users WHERE id = %s"

        params = [123]

        result1 = node._convert_to_named_parameters(query1, params)
        result2 = node._convert_to_named_parameters(query2, params)
        result3 = node._convert_to_named_parameters(query3, params)

        assert result1[0] == "SELECT * FROM users WHERE id = :p0"
        assert result2[0] == "SELECT * FROM users WHERE id = :p0"
        assert result3[0] == "SELECT * FROM users WHERE id = :p0"

        assert result1[1] == {"p0": 123}
        assert result2[1] == {"p0": 123}
        assert result3[1] == {"p0": 123}

    def test_no_parameters(self):
        """Test queries without parameters."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        query = "SELECT * FROM users"
        params = []

        new_query, param_dict = node._convert_to_named_parameters(query, params)

        assert new_query == "SELECT * FROM users"
        assert param_dict == {}

    def test_question_marks_in_strings(self):
        """Test that ? inside string literals are not replaced."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        # Note: This is a simplified test - proper SQL parsing would handle quoted strings
        query = "SELECT * FROM users WHERE name = ? AND description LIKE ?"
        params = ["John?", "%question?%"]

        new_query, param_dict = node._convert_to_named_parameters(query, params)

        assert (
            new_query == "SELECT * FROM users WHERE name = :p0 AND description LIKE :p1"
        )
        assert param_dict == {"p0": "John?", "p1": "%question?%"}


class TestAsyncSQLTypeSerializer:
    """Test type serialization functionality."""

    def test_serialize_decimal(self):
        """Test Decimal serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, SQLiteAdapter

        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            database="test.db",
        )
        adapter = SQLiteAdapter(config)

        value = Decimal("123.45")
        result = adapter._serialize_value(value)

        assert result == 123.45
        assert isinstance(result, float)

    def test_serialize_datetime(self):
        """Test datetime serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, SQLiteAdapter

        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            database="test.db",
        )
        adapter = SQLiteAdapter(config)

        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = adapter._serialize_value(dt)

        assert result == "2024-01-15T10:30:45"
        assert isinstance(result, str)

    def test_serialize_date(self):
        """Test date serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, SQLiteAdapter

        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            database="test.db",
        )
        adapter = SQLiteAdapter(config)

        d = date(2024, 1, 15)
        result = adapter._serialize_value(d)

        assert result == "2024-01-15"
        assert isinstance(result, str)

    def test_serialize_timedelta(self):
        """Test timedelta serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, SQLiteAdapter

        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            database="test.db",
        )
        adapter = SQLiteAdapter(config)

        td = timedelta(hours=2, minutes=30, seconds=45)
        result = adapter._serialize_value(td)

        assert result == 9045.0  # Total seconds
        assert isinstance(result, float)

    def test_serialize_uuid(self):
        """Test UUID serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

        # Create a real adapter instance
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="test",
            user="test",
            password="test",
        )
        adapter = PostgreSQLAdapter(config)

        # Create a real UUID
        import uuid

        test_uuid = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

        result = adapter._serialize_value(test_uuid)

        assert result == "550e8400-e29b-41d4-a716-446655440000"
        assert isinstance(result, str)

    def test_serialize_bytes(self):
        """Test bytes serialization."""
        from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

        # Create a real adapter instance
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="test",
            user="test",
            password="test",
        )
        adapter = PostgreSQLAdapter(config)

        data = b"Hello, World!"
        result = adapter._serialize_value(data)

        assert result == "SGVsbG8sIFdvcmxkIQ=="  # Base64 encoded
        assert isinstance(result, str)

    def test_serialize_nested_structures(self):
        """Test serialization of nested lists and dicts."""
        from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

        # Create a real adapter instance
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="test",
            user="test",
            password="test",
        )
        adapter = PostgreSQLAdapter(config)

        # List with various types
        list_data = [
            1,
            Decimal("123.45"),
            datetime(2024, 1, 15, 10, 30, 45),
            {"nested": True},
        ]
        result = adapter._serialize_value(list_data)

        assert result == [1, 123.45, "2024-01-15T10:30:45", {"nested": True}]

        # Dict with various types
        dict_data = {
            "id": 1,
            "price": Decimal("99.99"),
            "created": date(2024, 1, 15),
            "items": [1, 2, 3],
        }
        result = adapter._serialize_value(dict_data)

        assert result == {
            "id": 1,
            "price": 99.99,
            "created": "2024-01-15",
            "items": [1, 2, 3],
        }

    def test_serialize_none_and_primitives(self):
        """Test serialization of None and primitive types."""
        from kailash.nodes.data.async_sql import DatabaseConfig, PostgreSQLAdapter

        # Create a real adapter instance
        config = DatabaseConfig(
            type=DatabaseType.POSTGRESQL,
            host="localhost",
            database="test",
            user="test",
            password="test",
        )
        adapter = PostgreSQLAdapter(config)

        assert adapter._serialize_value(None) is None
        assert adapter._serialize_value(123) == 123
        assert adapter._serialize_value("hello") == "hello"
        assert adapter._serialize_value(True) is True
        assert adapter._serialize_value(3.14) == 3.14


class TestAsyncSQLParameterIntegration:
    """Test parameter handling integration with query execution."""

    @pytest.mark.asyncio
    async def test_positional_params_converted_in_execute(self):
        """Test that positional parameters are converted during execution."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        # Mock the adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = [{"id": 1, "name": "John"}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Use positional parameters
            result = await node.execute_async(
                query="SELECT * FROM users WHERE age > ? AND active = ?",
                params=[25, True],
            )

            # Verify the query was converted
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args

            # The query should be converted to named parameters
            assert ":p0" in call_args[1]["query"]
            assert ":p1" in call_args[1]["query"]
            assert "?" not in call_args[1]["query"]

            # Parameters should be a dict
            assert isinstance(call_args[1]["params"], dict)
            assert call_args[1]["params"] == {"p0": 25, "p1": True}

    @pytest.mark.asyncio
    async def test_single_param_converted_in_execute(self):
        """Test that single parameter is wrapped and converted."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        # Mock the adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = [{"id": 1, "name": "John"}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Use single parameter (not in list)
            result = await node.execute_async(
                query="SELECT * FROM users WHERE id = ?",
                params=123,  # Single value, not a list
            )

            # Verify the query was converted
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args

            # The query should be converted
            assert ":p0" in call_args[1]["query"]
            assert "?" not in call_args[1]["query"]

            # Parameters should be a dict
            assert call_args[1]["params"] == {"p0": 123}

    @pytest.mark.asyncio
    async def test_named_params_unchanged(self):
        """Test that named parameters are passed through unchanged."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="sqlite",
            database="test.db",
        )

        # Mock the adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = [{"id": 1, "name": "John"}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Use named parameters
            result = await node.execute_async(
                query="SELECT * FROM users WHERE age > :min_age AND active = :is_active",
                params={"min_age": 25, "is_active": True},
            )

            # Verify the query was NOT converted
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args

            # The query should remain unchanged
            assert (
                call_args[1]["query"]
                == "SELECT * FROM users WHERE age > :min_age AND active = :is_active"
            )

            # Parameters should be unchanged
            assert call_args[1]["params"] == {"min_age": 25, "is_active": True}
