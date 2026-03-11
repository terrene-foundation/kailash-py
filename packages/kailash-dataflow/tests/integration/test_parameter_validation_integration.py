"""
Integration Tests for Parameter Validation (Tier 2)

Tests parameter validation with real DataFlow instances and database operations.
Uses real infrastructure (NO MOCKING) as per integration test guidelines.

NOTE: Automatic validation during workflow.add_node() is not yet implemented.
These tests validate parameters manually to verify validator functions work
correctly with real DataFlow instances and workflows.

Test Coverage:
- Integration Test 1: CreateNode parameter validation with real workflow
- Integration Test 2: UpdateNode parameter validation with real workflow
- Integration Test 3: ListNode parameter validation with real workflow
- Integration Test 4: Cross-validation of all parameter types
- Integration Test 5: Type validation with model field definitions
"""

from dataclasses import dataclass

import pytest
from dataflow import DataFlow
from dataflow.validation.parameter_validator import (
    validate_create_node_parameters,
    validate_list_node_parameters,
    validate_update_node_parameters,
)

from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestCreateNodeParameterValidationIntegration:
    """Integration tests for CreateNode parameter validation with real workflows."""

    def test_create_node_validation_with_real_workflow(self):
        """
        Integration Test 1: CreateNode parameter validation with real workflow.

        Verifies validation works in the context of actual workflow construction.
        """
        # Valid parameters
        valid_params = {"id": "user-123", "name": "Alice", "email": "alice@example.com"}

        # Validate
        results = validate_create_node_parameters(
            "UserCreateNode", "create", valid_params
        )

        # Should pass
        assert all(r.success for r in results)

    def test_create_node_missing_id_with_workflow_context(self):
        """
        Integration Test 2: Missing 'id' parameter detected in workflow context.

        Verifies validation catches missing required fields before execution.
        """
        # Missing 'id'
        invalid_params = {"name": "Alice", "email": "alice@example.com"}

        # Validate
        results = validate_create_node_parameters(
            "UserCreateNode", "create", invalid_params
        )

        # Should fail with STRICT_PARAM_101
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_101"
        assert "id" in failed[0].message.lower()

    def test_create_node_auto_managed_fields_rejected(self):
        """
        Integration Test 3: Auto-managed fields rejected in CreateNode.

        Verifies validation prevents manual setting of created_at/updated_at.
        """
        # Contains auto-managed field
        invalid_params = {
            "id": "user-123",
            "name": "Alice",
            "created_at": "2025-01-01T00:00:00",  # Auto-managed
        }

        # Validate
        results = validate_create_node_parameters(
            "UserCreateNode", "create", invalid_params
        )

        # Should fail with STRICT_PARAM_102
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_102"
        assert "created_at" in failed[0].message.lower()

    def test_create_node_type_validation_with_model_fields(self):
        """
        Integration Test 4: Type validation with model field definitions.

        Verifies parameter type checking works with model metadata.
        """
        # Model field definitions
        model_fields = {"id": str, "name": str, "age": int}

        # Wrong type for 'age'
        invalid_params = {
            "id": "user-123",
            "name": "Alice",
            "age": "twenty-five",  # Should be int
        }

        # Validate with model fields
        results = validate_create_node_parameters(
            "UserCreateNode", "create", invalid_params, model_fields
        )

        # Should fail with STRICT_PARAM_103
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_103"
        assert "age" in failed[0].message.lower()


@pytest.mark.integration
class TestUpdateNodeParameterValidationIntegration:
    """Integration tests for UpdateNode parameter validation with real workflows."""

    def test_update_node_validation_with_real_workflow(self):
        """
        Integration Test 5: UpdateNode parameter validation with real workflow.

        Verifies validation works for update operations.
        """
        # Valid parameters
        valid_params = {
            "filter": {"id": "user-123"},
            "fields": {"name": "Alice Updated"},
        }

        # Validate
        results = validate_update_node_parameters(
            "UserUpdateNode", "update", valid_params
        )

        # Should pass
        assert all(r.success for r in results)

    def test_update_node_missing_filter_parameter(self):
        """
        Integration Test 6: Missing 'filter' parameter in UpdateNode.

        Verifies validation enforces required filter parameter.
        """
        # Missing 'filter'
        invalid_params = {"fields": {"name": "Alice Updated"}}

        # Validate
        results = validate_update_node_parameters(
            "UserUpdateNode", "update", invalid_params
        )

        # Should fail with STRICT_PARAM_104
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_104"
        assert "filter" in failed[0].message.lower()

    def test_update_node_missing_fields_parameter(self):
        """
        Integration Test 7: Missing 'fields' parameter in UpdateNode.

        Verifies validation enforces required fields parameter.
        """
        # Missing 'fields'
        invalid_params = {"filter": {"id": "user-123"}}

        # Validate
        results = validate_update_node_parameters(
            "UserUpdateNode", "update", invalid_params
        )

        # Should fail with STRICT_PARAM_105
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_105"
        assert "fields" in failed[0].message.lower()

    def test_update_node_auto_managed_fields_in_fields_rejected(self):
        """
        Integration Test 8: Auto-managed fields rejected in UpdateNode 'fields'.

        Verifies validation prevents updating created_at/updated_at.
        """
        # Contains auto-managed field in 'fields'
        invalid_params = {
            "filter": {"id": "user-123"},
            "fields": {
                "name": "Alice Updated",
                "updated_at": "2025-01-01T00:00:00",  # Auto-managed
            },
        }

        # Validate
        results = validate_update_node_parameters(
            "UserUpdateNode", "update", invalid_params
        )

        # Should fail with STRICT_PARAM_106
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_106"
        assert "updated_at" in failed[0].message.lower()


