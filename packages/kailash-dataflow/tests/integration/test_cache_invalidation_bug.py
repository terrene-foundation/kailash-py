"""
Reproduction test for cache invalidation bug in bulk operations.

Bug: BulkDeleteNode, BulkUpdateNode, and BulkUpsertNode do not invalidate
the query cache after modifying data, causing ListNode to return stale cached results.

Expected: After bulk_delete, bulk_update, or bulk_upsert, subsequent list queries
          should return fresh data from the database.
Actual: ListNode returns stale cached data because cache was not invalidated.
"""

from datetime import datetime, timedelta

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_test_table(test_suite):
    """Create test table for cache invalidation testing."""
    connection_string = test_suite.config.url

    # Drop and create table
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS cache_test_records CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE cache_test_records (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL,
            value INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        validate_queries=False,
    )
    await setup_node.async_run()
    await setup_node.cleanup()

    yield connection_string

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS cache_test_records CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestCacheInvalidationBugRepro:
    """Reproduce cache invalidation bug in bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_delete_cache_invalidation(self, setup_test_table):
        """
        Bug Reproduction: BulkDeleteNode doesn't invalidate cache.

        Sequence:
        1. BulkCreateNode creates records ✅ (invalidates cache ✅)
        2. ListNode queries → gets fresh data ✅
        3. BulkDeleteNode deletes records ✅ (doesn't invalidate cache ❌ BUG)
        4. ListNode queries → returns stale cached data ❌ BUG

        Expected: Step 4 should return empty list
        Actual: Step 4 returns old data from cache
        """
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class CacheTestRecord:
            name: str
            status: str
            value: int

        runtime = LocalRuntime()

        # Step 1: Create initial records with cache enabled
        create_wf = WorkflowBuilder()
        create_wf.add_node(
            "CacheTestRecordBulkCreateNode",
            "create",
            {
                "data": [
                    {"name": "record1", "status": "active", "value": 100},
                    {"name": "record2", "status": "active", "value": 200},
                    {"name": "record3", "status": "active", "value": 300},
                ]
            },
        )
        results, _ = runtime.execute(create_wf.build())
        assert results["create"]["success"], "Create should succeed"
        assert results["create"]["inserted"] == 3, "Should insert 3 records"

        # Step 2: Query with cache enabled - should get 3 records from database
        list1_wf = WorkflowBuilder()
        list1_wf.add_node(
            "CacheTestRecordListNode",
            "list1",
            {
                "filter": {"status": "active"},
                "enable_cache": True,
                "limit": 100,
            },
        )
        results, _ = runtime.execute(list1_wf.build())
        assert results["list1"]["count"] == 3, "Should get 3 records from database"
        # Cache should be populated now with 3 records

        # Step 3: Bulk delete all active records
        # BUG: This should invalidate cache but doesn't!
        delete_wf = WorkflowBuilder()
        delete_wf.add_node(
            "CacheTestRecordBulkDeleteNode",
            "delete",
            {
                "filter": {"status": "active"},
                "confirmed": True,
                "safe_mode": False,
            },
        )
        results, _ = runtime.execute(delete_wf.build())
        assert results["delete"]["success"], "Delete should succeed"
        assert results["delete"]["processed"] == 3, "Should delete 3 records"

        # Step 4: Query again with cache enabled
        # BUG: Returns stale cache (3 records) instead of fresh data (0 records)
        list2_wf = WorkflowBuilder()
        list2_wf.add_node(
            "CacheTestRecordListNode",
            "list2",
            {
                "filter": {"status": "active"},
                "enable_cache": True,
                "limit": 100,
            },
        )
        results, _ = runtime.execute(list2_wf.build())

        # THIS ASSERTION FAILS WITH THE BUG
        assert (
            results["list2"]["count"] == 0
        ), f"Should get 0 records after delete, but got {results['list2']['count']} from stale cache"

        # Verify it's actually a cache hit (not fresh query)
        if "_cache" in results["list2"]:
            cache_info = results["list2"]["_cache"]
            print(f"Cache info: {cache_info}")
            # If this is a cache hit, it proves the bug
            if cache_info.get("hit"):
                pytest.fail(
                    f"BUG CONFIRMED: Got stale cache hit after bulk_delete. "
                    f"Cache should have been invalidated but wasn't. "
                    f"Returned {results['list2']['count']} records from cache instead of 0 from database."
                )

    @pytest.mark.asyncio
    async def test_bulk_update_cache_invalidation(self, setup_test_table):
        """
        Bug Reproduction: BulkUpdateNode doesn't invalidate cache.

        Similar to delete test but with updates.
        """
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class CacheTestRecord:
            name: str
            status: str
            value: int

        runtime = LocalRuntime()

        # Step 1: Create records
        create_wf = WorkflowBuilder()
        create_wf.add_node(
            "CacheTestRecordBulkCreateNode",
            "create",
            {
                "data": [
                    {"name": "record1", "status": "pending", "value": 100},
                    {"name": "record2", "status": "pending", "value": 200},
                ]
            },
        )
        results, _ = runtime.execute(create_wf.build())
        assert results["create"]["inserted"] == 2

        # Step 2: Query and cache the results
        list1_wf = WorkflowBuilder()
        list1_wf.add_node(
            "CacheTestRecordListNode",
            "list1",
            {
                "filter": {"status": "pending"},
                "enable_cache": True,
            },
        )
        results, _ = runtime.execute(list1_wf.build())
        assert results["list1"]["count"] == 2
        # Verify all have status "pending"
        for record in results["list1"]["records"]:
            assert record["status"] == "pending"

        # Step 3: Bulk update to change status
        # BUG: This should invalidate cache but doesn't!
        update_wf = WorkflowBuilder()
        update_wf.add_node(
            "CacheTestRecordBulkUpdateNode",
            "update",
            {
                "filter": {"status": "pending"},
                "update": {"status": "completed"},
            },
        )
        results, _ = runtime.execute(update_wf.build())
        assert results["update"]["processed"] == 2

        # Step 4: Query for pending records again
        # BUG: Returns stale cache (2 records) instead of fresh data (0 records)
        list2_wf = WorkflowBuilder()
        list2_wf.add_node(
            "CacheTestRecordListNode",
            "list2",
            {
                "filter": {"status": "pending"},
                "enable_cache": True,
            },
        )
        results, _ = runtime.execute(list2_wf.build())

        # THIS ASSERTION FAILS WITH THE BUG
        assert (
            results["list2"]["count"] == 0
        ), f"Should get 0 pending records after update, but got {results['list2']['count']} from stale cache"

    @pytest.mark.asyncio
    async def test_bulk_create_then_delete_then_create_cache_bug(
        self, setup_test_table
    ):
        """
        EXACT reproduction from user's bug report.

        Test Sequence:
        1. BulkDeleteNode deletes all records ✅ (cache NOT invalidated ❌)
        2. BulkCreateNode inserts 1 record ✅ (cache invalidated ✅)
        3. ListNode queries → should return 1 record but gets stale empty cache

        This is the EXACT scenario the user reported.
        """
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class CacheTestRecord:
            name: str
            status: str
            value: int

        runtime = LocalRuntime()

        # Populate some initial data
        init_wf = WorkflowBuilder()
        init_wf.add_node(
            "CacheTestRecordBulkCreateNode",
            "init",
            {"data": [{"name": "old", "status": "old", "value": 999}]},
        )
        runtime.execute(init_wf.build())

        # Query to populate cache
        list_init_wf = WorkflowBuilder()
        list_init_wf.add_node(
            "CacheTestRecordListNode",
            "list_init",
            {"filter": {}, "enable_cache": True, "limit": 100},
        )
        results, _ = runtime.execute(list_init_wf.build())
        assert results["list_init"]["count"] == 1  # Cache now has 1 record

        # Step 1: Delete all records (cache NOT invalidated - BUG)
        delete_wf = WorkflowBuilder()
        delete_wf.add_node(
            "CacheTestRecordBulkDeleteNode",
            "cleanup",
            {"filter": {}, "confirmed": True, "safe_mode": False},
        )
        results, _ = runtime.execute(delete_wf.build())
        assert results["cleanup"]["success"]

        # Step 2: Insert new record (cache IS invalidated)
        insert_wf = WorkflowBuilder()
        insert_wf.add_node(
            "CacheTestRecordBulkCreateNode",
            "insert",
            {
                "data": [
                    {
                        "name": "new_record",
                        "status": "active",
                        "value": 300,
                    }
                ]
            },
        )
        results, _ = runtime.execute(insert_wf.build())
        assert results["insert"]["inserted"] == 1

        # Step 3: Query (should return 1 record from database)
        # BUG SCENARIO: If delete didn't invalidate cache, and query param changed,
        # we might get wrong cached result
        query_wf = WorkflowBuilder()
        query_wf.add_node(
            "CacheTestRecordListNode",
            "query",
            {"filter": {}, "enable_cache": True, "limit": 100},
        )
        results, _ = runtime.execute(query_wf.build())

        # Should get the newly inserted record
        assert (
            results["query"]["count"] == 1
        ), f"Expected 1 record, got {results['query']['count']}"
        assert results["query"]["records"][0]["name"] == "new_record"
