"""
Unit tests for CARE-009: Constraint Inheritance Validation.

Tests the validate_inheritance() method in ConstraintValidator that ensures
child constraints are strictly tighter than or equal to parent constraints.
This is a fundamental security property of EATP.

Key Principle: A delegation can only REMOVE permissions, never ADD them.

Test categories:
1. Identical constraints (valid)
2. Tightened numeric limits (valid)
3. Widened numeric limits (rejected)
4. Tightened allowed actions (valid)
5. Widened allowed actions (rejected)
6. Preserved forbidden actions (valid)
7. Removed forbidden actions (rejected)
8. Tightened resources (valid)
9. Expanded resources (rejected)
10. Tightened time windows (valid)
11. Widened time windows (rejected)
12. Empty parent constraints (any child valid)
13. Multiple violations (all reported)
14. Nested constraints (recursively validated)
"""

from typing import Any, Dict

import pytest
from kaizen.trust.constraint_validator import (
    ConstraintValidator,
    ConstraintViolation,
    ValidationResult,
)


class TestConstraintInheritanceValidation:
    """Tests for validate_inheritance() method."""

    @pytest.fixture
    def validator(self) -> ConstraintValidator:
        """Create a ConstraintValidator instance."""
        return ConstraintValidator()

    # =========================================================================
    # Test 1: Identical constraints are valid
    # =========================================================================

    def test_identical_constraints_valid(self, validator: ConstraintValidator):
        """Identical parent and child constraints pass validation."""
        parent = {
            "cost_limit": 1000,
            "rate_limit": 100,
            "allowed_actions": ["read", "write"],
        }
        child = {
            "cost_limit": 1000,
            "rate_limit": 100,
            "allowed_actions": ["read", "write"],
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True
        assert len(result.violations) == 0

    def test_identical_constraints_with_resources(self, validator: ConstraintValidator):
        """Identical resource constraints pass validation."""
        parent = {"resources": ["data/**", "logs/*.log"]}
        child = {"resources": ["data/**", "logs/*.log"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 2: Tightened numeric limits are valid
    # =========================================================================

    def test_tightened_cost_limit_valid(self, validator: ConstraintValidator):
        """Lower cost_limit in child is accepted (tightening)."""
        parent = {"cost_limit": 10000}
        child = {"cost_limit": 5000}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_rate_limit_valid(self, validator: ConstraintValidator):
        """Lower rate_limit in child is accepted (tightening)."""
        parent = {"rate_limit": 100}
        child = {"rate_limit": 50}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_budget_limit_valid(self, validator: ConstraintValidator):
        """Lower budget_limit in child is accepted (tightening)."""
        parent = {"budget_limit": 5000}
        child = {"budget_limit": 2500}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_max_delegation_depth_valid(self, validator: ConstraintValidator):
        """Lower max_delegation_depth in child is accepted (tightening)."""
        parent = {"max_delegation_depth": 10}
        child = {"max_delegation_depth": 5}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_max_api_calls_valid(self, validator: ConstraintValidator):
        """Lower max_api_calls in child is accepted (tightening)."""
        parent = {"max_api_calls": 1000}
        child = {"max_api_calls": 500}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_multiple_numeric_valid(self, validator: ConstraintValidator):
        """Multiple tightened numeric limits are all accepted."""
        parent = {
            "cost_limit": 10000,
            "rate_limit": 100,
            "budget_limit": 5000,
            "max_api_calls": 1000,
        }
        child = {
            "cost_limit": 5000,
            "rate_limit": 50,
            "budget_limit": 2500,
            "max_api_calls": 500,
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 3: Widened numeric limits are rejected
    # =========================================================================

    def test_widened_cost_limit_rejected(self, validator: ConstraintValidator):
        """Higher cost_limit in child is rejected (widening attack)."""
        parent = {"cost_limit": 1000}
        child = {"cost_limit": 10000}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.COST_LOOSENED in result.violations
        assert "cost_limit" in result.details

    def test_widened_rate_limit_rejected(self, validator: ConstraintValidator):
        """Higher rate_limit in child is rejected (widening attack)."""
        parent = {"rate_limit": 50}
        child = {"rate_limit": 100}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.RATE_LIMIT_INCREASED in result.violations

    def test_widened_budget_limit_rejected(self, validator: ConstraintValidator):
        """Higher budget_limit in child is rejected (widening attack)."""
        parent = {"budget_limit": 1000}
        child = {"budget_limit": 5000}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.BUDGET_LIMIT_INCREASED in result.violations

    def test_widened_max_delegation_depth_rejected(
        self, validator: ConstraintValidator
    ):
        """Higher max_delegation_depth in child is rejected (widening attack)."""
        parent = {"max_delegation_depth": 5}
        child = {"max_delegation_depth": 10}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.MAX_DELEGATION_DEPTH_INCREASED in result.violations

    def test_widened_max_api_calls_rejected(self, validator: ConstraintValidator):
        """Higher max_api_calls in child is rejected (widening attack)."""
        parent = {"max_api_calls": 100}
        child = {"max_api_calls": 1000}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.MAX_API_CALLS_INCREASED in result.violations

    # =========================================================================
    # Test 4: Tightened allowed actions are valid
    # =========================================================================

    def test_tightened_actions_valid(self, validator: ConstraintValidator):
        """Fewer allowed_actions in child is accepted (tightening)."""
        parent = {"allowed_actions": ["read", "write", "delete"]}
        child = {"allowed_actions": ["read"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_actions_subset_valid(self, validator: ConstraintValidator):
        """Subset of allowed_actions in child is accepted."""
        parent = {"allowed_actions": ["read", "write", "delete", "admin"]}
        child = {"allowed_actions": ["read", "write"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_child_omits_allowed_actions_valid(self, validator: ConstraintValidator):
        """Child without allowed_actions inherits parent's (valid)."""
        parent = {"allowed_actions": ["read", "write"]}
        child = {}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 5: Widened allowed actions are rejected
    # =========================================================================

    def test_widened_actions_rejected(self, validator: ConstraintValidator):
        """Additional allowed_actions in child is rejected (widening attack)."""
        parent = {"allowed_actions": ["read"]}
        child = {"allowed_actions": ["read", "write"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.ACTION_RESTRICTION_REMOVED in result.violations
        assert "allowed_actions" in result.details
        assert "write" in result.details["allowed_actions"]

    def test_widened_actions_new_action_rejected(self, validator: ConstraintValidator):
        """Completely new action in child is rejected."""
        parent = {"allowed_actions": ["read", "write"]}
        child = {"allowed_actions": ["read", "write", "admin", "delete"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.ACTION_RESTRICTION_REMOVED in result.violations

    # =========================================================================
    # Test 6: Preserved forbidden actions are valid
    # =========================================================================

    def test_preserved_forbidden_actions_valid(self, validator: ConstraintValidator):
        """Parent's forbidden_actions preserved in child is valid."""
        parent = {"forbidden_actions": ["delete", "admin"]}
        child = {"forbidden_actions": ["delete", "admin"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_extended_forbidden_actions_valid(self, validator: ConstraintValidator):
        """Child adds more forbidden_actions (more restrictive) is valid."""
        parent = {"forbidden_actions": ["delete"]}
        child = {"forbidden_actions": ["delete", "admin", "write"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 7: Removed forbidden actions are rejected
    # =========================================================================

    def test_removed_forbidden_rejected(self, validator: ConstraintValidator):
        """Removing parent's forbidden_actions is rejected (widening attack)."""
        parent = {"forbidden_actions": ["delete", "admin"]}
        child = {"forbidden_actions": ["delete"]}  # "admin" removed

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.FORBIDDEN_ACTION_REMOVED in result.violations
        assert "forbidden_actions" in result.details
        assert "admin" in result.details["forbidden_actions"]

    def test_empty_forbidden_when_parent_has_rejected(
        self, validator: ConstraintValidator
    ):
        """Empty forbidden_actions when parent has some is rejected."""
        parent = {"forbidden_actions": ["delete", "admin"]}
        child = {"forbidden_actions": []}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.FORBIDDEN_ACTION_REMOVED in result.violations

    # =========================================================================
    # Test 8: Tightened resources are valid
    # =========================================================================

    def test_tightened_resources_valid(self, validator: ConstraintValidator):
        """Subset of resources in child is accepted (tightening)."""
        parent = {"resources": ["data/**", "logs/**"]}
        child = {"resources": ["data/users/*"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_tightened_resources_more_specific_valid(
        self, validator: ConstraintValidator
    ):
        """More specific resource pattern in child is accepted."""
        parent = {"resources": ["invoices/*"]}
        child = {"resources": ["invoices/small/*"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_child_omits_resources_valid(self, validator: ConstraintValidator):
        """Child without resources inherits parent's (valid)."""
        parent = {"resources": ["data/**"]}
        child = {}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_exact_same_resources_valid(self, validator: ConstraintValidator):
        """Identical resource patterns are valid."""
        parent = {"resources": ["data/users/*", "data/orders/*"]}
        child = {"resources": ["data/users/*", "data/orders/*"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 9: Expanded resources are rejected
    # =========================================================================

    def test_expanded_resources_rejected(self, validator: ConstraintValidator):
        """Superset of resources in child is rejected (widening attack)."""
        parent = {"resources": ["invoices/small/*"]}
        child = {"resources": ["invoices/*"]}  # Wider pattern

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.RESOURCES_EXPANDED in result.violations

    def test_expanded_resources_new_pattern_rejected(
        self, validator: ConstraintValidator
    ):
        """New resource pattern not in parent is rejected."""
        parent = {"resources": ["data/*"]}
        child = {"resources": ["data/*", "logs/*"]}  # logs/* not in parent

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.RESOURCES_EXPANDED in result.violations

    # =========================================================================
    # Test 10: Tightened time windows are valid
    # =========================================================================

    def test_tightened_time_window_valid(self, validator: ConstraintValidator):
        """Narrower time window in child is accepted (tightening)."""
        parent = {"time_window": "08:00-18:00"}
        child = {"time_window": "09:00-17:00"}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_same_time_window_valid(self, validator: ConstraintValidator):
        """Same time window is valid."""
        parent = {"time_window": "09:00-17:00"}
        child = {"time_window": "09:00-17:00"}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_child_omits_time_window_valid(self, validator: ConstraintValidator):
        """Child without time_window inherits parent's (valid)."""
        parent = {"time_window": "09:00-17:00"}
        child = {}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 11: Widened time windows are rejected
    # =========================================================================

    def test_widened_time_window_rejected(self, validator: ConstraintValidator):
        """Wider time window in child is rejected (widening attack)."""
        parent = {"time_window": "09:00-17:00"}
        child = {"time_window": "08:00-18:00"}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations

    def test_widened_time_window_earlier_start_rejected(
        self, validator: ConstraintValidator
    ):
        """Earlier start time in child is rejected."""
        parent = {"time_window": "09:00-17:00"}
        child = {"time_window": "08:00-17:00"}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations

    def test_widened_time_window_later_end_rejected(
        self, validator: ConstraintValidator
    ):
        """Later end time in child is rejected."""
        parent = {"time_window": "09:00-17:00"}
        child = {"time_window": "09:00-18:00"}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.TIME_WINDOW_EXPANDED in result.violations

    # =========================================================================
    # Test 12: Empty parent constraints allow any child
    # =========================================================================

    def test_empty_parent_any_child_valid(self, validator: ConstraintValidator):
        """No parent constraints means any child constraints are OK."""
        parent: Dict[str, Any] = {}
        child = {
            "cost_limit": 1000,
            "rate_limit": 100,
            "allowed_actions": ["read"],
            "forbidden_actions": ["delete"],
            "resources": ["data/*"],
            "time_window": "09:00-17:00",
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_empty_parent_empty_child_valid(self, validator: ConstraintValidator):
        """Empty parent and empty child is valid."""
        parent: Dict[str, Any] = {}
        child: Dict[str, Any] = {}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_none_parent_treated_as_empty(self, validator: ConstraintValidator):
        """None in parent constraint fields is treated as no constraint."""
        parent = {"cost_limit": None}
        child = {"cost_limit": 1000}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Test 13: Multiple violations are all reported
    # =========================================================================

    def test_multiple_violations_all_reported(self, validator: ConstraintValidator):
        """All violations in a single validation are reported."""
        parent = {
            "cost_limit": 1000,
            "rate_limit": 50,
            "allowed_actions": ["read"],
            "forbidden_actions": ["delete"],
        }
        child = {
            "cost_limit": 10000,  # Widened
            "rate_limit": 100,  # Widened
            "allowed_actions": ["read", "write"],  # Widened
            "forbidden_actions": [],  # Removed restriction
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert len(result.violations) >= 4

        # Check all violation types are present
        assert ConstraintViolation.COST_LOOSENED in result.violations
        assert ConstraintViolation.RATE_LIMIT_INCREASED in result.violations
        assert ConstraintViolation.ACTION_RESTRICTION_REMOVED in result.violations
        assert ConstraintViolation.FORBIDDEN_ACTION_REMOVED in result.violations

    def test_multiple_violations_details_present(self, validator: ConstraintValidator):
        """Details are provided for all violations."""
        parent = {"cost_limit": 1000, "rate_limit": 50}
        child = {"cost_limit": 2000, "rate_limit": 100}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert "cost_limit" in result.details
        assert "rate_limit" in result.details

    # =========================================================================
    # Test 14: Nested constraints are validated recursively
    # =========================================================================

    def test_nested_constraints_validated(self, validator: ConstraintValidator):
        """Nested dict constraints are validated recursively."""
        parent = {
            "api_limits": {
                "max_calls": 100,
                "per_endpoint": {"users": 50, "orders": 30},
            }
        }
        child = {
            "api_limits": {
                "max_calls": 50,  # Tightened - valid
                "per_endpoint": {"users": 25, "orders": 15},  # Tightened - valid
            }
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_nested_constraints_widened_rejected(self, validator: ConstraintValidator):
        """Widened nested constraint is rejected."""
        parent = {
            "api_limits": {
                "max_calls": 100,
            }
        }
        child = {
            "api_limits": {
                "max_calls": 200,  # Widened!
            }
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.NESTED_CONSTRAINT_WIDENED in result.violations

    def test_deeply_nested_constraints_validated(self, validator: ConstraintValidator):
        """Deeply nested constraints are validated."""
        parent = {
            "service_limits": {
                "api": {
                    "max_requests": 1000,
                }
            }
        }
        child = {
            "service_limits": {
                "api": {
                    "max_requests": 500,  # Tightened
                }
            }
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_child_omits_nested_inherits_valid(self, validator: ConstraintValidator):
        """Child omitting nested constraint inherits parent's (valid)."""
        parent = {
            "api_limits": {
                "max_calls": 100,
            }
        }
        child: Dict[str, Any] = {}  # Inherits parent's api_limits

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    # =========================================================================
    # Additional edge cases
    # =========================================================================

    def test_data_scopes_tightened_valid(self, validator: ConstraintValidator):
        """Subset of data_scopes in child is accepted."""
        parent = {"data_scopes": ["users", "orders", "products"]}
        child = {"data_scopes": ["users"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_data_scopes_expanded_rejected(self, validator: ConstraintValidator):
        """Superset of data_scopes in child is rejected."""
        parent = {"data_scopes": ["users"]}
        child = {"data_scopes": ["users", "orders"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.DATA_SCOPE_EXPANDED in result.violations

    def test_communication_targets_tightened_valid(
        self, validator: ConstraintValidator
    ):
        """Subset of communication_targets in child is accepted."""
        parent = {"communication_targets": ["api.internal.com", "db.internal.com"]}
        child = {"communication_targets": ["api.internal.com"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_communication_targets_expanded_rejected(
        self, validator: ConstraintValidator
    ):
        """Superset of communication_targets in child is rejected."""
        parent = {"communication_targets": ["api.internal.com"]}
        child = {"communication_targets": ["api.internal.com", "external.com"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert ConstraintViolation.COMMUNICATION_TARGETS_EXPANDED in result.violations

    def test_child_adds_new_constraint_type_valid(self, validator: ConstraintValidator):
        """Child adding constraint type not in parent is valid (adds restriction)."""
        parent = {"cost_limit": 1000}
        child = {
            "cost_limit": 500,
            "rate_limit": 50,  # New constraint - adds restriction
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_string_resources_normalized(self, validator: ConstraintValidator):
        """String resource is normalized to list."""
        parent = {"resources": "data/**"}  # String, not list
        child = {"resources": ["data/users/*"]}

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True


class TestConstraintValidatorIntegration:
    """Integration tests for constraint validation in real-world scenarios."""

    @pytest.fixture
    def validator(self) -> ConstraintValidator:
        """Create a ConstraintValidator instance."""
        return ConstraintValidator()

    def test_realistic_delegation_scenario(self, validator: ConstraintValidator):
        """Test a realistic delegation scenario."""
        # Parent agent: Full access analyst
        parent = {
            "cost_limit": 10000,
            "rate_limit": 1000,
            "allowed_actions": [
                "read_data",
                "analyze_data",
                "export_report",
                "admin",
            ],
            "forbidden_actions": ["delete_data"],
            "resources": ["analytics/**", "reports/**"],
            "time_window": "06:00-22:00",
            "data_scopes": ["sales", "marketing", "finance"],
        }

        # Child agent: Limited report generator
        child = {
            "cost_limit": 1000,  # Tighter budget
            "rate_limit": 100,  # Lower rate limit
            "allowed_actions": ["read_data", "export_report"],  # Fewer actions
            "forbidden_actions": ["delete_data", "admin"],  # More forbidden
            "resources": ["reports/*"],  # Narrower resources
            "time_window": "09:00-17:00",  # Narrower window
            "data_scopes": ["sales"],  # Narrower scope
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is True

    def test_widening_attack_detected(self, validator: ConstraintValidator):
        """Test that a widening attack is properly detected."""
        # Parent agent: Limited analyst
        parent = {
            "cost_limit": 1000,
            "allowed_actions": ["read"],
            "resources": ["public/*"],
        }

        # Attacker tries to widen permissions
        child = {
            "cost_limit": 100000,  # Much higher budget
            "allowed_actions": ["read", "write", "admin"],  # More actions
            "resources": ["*"],  # All resources
        }

        result = validator.validate_inheritance(parent, child)

        assert result.valid is False
        assert len(result.violations) >= 3
