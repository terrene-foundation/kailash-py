"""
Comprehensive tests for DataFlow v0.10.6 features:
1. Timestamp auto-stripping (warning instead of error)
2. soft_delete auto-filtering in ListNode, CountNode, ReadNode

These tests verify both features work correctly together and don't regress.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import patch

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Ensure we import from our local src directory
from dataflow import DataFlow

# Test database URL - uses kaizen_postgres container
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://kaizen_dev:kaizen_dev_password@localhost:5432/kaizen_studio",
)


class TestTimestampAutoStripping:
    """Test that auto-managed timestamp fields are auto-stripped with warnings."""

    @pytest.fixture
    def db(self):
        """Create a DataFlow instance with a test model."""
        test_id = uuid.uuid4().hex[:8]
        db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        @db.model
        class TestUser:
            id: str
            name: str
            email: str
            created_at: Optional[str] = None
            updated_at: Optional[str] = None

        return db

    def test_update_with_updated_at_auto_stripped(self, db, caplog):
        """Test that updated_at is auto-stripped with warning instead of error."""
        # First, create a record
        workflow = WorkflowBuilder()
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        workflow.add_node(
            "TestUserCreateNode",
            "create",
            {"id": test_id, "name": "Original Name", "email": "test@example.com"},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        assert results["create"]["id"] == test_id

        # Now try to update WITH updated_at - should auto-strip with warning
        with caplog.at_level(logging.WARNING):
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "TestUserUpdateNode",
                "update",
                {
                    "filter": {"id": test_id},
                    "fields": {
                        "name": "Updated Name",
                        "updated_at": datetime.now(
                            timezone.utc
                        ).isoformat(),  # Should be stripped
                    },
                },
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(update_workflow.build())

            # Should succeed, not error
            assert results["update"]["name"] == "Updated Name"

            # Should have logged a warning
            assert (
                "AUTO-STRIPPED" in caplog.text or "auto-managed" in caplog.text.lower()
            )

    def test_update_with_created_at_auto_stripped(self, db, caplog):
        """Test that created_at is auto-stripped with warning instead of error."""
        # First, create a record
        workflow = WorkflowBuilder()
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        workflow.add_node(
            "TestUserCreateNode",
            "create",
            {"id": test_id, "name": "Original Name", "email": "test@example.com"},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        assert results["create"]["id"] == test_id

        # Now try to update WITH created_at - should auto-strip with warning
        with caplog.at_level(logging.WARNING):
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "TestUserUpdateNode",
                "update",
                {
                    "filter": {"id": test_id},
                    "fields": {
                        "name": "Updated Name",
                        "created_at": datetime.now(
                            timezone.utc
                        ).isoformat(),  # Should be stripped
                    },
                },
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(update_workflow.build())

            # Should succeed, not error
            assert results["update"]["name"] == "Updated Name"

            # Should have logged a warning
            assert (
                "AUTO-STRIPPED" in caplog.text or "auto-managed" in caplog.text.lower()
            )

    def test_update_with_both_timestamps_auto_stripped(self, db, caplog):
        """Test that both timestamps are auto-stripped with warning."""
        # First, create a record
        workflow = WorkflowBuilder()
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        workflow.add_node(
            "TestUserCreateNode",
            "create",
            {"id": test_id, "name": "Original Name", "email": "test@example.com"},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Now try to update WITH both timestamps - should auto-strip with warning
        with caplog.at_level(logging.WARNING):
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "TestUserUpdateNode",
                "update",
                {
                    "filter": {"id": test_id},
                    "fields": {
                        "name": "Updated Name",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(update_workflow.build())

            # Should succeed, not error
            assert results["update"]["name"] == "Updated Name"

    def test_update_without_timestamps_no_warning(self, db, caplog):
        """Test that updates without timestamps don't generate warnings."""
        # First, create a record
        workflow = WorkflowBuilder()
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        workflow.add_node(
            "TestUserCreateNode",
            "create",
            {"id": test_id, "name": "Original Name", "email": "test@example.com"},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Now update WITHOUT timestamps - should NOT generate warning
        with caplog.at_level(logging.WARNING):
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "TestUserUpdateNode",
                "update",
                {
                    "filter": {"id": test_id},
                    "fields": {"name": "Updated Name"},  # No timestamps
                },
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(update_workflow.build())

            # Should succeed
            assert results["update"]["name"] == "Updated Name"

            # Should NOT have auto-stripped warning
            assert "AUTO-STRIPPED" not in caplog.text


class TestSoftDeleteAutoFilter:
    """Test that soft_delete auto-filters queries by default."""

    @pytest.fixture
    def db_with_soft_delete(self):
        """Create a DataFlow instance with a soft_delete model."""
        test_id = uuid.uuid4().hex[:8]
        db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        @db.model
        class SoftDeletePatient:
            id: str
            name: str
            status: str
            deleted_at: Optional[str] = None
            created_at: Optional[str] = None
            updated_at: Optional[str] = None
            __dataflow__ = {"soft_delete": True}

        return db

    def test_list_excludes_soft_deleted_by_default(self, db_with_soft_delete):
        """ListNode should exclude soft-deleted records by default."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create some records
        test_prefix = f"test-{uuid.uuid4().hex[:8]}"
        for i, status in enumerate(["active", "deleted", "active"]):
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "SoftDeletePatientCreateNode",
                "create",
                {
                    "id": f"{test_prefix}-{i}",
                    "name": f"Patient {i}",
                    "status": status,
                    "deleted_at": (
                        datetime.now(timezone.utc).isoformat()
                        if status == "deleted"
                        else None
                    ),
                },
            )
            runtime.execute(create_workflow.build())

        # List without include_deleted - should only get 2 active records
        list_workflow = WorkflowBuilder()
        list_workflow.add_node(
            "SoftDeletePatientListNode",
            "list",
            {"filter": {"id": {"$startswith": test_prefix}}},
        )
        results, _ = runtime.execute(list_workflow.build())

        records = results["list"]["records"]
        # Should only have 2 records (the ones without deleted_at)
        assert len(records) == 2
        for record in records:
            assert record["deleted_at"] is None

    def test_list_includes_soft_deleted_with_flag(self, db_with_soft_delete):
        """ListNode should include soft-deleted records with include_deleted=True."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create some records
        test_prefix = f"test-{uuid.uuid4().hex[:8]}"
        for i, status in enumerate(["active", "deleted", "active"]):
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "SoftDeletePatientCreateNode",
                "create",
                {
                    "id": f"{test_prefix}-{i}",
                    "name": f"Patient {i}",
                    "status": status,
                    "deleted_at": (
                        datetime.now(timezone.utc).isoformat()
                        if status == "deleted"
                        else None
                    ),
                },
            )
            runtime.execute(create_workflow.build())

        # List WITH include_deleted=True - should get all 3 records
        list_workflow = WorkflowBuilder()
        list_workflow.add_node(
            "SoftDeletePatientListNode",
            "list",
            {
                "filter": {"id": {"$startswith": test_prefix}},
                "include_deleted": True,
            },
        )
        results, _ = runtime.execute(list_workflow.build())

        records = results["list"]["records"]
        # Should have all 3 records
        assert len(records) == 3

    def test_count_excludes_soft_deleted_by_default(self, db_with_soft_delete):
        """CountNode should exclude soft-deleted records by default."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create some records
        test_prefix = f"test-{uuid.uuid4().hex[:8]}"
        for i, status in enumerate(["active", "deleted", "active"]):
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "SoftDeletePatientCreateNode",
                "create",
                {
                    "id": f"{test_prefix}-{i}",
                    "name": f"Patient {i}",
                    "status": status,
                    "deleted_at": (
                        datetime.now(timezone.utc).isoformat()
                        if status == "deleted"
                        else None
                    ),
                },
            )
            runtime.execute(create_workflow.build())

        # Count without include_deleted - should count only 2 active records
        count_workflow = WorkflowBuilder()
        count_workflow.add_node(
            "SoftDeletePatientCountNode",
            "count",
            {"filter": {"id": {"$startswith": test_prefix}}},
        )
        results, _ = runtime.execute(count_workflow.build())

        # Should only count 2 records
        assert results["count"]["count"] == 2

    def test_count_includes_soft_deleted_with_flag(self, db_with_soft_delete):
        """CountNode should include soft-deleted records with include_deleted=True."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create some records
        test_prefix = f"test-{uuid.uuid4().hex[:8]}"
        for i, status in enumerate(["active", "deleted", "active"]):
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "SoftDeletePatientCreateNode",
                "create",
                {
                    "id": f"{test_prefix}-{i}",
                    "name": f"Patient {i}",
                    "status": status,
                    "deleted_at": (
                        datetime.now(timezone.utc).isoformat()
                        if status == "deleted"
                        else None
                    ),
                },
            )
            runtime.execute(create_workflow.build())

        # Count WITH include_deleted=True - should count all 3
        count_workflow = WorkflowBuilder()
        count_workflow.add_node(
            "SoftDeletePatientCountNode",
            "count",
            {
                "filter": {"id": {"$startswith": test_prefix}},
                "include_deleted": True,
            },
        )
        results, _ = runtime.execute(count_workflow.build())

        # Should count all 3 records
        assert results["count"]["count"] == 3

    def test_read_treats_soft_deleted_as_not_found_by_default(
        self, db_with_soft_delete
    ):
        """ReadNode should treat soft-deleted records as not found by default."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create a soft-deleted record
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "SoftDeletePatientCreateNode",
            "create",
            {
                "id": test_id,
                "name": "Deleted Patient",
                "status": "deleted",
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        runtime.execute(create_workflow.build())

        # Read without include_deleted - should return not found
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "SoftDeletePatientReadNode",
            "read",
            {"id": test_id},
        )
        results, _ = runtime.execute(read_workflow.build())

        # Should be not found (None or found=False)
        result = results["read"]
        assert result is None or result.get("found") is False

    def test_read_returns_soft_deleted_with_flag(self, db_with_soft_delete):
        """ReadNode should return soft-deleted records with include_deleted=True."""
        db = db_with_soft_delete
        runtime = LocalRuntime()

        # Create a soft-deleted record
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "SoftDeletePatientCreateNode",
            "create",
            {
                "id": test_id,
                "name": "Deleted Patient",
                "status": "deleted",
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        runtime.execute(create_workflow.build())

        # Read WITH include_deleted=True - should return the record
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "SoftDeletePatientReadNode",
            "read",
            {"id": test_id, "include_deleted": True},
        )
        results, _ = runtime.execute(read_workflow.build())

        # Should find the record
        result = results["read"]
        assert result is not None
        assert result.get("id") == test_id or result.get("found") is True


class TestModelWithoutSoftDelete:
    """Test that models without soft_delete behave normally."""

    @pytest.fixture
    def db_without_soft_delete(self):
        """Create a DataFlow instance with a regular model (no soft_delete)."""
        test_id = uuid.uuid4().hex[:8]
        db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        @db.model
        class RegularProduct:
            id: str
            name: str
            price: float
            deleted_at: Optional[str] = None  # Has field but NOT soft_delete enabled
            created_at: Optional[str] = None
            updated_at: Optional[str] = None

        return db

    def test_list_includes_all_records_without_soft_delete_config(
        self, db_without_soft_delete
    ):
        """Models without soft_delete config should return all records."""
        db = db_without_soft_delete
        runtime = LocalRuntime()

        # Create records (some with deleted_at set, but model doesn't have soft_delete)
        test_prefix = f"test-{uuid.uuid4().hex[:8]}"
        for i in range(3):
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "RegularProductCreateNode",
                "create",
                {
                    "id": f"{test_prefix}-{i}",
                    "name": f"Product {i}",
                    "price": 10.0 * (i + 1),
                    # Even if deleted_at is set, should still be included
                    "deleted_at": (
                        datetime.now(timezone.utc).isoformat() if i == 1 else None
                    ),
                },
            )
            runtime.execute(create_workflow.build())

        # List all - should get ALL 3 records because soft_delete is NOT enabled
        list_workflow = WorkflowBuilder()
        list_workflow.add_node(
            "RegularProductListNode",
            "list",
            {"filter": {"id": {"$startswith": test_prefix}}},
        )
        results, _ = runtime.execute(list_workflow.build())

        records = results["list"]["records"]
        # Should have all 3 records (soft_delete NOT enabled)
        assert len(records) == 3


class TestAsyncRuntime:
    """Test that features work with AsyncLocalRuntime."""

    @pytest.fixture
    def db(self):
        """Create a DataFlow instance with a test model."""
        test_id = uuid.uuid4().hex[:8]
        db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        @db.model
        class AsyncTestModel:
            id: str
            name: str
            deleted_at: Optional[str] = None
            created_at: Optional[str] = None
            updated_at: Optional[str] = None
            __dataflow__ = {"soft_delete": True}

        return db

    @pytest.mark.asyncio
    async def test_timestamp_stripping_async_runtime(self, db, caplog):
        """Test timestamp auto-stripping works with async runtime."""
        runtime = AsyncLocalRuntime()
        test_id = f"test-{uuid.uuid4().hex[:8]}"

        # Create a record
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "AsyncTestModelCreateNode",
            "create",
            {"id": test_id, "name": "Test"},
        )
        results, _ = await runtime.execute_workflow_async(create_workflow.build())

        # Update with timestamp - should auto-strip
        with caplog.at_level(logging.WARNING):
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "AsyncTestModelUpdateNode",
                "update",
                {
                    "filter": {"id": test_id},
                    "fields": {
                        "name": "Updated",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
            results, _ = await runtime.execute_workflow_async(update_workflow.build())
            assert results["update"]["name"] == "Updated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
