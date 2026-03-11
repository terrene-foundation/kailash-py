"""Unit tests for TypeAwareFieldProcessor.

Tests type-aware field processing for DataFlow model operations.
Ensures all model field types are preserved and validated correctly.

Related: TODO-153 - Type-Aware Model Processing
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Union
from uuid import UUID

import pytest


class TestTypeAwareFieldProcessorInit:
    """Tests for TypeAwareFieldProcessor initialization."""

    def test_init_with_empty_fields(self):
        """Should initialize with empty model fields."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        processor = TypeAwareFieldProcessor({}, "TestModel")
        assert processor.model_fields == {}
        assert processor.model_name == "TestModel"

    def test_init_with_model_fields(self):
        """Should initialize with model field metadata."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": str, "required": True},
            "name": {"type": str, "required": True},
            "age": {"type": int, "required": False, "default": 0},
        }
        processor = TypeAwareFieldProcessor(fields, "User")
        assert processor.model_fields == fields
        assert processor.model_name == "User"

    def test_init_resolves_optional_types(self):
        """Should pre-resolve Optional types during init."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "email": {"type": Optional[str], "required": False},
            "age": {"type": Optional[int], "required": False},
        }
        processor = TypeAwareFieldProcessor(fields, "User")
        # Internal _resolved_types should have unwrapped the Optional
        assert processor._resolved_types["email"] == str
        assert processor._resolved_types["age"] == int


class TestStringIDPreservation:
    """Tests for string ID type preservation (critical for TODO-149 compliance)."""

    def test_string_id_preserved_as_string(self):
        """String IDs should remain strings, not converted to int."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "User")

        result = processor.validate_field("id", "user-abc123")
        assert result == "user-abc123"
        assert isinstance(result, str)

    def test_string_id_not_converted_to_int(self):
        """String ID that looks like number should stay as string."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        # Even if the string looks numeric, it should stay as string
        result = processor.validate_field("id", "12345")
        assert result == "12345"
        assert isinstance(result, str)

    def test_string_foreign_key_preserved(self):
        """String foreign keys should be preserved as strings."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"user_id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        result = processor.validate_field("user_id", "user-xyz789")
        assert result == "user-xyz789"
        assert isinstance(result, str)


class TestUUIDHandling:
    """Tests for UUID field handling."""

    def test_uuid_preserved_as_uuid(self):
        """UUID values should be preserved as UUID objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = processor.validate_field("id", test_uuid)
        assert result == test_uuid
        assert isinstance(result, UUID)

    def test_uuid_string_converted_to_uuid(self):
        """Valid UUID strings should be converted to UUID objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        result = processor.validate_field("id", "12345678-1234-5678-1234-567812345678")
        assert isinstance(result, UUID)
        assert str(result) == "12345678-1234-5678-1234-567812345678"

    def test_invalid_uuid_string_raises_error(self):
        """Invalid UUID strings should raise TypeError."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        with pytest.raises(TypeError, match="expected valid UUID string"):
            processor.validate_field("id", "not-a-uuid")


class TestIntegerHandling:
    """Tests for integer field handling."""

    def test_int_id_preserved_as_int(self):
        """Integer IDs should be preserved as integers."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "User")

        result = processor.validate_field("id", 12345)
        assert result == 12345
        assert isinstance(result, int)

    def test_bool_is_not_int(self):
        """Boolean values should NOT be treated as integers."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"count": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Stats")

        with pytest.raises(TypeError, match="got bool"):
            processor.validate_field("count", True)

    def test_float_whole_number_converts_to_int(self):
        """Float with .0 should convert to int."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"quantity": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        result = processor.validate_field("quantity", 5.0)
        assert result == 5
        assert isinstance(result, int)

    def test_float_with_decimal_raises_error(self):
        """Float with decimal part should NOT convert to int."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"quantity": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        with pytest.raises(TypeError, match="decimal part"):
            processor.validate_field("quantity", 5.5)


