"""
Unit tests for BulkOperations.bulk_upsert delegation to BulkUpsertNode.

Tests the delegation layer without database operations - focuses on:
- Parameter mapping and transformation
- Tenant context application
- Error handling and response format
- Conflict resolution strategy mapping
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow import DataFlow
from dataflow.core.config import DatabaseConfig, DataFlowConfig, SecurityConfig


class TestBulkUpsertDelegation:
    """Unit tests for bulk_upsert delegation logic."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance with necessary configuration."""
        # Create real config objects
        config = DataFlowConfig(
            database=DatabaseConfig(
                url="postgresql://test:test@localhost:5432/test_db",
                pool_size=10,
                max_overflow=20,
            ),
            security=SecurityConfig(
                multi_tenant=False,
            ),
            environment="test",
        )

        # Create DataFlow instance with mock methods
        df = MagicMock(spec=DataFlow)
        df.config = config
        df._tenant_context = None
        df._detect_database_type = MagicMock(return_value="postgresql")
        df._class_name_to_table_name = MagicMock(return_value="test_users")

        return df

    @pytest.mark.asyncio
    async def test_bulk_upsert_empty_data_returns_zero_counts(self, mock_dataflow):
        """Test that bulk_upsert with empty data returns zero counts without calling node."""
        from dataflow.features.bulk import BulkOperations

        bulk_ops = BulkOperations(mock_dataflow)

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=[],  # Empty list
            conflict_resolution="update",
            batch_size=1000,
        )

        # Verify response format
        assert result["success"] is True
        assert result["records_processed"] == 0
        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert result["batch_size"] == 1000

    @pytest.mark.asyncio
    async def test_bulk_upsert_none_data_returns_error(self, mock_dataflow):
        """Test that bulk_upsert with None data returns error."""
        from dataflow.features.bulk import BulkOperations

        bulk_ops = BulkOperations(mock_dataflow)

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=None,  # None data
            conflict_resolution="update",
        )

        # Verify error response
        assert result["success"] is False
        assert "error" in result
        assert "cannot be none" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_bulk_upsert_tenant_context_applied(self, mock_dataflow):
        """Test that tenant context is applied when multi-tenant is enabled."""
        from dataflow.features.bulk import BulkOperations

        # Enable multi-tenant mode
        mock_dataflow.config.security.multi_tenant = True
        mock_dataflow._tenant_context = {"tenant_id": "tenant_123"}
        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node that bulk_upsert now uses directly
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 2})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        test_data = [
            {"id": 1, "email": "test1@example.com", "name": "Test 1"},
            {"id": 2, "email": "test2@example.com", "name": "Test 2"},
        ]

        await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data,
            conflict_resolution="update",
        )

        # Verify tenant_id was added to each record
        for record in test_data:
            assert record.get("tenant_id") == "tenant_123"

        # Verify SQL node was called
        mock_sql_node.async_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_upsert_delegates_to_node(self, mock_dataflow):
        """Test that bulk_upsert uses SQL node and returns correct result format."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node that bulk_upsert now uses
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 5})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        test_data = [
            {"id": i, "email": f"user{i}@example.com", "name": f"User {i}"}
            for i in range(5)
        ]

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data,
            conflict_resolution="update",
            batch_size=100,
        )

        # Verify SQL node was called with correct database type
        mock_dataflow._get_or_create_async_sql_node.assert_called_once_with(
            "postgresql"
        )

        # Verify SQL node execution was called
        mock_sql_node.async_run.assert_called_once()

        # Verify result format
        assert result["success"] is True
        assert result["batch_size"] == 100
        assert result["conflict_resolution"] == "update"
        assert "records_processed" in result
        assert "inserted" in result
        assert "updated" in result

    @pytest.mark.asyncio
    async def test_bulk_upsert_conflict_resolution_mapping(self, mock_dataflow):
        """Test conflict_resolution parameter validation (update, skip, ignore)."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 1})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        test_data = [{"id": 1, "email": "test@example.com", "name": "Test"}]

        # Test 'skip' is accepted
        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="skip",
        )
        assert result["success"] is True
        assert result["conflict_resolution"] == "skip"

        # Test 'update' is accepted
        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="update",
        )
        assert result["success"] is True
        assert result["conflict_resolution"] == "update"

        # Test 'ignore' is accepted
        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="ignore",
        )
        assert result["success"] is True
        assert result["conflict_resolution"] == "ignore"

        # Test invalid conflict_resolution returns error
        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="invalid",
        )
        assert result["success"] is False
        assert "Invalid conflict_resolution" in result["error"]

    @pytest.mark.asyncio
    async def test_bulk_upsert_response_format_matches_api(self, mock_dataflow):
        """Test that response format matches expected BulkOperations API."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 10})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=[
                {"id": i, "email": f"user{i}@example.com", "name": f"User {i}"}
                for i in range(10)
            ],
            conflict_resolution="update",
        )

        # Verify required fields
        assert "success" in result
        assert "records_processed" in result
        assert "inserted" in result
        assert "updated" in result
        assert "skipped" in result
        assert "conflict_resolution" in result
        assert "batch_size" in result
        assert "batches" in result

        # Verify values
        assert result["success"] is True
        assert result["conflict_resolution"] == "update"

    @pytest.mark.asyncio
    async def test_bulk_upsert_error_handling_returns_proper_format(
        self, mock_dataflow
    ):
        """Test that errors are properly formatted."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Test 1: Missing 'id' field returns error (validation before SQL execution)
        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=[{"email": "test@example.com", "name": "Test"}],  # Missing 'id'
            conflict_resolution="update",
        )

        assert result["success"] is False
        assert "error" in result
        assert "missing required 'id' field" in result["error"]

        # Test 2: SQL node raises exception
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(
            side_effect=Exception("Unexpected database error")
        )
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=[{"id": 1, "email": "test@example.com", "name": "Test"}],
            conflict_resolution="update",
        )

        assert result["success"] is False
        assert "error" in result
        assert "Unexpected database error" in result["error"]
        assert result["records_processed"] == 0

    @pytest.mark.asyncio
    async def test_bulk_upsert_optional_parameters_passed_correctly(
        self, mock_dataflow
    ):
        """Test that optional parameters are handled correctly."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 1})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        result = await bulk_ops.bulk_upsert(
            model_name="User",
            data=[{"id": 1, "email": "test@example.com", "name": "Test"}],
            conflict_resolution="update",
            batch_size=500,
        )

        # Verify result contains the batch_size that was passed
        assert result["success"] is True
        assert result["batch_size"] == 500
        assert result["conflict_resolution"] == "update"

        # Verify SQL node was called
        mock_sql_node.async_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_upsert_database_type_detection(self, mock_dataflow):
        """Test that database type is correctly detected and used for SQL node."""
        from dataflow.features.bulk import BulkOperations

        mock_dataflow._models = {"User": {"table_name": "test_users"}}
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 1})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        test_data = [{"id": 1, "email": "test@example.com", "name": "Test"}]

        # Test PostgreSQL detection
        mock_dataflow._detect_database_type.return_value = "postgresql"

        await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="update",
        )

        # Verify SQL node was created with postgresql database type
        mock_dataflow._get_or_create_async_sql_node.assert_called_with("postgresql")

        # Reset mock
        mock_dataflow._get_or_create_async_sql_node.reset_mock()

        # Test MySQL detection
        mock_dataflow._detect_database_type.return_value = "mysql"

        await bulk_ops.bulk_upsert(
            model_name="User",
            data=test_data.copy(),
            conflict_resolution="update",
        )

        # Verify SQL node was created with mysql database type
        mock_dataflow._get_or_create_async_sql_node.assert_called_with("mysql")

    @pytest.mark.asyncio
    async def test_bulk_upsert_table_name_conversion(self, mock_dataflow):
        """Test that model name is correctly converted to table name."""
        from dataflow.features.bulk import BulkOperations

        # Model not in _models, so _class_name_to_table_name should be used as fallback
        mock_dataflow._models = {}
        mock_dataflow._class_name_to_table_name.return_value = "converted_table_name"
        mock_dataflow.get_model_fields = MagicMock(return_value={})

        bulk_ops = BulkOperations(mock_dataflow)

        # Mock the internal SQL node
        mock_sql_node = AsyncMock()
        mock_sql_node.async_run = AsyncMock(return_value={"rows_affected": 1})
        mock_dataflow._get_or_create_async_sql_node = MagicMock(
            return_value=mock_sql_node
        )

        await bulk_ops.bulk_upsert(
            model_name="SomeModelName",
            data=[{"id": 1, "email": "test@example.com", "name": "Test"}],
            conflict_resolution="update",
        )

        # Verify _class_name_to_table_name was called as fallback
        mock_dataflow._class_name_to_table_name.assert_called_once_with("SomeModelName")

        # Verify SQL node was called (meaning the table name was used)
        mock_sql_node.async_run.assert_called_once()
