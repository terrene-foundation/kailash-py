"""
Tests for the SyncDDLExecutor - the fix for Docker/FastAPI auto_migrate issues.

This test suite verifies that DDL operations work correctly using synchronous
database connections, which is the key architectural fix for event loop
boundary issues in Docker/FastAPI deployments.
"""

import asyncio
import os
import sqlite3
import tempfile

import pytest

from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor


@pytest.mark.unit
class TestSyncDDLExecutor:
    """Test the SyncDDLExecutor basic functionality."""

    def test_sqlite_ddl_creates_table(self):
        """Test that SyncDDLExecutor can CREATE TABLE with SQLite."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")
            result = executor.execute_ddl(
                "CREATE TABLE test_sync (id INTEGER PRIMARY KEY, name TEXT)"
            )

            assert result["success"] is True

            # Verify table was created
            assert executor.table_exists("test_sync") is True
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_sqlite_query_returns_results(self):
        """Test that SyncDDLExecutor can execute SELECT queries."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")

            # Create and populate table
            executor.execute_ddl(
                "CREATE TABLE test_query (id INTEGER PRIMARY KEY, name TEXT)"
            )
            executor.execute_ddl("INSERT INTO test_query (name) VALUES ('Alice')")
            executor.execute_ddl("INSERT INTO test_query (name) VALUES ('Bob')")

            # Query data
            result = executor.execute_query("SELECT * FROM test_query")

            assert "result" in result
            assert len(result["result"]) == 2
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_get_table_columns_sqlite(self):
        """Test that get_table_columns works with SQLite."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")

            executor.execute_ddl(
                """CREATE TABLE test_columns (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT
                )"""
            )

            columns = executor.get_table_columns("test_columns")

            assert len(columns) == 3
            column_names = [c["name"] for c in columns]
            assert "id" in column_names
            assert "name" in column_names
            assert "email" in column_names
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


@pytest.mark.unit
class TestSyncDDLInAsyncContext:
    """
    Test that SyncDDLExecutor works correctly when called from within
    an async context (simulating Docker/FastAPI scenario).

    This is the KEY test - it verifies the architectural fix works.
    """

    @pytest.mark.asyncio
    async def test_ddl_works_inside_async_function(self):
        """
        Test DDL execution inside an async function.

        This simulates what happens in FastAPI when:
        1. uvicorn's event loop is running
        2. Module is imported, triggering @db.model
        3. auto_migrate=True triggers table creation
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # We're inside an async function - event loop is running
            loop = asyncio.get_running_loop()
            assert loop is not None, "Event loop should be running"

            # This should work WITHOUT hanging or causing event loop errors
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")
            result = executor.execute_ddl(
                "CREATE TABLE async_context_test (id INTEGER PRIMARY KEY)"
            )

            assert result["success"] is True
            assert executor.table_exists("async_context_test") is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_multiple_ddl_operations_in_async(self):
        """Test multiple DDL operations inside async context."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")

            # Create multiple tables
            result1 = executor.execute_ddl(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
            )
            result2 = executor.execute_ddl(
                "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT)"
            )

            assert result1["success"] is True
            assert result2["success"] is True

            # Insert data
            executor.execute_ddl("INSERT INTO users (name) VALUES ('Alice')")
            executor.execute_ddl(
                "INSERT INTO posts (user_id, title) VALUES (1, 'First Post')"
            )

            # Query should work too
            users = executor.execute_query("SELECT * FROM users")
            posts = executor.execute_query("SELECT * FROM posts")

            assert len(users["result"]) == 1
            assert len(posts["result"]) == 1

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ddl_batch_in_async(self):
        """Test batch DDL execution inside async context."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")

            statements = [
                "CREATE TABLE batch1 (id INTEGER PRIMARY KEY)",
                "CREATE TABLE batch2 (id INTEGER PRIMARY KEY)",
                "CREATE TABLE batch3 (id INTEGER PRIMARY KEY)",
            ]

            result = executor.execute_ddl_batch(statements)

            assert result["success"] is True
            assert result["executed_count"] == 3

            assert executor.table_exists("batch1") is True
            assert executor.table_exists("batch2") is True
            assert executor.table_exists("batch3") is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


@pytest.mark.unit
class TestSyncDDLEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_invalid_sql(self):
        """Test that invalid SQL returns error, not exception."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")
            result = executor.execute_ddl("THIS IS NOT VALID SQL")

            assert result["success"] is False
            assert "error" in result
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_handles_query_on_nonexistent_table(self):
        """Test that querying non-existent table returns error."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")
            result = executor.execute_query("SELECT * FROM nonexistent_table")

            assert "error" in result
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_table_exists_returns_false_for_nonexistent(self):
        """Test table_exists returns False for non-existent table."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            executor = SyncDDLExecutor(f"sqlite:///{db_path}")
            assert executor.table_exists("this_table_does_not_exist") is False
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
