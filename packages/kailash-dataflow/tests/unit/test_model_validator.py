"""
Unit tests for model_validator.py (Type Hint-Based Validation)

Tests the 4 validation layers for DataFlow strict mode:
1. Primary Key Validation (STRICT_MODEL_001-004)
2. Auto-Field Conflict Detection (STRICT_MODEL_010-012)
3. Reserved Field Validation (STRICT_MODEL_020-022)
4. Field Type Validation (STRICT_MODEL_030-032)

This file tests the type hint-based validation system (distinct from
SQLAlchemy-based validation in test_strict_mode_model_validation.py).
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Dict, List, Optional

import pytest
from dataflow.validation.model_validator import (
    ValidationResult,
    validate_auto_field_conflicts,
    validate_field_types,
    validate_model,
    validate_primary_key,
    validate_reserved_fields,
)
from dataflow.validation.validators import ValidationError

# ============================================================================
# Test Models
# ============================================================================


# Valid Models
@dataclass
class ValidModel:
    """Valid model with all required fields."""

    id: str
    name: str
    value: int


@dataclass
class ValidModelWithOptional:
    """Valid model with optional fields."""

    id: str
    name: str
    age: Optional[int]


@dataclass
class ValidModelAllTypes:
    """Valid model with all supported types."""

    id: str
    text: str
    number: int
    decimal: float
    flag: bool
    data: dict
    items: list
    timestamp: datetime
    birth_date: date
    alarm_time: time


# Invalid Models - Primary Key
@dataclass
class ModelMissingId:
    """Model without id field."""

    name: str
    value: int


@dataclass
class ModelWrongIdType:
    """Model with non-str id field."""

    id: int
    name: str


@dataclass
class ModelOptionalId:
    """Model with optional id field."""

    id: Optional[str]
    name: str


class ModelNoAnnotations:
    """Model without type annotations."""

    def __init__(self):
        self.id = "test"
        self.name = "test"


# Invalid Models - Auto-Field Conflicts
@dataclass
class ModelWithCreatedAt:
    """Model with manual created_at field."""

    id: str
    name: str
    created_at: datetime


@dataclass
class ModelWithUpdatedAt:
    """Model with manual updated_at field."""

    id: str
    name: str
    updated_at: datetime


@dataclass
class ModelWithBothAutoFields:
    """Model with both auto-managed fields."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime


# Invalid Models - Reserved Fields
@dataclass
class ModelWithReservedField:
    """Model with reserved field name."""

    id: str
    dataflow_instance: str


@dataclass
class ModelWithDataflowPrefix:
    """Model with _dataflow_ prefix."""

    id: str
    _dataflow_custom: str


@dataclass
class ModelWithDunderMethod:
    """Model with dunder method pattern."""

    id: str
    __custom__: str


# Invalid Models - Field Types
@dataclass
class ModelWithUnsupportedType:
    """Model with unsupported type."""

    id: str
    data: set  # set is not supported


@dataclass
class ModelWithCustomClass:
    """Model with custom class type."""

    id: str

    class CustomType:
        pass

    custom: CustomType


# Mock Config for Auto-Field Tests
class MockStrictModeConfig:
    """Mock strict mode configuration."""

    def __init__(self, auto_fields_enabled: bool = True):
        self.auto_fields_enabled = auto_fields_enabled


# ============================================================================
# Test Suite: Primary Key Validation (STRICT_MODEL_001-004)
# ============================================================================


@pytest.mark.unit
class TestPrimaryKeyValidation:
    """Test primary key validation rules."""

    def test_valid_model_with_id_str(self):
        """Test model with valid id: str field passes validation."""
        result = validate_primary_key(ValidModel)

        assert result.success is True
        assert result.error_code is None
        assert result.message is None

    def test_missing_id_field(self):
        """Test model without id field fails with STRICT_MODEL_001."""
        result = validate_primary_key(ModelMissingId)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_001"
        assert "missing required 'id' field" in result.message.lower()
        assert "ModelMissingId" in result.message
        assert "description" in result.solution
        assert "id: str" in result.solution["code_example"]

    def test_wrong_id_type(self):
        """Test model with non-str id field fails with STRICT_MODEL_002."""
        result = validate_primary_key(ModelWrongIdType)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_002"
        assert "field 'id' must be type 'str'" in result.message.lower()
        assert "ModelWrongIdType" in result.message
        assert "id: str" in result.solution["code_example"]

    def test_optional_id_field(self):
        """Test model with Optional[str] id fails with STRICT_MODEL_003."""
        result = validate_primary_key(ModelOptionalId)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_003"
        assert "field 'id' cannot be optional" in result.message.lower()
        assert "ModelOptionalId" in result.message
        assert "id: str" in result.solution["code_example"]
        assert "Optional" in result.solution["description"]

    def test_no_type_annotations(self):
        """Test model without type annotations fails with STRICT_MODEL_001 (missing id)."""
        result = validate_primary_key(ModelNoAnnotations)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_001"
        assert "missing required 'id' field" in result.message.lower()
        assert "ModelNoAnnotations" in result.message
        assert "description" in result.solution


