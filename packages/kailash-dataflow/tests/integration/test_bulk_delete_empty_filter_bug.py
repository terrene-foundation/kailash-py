"""
Bug Reproduction Test: BulkDeleteNode Empty Filter Issue

This test reproduces the bug where BulkDeleteNode fails when given an empty
filter {} (which should mean "delete all" in MongoDB-style query syntax).

Bug Location: dataflow/core/nodes.py lines 1905 and 1937
Current Code: elif operation == "bulk_delete" and (data or kwargs.get("filter")):
Expected Code: elif operation == "bulk_delete" and (data or "filter" in kwargs):

The issue is that kwargs.get("filter") returns {} which is falsy in Python,
causing the condition to fail even though the filter parameter exists.
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
        query="DROP TABLE IF EXISTS bug_test_users CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE IF NOT EXISTS bug_test_users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
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
        INSERT INTO bug_test_users (name, email, status)
        VALUES
            ('User 1', 'user1@example.com', 'active'),
            ('User 2', 'user2@example.com', 'active'),
            ('User 3', 'user3@example.com', 'inactive')
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
        query="DROP TABLE IF EXISTS bug_test_users CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestBulkDeleteEmptyFilterBug:
    """Test suite for reproducing the empty filter bug."""

    @pytest.mark.asyncio
    async def test_bulk_delete_with_empty_filter_FAILS(self, setup_test_table):
        """
        BUG REPRODUCTION: Empty filter {} should work but currently fails.

        Expected: Delete all records (with confirmed=True)
        Actual: Raises error "Unsupported bulk operation: bulk_delete"
        """
        connection_string = setup_test_table

        # Create BulkDeleteNode
        node = BulkDeleteNode(
            node_id="test_bulk_delete",
            table_name="bug_test_users",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # This SHOULD work but FAILS in v0.5.1
        # Empty filter {} means "match all" in MongoDB-style syntax
        result = await node.async_run(
            filter={},  # Empty filter = delete all
            confirmed=True,  # Required for dangerous operations
        )

        # This assertion will FAIL with current buggy code
        # Error: "Unsupported bulk operation: bulk_delete"
        print("\n=== BUG REPRODUCTION RESULT ===")
        print(f"Success: {result.get('success')}")
        print(f"Error: {result.get('error')}")
        print(f"Result: {result}")

        # These assertions show what SHOULD happen but currently fails
        # assert result["success"], f"Expected success but got error: {result.get('error')}"
        # assert result["deleted"] == 3, f"Expected 3 deletions but got {result.get('deleted')}"

    @pytest.mark.asyncio
    async def test_bulk_update_with_empty_filter_FAILS(self, setup_test_table):
        """
        BUG REPRODUCTION: Empty filter {} should work for bulk_update too.

        Expected: Update all records
        Actual: Raises error "Unsupported bulk operation: bulk_update"
        """
        connection_string = setup_test_table

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="bug_test_users",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # This SHOULD work but FAILS in v0.5.1
        result = await node.async_run(
            filter={},  # Empty filter = update all
            update={"status": "processed"},
            confirmed=True,
        )

        print("\n=== BULK UPDATE BUG REPRODUCTION ===")
        print(f"Success: {result.get('success')}")
        print(f"Error: {result.get('error')}")
        print(f"Result: {result}")

        # These assertions show what SHOULD happen but currently fails
        # assert result["success"], f"Expected success but got error: {result.get('error')}"
        # assert result["updated"] == 3, f"Expected 3 updates but got {result.get('updated')}"

    @pytest.mark.asyncio
    async def test_non_empty_filter_WORKS(self, setup_test_table):
        """
        REGRESSION TEST: Non-empty filters should continue to work.

        This test should PASS both before and after the fix.
        """
        connection_string = setup_test_table

        # Create BulkDeleteNode
        node = BulkDeleteNode(
            node_id="test_bulk_delete",
            table_name="bug_test_users",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Non-empty filter WORKS in v0.5.1
        result = await node.async_run(
            filter={"status": "inactive"}, confirmed=True  # Non-empty filter
        )

        print("\n=== NON-EMPTY FILTER (SHOULD WORK) ===")
        print(f"Success: {result.get('success')}")
        print(f"Deleted: {result.get('deleted')}")
        print(f"Result: {result}")

        # This should work
        assert result["success"], f"Non-empty filter failed: {result.get('error')}"
        assert (
            result["deleted"] == 1
        ), f"Expected 1 deletion but got {result.get('deleted')}"


@pytest.mark.asyncio
async def test_minimal_reproduction():
    """
    Minimal reproduction without IntegrationTestSuite.
    Shows the exact error message from the bug.
    """
    from dataflow.nodes.bulk_delete import BulkDeleteNode

    # This is the simplest way to reproduce the bug
    node = BulkDeleteNode(
        node_id="test_delete",
        table_name="test_table",
        database_type="postgresql",
        connection_string="postgresql://test:test@localhost:5434/test",
    )

    # Try to use empty filter
    try:
        result = await node.async_run(filter={}, confirmed=True)
        print(f"\nUnexpected success: {result}")
    except Exception as e:
        print(f"\nExpected error (shows bug): {e}")
        print(f"Error type: {type(e).__name__}")
