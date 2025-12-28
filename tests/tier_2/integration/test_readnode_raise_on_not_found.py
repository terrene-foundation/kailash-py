"""
Test ReadNode raise_on_not_found parameter in both async and sync modes.

Verifies that the raise_on_not_found parameter works correctly:
- raise_on_not_found=True (default): Raises exception when record not found
- raise_on_not_found=False: Returns {"found": False} without raising
"""

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow.builder import WorkflowBuilder

# Load environment variables
load_dotenv()

# Import models
import models  # noqa: F401, E402


@pytest_asyncio.fixture(scope="session")
async def async_runtime():
    """Session-scoped async runtime."""
    return AsyncLocalRuntime()


@pytest.fixture(scope="session")
def sync_runtime():
    """Session-scoped sync runtime."""
    return LocalRuntime()


class TestReadNodeRaiseOnNotFound:
    """Test raise_on_not_found parameter behavior."""

    @pytest.mark.asyncio
    async def test_async_raise_on_not_found_true_default(self, async_runtime):
        """Test async ReadNode raises exception by default when record not found."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserReadNode",
            "read",
            {"id": "nonexistent_user_12345"},
            # raise_on_not_found not specified - should default to True
        )

        # Should raise NodeExecutionError
        with pytest.raises(Exception) as exc_info:
            await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        # Verify it's the right exception with the right message
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_async_raise_on_not_found_false(self, async_runtime):
        """Test async ReadNode returns found=False when raise_on_not_found=False."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserReadNode",
            "read",
            {"id": "nonexistent_user_67890", "raise_on_not_found": False},
        )

        result = await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should not raise, should return found=False
        assert result["results"]["read"]["found"] is False
        assert "nonexistent_user_67890" in str(result["results"]["read"].get("id", ""))

    def test_sync_raise_on_not_found_true_default(self, sync_runtime):
        """Test sync ReadNode raises exception by default when record not found."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserReadNode",
            "read",
            {"id": "nonexistent_user_sync_123"},
            # raise_on_not_found not specified - should default to True
        )

        # Sync runtime catches node exceptions and returns them in results
        results, run_id = sync_runtime.execute(workflow.build())

        # Should have failed with error message
        assert (
            "error" in results.get("read", {})
            or results.get("read", {}).get("found") is None
        )

    def test_sync_raise_on_not_found_false(self, sync_runtime):
        """Test sync ReadNode returns found=False when raise_on_not_found=False."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserReadNode",
            "read",
            {"id": "nonexistent_user_sync_456", "raise_on_not_found": False},
        )

        results, run_id = sync_runtime.execute(workflow.build())

        # Should not raise, should return found=False
        assert results["read"]["found"] is False
        assert "nonexistent_user_sync_456" in str(results["read"].get("id", ""))

    @pytest.mark.asyncio
    async def test_async_raise_on_not_found_with_existing_record(self, async_runtime):
        """Test that raise_on_not_found doesn't affect behavior when record exists."""
        # Create a test user first
        test_id = "raise_test_exists"

        # Cleanup
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await async_runtime.execute_workflow_async(cleanup_workflow.build(), inputs={})

        # Create user
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "UserCreateNode",
            "create",
            {
                "id": test_id,
                "email": f"{test_id}@test.com",
                "display_name": "Test User",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            },
        )
        await async_runtime.execute_workflow_async(create_workflow.build(), inputs={})

        # Read with raise_on_not_found=False (should still return the record)
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "UserReadNode", "read", {"id": test_id, "raise_on_not_found": False}
        )
        result = await async_runtime.execute_workflow_async(
            read_workflow.build(), inputs={}
        )

        assert result["results"]["read"]["found"] is True
        assert result["results"]["read"]["id"] == test_id

        # Cleanup
        await async_runtime.execute_workflow_async(cleanup_workflow.build(), inputs={})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
