#!/usr/bin/env python3
"""
Unit test for basic SQLite functionality in DataFlow.

Uses standardized unit test fixtures and follows Tier 1 testing policy:
- ✅ SQLite databases (both :memory: and file-based)
- ✅ Mocks and stubs for external services
- ❌ NO PostgreSQL connections (use integration tests instead)
"""

import pytest

from dataflow import DataFlow
from dataflow.adapters.sqlite import SQLiteAdapter


@pytest.mark.unit
class TestSQLiteBasic:
    """Unit tests for basic SQLite functionality."""

    def test_sqlite_memory_database(self, memory_dataflow):
        """Test SQLite in-memory database initialization using standardized fixture."""
        db = memory_dataflow

        @db.model
        class TestUser:
            name: str
            email: str

        models = db.get_models()
        assert "TestUser" in models

    def test_sqlite_file_database_initialization(self, file_dataflow):
        """Test SQLite file database initialization using standardized fixture."""
        db = file_dataflow

        @db.model
        class FileUser:
            name: str
            active: bool = True

        models = db.get_models()
        assert "FileUser" in models

    @pytest.mark.asyncio
    async def test_sqlite_adapter_basic_operations(self, file_test_suite):
        """Test basic SQLite adapter operations using standardized fixture."""
        # Use the file-based test suite for adapter testing
        adapter = SQLiteAdapter(file_test_suite.config.url)
        await adapter.connect()

        # Create a test table
        await adapter.execute_query(
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)"
        )

        # Insert test data
        await adapter.execute_query(
            "INSERT INTO test_table (name) VALUES (?)", ["test"]
        )

        # Query the data
        result = await adapter.execute_query("SELECT * FROM test_table")
        assert len(result) == 1
        assert result[0]["name"] == "test"

        await adapter.disconnect()

    def test_memory_database_limitation(self, memory_dataflow):
        """Test that memory databases properly handle their limitations."""
        db = memory_dataflow

        @db.model
        class MemoryUser:
            name: str
            email: str

        models = db.get_models()
        assert "MemoryUser" in models

        # Memory database schema discovery should raise an error
        # as designed (they don't support real schema inspection)
        # The error may be wrapped in EnhancedDataFlowError
        from dataflow.exceptions import EnhancedDataFlowError

        with pytest.raises((NotImplementedError, EnhancedDataFlowError)) as exc_info:
            schema = db.discover_schema(use_real_inspection=True)

        # Verify the error message mentions in-memory SQLite limitation
        error_str = str(exc_info.value)
        assert "in-memory SQLite" in error_str or "memory" in error_str.lower()

        # Basic model registration should work fine though
        assert "MemoryUser" in db.get_models()

    @pytest.mark.asyncio
    async def test_sqlite_connection_context_manager(self, memory_test_suite):
        """Test SQLite connection using standardized context manager."""
        async with memory_test_suite.get_connection() as conn:
            # Create a simple test table
            await conn.execute(
                "CREATE TABLE context_test (id INTEGER PRIMARY KEY, value TEXT)"
            )
            await conn.execute(
                "INSERT INTO context_test (value) VALUES (?)", ("test_value",)
            )

            # Query the data
            cursor = await conn.execute("SELECT * FROM context_test")
            rows = await cursor.fetchall()

            assert len(rows) == 1
            assert rows[0][1] == "test_value"  # Check the value column

    @pytest.mark.asyncio
    async def test_basic_test_table_fixture(self, basic_test_table, memory_test_suite):
        """Test using the standardized basic test table fixture."""
        table_name = basic_test_table

        async with memory_test_suite.get_connection() as conn:
            # Query the pre-created test table
            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = await cursor.fetchone()
            count = row[0]

            # Should have 3 standard test records (Alice, Bob, Charlie)
            assert count == 3

            # Test that we can query specific records
            cursor = await conn.execute(
                f"SELECT name FROM {table_name} WHERE email = ?", ("alice@example.com",)
            )
            row = await cursor.fetchone()
            assert row[0] == "Alice"
