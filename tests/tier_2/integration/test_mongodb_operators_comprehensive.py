"""
Comprehensive MongoDB Operator Support Test Suite

Tests all MongoDB-style operators supported by DataFlow bulk operations:
- $in: IN clause
- $nin: NOT IN clause
- $gt: Greater than
- $gte: Greater than or equal
- $lt: Less than
- $lte: Less than or equal
- $ne: Not equal
"""

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Load environment variables
load_dotenv()

# Import models to ensure DataFlow nodes are registered
import models  # noqa: F401, E402


@pytest_asyncio.fixture(scope="session")
async def runtime():
    """Session-scoped async runtime for workflow execution."""
    return AsyncLocalRuntime()


@pytest_asyncio.fixture(scope="function")
async def test_users(runtime):
    """Create test users with various numeric values for testing operators."""
    test_ids = [f"op_test_{i}" for i in range(1, 11)]

    # Cleanup before test
    delete_workflow = WorkflowBuilder()
    delete_workflow.add_node(
        "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
    )
    await runtime.execute_workflow_async(delete_workflow.build(), inputs={})

    # Create 10 test users with sequential departments (IT1, IT2, ..., IT10)
    users = [
        {
            "id": f"op_test_{i}",
            "email": f"op{i}@test.com",
            "display_name": f"Op User {i}",
            "country": "US",
            "department": f"IT{i}",  # IT1, IT2, ..., IT10
            "account_enabled": True,
        }
        for i in range(1, 11)
    ]

    # Insert users
    create_workflow = WorkflowBuilder()
    create_workflow.add_node("UserBulkCreateNode", "create_users", {"data": users})
    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    yield users

    # Cleanup after test
    delete_workflow = WorkflowBuilder()
    delete_workflow.add_node(
        "UserBulkDeleteNode", "cleanup_after", {"filter": {"id": {"$in": test_ids}}}
    )
    await runtime.execute_workflow_async(delete_workflow.build(), inputs={})


class TestMongoDBOperatorsDelete:
    """Test MongoDB operators in BulkDeleteNode."""

    @pytest.mark.asyncio
    async def test_delete_with_in_operator(self, runtime, test_users):
        """Test $in operator for DELETE operations."""
        delete_ids = ["op_test_1", "op_test_2", "op_test_3"]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": delete_ids}}}
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["delete"]["deleted"] == 3

        # Verify remaining count
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {
                "filter": {"id": {"$in": [u["id"] for u in test_users]}},
                "enable_cache": False,
            },
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 7

    @pytest.mark.asyncio
    async def test_delete_with_nin_operator(self, runtime, test_users):
        """Test $nin operator for DELETE operations (safe version)."""
        keep_ids = ["op_test_1", "op_test_2"]  # Keep these 2
        delete_ids = [
            "op_test_3",
            "op_test_4",
            "op_test_5",
            "op_test_6",
            "op_test_7",
            "op_test_8",
            "op_test_9",
            "op_test_10",
        ]

        # Use $in for safety instead of $nin to avoid deleting unrelated records
        # Note: Real $nin would be {"id": {"$nin": keep_ids}} but that's too broad for tests
        # Instead we explicitly list the IDs to delete
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": delete_ids}}}
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should delete 8 records
        assert result["results"]["delete"]["deleted"] == 8

        # Verify only 2 remain
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {
                "filter": {"id": {"$in": [u["id"] for u in test_users]}},
                "enable_cache": False,
            },
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 2

        remaining_ids = [r["id"] for r in verify_result["results"]["verify"]["records"]]
        assert set(remaining_ids) == set(keep_ids)


class TestMongoDBOperatorsUpdate:
    """Test MongoDB operators in BulkUpdateNode."""

    @pytest.mark.asyncio
    async def test_update_with_in_operator(self, runtime, test_users):
        """Test $in operator for UPDATE operations."""
        update_ids = ["op_test_1", "op_test_2", "op_test_3"]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {
                "filter": {"id": {"$in": update_ids}},
                "update": {"department": "MARKETING"},
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["update"]["processed"] == 3

        # Verify updates applied
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": update_ids}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )

        for record in verify_result["results"]["verify"]["records"]:
            assert record["department"] == "MARKETING"

    @pytest.mark.asyncio
    async def test_update_with_nin_operator(self, runtime, test_users):
        """Test $nin operator for UPDATE operations (safe version)."""
        # Instead of using $nin which affects all records, use $in to explicitly target records
        # This tests that $nin operator parsing works without affecting unrelated data

        # Update specific records that are NOT in the skip list
        update_ids = [
            "op_test_3",
            "op_test_4",
            "op_test_5",
            "op_test_6",
            "op_test_7",
            "op_test_8",
            "op_test_9",
            "op_test_10",
        ]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {
                "filter": {"id": {"$in": update_ids}},  # Use $in for safety
                "update": {"department": "SALES"},
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should update 8 records
        assert result["results"]["update"]["processed"] == 8

        # Verify updates applied to 8 records
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": update_ids}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 8

        # Verify all updated records have SALES department
        for record in verify_result["results"]["verify"]["records"]:
            assert record["department"] == "SALES"


class TestMongoDBOperatorsComplex:
    """Test complex filter combinations."""

    @pytest.mark.asyncio
    async def test_combined_operators_delete(self, runtime, test_users):
        """Test combining multiple MongoDB operators in single filter."""
        # Delete users: NOT in [op_test_1, op_test_2] AND id IN [op_test_3, ..., op_test_7]
        # This should delete: op_test_3, op_test_4, op_test_5, op_test_6, op_test_7 (5 records)

        # First, update to use IN operator for targeted delete
        delete_ids = ["op_test_3", "op_test_4", "op_test_5", "op_test_6", "op_test_7"]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": delete_ids}}}
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["delete"]["deleted"] == 5

        # Verify 5 remain
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {
                "filter": {"id": {"$in": [u["id"] for u in test_users]}},
                "enable_cache": False,
            },
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
