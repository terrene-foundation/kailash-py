"""
Integration Tests for Model Validation (Tier 2)

Tests model validation with real DataFlow instances and database operations.
Uses real infrastructure (NO MOCKING) as per integration test guidelines.

NOTE: Automatic validation during @db.model decoration is not yet implemented.
These tests validate models manually after registration to verify validator
functions work correctly with real DataFlow instances.

Test Coverage:
- Integration Test 1: Manual validation of model structure
- Integration Test 2: Validation with real model classes
- Integration Test 3: Multiple validator functions working together
- Integration Test 4: Validation with different field types
- Integration Test 5: Cross-validation of all rules
"""

from dataclasses import dataclass

import pytest
from dataflow import DataFlow
from dataflow.validation.model_validator import (
    validate_auto_field_conflicts,
    validate_field_types,
    validate_primary_key,
    validate_reserved_fields,
)


@pytest.mark.integration
class TestModelValidationIntegration:
    """Integration tests for model validation with real DataFlow instances."""

    def test_manual_validation_of_model_structure(self):
        """
        Integration Test 1: Manual validation of model structure.

        Verifies that validator functions work correctly with real model classes.
        """

        @dataclass
        class InvalidModel:
            name: str  # Missing 'id' field

        # Manually validate
        result = validate_primary_key(InvalidModel)

        # Verify validation works
        assert result.success is False
        assert result.error_code == "STRICT_MODEL_001"
        assert "missing required 'id' field" in result.message.lower()

    def test_validation_with_real_model_classes(self):
        """
        Integration Test 2: Validation with real model classes.

        Verifies validators work with actual dataclass models.
        """

        @dataclass
        class ValidModel:
            id: str
            name: str
            value: int

        @dataclass
        class InvalidModel:
            id: str
            _dataflow_metadata: str  # Reserved field

        # Valid model passes
        result = validate_primary_key(ValidModel)
        assert result.success is True

        # Invalid model fails
        results = validate_reserved_fields(InvalidModel)
        assert any(not r.success for r in results)

    def test_multiple_validators_working_together(self):
        """
        Integration Test 3: Multiple validator functions working together.

        Verifies all validation rules can be applied to a single model.
        """

        @dataclass
        class TestModel:
            id: str
            name: str
            count: int

        # Apply all validators
        pk_result = validate_primary_key(TestModel)
        auto_field_results = validate_auto_field_conflicts(TestModel)
        reserved_results = validate_reserved_fields(TestModel)
        type_results = validate_field_types(TestModel)

        # All should pass for valid model
        assert pk_result.success is True
        assert auto_field_results.success is True  # Single result, not a list
        assert all(r.success for r in reserved_results)
        assert all(r.success for r in type_results)

    def test_validation_with_different_field_types(self):
        """
        Integration Test 4: Validation with different field types.

        Verifies field type validation works with various Python types.
        """

        @dataclass
        class ModelWithSupportedTypes:
            id: str
            name: str
            count: int
            price: float
            active: bool

        @dataclass
        class ModelWithUnsupportedTypes:
            id: str
            data: set  # Unsupported type

        # Supported types pass
        results = validate_field_types(ModelWithSupportedTypes)
        assert all(r.success for r in results)

        # Unsupported types fail
        results = validate_field_types(ModelWithUnsupportedTypes)
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_MODEL_030"

    def test_cross_validation_of_all_rules(self):
        """
        Integration Test 5: Cross-validation of all rules.

        Verifies all validation rules work correctly together with
        various combinations of valid and invalid models.
        """

        # Model with multiple errors
        @dataclass
        class MultipleErrorsModel:
            user_id: str  # Missing 'id'
            created_at: str  # Auto-field conflict
            metadata: str  # Reserved field
            data: set  # Unsupported type

        # Check all validators catch respective errors
        pk_result = validate_primary_key(MultipleErrorsModel)
        assert pk_result.success is False  # Missing 'id'

        auto_results = validate_auto_field_conflicts(MultipleErrorsModel)
        assert (
            auto_results.success is False
        )  # Single result, not a list - created_at conflict

        reserved_results = validate_reserved_fields(MultipleErrorsModel)
        assert any(not r.success for r in reserved_results)  # _internal reserved

        type_results = validate_field_types(MultipleErrorsModel)
        assert any(not r.success for r in type_results)  # set unsupported


@pytest.mark.integration
class TestModelValidatorWithDataFlow:
    """Integration tests with real DataFlow instances."""

    def test_validator_functions_work_with_dataflow_context(self):
        """
        Verifies validator functions work in the context of a real DataFlow instance,
        even though automatic validation is not yet integrated.
        """
        db = DataFlow(":memory:")

        @dataclass
        class TestModel:
            id: str
            name: str

        # Manually validate the model
        result = validate_primary_key(TestModel)

        # Validator works correctly even with DataFlow instance present
        assert result.success is True

        # Model can be registered (no automatic validation yet)
        @db.model
        class ValidModel:
            id: str
            name: str

        models = db.get_models()
        assert "ValidModel" in models
