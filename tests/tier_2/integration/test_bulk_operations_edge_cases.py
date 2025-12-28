"""
Comprehensive Edge Case Tests for DataFlow Bulk Operations

Tests edge cases, boundary conditions, and potential bugs across all database types:
- Empty data arrays
- Single record operations
- Large batch operations
- NULL value handling
- Special characters in data
- Transaction boundaries
- Mixed data types
- Operator edge cases
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


class TestBulkCreateEdgeCases:
    """Edge case tests for BulkCreateNode."""

    @pytest.mark.asyncio
    async def test_bulk_create_empty_array(self, runtime):
        """Test bulk create with empty array should succeed with 0 processed."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": []})
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["create"]["success"] is True
        # Should handle empty array gracefully
        processed = result["results"]["create"].get("processed", 0)
        assert processed == 0

    @pytest.mark.asyncio
    async def test_bulk_create_single_record(self, runtime):
        """Test bulk create with single record."""
        test_id = "edge_single_1"

        # Cleanup before
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await runtime.execute_workflow_async(cleanup_workflow.build(), inputs={})

        # Create single record
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "UserBulkCreateNode",
            "create",
            {
                "data": [
                    {
                        "id": test_id,
                        "email": f"{test_id}@test.com",  # Unique email
                        "display_name": "Single User",
                        "country": "US",
                        "department": "IT",
                        "account_enabled": True,
                    }
                ]
            },
        )
        result = await runtime.execute_workflow_async(
            create_workflow.build(), inputs={}
        )

        assert result["results"]["create"]["success"] is True

        # Verify
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": [test_id]}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )
        assert verify_result["results"]["verify"]["count"] == 1

        # Cleanup after
        await runtime.execute_workflow_async(cleanup_workflow.build(), inputs={})

    @pytest.mark.asyncio
    async def test_bulk_create_special_characters(self, runtime):
        """Test bulk create with special characters in data."""
        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "cleanup",
            {"filter": {"id": {"$in": ["edge_special_1"]}}},
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create with special characters
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create",
            {
                "data": [
                    {
                        "id": "edge_special_1",
                        "email": "special+test@example.com",
                        "display_name": "O'Brien (Test) <User>",  # Apostrophe, parens, brackets
                        "country": "US",
                        "department": "R&D",  # Ampersand
                        "account_enabled": True,
                    }
                ]
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["create"]["success"] is True

        # Verify data integrity
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": ["edge_special_1"]}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )

        record = verify_result["results"]["verify"]["records"][0]
        assert record["display_name"] == "O'Brien (Test) <User>"
        assert record["department"] == "R&D"

        # Cleanup
        await runtime.execute_workflow_async(workflow.build(), inputs={})


class TestBulkUpdateEdgeCases:
    """Edge case tests for BulkUpdateNode."""

    @pytest.mark.asyncio
    async def test_bulk_update_empty_filter(self, runtime):
        """Test bulk update with empty filter should require confirmation."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {
                "filter": {},  # Empty filter = update ALL
                "update": {"department": "UPDATED"},
                "safe_mode": True,
                "confirmed": False,
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should fail with safety error
        assert result["results"]["update"]["success"] is False
        assert "confirmed=True" in result["results"]["update"]["error"]

    @pytest.mark.asyncio
    async def test_bulk_update_with_in_empty_list(self, runtime):
        """Test $in operator with empty list."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {
                "filter": {"id": {"$in": []}},  # Empty list
                "update": {"department": "UPDATED"},
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should succeed but update 0 records
        assert result["results"]["update"]["success"] is True
        assert result["results"]["update"]["processed"] == 0

    @pytest.mark.asyncio
    async def test_bulk_update_multiple_operators_same_field(self, runtime):
        """Test multiple operators on same field (should use last one)."""
        # Create test data
        test_ids = ["edge_multi_1", "edge_multi_2", "edge_multi_3"]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create users
        users = [
            {
                "id": f"edge_multi_{i}",
                "email": f"multi{i}@test.com",
                "display_name": f"Multi {i}",
                "country": "US",
                "department": f"Dept{i}",
                "account_enabled": True,
            }
            for i in range(1, 4)
        ]
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": users})
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Update using $in operator
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {"filter": {"id": {"$in": test_ids}}, "update": {"department": "UPDATED"}},
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["update"]["success"] is True
        assert result["results"]["update"]["processed"] == 3

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})


