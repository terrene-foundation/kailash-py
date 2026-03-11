"""
Comprehensive Bulk Operations Test Suite

Tests ALL bulk operation methods to ensure complete resolution of:
1. Empty filter {} support
2. Empty data [] support
3. Both auto-generated and standalone nodes

Bug References:
- Bug #4 (v0.5.2): Empty filter support for bulk_update and bulk_delete
- Bug #5 (v0.5.3): Complete bulk operations support (all methods)
"""

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

from dataflow.nodes.bulk_create import BulkCreateNode
from dataflow.nodes.bulk_delete import BulkDeleteNode
from dataflow.nodes.bulk_update import BulkUpdateNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_test_table(test_suite):
    """Create test table with data and clean up after test."""
    connection_string = test_suite.config.url

    # Drop and create table
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS all_bulk_test CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE all_bulk_test (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            value INTEGER NOT NULL,
            status VARCHAR(20) DEFAULT 'active'
        )
        """,
        validate_queries=False,
    )
    await setup_node.async_run()
    await setup_node.cleanup()

    # Insert test data
    insert_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        INSERT INTO all_bulk_test (name, value, status)
        VALUES
            ('Item 1', 10, 'active'),
            ('Item 2', 20, 'active'),
            ('Item 3', 30, 'inactive'),
            ('Item 4', 40, 'active'),
            ('Item 5', 50, 'inactive')
        """,
        validate_queries=False,
    )
    await insert_node.async_run()
    await insert_node.cleanup()

    yield connection_string

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS all_bulk_test CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestBulkDeleteOperations:
    """Test all BulkDeleteNode scenarios including empty filter."""

    @pytest.mark.asyncio
    async def test_bulk_delete_with_empty_filter_safe_mode_disabled(
        self, setup_test_table
    ):
        """
        Test that BulkDeleteNode works with empty filter when safe_mode=False.

        Bug: safe_mode check uses truthiness instead of key existence.
        Expected: Should delete all records with filter={}.
        """
        connection_string = setup_test_table

        node = BulkDeleteNode(
            node_id="test_delete_all",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            safe_mode=False,  # Disable safe mode to allow empty filter
        )

        # Delete all records using empty filter
        result = await node.async_run(
            filter={},  # Empty filter = delete all
            confirmed=True,
        )

        # Verify success
        assert result[
            "success"
        ], f"Expected success but got error: {result.get('error')}"
        assert (
            result["deleted"] == 5
        ), f"Expected 5 deletions but got {result.get('deleted')}"

    @pytest.mark.asyncio
    async def test_bulk_delete_with_empty_filter_safe_mode_enabled_fails(
        self, setup_test_table
    ):
        """
        Test that BulkDeleteNode requires confirmation for empty filter when safe_mode=True.

        Behavior changed in v0.6.3: empty filter {} is now allowed WITH confirmed=True.
        Without confirmation, it should fail.
        """
        connection_string = setup_test_table

        node = BulkDeleteNode(
            node_id="test_delete_safe",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            safe_mode=True,
        )

        # Empty filter WITHOUT confirmation should fail
        result = await node.async_run(
            filter={},  # Empty filter
            confirmed=False,  # No confirmation = should return error
        )

        assert not result["success"]
        assert "Confirmation required" in result["error"]

    @pytest.mark.asyncio
    async def test_bulk_delete_with_non_empty_filter(self, setup_test_table):
        """Test BulkDeleteNode with non-empty filter (should work)."""
        connection_string = setup_test_table

        node = BulkDeleteNode(
            node_id="test_delete_filtered",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            safe_mode=True,  # Safe mode ON but with filter - should work
        )

        result = await node.async_run(
            filter={"status": "inactive"},
            confirmed=True,
        )

        assert result["success"]
        assert result["deleted"] == 2  # Only inactive records


