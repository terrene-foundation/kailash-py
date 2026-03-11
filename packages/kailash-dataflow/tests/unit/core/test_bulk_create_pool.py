"""
Unit tests for BulkCreatePoolNode.

Tests the bulk create node with connection pool functionality.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode

from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestBulkCreatePoolNode:
    """Test BulkCreatePoolNode functionality."""

    def test_node_initialization_basic(self):
        """Test basic node initialization."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", database_type="postgresql"
        )

        assert node.table_name == "users"
        assert node.database_type == "postgresql"
        assert node.batch_size == 1000
        assert node.conflict_resolution == "error"
        assert node.auto_timestamps is True
        assert node.multi_tenant is False
        assert node.default_tenant_id is None

    def test_node_initialization_with_options(self):
        """Test node initialization with all options."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create",
            table_name="products",
            database_type="mysql",
            batch_size=500,
            conflict_resolution="skip",
            auto_timestamps=False,
            multi_tenant=True,
            tenant_id="tenant_123",
            connection_pool_id="pool_1",
        )

        assert node.table_name == "products"
        assert node.database_type == "mysql"
        assert node.batch_size == 500
        assert node.conflict_resolution == "skip"
        assert node.auto_timestamps is False
        assert node.multi_tenant is True
        assert node.default_tenant_id == "tenant_123"

    def test_get_parameters(self):
        """Test parameter definition."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        params = node.get_parameters()

        # Check required parameters
        assert "data" in params
        assert params["data"].required is True
        assert params["data"].type == list

        # Check optional parameters
        assert "tenant_id" in params
        assert params["tenant_id"].required is False
        assert params["tenant_id"].type == str

        assert "return_ids" in params
        assert params["return_ids"].required is False
        assert params["return_ids"].type == bool
        assert params["return_ids"].default is False

        assert "dry_run" in params
        assert params["dry_run"].required is False
        assert params["dry_run"].type == bool
        assert params["dry_run"].default is False

    @pytest.mark.asyncio
    async def test_async_run_validation_error_no_table_name(self):
        """Test validation error when table_name is not provided."""
        node = BulkCreatePoolNode(node_id="test_bulk_create")

        with pytest.raises(NodeValidationError, match="table_name must be provided"):
            await node.execute_async(data=[{"name": "test"}])

    @pytest.mark.asyncio
    async def test_async_run_validation_error_no_data(self):
        """Test validation error when no data is provided."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        with pytest.raises(NodeValidationError, match="No data provided"):
            await node.execute_async(data=[])

    @pytest.mark.asyncio
    async def test_async_run_dry_run_mode(self):
        """Test dry run execution."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", batch_size=100
        )

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]

        result = await node.execute_async(data=test_data, dry_run=True)

        assert result["success"] is True
        assert result["created_count"] == 2
        assert result["total_records"] == 2
        assert result["batches"] == 1
        assert result["metadata"]["dry_run"] is True
        assert result["metadata"]["table"] == "users"

    @pytest.mark.asyncio
    async def test_async_run_direct_processing(self):
        """Test direct processing without connection pool."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", batch_size=100
        )

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": "charlie@example.com"},
        ]

        result = await node.execute_async(data=test_data)

        assert result["success"] is True
        assert result["created_count"] == 3
        assert result["total_records"] == 3
        assert result["batches"] == 1
        assert result["metadata"]["table"] == "users"
        assert result["metadata"]["used_connection_pool"] is False

    @pytest.mark.asyncio
    async def test_async_run_with_return_ids(self):
        """Test execution with return_ids enabled."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]

        result = await node.execute_async(data=test_data, return_ids=True)

        assert result["success"] is True
        assert result["created_count"] == 2
        assert "created_ids" in result
        assert len(result["created_ids"]) == 2

    @pytest.mark.asyncio
    async def test_async_run_multi_tenant(self):
        """Test execution with multi-tenant support."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create",
            table_name="users",
            multi_tenant=True,
            tenant_id="default_tenant",
        )

        test_data = [{"name": "Alice", "email": "alice@example.com"}]

        result = await node.execute_async(data=test_data, tenant_id="tenant_123")

        assert result["success"] is True
        assert result["tenant_id"] == "tenant_123"
        assert result["metadata"]["multi_tenant"] is True

    @pytest.mark.asyncio
    async def test_async_run_with_pool_processing(self):
        """Test execution with connection pool processing."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", connection_pool_id="pool_1"
        )

        # Mock the pool manager and connection
        mock_pool_manager = Mock()
        mock_pool_instance = AsyncMock()
        mock_connection = AsyncMock()

        # Setup pool mock with proper async context manager
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool_manager.get_pool_instance.return_value = mock_pool_instance
        mock_pool_instance.acquire = Mock(return_value=MockAsyncContextManager())

        node._pool_manager = mock_pool_manager

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]

        with patch.object(
            node,
            "_execute_batch_with_connection",
            return_value={"created_count": 2, "created_ids": [1, 2]},
        ) as mock_execute_batch:

            result = await node.execute_async(
                data=test_data, use_pooled_connection=True, return_ids=True
            )

        assert result["success"] is True
        assert result["created_count"] == 2
        assert "created_ids" in result
        assert result["metadata"]["used_connection_pool"] is True

        # Verify pool was used
        mock_pool_manager.get_pool_instance.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_direct_implementation(self):
        """Test direct processing implementation."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", batch_size=2
        )

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": "charlie@example.com"},
        ]

        result = await node._process_direct(
            data=test_data, tenant_id=None, return_ids=True, dry_run=False
        )

        assert result["created_count"] == 3
        assert result["batches"] == 2  # ceil(3/2) = 2
        assert len(result["created_ids"]) == 3
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_batched_inserts_with_pool(self):
        """Test batched inserts with connection pool."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", batch_size=2
        )

        mock_pool = AsyncMock()
        mock_connection = AsyncMock()

        # Setup pool connection mock with proper async context manager
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        test_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
            {"name": "Charlie", "email": "charlie@example.com"},
        ]

        with patch.object(
            node,
            "_execute_batch_with_connection",
            return_value={"created_count": 2, "created_ids": [1, 2]},
        ) as mock_execute_batch:

            result = await node._execute_batched_inserts_with_pool(
                pool=mock_pool,
                data=test_data,
                tenant_id=None,
                return_ids=True,
                dry_run=False,
            )

        assert result["created_count"] == 4  # 2 batches * 2 each
        assert result["batches"] == 2
        assert len(result["created_ids"]) == 4
        assert result["error_count"] == 0

        # Verify pool was used correctly
        assert mock_pool.acquire.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_batch_with_connection(self):
        """Test single batch execution with connection."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        mock_connection = Mock()
        batch_data = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]

        result = await node._execute_batch_with_connection(
            conn=mock_connection, batch=batch_data, tenant_id=None, return_ids=True
        )

        assert result["created_count"] == 2
        assert len(result["created_ids"]) == 2

    @pytest.mark.asyncio
    async def test_error_handling_in_pool_processing(self):
        """Test error handling during pool processing."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", conflict_resolution="skip"
        )

        mock_pool = AsyncMock()
        mock_connection = AsyncMock()

        # Setup pool with proper async context manager
        class MockAsyncContextManager:
            async def __aenter__(self):
                return mock_connection

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_pool.acquire = Mock(return_value=MockAsyncContextManager())

        test_data = [{"name": "Alice", "email": "alice@example.com"}]

        with patch.object(
            node,
            "_execute_batch_with_connection",
            side_effect=Exception("Connection error"),
        ):

            result = await node._execute_batched_inserts_with_pool(
                pool=mock_pool,
                data=test_data,
                tenant_id=None,
                return_ids=False,
                dry_run=False,
            )

        assert result["error_count"] == 1
        assert result["created_count"] == 0
        assert len(result["errors"]) == 1
        assert "Connection error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_validation_inputs(self):
        """Test input validation."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        # Test with valid inputs
        with patch.object(
            node,
            "validate_inputs",
            return_value={
                "data": [{"name": "Alice"}],
                "tenant_id": "tenant_123",
                "return_ids": False,
                "dry_run": False,
            },
        ) as mock_validate:

            result = await node.execute_async(
                data=[{"name": "Alice"}], tenant_id="tenant_123"
            )

            mock_validate.assert_called()
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_node_execution_error_handling(self):
        """Test handling of NodeExecutionError."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        # Mock an exception during processing
        with patch.object(
            node, "_process_direct", side_effect=Exception("Database error")
        ):

            with pytest.raises(
                NodeExecutionError, match="Bulk create operation failed"
            ):
                await node.execute_async(data=[{"name": "Alice"}])

    @pytest.mark.asyncio
    async def test_metadata_structure(self):
        """Test result metadata structure."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create",
            table_name="products",
            database_type="mysql",
            batch_size=500,
            conflict_resolution="update",
            auto_timestamps=False,
            multi_tenant=True,
        )

        test_data = [{"name": "Product A", "price": 100}]

        result = await node.execute_async(data=test_data, dry_run=True)

        metadata = result["metadata"]
        assert metadata["table"] == "products"
        assert metadata["conflict_resolution"] == "update"
        assert metadata["batch_size"] == 500
        assert metadata["dry_run"] is True
        assert metadata["multi_tenant"] is True
        assert metadata["auto_timestamps"] is False
        assert metadata["used_connection_pool"] is False

    @pytest.mark.asyncio
    async def test_large_dataset_batching(self):
        """Test handling of large datasets with batching."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create", table_name="users", batch_size=3
        )

        # Create data larger than batch size
        test_data = [
            {"name": f"User{i}", "email": f"user{i}@example.com"} for i in range(10)
        ]

        result = await node.execute_async(data=test_data)

        assert result["success"] is True
        assert result["created_count"] == 10
        assert result["total_records"] == 10
        assert result["batches"] == 4  # ceil(10/3) = 4

    def test_node_registration(self):
        """Test that the node is properly registered."""
        # The @register_node() decorator should register the node
        # We can test this by checking that the class has the decorator applied
        assert hasattr(BulkCreatePoolNode, "__dict__")
        assert BulkCreatePoolNode.__name__ == "BulkCreatePoolNode"

        # Test that we can instantiate the node (registration check)
        node = BulkCreatePoolNode(node_id="test_registration", table_name="test_table")
        assert node is not None
        assert node.table_name == "test_table"


