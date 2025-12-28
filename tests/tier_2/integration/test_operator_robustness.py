"""
Test MongoDB Operator Robustness - Edge Cases

Tests robustness improvements for MongoDB operators:
- None value filtering
- Duplicate value deduplication
- Size limit enforcement (10,000 item max)
- Empty list after filtering

BUG-012: None values in $in list (FIXED)
BUG-013: No size limit on $in/$nin lists (FIXED)
"""

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Load environment variables
load_dotenv()

# Import models
import models  # noqa: F401, E402


@pytest_asyncio.fixture(scope="session")
async def runtime():
    """Session-scoped async runtime."""
    return AsyncLocalRuntime()


class TestOperatorNoneHandling:
    """Test None value filtering in operator lists."""

    @pytest.mark.asyncio
    async def test_in_with_none_values(self, runtime):
        """Test $in operator filters out None values."""
        test_ids = ["robust_1", "robust_2", "robust_3"]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create test users
        users = [
            {
                "id": f"robust_{i}",
                "email": f"robust{i}@test.com",
                "display_name": f"Robust {i}",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            }
            for i in range(1, 4)
        ]
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": users})
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Delete with $in containing None values (should filter them out)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {"filter": {"id": {"$in": ["robust_1", None, "robust_2", None]}}},
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should delete 2 (filtering out None values)
        assert result["results"]["delete"]["deleted"] == 2

        # Verify robust_3 still exists
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": test_ids}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 1

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

    @pytest.mark.asyncio
    async def test_in_with_all_none_values(self, runtime):
        """Test $in operator with all None values returns empty (1=0)."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {"filter": {"id": {"$in": [None, None, None]}}},
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should delete 0 (all None values filtered out → empty list → 1=0)
        assert result["results"]["delete"]["deleted"] == 0


class TestOperatorDeduplication:
    """Test duplicate value deduplication in operator lists."""

    @pytest.mark.asyncio
    async def test_in_with_duplicates(self, runtime):
        """Test $in operator deduplicates values for efficiency."""
        test_id = "robust_dup_test"

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create test user
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create",
            {
                "id": test_id,
                "email": f"{test_id}@test.com",
                "display_name": "Dup Test",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            },
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Delete with many duplicates (should deduplicate)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {"filter": {"id": {"$in": [test_id] * 100}}},  # 100 duplicates of same ID
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should still delete just 1 record (deduplication works)
        assert result["results"]["delete"]["deleted"] == 1


class TestOperatorSizeLimit:
    """Test size limit enforcement for large operator lists."""

    @pytest.mark.asyncio
    async def test_in_size_limit_exceeded(self, runtime):
        """Test $in operator raises error when list exceeds 10,000 items."""
        # Create a list with 10,001 items
        large_list = [f"user_{i}" for i in range(10001)]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": large_list}}}
        )

        # AsyncRuntime catches the error and returns it in results
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Check that operation failed with size limit error
        assert result["results"]["delete"]["success"] is False
        error_msg = result["results"]["delete"].get("error", "")
        assert "too large" in error_msg.lower()
        assert "10,000" in error_msg or "10000" in error_msg

    @pytest.mark.asyncio
    async def test_in_size_limit_within_bounds(self, runtime):
        """Test $in operator works with exactly 10,000 items."""
        # Create a list with exactly 10,000 items (should work)
        large_list = [f"user_{i}" for i in range(10000)]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": large_list}}}
        )

        # Should succeed (won't delete anything, but should not error on size)
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})
        assert result["results"]["delete"]["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