class TestDatetimeHandling:
    """Tests for datetime field handling."""

    def test_datetime_preserved_as_datetime(self):
        """Datetime values should be preserved as datetime objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"created_at": {"type": datetime, "required": False}}
        processor = TypeAwareFieldProcessor(fields, "User")

        now = datetime.now()
        result = processor.validate_field("created_at", now)
        assert result == now
        assert isinstance(result, datetime)

    def test_iso_string_converted_to_datetime(self):
        """ISO 8601 datetime strings should be converted to datetime."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"scheduled_at": {"type": datetime, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Task")

        result = processor.validate_field("scheduled_at", "2024-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_iso_string_with_z_converted(self):
        """ISO datetime with Z timezone should be converted correctly."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"created_at": {"type": datetime, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Event")

        result = processor.validate_field("created_at", "2024-06-20T14:00:00Z")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_invalid_datetime_string_raises_error(self):
        """Invalid datetime strings should raise TypeError."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"event_date": {"type": datetime, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Event")

        with pytest.raises(TypeError, match="ISO datetime string"):
            processor.validate_field("event_date", "not-a-date")


class TestDateHandling:
    """Tests for date field handling."""

    def test_date_preserved_as_date(self):
        """Date values should be preserved as date objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"birth_date": {"type": date, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Person")

        today = date.today()
        result = processor.validate_field("birth_date", today)
        assert result == today
        assert isinstance(result, date)

    def test_iso_date_string_converted(self):
        """ISO date strings should be converted to date objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"due_date": {"type": date, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Invoice")

        result = processor.validate_field("due_date", "2024-12-31")
        assert isinstance(result, date)
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 31

    def test_invalid_date_string_raises_error(self):
        """Invalid date strings should raise TypeError."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"due_date": {"type": date, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Task")

        with pytest.raises(TypeError, match="ISO date string"):
            processor.validate_field("due_date", "31/12/2024")  # Wrong format


class TestDecimalHandling:
    """Tests for Decimal field handling."""

    def test_decimal_preserved_as_decimal(self):
        """Decimal values should be preserved as Decimal objects."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"price": {"type": Decimal, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Product")

        price = Decimal("19.99")
        result = processor.validate_field("price", price)
        assert result == price
        assert isinstance(result, Decimal)

    def test_string_converted_to_decimal(self):
        """String numbers should be converted to Decimal."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"amount": {"type": Decimal, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Transaction")

        result = processor.validate_field("amount", "123.45")
        assert result == Decimal("123.45")
        assert isinstance(result, Decimal)

    def test_int_converted_to_decimal(self):
        """Integer values should be converted to Decimal."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"total": {"type": Decimal, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Order")

        result = processor.validate_field("total", 100)
        assert result == Decimal("100")
        assert isinstance(result, Decimal)

    def test_float_converted_to_decimal(self):
        """Float values should be converted to Decimal (via string)."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"rate": {"type": Decimal, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Invoice")

        result = processor.validate_field("rate", 0.15)
        assert isinstance(result, Decimal)


class TestNoneValueHandling:
    """Tests for None/null value handling."""

    def test_none_value_allowed(self):
        """None values should be allowed and returned as None."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"email": {"type": str, "required": False}}
        processor = TypeAwareFieldProcessor(fields, "User")

        result = processor.validate_field("email", None)
        assert result is None

    def test_none_for_optional_field(self):
        """None should be valid for Optional[T] fields."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"nickname": {"type": Optional[str], "required": False}}
        processor = TypeAwareFieldProcessor(fields, "User")

        result = processor.validate_field("nickname", None)
        assert result is None


class TestUnknownFieldHandling:
    """Tests for unknown/untyped field handling."""

    def test_unknown_field_passes_through(self):
        """Fields not in model_fields should pass through unchanged."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"name": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "User")

        # Field not defined in model_fields
        result = processor.validate_field("extra_data", {"key": "value"})
        assert result == {"key": "value"}

    def test_field_without_type_passes_through(self):
        """Fields without type annotation should pass through."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"mystery": {"required": False}}  # No 'type' key
        processor = TypeAwareFieldProcessor(fields, "Data")

        result = processor.validate_field("mystery", [1, 2, 3])
        assert result == [1, 2, 3]


class TestOptionalTypeUnwrapping:
    """Tests for Optional[T] type unwrapping."""

    def test_optional_string_unwrapped(self):
        """Optional[str] should accept string values."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"bio": {"type": Optional[str], "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Profile")

        result = processor.validate_field("bio", "Hello world")
        assert result == "Hello world"
        assert isinstance(result, str)

    def test_optional_int_unwrapped(self):
        """Optional[int] should accept integer values."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"score": {"type": Optional[int], "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Game")

        result = processor.validate_field("score", 100)
        assert result == 100
        assert isinstance(result, int)


class TestStrictModeValidation:
    """Tests for strict mode validation (no automatic conversions)."""

    def test_strict_mode_rejects_uuid_string(self):
        """Strict mode should not convert UUID strings."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": UUID, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        with pytest.raises(TypeError):
            processor.validate_field(
                "id", "12345678-1234-5678-1234-567812345678", strict=True
            )

    def test_strict_mode_rejects_datetime_string(self):
        """Strict mode should not convert datetime strings."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"created_at": {"type": datetime, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Record")

        with pytest.raises(TypeError):
            processor.validate_field("created_at", "2024-01-01T00:00:00", strict=True)

    def test_strict_mode_accepts_correct_types(self):
        """Strict mode should accept values of correct type."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": UUID, "required": True},
            "name": {"type": str, "required": True},
        }
        processor = TypeAwareFieldProcessor(fields, "Entity")

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = processor.validate_field("id", test_uuid, strict=True)
        assert result == test_uuid