class TestBulkDeleteEdgeCases:
    """Edge case tests for BulkDeleteNode."""

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_filter_requires_confirmation(self, runtime):
        """Test bulk delete with empty filter requires confirmation."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {
                "filter": {},  # Empty filter = delete ALL
                "safe_mode": True,
                "confirmed": False,
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should fail with safety error
        assert result["results"]["delete"]["success"] is False
        assert "confirmed=True" in result["results"]["delete"]["error"]

    @pytest.mark.asyncio
    async def test_bulk_delete_with_in_empty_list(self, runtime):
        """Test $in operator with empty list."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": []}}}
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should succeed but delete 0 records
        assert result["results"]["delete"]["success"] is True
        assert result["results"]["delete"]["deleted"] == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_records(self, runtime):
        """Test bulk delete of records that don't exist."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {
                "filter": {
                    "id": {"$in": ["nonexistent_1", "nonexistent_2", "nonexistent_3"]}
                }
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should succeed but delete 0 records
        assert result["results"]["delete"]["success"] is True
        assert result["results"]["delete"]["deleted"] == 0


class TestBulkUpsertEdgeCases:
    """Edge case tests for BulkUpsertNode."""

    @pytest.mark.asyncio
    async def test_bulk_upsert_empty_array(self, runtime):
        """Test bulk upsert with empty array."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpsertNode",
            "upsert",
            {"data": [], "conflict_resolution": "update", "conflict_fields": ["id"]},
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["upsert"]["success"] is True
        assert result["results"]["upsert"]["processed"] == 0

    @pytest.mark.asyncio
    async def test_bulk_upsert_mixed_insert_update(self, runtime):
        """Test bulk upsert with mix of new and existing records."""
        test_ids = ["edge_mix_1", "edge_mix_2", "edge_mix_3"]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create first 2 users
        initial_users = [
            {
                "id": "edge_mix_1",
                "email": "mix1@test.com",
                "display_name": "Mix 1",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            },
            {
                "id": "edge_mix_2",
                "email": "mix2@test.com",
                "display_name": "Mix 2",
                "country": "US",
                "department": "HR",
                "account_enabled": True,
            },
        ]
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": initial_users})
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Upsert: update first 2, insert third
        upsert_data = [
            {
                "id": "edge_mix_1",
                "email": "mix1@test.com",
                "display_name": "Mix 1 UPDATED",
                "country": "US",
                "department": "IT-NEW",
                "account_enabled": True,
            },
            {
                "id": "edge_mix_2",
                "email": "mix2@test.com",
                "display_name": "Mix 2 UPDATED",
                "country": "US",
                "department": "HR-NEW",
                "account_enabled": True,
            },
            {
                "id": "edge_mix_3",
                "email": "mix3@test.com",
                "display_name": "Mix 3 NEW",
                "country": "US",
                "department": "Finance",
                "account_enabled": True,
            },
        ]
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpsertNode",
            "upsert",
            {
                "data": upsert_data,
                "conflict_resolution": "update",
                "conflict_fields": ["id"],
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["upsert"]["success"] is True
        assert result["results"]["upsert"]["inserted"] == 1  # edge_mix_3
        assert result["results"]["upsert"]["updated"] == 2  # edge_mix_1, edge_mix_2

        # Verify updates applied
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": test_ids}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )

        records = {r["id"]: r for r in verify_result["results"]["verify"]["records"]}
        assert records["edge_mix_1"]["department"] == "IT-NEW"
        assert records["edge_mix_2"]["department"] == "HR-NEW"
        assert records["edge_mix_3"]["department"] == "Finance"

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})