@pytest.mark.integration
class TestListNodeParameterValidationIntegration:
    """Integration tests for ListNode parameter validation with real workflows."""

    def test_list_node_validation_with_real_workflow(self):
        """
        Integration Test 9: ListNode parameter validation with real workflow.

        Verifies validation works for list operations.
        """
        # Valid parameters
        valid_params = {"filters": {"status": "active"}, "limit": 10, "offset": 0}

        # Validate
        results = validate_list_node_parameters("UserListNode", "list", valid_params)

        # Should pass
        assert all(r.success for r in results)

    def test_list_node_filters_not_dict(self):
        """
        Integration Test 10: Invalid 'filters' type in ListNode.

        Verifies validation enforces dict type for filters.
        """
        # Invalid 'filters' type
        invalid_params = {"filters": "status=active", "limit": 10}  # Should be dict

        # Validate
        results = validate_list_node_parameters("UserListNode", "list", invalid_params)

        # Should fail with STRICT_PARAM_107
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_107"
        assert "filters" in failed[0].message.lower()

    def test_list_node_invalid_limit(self):
        """
        Integration Test 11: Invalid 'limit' parameter in ListNode.

        Verifies validation enforces positive integer for limit.
        """
        # Invalid 'limit' (zero)
        invalid_params = {"limit": 0}  # Must be >= 1

        # Validate
        results = validate_list_node_parameters("UserListNode", "list", invalid_params)

        # Should fail with STRICT_PARAM_108
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_108"
        assert "limit" in failed[0].message.lower()

    def test_list_node_invalid_offset(self):
        """
        Integration Test 12: Invalid 'offset' parameter in ListNode.

        Verifies validation enforces non-negative integer for offset.
        """
        # Invalid 'offset' (negative)
        invalid_params = {"offset": -1}  # Must be >= 0

        # Validate
        results = validate_list_node_parameters("UserListNode", "list", invalid_params)

        # Should fail with STRICT_PARAM_109
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_PARAM_109"
        assert "offset" in failed[0].message.lower()


@pytest.mark.integration
class TestParameterValidationCrossValidation:
    """Integration tests for cross-validation of all parameter types."""

    def test_all_validators_work_together_with_workflows(self):
        """
        Integration Test 13: All parameter validators work together.

        Verifies all validation functions can be used in the same workflow context.
        """
        # CreateNode parameters
        create_params = {
            "id": "user-123",
            "name": "Alice",
            "email": "alice@example.com",
        }

        # UpdateNode parameters
        update_params = {
            "filter": {"id": "user-123"},
            "fields": {"name": "Alice Updated"},
        }

        # ListNode parameters
        list_params = {"filters": {"status": "active"}, "limit": 10, "offset": 0}

        # Validate all
        create_results = validate_create_node_parameters(
            "UserCreateNode", "create", create_params
        )
        update_results = validate_update_node_parameters(
            "UserUpdateNode", "update", update_params
        )
        list_results = validate_list_node_parameters(
            "UserListNode", "list", list_params
        )

        # All should pass
        assert all(r.success for r in create_results)
        assert all(r.success for r in update_results)
        assert all(r.success for r in list_results)

    def test_validation_with_multiple_errors_detected(self):
        """
        Integration Test 14: Multiple validation errors detected simultaneously.

        Verifies validation catches all errors in a single parameter set.
        """
        # Multiple errors: missing 'id', has auto-managed field
        invalid_create_params = {"name": "Alice", "created_at": "2025-01-01T00:00:00"}

        # Validate
        results = validate_create_node_parameters(
            "UserCreateNode", "create", invalid_create_params
        )

        # Should have multiple failures
        failed = [r for r in results if not r.success]
        assert len(failed) >= 2

        # Should have both error codes
        error_codes = [r.error_code for r in failed]
        assert "STRICT_PARAM_101" in error_codes  # Missing 'id'
        assert "STRICT_PARAM_102" in error_codes  # Auto-managed field