class TestProcessRecord:
    """Tests for process_record method (single record processing)."""

    def test_process_record_validates_all_fields(self):
        """Should validate all fields in a record."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": str, "required": True},
            "name": {"type": str, "required": True},
            "count": {"type": int, "required": True},
        }
        processor = TypeAwareFieldProcessor(fields, "Item")

        record = {"id": "item-001", "name": "Widget", "count": 10}
        result = processor.process_record(record, operation="create")

        assert result == {"id": "item-001", "name": "Widget", "count": 10}

    def test_process_record_skips_auto_managed_fields(self):
        """Should skip created_at and updated_at by default."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": str, "required": True},
            "created_at": {"type": datetime, "required": False},
            "updated_at": {"type": datetime, "required": False},
        }
        processor = TypeAwareFieldProcessor(fields, "Entity")

        record = {
            "id": "entity-001",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
        }
        result = processor.process_record(record, operation="create")

        # Auto-managed fields should be skipped
        assert "created_at" not in result
        assert "updated_at" not in result
        assert result == {"id": "entity-001"}

    def test_process_record_custom_skip_fields(self):
        """Should respect custom skip_fields parameter."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": str, "required": True},
            "internal_field": {"type": str, "required": False},
        }
        processor = TypeAwareFieldProcessor(fields, "Data")

        record = {"id": "data-001", "internal_field": "secret"}
        result = processor.process_record(
            record, operation="create", skip_fields={"internal_field"}
        )

        assert result == {"id": "data-001"}

    def test_process_record_raises_on_type_error(self):
        """Should raise TypeError with context on type mismatch."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Counter")

        with pytest.raises(TypeError, match="create operation"):
            processor.process_record({"id": True}, operation="create")


class TestProcessRecords:
    """Tests for process_records method (bulk record processing)."""

    def test_process_records_validates_all_records(self):
        """Should validate all records in a list."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {
            "id": {"type": str, "required": True},
            "value": {"type": int, "required": True},
        }
        processor = TypeAwareFieldProcessor(fields, "Item")

        records = [
            {"id": "item-001", "value": 10},
            {"id": "item-002", "value": 20},
            {"id": "item-003", "value": 30},
        ]
        result = processor.process_records(records, operation="bulk_create")

        assert len(result) == 3
        assert result[0] == {"id": "item-001", "value": 10}
        assert result[1] == {"id": "item-002", "value": 20}
        assert result[2] == {"id": "item-003", "value": 30}

    def test_process_records_error_includes_index(self):
        """Should include record index in error message."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"count": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Stats")

        records = [
            {"count": 1},
            {"count": 2},
            {"count": True},  # Invalid - bool is not int
        ]

        with pytest.raises(TypeError, match="record 2"):
            processor.process_records(records, operation="bulk_create")


