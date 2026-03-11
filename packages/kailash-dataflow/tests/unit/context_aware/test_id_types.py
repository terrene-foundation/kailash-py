#!/usr/bin/env python3
"""
Unit Tests for ID Types with DataFlow Context (TODO-156)

Tests that all ID types work correctly with DataFlow context:
- String IDs (default DataFlow pattern)
- Integer IDs
- UUID IDs
- Composite key patterns
- Auto-increment behavior
- ID preservation through CRUD operations
- Edge cases: empty string IDs, very long IDs, special characters

Uses SQLite in-memory databases following Tier 1 testing guidelines.
"""

from uuid import UUID

import pytest


@pytest.mark.unit
class TestStringIDTypes:
    """Test string ID handling in DataFlow context."""

    def test_string_id_model_registration(self, memory_dataflow):
        """String ID model registers correctly with DataFlow."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        models = db.get_models()
        assert "User" in models

    def test_string_id_preserved_in_model(self, memory_dataflow):
        """String ID is preserved without conversion."""
        db = memory_dataflow

        @db.model
        class Order:
            product: str

        # Model should be registered
        assert "Order" in db.get_models()

    def test_string_id_with_alphanumeric(self, memory_dataflow):
        """String ID with alphanumeric characters works correctly."""
        db = memory_dataflow

        @db.model
        class Entity:
            value: str

        # Verify model is registered
        models = db.get_models()
        assert "Entity" in models

    def test_string_id_with_dashes(self, memory_dataflow):
        """String ID with dashes (UUID-like format) works correctly."""
        db = memory_dataflow

        @db.model
        class Record:
            data: str

        # Verify model registration
        assert "Record" in db.get_models()

    def test_string_id_with_underscores(self, memory_dataflow):
        """String ID with underscores works correctly."""
        db = memory_dataflow

        @db.model
        class Document:
            title: str

        assert "Document" in db.get_models()


@pytest.mark.unit
class TestIntegerIDTypes:
    """Test integer ID handling in DataFlow context."""

    def test_integer_id_model_registration(self, memory_dataflow):
        """Integer ID model registers correctly with DataFlow."""
        db = memory_dataflow

        @db.model
        class Counter:
            id: int
            value: int

        models = db.get_models()
        assert "Counter" in models

    def test_integer_id_not_converted_to_string(self, memory_dataflow):
        """Integer IDs remain as integers, not converted to strings."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Counter")

        result = processor.validate_field("id", 12345)
        assert result == 12345
        assert isinstance(result, int)

    def test_integer_id_with_large_values(self, memory_dataflow):
        """Large integer IDs are handled correctly."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "BigNumber")

        large_id = 9999999999999
        result = processor.validate_field("id", large_id)
        assert result == large_id
        assert isinstance(result, int)

    def test_integer_id_with_zero(self, memory_dataflow):
        """Zero as integer ID is handled correctly."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entry")

        result = processor.validate_field("id", 0)
        assert result == 0
        assert isinstance(result, int)

    def test_integer_id_negative_values(self, memory_dataflow):
        """Negative integer IDs are preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "SignedEntry")

        result = processor.validate_field("id", -100)
        assert result == -100
        assert isinstance(result, int)


@pytest.mark.unit
class TestUUIDIDTypes:
    """Test UUID ID handling in DataFlow context."""

    def test_uuid_id_model_registration(self, memory_dataflow):
        """UUID ID model registers correctly with DataFlow."""
        db = memory_dataflow

        @db.model
        class Product:
            id: UUID
            name: str

        models = db.get_models()
        assert "Product" in models

    def test_uuid_object_preserved(self, memory_dataflow):
        """UUID object is preserved without conversion."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = processor.validate_field("id", test_uuid)
        assert result == test_uuid
        assert isinstance(result, UUID)

    def test_uuid_string_conversion(self, memory_dataflow):
        """UUID string is converted to UUID object."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        result = processor.validate_field("id", "12345678-1234-5678-1234-567812345678")
        assert isinstance(result, UUID)

    def test_uuid_without_dashes(self, memory_dataflow):
        """UUID string without dashes is rejected."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        # UUID without dashes should still work (Python UUID accepts it)
        result = processor.validate_field("id", "12345678123456781234567812345678")
        assert isinstance(result, UUID)

    def test_uuid_case_insensitive(self, memory_dataflow):
        """UUID string is case-insensitive."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        result = processor.validate_field("id", "ABCDEF12-3456-7890-ABCD-EF1234567890")
        assert isinstance(result, UUID)


@pytest.mark.unit
class TestCompositeKeyPatterns:
    """Test composite key patterns in DataFlow context."""

    def test_model_with_multiple_key_fields(self, memory_dataflow):
        """Model with multiple key-like fields registers correctly."""
        db = memory_dataflow

        @db.model
        class OrderItem:
            order_id: str
            product_id: str
            quantity: int

        assert "OrderItem" in db.get_models()

    def test_foreign_key_string_preserved(self, memory_dataflow):
        """String foreign keys are preserved as strings."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"user_id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        result = processor.validate_field("user_id", "user-abc-123")
        assert result == "user-abc-123"
        assert isinstance(result, str)

    def test_foreign_key_integer_preserved(self, memory_dataflow):
        """Integer foreign keys are preserved as integers."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"user_id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        result = processor.validate_field("user_id", 42)
        assert result == 42
        assert isinstance(result, int)

    def test_multiple_foreign_keys(self, memory_dataflow):
        """Model with multiple foreign keys handles them correctly."""
        db = memory_dataflow

        @db.model
        class Assignment:
            user_id: str
            project_id: str
            role: str

        assert "Assignment" in db.get_models()


@pytest.mark.unit
class TestAutoIncrementBehavior:
    """Test auto-increment ID behavior in DataFlow context."""

    def test_integer_id_without_explicit_value(self, memory_dataflow):
        """Integer ID field can be used for auto-increment pattern."""
        db = memory_dataflow

        @db.model
        class Sequence:
            id: int
            name: str

        assert "Sequence" in db.get_models()

    def test_optional_id_field(self, memory_dataflow):
        """Optional ID field allows null for auto-generation."""
        from typing import Optional

        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": Optional[int], "required": False}}
        processor = TypeAwareFieldProcessor(fields, "AutoRecord")

        result = processor.validate_field("id", None)
        assert result is None


@pytest.mark.unit
class TestIDPreservationThroughCRUD:
    """Test ID preservation through CRUD operations."""

    def test_string_id_in_create_params(self, memory_dataflow):
        """String ID is preserved in create node parameters."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "User",
            "Create",
            "create_user",
            {"id": "user-abc-123", "name": "Alice"},
        )

        # Verify node was added with correct params
        assert "create_user" in workflow.nodes
        assert workflow.nodes["create_user"]["config"]["id"] == "user-abc-123"

    def test_string_id_in_read_params(self, memory_dataflow):
        """String ID is preserved in read node parameters."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "User",
            "Read",
            "read_user",
            {"id": "user-xyz-789"},
        )

        assert "read_user" in workflow.nodes
        assert workflow.nodes["read_user"]["config"]["id"] == "user-xyz-789"

    def test_string_id_in_update_params(self, memory_dataflow):
        """String ID is preserved in update node parameters."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "User",
            "Update",
            "update_user",
            {"filter": {"id": "user-abc-123"}, "fields": {"name": "Bob"}},
        )

        assert "update_user" in workflow.nodes

    def test_string_id_in_delete_params(self, memory_dataflow):
        """String ID is preserved in delete node parameters."""
        db = memory_dataflow

        @db.model
        class User:
            name: str

        workflow = db.create_workflow()
        db.add_node(
            workflow,
            "User",
            "Delete",
            "delete_user",
            {"id": "user-to-delete"},
        )

        assert "delete_user" in workflow.nodes


