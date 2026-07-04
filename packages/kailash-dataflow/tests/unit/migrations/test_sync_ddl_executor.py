"""
Tests for the SyncDDLExecutor - the fix for Docker/FastAPI auto_migrate issues.

This test suite verifies that DDL operations work correctly using synchronous
database connections, which is the key architectural fix for event loop
boundary issues in Docker/FastAPI deployments.
"""

import asyncio

import pytest

from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor


@pytest.mark.unit
class TestSyncDDLExecutor:
    """Test the SyncDDLExecutor basic functionality."""

    def test_sqlite_ddl_creates_table(self, tmp_path):
        """Test that SyncDDLExecutor can CREATE TABLE with SQLite."""
        db_path = tmp_path / "ddl_creates_table.db"

        executor = SyncDDLExecutor(f"sqlite:///{db_path}")
        result = executor.execute_ddl(
            "CREATE TABLE test_sync (id INTEGER PRIMARY KEY, name TEXT)"
        )

        assert result["success"] is True

        # Verify table was created
        assert executor.table_exists("test_sync") is True

    def test_sqlite_query_returns_results(self, tmp_path):
        """Test that SyncDDLExecutor can execute SELECT queries."""
        db_path = tmp_path / "query_returns.db"

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

    def test_get_table_columns_sqlite(self, tmp_path):
        """Test that get_table_columns works with SQLite."""
        db_path = tmp_path / "get_columns.db"

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


@pytest.mark.unit
class TestSyncDDLInAsyncContext:
    """
    Test that SyncDDLExecutor works correctly when called from within
    an async context (simulating Docker/FastAPI scenario).

    This is the KEY test - it verifies the architectural fix works.
    """

    @pytest.mark.asyncio
    async def test_ddl_works_inside_async_function(self, tmp_path):
        """
        Test DDL execution inside an async function.

        This simulates what happens in FastAPI when:
        1. uvicorn's event loop is running
        2. Module is imported, triggering @db.model
        3. auto_migrate=True triggers table creation
        """
        db_path = tmp_path / "ddl_inside_async.db"

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

    @pytest.mark.asyncio
    async def test_multiple_ddl_operations_in_async(self, tmp_path):
        """Test multiple DDL operations inside async context."""
        db_path = tmp_path / "multiple_ddl.db"

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

    @pytest.mark.asyncio
    async def test_ddl_batch_in_async(self, tmp_path):
        """Test batch DDL execution inside async context."""
        db_path = tmp_path / "ddl_batch.db"

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


@pytest.mark.unit
class TestSyncDDLEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_invalid_sql(self, tmp_path):
        """Test that invalid SQL returns error, not exception."""
        db_path = tmp_path / "invalid_sql.db"

        executor = SyncDDLExecutor(f"sqlite:///{db_path}")
        result = executor.execute_ddl("THIS IS NOT VALID SQL")

        assert result["success"] is False
        assert "error" in result

    def test_handles_query_on_nonexistent_table(self, tmp_path):
        """Test that querying non-existent table returns error."""
        db_path = tmp_path / "nonexistent_table.db"

        executor = SyncDDLExecutor(f"sqlite:///{db_path}")
        result = executor.execute_query("SELECT * FROM nonexistent_table")

        assert "error" in result

    def test_table_exists_returns_false_for_nonexistent(self, tmp_path):
        """Test table_exists returns False for non-existent table."""
        db_path = tmp_path / "table_exists_false.db"

        executor = SyncDDLExecutor(f"sqlite:///{db_path}")
        assert executor.table_exists("this_table_does_not_exist") is False


@pytest.mark.unit
class TestIsBenignDDLObjectExists:
    """Pin the scoping of ``_is_benign_ddl_object_exists`` — the single guarantee
    the whole 1061-tolerance (issue #1537) rests on.

    The batch/per-statement re-migration paths mark a model's table ensured (and
    swallow the error at DEBUG) ONLY when this helper returns True. If the scoping
    ever loosens so that a 1061 INSIDE a ``CREATE TABLE`` (a genuine schema
    authoring bug) is treated as benign, real failures would be masked; if it
    tightens so that a re-run ``CREATE INDEX`` 1061 is NOT benign, every MySQL
    restart re-emits a WARN. This test locks both edges.
    """

    def test_1061_inside_create_table_is_not_benign(self):
        """A 1061 'Duplicate key name' raised by a CREATE TABLE definition is a
        genuine schema bug — MUST surface (False), NOT be swallowed."""
        from dataflow.migrations.sync_ddl_executor import (
            _is_benign_ddl_object_exists,
        )

        err = "(1061, \"Duplicate key name 'idx_email'\")"
        sql = "CREATE TABLE `docs` (id INT, email VARCHAR(255), UNIQUE KEY `idx_email` (email), KEY `idx_email` (email))"
        assert _is_benign_ddl_object_exists(err, sql) is False

    def test_1061_on_create_index_is_benign(self):
        """A 1061 'Duplicate key name' raised by a re-run CREATE INDEX (MySQL has
        no IF NOT EXISTS) means the index already exists — benign (True)."""
        from dataflow.migrations.sync_ddl_executor import (
            _is_benign_ddl_object_exists,
        )

        err = "(1061, \"Duplicate key name 'idx_email'\")"
        sql = "CREATE UNIQUE INDEX `idx_email` ON `docs` (`email`)"
        assert _is_benign_ddl_object_exists(err, sql) is True

    def test_1064_syntax_on_create_index_is_not_benign(self):
        """A real 1064 syntax error on a CREATE INDEX is NOT an already-present
        signal — MUST surface (False) even though the statement is CREATE INDEX."""
        from dataflow.migrations.sync_ddl_executor import (
            _is_benign_ddl_object_exists,
        )

        err = "(1064, \"You have an error in your SQL syntax near 'ONN'\")"
        sql = "CREATE INDEX `idx_email` ONN `docs` (`email`)"
        assert _is_benign_ddl_object_exists(err, sql) is False

    def test_already_exists_on_create_table_is_benign(self):
        """PostgreSQL / SQLite 'already exists' on any object (here CREATE TABLE)
        is the canonical benign already-present signal (True)."""
        from dataflow.migrations.sync_ddl_executor import (
            _is_benign_ddl_object_exists,
        )

        err = 'relation "docs" already exists'
        sql = 'CREATE TABLE "docs" (id INTEGER PRIMARY KEY, email TEXT)'
        assert _is_benign_ddl_object_exists(err, sql) is True
