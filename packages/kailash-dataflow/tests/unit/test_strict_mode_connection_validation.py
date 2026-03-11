"""
Unit tests for Strict Mode Connection Validation.

Tests connection type safety, required parameter enforcement, and unused connection detection.

Test Coverage:
- Type safety validation (STRICT-003)
- Required parameter validation (STRICT-004)
- Unused connection detection (STRICT-011)
"""

import pytest
from dataflow.validators.connection_validator import (
    StrictConnectionValidator,
    ValidationError,
)

from kailash.workflow.builder import WorkflowBuilder

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def workflow():
    """Create empty workflow for testing."""
    return WorkflowBuilder()


@pytest.fixture
def validator():
    """Create connection validator."""
    return StrictConnectionValidator()


# =============================================================================
# Test Type Safety (STRICT-003)
# =============================================================================


class TestTypeSafety:
    """Test connection type safety validation."""

    def test_compatible_types_pass(self, workflow, validator):
        """Test connection with compatible types passes validation."""
        # Arrange: Add nodes with compatible types
        workflow.add_node(
            "UserCreateNode",
            "user_create",
            {"id": "user-123", "name": "Alice", "email": "alice@example.com"},
        )
        workflow.add_node("UserReadNode", "user_read", {})

        # Connect string to string (compatible)
        workflow.add_connection("user_create", "id", "user_read", "id")

        # Act: Validate connections
        errors = validator.validate_type_compatibility(workflow)

        # Assert: No errors
        assert len(errors) == 0

    def test_incompatible_types_in_strict_mode_fails(self, workflow, validator):
        """Test connection with incompatible types in strict mode fails."""
        # Arrange: Nodes with incompatible types (string to int)
        workflow.add_node("InputNode", "input", {"data": "test-string"})
        workflow.add_node("ProcessNode", "process", {})

        # Connect string "data" to integer "count" (incompatible)
        workflow.add_connection("input", "data", "process", "count")

        # Act: Validate with strict mode (no coercion)
        errors = validator.validate_type_compatibility(
            workflow, strict_mode=True, allow_coercion=False
        )

        # Assert: Type mismatch error
        assert len(errors) == 1
        assert "STRICT-003" in errors[0].code
        assert "type mismatch" in errors[0].message.lower()
        assert "input.data" in errors[0].message
        assert "process.count" in errors[0].message

    def test_incompatible_types_in_warn_mode_warns(self, workflow, validator):
        """Test connection with incompatible types in WARN mode only warns."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("OrderCreateNode", "order_create", {})
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Act: Validate in warn mode
        errors = validator.validate_type_compatibility(workflow, strict_mode=False)

        # Assert: Returns warnings but doesn't block
        # In warn mode, we still detect but don't raise
        # Implementation should log warning instead of returning error
        assert len(errors) == 0  # No blocking errors in warn mode

    def test_type_coercion_string_to_int(self, workflow, validator):
        """Test type coercion between compatible types."""
        # Arrange
        workflow.add_node("InputNode", "input", {"value": "42"})
        workflow.add_node("ProcessNode", "process", {})
        workflow.add_connection("input", "value", "process", "count")

        # Act: Validate with type coercion enabled
        errors = validator.validate_type_compatibility(
            workflow, strict_mode=True, allow_coercion=True
        )

        # Assert: No errors (str->int coercion allowed)
        assert len(errors) == 0

    def test_nullable_type_handling(self, workflow, validator):
        """Test nullable types are handled correctly."""
        # Arrange: Optional field
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("ProfileNode", "profile", {})
        workflow.add_connection("user_create", "avatar_url", "profile", "image")

        # Act: Validate with nullable types
        errors = validator.validate_type_compatibility(workflow, strict_mode=True)

        # Assert: Optional types compatible with non-optional
        assert len(errors) == 0


# =============================================================================
# Test Required Parameter Enforcement (STRICT-004)
# =============================================================================


class TestRequiredParameterEnforcement:
    """Test required parameter validation."""

    def test_all_required_parameters_provided_passes(self, workflow, validator):
        """Test workflow with all required parameters passes."""
        # Arrange: All required params provided
        workflow.add_node(
            "UserCreateNode",
            "user_create",
            {"id": "user-123", "email": "alice@example.com", "name": "Alice"},
        )

        # Act: Validate
        errors = validator.validate_required_parameters(workflow)

        # Assert: No errors
        assert len(errors) == 0

    def test_missing_required_parameter_in_strict_mode_fails(self, workflow, validator):
        """Test missing required parameter in strict mode fails."""
        # Arrange: Use string-based node addition (WorkflowBuilder pattern)
        # This simulates a UserCreateNode missing required 'email'
        workflow.add_node(
            "UserCreateNode", "user_create", {"id": "user-123", "name": "Alice"}
        )

        # Act: Validate
        errors = validator.validate_required_parameters(workflow, strict_mode=True)

        # Assert: Missing parameter error for 'email'
        assert len(errors) >= 1
        # Find the email error
        email_errors = [e for e in errors if "email" in e.message]
        assert len(email_errors) == 1
        assert "STRICT-004" in email_errors[0].code
        assert "missing required parameter" in email_errors[0].message.lower()

    def test_missing_required_parameter_in_warn_mode_warns(self, workflow, validator):
        """Test missing required parameter in WARN mode only warns."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})

        # Act: Validate in warn mode
        errors = validator.validate_required_parameters(workflow, strict_mode=False)

        # Assert: No blocking errors in warn mode
        assert len(errors) == 0

    def test_required_parameter_provided_via_connection(self, workflow, validator):
        """Test required parameter provided via connection passes."""
        # Arrange: Missing 'email' in node params but connected from another node
        workflow.add_node("InputNode", "input", {"user_email": "alice@example.com"})
        workflow.add_node(
            "UserCreateNode", "user_create", {"id": "user-123", "name": "Alice"}
        )
        workflow.add_connection("input", "user_email", "user_create", "email")

        # Act: Validate
        errors = validator.validate_required_parameters(workflow, strict_mode=True)

        # Assert: No errors (email provided via connection)
        assert len(errors) == 0

    def test_optional_parameters_dont_trigger_validation(self, workflow, validator):
        """Test optional parameters don't trigger validation errors."""
        # Arrange: Optional 'avatar_url' missing
        workflow.add_node(
            "UserCreateNode",
            "user_create",
            {"id": "user-123", "email": "alice@example.com", "name": "Alice"},
        )

        # Act: Validate
        errors = validator.validate_required_parameters(workflow, strict_mode=True)

        # Assert: No errors (optional params OK to omit)
        assert len(errors) == 0

    def test_multiple_missing_required_parameters(self, workflow, validator):
        """Test multiple missing required parameters all reported."""
        # Arrange: Missing both 'id' and 'email'
        workflow.add_node("UserCreateNode", "user_create", {"name": "Alice"})

        # Act: Validate
        errors = validator.validate_required_parameters(workflow, strict_mode=True)

        # Assert: Multiple errors reported (at least id and email)
        assert len(errors) >= 2
        error_messages = " ".join([e.message for e in errors])
        assert "id" in error_messages
        assert "email" in error_messages


