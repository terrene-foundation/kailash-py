"""Unit tests for bulk operations nodes."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.data.bulk_operations import (
    BulkCreateNode,
    BulkDeleteNode,
    BulkErrorStrategy,
    BulkOperationResult,
    BulkUpdateNode,
    BulkUpsertNode,
    DatabaseType,
)
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestBulkOperationMixin:
    """Test the BulkOperationMixin functionality."""

    def test_validate_bulk_data_valid(self):
        """Test validation of valid bulk data."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
        )

        records = [{"name": "Item 1", "value": 10}, {"name": "Item 2", "value": 20}]

        validated = node.validate_bulk_data(records)
        assert validated == records

    def test_validate_bulk_data_empty(self):
        """Test validation rejects empty data."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
        )

        with pytest.raises(NodeValidationError, match="No records provided"):
            node.validate_bulk_data([])

    def test_validate_bulk_data_not_list(self):
        """Test validation rejects non-list data."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
        )

        with pytest.raises(NodeValidationError, match="Records must be a list"):
            node.validate_bulk_data({"not": "a list"})

    def test_validate_bulk_data_invalid_record(self):
        """Test validation rejects non-dict records."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
        )

        records = [
            {"name": "Valid"},
            "invalid",  # Not a dict
            {"name": "Another valid"},
        ]

        with pytest.raises(
            NodeValidationError, match="Record at index 1 must be a dictionary"
        ):
            node.validate_bulk_data(records)

    def test_chunk_records(self):
        """Test record chunking."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
            chunk_size=3,
        )

        records = [{"id": i} for i in range(10)]
        chunks = list(node.chunk_records(records))

        assert len(chunks) == 4  # 3, 3, 3, 1
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3
        assert len(chunks[2]) == 3
        assert len(chunks[3]) == 1

        # Verify all records are included
        all_ids = []
        for chunk in chunks:
            all_ids.extend([r["id"] for r in chunk])
        assert all_ids == list(range(10))

    @pytest.mark.asyncio
    async def test_report_progress(self):
        """Test progress reporting."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test_table",
            report_progress=True,
            progress_interval=2,
        )

        # Progress should be reported at intervals
        await node.report_progress_async(2, 10, "test")  # Should report (2 % 2 == 0)
        await node.report_progress_async(3, 10, "test")  # Should not report
        await node.report_progress_async(4, 10, "test")  # Should report


class TestBulkCreateNode:
    """Test BulkCreateNode functionality."""

    @pytest.mark.asyncio
    async def test_bulk_create_postgresql(self):
        """Test bulk create with PostgreSQL optimizations."""
        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.fetch_all = AsyncMock(
            return_value=[{"id": i} for i in range(1, 4)]
        )

        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            columns=["name", "price"],
            chunk_size=10,
        )

        # Mock adapter creation
        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[
                    {"name": "Product 1", "price": 10.99},
                    {"name": "Product 2", "price": 20.99},
                    {"name": "Product 3", "price": 30.99},
                ]
            )

        assert result["status"] == "success"
        assert result["total_records"] == 3
        assert result["successful_records"] == 3
        assert result["failed_records"] == 0
        assert result["success_rate"] == 100.0

        # Verify SQL was called with multi-row INSERT
        call_args = mock_adapter.fetch_all.call_args[0]
        query = call_args[0]
        assert "INSERT INTO products" in query
        assert "VALUES" in query
        assert "RETURNING" in query

    @pytest.mark.asyncio
    async def test_bulk_create_mysql(self):
        """Test bulk create with MySQL optimizations."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkCreateNode(
            database_type="mysql",
            host="localhost",
            database="test",
            table_name="products",
            columns=["name", "price"],
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[
                    {"name": "Product 1", "price": 10.99},
                    {"name": "Product 2", "price": 20.99},
                ]
            )

        assert result["status"] == "success"
        assert result["successful_records"] == 2

        # Verify multi-row INSERT
        call_args = mock_adapter.execute.call_args[0]
        query = call_args[0]
        assert "INSERT INTO products" in query
        assert "VALUES" in query

    @pytest.mark.asyncio
    async def test_bulk_create_error_handling_fail_fast(self):
        """Test bulk create with fail-fast error strategy."""
        mock_adapter = AsyncMock()
        mock_adapter.fetch_all = AsyncMock(side_effect=Exception("Database error"))

        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            error_strategy="fail_fast",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with pytest.raises(NodeExecutionError, match="Bulk insert failed"):
                await node.execute_async(records=[{"name": "Product 1"}])

    @pytest.mark.asyncio
    async def test_bulk_create_error_handling_continue(self):
        """Test bulk create with continue error strategy."""
        mock_adapter = AsyncMock()
        mock_adapter.fetch_all = AsyncMock(side_effect=Exception("Database error"))

        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            error_strategy="continue",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(records=[{"name": "Product 1"}])

        assert result["status"] == "partial_success"
        assert result["failed_records"] == 1  # 1 record failed during chunking
        assert len(result["errors"]) > 0
        assert "Database error" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_bulk_create_auto_detect_columns(self):
        """Test automatic column detection from records."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkCreateNode(
            database_type="sqlite",
            database=":memory:",
            table_name="products",
            # No columns specified
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[{"name": "Product 1", "price": 10.99, "stock": 100}]
            )

        # Columns should be auto-detected
        assert node.columns == ["name", "price", "stock"]
        assert result["status"] == "success"


class TestBulkUpdateNode:
    """Test BulkUpdateNode functionality."""

    @pytest.mark.asyncio
    async def test_bulk_update_simple(self):
        """Test simple bulk update."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=50)

        node = BulkUpdateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                table_name="products",
                filter={"category": "electronics"},
                updates={"price": 99.99, "updated_at": "2024-01-01"},
            )

        assert result["status"] == "success"
        assert result["updated_count"] == 50

        # Verify query
        call_args = mock_adapter.execute.call_args[0]
        query = call_args[0]
        assert "UPDATE products" in query
        assert "SET" in query
        assert "WHERE" in query

    @pytest.mark.asyncio
    async def test_bulk_update_with_expressions(self):
        """Test bulk update with SQL expressions."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=100)

        node = BulkUpdateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                filter={"in_stock": True},
                updates={
                    "price": "price * 0.9",  # 10% discount expression
                    "sale": True,
                },
            )

        assert result["status"] == "success"
        assert result["updated_count"] == 100

        # Verify expression handling
        query = mock_adapter.execute.call_args[0][0]
        assert "price = price * 0.9" in query
        assert "sale = $" in query  # Boolean should be parameterized

    @pytest.mark.asyncio
    async def test_bulk_update_with_complex_filter(self):
        """Test bulk update with complex filter conditions."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=25)

        node = BulkUpdateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                filter={
                    "price": {"$gte": 100},
                    "stock": {"$lt": 10},
                    "category": "electronics",
                },
                updates={"low_stock_alert": True},
            )

        assert result["status"] == "success"
        assert result["updated_count"] == 25

        # Verify complex conditions
        query = mock_adapter.execute.call_args[0][0]
        assert "price >= $" in query
        assert "stock < $" in query
        assert "category = $" in query

    def test_sql_operator_conversion(self):
        """Test MongoDB operator to SQL conversion."""
        node = BulkUpdateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test",
        )

        assert node._get_sql_operator("$eq") == "="
        assert node._get_sql_operator("$ne") == "!="
        assert node._get_sql_operator("$lt") == "<"
        assert node._get_sql_operator("$lte") == "<="
        assert node._get_sql_operator("$gt") == ">"
        assert node._get_sql_operator("$gte") == ">="
        assert node._get_sql_operator("$in") == "IN"
        assert node._get_sql_operator("$nin") == "NOT IN"


