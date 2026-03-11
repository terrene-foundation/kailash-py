"""
Regression Test: Empty Filter Bug Fix

This test verifies the fix for the empty filter bug where BulkDeleteNode and
BulkUpdateNode failed when given an empty filter {} (which should mean "delete/update all"
in MongoDB-style query syntax).

Bug Location: dataflow/core/nodes.py lines 1905 and 1937
Root Cause: Python truthiness - empty dict {} is falsy
Fix: Changed from truthiness check to key existence check

BUGGY:  elif operation == "bulk_delete" and (data or kwargs.get("filter")):
FIXED:  elif operation == "bulk_delete" and (data or "filter" in kwargs):
"""

import pytest
from dataflow.nodes.bulk_create import BulkCreateNode
from dataflow.nodes.bulk_delete import BulkDeleteNode
from dataflow.nodes.bulk_update import BulkUpdateNode

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
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
        query="DROP TABLE IF EXISTS empty_filter_test CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE empty_filter_test (
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
        INSERT INTO empty_filter_test (name, value, status)
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
        query="DROP TABLE IF EXISTS empty_filter_test CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestEmptyFilterRegression:
    """Regression tests for empty filter bug fix."""

    def _extract_result_data(self, result):
        """Extract data from AsyncSQLDatabaseNode result format."""
        if (
            isinstance(result, dict)
            and "result" in result
            and "data" in result["result"]
        ):
            data = result["result"]["data"]
            # Handle AsyncSQLDatabaseNode quirk where empty results return [{'rows_affected': 0}]
            if (
                len(data) == 1
                and isinstance(data[0], dict)
                and "rows_affected" in data[0]
                and len(data[0]) == 1
            ):
                return []  # Empty result
            return data
        return result

    @pytest.mark.asyncio
    async def test_bulk_delete_with_empty_filter(self, setup_test_table):
        """
        REGRESSION TEST: Empty filter {} should work for bulk_delete.

        Before fix: Failed with "Unsupported bulk operation: bulk_delete"
        After fix: Successfully deletes all records
        """
        connection_string = setup_test_table

        # Create BulkDeleteNode (disable safe_mode to allow empty filter)
        node = BulkDeleteNode(
            node_id="test_bulk_delete",
            table_name="empty_filter_test",
            database_type="postgresql",
            connection_string=connection_string,
            safe_mode=False,  # Disable safe mode for this test
        )

        # Delete all records using empty filter (MongoDB-style "match all")
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

        # Verify all records deleted
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM empty_filter_test",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert len(data) == 0, f"Expected 0 remaining records but found {len(data)}"

    @pytest.mark.asyncio
    async def test_bulk_update_with_empty_filter(self, setup_test_table):
        """
        REGRESSION TEST: Empty filter {} should work for bulk_update.

        Before fix: Failed with "Unsupported bulk operation: bulk_update"
        After fix: Successfully updates all records
        """
        connection_string = setup_test_table

        # Create BulkUpdateNode (disable auto_timestamps since our test table doesn't have updated_at)
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="empty_filter_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,  # Disable auto timestamps for simple test table
        )

        # Update all records using empty filter
        result = await node.async_run(
            filter={},  # Empty filter = update all
            update_fields={"status": "processed"},  # Use update_fields parameter
            confirmed=True,
        )

        # Verify success
        assert result[
            "success"
        ], f"Expected success but got error: {result.get('error')}"
        assert (
            result["updated"] == 5
        ), f"Expected 5 updates but got {result.get('updated')}"

        # Verify all records updated
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM empty_filter_test WHERE status = 'processed'",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert len(data) == 5, f"Expected 5 processed records but found {len(data)}"

    @pytest.mark.asyncio
    async def test_empty_filter_vs_non_empty_filter(self, setup_test_table):
        """
        REGRESSION TEST: Verify empty filter {} behaves differently from non-empty filter.

        This test ensures the fix correctly distinguishes between:
        - Empty filter {} = match all
        - Filter with condition = match specific records
        """
        connection_string = setup_test_table

        # First, test with NON-empty filter (should delete only matching records)
        node1 = BulkDeleteNode(
            node_id="test_delete_1",
            table_name="empty_filter_test",
            database_type="postgresql",
            connection_string=connection_string,
        )

        result1 = await node1.async_run(
            filter={"status": "inactive"},  # Non-empty filter
            confirmed=True,
        )

        assert result1["success"]
        assert result1["deleted"] == 2  # Only 2 inactive records

        # Verify 3 active records remain
        verify_node1 = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM empty_filter_test",
            validate_queries=False,
        )
        verify_result1 = await verify_node1.async_run()
        await verify_node1.cleanup()
        data1 = self._extract_result_data(verify_result1)
        assert len(data1) == 3, f"Expected 3 remaining records but found {len(data1)}"

        # Now test with EMPTY filter (should delete all remaining records)
        node2 = BulkDeleteNode(
            node_id="test_delete_2",
            table_name="empty_filter_test",
            database_type="postgresql",
            connection_string=connection_string,
            safe_mode=False,  # Disable safe mode for empty filter test
        )

        result2 = await node2.async_run(
            filter={},  # Empty filter = delete all
            confirmed=True,
        )

        assert result2["success"]
        assert result2["deleted"] == 3  # All 3 remaining records

        # Verify no records remain
        verify_node2 = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM empty_filter_test",
            validate_queries=False,
        )
        verify_result2 = await verify_node2.async_run()
        await verify_node2.cleanup()
        data2 = self._extract_result_data(verify_result2)
        assert len(data2) == 0, f"Expected 0 records but found {len(data2)}"

    @pytest.mark.asyncio
    async def test_no_filter_parameter_still_works(self, setup_test_table):
        """
        REGRESSION TEST: Verify operations without filter parameter still work.

        This ensures the fix doesn't break operations that don't use filter at all.
        """
        connection_string = setup_test_table

        # Create node for bulk create (doesn't use filter)
        create_node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="empty_filter_test",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=False,  # Disable auto timestamps for simple test table
        )

        # Create records without filter parameter
        result = await create_node.async_run(
            data=[
                {"name": "New Item 1", "value": 100, "status": "new"},
                {"name": "New Item 2", "value": 200, "status": "new"},
            ]
        )

        # Verify success
        assert result[
            "success"
        ], f"Bulk create without filter failed: {result.get('error')}"
        assert (
            result["inserted"] == 2
        ), f"Expected 2 inserted but got {result.get('inserted')}"

        # Verify records created
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM empty_filter_test WHERE status = 'new'",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert len(data) == 2, f"Expected 2 new records but found {len(data)}"
