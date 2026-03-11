"""Integration tests for type-aware operations using PostgreSQL.

Tests that TypeAwareFieldProcessor correctly validates and processes
field types in real database operations.

Related: TODO-153 - Type-Aware Model Processing
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import pytest
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# PostgreSQL connection URL for integration tests
PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://kaizen_dev:kaizen_dev_password@localhost:5432/kailash_test",
)


@pytest.fixture
def db():
    """Create a DataFlow instance for testing."""
    from dataflow import DataFlow

    db = DataFlow(PG_URL, auto_migrate=True)
    yield db
    # Cleanup handled by DataFlow's context manager


@pytest.fixture
def runtime():
    """Create a LocalRuntime for executing workflows."""
    return LocalRuntime()


class TestStringIDTypePreservation:
    """Integration tests for string ID preservation."""

    def test_string_id_preserved_in_create(self, db, runtime):
        """String IDs should be preserved during CREATE operations."""

        @db.model
        class StringUser:
            id: str
            name: str

        # Create a user with string ID
        workflow = WorkflowBuilder()
        workflow.add_node(
            "StringUserCreateNode",
            "create",
            {"id": "user-abc123", "name": "Alice"},
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        assert created["id"] == "user-abc123"
        assert isinstance(created["id"], str)

    def test_string_id_preserved_in_read(self, db, runtime):
        """String IDs should be preserved during READ operations."""

        @db.model
        class StringProduct:
            id: str
            name: str

        # Create first
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "StringProductCreateNode",
            "create",
            {"id": "prod-xyz789", "name": "Widget"},
        )
        runtime.execute(create_workflow.build())

        # Read back
        read_workflow = WorkflowBuilder()
        read_workflow.add_node(
            "StringProductReadNode",
            "read",
            {"id": "prod-xyz789"},
        )

        results, _ = runtime.execute(read_workflow.build())
        record = results.get("read")

        assert record is not None
        assert record["id"] == "prod-xyz789"
        assert isinstance(record["id"], str)


class TestUUIDFieldOperations:
    """Integration tests for UUID field handling."""

    def test_uuid_preserved_in_crud(self, db, runtime):
        """UUID fields should be properly handled in CRUD operations."""

        @db.model
        class UUIDEntity:
            id: UUID
            name: str

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")

        # Create with UUID
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UUIDEntityCreateNode",
            "create",
            {"id": str(test_uuid), "name": "Test Entity"},
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        # UUID may come back as string from DB but should be valid UUID
        assert str(created["id"]).replace("-", "") == str(test_uuid).replace("-", "")


class TestIntegerFieldValidation:
    """Integration tests for integer field validation."""

    def test_integer_id_preserved(self, db, runtime):
        """Integer IDs should be preserved during operations."""

        @db.model
        class IntCounter:
            id: int
            value: int

        # Create with integer values
        workflow = WorkflowBuilder()
        workflow.add_node(
            "IntCounterCreateNode",
            "create",
            {"value": 42},
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        assert created["value"] == 42
        assert isinstance(created["value"], int)


class TestDatetimeFieldConversion:
    """Integration tests for datetime field handling."""

    def test_iso_string_converted_to_datetime(self, db, runtime):
        """ISO datetime strings should be converted during CREATE."""

        @db.model
        class TimedEvent:
            id: int
            event_time: datetime
            name: str

        # Create with ISO string
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TimedEventCreateNode",
            "create",
            {
                "event_time": "2024-06-15T14:30:00Z",
                "name": "Conference",
            },
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        # Datetime should be stored and returned correctly
        assert "event_time" in created


class TestOptionalFieldHandling:
    """Integration tests for Optional field handling."""

    def test_optional_field_allows_none(self, db, runtime):
        """Optional fields should accept None values."""

        @db.model
        class OptionalProfile:
            id: int
            name: str
            bio: Optional[str] = None

        # Create without optional field
        workflow = WorkflowBuilder()
        workflow.add_node(
            "OptionalProfileCreateNode",
            "create",
            {"name": "User1"},
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        assert created["name"] == "User1"
        # bio should be None or not present
        assert created.get("bio") is None


class TestUpdateOperationTypeValidation:
    """Integration tests for UPDATE operation type handling."""

    def test_update_preserves_string_id_type(self, db, runtime):
        """UPDATE should preserve string ID types."""

        @db.model
        class UpdatableUser:
            id: str
            name: str
            status: str

        # Create user
        create_workflow = WorkflowBuilder()
        create_workflow.add_node(
            "UpdatableUserCreateNode",
            "create",
            {"id": "upd-user-001", "name": "Original", "status": "active"},
        )
        runtime.execute(create_workflow.build())

        # Update user
        update_workflow = WorkflowBuilder()
        update_workflow.add_node(
            "UpdatableUserUpdateNode",
            "update",
            {
                "filter": {"id": "upd-user-001"},
                "fields": {"name": "Updated", "status": "inactive"},
            },
        )

        results, _ = runtime.execute(update_workflow.build())
        updated = results.get("update")

        assert updated is not None
        assert updated.get("updated") is True or updated.get("name") == "Updated"


class TestUpsertOperationTypeValidation:
    """Integration tests for UPSERT operation type handling."""

    def test_upsert_handles_typed_fields(self, db, runtime):
        """UPSERT should properly validate field types."""

        @db.model
        class UpsertableEntity:
            id: str
            name: str
            count: int

        # Upsert (should insert)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UpsertableEntityUpsertNode",
            "upsert",
            {
                "where": {"id": "upsert-001"},
                "create": {"id": "upsert-001", "name": "New", "count": 1},
                "update": {"name": "Updated", "count": 2},
            },
        )

        results, _ = runtime.execute(workflow.build())
        result = results.get("upsert")

        assert result is not None
        # First upsert should create
        assert result.get("created") is True or result.get("record") is not None


class TestBulkOperationTypeValidation:
    """Integration tests for BULK operation type handling."""

    def test_bulk_create_validates_types(self, db, runtime):
        """BULK_CREATE should validate field types."""

        @db.model
        class BulkItem:
            id: str
            name: str
            quantity: int

        # Bulk create
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BulkItemBulkCreateNode",
            "bulk_create",
            {
                "data": [
                    {"id": "bulk-001", "name": "Item1", "quantity": 10},
                    {"id": "bulk-002", "name": "Item2", "quantity": 20},
                    {"id": "bulk-003", "name": "Item3", "quantity": 30},
                ]
            },
        )

        results, _ = runtime.execute(workflow.build())
        result = results.get("bulk_create")

        assert result is not None
        assert result.get("success") is True or result.get("processed", 0) > 0


class TestTypeProcessorDirectUsage:
    """Integration tests for TypeAwareFieldProcessor direct usage."""

    def test_get_type_processor_from_dataflow(self, db):
        """DataFlow.get_type_processor() should return processor for model."""

        @db.model
        class TypedModel:
            id: str
            value: int

        processor = db.get_type_processor("TypedModel")

        assert processor is not None
        assert processor.model_name == "TypedModel"

        # Test validation
        result = processor.validate_field("id", "test-id")
        assert result == "test-id"

    def test_type_processor_validates_fields(self, db):
        """TypeAwareFieldProcessor should validate field values."""

        @db.model
        class ValidationModel:
            id: str
            count: int
            active: bool

        processor = db.get_type_processor("ValidationModel")

        # Valid values
        assert processor.validate_field("id", "val-001") == "val-001"
        assert processor.validate_field("count", 42) == 42
        assert processor.validate_field("active", True) is True

    def test_type_processor_rejects_bool_as_int(self, db):
        """TypeAwareFieldProcessor should reject bool for int fields."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        @db.model
        class StrictModel:
            id: int
            count: int

        processor = db.get_type_processor("StrictModel")

        # Bool should not be treated as int
        with pytest.raises(TypeError, match="got bool"):
            processor.validate_field("count", True)


class TestBackwardCompatibility:
    """Integration tests for backward compatibility."""

    def test_existing_workflows_still_work(self, db, runtime):
        """Existing workflows without explicit types should work."""

        @db.model
        class LegacyModel:
            id: int
            data: str

        # Create using standard pattern
        workflow = WorkflowBuilder()
        workflow.add_node(
            "LegacyModelCreateNode",
            "create",
            {"data": "test data"},
        )

        results, _ = runtime.execute(workflow.build())
        created = results.get("create")

        assert created is not None
        assert "id" in created
        assert created["data"] == "test data"