# ============================================================================
# Test Suite: Auto-Field Conflict Detection (STRICT_MODEL_010-012)
# ============================================================================


@pytest.mark.unit
class TestAutoFieldConflicts:
    """Test auto-field conflict detection."""

    def test_model_with_created_at_conflict(self):
        """Test model with created_at field fails with STRICT_MODEL_010."""
        result = validate_auto_field_conflicts(ModelWithCreatedAt)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_010"
        assert "created_at" in result.message.lower()
        assert "auto-managed by dataflow" in result.message.lower()
        assert "ModelWithCreatedAt" in result.message
        assert "remove" in result.solution["description"].lower()

    def test_model_with_updated_at_conflict(self):
        """Test model with updated_at field fails with STRICT_MODEL_011."""
        result = validate_auto_field_conflicts(ModelWithUpdatedAt)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_011"
        assert "updated_at" in result.message.lower()
        assert "auto-managed by dataflow" in result.message.lower()
        assert "ModelWithUpdatedAt" in result.message

    def test_model_with_both_auto_fields(self):
        """Test model with both auto fields fails with STRICT_MODEL_012."""
        result = validate_auto_field_conflicts(ModelWithBothAutoFields)

        assert result.success is False
        assert result.error_code == "STRICT_MODEL_012"
        assert "created_at" in result.message.lower()
        assert "updated_at" in result.message.lower()
        assert "ModelWithBothAutoFields" in result.message

    def test_auto_fields_disabled_allows_manual_definition(self):
        """Test models can define auto fields when feature disabled."""
        config = MockStrictModeConfig(auto_fields_enabled=False)
        result = validate_auto_field_conflicts(ModelWithBothAutoFields, config)

        assert result.success is True
        assert result.error_code is None

    def test_valid_model_no_auto_fields(self):
        """Test valid model without auto fields passes validation."""
        result = validate_auto_field_conflicts(ValidModel)

        assert result.success is True
        assert result.error_code is None


# ============================================================================
# Test Suite: Reserved Field Validation (STRICT_MODEL_020-022)
# ============================================================================


@pytest.mark.unit
class TestReservedFields:
    """Test reserved field name validation."""

    def test_reserved_field_name(self):
        """Test model with reserved field fails with STRICT_MODEL_020."""
        results = validate_reserved_fields(ModelWithReservedField)

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_020"
        assert "dataflow_instance" in result.message.lower()
        assert "reserved by dataflow" in result.message.lower()
        assert "ModelWithReservedField" in result.message
        assert "rename" in result.solution["description"].lower()

    def test_dataflow_prefix_field(self):
        """Test model with _dataflow_ prefix fails with STRICT_MODEL_021."""
        results = validate_reserved_fields(ModelWithDataflowPrefix)

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_021"
        assert "_dataflow_custom" in result.message
        assert "dataflow internal prefix" in result.message.lower()
        assert "ModelWithDataflowPrefix" in result.message

    def test_dunder_method_field(self):
        """Test model with dunder method pattern fails with STRICT_MODEL_022."""
        results = validate_reserved_fields(ModelWithDunderMethod)

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_022"
        assert "__custom__" in result.message
        assert "dunder method pattern" in result.message.lower()
        assert "ModelWithDunderMethod" in result.message

    def test_valid_model_no_reserved_fields(self):
        """Test valid model with no reserved fields passes validation."""
        results = validate_reserved_fields(ValidModel)

        assert len(results) == 1
        result = results[0]
        assert result.success is True
        assert result.error_code is None

    def test_multiple_reserved_fields(self):
        """Test model with multiple reserved fields returns multiple errors."""

        @dataclass
        class ModelMultipleReserved:
            id: str
            dataflow_instance: str
            _dataflow_custom: str
            __dunder__: str

        results = validate_reserved_fields(ModelMultipleReserved)

        # Should have 3 errors (one for each reserved field)
        assert len(results) == 3
        error_codes = [r.error_code for r in results]
        assert "STRICT_MODEL_020" in error_codes
        assert "STRICT_MODEL_021" in error_codes
        assert "STRICT_MODEL_022" in error_codes