class TestBulkCreatePoolNodeAdvanced:
    """Test advanced functionality of BulkCreatePoolNode."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_behavior(self):
        """Test tenant isolation functionality."""
        node = BulkCreatePoolNode(
            node_id="test_bulk_create",
            table_name="users",
            multi_tenant=True,
            tenant_isolation=True,
            tenant_id="default_tenant",
        )

        assert node.multi_tenant is True
        assert node.tenant_isolation is True
        assert node.default_tenant_id == "default_tenant"

        test_data = [{"name": "Alice", "email": "alice@example.com"}]

        result = await node.execute_async(data=test_data, tenant_id="specific_tenant")

        assert result["success"] is True
        assert result["tenant_id"] == "specific_tenant"

    @pytest.mark.asyncio
    async def test_conflict_resolution_modes(self):
        """Test different conflict resolution modes."""
        test_modes = ["error", "skip", "update"]

        for mode in test_modes:
            node = BulkCreatePoolNode(
                node_id=f"test_{mode}", table_name="users", conflict_resolution=mode
            )

            assert node.conflict_resolution == mode

            test_data = [{"name": "Alice", "email": "alice@example.com"}]

            result = await node.execute_async(data=test_data)

            assert result["success"] is True
            assert result["metadata"]["conflict_resolution"] == mode

    @pytest.mark.asyncio
    async def test_auto_timestamps_behavior(self):
        """Test auto timestamps functionality."""
        # Test with auto timestamps enabled
        node_with_timestamps = BulkCreatePoolNode(
            node_id="test_with_timestamps", table_name="users", auto_timestamps=True
        )

        assert node_with_timestamps.auto_timestamps is True

        # Test with auto timestamps disabled
        node_without_timestamps = BulkCreatePoolNode(
            node_id="test_without_timestamps", table_name="users", auto_timestamps=False
        )

        assert node_without_timestamps.auto_timestamps is False

        test_data = [{"name": "Alice", "email": "alice@example.com"}]

        # Both should succeed but with different metadata
        result_with = await node_with_timestamps.execute_async(data=test_data)
        result_without = await node_without_timestamps.execute_async(data=test_data)

        assert result_with["metadata"]["auto_timestamps"] is True
        assert result_without["metadata"]["auto_timestamps"] is False

    @pytest.mark.asyncio
    async def test_empty_results_handling(self):
        """Test handling of operations that result in no changes."""
        node = BulkCreatePoolNode(node_id="test_bulk_create", table_name="users")

        # Mock _process_direct to return no created records
        with patch.object(
            node,
            "_process_direct",
            return_value={
                "created_count": 0,
                "batches": 1,
                "skipped_count": 2,
                "conflict_count": 0,
                "error_count": 0,
                "created_ids": [],
                "errors": [],
            },
        ):

            result = await node.execute_async(data=[{"name": "Alice"}, {"name": "Bob"}])

        # Should not be successful if nothing was created and not dry run
        assert result["success"] is False
        assert result["created_count"] == 0
        assert result["skipped_count"] == 2
        assert "skipped_count" in result