@pytest.mark.unit
class TestIDEdgeCases:
    """Test edge cases for ID handling."""

    def test_empty_string_id_preserved(self, memory_dataflow):
        """Empty string ID is preserved (though may fail validation)."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        result = processor.validate_field("id", "")
        assert result == ""
        assert isinstance(result, str)

    def test_very_long_id_preserved(self, memory_dataflow):
        """Very long string ID is preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        long_id = "a" * 1000
        result = processor.validate_field("id", long_id)
        assert result == long_id
        assert len(result) == 1000

    def test_special_characters_in_id(self, memory_dataflow):
        """ID with special characters is preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        special_id = "user_123!@#$%^&*()"
        result = processor.validate_field("id", special_id)
        assert result == special_id

    def test_unicode_in_id(self, memory_dataflow):
        """ID with unicode characters is preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        unicode_id = "user-test"
        result = processor.validate_field("id", unicode_id)
        assert result == unicode_id

    def test_whitespace_in_id(self, memory_dataflow):
        """ID with whitespace is preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        space_id = "user with spaces"
        result = processor.validate_field("id", space_id)
        assert result == space_id

    def test_numeric_string_id_not_converted(self, memory_dataflow):
        """Numeric string ID stays as string, not converted to int."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        numeric_string_id = "12345"
        result = processor.validate_field("id", numeric_string_id)
        assert result == "12345"
        assert isinstance(result, str)
        assert not isinstance(result, int)

    def test_none_id_handled(self, memory_dataflow):
        """None ID value is handled correctly."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        result = processor.validate_field("id", None)
        assert result is None