# ============================================================================
# Test Suite: Field Type Validation (STRICT_MODEL_030-032)
# ============================================================================


@pytest.mark.unit
class TestFieldTypes:
    """Test field type validation."""

    def test_all_supported_types(self):
        """Test model with all supported types passes validation."""
        results = validate_field_types(ValidModelAllTypes)

        assert len(results) == 1
        result = results[0]
        assert result.success is True
        assert result.error_code is None

    def test_unsupported_type(self):
        """Test model with unsupported type fails with STRICT_MODEL_030."""
        results = validate_field_types(ModelWithUnsupportedType)

        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_030"
        assert "data" in result.message
        assert "unsupported" in result.message.lower()
        assert "use one of" in result.solution["description"].lower()

    def test_optional_supported_type(self):
        """Test model with Optional[supported_type] passes validation."""
        results = validate_field_types(ValidModelWithOptional)

        assert len(results) == 1
        result = results[0]
        assert result.success is True
        assert result.error_code is None

    def test_custom_class_type(self):
        """Test model with custom class type fails with STRICT_MODEL_030."""
        results = validate_field_types(ModelWithCustomClass)

        # Should have at least one error for custom type
        assert len(results) >= 1
        # Find the error for 'custom' field
        custom_errors = [
            r for r in results if not r.success and "custom" in r.message.lower()
        ]
        assert len(custom_errors) == 1
        result = custom_errors[0]
        assert result.error_code == "STRICT_MODEL_030"
        assert "unsupported" in result.message.lower()

    def test_auto_fields_skipped_in_type_validation(self):
        """Test that created_at/updated_at are skipped during type validation."""

        # Create model with auto fields but with unusual types
        # (they should be skipped so no error)
        @dataclass
        class ModelAutoFieldsSkipped:
            id: str
            name: str
            created_at: str  # Wrong type but should be skipped
            updated_at: str  # Wrong type but should be skipped

        results = validate_field_types(ModelAutoFieldsSkipped)

        # Should pass because auto fields are skipped
        assert len(results) == 1
        result = results[0]
        assert result.success is True


# ============================================================================
# Test Suite: Main Validation Entry Point
# ============================================================================


