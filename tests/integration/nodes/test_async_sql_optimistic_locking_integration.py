"""Unit tests for AsyncSQLDatabaseNode optimistic locking support."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    ConflictResolution,
    LockStatus,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestAsyncSQLOptimisticLocking:
    """Test optimistic locking functionality."""

    def test_optimistic_locking_config(self):
        """Test optimistic locking configuration."""
        # Default disabled
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        assert node._enable_optimistic_locking is False
        assert node._version_field == "version"
        assert node._conflict_resolution == "fail_fast"
        assert node._version_retry_attempts == 3

        # Enabled with custom settings
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            version_field="row_version",
            conflict_resolution="retry",
            version_retry_attempts=5,
        )

        assert node._enable_optimistic_locking is True
        assert node._version_field == "row_version"
        assert node._conflict_resolution == "retry"
        assert node._version_retry_attempts == 5

    @pytest.mark.asyncio
    async def test_execute_with_version_check_disabled(self):
        """Test execute_with_version_check when optimistic locking is disabled."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=False,
        )

        # Mock execute_async
        mock_result = {"result": {"data": []}}
        with patch.object(node, "execute_async", return_value=mock_result) as mock_exec:
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
            )

            # Should call execute_async normally
            mock_exec.assert_called_once_with(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
            )

            assert result["version_checked"] is False
            assert result["status"] == LockStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_execute_with_version_check_success(self):
        """Test successful execution with version check."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
        )

        # Mock execute_async
        mock_result = {"result": {"rows_affected": 1}}
        with patch.object(node, "execute_async", return_value=mock_result) as mock_exec:
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
            )

            # Should add version increment and version check to WHERE clause
            expected_query = "UPDATE users SET name = :name, version = version + 1 WHERE id = :id AND version = :version"
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert call_args[1]["query"] == expected_query
            assert call_args[1]["params"]["version"] == 5

            assert result["status"] == LockStatus.SUCCESS
            assert result["version_checked"] is True
            assert result["new_version"] == 6
            assert result["rows_affected"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_version_conflict_fail_fast(self):
        """Test version conflict with fail_fast resolution."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            conflict_resolution="fail_fast",
        )

        # Mock execute_async to return 0 rows affected (version conflict)
        mock_result = {"result": {"rows_affected": 0}}
        with patch.object(node, "execute_async", return_value=mock_result):
            with pytest.raises(NodeExecutionError, match="Version conflict"):
                await node.execute_with_version_check(
                    query="UPDATE users SET name = :name WHERE id = :id",
                    params={"name": "John", "id": 1},
                    expected_version=5,
                )

    @pytest.mark.asyncio
    async def test_execute_with_version_conflict_retry(self):
        """Test version conflict with retry resolution."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            conflict_resolution="retry",
            version_retry_attempts=3,
        )

        # Mock execute_async
        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1

            if "SELECT" in kwargs["query"]:
                # Return current version
                return {"result": {"data": [{"version": 6}]}}
            else:
                # First attempt fails, second succeeds
                if call_count < 3:
                    return {"result": {"rows_affected": 0}}
                else:
                    return {"result": {"rows_affected": 1}}

        with patch.object(node, "execute_async", side_effect=mock_execute):
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
                record_id=1,
                table_name="users",
            )

            assert result["status"] == LockStatus.SUCCESS
            assert result["version_checked"] is True
            assert call_count > 1  # Should have retried

    @pytest.mark.asyncio
    async def test_execute_with_version_conflict_last_writer_wins(self):
        """Test version conflict with last_writer_wins resolution."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            conflict_resolution="last_writer_wins",
        )

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First attempt with version check fails
                return {"result": {"rows_affected": 0}}
            else:
                # Second attempt without version check succeeds
                return {"result": {"rows_affected": 1}}

        with patch.object(node, "execute_async", side_effect=mock_execute):
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
            )

            assert result["status"] == LockStatus.SUCCESS
            assert result["version_checked"] is False
            assert result["conflict_resolved"] == "last_writer_wins"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_read_with_version_single_record(self):
        """Test reading a single record with version."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
        )

        # Mock execute_async
        mock_result = {"result": {"data": [{"id": 1, "name": "John", "version": 5}]}}

        with patch.object(node, "execute_async", return_value=mock_result):
            result = await node.read_with_version(
                query="SELECT * FROM users WHERE id = :id", params={"id": 1}
            )

            assert result["version"] == 5
            assert result["record"]["name"] == "John"
            assert "result" in result

    @pytest.mark.asyncio
    async def test_read_with_version_multiple_records(self):
        """Test reading multiple records with versions."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
        )

        # Mock execute_async
        mock_result = {
            "result": {
                "data": [
                    {"id": 1, "name": "John", "version": 5},
                    {"id": 2, "name": "Jane", "version": 3},
                    {"id": 3, "name": "Bob", "version": 7},
                ]
            }
        }

        with patch.object(node, "execute_async", return_value=mock_result):
            result = await node.read_with_version(
                query="SELECT * FROM users", params={}
            )

            assert result["versions"] == [5, 3, 7]
            assert len(result["records"]) == 3
            assert result["records"][0]["name"] == "John"

    @pytest.mark.asyncio
    async def test_read_with_version_disabled(self):
        """Test read_with_version when optimistic locking is disabled."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=False,
        )

        # Mock execute_async
        mock_result = {"result": {"data": [{"id": 1, "name": "John"}]}}

        with patch.object(node, "execute_async", return_value=mock_result):
            result = await node.read_with_version(
                query="SELECT * FROM users WHERE id = :id", params={"id": 1}
            )

            # Should just return the raw result
            assert result == mock_result
            assert "version" not in result

    def test_build_versioned_update_query(self):
        """Test building versioned UPDATE queries."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
        )

        # With version increment
        query = node.build_versioned_update_query(
            table_name="users",
            update_fields={"name": "John", "email": "john@example.com"},
            where_clause="id = :id",
            increment_version=True,
        )

        expected = "UPDATE users SET name = :name, email = :email, version = version + 1 WHERE id = :id"
        assert query == expected

        # Without version increment
        query = node.build_versioned_update_query(
            table_name="users",
            update_fields={"last_login": "2024-01-01"},
            where_clause="id = :id",
            increment_version=False,
        )

        expected = "UPDATE users SET last_login = :last_login WHERE id = :id"
        assert query == expected

    def test_build_versioned_update_query_disabled(self):
        """Test build_versioned_update_query when optimistic locking is disabled."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=False,
        )

        query = node.build_versioned_update_query(
            table_name="users",
            update_fields={"name": "John", "email": "john@example.com"},
            where_clause="id = :id",
            increment_version=True,  # Should be ignored
        )

        expected = "UPDATE users SET name = :name, email = :email WHERE id = :id"
        assert query == expected

    @pytest.mark.asyncio
    async def test_version_retry_exhausted(self):
        """Test when all version retry attempts are exhausted."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            conflict_resolution="retry",
            version_retry_attempts=2,
        )

        # Mock execute_async to always return version conflict
        async def mock_execute(**kwargs):
            if "SELECT" in kwargs["query"]:
                return {"result": {"data": [{"version": 10}]}}
            else:
                return {"result": {"rows_affected": 0}}

        with patch.object(node, "execute_async", side_effect=mock_execute):
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
                record_id=1,
                table_name="users",
            )

            assert result["status"] == LockStatus.RETRY_EXHAUSTED
            assert result["retry_count"] == 2

    @pytest.mark.asyncio
    async def test_version_check_record_not_found(self):
        """Test version check when record is not found during retry."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            conflict_resolution="retry",
        )

        call_count = 0

        async def mock_execute(**kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First attempt - version conflict
                return {"result": {"rows_affected": 0}}
            else:
                # Second attempt - record not found
                return {"result": {"data": []}}

        with patch.object(node, "execute_async", side_effect=mock_execute):
            result = await node.execute_with_version_check(
                query="UPDATE users SET name = :name WHERE id = :id",
                params={"name": "John", "id": 1},
                expected_version=5,
                record_id=1,
                table_name="users",
            )

            assert result["status"] == LockStatus.RECORD_NOT_FOUND
            assert result["version_checked"] is True
