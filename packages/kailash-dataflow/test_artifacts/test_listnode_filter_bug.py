"""
Reproduction test for ListNode filter operator bug
https://github.com/terrene-foundation/kailash-py/issues/XXX

BUG: ListNode silently ignores MongoDB-style filter operators ($ne, $nin, $in, $not)
when filter_dict becomes empty due to JSON parse failure or truthiness check.

ROOT CAUSE: Line 1806 in nodes.py uses truthiness check `if filter_dict:`
which evaluates to False for empty dict {}, skipping QueryBuilder path.

EXPECTED: Use key existence check `"filter" in kwargs` like BulkUpdate/BulkDelete
"""

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestListNodeFilterBug:
    """Test suite proving ListNode filter operators bug"""

    @pytest.fixture
    def setup_test_data(self):
        """Setup: Create test database with sample data"""
        db = DataFlow(":memory:")

        @db.model
        class TestUser:
            id: str
            status: str
            role: str

        # Create test data
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestUserCreateNode",
            "create_active",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "id": "user-1",
                "status": "active",
                "role": "admin",
            },
        )
        workflow.add_node(
            "TestUserCreateNode",
            "create_inactive",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "id": "user-2",
                "status": "inactive",
                "role": "user",
            },
        )

        runtime = LocalRuntime()
        runtime.execute(workflow.build())

        return db

    def test_ne_operator_broken(self, setup_test_data):
        """
        BUG TEST: $ne operator should filter out records, but returns all records
        """
        db = setup_test_data
        workflow = WorkflowBuilder()

        # Query: Get users where status != "inactive"
        # Expected: 1 record (user-1 with status="active")
        # Actual (BUG): 2 records (returns ALL users)
        workflow.add_node(
            "TestUserListNode",
            "query",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "filter": {"status": {"$ne": "inactive"}},
                "limit": 100,
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        users = results["query"]["records"]

        # Assertion
        assert len(users) == 1, (
            f"BUG CONFIRMED: Expected 1 user, got {len(users)} users"
        )
        assert users[0]["status"] == "active", (
            f"Expected active user, got {users[0]['status']}"
        )

    def test_nin_operator_broken(self, setup_test_data):
        """
        BUG TEST: $nin operator should filter out records, but returns all records
        """
        db = setup_test_data
        workflow = WorkflowBuilder()

        # Query: Get users where status NOT IN ["inactive", "banned"]
        # Expected: 1 record (user-1 with status="active")
        # Actual (BUG): 2 records (returns ALL users)
        workflow.add_node(
            "TestUserListNode",
            "query",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "filter": {"status": {"$nin": ["inactive", "banned"]}},
                "limit": 100,
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        users = results["query"]["records"]

        # Assertion
        assert len(users) == 1, (
            f"BUG CONFIRMED: Expected 1 user, got {len(users)} users"
        )
        assert users[0]["status"] == "active"

    def test_in_operator_broken(self, setup_test_data):
        """
        BUG TEST: $in operator should filter records, but returns all records
        """
        db = setup_test_data
        workflow = WorkflowBuilder()

        # Query: Get users where status IN ["active"]
        # Expected: 1 record (user-1 with status="active")
        # Actual (BUG): 2 records (returns ALL users)
        workflow.add_node(
            "TestUserListNode",
            "query",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "filter": {"status": {"$in": ["active"]}},
                "limit": 100,
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        users = results["query"]["records"]

        # Assertion
        assert len(users) == 1, (
            f"BUG CONFIRMED: Expected 1 user, got {len(users)} users"
        )
        assert users[0]["status"] == "active"

    def test_eq_operator_works(self, setup_test_data):
        """
        CONTROL TEST: $eq operator works correctly (always worked)
        """
        db = setup_test_data
        workflow = WorkflowBuilder()

        # Query: Get users where status = "active"
        # Expected: 1 record (user-1)
        # Actual: 1 record ✅ (works correctly)
        workflow.add_node(
            "TestUserListNode",
            "query",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "filter": {"status": "active"},  # Implicit $eq
                "limit": 100,
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        users = results["query"]["records"]

        # Assertion
        assert len(users) == 1
        assert users[0]["status"] == "active"

    def test_empty_filter_dict_triggers_unfiltered_path(self, setup_test_data):
        """
        ROOT CAUSE TEST: Empty filter dict {} causes truthiness check to fail
        """
        db = setup_test_data
        workflow = WorkflowBuilder()

        # Pass empty filter dict (MongoDB "match all" pattern)
        # Expected (MongoDB semantics): Returns all records via QueryBuilder
        # Actual (BUG): Returns all records via unfiltered path (line 1856)
        workflow.add_node(
            "TestUserListNode",
            "query",
            {
                "db_instance": "test_db",
                "model_name": "TestUser",
                "filter": {},  # Empty dict
                "limit": 100,
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        users = results["query"]["records"]

        # This test documents the bug behavior
        # After fix: Should still return 2 records (match all)
        # But via QueryBuilder path, not unfiltered path
        assert len(users) == 2, "Empty filter should return all records"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