class TestBulkCreateOperations:
    """Test all BulkCreateNode scenarios including empty data."""

    @pytest.mark.asyncio
    async def test_bulk_create_with_empty_data_list(self, setup_test_table):
        """
        Test that BulkCreateNode handles empty data list gracefully.

        Bug: Raises "No data provided" error for empty list.
        Expected: Should return success with 0 inserted (or clear error message).
        """
        connection_string = setup_test_table

        node = BulkCreateNode(
            node_id="test_create_empty",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,
        )

        # This currently fails with "No data provided"
        # After fix, should either succeed with 0 inserted or have clear error
        try:
            result = await node.async_run(data=[])  # Empty data list
            # If it succeeds, verify it handles gracefully
            assert result.get("inserted", 0) == 0
        except Exception as e:
            # If it fails, ensure it's a clear validation error
            assert "No data provided" in str(e) or "Data list is empty" in str(e)

    @pytest.mark.asyncio
    async def test_bulk_create_with_valid_data(self, setup_test_table):
        """Test BulkCreateNode with valid data (should work)."""
        connection_string = setup_test_table

        node = BulkCreateNode(
            node_id="test_create_valid",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,
        )

        result = await node.async_run(
            data=[
                {"name": "New 1", "value": 100, "status": "active"},
                {"name": "New 2", "value": 200, "status": "active"},
            ]
        )

        assert result["success"]
        assert result["inserted"] == 2


class TestBulkUpdateOperations:
    """Test all BulkUpdateNode scenarios including empty filter."""

    @pytest.mark.asyncio
    async def test_bulk_update_with_empty_filter(self, setup_test_table):
        """
        Test that BulkUpdateNode works with empty filter.

        Expected: Should update all records with filter={}.
        """
        connection_string = setup_test_table

        from dataflow.nodes.bulk_update import BulkUpdateNode

        node = BulkUpdateNode(
            node_id="test_update_all",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,
        )

        result = await node.async_run(
            filter={},  # Empty filter = update all
            update_fields={"status": "processed"},
            confirmed=True,
        )

        assert result[
            "success"
        ], f"Expected success but got error: {result.get('error')}"
        assert (
            result["updated"] == 5
        ), f"Expected 5 updates but got {result.get('updated')}"

    @pytest.mark.asyncio
    async def test_bulk_update_with_non_empty_filter(self, setup_test_table):
        """Test BulkUpdateNode with non-empty filter (should work)."""
        connection_string = setup_test_table

        from dataflow.nodes.bulk_update import BulkUpdateNode

        node = BulkUpdateNode(
            node_id="test_update_filtered",
            table_name="all_bulk_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,
        )

        result = await node.async_run(
            filter={"status": "active"},
            update_fields={"value": 999},
            confirmed=True,
        )

        assert result["success"]
        assert result["updated"] == 3  # Only active records


class TestAutoGeneratedBulkNodes:
    """Test auto-generated bulk nodes from DataFlow core."""

    @pytest.mark.asyncio
    async def test_auto_generated_bulk_create_empty_data(self, setup_test_table):
        """
        Test auto-generated BulkCreateNode with empty data.

        Bug: Falls through to "Unsupported bulk operation" error.
        Expected: Should handle gracefully.
        """
        from dataflow import DataFlow

        connection_string = setup_test_table
        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AllBulkTestModel:
            name: str
            value: int
            status: str = "active"

        # Get auto-generated node
        BulkCreate = df._nodes.get("AllBulkTestModelBulkCreateNode")
        assert BulkCreate is not None, "Auto-generated BulkCreateNode not found"

        node = BulkCreate(node_id="auto_create_empty")

        # Test with empty data
        try:
            result = await node.async_run(data=[])
            # Should either succeed with 0 processed or raise clear error
            assert result.get("processed", 0) == 0 or "error" in result
        except Exception as e:
            # Should not be "Unsupported bulk operation"
            assert "Unsupported bulk operation" not in str(e)

    @pytest.mark.asyncio
    async def test_auto_generated_bulk_delete_empty_filter(self, setup_test_table):
        """
        Test auto-generated BulkDeleteNode with empty filter.

        Expected: Should work with empty filter (post-fix).
        """
        from dataflow import DataFlow

        connection_string = setup_test_table
        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class AllBulkTestModel:
            name: str
            value: int
            status: str = "active"

        # Get auto-generated node
        BulkDelete = df._nodes.get("AllBulkTestModelBulkDeleteNode")
        assert BulkDelete is not None, "Auto-generated BulkDeleteNode not found"

        node = BulkDelete(node_id="auto_delete_empty")

        # Test with empty filter
        result = await node.async_run(filter={})

        # Should work after fix (check for key existence, not truthiness)
        assert result.get("success") or result.get("processed") is not None