class TestBulkDeleteNode:
    """Test BulkDeleteNode functionality."""

    @pytest.mark.asyncio
    async def test_bulk_delete_hard(self):
        """Test hard delete operation."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=30)

        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            soft_delete=False,
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(filter={"discontinued": True})

        assert result["status"] == "success"
        assert result["deleted_count"] == 30
        assert result["soft_delete"] is False

        # Verify DELETE query
        query = mock_adapter.execute.call_args[0][0]
        assert "DELETE FROM products" in query
        assert "WHERE" in query

    @pytest.mark.asyncio
    async def test_bulk_delete_soft(self):
        """Test soft delete operation."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=20)

        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            soft_delete=True,
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(filter={"active": False})

        assert result["status"] == "success"
        assert result["deleted_count"] == 20
        assert result["soft_delete"] is True

        # Verify UPDATE query for soft delete
        query = mock_adapter.execute.call_args[0][0]
        assert "UPDATE products" in query
        assert "SET deleted_at = CURRENT_TIMESTAMP" in query

    @pytest.mark.asyncio
    async def test_bulk_delete_safety_check(self):
        """Test safety check prevents accidental full table deletion."""
        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            require_filter=True,
        )

        with pytest.raises(
            NodeValidationError, match="Filter required for bulk delete"
        ):
            await node.execute_async(filter={})  # Empty filter

    @pytest.mark.asyncio
    async def test_bulk_delete_no_safety_check(self):
        """Test deletion without safety check."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=1000)

        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            require_filter=False,
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(filter={})  # Empty filter allowed

        assert result["status"] == "success"
        assert result["deleted_count"] == 1000

        # Should delete all records
        query = mock_adapter.execute.call_args[0][0]
        assert "DELETE FROM products" in query
        assert "WHERE" not in query

    @pytest.mark.asyncio
    async def test_bulk_delete_with_in_operator(self):
        """Test deletion with IN operator."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock(return_value=5)

        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(filter={"id": {"$in": [1, 2, 3, 4, 5]}})

        assert result["status"] == "success"
        assert result["deleted_count"] == 5

        # Verify IN clause
        query = mock_adapter.execute.call_args[0][0]
        assert "id IN (" in query
        params = mock_adapter.execute.call_args[0][1:]
        assert list(params) == [1, 2, 3, 4, 5]


