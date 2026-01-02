"""
Test Required ID Validation Across All CRUD Operations

Ensures that READ, UPDATE, and DELETE operations properly validate
required ID parameters and don't default to dangerous values like record_id=1.

BUG-009: READ defaulted to record_id=1 (FIXED)
BUG-010: UPDATE defaulted to record_id=1 (FIXED)
"""

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.sdk_exceptions import NodeValidationError
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


class TestReadNodeRequiredID:
    """Test READ operation requires ID parameter."""

    @pytest.mark.asyncio
    async def test_async_read_without_id_raises_error(self, async_runtime):
        """Test async READ raises error when no ID provided."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserReadNode", "read", {})  # No ID provided

        # AsyncRuntime wraps NodeValidationError in WorkflowExecutionError
        with pytest.raises(Exception) as exc_info:
            await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        assert "requires 'id' or 'record_id'" in str(exc_info.value)

    def test_sync_read_without_id_raises_error(self, sync_runtime):
        """Test sync READ raises error when no ID provided."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserReadNode", "read", {})  # No ID provided

        results, run_id = sync_runtime.execute(workflow.build())

        # Runtime catches the exception
        assert "error" in results.get("read", {})
        assert "requires 'id' or 'record_id'" in str(results.get("read", {}))


class TestUpdateNodeRequiredID:
    """Test UPDATE operation requires ID parameter."""

    @pytest.mark.asyncio
    async def test_async_update_without_id_raises_error(self, async_runtime):
        """Test async UPDATE raises error when no ID provided."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpdateNode",
            "update",
            {"fields": {"department": "IT"}},  # Fields but no ID
        )

        # AsyncRuntime wraps NodeValidationError in WorkflowExecutionError
        with pytest.raises(Exception) as exc_info:
            await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        assert "requires 'id' or 'record_id'" in str(exc_info.value)

    def test_sync_update_without_id_raises_error(self, sync_runtime):
        """Test sync UPDATE raises error when no ID provided."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpdateNode",
            "update",
            {"fields": {"department": "HR"}},  # Fields but no ID
        )

        results, run_id = sync_runtime.execute(workflow.build())

        # Runtime catches the exception
        assert "error" in results.get("update", {})
        assert "requires 'id' or 'record_id'" in str(results.get("update", {}))


class TestDeleteNodeRequiredID:
    """Test DELETE operation already has proper validation (regression test)."""

    @pytest.mark.asyncio
    async def test_async_delete_without_id_raises_error(self, async_runtime):
        """Test async DELETE raises error when no ID provided (should already work)."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserDeleteNode", "delete", {})  # No ID provided

        with pytest.raises(Exception) as exc_info:
            await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        assert "requires 'id' or 'record_id'" in str(exc_info.value).lower()

    def test_sync_delete_without_id_raises_error(self, sync_runtime):
        """Test sync DELETE raises error when no ID provided (should already work)."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserDeleteNode", "delete", {})  # No ID provided

        results, run_id = sync_runtime.execute(workflow.build())

        # Runtime catches the exception
        assert "error" in results.get("delete", {})


class TestCreateNodeWithID:
    """Test CREATE operation with explicit ID (our User model requires string ID)."""

    @pytest.mark.asyncio
    async def test_async_create_with_id_succeeds(self, async_runtime):
        """Test async CREATE works with explicit ID."""
        test_id = "create_with_id_test"

        # Cleanup any existing test records
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await async_runtime.execute_workflow_async(delete_workflow.build(), inputs={})

        # Create with explicit ID
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create",
            {
                "id": test_id,
                "email": f"{test_id}@test.com",
                "display_name": "Create Test User",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            },
        )

        result = await async_runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should succeed
        assert "error" not in result.get("results", {}).get("create", {})
        assert result["results"]["create"].get("id") == test_id

        # Cleanup
        await async_runtime.execute_workflow_async(delete_workflow.build(), inputs={})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