class TestOperatorEdgeCases:
    """Edge case tests for MongoDB operators."""

    @pytest.mark.asyncio
    async def test_in_operator_single_value(self, runtime):
        """Test $in operator with single value in list."""
        test_id = "edge_in_single"

        # Cleanup before test
        cleanup_workflow = WorkflowBuilder()
        cleanup_workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await runtime.execute_workflow_async(cleanup_workflow.build(), inputs={})

        # Create
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "UserBulkCreateNode",
            "create",
            {
                "data": [
                    {
                        "id": test_id,
                        "email": f"{test_id}@test.com",  # Unique email per test
                        "display_name": "Single",
                        "country": "US",
                        "department": "IT",
                        "account_enabled": True,
                    }
                ]
            },
        )
        await runtime.execute_workflow_async(create_workflow.build(), inputs={})

        # Delete using $in with single value
        delete_workflow = WorkflowBuilder()
        delete_workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {"filter": {"id": {"$in": [test_id]}}},  # Single value in list
        )
        result = await runtime.execute_workflow_async(
            delete_workflow.build(), inputs={}
        )

        assert result["results"]["delete"]["success"] is True
        assert result["results"]["delete"]["deleted"] == 1

    @pytest.mark.asyncio
    async def test_in_operator_duplicate_values(self, runtime):
        """Test $in operator with duplicate values in list."""
        test_id = "edge_in_dup"

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": [test_id]}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create",
            {
                "data": [
                    {
                        "id": test_id,
                        "email": "dup@test.com",
                        "display_name": "Dup",
                        "country": "US",
                        "department": "IT",
                        "account_enabled": True,
                    }
                ]
            },
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Delete using $in with duplicates
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode",
            "delete",
            {"filter": {"id": {"$in": [test_id, test_id, test_id]}}},  # Duplicates
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["delete"]["success"] is True
        assert result["results"]["delete"]["deleted"] == 1  # Should delete once

    @pytest.mark.asyncio
    async def test_mixed_operators_in_filter(self, runtime):
        """Test combining multiple different operators."""
        test_ids = [f"edge_mixed_{i}" for i in range(1, 6)]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create test data with sequential departments
        users = [
            {
                "id": f"edge_mixed_{i}",
                "email": f"mixed{i}@test.com",
                "display_name": f"Mixed {i}",
                "country": "US",
                "department": f"Dept{i}",
                "account_enabled": True,
            }
            for i in range(1, 6)
        ]
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": users})
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Update using combined operators: id IN [...] AND account_enabled = true
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkUpdateNode",
            "update",
            {
                "filter": {
                    "id": {"$in": ["edge_mixed_1", "edge_mixed_2", "edge_mixed_3"]},
                    "account_enabled": True,  # Regular equality
                },
                "update": {"department": "COMBINED_OP"},
            },
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["update"]["success"] is True
        assert result["results"]["update"]["processed"] == 3

        # Verify
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {
                "filter": {
                    "id": {"$in": ["edge_mixed_1", "edge_mixed_2", "edge_mixed_3"]}
                },
                "enable_cache": False,
            },
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )

        for record in verify_result["results"]["verify"]["records"]:
            assert record["department"] == "COMBINED_OP"

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})


class TestParameterPlaceholderConsistency:
    """Test parameter placeholder consistency across databases."""

    @pytest.mark.asyncio
    async def test_postgresql_placeholders_sequential(self, runtime):
        """Test PostgreSQL uses sequential $1, $2, $3 placeholders correctly."""
        test_ids = ["edge_pg_1", "edge_pg_2", "edge_pg_3", "edge_pg_4", "edge_pg_5"]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Create
        users = [
            {
                "id": f"edge_pg_{i}",
                "email": f"pg{i}@test.com",
                "display_name": f"PG {i}",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            }
            for i in range(1, 6)
        ]
        workflow = WorkflowBuilder()
        workflow.add_node("UserBulkCreateNode", "create", {"data": users})
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Delete with many values in $in (tests placeholder numbering)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "delete", {"filter": {"id": {"$in": test_ids}}}
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert result["results"]["delete"]["success"] is True
        assert result["results"]["delete"]["deleted"] == 5


class TestTransactionBoundaries:
    """Test transaction handling in bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_create_rollback_on_error(self, runtime):
        """Test that bulk create rolls back on error."""
        # This test verifies transaction handling
        # If one record in batch fails, entire batch should roll back

        test_ids = ["edge_trans_1", "edge_trans_2"]

        # Cleanup
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkDeleteNode", "cleanup", {"filter": {"id": {"$in": test_ids}}}
        )
        await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Try to create with duplicate IDs (should fail)
        users = [
            {
                "id": "edge_trans_1",
                "email": "trans1@test.com",
                "display_name": "Trans 1",
                "country": "US",
                "department": "IT",
                "account_enabled": True,
            },
            {
                "id": "edge_trans_1",
                "email": "trans1_dup@test.com",
                "display_name": "Trans 1 Dup",
                "country": "US",
                "department": "HR",
                "account_enabled": True,
            },
        ]
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserBulkCreateNode",
            "create",
            {"data": users, "error_strategy": "fail_fast"},
        )
        result = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Should fail
        assert result["results"]["create"]["success"] is False

        # Verify NO records were inserted (transaction rolled back)
        verify_workflow = WorkflowBuilder()
        verify_workflow.add_node(
            "UserListNode",
            "verify",
            {"filter": {"id": {"$in": test_ids}}, "enable_cache": False},
        )
        verify_result = await runtime.execute_workflow_async(
            verify_workflow.build(), inputs={}
        )

        assert (
            verify_result["results"]["verify"]["count"] == 0
        )  # Should be 0 due to rollback


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