class TestForeignKeyValidation:
    """Tests for foreign key type validation."""

    def test_fk_type_matches_pk_type(self):
        """FK value type should match referenced model's PK type."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        user_fields = {"id": {"type": str, "required": True}}
        order_fields = {"user_id": {"type": str, "required": True}}

        processor = TypeAwareFieldProcessor(order_fields, "Order")
        result = processor.validate_foreign_key(
            "user_id",
            "user-123",
            referenced_model_fields=user_fields,
            referenced_model_name="User",
        )
        assert result == "user-123"

    def test_fk_type_mismatch_raises_error(self):
        """FK type mismatch should raise TypeError."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        user_fields = {"id": {"type": str, "required": True}}
        order_fields = {"user_id": {"type": int, "required": True}}  # Mismatch!

        processor = TypeAwareFieldProcessor(order_fields, "Order")

        with pytest.raises(TypeError, match="Foreign key"):
            processor.validate_foreign_key(
                "user_id",
                123,  # int instead of str
                referenced_model_fields=user_fields,
                referenced_model_name="User",
            )


class TestErrorMessages:
    """Tests for error message quality and context."""

    def test_error_includes_model_name(self):
        """Error messages should include model name."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"status": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "TaskQueue")

        with pytest.raises(TypeError) as exc_info:
            processor.validate_field("status", 123, strict=True)

        assert "TaskQueue" in str(exc_info.value)

    def test_error_includes_field_name(self):
        """Error messages should include field name."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"priority": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Task")

        with pytest.raises(TypeError) as exc_info:
            processor.validate_field("priority", True)

        assert "priority" in str(exc_info.value)

    def test_error_includes_expected_type(self):
        """Error messages should include expected type."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"email": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "User")

        with pytest.raises(TypeError) as exc_info:
            processor.validate_field("email", 123, strict=True)

        # Should mention "str" as expected type
        error_msg = str(exc_info.value).lower()
        assert "str" in error_msg

    def test_error_includes_actual_type(self):
        """Error messages should include actual value type."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"count": {"type": int, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Stats")

        with pytest.raises(TypeError) as exc_info:
            processor.validate_field("count", True)

        assert "bool" in str(exc_info.value).lower()


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    def test_nonstrict_mode_passes_through_unknown_types(self):
        """Non-strict mode should pass through mismatched types with logging."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        # Define a custom class that's not in the standard conversion list
        class CustomType:
            pass

        fields = {"data": {"type": CustomType, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Container")

        # In non-strict mode, unknown type mismatches should pass through
        result = processor.validate_field("data", "some string")
        assert result == "some string"

    def test_empty_record_returns_empty_dict(self):
        """Empty record should return empty dict."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        result = processor.process_record({}, operation="create")
        assert result == {}

    def test_empty_records_list_returns_empty_list(self):
        """Empty records list should return empty list."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"id": {"type": str, "required": True}}
        processor = TypeAwareFieldProcessor(fields, "Entity")

        result = processor.process_records([], operation="bulk_create")
        assert result == []


class TestComplexTypeAnnotations:
    """Tests for complex type annotations (List, Dict, Union)."""

    def test_list_type_preserved(self):
        """List fields should be preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"tags": {"type": list, "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Article")

        result = processor.validate_field("tags", ["python", "dataflow"])
        assert result == ["python", "dataflow"]
        assert isinstance(result, list)

    def test_dict_type_preserved(self):
        """Dict fields should be preserved."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"metadata": {"type": dict, "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Document")

        result = processor.validate_field("metadata", {"key": "value"})
        assert result == {"key": "value"}
        assert isinstance(result, dict)

    def test_union_type_with_none_resolved(self):
        """Union[T, None] (Optional[T]) should resolve to T."""
        from dataflow.core.type_processor import TypeAwareFieldProcessor

        fields = {"notes": {"type": Union[str, None], "required": False}}
        processor = TypeAwareFieldProcessor(fields, "Task")

        result = processor.validate_field("notes", "Important task")
        assert result == "Important task"
        assert isinstance(result, str)