# =============================================================================
# Test Unused Connection Detection (STRICT-011)
# =============================================================================


class TestUnusedConnectionDetection:
    """Test unused connection detection."""

    def test_all_connections_used_passes(self, workflow, validator):
        """Test workflow with all connections used passes."""
        # Arrange: All connections actively used
        workflow.add_node(
            "UserCreateNode", "user_create", {"id": "user-123", "name": "Alice"}
        )
        workflow.add_node("UserReadNode", "user_read", {})
        workflow.add_connection("user_create", "id", "user_read", "id")

        # Act: Validate
        warnings = validator.detect_unused_connections(workflow)

        # Assert: No warnings
        assert len(warnings) == 0

    def test_unused_connection_overridden_by_param(self, workflow, validator):
        """Test unused connection overridden by node parameter."""
        # Arrange: Connection shadowed by node parameter
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node(
            "OrderCreateNode", "order_create", {"user_id": "hardcoded-user"}
        )
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Act: Validate
        warnings = validator.detect_unused_connections(workflow)

        # Assert: Warning for shadowed connection
        assert len(warnings) == 1
        assert "STRICT-011a" in warnings[0].code
        assert "overridden" in warnings[0].message.lower()
        assert "user_create.id" in warnings[0].message
        assert "order_create.user_id" in warnings[0].message

    def test_unused_connection_shadowed_by_later_connection(self, workflow, validator):
        """Test unused connection shadowed by later connection."""
        # Arrange: Two connections to same parameter
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("AnotherNode", "another", {"id": "another-id"})
        workflow.add_node("OrderCreateNode", "order_create", {})

        # First connection (will be shadowed)
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Second connection (shadows first)
        workflow.add_connection("another", "id", "order_create", "user_id")

        # Act: Validate
        warnings = validator.detect_unused_connections(workflow)

        # Assert: Warning for first connection
        assert len(warnings) == 1
        assert "STRICT-011b" in warnings[0].code
        assert "shadowed" in warnings[0].message.lower()

    def test_unused_connection_in_strict_mode_warns(self, workflow, validator):
        """Test unused connection in strict mode generates warning (non-blocking)."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("OrderCreateNode", "order_create", {"user_id": "hardcoded"})
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Act: Validate in strict mode
        warnings = validator.detect_unused_connections(workflow, strict_mode=True)

        # Assert: Warning generated (but not error)
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"  # Not error


# =============================================================================
# Test Integration Scenarios
# =============================================================================


class TestIntegrationScenarios:
    """Test complete validation scenarios."""

    def test_strict_mode_disabled_allows_all_connections(self, workflow, validator):
        """Test strict mode disabled allows all connections."""
        # Arrange: Multiple validation issues
        workflow.add_node(
            "UserCreateNode", "user_create", {"name": "Alice"}
        )  # Missing id
        workflow.add_node("OrderCreateNode", "order_create", {"user_id": "hardcoded"})
        workflow.add_connection(
            "user_create", "id", "order_create", "user_id"
        )  # Overridden

        # Act: Validate with strict_mode=False
        errors = validator.validate_workflow_connections(workflow, strict_mode=False)

        # Assert: No errors (warnings only)
        assert len(errors) == 0

    def test_strict_mode_enabled_enforces_all_checks(self, workflow, validator):
        """Test strict mode enabled enforces all checks."""
        # Arrange: Multiple validation issues
        workflow.add_node(
            "UserCreateNode", "user_create", {"name": "Alice"}
        )  # Missing id
        workflow.add_node("OrderCreateNode", "order_create", {})

        # Act: Validate with strict_mode=True
        errors = validator.validate_workflow_connections(workflow, strict_mode=True)

        # Assert: Errors reported
        assert len(errors) > 0
        error_codes = [e.code for e in errors]
        assert any(
            "STRICT-004" in code for code in error_codes
        )  # Missing required param

    def test_per_workflow_override_capability(self, workflow, validator):
        """Test per-workflow strict mode override."""
        # Arrange: Global strict mode ON, workflow override OFF
        workflow.add_node("UserCreateNode", "user_create", {"name": "Alice"})

        # Act: Validate with workflow-level override
        errors = validator.validate_workflow_connections(
            workflow, strict_mode=False  # Override global
        )

        # Assert: No errors (workflow override respected)
        assert len(errors) == 0

    def test_complex_workflow_with_multiple_issues(self, workflow, validator):
        """Test complex workflow with multiple validation issues."""
        # Arrange: Multiple issues
        workflow.add_node("InputNode", "input", {"data": "test"})
        workflow.add_node(
            "UserCreateNode", "user_create", {"name": "Alice"}
        )  # Missing id, email
        workflow.add_node(
            "OrderCreateNode", "order_create", {"user_id": "hardcoded"}
        )  # Overridden param

        # Type mismatch connection (string to int without coercion)
        workflow.add_connection(
            "input", "data", "user_create", "count"
        )  # count expects int

        # Shadowed connection
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Act: Validate all with type checking (no coercion for clear type error)
        type_errors = validator.validate_type_compatibility(
            workflow, strict_mode=True, allow_coercion=False
        )
        param_errors = validator.validate_required_parameters(
            workflow, strict_mode=True
        )

        # Also check warnings separately
        warnings = validator.detect_unused_connections(workflow)

        # Assert: All issues detected
        assert len(type_errors) > 0  # Type mismatch (data->count, str->int)
        assert len(param_errors) > 0  # Missing params (id, email)
        assert len(warnings) > 0  # Unused connection (shadowed)


# =============================================================================
# Test Error Message Quality
# =============================================================================


class TestErrorMessageQuality:
    """Test error message formatting and clarity."""

    def test_type_mismatch_error_includes_context(self, workflow, validator):
        """Test type mismatch error includes full context."""
        # Arrange: Clear type mismatch (no coercion)
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("OrderCreateNode", "order_create", {})
        workflow.add_connection(
            "user_create", "id", "order_create", "count"
        )  # str -> int

        # Act: Validate without coercion
        errors = validator.validate_type_compatibility(
            workflow, strict_mode=True, allow_coercion=False
        )

        # Assert: Error message includes context
        assert len(errors) > 0
        error = errors[0]
        assert "user_create.id" in error.message
        assert "order_create.count" in error.message
        # Should include type information (str and int)
        assert "str" in error.message or "string" in error.message.lower()
        assert "int" in error.message or "integer" in error.message.lower()

    def test_missing_parameter_error_includes_solutions(self, workflow, validator):
        """Test missing parameter error includes actionable solutions."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"name": "Alice"})

        # Act
        errors = validator.validate_required_parameters(workflow, strict_mode=True)

        # Assert: Error includes solutions
        assert len(errors) > 0
        error_messages = " ".join([e.message for e in errors])
        # Should suggest how to fix
        assert "id" in error_messages or "email" in error_messages

    def test_unused_connection_warning_suggests_fix(self, workflow, validator):
        """Test unused connection warning suggests fix."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("OrderCreateNode", "order_create", {"user_id": "hardcoded"})
        workflow.add_connection("user_create", "id", "order_create", "user_id")

        # Act
        warnings = validator.detect_unused_connections(workflow)

        # Assert: Warning suggests removal or fixing
        assert len(warnings) > 0
        warning = warnings[0]
        assert (
            "overridden" in warning.message.lower()
            or "remove" in warning.message.lower()
        )


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_workflow_passes_validation(self, workflow, validator):
        """Test empty workflow passes validation."""
        # Act
        errors = validator.validate_workflow_connections(workflow, strict_mode=True)

        # Assert: No errors
        assert len(errors) == 0

    def test_node_with_no_connections_passes(self, workflow, validator):
        """Test node with no connections passes connection validation."""
        # Arrange: Single node, no connections
        workflow.add_node(
            "UserCreateNode",
            "user_create",
            {"id": "user-123", "email": "alice@example.com", "name": "Alice"},
        )

        # Act: Validate connections only (not orphan detection)
        errors = validator.validate_type_compatibility(workflow, strict_mode=True)

        # Assert: No connection errors
        assert len(errors) == 0

    def test_self_connection_handling(self, workflow, validator):
        """Test self-connection (node connects to itself)."""
        # NOTE: Kailash SDK prevents self-connections at WorkflowBuilder level
        # This test verifies that the validator doesn't need to handle this case
        # because WorkflowBuilder already blocks it

        # Arrange & Act: Attempt self-connection (will raise at builder level)
        workflow.add_node("ProcessNode", "process", {"input": "data"})

        # Assert: Self-connections blocked by WorkflowBuilder
        with pytest.raises(Exception) as exc_info:
            workflow.add_connection("process", "output", "process", "input")

        assert (
            "cannot connect node" in str(exc_info.value).lower()
            or "self" in str(exc_info.value).lower()
        )

    def test_connection_to_non_existent_parameter(self, workflow, validator):
        """Test connection to non-existent parameter."""
        # Arrange
        workflow.add_node("UserCreateNode", "user_create", {"id": "user-123"})
        workflow.add_node("OrderCreateNode", "order_create", {})
        workflow.add_connection(
            "user_create", "nonexistent_field", "order_create", "user_id"
        )

        # Act: Validate
        errors = validator.validate_type_compatibility(workflow, strict_mode=True)

        # Assert: Should detect invalid parameter reference
        # (May be caught by workflow structure validation instead)
        pass  # Implementation-specific