@pytest.mark.unit
class TestMainValidation:
    """Test main validate_model() entry point."""

    def test_valid_model_no_errors(self):
        """Test valid model returns empty error list."""
        errors = validate_model(ValidModel)

        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_invalid_model_returns_structured_errors(self):
        """Test invalid model returns structured ValidationError objects."""
        errors = validate_model(ModelMissingId)

        assert len(errors) > 0
        for error in errors:
            assert isinstance(error, ValidationError)
            assert hasattr(error, "error_code")
            assert hasattr(error, "category")
            assert hasattr(error, "severity")
            assert hasattr(error, "message")
            assert hasattr(error, "context")
            assert hasattr(error, "solution")

    def test_multiple_validation_errors(self):
        """Test model with multiple issues returns multiple errors."""

        @dataclass
        class ModelMultipleIssues:
            name: str  # Missing id
            created_at: datetime  # Auto-field conflict
            dataflow_instance: str  # Reserved field
            data: set  # Unsupported type

        errors = validate_model(ModelMultipleIssues)

        # Should have at least 4 errors (one from each layer)
        assert len(errors) >= 4
        error_codes = [e.error_code for e in errors]
        # Check we got errors from each validation layer
        assert any(
            code.startswith("STRICT_MODEL_00") for code in error_codes
        )  # Primary key
        assert any(
            code.startswith("STRICT_MODEL_01") for code in error_codes
        )  # Auto-field
        assert any(
            code.startswith("STRICT_MODEL_02") for code in error_codes
        )  # Reserved
        assert any(
            code.startswith("STRICT_MODEL_03") for code in error_codes
        )  # Field type

    def test_validation_error_structure(self):
        """Test ValidationError has correct structure."""
        errors = validate_model(ModelMissingId)

        assert len(errors) > 0
        error = errors[0]

        # Check all required fields
        assert error.error_code == "STRICT_MODEL_001"
        assert error.category == "MODEL_VALIDATION"
        assert error.severity == "ERROR"
        assert isinstance(error.message, str)
        assert len(error.message) > 0
        assert isinstance(error.context, dict)
        assert isinstance(error.solution, dict)

        # Check solution structure
        assert "description" in error.solution
        assert "code_example" in error.solution

    def test_config_passed_to_validators(self):
        """Test config is properly passed to auto-field validator."""
        config = MockStrictModeConfig(auto_fields_enabled=False)
        errors = validate_model(ModelWithBothAutoFields, config)

        # Should only fail on missing id (not auto-field conflicts)
        assert len(errors) == 0  # Model has id: str, so valid when auto_fields disabled

    def test_validation_order(self):
        """Test validators run in correct order."""

        # Create model that fails all validation layers
        @dataclass
        class ModelFailsAll:
            name: str  # Missing id (layer 1)
            created_at: datetime  # Auto-field (layer 2)
            _dataflow_test: str  # Reserved (layer 3)
            data: set  # Unsupported type (layer 4)

        errors = validate_model(ModelFailsAll)

        # Should have errors from all layers
        assert len(errors) >= 4

        # Verify error order matches validation layer order
        error_codes = [e.error_code for e in errors]
        pk_idx = next(
            i
            for i, code in enumerate(error_codes)
            if code.startswith("STRICT_MODEL_00")
        )
        auto_idx = next(
            i
            for i, code in enumerate(error_codes)
            if code.startswith("STRICT_MODEL_01")
        )
        reserved_idx = next(
            i
            for i, code in enumerate(error_codes)
            if code.startswith("STRICT_MODEL_02")
        )
        type_idx = next(
            i
            for i, code in enumerate(error_codes)
            if code.startswith("STRICT_MODEL_03")
        )

        # Errors should appear in layer order
        assert pk_idx < auto_idx < reserved_idx < type_idx


# ============================================================================
# Test Suite: Edge Cases and Integration
# ============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and integration scenarios."""

    def test_empty_model(self):
        """Test empty model without any fields."""

        @dataclass
        class EmptyModel:
            pass

        result = validate_primary_key(EmptyModel)
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_001"

    def test_model_with_only_id(self):
        """Test model with only id field is valid."""

        @dataclass
        class MinimalModel:
            id: str

        errors = validate_model(MinimalModel)
        assert len(errors) == 0

    def test_complex_optional_types(self):
        """Test models with complex Optional types are rejected."""

        @dataclass
        class ComplexOptionalModel:
            id: str
            data: Optional[Dict[str, List[int]]]
            items: Optional[List[str]]

        results = validate_field_types(ComplexOptionalModel)
        # Complex nested generics are not supported - should have at least one error
        assert len(results) >= 1
        # The 'data' field should fail (nested Dict[str, List[int]])
        data_errors = [
            r for r in results if not r.success and "data" in r.message.lower()
        ]
        assert len(data_errors) >= 1

    def test_nested_generic_types(self):
        """Test models with nested generic types are rejected."""

        @dataclass
        class NestedGenericModel:
            id: str
            nested: Dict[str, List[int]]

        results = validate_field_types(NestedGenericModel)
        # Complex nested generics are not supported - should have at least one error
        assert len(results) >= 1
        # The 'nested' field should fail (nested Dict[str, List[int]])
        nested_errors = [
            r for r in results if not r.success and "nested" in r.message.lower()
        ]
        assert len(nested_errors) >= 1

    def test_validation_result_helper(self):
        """Test ValidationResult helper class."""
        result = ValidationResult(
            success=False,
            error_code="TEST_001",
            message="Test message",
            solution={"suggestion": "Test suggestion"},
            context={"field": "test"},
        )

        assert result.success is False
        assert result.error_code == "TEST_001"
        assert result.message == "Test message"
        assert result.solution["suggestion"] == "Test suggestion"
        assert result.context["field"] == "test"

    def test_validation_result_defaults(self):
        """Test ValidationResult default values."""
        result = ValidationResult(success=True)

        assert result.success is True
        assert result.error_code is None
        assert result.message is None
        assert result.solution == {}
        assert result.context == {}