class TestBulkUpsertNode:
    """Test BulkUpsertNode functionality."""

    @pytest.mark.asyncio
    async def test_upsert_postgresql(self):
        """Test PostgreSQL UPSERT with ON CONFLICT."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkUpsertNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            conflict_columns=["sku"],
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[
                    {"sku": "PROD-001", "name": "Product 1", "price": 19.99},
                    {"sku": "PROD-002", "name": "Product 2", "price": 29.99},
                ]
            )

        assert result["status"] == "success"
        assert result["successful_records"] == 2

        # Verify PostgreSQL UPSERT syntax
        query = mock_adapter.execute.call_args[0][0]
        assert "INSERT INTO products" in query
        assert "ON CONFLICT (sku)" in query
        assert "DO UPDATE SET" in query

    @pytest.mark.asyncio
    async def test_upsert_mysql(self):
        """Test MySQL UPSERT with ON DUPLICATE KEY UPDATE."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkUpsertNode(
            database_type="mysql",
            host="localhost",
            database="test",
            table_name="products",
            conflict_columns=["sku"],
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[{"sku": "PROD-001", "name": "Product 1", "price": 19.99}]
            )

        assert result["status"] == "success"

        # Verify MySQL UPSERT syntax
        query = mock_adapter.execute.call_args[0][0]
        assert "INSERT INTO products" in query
        assert "ON DUPLICATE KEY UPDATE" in query
        assert "VALUES(" in query  # MySQL syntax

    @pytest.mark.asyncio
    async def test_upsert_sqlite(self):
        """Test SQLite UPSERT with INSERT OR REPLACE."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkUpsertNode(
            database_type="sqlite",
            database=":memory:",
            table_name="products",
            conflict_columns=["sku"],
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[{"sku": "PROD-001", "name": "Product 1", "price": 19.99}]
            )

        assert result["status"] == "success"

        # Verify SQLite syntax
        query = mock_adapter.execute.call_args[0][0]
        assert "INSERT OR REPLACE INTO products" in query

    @pytest.mark.asyncio
    async def test_upsert_auto_detect_update_columns(self):
        """Test automatic detection of update columns."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkUpsertNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            conflict_columns=["id", "sku"],
            # No update_columns specified
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[
                    {"id": 1, "sku": "PROD-001", "name": "Product 1", "price": 19.99}
                ]
            )

        # Should auto-detect update columns (all except conflict columns)
        assert node.update_columns == ["name", "price"]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_upsert_chunking(self):
        """Test upsert with chunking for large datasets."""
        mock_adapter = AsyncMock()
        mock_adapter.execute = AsyncMock()

        node = BulkUpsertNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="products",
            conflict_columns=["sku"],
            chunk_size=2,
        )

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                records=[
                    {"sku": f"PROD-{i:03d}", "name": f"Product {i}"} for i in range(5)
                ]
            )

        assert result["status"] == "success"
        assert result["successful_records"] == 5

        # Should have been called 3 times (chunks: 2, 2, 1)
        assert mock_adapter.execute.call_count == 3


class TestBulkOperationResult:
    """Test BulkOperationResult dataclass."""

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        result = BulkOperationResult(
            total_records=100, successful_records=95, failed_records=5
        )

        assert result.success_rate == 95.0

        # Test edge case: no records
        result_empty = BulkOperationResult(
            total_records=0, successful_records=0, failed_records=0
        )

        assert result_empty.success_rate == 0.0

        # Test all failed
        result_failed = BulkOperationResult(
            total_records=50, successful_records=0, failed_records=50
        )

        assert result_failed.success_rate == 0.0


class TestNodeParameters:
    """Test node parameter definitions."""

    def test_bulk_create_parameters(self):
        """Test BulkCreateNode parameters."""
        node = BulkCreateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test",
        )

        params = node.get_parameters()
        param_names = list(params.keys())

        assert "records" in param_names
        assert "table_name" in param_names
        assert "columns" in param_names
        assert "chunk_size" in param_names
        assert "error_strategy" in param_names
        assert "returning_columns" in param_names

        # Check required parameters
        required_params = [name for name, p in params.items() if p.required]
        assert "records" in required_params
        assert "table_name" in required_params

    def test_bulk_update_parameters(self):
        """Test BulkUpdateNode parameters."""
        node = BulkUpdateNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test",
        )

        params = node.get_parameters()
        param_names = list(params.keys())

        assert "table_name" in param_names
        assert "filter" in param_names
        assert "updates" in param_names
        assert "update_strategy" in param_names

    def test_bulk_delete_parameters(self):
        """Test BulkDeleteNode parameters."""
        node = BulkDeleteNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test",
        )

        params = node.get_parameters()
        param_names = list(params.keys())

        assert "table_name" in param_names
        assert "filter" in param_names
        assert "soft_delete" in param_names
        assert "require_filter" in param_names

    def test_bulk_upsert_parameters(self):
        """Test BulkUpsertNode parameters."""
        node = BulkUpsertNode(
            database_type="postgresql",
            host="localhost",
            database="test",
            table_name="test",
            conflict_columns=["id"],
        )

        params = node.get_parameters()
        param_names = list(params.keys())

        assert "records" in param_names
        assert "table_name" in param_names
        assert "conflict_columns" in param_names
        assert "update_columns" in param_names
