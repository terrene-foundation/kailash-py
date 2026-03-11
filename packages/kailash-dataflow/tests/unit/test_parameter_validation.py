"""
Unit Tests for Parameter Validation (Tier 1 - Layer 2)

Tests parameter-level validation for DataFlow's strict mode.
Validates node parameters at workflow.add_node() time to catch configuration errors early.

Test Coverage:
- CreateNode validation: STRICT_PARAM_101, 102, 103
- UpdateNode validation: STRICT_PARAM_104, 105, 106
- ListNode validation: STRICT_PARAM_107, 108, 109
- Validation result structure and error messages
"""

import pytest
from dataflow.validation.parameter_validator import (
    ValidationResult,
    validate_create_node_parameters,
    validate_list_node_parameters,
    validate_update_node_parameters,
)

# ==============================================================================
# Test Class 1: CreateNode Parameter Validation (STRICT_PARAM_101-103)
# ==============================================================================


@pytest.mark.unit
class TestCreateNodeParameterValidation:
    """Test CreateNode parameter validation rules."""

    def test_create_node_missing_id_parameter(self):
        """
        STRICT_PARAM_101: CreateNode without 'id' parameter should fail.

        Validates that the validator catches missing 'id' parameter at
        workflow.add_node() time instead of failing at runtime.
        """
        # Missing 'id' parameter
        parameters = {"name": "Alice", "email": "alice@example.com"}

        results = validate_create_node_parameters(
            node_type="UserCreateNode", node_id="create_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_101"
        assert "id" in errors[0].message.lower()
        assert "missing" in errors[0].message.lower()

    def test_create_node_with_auto_managed_field_created_at(self):
        """
        STRICT_PARAM_102: CreateNode with created_at should fail.

        DataFlow automatically manages created_at, so users should not
        set it manually.
        """
        parameters = {
            "id": "user-123",
            "name": "Alice",
            "created_at": "2025-01-01T00:00:00",  # Auto-managed field
        }

        results = validate_create_node_parameters(
            node_type="UserCreateNode", node_id="create_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_102"
        assert "created_at" in errors[0].message.lower()
        assert "auto-managed" in errors[0].message.lower()

    def test_create_node_with_auto_managed_field_updated_at(self):
        """
        STRICT_PARAM_102: CreateNode with updated_at should fail.

        DataFlow automatically manages updated_at, so users should not
        set it manually.
        """
        parameters = {
            "id": "user-123",
            "name": "Alice",
            "updated_at": "2025-01-01T00:00:00",  # Auto-managed field
        }

        results = validate_create_node_parameters(
            node_type="UserCreateNode", node_id="create_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_102"
        assert "updated_at" in errors[0].message.lower()
        assert "auto-managed" in errors[0].message.lower()

    def test_create_node_with_both_auto_managed_fields(self):
        """
        STRICT_PARAM_102: CreateNode with both auto-managed fields should fail.

        Should catch both created_at and updated_at violations.
        """
        parameters = {
            "id": "user-123",
            "name": "Alice",
            "created_at": "2025-01-01T00:00:00",  # Auto-managed
            "updated_at": "2025-01-01T00:00:00",  # Auto-managed
        }

        results = validate_create_node_parameters(
            node_type="UserCreateNode", node_id="create_user", parameters=parameters
        )

        # Should have 2 error results (one for each field)
        errors = [r for r in results if not r.success]
        assert len(errors) == 2
        assert all(e.error_code == "STRICT_PARAM_102" for e in errors)

    def test_create_node_type_mismatch_string_field(self):
        """
        STRICT_PARAM_103: CreateNode with wrong type (string field) should fail.

        Validates type checking when model_fields provided.
        """
        parameters = {"id": "user-123", "name": 123}  # Should be string, got int

        model_fields = {"name": str, "email": str}

        results = validate_create_node_parameters(
            node_type="UserCreateNode",
            node_id="create_user",
            parameters=parameters,
            model_fields=model_fields,
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_103"
        assert "type" in errors[0].message.lower()
        assert "name" in errors[0].message.lower()

    def test_create_node_type_mismatch_int_field(self):
        """
        STRICT_PARAM_103: CreateNode with wrong type (int field) should fail.

        Validates integer type checking.
        """
        parameters = {"id": "user-123", "age": "25"}  # Should be int, got string

        model_fields = {"age": int}

        results = validate_create_node_parameters(
            node_type="UserCreateNode",
            node_id="create_user",
            parameters=parameters,
            model_fields=model_fields,
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_103"

    def test_create_node_type_mismatch_bool_field(self):
        """
        STRICT_PARAM_103: CreateNode with wrong type (bool field) should fail.

        Validates boolean type checking.
        """
        parameters = {"id": "user-123", "active": "true"}  # Should be bool, got string

        model_fields = {"active": bool}

        results = validate_create_node_parameters(
            node_type="UserCreateNode",
            node_id="create_user",
            parameters=parameters,
            model_fields=model_fields,
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_103"

    def test_create_node_float_accepts_int(self):
        """
        STRICT_PARAM_103: CreateNode with int value for float field should pass.

        Float fields should accept int values (automatic coercion).
        """
        parameters = {"id": "user-123", "price": 100}  # Int is acceptable for float

        model_fields = {"price": float}

        results = validate_create_node_parameters(
            node_type="ProductCreateNode",
            node_id="create_product",
            parameters=parameters,
            model_fields=model_fields,
        )

        # Should pass (int acceptable for float)
        errors = [r for r in results if not r.success]
        assert len(errors) == 0

    def test_create_node_valid_parameters_passes(self):
        """
        CreateNode with valid parameters should pass validation.

        Tests the success case with all correct parameters.
        """
        parameters = {
            "id": "user-123",
            "name": "Alice",
            "email": "alice@example.com",
            "age": 30,
            "active": True,
        }

        model_fields = {"name": str, "email": str, "age": int, "active": bool}

        results = validate_create_node_parameters(
            node_type="UserCreateNode",
            node_id="create_user",
            parameters=parameters,
            model_fields=model_fields,
        )

        # Should have only success results
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0

    def test_create_node_without_model_fields_basic_validation(self):
        """
        CreateNode without model_fields should still validate basic rules.

        Should check for 'id' presence and auto-managed fields even without
        model field definitions.
        """
        parameters = {"id": "user-123", "name": "Alice"}

        results = validate_create_node_parameters(
            node_type="UserCreateNode",
            node_id="create_user",
            parameters=parameters,
            # No model_fields provided
        )

        # Should pass basic validation
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0


# ==============================================================================
# Test Class 2: UpdateNode Parameter Validation (STRICT_PARAM_104-106)
# ==============================================================================


@pytest.mark.unit
class TestUpdateNodeParameterValidation:
    """Test UpdateNode parameter validation rules."""

    def test_update_node_missing_filter_parameter(self):
        """
        STRICT_PARAM_104: UpdateNode without 'filter' parameter should fail.

        UpdateNode requires 'filter' to identify which records to update.
        """
        parameters = {"fields": {"name": "Alice Updated"}}

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_104"
        assert "filter" in errors[0].message.lower()
        assert "missing" in errors[0].message.lower()

    def test_update_node_missing_fields_parameter(self):
        """
        STRICT_PARAM_105: UpdateNode without 'fields' parameter should fail.

        UpdateNode requires 'fields' to specify what to update.
        """
        parameters = {"filter": {"id": "user-123"}}

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_105"
        assert "fields" in errors[0].message.lower()
        assert "missing" in errors[0].message.lower()

    def test_update_node_missing_both_filter_and_fields(self):
        """
        STRICT_PARAM_104-105: UpdateNode without both parameters should fail.

        Should catch both missing 'filter' and 'fields' violations.
        """
        parameters = {}

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have 2 error results
        errors = [r for r in results if not r.success]
        assert len(errors) == 2
        error_codes = {e.error_code for e in errors}
        assert "STRICT_PARAM_104" in error_codes
        assert "STRICT_PARAM_105" in error_codes

    def test_update_node_auto_managed_field_created_at_in_fields(self):
        """
        STRICT_PARAM_106: UpdateNode with created_at in 'fields' should fail.

        Cannot update auto-managed created_at field.
        """
        parameters = {
            "filter": {"id": "user-123"},
            "fields": {
                "name": "Alice",
                "created_at": "2025-01-01T00:00:00",  # Auto-managed
            },
        }

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_106"
        assert "created_at" in errors[0].message.lower()
        assert "auto-managed" in errors[0].message.lower()

    def test_update_node_auto_managed_field_updated_at_in_fields(self):
        """
        STRICT_PARAM_106: UpdateNode with updated_at in 'fields' should fail.

        Cannot update auto-managed updated_at field.
        """
        parameters = {
            "filter": {"id": "user-123"},
            "fields": {
                "name": "Alice",
                "updated_at": "2025-01-01T00:00:00",  # Auto-managed
            },
        }

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_106"
        assert "updated_at" in errors[0].message.lower()

    def test_update_node_both_auto_managed_fields_in_fields(self):
        """
        STRICT_PARAM_106: UpdateNode with both auto-managed fields should fail.

        Should catch both created_at and updated_at violations in 'fields'.
        """
        parameters = {
            "filter": {"id": "user-123"},
            "fields": {
                "name": "Alice",
                "created_at": "2025-01-01T00:00:00",  # Auto-managed
                "updated_at": "2025-01-01T00:00:00",  # Auto-managed
            },
        }

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have 2 error results
        errors = [r for r in results if not r.success]
        assert len(errors) == 2
        assert all(e.error_code == "STRICT_PARAM_106" for e in errors)

    def test_update_node_valid_parameters_passes(self):
        """
        UpdateNode with valid parameters should pass validation.

        Tests the success case with correct filter and fields structure.
        """
        parameters = {
            "filter": {"id": "user-123"},
            "fields": {"name": "Alice Updated", "email": "alice.updated@example.com"},
        }

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should have only success results
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0

    def test_update_node_fields_not_dict_still_validates_structure(self):
        """
        UpdateNode with non-dict 'fields' should still check for auto-managed fields.

        Validates that structure validation handles edge cases.
        """
        parameters = {"filter": {"id": "user-123"}, "fields": "invalid"}  # Not a dict

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        # Should pass structural validation (no auto-fields check on non-dict)
        # The actual execution would fail, but parameter validator just checks presence
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0


# ==============================================================================
# Test Class 3: ListNode Parameter Validation (STRICT_PARAM_107-109)
# ==============================================================================


@pytest.mark.unit
class TestListNodeParameterValidation:
    """Test ListNode parameter validation rules."""

    def test_list_node_filters_not_dict(self):
        """
        STRICT_PARAM_107: ListNode with non-dict 'filters' should fail.

        Filters parameter must be a dictionary.
        """
        parameters = {"filters": "invalid"}  # Should be dict

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_107"
        assert "filters" in errors[0].message.lower()
        assert "dict" in errors[0].message.lower()

    def test_list_node_limit_not_integer(self):
        """
        STRICT_PARAM_108: ListNode with non-integer 'limit' should fail.

        Limit parameter must be an integer.
        """
        parameters = {"limit": "10"}  # Should be int

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_108"
        assert "limit" in errors[0].message.lower()

    def test_list_node_limit_zero(self):
        """
        STRICT_PARAM_108: ListNode with limit=0 should fail.

        Limit must be >= 1.
        """
        parameters = {"limit": 0}  # Should be >= 1

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_108"

    def test_list_node_limit_negative(self):
        """
        STRICT_PARAM_108: ListNode with negative limit should fail.

        Limit must be >= 1.
        """
        parameters = {"limit": -5}  # Should be >= 1

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_108"

    def test_list_node_offset_not_integer(self):
        """
        STRICT_PARAM_109: ListNode with non-integer 'offset' should fail.

        Offset parameter must be an integer.
        """
        parameters = {"offset": "0"}  # Should be int

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_109"
        assert "offset" in errors[0].message.lower()

    def test_list_node_offset_negative(self):
        """
        STRICT_PARAM_109: ListNode with negative offset should fail.

        Offset must be >= 0.
        """
        parameters = {"offset": -10}  # Should be >= 0

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have error result
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].error_code == "STRICT_PARAM_109"

    def test_list_node_valid_parameters_passes(self):
        """
        ListNode with valid parameters should pass validation.

        Tests the success case with correct filters, limit, and offset.
        """
        parameters = {"filters": {"status": "active"}, "limit": 20, "offset": 0}

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should have only success results
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0

    def test_list_node_empty_parameters_passes(self):
        """
        ListNode with no parameters should pass validation.

        All parameters are optional for ListNode.
        """
        parameters = {}

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should pass (all parameters optional)
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0

    def test_list_node_only_filters_passes(self):
        """
        ListNode with only filters parameter should pass validation.
        """
        parameters = {"filters": {"status": "active"}}

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        # Should pass
        success_results = [r for r in results if r.success]
        assert len(success_results) > 0


# ==============================================================================
# Test Class 4: ValidationResult Structure
# ==============================================================================


@pytest.mark.unit
class TestValidationResultStructure:
    """Test ValidationResult helper class structure and attributes."""

    def test_validation_result_success_structure(self):
        """
        ValidationResult for success case should have correct structure.
        """
        result = ValidationResult(success=True)

        assert result.success is True
        assert result.error_code is None
        assert result.message is None
        assert result.solution == {}
        assert result.context == {}

    def test_validation_result_error_structure(self):
        """
        ValidationResult for error case should have correct structure.
        """
        result = ValidationResult(
            success=False,
            error_code="STRICT_PARAM_101",
            message="Missing required parameter 'id'",
            solution={"description": "Add 'id' parameter", "code_example": "..."},
            context={"node_type": "UserCreateNode", "node_id": "create_user"},
        )

        assert result.success is False
        assert result.error_code == "STRICT_PARAM_101"
        assert "Missing" in result.message
        assert "description" in result.solution
        assert "node_type" in result.context

    def test_create_node_validation_returns_list(self):
        """
        validate_create_node_parameters should return list of ValidationResult.
        """
        parameters = {"id": "user-123", "name": "Alice"}

        results = validate_create_node_parameters(
            node_type="UserCreateNode", node_id="create_user", parameters=parameters
        )

        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_update_node_validation_returns_list(self):
        """
        validate_update_node_parameters should return list of ValidationResult.
        """
        parameters = {"filter": {"id": "user-123"}, "fields": {"name": "Alice"}}

        results = validate_update_node_parameters(
            node_type="UserUpdateNode", node_id="update_user", parameters=parameters
        )

        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_list_node_validation_returns_list(self):
        """
        validate_list_node_parameters should return list of ValidationResult.
        """
        parameters = {"filters": {"status": "active"}}

        results = validate_list_node_parameters(
            node_type="UserListNode", node_id="list_users", parameters=parameters
        )

        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, ValidationResult) for r in results)
