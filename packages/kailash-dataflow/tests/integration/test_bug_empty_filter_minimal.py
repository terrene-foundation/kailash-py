"""
Minimal test to replicate the empty filter bug.
This test MUST fail before the fix and pass after the fix.
"""

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create test suite with database connection."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.asyncio
async def test_empty_filter_bug_reproduction(test_suite):
    """
    MINIMAL BUG REPRODUCTION TEST

    This test demonstrates the bug by trying to use an empty filter
    with BulkDeleteNode. It should FAIL with the current code and
    PASS after the fix is applied.

    Expected error (BEFORE fix): "Unsupported bulk operation: bulk_delete"
    Expected behavior (AFTER fix): Successfully deletes all records
    """
    connection_string = test_suite.config.url

    # Setup: Create a simple test table
    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        DROP TABLE IF EXISTS minimal_bug_test CASCADE;
        CREATE TABLE minimal_bug_test (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100)
        );
        INSERT INTO minimal_bug_test (name) VALUES ('test1'), ('test2'), ('test3');
        """,
        validate_queries=False,
    )

    await setup_node.async_run()
    await setup_node.cleanup()

    # Import BulkDeleteNode
    from dataflow.nodes.bulk_delete import BulkDeleteNode

    # Create BulkDeleteNode instance
    delete_node = BulkDeleteNode(
        node_id="test_delete",
        table_name="minimal_bug_test",
        database_type="postgresql",
        connection_string=connection_string,
    )

    # Try to delete all records using empty filter
    print("\n=== ATTEMPTING DELETE WITH EMPTY FILTER ===")
    result = await delete_node.async_run(
        filter={}, confirmed=True
    )  # Empty filter = delete all

    print(f"Result: {result}")
    print(f"Success: {result.get('success')}")
    if not result.get("success"):
        print(f"ERROR: {result.get('error')}")
    else:
        print(f"Deleted: {result.get('deleted')}")

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS minimal_bug_test CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()

    # Assertions
    # THIS WILL FAIL WITH CURRENT BUGGY CODE:
    assert result.get(
        "success"
    ), f"Expected success but got error: {result.get('error')}"
    assert (
        result.get("deleted", result.get("processed", 0)) == 3
    ), f"Expected 3 deletions but got {result.get('deleted', result.get('processed'))}"

    print("\n✅ TEST PASSED - Bug is fixed!")
